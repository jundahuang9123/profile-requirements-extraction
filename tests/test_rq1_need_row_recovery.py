import json
import pytest
from test_resume_discussions import setup
from requirement_reuse_service.llm.client import LLMError, OutputTokenLimitError, validate_json_payload
from requirement_reuse_service.workflow import needs
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow.models import RunRequest, SnapshotRequest, SourceRequest
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow.evidence import register_source
from test_rq1_need_assessment import FullNeedsClient
from requirement_reuse_service.workflow.need_recovery import SPECS


ROWS = {
    'NeedStatements':lambda i:{'group_id':i,'statement':'Users can identify a title.','members':[{'member_id':'m','expresses_need':True}]},
    'NeedGrounding':lambda i:{'group_id':i,'supported':True,'no_added_actor':True,'no_added_obligation':True,'no_added_condition':True,'no_added_scope':True,'rationale':'Source-supported.'},
    'NeedMembership':lambda i:{'member_id':i,'expresses_need':True,'rationale':'Same need.'},
    'ProposalSupport':lambda i:{'proposal_id':i,'support':'supported','supporting_evidence_ids':['q'],'obligation_stated':False,'rationale':'Supported.'},
    'NeedClassifications':lambda i:{'need_id':i,'classification':'domain','base_need_ids':[],'rationale':'Domain.'},
    'NeedUseCaseLinks':lambda i:{'need_id':i,'links':[]},
    'UseCaseCritic':lambda i:{'link_id':i,'keep':True,'rationale':'Necessary.'},
}

STEPS = {'NeedStatements':'need_statement','NeedGrounding':'need_statement','NeedMembership':'need_membership',
         'ProposalSupport':'proposal_support','NeedClassifications':'classification',
         'NeedUseCaseLinks':'scoping','UseCaseCritic':'scope_critic'}


@pytest.mark.parametrize('name', list(ROWS))
def test_transport_resume_preserves_accepted_rows_and_correction_budget(setup, name):
    store, run, _ = setup
    field, id_field, input_field = SPECS[name]
    payload = {input_field:{i:{} for i in ('good','bad')}}
    if input_field == 'links': payload = {'links':[{'link_id':i} for i in ('good','bad')]}
    class Client:
        def __init__(self): self.calls=[]; self.outage=True
        def generate_structured(self, **kw):
            data=json.loads(kw['user']); self.calls.append(data)
            ids=list(data[input_field]) if isinstance(data[input_field],dict) else [r[id_field] for r in data[input_field]]
            if len(self.calls)==2 and self.outage: raise LLMError('HTTP 503 unavailable (simulated).')
            rows=[ROWS[name](i) for i in ids]
            if len(self.calls)==1:
                next(r for r in rows if r[id_field]=='bad')[id_field]=None
            return validate_json_payload(json.dumps({field:rows}), kw['output_model'])
    client=Client(); model=getattr(needs,name)
    args=(store,run,STEPS[name],payload,model,'Offline transport test.',client)
    with pytest.raises(LLMError, match='HTTP 503'): needs.cached_generation(*args)
    chunk=next(iter(store.get('run',run['run_id'])['need_chunks'].values()))
    assert chunk['status']=='transport_failed'
    assert len(chunk['attempts'])==1 and set(chunk['accepted_rows'])=={'good'}
    assert chunk['fallback_rows']=={} and 'output' not in chunk
    assert chunk['transport_failures'][-1]['error_class']=='LLMError'
    assert chunk['transport_failures'][-1]['requested_ids']==['bad']
    client.outage=False
    result=needs.cached_generation(*args)
    assert {getattr(row,id_field) for row in getattr(result,field)}=={'good','bad'}
    assert result._fallbacks=={} and len(client.calls)==3
    pending=client.calls[-1][input_field]
    assert (list(pending) if isinstance(pending,dict) else [r[id_field] for r in pending])==['bad']
    chunk=next(iter(store.get('run',run['run_id'])['need_chunks'].values()))
    assert chunk['status']=='completed' and len(chunk['attempts'])==2


