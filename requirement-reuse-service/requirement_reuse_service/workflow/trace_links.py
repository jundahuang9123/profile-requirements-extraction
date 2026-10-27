"""Links from a need's trace to the saved results it was built from (rq1-need-trace-v1).

Junda, 27 Oct: every trace entry should link to where it was traced from, opening the result file of the step that
made it with the traced part highlighted, instead of sending the reviewer back through the step pages.

Each step of a run saves a result file (the workbench's step download). A trace entry links to the file of the step
that made it and to the place in it: a JSON pointer (RFC 6901) to the row, and for a quotation the characters to mark
in its source document. Model calls and source documents are files of their own. When the step's file does not hold
the entry as the trace shows it (a revision the discussion wrote later), the link goes to the next later file that
does, ending at the current saved state.
"""
import re
from .need_trace import ROW_IDS, folded, result_ids

STAGE_LABELS = {'decomposition': '2 · Evidence units', 'elicitation': '3b · Candidate extraction',
                'verification': '5 · Original-source checks', 'consolidation': '6 · Grouped needs & scope',
                'base_review': '6a · Base review', 'deliberation': '7 · Discussion', 'adjudication': '8 · Human review'}
# Where a step that judges needs one by one keeps its rows in the step 6 file (need_steps), by trace step.
DECISION_ROWS = {'proposal_support': ('proposal_support', 'decisions', 'proposal_id'),
                 'classification': ('classification', 'decisions', 'need_id'),
                 'fa_test': ('profile_scope', 'decisions', 'need_id'),
                 'dataset_applicability': ('dataset_applicability', 'decisions', 'need_id')}
# A judgement kept on the need's record, by trace step: the record field, and the step files that can hold it, in order.
RECORD_FIELDS = {'source_check': (('verification',), ('verification', 'consolidation', 'deliberation', 'adjudication')),
                 'proposal_support': (('proposal_support',), ('consolidation', 'deliberation', 'adjudication')),
                 'proposal_support_confirmation': (('proposal_support', 'confirmation'), ('consolidation', 'deliberation', 'adjudication')),
                 'fa_test': (('fa_scope',), ('consolidation', 'deliberation', 'adjudication')),
                 'record_test': (('profile_scope',), ('consolidation', 'deliberation', 'adjudication')),
                 'fa_test_confirmation': (('fa_scope', 'confirmation'), ('consolidation', 'deliberation', 'adjudication')),
                 'record_test_confirmation': (('profile_scope', 'confirmation'), ('consolidation', 'deliberation', 'adjudication')),
                 'classification': (('base_gap',), ('consolidation', 'deliberation', 'adjudication')),
                 'assessment': (('qualification',), ('consolidation', 'base_review', 'deliberation', 'adjudication')),
                 'base_review': (('base_relation',), ('base_review', 'deliberation', 'adjudication')),
                 'base_review_check': (('base_relation', 'check'), ('base_review', 'deliberation', 'adjudication'))}


def stage_results(run, stage):
    """What the step download holds under 'results' (the snapshot, audit and catalogues it adds sit beside it)."""
    from .engine import STAGE_RESULT_FIELDS
    if stage not in STAGE_RESULT_FIELDS:
        raise ValueError('Unknown workflow step.')
    checkpoint = (run.get('stage_results') or {}).get(stage) if stage not in {'adjudication', 'baseline'} else None
    return dict(checkpoint) if checkpoint is not None else {key: run.get(key) for key in STAGE_RESULT_FIELDS[stage]}


def source_document(store, source_version_id):
    """A source's parsed text with its evidence units in reading order: the file a quotation links to."""
    source = store.get('source', source_version_id)
    units = sorted((u for u in store.list('evidence') if u['source_version_id'] == source_version_id),
                   key=lambda u: ((u.get('selector') or {}).get('start') is None, (u.get('selector') or {}).get('start') or 0,
                                  u['evidence_id']))
    text = source.get('representation') or ''
    same_text = lambda u: (u.get('selector') or {}).get('representation_hash') == source.get('representation_hash')
    return {'source_version_id': source_version_id, 'name': source.get('name'), 'artifact_kind': source.get('artifact_kind'),
            'source_role': source.get('source_role'), 'text': text,
            'units': {u['evidence_id']: {'kind': u['kind'], 'content': u['content'], 'selector': u.get('selector'),
                                         'structural_context': u.get('structural_context'),
                                         # Where the unit sits in the text; units of another representation have none.
                                         'span': [u['selector']['start'], u['selector']['end']]
                                         if same_text(u) and isinstance((u.get('selector') or {}).get('start'), int) else None}
                      for u in units}}


