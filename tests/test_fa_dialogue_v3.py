"""Synthetic tests of the bookkeeping added in rq1-fa-dialogue-v3 (kept through v6): no evaluation answers or live generation.

Direct plan checks run on the v5 plan contract and on the v6 one (ExperiencePlan) that base-review runs use;
where v6 expects otherwise, its variant is in test_fa_experience.py."""
import json
from copy import deepcopy
import pytest
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_fa_workflow import Dialogue, contract_name
from test_base_review import prepared, Reviewer
from requirement_reuse_service.workflow import base_review as br, fa_discussion as fd, stakeholder_workflow as old


class Mediator(Dialogue):
    """Scripted roles from Dialogue; each Plan comes from plans(wire payload, call number, system)."""
    def __init__(self,plans,objection=True):
        super().__init__(objection=objection);self.plans=plans;self.plan_systems=[];self.calls_by_model=[]
    def generate_structured(self,*,user,output_model,system='',step=None,**kw):
        self.calls_by_model.append(contract_name(output_model))
        if output_model in (br.BaseReview,br.BaseReviewChecks):
            return Reviewer('new').generate_structured(user=user,output_model=output_model)
        if contract_name(output_model)=='Plan':
            self.plan_systems.append(system)
            return output_model.model_validate(self.plans(json.loads(user),len(self.plan_systems),system))
        return super().generate_structured(user=user,output_model=output_model,step=step,**kw)


def opted_in(setup,count=2):
    store,run,_=prepared(setup,count)
    store.mutate(run['run_id'],None,'fixture_expert',lambda r:r['request'].update(base_review='expert_v1'))
    return store,store.get('run',run['run_id'])


def ids(data):
    return [n['revision_id'] for n in data['packet']['needs']],[c['concern_id'] for m in data['messages'] for c in m['concerns']]


def retain_all(data,*_):
    needs,concerns=ids(data)
    return {'actions':[{'action_id':f'A{i+1}','action':'retain','parent_revision_ids':[n],'rationale':'Kept as stated.'} for i,n in enumerate(needs)],
        'concerns':[{'concern_id':c,'status':'satisfied','action_ids':['A1'],'rationale':'Condition kept.'} for c in concerns],
        'questions':[],'summary':'Needs retained.'}


def case_of(store,run):
    saved=store.get('run',run['run_id']);return saved,saved['deliberations'][0]


class Assessing(Mediator):
    """Also answers the strict revision verifier, so an applied change shows in the outcomes."""
    def generate_structured(self,*,user,output_model,system='',step=None,**kw):
        if output_model.__name__=='Qualification':
            return output_model.model_validate({'support':'explicit','rationale':'Synthetic.','findings':[],'assessor':'fixture'})
        return super().generate_structured(user=user,output_model=output_model,system=system,step=step,**kw)


def sourced(data):
    ex=data['packet']['excerpts'][0];return [{'evidence_id':ex['evidence_id'],'quote':ex['quote'],'quote_start':ex.get('quote_start')}]


def built(setup,count=2):
    """A base-aware case, its two needs, two saved concerns and the allowed evidence, for direct plan checks."""
    store,run=opted_in(setup,count);case=fd.build_cases(store,run,[],Dialogue())[0]
    assert case['policy_version']==fd.BASE_POLICY
    rids=case['revision_ids'];messages=[{'concerns':[{'concern_id':f'c{i+1}','revision_ids':[r]} for i,r in enumerate(rids)]}]
    return case,rids,messages,set(run['evidence_ids'])


def kept(rids,**extra):
    """Every need retained and every concern satisfied: a valid plan to break one way at a time."""
    return {'actions':[{'action_id':f'A{i+1}','action':'retain','parent_revision_ids':[r],'rationale':'Kept.'} for i,r in enumerate(rids)],
        'concerns':[{'concern_id':f'c{i+1}','status':'satisfied','action_ids':[f'A{i+1}'],'rationale':'Kept.'} for i in range(len(rids))],
        'questions':[],'summary':'Plan.',**extra}


@pytest.fixture(params=['Plan','ExperiencePlan'])
def plan_model(request):
    return getattr(fd,request.param)


def repaired(data,case,messages,allowed,model=fd.Plan):
    plan=model.model_validate(data);fixed,repairs=fd.repair_plan(plan,case,messages)
    return fd.plan_errors(plan,case,messages,allowed),fixed,repairs,fd.plan_errors(fixed,case,messages,allowed)


def test_bookkeeping_slips_are_repaired_and_audited(setup):
    store,run=opted_in(setup)
    def plans(data,*_):
        needs,concerns=ids(data)
        # The question names action A1 instead of its need, and the concerns omit the
        # question that lists them: both are repaired, with the model's plan kept.
        return {'actions':[{'action_id':f'A{i+1}','action':'retain','parent_revision_ids':[n],'rationale':'Kept.'} for i,n in enumerate(needs)],
            'questions':[{'question_id':'Q1','revision_ids':['A1'],'concern_ids':concerns,'question':'Which access condition applies?',
                'alternatives':['Keep the wording','Add the condition'],'rationale':'Open stakeholder point.'}],
            'concerns':[{'concern_id':c,'status':'unresolved','action_ids':[],'question_ids':[],'rationale':'Open.'} for c in concerns],
            'summary':'Retained with an open question.'}
    client=Mediator(plans);fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_complete' and case['policy_version']==fd.BASE_POLICY
    first=case['discussion_trace']['phases']['draft']['attempts'][0]
    assert first['errors']==[] and {r['kind'] for r in first['repairs']}=={'question_need_from_action','concern_links_question'}
    assert first['model_output']['questions'][0]['revision_ids']==['A1']
    assert first['output']['questions'][0]['revision_ids']==[case['revision_ids'][0]]
    assert len(client.plan_systems)==2  # draft and final, each accepted at its first attempt
    assert all(fd.BASE_MEDIATOR_GUIDANCE in s for s in client.plan_systems)


