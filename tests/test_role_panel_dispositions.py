"""Offline regressions for harmless panel duplicates and narrowly scoped recovery.

All migration fixtures use a temporary store. The observed batch-31 failure shape
is reproduced without opening the user's saved run or calling a provider.
"""
import json
from copy import deepcopy

import pytest

from test_role_selection import SelectorClient, auto_run, corpus
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import role_selection as selector
from requirement_reuse_service.workflow.engine import freeze_snapshot, new_run
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import RolePanel, RunRequest, SnapshotRequest, SourceRequest
from requirement_reuse_service.workflow.storage import Store, canonical, digest


FAILED_PANEL_ERROR = (
    'Panel accounting remained invalid after its single targeted correction; '
    'every candidate must be accounted for exactly once.')
OBSERVED_DUPLICATE_ID = 'role-candidate-226810a5d4a86fb00222c9bb'


def panel(*, members=None, omitted=None, extra_groups=None):
    return RolePanel.model_validate({'groups': [
        {'representative_id': 'kept', 'member_ids': members or ['kept'],
         'rationale': 'Keep the publication perspective.'}, *(extra_groups or [])],
        'omitted': omitted or []})


def test_duplicate_omission_preserves_first_reason_and_original_response():
    original = panel(omitted=[
        {'candidate_id': 'unused', 'reason': 'First explanation.'},
        {'candidate_id': 'unused', 'reason': 'Later explanation.'},
        {'candidate_id': 'unused', 'reason': 'Third explanation.'}])
    before = original.model_dump(mode='json')
    normalized, audit = selector.collapse_panel_dispositions(original)
    assert original.model_dump(mode='json') == before
    assert normalized.model_dump(mode='json')['omitted'] == [before['omitted'][0]]
    assert audit == [{'disposition': 'omitted', 'candidate_id': 'unused',
        'removed_count': 2, 'retained_index': 0, 'retained_reason': 'First explanation.'}]
    assert selector.panel_accounting_errors(normalized,
        [{'candidate_id': 'kept'}, {'candidate_id': 'unused'}], 2) == []


def test_same_group_duplicate_members_collapse_without_moving_members_between_groups():
    original = panel(members=['kept', 'other', 'kept', 'other', 'kept'])
    before = original.model_dump(mode='json')
    normalized, audit = selector.collapse_panel_dispositions(original)
    assert original.model_dump(mode='json') == before
    assert normalized.groups[0].member_ids == ['kept', 'other']
    assert audit == [
        {'disposition': 'group_member', 'candidate_id': 'kept', 'group_index': 0,
         'removed_count': 2, 'retained_index': 0},
        {'disposition': 'group_member', 'candidate_id': 'other', 'group_index': 0,
         'removed_count': 1, 'retained_index': 1}]


@pytest.mark.parametrize('conflict, expected_code', [
    ('kept_and_omitted', 'duplicate_disposition'),
    ('two_groups', 'duplicate_disposition'),
    ('missing', 'missing_candidate_ids'),
    ('unknown', 'unknown_candidate_ids'),
    ('representative_missing', 'representative_not_in_group'),
    ('role_limit', 'role_limit')])
def test_normalization_keeps_substantive_panel_errors(conflict, expected_code):
    pool = [{'candidate_id': 'kept'}, {'candidate_id': 'other'}]
    data = panel(members=['kept', 'other']).model_dump(mode='json')
    max_roles = 2
    if conflict == 'kept_and_omitted':
        data['omitted'] = [{'candidate_id': 'kept', 'reason': 'Conflicting disposition.'}] * 2
    elif conflict == 'two_groups':
        data['groups'].append({'representative_id': 'other', 'member_ids': ['other', 'other'],
                               'rationale': 'Conflicting group membership.'})
    elif conflict == 'missing':
        data['groups'][0]['member_ids'] = ['kept', 'kept']
    elif conflict == 'unknown':
        data['omitted'] = [{'candidate_id': 'not-in-registry', 'reason': 'Unknown candidate.'}] * 2
    elif conflict == 'representative_missing':
        data['groups'][0]['representative_id'] = 'not-in-registry'
    else:
        data['groups'] = [
            {'representative_id': candidate['candidate_id'], 'member_ids': [candidate['candidate_id']],
             'rationale': 'Separate perspective.'} for candidate in pool]
        max_roles = 1
    normalized, _ = selector.collapse_panel_dispositions(RolePanel.model_validate(data))
    assert expected_code in {error['code'] for error in
        selector.panel_accounting_errors(normalized, pool, max_roles)}


