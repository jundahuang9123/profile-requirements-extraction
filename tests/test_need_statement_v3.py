"""rq1-need-statement-v3 against the writer and critic failures seen live: no need is set aside because
its rewrite failed. Shapes copied from Stat run-6455e495 (26 groups, 37 needs) and JRC run-a89957db
(11 groups, 15 needs); scripted answers, no evaluation data or live generation."""
import json
from collections import Counter
import pytest
from test_resume_discussions import setup  # noqa: F401  (pytest fixture)
from test_rq1_need_grouping import NeedsClient, need_inputs
from test_semantic_consolidation import inputs, revised
from test_fa_workflow import enable
from requirement_reuse_service.workflow import needs
from requirement_reuse_service.workflow.base_profile import load_profile
from requirement_reuse_service.workflow.engine import verify
from requirement_reuse_service.workflow.models import RequirementRecord
from requirement_reuse_service.workflow.semantic_consolidation import NEED_SEMANTIC_POLICY
from requirement_reuse_service.workflow.storage import uid


class Habit(NeedsClient):
    """The writer repeats a group's row, marks no member as expressed, writes a vocabulary term or an
    obligation word, in both tries; or the F/A check finds the obligation lost. single_only limits the
    habit to single-need groups, group_only to larger groups."""
    def __init__(self, habit, single_only=False, group_only=False):
        super().__init__();self.habit=habit;self.single_only=single_only;self.group_only=group_only
    def applies(self, group):
        n=len(group['members']);return not ((self.single_only and n>1) or (self.group_only and n==1))
    def generate_structured(self, *, system, user, output_model, **kwargs):
        data=json.loads(user);name=output_model.__name__
        if name=='FAPreservation':
            self.calls.append((name,data))
            lost=self.habit=='obligation_lost'
            return output_model.model_validate({'checks':[{'group_id':g,'information_preserved':True,'actor_preserved':True,
                'purpose_preserved':True,'conditions_preserved':True,'obligation_preserved':not (lost and self.applies(row)),
                'negation_preserved':True,'rationale':"The original says 'shall be provided'; the rewrite drops the obligation."}
                for g,row in data['groups'].items()]})
        answer=super().generate_structured(system=system,user=user,output_model=output_model,**kwargs)
        if name!='NeedStatements' or self.habit=='obligation_lost':return answer
        rows=answer.model_dump(mode='json')['needs']
        for row in list(rows):
            if not self.applies(data['groups'][row['group_id']]):continue
            if self.habit=='repeat':rows.append(dict(row))
            elif self.habit=='unexpressed':row['members']=[{**m,'expresses_need':False} for m in row['members']]
            elif self.habit=='term':row['statement']='Users can identify the dct:title of a dataset.'
            elif self.habit=='modal':row['statement']='Datasets shall include a title.'
        return output_model.model_validate({'needs':rows})


def kept_unchanged(active, records):
    assert len(active)==len(records) and all('rewrite_not_applied' in r.processing_flags for r in active)
    assert sorted(r.need_statement for r in active)==sorted(r.normalized_statement for r in records)
    for r in active:
        RequirementRecord.model_validate(r.model_dump(mode='json'))
        assert r.verification['status']=='pass' and r.lifecycle_state=='need_assessment_pending' and r.evidence_links


def no_rewrite_aside(store, run):
    assert not any(a['reason']=='rewrite_rejected' for a in store.get('run',run['run_id'])['set_aside_observations'])


def each_member_once(records, active):
    """Every input member is the parent of exactly one need and inactive under that need's group."""
    assert Counter(p for n in active for p in n.parent_revision_ids)==Counter(r.revision_id for r in records)
    group={p:n.group_id for n in active for p in n.parent_revision_ids}
    assert all(r.lifecycle_state=='inactive_member' and r.group_id==group[r.revision_id] for r in records)


def many_inputs(setup, count):
    store,run,records=inputs(setup,count=count)
    for r in records: r.verification=verify(store,r,run['evidence_ids'])
    run.update(consolidation_policy_version=NEED_SEMANTIC_POLICY,needs_policies={})
    run['request']['output_form']='needs'
    store.mutate(run['run_id'],None,'need-test',lambda r:r.update(run))
    return store,run,records


def accept(group_id, supported=True):
    return {'group_id':group_id,'supported':supported,'no_added_actor':True,'no_added_obligation':True,
            'no_added_condition':True,'no_added_scope':True,'rationale':'Scripted rewrite check.'}


