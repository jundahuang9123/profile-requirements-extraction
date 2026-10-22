"""Synthetic tests of the rules added in rq1-fa-dialogue-v8: no evaluation answers or live generation."""
from copy import deepcopy
import pytest
from pydantic import ValidationError
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_fa_workflow import contract_name
from test_base_review import prepared
from test_fa_dialogue_v3 import Assessing, opted_in, ids, case_of, built, kept, sourced, retain_all
from test_fa_dialogue_v7 import link
from requirement_reuse_service.workflow import fa_discussion as fd
from requirement_reuse_service.workflow.models import WorkflowRun

REASON_RULE=('A set_aside needs a reason: not_find_or_access, statement_about_sources, duplicate or contradicted_by_source; '
    'otherwise retain or defer the need.')


def aside(rid,reason=None,action_id='A2',**extra):
    return {'action_id':action_id,'action':'set_aside','parent_revision_ids':[rid],'rationale':'Set aside.',
        'human_question':'Restore it?',**({'reason':reason} if reason else {}),**extra}


def plan_with(rids,*actions):
    """Every need retained, the last ones disposed by actions instead; concerns left to be noted."""
    data=kept(rids,concerns=[]);data['actions'][len(rids)-len(actions):]=list(actions)
    return fd.ExperiencePlan.model_validate(data)


def test_a_set_aside_needs_a_listed_reason(setup):
    case,(n1,n2),messages,allowed=built(setup)
    errors=lambda *actions:fd.plan_errors(plan_with([n1,n2],*actions),case,messages,allowed)
    assert REASON_RULE in errors(aside(n2))
    assert errors(aside(n2,'not_find_or_access'))==[] and errors(aside(n2,'statement_about_sources'))==[]
    # A missing obligation or scope is no reason the contract offers.
    with pytest.raises(ValidationError):fd.ExperienceAction.model_validate(aside(n2,'no_obligation'))
    assert 'Action A2 (set_aside): '+REASON_RULE in fd.plan_feedback(plan_with([n1,n2],aside(n2)),case,messages,allowed)


def test_a_duplicate_names_a_need_the_plan_keeps(setup):
    case,(n1,n2),messages,allowed=built(setup)
    errors=lambda plan:fd.plan_errors(plan,case,messages,allowed)
    assert errors(plan_with([n1,n2],aside(n2,'duplicate',duplicate_of=n1)))==[]
    assert 'A duplicate set_aside names the need it repeats in duplicate_of.' in errors(plan_with([n1,n2],aside(n2,'duplicate')))
    assert 'A need cannot duplicate itself.' in errors(plan_with([n1,n2],aside(n2,'duplicate',duplicate_of=n2)))
    assert 'duplicate_of names a need outside this case.' in errors(plan_with([n1,n2],aside(n2,'duplicate',duplicate_of='rev-x')))
    assert 'Only a duplicate set_aside names duplicate_of.' in errors(plan_with([n1,n2],aside(n2,'not_find_or_access',duplicate_of=n1)))
    # A need set aside before the discussion stays set aside when retained, so it cannot keep a duplicate's information.
    earlier=deepcopy(case);earlier['frozen_requirements'][0]['lifecycle_state']='set_aside'
    assert ('duplicate_of names a need that is set aside already: name a need of the working list, or merge the two needs.'
        in fd.plan_errors(plan_with([n1,n2],aside(n2,'duplicate',duplicate_of=n1)),earlier,messages,allowed))
    # Two needs cannot set each other aside as duplicates.
    pair=plan_with([n1,n2],aside(n1,'duplicate','A1',duplicate_of=n2),aside(n2,'duplicate',duplicate_of=n1))
    assert 'A duplicate set_aside needs the need it repeats kept by this plan.' in errors(pair)
    assert (f'Action A2 sets {n2} aside as a duplicate of {n1}, but the plan sets {n1} aside too: keep {n1}, or retain both '
        'needs.') in fd.plan_feedback(pair,case,messages,allowed)


def test_a_contradiction_cites_its_passage(setup):
    case,(n1,n2),messages,allowed=built(setup)
    errors=lambda action:fd.plan_errors(plan_with([n1,n2],action),case,messages,allowed)
    assert 'A set_aside contradicted by a source cites that passage in evidence_links.' in errors(aside(n2,'contradicted_by_source'))
    assert errors(aside(n2,'contradicted_by_source',evidence_links=[link(case)]))==[]


def test_a_reason_on_another_action_is_cleared_and_a_missing_one_never_given(setup):
    case,(n1,n2),messages,allowed=built(setup)
    data=kept([n1,n2],concerns=[]);data['actions'][1].update(reason='duplicate',duplicate_of=n1)
    plan=fd.ExperiencePlan.model_validate(data)
    assert 'Only a set_aside takes a reason or duplicate_of.' in fd.plan_errors(plan,case,messages,allowed)
    fixed,repairs=fd.repair_plan(plan,case,messages)
    assert fd.plan_errors(fixed,case,messages,allowed)==[] and (fixed.actions[1].reason,fixed.actions[1].duplicate_of)==(None,None)
    assert repairs==[{'kind':'set_aside_fields_cleared','action_id':'A2','action':'retain','reason':'duplicate','duplicate_of':n1}]
    assert fd.repair_plan(plan_with([n1,n2],aside(n2)),case,messages)[1]==[]


def test_salvage_drops_a_set_aside_without_its_reason(setup):
    case,(n1,n2),messages,allowed=built(setup)
    salvaged,audit=fd.salvage_plan(plan_with([n1,n2],aside(n2)),case,messages,allowed)
    assert [(a.action_id,a.action) for a in salvaged.actions]==[('A1','retain'),('salvage-1','defer')]
    assert audit['dropped_actions'][0]['problems']==[REASON_RULE]


