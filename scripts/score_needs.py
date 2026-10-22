#!/usr/bin/env python3
"""Read-only scores for the needs of a saved RQ1 run (rq1-need-scores-v2).

Two scores per active need, and needs ranked by F, then S:
- F, fidelity to the source: how close the need stays to what its sources say, the mean of the criteria
  that can be judged for it (F1 to F5);
- S, specificity: whether the need names a concrete information item rather than a vague topic.
R1 to R3 (serves find/access, worded as a user need, catalogue level) are reported as flags, not as a
score: in F/A runs the workflow has already filtered on them. A criterion that cannot be judged is blank
and left out of the mean. The run is read with GET requests only, or from a saved JSON file. No model
calls, no reference rows, nothing written to the run.
Spec: project doc claude/rq1-scorer-spec.md (22 Oct 2026; v2 after Junda's answers, 20:44)."""
import argparse
import csv
import json
import re
import statistics
import urllib.request
from pathlib import Path

VERSION = 'rq1-need-scores-v2'
# The fields read (see trimmed()): of the run; of each active need, with the parts of its nested fields;
# and of the needs and proposals it descends from.
RUN_FIELDS = ('run_id', 'status', 'active_revision_ids', 'requirements')
RECORD_FIELDS = ('revision_id', 'requirement_id', 'need_statement', 'normalized_statement', 'raw_statement',
                 'need_condition', 'scope', 'parent_revision_ids', 'contributing_roles', 'evidence_links',
                 'qualification', 'fa_scope', 'profile_scope', 'unbacked_obligation', 'processing_flags',
                 'base_relation', 'need_class', 'lifecycle_state')
NESTED_FIELDS = {'evidence_links': ('evidence_id', 'quote', 'relation'), 'qualification': ('support',),
                 'base_relation': ('verdict',),
                 'fa_scope': ('support', 'serves', 'nature', 'record_resource', 'catalogue_level', 'status'),
                 'profile_scope': ('support', 'serves', 'nature', 'record_resource', 'catalogue_level', 'status')}
LINEAGE_FIELDS = ('revision_id', 'raw_statement', 'parent_revision_ids', 'contributing_roles')
# Roles that write needs from other needs, not from the sources.
MEDIATION_ROLES = {'evidence_mediator', 'need_consolidation', 'mediator'}
SUPPORT = {'explicit': 1.0, 'inferred': 0.5, 'supported_inference': 0.5, 'uncertain': 0.25, 'disputed': 0.25,
           'unsupported': 0.0, 'contradicted': 0.0}
CATALOGUED = {'catalogue', 'dataset', 'distribution', 'data_service', 'other'}
PLACEHOLDER_SCOPE = 'unspecified'

STOP = set('''a an the and or but nor of to in on at by for with from as into onto over under about than then
that this these those which who whom whose what when where why how whether if is are was were be been being am
do does did has have had having can could may might must shall should will would it its they them their there
here such each every any all some no not only also either users user'''.split())
# S: words that name no particular information item, and the resources a need is about (neither way).
VAGUE = set('''metadata information info detail details aspect aspects element elements characteristic characteristics
feature features content contents thing things item items issue issues topic topics matter matters stuff fact facts
general generic various relevant related other certain appropriate additional further overall useful important
necessary available associated corresponding respective particular given existing possible different several many
multiple more most less etc kind kinds sort sorts way ways'''.split())
RESOURCES = set('''data dataset datasets distribution distributions catalogue catalogues catalog catalogs service services
resource resources record records'''.split())
ACTOR = (r'^\s*(?:(?:the|a|an|data|catalogue|catalog|end|potential)\s+)*'
         r'(?:users?|consumers?|publishers?|providers?|researchers?|reusers?|people|stakeholders?|readers?|analysts?)\s+')
# "Users can know ..." and the like: the frame the writer puts around a need.
FRAME = re.compile(ACTOR + r'(?:can|could|are able to|is able to|need to|want to|may)\s+'
    r'(?:(?:know|find|identify|obtain|see|determine|understand|learn|discover|locate|retrieve|access|tell|check|get|'
    r'judge|assess|compare|filter|search|read|view|recognise|recognize)\b(?:\s+(?:out|for|about|whether|if|which|what|'
    r'how|who|where|when))?)?', re.I)
