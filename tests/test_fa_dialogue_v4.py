"""Synthetic tests of the rules added in rq1-fa-dialogue-v4 (kept through v6): no evaluation answers or live generation."""
import json
import pytest
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_fa_workflow import Dialogue, contract_name
from test_base_review import prepared
from test_fa_dialogue_v3 import Mediator, opted_in, retain_all, ids, case_of, built, plan_model  # noqa: F401  (fixture)
from requirement_reuse_service.workflow import base_review as br, fa_discussion as fd, stakeholder_workflow as old
from requirement_reuse_service.workflow.models import WorkflowRun


class Recording(Mediator):
    """Records the system prompt of every stakeholder review and the output cap of every call."""
    def __init__(self,plans,objection=True):super().__init__(plans,objection=objection);self.review_systems=[];self.caps=[]
    def generate_structured(self,*,user,output_model,system='',step=None,**kw):
        self.caps.append((contract_name(output_model),kw.get('max_tokens')))
        if contract_name(output_model)=='Review':self.review_systems.append(system)
        return super().generate_structured(user=user,output_model=output_model,system=system,step=step,**kw)


def caps(client,*names):
    return {cap for name,cap in client.caps if name in names}


def test_policy_names():
    assert fd.BASE_POLICY=='rq1-fa-dialogue-v10' and br.POLICY=='rq1-base-expert-v5'
    assert fd.BASE_POLICIES=={'rq1-fa-dialogue-v2','rq1-fa-dialogue-v3','rq1-fa-dialogue-v4','rq1-fa-dialogue-v5','rq1-fa-dialogue-v6','rq1-fa-dialogue-v7',
        'rq1-fa-dialogue-v8','rq1-fa-dialogue-v9','rq1-fa-dialogue-v10'}


def test_stakeholders_get_the_concern_rules_and_plans_start_at_8000_tokens(setup):
    store,run=opted_in(setup);client=Recording(retain_all);fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_complete'
    assert len(client.review_systems)==4  # two initial positions and two responses
    assert all(fd.BASE_ROLE_GUIDANCE in s and fd.CONCERN_GUIDANCE in s for s in client.review_systems)
    assert not any(fd.CONCERN_GUIDANCE in s for s in client.plan_systems)
    assert caps(client,'Plan')=={8000} and caps(client,'Review','Checks')=={4000}
    phases=case['discussion_trace']['phases']
    draft=phases['draft']['context_budget']
    assert draft['policy_version']=='rq1-fa-context-budget-case-v3' and draft['limit_characters']==66000
    assert draft['output_tokens']=={'first':8000,'retry':8000}
    assert phases['check']['context_budget']['output_tokens']=={'first':4000,'retry':8000}
    # Two needs: the v4 limits plus one extra need's share (v5).
    assert (case['max_calls'],case['total_output_budget'],case['max_seconds'])==(17,136000,2100)


def test_a_legacy_v1_discussion_keeps_its_prompts_and_limits(setup):
    store,run,_=prepared(setup,2);assert fd.discussion_policy(run)=='rq1-fa-dialogue-v1'
    client=Recording(retain_all);fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run)
    assert client.review_systems and not any(fd.CONCERN_GUIDANCE in s for s in client.review_systems)
    assert caps(client,'Plan')=={4000}
    assert (case['max_calls'],case['total_output_budget'],case['max_seconds'])==(14,112000,1800)
    draft=case['discussion_trace']['phases']['draft']['context_budget']
    assert draft['policy_version']=='rq1-fa-context-budget-case-v1' and draft['limit_characters']==45000
    assert 'output_tokens' not in draft


def test_execution_reads_the_limits_recorded_in_the_case(setup,monkeypatch):
    # A two-need case adds one call to the base limit (v5).
    monkeypatch.setattr(fd,'BASE_CASE_LIMITS',{'max_calls':2,'total_output_budget':128000,'max_seconds':1800})
    store,run=opted_in(setup);client=Recording(retain_all);fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run)
    # Two initial positions and the draft; the first response finds the case budget spent.
    assert case['max_calls']==3 and case['model_attempts']==3
    assert case['stop_reason']=='budget_pending_human_review'
    [question]=case['mediation']['human_questions']
    assert question['question_id']=='budget' and question['alternatives']==['Retain original needs','Prepare a separately budgeted review']


