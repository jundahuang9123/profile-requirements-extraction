"""rq1-need-trace-v1, trace links (Junda, 27 Oct): every entry of a need's trace links to where it was traced from:
the result file of the step that made it at the traced row (a JSON pointer), a model call, or the source document with
the quotation marked. Each test follows the links over the API, as the workbench does."""
import collections
import copy
from fastapi.testclient import TestClient
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_need_trace_v1 import finished, full_client  # noqa: F401  (pytest fixture)
from test_need_trace_v1_shapes import RevisingDialogue, build_source, new_fa_run, saved_record, trial
from requirement_reuse_service.main import app
from requirement_reuse_service.workflow import engine, need_trace
from requirement_reuse_service.workflow.models import RunRequest

API = '/api/rq1/v2'
IDS = ('revision_id', 'need_id', 'proposal_id', 'group_id', 'observation_id', 'case_id', 'action_id')
ROW_FIELDS = ('proposal_id', 'need_id', 'group_id', 'member_id', 'revision_id', 'item_id')


def linked(client, run, revision):
    response = client.get(f"{API}/runs/{run['run_id']}/needs/{revision}/trace")
    assert response.status_code == 200, response.text
    return response.json()


def entries(trace):
    yield 'need', trace['revision_id'], trace
    for source in trace['sources']: yield 'source', source['evidence_id'], source
    for origin in trace['origin']: yield 'origin', origin['observation_id'], origin
    for decision in trace['decisions']: yield decision['step'], decision['revision_id'], decision
    for case in trace['discussion']:
        yield 'case', case['case_id'], case
        for outcome in case['outcomes']: yield 'outcome', (case['case_id'], outcome['action_id']), outcome


def follow(client, link):
    """The file a link names, and the objects on the way to the place it points at (the place last)."""
    response = client.get(API + link['file'])
    assert response.status_code == 200, (link, response.text[:300])
    node, trail = response.json(), []
    for raw in link['pointer'].split('/')[1:]:
        key = raw.replace('~1', '/').replace('~0', '~')
        node = node[int(key)] if isinstance(node, list) else node[key]
        trail.append(node)
    return response.json(), node, trail


def names(trail, wanted):
    """Whether an object on the way to the linked place is about one of the wanted items."""
    return any(isinstance(n, dict) and (any(n.get(f) in wanted for f in IDS) or wanted & set(n.get('outputs') or [])
                                        or wanted & set(n.get('result_revision_ids') or [])
                                        or wanted & set(n.get('observation_ids') or [])) for n in trail)


folded = lambda text: ' '.join(str(text or '').split())


def alias(run, revision):
    chunk = next((c for c in run['consolidation_chunks'].values() if revision in (c.get('revision_ids') or [])), None)
    return f"c{chunk['revision_ids'].index(revision) + 1}" if chunk else None


def own(run, trace, decision):
    """The items a decision is about: its revision, that revision's requirement ID and group (and, for the writer, the
    members it wrote from)."""
    record = saved_record(run, decision['revision_id'])
    items = {decision['revision_id'], record.get('requirement_id'), record.get('group_id')}
    if decision['step'] == 'need_statement': items |= set(trace['lineage'])
    return items - {None}


def about_row(row, items, said='', statement='', member=None, known=()):
    """A model's output row is about the item when an ID it names is the item's; a row under aliases (or naming no
    item of the run), when its member alias, verbatim reason or written statement is the item's."""
    named = [row[f] for f in ROW_FIELDS if isinstance(row.get(f), str) and (not known or row[f] in known)]
    if named: return bool(set(named) & items)
    return bool((member and member in (row.get('member_ids') or [])) or (len(said) >= 20 and folded(row.get('rationale')) == said)
                or (statement and folded(row.get('statement')) == statement))


def translated(run, call_id, pointer):
    """A base-review row as saved with real IDs: the model saw aliases (N1, B1)."""
    for entry in run['stakeholder_audit'].values():
        for attempt in (entry.get('attempts') or []) if isinstance(entry, dict) else []:
            if (attempt.get('call_ids') or [None])[-1] == call_id:
                node = attempt.get('output') or attempt.get('parsed')
                for key in pointer.split('/')[2:]: node = node[int(key)] if isinstance(node, list) else node[key]
                return node
    return None