USER_NEED = re.compile(ACTOR + r'(?:can|could|are able to|is able to)\b', re.I)
OBLIGATION = re.compile(r'\b(?:must|shall|should|obliges?|obliged)\b', re.I)
ABOUT_A_DOCUMENT = re.compile(r'^\s*(?:the|this|these)\s+(?:[\w-]+\s+){0,2}?(?:policy|policies|document|regulation|'
    r'directive|specification|standard|guidelines?|framework|decision|principles?|law|act|agreement|rules?|report)\b', re.I)

# Copied from workflow/needs.py (rq1-need-statement-v3) so that a later pipeline change cannot move the
# scores: the writer's conservative condition finder and the lexical terms of a condition.
_KNOWING = re.compile(r'\b(?:tell|see|know|check|find(?:\s+out)?|learn|determine|show|indicate|state|record|'
                      r'describe|specify|document|understand|judge)\s*(?:(?:clearly|easily|directly|exactly)\s*)?$', re.I)
_CONDITION_STOP = set('a an the if when where applicable provided that only for only when must shall should may can has '
                      'have is are be being to of for with in on as by and or this that which whose'.split())


def conditions(text):
    found = []
    for match in re.finditer(r'\b(?:if|when|unless|where applicable|provided that|only (?:for|when))\b[^.;]*', text, re.I):
        marker = match.group(0).split()[0].lower()
        if marker in {'if', 'when'} and _KNOWING.search(text[:match.start()]):
            continue
        clause = match.group(0)
        if marker in {'if', 'when', 'unless'} and re.search(r'(?:^|[.!?])\s*$', text[:match.start()]):
            clause = clause.split(',', 1)[0]
        found.append(clause.strip().rstrip('.'))
    return found


def condition_terms(text):
    terms = set(re.findall(r'[a-z0-9]+', (text or '').casefold())) - _CONDITION_STOP
    if terms & {'license', 'licence'}:
        terms |= {'license', 'licence'}
    return terms


def words(text):
    return re.findall(r'[a-z0-9]+', (text or '').casefold())


def stem(word):
    """Fold plural and verb endings the same way on both sides; not a linguistic stemmer."""
    for suffix, keep, replace in (('ies', 4, 'y'), ('sses', 5, 'ss'), ('ches', 5, 'ch'), ('shes', 5, 'sh'),
                                  ('xes', 4, 'x'), ('ing', 6, ''), ('ed', 5, ''), ('s', 4, '')):
        if word.endswith(suffix) and len(word) >= keep and not (suffix == 's' and word.endswith('ss')):
            return word[:len(word) - len(suffix)] + replace
    return word


VAGUE_STEMS = {stem(w) for w in VAGUE}
RESOURCE_STEMS = {stem(w) for w in RESOURCES}


def content_words(statement):
    rest = FRAME.sub('', statement or '', count=1)
    return [w for w in words(rest) if w not in STOP]


def edit_distance(a, b):
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def diminishing(count):
    """Each further distinct support adds half as much as the one before: 0, 0.5, 0.75, 0.875, ..."""
    return 1 - 0.5 ** count


def statement(record):
    return record.get('need_statement') or record.get('normalized_statement') or ''


def supporting_links(record):
    return [l for l in record.get('evidence_links') or [] if l.get('relation', 'supports') == 'supports']


def supporting_quotes(record):
    return [l.get('quote') or '' for l in supporting_links(record)]


def extracted_ancestors(record, by_id):
    """The first extracted statements behind a need: its ancestors without parents, written by a
    source-reading role. Returns (ancestors, longest path to one)."""
    found, depth, stack, seen = {}, 0, [(p, 1) for p in record.get('parent_revision_ids') or []], set()
    while stack:
        identifier, level = stack.pop()
        if (identifier, level) in seen or identifier not in by_id:
            continue
        seen.add((identifier, level))
        parent = by_id[identifier]
        if parent.get('parent_revision_ids'):
            stack.extend((p, level + 1) for p in parent['parent_revision_ids'])
        elif set(parent.get('contributing_roles') or []) - MEDIATION_ROLES:
            found[identifier] = parent
            depth = max(depth, level)
    return list(found.values()), depth