class DuplicateOmissionClient(SelectorClient):
    def generate_structured(self, **kwargs):
        if kwargs['output_model'].__name__ != 'RolePanel':
            return super().generate_structured(**kwargs)
        payload = json.loads(kwargs['user'])
        self.calls.append(('RolePanel', payload))
        ids = [candidate['candidate_id'] for candidate in payload['candidates']]
        assert len(ids) == 2
        return RolePanel.model_validate({'groups': [
            {'representative_id': ids[0], 'member_ids': [ids[0]],
             'rationale': 'Keep the already selected perspective.'}],
            'omitted': [
                {'candidate_id': ids[1], 'reason': 'First reason to omit the overlap.'},
                {'candidate_id': ids[1], 'reason': 'Repeated omission with a later explanation.'}]})


def test_panel_duplicate_omission_is_audited_without_spending_a_correction(corpus):
    store, snapshot, _ = corpus
    run = auto_run(corpus)
    run['role_manifest']['selected_roles'] = [selector.as_selected(
        selector.proposed_defaults()[0], candidate_ids=['existing-lineage'], reason='Previous batch selection.')]
    client = DuplicateOmissionClient()
    manifest = selector.select_roles(store, run, client)
    assert manifest['status'] == 'completed'
    assert [name for name, _ in client.calls] == ['RoleCandidates', 'RolePanel']
    assert not manifest.get('panel_accounting_repairs')
    report = manifest['batch_reports'][0]
    assert len(report['panel_disposition_collapses']) == 1
    change = report['panel_disposition_collapses'][0]
    assert change['phase'] == 'panel'
    assert len(change['original_selection']['omitted']) == 2
    assert change['normalized_selection']['omitted'] == [change['original_selection']['omitted'][0]]
    assert change['collapses'] == [{'disposition': 'omitted',
        'candidate_id': report['candidate_ids'][0], 'removed_count': 1, 'retained_index': 0,
        'retained_reason': 'First reason to omit the overlap.'}]
    assert manifest['selection_rounds'][0]['omitted'] == change['normalized_selection']['omitted']
    assert set(manifest['processed_evidence_ids']) == set(snapshot['evidence_ids'])
    selector.verify_manifest(manifest)


def test_correction_duplicates_are_audited_and_raw_correction_is_preserved(corpus):
    class CorrectionDuplicateClient(DuplicateOmissionClient):
        def generate_structured(self, **kwargs):
            if kwargs['output_model'].__name__ == 'RolePanel' and not any(
                    name == 'RolePanel' for name, _ in self.calls):
                data = json.loads(kwargs['user'])
                self.calls.append(('RolePanel', data))
                ids = [candidate['candidate_id'] for candidate in data['candidates']]
                return RolePanel.model_validate({'groups': [
                    {'representative_id': ids[0], 'member_ids': ids,
                     'rationale': 'Initial conflicting disposition.'}],
                    'omitted': [{'candidate_id': ids[1], 'reason': 'Also omitted, a genuine conflict.'}]})
            return super().generate_structured(**kwargs)

    store, _, _ = corpus
    run = auto_run(corpus)
    run['role_manifest']['selected_roles'] = [selector.as_selected(
        selector.proposed_defaults()[0], candidate_ids=['existing-lineage'])]
    client = CorrectionDuplicateClient()
    manifest = selector.select_roles(store, run, client)
    assert [name for name, _ in client.calls] == ['RoleCandidates', 'RolePanel', 'RolePanel']
    attempt = manifest['panel_accounting_repairs'][0]
    assert attempt['status'] == 'valid'
    assert attempt['validation_report'][0]['code'] == 'duplicate_disposition'
    assert len(attempt['corrected_selection']['omitted']) == 2
    assert attempt['normalized_selection']['omitted'] == [attempt['corrected_selection']['omitted'][0]]
    changes = manifest['batch_reports'][0]['panel_disposition_collapses']
    assert len(changes) == 1 and changes[0]['phase'] == 'correction'
    assert changes[0]['original_selection'] == attempt['corrected_selection']
    assert changes[0]['normalized_selection'] == attempt['normalized_selection']
    selector.verify_manifest(manifest)


