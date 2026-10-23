"""Synthetic tests of the rule added in rq1-fa-dialogue-v12: no evaluation answers or live generation.

Whole cases with the live habits are in test_fa_quirks.py; the salvage of one plan is in test_fa_dialogue_v3.py."""
import random
from copy import deepcopy
import pytest
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_fa_dialogue_v3 import built, opted_in, ids, case_of
from test_fa_quirks import Habits, parts_set_aside, sound
from requirement_reuse_service.workflow import fa_discussion as fd


def test_policy_names():
    # v13 keeps the v12 salvage rule.
    assert 'rq1-fa-dialogue-v12' in fd.BASE_POLICIES and fd.SALVAGE_POLICY=='rq1-fa-salvage-v2'
    assert fd.FIRST_SALVAGE_POLICY=='rq1-fa-salvage-v1' and not {fd.BASE_POLICY,'rq1-fa-dialogue-v12'}&fd.FIRST_SALVAGE_POLICIES
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


def test_a_case_that_runs_out_of_calls_after_a_salvage_that_kept_nothing_is_counted_apart(setup,monkeypatch):
    # One need, two roles, and both plans keep nothing (Stat case-0182df950): 2 reviews, 2 draft tries,
    # 2 responses and 2 final tries use 8 calls, so the check finds no call left. v11 stopped this case
    # after the draft as invalid output.
    monkeypatch.setattr(fd,'BASE_CASE_LIMITS',{**fd.BASE_CASE_LIMITS,'max_calls':8})
    store,run=opted_in(setup,1);before=list(run['active_revision_ids'])
    fd.deliberate(store,run['run_id'],Habits(parts_set_aside,'ideal'))
    saved,case=sound(store,run)
    assert case['stop_reason']=='budget_pending_human_review' and case['model_attempts']==8
    salvage=case['discussion_trace']['salvage']
    assert {k:(a['status'],a['nothing_kept']) for k,a in salvage.items()}=={'draft':('salvaged',True),'final':('salvaged',True)}
    m=saved['metrics']
    assert (m['lost_after_salvage_nothing_kept'],m['salvaged_nothing_kept'],m['salvaged_cases'])==(1,0,0)
    assert saved['active_revision_ids']==before and m['mediated_changes']==0


def overflowing(data,*_):
    """An invalid plan whose salvage needs a 33rd question: 32 questions list the unanswered first concern,
    and the other concerns are addressed by the invalid revise, so they go to the system review question."""
    (n,),(first,*rest)=ids(data)
    return {'actions':[{'action_id':'A1','action':'revise','parent_revision_ids':[n],'rationale':'No source.'}],
        'concerns':[{'concern_id':c,'status':'addressed','action_ids':['A1'],'rationale':'Revised.'} for c in rest],
        'questions':[{'question_id':f'Q{i}','revision_ids':[n],'concern_ids':[first],'question':'Which reading applies?',
            'alternatives':['One','Other'],'rationale':'Open.'} for i in range(32)],'summary':'s'}


def test_a_case_whose_salvage_is_refused_still_stops_as_invalid_output(setup):
    store,run=opted_in(setup,1);before=list(run['active_revision_ids'])
    fd.deliberate(store,run['run_id'],Habits(overflowing,'ideal'))
    saved,case=case_of(store,run)
    assert case['stop_reason']=='invalid_output_pending_human_review'
    audit=case['discussion_trace']['salvage']['draft']
    assert audit['status']=='not_salvaged' and audit['reason'].startswith('Salvaged plan exceeds the plan contract')
    assert 'final' not in case['discussion_trace']['phases'] and saved['active_revision_ids']==before
    assert saved['metrics']['lost_after_salvage_nothing_kept']==0 and saved['metrics']['salvaged_cases']==0
