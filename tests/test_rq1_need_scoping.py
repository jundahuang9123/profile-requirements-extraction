import json
from test_resume_discussions import setup
from test_rq1_need_grouping import need_inputs, NeedsClient
from requirement_reuse_service.workflow import needs
from requirement_reuse_service.workflow.engine import freeze_snapshot
from requirement_reuse_service.workflow.models import SnapshotRequest


class ScopeClient(NeedsClient):
    def generate_structured(self, **kwargs):
        name=kwargs['output_model'].__name__; data=json.loads(kwargs['user'])
        if name=='NeedUseCaseLinks':
            self.calls.append((name,data))
            return kwargs['output_model'].model_validate({'needs':[
                {'need_id':identifier,'links':[{'task_id':'CQ-1','justification':'Needed to identify its title.'}] if index else []}
                for index,identifier in enumerate(data['needs'])]})
        if name=='UseCaseCritic':
            self.calls.append((name,data))
            return kwargs['output_model'].model_validate({'decisions':[
                {'link_id':link['link_id'],'keep':False,'rationale':'Relatedness is not necessity.'} for link in data['links']]})
        return super().generate_structured(**kwargs)


def proposals(setup):
    store,run,candidates=need_inputs(setup)
    output,_=needs.write_needs(store,run,[candidates],NeedsClient(),None)
    variants=[]
    for index in range(2):
        n=output[0].model_copy(deep=True);n.requirement_id=f'need-{index}';needs.refresh_need(n);variants.append(n)
    snapshot=freeze_snapshot(store,SnapshotRequest(source_version_ids=store.get('snapshot',run['snapshot_id'])['source_version_ids'],
        user_tasks=[{'id':'CQ-1','kind':'competency_question','statement':'Which datasets cover this region?'}]))
    run['snapshot_id']=snapshot['snapshot_id'];run['request']['scoping']='use_cases'
    return store,run,candidates,variants


def test_no_link_and_weak_link_set_aside(setup):
    store,run,candidates,variants=proposals(setup);client=ScopeClient()
    assert needs.scope_needs(store,run,variants,candidates,client)==[]
    assert len([a for a in store.get('run',run['run_id'])['set_aside_observations'] if a['reason']=='no_use_case'])==2
    audit=store.get('run',run['run_id'])['need_steps']['scope_critic']
    assert audit['input_links']==1 and audit['kept_links']==0
    assert all(not n.supports_user_tasks and not n.task_justifications for n in variants)


def test_scoping_off_keeps_every_need_without_calls(setup):
    store,run,candidates,variants=proposals(setup);client=ScopeClient();run['request']['scoping']='off'
    assert needs.scope_needs(store,run,variants,candidates,client)==variants
    assert client.calls==[]
    assert store.get('run',run['run_id'])['need_steps']['scoping']['mode']=='off'