def test_correction_shows_the_rejected_plan_and_item_problems_in_aliases(setup):
    store,run=opted_in(setup)
    def plans(data,number,system):
        needs,concerns=ids(data)
        if 'Your previous answer was rejected' in system:return retain_all(data)
        # A set_aside without a need answers one concern; N2 has no action.
        return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'Kept.'},
                {'action_id':'A2','action':'set_aside','parent_revision_ids':[],'rationale':'Concern not accepted.','human_question':'Restore?'}],
            'concerns':[{'concern_id':c,'status':'rejected_with_reason','action_ids':['A2'],'rationale':'Not source-supported.'} for c in concerns],
            'questions':[],'summary':'Draft.'}
    client=Mediator(plans);fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_complete'
    rejected=case['discussion_trace']['phases']['draft']['attempts'][0]
    assert rejected['errors'] and any('names no need' in f for f in rejected['feedback'])
    second=client.plan_systems[1]
    assert 'Your previous answer was rejected: {' in second and '"action_id":"A2"' in second
    assert 'Action A2 (set_aside) names no need' in second and 'N2 is in no action' in second
    assert 'rev-' not in second and 'concern-' not in second


def test_salvage_keeps_valid_need_actions_and_defers_the_rest(setup):
    store,run=opted_in(setup)
    def plans(data,*_):
        needs,concerns=ids(data)
        # N1 is validly retained; the revision of N2 has no statement or source, and the
        # concerns are said to be addressed by that invalid revision.
        return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'Kept.'},
                {'action_id':'A2','action':'revise','parent_revision_ids':[needs[1]],'rationale':'Narrow it.'}],
            'concerns':[{'concern_id':c,'status':'addressed','action_ids':['A2'],'rationale':'Revised.'} for c in concerns],
            'questions':[],'summary':'Draft.'}
    before={r['revision_id']:r['content_hash'] for r in run['requirements']}
    client=Mediator(plans);fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_salvaged' and case['mediation']['phase']=='completed'
    salvage=case['mediation']['salvage']
    assert set(salvage)=={'draft','final'} and salvage['final']['kept_action_ids']==['A1']
    assert salvage['final']['dropped_actions'][0]['action_id']=='A2'
    assert any('statement and source links' in p for p in salvage['final']['dropped_actions'][0]['problems'])
    outcomes={o['action_id']:o for o in case['mediation']['outcomes']}
    assert outcomes['A1']['status']=='retained' and outcomes['salvage-1']['status']=='human_review'
    assert outcomes['salvage-1']['parent_revision_ids']==[case['revision_ids'][1]]
    # The dropped revise names N2, so N2's deferral offers it; the revise itself is a review row.
    assert outcomes['salvage-1']['alternatives']==['Keep the original need','Apply a rejected mediator action after review']
    rejected=outcomes['A2']
    assert rejected['salvage_rejected'] and rejected['status']=='human_review' and not rejected['applied'] and not rejected['human_accepted']
    assert rejected['action']=='revise' and rejected['parent_revision_ids']==[case['revision_ids'][1]] and rejected['rationale']=='Narrow it.'
    assert rejected['validation_errors']==salvage['final']['dropped_actions'][0]['problems']
    assert rejected['human_question']=='This mediator action failed validation and was not applied: '+'; '.join(rejected['validation_errors'])
    assert saved['metrics']['mediated_changes']==0
    question=next(q for q in case['mediation']['human_questions'] if q['question_id'].startswith('salvage-review'))
    assert set(question['concern_ids'])=={c['concern_id'] for m in case['messages'] for c in m['concerns']}
    # Nothing was rewritten: both originals stay active and unchanged.
    assert {r['revision_id']:r['content_hash'] for r in saved['requirements'] if r['revision_id'] in saved['active_revision_ids']}==before
    assert saved['metrics']['salvaged_cases']==1
    calls=len(client.calls_by_model);fd.deliberate(store,run['run_id'],client);assert len(client.calls_by_model)==calls


def test_salvage_keeps_the_single_deferral_among_unchanged_dispositions(setup):
    store,run=opted_in(setup)
    def plans(data,*_):
        needs,concerns=ids(data)
        # One action per concern: N2 is retained and also deferred.
        return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'Kept.'},
                {'action_id':'A2','action':'retain','parent_revision_ids':[needs[1]],'rationale':'Kept for the first concern.'},
                {'action_id':'A3','action':'defer','parent_revision_ids':[needs[1]],'rationale':'Second concern is open.',
                 'human_question':'Does the access condition apply to all datasets?','alternatives':['All datasets','Some datasets']}],
            'concerns':[{'concern_id':c,'status':'satisfied','action_ids':['A1'],'rationale':'Kept.'} for c in concerns],
            'questions':[],'summary':'Draft.'}
    fd.deliberate(store,run['run_id'],Mediator(plans))
    saved,case=case_of(store,run)
    audit=case['mediation']['salvage']['final']
    assert audit['kept_action_ids']==['A1','A3'] and audit['system_action_ids']==[] and audit['replaced_concern_ids']==[]
    assert [d['action_id'] for d in audit['dropped_actions']]==['A2']
    outcomes={o['action_id']:o for o in case['mediation']['outcomes']}
    assert {k:o['status'] for k,o in outcomes.items()}=={'A1':'retained','A3':'human_review','A2':'human_review'}
    # The dropped retain reads as the duplicate it is, beside the kept deferral.
    assert outcomes['A2']['salvage_rejected'] and 'its deferral was kept' in outcomes['A2']['human_question']
    assert not outcomes['A3'].get('salvage_rejected')


