"""Build the v3 merged benchmark reference sets (v1 rows + Claude v2 completion + PR #45 audit)."""
import collections, csv, json, os, re, sys

sys.path.insert(0, '/home/claude/analysis')
sys.path.insert(0, '/home/claude/merge')
from codes import CODES, DERIV
from plan_health import HEALTH, PARENT_CHANGES as H_CHANGES, NEW_PARENTS as H_NEW
from plan_other import STAT, GEO, JRC, STAT_PARENT_CHANGES, GEO_PARENT_CHANGES, JRC_PARENT_CHANGES
from plan_mobility_v3 import TABLE1, ATOMS as MOB_ATOMS, OVERLAPS as MOB_OVERLAPS
from plan_derived import DERIVED
from codes import NAP
from srcfind import found, norm, SRC
import adjudication_2026_10_23 as ADJ
ADJ_SUMMARY = {}

_pages = {}


def anchor_page(case, anchor):
    """Physical PDF page (1-based, from the form feeds in the pdftotext output) where the anchor starts."""
    a = norm(anchor)
    for f in SRC[case]:
        key = (case, f)
        if key not in _pages:
            _pages[key] = [norm(p) for p in open('/home/claude/analysis/' + f, encoding='utf-8').read().split('\f')]
        pages = _pages[key]
        for i, p in enumerate(pages):
            if a in p or a in p.replace('- ', '-'):
                return i + 1
        for i in range(len(pages) - 1):
            j = pages[i] + ' ' + pages[i + 1]
            if a in j or a in j.replace('- ', '-'):
                return i + 1
    return None

REPO = '/home/claude/jundahuang9123/profile-requirements-extraction/benchmark-data'
V2 = '/home/claude/analysis/out/v2'
PR = '/home/claude/pr45/benchmark-data/reference-audit-2026-10-22'
OUT = '/home/claude/merge/out/reference-sets-v3'
LABELS = '/home/claude/merge/label/labels-merged.json'
CONSOLIDATION_CASES = ('healthdcat', 'mobilitydcat')
LABELLED_BY = 'Claude subagents working only from the staged inputs (separate from the curation pass), 2026-10-22; quotes machine-checked; not human-reviewed'

LEVEL = {'M': 'content', 'G': 'profile', 'S': 'system'}
REL_FROM_RESP = {'A': 'beyond_base', 'B': 'beyond_base', 'C': 'beyond_base', 'D': 'extends_base', 'E': 'tightens_base',
                 'F': 'restates_base', 'G': 'not_term_level', 'H': 'beyond_base'}
SPECIAL = {'H-3': ('beyond_base', 'proposed'), 'H-12': ('unresolved', 'open_issue'), 'S-7': ('restates_base', 'guidance')}
STATUS_MODALITY = {'requirement': 'requirement', 'proposed': 'proposed', 'deferred': 'deferred_future_work',
                   'open_issue': 'issue', 'guidance': 'representation_guidance'}
ADDS_TO_V1 = {'HC-012', 'HC-013', 'HC-048', 'HC-049', 'HC-095', 'HC-085'}

CASES = {
 'mobilitydcat': dict(v1='consolidated-requirements.json', key='Req', doc='NAPCORE 4.4.2.1 Requirement analysis v1.0 (2022), Table 1', base='DCAT-AP 2.0.1',
                      changes={}, atoms=None, src=None),
 'healthdcat': dict(v1='curated-requirements.json', key='H', doc='HealthData@EU Pilot D6.2 (2024-09-30)', base='DCAT-AP 3.0.0',
                    changes=H_CHANGES, atoms=HEALTH, src='health', new=H_NEW),
 'statdcat': dict(v1='requirements-and-resolutions.json', key='S', doc='StatDCAT-AP 1.0.0 (2016-12-15)', base='DCAT-AP 1.1',
                  changes=STAT_PARENT_CHANGES, atoms=STAT, src='stat'),
 'geodcat': dict(v1='alignment-requirements.json', key='G', doc='GeoDCAT-AP 1.0 (2015-12-23)', base='DCAT-AP 1.1',
                 changes=GEO_PARENT_CHANGES, atoms=GEO, src='geo'),
 'jrc-research': dict(v1='core-requirements.json', key='JRC', doc='Perego et al., Using DCAT-AP for research data (SDSVoc 2016, paper 27)',
                      base='DCAT-AP 1.1', changes=JRC_PARENT_CHANGES, atoms=JRC, src=None),
}

