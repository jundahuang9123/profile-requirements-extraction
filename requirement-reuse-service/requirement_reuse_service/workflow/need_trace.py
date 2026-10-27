"""Need trace (rq1-need-trace-v1): the chain of evidence and decisions behind every need a run produced.

Junda, 26 Oct: every produced need must be traceable through the whole chain (which material it comes from, which
agent extracted it, what each step decided about it and why, and why the discussion ended as it did), and a need
whose chain cannot be shown is not found solidly. Reviewers must not get more work from it.

The trace is built only from what the run stores; nothing is asked of a model. A need is solid when four kinds of
link hold:
- sources: every supporting quotation is found in its evidence unit;
- origin: it comes from at least one extracted observation of a named agent (role run, prompt version, model);
- decisions: each step that judged, merged, split, revised or kept it recorded a decision with a reason;
- discussion: if it was discussed, an outcome or concern names it, and every revision an outcome names exists.
Model-call links (which call made a decision) are bookkeeping: they are reported per decision and counted for the
run, but a missing one does not make a need less solid. Since this version the pipeline records call IDs where a
decision is made; for earlier runs they are matched by output or input hash.
"""
from collections import defaultdict
from .storage import canonical, digest, uid

TRACE_POLICY = 'rq1-need-trace-v1'
NEED_STEPS = ('proposal_support', 'proposal_support_confirmation', 'need_statement', 'classification', 'base_search',
              'profile_scope', 'profile_scope_confirmation', 'fa_scope_confirmation', 'dataset_applicability', 'selection')
CALL_STEPS = {'proposal_support': ('proposal_support',), 'proposal_support_confirmation': ('proposal_support',),
              'need_statement': ('writer', 'rewrite_critic'), 'classification': ('classification',),
              'base_search': ('classification',), 'profile_scope': ('profile_scope',),
              'profile_scope_confirmation': ('profile_scope',), 'fa_scope_confirmation': ('profile_scope',),
              'dataset_applicability': ('profile_scope',), 'selection': ('selection',)}
ROW_IDS = ('proposal_id', 'need_id', 'group_id', 'member_id')


def folded(text):
    return ' '.join(str(text or '').split())