def check_links(client, run, revision):
    trace = linked(client, run, revision)
    calls = {c['call_id'] for c in run['model_calls']}
    for kind, identifier, entry in entries(trace):
        assert entry['links'], (kind, identifier)
        for link in entry['links']:
            document, node, trail = follow(client, link)
            if '/stages/' in link['file'] and not link['file'].endswith('/stages/adjudication'):
                # A step link opens a result the step saved, never the current state under the step's name.
                assert document['snapshot_kind'] == 'stage_checkpoint', link
            if '/calls/' in link['file']:
                assert document['call_id'] == link['file'].rsplit('/', 1)[1]
                if link['pointer'] in ('', '/output') or kind in {'case', 'outcome'}: continue
                if kind == 'origin': assert folded(node.get('statement')) == folded(entry['statement']), link
                else:
                    record = saved_record(run, entry['revision_id'])
                    node = translated(run, document['call_id'], link['pointer']) or node
                    assert about_row(node, own(run, trace, entry), folded(entry['reason']),
                                     folded(record.get('need_statement')) if kind == 'need_statement' else '',
                                     alias(run, entry['revision_id']) if kind == 'grouping' else None,
                                     {i for r in run['requirements'] for i in (r['revision_id'], r['requirement_id'], r.get('group_id')) if i}), (kind, link, node)
            elif kind == 'source':
                # The unit sits at its span in the source's text, and the mark covers the quotation.
                unit = node
                if unit['span']: assert document['text'][unit['span'][0]:unit['span'][1]] == unit['content']
                start, end = link['quote_span']
                assert folded(unit['content'][start:end]) == folded(entry['quote'])
            elif kind == 'origin' and '/stages/deliberation' in link['file']:
                # An observation the discussion gave a revision it wrote: the outcome wrote that revision.
                assert any(identifier in (saved_record(run, r).get('observation_ids') or []) for r in trail[-1]['result_revision_ids'])
            elif kind == 'origin':
                assert names(trail, {identifier}), link
            elif kind == 'case':
                assert names(trail, {identifier})
            elif kind == 'outcome':
                assert trail[-1].get('action_id') == identifier[1] and any(n.get('case_id') == identifier[0] for n in trail if isinstance(n, dict))
            elif kind == 'grouping':
                # The chunk's grouping row, at the group that holds the revision.
                row = next(n for n in trail if isinstance(n, dict) and n.get('action') == 'grouping_chunk')
                assert entry['revision_id'] in row['inputs']
                chunk = next(c for c in run['consolidation_chunks'].values() if c.get('chunk_key') == row['chunk_key'])
                group = int(link['pointer'].rsplit('/', 1)[1])
                assert alias(run, entry['revision_id']) in chunk['result']['groups'][group]['member_ids']
            elif kind == 'need':
                assert trail[-1]['revision_id'] == identifier
            else:
                assert names(trail, own(run, trace, entry)), (kind, link)
    return trace, calls


def test_every_entry_of_every_produced_need_links_to_the_place_it_was_traced_from(finished):
    store, run = finished
    client = TestClient(app)
    for revision in need_trace.produced_needs(run):
        trace, calls = check_links(client, run, revision)
        # Each decision made by a model links to the calls that made it.
        for decision in trace['decisions']:
            linked_calls = {l['file'].rsplit('/', 1)[1] for l in decision['links'] if '/calls/' in l['file']}
            assert linked_calls == set(decision['call_ids']) and linked_calls <= calls
        steps = {d['step']: d for d in trace['decisions']}
        # The proposals were checked against their sources in step 5; the need written from them in step 6.
        checks = [d for d in trace['decisions'] if d['step'] == 'source_check']
        proposals = [d for d in checks if not saved_record(run, d['revision_id']).get('parent_revision_ids')]
        assert proposals and all(d['links'][0]['file'].endswith('/stages/verification') for d in proposals)
        for step, row in (('proposal_support', 'proposal_support/decisions'), ('fa_test', 'profile_scope/decisions'),
                          ('record_test', 'profile_scope/record_decisions')):
            assert steps[step]['links'][0]['file'].endswith('/stages/consolidation')
            assert steps[step]['links'][0]['pointer'].startswith(f'/results/need_steps/{row}/')
        for origin in trace['origin']:
            link = origin['links'][0]
            assert link['file'].endswith('/stages/elicitation') and link['pointer'].startswith('/results/observations/')
            assert follow(client, link)[1]['observation_id'] == origin['observation_id']
        # A discussion links to every model call it made.
        for case in trace['discussion']:
            assert [l['file'].rsplit('/', 1)[1] for l in case['links'] if '/calls/' in l['file']] == case['call_ids']