def pointer(*parts):
    return ''.join('/' + str(p).replace('~', '~0').replace('/', '~1') for p in parts)


def position(rows, test):
    return next((i for i, row in enumerate(rows or []) if isinstance(row, dict) and test(row)), None)


def last_position(rows, test):
    found = [i for i, row in enumerate(rows or []) if isinstance(row, dict) and test(row)]
    return found[-1] if found else None


def dig(value, path):
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def quote_span(content, quote, start=None):
    """Where a quotation sits in its unit's content: at its recorded offset, else found exactly or with its spacing
    folded (the source check accepts both)."""
    quote = quote or ''
    if not quote: return None
    if isinstance(start, int) and content[start:start + len(quote)] == quote: return [start, start + len(quote)]
    found = content.find(quote)
    if found >= 0: return [found, found + len(quote)]
    words = quote.split()
    match = re.search(r'\s+'.join(map(re.escape, words)), content) if words else None
    return [match.start(), match.end()] if match else None


def row_path(value, test, path=(), depth=0):
    """The path to the first object in a model output that is about the traced item."""
    if depth > 6: return None
    if isinstance(value, dict):
        if test(value): return path
        items = value.items()
    elif isinstance(value, list): items = enumerate(value)
    else: return None
    for key, item in items:
        found = row_path(item, test, (*path, key), depth + 1)
        if found is not None: return found
    return None


