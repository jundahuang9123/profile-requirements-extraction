"""Bounded row-level correction and durable conservative fallbacks.

Valid rows are committed before another generation. Schema-invalid complete JSON
can be inspected row by row, but truncated output is never used. No fallback is a
positive semantic judgement or human acceptance.
"""
from collections import Counter
from copy import deepcopy
import time
from typing import get_args
from pydantic import ValidationError
from ..llm.client import LLMError, OutputTokenLimitError, OutputValidationError
from .storage import canonical, digest, now
from .call_log import recorded_calls

POLICY = 'rq1-needs-row-recovery-v2'


class InputBoundError(ValueError):
    """Deterministic local failure; a retry cannot change the input size."""
SPECS = {
    'FAPreservation': ('checks','group_id','groups'),
    'FAScopeResult': ('decisions', 'need_id', 'needs'),
    'DatasetCategories':('units','evidence_id','evidence'),
    'NeedEquivalence':('decisions','need_id','needs'),
    'NeedStatements':('needs','group_id','groups'),
    'NeedGrounding':('checks','group_id','groups'),
    'NeedMembership':('checks','member_id','members'),
    'ProposalSupport':('proposals','proposal_id','proposals'),
    'NeedClassifications':('classifications','need_id','needs'),
    'ProfileScope':('decisions','need_id','needs'),
    'NeedApplicability':('decisions','need_id','needs'),
    'NeedUseCaseLinks':('needs','need_id','needs'),
    'UseCaseCritic':('decisions','link_id','links'),
}


def subset(payload, input_field, id_field, ids):
    value=deepcopy(payload)
    if isinstance(payload[input_field],dict):
        value[input_field]={k:v for k,v in payload[input_field].items() if k in ids}
    else: value[input_field]=[r for r in payload[input_field] if r[id_field] in ids]
    if 'proposed_needs' in value:
        value['proposed_needs']['needs']=[r for r in value['proposed_needs']['needs'] if r['group_id'] in ids]
    if 'previous_rewrites' in value:
        value['previous_rewrites']={k:v for k,v in value['previous_rewrites'].items() if k in ids}
    return value


def fallback_row(name, identifier):
    why='Technical output failure: no checked judgement; human review required.'
    if name=='FAScopeResult': return {'need_id':identifier,'support':'uncertain','serves':'unresolved','nature':'uncertain','actor':'','task':'','example':'','rationale':why,'evidence_ids':[]}
    if name=='NeedClassifications': return {'need_id':identifier,'classification':'domain','base_need_ids':[],'rationale':why}
    if name=='NeedUseCaseLinks': return {'need_id':identifier,'links':[]}
    if name=='UseCaseCritic': return {'link_id':identifier,'keep':False,'rationale':why}
    if name=='NeedMembership': return {'member_id':identifier,'expresses_need':False,'rationale':why}
    return None  # Writer/critic/proposal callers handle missing rows visibly.


