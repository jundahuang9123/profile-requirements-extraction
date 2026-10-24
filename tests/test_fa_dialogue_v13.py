"""Synthetic tests of the rule added in rq1-fa-dialogue-v13: no evaluation answers or live generation.

Whole cases with the live checker habits are in test_fa_quirks.py."""
import json
import random
from collections import Counter
from test_fa_dialogue_v10 import checks, plan
from requirement_reuse_service.workflow import fa_discussion as fd

# The v10 plan: A1 splits a need into A1.1 and A1.2, A2 retains the other.
errors=lambda *i,policy=fd.BASE_POLICY:fd.check_errors(checks(*i),plan(),policy)


def refused(missing=(),repeated=(),unknown=()):
    return ['Check every action exactly once: '+json.dumps({'missing':list(missing),'repeated':list(repeated),
        'unknown':list(unknown)},separators=(',',':'))]


def test_policy_names():
    assert 'rq1-fa-dialogue-v13' in fd.BASE_POLICIES and fd.POLICY=='rq1-fa-dialogue-v1'
    assert 'rq1-fa-dialogue-v12' in fd.BASE_POLICIES and fd.BASE_POLICY not in fd.FIRST_SALVAGE_POLICIES


def test_a_check_of_an_id_that_is_not_an_action_of_the_plan_is_ignored():
    # An experience proposal, an invented ID, an action the salvage dropped, experience claims, a need, and
    # such IDs beside a split's new need or repeated.
    for extra in (['P1'],['S1'],['SA1','SA2'],['A3'],['X1','X2','X3'],['N1'],['A1.1','P1','P1']):
        assert errors('A1','A2',*extra)==[] and errors(*extra,'A2','A1')==[]
    assert fd.ignored_checks(checks('P1','A1','A1.1','A2','S1','P1'),plan())==['P1','S1','P1']
    assert fd.ignored_checks(checks('A1','A1.1','A1.2','A2'),plan())==[]


def test_every_action_of_the_plan_still_needs_exactly_one_check():
    # A missing check.
    assert errors('A1')==refused(missing=['A2']) and errors()==refused(missing=['A1','A2'])
    # A check filed under another ID leaves the action unchecked: a need ID, an invented ID, a split's new needs.
    assert errors('A1','N2')==refused(missing=['A2'],unknown=['N2'])
    assert errors('S1','A2')==refused(missing=['A1'],unknown=['S1'])
    assert errors('A1.1','A1.2','A2')==refused(missing=['A1'])
    # A repeated check of an action, alone or beside an ID outside the plan.
    assert errors('A1','A2','A2')==refused(repeated=['A2'])
    assert errors('A1','A1','A2','P1')==refused(repeated=['A1'],unknown=['P1'])
    # Only IDs outside the plan.
    assert errors('P1','S1')==refused(missing=['A1','A2'],unknown=['P1','S1'])


def test_checks_named_after_action_types_are_ignored_only_beside_the_actions_own_checks():
    # Stat run-6455e495 (v6) and run-c4cbca44 (v8): checks named after action types, beside the actions' checks.
    beside=checks('A1','set_aside','A2','defer','retain_B1')
    assert fd.check_errors(beside,plan(),fd.BASE_POLICY)==[]
    assert fd.ignored_checks(beside,plan())==['set_aside','defer','retain_B1']
    # The same names in place of an action's check leave that action missing, and the answer is refused.
    assert errors('A1','retain_B1')==refused(missing=['A2'],unknown=['retain_B1'])
    assert errors('set_aside','defer','A2')==refused(missing=['A1'],unknown=['defer','set_aside'])
    assert errors('set_aside','defer','retain_B1')==refused(missing=['A1','A2'],unknown=['defer','retain_B1','set_aside'])


def test_the_legacy_rule_and_wording_stay():
    assert errors('A1','A2','P1',policy=fd.POLICY)==['Check every action exactly once.']
    assert errors('A1','A2',policy=fd.POLICY)==[]


def random_plan(rng):
    """1-4 retains and splits A1..An; a split's new needs are named A<k>.<j>, A<k><letter> or, rarely, A1."""
    actions=[]
    for k in range(1,rng.randint(1,4)+1):
        if rng.random()<0.5:
            actions.append({'action_id':f'A{k}','action':'retain','parent_revision_ids':[f'n{k}'],'rationale':'Kept.'})
            continue
        names=[rng.choice([f'A{k}.{j}',f'A{k}{"ab"[j-1]}','A1']) for j in (1,2)]
        actions.append({'action_id':f'A{k}','action':'split','parent_revision_ids':[f'n{k}'],'rationale':'Two needs.',
            'children':[{'action_id':c,'statement':'Users can find part of the access conditions.','rationale':'Part.',
                'evidence_links':[{'evidence_id':'e1','quote':'q'}]} for c in names]})
    return fd.ExperiencePlan.model_validate({'actions':actions,'summary':'s'})


def test_v13_accepts_every_answer_v12_accepted_and_otherwise_only_one_check_per_action_beside_ignored_ids():
    rng=random.Random(13);seen=Counter()
    for _ in range(3000):
        p=random_plan(rng);wanted=[a.action_id for a in p.actions]
        children={c.action_id for a in p.actions for c in a.children}-set(wanted)
        answer=rng.sample(wanted,len(wanted))
        if rng.random()<0.3:answer.remove(rng.choice(answer))
        if rng.random()<0.3:answer.append(rng.choice(wanted))
        answer+=rng.sample(sorted(children),rng.randint(0,len(children)))
        answer+=[rng.choice(['P1','S1','SA1','X1','N1','A9']) for _ in range(rng.choice([0,0,1,3]))]
        rng.shuffle(answer)
        answer=checks(*answer)
        ids=[c.action_id for c in answer.checks]
        # The v12 rule: v10's, which ignored only a split's new needs.
        v12=Counter(i for i in ids if i not in children)==Counter(wanted)
        v13=fd.check_errors(answer,p,fd.BASE_POLICY)==[]
        # Accepted exactly when each action has one check, which apply then finds by the action's ID.
        assert v13==(Counter(i for i in ids if i in wanted)==Counter(wanted))
        assert v13 or not v12
        ignored=fd.ignored_checks(answer,p)
        assert ignored==[i for i in ids if i not in set(wanted)|children]
        if v13 and not v12:assert ignored
        seen[(v12,v13)]+=1
    assert seen[(True,True)] and seen[(False,True)] and seen[(False,False)] and not seen[(True,False)]