class TraceIndex:
    """Indexes one stored run (and the run it was derived from, for extraction) for tracing its needs."""

    def __init__(self, store, run):
        self.store, self.run = store, run
        self.records = {r['revision_id']: r for r in run.get('requirements', [])}
        self.active = set(run.get('active_revision_ids', []))
        self.children = defaultdict(set)
        for record in self.records.values():
            for parent in record.get('parent_revision_ids') or []:
                self.children[parent].add(record['revision_id'])
        self.observations = {o['observation_id']: o for o in run.get('observations', [])}
        # A derived run copies the extraction (role runs and observations) but not its model calls: those stay in the
        # run that extracted, possibly several derivations back.
        # It can also reuse the cached judgements of the run it was derived from, whose calls stay there.
        self.origin_run, hops, self.earlier_runs = run, 0, []
        while hops < 10 and not any(c.get('step') == 'extraction' for c in self.origin_run.get('model_calls') or []):
            source = (self.origin_run.get('derived_from') or {}).get('run_id')
            if not source: break
            try: self.origin_run = store.get_run(source, omit=('need_chunks', 'deliberations', 'stage_results', 'machine_snapshot',
                                                                 'requirements', 'stakeholder_audit', 'catalogues'))
            except Exception: break
            self.earlier_runs.append(self.origin_run); hops += 1
        self.run_ids = [run.get('run_id'), *[r.get('run_id') for r in self.earlier_runs]]
        extraction_calls = defaultdict(list)
        for call in self.origin_run.get('model_calls') or []:
            if call.get('step') == 'extraction' and call.get('output') is not None:
                extraction_calls[digest(call['output'])].append(call['call_id'])
        self.role_runs, self.extraction_calls = {}, {}
        for index, role_run in enumerate(run.get('role_runs') or self.origin_run.get('role_runs') or []):
            batches = [(b, o) for b, raw in enumerate(role_run.get('raw_outputs') or [])
                       for o in (raw or {}).get('observations') or []]
            ids = role_run.get('observation_ids') or []
            recorded = {o: s.get('call_ids') for s in role_run.get('citation_selections') or []
                        for o in s.get('observation_ids') or [] if s.get('call_ids')}
            for position, observation in enumerate(ids):
                self.role_runs[observation] = (index, role_run)
                if observation in recorded:
                    self.extraction_calls[observation] = call_status(list(recorded[observation]), 'recorded')
                elif len(batches) == len(ids):
                    found = extraction_calls.get(digest(role_run['raw_outputs'][batches[position][0]]), [])
                    self.extraction_calls[observation] = call_status(list(found), 'matched' if found else 'missing')
        self.set_asides = defaultdict(list)
        for aside in run.get('set_aside_observations', []):
            if aside.get('revision_id'): self.set_asides[aside['revision_id']].append(aside)
        steps = run.get('need_steps') or {}
        self.fa_run = fa_run(run)
        self.decisions = defaultdict(dict)  # step -> row id -> decision row
        # In an F/A run profile_scope.decisions are the F/A test and record_decisions the record test; in any other
        # needs run the one ProfileScope judgement (the record test) is profile_scope.decisions.
        layout = ((('profile_scope', 'decisions', 'need_id'), ('record_test', 'record_decisions', 'need_id')) if self.fa_run
                  else (('record_test', 'decisions', 'need_id'),))
        for step, key, field in (('proposal_support', 'decisions', 'proposal_id'), ('classification', 'decisions', 'need_id'),
                                 *layout, ('dataset_applicability', 'decisions', 'need_id')):
            source_step = 'profile_scope' if step == 'record_test' else step
            for row in (steps.get(source_step) or {}).get(key) or []:
                if isinstance(row, dict) and row.get(field): self.decisions[step][row[field]] = row
        # Writing events name the revisions they wrote; a revision re-hashed later (refresh_need) keeps its group.
        self.merges, self.group_merges = defaultdict(list), defaultdict(list)
        for event in (steps.get('need_statement') or {}).get('events') or []:
            for output in event.get('outputs') or []: self.merges[output].append(event)
            if event.get('group_id'): self.group_merges[event['group_id']].append(event)
        self.groupings = {}
        for chunk in (run.get('consolidation_chunks') or {}).values():
            if not isinstance(chunk, dict) or chunk.get('block_key') != 'underlying_needs': continue
            members = chunk.get('revision_ids') or []
            for group in ((chunk.get('result') or {}).get('groups') or []):
                ids = [members[int(a[1:]) - 1] for a in group.get('member_ids') or []
                       if isinstance(a, str) and a[:1] == 'c' and a[1:].isdigit() and 0 < int(a[1:]) <= len(members)]
                for identifier in ids:
                    self.groupings[identifier] = {'members': ids, 'rationale': group.get('rationale') or '',
                                                  'join_group_id': group.get('join_group_id'), 'chunk_key': chunk.get('chunk_key'),
                                                  'call_ids': chunk.get('call_ids') or []}
        self.calls = {c['call_id']: c for c in run.get('model_calls') or [] if c.get('call_id')}
        self.calls_by_output = defaultdict(list); self.calls_by_context = defaultdict(list)
        self.calls_by_error = defaultdict(list)
        for earlier in reversed(self.earlier_runs):
            for call in earlier.get('model_calls') or []:
                if call.get('output') is not None and call.get('call_id'): self.calls_by_output[digest(call['output'])].append(call['call_id'])
                if call.get('output') is None and call.get('error'): self.calls_by_error[call['error']].append(call['call_id'])
        self.calls_by_rationale = defaultdict(list)  # assessment and base review keep the call's rationale verbatim
        # A failed call stores no output, but the rows recovered from it keep the call's error text; one error text
        # in two runs (an attempt copied by a derived run) links to neither.
        for call in self.calls.values():
            if call.get('output') is None and call.get('error'): self.calls_by_error[call['error']].append(call['call_id'])
            if call.get('output') is not None: self.calls_by_output[digest(call['output'])].append(call['call_id'])
            if call.get('context_hash'): self.calls_by_context[call['context_hash']].append(call['call_id'])
            output = call.get('output') if isinstance(call.get('output'), dict) else {}
            for row in [output, *[r for rows in output.values() if isinstance(rows, list) for r in rows if isinstance(r, dict)]]:
                if call.get('step') in {'assessment', 'base_review', 'base_review_check'} and len(str(row.get('rationale') or '')) >= 20:
                    self.calls_by_rationale[(call['step'], folded(row['rationale']))].append(call['call_id'])
        self.audit = run.get('stakeholder_audit') or {}
        # A revision keeps its parent's requirement ID, so an assessment is found by what it says, not by the need.
        self.assessment_calls = {digest(c['qualification']): c['call_ids'] for c in (run.get('need_chunks') or {}).values()
                                 if isinstance(c, dict) and c.get('step') == 'assessment' and c.get('call_ids') and c.get('qualification')}
        self.assessment_calls.update({digest(entry['output']): entry['call_ids'] for key, entry in self.audit.items()
                                      if key.startswith('mediation_assessment:') and isinstance(entry, dict)
                                      and entry.get('call_ids') and entry.get('output')})
        self.chunk_rows = defaultdict(list)  # (step, row id) -> [(chunk key, attempt number, row, call ids, link)]
        for key, chunk in (run.get('need_chunks') or {}).items():
            if not isinstance(chunk, dict) or chunk.get('step') not in NEED_STEPS: continue
            for number, attempt in enumerate(chunk.get('attempts') or [], 1):
                output = attempt.get('output')
                calls, link = self.attempt_calls(attempt)
                for rows in (output.values() if isinstance(output, dict) else []):
                    for row in rows if isinstance(rows, list) else []:
                        if not isinstance(row, dict): continue
                        for field in ROW_IDS:
                            if isinstance(row.get(field), str):
                                self.chunk_rows[(chunk['step'], row_kind(chunk['step'], row), row[field])].append((key, number, row, calls, link))
        self.cases = defaultdict(list)
        for case in run.get('deliberations') or []:
            named = set(case.get('revision_ids') or [])
            for outcome in ((case.get('mediation') or {}).get('outcomes') or []):
                named.update(result_ids(outcome))
            for identifier in named: self.cases[identifier].append(case)
        self.evidence, self.sources = {}, {}
        manifest = run.get('role_manifest') or {}
        self.agent_names = {r.get('id'): r.get('label') or r.get('name') or r.get('id')
                            for r in (manifest.get('extraction_roles') or []) + (manifest.get('procedural_roles') or []) if isinstance(r, dict)}

    def agent(self, role_id):
        return self.agent_names.get(role_id) or {'shared_source_extractor': 'Shared source extractor'}.get(role_id, role_id)

    def source_name(self, source_version_id):
        if source_version_id not in self.sources:
            try: self.sources[source_version_id] = self.store.get('source', source_version_id).get('name')
            except Exception: self.sources[source_version_id] = source_version_id
        return self.sources[source_version_id]

    def attempt_calls(self, attempt):
        if attempt.get('call_ids'): return list(attempt['call_ids']), 'recorded'
        if attempt.get('output') is not None:
            found = self.calls_by_output.get(digest(attempt['output']))
            if found: return list(found), 'matched'
        found = self.calls_by_error.get(attempt.get('error')) if attempt.get('error') else None
        if found and len(found) == 1: return list(found), 'matched'
        return [], 'missing'

    def unit(self, evidence_id):
        if evidence_id not in self.evidence:
            try: self.evidence[evidence_id] = self.store.get('evidence', evidence_id)
            except Exception: self.evidence[evidence_id] = None
        return self.evidence[evidence_id]

    def ancestors(self, revision_id):
        seen, stack, order = set(), [revision_id], []
        while stack:
            current = stack.pop()
            if current in seen: continue
            seen.add(current); order.append(current)
            stack.extend((self.records.get(current) or {}).get('parent_revision_ids') or [])
        return order


def call_status(calls, link):
    return {'call_ids': calls, 'call_link': link}


def fa_run(run):
    request = run.get('request') or {}
    return request.get('requirements_scope') == 'find_access_v1' or request.get('stakeholder_workflow') == 'fa_mediated'


def record_outcome(scope):
    """The record test's outcome on a record: a first judgement that failed it stands when the second is missing."""
    confirmation = scope.get('confirmation') or {}
    if scope.get('failed_tests'): return 'failed ' + ', '.join(scope['failed_tests'])
    if confirmation.get('outcome') == 'not_checked' and confirmation.get('first_failed_tests'):
        return 'failed once (' + ', '.join(confirmation['first_failed_tests']) + '), second judgement missing'
    return 'passed'


