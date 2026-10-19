"""Synthetic procedural-review tests; no evaluation answers or live generation."""
import json
from copy import deepcopy
from types import SimpleNamespace
import pytest
from test_routed_stakeholder_workflow import setup,make_record,install_records
from test_fa_workflow import enable
from requirement_reuse_service.workflow import base_review as br
from requirement_reuse_service.workflow.base_needs import load_catalogue
from requirement_reuse_service.workflow.base_profile import load_profile
from requirement_reuse_service.workflow.models import RequirementRecord,RunRequest
from requirement_reuse_service.workflow.needs import refresh_need,need_integrity
from requirement_reuse_service.workflow.storage import digest


def prepared(setup,count=1):
    store,run,units,_=setup;run=enable(store,run)
    records=[make_record(store,run,units[i%len(units)],i) for i in range(count)]
    run=install_records(store,run,records);profile,fingerprint=load_profile('dcat-ap-1.1.0')
    cat=load_catalogue(profile['id'],fingerprint)
    def pin(r):
        r.update(base_profile_id=profile['id'],base_profile_sha256=fingerprint,
            base_needs_catalogue={k:v for k,v in cat.items() if k!='entries'})
        r['request'].update(base_profile_id=profile['id'],base_check=False)
    store.mutate(run['run_id'],None,'fixture_pin',pin)
    return store,store.get('run',run['run_id']),cat

class Reviewer:
    def __init__(self,verdict='new',invalid=None,checked=True):self.calls=[];self.verdict=verdict;self.invalid=invalid;self.checked=checked
    def describe(self):return {'provider':'scripted','model':'default-reviewer'}
    def generate_structured(self,*,user,output_model,**kwargs):
        p=json.loads(user);self.calls.append((output_model.__name__,p))
        if output_model==br.BaseReview:
            rows=[]
            for key,n in p['needs'].items():
                v={'item_id':key,'verdict':self.verdict,'entry_ids':n['offered_entry_ids'][:1] if self.verdict in {'restates_base','domain_use_of_base'} else [],'rationale':'Synthetic comparison.'}
                if self.verdict=='domain_use_of_base':v.update(addition_kind='condition',addition='A stated source condition.',evidence_ids=n['excerpt_ids'][:1])
                if self.invalid:self.invalid(v,n)
                rows.append(v)
            return output_model(verdicts=rows)
        return output_model(checks=[{'item_id':key,'entries_express_need':self.checked,'nothing_lost':self.checked,'rationale':'Independent synthetic check.'} for key in p['needs']])


def test_pin_and_effect_checkpoint_resume_without_changing_revision(setup,monkeypatch):
    store,run,cat=prepared(setup);before=deepcopy(run['requirements'][0]);client=Reviewer('restates_base')
    br.review_base(store,run,client);saved=store.get('run',run['run_id']);n=saved['requirements'][0]
    assert n['base_relation']['status']=='checked' and n['base_relation']['effect']=='flag_added'
    assert n['base_relation']['human_accepted'] is False
    assert n['revision_id']==before['revision_id'] and n['content_hash']==before['content_hash']
    assert n['need_integrity_hash']!=before['need_integrity_hash']
    assert 'covered_by_base' in n['processing_flags']
    br.review_base(store,saved,client);assert len(client.calls)==2
    monkeypatch.setattr(br,'REVIEW_SYSTEM',br.REVIEW_SYSTEM+' changed')
    with pytest.raises(ValueError,match='checkpoint mismatch'):br.review_base(store,store.get('run',run['run_id']),client)


@pytest.mark.parametrize('invalid',[
    lambda v,n:v.update(entry_ids=['B999']),
    lambda v,n:v.update(entry_ids=[]),
])
def test_invalid_restating_verdict_gets_one_correction_then_pending(setup,invalid):
    store,run,_=prepared(setup);client=Reviewer('restates_base',invalid)
    br.review_base(store,run,client);saved=store.get('run',run['run_id'])
    assert len(client.calls)==2 and saved['requirements'][0]['base_relation']['status']=='not_reviewed'
    assert 'base_review_pending'in saved['requirements'][0]['processing_flags']


