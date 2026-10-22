"""Synthetic tests of the experience claims and noted concerns added in rq1-fa-dialogue-v6 (kept in v7; from v8 a
review holds at most one claim, which proposes a change): no evaluation answers or live generation."""
import json
import pytest
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_fa_workflow import Dialogue, contract_name
from test_base_review import prepared
from test_fa_dialogue_v3 import Mediator, opted_in, retain_all, ids, case_of, built, kept
from requirement_reuse_service.workflow import fa_discussion as fd


class Experienced(Mediator):
    """Scripted roles that also bring experience: claims(wire, role_id) gives a role's claims."""
    def __init__(self,plans,claims,objection=True):
        super().__init__(plans,objection=objection);self.claims=claims;self.seen=[]
    def generate_structured(self,*,user,output_model,system='',step=None,**kw):
        self.seen.append((contract_name(output_model),system,json.loads(user)))
        answer=super().generate_structured(user=user,output_model=output_model,system=system,step=step,**kw)
        if output_model is not fd.ExperienceReview:return answer
        data=json.loads(user)
        return output_model.model_validate({**answer.model_dump(mode='json'),'experience':self.claims(data,data['role']['id'])})


def first_role_claims(roles):
    """One initial claim from each of the first two roles to speak: drop N2, and a need the case lacks."""
    def claims(data,role):
        roles.append(role)
        if data.get('draft') or len(roles)>2:return []
        if len(roles)==1:
            return [{'kind':'drop','revision_ids':['N2'],'task':'Publish datasets of the unit','experience':'When I publish a dataset, '
                 'nobody asks me for this detail.','claim':'N2 is not needed in practice.','query':'publisher detail request'}]
        return [{'kind':'missing_need','revision_ids':['N1'],'task':'Publish datasets of the unit','experience':'When I publish a '
                 'dataset, users ask me how often it is updated.','claim':'A need is missing.',
                 'proposed_statement':'Users can find how often a dataset is updated.'}]
    return claims


def decide(data,*_):
    """Admit both claims: the drop supports a set-aside of N2, the missing need becomes a proposal."""
    needs,_=ids(data)
    return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'Kept.'},
            {'action_id':'A2','action':'set_aside','parent_revision_ids':[needs[1]],'rationale':'Publishers report no use.',
             'human_question':'Restore it if a source shows the need?','experience_ids':['X1'],'reason':'not_find_or_access'}],
        'experience':[{'claim_id':'X1','decision':'admit','rationale':'Fits the publishing task of this case.'},
            {'claim_id':'X2','decision':'admit','rationale':'Fits the publishing task.'}],
        'proposals':[{'proposal_id':'P1','statement':'Users can find how often a dataset is updated.','experience_ids':['X2'],
            'revision_ids':[needs[0]],'rationale':'Proposed from experience; no passage in the packet supports it.'}],
        'concerns':[],'questions':[],'summary':'Plan with experience.'}


