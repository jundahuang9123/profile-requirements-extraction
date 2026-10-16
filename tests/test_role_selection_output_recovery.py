"""A role-selection answer that fails its output contract keeps its usable rows instead of stopping."""
import json
from copy import deepcopy

import pytest

from test_role_selection import corpus, auto_run, SelectorClient, legacy_repair_run, RepairClient, two_batch_corpus
from test_reselect_stakeholders import derive
from requirement_reuse_service.llm.client import OutputTokenLimitError, OutputValidationError, validate_json_payload
from requirement_reuse_service.workflow import engine, role_selection as selector
from requirement_reuse_service.workflow.models import StakeholderPanel
from requirement_reuse_service.workflow.output_recovery import POLICY, salvage_rows
from requirement_reuse_service.workflow.stakeholder_registry import ACCOUNTING_REPAIR_POLICY

NO_JSON = OutputValidationError('Answer', [{'loc': [], 'type': 'json_object_missing'}], 'stop')


def invalid(payload, output_model):
    """What the provider client raises when its single schema correction still fails."""
    return validate_json_payload(json.dumps(payload), output_model)


ROLE = {'stakeholders': ['Catalogue operators'], 'purpose': 'Examine catalogue maintenance needs.',
        'rationale': 'The source states an operational responsibility.',
        'focus_questions': ['What metadata must be maintained?'], 'task_ids': []}


class BadRowDiscovery(SelectorClient):
    """The JRC stop: one candidate breaks the basis rule (an inferred role without support)."""
    def generate_structured(self, *, system, user, output_model, max_tokens=None, schema_repair_attempts=0):
        if output_model.__name__ != 'RoleCandidates':
            return super().generate_structured(system=system, user=user, output_model=output_model, max_tokens=max_tokens)
        data = json.loads(user); self.calls.append((output_model.__name__, data))
        span = data['evidence_units'][0]['source_spans'][0]['span_id']
        return invalid({'candidates': [
            {**ROLE, 'label': 'Catalogue operator', 'basis': 'documented', 'source_span_ids': [span]},
            {**ROLE, 'label': 'Data user', 'basis': 'inferred', 'source_span_ids': []},
            {**ROLE, 'label': 'Data publisher', 'basis': 'documented', 'source_span_ids': ['invented-span']},
            {**ROLE, 'label': ' ', 'basis': 'proposed', 'source_span_ids': []}]}, output_model)


def test_one_bad_discovery_row_keeps_the_others_and_the_run_continues(corpus):
    store, _, _ = corpus
    run = auto_run(corpus)
    client = BadRowDiscovery()
    engine.execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'awaiting_human', saved['diagnostics']
    manifest = saved['role_manifest']
    attempt = next(a for a in manifest['validation_attempts'] if a['phase'] == 'discovery')
    recovery = attempt['output_recovery']['row_recovery']
    assert recovery['policy'] == POLICY and 'schema validation for RoleCandidates' in recovery['error']
    assert [row['disposition'] for row in recovery['rows']] == ['kept', 'kept_after_clean_up', 'kept_after_clean_up', 'dropped']
    assert recovery['rows'][1]['changes'] == ['inferred_without_support_kept_as_proposed']
    assert recovery['rows'][2]['changes'] == ['removed_unknown_or_repeated_excerpt_ids',
                                              'documented_without_citation_kept_as_proposed']
    assert attempt['generated_candidates'] == recovery['raw_output']['candidates']
    found = {c['label']: (c['basis'], len(c['evidence_links'])) for c in manifest['candidates']}
    assert found == {'Catalogue operator': ('documented', 1), 'Data user': ('proposed', 0), 'Data publisher': ('proposed', 0)}
    assert all(c['rationale'] != ROLE['rationale'] for c in manifest['candidates'] if c['basis'] == 'proposed')
    assert sum(name == 'RoleCandidates' for name, _ in client.calls) == 1


def test_a_cut_off_discovery_answer_is_asked_once_more_with_a_larger_budget(corpus):
    class CutOffOnce(SelectorClient):
        budgets = []
        def generate_structured(self, **kwargs):
            if kwargs['output_model'].__name__ == 'RoleCandidates':
                self.budgets.append(kwargs['max_tokens'])
                if len(self.budgets) == 1:
                    raise OutputTokenLimitError('Model stopped at the output token limit (finish_reason=length).')
            return super().generate_structured(**kwargs)
    store, _, _ = corpus
    run = auto_run(corpus)
    client = CutOffOnce()
    manifest = selector.select_roles(store, run, engine.TrackedClient(client, store, run['run_id']))
    assert manifest['status'] == 'completed'
    assert client.budgets == [selector.DISCOVERY_OUTPUT_TOKENS, selector.DISCOVERY_RETRY_TOKENS]
    retry = manifest['validation_attempts'][0]['output_recovery']['cutoff_retry']
    assert retry['policy'] == POLICY and retry['max_output_tokens'] == selector.DISCOVERY_RETRY_TOKENS