pr_items = {c['id']: c for c in json.load(open(f'{PR}/expansion-candidates.json'))['requirements']}
pr_legacy = {r['reference_id']: r for r in json.load(open(f'{PR}/legacy-row-review.json'))['rows']}
pr_clauses = json.load(open(f'{PR}/mobility-clause-draft.json'))['atoms']

MERGE_RULES = [
 'Rows: all v1 rows and all Claude v2 rows keep their IDs. A row statement, locator or status changes only where a source check showed it wrong; the earlier value is kept in statement_before_v3, source_locator_before_v3 or status_in_source_before_v3.',
 'Atoms are the scoring units and every atom belongs to exactly one row. PR #45 splits are used where PR #45 split a need; PR #45 items that state the same need for another data group are merged into one atom whose applicability lists the groups.',
 'Content found only in Claude v2 is split into atoms; content found only in PR #45 is added; a few needs found while checking anchors are added and marked added_in_merge.',
 'Requirements that only restate DCAT-AP (relation_to_base = restates_base) are kept and flagged with restates_dcat_ap so they can be left out at scoring time.',
 'Source inconsistencies and source errors are recorded on the atom (source_flags), not resolved.',
 'Overlapping atoms point to each other in overlaps; under one-to-one matching a prediction can be credited to only one of them.',
 'Adjudication (2026-10-23): equivalent atoms from different rows are scored once (the duplicate names its canonical atom in merged_into); an atom that only bundles separately scored atoms (umbrella_of) is not scored by default; every overlap pair carries a review (overlap_review).',
]
SCORING = {
 'unit': 'atom',
 'default_selection': 'stratum = content, status_in_source != deferred, and neither merged_into another atom nor umbrella_of separately scored atoms (field scored_by_default)',
 'optional_filters': {
   'leave_out_dcat_ap_restatements': 'restates_dcat_ap = true',
   'leave_out_rq2_reuse_and_alignment_rules': 'reuse_or_alignment_rule = true',
   'leave_out_unsettled_status': 'status_in_source in (proposed, open_issue, guidance)',
   'leave_out_atoms_added_in_merge': 'provenance.added_in_merge = true'},
 'never': 'Score a row and its atoms together, or credit one prediction to two overlapping atoms.',
 'row_level': 'Rows remain available for a separate row-level recovery analysis.',
}


def norm_rel(rel):
    return rel or 'not_term_level'


