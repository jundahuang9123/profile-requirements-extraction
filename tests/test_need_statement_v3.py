"""rq1-need-statement-v3 against the writer and critic failures seen live: no need is set aside because
its rewrite failed. Shapes copied from Stat run-6455e495 (26 groups, 37 needs) and JRC run-a89957db
(11 groups, 15 needs); scripted answers, no evaluation data or live generation."""
import json
import pytest
from test_resume_discussions import setup  # noqa: F401  (pytest fixture)
from test_rq1_need_grouping import NeedsClient, need_inputs
from test_fa_workflow import enable
from requirement_reuse_service.workflow import needs
from requirement_reuse_service.workflow.base_profile import load_profile
from requirement_reuse_service.workflow.models import RequirementRecord


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


def test_a_repeated_row_for_a_group_is_rewritten_member_by_member(setup):
    store,run,records=need_inputs(setup);client=Habit('repeat',group_only=True)
    active,events=needs.write_needs(store,run,[records],client,None)
    assert [e['action'] for e in events]==['split_unwritten_group','merge_need','merge_need']
    assert 'Repeated row ID.' in events[0]['reason']
    assert len(active)==2 and not any('rewrite_not_applied' in r.processing_flags for r in active)
    no_rewrite_aside(store,run)


@pytest.mark.parametrize('habit,expected',[('unexpressed','at least one member must express the written need'),
    ('term','forbidden vocabulary terms'),('modal','obligation words belong only in the separate obligation field')])
def test_a_single_need_whose_rewrite_cannot_be_used_keeps_its_statement(setup,habit,expected):
    store,run,records=need_inputs(setup)
    profile,_=load_profile('dcat-ap-2.0.1')
    active,events=needs.write_needs(store,run,[[r] for r in records],Habit(habit),profile)
    assert [e['action'] for e in events]==['keep_unwritten_need','keep_unwritten_need']
    assert all(expected in e['reason'] for e in events),events[0]['reason']
    kept_unchanged(active,records);no_rewrite_aside(store,run)


def test_a_group_whose_rewrite_loses_the_obligation_is_rewritten_member_by_member(setup):
    # JRC: the F/A check rejected 3 groups and 7 single needs whose rewrite moved 'shall' into the
    # obligation field.
    store,run,records=need_inputs(setup);run=enable(store,run)
    active,events=needs.write_needs(store,run,[records],Habit('obligation_lost',group_only=True),None)
    assert [e['action'] for e in events]==['split_unwritten_group','merge_need','merge_need']
    assert events[0]['reason'].startswith('Lossless rewrite not established:')
    assert len(active)==2 and not any('rewrite_not_applied' in r.processing_flags for r in active)
    no_rewrite_aside(store,run)


def test_a_single_need_whose_rewrite_loses_the_obligation_keeps_its_statement(setup):
    store,run,records=need_inputs(setup);run=enable(store,run)
    active,events=needs.write_needs(store,run,[records],Habit('obligation_lost'),None)
    assert [e['action'] for e in events]==['split_unwritten_group','keep_unwritten_need','keep_unwritten_need']
    kept_unchanged(active,records);no_rewrite_aside(store,run)


def test_the_policy_name_changes_so_v2_runs_are_not_continued_under_v3():
    assert needs.POLICIES['need_statement']=='rq1-need-statement-v3'
    with pytest.raises(ValueError,match='Needs policies changed'):
        needs.run_needs_policies({'needs_policies':{**needs.POLICIES,'need_statement':'rq1-need-statement-v2'}})
