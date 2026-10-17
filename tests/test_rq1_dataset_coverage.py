"""Source integrity, conservative compression, checkpoint reuse and frozen output."""
from copy import deepcopy
import itertools
import json
import random
import pytest
from test_resume_discussions import setup
from test_rq1_profile_scope import variants, ScopeJudge
from test_rq1_need_derived_export import derived
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import engine, needs, coverage
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import SourceRequest, SnapshotRequest, EvidenceLink, Qualification
from requirement_reuse_service.llm.client import LLMError

TEXT = 'Parking datasets describe parking facilities. Traffic datasets describe traffic flows.'


def category_source(setup):
    store, run, _ = setup
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(name='kinds.txt', content=TEXT),
                                                 source_role='stakeholder_need'))
    snapshot = engine.freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    run.update(snapshot_id=snapshot['snapshot_id'], evidence_ids=snapshot['evidence_ids'], needs_policies=needs.POLICIES)
    store.mutate(run['run_id'], None, 'offline_categories', lambda r:r.update(run))
    return store, run


class CategoriesClient:
    def __init__(self, bad=False): self.calls=[]; self.bad=bad
    def describe(self): return {'provider':'offline','model':'categories'}
    def generate_structured(self, **kw):
        data=json.loads(kw['user']); self.calls.append(data)
        return kw['output_model'].model_validate({'units':[
            {'evidence_id':i,'categories':[{'label':label,'quote':text if not self.bad else 'Invented quote',
                'rationale':'The source explicitly names this kind of data.'} for label in ('Parking datasets','Traffic datasets') if label in text]}
            for i,text in data['evidence'].items()]})


def test_registry_keeps_exact_source_citations_and_reuses_saved_scan(setup):
    store,run=category_source(setup); client=CategoriesClient()
    result=coverage.discover_categories(store,run,client)
    assert result['scan_complete'] and result['category_count']==2
    for category in result['categories']:
        for c in category['citations']:
            unit=store.get('evidence',c['evidence_id'])
            assert unit['content'][c['quote_start']:].startswith(c['quote'])
            assert c['source_name']=='kinds.txt' and category['label'] in c['quote']
    before=len(client.calls)
    repeated=coverage.discover_categories(store,run,client)
    assert repeated['categories']==result['categories'] and len(client.calls)==before


def test_invalid_quotes_are_corrected_then_reported_as_unchecked(setup):
    store,run=category_source(setup); client=CategoriesClient(bad=True)
    result=coverage.discover_categories(store,run,client)
    assert not result['scan_complete'] and not result['categories']
    assert result['unchecked_evidence_ids']==sorted(run['evidence_ids'])
    assert len(client.calls)==2
    coverage.discover_categories(store,run,client)
    assert len(client.calls)==2


def test_transport_error_does_not_become_empty_taxonomy(setup):
    store,run=category_source(setup)
    class Outage(CategoriesClient):
        def generate_structured(self,**kw): raise LLMError('offline transport failure')
    with pytest.raises(LLMError): coverage.discover_categories(store,run,Outage())
    assert 'dataset_categories' not in store.get('run',run['run_id'])['need_steps']
    assert coverage.discover_categories(store,run,CategoriesClient())['scan_complete']


def test_source_backed_scope_and_no_invented_applicability(setup):
    store,run,_,made=variants(setup, {'n':'Users can identify parking datasets.'})
    _,category_run=category_source(setup)
    run.update(snapshot_id=category_run['snapshot_id'], evidence_ids=category_run['evidence_ids'])
    registry=coverage.discover_categories(store,run,CategoriesClient())
    category=next(c for c in registry['categories'] if c['label']=='Parking datasets')
    citation=category['citations'][0]
    made[0].evidence_links=[EvidenceLink(evidence_id=citation['evidence_id'], quote=citation['quote'])]
    class LinkedJudge(ScopeJudge):
        def generate_structured(self,**kw):
            if kw['output_model'].__name__ == 'ProfileScope': return super().generate_structured(**kw)
            data=json.loads(kw['user']); self.calls.append(('NeedApplicability',data))
            assert data['dataset_context']['categories'][category['category_id']]['citation']['quote']==citation['quote']
            return kw['output_model'].model_validate({'decisions':[{'need_id':i,'representativeness':'common',
                'rationale':'Specific to parking.','category_links':[{'category_id':category['category_id'],
                'evidence_id':citation['evidence_id'],'quote':citation['quote'],'rationale':'Parking is explicit.'}]} for i in data['needs']]})
    out=needs.judge_profile_scope(store,run,made,LinkedJudge(),registry)
    assert out[0].profile_scope['scope_class']=='specialized'  # not common across Traffic as well
    assert out[0].dataset_coverage['category_ids']==[category['category_id']]
    before=out[0].need_integrity_hash
    out[0].dataset_coverage['category_ids'].append('invented')
    assert needs.need_integrity(out[0])!=before