def build_case(case, cfg):
    v1_rows = json.load(open(f"{REPO}/{case}/reference-requirements/{cfg['v1']}"))['requirements']
    v2_file = f"{V2}/{case}/reference-requirements/{cfg['v1'].replace('.json', '-v2.json')}"
    v2_all = json.load(open(v2_file))['requirements'] if os.path.exists(v2_file) else []
    v2_rows = [r for r in v2_all if r.get('added_in') == 'v2']

    rows = []
    for r in v1_rows:
        c = CODES[r['id']]
        rel, st = SPECIAL.get(r['id'], (REL_FROM_RESP[c['resp']], 'requirement'))
        row = dict(r)
        row.update(level=LEVEL[c['level']], relation_to_base=rel, status_in_source=st, origin=DERIV.get(r['id'], []),
                   problem=c['problem'], reuse_or_alignment_rule=c['rq2'], added_in='v1')
        lr = pr_legacy.get(r['id'])
        if lr:
            row['pr45_legacy_review'] = lr['review_action']
        rows.append(row)
    for r in v2_rows:
        row = {k: v for k, v in r.items() if k not in ('atoms', 'overlaps')}
        row['overlaps_v2'] = r.get('overlaps', [])
        rows.append(row)
    for n in cfg.get('new', []):
        rows.append(dict(id=n['id'], statement=n['statement'], statement_kind='curator_paraphrase', source_locator=n['source_locator'],
                         level=n['level'], relation_to_base=n['relation_to_base'], status_in_source=n['status_in_source'],
                         origin=n['origin'], problem=n['problem'],
                         reuse_or_alignment_rule=False, added_in='v3', note=n['note'],
                         curated_by='Claude (Anthropic), 2026-10-22, merge of Claude v2 and PR #45; not independently adjudicated',
                         adjudication_status='not_independently_adjudicated'))
    for r in rows:
        if case == 'mobilitydcat':
            src, contrib, persp = NAP[r['id']]
            r['table1_text'] = ' '.join(TABLE1[r['id']])
            r['table1_text_check'] = 'short exact excerpts read from the NAPCORE PDF via WebFetch on 2026-10-22; not in the corpus'
            r.update(table1_source=src, table1_contributor=contrib, table1_perspective=persp)
            r['derived_from'] = f'NAPCORE Table 1 source: {src}'
        else:
            r['derived_from'] = DERIVED[r['id']]
    byid = {r['id']: r for r in rows}
    for rid, ch in cfg['changes'].items():
        row = byid[rid]
        if 'statement' in ch:
            row['statement_before_v3'] = row['statement']
            row['statement'] = ch['statement']
        if 'source_locator' in ch:
            row['source_locator_before_v3'] = row['source_locator']
            row['source_locator'] = ch['source_locator']
        if 'status_in_source' in ch:
            row['status_in_source_before_v3'] = row['status_in_source']
            row['status_in_source'] = ch['status_in_source']
        if 'reason' in ch:
            row['changed_in_v3'] = ch['reason']
        if 'note_add' in ch:
            row['v3_note'] = ch['note_add']

    # ---- atoms
    atoms = []
    if case == 'mobilitydcat':
        for m in MOB_ATOMS:
            pid = m['id'].rsplit('.', 1)[0]
            p = byid[pid]
            stratum = m['stratum'] or p['level']
            if stratum == 'content' and not m['rel']:
                raise SystemExit(f'missing relation for {m["id"]}')
            rel = m['rel'] if stratum == 'content' else 'not_term_level'
            modality = p.get('importance') if m['modality'] == 'should' else f"{m['modality']} ({p.get('importance')})"
            atoms.append(dict(id=m['id'], parent_id=pid, statement=m['statement'], stratum=stratum,
                              status_in_source='requirement', modality=modality, applicability='',
                              relation_to_base=rel, relation_note='', reuse_or_alignment_rule=m['rq2'] if m['rq2'] is not None else p['reuse_or_alignment_rule'],
                              source_locator=p['source_locator'], anchor_page=None, anchor_quote=TABLE1[pid][m['anchor_idx']],
                              anchor_check='from_web_fetch_not_verified_locally: NAPCORE Table 1 (short exact excerpts, 2026-10-22)',
                              overlaps=[], source_flags=[],
                              provenance=dict(v1_row=True, claude_v2_rows=[], pr45_ids=m['pr45'], added_in_merge=False,
                                              checked_against_table1=True),
                              mobility=dict(type=p.get('type'), importance=p.get('importance'), table1_modal=m['modality']),
                              notes=m['note']))
        for x, y in MOB_OVERLAPS:
            for a in atoms:
                if a['id'] == x:
                    a['overlaps'].append(y)
    else:
        for a in cfg['atoms']:
            p = byid[a['parent']]
            prs = [pr_items[i] for i in a['pr45']]
            status = a['status'] or p['status_in_source']
            modality = a['modality'] or (prs[0]['source_modality'] if prs else STATUS_MODALITY[status])
            # D6.2 presents the §5.3 minimum elements as "discussed and proposed" (PR #45 finding): mark them proposed.
            if not a['status'] and status == 'requirement' and (modality.startswith('proposed_') or modality in ('conditional_mandatory', 'optional')):
                status = 'proposed'
            app = a['app'] if a['app'] is not None else (prs[0]['applicability'] if prs else '')
            if cfg['src'] and a['anchor']:
                check = 'verbatim_in_source_text' if found(cfg['src'], a['anchor']) else 'NOT_FOUND'
            elif a['anchor']:
                check = 'from_web_fetch_not_verified_locally'
            else:
                check = 'locator_only'
            pages = sorted({pg for x in prs for pg in (x.get('pdf_pages') or [])})
            apage = anchor_page(cfg['src'], a['anchor']) if (cfg['src'] and a['anchor']) else None
            v1_parent = p['added_in'] == 'v1'
            atom = dict(id=a['id'], parent_id=a['parent'], statement=a['statement'],
                        stratum=a['stratum'] or p['level'], status_in_source=status, modality=modality, applicability=app,
                        relation_to_base=a['rel'] or norm_rel(p.get('relation_to_base')), relation_note='',
                        reuse_or_alignment_rule=a['rq2'] if a['rq2'] is not None else bool(p.get('reuse_or_alignment_rule')),
                        source_locator=a['loc'] or p['source_locator'], pr45_pdf_pages=pages, anchor_page=apage, anchor_quote=a['anchor'], anchor_check=check,
                        overlaps=a['overlaps'], source_flags=a['flags'],
                        provenance=dict(v1_row=v1_parent and not (set(a['pr45']) & ADDS_TO_V1), claude_v2_rows=a['v2'],
                                        pr45_ids=a['pr45'], added_in_merge=a['added']),
                        notes=a['note'])
            if 'geo' in a:
                g = dict(a['geo'])
                if a['id'] == 'G-16.1':
                    g['dcat_ap_coverage'] = 'No (creation date not included)'
                elif a['id'] in ('G-16.2', 'G-16.3'):
                    g['dcat_ap_coverage'] = 'Yes'
                g['geodcat_ap_representation'] = prs[0].get('geodcat_representation') if prs else None
                atom['geo'] = g
            atoms.append(atom)

    for a in atoms:
        pv = a['provenance']
        if pv['added_in_merge']:
            fb = 'added in merge'
        elif pv['claude_v2_rows'] and pv['pr45_ids']:
            fb = 'both'
        elif pv['claude_v2_rows']:
            fb = 'Claude v2 only'
        elif case == 'mobilitydcat':
            fb = 'v1 row (PR #45 clause, checked against Table 1)' if pv['pr45_ids'] else 'v1 row (added from Table 1)'
        elif pv['pr45_ids'] and pv['v1_row']:
            fb = 'v1 row (split by PR #45)'
        elif pv['pr45_ids']:
            fb = 'PR #45 only'
        else:
            fb = 'v1 row'
        pv['found_by'] = fb
        a['restates_dcat_ap'] = a['relation_to_base'] == 'restates_base'
        par = next(r for r in rows if r['id'] == a['parent_id'])
        a['derived_from'] = par['derived_from']
        a['origin'] = par.get('origin', [])
        a['scored_by_default'] = a['stratum'] == 'content' and a['status_in_source'] != 'deferred'
        a['adjudication_status'] = 'not_independently_adjudicated'

    labels = json.load(open(LABELS, encoding='utf-8')) if os.path.exists(LABELS) else {}
    for a in atoms:
        lab = labels.get(a['id'])
        if lab:
            a['input_evidence'] = dict(raw=lab.get('raw'), consolidation=lab.get('consolidation') if case in CONSOLIDATION_CASES else None,
                                       labelled_by=LABELLED_BY, human_review='pending')
        else:
            a['input_evidence'] = 'unassessed'
    ADJ_SUMMARY[case] = ADJ.apply(case, rows, atoms)
    # overlap links are symmetric
    idx = {a['id']: a for a in atoms}
    for a in atoms:
        for o in list(a['overlaps']):
            if o in idx and a['id'] not in idx[o]['overlaps']:
                idx[o]['overlaps'].append(a['id'])
    for a in atoms:
        a['overlaps'] = sorted(set(a['overlaps']), key=lambda s: [int(x) if x.isdigit() else x for x in re.split(r'[-.]', s)])
    by_parent = collections.defaultdict(list)
    for a in atoms:
        by_parent[a['parent_id']].append(a['id'])
    for r in rows:
        r['atom_ids'] = by_parent.get(r['id'], [])
    return rows, atoms, v1_rows, v2_rows


