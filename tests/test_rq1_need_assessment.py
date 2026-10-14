import json
from test_resume_discussions import setup
from test_rq1_need_grouping import NeedsClient
from requirement_reuse_service.workflow import engine, needs
from requirement_reuse_service.workflow.models import RunRequest


class FullNeedsClient(NeedsClient):
    def generate_structured(self, **kwargs):
        name=kwargs['output_model'].__name__;data=json.loads(kwargs['user'])
        if name=='NeedSpanElicitationResult':
            self.calls.append((name,data));rows=[]
            for index,unit in enumerate(data['evidence_units']):
                span=unit['source_spans'][0];text=span['quote']
                obligation='mandatory' if ' must ' in text else 'recommended' if ' should ' in text else 'unknown'
                rows.append({'observation_id':'x','role_id':'x','statement':text,
                    'intent':{'obligation_hint':obligation,'resource_type':'Dataset','metadata_need':'title'},
                    'evidence_links':[{'source_span_id':span['span_id'],'component':'statement'},
                        *([{'source_span_id':span['span_id'],'component':'obligation'}] if obligation!='unknown' and self.mode != 'no_quote' else [])]})
            return kwargs['output_model'].model_validate({'observations':rows})
        if name=='Qualification':
            self.calls.append((name,data))
            return kwargs['output_model'].model_validate({'support':'explicit','rationale':'Scripted support check.','assessor':'scripted'})
        return super().generate_structured(**kwargs)


def test_full_pipeline_assesses_one_need_not_each_candidate(setup):
    store,original,_=setup;client=FullNeedsClient()
    run=engine.new_run(store,RunRequest(snapshot_id=original['snapshot_id'],strategy='multi_agent',
        role_ids=['consumer_discovery','publisher_feasibility'],discussion='on_request',scoping='off'))
    engine.execute_run(store,run['run_id'],client)
    saved=store.get('run',run['run_id'])
    assert saved['status']=='awaiting_human',saved['diagnostics']
    assert len(saved['observations'])==6 and len(saved['active_revision_ids'])==1
    assert sum(name=='Qualification' for name,_ in client.calls)==1
    assert all(r['qualification'] is None for r in saved['stage_results']['verification']['requirements'])
    assert saved['need_steps']['assessment']['assessed_count']==1


def test_full_needs_unquoted_labels_do_not_create_blocked_needs(setup):
    store,original,_=setup;client=FullNeedsClient('no_quote')
    run=engine.new_run(store,RunRequest(snapshot_id=original['snapshot_id'],strategy='multi_agent',
        role_ids=['consumer_discovery','publisher_feasibility'],discussion='on_request',scoping='off'))
    engine.execute_run(store,run['run_id'],client)
    saved=store.get('run',run['run_id'])
    assert saved['status']=='awaiting_human',saved['diagnostics']
    assert saved['need_steps']['source_check']['passed_count']==6
    assert len(saved['need_steps']['source_check']['unbacked_obligations'])==4
    assert len(saved['active_revision_ids'])==1
    n=next(r for r in saved['requirements'] if r['revision_id'] in saved['active_revision_ids'])
    assert n['normalized_intent']['obligation_hint']=='unknown' and n['verification']['status']=='pass'