def no_need_disposition(data,*_):
    """One action per concern and none per need: no need keeps a valid disposition."""
    needs,concerns=ids(data)
    return {'actions':[{'action_id':'A1','action':'defer','parent_revision_ids':[],'rationale':'One per concern.',
            'human_question':'Which?','alternatives':['One','Other']}],
        'concerns':[{'concern_id':c,'status':'unresolved','action_ids':['A1'],'rationale':'Open.'} for c in concerns],
        'questions':[],'summary':'Draft.'}


def test_a_plan_without_a_valid_need_disposition_is_salvaged_with_every_need_deferred(setup):
    # rq1-fa-salvage-v2 (v12): up to v11 this case stopped as invalid output.
    store,run=opted_in(setup)
    fd.deliberate(store,run['run_id'],Mediator(no_need_disposition))
    saved,case=case_of(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_salvaged' and case['mediation']['phase']=='completed'
    for phase in ('draft','final'):
        audit=case['mediation']['salvage'][phase]
        assert audit['policy_version']==fd.SALVAGE_POLICY=='rq1-fa-salvage-v2' and audit['nothing_kept'] and audit['kept_action_ids']==[]
        assert audit['deferred_revision_ids']==case['revision_ids'] and [d['action_id'] for d in audit['dropped_actions']]==['A1']
    outcomes={o['action_id']:o for o in case['mediation']['outcomes']}
    assert {k:(o['action'],o['status']) for k,o in outcomes.items()}=={'salvage-1':('defer','human_review'),
        'salvage-2':('defer','human_review'),'A1':('defer','human_review')}
    assert outcomes['A1']['salvage_rejected'] and not outcomes['A1']['applied']
    assert [outcomes[k]['parent_revision_ids'] for k in ('salvage-1','salvage-2')]==[[r] for r in case['revision_ids']]
    assert case['mediation']['salvage_nothing_kept'] and saved['metrics']['salvaged_nothing_kept']==saved['metrics']['salvaged_cases']==1
    assert saved['active_revision_ids']==run['active_revision_ids'] and saved['metrics']['mediated_changes']==0


def test_a_v11_case_without_a_valid_need_disposition_keeps_the_first_salvage_rule(setup,plan_model):
    case,rids,messages,allowed=built(setup)
    plan=plan_model.model_validate(no_need_disposition({'packet':{'needs':[{'revision_id':r} for r in rids]},'messages':messages}))
    assert fd.salvage_plan(plan,case,messages,allowed)[0] is not None
    salvaged,audit=fd.salvage_plan(plan,{**case,'policy_version':'rq1-fa-dialogue-v11'},messages,allowed)
    assert salvaged is None and audit['status']=='not_salvaged' and audit['reason']=='No need has a valid disposition.'
    assert audit['policy_version']==fd.FIRST_SALVAGE_POLICY=='rq1-fa-salvage-v1'


def test_a_lifted_label_is_not_forced_to_defer_but_a_labelled_need_stays_visible(setup,plan_model):
    store,run=opted_in(setup,1);rid=run['requirements'][0]['revision_id']
    case=fd.build_cases(store,run,[],Dialogue())[0]
    def errors(case,action,**extra):
        plan=plan_model(actions=[{'action_id':'a','action':action,'parent_revision_ids':[rid],'rationale':'Synthetic.',**extra}],summary='Synthetic plan.')
        return fd.plan_errors(plan,case,[],set(run['evidence_ids']))
    lifted=deepcopy(case);lifted['frozen_requirements'][0]['base_relation']={'effect':'flag_removed','verdict':'new'}
    assert not any('Base' in e for e in errors(lifted,'retain'))
    labelled=deepcopy(case);labelled['frozen_requirements'][0]['processing_flags']=['covered_by_base']
    assert any('stay visible' in e for e in errors(labelled,'set_aside',human_question='Restore?'))
    legacy=deepcopy(case);legacy['policy_version']='rq1-fa-dialogue-v2';legacy['frozen_requirements'][0]['base_relation']={'effect':'dispute'}
    assert any('dispute requires defer' in e for e in errors(legacy,'retain'))


def test_a_discussion_planned_under_v2_cannot_continue_under_v3():
    from requirement_reuse_service.workflow.models import DeriveRequest
    upstream=('acquisition','decomposition','role_selection','elicitation','normalization','verification','consolidation')
    source={'run_id':'run-v2','version':3,'status':'failed','request':{'stakeholder_workflow':'fa_mediated','base_review':'expert_v1'},
        'stages':{s:'completed' for s in upstream},'deliberations':[{'case_id':'c'}],
        'stakeholder_audit':{'fa_discussion_plan':{'policy_version':'rq1-fa-dialogue-v2'}}}
    with pytest.raises(ValueError,match='planned under rq1-fa-dialogue-v2'):
        fd.derive_discussion_run(None,source,DeriveRequest(start_from='deliberation',expected_version=3,rationale='Continue.'),'fixture')


def test_v3_discussion_refuses_labels_of_an_earlier_base_review(setup):
    store,run=opted_in(setup,1)
    store.mutate(run['run_id'],None,'fixture_v2_label',lambda r:r['requirements'][0].update(base_relation={'policy':'rq1-base-expert-v2','effect':'dispute'}))
    with pytest.raises(ValueError,match='Stage 6a ran under rq1-base-expert-v2'):fd.deliberate(store,run['run_id'],Mediator(retain_all))


def test_legacy_v1_correction_and_plans_are_unchanged(setup):
    store,run,_=prepared(setup,2);assert fd.discussion_policy(run)=='rq1-fa-dialogue-v1'
    def plans(data,number,system):
        if number>1:return retain_all(data)
        bad=retain_all(data);bad['actions'][1]['parent_revision_ids']=[]
        return bad
    client=Mediator(plans);fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run)
    first=case['discussion_trace']['phases']['draft']['attempts'][0]
    assert set(first)=={'output','errors'} and first['errors']
    assert ' Correct only these validation errors: ' in client.plan_systems[1]
    assert 'Your previous answer was rejected' not in client.plan_systems[1]
    assert fd.BASE_MEDIATOR_GUIDANCE not in client.plan_systems[0]


