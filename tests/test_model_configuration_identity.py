"""Transport tuning never changes semantic checkpoint identity."""
import pytest

from test_role_selection import corpus, auto_run, SelectorClient
from test_resume_discussions import setup
from test_semantic_consolidation import GroupClient, inputs
from test_rq1_need_row_recovery import ROWS, STEPS
from requirement_reuse_service.llm.step_models import model_identity, model_settings
from requirement_reuse_service.workflow import engine, needs, role_selection
from requirement_reuse_service.workflow.need_recovery import SPECS
from requirement_reuse_service.workflow.semantic_consolidation import grouped_block


def description(model='scripted', tuning=1):
    return dict(provider='offline-test', base_url='https://example.invalid/v1', model=model,
                reasoning_effort='low', max_concurrency=tuning, timeout_seconds=100*tuning,
                rate_limit_retries=tuning, retry_backoff_seconds=tuning)


def test_identity_keeps_only_model_settings():
    assert model_settings(description()) == model_settings(description(tuning=4))
    for key in ('provider', 'base_url', 'model', 'reasoning_effort'):
        changed = {**description(), key: 'different'}
        assert model_settings(description()) != model_settings(changed)


def test_selector_resume_ignores_transport_but_refuses_model_change(corpus):
    store, _, _ = corpus
    run = auto_run(corpus)
    run['step_models'] = {'role_selection': 'scripted'}
    broken = SelectorClient(fail_reducer=True)
    broken.describe = lambda: description()
    with pytest.raises(RuntimeError):
        role_selection.select_roles(store, run, broken)
    saved = store.get('run', run['run_id'])
    saved['step_models'] = run['step_models']
    changed = SelectorClient()
    changed.describe = lambda: description('other', 4)
    with pytest.raises(ValueError, match='model/configuration changed'):
        role_selection.select_roles(store, saved, changed)
    resumed = SelectorClient()
    resumed.describe = lambda: description(tuning=4)
    completed = role_selection.select_roles(store, saved, resumed)
    assert completed['status'] == 'completed'
    assert not any(name == 'RoleCandidates' for name, _ in resumed.calls)


def test_extraction_resume_reuses_passages_after_transport_change(setup):
    store, run, client = setup
    run['step_models'] = {'extraction': 'scripted'}
    client.describe = lambda: description()
    observations, reports = engine.elicit(store, run, client)
    for report in reports:
        report['status'] = 'running'  # Interrupted after its final passage checkpoint.
    run.update(observations=[o.model_dump(mode='json') for o in observations], role_runs=reports)
    previous_calls = len(client.calls)
    client.describe = lambda: description(tuning=4)
    again, _ = engine.elicit(store, run, client)
    assert again == observations and len(client.calls) == previous_calls
    client.describe = lambda: description('other', 4)
    _, failed = engine.elicit(store, run, client)
    assert all(r['status'] == 'failed' and 'model/configuration changed' in r['error'] for r in failed)
    assert len(client.calls) == previous_calls


@pytest.mark.parametrize('name', list(ROWS))
def test_need_checkpoints_reuse_after_transport_change(setup, name):
    store, run, _ = setup
    field, _, input_field = SPECS[name]
    payload = {input_field: {'row': {}}} if input_field != 'links' else {'links': [{'link_id': 'row'}]}
    class Client:
        model, tuning, calls = 'scripted', 1, 0
        def describe(self): return description(self.model, self.tuning)
        def generate_structured(self, **kw):
            self.calls += 1
            return kw['output_model'].model_validate({field: [ROWS[name]('row')]})
    client = Client()
    def generate():
        return needs.cached_generation(store, run, STEPS[name], payload, getattr(needs, name), 'Frozen.', client)
    generate(); client.tuning = 4; generate()
    assert client.calls == 1
    assert next(iter(store.get('run', run['run_id'])['need_chunks'].values()))['provider']['timeout_seconds'] == 100
    client.model = 'other'; generate()
    assert client.calls == 2


def test_group_checkpoints_reuse_after_transport_change(setup):
    store, run, records = inputs(setup)
    client = GroupClient()
    state = {'model': 'scripted', 'tuning': 1}
    client.describe = lambda: description(**state)
    def group():
        grouped_block(store, run, 'fixture', records, client,
                      store.get('run', run['run_id'])['consolidation_chunks'])
    group(); state['tuning'] = 4; group()
    assert len(client.group_requests) == 1
    state['model'] = 'other'; group()
    assert len(client.group_requests) == 2


def test_assessment_checkpoint_reuses_after_transport_change(setup):
    from test_step_models import FullNeedsClient
    store, run, records = inputs(setup)
    record = records[0]
    record.need_statement = record.normalized_statement
    client = FullNeedsClient()
    state = {'model': 'scripted', 'tuning': 1}
    client.describe = lambda: description(**state)
    needs.assess_needs(store, run, [record], client)
    state['tuning'] = 4
    needs.assess_needs(store, run, [record], client)
    assert sum(name == 'Qualification' for name, _ in client.calls) == 1
    state['model'] = 'other'
    needs.assess_needs(store, run, [record], client)
    assert sum(name == 'Qualification' for name, _ in client.calls) == 2
