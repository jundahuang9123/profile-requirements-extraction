#!/usr/bin/env python3
"""Integrity checks for the merged v3 reference sets (evaluator-only; no app imports).

Checks the structure of every case file, that all published v1 identities are kept, that counts and
derived flags are consistent (including merged and umbrella atoms and the overlap review), that every
evidence path is in the case's runtime allowlist for its mode, that the coverage ledger points to
existing atoms, and, where pdftotext is installed, that every anchor quote occurs in the reference PDF
and every evidence quote occurs in the cited runtime input.

Passing means structurally valid. It does not approve the sets for quantitative evaluation: the
evidence labels are AI labels and the atoms are not independently adjudicated as a whole.

    python3 benchmark-data/reference-sets-v3/validate_v3.py [--report VALIDATION.json]
"""
import argparse
import collections
import csv
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BD = HERE.parent
CASES = {
    'mobilitydcat': ('consolidated-requirements.json', None),
    'healthdcat': ('curated-requirements.json', 'healthdcat/reference-requirements/d6.2-requirements-and-profile.pdf'),
    'statdcat': ('requirements-and-resolutions.json', 'statdcat/reference-requirements/stat-final.pdf'),
    'geodcat': ('alignment-requirements.json', 'geodcat/reference-requirements/geo-final.pdf'),
    'jrc-research': ('core-requirements.json', None),
}
RELATIONS = {'restates_base', 'tightens_base', 'extends_base', 'partly_base', 'beyond_base', 'not_term_level', 'unresolved'}
STATUSES = {'requirement', 'proposed', 'deferred', 'open_issue', 'guidance'}
LABELS = {'supported', 'partial', 'uncertain', 'unsupported'}
OVERLAP_RELATIONS = {'equivalent', 'subsumes', 'subsumed_by', 'related'}


def norm(s):
    s = (s.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
         .replace(' ', ' ').replace('‑', '-').replace('­', ''))
    return re.sub(r'\s+', ' ', s).strip()


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip, self.parts = 0, []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


_cache = {}


def texts(rel, modes=('-layout',)):
    """Normalised text variants of a corpus file, or None when it cannot be read here."""
    key = (rel, modes)
    if key in _cache:
        return _cache[key]
    p = BD / rel
    out = None
    if p.suffix == '.pdf':
        if shutil.which('pdftotext'):
            out = []
            for m in modes:
                t = subprocess.run(['pdftotext', m, str(p), '-'], capture_output=True, text=True).stdout
                out.append(norm(t))
                out.append(norm(''.join(f'\n=== [page {i}] ===\n{pg}' for i, pg in enumerate(t.split('\f'), start=1) if pg.strip())))
    elif p.suffix == '.html':
        v = VisibleText()
        v.feed(p.read_text(encoding='utf-8', errors='replace'))
        out = [norm(' '.join(v.parts))]
    elif p.suffix == '.json':
        out = [norm(json.dumps(json.loads(p.read_text(encoding='utf-8')), indent=1, ensure_ascii=False))]
    if out:
        out += [t.replace('- ', '-') for t in out]
    _cache[key] = out
    return out