class Linker:
    """Builds the links of one run's traces; reads each step's results once."""

    def __init__(self, index):
        self.index, self.run = index, index.run
        self.run_id = self.run['run_id']
        self.cache = {}
        self.calls = {}  # call ID -> (run ID, call)
        for owner in reversed([self.run, *index.earlier_runs]):
            for call in owner.get('model_calls') or []:
                if call.get('call_id'): self.calls[call['call_id']] = (owner['run_id'], call)

    def results(self, stage):
        if stage not in self.cache:
            try: self.cache[stage] = stage_results(self.run, stage)
            except ValueError: self.cache[stage] = {}
        return self.cache[stage]

    def stage_link(self, stage, what, *path):
        return {'label': f'Step {STAGE_LABELS[stage]}: {what}', 'file': f'/runs/{self.run_id}/stages/{stage}',
                'pointer': pointer('results', *path)}

    def record_link(self, revision_id, field, stages, what):
        """The record's field in the first step file whose copy of the record says what the run says now."""
        current = dig(self.index.records.get(revision_id) or {}, field)
        fallback = None
        for stage in stages:
            rows = self.results(stage).get('requirements') or []
            at = position(rows, lambda r: r.get('revision_id') == revision_id)
            if at is None: continue
            link = self.stage_link(stage, what, 'requirements', at, *field)
            if dig(rows[at], field) == current: return link
            fallback = link
        return fallback

    def need_row(self, step, decision, row_id):
        """The row of a step that judges needs one by one, in the step 6 file."""
        if step == 'record_test':
            need_step, rows_key, field = 'profile_scope', 'record_decisions' if self.index.fa_run else 'decisions', 'need_id'
        elif step in DECISION_ROWS: need_step, rows_key, field = DECISION_ROWS[step]
        else: return None
        rows = (((self.results('consolidation').get('need_steps') or {}).get(need_step) or {}).get(rows_key)) or []
        said = folded(decision.get('reason'))
        at = last_position(rows, lambda r: r.get(field) == row_id and said and folded(r.get('rationale')) == said)
        if at is None: at = last_position(rows, lambda r: r.get(field) == row_id)
        if at is None: return None
        return self.stage_link('consolidation', f'{need_step} row', 'need_steps', need_step, rows_key, at)

    def call_links(self, call_ids, test):
        links = []
        for call_id in call_ids or []:
            owner, call = self.calls.get(call_id, (None, None))
            if not call: continue
            path = row_path(call.get('output'), test) if test else None
            links.append({'label': f"Model call {call_id[:8]} ({call.get('step')}, {call.get('model')})",
                          'file': f'/runs/{owner}/calls/{call_id}',
                          'pointer': pointer('output', *path) if path is not None else pointer('output') if call.get('output') is not None else ''})
        return links

    def source(self, entry):
        unit = self.index.unit(entry.get('evidence_id')) or {}
        if not unit: return []
        span = quote_span(unit.get('content') or '', entry.get('quote'), entry.get('quote_start'))
        return [{'label': f"Source: {entry.get('source') or entry.get('source_version_id')}",
                 'file': f"/sources/{unit['source_version_id']}/document", 'pointer': pointer('units', entry['evidence_id']),
                 'mark': entry.get('quote'), 'quote_span': span}]

    def origin(self, entry):
        links = []
        rows = self.results('elicitation').get('observations') or []
        at = position(rows, lambda o: o.get('observation_id') == entry['observation_id'])
        if at is not None: links.append(self.stage_link('elicitation', 'extracted observation', 'observations', at))
        role_runs = self.results('elicitation').get('role_runs') or []
        if isinstance(entry.get('role_run_index'), int) and entry['role_run_index'] < len(role_runs):
            links.append(self.stage_link('elicitation', "the agent's role run", 'role_runs', entry['role_run_index']))
        if at is None:
            # An observation ID no agent extracted: the discussion gave it to a revision it wrote (a split, for
            # instance); the outcome that wrote that revision is where it comes from.
            for revision, record in self.index.records.items():
                if entry['observation_id'] not in (record.get('observation_ids') or []): continue
                for case in self.index.cases.get(revision, []):
                    file = self.case_file(case['case_id'])
                    o = position(((file[1].get('mediation') or {}).get('outcomes') or []) if file else [],
                                 lambda x: revision in result_ids(x))
                    if o is not None: links.append(file[0](f'the outcome that wrote {revision}', 'mediation', 'outcomes', o))
                if links: break
        statement = folded(entry.get('statement'))
        links += self.call_links(entry.get('call_ids'), lambda row: bool(statement) and folded(row.get('statement')) == statement)
        return links

    def decision(self, entry, trace):
        step, revision = entry['step'], entry['revision_id']
        record = self.index.records.get(revision) or {}
        links = []
        if step == 'grouping':
            grouping = self.index.groupings.get(revision) or {}
            audit = ((self.results('consolidation').get('need_steps') or {}).get('grouping') or {}).get('audit') or []
            at = position(audit, lambda a: a.get('chunk_key') == grouping.get('chunk_key'))
            if at is not None:
                which = (audit[at].get('rationales') or [])
                sub = ('rationales', which.index(grouping['rationale'])) if grouping.get('rationale') in which else ()
                links.append(self.stage_link('consolidation', 'grouping', 'need_steps', 'grouping', 'audit', at, *sub))
        elif step == 'need_statement':
            events = ((self.results('consolidation').get('need_steps') or {}).get('need_statement') or {}).get('events') or []
            at = position(events, lambda e: revision in (e.get('outputs') or []))
            if at is None: at = position(events, lambda e: record.get('group_id') and e.get('group_id') == record.get('group_id'))
            if at is not None: links.append(self.stage_link('consolidation', 'need writing event', 'need_steps', 'need_statement', 'events', at))
        elif step == 'set_aside':
            aside = lambda a: a.get('revision_id') == revision and a.get('reason') == entry['decision']
            at = position(self.results('consolidation').get('set_aside_observations'), aside)
            if at is not None: links.append(self.stage_link('consolidation', 'set-aside', 'set_aside_observations', at))
            elif entry['decision'] == 'trace_incomplete' and ((self.run.get('stage_results') or {}).get('traceability') or {}).get('needs', {}).get(revision):
                links.append({'label': 'Traceability: the incomplete chain', 'file': f'/runs/{self.run_id}/traceability',
                              'pointer': pointer('needs', revision)})
            else:
                at = position(self.run.get('set_aside_observations'), aside)
                if at is not None: links.append({'label': 'Current saved run: set-aside', 'file': f'/runs/{self.run_id}?audit=false',
                                                 'pointer': pointer('set_aside_observations', at)})
        elif step == 'assessment':
            records = ((self.results('consolidation').get('need_steps') or {}).get('assessment') or {}).get('records') or []
            at = position(records, lambda r: r.get('revision_id') == revision and r.get('qualification') == record.get('qualification'))
            if at is not None: links.append(self.stage_link('consolidation', 'assessment', 'need_steps', 'assessment', 'records', at, 'qualification'))
        made_here = step in {'fa_test', 'record_test'} and any(revision in o['result_revision_ids'] for c in trace['discussion'] for o in c['outcomes'])
        if not links and not made_here and entry['decision'] != 'not_checked':
            row = self.need_row(step, entry, revision if step == 'proposal_support' else trace['requirement_id'])
            if row: links.append(row)
        if not links and step in RECORD_FIELDS:
            field, stages = RECORD_FIELDS[step]
            link = self.record_link(revision, field, stages, step.replace('_', ' ') + ' on the record')
            if link: links.append(link)
        # The model's row: by ID, else (rows under aliases) by the reason the decision keeps verbatim, else by the
        # statement the writer wrote.
        # statement the writer wrote; a grouping row names its members by their alias in the chunk (c1, c2, ...).
        ids = {revision, trace['requirement_id'], record.get('group_id')} - {None}
        if step == 'need_statement': ids |= set(trace['lineage'])
        reason, statement = folded(entry.get('reason')), folded(record.get('need_statement'))
        alias = self.alias(revision) if step == 'grouping' else None
        links += self.call_links(entry.get('call_ids'), lambda row: any(isinstance(row.get(f), str) and row[f] in ids
                                                                         for f in (*ROW_IDS, 'revision_id', 'item_id'))
                                 or (len(reason) >= 20 and folded(row.get('rationale')) == reason)
                                 or (step == 'need_statement' and bool(statement) and folded(row.get('statement')) == statement)
                                 or (alias is not None and alias in (row.get('member_ids') or [])))
        return links

    def alias(self, revision):
        chunk_key = (self.index.groupings.get(revision) or {}).get('chunk_key')
        chunk = next((c for c in (self.run.get('consolidation_chunks') or {}).values()
                      if isinstance(c, dict) and c.get('chunk_key') == chunk_key), None)
        members = (chunk or {}).get('revision_ids') or []
        return f'c{members.index(revision) + 1}' if revision in members else None

    def case_file(self, case_id):
        """The file holding a discussion case (the step 7 file, else the current saved run): a link maker and the case."""
        rows = self.results('deliberation').get('deliberations') or []
        at = position(rows, lambda c: c.get('case_id') == case_id)
        if at is not None:
            return (lambda what, *path: self.stage_link('deliberation', what, 'deliberations', at, *path)), rows[at]
        current = position(self.run.get('deliberations'), lambda c: c.get('case_id') == case_id)
        if current is None: return None
        return (lambda what, *path: {'label': f'Current saved run: {what}', 'file': f'/runs/{self.run_id}?audit=false',
                                     'pointer': pointer('deliberations', current, *path)}), self.run['deliberations'][current]

    def case(self, case):
        file = self.case_file(case['case_id'])
        if not file: return [], lambda outcome: []
        base, stored = file
        outcomes = ((stored.get('mediation') or {}).get('outcomes') or [])
        def outcome_links(outcome):
            o = position(outcomes, lambda x: x.get('action_id') == outcome['action_id'] and result_ids(x) == outcome['result_revision_ids'])
            if o is None: o = position(outcomes, lambda x: x.get('action_id') == outcome['action_id'])
            return [base(f"outcome {outcome['action_id']}", 'mediation', 'outcomes', o)] if o is not None else []
        return [base(f"case {case['case_id']}"), *self.call_links(case.get('call_ids'), None)], outcome_links

    def need(self, revision_id):
        stage = 'adjudication'
        rows = self.results(stage).get('requirements') or []
        at = position(rows, lambda r: r.get('revision_id') == revision_id)
        return [self.stage_link(stage, 'the need record', 'requirements', at)] if at is not None else []


def link_trace(index, trace, linker=None):
    """The trace with a list of links on every entry: the need, each quotation, each extracted observation, each
    decision and each discussion case and outcome."""
    linker = linker or Linker(index)
    trace = {**trace, 'links': linker.need(trace['revision_id'])}
    trace['sources'] = [{**s, 'links': linker.source(s)} for s in trace['sources']]
    trace['origin'] = [{**o, 'links': linker.origin(o)} for o in trace['origin']]
    trace['decisions'] = [{**d, 'links': linker.decision(d, trace)} for d in trace['decisions']]
    cases = []
    for case in trace['discussion']:
        links, outcome_links = linker.case(case)
        cases.append({**case, 'links': links, 'outcomes': [{**o, 'links': outcome_links(o)} for o in case['outcomes']]})
    trace['discussion'] = cases
    return trace
