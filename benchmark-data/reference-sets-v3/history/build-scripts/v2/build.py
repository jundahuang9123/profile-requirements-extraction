import json, html, collections, sys
sys.path.insert(0, '/home/claude/analysis')
rows = json.load(open('/home/claude/analysis/rows.json'))
E = html.escape

CASES = [('Mobility', 'mobilityDCAT-AP', 'DCAT-AP 2.0.1'), ('Health', 'HealthDCAT-AP', 'DCAT-AP 3.0.0'),
         ('Stat', 'StatDCAT-AP', 'DCAT-AP 1.1'), ('Geo', 'GeoDCAT-AP', 'DCAT-AP 1.1'), ('JRC', 'DCAT-AP-JRC', 'DCAT-AP 1.1')]
CASE_NAME = {k: n for k, n, _ in CASES}
GROUPS = [('new-minted', 'New class or property, minted'), ('new-imported', 'New class or property, imported'),
          ('changed', 'Existing term constrained or expanded'), ('base', 'Already in base'),
          ('open', 'Proposed or not addressed'), ('none', 'No term-level response')]
GLABEL = dict(GROUPS)
RESP = {'A': 'New class', 'B': 'New property', 'C': 'New code lists', 'D': 'Expand existing term', 'E': 'Constrain existing term',
        'F': 'Already in base', 'G': 'No term-level response', 'H': 'Proposed or not addressed'}
PROB = [('P1', 'Discover'), ('P2', 'Access'), ('P3', 'Understand & assess'), ('P4', 'Identify, link & attribute'),
        ('P5', 'Legal context'), ('P6', 'Manage records'), ('P7', 'Engineer the profile')]
DER = [('std', 'Prior standard or spec'), ('proj', 'Project report or literature'), ('exp', 'Expert or WG deliberation'),
       ('prac', 'Practitioner experience'), ('law', 'Law or policy'), ('tech', 'Technical considerations')]
LEVEL = {'M': 'Content', 'G': 'Profile', 'S': 'System or process'}
KIND = {'minted': 'new, minted', 'imported': 'new, imported', 'newclass': 'existing, on a new class', 'constrained': 'existing, constrained',
        'asis': 'existing, as is', 'cvext': 'code list extended', 'proposed': 'proposed only', 'gap': 'not covered'}

def grp(r):
    if r['resp'] in ('A', 'B'): return 'new-' + r['sub']
    if r['resp'] == 'C': return 'new-minted'
    return {'D': 'changed', 'E': 'changed', 'F': 'base', 'G': 'none', 'H': 'open'}[r['resp']]

for r in rows:
    r['group'] = grp(r)
    r['caseName'] = CASE_NAME[r['case']]
    r['respLabel'] = RESP[r['resp']] + ((', ' + r['sub']) if r['resp'] in ('A', 'B') else '')

# ---------- colour tokens (dataviz reference palette; validated adjacent order) ----------
LIGHT = {'new-minted': '#2a78d6', 'new-imported': '#eb6834', 'changed': '#1baf7a', 'base': '#eda100', 'open': '#e87ba4', 'none': '#c3c2b7'}
DARK = {'new-minted': '#3987e5', 'new-imported': '#d95926', 'changed': '#199e70', 'base': '#c98500', 'open': '#d55181', 'none': '#5f5e59'}

def lum(h):
    h = h.lstrip('#'); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
def contrast(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True); return (la + 0.05) / (lb + 0.05)
def ink_on(fill):
    return '#ffffff' if contrast(fill, '#ffffff') >= contrast(fill, '#0b0b0b') else '#0b0b0b'

HEAT_L = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95']
HEAT_D = ['#0d366b', '#104281', '#1c5cab', '#256abf', '#3987e5', '#6da7ec']
def heat_bin(share):
    for i, lim in enumerate([0.10, 0.20, 0.35, 0.50, 0.75, 1.01]):
        if share <= lim: return i
    return 5

def tokens(mode):
    pal = LIGHT if mode == 'light' else DARK
    heat = HEAT_L if mode == 'light' else HEAT_D
    out = []
    for k, v in pal.items():
        out.append(f'--c-{k}:{v};--t-{k}:{ink_on(v)};')
    for i, v in enumerate(heat):
        out.append(f'--h{i}:{v};--ht{i}:{ink_on(v)};')
    return ''.join(out)

# ---------- figure 1: stacked bars ----------
def bar_row(label, sub, rs, levels_txt):
    n = len(rs)
    c = collections.Counter(r['group'] for r in rs)
    segs = []
    for g, gl in GROUPS:
        k = c.get(g, 0)
        if not k: continue
        pct = 100 * k / n
        ids = ', '.join(r['id'] for r in rs if r['group'] == g)
        tip = f"{label}: {gl}, {k} of {n} rows ({pct:.0f}%). {ids}"
        lab = f'<span class="seglab">{k}</span>' if pct >= 8 else ''
        segs.append(f'<div class="seg s-{g}" style="flex:{k} 1 0" tabindex="0" data-tip="{E(tip)}" aria-label="{E(tip)}">{lab}</div>')
    return (f'<div class="barrow"><div class="barlab"><span class="bl1">{E(label)}</span><span class="bl2">{E(sub)}</span></div>'
            f'<div class="bar">{"".join(segs)}</div><div class="barnote">{E(levels_txt)}</div></div>')