@pytest.mark.parametrize('lowered,stopped',[('MAX_CONTEXT',False),('BASE_MAX_CONTEXT',True)])
def test_v4_measures_its_input_against_its_own_limit(setup,monkeypatch,lowered,stopped):
    monkeypatch.setattr(fd,lowered,10)
    store,run=opted_in(setup);fd.deliberate(store,run['run_id'],Mediator(retain_all))
    case=case_of(store,run)[1]
    if not stopped:
        assert case['stop_reason']=='bounded_fa_dialogue_complete'
        return
    assert case['stop_reason']=='budget_pending_human_review'
    [question]=case['mediation']['human_questions']
    assert question['question_id']=='budget' and 'exceeds context budget' in question['question']


def test_an_invalid_case_asks_under_invalid_output(setup):
    store,run=opted_in(setup)
    def plans(data,*_):
        needs,concerns=ids(data)
        # One action per concern and none per need: nothing can be salvaged.
        return {'actions':[{'action_id':'A1','action':'defer','parent_revision_ids':[],'rationale':'One per concern.',
                'human_question':'Which?','alternatives':['One','Other']}],
            'concerns':[{'concern_id':c,'status':'unresolved','action_ids':['A1'],'rationale':'Open.'} for c in concerns],
            'questions':[],'summary':'Draft.'}
    fd.deliberate(store,run['run_id'],Mediator(plans))
    case=case_of(store,run)[1]
    assert case['stop_reason']=='invalid_output_pending_human_review'
    [question]=case['mediation']['human_questions']
    assert question['question_id']=='invalid_output' and question['alternatives']==['Retain original needs','Prepare a separate review']


def test_a_legacy_v1_invalid_case_keeps_its_question_id(setup):
    store,run,_=prepared(setup,2)
    def plans(data,*_):
        bad=retain_all(data);bad['actions'][1]['parent_revision_ids']=[]
        return bad
    fd.deliberate(store,run['run_id'],Mediator(plans))
    case=case_of(store,run)[1]
    assert case['stop_reason']=='invalid_output_pending_human_review'
    assert case['mediation']['human_questions'][0]['question_id']=='budget'


class NamesDraftAction(Mediator):
    """In its response, the first concern names the draft's action A2 instead of the need."""
    def generate_structured(self,*,user,output_model,system='',step=None,**kw):
        answer=super().generate_structured(user=user,output_model=output_model,system=system,step=step,**kw)
        if contract_name(output_model)!='Review' or not json.loads(user).get('draft'):return answer
        raw=answer.model_dump(mode='json')
        raw['concerns'][0].update(revision_ids=['A2'],kind='scope',proposed_statement='Users can find the licence of a distribution.')
        return output_model.model_validate(raw)


def test_a_response_naming_a_draft_action_gets_that_actions_need(setup):
    store,run=opted_in(setup);fd.deliberate(store,run['run_id'],NamesDraftAction(retain_all))
    saved,case=case_of(store,run);n2=case['revision_ids'][1]
    assert case['stop_reason']=='bounded_fa_dialogue_complete'
    responses=[v for k,v in case['discussion_trace']['phases'].items() if k.startswith('response:')]
    assert len(responses)==2
    for phase in responses:
        [first]=phase['attempts']
        assert first['errors']==[] and first['model_output']['concerns'][0]['revision_ids']==['A2']
        assert first['output']['concerns'][0]['revision_ids']==[n2]
        assert first['repairs']==[{'kind':'concern_need_from_draft','concern_index':0,'from':'A2','to':[n2]}]
    assert all(c['revision_ids']==[n2] for m in case['messages'] if m['round']==2 for c in m['concerns'][:1])


def review(*lists):
    return fd.Review.model_validate({'summary':'Checked.','concerns':[{'revision_ids':ids,'kind':'scope','statement':'Missing.'} for ids in lists]})


