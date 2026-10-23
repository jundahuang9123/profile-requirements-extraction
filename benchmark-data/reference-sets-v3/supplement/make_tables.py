"""LaTeX tables for the RQ1 paper from the reference sets v3 (adjudicated, PR #45).

Writes
  table-benchmark.tex      Table 2 (summary per case), drop-in replacement in main.tex
  appendix-test-cases.tex  Appendix A: scored atoms of the two test cases (fits the 2-page appendix)
  supplement-reference-requirements.tex  standalone document: every row and atom of all five cases
"""
import json
import os
import re
import sys

REF = os.environ.get('RQ1_REF', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))  # reference-sets-v3
COMMIT = os.environ.get('RQ1_REF_COMMIT', '671c60a')
OUT = os.path.dirname(os.path.abspath(__file__))

CASES = [  # order of Table 2: test cases first
 ('mobilitydcat', 'mobilityDCAT-AP', 'NAPCORE analysis~\\cite{bures2022napcore} (2022)', 'NAPCORE requirement analysis (2022), Table~1', '13+3', '822', '2.0.1', 'test'),
 ('geodcat', 'GeoDCAT-AP', 'GeoDCAT-AP 1.0~\\cite{geodcatap10} (2015)', 'GeoDCAT-AP 1.0 (2015)', '5', '271', '1.1', 'test'),
 ('healthdcat', 'HealthDCAT-AP', 'HealthData@EU D6.2~\\cite{healthdataeu2024d62} (2024)', 'HealthData@EU Pilot D6.2 (2024)', '3+2', '\\tbd', '3.0.0', 'dev.'),
 ('statdcat', 'StatDCAT-AP', 'StatDCAT-AP 1.0.0~\\cite{statdcatap} (2016)', 'StatDCAT-AP 1.0.0 (2016)', '2', '60', '1.1', 'dev.'),
 ('jrc-research', 'DCAT-AP-JRC', 'Perego et al.~\\cite{perego2016jrc} (2016)', 'Perego et al., SDSVoc 2016, paper 27', '3', '59', '1.1', 'dev.'),
]
LEVEL = {'content': 'c', 'profile': 'p', 'system': 's'}
STATUS = {'requirement': 'req.', 'proposed': 'prop.', 'open_issue': 'open', 'guidance': 'guid.', 'deferred': 'def.'}
REL = {'restates_base': 'restates', 'tightens_base': 'tightens', 'extends_base': 'extends', 'partly_base': 'partly',
       'beyond_base': 'beyond', 'not_term_level': '--', 'unresolved': '?'}
EV = {'supported': 'S', 'partial': 'P', 'uncertain': 'U', 'unsupported': 'N'}


def tex(s):
    """Escape plain text for LaTeX (T1, utf8 inputenc); straight double quotes become TeX quotes."""
    s = s.replace('\\', '\\textbackslash{}')
    s = re.sub(r'([&%$#_{}])', r'\\\1', s)
    s = s.replace('~', '\\textasciitilde{}').replace('^', '\\textasciicircum{}')
    s = re.sub(r'"([^"]*)"', r"``\1''", s)
    assert '"' not in s, s
    return s


def ev(a, kind):
    ie = a.get('input_evidence') or {}
    b = ie.get(kind) if isinstance(ie, dict) else None
    return EV[b['label']] if b else '--'


def scored_mark(a):
    if a['scored_by_default']:
        return '\\checkmark'
    if a.get('merged_into'):
        return 'm'
    if a.get('umbrella_of'):
        return 'u'
    return ''


def load(case):
    return json.load(open(f'{REF}/{case}.json', encoding='utf-8'))