def test_every_phrase_of_the_reviewer_card_links_to_its_entry(finished):
    store, run = finished
    client = TestClient(app)
    for revision in need_trace.produced_needs(run):
        trace = linked(client, run, revision)
        lines = trace['summary'].split('\n')
        assert [f"{line['label']}: " + ''.join(p['text'] for p in line['parts']) for line in trace['summary_parts']] == lines
        refs = [p['ref'] for line in trace['summary_parts'] for p in line['parts'] if p['ref'] and p['ref'] != '/completeness']
        assert refs
        reported = {'the quote': 'proposal_support', 'it helps users': 'fa_test', 'record test': 'record_test',
                    'in the base profile': ('classification', 'base_review')}
        for part in (p for line in trace['summary_parts'] if line['label'] == 'Checks' for p in line['parts'] if p['ref']):
            step = trace['decisions'][int(part['ref'].rsplit('/', 1)[1])]['step']
            wanted = next((v for k, v in reported.items() if k in part['text']), None)
            if wanted: assert step in (wanted if isinstance(wanted, tuple) else (wanted,)), (part, step)
        for ref in refs:
            entry = trace
            for key in ref.split('/')[1:]: entry = entry[int(key)] if isinstance(entry, list) else entry[key]
            assert entry['links']


def test_a_revision_the_discussion_wrote_links_to_its_own_judgements(setup):
    # A revision keeps its parent's requirement ID: its scope judgements are on its record in the step 7 file, not
    # the parent's rows in step 6.
    store, original, _, _ = setup
    client = full_client(); client.dialogue = RevisingDialogue()
    run = new_fa_run(store, original)
    engine.execute_run(store, run['run_id'], client)
    saved = store.get_run(run['run_id'])
    made = next(o for c in saved['deliberations'] for o in c['mediation']['outcomes'] if o['action'] == 'revise')['result_revision_ids'][0]
    trace, _ = check_links(TestClient(app), saved, made)
    steps = {d['step']: d for d in trace['decisions']}
    for step in ('fa_test', 'assessment'):
        link = steps[step]['links'][0]
        assert '/stages/consolidation' not in link['file'] or '/need_steps/' not in link['pointer']
        _, _, trail = follow(TestClient(app), link)
        assert any(isinstance(n, dict) and n.get('revision_id') == made for n in trail)
    made_by = next(o for c in trace['discussion'] for o in c['outcomes'] if made in o['result_revision_ids'])
    assert made_by['links'][0]['file'].endswith('/stages/deliberation')


def test_a_need_set_aside_for_its_chain_links_to_the_missing_link(setup):
    store, original, _, _ = setup
    run = new_fa_run(store, original)
    engine.execute_run(store, run['run_id'], full_client())
    need = store.get_run(run['run_id'])['active_revision_ids'][0]
    def drop(r):
        step = copy.deepcopy(r['need_steps']['profile_scope'])
        for row in step['record_decisions']: row['need_id'] = 'req-another'
        r['need_steps']['profile_scope'] = step
    store.mutate(run['run_id'], None, 'fixture_drop_record_test', drop, parts=True)
    need_trace.record_traceability(store, run['run_id'])
    saved = store.get_run(run['run_id'])
    trace = linked(TestClient(app), saved, need)
    aside = next(d for d in trace['decisions'] if d['step'] == 'set_aside')
    _, node, _ = follow(TestClient(app), aside['links'][0])
    assert aside['links'][0]['file'].endswith('/traceability') and not node['solid'] and node['missing']


def test_a_trial_derived_from_an_older_run_links_to_the_calls_of_the_run_that_made_them(setup):
    store, original, _, _ = setup
    source = build_source(store, original, strip=False)
    derived = trial(store, source)
    assert derived['status'] == 'awaiting_human', derived['diagnostics']
    client = TestClient(app)
    for revision in derived['active_revision_ids']:
        trace, _ = check_links(client, derived, revision)
        extraction = [l for o in trace['origin'] for l in o['links'] if '/calls/' in l['file']]
        assert extraction and all(l['file'].startswith(f"/runs/{source['run_id']}/calls/") for l in extraction)
        assert any(l['file'].endswith('/stages/base_review') for d in trace['decisions'] if d['step'] == 'base_review' for l in d['links'])


