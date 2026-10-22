"""Synthetic tests of the rules added in rq1-fa-dialogue-v8: no evaluation answers or live generation."""
import json
from copy import deepcopy
import pytest
from pydantic import ValidationError
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_fa_workflow import contract_name
from test_base_review import prepared
from test_fa_dialogue_v3 import Assessing, opted_in, ids, case_of, built, kept, sourced, retain_all
from test_fa_dialogue_v7 import link
from test_fa_experience import Experienced
from requirement_reuse_service.workflow import fa_discussion as fd
from requirement_reuse_service.workflow.models import EvidenceLink, WorkflowRun

REASON_RULE=('A set_aside needs a reason: not_find_or_access, statement_about_sources, duplicate or contradicted_by_source; '
    'otherwise retain or defer the need.')


def aside(rid,reason=None,action_id='A2',**extra):
    return {'action_id':action_id,'action':'set_aside','parent_revision_ids':[rid],'rationale':'Set aside.',
        'human_question':'Restore it?',**({'reason':reason} if reason else {}),**extra}


def plan_with(rids,*actions):
    """Every need retained, the last ones disposed by actions instead; concerns left to be noted."""
    data=kept(rids,concerns=[]);data['actions'][len(rids)-len(actions):]=list(actions)
    return fd.ExperiencePlan.model_validate(data)


def same_sources(case,*indices):
    """The needs at these indices cite the sources of the first need."""
    case=deepcopy(case)
    for i in indices:case['frozen_requirements'][i]['evidence_links']=deepcopy(case['frozen_requirements'][0]['evidence_links'])
    return case


def test_a_set_aside_needs_a_listed_reason(setup):
    case,(n1,n2),messages,allowed=built(setup)
    errors=lambda *actions:fd.plan_errors(plan_with([n1,n2],*actions),case,messages,allowed)
    assert REASON_RULE in errors(aside(n2))
    assert errors(aside(n2,'not_find_or_access'))==[] and errors(aside(n2,'statement_about_sources'))==[]
    # A missing obligation or scope is no reason the contract offers.
    with pytest.raises(ValidationError):fd.ExperienceAction.model_validate(aside(n2,'no_obligation'))
    assert 'Action A2 (set_aside): '+REASON_RULE in fd.plan_feedback(plan_with([n1,n2],aside(n2)),case,messages,allowed)
    # Setting aside a need that is set aside already changes nothing and needs no reason.
    earlier=deepcopy(case);earlier['frozen_requirements'][1]['lifecycle_state']='set_aside'
    assert fd.plan_errors(plan_with([n1,n2],aside(n2)),earlier,messages,allowed)==[]


def test_a_duplicate_repeats_a_need_kept_as_it_is_from_the_same_sources(setup):
    case,(n1,n2),messages,allowed=built(setup);same=same_sources(case,1)
    errors=lambda plan,case=same:fd.plan_errors(plan,case,messages,allowed)
    assert errors(plan_with([n1,n2],aside(n2,'duplicate',duplicate_of=n1)))==[]
    assert 'A duplicate set_aside names the need it repeats in duplicate_of.' in errors(plan_with([n1,n2],aside(n2,'duplicate')))
    assert 'A need cannot duplicate itself.' in errors(plan_with([n1,n2],aside(n2,'duplicate',duplicate_of=n2)))
    assert 'duplicate_of names a need outside this case.' in errors(plan_with([n1,n2],aside(n2,'duplicate',duplicate_of='rev-x')))
    assert 'Only a duplicate set_aside names duplicate_of.' in errors(plan_with([n1,n2],aside(n2,'not_find_or_access',duplicate_of=n1)))
    # A need with a source the other lacks is merged, so that the working list keeps every source.
    assert case['frozen_requirements'][0]['evidence_links']!=case['frozen_requirements'][1]['evidence_links']
    assert ('A duplicate cites only sources that the need it repeats cites; merge needs with other sources.'
        in errors(plan_with([n1,n2],aside(n2,'duplicate',duplicate_of=n1)),case))
    # A need set aside before the discussion stays set aside when retained, so it cannot hold the information.
    earlier=deepcopy(same);earlier['frozen_requirements'][0]['lifecycle_state']='set_aside'
    assert ('duplicate_of names a need that is set aside already: name a need of the working list, or merge the two needs.'
        in errors(plan_with([n1,n2],aside(n2,'duplicate',duplicate_of=n1)),earlier))


