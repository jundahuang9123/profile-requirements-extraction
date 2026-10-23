"""The report reads saved machine results without reinterpreting legacy checks."""
import csv
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest


@pytest.mark.parametrize('check_field', [None, 'entries_express_need', 'verdict_supported'])
def test_saved_report_preserves_check_semantics_and_only_reads_api(tmp_path, monkeypatch, check_field):
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'fa_base_report.py'
    spec = importlib.util.spec_from_file_location('fa_base_report', path)
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    relation = {}
    if check_field:
        relation = {'verdict': 'domain_use_of_base', 'status': 'checked', 'effect': 'note',
                    'phase': 'before_discussion', 'classifier_state': {'need_class': 'domain'},
                    'check': {check_field: check_field == 'verdict_supported', 'nothing_lost': True,
                              'rationale': 'Saved machine judgement.'}}
    run = {'run_id': 'report-test', 'status': 'awaiting_human', 'active_revision_ids': ['revision-1'],
           'requirements': [{'revision_id': 'revision-1', 'need_statement': 'Find the contact details.',
                             'normalized_statement': 'Find the contact details.', 'need_class': 'domain',
                             'base_relation': relation}], 'deliberations': [], 'model_calls': []}
    before = deepcopy(run)
    reads = []
    def get(url):
        reads.append(url)
        if url.endswith('?audit=true'):
            return run
        assert url.endswith('/coverage')
        return {'counts': {'source_units': 1, 'processed_units': 1}}
    monkeypatch.setattr(report, 'get', get)
    monkeypatch.setattr(sys, 'argv', ['fa_base_report.py', '--api', 'http://local-test',
                                    '--run', 'report-test', '--out', str(tmp_path)])
    report.main()
    assert reads == ['http://local-test/api/rq1/v2/runs/report-test?audit=true',
                     'http://local-test/api/rq1/v2/runs/report-test/coverage']
    assert run == before
    with (tmp_path / 'base-review.csv').open(encoding='utf-8-sig', newline='') as f:
        row, = list(csv.DictReader(f))
    markdown = (tmp_path / 'base-review.md').read_text()
    if check_field:
        assert json.loads(row['check']) == relation['check']
        assert check_field in row['check_summary'] and check_field in markdown
        other = 'entries_express_need' if check_field == 'verdict_supported' else 'verdict_supported'
        assert other not in row['check_summary']
    else:
        assert row['reviewer'] == row['check_summary'] == ''
    assert 'Machine judgements only' in markdown
    assert 'not ancestral calls' in markdown