def test_the_step_download_is_unchanged_and_unknown_files_are_not_found(finished):
    store, run = finished
    client = TestClient(app)
    for stage, saved in run['stage_results'].items():
        if stage in engine.STAGE_RESULT_FIELDS and stage not in {'acquisition', 'decomposition', 'elicitation'}:
            assert client.get(f"{API}/runs/{run['run_id']}/stages/{stage}").json()['results'] == saved
    current = client.get(f"{API}/runs/{run['run_id']}/stages/adjudication").json()
    assert current['snapshot_kind'] == 'current_saved_state' and current['results']['requirements'] == run['requirements']
    assert client.get(f"{API}/runs/{run['run_id']}/calls/none").status_code == 404
    assert client.get(f"{API}/sources/srcv-none/document").status_code == 404


def test_a_quotation_is_found_where_the_source_check_finds_it():
    from requirement_reuse_service.workflow.trace_links import quote_span
    content = 'Title.  The dataset  has\na licence. The dataset has a licence.'
    assert quote_span(content, 'The dataset has a licence.', 36) == [36, 62]
    assert quote_span(content, 'The dataset has a licence.') == [36, 62]
    assert quote_span(content, 'The dataset has a licence.', 3) == [36, 62]
    assert quote_span(content, 'dataset has a licence') == [40, 61]
    assert quote_span('Title.  The dataset  has\na licence.', 'The dataset has a licence.') == [8, 35]
    assert quote_span(content, 'Not there.') is None and quote_span(content, '') is None


# Review of the links (27 Oct).

def call_row(client, link):
    _, node, _ = follow(client, link)
    return node


def test_a_call_link_opens_the_row_of_its_own_proposal_when_the_batch_gives_one_reason(finished):
    # The scripted support check gives every proposal of a batch the same reason; the row is found by ID first.
    store, run = finished
    client = TestClient(app)
    trace = linked(client, run, run['active_revision_ids'][0])
    decisions = [d for d in trace['decisions'] if d['step'] == 'proposal_support']
    assert len({d['reason'] for d in decisions}) == 1 and len({d['revision_id'] for d in decisions}) > 1
    for decision in decisions:
        link = next(l for l in decision['links'] if '/calls/' in l['file'])
        assert call_row(client, link)['proposal_id'] == decision['revision_id']


def test_a_record_judgement_never_links_to_a_step_that_did_not_run(setup):
    # Base review did not run: the step 6a download serves the current state, which is not a base review result.
    store, original, _, _ = setup
    client = full_client(); client.dialogue = RevisingDialogue()
    run = new_fa_run(store, original)
    engine.execute_run(store, run['run_id'], client)
    saved = store.get_run(run['run_id'])
    assert 'base_review' not in saved['stage_results']
    made = next(o for c in saved['deliberations'] for o in c['mediation']['outcomes'] if o['action'] == 'revise')['result_revision_ids'][0]
    trace = linked(TestClient(app), saved, made)
    assessment = next(d for d in trace['decisions'] if d['step'] == 'assessment')
    assert assessment['links'][0]['file'].endswith('/stages/deliberation')
    assert not any(l['file'].endswith('/stages/base_review') for _, _, e in entries(trace) for l in e['links'])


def test_a_grouping_link_opens_the_chunks_grouping_row_at_the_group_that_holds_it(finished):
    # A salvaged chunk has a salvage row under the same key before its grouping row, and groups that give no reason.
    store, run = finished
    def salvage(r):
        chunk = next(c for c in r['consolidation_chunks'].values() if c.get('block_key') == 'underlying_needs')
        groups = chunk['result']['groups']
        chunk['result']['groups'] = [{'member_ids': ['c99'], 'join_group_id': None, 'rationale': ''}, *groups]
        for steps in (r['need_steps'], r['stage_results']['consolidation']['need_steps']):
            audit = steps['grouping']['audit']
            row = next(a for a in audit if a['action'] == 'grouping_chunk')
            row['rationales'] = ['', *row['rationales']]
            audit.insert(0, {'action': 'semantic_grouping_salvaged', 'chunk_key': row['chunk_key'], 'inputs': row['inputs'],
                             'reason': 'fixture', 'model_call_ids': row['model_call_ids']})
    store.mutate(run['run_id'], None, 'fixture_salvage', salvage, parts=True)
    saved = store.get_run(run['run_id'])
    client = TestClient(app)
    trace = linked(client, saved, saved['active_revision_ids'][0])
    groupings = [d for d in trace['decisions'] if d['step'] == 'grouping']
    assert groupings
    for decision in groupings:
        link = decision['links'][0]
        _, node, trail = follow(client, link)
        assert trail[-3]['action'] == 'grouping_chunk' and link['pointer'].endswith('/rationales/1')
    check_links(client, saved, saved['active_revision_ids'][0])


