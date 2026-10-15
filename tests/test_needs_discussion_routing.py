"""An obligation that no source states opens no discussion case by itself (rq1-needs-routing-v2).

All generation is scripted and offline.
"""
from copy import deepcopy

from test_resume_discussions import setup  # noqa: F401  (pytest fixture)
from test_rq1_need_assessment import FullNeedsClient
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow.models import Finding, RequirementRecord, RunRequest
from requirement_reuse_service.workflow.needs import POLICIES, ROUTING_POLICY


def needs_run(store, original, discussion='on_request'):
    client = FullNeedsClient('no_quote')  # obligation labels without quotes: every need ends as unknown
    run = engine.new_run(store, RunRequest(snapshot_id=original['snapshot_id'], strategy='multi_agent',
        role_ids=['consumer_discovery', 'publisher_feasibility'], discussion=discussion, scoping='off'))
    engine.execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'awaiting_human', saved['diagnostics']
    active = [RequirementRecord.model_validate(r) for r in saved['requirements']
              if r['revision_id'] in saved['active_revision_ids']]
    return saved, active


def only(records, criteria):
    """Give each record exactly these review findings and an explicit support verdict."""
    records = [r.model_copy(deep=True) for r in records]
    for record in records:
        record.qualification.support = 'explicit'
        record.qualification.findings = [Finding(criterion=c, severity='review', message='Scripted finding.')
                                         for c in criteria]
    return records


def test_new_needs_runs_save_the_routing_policy(setup):
    store, original, _ = setup
    saved, active = needs_run(store, original)
    assert saved['needs_policies']['routing'] == ROUTING_POLICY == POLICIES['routing']
    assert active and all(r.normalized_intent.obligation_hint == 'unknown' for r in active)


def test_unstated_obligation_alone_opens_no_case(setup):
    store, original, _ = setup
    saved, active = needs_run(store, original)
    records = only(active, ['obligation'])
    cases, routing = engine.route_cases(saved, records, [], 'automatic')
    assert cases == []
    assert {row['route'] for row in routing} == {'human_review'}
    assert all(row['reasons'] == ['obligation_not_stated_by_sources'] for row in routing)
    # The finding itself stays on the need for the reviewer.
    assert all(any(f.criterion == 'obligation' for f in r.qualification.findings) for r in records)


def test_other_findings_still_open_a_case_without_the_obligation_trigger(setup):
    store, original, _ = setup
    saved, active = needs_run(store, original)
    cases, _ = engine.route_cases(saved, only(active, ['obligation', 'missing premise']), [], 'automatic')
    assert len(cases) == len(active)
    assert all(case['triggers'] == ['missing premise'] for case in cases)
    unsupported = only(active, ['obligation'])
    for record in unsupported:
        record.qualification.support = 'unsupported'
    cases, _ = engine.route_cases(saved, unsupported, [], 'automatic')
    assert all(case['triggers'] == ['semantic_support_unsupported'] for case in cases)


def test_a_stated_obligation_finding_is_still_discussed(setup):
    store, original, _ = setup
    saved, active = needs_run(store, original)
    records = only(active, ['obligation'])
    for record in records:
        record.normalized_intent.obligation_hint = 'mandatory'
    cases, _ = engine.route_cases(saved, records, [], 'automatic')
    assert len(cases) == len(records) and all(case['triggers'] == ['obligation'] for case in cases)


def test_runs_saved_before_the_routing_policy_keep_their_routing(setup):
    store, original, _ = setup
    saved, active = needs_run(store, original)
    legacy = deepcopy(saved)
    legacy['needs_policies'].pop('routing')
    cases, _ = engine.route_cases(legacy, only(active, ['obligation']), [], 'automatic')
    assert len(cases) == len(active) and all(case['triggers'] == ['obligation'] for case in cases)


def test_on_request_discussion_is_unchanged(setup):
    store, original, _ = setup
    saved, active = needs_run(store, original)
    cases, routing = engine.route_cases(saved, only(active, ['obligation', 'atomicity']), [], 'on_request')
    assert cases == [] and all(row['reasons'] == ['atomicity'] for row in routing)


def lexical(records, *, model_atomicity=False, assessor=None):
    """The lexical 'and' hint as assess() adds it, optionally with the model's own atomicity finding."""
    records = [r.model_copy(deep=True) for r in records]
    for record in records:
        record.qualification.support = 'explicit'
        record.qualification.assessor = assessor or f'{engine.QUALIFICATION_VERSION}/scripted-model'
        record.qualification.findings = [Finding(criterion='atomicity', severity='review',
                                                 message=engine.LEXICAL_ATOMICITY_MESSAGE)]
        if model_atomicity:
            record.qualification.findings.append(Finding(criterion='Atomicity', severity='review',
                message='Two distinct metadata needs are combined; split them.'))
    return records


def test_lexical_and_hint_alone_opens_no_case_when_the_model_judged_atomicity(setup):
    store, original, _ = setup
    saved, active = needs_run(store, original)
    assert saved['needs_policies']['routing'] == 'rq1-needs-routing-v3'
    records = lexical(active)
    cases, routing = engine.route_cases(saved, records, [], 'automatic')
    assert cases == []
    assert all(row['route'] == 'human_review' and row['reasons'] == ['possible_compound_wording'] for row in routing)
    # The hint itself stays on the need for the reviewer.
    assert all(f.message == engine.LEXICAL_ATOMICITY_MESSAGE for r in records for f in r.qualification.findings)


def test_the_models_own_atomicity_finding_still_opens_a_case(setup):
    store, original, _ = setup
    saved, active = needs_run(store, original)
    cases, _ = engine.route_cases(saved, lexical(active, model_atomicity=True), [], 'automatic')
    assert len(cases) == len(active)
    assert all(case['triggers'] == ['Atomicity', 'atomicity'] for case in cases)


def test_without_a_model_assessment_the_lexical_hint_remains_a_trigger(setup):
    store, original, _ = setup
    saved, active = needs_run(store, original)
    for assessor in (f'{engine.QUALIFICATION_VERSION}/unavailable/scripted-model', 'offline-structural-v2'):
        cases, _ = engine.route_cases(saved, lexical(active, assessor=assessor), [], 'automatic')
        assert len(cases) == len(active) and all(case['triggers'] == ['atomicity'] for case in cases)


def test_runs_saved_under_routing_v2_keep_it_and_still_process_needs(setup):
    from requirement_reuse_service.workflow.needs import run_needs_policies
    store, original, _ = setup
    saved, active = needs_run(store, original)
    v2 = deepcopy(saved)
    v2['needs_policies']['routing'] = 'rq1-needs-routing-v2'
    assert run_needs_policies(v2) == v2['needs_policies']
    cases, _ = engine.route_cases(v2, lexical(active), [], 'automatic')
    assert len(cases) == len(active) and all(case['triggers'] == ['atomicity'] for case in cases)
    # The v2 rule for unstated obligations still applies to such runs.
    cases, _ = engine.route_cases(v2, only(active, ['obligation']), [], 'automatic')
    assert cases == []
    changed = deepcopy(saved)
    changed['needs_policies']['grouping'] = 'another-grouping-policy'
    import pytest
    with pytest.raises(ValueError, match='Needs policies changed'):
        run_needs_policies(changed)