def judged_scope(record):
    """The find/access judgement: the F/A scope check, else the D5 profile-scope judge."""
    for key in ('fa_scope', 'profile_scope'):
        value = record.get(key) or {}
        if value.get('serves') or value.get('nature'):
            return value
    return {}


def criteria(record, by_id):
    text = statement(record)
    quotes = supporting_quotes(record)
    qualification = record.get('qualification') or {}
    support = qualification.get('support') or (record.get('fa_scope') or {}).get('support')
    f1 = SUPPORT.get(support, 0.0)

    content = content_words(text)
    quoted = {stem(w) for q in quotes for w in words(q)}
    f2 = (sum(stem(w) in quoted for w in content) / len(content)) if content else None

    ancestors, depth = extracted_ancestors(record, by_id)
    if ancestors:
        mine = words(text)
        f3 = 1 - min(edit_distance(mine, words(a.get('raw_statement'))) / max(len(mine), len(words(a.get('raw_statement'))), 1)
                     for a in ancestors)
    else:
        f3 = None

    quote_terms = condition_terms(' '.join(quotes))
    scope = record.get('scope') or ''
    stated = [record.get('need_condition') or '', *conditions(text),
              '' if scope.strip().casefold() == PLACEHOLDER_SCOPE else scope]
    added = []
    if record.get('unbacked_obligation'):
        added.append('obligation')
    if any(value.strip() and not condition_terms(value) <= quote_terms for value in stated):
        added.append('condition_or_scope')
    f4 = 1 - 0.5 * len(added)

    # Corroboration (Junda, 20:44: count it, but repeats add less): distinct quoted passages and distinct
    # source-reading roles, each further one adding half as much as the one before.
    passages = len({' '.join(q.casefold().split()) for q in quotes if q.strip()})
    roles = len(set(record.get('contributing_roles') or []) - MEDIATION_ROLES)
    f5 = (diminishing(passages) + diminishing(roles)) / 2

    named = [stem(w) for w in content if stem(w) not in RESOURCE_STEMS]
    vague = sum(w in VAGUE_STEMS for w in named)
    s = (len(named) - vague) / len(named) if named else 0.0

    judged = judged_scope(record)
    serves, nature = judged.get('serves'), judged.get('nature')
    if nature in {'background', 'implementation_detail'} or serves == 'neither':
        r1 = 0.0
    elif nature == 'operational_obligation':
        r1 = 0.5
    elif serves in {'find', 'access', 'both'} and nature in {None, 'information_requirement'}:
        r1 = 1.0
    else:
        r1 = None
    if OBLIGATION.search(text) or ABOUT_A_DOCUMENT.search(text):
        r2 = 0.0
    elif USER_NEED.search(text):
        r2 = 1.0
    else:
        r2 = 0.5
    resource = (record.get('profile_scope') or {}).get('record_resource')
    if resource is None:
        r3 = None
    elif resource in CATALOGUED:
        r3 = 1.0 if (record.get('profile_scope') or {}).get('catalogue_level', True) else 0.5
    else:
        r3 = 0.0
    requirement_flags = [name for name, on in (('rule_or_policy_wording', r2 == 0.0), ('unclear_wording', r2 == 0.5),
        ('operational_obligation', r1 == 0.5), ('not_find_or_access', r1 == 0.0), ('not_catalogue_level', r3 == 0.0),
        ('part_of_a_resource', r3 == 0.5)) if on]

    flags = record.get('processing_flags') or []
    parents = record.get('parent_revision_ids') or []
    origin = ('discussion_added' if not parents and not ancestors else
              'discussion_revised' if 'mediated_machine_proposal' in flags else 'consolidated')
    return {'F1': f1, 'F2': f2, 'F3': f3, 'F4': f4, 'F5': f5, 'S': s, 'R1': r1, 'R2': r2, 'R3': r3,
            'requirement_flags': ', '.join(requirement_flags),
            'support_from': 'qualification' if qualification.get('support') else 'fa_scope' if support else '',
            'added': ', '.join(added), 'vague_words': vague, 'origin': origin, 'rewording_steps': depth,
            'extracted_proposals': len(ancestors), 'passages': passages,
            'evidence_units': len({l.get('evidence_id') for l in supporting_links(record)}), 'source_roles': roles}


