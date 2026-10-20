"""Scripted per-case fallback: no provider generation or benchmark answers."""
from copy import deepcopy
import json
import pytest
from test_fa_workflow import Dialogue, enable
from test_routed_stakeholder_workflow import setup, make_record, install_records
from requirement_reuse_service.llm.client import LLMError, LLMRequestTimeoutError
from requirement_reuse_service.llm.config import LLMConfig
from requirement_reuse_service.llm.step_models import StepModelRouter
from requirement_reuse_service.workflow import engine, fa_discussion as discussion
from requirement_reuse_service.workflow.models import DeriveRequest, RunRequest, MediationTimeoutFallback

POLICY={'policy_version':'rq1-case-mediation-timeout-v1','fallback_model':'model-gptoss','timeout_seconds':120}

class RoutedDialogue(Dialogue):
    def __init__(self, *, fail_model='model-mediation', error=LLMRequestTimeoutError,
                 objection=False, fail_check=False):
        super().__init__(objection=objection)
        self.fail_model=fail_model;self.error=error;self.failed=False
        self.routes=[];self.fail_check=fail_check
    def mediation_client(self, model, timeout_seconds):
        parent=self
        class Bound:
            def describe(self):return {'provider':'scripted','model':model,'reasoning_effort':'low'}
            def generate_structured(self, **kw):
                parent.routes.append((model,timeout_seconds,json.loads(kw['user'])))
                if model==parent.fail_model and not parent.failed:
                    parent.failed=True
                    raise parent.error('scripted transport failure')
                return parent.generate_structured(**kw,step='mediation')
        return Bound()
    def generate_structured(self, *, user, output_model, step=None, **kw):
        data=json.loads(user)
        if output_model.__name__=='TaskGroups':
            return output_model.model_validate({'groups':[{'task':'Separate synthetic task',
                'revision_ids':[n['revision_id']],'rationale':'Separate source-supported need.'}
                for n in data['needs']]})
        if output_model.__name__=='Checks' and self.fail_check:
            raise LLMError('scripted check interruption')
        return super().generate_structured(user=user,output_model=output_model,step=step,**kw)


def prepare(setup):
    store,run,units,_=setup
    run=enable(store,run)
    run=install_records(store,run,[make_record(store,run,u,i) for i,u in enumerate(units)])
    def options(r):
        r['request']['mediation_timeout_fallback']=deepcopy(POLICY)
        r['step_models']=r['request']['step_models']={'mediation':'model-mediation'}
    store.mutate(run['run_id'],None,'fixture_policy',options)
    return store,store.get('run',run['run_id'])


def test_timeout_default_is_two_minutes_and_explicit_legacy_value_is_preserved():
    default=MediationTimeoutFallback(fallback_model='model-gptoss')
    assert default.timeout_seconds==120
    legacy=MediationTimeoutFallback.model_validate({**POLICY,'timeout_seconds':300})
    assert legacy.model_dump()['timeout_seconds']==300


@pytest.mark.parametrize('timeout_seconds',[120,300])
def test_timeout_switches_only_one_case_and_next_case_uses_primary(setup,timeout_seconds):
    store,run=prepare(setup);client=RoutedDialogue()
    store.mutate(run['run_id'],None,'fixture_timeout',
        lambda r:r['request']['mediation_timeout_fallback'].update(timeout_seconds=timeout_seconds))
    discussion.deliberate(store,run['run_id'],client)
    saved=store.get('run',run['run_id'])
    assert [model for model,_,_ in client.routes]==['model-mediation','model-gptoss','model-mediation']
    assert all(seconds==timeout_seconds for _,seconds,_ in client.routes)
    first,second=saved['deliberations']
    route=first['discussion_trace']['mediator_routing']
    assert route['active_model']=='model-gptoss' and len(route['switches'])==1
    phases=first['discussion_trace']['phases']
    assert not phases['draft'].get('output') and phases['draft']['timeout']['error_type']=='LLMRequestTimeoutError'
    assert phases['draft:fallback']['output'] and phases['draft:fallback']['model']['model']=='model-gptoss'
    assert not second['discussion_trace']['mediator_routing']['switches']
    assert first['model_attempts']==second['model_attempts']+1
    assert first['output_tokens_reserved']==second['output_tokens_reserved']+4000
    assert saved['machine_snapshot']==run['machine_snapshot']
    before=len(client.routes)
    discussion.deliberate(store,run['run_id'],client)
    assert len(client.routes)==before