@pytest.mark.parametrize('other',['set_aside','revise'])
def test_the_need_a_duplicate_repeats_is_not_set_aside_or_rewritten(setup,other):
    case,(n1,n2),messages,allowed=built(setup);same=same_sources(case,1)
    first=(aside(n1,'duplicate','A1',duplicate_of=n2) if other=='set_aside' else
        {'action_id':'A1','action':'revise','parent_revision_ids':[n1],'statement':'Users can find the access conditions of open '
         'datasets.','evidence_links':[link(case)],'rationale':'Narrowed.'})
    plan=plan_with([n1,n2],first,aside(n2,'duplicate',duplicate_of=n1))
    assert ('A duplicate set_aside needs the need it repeats retained, covered_by_base or deferred as it is.'
        in fd.plan_errors(plan,same,messages,allowed))
    assert (f'Action A2 sets {n2} aside as a duplicate of {n1}, but the plan disposes {n1} with {other}: retain {n1} as it '
        'is, or merge the two needs.') in fd.plan_feedback(plan,same,messages,allowed)


def test_a_contradiction_cites_its_passage_as_contradicting(setup):
    case,(n1,n2),messages,allowed=built(setup)
    errors=lambda action:fd.plan_errors(plan_with([n1,n2],action),case,messages,allowed)
    rule='A set_aside contradicted by a source cites that passage in evidence_links with relation contradicts.'
    assert rule in errors(aside(n2,'contradicted_by_source'))
    # The need's own supporting passage is not a contradiction.
    assert rule in errors(aside(n2,'contradicted_by_source',evidence_links=[link(case)]))
    assert errors(aside(n2,'contradicted_by_source',evidence_links=[{**link(case),'relation':'contradicts'}]))==[]


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


def test_salvage_drops_a_duplicate_whose_need_is_not_kept_as_it_is(setup):
    case,(n1,n2,n3),messages,allowed=built(setup,3);same=same_sources(case,1,2)
    pair=plan_with([n1,n2,n3],aside(n2,'duplicate',duplicate_of=n3),aside(n3,'duplicate','A3',duplicate_of=n2))
    salvaged,audit=fd.salvage_plan(pair,same,messages,allowed)
    # Each need of the pair is kept by a system deferral.
    assert [(a.action,a.parent_revision_ids) for a in salvaged.actions]==[('retain',[n1]),('defer',[n2]),('defer',[n3])]
    assert [d['problems'] for d in audit['dropped_actions']]==[['The need it duplicates is not kept as it is.']]*2
    assert fd.plan_errors(salvaged,same,messages,allowed)==[]


class Doubting(Assessing):
    """The checker sets the given flags (by default condition_supported and obligation_preserved,
    as the v6 checker did for needs whose sources state no condition or obligation) false for
    every action."""
    def __init__(self,plans,flags=('condition_supported','obligation_preserved'),**kw):
        super().__init__(plans,**kw);self.flags=flags
    def generate_structured(self,*,user,output_model,system='',step=None,**kw):
        answer=super().generate_structured(user=user,output_model=output_model,system=system,step=step,**kw)
        if contract_name(output_model)!='Checks':return answer
        self.check_model=output_model;self.check_system=system;self.check_wire=json.loads(user)
        return output_model.model_validate({'checks':[{**c,**dict.fromkeys(self.flags,False)}
            for c in answer.model_dump(mode='json')['checks']]})


def aliases(store,run):
    """The needs of the single case as the discussion names them (N1... over sorted revision IDs),
    with the source units each cites."""
    rows=sorted(store.get('run',run['run_id'])['requirements'],key=lambda r:r['revision_id'])
    return [(f'N{i+1}',r['revision_id'],{l['evidence_id'] for l in r['evidence_links']}) for i,r in enumerate(rows)]


