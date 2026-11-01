"""Every resume adds a copy of the run's working state to attempt_history, so a run resumed often
carries hundreds of megabytes of earlier attempts. The worker and the workbench view never load them;
the export, a baseline and ``/runs/{id}/attempts`` do."""
import pytest
from fastapi.testclient import TestClient

from test_routed_stakeholder_workflow import setup  # noqa: F401 (fixture)
from test_resume_base_review import Reviewer, resume, stopped_in_base_review  # noqa: F401 (fixture)
from test_need_trace_v1 import full_client
from requirement_reuse_service.main import app
from requirement_reuse_service.workflow import api, engine
from requirement_reuse_service.workflow.models import RunRequest
from requirement_reuse_service.workflow.storage import Store


@pytest.fixture
def attempt_reads(monkeypatch):
    """The attempt_history rows read from the store while ``reads['on']`` is set."""
    reads = {'on': False, 'rows': 0}
    collect = Store._collect_parts
    def counted(rows, **kwargs):
        rows = list(rows)
        if reads['on']:
            reads['rows'] += sum(name == 'attempt_history' for name, _, _ in rows)
        return collect(rows, **kwargs)
    monkeypatch.setattr(Store, '_collect_parts', staticmethod(counted))
    return reads


def needs_run(store, original):
    """A new F/A needs run with one earlier attempt in its history."""
    run = engine.new_run(store, RunRequest(snapshot_id=original['snapshot_id'], strategy='multi_agent',
        role_ids=['consumer_discovery', 'publisher_feasibility'], stakeholder_workflow='fa_mediated', discussion='automatic',
        scoping='off', base_check=False))
    store.mutate(run['run_id'], None, 'earlier_attempt', lambda r: r['attempt_history'].append({'status': 'failed'}))
    return run


def test_a_run_worker_never_reads_the_earlier_attempts(setup, attempt_reads):
    store, original, _, _ = setup
    run = needs_run(store, original)
    attempt_reads['on'] = True
    engine.execute_run(store, run['run_id'], full_client())
    attempt_reads['on'] = False
    done = store.get('run', run['run_id'])
    # The run went through every step, discussion and need trace included.
    assert done['status'] == 'awaiting_human', done['diagnostics']
    assert done['deliberations'] and done['stage_results']['traceability']
    assert attempt_reads['rows'] == 0
    assert done['attempt_history'] == [{'status': 'failed'}]


def test_a_resumed_base_review_never_reads_the_earlier_attempts(stopped_in_base_review, attempt_reads, monkeypatch):
    store, run_id, _ = stopped_in_base_review
    client = Reviewer()
    def work(store, run_id):
        attempt_reads['on'] = True
        try:
            engine.execute_run(store, run_id, client)
        finally:
            attempt_reads['on'] = False
    monkeypatch.setattr(api, 'execute_run', work)
    monkeypatch.setattr(api, 'configured_client', lambda request: client)
    assert resume(store, run_id).status_code == 202
    done = store.get('run', run_id)
    assert done['stages']['base_review'] == 'completed', done['diagnostics']
    assert attempt_reads['rows'] == 0
    assert done['attempt_history'][-1]['status'] == 'reviewing_base'


def test_the_workbench_view_leaves_out_the_attempts_and_they_are_served_apart(setup):
    store, original, _, _ = setup
    run = engine.new_run(store, RunRequest(snapshot_id=original['snapshot_id'], strategy='multi_agent',
        role_ids=['consumer_discovery'], stakeholder_workflow='fa_mediated'))
    for status in ('failed', 'cancelled'):
        store.mutate(run['run_id'], None, 'earlier_attempt', lambda r, s=status: r['attempt_history'].append({'status': s}))
    http = TestClient(app)
    assert 'attempt_history' not in http.get(f'/api/rq1/v2/runs/{run["run_id"]}?audit=false').json()
    assert http.get(f'/api/rq1/v2/runs/{run["run_id"]}').json()['attempt_history'] == [{'status': 'failed'}, {'status': 'cancelled'}]
    served = http.get(f'/api/rq1/v2/runs/{run["run_id"]}/attempts')
    assert served.json() == {'run_id': run['run_id'], 'attempts': [{'status': 'failed'}, {'status': 'cancelled'}]}
    assert http.get('/api/rq1/v2/runs/run-missing/attempts').status_code == 404


def test_the_workbench_reads_and_commands_never_load_the_earlier_attempts(setup, attempt_reads):
    store, original, _, _ = setup
    run = needs_run(store, original)
    engine.execute_run(store, run['run_id'], full_client())
    done = store.get('run', run['run_id'])
    base, http = f'/api/rq1/v2/runs/{run["run_id"]}', TestClient(app)
    reads = ['?audit=false', '/evaluation', '/coverage', '/needs', '/traceability',
             f'/needs/{done["active_revision_ids"][0]}/trace', *[f'/stages/{stage}' for stage in done['stages']]]
    attempt_reads['on'] = True
    for path in reads:
        assert http.get(base + path).status_code == 200, path
    command = {'expected_version': done['version'], 'idempotency_key': 'defer-1', 'action': 'defer', 'revision_ids': done['active_revision_ids'][:1],
               'rationale': 'Needs a second look.'}
    response = http.post(base + '/decisions', json=command)
    assert response.status_code == 200, response.text
    assert attempt_reads['rows'] == 0 and 'attempt_history' not in response.json()['run']
    # The audit views still include them.
    assert http.get(base + '/export').json()['run']['attempt_history'] == [{'status': 'failed'}]
    assert http.get(base + '/trace').json()['attempt_history'] == [{'status': 'failed'}]
    assert attempt_reads['rows'] == 2