def counts(d):
    c = d['counts']
    rows = d['requirements']
    v1 = sum(r['added_in'] == 'v1' for r in rows)
    return dict(rows=len(rows), v1=v1, added=len(rows) - v1, atoms=c['scored_by_default'],
                settled=c['scored_by_default_requirement_status_only'],
                in_base=c['scored_by_default'] - c['scored_by_default_without_dcat_ap_restatements'],
                stated=c['scored_by_default_raw_supported'], stated_or_partly=c['scored_by_default_raw_supported_or_partial'],
                cons=c.get('scored_by_default_consolidation_supported'), cons_p=c.get('scored_by_default_consolidation_supported_or_partial'))


# ---------------------------------------------------------------- Table 2
def table_benchmark():
    lines = []
    tot = dict(v1=0, added=0, atoms=0, settled=0, in_base=0, stated=0, stated_or_partly=0)
    for case, name, ref, _, files, units, base, use in CASES:
        c = counts(load(case))
        for k in tot:
            tot[k] += c[k]
        rows = f"{c['v1']}" if not c['added'] else f"{c['v1']}+{c['added']}"
        lines.append(f"{name} & {ref} & {files} & {units} & {base} & {rows} & {c['atoms']} & {c['stated']} ({c['stated_or_partly']}) & {use}\\\\")
    body = '\n'.join(lines)
    return f"""% Table 2, generated from benchmark-data/reference-sets-v3 (commit {COMMIT}) by make_tables.py.
% "Stated" uses the raw input-evidence labels of v3: AI labels, human review pending; align Sect. 5 and the
% Use of Generative AI section with how they were made.
\\begin{{table}}[t]
\\caption{{Benchmark cases. Files: evidence files plus base specifications kept as background; units: evidence units; base: the \\dcatap\\ release that the extension's own documents cite. Rows: published reference rows plus rows added from the same document. Atoms: scoring units (content, not deferred, each need once); of all {tot['atoms']}, {tot['in_base']} restate the base and {tot['atoms'] - tot['settled']} are proposals, open issues or guidance in their source. Stated: atoms whose meaning the raw corpus states (in parentheses, at least in part).}}
\\label{{tab:benchmark}}
\\centering\\scriptsize\\setlength{{\\tabcolsep}}{{4pt}}
\\begin{{tabularx}}{{\\textwidth}}{{@{{}}lYrrlrrrl@{{}}}}
\\toprule
Case & Reference (date) & Files & Units & Base & Rows & Atoms & Stated & Use\\\\
\\midrule
{body}
\\midrule
Total & & & & & {tot['v1']}+{tot['added']} & {tot['atoms']} & {tot['stated']} ({tot['stated_or_partly']}) & \\\\
\\bottomrule
\\end{{tabularx}}
\\end{{table}}
"""