def test_review_repair_maps_only_draft_references(setup):
    case,(n1,n2),_,_=built(setup)
    draft={'actions':[{'action_id':'A1','parent_revision_ids':[n1]},{'action_id':'A2','parent_revision_ids':[n2]},
            {'action_id':'A3','parent_revision_ids':[]}],
        'questions':[{'question_id':'salvage-review-1','revision_ids':[n1,n2]}]}
    fixed,repairs=fd.repair_review(review(['A2'],['salvage-review-1'],[n1,'A1'],['N4'],['A3'],['A1','A1']),case,draft)
    # An invented ID or an action without needs stays for correction; a repeat the model wrote stays repeated.
    assert [c.revision_ids for c in fixed.concerns]==[[n2],[n1,n2],[n1],['N4'],['A3'],[n1,n1]]
    assert repairs==[{'kind':'concern_need_from_draft','concern_index':0,'from':'A2','to':[n2]},
        {'kind':'concern_need_from_draft','concern_index':1,'from':'salvage-review-1','to':[n1,n2]},
        {'kind':'concern_need_from_draft','concern_index':2,'from':'A1','to':[n1]},
        {'kind':'concern_need_from_draft','concern_index':5,'from':'A1','to':[n1]}]
    # An ID used twice in the draft with different needs is ambiguous.
    twice={'actions':[{'action_id':'A1','parent_revision_ids':[n1]},{'action_id':'A1','parent_revision_ids':[n2]}]}
    assert fd.repair_review(review(['A1']),case,twice)==(review(['A1']),[])
    # A mapping beyond the four IDs a concern may list is not applied.
    assert fd.repair_review(review(['salvage-review-1']*3),case,draft)==(review(['salvage-review-1']*3),[])
    # A need is never remapped, even when an action has the same ID.
    clash={'actions':[{'action_id':n1,'parent_revision_ids':[n2]}]}
    assert fd.repair_review(review([n1]),case,clash)==(review([n1]),[])


def test_review_feedback_names_the_valid_needs_and_excerpts(setup):
    case,(n1,n2),_,allowed=built(setup)
    answer=fd.Review.model_validate({'summary':'Checked.','concerns':[
        {'revision_ids':[n1],'kind':'support','statement':'Fine.'},
        {'revision_ids':['N4',n2,'N4'],'kind':'scope','statement':'Missing.','evidence_ids':['E99']}]})
    notes=fd.review_feedback(answer,case,allowed)
    assert notes==[f'Concern 2 lists N4 in revision_ids, but the needs of this case are only {n1}, {n2}. To propose a need '
            'the case lacks, write it in proposed_statement of a scope concern on the closest need.',
        f'Concern 2 cites E99, but the excerpts of this packet are only E1 to E{len(allowed)}.']
    assert fd.review_feedback(review([n1]),case,allowed) is None
    # The correction names the needs by the aliases the model saw.
    text=br.correction({'output':answer.model_dump(mode='json'),'errors':old.stakeholder_review_errors(answer,case,allowed),'feedback':notes},
        {'N1':n1,'N2':n2})
    assert 'but the needs of this case are only N1, N2.' in text and n1 not in text and n2 not in text


def set_aside_second_need(store,run):
    """The second need was set aside before the discussion; cases include it for review."""
    rid=run['requirements'][1]['revision_id']
    def aside(r):
        rec=next(x for x in r['requirements'] if x['revision_id']==rid);rec['lifecycle_state']='set_aside'
        r['active_revision_ids']=[i for i in r['active_revision_ids'] if i!=rid]
        r['set_aside_observations'].append({'observation_id':(rec.get('observation_ids') or ['obs'])[0],'role_id':'scope_checker',
            'reason':'fa_scope_set_aside','revision_id':rid,'need_id':rec['requirement_id'],'rationale':'Fixture set-aside.'})
    store.mutate(run['run_id'],None,'fixture_set_aside',aside)
    return rid,store.get('run',run['run_id'])


def set_aside_plan(pick):
    """Sets aside the need that pick(packet needs) names and retains the others."""
    def plans(data,*_):
        needs,concerns=ids(data);target=pick(data['packet']['needs'])
        actions=[{'action_id':f'A{i+1}','action':'set_aside' if n==target else 'retain','parent_revision_ids':[n],
            'rationale':'Not a find or access need.' if n==target else 'Kept.','human_question':'Restore it?' if n==target else None,
            'reason':'not_find_or_access' if n==target else None}
            for i,n in enumerate(needs)]
        kept=next(a['action_id'] for a in actions if a['action']=='retain')
        return {'actions':actions,'questions':[],'summary':'Plan.',
            'concerns':[{'concern_id':c,'status':'satisfied','action_ids':[kept],'rationale':'Kept.'} for c in concerns]}
    return plans