def _ev(a, kind, ok):
    ie = a.get('input_evidence')
    if not isinstance(ie, dict) or not ie.get(kind):
        return False
    b = ie[kind]
    return b['label'] in ok and b.get('quotes_verified', False)


def evidence_counts(atoms):
    scored = [a for a in atoms if a['scored_by_default']]
    labelled = [a for a in atoms if isinstance(a.get('input_evidence'), dict)]
    out = {'atoms_with_evidence_labels': len(labelled)}
    if not labelled:
        return out
    for kind in ('raw', 'consolidation'):
        if not any(a['input_evidence'].get(kind) for a in labelled):
            continue
        out[f'{kind}_evidence_labels'] = dict(collections.Counter(a['input_evidence'][kind]['label'] for a in labelled if a['input_evidence'].get(kind)))
        out[f'scored_by_default_{kind}_supported'] = sum(1 for a in scored if _ev(a, kind, ('supported',)))
        out[f'scored_by_default_{kind}_supported_or_partial'] = sum(1 for a in scored if _ev(a, kind, ('supported', 'partial')))
    return out


def counts(rows, atoms):
    c = collections.Counter
    content = [a for a in atoms if a['scored_by_default']]
    return {
     'rows': len(rows), 'rows_by_added_in': dict(c(r['added_in'] for r in rows)),
     'atoms': len(atoms), 'atoms_by_stratum': dict(c(a['stratum'] for a in atoms)),
     'atoms_by_status': dict(c(a['status_in_source'] for a in atoms)),
     'atoms_by_relation_to_base': dict(c(a['relation_to_base'] for a in atoms)),
     'atoms_by_found_by': dict(c(a['provenance']['found_by'] for a in atoms)),
     'scored_by_default': len(content),
     'scored_by_default_without_dcat_ap_restatements': sum(1 for a in content if not a['restates_dcat_ap']),
     'scored_by_default_without_rq2_rules': sum(1 for a in content if not a['reuse_or_alignment_rule']),
     'scored_by_default_requirement_status_only': sum(1 for a in content if a['status_in_source'] == 'requirement'),
     'atoms_merged_for_scoring': sum(1 for a in atoms if a.get('merged_into')),
     'umbrella_atoms_not_scored': sum(1 for a in atoms if a.get('umbrella_of')),
     'atoms_provisionally_adjudicated': sum(1 for a in atoms if a.get('adjudication')),
     'atoms_with_source_flags': sum(1 for a in atoms if a['source_flags']),
     **evidence_counts(atoms),
     'atoms_with_overlaps': sum(1 for a in atoms if a['overlaps']),
    }