def test_missing_category_context_cannot_assert_common(setup):
    store,run,_,made=variants(setup, {'n':'Users can identify datasets.'})
    out=needs.judge_profile_scope(store,run,made,ScopeJudge())
    assert out[0].profile_scope['representativeness']=='uncertain'
    assert out[0].dataset_coverage['status']=='unresolved'


def selection_inputs(setup):
    store,run,_,made=variants(setup, {str(i):'Users can see dataset coverage.' for i in range(4)})
    run['needs_policies']=needs.POLICIES
    for rank,n in enumerate(made,1):
        n.rank=rank
        n.qualification=Qualification(support='explicit',rationale='Offline supported need.',findings=[],assessor='offline')
        n.dataset_coverage={'category_ids':['parking'],'status':'source_linked','links':[]}
        n.processing_flags=[]
    family=[{'member_need_ids':[n.requirement_id for n in made]}]
    registry={'scan_complete':True,'categories':[{'category_id':'parking'},{'category_id':'traffic'}]}
    return store,run,made,family,registry


class EquivalenceClient:
    def __init__(self, pairs=None, omit=False): self.calls=[]; self.pairs=pairs; self.omit=omit
    def generate_structured(self,**kw):
        data=json.loads(kw['user']); self.calls.append(data)
        return kw['output_model'].model_validate({'decisions':[] if self.omit else [
            {'need_id':i,'equivalent_to':self.pairs.get(i,[]) if self.pairs is not None else [j for j in data['needs'] if j!=i],
             'rationale':'Same atomic need in both directions.'} for i in data['needs']]})


def test_compact_cover_preserves_every_need_and_does_not_mutate_records(setup):
    store,run,made,families,registry=selection_inputs(setup); client=EquivalenceClient()
    original=deepcopy(made)
    result=coverage.compact_selection(store,run,made,families,registry,client)
    assert result['selected_need_ids']==['0']
    assert result['covered_by']=={str(i):'0' for i in range(4)}
    assert result['uncovered_category_ids']==['traffic']
    assert result['optimal_for_recorded_coverage'] and made==original
    before=len(client.calls)
    repeated=coverage.compact_selection(store,run,made,families,registry,client)
    assert repeated['covered_by']==result['covered_by'] and len(client.calls)==before


@pytest.mark.parametrize('difference',['condition','scope','obligation','category','use_case'])
def test_no_disappearance_of_distinct_constraints_or_specialised_categories(setup,difference):
    store,run,made,families,registry=selection_inputs(setup)
    if difference=='condition': made[-1].need_condition='When access is restricted'
    if difference=='scope': made[-1].scope='Traffic'
    if difference=='obligation': made[-1].normalized_intent.obligation_hint='mandatory'
    if difference=='category': made[-1].dataset_coverage['category_ids']=['traffic']
    if difference=='use_case': made[-1].supports_user_tasks=['CQ-traffic']
    result=coverage.compact_selection(store,run,made,families,registry,EquivalenceClient())
    assert '3' in result['selected_need_ids']
    if difference!='use_case': assert len(result['selected_need_ids'])==2
    assert result['rejected_equivalences']


def test_asymmetric_or_uncertain_equivalence_cannot_remove_needs(setup):
    store,run,made,families,registry=selection_inputs(setup)
    result=coverage.compact_selection(store,run,made,families,registry,EquivalenceClient({'0':['1']}))
    assert result['selected_count']==4
    assert result['rejected_equivalences'][0]['reason']=='not_reciprocal'


def test_exhausted_equivalence_keeps_every_need_and_audits_uncertainty(setup):
    store,run,made,families,registry=selection_inputs(setup); client=EquivalenceClient(omit=True)
    result=coverage.compact_selection(store,run,made,families,registry,client)
    assert result['selected_count']==4 and result['unchecked_need_ids']==['0','1','2','3']
    assert len(client.calls)==2
    coverage.compact_selection(store,run,made,families,registry,client)
    assert len(client.calls)==2


def test_incomplete_scan_allows_checked_equivalences_and_reports_coverage_gap(setup):
    store,run,made,families,registry=selection_inputs(setup); registry['scan_complete']=False
    client=EquivalenceClient()
    result=coverage.compact_selection(store,run,made,families,registry,client)
    assert result['selected_count']==1 and client.calls
    assert not result['category_scan_complete'] and not result['category_coverage_complete']
    assert result['uncovered_category_ids']==['traffic']