def mean(values):
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


def score_run(run):
    """Rows of the active needs, ranked by F, then S."""
    by_id = {r['revision_id']: r for r in run['requirements']}
    rows = []
    for identifier in run.get('active_revision_ids') or []:
        record = by_id.get(identifier)
        if not record:
            continue
        c = criteria(record, by_id)
        flags = record.get('processing_flags') or []
        rows.append({'rank': None, 'revision_id': identifier, 'requirement_id': record.get('requirement_id', ''),
                     'statement': statement(record), 'F': mean([c['F1'], c['F2'], c['F3'], c['F4'], c['F5']]), **c,
                     'covered_by_base': 'covered_by_base' in flags,
                     'base_relation': (record.get('base_relation') or {}).get('verdict', ''),
                     'need_class': record.get('need_class') or '', 'flags': ', '.join(flags)})
    rows.sort(key=lambda r: (-r['F'], -r['S'], r['revision_id']))
    for position, row in enumerate(rows, 1):
        row['rank'] = position
    return rows


def _pick(value, keys):
    return {k: value[k] for k in keys if k in value}


def trimmed(run):
    """The part of a run the scorer reads; a run and its trimmed copy score the same."""
    by_id = {r['revision_id']: r for r in run['requirements']}
    active = set(run.get('active_revision_ids') or [])
    ancestors, stack = set(), [p for i in active for p in (by_id.get(i) or {}).get('parent_revision_ids') or []]
    while stack:
        identifier = stack.pop()
        if identifier in ancestors or identifier not in by_id:
            continue
        ancestors.add(identifier)
        stack.extend(by_id[identifier].get('parent_revision_ids') or [])
    records = []
    for record in run['requirements']:
        if record['revision_id'] in active:
            kept = _pick(record, RECORD_FIELDS)
            for key, keys in NESTED_FIELDS.items():
                if isinstance(kept.get(key), list):
                    kept[key] = [_pick(item, keys) for item in kept[key]]
                elif isinstance(kept.get(key), dict):
                    kept[key] = _pick(kept[key], keys)
            records.append(kept)
        elif record['revision_id'] in ancestors:
            records.append(_pick(record, LINEAGE_FIELDS))
    return {**_pick(run, RUN_FIELDS), 'requirements': records}


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    result = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            result[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return result


def spearman(left, right):
    if len(left) < 3:
        return None
    a, b = ranks(left), ranks(right)
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return num / den if den else None


def same_statement(text):
    return ' '.join(text.casefold().split())


def compare(rows, other_rows):
    other = {same_statement(r['statement']): r for r in other_rows}
    pairs = [(r, other[same_statement(r['statement'])]) for r in rows if same_statement(r['statement']) in other]
    result = {'matched': len(pairs), 'needs': len(rows), 'other_needs': len(other_rows)}
    for key in ('F', 'S'):
        kept = [(a[key], b[key]) for a, b in pairs if a[key] is not None and b[key] is not None]
        result['spearman_' + key] = spearman([a for a, _ in kept], [b for _, b in kept])
    return result


def fmt(value):
    return '' if value is None else f'{value:.2f}' if isinstance(value, float) else str(value)


def summary(run, rows, comparison=None, label=''):
    lines = [f'# Need scores · {label or run.get("run_id", "")}',
             f'Scorer `{VERSION}` · run `{run.get("run_id", "")}` · status {run.get("status", "")} · '
             f'{len(rows)} active needs, ranked by F, then S. Read-only: no model calls, no reference rows.',
             'F = mean of F1 support, F2 wording found in its quotes, F3 closeness to the first extracted '
             'statement, F4 nothing added beyond the quotes, F5 corroboration (distinct passages and source roles, '
             'repeats adding less). S = share of the words naming the need that are not vague. R1 serves '
             'find/access, R2 worded as a user need and R3 catalogue level are flags, not a score. Blank criteria '
             'are not judged for that need and are left out of the mean.', '', '## Criteria', '',
             '| Criterion | Judged | Mean | Median | Min | Max |', '|---|---|---|---|---|---|']
    for key in ('F', 'F1', 'F2', 'F3', 'F4', 'F5', 'S', 'R1', 'R2', 'R3'):
        values = [r[key] for r in rows if r[key] is not None]
        lines.append(f'| {key} | {len(values)} | ' + (' | '.join(fmt(v) for v in (
            statistics.fmean(values), statistics.median(values), min(values), max(values))) if values else '– | – | – | –') + ' |')
    lines += ['', '## By group', '', '| Group | Needs | Mean F | Mean S |', '|---|---|---|---|']
    groups = [('covered by the base', lambda r: r['covered_by_base']), ('not covered', lambda r: not r['covered_by_base']),
              *[(origin.replace('_', ' '), lambda r, o=origin: r['origin'] == o)
                for origin in ('consolidated', 'discussion_revised', 'discussion_added')]]
    for name, keep in groups:
        chosen = [r for r in rows if keep(r)]
        if chosen:
            lines.append(f'| {name} | {len(chosen)} | {fmt(mean([r["F"] for r in chosen]))} | {fmt(mean([r["S"] for r in chosen]))} |')
    for title, chosen in (('Highest ranked (F, then S)', rows[:10]), ('Lowest ranked', rows[::-1][:10]),
                          ('Least specific (S)', sorted(rows, key=lambda r: (r['S'], r['rank']))[:10])):
        lines += ['', f'## {title}', '', '| Rank | F | S | Need |', '|---|---|---|---|']
        lines += [f'| {r["rank"]} | {fmt(r["F"])} | {fmt(r["S"])} | {r["statement"]} |' for r in chosen]
    flagged = [r for r in rows if r['requirement_flags']]
    lines += ['', '## Requirement flags (R)', '']
    lines += [f'- {r["statement"]} — {r["requirement_flags"]}' for r in flagged] or ['- none']
    if comparison:
        lines += ['', '## Comparison', '',
                  f'{comparison["matched"]} of {comparison["needs"]} needs have the same statement in the other run '
                  f'({comparison["other_needs"]} needs). Rank correlation (Spearman) of their scores: '
                  f'F {fmt(comparison["spearman_F"])}, S {fmt(comparison["spearman_S"])}.']
    return '\n'.join(lines) + '\n'


def get(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return json.load(response)


def load(source, api):
    if Path(source).is_file():
        return json.loads(Path(source).read_text(encoding='utf-8'))
    if not api:
        raise SystemExit(f'{source} is not a file; give --api to read the run from the app.')
    return get(api.rstrip('/') + '/api/rq1/v2/runs/' + source + '?audit=false')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--run', required=True, help='Run ID (read from --api) or a saved run JSON file.')
    parser.add_argument('--api', help='Base URL of the app, for example http://127.0.0.1:8013. GET only.')
    parser.add_argument('--compare', help='A second run (ID or JSON file) to compare needs with the same statement.')
    parser.add_argument('--label', default='')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    run = load(args.run, args.api)
    rows = score_run(run)
    comparison = compare(rows, score_run(load(args.compare, args.api))) if args.compare else None
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    name = run.get('run_id') or Path(args.run).stem
    with (out / f'{name}-need-scores.csv').open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ['rank'])
        writer.writeheader()
        writer.writerows({k: fmt(v) if isinstance(v, float) or v is None else v for k, v in row.items()} for row in rows)
    (out / f'{name}-need-scores.md').write_text(summary(run, rows, comparison, args.label), encoding='utf-8')
    print(f'{len(rows)} needs scored; wrote {out / (name + "-need-scores.csv")} and .md')


if __name__ == '__main__':
    main()