def levels_txt(rs):
    c = collections.Counter(r['level'] for r in rs)
    return f"{c.get('M',0)} content · {c.get('G',0)} profile · {c.get('S',0)} system"

fig1 = []
for k, name, base in CASES:
    rs = [r for r in rows if r['case'] == k]
    fig1.append(bar_row(name, f'{len(rs)} rows · base {base}', rs, levels_txt(rs)))
fig1.append('<div class="bardiv"></div>')
fig1.append(bar_row('All cases', '75 rows', rows, levels_txt(rows)))
content = [r for r in rows if r['level'] == 'M']
fig1.append(bar_row('Content rows only', f'{len(content)} rows', content, 'metadata-content needs'))
legend = ''.join(f'<span class="lg"><span class="sw s-{g}"></span>{E(l)}</span>' for g, l in GROUPS)

# counts table (table view of fig 1)
t1 = ['<table class="mini"><thead><tr><th>Case</th>' + ''.join(f'<th>{E(l)}</th>' for _, l in GROUPS) + '<th>Rows</th></tr></thead><tbody>']
for label, rs in [(n, [r for r in rows if r['case'] == k]) for k, n, _ in CASES] + [('All cases', rows), ('Content rows only', content)]:
    c = collections.Counter(r['group'] for r in rs)
    t1.append(f'<tr><th>{E(label)}</th>' + ''.join(f'<td>{c.get(g,0)}</td>' for g, _ in GROUPS) + f'<td>{len(rs)}</td></tr>')
t1.append('</tbody></table>')

# ---------- heatmaps ----------
def heatmap(cols, key, multi=False, caption=''):
    h = ['<table class="heat"><thead><tr><th></th>' + ''.join(f'<th><span>{E(l)}</span></th>' for _, l in cols) + '</tr></thead><tbody>']
    for k, name, _ in CASES + [('All', 'All cases', '')]:
        rs = rows if k == 'All' else [r for r in rows if r['case'] == k]
        n = len(rs)
        cells = []
        for ck, cl in cols:
            hit = [r for r in rs if (ck in r[key] if multi else r[key] == ck)]
            v = len(hit)
            if v == 0:
                cells.append('<td class="h0" data-tip="' + E(f'{name}: {cl}, none') + '" tabindex="0">·</td>')
            else:
                b = heat_bin(v / n)
                tip = f"{name}: {cl}, {v} of {n} rows ({100*v/n:.0f}%). " + ', '.join(r['id'] for r in hit)
                cells.append(f'<td class="hb{b}" data-tip="{E(tip)}" tabindex="0">{v}</td>')
        cls = ' class="allrow"' if k == 'All' else ''
        h.append(f'<tr{cls}><th>{E(name)}<span class="n">{n}</span></th>' + ''.join(cells) + '</tr>')
    h.append('</tbody></table>')
    return ''.join(h)

PROB_SHORT = [('P1','Discover'),('P2','Access'),('P3','Understand'),('P4','Link'),('P5','Legal'),('P6','Records'),('P7','Profile')]
fig2 = heatmap(PROB_SHORT, 'problem')
DER_SHORT = [('std','Prior spec'),('proj','Project / literature'),('exp','Expert / WG'),('prac','Practice'),('law','Law / policy'),('tech','Technical')]
fig3 = heatmap(DER_SHORT, 'deriv', multi=True)
heatlegend = ('<div class="heatlegend"><span>share of the case’s rows</span>' +
              ''.join(f'<span class="hk hb{i}"></span>' for i in range(6)) + '<span>0 → 100%</span></div>')

