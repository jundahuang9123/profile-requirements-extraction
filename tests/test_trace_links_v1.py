"""rq1-need-trace-v1, trace links (Junda, 27 Oct): every entry of a need's trace links to where it was traced from:
the result file of the step that made it at the traced row (a JSON pointer), a model call, or the source document with
the quotation marked. Each test follows the links over the API, as the workbench does."""
import copy
from fastapi.testclient import TestClient
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_need_trace_v1 import finished, full_client  # noqa: F401  (pytest fixture)
from test_need_trace_v1_shapes import RevisingDialogue, build_source, new_fa_run, saved_record, trial
from requirement_reuse_service.main import app
from requirement_reuse_service.workflow import engine, need_trace

API = '/api/rq1/v2'
IDS = ('revision_id', 'need_id', 'proposal_id', 'group_id', 'observation_id', 'case_id', 'action_id')


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
        for outcome in case['outcomes']: yield 'outcome', outcome['action_id'], outcome


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


def check_links(client, run, revision):
    trace = linked(client, run, revision)
    record = saved_record(run, revision)
    wanted = {revision, trace['requirement_id'], *trace['lineage'], record.get('group_id')} - {None}
    calls = {c['call_id'] for c in run['model_calls']}
    for kind, identifier, entry in entries(trace):
        assert entry['links'], (kind, identifier)
        for link in entry['links']:
            document, node, trail = follow(client, link)
            if '/calls/' in link['file']:
                assert document['call_id'] == link['file'].rsplit('/', 1)[1]
            elif kind == 'source':
                # The unit sits at its span in the source's text, and the mark covers the quotation.
                unit = node
                if unit['span']: assert document['text'][unit['span'][0]:unit['span'][1]] == unit['content']
                start, end = link['quote_span']
                assert ' '.join(unit['content'][start:end].split()) == ' '.join(entry['quote'].split())
            elif kind == 'origin':
                assert names(trail, {identifier}) or names(trail, wanted)
            elif kind in {'case', 'outcome'}:
                assert names(trail, {identifier})
            elif kind == 'grouping':
                assert trail[-1] == node and (isinstance(node, str) or names(trail, wanted) or node.get('action') == 'grouping_chunk')
            else:
                assert names(trail, wanted), (kind, link)
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
        assert all(o['links'][0]['file'].endswith('/stages/elicitation') for o in trace['origin'])


def test_every_phrase_of_the_reviewer_card_links_to_its_entry(finished):
    store, run = finished
    client = TestClient(app)
    for revision in need_trace.produced_needs(run):
        trace = linked(client, run, revision)
        lines = trace['summary'].split('\n')
        assert [f"{line['label']}: " + ''.join(p['text'] for p in line['parts']) for line in trace['summary_parts']] == lines
        refs = [p['ref'] for line in trace['summary_parts'] for p in line['parts'] if p['ref'] and p['ref'] != '/completeness']
        assert refs
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