def test_experience_is_admitted_noted_and_kept_apart_from_sources(setup):
    store,run=opted_in(setup);roles=[];client=Experienced(decide,first_role_claims(roles))
    fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run);n1,n2=case['revision_ids']
    assert case['stop_reason']=='bounded_fa_dialogue_complete'
    claims=[x for m in case['messages'] for x in m.get('experience',[])]
    assert [x['kind'] for x in claims]==['drop','missing_need'] and all(x['claim_id'].startswith('experience-') for x in claims)
    assert claims[0]['revision_ids']==[n2] and all('experience' in m for m in case['messages'])
    # Decisions come back under the internal claim IDs.
    assert [d['claim_id'] for d in case['mediation']['experience_decisions']]==[x['claim_id'] for x in claims]
    outcomes={o['action_id']:o for o in case['mediation']['outcomes']}
    assert outcomes['A2']['status']=='set_aside' and outcomes['A2']['applied'] and outcomes['A2']['experience_ids']==[claims[0]['claim_id']]
    # A need proposed from experience alone is a review row, never applied.
    proposal=outcomes['P1']
    assert proposal['status']=='experience_proposal' and not proposal['applied'] and not proposal['human_accepted']
    assert proposal['role_ids']==[roles[1]] and proposal['related_revision_ids']==[n1] and proposal['parent_revision_ids']==[]
    assert len(saved['requirements'])==len(run['requirements']) and saved['active_revision_ids']==[n1]
    # The set-aside says which admitted claim it rests on.
    assert saved['set_aside_observations'][-1]['revision_id']==n2 and saved['set_aside_observations'][-1]['experience_ids']==[claims[0]['claim_id']]
    # Unanswered concerns are recorded as noted against the actions on their needs.
    concerns=[c['concern_id'] for m in case['messages'] for c in m['concerns']]
    noted=case['mediation']['concern_dispositions']
    assert [d['concern_id'] for d in noted]==concerns and {d['status'] for d in noted}=={'noted'} and all(d['derived'] for d in noted)
    assert all(d['action_ids']==['A1','A2'] for d in noted)
    m=saved['metrics']
    assert (m['experience_claims'],m['experience_admitted'],m['experience_excluded'])==(2,2,0)
    assert (m['experience_actions'],m['experience_applied_changes'],m['experience_proposals'],m['noted_concerns'])==(1,1,1,len(concerns))
    # Roles get the experience rules, the checker the evidence rule; the mediator sees aliases and role cards.
    assert all(fd.EXPERIENCE_GUIDANCE in s for name,s,_ in client.seen if name=='Review')
    assert any(fd.EXPERIENCE_CHECK_GUIDANCE in s for name,s,_ in client.seen if name=='Checks')
    draft=next(p for name,_,p in client.seen if name=='Plan')
    assert [x['claim_id'] for m in draft['messages'] for x in m['experience']]==['X1','X2']
    assert [r['id'] for r in draft['roles']]==case['participants'] and all('purpose' in r and 'focus_questions' in r for r in draft['roles'])
    assert 'decide experience claims as the plan bookkeeping says' in next(s for name,s,_ in client.seen if name=='Plan')


def test_experience_queries_are_searched_in_turn_across_roles(setup,monkeypatch):
    store,run=opted_in(setup);asked=[];real=fd.retrieve_frozen
    monkeypatch.setattr(fd,'retrieve_frozen',lambda store,run,queries,existing:(asked.append(list(queries)),real(store,run,queries,existing))[1])
    class Asking(Experienced):
        def generate_structured(self,*,user,output_model,system='',step=None,**kw):
            answer=super().generate_structured(user=user,output_model=output_model,system=system,step=step,**kw)
            if output_model is not fd.ExperienceReview or json.loads(user).get('draft'):return answer
            first=json.loads(user)['role']['id']==roles[0]
            return output_model.model_validate({**answer.model_dump(mode='json'),'evidence_queries':['a1','a2'] if first else ['b1']})
    roles=[]
    def claims(data,role):
        roles.append(role)
        if data.get('draft'):return []
        return [{'kind':'split','revision_ids':['N1'],'task':'Find data','experience':'When I search, I filter by each part.',
                 'claim':'N1 holds two needs.','query':'ax' if role==roles[0] else 'bx'}]
    def plans(data,*_):
        plan=retain_all(data);plan['experience']=[{'claim_id':x['claim_id'],'decision':'exclude','rationale':'Not needed here.'}
            for m in data['messages'] for x in m.get('experience',[])]
        return plan
    fd.deliberate(store,run['run_id'],Asking(plans,claims))
    assert asked==[['a1','b1','a2','bx','ax']]
    saved,case=case_of(store,run)
    assert {d['decision'] for d in case['mediation']['experience_decisions']}=={'exclude'}
    assert saved['metrics']['experience_excluded']==2 and saved['metrics']['experience_actions']==0