def test_a_resumed_case_rebuilds_the_same_salvaged_draft(setup):
    from requirement_reuse_service.llm.client import LLMError
    store,run=opted_in(setup)
    def plans(data,*_):
        if data.get('draft') and not interrupted:interrupted.append(True);raise LLMError('scripted interruption')
        needs,concerns=ids(data)
        return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'Kept.'},
                {'action_id':'A2','action':'revise','parent_revision_ids':[needs[1]],'rationale':'Narrow it.'}],
            'concerns':[{'concern_id':c,'status':'addressed','action_ids':['A2'],'rationale':'Revised.'} for c in concerns],
            'questions':[],'summary':'Draft.'}
    interrupted=[]
    with pytest.raises(LLMError):fd.deliberate(store,run['run_id'],Mediator(plans))
    trace=store.get('run',run['run_id'])['deliberations'][0]['discussion_trace']
    first=deepcopy(trace['draft']);responses={k:v['input_hash'] for k,v in trace['phases'].items() if k.startswith('response:')}
    assert responses and trace['salvage']['draft']['status']=='salvaged'
    # Resuming reuses every saved role response; their checkpoints bind the rebuilt draft.
    client=Mediator(plans);fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run)
    assert case['discussion_trace']['draft']==first and case['stop_reason']=='bounded_fa_dialogue_salvaged'
    assert {k:v['input_hash'] for k,v in case['discussion_trace']['phases'].items() if k.startswith('response:')}==responses
    assert client.calls_by_model.count('Review')==0


def test_a_question_that_names_an_action_gets_that_actions_need(setup,plan_model):
    case,(n1,n2),messages,allowed=built(setup)
    data=kept([n1,n2],questions=[{'question_id':'Q1','revision_ids':['A1'],'concern_ids':['c1'],'question':'Which licence applies?',
        'alternatives':['Keep','Revise'],'rationale':'Open.'}])
    data['concerns'][0].update(status='unresolved',action_ids=[],question_ids=['Q1'])
    before,fixed,repairs,after=repaired(data,case,messages,allowed,plan_model)
    assert 'Human question must link only distinct current needs.' in before and after==[]
    assert fixed.questions[0].revision_ids==[n1] and repairs==[{'kind':'question_need_from_action','question_id':'Q1','action_id':'A1'}]


def test_a_concern_gets_the_question_that_lists_it(setup,plan_model):
    case,(n1,n2),messages,allowed=built(setup)
    data=kept([n1,n2],questions=[{'question_id':'Q1','revision_ids':[n1],'concern_ids':['c1'],'question':'Which licence applies?',
        'alternatives':['Keep','Revise'],'rationale':'Open.'}])
    data['concerns'][0].update(status='unresolved',action_ids=[])
    before,fixed,repairs,after=repaired(data,case,messages,allowed,plan_model)
    assert 'Question and concern links must be reciprocal.' in before and after==[]
    assert fixed.concerns[0].question_ids==['Q1'] and repairs==[{'kind':'concern_links_question','concern_id':'c1','question_id':'Q1'}]


def test_a_question_gets_the_concern_that_lists_it(setup,plan_model):
    case,(n1,n2),messages,allowed=built(setup)
    data=kept([n1,n2],questions=[{'question_id':'Q1','revision_ids':[n1,n2],'concern_ids':['c2'],'question':'Which licence applies?',
        'alternatives':['Keep','Revise'],'rationale':'Open.'}])
    for row in data['concerns']:row.update(status='unresolved',action_ids=[],question_ids=['Q1'])
    before,fixed,repairs,after=repaired(data,case,messages,allowed,plan_model)
    assert 'Concern and question links must be reciprocal.' in before and after==[]
    assert fixed.questions[0].concern_ids==['c2','c1'] and repairs==[{'kind':'question_links_concern','concern_id':'c1','question_id':'Q1'}]


