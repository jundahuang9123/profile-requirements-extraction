"""D5 scoring unit: families only group kept needs; a family is headed by a member need."""
import json
from test_resume_discussions import setup
from test_rq1_profile_scope import variants
from test_rq1_need_derived_export import derived
from test_rq1_need_grouping import NeedsClient
from requirement_reuse_service.workflow import needs
from requirement_reuse_service.workflow.evaluation import workflow_metrics

STATEMENTS = {
    'need-0': 'Users can find datasets by the area they cover.',
    'need-1': 'Users can see the bounding box of a dataset.',
    'need-2': 'Users can know the period a dataset covers.',
    'need-3': 'Users can find datasets by the period they cover.',
    'need-4': 'Users can know the publisher of a dataset.',
}
RANKS = {'need-1': (1, 0), 'need-2': (2, 1), 'need-0': (3, 1), 'need-3': (4, 1), 'need-4': (5, 1)}


class FamilyClient(NeedsClient):
    def __init__(self, mode='normal'):
        super().__init__(); self.mode = mode
    def generate_structured(self, **kwargs):
        if kwargs['output_model'].__name__ != 'SemanticGrouping':
            return super().generate_structured(**kwargs)
        data = json.loads(kwargs['user']); self.calls.append(('SemanticGrouping', data))
        assert 'one catalogue element would serve' in kwargs['system']
        if self.mode == 'invalid':  # loses a candidate on both generations
            return kwargs['output_model'].model_validate({'groups': [{'member_ids': list(data['candidates'])[:1]}]})
        area = [c for c, row in data['candidates'].items() if 'area' in row['statement'] or 'bounding' in row['statement']]
        rest = [c for c in data['candidates'] if c not in area]
        return kwargs['output_model'].model_validate({'groups': [{'member_ids': ids} for ids in (area, rest) if ids]})


def kept_needs(setup):
    store, run, _, made = variants(setup, STATEMENTS)
    run['request']['consolidation'] = 'semantic'
    for need in made:
        need.rank, order = RANKS[need.requirement_id]
        need.rank_keys = {'support_order': order}
    made[4].verification = {'status': 'fail', 'links': [], 'message': 'Offline source failure.'}
    return store, run, made


def test_families_group_kept_needs_headed_by_best_ranked_member(setup):
    store, run, made = kept_needs(setup); client = FamilyClient()
    families = needs.need_families(store, run, made, client, {})
    assert [f['rank'] for f in families] == [1, 2]
    assert [(f['head_need_id'], f['member_need_ids']) for f in families] == [
        ('need-1', ['need-1', 'need-0']), ('need-2', ['need-2', 'need-3'])]
    # No family text is written: the statement is the head member's need.
    assert [f['statement'] for f in families] == [STATEMENTS['need-1'], STATEMENTS['need-2']]
    assert families[0]['rank_keys']['support_order'] == 0 and families[1]['rank_keys']['members'] == 2
    grouped = [i for f in families for i in f['member_need_ids']]
    assert sorted(grouped) == ['need-0', 'need-1', 'need-2', 'need-3']  # each kept need exactly once
    offered = [i for name, data in client.calls for i in data['candidates'].values()]
    assert STATEMENTS['need-4'] not in [row['statement'] for row in offered]
    step = store.get('run', run['run_id'])['need_steps']['families']
    assert step['family_count'] == 2 and step['not_grouped_need_ids'] == ['need-4']
    assert step['grouping_unavailable_chunks'] == 0 and step['policy_version'] == 'rq1-need-families-v2'
    saved = store.get('run', run['run_id'])['consolidation_chunks']
    before = len(client.calls)
    assert needs.need_families(store, run, made, client, saved) == families
    assert len(client.calls) == before  # resume reuses the grouping checkpoint


def test_invalid_family_grouping_keeps_singletons(setup):
    store, run, made = kept_needs(setup); client = FamilyClient('invalid')
    families = needs.need_families(store, run, made, client, {})
    assert [f['member_need_ids'] for f in families] == [['need-1'], ['need-2'], ['need-0'], ['need-3']]
    saved=store.get('run', run['run_id'])['need_steps']['families']
    assert saved['grouping_unavailable_chunks'] == 0
    assert any(event['action']=='semantic_grouping_salvaged' for event in saved['audit'])
    assert sum(name == 'SemanticGrouping' for name, _ in client.calls) == 2


def test_exact_consolidation_makes_singleton_families_without_calls(setup):
    store, run, made = kept_needs(setup); run['request']['consolidation'] = 'exact'
    client = FamilyClient()
    families = needs.need_families(store, run, made, client, {})
    assert len(families) == 4 and all(len(f['member_need_ids']) == 1 for f in families)
    assert client.calls == []


def test_export_lists_ranked_families_with_member_statements(setup):
    store, run, _ = derived(setup)
    export = needs.needs_export(store, run['run_id'])
    assert len(export['families']) == 1
    family, need = export['families'][0], export['needs'][0]
    assert family['rank'] == 1 and family['head_need_id'] == need['requirement_id']
    assert family['statement'] == family['members'][0]['statement'] == need['need_statement']
    assert run['machine_snapshot']['need_steps']['families']['family_count'] == 1
    counts = workflow_metrics(run)['needs']['counts']
    assert counts['families'] == 1 and counts['after_profile_scope'] == 1
    assert run['need_steps']['profile_scope']['retained_count'] == 1


def test_group_accounting_salvage_preserves_valid_groups_and_keeps_others_singleton():
    from types import SimpleNamespace
    from requirement_reuse_service.workflow.models import CandidateGroup, SemanticGrouping
    from requirement_reuse_service.workflow.semantic_consolidation import (
        FAMILY_POLICY, accounting_errors, salvage_independent_groups)
    candidates={f'c{i}':SimpleNamespace(revision_id=str(i),normalized_statement=f'Users can find need {i}.')
                for i in range(1,5)}
    answer=SemanticGrouping(groups=[
        CandidateGroup(member_ids=['c1','c2'],rationale='Same need.'),
        CandidateGroup(member_ids=['c3','unknown-id'],rationale='Malformed but separable.'),
        CandidateGroup(member_ids=['c4','c4'],rationale='Repeated ID.')])
    salvaged,audit=salvage_independent_groups(answer,candidates,{},FAMILY_POLICY)
    assert salvaged is not None and accounting_errors(salvaged,candidates,{},FAMILY_POLICY)==[]
    memberships=[group.member_ids for group in salvaged.groups]
    assert ['c1','c2'] in memberships
    assert ['c3'] in memberships and ['c4'] in memberships
    assert all(sum(group.count(item) for group in memberships)==1 for item in candidates)
    assert any(row['action']=='preserved_valid_group' and row['unknown_member_ids']==['unknown-id'] for row in audit['groups'])
