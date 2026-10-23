"""Write the mock benchmark summary (Markdown) from out/mock-benchmark-results.json and the CSVs.

Evidence-eligible atoms only (raw input-evidence label supported, or supported or partial)."""
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(f'{HERE}/out/mock-benchmark-results.json', encoding='utf-8'))
ATOM = list(csv.DictReader(open(f'{HERE}/out/atom-by-run.csv', encoding='utf-8')))
DIFF = list(csv.DictReader(open(f'{HERE}/out/discussion-effect.csv', encoding='utf-8'))) if os.path.exists(f'{HERE}/out/discussion-effect.csv') else []
ORDER = ['6a-cancelled', 'v6', 'v8', 'v9', 'v10', 'v11', 'v11+needs-v3']
RANK = {'equivalent': 6, 'equivalent_used_elsewhere': 5, 'broader': 4, 'narrower': 3, 'partial': 2, 'conflicts': 1, 'none': 0}
SHORT = {'equivalent': 'E', 'broader': 'b', 'narrower': 'n', 'partial': 'p', 'conflicts': 'x', 'none': '·', 'equivalent_used_elsewhere': 'e*'}
REF_COMMIT = os.environ.get('RQ1_REF_COMMIT', 'working copy')


def frac(d):
    return f"{d['recovered']}/{d['n']}"


def runs_of(case):
    return sorted([r for r in R['runs'] if r['case'] == case and r['label'] != '6a-cancelled'], key=lambda r: ORDER.index(r['label']))


def key_table():
    by = {(r['case'], r['label']): r for r in R['runs']}
    first = {c: next(r for r in R['runs'] if r['case'] == c and r['label'] == 'v8') for c in ('jrc', 'stat')}

    def cells(r, view='active'):
        if r is None:
            return ['–', '–']
        return [frac(r[f'{view}.raw_supported']), frac(r[f'{view}.raw_supported_or_partial'])]

    n = R['cases']
    out = [f"| Version | JRC: supported ({n['jrc']['denominators']['raw_supported']}) | JRC: supported or partial ({n['jrc']['denominators']['raw_supported_or_partial']}) "
           f"| Stat: supported ({n['stat']['denominators']['raw_supported']}) | Stat: supported or partial ({n['stat']['denominators']['raw_supported_or_partial']}) |",
           '|---|---:|---:|---:|---:|',
           '| before the discussion (6a input) | ' + ' | '.join(cells(first['jrc'], 'pre_discussion') + cells(first['stat'], 'pre_discussion')) + ' |']
    for v in ('v6', 'v8', 'v9', 'v10', 'v11'):
        out.append(f'| {v} | ' + ' | '.join(cells(by.get(('jrc', v))) + cells(by.get(('stat', v)))) + ' |')
    n3 = by[('jrc', 'v11+needs-v3')]
    out.append('| needs v3 (#44), before the discussion | ' + ' | '.join(cells(n3, 'pre_discussion') + ['–'] * 2) + ' |')
    out.append('| needs v3 (#44) + v11 | ' + ' | '.join(cells(n3) + ['–'] * 2) + ' |')
    return '\n'.join(out)


def run_table(case):
    rows = runs_of(case)
    out = ['| Run | Discussion | Needs (covered / working) | Supported | Supported or partial | Settled requirements among supported | Supported, without DCAT-AP restatements | Supported or partial: only broader / narrower / partial / none |',
           '|---|---|---:|---:|---:|---:|---:|---:|']
    seen = set()
    for r in rows:
        if r['lineage'] not in seen:
            seen.add(r['lineage'])
            f = r['pre_discussion.raw_supported_or_partial']
            out.append(f"| **before the discussion** ({', '.join(x['label'] for x in rows if x['lineage'] == r['lineage'])}) | — | {r['pre_discussion_needs']} | "
                       f"{frac(r['pre_discussion.raw_supported'])} | {frac(f)} | {frac(r['pre_discussion.raw_supported_settled'])} | "
                       f"{frac(r['pre_discussion.raw_supported_without_restatements'])} | {f['only_broader']} / {f['only_narrower']} / {f['only_partial']} / {f['none']} |")
        f = r['active.raw_supported_or_partial']
        out.append(f"| {r['label']} `{r['run_id'][4:12]}` | {r['plan'] or '—'} | {r['active_needs']} ({r['covered_by_base']} / {r['working']}) | "
                   f"{frac(r['active.raw_supported'])} | {frac(f)} | {frac(r['active.raw_supported_settled'])} | "
                   f"{frac(r['active.raw_supported_without_restatements'])} | {f['only_broader']} / {f['only_narrower']} / {f['only_partial']} / {f['none']} |")
    return '\n'.join(out)


