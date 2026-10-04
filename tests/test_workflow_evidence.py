import base64
import io
import json
import sys
import zipfile
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow.evidence import decompose, register_source, resolve_evidence, source_model
from requirement_reuse_service.workflow.models import EvidenceUnit, SourceRequest
from requirement_reuse_service.workflow.storage import ConflictError, Store, canonical

@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / 'workflow.sqlite3'))

def register(store, name, content, **kwargs):
    encoding = 'text'
    if isinstance(content, bytes):
        content, encoding = base64.b64encode(content).decode(), 'base64'
    return register_source(store, SourceRequest(artifact=ArtifactPayload(name=name, content=content, content_encoding=encoding), **kwargs))

def units(store, source):
    return [EvidenceUnit.model_validate(item) for item in store.list('evidence') if item['source_version_id'] == source['source_version_id']]

def test_source_versions_stability_and_name_collisions(store):
    first = register(store, 'needs.md', 'No recognized keywords.\n😀 All text survives.', source_id='logical-1')
    repeated = register(store, 'needs.md', 'No recognized keywords.\n😀 All text survives.', source_id='logical-1')
    changed = register(store, 'needs.md', 'Changed content.', source_id='logical-1')
    unrelated = register(store, 'needs.md', 'No recognized keywords.\n😀 All text survives.')
    assert first == repeated
    assert first['source_version_id'] != changed['source_version_id']
    assert first['source_id'] != unrelated['source_id']
    regenerated, _, _ = decompose(source_model(first))
    assert {unit.evidence_id for unit in regenerated} == {unit.evidence_id for unit in units(store, first)}
    assert len(regenerated) == 2
    for unit in regenerated:
        assert first['representation'][unit.selector.start:unit.selector.end] == unit.content
        assert resolve_evidence(store, unit)['status'] == 'pass'

def test_selector_and_source_tampering_fail_original_resolution(store):
    source = register(store, 'needs.md', 'Datasets shall carry titles.')
    unit = units(store, source)[0]
    modified = unit.model_copy(deep=True)
    modified.selector.start += 1
    assert resolve_evidence(store, modified)['status'] == 'fail'
    source['raw_base64'] = base64.b64encode(b'Altered').decode()
    with store.connect() as db:
        db.execute('UPDATE objects SET body=? WHERE kind="source" AND id=?', (canonical(source), source['source_version_id']))
    assert 'hash mismatch' in resolve_evidence(store, unit)['message']

def test_json_pointer_escaping_repeated_idshort_and_typed_values(store):
    data = {'a/b~c': 42, 'submodels': [{'idShort': 'Repeated', 'value': '42'}, {'idShort': 'Repeated', 'value': 42}]}
    source = register(store, 'model.json', json.dumps(data))
    assert source['parse_status'] == 'parsed'
    evidence = units(store, source)
    assert any(unit.selector.pointer == '/a~1b~0c' for unit in evidence)
    values = [unit for unit in evidence if unit.selector.pointer.endswith('/value')]
    assert len({unit.selector.value_hash for unit in values}) == 2
    assert all(resolve_evidence(store, unit)['status'] == 'pass' for unit in evidence)

def test_namespace_xml_and_external_entities(store):
    source = register(store, 'model.xml', '<a:submodel xmlns:a="urn:aas"><a:idShort>Name</a:idShort></a:submodel>')
    unit = units(store, source)[0]
    assert unit.selector.tag == '{urn:aas}idShort'
    assert resolve_evidence(store, unit)['status'] == 'pass'
    bad = register(store, 'bad.xml', '<!DOCTYPE foo [<!ENTITY secret SYSTEM "file:///etc/passwd">]><foo>&secret;</foo>')
    assert bad['parse_status'] == 'failed'
    assert units(store, bad) == []