def matching_row(index, step, identifier, kind, wanted, latest=False, exact=False):
    """The cached row that made a decision: the one saying what the decision says. A revision written by the discussion
    keeps its parent's requirement ID, so the rows under one ID can be the parent's (earliest) and the scope tests
    at apply of its revisions (latest)."""
    rows = index.chunk_rows.get((step, kind, identifier)) or []
    said = folded((wanted or {}).get('rationale'))
    same = [r for r in rows if said and folded(r[2].get('rationale')) == said]
    if same: return same[-1]
    if exact: return None
    return (rows[-1] if latest else rows[0]) if rows else None


# A judgement made twice (a first judgement, then one made alone) keeps on the record the one that stands; the other
# is its confirmation's verdict. A classification can come from any chunk of the base search. Each is linked to the
# call that gave it: the row that says what it says, in any of the steps that make that judgement.
SUPPORT = (('proposal_support', ''), ('proposal_support_confirmation', ''))
FA_TEST = (('profile_scope', 'fa'), ('fa_scope_confirmation', ''))
RECORD_TEST = (('profile_scope', 'record'), ('profile_scope_confirmation', ''))
JUDGED_IN = {'classification': (('classification', ''), ('base_search', '')), 'fa_test': FA_TEST, 'record_test': RECORD_TEST,
             'dataset_applicability': (('dataset_applicability', ''),),
             'fa_test_confirmation': FA_TEST[::-1], 'record_test_confirmation': RECORD_TEST[::-1]}


def judged_row(index, places, identifier, wanted, latest=False, exact=False):
    """The cached row that gave a judgement: the one saying what it says in any of its steps, else (unless exact) the
    first step's row under the ID."""
    for step, kind in places:
        hit = matching_row(index, step, identifier, kind, wanted, latest=latest, exact=True)
        if hit: return hit
    return None if exact else matching_row(index, places[0][0], identifier, places[0][1], wanted, latest=latest)


def result_ids(outcome):
    """The revisions an outcome wrote: result_revision_ids (F/A discussion) or result_revision_id (routed discussion)."""
    return [*(outcome.get('result_revision_ids') or []), *([outcome['result_revision_id']] if outcome.get('result_revision_id') else [])]


def row_kind(step, row):
    """One step keeps rows of several contracts under the same IDs: the F/A test and the record test (profile_scope),
    the writer and its critics (need_statement)."""
    if step == 'profile_scope': return 'record' if 'catalogue_level' in row or 'record_resource' in row else 'fa'
    if step == 'need_statement': return 'writer' if 'statement' in row else 'check'
    return ''


def rationale_calls(index, step, decision, recorded=None):
    if recorded: return call_status(list(recorded), 'recorded')
    found = index.calls_by_rationale.get((step, folded(decision.get('rationale'))), [])
    return call_status(list(dict.fromkeys(found)), 'matched' if found else 'missing')


def step_rows(index, step, identifier, kind=''):
    rows = index.chunk_rows.get((step, kind, identifier)) or []
    return rows[-1] if rows else None