def test_a_claim_naming_another_profile_gets_one_correction(setup):
    store,run=opted_in(setup);roles=[]
    def claims(data,role):
        roles.append(role)
        if role!=roles[0] or data.get('draft'):return []
        named=sum(r==roles[0] for r in roles)==1
        return [{'kind':'split','revision_ids':['N1'],'task':'Publish health data','claim':'N1 holds two needs.',
            'experience':'When I publish health data '+('following HealthDCAT-AP' if named else 'for researchers')+', I record this.'}]
    def plans(data,*_):
        plan=retain_all(data);plan['experience']=[{'claim_id':x['claim_id'],'decision':'admit','rationale':'Fits the role.'}
            for m in data['messages'] for x in m.get('experience',[])]
        return plan
    client=Experienced(plans,claims);fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run)
    first=case['discussion_trace']['phases']['initial:'+roles[0]]['attempts']
    assert first[0]['errors']==['Experience claim 1: it names HealthDCAT-AP: never name an existing application profile; describe '
        'the practice of your own role.']
    assert first[1]['errors']==[] and 'HealthDCAT-AP' not in json.dumps(case['messages'])
    retry=[s for name,s,p in client.seen if name=='Review' and p['role']['id']==roles[0] and not p.get('draft')][1]
    assert 'Your previous answer was rejected' in retry and 'Experience claim 1: it names HealthDCAT-AP' in retry


def test_profile_names_are_matched_but_the_base_and_its_adjectives_are_not():
    found=lambda text:[m.group() for m in fd.PROFILE_NAME.finditer(text)]
    assert found('HealthDCAT-AP, GeoDCAT-AP 3, StatDCAT-AP, mobilityDCAT-AP, DCAT-AP-NO, DCAT-AP_IT, DCAT-AP.de, DCAT-AP-HVD')==[
        'HealthDCAT-AP','GeoDCAT-AP','StatDCAT-AP','mobilityDCAT-AP','DCAT-AP-NO','DCAT-AP_IT','DCAT-AP.de','DCAT-AP-HVD']
    assert found('Health DCAT-AP, healthdcat-ap, geo-dcat, Stat DCAT')==['Health DCAT-AP','healthdcat-ap','geo-dcat','Stat DCAT']
    assert found('DCAT-AP 1.1, a DCAT-AP-compliant catalogue, DCAT-AP-based records, dcat:Dataset, DCAT, The DCAT-AP, '
        'geographic DCAT-AP records, statistical data')==[]


@pytest.mark.parametrize('claim,problem',[
    ({'kind':'drop','revision_ids':['rev-x']},'it lists rev-x in revision_ids, but the needs of this case are only'),
    ({'kind':'missing_need','revision_ids':[]},'it is missing_need but has no proposed_statement'),
    ({'kind':'drop','revision_ids':[]},'it is drop but names no need'),
    ({'kind':'merge','revision_ids':['N']},'it is merge but names fewer than two needs'),
    ({'kind':'split','revision_ids':['N'],'query':'GeoDCAT-AP location'},'it names GeoDCAT-AP'),
])
def test_experience_claim_problems(setup,claim,problem):
    case,(n1,n2),_,_=built(setup)
    claim={'task':'Find data','experience':'When I search, I filter.','claim':'It follows.',**claim}
    claim['revision_ids']=[n1 if r=='N' else r for r in claim['revision_ids']]
    answer=fd.ExperienceReview(summary='s',experience=[claim])
    errors=fd.experience_errors(answer,case)
    assert len(errors)==1 and errors[0].startswith('Experience claim 1: '+problem)
    assert errors[0] in fd.review_feedback(answer,case,set())
    assert fd.experience_errors(fd.Review(summary='s'),case)==[]


def claim_messages(rids):
    n1,n2=rids
    return [{'role_id':'r1','concerns':[{'concern_id':'c1','revision_ids':[n1]},{'concern_id':'c2','revision_ids':[n2]}],
        'experience':[{'claim_id':'x1','kind':'drop','revision_ids':[n2]},{'claim_id':'x2','kind':'missing_need','revision_ids':[]}]}]


def v6(rids,**extra):
    """A valid v6 plan: needs retained, concerns left to be noted, both claims decided."""
    return fd.ExperiencePlan.model_validate({**kept(rids,concerns=[]),'experience':[
        {'claim_id':'x1','decision':'admit','rationale':'Fits.'},{'claim_id':'x2','decision':'exclude','rationale':'Outside the task.'}],**extra})