# ---------------------------------------------------------------- Appendix A
def appendix():
    head = ('\\toprule\nID & Reference requirement (atom) & Base & Raw & Cons.\\\\\n\\midrule\n')
    body = []
    n_total = 0
    for case, name, _, _, _, _, base, use in CASES:
        if use != 'test':
            continue
        d = load(case)
        atoms = [a for a in d['atoms'] if a['scored_by_default']]
        n_total += len(atoms)
        body.append(f"\\multicolumn{{5}}{{@{{}}l}}{{\\textbf{{{name}}} ({len(atoms)} atoms, base \\dcatap\\ {base})}}\\\\*")
        for a in atoms:
            cons = ev(a, 'consolidation') if case == 'mobilitydcat' else '--'
            body.append(f"\\req{{{a['id']}}} & {tex(a['statement'])} & {REL[a['relation_to_base']]} & {ev(a, 'raw')} & {cons}\\\\")
        body.append('\\addlinespace')
    body = '\n'.join(body[:-1])
    return f"""% Appendix A, generated from benchmark-data/reference-sets-v3 (commit {COMMIT}) by make_tables.py.
% Needs \\usepackage{{longtable}} in the preamble. ESWC 2027 allows an optional appendix of at most 2 pages;
% reviewers need not read it, so the paper must not depend on it. Starting it on a new page keeps its length visible.
\\clearpage
\\appendix
\\section{{Reference Requirements of the Test Cases}}\\label{{app:references}}

% longtable captions in the LNCS style (bold ``Table n.'', small type), as for floating tables.
\\makeatletter
\\def\\LT@makecaption#1#2#3{{\\LT@mcol\\LT@cols c{{\\hbox to\\z@{{\\hss\\parbox[t]\\LTcapwidth{{\\small{{\\bfseries #2.}} #3\\par\\vskip\\abovecaptionskip}}\\hss}}}}}}
\\makeatother
{{\\scriptsize\\setlength{{\\tabcolsep}}{{2.5pt}}\\setlength{{\\LTcapwidth}}{{\\textwidth}}
\\begin{{longtable}}{{@{{}}>{{\\raggedright\\arraybackslash}}p{{1.25cm}}>{{\\raggedright\\arraybackslash}}p{{8.0cm}}lcc@{{}}}}
\\caption{{The {n_total} scored reference requirements (atoms) of the test cases; all are requirements in their source. Base: relation to the pinned \\dcatap\\ release. Raw, Cons.: whether the raw and the pre-consolidation corpus state the atom (S stated, P in part, U uncertain, N not stated). The other cases, unscored atoms and the rows are in the supplementary material.}}\\label{{tab:app-references}}\\\\
{head}\\endfirsthead
{head}\\endhead
\\bottomrule
\\endlastfoot
{body}
\\end{{longtable}}}}
"""