def need_trace(index, revision_id):
    """The trace of one produced need: sources, origin, decisions, discussion and whether the chain is complete."""
    record = index.records[revision_id]
    lineage = index.ancestors(revision_id)
    missing = []
    # Sources: every supporting quotation is found in its unit.
    sources = []
    for link in record.get('evidence_links') or []:
        if link.get('relation', 'supports') != 'supports': continue
        unit = index.unit(link.get('evidence_id'))
        content = (unit or {}).get('content') or ''
        found = bool(unit) and (link.get('quote', '') in content or folded(link.get('quote')) in folded(content))
        sources.append({'evidence_id': link.get('evidence_id'), 'source_version_id': (unit or {}).get('source_version_id'),
                        'source': index.source_name((unit or {}).get('source_version_id')) if unit else None,
                        'selector': (unit or {}).get('selector'), 'quote': link.get('quote'), 'quote_start': link.get('quote_start'),
                        'component': link.get('component'), 'found': found})
        if not found: missing.append({'link': 'sources', 'detail': f"Quotation not found in {link.get('evidence_id')}."})
    if not sources: missing.append({'link': 'sources', 'detail': 'No supporting quotation.'})
    verification = record.get('verification') or {}
    if verification and verification.get('status') != 'pass':
        failed = [l.get('evidence_id') for l in verification.get('links') or [] if l.get('status') != 'pass']
        missing.append({'link': 'sources', 'detail': 'The source check failed' + (f" for {', '.join(map(str, failed))}" if failed else '')
                        + (f": {verification['message']}" if verification.get('message') else '.')})
    # Origin: the extracted observations and the agent (role run) behind each.
    origin = []
    observation_ids = list(dict.fromkeys(o for r in lineage for o in (index.records.get(r) or {}).get('observation_ids') or []))
    for observation_id in observation_ids:
        observation = index.observations.get(observation_id)
        role_index, role_run = index.role_runs.get(observation_id, (None, None))
        entry = {'observation_id': observation_id, 'statement': (observation or {}).get('statement'),
                 'agent': (role_run or {}).get('role_id') or (observation or {}).get('role_id'),
                 'agent_name': index.agent((role_run or {}).get('role_id') or (observation or {}).get('role_id')),
                 'prompt_version': (role_run or {}).get('prompt_version'), 'extraction_policy': (role_run or {}).get('extraction_policy'),
                 'model': ((role_run or {}).get('provider') or {}).get('model'), 'role_run_index': role_index,
                 'extraction_run_id': index.origin_run.get('run_id'),
                 **index.extraction_calls.get(observation_id, call_status([], 'missing'))}
        cited = {l.get('evidence_id') for l in (observation or {}).get('evidence_links') or []}
        assigned = set((role_run or {}).get('assigned_evidence_ids') or [])
        entry['cited_within_assignment'] = bool(cited) and cited <= assigned if assigned else None
        origin.append(entry)
    mediated = [o for o in observation_ids if o not in index.observations]
    if not any(o['statement'] and o['agent'] and o['prompt_version'] for o in origin) and not trace_from_discussion(index, revision_id):
        missing.append({'link': 'origin', 'detail': 'No extracted observation with a named agent, prompt version and model.'})
    # Decisions, from the proposals up to the need.
    decisions = []
    def decided(step, revision, decision, reason, policy=None, calls=None, required=True):
        entry = {'step': step, 'revision_id': revision, 'decision': decision, 'reason': reason or '', 'policy_version': policy,
                 **(calls or call_status([], 'not_applicable'))}
        decisions.append(entry)
        if required and not (reason or '').strip():
            missing.append({'link': 'decisions', 'detail': f'{step} recorded no reason for {revision}.'})
    for revision in reversed(lineage):
        current = index.records.get(revision) or {}
        check = current.get('verification') or {}
        if check:
            decided('source_check', revision, check.get('status'), check.get('message') or
                    ('Every cited quotation was found in its source.' if check.get('status') == 'pass' else ''),
                    check.get('method_version'), required=False)
        # The record keeps its own support judgement, including one the check could not make (not_checked, with
        # the reason); the step's decision list holds the valid rows.
        row = current.get('proposal_support') or index.decisions['proposal_support'].get(revision)
        if row:
            # A second judgement that failed leaves the proposal not_checked, with that call's failure as its reason.
            failed = ((current.get('proposal_support') or {}).get('confirmation') or {}).get('outcome') == 'not_checked'
            hit = judged_row(index, SUPPORT[::-1] if failed else SUPPORT, revision, row, latest=True)
            decided('proposal_support', revision, row.get('support'),
                    row.get('rationale') or (row.get('fallback') or {}).get('reason'), row.get('policy_version'),
                    call_status(*hit[3:]) if hit else None)
            confirmation = (current.get('proposal_support') or {}).get('confirmation')
            if confirmation:
                hit = judged_row(index, SUPPORT[::-1], revision, confirmation.get('verdict'), latest=True)
                decided('proposal_support_confirmation', revision, confirmation.get('outcome'),
                        (confirmation.get('verdict') or {}).get('rationale'), None, call_status(*hit[3:]) if hit else None)
        grouping = index.groupings.get(revision)
        if grouping and len(grouping['members']) > 1:
            decided('grouping', revision, 'merged with ' + ', '.join(m for m in grouping['members'] if m != revision),
                    grouping['rationale'], None, call_status(grouping['call_ids'], 'recorded' if grouping['call_ids'] else 'missing'),
                    required=False)
        for event in index.merges.get(revision) or (index.group_merges.get(current.get('group_id')) if revision == revision_id else []) or []:
            # The writer and its critics answer for the group they were offered; when the writer left a member out,
            # the event names the smaller group it wrote.
            writer_run = next((rid for rid in index.run_ids if uid('group', rid, list(event.get('inputs') or [])) == event.get('group_id')),
                              index.run.get('run_id'))
            offered = event.get('written_group_id') or uid('group', writer_run,
                                                           sorted([*(event.get('inputs') or []), *(event.get('split_member_ids') or [])]))
            groups = list(dict.fromkeys([offered, event.get('group_id')]))
            writer = next((hit for g in groups for hit in [step_rows(index, 'need_statement', g, 'writer')] if hit), None)
            checks = [r for g in groups for r in index.chunk_rows.get(('need_statement', 'check', g), []) if r[2].get('rationale')]
            reason = ' '.join(dict.fromkeys(r[2]['rationale'] for r in checks)) or (grouping or {}).get('rationale', '')
            decided('need_statement', revision, f"{event.get('action')} of {len(event.get('inputs') or [])} member(s)",
                    reason, event.get('policy_version'), call_status(*writer[3:]) if writer else None,
                    required=len(event.get('inputs') or []) > 1)
    need_id = record.get('requirement_id')
    made_here = trace_from_discussion(index, revision_id)
    if made_here:
        # A need the discussion wrote keeps its parent's requirement ID, so the step rows under that ID are the
        # parent's; its own scope judgements are on its record (scope tests at apply, or the mediation check).
        for field, label in (('fa_scope', 'fa_test'), ('profile_scope', 'record_test')):
            own = record.get(field) or {}
            if own.get('rationale') or own.get('status'):
                decision = (own.get('serves') or own.get('status') if label == 'fa_test' else
                            record_outcome(own) if own.get('rationale') else own.get('status'))
                hit = judged_row(index, JUDGED_IN[label], need_id, own, latest=True, exact=True)
                same = hit and folded(hit[2].get('rationale')) == folded(own.get('rationale'))
                decided(label, revision_id, decision, own.get('rationale') or own.get('reason'), own.get('policy_version'),
                        call_status(*hit[3:]) if same else None, required=False)
    by_need = (('classification', 'rationale', 'classification'), ('profile_scope', 'rationale', 'fa_test'),
               ('record_test', 'rationale', 'record_test'), ('dataset_applicability', None, 'dataset_applicability'))
    for step, field, label in () if made_here else by_need:
        row = index.decisions[step].get(need_id)
        kept = record.get({'fa_test': 'fa_scope', 'record_test': 'profile_scope'}.get(label, '')) or {}
        if not row and kept.get('status') == 'not_checked':
            # No valid row after the correction: the need is kept, flagged, with the reason on its record.
            hit = judged_row(index, JUDGED_IN[label], need_id, kept)
            decided(label, revision_id, 'not_checked', kept.get('reason') or (kept.get('fallback') or {}).get('reason'),
                    kept.get('policy_version'), call_status(*hit[3:]) if hit else None)
            continue
        if not row: continue
        hit = judged_row(index, JUDGED_IN[label], need_id, row)
        if label == 'classification' and not judged_row(index, JUDGED_IN[label], need_id, row, exact=True):
            # The decision sums up several chunks of the search, each answered by its own call (a chunk's last attempt
            # is the answer it kept): every chunk when none matched, else the chunks that matched.
            final = {}
            for step, kind in JUDGED_IN[label]:
                for h in index.chunk_rows.get((step, kind, need_id)) or []:
                    if h[0] not in final or h[1] > final[h[0]][1]: final[h[0]] = h
            rows = [h for h in final.values() if row.get('classification') == 'domain' or h[2].get('classification') != 'domain']
            calls = list(dict.fromkeys(c for h in rows for c in h[3]))
            if calls: hit = (None, None, row, calls, 'recorded' if all(h[4] == 'recorded' for h in rows) else 'matched')
        reason = row.get(field) if field else '; '.join(l.get('rationale', '') for l in row.get('category_links') or [])
        decision = {'classification': row.get('classification'), 'fa_test': row.get('serves'),
                    'record_test': record_outcome({**kept, 'failed_tests': row.get('failed_tests') or kept.get('failed_tests')}),
                    'dataset_applicability': f"{len(row.get('category_links') or [])} categories"}[label]
        gap = record.get('base_gap') or {}
        if label == 'classification' and (gap.get('status') == 'not_checked' or 'not_classified' in (record.get('processing_flags') or [])):
            # The base search fell back after invalid answers: the 'domain' row records no search, only its absence.
            hit = judged_row(index, JUDGED_IN[label], need_id, row, exact=True)
            decided(label, revision_id, 'not_checked', 'The base search returned no valid classification'
                    + (f" ({len(gap.get('checked_entry_ids') or [])} of {gap.get('catalogue_entry_count')} entries checked)." if gap else '.'),
                    row.get('policy_version'), call_status(*hit[3:]) if hit else call_status([], 'missing'))
            continue
        decided(label, revision_id, decision, reason, row.get('policy_version'), call_status(*hit[3:]) if hit else None,
                required=label != 'dataset_applicability')
    for field, label, step in (('fa_scope', 'fa_test_confirmation', 'fa_scope_confirmation'),
                               ('profile_scope', 'record_test_confirmation', 'profile_scope_confirmation')):
        confirmation = (record.get(field) or {}).get('confirmation')
        if confirmation:
            hit = judged_row(index, JUDGED_IN[label], need_id, confirmation.get('verdict'), latest=made_here)
            decided(label, revision_id, confirmation.get('outcome'), (confirmation.get('verdict') or {}).get('rationale')
                    or confirmation.get('reason'), None, call_status(*hit[3:]) if hit else None)
    qualification = record.get('qualification') or {}
    if qualification:
        decided('assessment', revision_id, qualification.get('support'),
                qualification.get('rationale') or '; '.join(f.get('message', '') for f in qualification.get('findings') or []),
                qualification.get('assessor'), rationale_calls(index, 'assessment', qualification,
                                                               index.assessment_calls.get(digest(qualification))),
                required=False)
    relation = record.get('base_relation') or {}
    if relation:
        check = relation.get('check') or {}
        reviewed = relation.get('status') != 'not_reviewed' or relation.get('review_call_ids') or relation.get('errors')
        decided('base_review', revision_id, f"{relation.get('verdict') or relation.get('status')} ({relation.get('effect')})",
                relation.get('rationale') or check.get('rationale') or '; '.join(map(str, relation.get('errors') or []))
                or (f"not reviewed: {relation['reason']}" if relation.get('reason') else ''),
                None, rationale_calls(index, 'base_review', relation, relation.get('review_call_ids')) if reviewed else None)
        if check:
            decided('base_review_check', revision_id, 'supported' if check.get('verdict_supported') else 'not supported',
                    check.get('rationale'), None, rationale_calls(index, 'base_review_check', check, relation.get('check_call_ids')),
                    required=False)
    for aside in index.set_asides.get(revision_id, []):
        decided('set_aside', revision_id, aside.get('reason'), aside.get('rationale'))
    discussion = discussion_trace(index, revision_id, missing)
    if revision_id in index.active: expected_decisions(index, record, lineage, decisions, missing)
    state = ('active' if revision_id in index.active else 'set_aside' if index.set_asides.get(revision_id)
             else 'superseded' if index.children.get(revision_id) else 'inactive')
    calls = defaultdict(int)
    for entry in decisions:
        if entry['call_link'] != 'not_applicable': calls[entry['call_link']] += 1
    return {'policy_version': TRACE_POLICY, 'revision_id': revision_id, 'requirement_id': need_id,
            'statement': record.get('need_statement') or record.get('normalized_statement'), 'state': state,
            'lifecycle_state': record.get('lifecycle_state'), 'flags': record.get('processing_flags') or [],
            'sources': sources, 'origin': origin, 'mediated_observation_ids': mediated, 'lineage': lineage,
            'decisions': decisions, 'discussion': discussion,
            'completeness': {'solid': not missing, 'missing': missing, 'call_links': dict(calls)}}


