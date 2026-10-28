"""rq1-need-semantic-grouping-v3: a need the resource guard kept apart from its grouping shows that decision, with its
reason and a link to the grouping step's audit row, and is no longer shown as merged with the other part
(see test_need_resource_guard)."""
import copy
from test_need_trace_v1 import finished, active_trace  # noqa: F401  (pytest fixture)
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from requirement_reuse_service.workflow.trace_links import link_trace


def test_the_trace_shows_a_need_kept_apart_by_resource(finished):
    store, run = finished
    [chunk] = [c for c in run['consolidation_chunks'].values() if c.get('block_key') == 'underlying_needs']
    a, b = chunk['revision_ids']
    index, trace = active_trace(store, run)
    assert ('grouping', a, f'merged with {b}') in [(d['step'], d['revision_id'], d['decision']) for d in trace['decisions']]
    other = {'action': 'kept_apart_by_resource', 'policy_version': 'rq1-need-semantic-grouping-v3', 'inputs': ['rev-x', 'rev-y'],
             'reason': 'Another split.', 'parts': [{'resources': ['dataset'], 'revision_ids': ['rev-x']},
                                                   {'resources': ['distribution'], 'revision_ids': ['rev-y']}]}
    event = {'action': 'kept_apart_by_resource', 'policy_version': 'rq1-need-semantic-grouping-v3', 'inputs': sorted([a, b]),
             'reason': 'Grouped needs about different resources (catalogue; catalogue record).',
             'parts': [{'resources': ['catalogue'], 'revision_ids': [a]}, {'resources': ['catalogue record'], 'revision_ids': [b]}]}
    def add(r):
        for steps in (r['need_steps'], r['stage_results']['consolidation']['need_steps']):
            steps['grouping']['audit'] = [*steps['grouping'].get('audit', []), copy.deepcopy(other), copy.deepcopy(event)]
    store.mutate(run['run_id'], None, 'fixture_kept_apart', add, parts=True)
    run = store.get_run(run['run_id'])
    index, trace = active_trace(store, run)
    assert not [d for d in trace['decisions'] if d['step'] == 'grouping']
    kept = {d['revision_id']: d for d in trace['decisions'] if d['step'] == 'resource_guard'}
    assert kept[a]['decision'] == f'kept apart from {b} (about catalogue)'
    assert kept[b]['decision'] == f'kept apart from {a} (about catalogue record)'
    assert kept[a]['reason'] == event['reason'] and kept[a]['policy_version'] == 'rq1-need-semantic-grouping-v3'
    assert index.groupings[a]['members'] == [a] and index.groupings[b]['members'] == [b]
    trace = link_trace(index, trace)
    at = len(run['need_steps']['grouping']['audit']) - 1
    for d in trace['decisions']:
        if d['step'] != 'resource_guard': continue
        assert d['links'][0]['file'].endswith('/stages/consolidation')
        assert d['links'][0]['pointer'] == f'/results/need_steps/grouping/audit/{at}'


def test_a_need_naming_no_resource_says_so(finished):
    store, run = finished
    [chunk] = [c for c in run['consolidation_chunks'].values() if c.get('block_key') == 'underlying_needs']
    a, b = chunk['revision_ids']
    event = {'action': 'kept_apart_by_resource', 'policy_version': 'rq1-need-semantic-grouping-v3', 'inputs': sorted([a, b]),
             'reason': 'Grouped needs about different resources.', 'parts': [{'resources': ['dataset'], 'revision_ids': [a]},
                                                                            {'resources': [], 'revision_ids': [b]}]}
    def add(r):
        for steps in (r['need_steps'], r['stage_results']['consolidation']['need_steps']):
            steps['grouping']['audit'] = [*steps['grouping'].get('audit', []), copy.deepcopy(event)]
    store.mutate(run['run_id'], None, 'fixture_kept_apart', add, parts=True)
    index, trace = active_trace(store, store.get_run(run['run_id']))
    kept = {d['revision_id']: d['decision'] for d in trace['decisions'] if d['step'] == 'resource_guard'}
    assert kept == {a: f'kept apart from {b} (about dataset)', b: f'kept apart from {a} (it names no resource)'}


def test_the_trace_shows_a_group_the_writer_wrote_member_by_member(finished):
    store, run = finished
    [chunk] = [c for c in run['consolidation_chunks'].values() if c.get('block_key') == 'underlying_needs']
    a, b = chunk['revision_ids']
    need = run['active_revision_ids'][0]
    split = {'action': 'split_unwritten_group', 'policy_version': 'rq1-need-statement-v4', 'group_id': 'group-fixture',
             'inputs': sorted([a, b]), 'reason': 'g: name the resource its members are about (catalogue) in the need.', 'rewrites': []}
    kept = {'action': 'keep_unwritten_need', 'policy_version': 'rq1-need-statement-v4', 'group_id': 'group-fixture-kept',
            'inputs': [a], 'outputs': [need], 'reason': 'Writer output unavailable: (catalogue).', 'rewrites': []}
    def add(r):
        for steps in (r['need_steps'], r['stage_results']['consolidation']['need_steps']):
            steps['need_statement']['events'] = [*steps['need_statement']['events'], copy.deepcopy(split), copy.deepcopy(kept)]
    store.mutate(run['run_id'], None, 'fixture_writer_split', add, parts=True)
    run = store.get_run(run['run_id'])
    index, trace = active_trace(store, run)
    splits = {d['revision_id']: d for d in trace['decisions'] if d['step'] == 'writer_split'}
    assert splits[a]['decision'] == f'written apart from {b}' and splits[b]['decision'] == f'written apart from {a}'
    assert splits[a]['reason'] == split['reason'] and splits[a]['policy_version'] == 'rq1-need-statement-v4'
    # A writing event without a critic row gives its own reason.
    [unwritten] = [d for d in trace['decisions'] if d['step'] == 'need_statement' and d['decision'].startswith('keep_unwritten_need')]
    assert unwritten['reason'] == kept['reason']
    trace = link_trace(index, trace)
    at = len(run['need_steps']['need_statement']['events']) - 2
    for d in trace['decisions']:
        if d['step'] == 'writer_split':
            assert d['links'][0]['pointer'] == f'/results/need_steps/need_statement/events/{at}'
