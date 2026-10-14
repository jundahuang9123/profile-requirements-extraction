import json
import pytest
from test_resume_discussions import setup
from requirement_reuse_service.llm.client import validate_json_payload
from requirement_reuse_service.workflow import needs
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow.models import RunRequest, SnapshotRequest
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
