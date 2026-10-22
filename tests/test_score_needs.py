"""rq1-need-scores-v1: read-only scores of the needs of a saved run. Synthetic records only; no run data,
no reference rows."""
import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _load():
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'score_needs.py'
    spec = importlib.util.spec_from_file_location('score_needs', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S = _load()
EXTRACTOR = ['shared_source_extractor']


def proposal(rid, raw, roles=EXTRACTOR):
    """A normalised proposal: an extracted statement, no parents, no need statement."""
    return {'revision_id': rid, 'requirement_id': 'req-' + rid, 'need_statement': None, 'normalized_statement': raw,
            'raw_statement': raw, 'parent_revision_ids': [], 'contributing_roles': list(roles), 'evidence_links': []}


def need(rid, text, parents=(), quotes=(), roles=EXTRACTOR, support='explicit', serves='find',
         nature='information_requirement', **extra):
    return {'revision_id': rid, 'requirement_id': 'req-' + rid, 'need_statement': text, 'normalized_statement': text,
            'raw_statement': text, 'need_condition': '', 'scope': 'Unspecified', 'parent_revision_ids': list(parents),
            'contributing_roles': list(roles),
            'evidence_links': [{'evidence_id': f'eu-{i}', 'quote': q, 'relation': 'supports'} for i, q in enumerate(quotes)],
            'qualification': {'support': support} if support else None,
            'fa_scope': {'status': 'checked', 'support': 'explicit', 'serves': serves, 'nature': nature},
            'processing_flags': [], **extra}


def run_of(*records, active):
    return {'run_id': 'run-test', 'status': 'awaiting_human', 'requirements': list(records), 'active_revision_ids': list(active)}


def only(run):
    rows = S.score_run(run)
    assert len(rows) == 1
    return rows[0]


def test_a_need_from_one_word_keeps_full_support_but_half_its_wording():
    # The JRC creator need: its only quote is the word "Creator".
    row = only(run_of(proposal('p1', 'Users can know the creator of a dataset.'),
                      need('n1', 'Users can know the creator of a dataset.', parents=['p1'], quotes=['Creator']), active=['n1']))
    assert (row['F1'], row['F2'], row['F3'], row['F4']) == (1.0, 0.5, 1.0, 1.0)
    assert row['F'] == 0.875 and (row['R1'], row['R2'], row['R3']) == (1.0, 1.0, None) and row['R'] == 1.0
    assert (row['origin'], row['rewording_steps'], row['extracted_proposals']) == ('consolidated', 1, 1)


def test_a_statement_about_a_policy_stays_close_to_its_source_but_is_no_user_need():
    quote = 'JRC data shall be provided with free, full, open and timely access'
    text = 'The policy obliges that JRC data shall be provided with free, full, open and timely access.'
    row = only(run_of(proposal('p1', 'Users can know that JRC data shall be provided with free, full, open and timely access.'),
                      need('n1', text, parents=['p1'], quotes=[quote]), active=['n1']))
    # 10 content words; 'policy' and 'obliges' are not in the quote.
    assert row['R2'] == 0.0 and row['F2'] == pytest.approx(8 / 10)
    assert row['F'] > 0.8 and row['R'] == 0.5


def test_a_need_the_discussion_added_has_no_extracted_statement_and_no_scope_judgement():
    added = need('n1', 'Users can obtain the download URL of a distribution.', quotes=['The download URL of a distribution'],
                 roles=['evidence_mediator'], processing_flags=['mediated_machine_proposal'],
                 fa_scope={'status': 'checked_mediation', 'rationale': 'Mediation check passed.'})
    row = only(run_of(added, active=['n1']))
    assert row['origin'] == 'discussion_added' and row['F3'] is None and row['R1'] is None
    assert row['F'] == pytest.approx((row['F1'] + row['F2'] + row['F4']) / 3) and row['R'] == row['R2'] == 1.0
    assert row['support_from'] == 'qualification'


def test_a_revised_need_is_measured_against_the_closer_of_its_extracted_statements():
    records = [proposal('p1', 'Users can know the landing page of a dataset.'),
               proposal('p2', 'A landing page URL must be given for every dataset in the catalogue.', roles=['stakeholder-1']),
               need('m1', 'Users can know the landing page of a dataset.', parents=['p1', 'p2']),
               need('n1', 'Users can know the landing page URL for a dataset.', parents=['m1'],
                    processing_flags=['mediated_machine_proposal'])]
    row = only(run_of(*records, active=['n1']))
    # 10 words against 9: replace "of" by "URL", insert "for" -> 2 edits of 10.
    assert row['F3'] == pytest.approx(0.8)
    assert (row['origin'], row['rewording_steps'], row['extracted_proposals']) == ('discussion_revised', 2, 2)


def test_a_condition_or_obligation_not_in_the_quotes_counts_as_added():
    base = dict(parents=['p1'], quotes=['Metadata shall be open even if access to the data is restricted.'])
    records = [proposal('p1', 'x')]
    stated = only(run_of(*records, need('n1', 'Users can know whether metadata is open.', need_condition='if access is restricted', **base), active=['n1']))
    assert stated['F4'] == 1.0 and stated['added'] == ''
    added = only(run_of(*records, need('n1', 'Users can know whether metadata is open.', need_condition='when the publisher agrees',
                                       unbacked_obligation={'label': 'mandatory', 'reason': 'no_quote'}, **base), active=['n1']))
    assert added['F4'] == 0.0 and added['added'] == 'obligation, condition_or_scope'
    placeholder = only(run_of(*records, need('n1', 'Users can know whether metadata is open.', **base), active=['n1']))
    assert placeholder['F4'] == 1.0
    scoped = only(run_of(*records, need('n1', 'Users can know whether metadata is open.', scope='statistical tables', **base), active=['n1']))
    assert scoped['F4'] == 0.5


@pytest.mark.parametrize('serves,nature,expected', [('find', 'information_requirement', 1.0), ('both', 'information_requirement', 1.0),
    ('find', 'operational_obligation', 0.5), ('neither', 'information_requirement', 0.0), ('find', 'background', 0.0),
    ('access', 'implementation_detail', 0.0), ('unresolved', 'uncertain', None)])
def test_find_access_judgement(serves, nature, expected):
    assert only(run_of(need('n1', 'Users can know the title of a dataset.', serves=serves, nature=nature), active=['n1']))['R1'] == expected


@pytest.mark.parametrize('text,expected', [
    ('Users can know the unit of measure of an observation.', 1.0),
    ('Data users are able to find the licence of a dataset.', 1.0),
    ('Publishers can state the update frequency of a dataset.', 1.0),
    ('Users can know that JRC data shall be provided free of charge.', 0.0),
    ('Metadata for JRC datasets shall be open for access.', 0.0),
    ('The policy obliges that data are provided openly.', 0.0),
    ('The JRC data policy defines open access as the default.', 0.0),
    ('Title of a dataset.', 0.5)])
def test_worded_as_a_user_need(text, expected):
    assert only(run_of(need('n1', text), active=['n1']))['R2'] == expected


@pytest.mark.parametrize('scope,expected', [({'record_resource': 'dataset', 'catalogue_level': True, 'serves': 'find'}, 1.0),
    ({'record_resource': 'distribution', 'catalogue_level': False, 'serves': 'access'}, 0.5),
    ({'record_resource': 'none', 'catalogue_level': False, 'serves': 'neither'}, 0.0)])
def test_catalogue_level_from_the_profile_scope_judge(scope, expected):
    record = need('n1', 'Users can know the title of a dataset.', fa_scope=None, profile_scope=scope)
    row = only(run_of(record, active=['n1']))
    assert row['R3'] == expected and row['R1'] == (0.0 if scope['serves'] == 'neither' else 1.0)


def test_only_active_needs_are_scored_and_a_trimmed_run_scores_the_same():
    records = [proposal('p1', 'Users can know the creator of a dataset.'),
               need('n1', 'Users can know the creator of a dataset.', parents=['p1'], quotes=['Creator'], extra_field={'x': 1}),
               need('n2', 'Users can know the title of a dataset.', parents=['p1'])]
    run = {**run_of(*records, active=['n1']), 'model_calls': [{'x': 1}], 'deliberations': [{'case_id': 'c'}]}
    assert [r['revision_id'] for r in S.score_run(run)] == ['n1']
    small = S.trimmed(run)
    assert S.score_run(small) == S.score_run(run)
    # n1 in full, p1 for its lineage only, n2 (not active, no descendant active) left out.
    assert set(small) == set(S.RUN_FIELDS) and [r['revision_id'] for r in small['requirements']] == ['p1', 'n1']
    assert set(small['requirements'][0]) == set(S.LINEAGE_FIELDS) and 'extra_field' not in small['requirements'][1]


def test_stems_fold_plural_and_verb_endings_alike():
    assert [S.stem(w) for w in ('datasets', 'dataset', 'licences', 'categories', 'publishing', 'published', 'access', 'classes')] == \
        ['dataset', 'dataset', 'licence', 'category', 'publish', 'publish', 'access', 'class']


def test_rank_correlation_of_two_runs_on_needs_with_the_same_statement():
    rows = [{'statement': f'Need {i}.', 'F': f, 'R': 1.0} for i, f in enumerate([0.9, 0.5, 0.7, 0.2])]
    other = [{'statement': f' need {i}. ', 'F': f, 'R': 1.0} for i, f in enumerate([0.8, 0.4, 0.6, 0.3])]
    result = S.compare(rows, other + [{'statement': 'Other.', 'F': 0.1, 'R': 0.1}])
    assert result['matched'] == 4 and result['spearman_F'] == pytest.approx(1.0) and result['spearman_R'] is None


def test_the_script_reads_with_get_only_and_writes_the_csv_and_summary(tmp_path, monkeypatch):
    run = run_of(proposal('p1', 'Users can know the creator of a dataset.'),
                 need('n1', 'Users can know the creator of a dataset.', parents=['p1'], quotes=['Creator']), active=['n1'])
    seen = []

    class Response:
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, *a): return self.body

    def urlopen(request, timeout=None):
        url = request if isinstance(request, str) else request.full_url
        assert isinstance(request, str) or request.get_method() == 'GET'
        seen.append(url)
        return Response(json.dumps(run).encode())

    monkeypatch.setattr(S.urllib.request, 'urlopen', urlopen)
    monkeypatch.setattr(sys, 'argv', ['score_needs.py', '--api', 'http://local-test/', '--run', 'run-test',
                                      '--compare', 'run-test', '--out', str(tmp_path)])
    S.main()
    assert seen == ['http://local-test/api/rq1/v2/runs/run-test?audit=false'] * 2
    rows = list(csv.DictReader((tmp_path / 'run-test-need-scores.csv').open(encoding='utf-8-sig')))
    assert len(rows) == 1 and rows[0]['F'] == '0.88' and rows[0]['R3'] == '' and rows[0]['R'] == '1.00'
    text = (tmp_path / 'run-test-need-scores.md').read_text(encoding='utf-8')
    assert S.VERSION in text and '1 of 1 needs have the same statement' in text
    saved = tmp_path / 'saved.json'
    saved.write_text(json.dumps(S.trimmed(run)), encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['score_needs.py', '--run', str(saved), '--out', str(tmp_path / 'file')])
    S.main()
    assert (tmp_path / 'file' / 'run-test-need-scores.csv').read_text(encoding='utf-8-sig') == \
        (tmp_path / 'run-test-need-scores.csv').read_text(encoding='utf-8-sig')
