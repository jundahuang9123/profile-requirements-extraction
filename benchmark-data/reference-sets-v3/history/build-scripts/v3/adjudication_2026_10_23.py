"""Provisional adjudication of 23 October 2026, applied to the merged v3 sets.

Source: benchmark-data/reference-sets-v3/CODEX-REVIEW-2026-10-23.md (Junda's adjudication with
ChatGPT/Codex assistance, review of head 8e81e5b). Every change below names the review item it
implements. Changes that the register accepts as they are only get a log entry.
"""
import copy
import sys

sys.path.insert(0, '/home/claude/merge')
from integrate_labels import quote_ok

REVIEW = 'CODEX-REVIEW-2026-10-23.md'
DATE = '2026-10-23'
LABEL_WHO = ('Claude, adjudication follow-up 2026-10-23, from the staged inputs; not blind to the reference; '
             'quotes machine-checked; not human-reviewed')
EHDS = 'healthdcat/input-raw/ehds-proposal.html'
TWG = 'healthdcat/input-preconsolidation/twg-observations.json'
LABEL_CONTEXT = ('Elements of the EHDS data quality and utility label, which covers its elements where applicable '
                 '(D6.2 §5.2.8, p. 60, quoting EHDS Art. 56(3)).')
COHORT = ('In the staged 2022 proposal the label is optional for datasets made available through health data access bodies '
          '(Art. 56(1)) and mandatory for datasets collected with Union or national public funding (Art. 56(2)).')


def _src(path, locator, quote):
    assert quote_ok(path, quote), (path, quote)
    return dict(path=path, locator=locator, quote=quote, quote_check='verbatim_in_input_text')


def _block(label, sources, rationale):
    return dict(label=label, sources=sources, rationale=rationale,
                quotes_verified=any(s['quote_check'] == 'verbatim_in_input_text' for s in sources) if sources else label == 'unsupported')


def _log(a, item, change):
    a.setdefault('adjudication', []).append(dict(date=DATE, source=REVIEW, item=item, change=change))
    a['adjudication_status'] = 'provisional_adjudication_2026_10_23'


