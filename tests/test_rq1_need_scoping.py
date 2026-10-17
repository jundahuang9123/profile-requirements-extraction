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


class ContributionClient(NeedsClient):
    """Both needs contribute to the use case; only the first is indispensable to it."""
    def generate_structured(self, **kwargs):
        name=kwargs['output_model'].__name__; data=json.loads(kwargs['user'])
        if name=='NeedUseCaseLinks':
            self.calls.append((name,data))
            assert 'Set necessary to true only when' in kwargs['system']
            return kwargs['output_model'].model_validate({'needs':[
                {'need_id':identifier,'links':[{'task_id':'CQ-1','justification':'Lets users filter datasets by region.',
                                                'necessary':index==0}]}
                for index,identifier in enumerate(data['needs'])]})
        if name=='UseCaseCritic':
            self.calls.append((name,data))
            # The critic judges the contribution only; the necessity claim is not in its input.
            assert all('necessary' not in link for link in data['links'])
            assert 'need not be indispensable' in kwargs['system']
            return kwargs['output_model'].model_validate({'decisions':[
                {'link_id':link['link_id'],'keep':True,'rationale':'Contributes a regional filter.'} for link in data['links']]})
        return super().generate_structured(**kwargs)


def test_contributing_link_is_kept_and_necessity_is_only_recorded(setup):
    from requirement_reuse_service.workflow import engine
    store,run,candidates,variants=proposals(setup);client=ContributionClient()
    kept=needs.scope_needs(store,run,variants,candidates,client)
    assert [n.requirement_id for n in kept]==['need-0','need-1']
    assert kept[0].use_case_necessity=={'CQ-1':True} and kept[1].use_case_necessity=={'CQ-1':False}
    assert all(n.supports_user_tasks==['CQ-1'] for n in kept)
    step=store.get('run',run['run_id'])['need_steps']['scoping']
    assert step['policy_version']=='rq1-use-case-contribution-v1' and step['kept_necessary_links']==1
    assert [link['necessary'] for link in step['kept_links']]==[True,False]
    assert store.get('run',run['run_id'])['need_steps']['scope_critic']['policy_version']=='rq1-use-case-contribution-critic-v1'
    assert all(engine.verify(store,n,run['evidence_ids'])['status']=='pass' for n in kept)
