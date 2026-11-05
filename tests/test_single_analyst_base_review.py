"""The single-analyst condition (S) with the procedural base review.

One neutral role reads every evidence unit without routing or the shared extractor, the F/A checks run, the
base review runs after consolidation, and the run waits for human review without a discussion. All generation
is scripted and offline; the sources are synthetic (test_routed_stakeholder_workflow.setup).
"""
import json
import pytest
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_need_trace_v1 import full_client
from test_base_review import Reviewer
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow import base_review as br
from requirement_reuse_service.workflow.fa_requirements import coverage_ledger
from requirement_reuse_service.workflow.models import RunRequest

S = dict(strategy='multi_agent', role_selection='manual', role_ids=['single_analyst'], stakeholder_workflow='independent',
         requirements_scope='find_access_v1', output_form='needs', discussion='on_request', base_review='expert_v1')
# Contracts of source routing, the independent discussion (Turn) and the F/A discussion.
DISCUSSION = {'SourceRouting', 'Turn', 'TaskGroups', 'TaskLabels', 'Review', 'ExperienceReview', 'Plan', 'ExperiencePlan',
              'Checks', 'DefinedChecks'}


def s_client():
    client = full_client(); base = client.generate_structured; client.contracts = []
    def generate(**kw):
        client.contracts.append(kw['output_model'].__name__)
        if kw['output_model'] in (br.BaseReview, br.BaseReviewChecks):
            return Reviewer('new').generate_structured(user=kw['user'], output_model=kw['output_model'])
        if kw['output_model'].__name__ == 'NeedClassifications':
            data = json.loads(kw['user'])
            return kw['output_model'].model_validate({'classifications': [{'need_id': i, 'classification': 'domain',
                'base_need_ids': [], 'rationale': 'Scripted classification.'} for i in data['needs']]})
        return base(**kw)
    client.generate_structured = generate
    return client


def test_an_s_request_may_add_the_base_review():
    request = RunRequest(snapshot_id='s', base_profile_id='dcat-ap-1.1.0', **S)
    assert (request.base_review, request.stakeholder_workflow, request.requirements_scope, request.output_form,
            request.discussion) == ('expert_v1', 'independent', 'find_access_v1', 'needs', 'on_request')


@pytest.mark.parametrize('change', [
    {'base_profile_id': None},
    {'discussion': 'automatic'},
    {'role_ids': ['single_analyst', 'consumer_discovery']},
    {'role_ids': ['consumer_discovery']},
    {'role_selection': 'automatic'},
    {'requirements_scope': None},
    {'output_form': 'candidates'},
    {'stakeholder_workflow': 'routed_mediated'},
])
def test_outside_the_fa_workflow_only_the_s_shape_adds_the_base_review(change):
    with pytest.raises(ValueError, match='requires the F/A'):
        RunRequest(**{'snapshot_id': 's', 'base_profile_id': 'dcat-ap-1.1.0', **S, **change})


