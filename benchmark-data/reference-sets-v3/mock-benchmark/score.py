"""Mock benchmark scoring of saved RQ1 runs against the frozen v3 reference atoms.

Inputs (all local, read-only):
  runs.json                       run outputs fetched from 8013 (hash-verified)
  private/need-id-map.json        blind need IDs -> statement index
  judge/out/<case>-{A,B}.json     two independent reviewers' pair labels
  judge/out/<case>-adjudicated.json  adjudicator's labels for the pairs A and B disagree on
  reference-sets-v3/<case>.json   frozen atoms (commit 8e81e5b)

Scoring follows benchmark-data/BENCHMARK-METHODOLOGY.md: atoms are the unit, only
`equivalent` earns recovery credit, matching is one-to-one (maximum bipartite matching, computed
separately for each denominator), and narrower/broader/partial coverage is reported separately.

Evidence-eligible only: the scored atoms are restricted to those whose raw input-evidence label is
`supported` (primary) or `supported`/`partial` (secondary); atoms the staged inputs do not support are
left out of every figure.
"""
import collections
import csv
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.environ.get('RQ1_REF', os.path.join(HERE, '..'))  # reference-sets-v3 (results here: commit 671c60a)
CASES = {'jrc': 'jrc-research', 'stat': 'statdcat'}
LABELS = ('equivalent', 'narrower', 'broader', 'partial', 'conflicts')
RANK = {'equivalent': 5, 'broader': 4, 'narrower': 3, 'partial': 2, 'conflicts': 1, None: 0}


def load(p):
    return json.load(open(os.path.join(HERE, p), encoding='utf-8'))


def parse_run(r):
    active = [(int(s), f) for s, f in (x.split(':') for x in r['active'].split())]
    inactive = [(int(s), c) for s, c in (x.split(':') for x in r['inactive'].split())]
    compact = [int(x) for x in r['compact'].split()]
    applied = []
    for a in filter(None, r['applied'].split(' | ')):
        act, rest = a.split(':', 1)
        p, q = rest.split('>')
        applied.append((act, [int(x) for x in p.split('+') if x], [int(x) for x in q.split('+') if x]))
    return dict(active=active, inactive=inactive, compact=compact, applied=applied)


def judge_labels(case, judge):
    """{(atom_id, sid): label} for one reviewer; unlisted pairs are unrelated."""
    idmap = load('private/need-id-map.json')[case]
    out = {}
    for a in load(f'judge/out/{case}-{judge}.json')['atoms']:
        for m in a['matches']:
            assert m['label'] in LABELS, m
            key = (a['atom_id'], idmap[m['need_id']])
            if RANK[m['label']] > RANK[out.get(key)]:
                out[key] = m['label']
    return out


def rationales(case):
    idmap = load('private/need-id-map.json')[case]
    out = collections.defaultdict(dict)
    for j in ('A', 'B'):
        for a in load(f'judge/out/{case}-{j}.json')['atoms']:
            for m in a['matches']:
                out[(a['atom_id'], idmap[m['need_id']])][j] = m.get('rationale', '')
    p = os.path.join(HERE, f'judge/out/{case}-adjudicated.json')
    if os.path.exists(p):
        for d in load(f'judge/out/{case}-adjudicated.json')['decisions']:
            out[(d['atom_id'], idmap[d['need_id']])]['adj'] = d['label'] + ': ' + d.get('rationale', '')
    return out


def final_labels(case):
    A, B = judge_labels(case, 'A'), judge_labels(case, 'B')
    adj_path = os.path.join(HERE, f'judge/out/{case}-adjudicated.json')
    adj = {}
    if os.path.exists(adj_path):
        idmap = load('private/need-id-map.json')[case]
        for d in load(f'judge/out/{case}-adjudicated.json')['decisions']:
            adj[(d['atom_id'], idmap[d['need_id']])] = None if d['label'] == 'unrelated' else d['label']
    final, unresolved = {}, []
    for key in set(A) | set(B):
        a, b = A.get(key), B.get(key)
        if a == b:
            final[key] = a
        elif key in adj:
            if adj[key]:
                final[key] = adj[key]
        else:
            unresolved.append(key)
    return A, B, final, unresolved