def test_unanswered_concerns_are_valid_in_v6_and_answered_ones_still_checked(setup):
    case,rids,_,allowed=built(setup);messages=claim_messages(rids)
    plan=v6(rids);assert fd.plan_errors(plan,case,messages,allowed)==[]
    notes=fd.plan_feedback(plan,case,messages,allowed);assert not any('has no disposition' in n for n in notes)
    # The v5 Plan contract still requires every concern.
    assert any(e.startswith('Account for every saved stakeholder concern exactly once') for e in
        fd.plan_errors(fd.Plan.model_validate(kept(rids,concerns=[])),case,messages,allowed))
    twice=v6(rids,concerns=[{'concern_id':'c1','status':'rejected_with_reason','rationale':'No.'}]*2+
        [{'concern_id':'c9','status':'rejected_with_reason','rationale':'No.'}])
    assert 'Answer a saved stakeholder concern at most once: {"repeated":["c1"],"unknown":["c9"]}' in fd.plan_errors(twice,case,messages,allowed)
    assert 'Concern c1 has 2 dispositions: keep at most one.' in fd.plan_feedback(twice,case,messages,allowed)
    # A question may list an unanswered concern; an answered one must list the question back.
    question={'question_id':'Q1','revision_ids':[rids[0]],'concern_ids':['c1'],'question':'Which?','alternatives':['a'],'rationale':'r'}
    assert fd.plan_errors(v6(rids,questions=[question]),case,messages,allowed)==[]
    linked=v6(rids,questions=[question],concerns=[{'concern_id':'c1','status':'rejected_with_reason','rationale':'No.'}])
    assert 'Question and concern links must be reciprocal.' in fd.plan_errors(linked,case,messages,allowed)


def test_every_claim_is_decided_once_and_only_admitted_claims_are_cited(setup):
    case,rids,_,allowed=built(setup);messages=claim_messages(rids)
    errors=lambda plan:fd.plan_errors(plan,case,messages,allowed)
    undecided=v6(rids);undecided.experience=undecided.experience[:1]
    assert 'Decide every experience claim exactly once: {"missing":["x2"],"repeated":[],"unknown":[]}' in errors(undecided)
    assert 'Experience claim x2 has no decision: add exactly one experience entry for x2 (admit or exclude, with the reason).' in \
        fd.plan_feedback(undecided,case,messages,allowed)
    cited=v6(rids);cited.actions[1].experience_ids=['x2']
    assert 'An action may cite only admitted experience claims.' in errors(cited)
    assert 'Action A2 cites x2 in experience_ids, but the plan does not admit it: cite only admitted claims.' in fd.plan_feedback(cited,case,messages,allowed)
    proposal={'proposal_id':'P1','statement':'Users can find the update frequency.','experience_ids':['x2'],'revision_ids':['rev-x'],'rationale':'r'}
    bad=v6(rids,proposals=[proposal,proposal])
    assert {'A proposal needs admitted experience claims.','A proposal names a need outside this case.','Proposal IDs must be unique.'}<=set(errors(bad))
    good=v6(rids,proposals=[{**proposal,'experience_ids':['x1'],'revision_ids':[rids[1]]}])
    assert errors(good)==[]


def test_salvage_excludes_undecided_claims_and_drops_what_cites_them(setup):
    case,rids,_,allowed=built(setup);messages=claim_messages(rids)
    plan=v6(rids,proposals=[{'proposal_id':'P1','statement':'S.','experience_ids':['x2'],'rationale':'r'},
        {'proposal_id':'P2','statement':'T.','experience_ids':['x1'],'rationale':'r'}],
        concerns=[{'concern_id':'c2','status':'addressed','action_ids':['A9'],'rationale':'Answered by a missing action.'}])
    plan.experience=[plan.experience[0]];plan.actions[1].experience_ids=['x2']
    assert fd.plan_errors(plan,case,messages,allowed)
    salvaged,audit=fd.salvage_plan(plan,case,messages,allowed)
    assert fd.plan_errors(salvaged,case,messages,allowed)==[] and isinstance(salvaged,fd.ExperiencePlan)
    assert [(d.claim_id,d.decision) for d in salvaged.experience]==[('x1','admit'),('x2','exclude')]
    assert salvaged.experience[1].rationale.startswith('System salvage:') and audit['system_excluded_claim_ids']==['x2']
    # A2 cited the undecided claim: dropped, and its need deferred by the system.
    assert [(a.action_id,a.action) for a in salvaged.actions]==[('A1','retain'),('salvage-1','defer')]
    assert audit['dropped_actions'][0]['problems']==['Cites experience the plan does not validly admit.']
    assert [p.proposal_id for p in salvaged.proposals]==['P2'] and audit['dropped_proposal_ids']==['P1']
    # Only the inconsistently answered concern goes to the system question; c1 stays to be noted.
    assert audit['replaced_concern_ids']==['c2'] and [c.concern_id for c in salvaged.concerns]==['c2']