def test_only_an_empty_note_without_a_need_is_dropped(setup,plan_model):
    case,(n1,n2),messages,allowed=built(setup)
    note={'action_id':'A3','action':'retain','parent_revision_ids':[],'rationale':'Concern noted.'}
    data=kept([n1,n2]);data['actions'].append(note)
    before,fixed,repairs,after=repaired(data,case,messages,allowed,plan_model)
    assert 'Non-addition requires a current parent.' in before and after==[]
    assert [a.action_id for a in fixed.actions]==['A1','A2']
    assert repairs==[{'kind':'dropped_unlinked_action_without_need','action_id':'A3','action':'retain'}]
    # Content, a question, a concern link, or an addition anywhere in the plan keeps it for correction.
    link=deepcopy(case['frozen_requirements'][0]['evidence_links'][0])
    addition={'action_id':'A4','action':'add','statement':'Users need to find the contact point of a dataset.','evidence_links':[link],'rationale':'Idea.'}
    # A priority source, a condition or alternatives are content too (review probe: each was dropped).
    for extra,also in [({'statement':'Users need a licence.'},[]),({'evidence_links':[link]},[]),({'human_question':'Restore?'},[]),({},[addition]),
            ({'priority_links':[link]},[]),({'priority_basis':'The access passage comes first.'},[]),
            ({'condition':'Only for datasets with restricted access.'},[]),({'alternatives':['Keep the wording','Add the access condition']},[])]:
        data=kept([n1,n2]);data['actions']+=[{**note,**extra},*also]
        before,fixed,repairs,after=repaired(data,case,messages,allowed,plan_model)
        assert 'A3' in [a.action_id for a in fixed.actions] and repairs==[] and 'Non-addition requires a current parent.' in after
    data=kept([n1,n2]);data['actions'].append(note);data['concerns'][1]['action_ids']=['A3']
    assert 'A3' in [a.action_id for a in repaired(data,case,messages,allowed,plan_model)[1].actions]


def test_defer_fields_are_copied_from_the_linked_question(setup,plan_model):
    case,(n1,n2),messages,allowed=built(setup)
    data=kept([n1,n2],questions=[{'question_id':'Q1','revision_ids':[n1],'concern_ids':['c1'],'question':'Which licence applies?',
        'alternatives':['Keep','Revise'],'rationale':'Open.'}])
    data['actions'][0].update(action='defer',rationale='Ask a person.')
    data['concerns'][0].update(status='unresolved',question_ids=['Q1'])
    before,fixed,repairs,after=repaired(data,case,messages,allowed,plan_model)
    assert 'Deferral requires a precise human question and preserved alternatives.' in before and after==[]
    assert fixed.actions[0].human_question=='Which licence applies?' and fixed.actions[0].alternatives==['Keep','Revise']
    assert repairs==[{'kind':'defer_fields_copied_from_linked_question','action_id':'A1','question_id':'Q1','fields':['human_question','alternatives']}]


def test_a_repeated_need_in_a_question_is_not_silently_deduplicated(setup,plan_model):
    case,(n1,n2),messages,allowed=built(setup)
    data=kept([n1,n2],questions=[{'question_id':'Q1','revision_ids':[n1,n1],'concern_ids':['c1'],'question':'Which licence applies?',
        'alternatives':['Keep','Revise'],'rationale':'Open.'}])
    data['concerns'][0].update(status='unresolved',action_ids=[],question_ids=['Q1'])
    before,fixed,repairs,after=repaired(data,case,messages,allowed,plan_model)
    assert repairs==[] and fixed.questions[0].revision_ids==[n1,n1]
    assert before==after and 'Human question must link only distinct current needs.' in after
    # Mapping an action to its need removes no ID the model repeated, a need or an action (review probe).
    for written,expected in [([n1,n1,'A2'],[n1,n1,n2]),(['A1','A1'],[n1,n1])]:
        data['questions'][0]['revision_ids']=written
        before,fixed,repairs,after=repaired(data,case,messages,allowed,plan_model)
        assert fixed.questions[0].revision_ids==expected and 'Human question must link only distinct current needs.' in after
        assert repairs==[{'kind':'question_need_from_action','question_id':'Q1','action_id':i} for i in dict.fromkeys(written) if i.startswith('A')]


def test_feedback_names_repeated_links(setup,plan_model):
    case,(n1,n2),messages,allowed=built(setup)
    plan=plan_model.model_validate({'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[n1],'rationale':'Kept.'}],
        'questions':[{'question_id':'Q1','revision_ids':[n2,n2],'concern_ids':['c1','c1'],'question':'Which?','alternatives':['a'],'rationale':'r'}],
        'concerns':[{'concern_id':'c1','status':'unresolved','action_ids':['A1','A1'],'question_ids':['Q1','Q1'],'rationale':'Open.'},
            {'concern_id':'c2','status':'satisfied','action_ids':['A1'],'rationale':'Kept.'}],'summary':'Broken.'})
    errors=fd.plan_errors(plan,case,messages,allowed);notes=fd.plan_feedback(plan,case,messages,allowed)
    assert 'Human question must link only distinct current needs.' in errors and 'Concern disposition names an unknown or repeated question.' in errors
    assert f'{n2} is in no action: write exactly one action that names {n2} in parent_revision_ids.' in notes
    assert {f'Question Q1 lists {n2} more than once in revision_ids; list each ID once.','Question Q1 lists c1 more than once in concern_ids; list each ID once.',
        'Concern c1 lists A1 more than once in action_ids; list each ID once.','Concern c1 lists Q1 more than once in question_ids; list each ID once.'}<=set(notes)


def test_a_cut_correction_says_how_many_problems_it_does_not_show(setup):
    # The v5 plan contract: 40 concerns without a disposition (v6 notes them; see test_fa_experience).
    case,(n1,n2),_,allowed=built(setup)
    messages=[{'concerns':[{'concern_id':f'c{i}','revision_ids':[n1]} for i in range(40)]}]
    plan=fd.Plan.model_validate(kept([n1,n2],concerns=[]))
    notes=fd.plan_feedback(plan,case,messages,allowed);assert len(notes)==40
    text=br.correction({'output':plan.model_dump(mode='json'),'errors':['Account for every saved stakeholder concern exactly once.'],'feedback':notes},{})
    assert text.endswith(' (10 more problems not shown)') and 'Concern c29 ' in text and 'Concern c30 ' not in text
    assert 'not shown' not in br.correction({'output':None,'errors':notes[:30]},{})