def test_setting_aside_a_need_that_is_already_set_aside_changes_nothing(setup):
    store,run=opted_in(setup);rid,run=set_aside_second_need(store,run)
    # The mediator sees the need's lifecycle state and sets it aside again.
    fd.deliberate(store,run['run_id'],Mediator(set_aside_plan(lambda rows:next(r['revision_id'] for r in rows if r['lifecycle_state']=='set_aside'))))
    saved,case=case_of(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_complete' and rid in case['revision_ids']
    outcome=next(o for o in case['mediation']['outcomes'] if o['parent_revision_ids']==[rid])
    assert outcome['action']=='set_aside' and outcome['status']=='already_set_aside' and not outcome['applied']
    assert saved['metrics']['mediated_changes']==0
    assert [a['revision_id'] for a in saved['set_aside_observations']]==[rid]  # no second record
    assert rid not in case['discussion_trace']['after_revision_ids'] and rid not in saved['active_revision_ids']


def test_a_mediated_set_aside_is_applied_and_its_record_validates(setup):
    store,run=opted_in(setup)
    fd.deliberate(store,run['run_id'],Mediator(set_aside_plan(lambda rows:rows[-1]['revision_id'])))
    saved,case=case_of(store,run)
    outcome=next(o for o in case['mediation']['outcomes'] if o['action']=='set_aside');[rid]=outcome['parent_revision_ids']
    assert outcome['status']=='set_aside' and outcome['applied'] and saved['metrics']['mediated_changes']==1
    [record]=[a for a in saved['set_aside_observations'] if a['revision_id']==rid]
    assert record['reason']=='mediated_fa_set_aside' and record['reversible'] is True
    # A discussion continuation validates the whole run; this record failed the contract.
    WorkflowRun.model_validate(saved)


def test_feedback_tells_an_add_that_rewords_a_need_to_revise_it(setup,plan_model):
    # GPT-OSS-only JRC replay: 8 of 13 drafts that stayed invalid wrote a lone add, were told
    # "N1 is in no action", then named N1 in the add ("Addition cannot replace an existing parent").
    case,(n1,n2),messages,allowed=built(setup)
    link=dict(case['frozen_requirements'][0]['evidence_links'][0])
    lone=plan_model.model_validate({'actions':[{'action_id':'A1','action':'add','statement':'Users can find the licence of a dataset.',
            'evidence_links':[link],'rationale':'Reworded.'},{'action_id':'A2','action':'retain','parent_revision_ids':[n2],'rationale':'Kept.'}],
        'concerns':[{'concern_id':'c1','status':'addressed','action_ids':['A1'],'rationale':'Reworded.'},
            {'concern_id':'c2','status':'satisfied','action_ids':['A2'],'rationale':'Kept.'}],'summary':'Draft.'})
    notes=fd.plan_feedback(lone,case,messages,allowed)
    assert (f'{n1} is in no action: write exactly one action that names {n1} in parent_revision_ids. An add never names an '
        f'existing need: if A1 rewords {n1}, write it as revise of {n1} with the statement and its sources; if it is a further '
        f'need, keep {n1} with its own retain action.') in notes
    data=lone.model_dump(mode='json');data['actions'][0]['parent_revision_ids']=[n1]
    named=plan_model.model_validate(data)
    assert 'Addition cannot replace an existing parent.' in fd.plan_errors(named,case,messages,allowed)
    notes=fd.plan_feedback(named,case,messages,allowed)
    assert (f'Action A1 (add) names {n1}, but an add never names an existing need. To reword {n1}, make A1 a revise of {n1} '
        f'with the statement and its sources; to keep {n1} and propose a further need, retain {n1} in its own action and give '
        'A1 no parent_revision_ids.') in notes
    assert not any('Addition cannot replace an existing parent.' in x for x in notes)
    data['actions'][0]['parent_revision_ids']=[n1,n2];data['actions']=data['actions'][:1]
    assert any('make A1 a merge of them' in x for x in fd.plan_feedback(plan_model.model_validate(data),case,messages,allowed))
    # A plan without additions keeps the plain note.
    assert f'{n1} is in no action: write exactly one action that names {n1} in parent_revision_ids.' in fd.plan_feedback(
        plan_model.model_validate({**lone.model_dump(mode='json'),'actions':[lone.actions[1].model_dump(mode='json')]}),case,messages,allowed)
