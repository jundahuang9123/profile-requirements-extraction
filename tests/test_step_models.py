"""Model routing tests are scripted; the suite forbids real network calls."""
import json
from copy import deepcopy

import httpx
import pytest
from pydantic import ValidationError, create_model

from test_resume_discussions import setup
from test_role_selection import corpus
from test_rq1_need_assessment import FullNeedsClient
from test_rq1_need_row_recovery import ROWS, STEPS as ROW_STEPS
from test_semantic_consolidation import GroupClient, inputs
from requirement_reuse_service.llm.config import LLMConfig
from requirement_reuse_service.llm.step_models import CONTRACT_STEPS, STEPS, StepModelRouter, resolve_models
from requirement_reuse_service.workflow import engine, needs
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import DeriveRequest, Qualification, RunRequest, SnapshotRequest, SourceRequest
from requirement_reuse_service.workflow.need_recovery import SPECS
from requirement_reuse_service.workflow.semantic_consolidation import grouped_block


def fake_catalog(monkeypatch, models):
    reads = []
    def get(url, **kwargs):
        reads.append(url)
        return httpx.Response(200, json={'data': [{'id': m} for m in models]},
                              request=httpx.Request('GET', url))
    monkeypatch.setattr(httpx, 'get', get)
    return reads


def live_config(monkeypatch, models=('default', 'qwen-other')):
    config = LLMConfig(provider='openai-compatible', model='default', base_url='https://example.invalid/v1')
    monkeypatch.setattr(LLMConfig, 'from_env', classmethod(lambda cls: config))
    return config, fake_catalog(monkeypatch, models)


def test_default_model_is_frozen_for_every_step_and_resume_does_not_rediscover(setup, monkeypatch):
    store, original, _ = setup
    config, reads = live_config(monkeypatch)
    created = engine.new_run(store, RunRequest(snapshot_id=original['snapshot_id'], strategy='multi_agent',
        allow_live_provider=True, step_models={'writer': 'qwen-other'}))
    expected = {step: 'qwen-other' if step == 'writer' else 'default' for step in STEPS}
    assert created['step_models'] == created['request']['step_models'] == expected
    assert len(reads) == 1
    config.model = 'a different global default'
    router = engine.configured_client(RunRequest.model_validate(created['request']))
    assert router.for_step('writer').describe()['model'] == 'qwen-other'
    assert router.for_step('assessment').describe()['model'] == 'default'
    assert len(reads) == 1  # Resume trusts frozen choices, not a newly changed default.


@pytest.mark.parametrize('overrides', [{'writer': 'unknown'}, {'writer': 'text-embedding-3-small'}])
def test_bad_model_fails_before_a_run_is_created(setup, monkeypatch, overrides):
    store, original, _ = setup
    live_config(monkeypatch, ('default', 'text-embedding-3-small'))
    before = deepcopy(store.list('run'))
    with pytest.raises(ValueError, match='unavailable for text generation'):
        engine.new_run(store, RunRequest(snapshot_id=original['snapshot_id'], strategy='multi_agent',
            allow_live_provider=True, step_models=overrides))
    assert store.list('run') == before


def test_missing_permission_does_not_even_read_catalogue(setup, monkeypatch):
    store, original, _ = setup
    _, reads = live_config(monkeypatch)
    with pytest.raises(ValueError, match='allow_live_provider'):
        engine.new_run(store, RunRequest(snapshot_id=original['snapshot_id'], strategy='multi_agent'))
    assert reads == []


def test_catalogue_failure_is_safe_and_creates_no_job(setup, monkeypatch):
    store, original, _ = setup
    live_config(monkeypatch)
    def fail(*a, **kw): raise httpx.ConnectError('secret must not appear')
    monkeypatch.setattr(httpx, 'get', fail)
    before = deepcopy(store.list('run'))
    with pytest.raises(ValueError, match='Could not load provider model list') as error:
        engine.new_run(store, RunRequest(snapshot_id=original['snapshot_id'], strategy='multi_agent', allow_live_provider=True))
    assert 'secret must not appear' not in str(error.value)
    assert store.list('run') == before


@pytest.mark.parametrize('mapping', [{'unknown_step': 'model'}, {'writer': ''}, {'writer': '   '}])
def test_invalid_step_setting_is_rejected(mapping):
    with pytest.raises(ValidationError):
        RunRequest(snapshot_id='s', strategy='multi_agent', step_models=mapping)


