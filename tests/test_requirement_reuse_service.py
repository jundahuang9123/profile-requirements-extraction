import base64
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / 'requirement-reuse-service'
sys.path.insert(0, str(SERVICE_ROOT))

from requirement_reuse_service.models import AnalysisRequest
from requirement_reuse_service.service import analyze_payload


def test_text_analysis_extracts_traceable_requirements():
    analysis = analyze_payload(
        AnalysisRequest(
            text='Datasets should indicate the construction asset type they describe. Metadata should include lifecycle phase and access conditions. Datasets need title, description, format, and semantic anchors to AAS submodels.'
        )
    )

    assert analysis.evidence_units
    assert {item.category for item in analysis.requirements} >= {'Dataset Metadata', 'Semantic Anchors', 'Lifecycle Information', 'Access/Policy'}
    assert any(item.fair_dimensions for item in analysis.requirements)
    assert any(item.source_evidence for item in analysis.requirements)



def test_aas_json_extracts_evidence_semantic_ids():
    analysis = analyze_payload(
        AnalysisRequest(
            artifacts=[
                {
                    'name': 'pump-submodel.json',
                    'content': '{"submodels":[{"idShort":"PumpStatus","semanticId":{"keys":[{"value":"https://example.org/aas/PumpStatus"}]}}]}',
                }
            ]
        )
    )

    assert any(candidate.kind.startswith('aas-') for candidate in analysis.semantic_candidates)
    assert any(attribute.label == 'idShort' and attribute.value == 'PumpStatus' for attribute in analysis.extracted_attributes)
    assert any(unit.artifact_kind == 'aas-json' and unit.locator and 'semanticId' in unit.locator for unit in analysis.evidence_units)
    assert any('AAS semantic identifiers' in (requirement.normalized_statement or '') for requirement in analysis.requirements)
    assert any({'F', 'I', 'R'} <= set(requirement.fair_dimensions) for requirement in analysis.requirements if requirement.requirement_type == 'semantic_anchor')



def test_aasx_package_extracts_embedded_aas_json():
    package = io.BytesIO()
    aas_payload = {
        'submodels': [
            {
                'idShort': 'PumpMaintenance',
                'semanticId': {'keys': [{'value': 'https://example.org/aas/PumpMaintenance'}]},
            }
        ]
    }
    with zipfile.ZipFile(package, 'w') as archive:
        archive.writestr('aas/submodel.json', json.dumps(aas_payload))

    analysis = analyze_payload(
        AnalysisRequest(
            artifacts=[
                {
                    'name': 'pump.aasx',
                    'content': base64.b64encode(package.getvalue()).decode('ascii'),
                    'content_encoding': 'base64',
                }
            ]
        )
    )

    assert any(summary.kind == 'aasx' for summary in analysis.artifacts)
    assert any(candidate.label == 'PumpMaintenance' for candidate in analysis.semantic_candidates)
    assert any(attribute.label == 'idShort' and attribute.value == 'PumpMaintenance' for attribute in analysis.extracted_attributes)
    assert any(unit.artifact_kind in {'aasx', 'aas-json'} for unit in analysis.evidence_units)
    assert any(candidate.property == 'hasAASSubmodel' for candidate in analysis.metadata_candidates)


def test_ifc_evidence_generates_schema_entity_and_asset_requirements():
    analysis = analyze_payload(
        AnalysisRequest(
            artifacts=[
                {
                    'name': 'building.ifc',
                    'content': "ISO-10303-21; FILE_SCHEMA(('IFC4')); #1=IFCWALL(); #2=IFCSPACE(); #3=IFCPROPERTYSET(); ENDSEC; END-ISO-10303-21;",
                }
            ]
        )
    )

    statements = ' '.join(requirement.normalized_statement or '' for requirement in analysis.requirements)
    assert any(unit.locator == 'FILE_SCHEMA' for unit in analysis.evidence_units)
    assert 'IFC schema version' in statements
    assert 'IFC entity classes' in statements
    assert 'construction asset type' in statements


def test_duplicate_detection_groups_overlapping_semantic_requirements():
    analysis = analyze_payload(
        AnalysisRequest(
            text='A dcat:Dataset should reference AAS semantic identifiers. A dcat:Dataset should support external semantic identifiers. A dcat:Dataset should expose semantic IDs for discovery.'
        )
    )

    assert analysis.duplicate_groups
    assert any(len(group.requirement_ids) >= 2 for group in analysis.duplicate_groups)