# ---------------------------------------------------------------- Supplement
def supplement():
    parts = []
    for case, name, _, refdoc, _, _, base, use in CASES:
        d = load(case)
        c = counts(d)
        atoms_by_row = {}
        for a in d['atoms']:
            atoms_by_row.setdefault(a['parent_id'], []).append(a)
        has_cons = case in ('mobilitydcat', 'healthdcat')
        parts.append(f"\\multicolumn{{8}}{{@{{}}>{{\\raggedright\\arraybackslash}}p{{\\linewidth}}@{{}}}}{{\\normalsize\\textbf{{{name}}}\\quad\\footnotesize {refdoc}; base \\dcatap\\ {base}; {use.replace('dev.', 'development')} case}}\\\\*")
        parts.append(f"\\multicolumn{{8}}{{@{{}}>{{\\raggedright\\arraybackslash}}p{{\\linewidth}}@{{}}}}{{{c['rows']} rows ({c['v1']} published), {len(d['atoms'])} atoms, {c['atoms']} scored ({c['settled']} requirements), "
                     f"{c['in_base']} restate the base, {c['stated']} stated ({c['stated_or_partly']} at least in part)"
                     + (f"; pre-consolidation corpus: {c['cons']} ({c['cons_p']})" if has_cons else '') + "}\\\\*")
        parts.append('\\midrule')
        for r in d['requirements']:
            added = '' if r['added_in'] == 'v1' else '$^{\\dagger}$'
            loc = tex(re.sub(r'^Main report Table 1, original Req-\d+, PDF pages ', 'Table 1, PDF pp. ', r.get('source_locator') or ''))
            parts.append(f"\\multicolumn{{8}}{{@{{}}>{{\\raggedright\\arraybackslash}}p{{\\linewidth}}@{{}}}}{{\\textbf{{\\req{{{r['id']}}}}}{added}\\enspace "
                         f"{tex(r['statement'])}\\enspace\\textit{{({loc})}}}}\\\\*")
            for a in atoms_by_row.get(r['id'], []):
                cons = ev(a, 'consolidation') if has_cons else '--'
                parts.append(f"\\req{{{a['id']}}} & {tex(a['statement'])} & {LEVEL[a['stratum']]} & {STATUS[a['status_in_source']]} & "
                             f"{REL[a['relation_to_base']]} & {ev(a, 'raw')} & {cons} & {scored_mark(a)}\\\\")
            parts.append('\\addlinespace[2pt]')
        parts.append('\\midrule')
    body = '\n'.join(parts[:-1])
    head = '\\toprule\nID & Reference requirement (atom) & Lev. & Status & Base & Raw & Cons. & Sc.\\\\\n\\midrule\n'
    return f"""% Supplementary material: every row and atom of the five reference sets.
% Generated from benchmark-data/reference-sets-v3 (commit {COMMIT}) by make_tables.py. Compile with pdfLaTeX.
\\documentclass{{llncs}}
\\usepackage[T1]{{fontenc}}
\\IfFileExists{{lmodern.sty}}{{\\usepackage{{lmodern}}}}{{}}
\\usepackage[utf8]{{inputenc}}
\\usepackage{{booktabs}}
\\usepackage{{array}}
\\usepackage{{longtable}}
\\usepackage{{amssymb}}
\\usepackage{{microtype}}
\\usepackage[hidelinks]{{hyperref}}
\\newcommand{{\\dcat}}{{\\textsc{{dcat}}}}
\\newcommand{{\\dcatap}}{{\\textsc{{dcat-ap}}}}
\\newcommand{{\\req}}[1]{{\\texttt{{#1}}}}

\\title{{Supplementary Material: Reference Requirements of the Benchmark}}
\\author{{Anonymous Author(s)}}
\\institute{{Anonymous Institution}}

\\begin{{document}}
\\maketitle

This table lists every row and atom of the five reference sets (version 3). Rows are the published reference rows and rows added from the same reference document (marked $^{{\\dagger}}$); each row is followed by its atoms, the scoring units. The reference statements are curator paraphrases; the reference documents' own wording is cited in the benchmark files. A provisional adjudication of reviewed items was applied on 23 October 2026: one duplicate merged, one umbrella atom left out of scoring, two compound atoms split, three evidence labels downgraded and one omitted need restored; each change is logged in the benchmark files.

\\paragraph{{Columns.}} \\emph{{Lev.}}: the atom is about catalog content (c), the profile as a whole (p) or the catalog system (s); only content atoms are scored. \\emph{{Status}} in the source: requirement (req.), proposal (prop.), open issue (open), guidance (guid.) or deferred to future work (def.). \\emph{{Base}}: relation to the pinned \\dcatap\\ release: restates, tightens, extends, partly covered by, or beyond the base; -- for atoms that are not about metadata terms, ? if unresolved. \\emph{{Raw}} and \\emph{{Cons.}}: whether the raw corpus and, for mobilityDCAT-AP and HealthDCAT-AP, the pre-consolidation corpus state the atom: S stated, P in part, U uncertain, N not stated, -- no such corpus. These are AI labels with verbatim quotations checked by program; human review is pending. \\emph{{Sc.}}: scored by default (\\checkmark); m merged into an equivalent atom of another row (\\req{{Req-24.1}} into \\req{{Req-19.7}}); u an umbrella of separately scored atoms (\\req{{H-4.1}} of \\req{{H-16.1}}, \\req{{H-26.1}}, \\req{{H-28.1}}, \\req{{H-36.1}}, \\req{{H-66.2}}).

{{\\scriptsize\\setlength{{\\tabcolsep}}{{3pt}}
\\begin{{longtable}}{{@{{}}>{{\\raggedright\\arraybackslash}}p{{1.3cm}}>{{\\raggedright\\arraybackslash}}p{{5.5cm}}cllccc@{{}}}}
{head}\\endfirsthead
{head}\\endhead
\\bottomrule
\\endlastfoot
{body}
\\end{{longtable}}}}

\\end{{document}}
"""


def main():
    for name, text in (('table-benchmark.tex', table_benchmark()), ('appendix-test-cases.tex', appendix()),
                       ('supplement-reference-requirements.tex', supplement())):
        open(os.path.join(OUT, name), 'w', encoding='utf-8').write(text)
        print('wrote', name, len(text))


if __name__ == '__main__':
    main()
