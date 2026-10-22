"""Synthetic tests of the rule added in rq1-fa-dialogue-v9: no evaluation answers or live generation."""
import pytest
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_fa_dialogue_v3 import Assessing, Mediator, opted_in, ids, case_of
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
    assert fd.scope_conflict(act('duplicate'),[need]) is None and fd.scope_conflict(act('contradicted_by_source'),[need]) is None
    assert fd.scope_conflict(act(None),[need]) is None and fd.scope_conflict(act('not_find_or_access'),[{'revision_id':'n1'}]) is None