def test_domain_addition_requires_source_and_other_batches_continue(setup):
    store,run,_=prepared(setup,5)
    client=Reviewer('domain_use_of_base',lambda v,n:v.update(evidence_ids=[]) if len(n['offered_entry_ids']) else None)
    br.review_base(store,run,client);assert len(client.calls)==4
    assert all(n['base_relation']['status']=='not_reviewed' for n in store.get('run',run['run_id'])['requirements'])


def test_condition_and_catalogue_pin(setup):
    store,run,_=prepared(setup)
    run['requirements'][0]['need_condition']='Only if an authorised recipient has signed a special agreement.'
    br.review_base(store,run,Reviewer('restates_base'))
    assert store.get('run',run['run_id'])['requirements'][0]['base_relation']['status']=='not_reviewed'
    run['base_needs_catalogue']['catalogue_hash']='changed'
    with pytest.raises(ValueError,match='catalogue changed'):br.review_base(store,run,Reviewer())


def test_older_catalogue_cannot_offer_or_accept_other_version_creator(setup):
    store,run,cat=prepared(setup);n=RequirementRecord.model_validate(run['requirements'][0]);n.need_statement='Users can find the creator of a resource.'
    p,a=br.make_payload(store,run,[n],cat,'before_discussion')
    assert all(e['property']!='dct:creator' for e in p['base']['entries'].values())
    other=next(e for e in load_catalogue('dcat-ap-2.1.1')['entries'] if e.get('property')=='dct:creator')
    bad=br.BaseReview(verdicts=[{'item_id':n.revision_id,'verdict':'restates_base','entry_ids':[other['id']],'rationale':'Wrong version.'}])
    assert br.verdict_errors(bad,[n],p)


@pytest.mark.parametrize('state',['covered','domain_use_of_base','domain',None])
@pytest.mark.parametrize('verdict',['restates_base','domain_use_of_base','new','uncertain'])
def test_effect_table_preserves_inventory(setup,state,verdict):
    store,run,cat=prepared(setup);n=RequirementRecord.model_validate(run['requirements'][0]);n.need_class='domain' if state=='covered' else state
    if state=='covered':n.processing_flags=['covered_by_base']
    p,a=br.make_payload(store,run,[n],cat,'before_discussion');rid=n.revision_id;h=n.content_hash
    v=br.BaseVerdict(item_id=rid,verdict=verdict,entry_ids=[],rationale='Synthetic judgement.')
    check=br.BaseVerdictCheck(item_id=rid,entries_express_need=True,nothing_lost=True,rationale='Checked.')
    br.apply_verdict(n,v,check,'before_discussion',cat,'key',{},p);refresh_need(n)
    assert n.revision_id==rid and n.content_hash==h
    assert ('covered_by_base'in n.processing_flags)==(state=='covered' or verdict=='restates_base')
    assert (n.base_relation['effect']=='dispute')==(state=='covered' and verdict in {'new','domain_use_of_base'})


def test_failed_check_keeps_labels_and_surfaces_review(setup):
    store,run,_=prepared(setup);br.review_base(store,run,Reviewer('restates_base',checked=False))
    n=store.get('run',run['run_id'])['requirements'][0]
    assert n['base_relation']['status']=='check_failed' and 'covered_by_base'not in n['processing_flags']
    assert 'base_relation_review'in n['processing_flags']


def test_size_splits_and_single_need_pending(setup,monkeypatch):
    store,run,_=prepared(setup,5);monkeypatch.setattr(br,'MAX_PAYLOAD',1);client=Reviewer()
    br.review_base(store,run,client)
    assert client.calls==[]
    assert all(n['base_relation']['reason']=='payload_budget' for n in store.get('run',run['run_id'])['requirements'])