# ---- overlap review: every overlap pair, classified (equivalent, subsumes, related) with the decision taken
OVERLAP_REVIEW = {
 'mobilitydcat': [
  ('Req-17.1', 'Req-35.1', 'related', 'kept', 'A last-modified timestamp is not change and version tracking.'),
  ('Req-19.7', 'Req-24.1', 'equivalent', 'merged into Req-19.7', 'Both state the georeferencing (location referencing) method of the payload, map to mobilitydcatap:georeferencingMethod and share CMC-11 evidence.'),
  ('Req-23.1', 'Req-23.2', 'related', 'kept', 'Table 1 lists the area covered and the regions in which a dataset is valid separately.'),
  ('Req-28.4', 'Req-30.1', 'related', 'kept (register)', 'Model identity and precise model version can be independently useful.'),
 ],
 'healthdcat': [
  ('H-11.3', 'H-7.3', 'related', 'kept', 'Describing vocabularies publicly is not identifying coding systems by URI.'),
  ('H-11.4', 'H-7.3', 'related', 'kept', 'Describing classification schemes publicly is not identifying coding systems by URI.'),
  ('H-11.6', 'H-7.4', 'related', 'kept', 'Describing code lists publicly is not identifying code values by URI.'),
  ('H-13.1', 'H-17.5', 'related', 'kept', 'Re-use rights per distribution differ from the conditions for making data available.'),
  ('H-13.4', 'H-9.1', 'related', 'kept; unresolved source tension (register)', 'Mandatory dictionary, conditional wording and redacted fallback must not be flattened into one need.'),
  ('H-15.1', 'H-5.8', 'related', 'kept', 'Describing a quality annotation is not filtering by it.'),
  ('H-16.1', 'H-4.1', 'subsumes', 'umbrella H-4.1 not scored', 'H-4.1 lists purpose (why) among the free-text properties of D6.2 p. 32.'),
  ('H-17.1', 'H-26.1', 'related', 'kept', 'The source of a dataset is not its lineage.'),
  ('H-17.1', 'H-33.1', 'related', 'kept', 'The source of a dataset is not the datasets it was derived from.'),
  ('H-17.3', 'H-4.1', 'related', 'kept (H-4.1 not scored as an umbrella)', 'Main characteristics (EHDS Art. 55) are not one of the free-text properties H-4.1 lists.'),
  ('H-17.4', 'H-23.1', 'subsumes', 'kept', 'Personal or non-personal data is one aspect of the nature of the data; the rest is not decomposed.'),
  ('H-17.4', 'H-5.1', 'related', 'kept', 'The nature of the data is not the EHDS Art. 33 health category.'),
  ('H-17.5', 'H-19.1', 'related', 'kept', 'Conditions for making data available differ from the access-rights class.'),
  ('H-20.2', 'H-66.3', 'subsumes', 'kept', 'H-20.2 tightens the general access URL (H-66.3) by access rights.'),
  ('H-22.1', 'H-5.2', 'related', 'kept', 'Identifying the access body is not filtering by it.'),
  ('H-26.1', 'H-4.1', 'subsumes', 'umbrella H-4.1 not scored', 'H-4.1 lists provenance (how) among the free-text properties of D6.2 p. 32.'),
  ('H-26.1', 'H-46.4', 'related', 'kept', 'Lineage is not the label element on data modifications.'),
  ('H-28.1', 'H-4.1', 'subsumes', 'umbrella H-4.1 not scored', 'H-4.1 lists the publisher note (who) among the free-text properties of D6.2 p. 32.'),
  ('H-28.2', 'H-5.3', 'related', 'kept', 'Classifying the data holder is not filtering by publisher type.'),
  ('H-36.1', 'H-4.1', 'subsumes', 'umbrella H-4.1 not scored', 'H-4.1 lists population coverage (what) among the free-text properties of D6.2 p. 32.'),
  ('H-37.2', 'H-5.7', 'related', 'kept', 'Stating the number of individuals is not filtering by population size.'),
  ('H-4.2', 'H-7.1', 'related', 'kept', 'Queryable concepts and relationships differ in purpose from shared concepts with persistent identifiers.'),
  ('H-5.9', 'H-7.4', 'related', 'kept', 'Filtering by code values is not identifying them by URI.'),
 ],
 'statdcat': [
  ('S-1.1', 'S-15.1', 'related', 'kept', 'S-15.1 is a profile-level aim and not scored.'),
  ('S-15.1', 'S-2.1', 'related', 'kept', 'S-15.1 is a profile-level aim and not scored.'),
  ('S-2.1', 'S-6.1', 'subsumes', 'kept', 'Units are one example among the attributes of S-2.1; scaling factors and observation status are not separate atoms.'),
  ('S-20.1', 'S-3.1', 'related', 'kept', 'S-20.1 is deferred and not scored.'),
 ],
 'geodcat': [
  ('G-1.3', 'G-42.1', 'related', 'kept', 'Neither is scored (profile level).'),
  ('G-3.1', 'G-44.1', 'related', 'kept', 'Neither is scored (profile level).'),
  ('G-4.2', 'G-7.2', 'related', 'kept', 'Neither is scored (profile level).'),
  ('G-43.1', 'G-7.1', 'related', 'kept', 'Neither is scored (system level).'),
  ('G-44.1', 'G-5.1', 'related', 'kept', 'Neither is scored (profile level).'),
 ],
 'jrc-research': [
  ('JRC-1.1', 'JRC-7.1', 'related', 'kept', 'Identifying authors is not defining a set of agent roles.'),
  ('JRC-2.1', 'JRC-9.1', 'related', 'kept', 'JRC-9.1 asks for detailed provenance for reproducibility and usage tracking, beyond lineage.'),
  ('JRC-6.3', 'JRC-6.4', 'related', 'kept', 'Distinguishing primary from alternative identifiers is not the DOI rule for DataCite citations.'),
 ],
}

H46 = {
 'H-46.1': dict(statement='For the EHDS data quality and utility label, describe, when applicable, how representative the sampled population is.',
                anchor='when applicable, representativity of population sampled',
                applicability=LABEL_CONTEXT + ' Representativity only when applicable.'),
 'H-46.5': dict(statement='For the EHDS data quality and utility label, state the average time a natural person appears in the dataset.',
                anchor='average timeframe in which a natural person appears in a dataset',
                applicability=LABEL_CONTEXT + " The source's 'when applicable' may also govern this item."),
 'H-46.2': dict(statement='For the EHDS data quality and utility label, describe the maturity of the data quality management processes, including review and audit processes and the examination of biases.',
                anchor=None, applicability=LABEL_CONTEXT),
 'H-46.3': dict(statement='For the EHDS data quality and utility label, state the time between collecting the data and adding them to the dataset.',
                anchor='time between the collection of the electronic health data and their addition to the dataset',
                applicability=LABEL_CONTEXT),
 'H-46.6': dict(statement='For the EHDS data quality and utility label, state the time to provide the data after a data access application is approved.',
                anchor='time to provide electronic health data following an electronic health data access application approval',
                applicability=LABEL_CONTEXT),
 'H-46.4': dict(statement='For the EHDS data quality and utility label, describe modifications of the data: merging and adding data to an existing dataset, including links with other datasets.',
                anchor=None, applicability=LABEL_CONTEXT),
}


