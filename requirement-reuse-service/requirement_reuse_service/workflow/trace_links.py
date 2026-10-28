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


def reasons(output):
    """The reasons of an answer's rows, in order: what a saved answer and the call that gave it share."""
    rows = [r for v in (output.values() if isinstance(output, dict) else []) if isinstance(v, list) for r in v if isinstance(r, dict)]
    return tuple(folded(r.get('rationale')) for r in rows) if rows and all(r.get('rationale') for r in rows) else ()


def resolve(value, path):
    for key in path:
        if isinstance(value, dict) and key in value: value = value[key]
        elif isinstance(value, list) and isinstance(key, int) and key < len(value): value = value[key]
        else: return None
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
    """The path to the first object in a model output that passes the test."""
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
        # Base review shows the model aliases (N1, B1, E1) and saves its answer with the real IDs, in the same order:
        # the saved answer of a call says which of its rows is about which need.
        # A run saved before call IDs were recorded pairs each saved answer with the call whose rows give the same
        # reasons in the same order.
        self.translated, by_reasons = {}, {}
        for call_id, (_, call) in self.calls.items():
            if call.get('step') in {'base_review', 'base_review_check'} and reasons(call.get('output')):
                by_reasons.setdefault(reasons(call['output']), []).append(call_id)
        for entry in (self.run.get('stakeholder_audit') or {}).values():
            for attempt in (entry.get('attempts') or []) if isinstance(entry, dict) else []:
                answer = attempt.get('output') or attempt.get('parsed')
                if not isinstance(answer, dict): continue
                if attempt.get('call_ids'): self.translated[attempt['call_ids'][-1]] = answer
                elif len(by_reasons.get(reasons(answer), [])) == 1: self.translated[by_reasons[reasons(answer)][0]] = answer

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
        saved = self.run.get('stage_results') or {}
        for stage in stages:
            # A step that saved no result (base review when it did not run) would serve the current state under
            # its own name.
            if stage != 'adjudication' and stage not in saved: continue
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
        # A proposal the support check re-hashed (an obligation its quote does not state) keeps its proposal ID in
        # the row, with the new revision ID beside it.
        about = lambda r: r.get(field) == row_id or (step == 'proposal_support' and r.get('revision_id') == row_id)
        at = last_position(rows, lambda r: about(r) and said and folded(r.get('rationale')) == said)
        if at is None: at = last_position(rows, about)
        if at is None: return None
        return self.stage_link('consolidation', f'{need_step} row', 'need_steps', need_step, rows_key, at)

    def call_links(self, call_ids, tests=()):
        """Links to the calls, each at the output row about the traced item: the tests are tried in turn over the
        whole output, the most specific first, since rows of one batch often give the same reason."""
        links = []
        for call_id in call_ids or []:
            owner, call = self.calls.get(call_id, (None, None))
            if not call: continue
            path = None
            if call_id in self.translated:
                path = next((found for test in tests for found in [row_path(self.translated[call_id], test)] if found is not None), None)
                if path is not None and resolve(call.get('output'), path) is None: path = None
            if path is None:
                path = next((found for test in tests for found in [row_path(call.get('output'), test)] if found is not None), None)
            # A failed call (an answer that broke its contract) saves no output; the decision kept the valid rows.
            failed = ', failed, no answer saved' if call.get('output') is None else ''
            links.append({'label': f"Model call {call_id[:8]} ({call.get('step')}, {call.get('model')}{failed})",
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
        links += self.call_links(entry.get('call_ids'), [lambda row: bool(statement) and folded(row.get('statement')) == statement])
        return links

    def decision(self, entry, trace):
        step, revision = entry['step'], entry['revision_id']
        record = self.index.records.get(revision) or {}
        links = []
        if step == 'grouping':
            grouping = self.index.groupings.get(revision) or {}
            audit = ((self.results('consolidation').get('need_steps') or {}).get('grouping') or {}).get('audit') or []
            at = position(audit, lambda a: a.get('action') == 'grouping_chunk' and a.get('chunk_key') == grouping.get('chunk_key'))
            if at is not None:
                # The row keeps one rationale per group of the chunk's answer, in its order.
                group = self.group_index(revision)
                sub = ('rationales', group) if group is not None and group < len(audit[at].get('rationales') or []) else ()
                links.append(self.stage_link('consolidation', 'grouping', 'need_steps', 'grouping', 'audit', at, *sub))
        elif step == 'resource_guard':
            audit = ((self.results('consolidation').get('need_steps') or {}).get('grouping') or {}).get('audit') or []
            at = position(audit, lambda a: a.get('action') == 'kept_apart_by_resource' and revision in (a.get('inputs') or []))
            if at is not None: links.append(self.stage_link('consolidation', 'grouping kept apart by resource', 'need_steps', 'grouping', 'audit', at))
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
        # The model's row: by the decision's own revision, then its requirement ID, then its group (for the writer
        # also the members it wrote from), then (rows under aliases) the reason the decision keeps verbatim, then the
        # statement the writer wrote; a grouping row names its members by their alias in the chunk (c1, c2, ...).
        names = lambda wanted: lambda row: any(isinstance(row.get(f), str) and row[f] in wanted for f in (*ROW_IDS, 'revision_id', 'item_id'))
        reason, statement = folded(entry.get('reason')), folded(record.get('need_statement'))
        alias = self.alias(revision) if step == 'grouping' else None
        tests = ([lambda row: alias in (row.get('member_ids') or [])] if alias else []) + [
            names({revision}), names({record.get('requirement_id') or trace['requirement_id']} - {None}),
            names({record.get('group_id')} - {None}), *([names(set(trace['lineage']))] if step == 'need_statement' else []),
            lambda row: len(reason) >= 20 and folded(row.get('rationale')) == reason,
            *([lambda row: bool(statement) and folded(row.get('statement')) == statement] if step == 'need_statement' else [])]
        links += self.call_links(entry.get('call_ids'), tests)
        return links

    def chunk(self, revision):
        chunk_key = (self.index.groupings.get(revision) or {}).get('chunk_key')
        return next((c for c in (self.run.get('consolidation_chunks') or {}).values()
                     if isinstance(c, dict) and c.get('chunk_key') == chunk_key and c.get('block_key') == 'underlying_needs'), None)

    def alias(self, revision):
        members = (self.chunk(revision) or {}).get('revision_ids') or []
        return f'c{members.index(revision) + 1}' if revision in members else None

    def group_index(self, revision):
        alias = self.alias(revision)
        groups = ((self.chunk(revision) or {}).get('result') or {}).get('groups') or []
        return position(groups, lambda g: alias in (g.get('member_ids') or [])) if alias else None

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
        current = position(self.run.get('deliberations'), lambda c: c.get('case_id') == case['case_id'])
        def find(rows, outcome):
            o = position(rows, lambda x: x.get('action_id') == outcome['action_id'] and result_ids(x) == outcome['result_revision_ids'])
            return o if o is not None else position(rows, lambda x: x.get('action_id') == outcome['action_id'])
        def outcome_links(outcome):
            o = find(outcomes, outcome)
            if o is not None: return [base(f"outcome {outcome['action_id']}", 'mediation', 'outcomes', o)]
            # An outcome added after the step 7 file was saved (a later discussion round) is in the current run.
            later = ((self.run['deliberations'][current].get('mediation') or {}).get('outcomes') or []) if current is not None else []
            o = find(later, outcome)
            return [{'label': f"Current saved run: outcome {outcome['action_id']}", 'file': f'/runs/{self.run_id}?audit=false',
                     'pointer': pointer('deliberations', current, 'mediation', 'outcomes', o)}] if o is not None else []
        return [base(f"case {case['case_id']}"), *self.call_links(case.get('call_ids'))], outcome_links

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
