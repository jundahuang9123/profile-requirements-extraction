"""rq1-need-semantic-grouping-v3: a need the resource guard kept apart from its grouping shows that decision, with its
reason and a link to the grouping step's audit row (see test_need_resource_guard)."""
import copy
from test_need_trace_v1 import finished, active_trace  # noqa: F401  (pytest fixture)
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from requirement_reuse_service.workflow.trace_links import link_trace


def test_the_trace_shows_a_need_kept_apart_by_resource(finished):
    store, run = finished
    index, trace = active_trace(store, run)
    member = next(d['revision_id'] for d in trace['decisions'] if d['step'] == 'need_statement')
    event = {'action': 'kept_apart_by_resource', 'policy_version': 'rq1-need-semantic-grouping-v3',
             'inputs': sorted([member, 'rev-other']), 'reason': 'Grouped needs about different resources (catalogue, dataset).',
             'parts': [{'resource': 'catalogue', 'revision_ids': [member]}, {'resource': 'dataset', 'revision_ids': ['rev-other']}]}
    def add(r):
        for steps in (r['need_steps'], r['stage_results']['consolidation']['need_steps']):
            steps['grouping']['audit'] = [*steps['grouping'].get('audit', []), copy.deepcopy(event)]
    store.mutate(run['run_id'], None, 'fixture_kept_apart', add, parts=True)
    run = store.get_run(run['run_id'])
    index, trace = active_trace(store, run)
    [kept] = [d for d in trace['decisions'] if d['step'] == 'resource_guard']
    assert kept['revision_id'] == member and kept['decision'] == 'kept apart from rev-other (about catalogue)'
    assert kept['reason'] == event['reason'] and kept['policy_version'] == 'rq1-need-semantic-grouping-v3'
    grouping = index.groupings[member]
    assert 'rev-other' not in grouping['members']
    trace = link_trace(index, trace)
    [kept] = [d for d in trace['decisions'] if d['step'] == 'resource_guard']
    assert kept['links'][0]['file'].endswith('/stages/consolidation')
    assert kept['links'][0]['pointer'] == f"/results/need_steps/grouping/audit/{len(run['need_steps']['grouping']['audit']) - 1}"
