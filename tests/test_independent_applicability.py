"""Reproduce lost D5 verdicts without paid calls or saved research outputs."""
import json
import pytest
from test_resume_discussions import setup
from test_rq1_profile_scope import variants, ScopeJudge
from test_rq1_dataset_coverage import category_source, CategoriesClient, selection_inputs, EquivalenceClient
from requirement_reuse_service.workflow import needs, coverage
from requirement_reuse_service.llm.client import validate_json_payload, LLMError


def registry_for(need):
    link=need.evidence_links[0]
    return {'scan_complete':True,'categories':[{'category_id':'kind','label':'Synthetic structure',
        'dimension':'structure','citations':[{'evidence_id':link.evidence_id,'quote':link.quote,'source_name':'fixture'}]}]}


class ApplicabilityJudge(ScopeJudge):
    def __init__(self, fault=None):
        super().__init__(); self.fault=fault
    def generate_structured(self, **kw):
        if kw['output_model'].__name__ != 'NeedApplicability':
            return super().generate_structured(**kw)
        data=json.loads(kw['user']);self.calls.append(('NeedApplicability',data))
        if self.fault=='transport': raise LLMError('Synthetic transport interruption')
        rows=[]
        for identifier,need in data['needs'].items():
            evidence_id,excerpt=next(iter(need['excerpts'].items()))
            row={'need_id':identifier,'representativeness':'specialized',
                 'category_links':[{'category_id':'kind','evidence_id':evidence_id,'quote':excerpt,
                                    'rationale':'The source supports applicability.'}],
                 'rationale':'Synthetic applicability judgement.'}
            if self.fault=='quote': row['category_links'][0]['quote']='An invented quotation'
            if self.fault=='unknown_id': row['category_links'][0]['category_id']='invented'
            if self.fault=='schema': row['category_links']='not a list'
            rows.append(row)
        return validate_json_payload(json.dumps({'decisions':rows}),kw['output_model'])


@pytest.mark.parametrize('fault',['quote','unknown_id','schema'])
def test_invalid_applicability_cannot_erase_valid_c1_c2_and_cache_reuses_core(setup,fault):
    store,run,_,made=variants(setup,{'need-0':'Users can identify datasets.','need-2':'Every row has a timestamp.'})
    registry=registry_for(made[0]);client=ApplicabilityJudge(fault)
    kept=needs.judge_profile_scope(store,run,made,client,registry)
    assert [n.requirement_id for n in kept]==['need-0']
    assert kept[0].profile_scope['status']=='checked'
    assert kept[0].profile_scope['catalogue_level'] is True
    assert kept[0].profile_scope['serves']=='find'
    assert kept[0].dataset_coverage['status']=='unresolved'
    assert 'profile_scope_not_checked' not in kept[0].processing_flags
    saved=store.get('run',run['run_id'])
    assert saved['set_aside_observations'][0]['need_id']=='need-2'
    assert saved['set_aside_observations'][0]['reason']=='not_catalogue_level'
    assert saved['need_steps']['profile_scope']['not_checked_ids']==[]
    assert saved['need_steps']['dataset_applicability']['not_checked_ids']==['need-0']
    assert [name for name,_ in client.calls]==['ProfileScope','NeedApplicability','NeedApplicability']
    before=len(client.calls)
    needs.judge_profile_scope(store,run,made,client,registry)
    assert len(client.calls)==before


def test_applicability_outage_preserves_core_checkpoint_for_resume(setup):
    store,run,_,made=variants(setup,{'need-0':'Users can identify datasets.'})
    registry=registry_for(made[0]);client=ApplicabilityJudge('transport')
    with pytest.raises(LLMError,match='transport'):
        needs.judge_profile_scope(store,run,made,client,registry)
    saved=store.get('run',run['run_id'])
    assert next(c for c in saved['need_chunks'].values() if c['step']=='profile_scope')['status']=='completed'
    client.fault=None
    kept=needs.judge_profile_scope(store,run,made,client,registry)
    assert sum(name=='ProfileScope' for name,_ in client.calls)==1
    assert kept[0].dataset_coverage['status']=='source_linked'