def expected_decisions(index, record, lineage, decisions, missing):
    """An active need must show a decision at every step that judges each need: proposal support for each proposal it
    was written from, and classification, the scope tests, assessment and base review where the run ran them. A need
    the discussion created shows instead the outcome that made it, with its reason."""
    run, made = index.run, {d['step'] for d in decisions}
    if trace_from_discussion(index, record['revision_id']):
        # Its reason is the outcome's; scope tests at apply exist only where the discussion policy runs them (v13 and
        # later), so they are shown when present but not required.
        outcome = next(o for case in index.cases.get(record['revision_id'], [])
                       for o in ((case.get('mediation') or {}).get('outcomes') or [])
                       if record['revision_id'] in result_ids(o))
        if not (outcome.get('rationale') or '').strip():
            missing.append({'link': 'decisions', 'detail': f"Outcome {outcome.get('action_id')} that made it recorded no reason."})
        return
    steps = run.get('need_steps') or {}
    if 'proposal_support' in steps:
        for revision in lineage:
            current = index.records.get(revision) or {}
            if (current.get('observation_ids') and not current.get('parent_revision_ids') and not current.get('proposal_support')
                    and revision not in index.decisions['proposal_support']):
                missing.append({'link': 'decisions', 'detail': f'proposal_support recorded no decision for {revision}.'})
    if not any(index.merges.get(r) for r in lineage) and not index.group_merges.get(record.get('group_id')):
        missing.append({'link': 'decisions', 'detail': 'need_statement recorded no writing event for it.'})
    # A step is expected only when it judged needs one by one in this run (a run without a base profile, for
    # instance, classifies nothing).
    ran = lambda step, key: bool((steps.get(step) or {}).get(key))
    # Classification and the record test skip a need whose source check failed; that failure is its missing link.
    verified = (record.get('verification') or {}).get('status', 'pass') == 'pass'
    for step, label, wanted in (('classification', 'classification', verified and ran('classification', 'decisions')),
                                ('profile_scope', 'fa_test', index.fa_run and ran('profile_scope', 'decisions')),
                                ('record_test', 'record_test', verified and ran('profile_scope', 'record_decisions' if index.fa_run else 'decisions')),
                                ('assessment', 'assessment', ran('assessment', 'records')),
                                ('base_review', 'base_review', bool(((run.get('stage_results') or {}).get('base_review') or {}).get('phases')))):
        if wanted and label not in made:
            missing.append({'link': 'decisions', 'detail': f'{label} recorded no decision.'})


