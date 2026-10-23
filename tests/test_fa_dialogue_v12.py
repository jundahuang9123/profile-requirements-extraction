"""Synthetic tests of the rule added in rq1-fa-dialogue-v12: no evaluation answers or live generation.

Whole cases with the live habits are in test_fa_quirks.py; the salvage of one plan is in test_fa_dialogue_v3.py."""
import random
from copy import deepcopy
import pytest
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_fa_dialogue_v3 import built
from requirement_reuse_service.workflow import fa_discussion as fd


def test_policy_names():
    assert fd.BASE_POLICY=='rq1-fa-dialogue-v12' and fd.SALVAGE_POLICY=='rq1-fa-salvage-v2'
    assert fd.FIRST_SALVAGE_POLICY=='rq1-fa-salvage-v1' and fd.BASE_POLICY not in fd.FIRST_SALVAGE_POLICIES
    assert fd.FIRST_SALVAGE_POLICIES=={f'rq1-fa-dialogue-v{i}' for i in range(3,12)}


def broken_plan(rng,rids,link):
    """A plan of 1-5 actions of any kind, naming any of the needs or none, with or without the fields
    their rules ask for, and concern dispositions that may link nothing or unknown actions."""
    actions=[]
    for k in range(rng.randint(1,5)):
        kind=rng.choice(['retain','defer','set_aside','split','revise','add','covered_by_base'])
        parents=rng.choice([[],[rids[0]],[rids[-1]],list(rids)]) if kind!='add' else rng.choice([[],[rids[0]]])
        a={'action_id':rng.choice([f'A{k}','A1']),'action':kind,'parent_revision_ids':parents,'rationale':'r'}
        if kind in ('revise','add') and rng.random()<0.7:
            a.update(statement='Users can find the licence of a dataset.',evidence_links=[link] if rng.random()<0.7 else [])
        if kind=='split':a['children']=[{'action_id':f'A{k}.{j}','statement':f'Users can find part {j} of the licence.',
            'evidence_links':[link] if rng.random()<0.7 else [],'rationale':'r'} for j in range(rng.randint(1,5))]
        if kind in ('defer','set_aside') and rng.random()<0.7:a.update(human_question='Keep it?',alternatives=['Keep','Drop'])
        if kind=='set_aside' and rng.random()<0.6:a['reason']=rng.choice(['not_find_or_access','duplicate','statement_about_sources'])
        if a.get('reason')=='duplicate':a['duplicate_of']=rng.choice(rids+['N9'])
        if rng.random()<0.2:a['experience_ids']=['x1']
        actions.append(a)
    return {'actions':actions,'questions':[],'summary':'s',
        'concerns':[{'concern_id':c,'status':rng.choice(['satisfied','addressed','unresolved','rejected_with_reason']),
            'action_ids':rng.choice([[],[actions[0]['action_id']],['A9']]),'rationale':'r'} for c in ('c1','c2')[:len(rids)] if rng.random()<0.8],
        'experience':[{'claim_id':'x1','decision':rng.choice(['admit','exclude']),'rationale':'r'}] if rng.random()<0.6 else [],
        'proposals':[{'proposal_id':'P1','statement':'Users can find the rights holder.','experience_ids':['x1'],
            'revision_ids':[rids[0]],'rationale':'r'}] if rng.random()<0.3 else []}


@pytest.mark.parametrize('count',[1,2])
@pytest.mark.parametrize('labelled',[False,True])
def test_salvage_always_gives_every_need_one_valid_disposition(setup,count,labelled):
    # v12: whatever an invalid plan of one or two needs holds, salvage returns a plan that passes the plan rules
    # and names every need exactly once, keeping only mediator actions that are valid on their own.
    case,rids,messages,allowed=built(setup,count)
    if labelled:case=deepcopy(case);case['frozen_requirements'][0]['processing_flags']=['covered_by_base']
    link=deepcopy(case['frozen_requirements'][0]['evidence_links'][0])
    messages=[{**messages[0],'experience':[{'claim_id':'x1','revision_ids':[rids[0]]}]}]
    rng=random.Random(count*2+labelled);salvaged_count=0
    for _ in range(150):
        plan=fd.ExperiencePlan.model_validate(broken_plan(rng,rids,link))
        salvaged,audit=fd.salvage_plan(plan,case,messages,allowed)
        assert salvaged is not None,audit
        assert fd.plan_errors(salvaged,case,messages,allowed)==[]
        assert sorted(p for a in salvaged.actions for p in a.parent_revision_ids)==sorted(rids)
        assert audit['nothing_kept']==(not audit['kept_action_ids']) and audit['policy_version']==fd.SALVAGE_POLICY
        kept={a['action_id'] for a in plan.model_dump(mode='json')['actions']}&set(audit['kept_action_ids'])
        assert all(a.action_id in kept or a.action_id.startswith('salvage-') for a in salvaged.actions)
        salvaged_count+=audit['nothing_kept']
    # The random plans include many that keep nothing, which v11 refused to salvage.
    assert salvaged_count>20