def max_matching(atoms, preds, edges):
    """Kuhn's algorithm. edges: atom -> list of prediction indices. Returns {atom: pred}."""
    match_pred = {}

    def try_atom(a, seen):
        for p in edges.get(a, ()):
            if p in seen:
                continue
            seen.add(p)
            if p not in match_pred or try_atom(match_pred[p], seen):
                match_pred[p] = a
                return True
        return False

    for a in atoms:
        try_atom(a, set())
    return {a: p for p, a in match_pred.items()}


def score_set(sids, atoms, labels):
    """sids: list of statement indices (one per prediction, duplicates allowed)."""
    edges = collections.defaultdict(list)
    for i, s in enumerate(sids):
        for a in atoms:
            if labels.get((a, s)) == 'equivalent':
                edges[a].append(i)
    m = max_matching(atoms, sids, edges)
    best = {}
    for a in atoms:
        if a in m:
            best[a] = 'equivalent'
        else:
            lab = max((labels.get((a, s)) for s in set(sids)), key=lambda x: RANK[x], default=None)
            # an equivalent need already credited to another atom (one-to-one) gives no credit here
            best[a] = 'equivalent_used_elsewhere' if lab == 'equivalent' else lab
    return {a: sids[p] for a, p in m.items()}, best


def kappa(pairs, A, B, cats):
    n = len(pairs)
    if not n:
        return None
    agree = sum((A.get(k) or 'unrelated') == (B.get(k) or 'unrelated') for k in pairs) / n
    ca = collections.Counter(A.get(k) or 'unrelated' for k in pairs)
    cb = collections.Counter(B.get(k) or 'unrelated' for k in pairs)
    pe = sum(ca[c] * cb[c] for c in cats) / (n * n)
    return round((agree - pe) / (1 - pe), 3) if pe < 1 else 1.0