def test_noted_concerns_and_proposal_rows():
    plan=fd.ExperiencePlan.model_validate({'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':['n1'],'rationale':'r'},
        {'action_id':'A2','action':'retain','parent_revision_ids':['n2'],'rationale':'r'}],
        'questions':[{'question_id':'Q1','revision_ids':['n2'],'concern_ids':['c2'],'question':'?','alternatives':['a'],'rationale':'r'}],
        'concerns':[{'concern_id':'c3','status':'rejected_with_reason','rationale':'No source.'}],
        'experience':[{'claim_id':'x1','decision':'admit','rationale':'Fits.'}],
        'proposals':[{'proposal_id':'P1','statement':'Users can find X.','experience_ids':['x1'],'revision_ids':['n1'],'rationale':'r'}],'summary':'s'})
    messages=[{'role_id':'r1','concerns':[{'concern_id':'c1','revision_ids':['n1','n2']},{'concern_id':'c2','revision_ids':['n2']},
        {'concern_id':'c3','revision_ids':['n1']}],'experience':[{'claim_id':'x1'}]}]
    # A concern a question lists stays open; any other unanswered concern is noted.
    assert [(d['concern_id'],d['status'],d['action_ids'],d['question_ids']) for d in fd.noted_concerns(plan,messages)]==[
        ('c1','noted',['A1','A2'],[]),('c2','unresolved',['A2'],['Q1'])]
    [row]=fd.proposal_rows(plan,messages)
    assert (row['action'],row['applied'],row['role_ids'],row['related_revision_ids'],row['parent_revision_ids'])==('experience_proposal',False,['r1'],['n1'],[])


def test_a_response_naming_a_draft_action_in_a_claim_gets_that_actions_need(setup):
    case,(n1,n2),_,_=built(setup)
    draft={'actions':[{'action_id':'A2','parent_revision_ids':[n2]}],'questions':[]}
    answer=fd.ExperienceReview(summary='s',experience=[{'kind':'drop','revision_ids':['A2'],'task':'t','experience':'e','claim':'c'}])
    fixed,repairs=fd.repair_review(answer,case,draft)
    assert isinstance(fixed,fd.ExperienceReview) and fixed.experience[0].revision_ids==[n2]
    assert repairs==[{'kind':'experience_need_from_draft','experience_index':0,'from':'A2','to':[n2]}]


@pytest.mark.parametrize('propose',[True,False])
def test_a_proposal_in_the_draft_is_put_to_every_role(setup,propose):
    store,run=opted_in(setup);roles=[]
    def claims(data,role):
        roles.append(role)
        if role!=roles[0] or data.get('draft'):return []
        # A missing need that names no need of the case raises no objection.
        return [{'kind':'missing_need','task':'Publish datasets','experience':'When I publish, users ask for the update frequency.',
            'claim':'A need is missing.','proposed_statement':'Users can find how often a dataset is updated.'}]
    def plans(data,*_):
        plan=retain_all(data)
        plan['experience']=[{'claim_id':x['claim_id'],'decision':'admit','rationale':'Fits.'} for m in data['messages'] for x in m.get('experience',[])]
        plan['proposals']=[{'proposal_id':'P1','statement':'Users can find how often a dataset is updated.','experience_ids':['X1'],
            'rationale':'From experience alone.'}] if propose else []
        return plan
    # Without objections or changes, only a proposal asks the roles to respond.
    fd.deliberate(store,run['run_id'],Experienced(plans,claims,objection=False))
    saved,case=case_of(store,run)
    assert len(case['discussion_trace']['targeted_roles'])==(2 if propose else 0)
    assert [o['action_id'] for o in case['mediation']['outcomes'] if o['status']=='experience_proposal']==(['P1'] if propose else [])


