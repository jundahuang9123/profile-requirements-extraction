import json
import pytest
from test_resume_discussions import setup
from test_semantic_consolidation import inputs, revised
from requirement_reuse_service.workflow import needs
from requirement_reuse_service.workflow.semantic_consolidation import NEED_SEMANTIC_POLICY, grouped_block
from requirement_reuse_service.workflow.base_profile import load_profile


class NeedsClient:
    def __init__(self, mode='normal'):
        self.calls=[]; self.mode=mode
    def describe(self): return {'provider':'offline-test','model':'scripted'}
    def generate_structured(self, *, system, user, output_model, **kwargs):
        data=json.loads(user); name=output_model.__name__; self.calls.append((name,data))
        if name == 'DatasetCategories':
            return output_model.model_validate({'units':[{'evidence_id':i,'categories':[]} for i in data['evidence']]})
        if name == 'ProposalSupport':
            return output_model.model_validate({'proposals':[{'proposal_id':identifier,'support':'supported',
                'supporting_evidence_ids':list(row['excerpts']),'obligation_stated':row['obligation']!='unknown',
                'rationale':'Scripted supporting-quote check.'} for identifier,row in data['proposals'].items()]})
        if name == 'SemanticGrouping':
            return output_model.model_validate({'groups':[{'member_ids':list(data['candidates'])}]})
        if name == 'NeedStatements':
            results=[]
            for identifier, group in data['groups'].items():
                statement='Users can identify the title of a dataset.'
                condition=''
                if self.mode == 'invent': statement+=' When access is restricted.'; condition='When access is restricted'
                if self.mode == 'term' and sum(n == name for n,d in self.calls) == 1:
                    statement='The metadata provides dct:title.'
                flags=[{'member_id':m,'expresses_need':True} for m in group['members']]
                if self.mode == 'split' and len(flags)>1: flags[-1]['expresses_need']=False
                results.append({'group_id':identifier,'statement':statement,'condition':condition,'members':flags})
            return output_model.model_validate({'needs':results})
        if name == 'NeedGrounding':
            return output_model.model_validate({'checks':[{'group_id':g,'supported':True,
                'no_added_actor':True,'no_added_obligation':True,'no_added_condition':True,'no_added_scope':True,
                'rationale':'Scripted independent rewrite check.'} for g in data['groups']]})
        if name == 'ProfileScope':
            return output_model.model_validate({'decisions':[{'need_id':i,'catalogue_level':True,'serves':'find',
                'example':'Find datasets by their title.',
                'rationale':'Scripted in-scope judgement.'} for i in data['needs']]})
        raise AssertionError(name)


def need_inputs(setup):
    store, run, records=inputs(setup)
    records[0]=revised(run,records[0],statement='A consumer must be able to read the title.', extension_kind=None, base_property=None)
    records[1]=revised(run,records[1],statement='Datasets should include a title.',
        intent={**records[1].normalized_intent.model_dump(),'obligation_hint':'recommended'}, extension_kind=None, base_property=None)
    from requirement_reuse_service.workflow.engine import verify
    for r in records: r.verification=verify(store,r,run['evidence_ids'])
    run.update(consolidation_policy_version=NEED_SEMANTIC_POLICY,needs_policies={})
    run['request']['output_form']='needs'
    store.mutate(run['run_id'],None,'need-test',lambda r:r.update(run))
    return store,run,records


def test_underlying_capability_content_merge_and_obligation_alternatives(setup):
    store,run,records=need_inputs(setup); client=NeedsClient()
    groups,_=grouped_block(store,run,'underlying_needs',records,client,{})
    active,events=needs.write_needs(store,run,groups,client,None)
    assert len(active)==1
    record=active[0]
    assert record.need_statement == record.normalized_statement
    assert record.normalized_intent.obligation_hint == 'unknown'
    assert {a.obligation:a.count for a in record.obligation_alternatives} == {'mandatory':1,'recommended':1}
    assert set(record.parent_revision_ids)=={r.revision_id for r in records}
    assert all(r.lifecycle_state=='inactive_member' for r in records)
    assert all(name!='Qualification' for name,_ in client.calls)


def test_added_condition_rejected_and_not_retried_on_resume(setup):
    store,run,records=need_inputs(setup);client=NeedsClient('invent')
    active,_=needs.write_needs(store,run,[records],client,None)
    assert active==[] and len(client.calls)==2
    aside=store.get('run',run['run_id'])['set_aside_observations'][-1]
    assert aside['reason']=='rewrite_rejected' and 'added condition' in aside['rationale']
    needs.write_needs(store,run,[records],client,None)
    assert len(client.calls)==2


def test_term_gets_one_correction_and_rejected_member_splits(setup):
    store,run,records=need_inputs(setup);client=NeedsClient('term')
    profile,_=load_profile('dcat-ap-2.0.1')
    active,_=needs.write_needs(store,run,[records],client,profile)
    assert len(active)==1 and sum(name=='NeedStatements' for name,_ in client.calls)==2
    client=NeedsClient('split')
    # Different frozen inputs use separate checkpoint identities.
    records=[revised(run,r,statement=r.raw_statement+' This is an offline test.') for r in records]
    for r in records: r.verification={'status':'pass'}
    active,events=needs.write_needs(store,run,[records],client,profile)
    assert len(active)==2 and any(e['split_member_ids'] for e in events)
    assert {r for need in active for r in need.parent_revision_ids}=={r.revision_id for r in records}


def test_valid_negative_rewrite_critic_is_not_pressured_to_flip(setup):
    store,run,records=need_inputs(setup)
    class NegativeCritic(NeedsClient):
        def generate_structured(self,**kwargs):
            if kwargs['output_model'].__name__=='NeedGrounding':
                data=json.loads(kwargs['user']);self.calls.append(('NeedGrounding',data))
                return kwargs['output_model'].model_validate({'checks':[{'group_id':identifier,'supported':False,
                    'no_added_actor':False,'no_added_obligation':True,'no_added_condition':True,'no_added_scope':True,
                    'rationale':'The actor was not in the members.'} for identifier in data['groups']]})
            return super().generate_structured(**kwargs)
    client=NegativeCritic()
    active,_=needs.write_needs(store,run,[records],client,None)
    assert active==[]
    assert sum(name=='NeedGrounding' for name,_ in client.calls)==1
    assert sum(name=='NeedStatements' for name,_ in client.calls)==2
    saved=store.get('run',run['run_id'])
    assert saved['set_aside_observations'][-1]['reason']=='rewrite_rejected'
    assert len(saved['set_aside_observations'][-1]['details']['rewrites'])==2
    before=len(client.calls)
    needs.write_needs(store,run,[records],client,None)
    assert len(client.calls)==before


@pytest.mark.parametrize('obligation', ['mandatory','recommended','optional','unknown'])
@pytest.mark.parametrize('word', ['must','SHALL','Should'])
def test_need_wording_keeps_obligation_separate(obligation, word):
    offered={'g':{'obligation':obligation,'members':{'m':{'statement':'Users can identify titles.'}}}}
    answer=needs.NeedStatements(needs=[{'group_id':'g','statement':f'Users {word} identify titles.',
        'members':[{'member_id':'m','expresses_need':True}]}])
    assert any('obligation words' in e for e in needs.statement_errors(answer,offered,None))
    answer.needs[0].statement='Users can identify titles.'
    assert needs.statement_errors(answer,offered,None)==[]