def test_a_resumed_second_attempt_keeps_its_correction(setup):
    from requirement_reuse_service.llm.client import LLMError
    store,run=opted_in(setup)
    def plans(data,number,system):
        if number==2:raise LLMError('scripted interruption')
        bad=retain_all(data);bad['actions'][1]['parent_revision_ids']=[]
        return bad
    with pytest.raises(LLMError):fd.deliberate(store,run['run_id'],Mediator(plans))
    attempts=store.get('run',run['run_id'])['deliberations'][0]['discussion_trace']['phases']['draft']['attempts']
    assert len(attempts)==1 and attempts[0]['errors']
    client=Mediator(retain_all);fd.deliberate(store,run['run_id'],client)
    resumed=client.plan_systems[0]
    assert 'Your previous answer was rejected: {' in resumed and 'N2 is in no action' in resumed
    saved,case=case_of(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_complete' and len(case['discussion_trace']['phases']['draft']['attempts'])==2


def test_an_addition_withdrawn_by_a_set_aside_without_a_need_is_never_applied(setup):
    store,run=opted_in(setup)
    def plans(data,*_):
        needs,concerns=ids(data)
        # The mediator adds a need, then withdraws it in a set-aside that names no need.
        return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'Kept.'},
                {'action_id':'A2','action':'retain','parent_revision_ids':[needs[1]],'rationale':'Kept.'},
                {'action_id':'A3','action':'add','statement':'Users need to find the contact point of a dataset.',
                 'evidence_links':sourced(data),'rationale':'Idea from a concern.'},
                {'action_id':'A4','action':'set_aside','parent_revision_ids':[],'rationale':'Drop the proposed addition A3.',
                 'human_question':'Restore the proposed addition?'}],
            'concerns':[{'concern_id':c,'status':'satisfied','action_ids':['A1'],'rationale':'Kept.'} for c in concerns],
            'questions':[],'summary':'Draft.'}
    client=Assessing(plans);fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run)
    first=case['discussion_trace']['phases']['draft']['attempts'][0]
    assert 'Non-addition requires a current parent.' in first['errors'] and not first.get('repairs')
    assert case['stop_reason']=='bounded_fa_dialogue_salvaged' and saved['metrics']['salvaged_cases']==1
    outcomes={o['action_id']:o for o in case['mediation']['outcomes']}
    assert {k:o['status'] for k,o in outcomes.items()}=={'A1':'retained','A2':'retained','A3':'human_review','A4':'human_review'}
    assert outcomes['A3']['salvage_rejected'] and not outcomes['A3']['applied']
    assert outcomes['A3']['validation_errors']==['Additions are not applied from a salvaged plan.']
    assert outcomes['A4']['salvage_rejected'] and outcomes['A4']['human_question'].endswith('. Its question: Restore the proposed addition?')
    assert saved['active_revision_ids']==run['active_revision_ids'] and len(saved['requirements'])==len(run['requirements'])
    assert saved['metrics']['mediated_changes']==0


def test_a_sourced_proposal_without_a_need_is_shown_for_review(setup):
    store,run=opted_in(setup)
    def plans(data,*_):
        needs,concerns=ids(data)
        # A source-supported proposal written as a revise that names no need; no concern links it.
        return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'Kept.'},
                {'action_id':'A2','action':'retain','parent_revision_ids':[needs[1]],'rationale':'Kept.'},
                {'action_id':'A3','action':'revise','parent_revision_ids':[],'statement':'Users need to find the contact point of a dataset.',
                 'evidence_links':sourced(data),'rationale':'Proposed by a stakeholder.',
                 'human_question':'Should this be a separate need?','alternatives':['Add it','Leave it out']}],
            'concerns':[{'concern_id':c,'status':'satisfied','action_ids':['A1'],'rationale':'Kept.'} for c in concerns],
            'questions':[],'summary':'Draft.'}
    client=Assessing(plans);fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run)
    first=case['discussion_trace']['phases']['draft']['attempts'][0]
    assert 'Non-addition requires a current parent.' in first['errors'] and not first.get('repairs')
    assert 'Action A3 (revise) names no need' in client.plan_systems[1]
    assert case['stop_reason']=='bounded_fa_dialogue_salvaged'
    row=next(o for o in case['mediation']['outcomes'] if o['action_id']=='A3')
    assert row['salvage_rejected'] and row['status']=='human_review' and not row['applied']
    assert row['statement']=='Users need to find the contact point of a dataset.' and row['evidence_links'] and row['alternatives']==['Add it','Leave it out']
    assert row['human_question'].endswith('. Its question: Should this be a separate need?')
    assert saved['active_revision_ids']==run['active_revision_ids']


