"""rq1-need-trace-v1 (Junda, 26 Oct): every produced need can be traced through the whole chain (its quotations,
the agent that extracted it, each step's decision and reason with the model call behind it, and the discussion),
and an active need whose chain is incomplete is set aside as not found solidly, never put before a reviewer."""
import copy
import json
import pytest
from fastapi.testclient import TestClient
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_fa_workflow import Dialogue
from requirement_reuse_service.main import app
from requirement_reuse_service.workflow import engine, need_trace
from requirement_reuse_service.workflow.call_log import recorded_calls, report_call
from requirement_reuse_service.workflow.models import RunRequest


def full_client():
    from test_rq1_need_assessment import FullNeedsClient
    class Full(FullNeedsClient):
        def __init__(self): super().__init__(); self.dialogue = Dialogue()
        def generate_structured(self, **kw):
            name = kw['output_model'].__name__; data = json.loads(kw['user'])
            if name in {'TaskGroups', 'Review', 'Plan', 'Checks'}: return self.dialogue.generate_structured(**kw)
            if name == 'SourceRouting': raw = {'routes': [{'evidence_id': s['evidence_id'], 'kind': 'shared', 'role_ids': ['shared_source_extractor'], 'rationale': 'Common source information task.'} for s in data['sections']]}
            elif name == 'FAPreservation': raw = {'checks': [{'group_id': g, 'information_preserved': True, 'actor_preserved': True, 'purpose_preserved': True, 'conditions_preserved': True, 'obligation_preserved': True, 'negation_preserved': True, 'rationale': 'Fixture distinctions preserved.'} for g in data['groups']]}
            elif name == 'FAScopeResult': raw = {'decisions': [{'need_id': i, 'support': 'explicit', 'serves': 'find', 'nature': 'information_requirement', 'actor': 'Users', 'task': 'Find a dataset', 'example': 'Select a dataset using its title', 'rationale': 'Synthetic source-supported discovery task.', 'evidence_ids': list(row['excerpts'])} for i, row in data['needs'].items()]}
            elif name == 'NeedMembership': raw = {'checks': [{'member_id': i, 'expresses_need': True, 'rationale': 'Same fixture need.'} for i in data['members']]}
            else: return super().generate_structured(**kw)
            return kw['output_model'].model_validate(raw)
    return Full()


@pytest.fixture
def finished(setup):
    store, original, _, _ = setup
    run = engine.new_run(store, RunRequest(snapshot_id=original['snapshot_id'], strategy='multi_agent',
        role_ids=['consumer_discovery', 'publisher_feasibility'], stakeholder_workflow='fa_mediated', discussion='automatic',
        scoping='off', base_check=False))
    engine.execute_run(store, run['run_id'], full_client())
    return store, store.get_run(run['run_id'])


def active_trace(store, run):
    index = need_trace.TraceIndex(store, run)
    return index, need_trace.need_trace(index, run['active_revision_ids'][0])


def test_a_fresh_run_traces_every_produced_need_with_recorded_calls(finished):
    store, run = finished
    saved = run['stage_results']['traceability']
    assert saved['produced'] and saved['solid'] == saved['produced'] and saved['active_solid'] == saved['active']
    assert saved['set_aside_ids'] == [] and saved['review_items_unresolved'] == []
    traces = need_trace.run_traces(store, run)
    calls = {c['call_id'] for c in run['model_calls']}
    for trace in traces.values():
        # Each model decision names the calls that made it, recorded where it was made, not matched afterwards.
        assert {d['call_link'] for d in trace['decisions']} <= {'recorded', 'not_applicable'}
        assert all(set(d['call_ids']) <= calls for d in trace['decisions'])
        assert trace['origin'] and all(o['call_link'] == 'recorded' and o['agent'] and o['prompt_version'] for o in trace['origin'])
        assert all(s['found'] and s['source'] for s in trace['sources'])
        assert all(case['call_ids'] and set(case['call_ids']) <= calls for case in trace['discussion'])
    steps = {d['step'] for t in traces.values() for d in t['decisions']}
    assert {'proposal_support', 'need_statement', 'fa_test', 'record_test', 'assessment'} <= steps


def test_an_unfound_quotation_breaks_the_chain(finished):
    store, run = finished
    run = copy.deepcopy(run); need = next(r for r in run['requirements'] if r['revision_id'] == run['active_revision_ids'][0])
    need['evidence_links'][0]['quote'] = 'A sentence no source contains.'
    _, trace = active_trace(store, run)
    assert not trace['completeness']['solid'] and {m['link'] for m in trace['completeness']['missing']} == {'sources'}