def test_a_v1_discussion_keeps_its_contracts_prompt_and_messages(setup):
    store,run,_=prepared(setup,2);assert fd.discussion_policy(run)=='rq1-fa-dialogue-v1'
    class Watching(Dialogue):
        def __init__(self):super().__init__(objection=True);self.models=[];self.systems=[];self.wires=[]
        def generate_structured(self,*,user,output_model,system='',step=None,**kw):
            self.models.append(output_model.__name__);self.systems.append((output_model.__name__,system));self.wires.append(json.loads(user))
            return super().generate_structured(user=user,output_model=output_model,step=step,**kw)
    client=Watching();fd.deliberate(store,run['run_id'],client)
    assert not {'ExperienceReview','ExperiencePlan'}&set(client.models) and {'Review','Plan'}<=set(client.models)
    plan_system=next(s for name,s in client.systems if name=='Plan')
    assert plan_system==fd.WRITE_GUIDANCE+(' Mediate needs, not stakeholder rank. Account for every current need exactly once and '
        'every concern exactly once with reciprocal action/question links. Preserve conditions and distinct needs. '
        'Use source-supported priority only; otherwise defer with alternatives and a human question. '
        'retain/revise/split/merge/add/recover/covered_by_base/reversible set_aside/defer are provisional. '
        'A set-aside must have a review question. A covered_by_base decision requires an existing checked base match. '
        'Do not force consensus or interpret silence as approval. Return Plan JSON.')
    mediation=[w for name,w in zip(client.models,client.wires) if name=='Plan']
    assert mediation and all('roles' not in w for w in mediation)
    saved=store.get('run',run['run_id'])
    assert all('experience' not in m for c in saved['deliberations'] for m in c['messages'])
    assert 'experience_claims' not in saved['metrics']


def test_an_addition_from_experience_alone_is_told_to_be_a_proposal(setup):
    case,rids,_,allowed=built(setup);messages=claim_messages(rids)
    plan=v6(rids);plan.actions.append(fd.ExperienceAction(action_id='A3',action='add',statement='Users can find the update frequency.',
        rationale='From experience.',experience_ids=['x1']))
    assert 'Changed need requires a statement and source links.' in fd.plan_errors(plan,case,messages,allowed)
    assert ('Action A3 (add) cites no source passage: a need proposed from experience alone goes to proposals, with its '
        'experience_ids and closest needs, not to actions.') in fd.plan_feedback(plan,case,messages,allowed)


