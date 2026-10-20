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
