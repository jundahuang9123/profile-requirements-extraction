"""Base policy gates are audited before source checks and survive later review."""
from copy import deepcopy

import pytest
from test_resume_discussions import setup, ROLES
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import engine, base_profile
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import (
    DecisionRequest, DeriveRequest, Finding, Observation, Qualification, RevisionDraft, RunRequest,
    SnapshotRequest, SourceRequest)
from requirement_reuse_service.workflow.storage import digest


def with_base(setup, **settings):
    store, initial, client = setup
    conditional = register_source(store, SourceRequest(source_role='stakeholder_need',
        artifact=ArtifactPayload(name='conditional-title.md',
            content='Each dataset should publish its title if access is restricted.')))
    source_ids = store.get('snapshot', initial['snapshot_id'])['source_version_ids']
    snapshot = engine.freeze_snapshot(store, SnapshotRequest(
        source_version_ids=[*source_ids, conditional['source_version_id']]))
    request = RunRequest(snapshot_id=snapshot['snapshot_id'], strategy='multi_agent',
        role_ids=ROLES, consolidation='exact', discussion='on_request',
        base_profile_id='dcat-ap-2.0.1', **settings)
    return store, engine.new_run(store, request), client


def test_inherited_skips_source_checks_and_assessments_with_saved_audit(setup, monkeypatch):
    store, run, client = with_base(setup)
    checked = []
    original = engine.verify
    def spy(store, record, *args, **kwargs):
        checked.append(record.revision_id)
        return original(store, record, *args, **kwargs)
    monkeypatch.setattr(engine, 'verify', spy)
    engine.execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'awaiting_human'
    inherited = [audit for audit in saved['base_check_audit'] if audit['set_aside']]
    assert inherited and {a['revision_id'] for a in inherited}.isdisjoint(checked)
    assert all(item['reason'] == 'inherited_from_base' and item['base_check']
               for item in saved['set_aside_observations'])
    qualifications = [data for name, data in client.calls if name == 'Qualification']
    assert qualifications and all(data['requirement']['base_check']['relation'] == 'loosened'
                                  for data in qualifications)
    assert saved['machine_snapshot']['base_check_audit'] == saved['base_check_audit']
    stage = saved['stage_results']['normalization']
    assert stage['base_check_audit'] == saved['base_check_audit']
    assert stage['base_profile_sha256'] == saved['base_profile_sha256']
    assert stage['base_check_policy_version'] == base_profile.BASE_CHECK_POLICY_VERSION
    assert stage['base_registry_policy_version'] == saved['base_registry_policy_version'] == 'rq1-base-registry-v1'
    assert stage['base_check']['set_aside_inherited'] == len(inherited)
    assert stage['base_check']['by_relation']['inherited'] == len(inherited)
    assert saved['machine_snapshot']['base_check'] == saved['metrics']['base_check']
    for stage_name in ('normalization', 'verification', 'consolidation', 'deliberation'):
        for key in engine.RUN_POLICY_FIELDS:
            assert saved['stage_results'][stage_name][key] == saved[key]
            assert saved['machine_snapshot'][key] == saved[key]
    assert all(r['base_check']['relation'] == 'loosened' for r in saved['requirements'])


def test_saved_legacy_extraction_derives_without_extraction_or_assessment_calls(setup):
    store, source, client = setup
    engine.execute_run(store, source['run_id'], client)
    store.mutate(source['run_id'], None, 'test_legacy_policy', lambda run: run.update(
        elicitation_policy_version='rq1-independent-elicitation-v2.11'))
    source = store.get('run', source['run_id'])
    before = deepcopy(source)
    trial = engine.derive_run(store, source['run_id'], DeriveRequest(
        expected_version=source['version'], consolidation='exact', base_profile_id='dcat-ap-2.0.1',
        rationale='Apply a base check to frozen extraction.'))
    mark = len(client.calls)
    engine.execute_run(store, trial['run_id'], client)
    saved = store.get('run', trial['run_id'])
    assert saved['status'] == 'awaiting_human'
    assert client.count('SpanElicitationResult', mark) == client.count('Qualification', mark) == 0
    assert saved['base_check_audit'] and saved['set_aside_observations']
    assert saved['elicitation_policy_version'] == 'rq1-independent-elicitation-v2.11'
    assert store.get('run', source['run_id']) == before
    for record in saved['requirements']:
        assert any(f['criterion'] == 'conflicts_with_base' for f in record['qualification']['findings'])


def test_new_base_policy_does_not_reuse_assessments_from_v1(setup):
    store, source, client = with_base(setup)
    engine.execute_run(store, source['run_id'], client)
    store.mutate(source['run_id'], None, 'historical-v1-test', lambda run: run.update(
        base_check_policy_version='rq1-base-check-v1'))
    source = store.get('run', source['run_id'])
    trial = engine.derive_run(store, source['run_id'], DeriveRequest(
        expected_version=source['version'], consolidation='exact',
        rationale='Reprocess a historical base check under the current policy.'))
    assert trial['base_check_policy_version'] == 'rq1-base-check-v2'
    assert not trial['derived_from']['base_assessment_context_compatible']
    assert trial['assessment_reuse'] == {}