def test_the_condition_and_obligation_flags_decide_only_written_statements(setup):
    store,run=opted_in(setup,4);named=aliases(store,run)
    # The fixture's records 0 and 2, and 1 and 3, cite the same unit.
    keep,dup=next((a,b) for a in named for b in named if a[0]<b[0] and a[2]==b[2])
    labelled,revised=[n for n in named if n not in (keep,dup)]
    store.mutate(run['run_id'],None,'fixture_label',lambda r:next(x for x in r['requirements']
        if x['revision_id']==labelled[1]).update(processing_flags=['covered_by_base']))
    def plans(data,*_):
        return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[keep[0]],'rationale':'Kept.'},
            {'action_id':'A2','action':'revise','parent_revision_ids':[revised[0]],'statement':'Users can find the contact point '
             'of a dataset.','evidence_links':sourced(data),'rationale':'Reworded.'},
            {'action_id':'A3','action':'set_aside','parent_revision_ids':[dup[0]],'rationale':'Repeats the kept need.',
             'human_question':'Restore it?','reason':'duplicate','duplicate_of':keep[0]},
            {'action_id':'A4','action':'covered_by_base','parent_revision_ids':[labelled[0]],'rationale':'The base provides it.'}],
            'concerns':[],'questions':[],'summary':'Plan.'}
    client=Doubting(plans);fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_complete'
    outcomes={o['action_id']:o for o in case['mediation']['outcomes']}
    # Kept, base-covered and set-aside needs no longer go to review on these flags; a written statement still does.
    assert {k:o['status'] for k,o in outcomes.items()}=={'A1':'retained','A2':'human_review','A3':'set_aside','A4':'retained'}
    assert outcomes['A3']['duplicate_of']==keep[1] and dup[1] not in saved['active_revision_ids']
    # The set-aside record keeps the reason and the need it repeats, under internal IDs; the checker saw the alias.
    record=next(a for a in saved['set_aside_observations'] if a['revision_id']==dup[1])
    assert record['details']=={'mediator_reason':'duplicate','duplicate_of':keep[1]}
    assert next(a for a in client.check_wire['plan']['actions'] if a['action_id']=='A3')['duplicate_of']==keep[0]
    WorkflowRun.model_validate(saved)
    assert client.check_model is fd.DefinedChecks and 'A set_aside is justified only when its reason holds' in client.check_system


@pytest.mark.parametrize('flag',['disposition_justified','preserves_distinctions'])
def test_a_set_aside_still_needs_a_justified_disposition(setup,flag):
    store,run=opted_in(setup)
    def plans(data,*_):
        needs,_=ids(data)
        return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'Kept.'},
            aside(needs[1],'statement_about_sources')],'concerns':[],'questions':[],'summary':'Plan.'}
    fd.deliberate(store,run['run_id'],Doubting(plans,flags=(flag,)))
    saved,case=case_of(store,run)
    assert {o['action_id']:o['status'] for o in case['mediation']['outcomes']}=={'A1':'human_review','A2':'human_review'}
    assert not saved['set_aside_observations']


def v1_plans(data,*_):
    needs,concerns=ids(data)
    return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'Kept.'},
        {'action_id':'A2','action':'set_aside','parent_revision_ids':[needs[1]],'rationale':'Not a find or access need.',
         'human_question':'Restore it?'}],
        'concerns':[{'concern_id':c,'status':'satisfied','action_ids':['A1'],'rationale':'Kept.'} for c in concerns],
        'questions':[],'summary':'Plan.'}


@pytest.mark.parametrize('plans',[retain_all,v1_plans])
def test_a_v1_discussion_keeps_its_checks_and_gate(setup,plans):
    store,run,_=prepared(setup,2);assert fd.discussion_policy(run)=='rq1-fa-dialogue-v1'
    client=Doubting(plans);fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run)
    assert client.check_model is fd.Checks and {o['status'] for o in case['mediation']['outcomes']}=={'human_review'}


@pytest.mark.parametrize('quote,status',[(None,'set_aside'),('A sentence the source never says.','human_review')])
def test_a_set_aside_on_a_contradiction_rests_on_a_passage_that_exists(setup,quote,status):
    store,run=opted_in(setup)
    def plans(data,*_):
        needs,_=ids(data);cited=[{**sourced(data)[0],'relation':'contradicts'}]
        if quote:cited=[{**cited[0],'quote':quote,'quote_start':None}]
        return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'Kept.'},
            {'action_id':'A2','action':'set_aside','parent_revision_ids':[needs[1]],'rationale':'The source says otherwise.',
             'human_question':'Restore it?','reason':'contradicted_by_source','evidence_links':cited}],
            'concerns':[],'questions':[],'summary':'Plan.'}
    fd.deliberate(store,run['run_id'],Assessing(plans))
    saved,case=case_of(store,run)
    row=next(o for o in case['mediation']['outcomes'] if o['action_id']=='A2')
    assert row['status']==status and row['applied']==(status=='set_aside')
    if quote:assert row['human_question'].startswith('The passage cited as contradicting this need was not found exactly once')