def test_an_s_run_reviews_the_base_before_human_review_and_opens_no_discussion(setup):
    store, original, _, _ = setup
    run = engine.new_run(store, RunRequest(snapshot_id=original['snapshot_id'], base_profile_id='dcat-ap-1.1.0',
                                           base_check=False, scoping='off', **S))
    assert run['stages']['base_review'] == 'pending' and run['base_needs_catalogue']['catalogue_hash']
    client = s_client()
    engine.execute_run(store, run['run_id'], client)
    saved = store.get_run(run['run_id'])
    assert saved['status'] == 'awaiting_human', saved['diagnostics']
    assert saved['stages']['base_review'] == 'completed' and saved['stages']['deliberation'] == 'skipped'
    assert saved['deliberations'] == [] and not DISCUSSION & set(client.contracts)
    # One neutral role read every evidence unit; no routing plan and no shared extractor.
    [report] = saved['role_runs']
    assert report['role_id'] == 'single_analyst' and report['assigned_evidence_ids'] == sorted(saved['evidence_ids'])
    assert report['processed_unit_count'] == len(saved['evidence_ids']) and 'routing_plan' not in saved['stakeholder_audit']
    # The F/A extraction contract and need checks of the F/A workflow.
    assert saved['elicitation_policy_version'] == 'rq1-fa-single-analyst-elicitation-v1' and saved['stakeholder_audit']['fa_contract']
    assert {'source_check', 'proposal_support', 'grouping', 'need_statement', 'classification', 'profile_scope',
            'assessment', 'families', 'selection'} <= set(saved['need_steps'])
    assert saved['need_steps']['profile_scope']['fa_policy_version'] == 'rq1-find-access-v1'
    # The base review judged every active need after consolidation (the frozen machine output has no relation).
    active = [r for r in saved['requirements'] if r['revision_id'] in saved['active_revision_ids']]
    assert active and all((r['base_relation']['phase'], r['base_relation']['status']) == ('before_discussion', 'checked')
                          for r in active)
    assert not any(r.get('base_relation') for r in saved['machine_snapshot']['requirements'])
    assert client.contracts.index('BaseReview') > max(i for i, c in enumerate(client.contracts) if c == 'Qualification')
    assert client.contracts[-1] == 'BaseReviewChecks'
    phases = saved['stage_results']['base_review']['phases']
    assert list(phases) == ['before_discussion'] and phases['before_discussion']['counts'] == {'checked': len(active)}
    assert {c['step'] for c in saved['model_calls'] if c['output_contract'] in {'BaseReview', 'BaseReviewChecks'}} == {
        'base_review', 'base_review_check'}
    # Routed straight to human review, traced, and counted like an F/A run with the base review.
    assert {row['route'] for row in saved['metrics']['routing']} == {'human_review'}
    trace = saved['stage_results']['traceability']
    assert trace['active'] == trace['active_solid'] == len(active) and trace['set_aside_ids'] == []
    assert coverage_ledger(saved)['base_relation_counts'] == {'before_discussion': {'verdict': {'new': len(active)},
                                                                                     'effect': {'agree': len(active)}}}


def test_the_s_request_json_is_accepted_and_run_by_the_api(setup, monkeypatch):
    from fastapi.testclient import TestClient
    from requirement_reuse_service.main import app
    from requirement_reuse_service.workflow import api
    store, original, _, _ = setup
    client = s_client()
    monkeypatch.setattr(api, 'execute_run', lambda store, run_id: engine.execute_run(store, run_id, client))
    body = {'name': 'Requirements extraction - single analyst + base review', 'snapshot_id': original['snapshot_id'],
            'strategy': 'multi_agent', 'role_selection': 'manual', 'role_ids': ['single_analyst'],
            'stakeholder_workflow': 'independent', 'requirements_scope': 'find_access_v1', 'output_form': 'needs',
            'scoping': None, 'consolidation': 'semantic', 'discussion': 'on_request', 'base_profile_id': 'dcat-ap-1.1.0',
            'base_check': True, 'base_review': 'expert_v1', 'execution_mode': 'automatic', 'step_models': {},
            'step_model_options': {}, 'allow_live_provider': True}
    created = TestClient(app).post('/api/rq1/v2/runs', json=body)
    assert created.status_code == 202, created.text
    saved = store.get_run(created.json()['run_id'])
    assert saved['status'] == 'awaiting_human', saved['diagnostics']
    assert (saved['stages']['base_review'], saved['stages']['deliberation'], saved['deliberations']) == ('completed', 'skipped', [])
    assert saved['request']['scoping'] == 'off' and saved['base_check_policy_version']
    assert not DISCUSSION & set(client.contracts) and 'BaseReviewChecks' in client.contracts
    # The same request without the base review is accepted as before and skips the stage.
    plain = TestClient(app).post('/api/rq1/v2/runs', json={**body, 'base_review': 'none'})
    assert plain.status_code == 202, plain.text
    assert store.get_run(plain.json()['run_id'])['stages']['base_review'] == 'skipped'