def trace_from_discussion(index, revision_id):
    """A need the discussion created (add, split, revise) has its origin in the outcome that made it."""
    return any(revision_id in result_ids(o)
               for case in index.cases.get(revision_id, [])
               for o in ((case.get('mediation') or {}).get('outcomes') or []))


def discussion_trace(index, revision_id, missing):
    cases = []
    for case in index.cases.get(revision_id, []):
        mediation = case.get('mediation') or {}
        concerns = [{'role_id': m.get('role_id'), 'round': m.get('round'), 'kind': c.get('kind'), 'statement': c.get('statement')}
                    for m in case.get('messages') or [] for c in m.get('concerns') or [] if revision_id in (c.get('revision_ids') or [])]
        outcomes = []
        for outcome in mediation.get('outcomes') or []:
            named = set(outcome.get('parent_revision_ids') or []) | set(result_ids(outcome))
            if revision_id not in named: continue
            dangling = [r for r in named if r not in index.records and r not in plan_actions(case)]
            # A proposal the salvage rejected is shown to the person as the model wrote it, names and all; it is
            # listed with the review items, and does not break the chain of the need that was kept.
            if dangling and not outcome.get('salvage_rejected'):
                missing.append({'link': 'discussion', 'detail': f"Outcome {outcome.get('action_id')} names {', '.join(sorted(dangling))}, which is no revision."})
            check = outcome.get('independent_check') or {}
            outcomes.append({'action_id': outcome.get('action_id'), 'action': outcome.get('action'), 'status': outcome.get('status'),
                             'applied': outcome.get('applied'), 'rationale': outcome.get('rationale'),
                             'check': {k: v for k, v in check.items() if k != 'item_id'} if check else None,
                             'question': (outcome.get('human_question') or {}).get('question') if isinstance(outcome.get('human_question'), dict)
                                         else outcome.get('human_question'),
                             'result_revision_ids': result_ids(outcome),
                             'scope_tests': [{'need_id': (s.get('fa_scope') or {}).get('need_id'), 'failed_tests': s.get('failed_tests') or [],
                                              'serves': (s.get('fa_scope') or {}).get('serves'),
                                              'judged': all((s.get(f) or {}).get('status', 'checked') == 'checked'
                                                            and ((s.get(f) or {}).get('confirmation') or {}).get('outcome') != 'not_checked'
                                                            for f in ('fa_scope', 'profile_scope'))}
                                             for s in outcome.get('scope_tests') or []]})
        questions = [q.get('question') for q in mediation.get('human_questions') or [] if revision_id in (q.get('revision_ids') or [])]
        phases = (case.get('discussion_trace') or {}).get('phases') or {}
        calls = sorted({c for phase in phases.values() if isinstance(phase, dict)
                        for c in ([c for a in phase.get('attempts') or [] for c in a.get('call_ids') or []]
                                  or index.calls_by_context.get((phase.get('context_budget') or {}).get('wire_hash'), []))})
        # A mediated case accounts for each of its needs; an earlier free discussion (messages only) does not.
        if mediation.get('outcomes') and not outcomes and not concerns and not questions:
            missing.append({'link': 'discussion', 'detail': f"Case {case.get('case_id')} discussed it but no outcome or concern names it."})
        cases.append({'case_id': case.get('case_id'), 'stop_reason': case.get('stop_reason'), 'roles': case.get('participants') or [],
                      'concerns': concerns, 'outcomes': outcomes, 'questions': questions,
                      'summary': mediation.get('summary'), 'call_ids': calls})
    return cases


def plan_actions(case):
    return {o.get('action_id') for o in ((case.get('mediation') or {}).get('outcomes') or []) if o.get('action_id')}


def review_items(index):
    """Every item the discussion sends to a person must name what it is about: a revision of the run, or another
    action of the same plan (a defer of a proposed addition). Returns the items that name neither."""
    loose = []
    for case in index.run.get('deliberations') or []:
        actions = plan_actions(case)
        for outcome in ((case.get('mediation') or {}).get('outcomes') or []):
            if outcome.get('status') != 'human_review': continue
            named = list(outcome.get('parent_revision_ids') or []) + result_ids(outcome)
            unresolved = [r for r in named if r not in index.records and r not in actions]
            if unresolved or (not named and outcome.get('action') not in {'add', 'experience_proposal'}):
                loose.append({'case_id': case.get('case_id'), 'action_id': outcome.get('action_id'),
                              'action': outcome.get('action'), 'unresolved': unresolved})
    return loose


def produced_needs(run):
    """The needs a run produced: written needs that are active, set aside or superseded (not raw proposals)."""
    return [r['revision_id'] for r in run.get('requirements', []) if r.get('need_statement')]


def run_traces(store, run, revision_ids=None):
    index = TraceIndex(store, run)
    return {r: need_trace(index, r) for r in (revision_ids or produced_needs(run))}


def traceability(traces, active):
    """The run-level summary: how many produced and active needs are solid, and which links fail."""
    rows = list(traces.values())
    failing = defaultdict(int)
    for trace in rows:
        for link in {m['link'] for m in trace['completeness']['missing']}: failing[link] += 1
    calls = defaultdict(int)
    for trace in rows:
        for link, count in trace['completeness']['call_links'].items(): calls[link] += count
    return {'policy_version': TRACE_POLICY, 'produced': len(rows), 'solid': sum(t['completeness']['solid'] for t in rows),
            'active': sum(t['revision_id'] in active for t in rows),
            'active_solid': sum(t['completeness']['solid'] for t in rows if t['revision_id'] in active),
            'not_solid_by_link': dict(failing), 'decision_call_links': dict(calls)}


SUMMARY_STYLES = ('line', 'card', 'exceptions')
MAX_SET_ASIDE_COUNT, MAX_SET_ASIDE_SHARE = 3, 0.1


def short(text, limit):
    text = folded(text)
    return text if len(text) <= limit else text[:limit].rstrip() + '…'