def test_exact_ids_with_spaces_and_anthropic_pagination(monkeypatch):
    config = LLMConfig(provider='anthropic', model='Claude Example')
    calls = []
    def get(url, **kwargs):
        calls.append(kwargs.get('params'))
        payload = ({'data': [{'id': 'Claude Example'}], 'has_more': True, 'last_id': 'first'}
                   if len(calls) == 1 else {'data': [{'id': 'Claude Second'}], 'has_more': False})
        return httpx.Response(200, json=payload, request=httpx.Request('GET', url))
    monkeypatch.setattr(httpx, 'get', get)
    assert resolve_models(config, {'writer': 'Claude Second'})['writer'] == 'Claude Second'
    assert calls == [None, {'after_id': 'first'}]


def test_each_step_routes_and_every_model_call_records_its_actual_model(setup):
    store, run, _ = setup
    calls = []
    class Scripted:
        def __init__(self, config): self.model = config.model
        def describe(self): return {'provider': 'scripted', 'model': self.model}
        def generate_structured(self, **kw):
            calls.append((self.model, kw['output_model'].__name__))
            return kw['output_model'].model_validate({'value': self.model})
    choices = {step: 'model-' + step for step in STEPS}
    router = StepModelRouter(LLMConfig(provider='mock'), choices, Scripted)
    tracked = engine.TrackedClient(router, store, run['run_id'])
    for step in STEPS:
        name = next((name for name, target in CONTRACT_STEPS.items() if target == step), 'Turn')
        output = create_model(name, value=(str, ...))
        client = tracked.for_step(step) if step in {'role_selection', 'extraction', 'discussion'} else tracked
        answer = client.generate_structured(system='Scripted test.', user='{}', output_model=output, max_tokens=10)
        assert answer.value == choices[step]
    audit = store.get('run', run['run_id'])['model_calls']
    assert len(audit) == len(STEPS)
    assert {a['step']: a['model'] for a in audit} == choices
    assert all(a['provider']['model'] == a['model'] for a in audit)
    assert choices['writer'] != choices['rewrite_critic']


def test_real_needs_pipeline_routes_all_processing_and_discussion_calls(setup):
    store, _, _ = setup
    source = register_source(store, SourceRequest(source_role='stakeholder_need', artifact=ArtifactPayload(
        name='synthetic-model-routing.md', content='\n'.join(
            f'Each dataset describes its title (fixture {i}).' for i in range(11)))))
    snapshot = engine.freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']],
        user_tasks=[{'id': 'CQ-1', 'statement': 'Which datasets have a title?', 'kind': 'competency_question'}]))
    run = engine.new_run(store, RunRequest(snapshot_id=snapshot['snapshot_id'], strategy='multi_agent',
        base_profile_id='dcat-ap-2.0.1', base_check=False, scoping='use_cases', discussion='automatic',
        role_ids=['consumer_discovery', 'publisher_feasibility']))
    class Scripted(FullNeedsClient):
        def __init__(self, config): super().__init__(); self.model = config.model
        def describe(self): return {'provider': 'scripted', 'model': self.model}
        def generate_structured(self, **kw):
            name = kw['output_model'].__name__; data = json.loads(kw['user'])
            if name in {'NeedMembership', 'NeedClassifications', 'NeedUseCaseLinks', 'UseCaseCritic', 'Turn'}:
                self.calls.append((name, data))
                if name == 'NeedMembership': raw = {'checks': [ROWS[name](i) for i in data['members']]}
                elif name == 'NeedClassifications': raw = {'classifications': [ROWS[name](i) for i in data['needs']]}
                elif name == 'NeedUseCaseLinks': raw = {'needs': [{'need_id': i, 'links': [
                    {'task_id': 'CQ-1', 'justification': 'Title enables the declared discovery task.'}]} for i in data['needs']]}
                elif name == 'UseCaseCritic': raw = {'decisions': [ROWS[name](row['link_id']) for row in data['links']]}
                else: raw = {'body': 'The need remains for human review.', 'finished': True, 'evidence_ids': []}
                return kw['output_model'].model_validate(raw)
            if name == 'Qualification':
                # An unstated obligation alone no longer opens a case (rq1-needs-routing-v2);
                # uncertain support does, so the discussion route is still exercised.
                self.calls.append((name, data))
                return kw['output_model'].model_validate({'support': 'uncertain',
                    'rationale': 'Scripted uncertain support.', 'assessor': 'scripted'})
            return super().generate_structured(**kw)
    choices = {step: 'model-' + step for step in STEPS}
    router = StepModelRouter(LLMConfig(provider='mock'), choices, Scripted)
    engine.execute_run(store, run['run_id'], router)
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'awaiting_human', saved['diagnostics']
    assert saved['active_revision_ids']
    audit = saved['model_calls']
    assert {row['step'] for row in audit} == set(STEPS) - {'role_selection'}
    assert all(row['model'] == choices[row['step']] for row in audit)


