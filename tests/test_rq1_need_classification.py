import json
from copy import deepcopy
from test_resume_discussions import setup
from test_rq1_need_grouping import need_inputs, NeedsClient
from requirement_reuse_service.workflow import needs
from requirement_reuse_service.workflow.base_profile import load_profile
from requirement_reuse_service.workflow.base_needs import load_catalogue


class ClassClient(NeedsClient):
    def generate_structured(self, **kwargs):
        if kwargs['output_model'].__name__!='NeedClassifications': return super().generate_structured(**kwargs)
        data=json.loads(kwargs['user']);self.calls.append(('NeedClassifications',data));entries=[key for key,value in data['base_needs'].items() if value['need']=='Find the title of a dataset.']
        assert entries
        return kwargs['output_model'].model_validate({'classifications':[
            {'need_id':identifier,'classification':label,'base_need_ids':entries[:1] if label!='domain' else [],
             'rationale':'Scripted coverage classification.'}
            for identifier,label in zip(data['needs'],['generic','domain_use_of_base','domain'])]})


def test_base_catalogue_hash_and_no_pretended_review():
    catalogue=load_catalogue('dcat-ap-2.0.1')
    profile,_=load_profile('dcat-ap-2.0.1')
    assert len(catalogue['entries'])==sum(1+len(props) for props in profile['classes'].values())
    from requirement_reuse_service.workflow.base_profile import PROFILE_DIRECTORY
    review_path=PROFILE_DIRECTORY/'dcat-ap-2.0.1.needs-review.json'
    assert catalogue['review']['status']==('reviewed' if review_path.exists() else 'unreviewed')


def test_generic_set_aside_with_base_match_but_domain_kept(setup):
    store,run,records=need_inputs(setup)
    originals,_=needs.write_needs(store,run,[records],NeedsClient(),None)
    proposals=[]
    for index in range(3):
        r=originals[0].model_copy(deep=True);r.requirement_id=f'need-{index}';needs.refresh_need(r);proposals.append(r)
    profile,fingerprint=load_profile('dcat-ap-2.0.1')
    run.update(base_profile_id=profile['id'],base_profile_sha256=fingerprint)
    retained=needs.classify_needs(store,run,proposals,ClassClient())
    assert len(retained)==2 and {n.need_class for n in retained}=={'domain_use_of_base','domain'}
    generic=proposals[0]
    aside=store.get('run',run['run_id'])['set_aside_observations'][-1]
    assert aside['reason']=='generic_need_served_by_base' and aside['matched_base_need_ids']
    assert generic.base_need_matches[0]['rq2_term'] and not generic.rq2_hints
    assert generic.base_need_matches[0]['catalogue_review']==load_catalogue('dcat-ap-2.0.1')['review']


def test_base_gap_status_records_what_was_searched(setup):
    store,run,records=need_inputs(setup)
    originals,_=needs.write_needs(store,run,[records],NeedsClient(),None)
    proposals=[]
    for index in range(3):
        r=originals[0].model_copy(deep=True);r.requirement_id=f'need-{index}';needs.refresh_need(r);proposals.append(r)
    profile,fingerprint=load_profile('dcat-ap-2.0.1')
    run.update(base_profile_id=profile['id'],base_profile_sha256=fingerprint)
    needs.classify_needs(store,run,proposals,ClassClient())
    total=len(load_catalogue('dcat-ap-2.0.1')['entries'])
    gaps=[n.base_gap for n in proposals]
    # A miss among the offered entries is unresolved, never proof that the base lacks the capability.
    assert [g['status'] for g in gaps]==['served_by_base','refines_base','unresolved']
    assert all(g['catalogue_entry_count']==total and 0<g['offered_entry_count']<total and not g['search_complete'] for g in gaps)
    step=store.get('run',run['run_id'])['need_steps']['classification']
    assert step['base_gap_counts']=={'served_by_base':1,'refines_base':1,'unresolved':1}
    assert step['offered_entries'][0]['need_ids']==['need-0','need-1','need-2']
    from requirement_reuse_service.workflow import engine
    assert all(engine.verify(store,n,run['evidence_ids'])['status']=='pass' for n in proposals)


def test_without_a_base_the_gap_is_not_checked(setup):
    store,run,records=need_inputs(setup)
    originals,_=needs.write_needs(store,run,[records],NeedsClient(),None)
    run['base_profile_id']=None
    kept=needs.classify_needs(store,run,originals,ClassClient())
    assert all(n.need_class=='domain' and n.base_gap['status']=='not_checked' for n in kept)