def test_salvage_drops_both_needs_of_a_duplicate_pair(setup):
    case,(n1,n2,n3),messages,allowed=built(setup,3)
    pair=plan_with([n1,n2,n3],aside(n2,'duplicate',duplicate_of=n3),aside(n3,'duplicate','A3',duplicate_of=n2))
    salvaged,audit=fd.salvage_plan(pair,case,messages,allowed)
    # Each need of the pair is kept by a system deferral.
    assert [(a.action,a.parent_revision_ids) for a in salvaged.actions]==[('retain',[n1]),('defer',[n2]),('defer',[n3])]
    assert [d['problems'] for d in audit['dropped_actions']]==[['The need it duplicates is set aside too.']]*2
    assert fd.plan_errors(salvaged,case,messages,allowed)==[]


class Doubting(Assessing):
    """The checker sets condition_supported and obligation_preserved false for every action, as the
    v6 checker did for needs whose sources state no condition or obligation."""
    def generate_structured(self,*,user,output_model,system='',step=None,**kw):
        answer=super().generate_structured(user=user,output_model=output_model,system=system,step=step,**kw)
        if contract_name(output_model)!='Checks':return answer
        self.check_model=output_model;self.check_system=system
        return output_model.model_validate({'checks':[{**c,'condition_supported':False,'obligation_preserved':False}
            for c in answer.model_dump(mode='json')['checks']]})


def test_the_condition_and_obligation_flags_decide_only_written_statements(setup):
    store,run=opted_in(setup,3)
    def plans(data,*_):
        needs,_=ids(data)
        return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'Kept.'},
            {'action_id':'A2','action':'revise','parent_revision_ids':[needs[1]],'statement':'Users can find the contact point of a dataset.',
             'evidence_links':sourced(data),'rationale':'Reworded.'},
            {'action_id':'A3','action':'set_aside','parent_revision_ids':[needs[2]],'rationale':'Repeats N1.',
             'human_question':'Restore it?','reason':'duplicate','duplicate_of':needs[0]}],
            'concerns':[],'questions':[],'summary':'Plan.'}
    client=Doubting(plans);fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run);n1,_,n3=case['revision_ids']
    assert case['stop_reason']=='bounded_fa_dialogue_complete'
    outcomes={o['action_id']:o for o in case['mediation']['outcomes']}
    # Kept and set-aside needs no longer go to review on these flags; a written statement still does.
    assert {k:o['status'] for k,o in outcomes.items()}=={'A1':'retained','A2':'human_review','A3':'set_aside'}
    assert outcomes['A3']['duplicate_of']==n1 and saved['active_revision_ids']==[r for r in run['active_revision_ids'] if r!=n3]
    # The set-aside record keeps the reason and the need it repeats, under internal IDs.
    record=next(a for a in saved['set_aside_observations'] if a['revision_id']==n3)
    assert record['details']=={'mediator_reason':'duplicate','duplicate_of':n1}
    WorkflowRun.model_validate(saved)
    assert client.check_model is fd.DefinedChecks and 'A set_aside is justified only when its reason holds' in client.check_system


def test_a_v1_discussion_keeps_its_checks_and_gate(setup):
    store,run,_=prepared(setup,2);assert fd.discussion_policy(run)=='rq1-fa-dialogue-v1'
    client=Doubting(retain_all);fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run)
    assert client.check_model is fd.Checks and {o['status'] for o in case['mediation']['outcomes']}=={'human_review'}


@pytest.mark.parametrize('quote,status',[(None,'set_aside'),('A sentence the source never says.','human_review')])
def test_a_set_aside_on_a_contradiction_rests_on_a_passage_that_exists(setup,quote,status):
    store,run=opted_in(setup)
    def plans(data,*_):
        needs,_=ids(data);cited=sourced(data)
        if quote:cited=[{**cited[0],'quote':quote,'quote_start':None}]
        return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'Kept.'},
            {'action_id':'A2','action':'set_aside','parent_revision_ids':[needs[1]],'rationale':'The source says otherwise.',
             'human_question':'Restore it?','reason':'contradicted_by_source','evidence_links':cited}],
            'concerns':[],'questions':[],'summary':'Plan.'}
    fd.deliberate(store,run['run_id'],Assessing(plans))
    saved,case=case_of(store,run)
    row=next(o for o in case['mediation']['outcomes'] if o['action_id']=='A2')
    assert row['status']==status and row['applied']==(status=='set_aside')
    if quote:assert row['human_question'].startswith('The passage cited as contradicting this need was not found')


def test_a_review_holds_one_claim_and_it_proposes_a_change():
    claim={'kind':'split','revision_ids':['n1'],'task':'Find data','experience':'When I search, I filter by each part.','claim':'Split it.'}
    assert fd.ExperienceReview(summary='s',experience=[claim]).experience[0].kind=='split'
    with pytest.raises(ValidationError):fd.ExperienceReview(summary='s',experience=[claim,claim])
    with pytest.raises(ValidationError):fd.ExperienceReview(summary='s',experience=[{**claim,'kind':'keep'}])
    assert 'you may add one experience claim' in fd.EXPERIENCE_GUIDANCE and 'A need you agree with needs no claim.' in fd.EXPERIENCE_GUIDANCE


def test_the_check_schema_defines_the_statement_flags():
    fields=fd.DefinedChecks.model_json_schema()['$defs']['DefinedCheck']['properties']
    assert set(fields)==set(fd.Check.model_json_schema()['properties'])
    for flag in ('condition_supported','obligation_preserved'):
        assert 'For an action that writes a statement' in fields[flag]['description']
        assert fields[flag]['description'].endswith('true.')