def test_an_s_run_stopped_by_a_provider_failure_in_base_review_resumes_there(setup, monkeypatch):
    from fastapi.testclient import TestClient
    from requirement_reuse_service.main import app
    from requirement_reuse_service.workflow import api
    store, original, _, _ = setup
    run = engine.new_run(store, RunRequest(snapshot_id=original['snapshot_id'], base_profile_id='dcat-ap-1.1.0',
                                           base_check=False, scoping='off', **S))
    failing = s_client(); answer = failing.generate_structured
    def fail_in_review(**kw):
        if kw['output_model'] is br.BaseReview:
            raise RuntimeError('Synthetic provider failure.')
        return answer(**kw)
    failing.generate_structured = fail_in_review
    engine.execute_run(store, run['run_id'], failing)
    stopped = store.get_run(run['run_id'])
    assert stopped['status'] == 'failed' and stopped['stages']['base_review'] == 'failed'
    assert stopped['stages']['consolidation'] == 'completed' and stopped['diagnostics'][-1].startswith('base_review:')
    client = s_client()
    monkeypatch.setattr(api, 'execute_run', lambda store, run_id: engine.execute_run(store, run_id, client))
    monkeypatch.setattr(api, 'configured_client', lambda request: client)
    response = TestClient(app).post(f"/api/rq1/v2/runs/{run['run_id']}/resume", json={'expected_version': stopped['version']})
    assert response.status_code == 202, response.text
    done = store.get_run(run['run_id'])
    assert done['status'] == 'awaiting_human', done['diagnostics']
    assert (done['stages']['base_review'], done['stages']['deliberation'], done['deliberations']) == ('completed', 'skipped', [])
    # Only the base review ran again; extraction and the need steps were not repeated.
    assert set(client.contracts) == {'BaseReview', 'BaseReviewChecks'}
    assert all(r['base_relation']['status'] == 'checked' for r in done['requirements'] if r['revision_id'] in done['active_revision_ids'])


def failing_extraction(client, needle):
    """Fail the extraction of the evidence units whose excerpts contain needle (a schema-invalid answer)."""
    from requirement_reuse_service.llm.client import OutputValidationError
    answer = client.generate_structured
    def generate(**kw):
        if kw['output_model'].__name__ == 'NeedSpanElicitationResult':
            data = json.loads(kw['user'])
            if any(needle in span['quote'] for unit in data['evidence_units'] for span in unit['source_spans']):
                raise OutputValidationError('NeedSpanElicitationResult', [{'loc': ['observations'], 'type': 'synthetic'}])
        return answer(**kw)
    client.generate_structured = generate
    return client


def failing_transport(client):
    answer = client.generate_structured
    def generate(**kw):
        if kw['output_model'].__name__ == 'NeedSpanElicitationResult':
            raise RuntimeError('Synthetic transport failure.')
        return answer(**kw)
    client.generate_structured = generate
    return client


def resume(store, run, monkeypatch, client):
    from fastapi.testclient import TestClient
    from requirement_reuse_service.main import app
    from requirement_reuse_service.workflow import api
    monkeypatch.setattr(api, 'execute_run', lambda store, run_id: engine.execute_run(store, run_id, client))
    monkeypatch.setattr(api, 'configured_client', lambda request: client)
    return TestClient(app).post(f"/api/rq1/v2/runs/{run['run_id']}/resume", json={'expected_version': run['version']})


def reviewed(saved):
    active = [r for r in saved['requirements'] if r['revision_id'] in saved['active_revision_ids']]
    return active, [r for r in active if (r.get('base_relation') or {}).get('status') == 'checked']


@pytest.mark.parametrize('failure', ['lost_unit', 'transport'])
def test_a_resumed_s_run_reviews_the_rebuilt_needs_against_the_base_again(setup, monkeypatch, failure):
    store, original, _, _ = setup
    run = engine.new_run(store, RunRequest(snapshot_id=original['snapshot_id'], base_profile_id='dcat-ap-1.1.0',
                                           base_check=False, scoping='off', **S))
    first_client = (failing_extraction(s_client(), 'contact details') if failure == 'lost_unit'
                    else failing_transport(s_client()))
    engine.execute_run(store, run['run_id'], first_client)
    first = store.get_run(run['run_id'])
    # The analyst's failure leaves a partial run that has already been through the base review.
    assert first['status'] == 'awaiting_human' and first['metrics']['failed_role_count'] == 1
    assert first['stages']['base_review'] == 'completed'
    client = s_client()
    response = resume(store, first, monkeypatch, client)
    assert response.status_code == 202, response.text
    done = store.get_run(run['run_id'])
    assert done['status'] == 'awaiting_human', done['diagnostics']
    assert done['metrics']['failed_role_count'] == 0 and done['stages']['base_review'] == 'completed'
    # The base review ran again, on the rebuilt needs, and every active need carries its decision.
    assert 'BaseReview' in client.contracts and client.contracts[-1] == 'BaseReviewChecks'
    active, checked = reviewed(done)
    assert active and len(checked) == len(active)
    assert done['stage_results']['base_review']['phases']['before_discussion']['counts'] == {'checked': len(active)}
    trace = done['stage_results']['traceability']
    assert trace['set_aside_ids'] == [] and trace['active'] == trace['active_solid'] == len(active)
    # The failed attempt is kept in the attempt history.
    assert done['attempt_history'] and done['attempt_history'][-1]['stages']['base_review'] == 'completed'


