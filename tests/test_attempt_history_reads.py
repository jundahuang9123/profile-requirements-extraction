"""Every resume adds a copy of the run's working state to attempt_history, so a run resumed often
carries hundreds of megabytes of earlier attempts. The worker, the workbench's reads and command
responses never load them; the export, the audit trace, a baseline and ``/runs/{id}/attempts`` do."""
import pytest
from fastapi.testclient import TestClient

from test_routed_stakeholder_workflow import setup  # noqa: F401 (fixture)
from test_resume_discussions import setup as discussions_setup  # noqa: F401 (fixture)
from test_resume_base_review import Reviewer, resume, stopped_in_base_review  # noqa: F401 (fixture)
from test_base_review import prepared
from test_derived_runs import completed
from test_fa_workflow import Dialogue
from test_need_trace_v1 import full_client
from test_need_trace_v1_shapes import build_source, client_for, merged_event, new_fa_run, split_client
from test_semantic_consolidation import GroupClient, inputs
from requirement_reuse_service.main import app
from requirement_reuse_service.workflow import api, base_review, engine, fa_discussion
from requirement_reuse_service.workflow.models import DeriveRequest, RunRequest
from requirement_reuse_service.workflow.semantic_consolidation import semantic_consolidate
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


def needs_run(store, original, **request):
    """A new F/A needs run with one earlier attempt in its history."""
    run = new_fa_run(store, original, **request)
    return seeded(store, run)


def seeded(store, run):
    store.mutate(run['run_id'], None, 'earlier_attempt', lambda r: r['attempt_history'].append({'status': 'failed'}))
    return store.get('run', run['run_id'])


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


def test_a_run_with_a_base_profile_never_reads_the_earlier_attempts(setup, attempt_reads):
    store, original, _, _ = setup
    run = needs_run(store, original, base_profile_id='dcat-ap-1.1.0')
    attempt_reads['on'] = True
    engine.execute_run(store, run['run_id'], client_for('revise'))
    attempt_reads['on'] = False
    done = store.get('run', run['run_id'])
    assert done['status'] == 'awaiting_human', done['diagnostics']
    # The needs were searched against the base, after its catalogue was checked against the pinned one.
    assert 'base_needs_catalogue_pinned' in [e['event_type'] for e in store.events(run['run_id'])]
    assert done['need_steps']['classification']['base_gap_counts']
    assert attempt_reads['rows'] == 0 and done['attempt_history'] == [{'status': 'failed'}]


def test_a_derived_run_reads_its_assessment_cache_without_the_earlier_attempts(discussions_setup, attempt_reads):
    store, source, client = completed(discussions_setup)
    child = engine.derive_run(store, source['run_id'], DeriveRequest(output_form='candidates', consolidation='exact',
        expected_version=source['version'], rationale='Reuse the assessments.'))
    assert child['derived_from']['reuse_assessments'] and child['assessment_reuse']
    seeded(store, child)
    mark = len(client.calls)
    attempt_reads['on'] = True
    engine.execute_run(store, child['run_id'], client)
    attempt_reads['on'] = False
    done = store.get('run', child['run_id'])
    # Every candidate took its assessment from the frozen cache instead of asking the model.
    assert done['status'] == 'awaiting_human', done['diagnostics']
    assert done['metrics']['assessments_reused'] == len(source['observations']) and client.count('Qualification', mark) == 0
    assert attempt_reads['rows'] == 0 and done['attempt_history'] == [{'status': 'failed'}]


def test_semantic_grouping_never_reads_the_earlier_attempts(discussions_setup, attempt_reads):
    store, run, records = inputs(discussions_setup)
    seeded(store, run)
    client = GroupClient()
    attempt_reads['on'] = True
    active, _, _ = semantic_consolidate(store, run, records, client)
    mark = len(client.calls)
    # The second pass groups from the checkpoint the first one saved, which it reads with the run.
    again, _, _ = semantic_consolidate(store, run, records, client)
    attempt_reads['on'] = False
    assert len(active) == 1 and [r.revision_id for r in again] == [r.revision_id for r in active]
    assert client.count('SemanticGrouping') == 1 and client.count('SemanticGrouping', mark) == 0
    assert attempt_reads['rows'] == 0 and store.get('run', run['run_id'])['attempt_history'] == [{'status': 'failed'}]


class ReviewingDialogue(Dialogue):
    def generate_structured(self, *, user, output_model, **kwargs):
        if output_model in (base_review.BaseReview, base_review.BaseReviewChecks):
            return Reviewer('restates_base').generate_structured(user=user, output_model=output_model, **kwargs)
        return super().generate_structured(user=user, output_model=output_model, **kwargs)


def test_the_base_review_after_a_discussion_never_reads_the_earlier_attempts(setup, attempt_reads):
    store, run, _ = prepared(setup)
    def opt_in(r):
        r['request']['base_review'] = 'expert_v1'
        # A need the discussion rewrote is reviewed against the base again once the discussion ends.
        r['requirements'][0].update(processing_flags=['base_recheck_required'], base_relation=None)
        r['attempt_history'].append({'status': 'failed'})
    store.mutate(run['run_id'], None, 'fixture_expert', opt_in)
    attempt_reads['on'] = True
    fa_discussion.deliberate(store, run['run_id'], ReviewingDialogue())
    attempt_reads['on'] = False
    done = store.get('run', run['run_id'])
    assert done['status'] == 'awaiting_human', done['diagnostics']
    assert done['requirements'][0]['base_relation']['phase'] == 'after_discussion'
    assert attempt_reads['rows'] == 0 and done['attempt_history'] == [{'status': 'failed'}]


def test_tracing_a_trial_reads_the_run_it_was_derived_from_without_its_earlier_attempts(setup, attempt_reads):
    store, original, _, _ = setup
    # Merge events saved before written_group_id name a group of the source run: the trial's merged need is solid
    # only when its trace reads the run the trial was derived from.
    source = seeded(store, build_source(store, original, strip=True))
    child = engine.derive_run(store, source['run_id'], DeriveRequest(start_from='base_review', expected_version=source['version'],
                              rationale='Base trial of an older run.'))
    attempt_reads['on'] = True
    engine.execute_run(store, child['run_id'], split_client())
    attempt_reads['on'] = False
    trial = store.get('run', child['run_id'])
    assert trial['status'] == 'awaiting_human', trial['diagnostics']
    assert trial['derived_from']['run_id'] == source['run_id'] and not any(c.get('step') == 'extraction' for c in trial['model_calls'])
    merged, traced = merged_event(trial)['outputs'][0], trial['stage_results']['traceability']
    assert merged in trial['active_revision_ids'] and traced['needs'][merged]['solid'] and not traced['set_aside_ids']
    assert attempt_reads['rows'] == 0 and store.get('run', source['run_id'])['attempt_history'] == [{'status': 'failed'}]