def test_a_quotation_is_found_at_its_offset_or_exactly_once():
    class Store:
        def get(self,kind,identifier):
            if identifier!='e1':raise KeyError(identifier)
            return {'content':'open data. Closed data. open data.'}
    found=lambda quote,start,eid='e1':fd.quoted(Store(),EvidenceLink(evidence_id=eid,quote=quote,quote_start=start),{'e1','e2'})
    assert found('open data.',0) and found('open data.',24) and found('Closed data.',None) and found('Closed data.',3)
    # Repeated, and the offset does not point at it: not found exactly once.
    assert not found('open data.',None) and not found('open data.',5)
    assert not found('A new sentence.',None) and not found('open data.',0,'e2') and not found('open data.',0,'e3')


def experienced(claims):
    """The first role brings these claims in both of its initial attempts; every claim is excluded."""
    roles=[]
    def answer(data,role):
        roles.append(role)
        return claims if role==roles[0] and not data.get('draft') else []
    def plans(data,*_):
        plan=retain_all(data);plan['experience']=[{'claim_id':x['claim_id'],'decision':'exclude','rationale':'Not needed.'}
            for m in data['messages'] for x in m.get('experience',[])]
        return plan
    return Experienced(plans,answer),roles


CLAIM={'revision_ids':['N1'],'task':'Find data','experience':'When I search, I filter by each part.','claim':'Change N1.'}


@pytest.mark.parametrize('kinds,problem',[(['keep','split'],(1,'it is keep, but a claim proposes a change')),
    (['split','drop'],(2,'a review holds one claim'))])
def test_a_keep_or_second_claim_is_corrected_then_left_out_not_failing_the_review(setup,kinds,problem):
    store,run=opted_in(setup);client,roles=experienced([{**CLAIM,'kind':k} for k in kinds])
    fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_complete'
    first,last=case['discussion_trace']['phases']['initial:'+roles[0]]['attempts']
    index,text=problem
    assert first['errors']==[e for e in first['errors'] if e.startswith('Experience claim ')] and any(
        e.startswith(f'Experience claim {index}: {text}') for e in first['errors'])
    assert [r['index'] for r in last['experience_removed']]==[index-1]
    message=next(m for m in case['messages'] if m['role_id']==roles[0] and m['round']==1)
    assert [x['kind'] for x in message['experience']]==['split'] and message['concerns']


def test_the_review_schema_shows_one_change_claim_and_parsing_accepts_more():
    schema=fd.ExperienceReview.model_json_schema()
    assert schema['properties']['experience']['maxItems']==1
    assert schema['$defs']['ExperienceClaim']['properties']['kind']['enum']==['merge','split','drop','missing_need']
    claim={**CLAIM,'revision_ids':['n1']}
    answer=fd.ExperienceReview(summary='s',experience=[{**claim,'kind':'keep'},{**claim,'kind':'split'},{**claim,'kind':'drop'}])
    assert [(i,p.split(':')[0].split(',')[0]) for i,p in fd.experience_problems(answer,['n1'])]==[(0,'it is keep'),(2,'a review holds one claim')]
    with pytest.raises(ValidationError):fd.ExperienceReview(summary='s',experience=[{**claim,'kind':'split'}]*5)
    assert 'you may add one experience claim' in fd.EXPERIENCE_GUIDANCE and 'A need you agree with needs no claim.' in fd.EXPERIENCE_GUIDANCE


def test_the_check_schema_defines_the_statement_flags():
    fields=fd.DefinedChecks.model_json_schema()['$defs']['DefinedCheck']['properties']
    assert set(fields)==set(fd.Check.model_json_schema()['properties'])
    for flag in ('condition_supported','obligation_preserved'):
        assert 'For an action that writes a statement' in fields[flag]['description']
        assert fields[flag]['description'].endswith('true.')
    assert 'description' not in fd.DefinedChecks.model_json_schema()['$defs']['DefinedCheck']