@pytest.mark.parametrize('fault', list(ROWS))
@pytest.mark.parametrize('error', ['HTTP 401 unauthorized', 'HTTP 503 unavailable', 'Request timeout'])
def test_provider_outage_fails_run_and_resume_checks_rows_for_all_seven_steps(setup, fault, error):
    store, _, _ = setup
    source=register_source(store, SourceRequest(
        artifact=ArtifactPayload(name='synthetic-title-needs.md', content='\n'.join(
            f'Each dataset describes its title (fixture {i}).' for i in range(11))),
        source_role='stakeholder_need'))
    snapshot=engine.freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']],
        user_tasks=[{'id':'CQ-1','statement':'Which datasets have a title?','kind':'competency_question'}]))
    class Client(FullNeedsClient):
        def __init__(self): super().__init__(); self.outage=True
        def generate_structured(self, **kw):
            name=kw['output_model'].__name__; data=json.loads(kw['user'])
            if name==fault and self.outage:
                self.calls.append((name,data)); raise LLMError(error+' (simulated).')
            if name in {'NeedMembership','NeedClassifications','NeedUseCaseLinks','UseCaseCritic'}:
                self.calls.append((name,data))
                if name=='NeedMembership': raw={'checks':[ROWS[name](i) for i in data['members']]}
                elif name=='NeedClassifications': raw={'classifications':[ROWS[name](i) for i in data['needs']]}
                elif name=='NeedUseCaseLinks': raw={'needs':[{'need_id':i,'links':[
                    {'task_id':'CQ-1','justification':'Title is needed for this declared task.'}]} for i in data['needs']]}
                else: raw={'decisions':[ROWS[name](row['link_id']) for row in data['links']]}
                return kw['output_model'].model_validate(raw)
            return super().generate_structured(**kw)
    client=Client()
    run=engine.new_run(store, RunRequest(snapshot_id=snapshot['snapshot_id'],strategy='multi_agent',
        base_profile_id='dcat-ap-2.0.1',base_check=False,scoping='use_cases',discussion='on_request',
        role_ids=['consumer_discovery','publisher_feasibility']))
    engine.execute_run(store,run['run_id'],client)
    failed=store.get('run',run['run_id'])
    assert failed['status']=='failed', failed['diagnostics']
    assert any(error in message for message in failed['diagnostics'])
    chunks=[c for c in failed['need_chunks'].values() if c['status']=='transport_failed']
    assert len(chunks)==1 and chunks[0]['attempts']==[] and chunks[0]['fallback_rows']=={}
    assert chunks[0]['transport_failures'][-1]['error_class']=='LLMError'
    assert not any(c.get('fallback_rows') for c in failed['need_chunks'].values())
    mark=len(client.calls); client.outage=False
    engine.execute_run(store,run['run_id'],client)
    completed=store.get('run',run['run_id'])
    assert completed['status']=='awaiting_human', completed['diagnostics']
    assert any(name==fault for name,_ in client.calls[mark:])
    assert completed['active_revision_ids'] and completed['need_steps']['assessment']['assessed_count']==1
    assert not any(c.get('fallback_rows') for c in completed['need_chunks'].values())
    assert not any('not_checked' in flag or flag=='not_classified'
                   for r in completed['requirements'] for flag in r['processing_flags'])


@pytest.mark.parametrize('failure', ['cutoff','input_bound'])
def test_cutoff_and_deterministic_input_bound_still_exhaust_bounded_recovery(setup, failure):
    store,run,_=setup
    class Client:
        def __init__(self): self.calls=0
        def generate_structured(self, **kw):
            self.calls+=1
            raise OutputTokenLimitError('Output truncated (simulated).')
    client=Client()
    payload={'needs':{'n':{'statement':'x' * (25000 if failure=='input_bound' else 1)}}}
    result=needs.cached_generation(store,run,'classification',payload,needs.NeedClassifications,
                                   'Offline bound test.',client)
    assert 'n' in result._fallbacks and client.calls==(0 if failure=='input_bound' else 2)
    chunk=next(iter(store.get('run',run['run_id'])['need_chunks'].values()))
    assert chunk['status']=='completed_with_fallbacks' and len(chunk['attempts'])==2
    assert not chunk.get('transport_failures')


