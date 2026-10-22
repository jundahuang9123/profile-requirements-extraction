"""Synthetic tests of the rule added in rq1-fa-dialogue-v9: no evaluation answers or live generation."""
import pytest
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from copy import deepcopy
from test_fa_dialogue_v3 import Assessing, Mediator, opted_in, ids, case_of, built, kept, sourced
from test_fa_dialogue_v7 import link
from test_fa_dialogue_v4 import set_aside_second_need
from test_fa_dialogue_v8 import aside, aliases
from requirement_reuse_service.workflow import fa_discussion as fd
from requirement_reuse_service.workflow.models import WorkflowRun

FIND={'policy_version':'rq1-find-access-v1','status':'checked','serves':'find','nature':'information_requirement','support':'explicit'}
BACKGROUND={**FIND,'serves':'unresolved','nature':'background'}


def scoped(store,run,rid,scope):
    """Give the need the F/A scope judgement of the scope step (None: no judgement)."""
    def change(r):
        next(x for x in r['requirements'] if x['revision_id']==rid)['fa_scope']=scope
    store.mutate(run['run_id'],None,'fixture_scope',change)
    return store.get('run',run['run_id'])


def keep_and_set_aside(target,**extra):
    """Retain every other need and set target aside with **extra (a reason and what it needs)."""
    def plans(data,*_):
        needs,_=ids(data)
        return {'actions':[aside(n,action_id=f'A{i+1}',**extra) if n==target else
                {'action_id':f'A{i+1}','action':'retain','parent_revision_ids':[n],'rationale':'Kept.'} for i,n in enumerate(needs)],
            'concerns':[],'questions':[],'summary':'Plan.'}
    return plans