def quote_window(quote, statement, limit=180):
    """The part of a quotation that best matches the need's words: reviewers judged sources from the first 90
    characters of a quotation, which often stopped before the clause that supports the need."""
    words = folded(quote).split()
    if len(' '.join(words)) <= limit: return ' '.join(words)
    norm = lambda w: ''.join(c for c in w.lower() if c.isalnum())
    wanted = {norm(w) for w in folded(statement).split() if len(norm(w)) > 3}
    hits = lambda word: any(w in norm(word) or (len(norm(word)) > 3 and norm(word) in w) for w in wanted)
    best, best_score = 0, -1
    for start in range(len(words)):
        span, size = [], 0
        for word in words[start:]:
            if size + len(word) + 1 > limit: break
            span.append(word); size += len(word) + 1
        score = sum(hits(w) for w in span)
        if score > best_score: best, best_score = start, score
    span, size = [], 0
    for word in words[best:]:
        if size + len(word) + 1 > limit: break
        span.append(word); size += len(word) + 1
    return ('…' if best else '') + ' '.join(span) + ('…' if best + len(span) < len(words) else '')


def summary_items(trace):
    """The phrases of a reviewer's account of the trace, each with the trace entry it reports (a JSON pointer into the
    trace, or None), so the workbench can link every phrase to the saved result it comes from."""
    sources = trace['sources']
    first = sources[0] if sources else {}
    source = (f'{first.get("source") or first.get("evidence_id")}: "{quote_window(first.get("quote"), trace["statement"])}"'
              if first else 'no quotation')
    if len(sources) > 1: source += f' (+{len(sources) - 1} more)'
    agents = list(dict.fromkeys(o['agent_name'] or o['agent'] for o in trace['origin'] if o.get('agent')))
    merged = len(trace['origin'])
    who = (', '.join(agents) or 'the discussion') + (f'; {merged} extracted proposals merged' if merged > 1 else '')
    by_step = {}
    for i, d in enumerate(trace['decisions']): by_step.setdefault(d['step'], []).append((f'/decisions/{i}', d))
    def last(step): return (by_step.get(step) or [(None, {})])[-1]
    plain = {'proposal_support': 'quote check', 'fa_test': 'find/access test', 'record_test': 'record test'}
    second = lambda outcome: [(f'/decisions/{i}', plain.get(d['step'].replace('_confirmation', ''), d['step']))
                              for i, d in enumerate(trace['decisions'])
                              if d['step'].endswith('_confirmation') and d['decision'] == outcome]
    serves = {'find': 'find data', 'access': 'access data', 'both': 'find and access data'}
    # Each phrase says what the decision was; a judgement a step could not make is never reported as passed.
    checks = []
    supports = by_step.get('proposal_support') or []
    if supports:
        # A merged need was written from several proposals: it is supported only if each of them is.
        said = [d['decision'] for _, d in supports]
        unjudged = said.count('not_checked')
        ref = next((r for r, d in supports if d['decision'] == 'not_checked'), supports[0][0]) if unjudged else supports[0][0]
        checks.append((('the quote check could not judge it' if len(said) == 1 else
                        f'the quote check could not judge {unjudged} of its {len(said)} proposals') if unjudged else
                       'the quote supports it' if set(said) == {'supported'} else
                       'the quote partly supports it' if 'partly' in said else 'quote check: ' + ', '.join(sorted(set(said))), ref))
    ref, fa = last('fa_test'); fa = fa.get('decision')
    if fa: checks.append((f'it helps users {serves[fa]}' if fa in serves else 'it does not help users find or access data'
                          if fa == 'neither' else 'judged by the discussion check' if fa == 'checked_mediation'
                          else 'the find/access test could not judge it', ref))
    ref, record_test = last('record_test'); record_test = record_test.get('decision')
    if record_test: checks.append(('the record test could not judge it' if record_test == 'not_checked' else f'record test {record_test}', ref))
    ref, classification = last('classification'); classification = classification.get('decision')
    if 'covered_by_base' in trace['flags'] or classification == 'generic':
        # The label comes from the classification, or else from the base review that found the need restated.
        checks.append(('already in the base profile', ref if classification == 'generic' else last('base_review')[0]))
    elif classification == 'not_checked': checks.append(('the base search could not judge it', ref))
    elif classification: checks.append(('not in the base profile', ref))
    disputed, unchecked = second('disputed'), second('not_checked')
    if disputed: checks.append(('a first judgement was overruled at the ' + ', '.join(s for _, s in disputed), disputed[0][0]))
    if unchecked: checks.append(('a second judgement is missing at the ' + ', '.join(s for _, s in unchecked), unchecked[0][0]))
    outcomes = [(f'/discussion/{c}/outcomes/{o}', outcome) for c, case in enumerate(trace['discussion'])
                for o, outcome in enumerate(case['outcomes'])]
    for ref, outcome in outcomes:
        if trace['revision_id'] not in outcome['result_revision_ids']: continue
        tests = [s for s in outcome['scope_tests'] if s['need_id'] == trace['requirement_id']]
        checks.append((f"written by the discussion ({outcome['action']})" + (
            '; a scope test failed' if any(s['failed_tests'] for s in tests) else
            '; its scope tests passed' if all(s.get('judged', True) for s in tests) else
            '; no scope test failed, but one could not judge it') if tests else '', ref))
    discussion, questions = [], {}
    for c, case in enumerate(trace['discussion']):
        for o, outcome in enumerate(case['outcomes']):
            ref = f'/discussion/{c}/outcomes/{o}'
            discussion.append((f"{outcome['action']} ({outcome['status']}): {short(outcome['rationale'], 220)}", ref))
            if outcome.get('question'): questions.setdefault(short(outcome['question'], 160), ref)
        if case.get('stop_reason') and not case['outcomes']: discussion.append((f"stopped ({case['stop_reason']})", f'/discussion/{c}'))
        for q in case.get('questions') or []: questions.setdefault(short(q, 160), f'/discussion/{c}')
    return {'source': (source, '/sources/0' if first else None), 'agents': agents, 'merged': merged,
            'who': (who, '/origin/0' if trace['origin'] else None), 'checks': checks, 'discussion': discussion,
            'questions': list(questions.items()), 'disputed': [s for _, s in disputed], 'unchecked': [s for _, s in unchecked],
            'missing': [m['detail'] for m in trace['completeness']['missing']]}