def test_a_proposal_the_support_check_rehashed_links_to_its_row(finished):
    # The check re-hashes a proposal whose obligation its quote does not state: the row keeps the old proposal ID.
    store, run = finished
    proposal = next(d['revision_id'] for d in need_trace.need_trace(need_trace.TraceIndex(store, run), run['active_revision_ids'][0])['decisions']
                    if d['step'] == 'proposal_support')
    def rehash(r):
        for steps in (r['need_steps'], r['stage_results']['consolidation']['need_steps']):
            row = next(x for x in steps['proposal_support']['decisions'] if x['proposal_id'] == proposal)
            row.update(proposal_id='rev-before-the-check', revision_id=proposal)
    store.mutate(run['run_id'], None, 'fixture_rehash', rehash, parts=True)
    saved = store.get_run(run['run_id'])
    trace = linked(TestClient(app), saved, saved['active_revision_ids'][0])
    decision = next(d for d in trace['decisions'] if d['step'] == 'proposal_support' and d['revision_id'] == proposal)
    assert '/need_steps/proposal_support/decisions/' in decision['links'][0]['pointer']
    assert call_row(TestClient(app), decision['links'][0])['revision_id'] == proposal


def test_an_outcome_saved_after_the_step_7_file_links_to_the_current_run(setup):
    store, original, _, _ = setup
    client = full_client(); client.dialogue = RevisingDialogue()
    run = new_fa_run(store, original)
    engine.execute_run(store, run['run_id'], client)
    def earlier(r):
        for case in r['stage_results']['deliberation']['deliberations']:
            case['mediation']['outcomes'] = [o for o in case['mediation']['outcomes'] if o['action'] != 'revise']
        # Another discussion first, and in the revised need's discussion an outcome under the same action ID that
        # wrote another revision: the link must find the case and the outcome by what they are about.
        case = r['deliberations'][0]
        revise = next(o for o in case['mediation']['outcomes'] if o['action'] == 'revise')
        decoy = {**copy.deepcopy(revise), 'action': 'retain', 'result_revision_ids': ['rev-another'], 'rationale': 'Another outcome.'}
        case['mediation']['outcomes'].insert(0, decoy)
        other = {**copy.deepcopy(case), 'case_id': 'case-another', 'revision_ids': ['rev-another']}
        other['mediation'] = {**case['mediation'], 'outcomes': [decoy]}
        r['deliberations'].insert(0, other)
    store.mutate(run['run_id'], None, 'fixture_step7_before_revise', earlier, parts=True)
    saved = store.get_run(run['run_id'])
    made = next(o for c in saved['deliberations'] for o in c['mediation']['outcomes'] if o['action'] == 'revise')['result_revision_ids'][0]
    trace = linked(TestClient(app), saved, made)
    outcome = next(o for c in trace['discussion'] for o in c['outcomes'] if made in o['result_revision_ids'])
    link = outcome['links'][0]
    assert link['file'] == f"/runs/{saved['run_id']}?audit=false" and link['pointer'] == '/deliberations/1/mediation/outcomes/1'
    _, node, _ = follow(TestClient(app), link)
    assert node['action'] == 'revise' and made in node['result_revision_ids']


# Second review of the links (27 Oct).