def atom_table(case):
    runs = runs_of(case)
    cols, seen = [], set()
    for r in runs:
        if r['lineage'] not in seen:
            seen.add(r['lineage'])
            tag = ' (needs v3)' if 'needs-v3' in r['label'] else ''
            cols.append(('set aside upstream' + tag, [x['label'] for x in runs if x['lineage'] == r['lineage']], 'best_label_set_aside_upstream'))
            cols.append(('before' + tag, r['label'], 'best_label_pre_discussion'))
        cols.append((r['label'], r['label'], 'best_label_active'))
    cell = {(x['atom_id'], x['run']): x for x in ATOM if x['case'] == case}
    atoms = []
    for x in ATOM:
        if x['case'] == case and x['atom_id'] not in atoms:
            atoms.append(x['atom_id'])
    out = ['| Atom | Raw evidence | Status | Restates DCAT-AP | ' + ' | '.join(h for h, _, _ in cols) + ' |',
           '|---|---|---|---|' + '---|' * len(cols)]
    for a in atoms:
        first = cell[(a, cols[1][1])]
        vals = [max((cell[(a, x)][field] for x in run), key=lambda v: RANK[v]) if isinstance(run, list) else cell[(a, run)][field]
                for _, run, field in cols]
        out.append(f"| {a} | {first['raw_evidence']} | {first['status_in_source']} | {'yes' if first['restates_dcat_ap'] == 'True' else ''} | "
                   + ' | '.join(SHORT[v] for v in vals) + ' |')
    return '\n'.join(out)


FINDINGS = """## Findings

- **Two eligible atoms are ever recovered**, both supported: JRC-1.1 (authors, by "Users can know the creator of a dataset.") and S-6.1 (unit of measurement, by "Users can know the units (years) of the measured values for each observation.").
- **JRC differs between versions by one need.** The v6 and v8 discussions set the creator need aside (0 of 6); v9, v10, v11 and the needs-v3 run keep it (1 of 6). Stat is 1 of 4 in v6, v8 and v10.
- **The missed supported atoms have only weaker needs.** JRC: lineage (JRC-2.1), primary versus alternative identifiers (JRC-6.3) and the DOI rule (JRC-6.4) get partial needs, identifier types (JRC-6.5) a narrower one, and an API pointer (JRC-8.1) none outside the needs-v3 run. Stat: start and end of a time series (S-7.1, S-7.2) get only "temporal coverage" (broader), the structure definition link (S-17.1) a partial need.
- **Every eligible Stat atom has a related need; three JRC atoms have none** in v9 to v11 (persistent identifiers JRC-6.1, API pointer JRC-8.1, API description JRC-8.2); the needs-v3 run adds partial needs for JRC-8.1 and JRC-8.2.
- **Settled requirements only:** JRC 0 of 5 (v6, v8) or 1 of 5 (v9 onward); Stat 1 of 1 (S-6.1 is its only supported atom with requirement status; the others are guidance).
- **Label caveat:** JRC-8.1 and S-17.1 may overstate "supported" in the way the adjudication's P1 describes (the inputs show the distinction or the link at another level, not the requirement). They were not relabelled, because they were checked after the results were seen. Without them, the supported figures would be JRC 1 of 5 and Stat 1 of 3.
"""


def main():
    c = R['cases']
    parts = ['# Mock benchmark on evidence-eligible atoms: discussion v6–v11 against reference sets v3', '',
             f"Machine-made: two blind AI reviewers and an AI adjudicator, no people. JRC and Stat are development cases; nothing here is a test result. "
             f"Reference: v3 with the 23 October adjudication ({REF_COMMIT}). Only atoms that the staged raw inputs support are scored: "
             f"`supported` (primary) or `supported` or `partial` (secondary). Method: `METHOD.md`.", '',
             '## Key results', '', 'Recovered atoms (equivalent, one-to-one) out of the eligible atoms.', '', key_table(), '', FINDINGS]
    for case, name in (('jrc', 'JRC'), ('stat', 'StatDCAT')):
        x = c[case]
        parts += [f'## {name}', '', run_table(case), '',
                  'Atoms: E equivalent (credited), e* equivalent but its need is credited to another atom, b broader, n narrower, p partial, · none.', '',
                  atom_table(case), '',
                  f"Reviewers on these atoms: {x['pairs_flagged_either']} pairs flagged by either; agreement {x['agreement_on_flagged_pairs']}, kappa {x['kappa_on_flagged_pairs']} on those; "
                  f"equivalence kappa over all {x['pairs_in_grid']} pairs {x['kappa_equivalent_full_grid']}; {x['disagreements']} disagreements adjudicated, {x['unresolved_after_adjudication']} unresolved.", '']
    if DIFF:
        parts += ['## What the discussion changed (eligible atoms)', '', '| Case | Run | Atom | Before | After | Why |', '|---|---|---|---|---|---|']
        parts += [f"| {d['case']} | {d['run']} | {d['atom_id']} | {d['pre_discussion']} | {d['after_discussion']} | {d['why']} |" for d in DIFF]
    open(f'{HERE}/out/SUMMARY.md', 'w', encoding='utf-8').write('\n'.join(parts) + '\n')
    print('\n'.join(parts)[:3500])


if __name__ == '__main__':
    main()