def test_strict_common_requires_profile_wide_source_or_complete_recorded_coverage():
    def decision(**extra):
        return needs.ApplicabilityDecision.model_validate({'need_id':'n','representativeness':'common',
            'rationale':'Synthetic judgement.',**extra})
    link={'category_id':'a','evidence_id':'e','quote':'Exact source quotation','rationale':'Source link.'}
    context={'categories':{'a':{},'b':{}},'all_categories_offered':True,'scan_complete':False}
    assert coverage.resolved_scope(decision(),context)[0]=='uncertain'
    assert coverage.resolved_scope(decision(category_links=[link,{**link,'category_id':'b'}]),context)[0]!='common'
    context['scan_complete']=True
    label,audit=coverage.resolved_scope(decision(category_links=[link,{**link,'category_id':'b'}]),context)
    assert label=='common' and audit['common_basis']=='all_recorded_categories'
    context['scan_complete']=False
    quote={k:v for k,v in link.items() if k!='category_id'}
    label,audit=coverage.resolved_scope(decision(profile_wide_links=[quote]),context)
    assert label=='common' and audit['common_basis']=='explicit_profile_wide'
    assert not audit['scan_complete']


def test_partial_unit_retains_valid_mentions_and_records_rejected_quotes(setup):
    store,run=category_source(setup)
    class Mixed(CategoriesClient):
        def generate_structured(self,**kw):
            data=json.loads(kw['user']);self.calls.append(data)
            return kw['output_model'].model_validate({'units':[{'evidence_id':identifier,'categories':[
                {'label':'Parking datasets','quote':text,'rationale':'Explicit data distinction.'},
                {'label':'Invented kind','quote':'Invented quotation','rationale':'Invalid.'}]}
                for identifier,text in data['evidence'].items()]})
    client=Mixed();result=coverage.discover_categories(store,run,client)
    assert result['attempted_count']==result['input_count']
    assert result['examined_count']==0 and result['unchecked_evidence_ids']==sorted(run['evidence_ids'])
    assert result['status']=='partial' and not result['scan_complete']
    assert result['category_count']==1 and result['categories'][0]['label']=='Parking datasets'
    assert result['rejected_mentions'] and all(not c['unit_scan_complete'] for c in result['categories'][0]['citations'])
    coverage.discover_categories(store,run,client)
    assert len(client.calls)==2


def test_format_spelling_and_cited_aliases_join_but_dimensions_remain_separate(setup):
    store,run=category_source(setup)
    class Dimensions(CategoriesClient):
        def generate_structured(self,**kw):
            data=json.loads(kw['user']);self.calls.append(data)
            return kw['output_model'].model_validate({'units':[{'evidence_id':identifier,'categories':[
                {'label':'Parking datasets','dimension':'format','aliases':['Parking'],
                 'quote':text,'rationale':'Synthetic alias in the same source.'},
                {'label':'Parking','dimension':'format','quote':text,'rationale':'Same source label.'},
                {'label':'Parking','dimension':'structure','quote':text,'rationale':'Independent dimension.'}]}
                for identifier,text in data['evidence'].items()]})
    result=coverage.discover_categories(store,run,Dimensions())
    assert result['category_count']==2 and result['dimension_counts']=={'format':1,'structure':1}
    category=next(c for c in result['categories'] if c['dimension']=='format')
    assert set(category['labels'])=={'Parking','Parking datasets'} and len(category['citations'])==2
    assert coverage.category_key('CSV files','format')==coverage.category_key('CSV file','format')
    assert coverage.category_key('CSV','format')!=coverage.category_key('CSV','structure')


def test_partial_scan_protects_unresolved_need_and_keeps_equivalences_review_only(setup):
    store,run,made,families,registry=selection_inputs(setup)
    registry.update(scan_complete=False,unchecked_evidence_ids=['unexamined-unit'])
    made[-1].dataset_coverage={'category_ids':[],'status':'unresolved','links':[]}
    result=coverage.compact_selection(store,run,made,families,registry,EquivalenceClient())
    assert result['selected_count']==4 and '3' in result['selected_need_ids']
    assert result['protected_needs']['3']==['dataset_applicability_unresolved']
    assert not result['category_coverage_complete']
    assert result['unchecked_evidence_ids']==['unexamined-unit']
    assert result['accepted_equivalences']==[] and result['review_only_equivalences']


@pytest.mark.parametrize('bad_units', [None, 'not a list', {'not': 'rows'}])
def test_malformed_category_container_remains_unchecked_without_salvage_crash(setup, bad_units):
    store, run = category_source(setup)
    class Broken(CategoriesClient):
        def generate_structured(self, **kw):
            self.calls.append(json.loads(kw['user']))
            return validate_json_payload(json.dumps({'units': bad_units}), kw['output_model'])
    result = coverage.discover_categories(store, run, Broken())
    assert not result['scan_complete'] and result['category_count'] == 0
    assert sorted(result['unchecked_evidence_ids']) == sorted(run['evidence_ids'])


def test_alias_must_be_in_exact_source_quote():
    mention = coverage.CategoryMention(label='CSV', dimension='format', aliases=['tabular data'],
        quote='CSV files', rationale='Synthetic unsupported alias.')
    assert coverage.mention_errors(mention, 'CSV files')