def test_salvage_never_keeps_an_addition(setup,plan_model):
    case,(n1,n2),_,allowed=built(setup)
    messages=[{'concerns':[{'concern_id':'c1','revision_ids':[n2]}]}]
    link=deepcopy(case['frozen_requirements'][0]['evidence_links'][0])
    plan=plan_model.model_validate({'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[n1],'rationale':'Kept.'},
        {'action_id':'A2','action':'add','statement':'Users can find an invented need.','evidence_links':[link],'rationale':'Idea.'},
        {'action_id':'A3','action':'set_aside','rationale':'Drop the idea.','human_question':'Restore?'},
        {'action_id':'A4','action':'revise','parent_revision_ids':[n2],'rationale':'No source.'}],
        'concerns':[{'concern_id':'c1','status':'addressed','action_ids':['A4'],'rationale':'Revised.'}],'summary':'Broken plan.'})
    assert fd.plan_errors(plan,case,messages,allowed)
    salvaged,audit=fd.salvage_plan(plan,case,messages,allowed)
    assert fd.plan_errors(salvaged,case,messages,allowed)==[]
    assert [(a.action_id,a.action,a.parent_revision_ids) for a in salvaged.actions]==[('A1','retain',[n1]),('salvage-1','defer',[n2])]
    dropped={d['action_id']:d for d in audit['dropped_actions']}
    assert set(dropped)=={'A2','A3','A4'} and dropped['A2']['problems']==['Additions are not applied from a salvaged plan.']
    assert all(d['proposal']==a.model_dump(mode='json') for d,a in zip(audit['dropped_actions'],plan.actions[1:]))
    assert 'apply a rejected action after review' in salvaged.actions[1].human_question
    assert audit['deferred_revision_ids']==[n2] and audit['replaced_concern_ids']==['c1']
    assert salvaged.concerns[0].status=='unresolved' and salvaged.questions[0].concern_ids==['c1']
    # v12: a plan of only an addition and a parentless set-aside keeps nothing; every need is deferred.
    only=plan_model(actions=[plan.actions[1],plan.actions[2]],summary='Only an addition.')
    deferred,audit=fd.salvage_plan(only,case,[],allowed)
    assert fd.plan_errors(deferred,case,[],allowed)==[] and audit['nothing_kept'] and audit['kept_action_ids']==[]
    assert [(a.action_id,a.action,a.parent_revision_ids) for a in deferred.actions]==[('salvage-1','defer',[n1]),('salvage-2','defer',[n2])]
    assert [d['action_id'] for d in audit['dropped_actions']]==['A2','A3']
    nothing,audit=fd.salvage_plan(only,{**case,'policy_version':'rq1-fa-dialogue-v11'},[],allowed)
    assert nothing is None and audit['status']=='not_salvaged'


def test_salvage_leaves_a_concern_open_when_its_action_was_dropped(setup,plan_model):
    case,(n1,n2),_,allowed=built(setup)
    messages=[{'concerns':[{'concern_id':'c1','revision_ids':[n2]}]}]
    plan=plan_model.model_validate({'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[n1],'rationale':'Kept.'},
        {'action_id':'A2','action':'revise','parent_revision_ids':[n2],'rationale':'No source.'}],
        'concerns':[{'concern_id':'c1','status':'addressed','action_ids':['A1','A2'],'rationale':'Addressed by the revision.'}],'summary':'Broken.'})
    salvaged,audit=fd.salvage_plan(plan,case,messages,allowed)
    assert [c.model_dump(mode='json') for c in salvaged.concerns]==[{'concern_id':'c1','status':'unresolved','action_ids':[],
        'question_ids':['salvage-review-1'],'rationale':'System salvage: the mediator gave this concern no valid disposition; a person reviews it.'}]
    assert audit['replaced_concern_ids']==['c1'] and audit['deferred_revision_ids']==[n2]


def test_salvage_leaves_a_concern_with_two_dispositions_open(setup,plan_model):
    case,(n1,n2),_,allowed=built(setup)
    messages=[{'concerns':[{'concern_id':'c1','revision_ids':[n2]}]}]
    plan=plan_model.model_validate({'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[n1],'rationale':'Kept.'},
        {'action_id':'A2','action':'revise','parent_revision_ids':[n2],'rationale':'No source.'}],
        'questions':[{'question_id':'Q1','revision_ids':[n2],'concern_ids':['c1'],'question':'Which?','alternatives':['a'],'rationale':'r'}],
        'concerns':[{'concern_id':'c1','status':'satisfied','action_ids':['A1'],'rationale':'First.'},
            {'concern_id':'c1','status':'unresolved','question_ids':['Q1'],'rationale':'Second.'}],'summary':'Broken.'})
    salvaged,audit=fd.salvage_plan(plan,case,messages,allowed)
    assert [(c.concern_id,c.status,c.question_ids) for c in salvaged.concerns]==[('c1','unresolved',['salvage-review-1'])]
    assert audit['replaced_concern_ids']==['c1'] and audit['dropped_question_ids']==['Q1']
    assert [q.question_id for q in salvaged.questions]==['salvage-review-1'] and salvaged.questions[0].concern_ids==['c1']


def test_a_salvage_beyond_the_plan_contract_is_not_salvaged(setup):
    # The v5 plan contract: the system question for the 33rd concern overflows (v6 variant in test_fa_experience).
    case,(n1,n2),_,allowed=built(setup)
    messages=[{'concerns':[{'concern_id':f'c{i}','revision_ids':[n1]} for i in range(33)]}]
    plan=fd.Plan.model_validate({'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[n1],'rationale':'Kept.'},
        {'action_id':'A2','action':'revise','parent_revision_ids':[n2],'rationale':'No source.'}],
        'questions':[{'question_id':f'Q{i}','revision_ids':[n1],'concern_ids':[f'c{i}'],'question':'?','alternatives':['a'],'rationale':'r'} for i in range(32)],
        'concerns':[{'concern_id':f'c{i}','status':'unresolved','question_ids':[f'Q{i}'],'rationale':'Open.'} for i in range(32)],'summary':'p'})
    # 32 kept questions plus the system review question exceed Plan.questions: refused, not raised.
    salvaged,audit=fd.salvage_plan(plan,case,messages,allowed)
    assert salvaged is None and audit['status']=='not_salvaged' and audit['reason'].startswith('Salvaged plan exceeds the plan contract')