def test_a_discovery_answer_with_nothing_usable_stops_and_resume_asks_again(corpus):
    class NoJsonOnce(SelectorClient):
        broken = True
        def generate_structured(self, **kwargs):
            if kwargs['output_model'].__name__ == 'RoleCandidates' and self.broken:
                self.calls.append(('RoleCandidates', None))
                raise NO_JSON
            return super().generate_structured(**kwargs)
    store, _, _ = corpus
    run = auto_run(corpus)
    client = NoJsonOnce()
    engine.execute_run(store, run['run_id'], client)
    failed = store.get('run', run['run_id'])
    assert failed['status'] == 'failed' and failed['role_manifest']['validation_attempts'] == []
    client.broken = False
    engine.execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'awaiting_human', saved['diagnostics']
    assert sum(name == 'RoleCandidates' for name, _ in client.calls) == 2


class SeparateRegistry(SelectorClient):
    """Registry answers keep entries separate; the first one has an invalid group row."""
    def __init__(self, correction='valid'):
        super().__init__(); self.correction = correction; self.registry_calls = 0
    def generate_structured(self, *, system, user, output_model, max_tokens=None, schema_repair_attempts=0):
        if output_model.__name__ != 'RoleRegistry':
            return super().generate_structured(system=system, user=user, output_model=output_model, max_tokens=max_tokens)
        data = json.loads(user); self.calls.append((output_model.__name__, data)); self.registry_calls += 1
        groups = [{'representative_id': c['candidate_id'], 'member_ids': [c['candidate_id']],
                   'rationale': 'Distinct scripted perspective.'} for c in data['candidates']]
        if self.registry_calls == 1:
            groups[-1]['rationale'] = ''
            return invalid({'groups': groups}, output_model)
        if self.registry_calls == 2 and self.correction == 'unusable':
            raise NO_JSON
        return output_model.model_validate({'groups': groups})


@pytest.mark.parametrize('correction', ['valid', 'unusable'])
def test_registry_answer_keeps_valid_groups_and_completes_through_correction_or_repair(corpus, monkeypatch, correction):
    store, _, _ = corpus
    two_batch_corpus(corpus, monkeypatch)
    run = auto_run(corpus)
    client = SeparateRegistry(correction)
    manifest = selector.select_roles(store, run, engine.TrackedClient(client, store, run['run_id']))
    assert manifest['status'] == 'completed'
    record = manifest['registry_calls'][0]
    initial = record['output_recoveries'][0]
    assert initial['policy'] == POLICY and initial['phase'] == 'initial' and initial['usable']
    assert [(row['field'], row['index']) for row in initial['dropped_rows']] == [('groups', 1)]
    assert record['validation_errors']
    if correction == 'valid':
        assert record['correction']['status'] == 'valid' and 'repair' not in record
    else:
        assert record['output_recoveries'][1]['phase'] == 'correction' and not record['output_recoveries'][1]['usable']
        assert record['correction']['original'] is None and record['correction']['status'] == 'invalid'
        assert record['repair']['policy'] == ACCOUNTING_REPAIR_POLICY
        assert record['repair']['changes']['missing_ids_kept_separate']
    assert len(manifest['registry']) == 2  # nothing merged that the model did not merge


class ChoiceWithBadVerdict(SelectorClient):
    """Two separate entries; the first panel answer has one verdict without a reason."""
    def __init__(self, initial='bad_row'):
        super().__init__(); self.initial = initial; self.panel_calls = 0
    def generate_structured(self, *, system, user, output_model, max_tokens=None, schema_repair_attempts=0):
        name = output_model.__name__
        if name == 'RoleRegistry':
            data = json.loads(user); self.calls.append((name, data))
            return output_model.model_validate({'groups': [{'representative_id': c['candidate_id'],
                'member_ids': [c['candidate_id']], 'rationale': 'Distinct scripted perspective.'} for c in data['candidates']]})
        if name != 'StakeholderPanel':
            return super().generate_structured(system=system, user=user, output_model=output_model, max_tokens=max_tokens)
        data = json.loads(user); self.calls.append((name, data)); self.panel_calls += 1
        entries = data['entries']
        answer = {'verdicts': [{'entry_id': e['entry_id'], 'relevant': True, 'reason': 'Scripted relevance.'}
                               for e in entries], 'kept_ids': [e['entry_id'] for e in entries][:data['max_roles']]}
        if self.panel_calls == 1 and self.initial == 'no_json':
            raise NO_JSON
        if self.panel_calls == 1:
            answer['verdicts'][1]['reason'] = ''
            return invalid(answer, output_model)
        return output_model.model_validate(answer)


def test_panel_answer_with_one_invalid_verdict_keeps_the_rest_and_continues(corpus, monkeypatch):
    store, _, _ = corpus
    two_batch_corpus(corpus, monkeypatch)
    run = auto_run(corpus)
    client = ChoiceWithBadVerdict()
    manifest = selector.select_roles(store, run, engine.TrackedClient(client, store, run['run_id']))
    assert manifest['status'] == 'completed' and len(manifest['selected_roles']) == 2
    record = manifest['panel_calls'][0]
    assert record['output_recoveries'][0]['usable']
    assert [(row['field'], row['index']) for row in record['output_recoveries'][0]['dropped_rows']] == [('verdicts', 1)]
    assert record['validation_errors'][0]['code'] == 'verdict_accounting'
    assert record['correction']['status'] == 'valid'