def _h46_evidence():
    s56_1 = _src(EHDS, 'Article 56(1)', 'Datasets made available through health data access bodies may have a Union data quality and utility label provided by the data holders.')
    s56_2 = _src(EHDS, 'Article 56(2)', 'Datasets with electronic health data collected and processed with the support of Union or national public funding shall have a data quality and utility label')
    twg8 = _src(TWG, 'TWG-8', 'Describe provenance, population and collection purpose in metadata that can support AI-assisted discovery.')
    twg7 = _src(TWG, 'TWG-7', 'Provide descriptive dataset metrics.')
    return {
     'H-46.1': dict(raw=_block('supported', [_src(EHDS, 'Article 56(3)(d)', 'representativity of population sampled'), s56_1, s56_2],
                                'The proposal lists representativity of the sampled population as a label element (Art. 56(3)(d)). ' + COHORT),
                    consolidation=_block('partial', [twg8], 'TWG-8 asks to describe the population; its representativity is not named.')),
     'H-46.5': dict(raw=_block('supported', [_src(EHDS, 'Article 56(3)(d)', 'average timeframe in which a natural person appears in a dataset'), s56_1, s56_2],
                                'The proposal lists the average timeframe a natural person appears as a label element (Art. 56(3)(d)). ' + COHORT),
                    consolidation=_block('partial', [twg7], 'TWG-7 asks for descriptive dataset metrics; the average timeframe is not named.')),
     'H-46.3': dict(raw=_block('supported', [_src(EHDS, 'Article 56(3)(e)', 'time between the collection of the electronic health data and their addition to the dataset'), s56_1, s56_2],
                                'The proposal lists the time between collection and addition to the dataset as a label element (Art. 56(3)(e)). ' + COHORT),
                    consolidation=_block('unsupported', [], 'No TWG observation mentions the time between collection and addition to the dataset.')),
     'H-46.6': dict(raw=_block('supported', [_src(EHDS, 'Article 56(3)(e)', 'time to provide electronic health data following electronic health data access application approval'), s56_1, s56_2],
                                'The proposal lists the time to provide data after an access application is approved as a label element (Art. 56(3)(e)). ' + COHORT),
                    consolidation=_block('unsupported', [], 'No TWG observation mentions provision times after approval.')),
    }


DOWNGRADES = {  # P1: raw "supported" overstates the evidence for the full requirement
 'H-1.1': ('P1 (H-1.1)', 'W3C DCAT relies on persistent HTTP URIs and recommends global identifiers, and DCAT-AP has an optional (0..n) dataset identifier. '
           'This supports identifier practice, not a mandatory persistent, dereferenceable identifier for every metadata record.'),
 'H-29.1': ('P1 (H-29.1)', 'M6.1 selects health datasets on data.europa.eu by the HEAL theme and DCAT-AP mandates the theme vocabulary for dcat:theme. '
            'A query that finds HEAL-labelled datasets does not require every record in an access-body catalogue to carry HEAL.'),
 'H-22.1': ('register (H-22.1)', 'The EHDS proposal makes a health data access body competent for access decisions and lets applicants identify the bodies concerned. '
            'It does not require a metadata field naming the access body for every personal or non-public dataset.'),
}

