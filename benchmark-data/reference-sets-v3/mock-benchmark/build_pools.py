"""Build blind judging packets: per case, every statement seen in any scored run, under random IDs.

The packets in judge/ are the ones the reviewers saw (built on 22 October from v3 at 8e81e5b).
Rebuilding overwrites them, so it needs --force.
"""
import json
import os, random, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(HERE, 'judge', 'jrc-atoms.json')) and '--force' not in sys.argv:
    raise SystemExit('judge/ already holds the packets the reviewers saw; pass --force to rebuild them.')
os.chdir(HERE)

D = json.load(open('runs.json', encoding='utf-8'))
ST = D['statements']
REF = os.environ.get('RQ1_REF', os.path.join(HERE, '..'))  # reference-sets-v3
CASES = {'jrc': 'jrc-research', 'stat': 'statdcat'}


def sids_of(run):
    out = set()
    for k in ('active', 'inactive', 'obs'):
        out |= {int(x.split(':')[0]) for x in run[k].split()}
    out |= {int(x) for x in run['compact'].split()}
    for a in filter(None, run['applied'].split(' | ')):
        _, rest = a.split(':', 1)
        p, r = rest.split('>')
        out |= {int(x) for x in re.split(r'\+', p) if x} | {int(x) for x in re.split(r'\+', r) if x}
    return out


mapping = {}
for case, folder in CASES.items():
    pool = sorted(set().union(*[sids_of(r) for r in D['runs'] if r['case'] == case]))
    rng = random.Random(f'rq1-mock-{case}-ids')
    ids = rng.sample(range(100, 1000), len(pool))
    need_ids = {sid: f'N{n}' for sid, n in zip(pool, ids)}
    mapping[case] = {need_ids[s]: s for s in pool}
    needs = [{'need_id': need_ids[s], 'statement': ST[s]} for s in pool]
    for judge in ('A', 'B'):
        order = needs[:]
        random.Random(f'rq1-mock-{case}-order-{judge}').shuffle(order)
        json.dump(order, open(f'judge/{case}-needs-{judge}.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    ref = json.load(open(f'{REF}/{folder}.json', encoding='utf-8'))
    atoms = [{'atom_id': a['id'], 'statement': a['statement'], 'source_passage': a.get('anchor_quote'),
              'source_wording_of_obligation': a.get('modality'), 'status_in_source': a['status_in_source']}
             for a in ref['atoms'] if a['scored_by_default']]
    json.dump(atoms, open(f'judge/{case}-atoms.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(case, 'pool', len(pool), 'atoms', len(atoms))
json.dump(mapping, open('private/need-id-map.json', 'w'), indent=1)