def test_a_claim_that_stays_invalid_is_left_out_and_the_review_kept(setup):
    store,run=opted_in(setup);roles=[]
    def claims(data,role):
        roles.append(role)
        if role!=roles[0] or data.get('draft'):return []
        # Still named after its correction.
        return [{'kind':'split','revision_ids':['N1'],'task':'Publish health data','claim':'N1 holds two needs.',
            'experience':'When I publish health data following HealthDCAT-AP, I record this.'}]
    fd.deliberate(store,run['run_id'],Experienced(retain_all,claims))
    saved,case=case_of(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_complete'
    phase=case['discussion_trace']['phases']['initial:'+roles[0]]
    first,last=phase['attempts']
    assert first['errors'] and last['errors']==[] and last['output']['experience']==[] and phase['output']['experience']==[]
    assert [r['index'] for r in last['experience_removed']]==[0] and 'HealthDCAT-AP' in last['experience_removed'][0]['claim']['experience']
    assert last['rejected_errors']==first['errors'] and last['model_output']['experience']
    # The role's concerns stay in the discussion.
    assert next(m for m in case['messages'] if m['role_id']==roles[0] and m['round']==1)['concerns']


def test_a_response_naming_a_proposal_gets_its_closest_needs(setup):
    case,(n1,n2),_,_=built(setup)
    draft={'actions':[],'questions':[],'proposals':[{'proposal_id':'P1','revision_ids':[n1]},{'proposal_id':'P2','revision_ids':[]}]}
    answer=fd.ExperienceReview(summary='s',concerns=[{'revision_ids':['P1'],'kind':'scope','statement':'Not needed.'},
        {'revision_ids':['P2'],'kind':'scope','statement':'Not needed either.'}])
    fixed,repairs=fd.repair_review(answer,case,draft)
    # A proposal without closest needs has nothing to map to.
    assert [c.revision_ids for c in fixed.concerns]==[[n1],['P2']]
    assert repairs==[{'kind':'concern_need_from_draft','concern_index':0,'from':'P1','to':[n1]}]


def test_a_proposal_id_must_differ_from_the_action_ids(setup):
    case,rids,_,allowed=built(setup);messages=claim_messages(rids)
    plan=v6(rids,proposals=[{'proposal_id':'A1','statement':'Users can find the update frequency.','experience_ids':['x1'],'rationale':'r'}])
    assert 'A proposal ID must differ from every action ID.' in fd.plan_errors(plan,case,messages,allowed)
    assert 'Proposal ID A1 is also an action ID; give the proposal its own ID.' in fd.plan_feedback(plan,case,messages,allowed)
    plan.actions[1].parent_revision_ids=[]
    salvaged,audit=fd.salvage_plan(plan,case,messages,allowed)
    assert salvaged.proposals==[] and audit['dropped_proposal_ids']==['A1'] and fd.plan_errors(salvaged,case,messages,allowed)==[]


def test_a_salvage_marks_its_exclusions_and_rejected_rows_are_not_counted(setup):
    store,run=opted_in(setup);roles=[]
    def plans(data,*_):
        # Valid dispositions, but the claim stays undecided and A2 cites it: salvaged every time.
        needs,_=ids(data)
        return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'Kept.'},
            {'action_id':'A2','action':'retain','parent_revision_ids':[needs[1]],'rationale':'Kept.','experience_ids':['X1']}],
            'concerns':[],'questions':[],'summary':'Draft.'}
    fd.deliberate(store,run['run_id'],Experienced(plans,first_role_claims(roles)))
    saved,case=case_of(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_salvaged'
    assert {d['decision'] for d in case['mediation']['experience_decisions']}=={'exclude'}
    assert all(d['system'] for d in case['mediation']['experience_decisions'])
    rejected=next(o for o in case['mediation']['outcomes'] if o['action_id']=='A2')
    assert rejected['salvage_rejected'] and rejected['experience_ids']
    m=saved['metrics']
    assert (m['experience_excluded'],m['experience_excluded_by_system'],m['experience_actions'])==(0,2,0)


def test_a_cut_v6_correction_says_how_many_problems_it_does_not_show(setup):
    from requirement_reuse_service.workflow import base_review as br
    case,rids,_,allowed=built(setup)
    messages=[{'role_id':'r1','concerns':[],'experience':[{'claim_id':f'x{i}','kind':'drop','revision_ids':[rids[0]]} for i in range(40)]}]
    plan=fd.ExperiencePlan.model_validate(kept(rids,concerns=[]))
    notes=fd.plan_feedback(plan,case,messages,allowed);assert len(notes)==40
    text=br.correction({'output':plan.model_dump(mode='json'),'errors':['Decide every experience claim exactly once.'],'feedback':notes},{})
    assert text.endswith(' (10 more problems not shown)') and 'Experience claim x29 ' in text and 'Experience claim x30 ' not in text


def test_a_v6_salvage_beyond_the_plan_contract_is_not_salvaged(setup):
    case,rids,_,allowed=built(setup)
    messages=[{'role_id':'r1','concerns':[],'experience':[{'claim_id':f'x{i}','kind':'drop','revision_ids':[rids[0]]} for i in range(65)]}]
    plan=fd.ExperiencePlan.model_validate(kept(rids,concerns=[]))
    # 65 claims need 65 decisions, more than the 64 a plan holds: refused, not raised.
    salvaged,audit=fd.salvage_plan(plan,case,messages,allowed)
    assert salvaged is None and audit['status']=='not_salvaged' and audit['reason'].startswith('Salvaged plan exceeds the plan contract')