def test_resume_reuses_fallback_and_primary_role_outputs(setup):
    store,run=prepare(setup);client=RoutedDialogue(objection=True,fail_check=True)
    with pytest.raises(LLMError,match='check interruption'):
        discussion.deliberate(store,run['run_id'],client)
    failed=store.get('run',run['run_id']);case=failed['deliberations'][0]
    accepted=deepcopy(case['discussion_trace']['phases'])
    calls=len(client.calls);routes=len(client.routes)
    assert accepted['draft:fallback']['output'] and accepted['final:fallback']['output']
    client.fail_check=False
    discussion.deliberate(store,run['run_id'],client)
    # Only the subsequent case generates new mediator responses.
    assert all(m=='model-mediation' for m,_,_ in client.routes[routes:])
    resumed=store.get('run',run['run_id'])['deliberations'][0]
    assert resumed['discussion_trace']['phases']['draft:fallback']==accepted['draft:fallback']
    assert resumed['discussion_trace']['phases']['final:fallback']==accepted['final:fallback']
    assert client.calls[calls][1]=='Checks'


def test_non_timeout_error_never_switches_models(setup):
    store,run=prepare(setup);client=RoutedDialogue(error=LLMError)
    with pytest.raises(LLMError,match='transport failure'):
        discussion.deliberate(store,run['run_id'],client)
    assert [m for m,_,_ in client.routes]==['model-mediation']
    route=store.get('run',run['run_id'])['deliberations'][0]['discussion_trace']['mediator_routing']
    assert not route['switches']


def test_explicit_router_binding_has_single_attempt_and_audits_actual_model(setup):
    from pydantic import create_model
    store,run,_,_=setup;configs=[]
    class Fake:
        def __init__(self,config):self.config=config;configs.append(config)
        def describe(self):return {'provider':'scripted','model':self.config.model,'timeout':self.config.timeout}
        def generate_structured(self,**kw):return kw['output_model'].model_validate({'value':'accepted'})
    router=StepModelRouter(LLMConfig(provider='mock',timeout=480,transient_retries=2),
        {'mediation':'primary'},Fake)
    tracked=engine.TrackedClient(router,store,run['run_id'])
    for model in ['primary','fallback','primary']:
        tracked.mediation_client(model,120).generate_structured(system='fixture',user='{}',
            output_model=create_model('Plan',value=(str,...)),max_tokens=10)
    assert [c['model'] for c in store.get('run',run['run_id'])['model_calls']]==['primary','fallback','primary']
    assert all(c.timeout==120 and c.transient_retries==0 for c in configs)
    assert router.for_step('mediation').config.timeout==480


def test_discussion_child_preserves_parent_and_completed_work(setup):
    store,run,units,_=setup;run=enable(store,run)
    run=install_records(store,run,[make_record(store,run,u,i) for i,u in enumerate(units)])
    # Save the normal hybrid plan before adding the new policy.
    class Interrupted(Dialogue):
        def generate_structured(self,**kw):
            if kw['output_model'].__name__=='Plan':raise LLMError('scripted timeout')
            return super().generate_structured(**kw)
    with pytest.raises(LLMError):discussion.deliberate(store,run['run_id'],Interrupted())
    def stopped(r):
        r['status']='failed';r['stages'].update({s:'completed' for s in
            ('acquisition','decomposition','role_selection','elicitation','normalization','verification','consolidation')})
        r['stages']['deliberation']='failed'
        r['step_models']=r['request']['step_models']={'mediation':'model-mediation'}
    store.mutate(run['run_id'],None,'fixture_stopped',stopped)
    parent=store.get('run',run['run_id']);frozen=deepcopy(parent)
    request=DeriveRequest(start_from='deliberation',expected_version=parent['version'],
        name='Timeout fallback trial',rationale='Explicit case-level policy',mediation_timeout_fallback=POLICY)
    child=engine.derive_run(store,parent['run_id'],request)
    assert store.get('run',parent['run_id'])==frozen
    assert child['requirements']==frozen['requirements'] and child['deliberations']==frozen['deliberations']
    assert child['machine_snapshot']==frozen['machine_snapshot']
    assert not child['model_calls']
    assert child['derived_from']['stage']=='deliberation'
    engine.execute_run(store,child['run_id'],RoutedDialogue())
    finished=store.get('run',child['run_id'])
    assert finished['status']=='awaiting_human', finished['diagnostics']
    assert all(c['step'] in {'mediation','mediation_check'} for c in finished['model_calls'])
    changed=request.model_copy(update={'step_models':{'mediation':'other'}})
    with pytest.raises(ValueError,match='cannot change upstream'):
        engine.derive_run(store,parent['run_id'],changed)