def test_an_invalid_plan_is_salvaged_and_its_rejected_action_shown(setup):
    store,run=opted_in(setup)
    br.review_base(store,store.get('run',run['run_id']),Reviewer('new'))
    def plans(data,*_):
        needs,concerns=ids(data)
        # A valid retain of N1 and a set-aside that names no need: the shape of most JRC failures.
        return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'Kept.'},
                {'action_id':'A9','action':'set_aside','rationale':'Drop an idea.','human_question':'Restore?'}],
            'concerns':[{'concern_id':c,'status':'satisfied','action_ids':['A1'],'rationale':'Kept.'} for c in concerns],
            'questions':[],'summary':'Draft.'}
    client=Mediator(plans);fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_salvaged' and saved['metrics']['salvaged_cases']==1
    # Draft and final each get one correction; the salvaged draft's deferral re-engages the roles.
    assert len(client.plan_systems)==4
    correction=client.plan_systems[1].split('Your previous answer was rejected')[1]
    assert 'Action A9 (set_aside) names no need' in correction and 'N2 is in no action' in correction
    assert all(rid not in correction for rid in case['revision_ids'])
    outcomes={o['action_id']:o for o in case['mediation']['outcomes']}
    assert outcomes['A1']['status']=='retained'
    assert outcomes['A9']['salvage_rejected'] and not outcomes['A9']['applied'] and outcomes['A9']['status']=='human_review'
    assert outcomes['A9']['human_question'].endswith(' Its question: Restore?')
    # No action named N2, so its deferral offers no rejected action.
    assert outcomes['salvage-1']['action']=='defer' and outcomes['salvage-1']['parent_revision_ids']==[case['revision_ids'][1]]
    assert outcomes['salvage-1']['alternatives']==['Keep the original need','Prepare a separately reviewed revision']
    assert case['mediation']['salvage']['final']['policy_version']==fd.SALVAGE_POLICY
    calls=len(client.calls_by_model);fd.deliberate(store,run['run_id'],client);assert len(client.calls_by_model)==calls


def test_a_v3_case_does_not_force_a_removed_label_to_defer(setup,plan_model):
    case,(n1,n2),messages,allowed=built(setup)
    # rq1-base-expert-v3 saved 'dispute' with the label already removed (JRC run-fd39639e: 11 needs).
    relation={'policy':'rq1-base-expert-v3','status':'checked','verdict':'new','effect':'dispute'}
    case['frozen_requirements'][0]['base_relation']=relation;assert br.label_removed(relation)
    assert fd.plan_errors(plan_model.model_validate(kept([n1,n2])),case,messages,allowed)==[]


def test_the_discussion_refuses_labels_of_rq1_base_expert_v3(setup):
    store,run=opted_in(setup)
    def label(r):
        r['requirements'][0].update(base_relation={'policy':'rq1-base-expert-v3','status':'checked','verdict':'new','effect':'dispute'})
        r['requirements'][1].update(base_relation={'status':'not_reviewed'})  # no policy: reported, not a TypeError
    store.mutate(run['run_id'],None,'fixture_v3_label',label)
    with pytest.raises(ValueError,match='Stage 6a ran under None, rq1-base-expert-v3; rq1-fa-dialogue-v12 needs rq1-base-expert-v5'):
        fd.deliberate(store,run['run_id'],Mediator(retain_all))


@pytest.mark.parametrize('planned',['rq1-fa-dialogue-v2','rq1-fa-dialogue-v3','rq1-fa-dialogue-v4','rq1-fa-dialogue-v5','rq1-fa-dialogue-v6',
    'rq1-fa-dialogue-v7','rq1-fa-dialogue-v8','rq1-fa-dialogue-v9','rq1-fa-dialogue-v10','rq1-fa-dialogue-v11'])
def test_a_discussion_planned_under_an_earlier_version_is_refused_by_name(setup,planned):
    store,run=opted_in(setup)
    old.save(store,run['run_id'],'fa_discussion_plan',{'policy_version':planned})
    with pytest.raises(ValueError,match=f'planned under {planned}; the current protocol is rq1-fa-dialogue-v12. Derive a separate base-review trial'):
        fd.deliberate(store,run['run_id'],Mediator(retain_all))


def test_a_stakeholder_review_with_structured_errors_gets_its_correction(setup):
    # Stakeholder review errors are dicts (unknown need/evidence IDs); the v3 correction crashed on them.
    store,run=opted_in(setup)
    class UnknownNeedFirst(Mediator):
        def __init__(self):super().__init__(retain_all);self.review_systems=[]
        def generate_structured(self,*,user,output_model,system='',step=None,**kw):
            if contract_name(output_model)!='Review':return super().generate_structured(user=user,output_model=output_model,system=system,step=step,**kw)
            self.review_systems.append(system)
            raw=super().generate_structured(user=user,output_model=output_model,step=step,**kw).model_dump(mode='json')
            if len(self.review_systems)==1:raw['concerns'][0]['revision_ids']=['N99']
            return output_model.model_validate(raw)
    client=UnknownNeedFirst();fd.deliberate(store,run['run_id'],client)
    # v4 names the valid IDs in the model's aliases (fd.review_feedback).
    assert 'Your previous answer was rejected: {' in client.review_systems[1]
    assert 'Concern 1 lists N99 in revision_ids, but the needs of this case are only N1, N2.' in client.review_systems[1]
    assert 'rev-' not in client.review_systems[1].split('Your previous answer was rejected')[1]
    saved,case=case_of(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_complete'
