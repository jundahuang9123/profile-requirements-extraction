"""Synthetic tests of the rules added in rq1-fa-dialogue-v7: no evaluation answers or live generation."""
from copy import deepcopy
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_fa_dialogue_v3 import Assessing, opted_in, ids, case_of, built, kept, sourced
from requirement_reuse_service.workflow import fa_discussion as fd


def link(case,i=0):
    return deepcopy(case['frozen_requirements'][i]['evidence_links'][0])


def child(case,cid,statement):
    return {'action_id':cid,'statement':statement,'evidence_links':[link(case)],'rationale':'Sourced part.'}


def test_a_split_needs_sources_only_in_its_children(setup):
    case,(n1,n2),messages,allowed=built(setup)
    split={'action_id':'A1','action':'split','parent_revision_ids':[n1],'rationale':'Two needs in one.',
        'children':[child(case,'A1a','Users can find the licence of a dataset.'),child(case,'A1b','Users can find the rights holder of a dataset.')]}
    plan=fd.ExperiencePlan.model_validate({**kept([n1,n2],concerns=[]),'actions':[split,kept([n1,n2])['actions'][1]]})
    assert fd.plan_errors(plan,case,messages,allowed)==[]
    # The legacy protocol keeps its rule, and a recovery still needs its own statement and sources.
    legacy={**case,'policy_version':'rq1-fa-dialogue-v1'}
    assert 'Recovery/split requires source-supported statement and links.' in fd.plan_errors(plan,legacy,messages,allowed)
    recover={'action_id':'A1','action':'recover','parent_revision_ids':[n1],'rationale':'Recovered.'}
    plan=fd.ExperiencePlan.model_validate({**kept([n1,n2],concerns=[]),'actions':[recover,kept([n1,n2])['actions'][1]]})
    assert 'Recovery/split requires source-supported statement and links.' in fd.plan_errors(plan,case,messages,allowed)
    # Children still need their sources.
    split['children'][1]['evidence_links']=[]
    plan=fd.ExperiencePlan.model_validate({**kept([n1,n2],concerns=[]),'actions':[split,kept([n1,n2])['actions'][1]]})
    assert 'Every split child requires sources.' in fd.plan_errors(plan,case,messages,allowed)


def repaired(data,case,messages,allowed,model=fd.ExperiencePlan):
    plan=model.model_validate(data);fixed,repairs=fd.repair_plan(plan,case,messages)
    return fd.plan_errors(plan,case,messages,allowed),fixed,repairs,fd.plan_errors(fixed,case,messages,allowed)


def test_an_add_naming_only_its_own_needs_becomes_a_revise_or_a_merge(setup):
    case,(n1,n2),messages,allowed=built(setup)
    add={'action_id':'A1','action':'add','parent_revision_ids':[n1],'statement':'Users can find the licence of a dataset.',
        'evidence_links':[link(case)],'rationale':'Reworded.'}
    data={**kept([n1,n2],concerns=[]),'actions':[add,kept([n1,n2])['actions'][1]]}
    before,fixed,repairs,after=repaired(data,case,messages,allowed)
    assert 'Addition cannot replace an existing parent.' in before and after==[]
    assert fixed.actions[0].action=='revise' and repairs==[{'kind':'add_rewording_needs_as_revise','action_id':'A1','revision_ids':[n1]}]
    merged={**add,'parent_revision_ids':[n1,n2]}
    before,fixed,repairs,after=repaired({**kept([n1,n2],concerns=[]),'actions':[merged]},case,messages,allowed)
    assert after==[] and fixed.actions[0].action=='merge' and repairs[0]['kind']=='add_rewording_needs_as_merge'


