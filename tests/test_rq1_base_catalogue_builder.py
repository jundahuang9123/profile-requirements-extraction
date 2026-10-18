import importlib.util
import json
import hashlib
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
        review_path=path.with_name(path.name.replace('.needs.json','.needs-review.json'))
        assert catalogue['review']['status']==('reviewed' if review_path.exists() else 'unreviewed')
        keys=set()
        for row in catalogue['entries']:
            assert row['label'] and not row['label'].endswith('-')
            assert row['label']==row['label'].strip()
            key=row['class'],row['need']
            assert key not in keys
            keys.add(key)
        # Some normative sources publish prose usage notes but no formal
        # definitions (the DCAT-AP 1.1 PDF is such a case).
        assert any(row['definition'] or row['usage_notes'] for row in catalogue['entries'])


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
    assert [e['id'] for e in offered][0]=='yes'
    assert {e['id'] for e in offered}=={'yes','no'}  # complete catalogue; ranking only orders context


@pytest.mark.parametrize('version',['2.0.0','3.0.0'])
@pytest.mark.parametrize('prop',['dct:description','dct:issued'])
def test_catalog_inherits_resource_definition_with_original_pin(version,prop):
    catalogue=load_catalogue('dcat-'+version)
    entries={(e['class'],e['property']):e for e in catalogue['entries']}
    resource=entries['dcat:Resource',prop];catalog=entries['dcat:Catalog',prop]
    assert catalog['definition'] and catalog['definition']==resource['definition']
    pin=next(s for s in catalog['definition_sources'] if s.get('inherited_from')=='dcat:Resource')
    assert {k:pin[k] for k in ['file','sha256','anchor']}==resource['definition_sources'][0]
    assert pin['anchor'].startswith('Property:resource_')


def test_inherited_definition_does_not_replace_target_class_label():
    entries={(e['class'],e['property']):e for e in load_catalogue('dcat-2.0.0')['entries']}
    assert entries['dcat:Catalog','dct:issued']['label']=='issued'
    assert entries['dcat:Resource','dct:issued']['label']=='release date'


def test_inherited_definition_keeps_nearest_override_in_same_file(tmp_path):
    def section(cls,parent=None,definition=None):
        prop=('''<section id="Property:'''+cls+'''_description"><h4>Property: description</h4><table>
            <tr><th>RDF Property:</th><td>dct:description</td></tr><tr><th>Definition:</th><td>'''+definition+'''</td></tr>
            </table></section>''') if definition else ''
        ancestry=f'<tr><th>Sub-class of:</th><td>{parent}</td></tr>' if parent else ''
        return f'<section id="Class:{cls}"><table><tr><th>RDF Class:</th><td>dcat:{cls}</td></tr>{ancestry}</table>{prop}</section>'
    raw=('<html>'+section('Resource',definition='Resource prose.')+
         section('Dataset','dcat:Resource','Dataset override.')+section('Catalog','dcat:Dataset')+
         section('DataService','dcat:Resource','Direct service definition.')+
         section('Unrelated')+'</html>').encode()
    relative='w3c/fixture.html';path=tmp_path/relative;path.parent.mkdir();path.write_bytes(raw)
    profile={'source':{'files':{relative:hashlib.sha256(raw).hexdigest()}},
             'classes':{f'dcat:{cls}':{'dct:description':{}} for cls in ['Resource','Dataset','Catalog','DataService','Unrelated']}}
    result=builder.source_descriptions(profile,tmp_path)
    assert result['dcat:Catalog','dct:description']['definitions']==['Dataset override.']
    assert result['dcat:Catalog','dct:description']['sources'][0]['inherited_from']=='dcat:Dataset'
    assert result['dcat:DataService','dct:description']['definitions']==['Direct service definition.']
    assert ('dcat:Unrelated','dct:description') not in result