def test_fallback_restricted_to_fa_workflow():
    with pytest.raises(ValueError,match='F/A'):
        RunRequest(snapshot_id='s',strategy='multi_agent',mediation_timeout_fallback=POLICY)


def test_fallback_model_is_validated_against_provider_catalogue(monkeypatch):
    import httpx
    config=LLMConfig(provider='openai-compatible',model='inferenz-qwen3-8-27b',base_url='https://provider.invalid/v1')
    monkeypatch.setattr(LLMConfig,'from_env',classmethod(lambda cls:config))
    reads=[]
    def get(url,**kw):
        reads.append(url)
        return httpx.Response(200,json={'data':[{'id':config.model},{'id':'inferenz-gpt-oss-120b'}]},
            request=httpx.Request('GET',url))
    monkeypatch.setattr(httpx,'get',get)
    request=RunRequest(snapshot_id='s',strategy='multi_agent',allow_live_provider=True,
        stakeholder_workflow='fa_mediated',mediation_timeout_fallback={**POLICY,'fallback_model':'missing'})
    with pytest.raises(ValueError,match='unavailable'):
        engine.freeze_step_models(request)
    request.mediation_timeout_fallback.fallback_model='inferenz-gpt-oss-120b'
    frozen=engine.freeze_step_models(request)
    assert frozen.step_models['mediation']==config.model
    assert len(reads)==2
    request.mediation_timeout_fallback.fallback_model=config.model
    with pytest.raises(ValueError,match='differ'):
        engine.freeze_step_models(request)


def test_fallback_timeout_stops_instead_of_oscillating(setup):
    store,run=prepare(setup)
    class AllSlow(RoutedDialogue):
        def mediation_client(self,model,timeout_seconds):
            bound=super().mediation_client(model,timeout_seconds)
            def fail(**kw):
                self.routes.append((model,timeout_seconds,{}))
                raise LLMRequestTimeoutError('both unavailable')
            bound.generate_structured=fail
            return bound
    client=AllSlow()
    with pytest.raises(LLMRequestTimeoutError):
        discussion.deliberate(store,run['run_id'],client)
    assert [m for m,_,_ in client.routes]==['model-mediation','model-gptoss']


def test_changed_case_policy_fails_before_new_calls(setup):
    store,run=prepare(setup);client=RoutedDialogue(error=LLMError)
    with pytest.raises(LLMError):discussion.deliberate(store,run['run_id'],client)
    count=len(client.routes)
    store.mutate(run['run_id'],None,'fixture_tamper',
        lambda r:r['request']['mediation_timeout_fallback'].update(timeout_seconds=400))
    with pytest.raises(ValueError,match='policy, role or model mismatch'):
        discussion.deliberate(store,run['run_id'],client)
    assert len(client.routes)==count


def test_fa_set_aside_reason_matches_existing_writer():
    from requirement_reuse_service.workflow.models import SetAside
    assert SetAside(observation_id='o',role_id='r',reason='fa_scope_set_aside').reason=='fa_scope_set_aside'
    with pytest.raises(ValueError):SetAside(observation_id='o',role_id='r',reason='made_up')