def test_weaker_plain_restatements_are_audited_and_make_no_assessment_calls(setup):
    store, source, client = setup
    run = engine.new_run(store, RunRequest(snapshot_id=source['snapshot_id'], strategy='multi_agent',
        role_ids=ROLES, consolidation='exact', discussion='on_request', base_profile_id='dcat-ap-2.0.1'))
    engine.execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'awaiting_human' and saved['active_revision_ids'] == []
    assert client.count('Qualification') == 0
    weaker = [a for a in saved['base_check_audit'] if a['base_check'].get('notes') == ['weaker label than base']]
    assert weaker and all(a['set_aside'] and not a['findings'] for a in weaker)


def test_registry_hash_guard_stops_before_provider_and_preserves_checkpoint(setup, monkeypatch):
    store, run, client = with_base(setup)
    original = engine.load_profile
    monkeypatch.setattr(engine, 'load_profile', lambda identifier: (original(identifier)[0], 'changed-hash'))
    engine.execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'failed' and saved['stages']['normalization'] == 'failed'
    assert any('registry changed' in message for message in saved['diagnostics'])
    assert not client.calls and saved['base_check_audit'] == []
    assert saved['observations'] == []


@pytest.mark.parametrize('legacy,disabled', [(True,False),(False,True)])
def test_no_policy_or_disabled_base_keeps_legacy_behavior(setup, legacy, disabled):
    store, run, client = with_base(setup, base_check=not disabled)
    if legacy:
        store.mutate(run['run_id'], None, 'test_legacy_no_policy', lambda run: run.pop('base_check_policy_version'))
    engine.execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'awaiting_human' and saved['base_check_audit'] == []
    assert saved['set_aside_observations'] == []
    assert all(not r['base_check'] and not r['base_check_findings'] for r in saved['requirements'])


def test_required_findings_survive_human_support_override_and_edit(setup):
    store, run, client = with_base(setup)
    engine.execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    original = next(r for r in saved['requirements'] if r['revision_id'] in saved['active_revision_ids'])
    record = engine.RequirementRecord.model_validate(original)
    record.qualification = Qualification(support='explicit', rationale='Reviewed support.', findings=[],
        assessor='human', revision_hash=record.content_hash)
    with pytest.raises(ValueError, match='base-profile findings'):
        engine.eligible(record)
    engine.retain_base_findings(record)
    assert any(f.criterion == 'conflicts_with_base' for f in record.qualification.findings)
    draft = RevisionDraft(statement=original['raw_statement'], evidence_links=original['evidence_links'],
        requirement_type=original['requirement_type'], intent=original['normalized_intent'],
        scope=original['scope'], rationale=original['rationale'])
    engine.decide(store, run['run_id'], DecisionRequest(expected_version=saved['version'],
        idempotency_key='base-edit', revision_ids=[record.revision_id], action='edit',
        drafts=[draft], rationale='Edit preserves the source requirement.'), 'reviewer')
    latest = store.get('run', run['run_id'])
    edited = next(r for r in latest['requirements'] if r['parent_revision_ids'] == [record.revision_id])
    assert edited['base_check']['relation'] == 'loosened'
    assert any(f['criterion'] == 'conflicts_with_base' for f in edited['qualification']['findings'])


def test_merge_preserves_members_and_cannot_upgrade_tightening_from_union(setup):
    store, initial, client = setup
    engine.execute_run(store, initial['run_id'], client)
    saved = store.get('run', initial['run_id'])
    raw = [r for r in saved['requirements'] if not r['parent_revision_ids']]
    first, second = [engine.RequirementRecord.model_validate(row) for row in raw[:2]]
    common = {'base_profile':'dcat-ap-2.0.1','class':'dcat:Dataset','property':'dct:publisher',
        'base_obligation':'recommended','candidate_obligation':'mandatory','constraint_signals':[],
        'resolved_via':'statement_curie'}
    first.base_check = dict(common, relation='inherited', requires_review=True,
        evidence_source_groups=['base_only'])
    second.base_check = dict(common, relation='tightened', evidence_source_groups=['inspire_geodcat'])
    first.base_check_findings = [Finding(criterion='conflicts_with_base', severity='blocking', message='Required conflict.')]
    observation = Observation(observation_id='merged-base', role_id='consolidation', statement=first.raw_statement,
        intent=first.normalized_intent, evidence_links=[*first.evidence_links,*second.evidence_links])
    merged = engine.record_from_observation(saved['run_id'], observation, parents=[first.revision_id,second.revision_id])
    engine.inherit_base_checks(merged, [first,second])
    assert merged.base_check['relation'] == 'inherited' and merged.base_check['requires_review']
    assert set(merged.base_check['member_checks']) == {first.revision_id, second.revision_id}
    assert merged.base_check['evidence_source_groups'] == ['base_only','inspire_geodcat']
    engine.qualify_record(store, merged, saved['evidence_ids'])
    assert {'conflicts_with_base','merged_base_check_disagreement'} <= {f.criterion for f in merged.qualification.findings}