class Retry(NeedsClient):
    """The critic rejects a group's first rewrite. Then the retry writer repeats its row in both tries
    ('retry_writer'), or it changes the rewrite and the critic repeats its row for the new rewrite in both
    tries ('second_critic'). group_only limits this to groups of more than one need."""
    def __init__(self, stage, group_only):
        super().__init__();self.stage=stage;self.group_only=group_only;self.critic=Counter()
    def applies(self, group):
        return len(group['members'])>1 or not self.group_only
    def generate_structured(self, *, system, user, output_model, **kwargs):
        data=json.loads(user);name=output_model.__name__
        if name=='NeedGrounding':
            self.calls.append((name,data));rows=[]
            for g,group in data['groups'].items():
                self.critic[g]+=1;hit=self.applies(group)
                if hit and self.critic[g]==1:rows.append(accept(g,supported=False))
                elif hit and self.stage=='second_critic':rows+=[accept(g),accept(g)]
                else:rows.append(accept(g))
            return output_model.model_validate({'checks':rows})
        answer=super().generate_structured(system=system,user=user,output_model=output_model,**kwargs)
        if name!='NeedStatements' or 'previous_rewrites' not in data:return answer
        rows=answer.model_dump(mode='json')['needs']
        for row in list(rows):
            if not self.applies(data['groups'][row['group_id']]):continue
            if self.stage=='retry_writer':rows.append(dict(row))
            else:row['statement']='Users can identify the title of each dataset.'
        return output_model.model_validate({'needs':rows})


def test_a_repeated_row_for_a_group_is_rewritten_member_by_member(setup):
    store,run,records=need_inputs(setup);client=Habit('repeat',group_only=True)
    active,events=needs.write_needs(store,run,[records],client,None)
    assert [e['action'] for e in events]==['split_unwritten_group','merge_need','merge_need']
    assert 'Repeated row ID.' in events[0]['reason']
    assert len(active)==2 and not any('rewrite_not_applied' in r.processing_flags for r in active)
    each_member_once(records,active);no_rewrite_aside(store,run)


@pytest.mark.parametrize('habit,expected',[('unexpressed','at least one member must express the written need'),
    ('term','forbidden vocabulary terms'),('modal','obligation words belong only in the separate obligation field')])
def test_a_single_need_whose_rewrite_cannot_be_used_keeps_its_statement(setup,habit,expected):
    store,run,records=need_inputs(setup)
    profile,_=load_profile('dcat-ap-2.0.1')
    active,events=needs.write_needs(store,run,[[r] for r in records],Habit(habit),profile)
    assert [e['action'] for e in events]==['keep_unwritten_need','keep_unwritten_need']
    assert all(expected in e['reason'] for e in events),events[0]['reason']
    kept_unchanged(active,records);each_member_once(records,active);no_rewrite_aside(store,run)


def test_a_group_whose_rewrite_loses_the_obligation_is_rewritten_member_by_member(setup):
    # JRC: the F/A check rejected 3 groups and 7 single needs whose rewrite moved 'shall' into the
    # obligation field.
    store,run,records=need_inputs(setup);run=enable(store,run)
    active,events=needs.write_needs(store,run,[records],Habit('obligation_lost',group_only=True),None)
    assert [e['action'] for e in events]==['split_unwritten_group','merge_need','merge_need']
    assert events[0]['reason'].startswith('Lossless rewrite not established:')
    assert len(active)==2 and not any('rewrite_not_applied' in r.processing_flags for r in active)
    each_member_once(records,active);no_rewrite_aside(store,run)


def test_a_single_need_whose_rewrite_loses_the_obligation_keeps_its_statement(setup):
    store,run,records=need_inputs(setup);run=enable(store,run)
    active,events=needs.write_needs(store,run,[records],Habit('obligation_lost'),None)
    assert [e['action'] for e in events]==['split_unwritten_group','keep_unwritten_need','keep_unwritten_need']
    kept_unchanged(active,records);each_member_once(records,active);no_rewrite_aside(store,run)


@pytest.mark.parametrize('stage,reason',[('retry_writer','Retry writer unavailable after bounded recovery.'),
    ('second_critic','New rewrite critic not checked after bounded recovery.')])