def test_cancelled_child_shortens_timeout_without_repeating_completed_work(setup):
    store,run=prepare(setup)
    store.mutate(run['run_id'],None,'fixture_legacy_timeout',
        lambda r:r['request']['mediation_timeout_fallback'].update(timeout_seconds=300))
    class StopSecond(RoutedDialogue):
        plans=0
        def generate_structured(self,**kw):
            if kw['output_model'].__name__=='Plan':
                self.plans+=1
                if self.plans==2:raise LLMError('fixture interruption before second draft')
            return super().generate_structured(**kw)
    with pytest.raises(LLMError,match='fixture interruption'):
        discussion.deliberate(store,run['run_id'],StopSecond(fail_model='never'))
    def cancel(r):
        r.update(status='cancelled',worker_id=None,job_lease_until=0)
        r['stages'].update({s:'completed' for s in
            ('acquisition','decomposition','role_selection','elicitation','normalization','verification','consolidation','deliberation')})
        for c in r['deliberations']:
            if c['status'] in {'queued','running'}:c.update(status='cancelled',stop_reason='human_cancelled')
    store.mutate(run['run_id'],None,'fixture_user_cancelled',cancel)
    parent=store.get('run',run['run_id']);before=deepcopy(parent)
    complete,unfinished=before['deliberations']
    assert complete['status']=='mediated' and unfinished['status']=='cancelled'
    request=DeriveRequest(start_from='deliberation',expected_version=parent['version'],
        name='Two-minute continuation',rationale='User explicitly requests shorter timeout',
        mediation_timeout_fallback=POLICY)
    child=engine.derive_run(store,parent['run_id'],request)
    assert store.get('run',parent['run_id'])==before
    assert child['deliberations'][0]==complete
    continued=child['deliberations'][1]
    assert continued['status']=='queued' and continued['stop_reason'] is None
    assert continued['model_attempts']==unfinished['model_attempts']
    assert continued['model_seconds']==unfinished['model_seconds']
    assert continued['output_tokens_reserved']==unfinished['output_tokens_reserved']
    assert continued['discussion_trace']['phases']==unfinished['discussion_trace']['phases']
    route=continued['discussion_trace']['mediator_routing']
    assert route['policy']['timeout_seconds']==120
    assert route['policy_changes'][0]['from_policy']['timeout_seconds']==300
    assert child['derived_from']['continued_cancelled_case_ids']==[unfinished['case_id']]
    for policy in [{**POLICY,'timeout_seconds':400},{**POLICY,'fallback_model':'different'}]:
        with pytest.raises(ValueError,match='only a shorter'):
            engine.derive_run(store,parent['run_id'],request.model_copy(update={
                'mediation_timeout_fallback':MediationTimeoutFallback.model_validate(policy)}))
    client=RoutedDialogue(fail_model='never')
    engine.execute_run(store,child['run_id'],client)
    finished=store.get('run',child['run_id'])
    assert finished['status']=='awaiting_human',finished['diagnostics']
    assert finished['deliberations'][0]==complete
    assert len(client.routes)==1 and client.routes[0][1]==120
    assert not any(step=='stakeholder_review' for step,_,_ in client.calls)
    assert finished['deliberations'][1]['discussion_trace']['mediator_routing']['policy_changes']==route['policy_changes']


def test_context_guard_measures_reversible_wire_ids_not_internal_payload(setup, monkeypatch):
    store,run=prepare(setup)
    seen=[]
    class WireClient(RoutedDialogue):
        def generate_structured(self, *, user, output_model, **kw):
            if output_model.__name__=='Review':seen.append(len(user))
            return super().generate_structured(user=user,output_model=output_model,**kw)
    client=WireClient(fail_model='never')
    discussion.deliberate(store,run['run_id'],client)
    saved=store.get('run',run['run_id'])
    budgets=[p['context_budget'] for c in saved['deliberations']
             for p in c['discussion_trace']['phases'].values() if 'context_budget' in p]
    assert budgets and seen
    assert all(b['wire_characters']<=b['internal_characters'] for b in budgets)
    assert all(b['measured_characters']==b['wire_characters'] for b in budgets)
    assert any(b['wire_characters']<b['internal_characters'] for b in budgets)
    assert all(b['policy_version']=='rq1-fa-context-budget-case-v1' for b in budgets)
    assert all(b['wire_hash'] for b in budgets)


def test_real_wire_overflow_goes_to_visible_review_without_stopping_run(setup,monkeypatch):
    store,run=prepare(setup);client=RoutedDialogue(fail_model='never')
    monkeypatch.setattr(discussion,'MAX_CONTEXT',1)
    discussion.deliberate(store,run['run_id'],client)
    saved=store.get('run',run['run_id'])
    assert saved['status']=='awaiting_human'
    assert saved['active_revision_ids']==run['active_revision_ids']
    assert all(c['stop_reason']=='budget_pending_human_review' for c in saved['deliberations'])
    assert all('context budget' in c['mediation']['human_questions'][0]['question'] for c in saved['deliberations'])
    assert client.routes==[]