def test_source_groups_are_named_from_corpus_not_references(setup):
    store, run, _ = setup
    row = Observation(observation_id='group', role_id='r', statement='A title is required.',
        evidence_links=[{'evidence_id': 'e', 'quote':'A title is required.'}])
    record = engine.record_from_observation(run['run_id'], row)
    context = {'evidence_by_id':{'e': {'source_version_id':'s'}}, 'base_source_version_ids':set(),
        'source_name_by_version':{'s':'SPRINT_NAP_paper.pdf'}}
    assert engine.evidence_source_group(record, context) == 'mobility'
    context['source_name_by_version']['s'] = 'INSPIRE.pdf'
    assert engine.evidence_source_group(record, context) == 'inspire_geodcat'
    context['source_name_by_version']['s'] = 'FAIR.pdf'
    assert engine.evidence_source_group(record, context) == 'other_generic'
    context['base_source_version_ids'] = {'s'}
    assert engine.evidence_source_group(record, context) == 'base_only'


def test_custom_source_with_no_base_classification_keeps_stronger_rule_for_review(setup):
    store, _, client = setup
    source = register_source(store, SourceRequest(source_role='stakeholder_need',
        artifact=ArtifactPayload(name='domain-needs.md', content='Each dataset must include dct:publisher.')))
    snapshot = engine.freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    run = engine.new_run(store, RunRequest(snapshot_id=snapshot['snapshot_id'], strategy='multi_agent',
        role_ids=ROLES, consolidation='exact', discussion='on_request', base_profile_id='dcat-ap-2.0.1'))
    engine.execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'awaiting_human' and saved['set_aside_observations'] == []
    assert saved['active_revision_ids']
    for record in saved['requirements']:
        assert record['base_check']['relation'] == 'inherited' and record['base_check']['requires_review']
        assert any(f['criterion'] == 'unresolved_base_source_classification'
                   for f in record['qualification']['findings'])


def test_mixed_inherited_and_new_property_clause_is_retained_without_fabricating_support(setup):
    store, _, client = setup
    text = 'Each dataset must publish dct:title and ex:roadDirection.'
    source = register_source(store, SourceRequest(source_role='stakeholder_need',
        artifact=ArtifactPayload(name='domain-needs.md', content=text)))
    snapshot = engine.freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    run = engine.new_run(store, RunRequest(snapshot_id=snapshot['snapshot_id'], strategy='multi_agent',
        role_ids=ROLES, consolidation='exact', discussion='on_request', base_profile_id='dcat-ap-2.0.1'))
    engine.execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'awaiting_human' and saved['set_aside_observations'] == []
    assert saved['active_revision_ids']
    for record in saved['requirements']:
        assert record['raw_statement'] == text
        assert record['base_check']['relation'] == 'inherited' and record['base_check']['requires_review']
        assert any(f['criterion'] == 'compound_base_check' for f in record['qualification']['findings'])
        assert record['verification']['status'] == 'pass'
        assert all(link['quote'] == text for link in record['evidence_links'])


def test_negated_base_statement_stays_for_review_with_authentic_evidence(setup):
    store, _, client = setup
    text = 'Each dataset must not include dct:title.'
    source = register_source(store, SourceRequest(source_role='stakeholder_need',
        artifact=ArtifactPayload(name='domain-needs.md', content=text)))
    snapshot = engine.freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    run = engine.new_run(store, RunRequest(snapshot_id=snapshot['snapshot_id'], strategy='multi_agent',
        role_ids=ROLES, consolidation='exact', discussion='on_request', base_profile_id='dcat-ap-2.0.1'))
    engine.execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'awaiting_human' and saved['set_aside_observations'] == []
    assert saved['active_revision_ids']
    for record in saved['requirements']:
        assert record['raw_statement'] == text and record['verification']['status'] == 'pass'
        assert record['base_check']['relation'] == 'inherited' and record['base_check']['requires_review']
        assert any(f['criterion'] == 'base_polarity_review' for f in record['qualification']['findings'])


def test_base_context_change_does_not_reuse_stale_base_findings(setup):
    store, run, client = with_base(setup)
    engine.execute_run(store, run['run_id'], client)
    source = store.get('run', run['run_id'])
    derived = engine.derive_run(store, source['run_id'], DeriveRequest(
        expected_version=source['version'], consolidation='exact', base_check=False,
        rationale='Compare the disabled base check.'))
    assert derived['assessment_reuse'] == {}
    assert derived['derived_from']['base_assessment_context_compatible'] is False