def test_an_overruled_judgement_links_to_the_call_that_gave_the_judgement_kept(setup):
    # Every first judgement fails and every second one, made alone, passes: the record keeps the second verdict and
    # the confirmation keeps the first. Each entry opens the row of the call that gave its own judgement.
    store, original, _, _ = setup
    client = full_client(); base = client.generate_structured; seen = collections.Counter()
    def generate(**kw):
        answer = base(**kw); name = kw['output_model'].__name__
        if name not in {'ProposalSupport', 'ProfileScope'}: return answer
        raw = answer.model_dump(mode='json')
        for row in raw['proposals' if name == 'ProposalSupport' else 'decisions']:
            key = (name, row.get('proposal_id') or row.get('need_id')); seen[key] += 1
            first = seen[key] == 1
            if name == 'ProposalSupport':
                row.update(rationale=('FIRST judgement: the quote does not support it.' if first else 'SECOND judgement: the quote supports it.'),
                           **({'support': 'not_supported', 'supporting_evidence_ids': []} if first else {}))
            elif first: row.update(catalogue_level=False, record_resource='none', record_statement='', rationale='FIRST judgement: no catalogue record states it.')
            else: row.update(rationale='SECOND judgement: a dataset record states it.')
        return kw['output_model'].model_validate(raw)
    client.generate_structured = generate
    run = engine.new_run(store, RunRequest(snapshot_id=original['snapshot_id'], strategy='multi_agent', role_ids=['consumer_discovery', 'publisher_feasibility'],
                                           stakeholder_workflow='fa_mediated', discussion='automatic', scoping='off', base_check=False))
    engine.execute_run(store, run['run_id'], client)
    saved = store.get_run(run['run_id'])
    api = TestClient(app)
    checked = collections.Counter()
    for revision in saved['active_revision_ids']:
        trace = linked(api, saved, revision)
        for decision in trace['decisions']:
            if decision['step'] not in {'proposal_support', 'proposal_support_confirmation', 'record_test', 'record_test_confirmation'}: continue
            calls = [l for l in decision['links'] if '/calls/' in l['file']]
            assert calls, decision
            said = follow(api, calls[0])[1]['rationale']
            # The decision says what the second judgement said; the disputed confirmation, what the first said.
            assert said.startswith('FIRST' if decision['step'].endswith('_confirmation') else 'SECOND'), (decision['step'], said)
            assert said == decision['reason']
            checked[decision['step']] += 1
    assert checked['proposal_support'] and checked['proposal_support_confirmation'] and checked['record_test'] and checked['record_test_confirmation']


def test_the_card_links_a_label_set_by_base_review_to_the_base_review():
    trace = {'revision_id': 'r1', 'requirement_id': 'q1', 'statement': 'Users can find X.', 'flags': ['covered_by_base'],
             'sources': [], 'origin': [], 'discussion': [], 'completeness': {'missing': []},
             'decisions': [{'step': 'classification', 'decision': 'domain'}, {'step': 'base_review', 'decision': 'restates_base (flag_added)'}]}
    part = next(p for line in need_trace.summary_parts(trace) for p in line['parts'] if p['text'] == 'already in the base profile')
    assert part['ref'] == '/decisions/1'
    trace['decisions'][0]['decision'] = 'generic'
    part = next(p for line in need_trace.summary_parts(trace) for p in line['parts'] if p['text'] == 'already in the base profile')
    assert part['ref'] == '/decisions/0'


def test_a_need_no_search_chunk_matched_links_to_every_chunk_of_its_search(setup):
    # The base search offers the catalogue in chunks, each answered by its own call; when no chunk matches, the
    # decision ("no matching entry") sums them all up.
    from test_need_trace_v1_shapes import client_for
    store, original, _, _ = setup
    run = new_fa_run(store, original, base_profile_id='dcat-ap-1.1.0', base_review='expert_v1')
    engine.execute_run(store, run['run_id'], client_for('revise'))
    saved = store.get_run(run['run_id'])
    index = need_trace.TraceIndex(store, saved)
    checked = 0
    for revision in need_trace.produced_needs(saved):
        trace = linked(TestClient(app), saved, revision)
        decision = next((d for d in trace['decisions'] if d['step'] == 'classification'), None)
        if not decision or decision['decision'] != 'domain': continue
        chunks = [h for step in ('classification', 'base_search') for h in index.chunk_rows.get((step, '', trace['requirement_id'])) or []]
        assert len(chunks) > 1
        assert decision['call_ids'] == list(dict.fromkeys(c for h in chunks for c in h[3]))
        assert {l['file'].rsplit('/', 1)[1] for l in decision['links'] if '/calls/' in l['file']} == set(decision['call_ids'])
        checked += 1
    assert checked