def main(write=True):
    data = load('runs.json')
    ST = data['statements']
    runs = [dict(r, **parse_run(r)) for r in data['runs']]
    report = {'cases': {}, 'runs': []}
    pair_rows, atom_rows, diff_rows = [], [], []
    for case, folder in CASES.items():
        ref = json.load(open(f'{REF}/{folder}.json', encoding='utf-8'))
        atoms = [a for a in ref['atoms'] if a['scored_by_default']
                 and ((a.get('input_evidence') or {}).get('raw') or {}).get('label') in ('supported', 'partial')]
        ids = [a['id'] for a in atoms]
        info = {a['id']: a for a in atoms}
        raw = {a['id']: ((a.get('input_evidence') or {}).get('raw') or {}).get('label') for a in atoms}
        denoms = {
            'raw_supported': [a for a in ids if raw[a] == 'supported'],
            'raw_supported_or_partial': ids,
            'raw_supported_settled': [a for a in ids if raw[a] == 'supported' and info[a]['status_in_source'] == 'requirement'],
            'raw_supported_without_restatements': [a for a in ids if raw[a] == 'supported' and not info[a]['restates_dcat_ap']],
        }
        A, B, final, unresolved = final_labels(case)
        keep = set(ids)
        A = {k: v for k, v in A.items() if k[0] in keep}
        B = {k: v for k, v in B.items() if k[0] in keep}
        final = {k: v for k, v in final.items() if k[0] in keep}
        unresolved = [k for k in unresolved if k[0] in keep]
        pool = sorted(set(load('private/need-id-map.json')[case].values()))
        # agreement
        flagged = set(A) | set(B)
        eqA = {k for k, v in A.items() if v == 'equivalent'}
        eqB = {k for k, v in B.items() if v == 'equivalent'}
        grid = len(ids) * len(pool)
        both_eq, only_eq = len(eqA & eqB), len(eqA ^ eqB)
        po = (grid - only_eq) / grid
        pa, pb = len(eqA) / grid, len(eqB) / grid
        pe = pa * pb + (1 - pa) * (1 - pb)
        report['cases'][case] = {
            'atoms_scored': len(ids), 'denominators': {k: len(v) for k, v in denoms.items()},
            'statement_pool': len(pool), 'pairs_in_grid': grid,
            'pairs_flagged_A': len(A), 'pairs_flagged_B': len(B), 'pairs_flagged_either': len(flagged),
            'labels_A': dict(collections.Counter(A.values())), 'labels_B': dict(collections.Counter(B.values())),
            'agreement_on_flagged_pairs': round(sum((A.get(k) or 'unrelated') == (B.get(k) or 'unrelated') for k in flagged) / max(1, len(flagged)), 3),
            'kappa_on_flagged_pairs': kappa(flagged, A, B, LABELS + ('unrelated',)),
            'equivalent_both': both_eq, 'equivalent_one_only': only_eq,
            'kappa_equivalent_full_grid': round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0,
            'disagreements': sum((A.get(k) or 'unrelated') != (B.get(k) or 'unrelated') for k in flagged),
            'unresolved_after_adjudication': len(unresolved),
            'final_labels': dict(collections.Counter(final.values())),
        }
        why = rationales(case)
        for (a, s) in sorted(set(A) | set(B), key=lambda x: (ids.index(x[0]), x[1])):
            lab = final.get((a, s)) if (a, s) in final else ('UNRESOLVED' if (a, s) in unresolved else None)
            pair_rows.append({'case': case, 'atom_id': a, 'atom_statement': info[a]['statement'], 'statement_index': s,
                              'need_statement': ST[s], 'label_A': A.get((a, s)) or 'unrelated', 'label_B': B.get((a, s)) or 'unrelated',
                              'final_label': lab or 'unrelated', 'rationale_A': why[(a, s)].get('A', ''),
                              'rationale_B': why[(a, s)].get('B', ''), 'adjudication': why[(a, s)].get('adj', ''),
                              'your_decision': '', 'your_note': ''})
        strict = {k: ('equivalent' if A.get(k) == B.get(k) == 'equivalent' else (final.get(k) if final.get(k) != 'equivalent' else 'partial')) for k in final}
        lenient = dict(final)
        for k in flagged:
            if 'equivalent' in (A.get(k), B.get(k)):
                lenient[k] = 'equivalent'
        case_runs = [r for r in runs if r['case'] == case]
        # pre-discussion set per lineage: the shared 6a input (= compact selection for these runs)
        lineages = {}
        for r in case_runs:
            pre = [s for s, f in r['active'] if 'd' not in f]
            pre += [s for s, c in r['inactive'] if c == 'A']
            parents = {p for act, ps, _ in r['applied'] if act != 'set_aside' for p in ps}
            pre += [s for s, c in r['inactive'] if c == 'S' and s in parents and s in r['compact']]
            r['pre'] = pre
            lineages.setdefault(tuple(sorted(r['compact'])), []).append(r['label'])
        # independent checks of the reconstruction: runs with no applied change show the 6a input as is
        report['cases'][case]['pre_discussion_checks'] = {
            r['label']: {'no_applied_changes': True, 'active_equals_compact': sorted(s for s, _ in r['active']) == sorted(r['compact'])}
            for r in case_runs if not r['applied']}
        report['cases'][case]['lineages'] = [{'runs': v, 'compact_needs': len(k)} for k, v in lineages.items()]
        for r in case_runs:
            row = {'case': case, 'label': r['label'], 'run_id': r['run_id'], 'name': r['name'], 'plan': r['plan'],
                   'lineage': hashlib.sha1(' '.join(map(str, sorted(r['pre']))).encode()).hexdigest()[:8],
                   'status': r['status'], 'implementation_hash': r['implementation_hash'], 'parent': r['parent'],
                   'active_needs': len(r['active']), 'covered_by_base': sum('c' in f for _, f in r['active']),
                   'working': sum('w' in f for _, f in r['active']),
                   'discussion_created': sum('d' in f for _, f in r['active']),
                   'applied_changes': collections.Counter(a for a, _, _ in r['applied']),
                   'pre_discussion_needs': len(r['pre']), 'compact_needs': len(r['compact']),
                   'pre_discussion_equals_compact': sorted(r['pre']) == sorted(r['compact'])}
            sets = {'active': [s for s, _ in r['active']], 'pre_discussion': r['pre'], 'compact': r['compact']}
            for view, sids in sets.items():
                for dname, dids in denoms.items():
                    m, best = score_set(sids, dids, final)
                    ms, _ = score_set(sids, dids, strict)
                    ml, _ = score_set(sids, dids, lenient)
                    cov = collections.Counter(best[a] for a in dids if best[a] != 'equivalent')
                    row[f'{view}.{dname}'] = {
                        'n': len(dids), 'recovered': len(m), 'recall': round(len(m) / len(dids), 3) if dids else None,
                        'strict_bound': len(ms), 'lenient_bound': len(ml),
                        'equivalent_used_elsewhere': cov.get('equivalent_used_elsewhere', 0),
                        'only_broader': cov.get('broader', 0), 'only_narrower': cov.get('narrower', 0),
                        'only_partial': cov.get('partial', 0), 'only_conflicts': cov.get('conflicts', 0),
                        'none': cov.get(None, 0)}
                    assert sum(row[f'{view}.{dname}'][k] for k in ('recovered', 'equivalent_used_elsewhere', 'only_broader', 'only_narrower', 'only_partial', 'only_conflicts', 'none')) == len(dids)
                    if view == 'active' and dname == 'raw_supported_or_partial':
                        r['_match'], r['_best'] = m, best
                    if view == 'pre_discussion' and dname == 'raw_supported_or_partial':
                        r['_pre_match'], r['_pre_best'] = m, best
            # sensitivity (not recall): one-to-one credit when the need contains the atom, or for any relation
            for tag, ok in (('contains', {'equivalent', 'broader'}), ('any_relation', set(LABELS))):
                relaxed = {k: ('equivalent' if v in ok else None) for k, v in final.items()}
                for view in ('active', 'pre_discussion'):
                    sids = [s for s, _ in r['active']] if view == 'active' else r['pre']
                    m, _ = score_set(sids, ids, relaxed)
                    row[f'{view}.eligible.one_to_one_{tag}'] = len(m)
            # predictions related to any scored atom
            rel = {s for s, _ in r['active'] if any(final.get((a, s)) for a in ids)}
            eqs = {s for s, _ in r['active'] if any(final.get((a, s)) == 'equivalent' for a in ids)}
            row['needs_equivalent_to_an_atom'] = sum(s in eqs for s, _ in r['active'])
            row['needs_related_to_an_atom'] = sum(s in rel for s, _ in r['active'])
            row['needs_unrelated'] = len(r['active']) - row['needs_related_to_an_atom']
            row['unrelated_covered_by_base'] = sum(s not in rel and 'c' in f for s, f in r['active'])
            row['unrelated_working'] = sum(s not in rel and 'w' in f for s, f in r['active'])
            # 6a label of the matched needs vs the atom's DCAT-AP restatement flag
            flags = {s: f for s, f in r['active']}
            row['matched_need_6a_label_by_atom_restates'] = dict(collections.Counter(
                ('restates' if info[a]['restates_dcat_ap'] else 'not_restates') + '/' +
                ('covered' if 'c' in flags[s] else 'working' if 'w' in flags[s] else 'unlabelled')
                for a, s in r['_match'].items()))
            report['runs'].append(row)
            for a in ids:
                atom_rows.append({'case': case, 'run': r['label'], 'atom_id': a, 'restates_dcat_ap': info[a]['restates_dcat_ap'],
                                  'raw_evidence': raw[a], 'status_in_source': info[a]['status_in_source'], 'best_label_active': r['_best'][a] or 'none',
                                  'matched_statement': ST[r['_match'][a]] if a in r['_match'] else '',
                                  'matched_need_6a': ('covered' if 'c' in flags[r['_match'][a]] else 'working') if a in r['_match'] else '',
                                  'best_label_pre_discussion': r['_pre_best'][a] or 'none',
                                  'best_label_set_aside_upstream': max((final.get((a, s)) for s, c in r['inactive'] if c == 'U'),
                                                                       key=lambda x: RANK[x], default=None) or 'none'})
            # discussion effect: atoms gained or lost against the run's own pre-discussion set
            codes = dict(r['inactive'])
            for a in ids:
                pre_eq, post_eq = a in r['_pre_match'], a in r['_match']
                if pre_eq != post_eq or (r['_pre_best'][a] != r['_best'][a]):
                    why = []
                    for s in {s for s in r['pre'] if final.get((a, s))} | {s for s, _ in r['active'] if final.get((a, s))}:
                        in_pre, in_post = s in r['pre'], s in {x for x, _ in r['active']}
                        if in_pre and not in_post:
                            why.append(f"{final[(a, s)]} need {'set aside' if codes.get(s) == 'A' else 'replaced'} by the discussion: {ST[s]}")
                        elif in_post and not in_pre:
                            why.append(f"{final[(a, s)]} need added by the discussion: {ST[s]}")
                    diff_rows.append({'case': case, 'run': r['label'], 'atom_id': a,
                                      'pre_discussion': r['_pre_best'][a] or 'none', 'after_discussion': r['_best'][a] or 'none',
                                      'why': '; '.join(sorted(why))})
    report['reference'] = {'set': 'benchmark-data/reference-sets-v3', 'commit': '671c60a', 'note': 'v3 with the 23 October adjudication applied'}
    if write:
        os.makedirs(os.path.join(HERE, 'out'), exist_ok=True)
        json.dump(report, open(os.path.join(HERE, 'out/mock-benchmark-results.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False, default=dict, sort_keys=True)
        for name, rows in (('pair-labels.csv', pair_rows), ('atom-by-run.csv', atom_rows), ('discussion-effect.csv', diff_rows)):
            if rows:
                with open(os.path.join(HERE, 'out', name), 'w', newline='', encoding='utf-8') as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0]))
                    w.writeheader()
                    w.writerows(rows)
    return report, pair_rows, atom_rows, diff_rows


if __name__ == '__main__':
    rep = main()[0]
    for case, c in rep['cases'].items():
        print(case, {k: c[k] for k in ('atoms_scored', 'denominators', 'pairs_flagged_either', 'kappa_on_flagged_pairs', 'kappa_equivalent_full_grid', 'disagreements', 'unresolved_after_adjudication', 'final_labels')})
    for r in rep['runs']:
        f, p = r['active.raw_supported'], r['active.raw_supported_or_partial']
        print(f"{r['case']:4} {r['label']:13} needs {r['active_needs']:3}  supported {f['recovered']}/{f['n']} [{f['strict_bound']}-{f['lenient_bound']}]  "
              f"sup|part {p['recovered']}/{p['n']}  settled {r['active.raw_supported_settled']['recovered']}/{r['active.raw_supported_settled']['n']}  "
              f"w/o restates {r['active.raw_supported_without_restatements']['recovered']}/{r['active.raw_supported_without_restatements']['n']}  "
              f"pre {r['pre_discussion.raw_supported']['recovered']}/{r['pre_discussion.raw_supported_or_partial']['recovered']}  "
              f"(sup|part) broader {p['only_broader']} narrower {p['only_narrower']} partial {p['only_partial']} none {p['none']}")