class NoModelCalls:
    def __init__(self):
        self.calls = []

    def describe(self):
        return {'provider': 'offline-test', 'model': 'forbidden'}

    def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError('Saved migration must not call a model.')


@pytest.fixture
def duplicate_only_v10_run(tmp_path, monkeypatch):
    monkeypatch.setenv('RQ1_WORKFLOW_STORE', str(tmp_path / 'panel-recovery.sqlite3'))
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'mock')
    monkeypatch.delenv('RQ1_ROLE_SELECTION_MAX_BATCHES', raising=False)
    store = Store()
    source_ids = []
    for index in range(32):
        source = register_source(store, SourceRequest(
            artifact=ArtifactPayload(name=f'source-{index:02d}.md',
                content=f'Catalogue operators for source {index:02d} must maintain publication metadata.'),
            source_role='stakeholder_need'))
        source_ids.append(source['source_version_id'])
    snapshot = freeze_snapshot(store, SnapshotRequest(source_version_ids=source_ids))
    units = selector.selection_units(store, snapshot)
    assert len(units) == 32
    monkeypatch.setattr(selector, 'BATCH_CHARS', max(len(canonical(unit)) for unit in units) + 1)
    batches = selector.pack_batches(units)
    assert len(batches) == 32
    run = new_run(store, RunRequest(output_form='candidates', consolidation='exact',
        snapshot_id=snapshot['snapshot_id'], strategy='multi_agent', role_selection='automatic'))
    manifest = run['role_manifest']
    selected = selector.as_selected(selector.proposed_defaults()[0], candidate_ids=['original-member'],
                                    reason='Selected in preceding completed batches.')
    manifest.update(policy_version='rq1-stakeholder-selection-v10', status='failed',
                    last_error=FAILED_PANEL_ERROR, selected_roles=[selected])
    for index, batch in enumerate(batches):
        proposal = selector.proposed_defaults()[1].model_dump(mode='json')
        proposal['label'] = f'Publication perspective {index:02d}'
        candidate_id = OBSERVED_DUPLICATE_ID if index == 31 else f'role-candidate-completed-{index:02d}'
        manifest['candidates'].append({'candidate_id': candidate_id, 'batch_index': index, **proposal})
        manifest['batch_reports'].append({'batch_index': index,
            'evidence_ids': [batch[0]['evidence_id']], 'context_hash': digest({'tasks': [], 'units': batch}),
            'candidate_ids': [candidate_id], 'provider': {'provider': 'offline-test', 'model': 'saved-v10'}})
        manifest['validation_attempts'].append({'batch_index': index, 'phase': 'discovery',
            'status': 'valid', 'candidates': [proposal],
            'validation_report': [{'candidate_index': 0, 'label': proposal['label'], 'status': 'valid', 'errors': []}]})
        if index < 31:
            omission = {'candidate_id': candidate_id, 'reason': 'Overlapping publication remit.'}
            manifest['selection_rounds'].append({'batch_index': index,
                'provider': {'provider': 'offline-test', 'model': 'saved-v10'},
                'groups': [{'representative_id': selected['role_id'], 'member_ids': [selected['role_id']],
                            'rationale': 'Retain the selected role.'}], 'omitted': [omission]})
            manifest['processed_evidence_ids'].append(batch[0]['evidence_id'])
            manifest['omissions'].append({'batch_index': index, **omission, 'candidate_ids': [candidate_id]})
    raw = {'groups': [{'representative_id': selected['role_id'], 'member_ids': [selected['role_id']],
                      'rationale': 'Retain the existing role.'}],
           'omitted': [{'candidate_id': OBSERVED_DUPLICATE_ID, 'reason': 'First saved explanation.'},
                       {'candidate_id': OBSERVED_DUPLICATE_ID, 'reason': 'Second saved explanation.'}]}
    pool = [{'candidate_id': selected['role_id']}, {'candidate_id': OBSERVED_DUPLICATE_ID}]
    errors = selector.panel_accounting_errors(RolePanel.model_validate(raw), pool, manifest['max_roles'])
    assert [error['code'] for error in errors] == ['duplicate_disposition']
    manifest['panel_accounting_repairs'] = [{'batch_index': 31, 'phase': 'panel_accounting',
        'status': 'invalid', 'original_selection': deepcopy(raw), 'validation_report': deepcopy(errors),
        'corrected_selection': deepcopy(raw), 'correction_validation_report': deepcopy(errors)}]
    return store, snapshot, run