def test_an_add_beside_the_disposition_of_its_need_loses_its_parents(setup):
    case,(n1,n2),messages,allowed=built(setup)
    add={'action_id':'A3','action':'add','parent_revision_ids':[n1],'statement':'Users can find the rights holder of a dataset.',
        'evidence_links':[link(case)],'rationale':'A further need.'}
    data=kept([n1,n2],concerns=[]);data['actions'].append(add)
    before,fixed,repairs,after=repaired(data,case,messages,allowed)
    assert before and after==[] and fixed.actions[2].parent_revision_ids==[]
    assert repairs==[{'kind':'add_parents_cleared','action_id':'A3','revision_ids':[n1]}]


def test_an_add_without_sources_or_with_mixed_parents_is_not_repaired(setup):
    case,(n1,n2),messages,allowed=built(setup)
    lone={'action_id':'A1','action':'add','parent_revision_ids':[n1],'statement':'Users can find the licence.','rationale':'No source.'}
    data={**kept([n1,n2],concerns=[]),'actions':[lone,kept([n1,n2])['actions'][1]]}
    assert repaired(data,case,messages,allowed)[2]==[]
    # n1 is retained elsewhere, n2 is not: neither reading is safe.
    mixed={**lone,'action_id':'A3','parent_revision_ids':[n1,n2],'evidence_links':[link(case)]}
    data={**kept([n1,n2],concerns=[]),'actions':[kept([n1,n2])['actions'][0],mixed]}
    before,fixed,repairs,after=repaired(data,case,messages,allowed)
    assert repairs==[] and 'Addition cannot replace an existing parent.' in after


def test_concern_links_to_missing_actions_are_repaired(setup):
    case,(n1,n2),messages,allowed=built(setup)
    data=kept([n1,n2]);data['concerns']=[{'concern_id':'c1','status':'addressed','action_ids':['A9'],'rationale':'Answered.'},
        {'concern_id':'c2','status':'satisfied','action_ids':[],'rationale':'Kept.'}]
    before,fixed,repairs,after=repaired(data,case,messages,allowed)
    assert 'Concern disposition names an unknown action.' in before and 'Addressed concerns must link to their resulting action.' in before
    assert after==[] and [c.action_ids for c in fixed.concerns]==[['A1'],['A2']]
    assert repairs==[{'kind':'concern_unknown_actions_dropped','concern_id':'c1','action_ids':['A9']},
        {'kind':'concern_actions_from_needs','concern_id':'c1','action_ids':['A1']},
        {'kind':'concern_actions_from_needs','concern_id':'c2','action_ids':['A2']}]


def test_the_v5_plan_contract_gets_no_v7_repairs(setup):
    case,(n1,n2),messages,allowed=built(setup)
    add={'action_id':'A1','action':'add','parent_revision_ids':[n1],'statement':'Users can find the licence of a dataset.',
        'evidence_links':[link(case)],'rationale':'Reworded.'}
    data={**kept([n1,n2],concerns=[]),'actions':[add,kept([n1,n2])['actions'][1]]}
    assert repaired(data,case,messages,allowed,fd.Plan)[2]==[]


def test_a_split_with_sourced_children_completes_the_case(setup):
    store,run=opted_in(setup)
    def plans(data,*_):
        needs,_=ids(data);source=sourced(data)
        return {'actions':[{'action_id':'A1','action':'split','parent_revision_ids':[needs[0]],'rationale':'Two needs in one.',
                'children':[{'action_id':'A1a','statement':'Users can find the licence of a dataset.','evidence_links':source,'rationale':'Part one.'},
                    {'action_id':'A1b','statement':'Users can find the rights holder of a dataset.','evidence_links':source,'rationale':'Part two.'}]},
            {'action_id':'A2','action':'retain','parent_revision_ids':[needs[1]],'rationale':'Kept.'}],
            'concerns':[],'questions':[],'summary':'Split.'}
    fd.deliberate(store,run['run_id'],Assessing(plans))
    saved,case=case_of(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_complete'
    draft=case['discussion_trace']['phases']['draft']['attempts']
    assert len(draft)==1 and draft[0]['errors']==[]
    assert next(o for o in case['mediation']['outcomes'] if o['action_id']=='A1')['action']=='split'