def package(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return buffer.getvalue()

def test_aasx_package_member_and_parent_resolution(store):
    source = register(store, 'model.aasx', package([('model.json', '{"idShort":"Asset"}'), ('extra.txt', 'context')]))
    assert source['parse_status'] == 'parsed', source['diagnostics']
    child = store.get('source', source['child_source_version_ids'][0])
    assert child['package_entry_path'] == 'model.json'
    evidence = units(store, child)
    assert evidence and all(resolve_evidence(store, unit)['status'] == 'pass' for unit in evidence)
    source['raw_base64'] = base64.b64encode(b'bad package').decode()
    with store.connect() as db:
        db.execute('UPDATE objects SET body=? WHERE kind="source" AND id=?', (canonical(source), source['source_version_id']))
    assert resolve_evidence(store, evidence[0])['status'] == 'fail'

def test_duplicate_package_members_and_malformed_sources_report_failure(store):
    with pytest.warns(UserWarning):
        source = register(store, 'duplicate.aasx', package([('model.json', '{}'), ('model.json', '{"a":1}')]))
    assert source['parse_status'] == 'failed'
    assert register(store, 'bad.json', 'not json')['parse_status'] == 'failed'
    assert register(store, 'unsupported.doc', b'bad')['parse_status'] == 'unsupported'

def test_rdf_named_graph_blank_nodes_and_literals_are_reproducible(store):
    a = register(store, 'graph.trig', '<urn:g> { _:a <urn:p> "Titel"@de; <urn:q> "2"^^<http://www.w3.org/2001/XMLSchema#integer>. }')
    b = register(store, 'graph.trig', '<urn:g> { _:z <urn:q> "2"^^<http://www.w3.org/2001/XMLSchema#integer>; <urn:p> "Titel"@de. }')
    assert a['parse_status'] == b['parse_status'] == 'parsed'
    assert a['representation'] == b['representation']
    evidence = units(store, a)
    assert len(evidence) == 2
    assert all('<urn:g>' in unit.content for unit in evidence)
    assert all(resolve_evidence(store, unit)['status'] == 'pass' for unit in evidence)

def test_jsonld_external_context_is_blocked_without_network(store):
    source = register(store, 'graph.jsonld', '{"@context":"https://example.com/context","@id":"urn:a"}')
    assert source['parse_status'] == 'failed'
    assert 'External JSON-LD' in source['diagnostics'][0]

def test_ifc_properties_include_owner_relationship_typed_value_and_unit(store):
    import ifcopenshell
    import ifcopenshell.guid
    model = ifcopenshell.file(schema='IFC4')
    owner = model.create_entity('IfcWall', GlobalId=ifcopenshell.guid.new(), Name='Wall')
    unit = model.create_entity('IfcSIUnit', UnitType='LENGTHUNIT', Name='METRE')
    prop = model.create_entity('IfcPropertySingleValue', Name='Height', NominalValue=model.create_entity('IfcLengthMeasure', 2.5), Unit=unit)
    pset = model.create_entity('IfcPropertySet', GlobalId=ifcopenshell.guid.new(), Name='Pset_Test', HasProperties=[prop])
    relation = model.create_entity('IfcRelDefinesByProperties', GlobalId=ifcopenshell.guid.new(), RelatedObjects=[owner], RelatingPropertyDefinition=pset)
    source = register(store, 'model.ifc', model.to_string())
    assert source['parse_status'] == 'parsed', source['diagnostics']
    evidence = next(item for item in units(store, source) if item.kind == 'ifc_property')
    assert evidence.selector.relationship_ids == [relation.id(), pset.id()]
    assert 'IfcLengthMeasure' in evidence.content and '2.5' in evidence.content
    assert resolve_evidence(store, evidence)['status'] == 'pass'

def test_store_is_immutable(store):
    store.put('source', 'immutable', {'a': 1})
    with pytest.raises(ConflictError):
        store.put('source', 'immutable', {'a': 2})



def test_table_rows_retain_headers_and_namespaces_in_context(store):
    source = register(store, 'table.md', '# Access policy\n| Population | Obligation |\n| --- | --- |\n| Dataset | Must provide rights |')
    evidence = units(store, source)
    row = next(unit for unit in evidence if 'Must provide' in unit.content)
    assert row.kind == 'table_region'
    assert 'Population' in row.structural_context['table_header']
    assert row.structural_context['headings'] == ['# Access policy']
    assert resolve_evidence(store, row)['status'] == 'pass'


def test_context_imports_and_rdf_xml_entities_are_rejected(store):
    source = register(store, 'import.jsonld', '{"@context":{"@import":"https://example.com/context"},"@id":"urn:a"}')
    assert source['parse_status'] == 'failed'
    source = register(store, 'bad.rdf', '<!DOCTYPE foo [<!ENTITY x SYSTEM "file:///etc/passwd">]><foo>&x;</foo>')
    assert source['parse_status'] == 'failed'