def test_bounded_solver_matches_small_exhaustive_oracle():
    rng=random.Random(7)
    for _ in range(35):
        order=list('abcdef')
        graph={i:{i}|{j for j in order if rng.random()<.3} for i in order}
        selected,optimal,_=coverage.minimum_cover(graph,order)
        minimum=next(k for k in range(1,7) if any(set().union(*(graph[i] for i in s))==set(order)
                       for s in itertools.combinations(order,k)))
        assert optimal and len(selected)==minimum
        assert set().union(*(graph[i] for i in selected))==set(order)
        greedy,optimal,_=coverage.minimum_cover(graph,order,node_budget=0)
        assert not optimal and set().union(*(graph[i] for i in greedy))==set(order)


def test_frozen_compact_export_survives_current_human_list_changes(setup):
    store,run,_=derived(setup)
    original=needs.needs_export(store,run['run_id'])
    assert original['compact_selection']['selected_count']==1
    assert original['compact_needs'][0]['need_statement']==original['needs'][0]['need_statement']
    store.mutate(run['run_id'],None,'offline_human_list_change',lambda r:r.update(active_revision_ids=[]))
    changed=needs.needs_export(store,run['run_id'])
    assert not changed['needs'] and changed['compact_needs']==original['compact_needs']
    assert changed['compact_selection']==original['compact_selection']


def test_incomplete_category_context_is_not_used_for_compression(setup):
    store,run,made,families,registry=selection_inputs(setup)
    made[-1].dataset_coverage['all_categories_offered']=False
    result=coverage.compact_selection(store,run,made,families,registry,EquivalenceClient())
    assert '3' in result['selected_need_ids']
    assert result['protected_needs']['3']==['category_context_incomplete']


@pytest.mark.parametrize('contract,step,payload,answer',[
    (coverage.DatasetCategories,'dataset_categories',{'evidence':{'e':'Documented data'}},
     {'units':[{'evidence_id':'e','categories':[]}]}),
    (coverage.NeedEquivalence,'selection',{'needs':{'n':{'statement':'Users can find data'}}},
     {'decisions':[{'need_id':'n','equivalent_to':[],'rationale':'No equivalent offered.'}]})])
def test_new_step_checkpoints_are_model_specific(setup,contract,step,payload,answer):
    from requirement_reuse_service.llm.config import LLMConfig
    from requirement_reuse_service.llm.step_models import StepModelRouter
    store,run,_=setup
    class BoundClient:
        def __init__(self,config): self.model=config.model;self.calls=0
        def describe(self): return {'provider':'offline','model':self.model}
        def generate_structured(self,**kw):
            self.calls+=1
            return kw['output_model'].model_validate(answer)
    for model in ('model-a','model-b'):
        router=StepModelRouter(LLMConfig(provider='mock'),{step:model},BoundClient)
        for _ in range(2): needs.cached_generation(store,run,step,payload,contract,'Offline contract.',router)
        assert router._clients[model].calls==1
    saved=store.get('run',run['run_id'])['need_chunks']
    assert {row['provider']['model'] for row in saved.values()}=={'model-a','model-b'}


def test_false_applicability_quote_is_never_materialized(setup):
    store,run,_,made=variants(setup, {'n':'Users can identify datasets.'})
    evidence_id=made[0].evidence_links[0].evidence_id
    registry={'scan_complete':True,'categories':[{'category_id':'parking','label':'Parking',
        'citations':[{'evidence_id':evidence_id,'quote':'Parking','source_name':'offline'}]}]}
    class FalseLink(ScopeJudge):
        def generate_structured(self,**kw):
            if kw['output_model'].__name__ == 'ProfileScope': return super().generate_structured(**kw)
            data=json.loads(kw['user']);self.calls.append(('NeedApplicability',data))
            return kw['output_model'].model_validate({'decisions':[{'need_id':i,'representativeness':'specialized','rationale':'Offline false citation.',
                'category_links':[{'category_id':'parking','evidence_id':evidence_id,'quote':'Invented quote',
                                   'rationale':'Not actually in source.'}]} for i in data['needs']]})
    client=FalseLink()
    kept=needs.judge_profile_scope(store,run,made,client,registry)
    assert len(client.calls)==3 and len(kept)==1
    assert kept[0].dataset_coverage['category_ids']==[]
    assert kept[0].profile_scope['scope_class']=='review'
    assert kept[0].profile_scope['status']=='checked'
    assert 'profile_scope_not_checked' not in kept[0].processing_flags
    assert 'dataset_applicability_not_checked' in kept[0].processing_flags