def test_the_resume_guard_applies_to_the_s_shape_only():
    from requirement_reuse_service.workflow.models import single_analyst_review, single_analyst_shape
    request = RunRequest(snapshot_id='s', base_profile_id='dcat-ap-1.1.0', **S)
    assert single_analyst_review(request) and single_analyst_review(request.model_dump(mode='json'))
    assert single_analyst_shape({**request.model_dump(mode='json'), 'base_review': 'none'})
    assert not single_analyst_review({**request.model_dump(mode='json'), 'base_review': 'none'})
    fa = RunRequest(snapshot_id='s', base_profile_id='dcat-ap-1.1.0', strategy='multi_agent',
                    stakeholder_workflow='fa_mediated', output_form='needs', base_review='expert_v1')
    assert not single_analyst_shape(fa) and not single_analyst_review(fa.model_dump(mode='json'))


GENERAL = ('Read every supplied excerpt and collect distinct source-supported user information needs without an '
           'arbitrary candidate quota. Preserve different actors, conditions and obligations. General explanations of '
           'RDF syntax, document layout and implementation mechanics are not automatically catalogue metadata needs. '
           'When a passage has no supported information need, return an empty observation list.')
ROUTED_ONLY = ('This is the single planned extraction pass', 'Use your assigned perspective',
               'Later stakeholder discussion reviews this common pool')


def extraction_texts(store, original, base_review):
    run = engine.new_run(store, RunRequest(snapshot_id=original['snapshot_id'], base_profile_id='dcat-ap-1.1.0',
                                           base_check=False, scoping='off', **{**S, 'base_review': base_review}))
    client = s_client(); answer = client.generate_structured; seen = []
    def spy(**kw):
        if kw['output_model'].__name__ == 'NeedSpanElicitationResult':
            seen.append((kw.get('system') or '', json.loads(kw['user'])))
        return answer(**kw)
    client.generate_structured = spy
    engine.execute_run(store, run['run_id'], client)
    return store.get_run(run['run_id']), seen


def test_the_s_extraction_gets_the_general_sentences_of_the_routed_paragraph_only(setup):
    store, original, _, _ = setup
    saved, seen = extraction_texts(store, original, 'expert_v1')
    assert seen and saved['elicitation_policy_version'] == 'rq1-fa-single-analyst-elicitation-v1'
    for system, user in seen:
        assert GENERAL in system and not any(text in system for text in ROUTED_ONLY)
        # A neutral role, asked about the same scope as PM's shared extractor; nothing names a baseline.
        assert user['role']['label'] == user['stakeholder_perspective']['label'] == 'Single Analyst'
        assert user['role']['focus_questions'][0] == 'Which needs to find, know, judge or access the data do the sources state?'
        assert 'baseline' not in json.dumps(user).lower() and 'baseline' not in system.lower()
    assert {report['prompt_version'] for report in saved['role_runs']} == {'rq1-fa-single-analyst-elicitation-v1'}


def test_a_single_analyst_run_without_the_base_review_keeps_its_extraction_text(setup):
    store, original, _, _ = setup
    saved, seen = extraction_texts(store, original, 'none')
    assert seen and saved['elicitation_policy_version'] == 'rq1-fa-elicitation-v1'
    assert all(GENERAL not in system and not any(text in system for text in ROUTED_ONLY) for system, _ in seen)