def test_v10_batch31_duplicate_only_recovery_reuses_all_saved_outputs_without_calls(duplicate_only_v10_run):
    store, snapshot, run = duplicate_only_v10_run
    original = deepcopy(run['role_manifest'])
    client = NoModelCalls()
    manifest = selector.select_roles(store, run, client)
    assert not client.calls
    assert manifest['status'] == 'completed'
    assert manifest['policy_version'] == 'rq1-stakeholder-selection-v11'
    assert manifest['selection_rounds'][:31] == original['selection_rounds']
    assert manifest['batch_reports'][:31] == original['batch_reports'][:31]
    assert manifest['validation_attempts'] == original['validation_attempts']
    assert manifest['candidates'] == original['candidates']
    assert set(manifest['processed_evidence_ids']) == set(snapshot['evidence_ids'])
    assert len(manifest['selection_rounds']) == 32
    attempt = manifest['panel_accounting_repairs'][0]
    for key in ('original_selection', 'corrected_selection', 'validation_report', 'correction_validation_report'):
        assert attempt[key] == original['panel_accounting_repairs'][0][key]
    assert attempt['status'] == 'valid'
    assert attempt['normalized_selection']['omitted'] == [attempt['corrected_selection']['omitted'][0]]
    assert attempt['recovery']['from_policy'] == 'rq1-stakeholder-selection-v10'
    assert attempt['recovery']['previous_status'] == 'invalid'
    assert manifest['migration_notes']
    assert 'v11' in manifest['migration_notes'][-1]
    changes = manifest['batch_reports'][31]['panel_disposition_collapses']
    assert len(changes) == 1
    assert changes[0]['phase'] == 'migration'
    assert changes[0]['original_selection'] == attempt['corrected_selection']
    assert changes[0]['normalized_selection'] == attempt['normalized_selection']
    assert changes[0]['collapses'][0]['candidate_id'] == OBSERVED_DUPLICATE_ID
    assert changes[0]['collapses'][0]['retained_reason'] == 'First saved explanation.'
    assert run['role_manifest'] == original  # The caller's original historical object is intact.
    selector.verify_manifest(manifest)


@pytest.mark.parametrize('failure', [
    'kept_and_omitted', 'mixed_report', 'incomplete_attempt', 'missing_response',
    'unrelated_last_error', 'missing_candidate', 'unknown_candidate', 'multiple_repairs'])
def test_v10_recovery_refuses_substantive_or_incomplete_failures(duplicate_only_v10_run, failure):
    store, _, run = duplicate_only_v10_run
    manifest = run['role_manifest']
    attempt = manifest['panel_accounting_repairs'][0]
    if failure == 'kept_and_omitted':
        attempt['corrected_selection']['groups'][0]['member_ids'].append(OBSERVED_DUPLICATE_ID)
    elif failure == 'mixed_report':
        attempt['correction_validation_report'].append({'code': 'unknown_candidate_ids', 'candidate_ids': ['missing']})
    elif failure == 'incomplete_attempt':
        attempt['status'] = 'started'
    elif failure == 'missing_response':
        del attempt['corrected_selection']
    elif failure == 'unrelated_last_error':
        manifest['last_error'] = 'Provider unavailable.'
    elif failure == 'missing_candidate':
        attempt['corrected_selection']['omitted'] = []
    elif failure == 'unknown_candidate':
        attempt['corrected_selection']['omitted'][1]['candidate_id'] = 'role-candidate-outside-registry'
    else:
        manifest['panel_accounting_repairs'].append(deepcopy(attempt))
    before = deepcopy(manifest)
    client = NoModelCalls()
    with pytest.raises(ValueError):
        selector.select_roles(store, run, client)
    assert not client.calls
    assert run['role_manifest'] == before

