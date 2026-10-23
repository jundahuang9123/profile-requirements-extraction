import json, re, os, csv, sys, collections
sys.path.insert(0, '/home/claude/analysis')
from completion import CASES
from codes import CODES

REPO = '/home/claude/jundahuang9123/profile-requirements-extraction/benchmark-data'
OUT = '/home/claude/analysis/out/v2'
LEVEL = {'M': 'content', 'G': 'profile', 'S': 'system'}
REL_FROM_RESP = {'A': 'beyond_base', 'B': 'beyond_base', 'C': 'beyond_base', 'D': 'extends_base', 'E': 'tightens_base',
                 'F': 'restates_base', 'G': 'not_term_level'}
SPECIAL = {'H-3': ('beyond_base', 'proposed'), 'H-12': ('unresolved', 'open_issue'), 'S-7': ('restates_base', 'guidance')}

def norm(s):
    s = (s.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
         .replace(' ', ' ').replace('‑', '-').replace('­', ''))
    return re.sub(r'\s+', ' ', s).strip()

problems = []
summary = []
review = []
for case, cfg in CASES.items():
    v1 = json.load(open(f'{REPO}/{case}/reference-requirements/{cfg["v1"]}', encoding='utf-8'))
    texts = [norm(open('/home/claude/analysis/' + f, encoding='utf-8').read()) for f in cfg['src']]
    texts += [t.replace('- ', '-') for t in texts]  # tolerate hyphenated line breaks
    rows = []
    for r in v1['requirements']:
        c = CODES[r['id']]
        rel, st = SPECIAL.get(r['id'], (REL_FROM_RESP.get(c['resp'], 'not_term_level'), 'requirement'))
        row = dict(r)
        row.update(level=LEVEL[c['level']], relation_to_base=rel, status_in_source=st, added_in='v1')
        rows.append(row)
    ids = {r['id'] for r in rows}
    for n in cfg['new']:
        assert n['id'] not in ids, n['id']
        ids.add(n['id'])
        if texts:
            ok = any(norm(n['anchor']) in t for t in texts)
            check = 'verbatim_in_source_text' if ok else 'NOT_FOUND'
            if not ok:
                problems.append((n['id'], n['anchor']))
        else:
            check = 'from_web_fetch_not_verified_locally'
        row = {'id': n['id'], 'statement': n['statement'], 'statement_kind': 'curator_paraphrase',
               'source_locator': n['locator'], 'anchor_quote': n['anchor'], 'anchor_check': check,
               'level': n['level'], 'relation_to_base': n['relation'], 'status_in_source': n['status'],
               'atoms': n['atoms'], 'overlaps': n['overlaps'], 'reuse_or_alignment_rule': n['rq2'],
               'origin': n['origin'], 'problem': n['problem'], 'note': n['note'],
               'added_in': 'v2', 'curated_by': 'Claude (Anthropic), 2026-10-22; not independently adjudicated',
               'adjudication_status': 'not_independently_adjudicated'}
        row.update(n['extra'])
        rows.append(row)
        review.append(dict(case=case, **{k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
                                          for k, v in row.items() if k not in ('statement_kind', 'curated_by', 'adjudication_status')},
                           your_decision='', your_note=''))
    out = {
        'schema_version': 'rq1-reference-set-2',
        'case': case,
        'reference_document': cfg['doc'],
        'base': cfg['base'],
        'supersedes': f'{cfg["v1"]} (v1 rows kept unchanged, marked added_in=v1)',
        'completion_rule': ('v2 adds every requirement the reference document states for the profile, its metadata or the systems around it '
                            'that v1 did not contain: a requirement sentence, a rationale, a changed obligation or a reported request. '
                            'Text copied from DCAT-AP and table entries that only repeat a base obligation without a rationale are not added. '
                            'Rows that are only proposed, deferred or open issues are kept and marked in status_in_source.'),
        'scoring_note': 'Score level=content rows for need recovery; profile and system rows are reported separately.',
        'count': len(rows),
        'count_by_level': dict(collections.Counter(r['level'] for r in rows)),
        'count_added_in_v2': sum(1 for r in rows if r['added_in'] == 'v2'),
        'requirements': rows,
    }
    os.makedirs(f'{OUT}/{case}/reference-requirements', exist_ok=True)
    name = cfg['v1'].replace('.json', '-v2.json')
    json.dump(out, open(f'{OUT}/{case}/reference-requirements/{name}', 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    summary.append((case, len(v1['requirements']), out['count_added_in_v2'], len(rows), out['count_by_level'],
                    dict(collections.Counter(r['level'] for r in rows if r['added_in'] == 'v2'))))

print('anchor problems:', len(problems))
for p in problems: print('  ', p)
for s in summary: print(s)
with open('/home/claude/analysis/out/v2/reference-completion-review.csv', 'w', newline='', encoding='utf-8') as f:
    cols = ['case', 'id', 'statement', 'source_locator', 'anchor_quote', 'anchor_check', 'level', 'problem', 'origin', 'relation_to_base',
            'status_in_source', 'atoms', 'overlaps', 'reuse_or_alignment_rule', 'note', 'inspire_obligation', 'iso19115_core_obligation',
            'dcat_ap_coverage', 'added_in', 'your_decision', 'your_note']
    w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
    w.writeheader()
    for r in review: w.writerow(r)
print('review rows', len(review))