def summary_parts(trace):
    """The reviewer card (style 'card') as lines of phrases, each phrase with the trace entry it reports."""
    items = summary_items(trace)
    def joined(pairs, sep):
        parts = []
        for n, (text, ref) in enumerate(pairs):
            if n: parts.append({'text': sep, 'ref': None})
            parts.append({'text': text, 'ref': ref})
        return parts
    lines = [('Source', [items['source']]), ('Extracted by', [items['who']]),
             ('Checks', items['checks'] or [('none recorded', None)])]
    if items['discussion']: lines.append(('Discussion', items['discussion']))
    lines.append(('For you', items['questions'] or [('confirm, edit or reject.', None)]))
    if items['missing']: lines.append(('Chain incomplete', [(m, '/completeness') for m in items['missing']]))
    sep = {'Checks': '; ', 'Chain incomplete': '; '}
    return [{'label': label, 'parts': joined(pairs, sep.get(label, ' / '))} for label, pairs in lines]


def need_summary(trace, style='card'):
    """A short account of the trace for a reviewer, built from the trace alone (no model): where the need comes from,
    who extracted it, what the checks decided, what the discussion did and what is asked of the person."""
    items = summary_items(trace)
    source, who, agents, merged = items['source'][0], items['who'][0], items['agents'], items['merged']
    checks = [text for text, _ in items['checks']]
    discussion = [text for text, _ in items['discussion']]
    questions = [text for text, _ in items['questions']]
    disputed, unchecked, missing = items['disputed'], items['unchecked'], items['missing']
    if style == 'line':
        parts = [f'From {source}', f'extracted by {who}', 'checks: ' + ('; '.join(checks) or 'none recorded')]
        if discussion: parts.append('discussion: ' + ' / '.join(discussion))
        if questions: parts.append('asks you: ' + ' / '.join(questions))
        if missing: parts.append('chain incomplete: ' + '; '.join(missing))
        return '. '.join(parts) + '.'
    if style == 'card':
        lines = [f'Source: {source}', f'Extracted by: {who}', 'Checks: ' + ('; '.join(checks) or 'none recorded')]
        if discussion: lines.append('Discussion: ' + ' / '.join(discussion))
        lines.append('For you: ' + (' / '.join(questions) if questions else 'confirm, edit or reject.'))
        if missing: lines.append('Chain incomplete: ' + '; '.join(missing))
        return '\n'.join(lines)
    notable = []
    if merged > 1: notable.append(f'merged from {merged} extracted proposals ({", ".join(agents)})')
    if disputed: notable.append('a first judgement was overruled at the ' + ', '.join(disputed))
    if unchecked: notable.append('a second judgement is missing at the ' + ', '.join(unchecked))
    notable += [c for c in checks if 'could not judge' in c or 'second judgement missing' in c]
    if 'covered_by_base' in trace['flags']: notable.append('already in the base profile')
    notable += [f'discussion: {d}' for d in discussion if not d.startswith('retain (retained)')]
    notable += [f'asks you: {q}' for q in questions]
    notable += [f'chain incomplete: {m}' for m in missing]
    head = f'From {source}, extracted by {", ".join(agents) or "the discussion"}.'
    return head + (' Standard path: every check passed.' if not notable else ' Note: ' + '; '.join(notable) + '.')


def record_traceability(store, run_id, style='card'):
    """At the end of a needs run: trace every produced need, save the summary under stage_results.traceability, and
    set aside each active need whose chain is incomplete (trace_incomplete): it is not found solidly, and it is not
    put in front of a reviewer. It stays visible and restorable like any set-aside."""
    from .models import RequirementRecord
    from .needs import need_integrity
    run = store.get_run(run_id)
    if run.get('status') != 'awaiting_human' or not produced_needs(run): return None
    index = TraceIndex(store, run)
    traces = {r: need_trace(index, r) for r in produced_needs(run)}
    active = set(run['active_revision_ids'])
    weak = [traces[r] for r in run['active_revision_ids'] if r in traces and not traces[r]['completeness']['solid']]
    # A broken chain is rare (none of the 203 active needs of three JRC runs). When many needs of one run fail at
    # once, the trace is more likely wrong than the needs: nothing is set aside, and the run says so.
    held = len(weak) > max(MAX_SET_ASIDE_COUNT, MAX_SET_ASIDE_SHARE * len(active))
    result = {**traceability(traces, active), 'summary_style': style, 'review_items_unresolved': review_items(index),
              'set_aside_ids': [] if held else [t['revision_id'] for t in weak],
              'held_ids': [t['revision_id'] for t in weak] if held else [],
              'needs': {r: {'solid': t['completeness']['solid'], 'missing': t['completeness']['missing'],
                            'call_links': t['completeness']['call_links'], 'summary': need_summary(t, style)}
                        for r, t in traces.items()}}
    def save(r):
        r['stage_results']['traceability'] = result
        if held:
            r['diagnostics'] = [*r.get('diagnostics', []), f'Traceability: {len(weak)} of {len(active)} active needs have an '
                                'incomplete chain; none was set aside, since so many at once points to the trace, not the needs.']
            return
        for trace in weak:
            record = next(x for x in r['requirements'] if x['revision_id'] == trace['revision_id'])
            record['lifecycle_state'] = 'set_aside'
            record['processing_flags'] = list(dict.fromkeys([*(record.get('processing_flags') or []), 'trace_incomplete']))
            # The flag is part of the need's integrity hash; a stale hash fails verification on restore.
            record['need_integrity_hash'] = need_integrity(RequirementRecord.model_validate(record))
            if not any(a.get('need_id') == record['requirement_id'] and a['reason'] == 'trace_incomplete' for a in r['set_aside_observations']):
                r['set_aside_observations'].append({'observation_id': (record.get('observation_ids') or [''])[0],
                    'role_id': (record.get('contributing_roles') or [''])[0], 'revision_id': record['revision_id'],
                    'need_id': record['requirement_id'], 'reason': 'trace_incomplete',
                    'rationale': '; '.join(m['detail'] for m in trace['completeness']['missing']),
                    'matched_base_need_ids': record.get('matched_base_need_ids') or [], 'restored': False})
        r['active_revision_ids'] = [x for x in r['active_revision_ids'] if x not in set(result['set_aside_ids'])]
    store.mutate(run_id, None, 'traceability_recorded', save)
    return result