def test_a_missing_decision_breaks_the_chain(finished):
    store, run = finished
    # The record test judged needs in this run, but its row for this need is gone.
    run = copy.deepcopy(run)
    for row in run['need_steps']['profile_scope']['record_decisions']: row['need_id'] = 'req-another'
    _, trace = active_trace(store, run)
    assert not trace['completeness']['solid']
    assert trace['completeness']['missing'] == [{'link': 'decisions', 'detail': 'record_test recorded no decision.'}]


def test_an_outcome_naming_no_revision_breaks_the_chain_and_an_action_does_not(finished):
    store, run = finished
    run = copy.deepcopy(run); need = run['active_revision_ids'][0]
    outcome = next(o for c in run['deliberations'] for o in c['mediation']['outcomes'] if need in o['parent_revision_ids'])
    outcome['parent_revision_ids'] = [need, outcome['action_id']]
    assert active_trace(store, run)[1]['completeness']['solid']
    outcome['parent_revision_ids'] = [need, 'rev-that-does-not-exist']
    _, trace = active_trace(store, run)
    assert [m['link'] for m in trace['completeness']['missing']] == ['discussion']


def test_an_incomplete_need_is_set_aside_instead_of_reviewed(finished):
    store, run = finished
    need = run['active_revision_ids'][0]
    def drop(r):
        step = copy.deepcopy(r['need_steps']['profile_scope'])
        for row in step['record_decisions']: row['need_id'] = 'req-another'
        r['need_steps']['profile_scope'] = step
    store.mutate(run['run_id'], None, 'fixture_drop_record_test', drop, parts=True)
    result = need_trace.record_traceability(store, run['run_id'])
    assert result['set_aside_ids'] == [need]
    saved = store.get_run(run['run_id'])
    assert need not in saved['active_revision_ids']
    aside = [a for a in saved['set_aside_observations'] if a['reason'] == 'trace_incomplete']
    assert len(aside) == 1 and aside[0]['revision_id'] == need and 'record_test' in aside[0]['rationale']
    record = next(r for r in saved['requirements'] if r['revision_id'] == need)
    assert record['lifecycle_state'] == 'set_aside' and 'trace_incomplete' in record['processing_flags']
    # A second pass finds nothing more to set aside and lists the need once.
    assert need_trace.record_traceability(store, run['run_id'])['set_aside_ids'] == []
    assert sum(a['reason'] == 'trace_incomplete' for a in store.get_run(run['run_id'])['set_aside_observations']) == 1


def test_runs_before_this_version_are_traced_by_matching(finished):
    store, run = finished
    run = copy.deepcopy(run)
    for chunk in run['need_chunks'].values():
        for attempt in chunk.get('attempts') or []: attempt.pop('call_ids', None)
        chunk.pop('call_ids', None)
    for role_run in run['role_runs']:
        for selection in role_run['citation_selections']: selection.pop('call_ids', None)
    _, trace = active_trace(store, run)
    links = {d['step']: d['call_link'] for d in trace['decisions']}
    assert trace['completeness']['solid'] and links['proposal_support'] == links['fa_test'] == 'matched'
    assert {o['call_link'] for o in trace['origin']} == {'matched'}


@pytest.mark.parametrize('style', need_trace.SUMMARY_STYLES)
def test_the_reviewer_summary_names_source_agent_and_what_to_decide(finished, style):
    store, run = finished
    _, trace = active_trace(store, run)
    text = need_trace.need_summary(trace, style)
    assert trace['sources'][0]['source'] in text and 'Shared source extractor' in text
    if style != 'exceptions': assert 'quote supports it' in text


def test_the_trace_and_the_summary_are_served(finished):
    store, run = finished
    client = TestClient(app); need = run['active_revision_ids'][0]
    trace = client.get(f"/api/rq1/v2/runs/{run['run_id']}/needs/{need}/trace")
    assert trace.status_code == 200 and trace.json()['completeness']['solid'] and trace.json()['summary']
    summary = client.get(f"/api/rq1/v2/runs/{run['run_id']}/traceability")
    assert summary.status_code == 200 and summary.json()['needs'][need]['solid']
    assert client.get(f"/api/rq1/v2/runs/{run['run_id']}/needs/rev-none/trace").status_code == 404


def test_calls_are_logged_only_inside_open_blocks():
    report_call('outside')
    with recorded_calls() as outer:
        report_call('a')
        with recorded_calls() as inner: report_call('b')
    report_call('after')
    assert outer == ['a', 'b'] and inner == ['b']