@pytest.mark.parametrize('reason,scope,status',[
    ('not_find_or_access',FIND,'human_review'),
    ('statement_about_sources',FIND,'human_review'),
    ('statement_about_sources',{**FIND,'serves':'both','nature':'operational_obligation'},'human_review'),
    ('not_find_or_access',{**FIND,'serves':'both'},'human_review'),
    ('not_find_or_access',{**FIND,'serves':'neither'},'set_aside'),
    ('not_find_or_access',BACKGROUND,'set_aside'),
    ('statement_about_sources',BACKGROUND,'set_aside'),
    # Only a checked judgement can contradict the mediator.
    ('not_find_or_access',{**FIND,'status':'not_checked'},'set_aside'),
    ('not_find_or_access',None,'set_aside'),
])
def test_a_set_aside_against_the_scope_judgement_goes_to_a_person(setup,reason,scope,status):
    store,run=opted_in(setup);alias,rid,_=aliases(store,run)[1];run=scoped(store,run,rid,scope)
    fd.deliberate(store,run['run_id'],Assessing(keep_and_set_aside(alias,reason=reason)))
    saved,case=case_of(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_complete'
    row=next(o for o in case['mediation']['outcomes'] if o['action']=='set_aside')
    assert row['status']==status and row['applied']==(status=='set_aside')
    if status=='human_review':
        field='serves' if reason=='not_find_or_access' else 'nature'
        assert row['scope_conflict']=={'revision_id':rid,'reason':reason,'scope_policy':'rq1-find-access-v1',field:scope[field]}
        assert row['human_question'].endswith('Keep the need, or set it aside after review?')
        assert rid in saved['active_revision_ids'] and not saved['set_aside_observations']
    else:
        assert 'scope_conflict' not in row and rid not in saved['active_revision_ids']
    WorkflowRun.model_validate(saved)


def test_a_duplicate_is_not_judged_by_the_scope(setup):
    store,run=opted_in(setup,3);named=aliases(store,run)
    keep,dup=next((a,b) for a in named for b in named if a[0]<b[0] and a[2]==b[2])
    run=scoped(store,run,dup[1],FIND)
    fd.deliberate(store,run['run_id'],Assessing(keep_and_set_aside(dup[0],reason='duplicate',duplicate_of=keep[0])))
    saved,case=case_of(store,run)
    row=next(o for o in case['mediation']['outcomes'] if o['action']=='set_aside')
    assert row['status']=='set_aside' and row['applied'] and dup[1] not in saved['active_revision_ids']


def test_a_need_set_aside_before_stays_as_it_was(setup):
    store,run=opted_in(setup);rid,run=set_aside_second_need(store,run);run=scoped(store,run,rid,FIND)
    alias=next(a for a,r,_ in aliases(store,run) if r==rid)
    fd.deliberate(store,run['run_id'],Assessing(keep_and_set_aside(alias,reason='not_find_or_access')))
    saved,case=case_of(store,run)
    row=next(o for o in case['mediation']['outcomes'] if o['action']=='set_aside')
    assert row['status']=='already_set_aside' and 'scope_conflict' not in row


def test_the_mediator_sees_the_scope_judgement_and_the_rule(setup):
    store,run=opted_in(setup);alias,rid,_=aliases(store,run)[1];run=scoped(store,run,rid,FIND)
    seen=[]
    def plans(data,number,system):
        seen.append((data,system));return keep_and_set_aside(alias,reason='not_find_or_access')(data)
    fd.deliberate(store,run['run_id'],Mediator(plans))
    data,system=seen[0]
    assert next(n for n in data['packet']['needs'] if n['revision_id']==alias)['fa_scope']['serves']=='find'
    assert 'such a set-aside goes to a person instead of being applied' in system and fd.BASE_MEDIATOR_GUIDANCE in system


def test_scope_conflict_reads_only_checked_judgements_for_the_two_reasons():
    need={'revision_id':'n1','fa_scope':FIND}
    act=lambda reason:fd.ExperienceAction(action_id='A1',action='set_aside',parent_revision_ids=['n1'],rationale='r',reason=reason)
    assert fd.scope_conflict(act('not_find_or_access'),[need])=={'revision_id':'n1','reason':'not_find_or_access',
        'scope_policy':'rq1-find-access-v1','serves':'find'}
    assert fd.scope_conflict(act('statement_about_sources'),[need])['nature']=='information_requirement'
    assert fd.scope_conflict(act('statement_about_sources'),[{**need,'fa_scope':{**FIND,'nature':'operational_obligation'}}])
    assert fd.scope_conflict(act('statement_about_sources'),[{**need,'fa_scope':{**FIND,'nature':'implementation_detail'}}]) is None
    assert fd.scope_conflict(act('duplicate'),[need]) is None and fd.scope_conflict(act('contradicted_by_source'),[need]) is None
    assert fd.scope_conflict(act(None),[need]) is None and fd.scope_conflict(act('not_find_or_access'),[{'revision_id':'n1'}]) is None


def worded(case,rid,action_id,action,statement,**extra):
    return {'action_id':action_id,'action':action,'parent_revision_ids':[rid],'statement':statement,
        'evidence_links':[link(case)],'rationale':'Part of '+rid+'.',**extra}


LICENCE,HOLDER='Users can find the licence of a dataset.','Users can find the rights holder of a dataset.'


@pytest.mark.parametrize('action',['retain','add','revise'])
def test_several_sourced_statements_on_one_need_are_its_split(setup,action):
    case,(n1,n2),messages,allowed=built(setup)
    data=kept([n1,n2]);data['actions'][1:]=[worded(case,n2,'A2',action,LICENCE),worded(case,n2,'A3',action,HOLDER)]
    data['concerns'][1]['action_ids']=['A3']
    plan=fd.ExperiencePlan.model_validate(data)
    assert any(e.startswith('Every current case parent must occur exactly once') for e in fd.plan_errors(plan,case,messages,allowed))
    fixed,repairs=fd.repair_plan(plan,case,messages)
    assert fd.plan_errors(fixed,case,messages,allowed)==[]
    split=fixed.actions[1]
    assert (split.action_id,split.action,split.parent_revision_ids)==('A2','split',[n2]) and len(fixed.actions)==2
    assert [(c.action_id,c.statement,c.rationale) for c in split.children]==[('A2.1',LICENCE,'Part of '+n2+'.'),('A2.2',HOLDER,'Part of '+n2+'.')]
    assert fixed.concerns[1].action_ids==['A2']
    assert repairs[-1]=={'kind':'actions_on_one_need_as_split','revision_id':n2,'action_id':'A2','children':{'A2.1':'A2','A2.2':'A3'}}


def test_only_clear_splits_are_repaired(setup):
    case,(n1,n2),messages,allowed=built(setup)
    def repaired(*actions,case=case):
        data=kept([n1,n2],concerns=[]);data['actions'][1:]=list(actions)
        return [r['kind'] for r in fd.repair_plan(fd.ExperiencePlan.model_validate(data),case,messages)[1]]
    assert repaired(worded(case,n2,'A2','retain',LICENCE),worded(case,n2,'A3','retain',HOLDER))==['actions_on_one_need_as_split']
    # The same wording twice, a statement without sources, or another disposition beside them.
    assert repaired(worded(case,n2,'A2','retain',LICENCE),worded(case,n2,'A3','retain','users can find the licence  of a dataset.'))==[]
    assert repaired(worded(case,n2,'A2','retain',LICENCE),{**worded(case,n2,'A3','retain',HOLDER),'evidence_links':[]})==[]
    assert repaired(worded(case,n2,'A2','retain',LICENCE),{'action_id':'A3','action':'set_aside','parent_revision_ids':[n2],
        'rationale':'r','human_question':'Restore?','reason':'not_find_or_access'})==[]
    # An action that also names another need, a repeated action ID, a labelled need.
    assert repaired(worded(case,n2,'A2','retain',LICENCE),{**worded(case,n2,'A3','retain',HOLDER),'parent_revision_ids':[n1,n2]})==[]
    assert repaired(worded(case,n2,'A2','retain',LICENCE),worded(case,n2,'A2','retain',HOLDER))==[]
    labelled=deepcopy(case);labelled['frozen_requirements'][1]['processing_flags']=['covered_by_base']
    assert repaired(worded(case,n2,'A2','retain',LICENCE),worded(case,n2,'A3','retain',HOLDER),case=labelled)==[]
    # A sourced add beside an unchanged retain stays an addition (repair 6 comes first).
    assert repaired({'action_id':'A2','action':'retain','parent_revision_ids':[n2],'rationale':'Kept.'},
        worded(case,n2,'A3','add',HOLDER))==['add_parents_cleared']


def test_a_split_written_as_two_retains_is_applied_as_a_split(setup):
    store,run=opted_in(setup,1)
    def plans(data,*_):
        [need],_=ids(data);cited=sourced(data)
        return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[need],'statement':LICENCE,'evidence_links':cited,'rationale':'Part one.'},
            {'action_id':'A2','action':'retain','parent_revision_ids':[need],'statement':HOLDER,'evidence_links':cited,'rationale':'Part two.'}],
            'concerns':[],'questions':[],'summary':'Split.'}
    client=Assessing(plans);fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_complete'
    first=case['discussion_trace']['phases']['draft']['attempts'][0]
    assert first['errors']==[] and [r['kind'] for r in first['repairs']]==['actions_on_one_need_as_split']
    row=next(o for o in case['mediation']['outcomes'] if o['action_id']=='A1')
    assert row['action']=='split' and row['status']=='machine_revised' and len(row['result_revision_ids'])==2
    assert case['revision_ids'][0] not in saved['active_revision_ids'] and set(row['result_revision_ids'])<=set(saved['active_revision_ids'])
    assert all('To split a need into several, write one split action' in s for s in client.plan_systems)