def validate(case, rows, atoms, v1_rows, v2_rows):
    errs = []
    ids = [a['id'] for a in atoms]
    errs += [f'duplicate atom {k}' for k, v in collections.Counter(ids).items() if v > 1]
    rids = {r['id'] for r in rows}
    errs += [f'atom {a["id"]} has unknown parent {a["parent_id"]}' for a in atoms if a['parent_id'] not in rids]
    errs += [f'atom {a["id"]} id does not start with its parent' for a in atoms if not a['id'].startswith(a['parent_id'] + '.')]
    errs += [f'row {r["id"]} has no atoms' for r in rows if not r['atom_ids']]
    aid = set(ids)
    errs += [f'atom {a["id"]} overlaps unknown {o}' for a in atoms for o in a['overlaps'] if o not in aid]
    errs += [f'atom {a["id"]} anchor not found' for a in atoms if a['anchor_check'] == 'NOT_FOUND']
    for a in atoms:
        for k in ('stratum', 'status_in_source', 'modality', 'relation_to_base', 'source_locator'):
            if not a.get(k):
                errs.append(f'atom {a["id"]} missing {k}')
        if a['stratum'] not in ('content', 'profile', 'system'):
            errs.append(f'atom {a["id"]} bad stratum')
        if a['relation_to_base'] not in ('restates_base', 'tightens_base', 'extends_base', 'partly_base', 'beyond_base', 'not_term_level', 'unresolved'):
            errs.append(f'atom {a["id"]} bad relation')
    covered_v2 = {r for a in atoms for r in a['provenance']['claude_v2_rows']}
    errs += [f'v2 row {r["id"]} not covered by any atom' for r in v2_rows if r['id'] not in covered_v2 and not any(x['parent_id'] == r['id'] for x in atoms)]
    errs += [f'v1 row {r["id"]} lost' for r in v1_rows if r['id'] not in rids]
    return errs