def test_a_group_whose_repair_cannot_be_checked_is_rewritten_member_by_member(setup,stage,reason):
    store,run,records=need_inputs(setup);client=Retry(stage,group_only=True)
    active,events=needs.write_needs(store,run,[records],client,None)
    assert [e['action'] for e in events]==['split_unwritten_group','merge_need','merge_need']
    assert events[0]['reason']==reason and len(events[0]['rewrites'])==(1 if stage=='retry_writer' else 2)
    assert not any('rewrite_not_applied' in r.processing_flags for r in active)
    each_member_once(records,active);no_rewrite_aside(store,run)
    calls=len(client.calls);needs.write_needs(store,run,[records],client,None)
    assert len(client.calls)==calls


@pytest.mark.parametrize('stage,reason',[('retry_writer','Retry writer unavailable after bounded recovery.'),
    ('second_critic','New rewrite critic not checked after bounded recovery.')])
def test_a_single_need_whose_repair_cannot_be_checked_keeps_its_statement(setup,stage,reason):
    store,run,records=need_inputs(setup)
    active,events=needs.write_needs(store,run,[[r] for r in records],Retry(stage,group_only=False),None)
    assert [e['action'] for e in events]==['keep_unwritten_need','keep_unwritten_need']
    assert all(e['reason']==reason for e in events)
    kept_unchanged(active,records);each_member_once(records,active);no_rewrite_aside(store,run)


def test_a_kept_need_takes_a_condition_or_scope_only_from_its_own_statement(setup):
    # The extraction's scope label is model-written and not source-checked. A written need may only take a
    # condition or scope that stands in its members' statements; so may a kept one.
    store,run,records=need_inputs(setup)
    records=[revised(run,records[0],statement='Users can read the title of open datasets.',scope='Open  Datasets',
                     extension_kind=None,base_property=None),
             revised(run,records[1],scope='Datasets of the statistics office',extension_kind=None,base_property=None)]
    for r in records: r.verification=verify(store,r,run['evidence_ids'])
    active,events=needs.write_needs(store,run,[[r] for r in records],Habit('unexpressed'),None)
    assert [e['action'] for e in events]==['keep_unwritten_need','keep_unwritten_need']
    scope={n.parent_revision_ids[0]:(n.scope,n.need_condition) for n in active}
    assert scope=={records[0].revision_id:('Open  Datasets',''),records[1].revision_id:('Unspecified','')}
    each_member_once(records,active)


def test_a_replay_keeps_the_order_of_split_groups_and_makes_no_calls(setup):
    # Two groups of 12 whose writer rows stay unavailable give 24 singles, two writer batches in the next
    # round. A replay reads the writer's fallback rows back in sorted key order; the next round must still
    # follow batch order, or its batches differ and are generated again.
    store,run,records=many_inputs(setup,24)
    groups=[records[:12],records[12:]]
    ids=[uid('group',run['run_id'],sorted(r.revision_id for r in g)) for g in groups]
    if ids[0]<ids[1]:groups.reverse()
    client=Habit('repeat',group_only=True)
    active,events=needs.write_needs(store,run,groups,client,None)
    assert [e['action'] for e in events][:2]==['split_unwritten_group']*2 and len(active)==24
    assert [len(d['groups']) for n,d in client.calls if n=='NeedStatements'][-2:]==[20,4]
    each_member_once(records,active)
    calls=len(client.calls)
    again,replayed=needs.write_needs(store,run,groups,client,None)
    assert len(client.calls)==calls
    assert [n.revision_id for n in again]==[n.revision_id for n in active] and replayed==events


def test_the_policy_name_changes_so_v2_runs_are_not_continued_under_v3():
    # rq1-need-statement-v4/v5 and rq1-need-semantic-grouping-v3 (resource guard, 28 Oct; folded whitespace, 29 Oct) are later names: a run
    # saved under v2, v3 or the earlier grouping is not continued under them.
    assert needs.POLICIES['need_statement']=='rq1-need-statement-v5' and needs.POLICIES['grouping']=='rq1-need-semantic-grouping-v3'
    for saved in ({'need_statement':'rq1-need-statement-v2'},{'need_statement':'rq1-need-statement-v3'},
                  {'need_statement':'rq1-need-statement-v4'},
                  {'grouping':'rq1-need-semantic-grouping-v2'}):
        with pytest.raises(ValueError,match='Needs policies changed'):
            needs.run_needs_policies({'needs_policies':{**needs.POLICIES,**saved}})
