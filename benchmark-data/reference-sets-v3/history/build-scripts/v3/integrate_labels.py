"""Verify and merge the input-evidence labels returned by the labelling agents."""
import json, os, re, sys, collections
sys.path.insert(0, '/home/claude/merge')
from srcfind import norm

LBL = '/tmp/claude-0/-home-claude/52db0194-1e75-558e-bfb2-4f590f0a248c/scratchpad/label'
INP = '/home/claude/merge/inputs'
RANK = {'supported': 3, 'partial': 2, 'uncertain': 1, 'unsupported': 0}
_text = {}


def text_of(path):
    if path not in _text:
        f = f'{INP}/{path}.txt'
        t = norm(open(f, encoding='utf-8').read()) if os.path.exists(f) else None
        _text[path] = (t, t.replace('- ', '-') if t else None)
    return _text[path]


def quote_ok(path, quote):
    t, t2 = text_of(path)
    if not t or not quote:
        return False
    parts = [p.strip(' .') for p in re.split(r'\.\.\.|…|\[\.\.\.\]', quote) if len(p.strip(' .')) >= 12] or [quote]
    for p in parts:
        q = norm(p)
        if not (q in t or q in t2 or q.replace('- ', '-') in t2):
            return False
    return True


def load(name):
    f = f'{LBL}/{name}.json'
    if os.path.exists(f):
        return json.load(open(f, encoding='utf-8'))
    raise SystemExit(f'missing label file {f}')


def checked(block):
    if not block:
        return None
    srcs = []
    for s in block.get('sources') or []:
        s = dict(s)
        s['quote_check'] = 'verbatim_in_input_text' if quote_ok(s.get('path', ''), s.get('quote', '')) else 'NOT_FOUND'
        srcs.append(s)
    label = block.get('label', 'unsupported')
    assert label in RANK, label
    return dict(label=label, sources=srcs, rationale=block.get('rationale', ''),
                quotes_verified=any(s['quote_check'] == 'verbatim_in_input_text' for s in srcs) if srcs else (label == 'unsupported'))


def main():
    merged = {}
    problems = collections.Counter()
    for name in ('health-a', 'health-b', 'geo', 'stat-jrc', 'mobility-consolidation'):
        for e in load(name):
            m = merged.setdefault(e['atom_id'], {})
            for k in ('raw', 'consolidation'):
                if e.get(k):
                    if k in m:
                        problems['duplicate ' + k] += 1
                    m[k] = checked(e[k])
    groups = {}
    for name, tag in (('mobility-policy', 'policy and legal texts'), ('mobility-standards', 'standards and specifications'),
                      ('mobility-literature', 'literature and projects')):
        for e in load(name):
            groups.setdefault(e['atom_id'], []).append((tag, checked(e['raw'])))
    for aid, gs in groups.items():
        best = max(gs, key=lambda g: RANK[g[1]['label']])[1]['label']
        srcs, rats = [], []
        for tag, b in gs:
            if RANK[b['label']] >= 1:
                srcs += b['sources']
            rats.append(f"{tag}: {b['label']}" + (f" ({b['rationale']})" if b['rationale'] and RANK[b['label']] >= 1 else ''))
        merged.setdefault(aid, {})['raw'] = dict(label=best, sources=srcs, rationale='; '.join(rats),
                                                 quotes_verified=any(s['quote_check'] == 'verbatim_in_input_text' for s in srcs) if srcs else best == 'unsupported',
                                                 by_input_group={tag: b['label'] for tag, b in gs})
    nf = sum(1 for m in merged.values() for k in ('raw', 'consolidation') if m.get(k) for s in m[k]['sources'] if s['quote_check'] == 'NOT_FOUND')
    tot = sum(1 for m in merged.values() for k in ('raw', 'consolidation') if m.get(k) for s in m[k]['sources'])
    json.dump(merged, open('/home/claude/merge/label/labels-merged.json', 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print('atoms labelled', len(merged), '| quotes', tot, 'not found', nf, '| problems', dict(problems))
    for k in ('raw', 'consolidation'):
        print(k, collections.Counter(m[k]['label'] for m in merged.values() if m.get(k)))
    bad = [(aid, k, s['path'], s['quote'][:80]) for aid, m in merged.items() for k in ('raw', 'consolidation') if m.get(k)
           for s in m[k]['sources'] if s['quote_check'] == 'NOT_FOUND']
    for b in bad[:40]:
        print('  NOT FOUND', b)


if __name__ == '__main__':
    main()