def one_line(d):
    return {k: re.sub(r'\s+', ' ', v).strip() if isinstance(v, str) else v for k, v in d.items()}


def write_evidence_csv(all_atoms):
    """Atom-level evidence labels in the columns of benchmark-data/REFERENCE-COVERAGE-TEMPLATE.csv."""
    cols = ['benchmark', 'reference_id', 'reference_file', 'independent_reference_review', 'raw_evidence_coverage',
            'raw_source_paths_and_locators', 'consolidation_evidence_coverage', 'consolidation_source_paths_and_locators', 'reviewer', 'rationale']
    def locs(b):
        return '; '.join(f"{s['path']} ({s['locator']})" for s in b['sources']) if b else ''
    with open(f'{OUT}/reference-coverage.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for case, a in all_atoms:
            ie = a.get('input_evidence')
            raw = ie.get('raw') if isinstance(ie, dict) else None
            con = ie.get('consolidation') if isinstance(ie, dict) else None
            w.writerow(one_line(dict(benchmark=case, reference_id=a['id'], reference_file=f'reference-sets-v3/{case}.json',
                                     independent_reference_review='pending',
                                     raw_evidence_coverage=raw['label'] if raw else 'unassessed', raw_source_paths_and_locators=locs(raw),
                                     consolidation_evidence_coverage=con['label'] if con else ('unassessed' if case in CONSOLIDATION_CASES else 'not_applicable'),
                                     consolidation_source_paths_and_locators=locs(con),
                                     reviewer=('Claude subagent (AI), 2026-10-22' if ie.get('labelled_by') == LABELLED_BY else 'Claude (adjudication follow-up), 2026-10-23') if raw else '',
                                     rationale=' | '.join(x for x in ((raw or {}).get('rationale', ''), (con or {}).get('rationale', '')) if x))))


def main():
    os.makedirs(OUT, exist_ok=True)
    all_atoms, all_rows, summary, problems = [], [], {}, []
    used_pr = collections.Counter()
    for case, cfg in CASES.items():
        rows, atoms, v1_rows, v2_rows = build_case(case, cfg)
        problems += [f'{case}: {e}' for e in validate(case, rows, atoms, v1_rows, v2_rows)]
        for a in atoms:
            for p in a['provenance']['pr45_ids']:
                used_pr[p] += 1
        cnt = counts(rows, atoms)
        summary[case] = cnt
        out = {
         'schema_version': 'rq1-reference-set-3',
         'case': case,
         'reference_document': cfg['doc'],
         'base': cfg['base'],
         'status': 'merged reference set with AI input-evidence labels; provisional adjudication of the reviewed items (2026-10-23); not independently adjudicated as a whole',
         'built_from': {
           'v1': f'{case}/reference-requirements/{cfg["v1"]} (published identities kept)',
           'claude_v2': cfg['v1'].replace('.json', '-v2.json') + ' (Claude completion, 2026-10-22)' if v2_rows else 'none for this case',
           'pr45': 'benchmark-data/reference-audit-2026-10-22 (PR #45, commit 7fec154)'},
         'decisions': ['Mobility is scored at clause level (the PR #45 clauses, checked against NAPCORE Table 1).',
                       'Requirements that restate DCAT-AP are included and flagged (restates_dcat_ap); they may be left out at scoring time.']
                      + (['Geo restatement tags stay as coded: the INSPIRE and ISO obligation levels are kept as fields but are not part of each need, '
                          'since requirements are scored on the need and implementations may differ later (Junda, 2026-10-22).'] if case == 'geodcat' else []),
         'adjudication': ADJ_SUMMARY[case],
         'merge_rules': MERGE_RULES,
         'scoring': SCORING,
         'counts': cnt,
         'requirements': rows,
         'atoms': atoms,
        }
        os.makedirs(OUT, exist_ok=True)
        with open(f'{OUT}/{case}.json', 'w', encoding='utf-8') as f:
            json.dump(out, f, indent=1, ensure_ascii=False)
            f.write('\n')
        for a in atoms:
            all_atoms.append((case, a))
        for r in rows:
            all_rows.append((case, r))
    # every PR #45 item and Mobility clause used
    expected = set(pr_items) | {c['id'] for c in pr_clauses}
    problems += [f'PR #45 item {k} not used' for k in sorted(expected - set(used_pr))]
    problems += [f'PR #45 item {k} used {v} times' for k, v in used_pr.items() if v > 1 and k not in ('JC-006', 'MA-01-01')]

    # review table (atoms)
    cols = ['case', 'parent_id', 'id', 'statement', 'stratum', 'status_in_source', 'modality', 'relation_to_base', 'restates_dcat_ap',
            'reuse_or_alignment_rule', 'scored_by_default', 'applicability', 'source_locator', 'anchor_quote', 'anchor_check',
            'found_by', 'pr45_ids', 'claude_v2_rows', 'overlaps', 'merged_into', 'umbrella_of', 'adjudication', 'source_flags', 'notes', 'your_decision', 'your_note']
    with open(f'{OUT}/atoms-review.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for case, a in all_atoms:
            w.writerow(one_line(dict(case=case, parent_id=a['parent_id'], id=a['id'], statement=a['statement'], stratum=a['stratum'],
                            status_in_source=a['status_in_source'], modality=a['modality'], relation_to_base=a['relation_to_base'],
                            restates_dcat_ap=a['restates_dcat_ap'], reuse_or_alignment_rule=a['reuse_or_alignment_rule'],
                            scored_by_default=a['scored_by_default'], applicability=a['applicability'], source_locator=a['source_locator'],
                            anchor_quote=a['anchor_quote'] or '', anchor_check=a['anchor_check'], found_by=a['provenance']['found_by'],
                            pr45_ids=' '.join(a['provenance']['pr45_ids']), claude_v2_rows=' '.join(a['provenance']['claude_v2_rows']),
                            overlaps=' '.join(a['overlaps']), merged_into=a.get('merged_into') or '', umbrella_of=' '.join(a.get('umbrella_of', [])),
                            adjudication=' | '.join(f"{x['item']}: {x['change']}" for x in a.get('adjudication', [])), source_flags=' | '.join(a['source_flags']),
                            notes=' '.join(x for x in (a['notes'], a.get('relation_note', '')) if x), your_decision='', your_note='')))
    # coverage ledger: where every input ID went
    ledger = []
    for case, a in all_atoms:
        for p in a['provenance']['pr45_ids']:
            ledger.append(dict(input='PR #45', input_id=p, case=case, atom_id=a['id']))
        for r in a['provenance']['claude_v2_rows']:
            ledger.append(dict(input='Claude v2', input_id=r, case=case, atom_id=a['id']))
    for case, r in all_rows:
        for aid in r['atom_ids']:
            ledger.append(dict(input=f'row ({r["added_in"]})', input_id=r['id'], case=case, atom_id=aid))
    with open(f'{OUT}/coverage-ledger.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['input', 'input_id', 'case', 'atom_id'])
        w.writeheader()
        w.writerows(ledger)
    write_evidence_csv(all_atoms)
    with open(f'{OUT}/counts.json', 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=1)
    print('problems:', len(problems))
    for p in problems:
        print('  ', p)
    for case, s in summary.items():
        print(case, json.dumps(s))


if __name__ == '__main__':
    main()
