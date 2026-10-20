"""Synthetic tests of the rq1-fa-dialogue-v3 bookkeeping: no evaluation answers or live generation."""
import json
from copy import deepcopy
import pytest
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_fa_workflow import Dialogue
from test_base_review import prepared, Reviewer
from requirement_reuse_service.workflow import base_review as br, fa_discussion as fd


class Mediator(Dialogue):
    """Scripted roles from Dialogue; each Plan comes from plans(wire payload, call number, system)."""
    def __init__(self,plans,objection=True):
        super().__init__(objection=objection);self.plans=plans;self.plan_systems=[];self.calls_by_model=[]
    def generate_structured(self,*,user,output_model,system='',step=None,**kw):
        self.calls_by_model.append(output_model.__name__)
        if output_model in (br.BaseReview,br.BaseReviewChecks):
            return Reviewer('new').generate_structured(user=user,output_model=output_model)
        if output_model.__name__=='Plan':
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
    assert case['stop_reason']=='bounded_fa_dialogue_complete' and case['policy_version']=='rq1-fa-dialogue-v3'
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
    assert {o['action_id']:o['status'] for o in case['mediation']['outcomes']}=={'A1':'retained','A3':'human_review'}


def test_no_salvage_without_a_valid_need_disposition(setup):
    store,run=opted_in(setup)
    def plans(data,*_):
        needs,concerns=ids(data)
        return {'actions':[{'action_id':'A1','action':'defer','parent_revision_ids':[],'rationale':'One per concern.',
                'human_question':'Which?','alternatives':['One','Other']}],
            'concerns':[{'concern_id':c,'status':'unresolved','action_ids':['A1'],'rationale':'Open.'} for c in concerns],
            'questions':[],'summary':'Draft.'}
    fd.deliberate(store,run['run_id'],Mediator(plans))
    saved,case=case_of(store,run)
    assert case['stop_reason']=='invalid_output_pending_human_review' and case['mediation']['phase']=='human_review'
    assert case['discussion_trace']['salvage']['draft']['status']=='not_salvaged'
    assert saved['active_revision_ids']==run['active_revision_ids']


def test_a_lifted_label_is_not_forced_to_defer_but_a_labelled_need_stays_visible(setup):
    store,run=opted_in(setup,1);rid=run['requirements'][0]['revision_id']
    case=fd.build_cases(store,run,[],Dialogue())[0]
    def errors(case,action,**extra):
        plan=fd.Plan(actions=[{'action_id':'a','action':action,'parent_revision_ids':[rid],'rationale':'Synthetic.',**extra}],summary='Synthetic plan.')
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
