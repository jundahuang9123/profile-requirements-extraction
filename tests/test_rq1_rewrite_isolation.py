import json
from test_resume_discussions import setup
from test_rq1_need_assessment import FullNeedsClient
from requirement_reuse_service.workflow import engine, needs
from requirement_reuse_service.workflow.models import RunRequest


class RejectedOne(FullNeedsClient):
    def __init__(self, twice=False): super().__init__();self.target=None;self.twice=twice
    def generate_structured(self,**kwargs):
        name=kwargs['output_model'].__name__;data=json.loads(kwargs['user'])
        if name=='NeedStatements' and 'previous_rewrites' in data:
            answer=super().generate_structured(**kwargs)
            for n in answer.needs: n.statement='Users can read the title of a dataset.'
            return answer
        if name=='NeedGrounding':
            if self.target is None: self.target=next(iter(data['groups']))
            self.calls.append((name,data))
            prior=sum(n==name for n,_ in self.calls)
            return kwargs['output_model'].model_validate({'checks':[{'group_id':identifier,
                'supported':not(identifier==self.target and (prior==1 or self.twice)),
                'no_added_actor':True,'no_added_obligation':True,'no_added_condition':True,'no_added_scope':True,
                'rationale':'Controlled offline rejection.'} for identifier in data['groups']]})
        return super().generate_structured(**kwargs)


def test_one_rejected_group_keeps_its_statement_beside_the_other_five_and_replays_without_calls(setup):
    store,source,_=setup;client=RejectedOne(twice=True)
    run=engine.new_run(store,RunRequest(snapshot_id=source['snapshot_id'],strategy='multi_agent',
        consolidation='exact',discussion='on_request',scoping='off',role_ids=['consumer_discovery','publisher_feasibility']))
    # Use six distinct source-backed observations to exercise the writer batch,
    # independently of the semantic grouper's deliberate equivalence behaviour.
    engine.execute_run(store,run['run_id'],FullNeedsClient())
    saved=store.get('run',run['run_id'])
    candidates=[engine.RequirementRecord.model_validate(r) for r in saved['requirements'] if not r['parent_revision_ids']]
    result,events=needs.write_needs(store,saved,[[r] for r in candidates],client,None)
    # rq1-need-statement-v3: the need whose rewrite the critic rejects twice keeps its own statement.
    assert len(result)==6
    kept=[r for r in result if 'rewrite_not_applied' in r.processing_flags]
    assert len(kept)==1 and kept[0].need_statement in {r.normalized_statement for r in candidates}
    assert [len(d['groups']) for name,d in client.calls if name=='NeedStatements']==[6,1]
    event=next(e for e in events if e['action']=='keep_unwritten_need')
    assert len(event['rewrites'])==2 and event['outputs']==[kept[0].revision_id]
    before=len(client.calls);needs.write_needs(store,saved,[[r] for r in candidates],client,None)
    assert len(client.calls)==before
    assert not any(a['reason']=='rewrite_rejected' for a in store.get('run',run['run_id'])['set_aside_observations'])