def test_panel_answer_with_nothing_usable_stops_and_resume_asks_again(corpus, monkeypatch):
    store, _, _ = corpus
    two_batch_corpus(corpus, monkeypatch)
    run = auto_run(corpus)
    client = ChoiceWithBadVerdict('no_json')
    with pytest.raises(OutputValidationError):
        selector.select_roles(store, run, engine.TrackedClient(client, store, run['run_id']))
    saved = store.get('run', run['run_id'])
    record = saved['role_manifest']['panel_calls'][0]
    assert 'original' not in record and not record['output_recoveries'][0]['usable']
    manifest = selector.select_roles(store, saved, engine.TrackedClient(client, store, run['run_id']))
    assert manifest['status'] == 'completed'
    assert client.panel_calls == 2 and not any(name == 'RoleCandidates' for name, _ in client.calls[2:])


def test_citation_repair_answer_with_nothing_usable_keeps_the_candidate_as_proposed(corpus):
    class RepairOutputFailure(RepairClient):
        def generate_structured(self, **kwargs):
            if kwargs['output_model'].__name__ == 'RoleCitationCorrections':
                self.calls.append(('RoleCitationCorrections', json.loads(kwargs['user'])))
                raise NO_JSON
            return super().generate_structured(**kwargs)
    store, _, _ = corpus
    run = legacy_repair_run(corpus)
    client = RepairOutputFailure()
    manifest = selector.select_roles(store, run, engine.TrackedClient(client, store, run['run_id']))
    assert manifest['status'] == 'completed'
    repair = next(a for a in manifest['validation_attempts'] if a['phase'] == 'citation_repair')
    assert repair['status'] == 'valid' and repair['output_recovery']['policy'] == POLICY
    assert not repair['output_recovery']['usable'] and repair['fallback']['retained_as_proposed'] == [1]
    candidate = next(c for c in manifest['candidates'] if c['label'] == 'Data publisher')
    assert candidate['basis'] == 'proposed' and candidate['evidence_links'] == []
    assert sum(name == 'RoleCitationCorrections' for name, _ in client.calls) == 1


def recovered_scan(corpus):
    store, _, _ = corpus
    run = auto_run(corpus)
    manifest = selector.select_roles(store, run, engine.TrackedClient(BadRowDiscovery(), store, run['run_id']))
    store.mutate(run['run_id'], None, 'fixture_completed_scan', lambda r: (
        r.update(role_manifest=manifest), r['stages'].update(role_selection='completed')))
    return store, store.get('run', run['run_id'])


def test_a_recovered_scan_can_be_reused_for_a_new_panel_without_discovery_calls(corpus):
    store, source = recovered_scan(corpus)
    trial = derive(store, source)
    assert trial['role_manifest']['candidates'] == source['role_manifest']['candidates']
    client = SelectorClient()
    engine.execute_run(store, trial['run_id'], client)
    saved = store.get('run', trial['run_id'])
    assert saved['stages']['role_selection'] == 'completed', saved['diagnostics']
    assert not any(name == 'RoleCandidates' for name, _ in client.calls)


def test_a_tampered_recovery_audit_is_refused_for_reuse(corpus):
    store, source = recovered_scan(corpus)
    changed = deepcopy(source['role_manifest'])
    attempt = next(a for a in changed['validation_attempts'] if a['phase'] == 'discovery')
    attempt['output_recovery']['row_recovery']['raw_output']['candidates'][1]['basis'] = 'proposed'
    selector.seal_manifest(store, changed)
    store.mutate(source['run_id'], None, 'fixture_tampered_scan', lambda r: r.update(role_manifest=changed))
    with pytest.raises(ValueError, match='does not reproduce'):
        derive(store, store.get('run', source['run_id']))


def test_salvage_keeps_valid_rows_and_resets_only_defaulted_fields():
    verdict = {'entry_id': 'a', 'relevant': True, 'reason': 'Relevant.'}
    answer, dropped = salvage_rows(StakeholderPanel, {'verdicts': [verdict, {'entry_id': 'b', 'relevant': True,
        'reason': ''}], 'kept_ids': ['a'] * 9})
    assert [v.entry_id for v in answer.verdicts] == ['a'] and answer.kept_ids == []
    assert dropped[0]['index'] == 1 and dropped[1] == {'field': 'kept_ids', 'reset_to_default': True}
    assert 'Relevant.' not in json.dumps(dropped)  # paths, types and messages only
    assert salvage_rows(StakeholderPanel, {'verdicts': [{'entry_id': 'b', 'relevant': True, 'reason': ''}]})[0] is None
    assert salvage_rows(StakeholderPanel, None) == (None, [])