def test_actual_role_selector_uses_bound_model(corpus):
    from test_role_selection import auto_run, SelectorClient
    store, _, _ = corpus
    run = auto_run(corpus)
    class Selector(SelectorClient):
        def __init__(self, config): super().__init__(); self.model = config.model
        def describe(self): return {'provider': 'scripted', 'model': self.model}
    router = StepModelRouter(LLMConfig(provider='mock'), {'role_selection': 'selector-model'}, Selector)
    # Exercise the actual discovery, citation and panel call sites, without extraction.
    engine.select_roles(store, run, engine.TrackedClient(router, store, run['run_id']))
    audit = store.get('run', run['run_id'])['model_calls']
    assert audit and all(row['step'] == 'role_selection' and row['model'] == 'selector-model' for row in audit)


@pytest.mark.parametrize('name', list(ROWS))
def test_every_recovery_checkpoint_is_model_specific(setup, name):
    store, run, _ = setup
    field, id_field, input_field = SPECS[name]
    payload = {input_field: {'row': {}}} if input_field != 'links' else {'links': [{'link_id': 'row'}]}
    class Scripted:
        def __init__(self, config): self.model = config.model; self.calls = 0
        def describe(self): return {'provider': 'scripted', 'model': self.model}
        def generate_structured(self, **kw):
            self.calls += 1
            return kw['output_model'].model_validate({field: [ROWS[name]('row')]})
    routers = [StepModelRouter(LLMConfig(provider='mock'), {s: m for s in STEPS}, Scripted) for m in ('a', 'b')]
    model = getattr(needs, name)
    for router in routers:
        for _ in range(2):
            needs.cached_generation(store, run, ROW_STEPS[name], payload, model, 'Frozen input.', router)
        assert sum(c.calls for c in router._clients.values()) == 1
    chunks = store.get('run', run['run_id'])['need_chunks']
    assert len(chunks) == 2
    assert {row['provider']['model'] for row in chunks.values()} == {'a', 'b'}


def test_grouping_checkpoint_is_model_specific(setup):
    store, run, records = inputs(setup)
    clients = []
    for model in ('a', 'b'):
        client = GroupClient()
        client.describe = lambda model=model: {'provider': 'scripted', 'model': model}
        saved = store.get('run', run['run_id'])['consolidation_chunks']
        grouped_block(store, run, 'test', records, client, saved)
        grouped_block(store, run, 'test', records, client, saved)
        assert len(client.group_requests) == 1
        clients.append(client)
    assert len(store.get('run', run['run_id'])['consolidation_chunks']) == 2


def test_assessment_checkpoint_uses_selected_assessment_model(setup):
    store, run, records = inputs(setup)
    record = records[0]
    record.need_statement = record.normalized_statement
    clients = []
    for model in ('a', 'b'):
        client = FullNeedsClient()
        client.describe = lambda model=model: {'provider': 'scripted', 'model': model}
        router = StepModelRouter(LLMConfig(provider='mock'), {'assessment': model}, lambda config: client)
        needs.assess_needs(store, run, [record], router)
        needs.assess_needs(store, run, [record], router)
        assert sum(name == 'Qualification' for name, _ in client.calls) == 1
        assert record.qualification.assessor.endswith('/' + model)
        clients.append(client)
    assert len(store.get('run', run['run_id'])['need_chunks']) == 2


def test_saved_extraction_trial_accepts_new_choices_without_mutating_source(setup, monkeypatch):
    store, run, source_client = setup
    engine.execute_run(store, run['run_id'], source_client)
    source = store.get('run', run['run_id']); before = deepcopy(source)
    live_config(monkeypatch)
    trial = engine.derive_run(store, source['run_id'], DeriveRequest(expected_version=source['version'],
        rationale='Compare downstream models only.', allow_live_provider=True,
        step_models={'writer': 'qwen-other'}, reuse_assessments=True))
    assert trial['observations'] == source['observations']
    assert trial['role_runs'] == source['role_runs']
    assert trial['step_models']['writer'] == 'qwen-other'
    assert trial['step_models']['rewrite_critic'] == 'default'
    assert not trial['assessment_reuse']
    assert store.get('run', source['run_id']) == before
    for name in ('normalization', 'verification', 'consolidation', 'deliberation'):
        assert trial['stages'][name] == 'pending'


def test_discussion_and_reusable_assessment_keys_include_model():
    case = {'triggers': ['review'], 'participants': ['p'], 'frozen_requirements': []}
    assert engine.discussion_key({**case, 'model': 'a'}) != engine.discussion_key({**case, 'model': 'b'})
    row = {'content_hash': 'h', 'qualification': Qualification(support='explicit', rationale='Fixture.',
        assessor=engine.QUALIFICATION_VERSION + '/a', revision_hash='h').model_dump(mode='json')}
    assert engine.reusable_qualification(row, 'h', 'a')
    assert engine.reusable_qualification(row, 'h', 'b') is None