ACCEPTED = {
 'healthdcat': {'H-3.1': 'accepted: source correction (holder actor, annual cadence, accuracy/currency)',
                'H-3.2': 'accepted: retained as proposed/conditional',
                'H-10.1': 'accepted: locator correction (§5.2.6, pp. 43-44)',
                'H-37.2': 'accepted: recovered content (number of unique individuals)',
                'H-40.1': 'accepted: conditional form (datasets with a deletion deadline)',
                'H-9.1': 'unresolved source tension with H-13.4; left as recorded in source_flags',
                'H-13.4': 'unresolved source tension with H-9.1; left as recorded in source_flags'},
 'jrc-research': {'JRC-8.2': 'accepted: restored capability (interface and query-parameter description)'},
 'statdcat': {'S-19.1': 'accepted: deferred, excluded from default scoring', 'S-20.1': 'accepted: deferred, excluded from default scoring',
              'S-21.1': 'accepted: deferred, excluded from default scoring'},
 'mobilitydcat': {'Req-28.4': 'accepted: distinction from Req-30.1 retained', 'Req-30.1': 'accepted: distinction from Req-28.4 retained'},
}

CASE_NOTES = {
 'geodcat': ['Geo M/C/O scoring choice left unresolved as a declared scope choice (register): need-level scoring is kept distinct from obligation-sensitive scoring; INSPIRE/ISO conditions stay in the source fields.'],
}


def scored(a):
    return (a['stratum'] == 'content' and a['status_in_source'] != 'deferred'
            and not a.get('merged_into') and not a.get('umbrella_of'))


