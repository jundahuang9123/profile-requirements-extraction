"""Collect the pairs on which reviewers A and B disagree into one packet per case for the adjudicator."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def main(cases=('jrc', 'stat')):
    for case in cases:
        atoms = {a['atom_id']: a for a in json.load(open(f'{HERE}/judge/{case}-atoms.json', encoding='utf-8'))}
        needs = {n['need_id']: n['statement'] for n in json.load(open(f'{HERE}/judge/{case}-needs-A.json', encoding='utf-8'))}
        lab = {}
        for j in ('A', 'B'):
            out = json.load(open(f'{HERE}/judge/out/{case}-{j}.json', encoding='utf-8'))
            assert out['case'] == case and out['judge'] == j
            assert sorted(a['atom_id'] for a in out['atoms']) == sorted(atoms), f'{case}-{j}: atoms differ'
            for a in out['atoms']:
                for m in a['matches']:
                    assert m['need_id'] in needs, (case, j, m['need_id'])
                    lab.setdefault((a['atom_id'], m['need_id']), {})[j] = m
        items = []
        for (aid, nid), d in sorted(lab.items()):
            la = d.get('A', {}).get('label', 'unrelated')
            lb = d.get('B', {}).get('label', 'unrelated')
            if la == lb:
                continue
            items.append({'atom_id': aid, 'atom_statement': atoms[aid]['statement'], 'source_passage': atoms[aid]['source_passage'],
                          'need_id': nid, 'need_statement': needs[nid],
                          'reviewer_1': {'label': la, 'rationale': d.get('A', {}).get('rationale', 'not listed, so unrelated')},
                          'reviewer_2': {'label': lb, 'rationale': d.get('B', {}).get('rationale', 'not listed, so unrelated')}})
        json.dump(items, open(f'{HERE}/judge/{case}-disagreements.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(case, 'pairs', len(lab), 'disagreements', len(items))


if __name__ == '__main__':
    import sys
    main(tuple(sys.argv[1:]) or ('jrc', 'stat'))
