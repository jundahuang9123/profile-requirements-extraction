"""Synthetic tests of the rule added in rq1-fa-dialogue-v10: no evaluation answers or live generation."""
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_fa_workflow import contract_name
from test_fa_dialogue_v3 import Assessing, opted_in, ids, case_of, sourced
from requirement_reuse_service.workflow import fa_discussion as fd

CHECK={'supported':True,'preserves_distinctions':True,'priority_supported':False,'condition_supported':True,
    'obligation_preserved':True,'fa_relevant':True,'disposition_justified':True,'rationale':'Checked.'}


def plan():
    child=lambda cid:{'action_id':cid,'statement':'Users can find part of the access conditions.','rationale':'Part.',
        'evidence_links':[{'evidence_id':'e1','quote':'q'}]}
    return fd.ExperiencePlan.model_validate({'actions':[{'action_id':'A1','action':'split','parent_revision_ids':['n1'],
        'rationale':'Two needs.','children':[child('A1.1'),child('A1.2')]},
        {'action_id':'A2','action':'retain','parent_revision_ids':['n2'],'rationale':'Kept.'}],'summary':'s'})


def checks(*action_ids):
    return fd.DefinedChecks.model_validate({'checks':[{**CHECK,'action_id':i} for i in action_ids]})


def test_checks_of_a_splits_new_needs_are_accepted_and_every_action_still_needs_one():
    errors=lambda *i,policy=fd.BASE_POLICY:fd.check_errors(checks(*i),plan(),policy)
    assert errors('A1','A1.1','A1.2','A2')==[] and errors('A2','A1')==[]
    assert errors('A1.1','A1.2','A2')==['Check every action exactly once: {"missing":["A1"],"repeated":[],"unknown":[]}']
    assert errors('A1','A1','A2')==['Check every action exactly once: {"missing":[],"repeated":["A1"],"unknown":[]}']
    assert errors('A1','A2','Z9')==['Check every action exactly once: {"missing":[],"repeated":[],"unknown":["Z9"]}']
    # The legacy rule and wording stay.
    assert errors('A1','A1.1','A1.2','A2',policy='rq1-fa-dialogue-v1')==['Check every action exactly once.']
    assert errors('A1','A2',policy='rq1-fa-dialogue-v1')==[]
    assert len(checks(*[f'A{i}' for i in range(24)]).checks)==24
    assert 'Check a split once, as one action covering all its new needs.' in fd.BASE_CHECK_GUIDANCE


class ChildChecker(Assessing):
    """The checker also checks the new needs of each split, as gpt-oss did in JRC run-4d980b17."""
    def generate_structured(self,*,user,output_model,system='',step=None,**kw):
        answer=super().generate_structured(user=user,output_model=output_model,system=system,step=step,**kw)
        if contract_name(output_model)!='Checks':return answer
        import json
        extra=[{**CHECK,'action_id':c['action_id']} for a in json.loads(user)['plan']['actions'] for c in a.get('children') or []]
        return output_model.model_validate({'checks':[*answer.model_dump(mode='json')['checks'],*extra]})


def test_a_split_checked_with_its_new_needs_is_applied(setup):
    store,run=opted_in(setup)
    def plans(data,*_):
        needs,_=ids(data);cited=sourced(data)
        return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'Kept.'},
            {'action_id':'A2','action':'split','parent_revision_ids':[needs[1]],'rationale':'Two needs.','children':[
                {'action_id':'A2a','statement':'Users can find the licence of a dataset.','evidence_links':cited,'rationale':'One.'},
                {'action_id':'A2b','statement':'Users can find the rights holder of a dataset.','evidence_links':cited,'rationale':'Two.'}]}],
            'concerns':[],'questions':[],'summary':'Split.'}
    fd.deliberate(store,run['run_id'],ChildChecker(plans))
    saved,case=case_of(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_complete'
    attempts=case['discussion_trace']['phases']['check']['attempts']
    assert len(attempts)==1 and attempts[0]['errors']==[] and {c['action_id'] for c in attempts[0]['output']['checks']}=={'A1','A2','A2a','A2b'}
    row=next(o for o in case['mediation']['outcomes'] if o['action_id']=='A2')
    assert row['status']=='machine_revised' and len(row['result_revision_ids'])==2