def apply(case, rows, atoms):
    """Apply the adjudication in place; return the case-level summary."""
    idx = {a['id']: a for a in atoms}
    summary = []

    if case == 'mobilitydcat':
        dup, can = idx['Req-24.1'], idx['Req-19.7']
        dup['merged_into'] = 'Req-19.7'
        dup['notes'] = (dup['notes'] + ' ' if dup['notes'] else '') + (
            'Merged for scoring into Req-19.7 (same need). Req-24 also names services; no residual service atom is isolated, '
            'because no separate source passage or property supports one.')
        can['merged_from'] = ['Req-24.1']
        can['scoring_unit_rows'] = ['Req-19', 'Req-24']
        _log(dup, 'P1 overlap (Req-19.7 / Req-24.1)', 'merged into Req-19.7; not scored by default')
        _log(can, 'P1 overlap (Req-19.7 / Req-24.1)', 'canonical scoring unit for Req-19 and Req-24')
        summary.append('Req-24.1 merged into Req-19.7 for scoring (P1); both rows kept as provenance.')

    if case == 'healthdcat':
        for aid, (item, why) in DOWNGRADES.items():
            a = idx[aid]
            b = a['input_evidence']['raw']
            b['label_before_adjudication'] = b['label']
            b['label'] = 'partial'
            b['rationale'] = why + ' (adjudication 2026-10-23)'
            _log(a, item, 'raw evidence label supported -> partial')
        summary.append('Raw evidence labels of H-1.1, H-29.1 and H-22.1 changed from supported to partial (P1, register).')
        ev = _h46_evidence()
        out = []
        for a in atoms:
            out.append(a)
            if a['id'] in ('H-46.1', 'H-46.3'):
                child_id = {'H-46.1': 'H-46.5', 'H-46.3': 'H-46.6'}[a['id']]
                child = copy.deepcopy(a)
                child['id'] = child_id
                child['split_from'] = a['id']
                child.pop('adjudication', None)
                out.append(child)
        atoms[:] = out
        idx = {a['id']: a for a in atoms}
        for aid, spec in H46.items():
            a = idx[aid]
            if a['statement'] != spec['statement']:
                a['statement_before_adjudication'] = idx[aid]['statement'] if aid not in ('H-46.5', 'H-46.6') else None
                a['statement'] = spec['statement']
            a['applicability'] = spec['applicability']
            if spec['anchor']:
                a['anchor_quote'] = spec['anchor']
                a['anchor_page'] = 60
                a['anchor_check'] = 'verbatim_in_source_text'
            if aid in ev:
                a['input_evidence'] = dict(raw=ev[aid]['raw'], consolidation=ev[aid]['consolidation'], labelled_by=LABEL_WHO, human_review='pending')
            item = 'P2 (H-46.1 / H-46.3)'
            if aid in ('H-46.5', 'H-46.6'):
                _log(a, item, f"split from {a['split_from']}; label context and applicability added; evidence relabelled")
            elif aid in ('H-46.1', 'H-46.3'):
                _log(a, item, 'split (second child ' + {'H-46.1': 'H-46.5', 'H-46.3': 'H-46.6'}[aid] + '); label context and applicability added; evidence relabelled')
            else:
                _log(a, item, 'label context and applicability added (same source passage)')
        for k in ('H-46.5', 'H-46.6'):
            idx[k].pop('statement_before_adjudication', None)
        summary.append('H-46.1 and H-46.3 split into H-46.1/H-46.5 and H-46.3/H-46.6; all H-46 atoms state the quality-label context and its applicability (P2).')
        u = idx['H-4.1']
        u['umbrella_of'] = ['H-66.2', 'H-36.1', 'H-16.1', 'H-26.1', 'H-28.1']
        u['notes'] = (u['notes'] + ' ' if u['notes'] else '') + (
            'Umbrella of the free-text properties D6.2 p. 32 lists: description (H-66.2), population coverage, what (H-36.1), '
            'purpose, why (H-16.1), provenance, how (H-26.1), publisher note, who (H-28.1). Not scored by default, so it does not compete with its components.')
        _log(u, 'P1 overlap review (umbrella rule)', 'umbrella of H-66.2, H-36.1, H-16.1, H-26.1, H-28.1; not scored by default')
        summary.append('H-4.1 is an umbrella of five separately scored free-text needs and is no longer scored by default (overlap review).')

    if case == 'jrc-research':
        a = idx['JRC-6.4']
        a['status_in_source_before_adjudication'] = a['status_in_source']
        a['status_in_source'] = 'requirement'
        a['applicability'] = 'Conditional: applies when DataCite citations are generated (DataCite requires the dataset identifier to be a DOI).'
        _log(a, 'register (JRC-6.4)', 'status open_issue -> requirement, with its condition in applicability')
        a = idx['JRC-10.1']
        a['anchor_quote'] = 'Modelling and using data quality assessments'
        a['anchor_check'] = 'from_web_fetch_not_verified_locally'
        _log(a, 'P2 (JRC-10.1 / JC-006)', 'anchor added (section heading in "Additional requirements")')
        new = copy.deepcopy(idx['JRC-10.1'])
        new.update(id='JRC-10.3', statement='Describe quality assessments of the metadata of a dataset.',
                   anchor_quote='This is not limited to data, but concerns metadata as well',
                   anchor_check='from_web_fetch_not_verified_locally')
        new['provenance'] = dict(new['provenance'], added_in_adjudication=True, found_by='restored in adjudication (JC-006)')
        new['adjudication'] = []
        new['input_evidence'] = dict(
            raw=_block('unsupported', [], 'No staged input addresses the quality of metadata; the JRC policy objective "Access to quality data" concerns the data.'),
            consolidation=None, labelled_by=LABEL_WHO, human_review='pending')
        _log(new, 'P2 (JRC-10.1 / JC-006)', 'restored metadata-quality capability (under investigation)')
        pos = atoms.index(idx['JRC-10.2']) + 1
        atoms.insert(pos, new)
        row = next(r for r in rows if r['id'] == 'JRC-10')
        row['statement_before_adjudication'] = row['statement']
        row['statement'] = "Describe data and metadata quality assessments and include users' feedback on the data."
        summary.append('JRC-6.4 is a conditional requirement; JRC-10.1 has its anchor; JRC-10.3 restores metadata-quality assessment (P2, register).')
        idx = {a['id']: a for a in atoms}

    for aid, what in ACCEPTED.get(case, {}).items():
        _log(idx[aid], 'register', what)
    review = OVERLAP_REVIEW.get(case, [])
    pairs = {tuple(sorted((a['id'], o))) for a in atoms for o in a['overlaps']}
    listed = {tuple(sorted((x, y))) for x, y, *_ in review}
    assert pairs == listed, (case, sorted(pairs ^ listed))
    for x, y, rel, decision, why in review:
        for me, other in ((x, y), (y, x)):
            r = rel
            if rel == 'subsumes':
                r = 'subsumes' if me == x else 'subsumed_by'
            idx[me].setdefault('overlap_review', []).append(dict(atom=other, relation=r, decision=decision, rationale=why))
    for a in atoms:
        a['scored_by_default'] = scored(a)
    summary.append(f'Overlap review: {len(review)} pairs classified ({sum(r[2] == "equivalent" for r in review)} equivalent, '
                   f'{sum(r[2] == "subsumes" for r in review)} subsumption, {sum(r[2] == "related" for r in review)} related).')
    summary += CASE_NOTES.get(case, [])
    return dict(date=DATE, source=f'reference-sets-v3/{REVIEW}', by='Junda, provisional adjudication with ChatGPT/Codex assistance; applied by Claude',
                status='provisional; not an independent human adjudication of the whole set', changes=summary)
