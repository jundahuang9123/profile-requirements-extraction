import importlib.util
import json
import sys
from pathlib import Path
import pytest
from requirement_reuse_service.workflow.base_needs import load_catalogue, offer_entries
from requirement_reuse_service.workflow.models import RequirementRecord

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build_base_needs as builder


def test_all_catalogues_are_reproducible_and_have_distinct_phrases():
    for path in sorted(builder.DIRECTORY.glob('*.needs.json')):
        assert path.read_text()==builder.build(path.with_name(path.name.replace('.needs','')))
        catalogue=load_catalogue(path.stem.removesuffix('.needs'))
        assert catalogue['policy_version']=='rq1-base-needs-catalogue-v2'
        assert catalogue['review']['status']=='unreviewed'
        keys=set()
        for row in catalogue['entries']:
            assert row['label'] and not row['label'].endswith('-')
            assert row['label']==row['label'].strip()
            key=row['class'],row['need']
            assert key not in keys
            keys.add(key)
        assert any(row['definition'] for row in catalogue['entries'])


def test_release_context_definitions_and_identifier_labels():
    catalogue=load_catalogue('dcat-ap-2.0.1')
    entries={(e['class'],e['property']):e for e in catalogue['entries']}
    dataset=entries['dcat:Dataset','dcat:temporalResolution']
    distribution=entries['dcat:Distribution','dcat:temporalResolution']
    assert dataset['definition']=='This property refers to the minimum time period resolvable in the dataset. .'
    assert distribution['definition']=='This property refers to the minimum time period resolvable in the dataset distribution .'
    assert dataset['definition_sources'][0]['anchor'].endswith('#Property:dataset_temporal_resolution')
    assert distribution['definition_sources'][0]['anchor'].endswith('#Property:distribution_temporal_resolution')
    assert entries['dcat:Dataset','adms:identifier']['label']=='other identifier'
    assert entries['dcat:Dataset','dct:identifier']['label']=='identifier'
    assert entries['dcat:Dataset','dct:identifier']['definition']
    assert entries['dcat:Catalog','dct:title']['definition']
    assert entries['dcat:Catalog','dct:creator']['label']=='creator'
    assert entries['adms:Identifier',None]['need']=='Identify and describe an identifier.'


def test_duplicate_phrase_fails_build(tmp_path,monkeypatch):
    profile={'id':'fake','source':{'files':{}},'classes':{'dcat:Dataset':{
        'dct:identifier':{'labels':['identifier']},'adms:identifier':{'labels':['identifier']}}}}
    path=tmp_path/'profile.json';path.write_text(json.dumps(profile))
    with pytest.raises(ValueError,match='Duplicate base need phrase'):builder.build(path,tmp_path)


def test_pin_mismatch_refused(tmp_path):
    path=builder.DIRECTORY/'dcat-ap-2.0.1.json'
    rel='releases/2.0.1/dcat-ap_2.0.1.rdf';bad=tmp_path/rel;bad.parent.mkdir(parents=True);bad.write_text('changed')
    with pytest.raises(ValueError,match='checksum mismatch'):builder.build(path,tmp_path)


def test_retrieval_uses_definitions():
    from types import SimpleNamespace
    catalogue={'entries':[{'id':'yes','need':'Find the title.','definition':'minimum resolvable period','usage_notes':[]},
                           {'id':'no','need':'Find the name.','definition':None,'usage_notes':[]}]}
    offered=offer_entries([SimpleNamespace(need_statement='Users can judge the minimum resolvable period.',normalized_statement='')],catalogue)
    assert [e['id'] for e in offered]==['yes']