def contains(variants, quote):
    parts = [x.strip(' .') for x in re.split(r'\.\.\.|…|\[\.\.\.\]', quote) if len(x.strip(' .')) >= 12] or [quote]
    return all(any(norm(x) in t or norm(x).replace('- ', '-') in t for t in variants) for x in parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report', type=Path)
    args = ap.parse_args()
    errors, notes, summary = [], [], {}
    anchors = collections.Counter()
    quotes = collections.Counter()
    allow = json.loads((BD / 'runtime-inputs.json').read_text(encoding='utf-8'))['benchmarks']
    ledger = list(csv.DictReader((HERE / 'coverage-ledger.csv').read_text(encoding='utf-8').splitlines()))
    all_ids = {}
    for case, (v1_name, ref_pdf) in CASES.items():
        d = json.loads((HERE / f'{case}.json').read_text(encoding='utf-8'))
        rows, atoms = d['requirements'], d['atoms']
        if d.get('schema_version') != 'rq1-reference-set-3' or d.get('case') != case:
            errors.append(f'{case}: wrong schema_version or case')
        rid = [r['id'] for r in rows]
        aid = [a['id'] for a in atoms]
        errors += [f'{case}: duplicate row {k}' for k, v in collections.Counter(rid).items() if v > 1]
        errors += [f'{case}: duplicate atom {k}' for k, v in collections.Counter(aid).items() if v > 1]
        rows_by = {r['id']: r for r in rows}
        atoms_by = {a['id']: a for a in atoms}
        all_ids[case] = set(atoms_by)
        v1 = json.loads((BD / case / 'reference-requirements' / v1_name).read_text(encoding='utf-8'))['requirements']
        for r in v1:
            row = rows_by.get(r['id'])
            if not row:
                errors.append(f'{case}: v1 row {r["id"]} missing')
            elif row['statement'] != r['statement'] and row.get('statement_before_v3') != r['statement']:
                errors.append(f'{case}: v1 row {r["id"]} changed without statement_before_v3')
        for r in rows:
            if not r.get('atom_ids'):
                errors.append(f'{case}: row {r["id"]} has no atoms')
            if sorted(r.get('atom_ids', [])) != sorted(a['id'] for a in atoms if a['parent_id'] == r['id']):
                errors.append(f'{case}: row {r["id"]} atom_ids inconsistent')
        for a in atoms:
            p = a['parent_id']
            if p not in rows_by or not a['id'].startswith(p + '.'):
                errors.append(f'{case}: atom {a["id"]} has a bad parent')
            if a['stratum'] not in ('content', 'profile', 'system'):
                errors.append(f'{case}: atom {a["id"]} bad stratum')
            if a['relation_to_base'] not in RELATIONS:
                errors.append(f'{case}: atom {a["id"]} bad relation_to_base')
            if a['status_in_source'] not in STATUSES:
                errors.append(f'{case}: atom {a["id"]} bad status_in_source')
            if a['restates_dcat_ap'] != (a['relation_to_base'] == 'restates_base'):
                errors.append(f'{case}: atom {a["id"]} restates_dcat_ap inconsistent')
            if a['scored_by_default'] != (a['stratum'] == 'content' and a['status_in_source'] != 'deferred'
                                          and not a.get('merged_into') and not a.get('umbrella_of')):
                errors.append(f'{case}: atom {a["id"]} scored_by_default inconsistent')
            for o in a['overlaps']:
                if o not in atoms_by or a['id'] not in atoms_by[o]['overlaps']:
                    errors.append(f'{case}: overlap {a["id"]} -> {o} missing or one-way')
            reviewed = [r['atom'] for r in a.get('overlap_review', [])]
            if sorted(reviewed) != sorted(a['overlaps']) or any(r['relation'] not in OVERLAP_RELATIONS for r in a.get('overlap_review', [])):
                errors.append(f'{case}: atom {a["id"]} overlap_review does not cover its overlaps once each')
            m = a.get('merged_into')
            if m and (m not in atoms_by or not atoms_by[m]['scored_by_default'] or a['id'] not in atoms_by[m].get('merged_from', [])):
                errors.append(f'{case}: atom {a["id"]} merged_into {m} invalid')
            for c in a.get('umbrella_of', []):
                if c not in atoms_by or not atoms_by[c]['scored_by_default']:
                    errors.append(f'{case}: umbrella {a["id"]} names {c}, which is missing or not scored')
            # anchor quote against the reference document
            if a.get('anchor_check') == 'verbatim_in_source_text':
                v = texts(ref_pdf, ('-layout', '-raw')) if ref_pdf else None
                if v is None:
                    anchors['skipped (pdftotext not installed)'] += 1
                elif contains(v, a['anchor_quote']):
                    anchors['verified'] += 1
                else:
                    anchors['not found'] += 1
                    errors.append(f'{case}: anchor of {a["id"]} not found in {ref_pdf}')
            else:
                anchors[a.get('anchor_check', 'none').split(':')[0]] += 1
            # evidence quotes against the runtime inputs
            ie = a.get('input_evidence')
            if isinstance(ie, dict):
                for kind in ('raw', 'consolidation'):
                    b = ie.get(kind)
                    if not b:
                        continue
                    if b['label'] not in LABELS:
                        errors.append(f'{case}: atom {a["id"]} bad {kind} label')
                    for s in b['sources']:
                        if s['path'] not in allow[case][kind]:
                            errors.append(f'{case}: {kind} evidence of {a["id"]} cites {s["path"]}, which is not in the {kind} allowlist')
                        if s.get('quote_check') != 'verbatim_in_input_text':
                            quotes['recorded as not found'] += 1
                            continue
                        v = texts(s['path'])
                        if v is None:
                            quotes['skipped (pdftotext not installed)'] += 1
                        elif contains(v, s['quote']):
                            quotes['verified'] += 1
                        else:
                            quotes['not found'] += 1
                            errors.append(f'{case}: {kind} evidence quote of {a["id"]} not found in {s["path"]}')
        # counts recomputed
        c = d['counts']
        scored = [a for a in atoms if a['scored_by_default']]
        for k, val in (('atoms', len(atoms)), ('rows', len(rows)), ('scored_by_default', len(scored)),
                       ('scored_by_default_without_dcat_ap_restatements', sum(not a['restates_dcat_ap'] for a in scored))):
            if c.get(k) != val:
                errors.append(f'{case}: counts.{k} is {c.get(k)}, recomputed {val}')
        summary[case] = {'rows': len(rows), 'atoms': len(atoms), 'scored_by_default': len(scored)}
    for r in ledger:
        if r['atom_id'] not in all_ids.get(r['case'], set()):
            errors.append(f'coverage-ledger.csv: {r["input_id"]} points to unknown atom {r["case"]}/{r["atom_id"]}')
    for name, n in (('atoms-review.csv', sum(v['atoms'] for v in summary.values())),
                    ('reference-coverage.csv', sum(v['atoms'] for v in summary.values()))):
        rows = list(csv.reader((HERE / name).read_text(encoding='utf-8').splitlines()))
        if len(rows) - 1 != n or any(len(r) != len(rows[0]) for r in rows):
            errors.append(f'{name}: expected {n} single-line rows')
    if not shutil.which('pdftotext'):
        notes.append('pdftotext not installed: PDF anchor and evidence quotes were not re-checked.')
    notes.append('Structurally valid only: not an approval for quantitative evaluation (AI evidence labels; no independent adjudication of the whole set).')
    report = {'status': 'passed' if not errors else 'failed', 'cases': summary, 'anchor_quotes': dict(anchors),
              'evidence_quotes': dict(quotes), 'errors': errors, 'notes': notes}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    sys.exit(0 if not errors else 1)


if __name__ == '__main__':
    main()