@pytest.mark.parametrize('name',list(ROWS))
def test_invalid_row_twice_retains_good_row_corrects_only_bad_and_replays(setup,name):
    store,run,_=setup;field,id_field,input_field=SPECS[name];model=getattr(needs,name)
    payload={input_field:{i:{} for i in ('good','bad')}}
    if input_field=='links': payload={'links':[{'link_id':i} for i in ('good','bad')]}
    class InvalidRow:
        def __init__(self): self.calls=[]
        def generate_structured(self,**kw):
            request=json.loads(kw['user']);self.calls.append(request)
            ids=list(request[input_field]) if isinstance(request[input_field],dict) else [r[id_field] for r in request[input_field]]
            rows=[ROWS[name](i) for i in ids]
            for row in rows:
                if row[id_field]=='bad': row[id_field]=None
            return validate_json_payload(json.dumps({field:rows}),kw['output_model'])
    client=InvalidRow()
    step={'NeedStatements':'need_statement','NeedGrounding':'need_statement','NeedMembership':'need_membership',
          'ProposalSupport':'proposal_support','NeedClassifications':'classification','NeedUseCaseLinks':'scoping','UseCaseCritic':'scope_critic'}[name]
    accounting_messages={'NeedStatements':'Account for each offered group exactly once.',
        'NeedGrounding':'Critic must account for every offered group exactly once.',
        'NeedMembership':'Check every offered member exactly once.',
        'ProposalSupport':'Judge each offered proposal exactly once.',
        'NeedClassifications':'Classify every offered need exactly once.',
        'NeedUseCaseLinks':'Account for every offered need exactly once.',
        'UseCaseCritic':'Decide every offered link ID exactly once.'}
    def validate(result):
        ids={getattr(row,id_field) for row in getattr(result,field)}
        return [] if ids=={'good','bad'} else [accounting_messages[name]]
    result=needs.cached_generation(store,run,step,payload,model,'Offline row test.',client,validate)
    assert 'bad' in result._fallbacks and 'good' not in result._fallbacks
    assert any(getattr(r,id_field)=='good' for r in getattr(result,field))
    corrected=client.calls[1][input_field]
    assert (list(corrected) if isinstance(corrected,dict) else [r[id_field] for r in corrected])==['bad']
    replay=needs.cached_generation(store,run,step,payload,model,'Offline row test.',client)
    assert replay._fallbacks==result._fallbacks and len(client.calls)==2
    chunk=next(iter(store.get('run',run['run_id'])['need_chunks'].values()))
    assert chunk['status']=='completed_with_fallbacks' and set(chunk['accepted_rows'])=={'good'}


@pytest.mark.parametrize('fault',['ProposalSupport','NeedStatements','NeedGrounding','NeedClassifications','NeedUseCaseLinks','UseCaseCritic'])
def test_full_pipeline_fallback_reaches_review_and_resume_does_not_regenerate(setup,fault):
    store,source,_=setup
    snapshot=engine.freeze_snapshot(store,SnapshotRequest(
        source_version_ids=store.get('snapshot',source['snapshot_id'])['source_version_ids'],
        user_tasks=[{'id':'CQ-1','statement':'Which datasets have a title?','kind':'competency_question'}]))
    class FaultClient(FullNeedsClient):
        def __init__(self): super().__init__();self.target=None
        def generate_structured(self,**kw):
            name=kw['output_model'].__name__;data=json.loads(kw['user'])
            if name=='NeedClassifications':
                self.calls.append((name,data));answer=kw['output_model'].model_validate({'classifications':[
                    {'need_id':i,'classification':'domain','base_need_ids':[],'rationale':'Offline domain judgement.'} for i in data['needs']]})
            elif name=='NeedUseCaseLinks':
                self.calls.append((name,data));answer=kw['output_model'].model_validate({'needs':[
                    {'need_id':i,'links':[{'task_id':'CQ-1','justification':'Title needed to answer this declared task.'}]} for i in data['needs']]})
            elif name=='UseCaseCritic':
                self.calls.append((name,data));answer=kw['output_model'].model_validate({'decisions':[
                    {'link_id':i['link_id'],'keep':True,'rationale':'Offline necessary link.'} for i in data['links']]})
            else: answer=super().generate_structured(**kw)
            if name==fault:
                field,id_field,_=SPECS[name];raw=answer.model_dump(mode='json')
                if self.target is None: self.target=raw[field][0][id_field]
                for row in raw[field]:
                    if row[id_field]==self.target: row[id_field]=None
                return validate_json_payload(json.dumps(raw),kw['output_model'])
            return answer
    client=FaultClient()
    run=engine.new_run(store,RunRequest(snapshot_id=snapshot['snapshot_id'],strategy='multi_agent',
        base_profile_id='dcat-ap-2.0.1',base_check=False,scoping='use_cases',discussion='on_request',
        role_ids=['consumer_discovery','publisher_feasibility']))
    engine.execute_run(store,run['run_id'],client)
    saved=store.get('run',run['run_id'])
    assert saved['status']=='awaiting_human',saved['diagnostics']
    assert any(c.get('fallback_rows') for c in saved['need_chunks'].values())
    if fault in {'NeedUseCaseLinks','UseCaseCritic'}:
        assert saved['active_revision_ids']
        assert not any(a['reason']=='no_use_case' for a in saved['set_aside_observations'])
        assert any('scoping_not_checked' in r['processing_flags'] for r in saved['requirements'])
    before=len(client.calls);engine.execute_run(store,run['run_id'],client)
    assert len(client.calls)==before
