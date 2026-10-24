"""Independent recomputation of the headline figures from out/pair-labels.csv and runs.json.

Does not import score.py. Uses brute-force matching (every assignment of atoms to distinct needs),
which is feasible because equivalent edges are few, and compares with out/mock-benchmark-results.json.
"""
import csv
import itertools
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.environ.get('RQ1_REF', os.path.join(HERE, '..'))  # reference-sets-v3 (results here: commit 671c60a)
data = json.load(open(os.path.join(HERE, 'runs.json'), encoding='utf-8'))
res = json.load(open(os.path.join(HERE, 'out/mock-benchmark-results.json'), encoding='utf-8'))
pairs = list(csv.DictReader(open(os.path.join(HERE, 'out/pair-labels.csv'), encoding='utf-8')))
problems = []
for case, folder in (('jrc', 'jrc-research'), ('stat', 'statdcat')):
    atoms = [a for a in json.load(open(f'{REF}/{folder}.json', encoding='utf-8'))['atoms'] if a['scored_by_default']]
    sup = [a for a in atoms if a['input_evidence']['raw']['label'] == 'supported']
    den = {'raw_supported': [a['id'] for a in sup],
           'raw_supported_or_partial': [a['id'] for a in atoms if a['input_evidence']['raw']['label'] in ('supported', 'partial')],
           'raw_supported_settled': [a['id'] for a in sup if a['status_in_source'] == 'requirement'],
           'raw_supported_without_restatements': [a['id'] for a in sup if a['relation_to_base'] != 'restates_base']}
    eq = {(p['atom_id'], int(p['statement_index'])) for p in pairs if p['case'] == case and p['final_label'] == 'equivalent'}
    for run in data['runs']:
        if run['case'] != case:
            continue
        active = [int(x.split(':')[0]) for x in run['active'].split()]
        row = next(r for r in res['runs'] if r['case'] == case and r['label'] == run['label'])
        for dname, ids in den.items():
            cand = {a: [i for i, s in enumerate(active) if (a, s) in eq] for a in ids}
            cand = {a: v for a, v in cand.items() if v}
            best = 0
            keys = list(cand)
            for k in range(len(keys), 0, -1):
                for sub in itertools.combinations(keys, k):
                    if any(len(set(c)) == k for c in itertools.product(*(cand[a] for a in sub))):
                        best = k
                        break
                if best:
                    break
            if best != row[f'active.{dname}']['recovered'] or len(ids) != row[f'active.{dname}']['n']:
                problems.append((case, run['label'], dname, best, row[f'active.{dname}']))
        n_active = len(active)
        if n_active != row['active_needs']:
            problems.append((case, run['label'], 'active_needs', n_active, row['active_needs']))
print('problems:', problems or 'none')