# ---------- writing table ----------
WRITE = [
    ('Published as',
     ['Table 1 of a requirements report: ID, Type, Requirement, Perspective, Importance, Source, Contributor',
      'No list. Needs sit in the §5.2 narrative of D6.2, next to the adopted properties; the 16 rows are a curator extraction',
      '§7.2: one subsection per extension — a requirement sentence, a property table, the design rationale and an RDF example',
      'Objectives and alignment criteria in the method section (§1.1, §4.1–4.2)',
      'Numbered list of five core elements in a workshop paper']),
    ('Written relative to the design',
     ['Before it (June 2022 report; profile October 2023)', 'Alongside it (September 2024 deliverable presenting the extensions)',
      'Recorded in the final specification as the reason for each extension (December 2016)', 'Alongside it (method section of the specification)',
      'After it (paper on the adopted profile, November 2016)']),
    ('Grammatical form',
     ['Obligation on the profile', 'Mixed: profile obligations, reported needs, user capabilities', 'Reported need, passive voice',
      'Normative rule for the profile', 'Capability phrase without a verb']),
    ('Typical sentence',
     ['“napDCAT-AP should support the description of temporal information”',
      '“HealthDCAT-AP mandates the use of persistent dereferenceable URIs”; “one requirement raised during the Technical Working Group sessions was the need to …”',
      '“A requirement has been expressed to expose information about: …”',
      '“GeoDCAT-AP must include, at least, all the mandatory DCAT-AP elements”',
      '“Ability to indicate dataset authors.”']),
    ('Obligation',
     ['“should” in all 40 rows; bindingness in a separate column (32 mandatory, 8 optional)', 'MUST / should, mostly attached to the adopted solution',
      'None in the requirement; obligations in the property tables', 'must / only', 'None']),
    ('What comes with it',
     ['Source, contributor country, stakeholder perspective; no solution', 'Legal excerpts, examples, the adopted term', 'The adopted term and an example; once a rejected alternative (qb:dimension)',
      'Reasons (e.g. avoid conflicts with standards in preparation)', 'The adopted term and a short explanation']),
    ('Granularity (curator count)',
     ['2.2 items per row (max 7); 24 of 40 compound', '1.8 items per row (max 8); 7 of 16 compound', '1.1 items per row; 1 of 7 compound',
      '2.0 items per row; 5 of 7 compound', '1 item per row']),
    ('Names standards or terms',
     ['10 of 40 rows (DCAT-AP, CMC, INSPIRE, DATEX II, MMTIS, delegated regulations)', 'Property names woven into the text', 'Data Cube concepts (dimension, attribute)',
      'DCAT-AP, ISO 19115, INSPIRE', 'Element labels (authors, lineage, usage notes)']),
]
wt = ['<table class="write"><thead><tr><th></th>' + ''.join(f'<th>{E(n)}</th>' for _, n, _ in CASES) + '</tr></thead><tbody>']
for lab, vals in WRITE:
    wt.append(f'<tr><th>{E(lab)}</th>' + ''.join(f'<td>{E(v)}</td>' for v in vals) + '</tr>')
wt.append('</tbody></table>')

data_json = json.dumps([{k: r.get(k) for k in ['id', 'case', 'caseName', 'statement', 'locator', 'level', 'problem', 'deriv', 'resp', 'sub', 'respLabel',
                                               'group', 'terms', 'conf', 'note', 'atoms', 'rq2', 'napType', 'importance', 'nap']} for r in rows],
                       ensure_ascii=False).replace('</', '<\\/')

SEGCSS = ''.join(f'.s-{g}{{background:var(--c-{g})}}.s-{g} .seglab{{color:var(--t-{g})}}' for g, _ in GROUPS)
HEATCSS = ''.join(f'.hb{i}{{background:var(--h{i});color:var(--ht{i})}}' for i in range(6))
page = open('/home/claude/analysis/template.html', encoding='utf-8').read()
page = (page.replace('%%SEGCSS%%', SEGCSS).replace('%%HEATCSS%%', HEATCSS)
        .replace('%%TOK_LIGHT%%', tokens('light')).replace('%%TOK_DARK%%', tokens('dark'))
        .replace('%%FIG1%%', ''.join(fig1)).replace('%%LEGEND%%', legend).replace('%%T1%%', ''.join(t1))
        .replace('%%FIG2%%', fig2).replace('%%FIG3%%', fig3).replace('%%HEATLEGEND%%', heatlegend)
        .replace('%%WRITE%%', ''.join(wt)).replace('%%DATA%%', data_json)
        .replace('%%PROB%%', json.dumps(dict(PROB))).replace('%%DER%%', json.dumps(dict(DER)))
        .replace('%%LEVEL%%', json.dumps(LEVEL)).replace('%%KIND%%', json.dumps(KIND)).replace('%%GLABEL%%', json.dumps(GLABEL)))
import os
os.makedirs('/home/claude/analysis/out', exist_ok=True)
open('/home/claude/analysis/out/reference-requirements-comparison.html', 'w', encoding='utf-8').write(page)

# CSV export
import csv
with open('/home/claude/analysis/out/reference-requirements-coding.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['id', 'case', 'statement_curator_paraphrase', 'source_locator', 'level', 'problem', 'derived_from', 'response', 'response_group',
                'terms', 'confidence', 'items_in_row', 'reuse_or_alignment_rule', 'napcore_type', 'napcore_importance', 'napcore_source', 'napcore_contributor',
                'napcore_perspective', 'note'])
    for r in rows:
        nap = r.get('nap') or ('', '', '')
        w.writerow([r['id'], r['caseName'], r['statement'], r['locator'], LEVEL[r['level']], dict(PROB)[r['problem']],
                    '; '.join(dict(DER)[d] for d in r['deriv']), r['respLabel'], GLABEL[r['group']],
                    '; '.join(f'{t} [{c}] ({KIND[k]})' for t, c, k in r['terms']), r['conf'], r['atoms'], 'yes' if r['rq2'] else '',
                    r.get('napType') or '', r.get('importance') or '', nap[0], nap[1], nap[2], r['note']])
print('ok')