def test_report_separates_removed_labels_from_kept_disputes_and_lists_salvage(tmp_path, monkeypatch):
    # rq1-base-expert-v3 wrote "dispute" for a removed label; v4 writes flag_removed.
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'fa_base_report.py'
    spec = importlib.util.spec_from_file_location('fa_base_report', path)
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    def need(i, **relation):
        return {'revision_id': f'revision-{i}', 'need_statement': f'Need {i}.', 'normalized_statement': f'Need {i}.',
                'need_class': 'domain', 'base_relation': {'phase': 'before_discussion', 'classifier_state': {}, **relation}}
    run = {'run_id': 'report-test', 'status': 'awaiting_human', 'model_calls': [], 'metrics': {'salvaged_cases': 1},
           'active_revision_ids': [f'revision-{i}' for i in range(1, 5)],
           'requirements': [need(1, policy='rq1-base-expert-v4', effect='flag_removed', status='checked', verdict='new'),
                            need(2, policy='rq1-base-expert-v3', effect='dispute', status='checked', verdict='new'),
                            need(3, policy='rq1-base-expert-v2', effect='dispute', status='checked', verdict='new'),
                            need(4, policy='rq1-base-expert-v4', status='not_reviewed', reason='invalid_output',
                                 errors=['N1: cite only entries of this base’s index.'], isolated_from_failed_batch={'review': 'k'})],
           'deliberations': [{'case_id': 'case-1', 'stop_reason': 'bounded_fa_dialogue_salvaged', 'frozen_requirements': [],
                              'mediation': {'outcomes': [{'action_id': 'A2', 'action': 'add', 'salvage_rejected': True,
                                  'validation_errors': ['Additions are not applied from a salvaged plan.']}]}}]}
    monkeypatch.setattr(report, 'get', lambda url: run if url.endswith('?audit=true') else {'counts': {}})
    monkeypatch.setattr(sys, 'argv', ['fa_base_report.py', '--api', 'http://local-test', '--run', 'report-test', '--out', str(tmp_path)])
    report.main()
    markdown = (tmp_path / 'base-review.md').read_text()
    removed = markdown.split('## Labels removed')[1].split('\n## ')[0]
    kept = markdown.split('## Disputes (label kept; rq1-base-expert-v1/v2)')[1].split('\n## ')[0]
    assert 'Need 1.' in removed and 'Need 2.' in removed and 'Need 3.' not in removed
    assert 'Need 3.' in kept and 'Need 1.' not in kept and 'Need 2.' not in kept
    assert 'errors: N1: cite only entries' in markdown.split('## Not reviewed')[1].split('\n## ')[0]
    assert 'case-1 · add A2: Additions are not applied from a salvaged plan.' in markdown
    assert 'Salvaged cases (metrics): 1; mediator actions rejected by salvage: 1.' in markdown
    # Runs before rq1-fa-salvage-v2 have no count of salvages that kept no mediator action.
    assert 'Salvaged with no mediator action kept (metrics): not recorded; lost after such a salvage' in markdown
    assert 'v11 stopped these earlier as invalid output): not recorded.' in markdown
    # Runs before rq1-fa-dialogue-v13 have no count of ignored checks.
    ignored = markdown.split('## Checks of IDs outside the plan (ignored)')[1].split('\n## ')[0]
    assert ignored.strip() == 'Ignored checks (metrics): not recorded.'
    with (tmp_path / 'base-review.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = {r['revision_id']: r for r in csv.DictReader(f)}
    assert rows['revision-2']['policy'] == 'rq1-base-expert-v3' and rows['revision-4']['errors'].startswith('N1:')
    assert json.loads(rows['revision-4']['isolated']) == {'review': 'k'}


def test_report_lists_the_checks_the_v13_rule_ignored(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'fa_base_report.py'
    spec = importlib.util.spec_from_file_location('fa_base_report', path)
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    case = lambda i, **mediation: {'case_id': f'case-{i}', 'stop_reason': 'bounded_fa_dialogue_complete', 'frozen_requirements': [],
                                   'mediation': {'outcomes': [], **mediation}}
    run = {'run_id': 'report-test', 'status': 'awaiting_human', 'model_calls': [], 'active_revision_ids': [], 'requirements': [],
           'metrics': {'salvaged_cases': 0, 'ignored_checks': 3},
           'deliberations': [case(1, ignored_check_ids=['P1']), case(2), case(3, ignored_check_ids=['experience-1', 'S1'])]}
    monkeypatch.setattr(report, 'get', lambda url: run if url.endswith('?audit=true') else {'counts': {}})
    monkeypatch.setattr(sys, 'argv', ['fa_base_report.py', '--api', 'http://local-test', '--run', 'report-test', '--out', str(tmp_path)])
    report.main()
    ignored = (tmp_path / 'base-review.md').read_text().split('## Checks of IDs outside the plan (ignored)')[1].split('\n## ')[0]
    assert ignored.split() == 'Ignored checks (metrics): 3. - case-1: P1 - case-3: experience-1, S1'.split()


def test_report_lists_what_the_scope_contract_set_aside_and_blocked_apart(tmp_path, monkeypatch):
    # Scope contract v1: record-test set-asides at normalisation and scope blocks at apply, each counted apart.
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'fa_base_report.py'
    spec = importlib.util.spec_from_file_location('fa_base_report', path)
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    record = lambda i, text: {'revision_id': f'revision-{i}', 'need_statement': text, 'normalized_statement': text}
    run = {'run_id': 'report-test', 'status': 'awaiting_human', 'model_calls': [], 'active_revision_ids': ['revision-3'], 'metrics': {},
           'requirements': [record(1, 'Users can know that DCAT is a W3C Recommendation.'), record(2, 'Users can find the licence.'),
                            record(3, 'Users can find the dimensions of a dataset.')],
           'set_aside_observations': [
               {'revision_id': 'revision-1', 'need_id': 'need-1', 'reason': 'not_catalogue_level', 'rationale': 'A fact about the specification.',
                'details': {'profile_scope': {'record_resource': 'none'}, 'fa_scope': {'serves': 'find'}}},
               {'revision_id': 'revision-2', 'need_id': 'need-2', 'reason': 'fa_scope_set_aside', 'rationale': 'Serves neither.'}],
           'deliberations': [{'case_id': 'case-1', 'stop_reason': 'bounded_fa_dialogue_complete', 'frozen_requirements': [],
               'mediation': {'outcomes': [
                   {'action_id': 'A2', 'action': 'revise', 'status': 'blocked_change', 'scope_tests': [{}],
                    'scope_block': [{'revision_id': 'r', 'statement': 'Publishers must use all DCAT classes consistently.',
                                     'test': 'not_catalogue_level', 'record_resource': 'none', 'rationale': 'A rule for publishers.'}]},
                   {'action_id': 'A3', 'action': 'add', 'status': 'blocked_change',
                    'validation_error': 'F/A scope test budget exhausted; original needs retained.'},
                   {'action_id': 'A4', 'action': 'revise', 'status': 'blocked_change', 'validation_error': 'Ambiguous or unmatched source quotation.'},
                   {'action_id': 'A5', 'action': 'split', 'status': 'machine_revised', 'applied': True,
                    'scope_tests': [{'profile_scope': {'status': 'checked'}}, {'profile_scope': {'status': 'not_checked'}}]}]}}]}
    monkeypatch.setattr(report, 'get', lambda url: run if url.endswith('?audit=true') else {'counts': {}})
    monkeypatch.setattr(sys, 'argv', ['fa_base_report.py', '--api', 'http://local-test', '--run', 'report-test', '--out', str(tmp_path)])
    report.main()
    markdown = (tmp_path / 'base-review.md').read_text()
    normalisation = markdown.split('## Scope contract v1: set aside by the record test at normalisation')[1].split('\n## ')[0]
    assert "1 needs ({'not_catalogue_level': 1}); set aside by the F/A test: 1." in normalisation
    assert '- Users can know that DCAT is a W3C Recommendation. — not_catalogue_level; record: none; A fact about the specification.' in normalisation
    apply = markdown.split('## Scope contract v1: changes blocked by the scope tests at apply')[1].split('\n## ')[0]
    assert ("1 changes blocked by a failed test (first failure by test: {'not_catalogue_level': 1}; other blocked changes: 1); "
            "1 blocked because the scope tests' allowance ran out; "
            '2 changes tested; 1 applied needs without a record judgement (kept, flagged).') in apply
    assert '- case-1 · revise A2: Publishers must use all DCAT classes consistently. — not_catalogue_level; record: none; A rule for publishers.' in apply