def generation(store, run, step, payload, output_model, system, client, validate, policy=None):
    """policy: for a step that is not a needs policy of its own (profile_scope_confirmation,
    fa_scope_confirmation, proposal_support_confirmation), the policy it belongs to; by default the run's
    needs policy for the step."""
    from ..llm.step_models import for_contract, model_identity
    client = for_contract(client, output_model)
    model = model_identity(client)
    field,id_field,input_field=SPECS[output_model.__name__]
    offered=(list(payload[input_field]) if isinstance(payload[input_field],dict)
             else [r[id_field] for r in payload[input_field]])
    if policy is None: policy=run.get('needs_policies',{}).get(step)
    key=digest([POLICY,step,policy,system,payload,output_model.model_json_schema(),model])
    saved=store.get_run_part_entry(run['run_id'],'need_chunks',key)
    if saved and saved.get('checkpoint_hash')!=digest({k:v for k,v in saved.items() if k!='checkpoint_hash'}):
        raise ValueError('Need row checkpoint integrity mismatch.')
    def materialize(audit):
        answer=output_model.model_validate(audit['output'])
        object.__setattr__(answer,'_fallbacks',deepcopy(audit.get('fallback_rows',{})))
        if output_model.__name__ == 'DatasetCategories':
            object.__setattr__(answer,'_attempts',deepcopy(audit.get('attempts',[])))
        return answer
    if saved and saved['status'] in {'completed','completed_with_fallbacks'}: return materialize(saved)
    if client is None: raise ValueError('Need processing requires a configured model or scripted offline client.')
    audit=deepcopy(saved) if saved else {'step':step,'policy_version':policy,
        'recovery_policy':POLICY,'input_hash':digest(payload),
        'provider':client.describe() if hasattr(client, 'describe') else model,'status':'running','attempts':[],
        'accepted_rows':{},'fallback_rows':{}}
    audit.pop('checkpoint_hash',None)
    def save():
        audit['checkpoint_hash']=digest({k:v for k,v in audit.items() if k!='checkpoint_hash'})
        store.mutate(run['run_id'],None,'need_rows_saved',lambda r:r['need_chunks'].__setitem__(key,deepcopy(audit)))
    row_model=get_args(output_model.model_fields[field].annotation)[0]
    audit['status']='running'
    accepted=audit['accepted_rows']
    errors=audit['attempts'][-1].get('validation_errors',{}) if audit['attempts'] else {}
    while len(audit['attempts'])<2 and set(offered)-set(accepted):
        pending=[i for i in offered if i not in accepted]
        request=subset(payload,input_field,id_field,set(pending))
        correction=(' Correct only these failing rows; valid rows from the prior response are already saved. Errors: '+canonical(errors)) if audit['attempts'] else ''
        started=time.monotonic(); raw=None; technical=None; calls=[]
        try:
            limit=48000 if output_model.__name__=='NeedGrounding' else 24000
            if len(canonical(request))>limit:
                raise InputBoundError('Input bound exceeded; no provider request was sent.')
            with recorded_calls(calls):
                answer=client.generate_structured(system=system+correction,user=canonical(request),
                    output_model=output_model,max_tokens=8000 if not audit['attempts'] else 12000)
            raw=answer.model_dump(mode='json')
        except OutputValidationError as exc:
            raw=exc.parsed_payload; technical=str(exc)
        except (OutputTokenLimitError, InputBoundError) as exc:
            technical=type(exc).__name__+': '+str(exc)
        except LLMError as exc:
            # Provider availability says nothing about the offered rows. Preserve
            # accepted answers and correction budget, then retry unfinished rows
            # on Resume rather than recording permanent semantic fallbacks.
            audit['status']='transport_failed'
            audit.setdefault('transport_failures',[]).append({
                'error_class':type(exc).__name__, 'error':str(exc),
                'requested_ids':pending, 'seconds':time.monotonic()-started,
                'saved_at':now(), 'call_ids':calls})
            save()
            raise
        # Unexpected runtime errors are implementation defects, not a reason to
        # manufacture a fallback. Let them fail visibly for repair.
        errors={i:[] for i in pending}; typed={}; unexpected=[]
        rows=raw.get(field,[]) if isinstance(raw,dict) else []
        if not isinstance(rows,list): rows=[]
        counts=Counter(r.get(id_field) for r in rows if isinstance(r,dict) and isinstance(r.get(id_field),str))
        for row in rows:
            identifier=row.get(id_field) if isinstance(row,dict) else None
            if identifier not in errors:
                unexpected.append(identifier);continue
            if counts[identifier]!=1:
                errors[identifier].append('Repeated row ID.');continue
            try: typed[identifier]=row_model.model_validate(row)
            except ValidationError as exc:
                errors[identifier].extend(str(e['loc'])+': '+e['type'] for e in exc.errors(include_input=False,include_context=False))
        for identifier in pending:
            if identifier not in typed and not errors[identifier]: errors[identifier].append(technical or 'Row missing or invalid.')
        valid_container=output_model.model_validate({field:[r.model_dump(mode='json') for r in typed.values()]})
        for error in validate(valid_container) if validate else []:
            matched=[i for i in pending if error.startswith(i+':')]
            if matched:
                for identifier in matched: errors[identifier].append(error)
            elif not error.startswith(('Account ','Judge ','Critic must account ','Check every ','Decide every ','Classify every ')):
                # Unknown global constraints must not be guessed away.
                for identifier in pending: errors[identifier].append(error)
        for identifier,row in typed.items():
            if not errors[identifier]: accepted[identifier]=row.model_dump(mode='json')
        errors={i:e for i,e in errors.items() if e}
        audit['attempts'].append({'attempt':len(audit['attempts'])+1,'requested_ids':pending,
            'validation_errors':errors,'unexpected_ids':unexpected,'error':technical,
            'output':raw,'seconds':time.monotonic()-started,'call_ids':calls})
        save()
    rows=[]
    for identifier in offered:
        if identifier in accepted: rows.append(accepted[identifier]);continue
        previous=(audit['attempts'][-1].get('validation_errors',{}).get(identifier,[]) if audit['attempts'] else [])
        audit['fallback_rows'][identifier]={'policy_version':POLICY,'status':'not_checked',
            'reason':'; '.join(previous) or 'Correction budget exhausted.','saved_at':now()}
        row=fallback_row(output_model.__name__,identifier)
        if row is not None: rows.append(row)
    audit.update(output={field:rows},exhausted=bool(audit['fallback_rows']),
        status='completed_with_fallbacks' if audit['fallback_rows'] else 'completed')
    save()
    return materialize(audit)
