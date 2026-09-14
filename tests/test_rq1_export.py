"""RQ1 export and RQ1->RQ2 handoff tests (against the dict-based backend export)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / 'requirement-reuse-service'
sys.path.insert(0, str(SERVICE_ROOT))

import pytest  # noqa: E402

from requirement_reuse_service.models import AnalysisRequest, UserTask  # noqa: E402
from requirement_reuse_service.service import analyze_payload, export_rq1_dataset  # noqa: E402

SOURCE_TEXT = (
    'Each dataset must carry a license or access rights statement. '
    'Datasets exchanged in the dataspace should reference the AAS submodels they represent.'
)

TASKS = [
    UserTask(id='cq-1', statement='Which datasets can be reused under an open license?'),
    UserTask(id='cq-uncovered', statement='Completely unrelated question about quantum entanglement metrics?'),
]


@pytest.fixture(autouse=True)
def offline_provider(monkeypatch):
    for variable in ['RRS_LLM_PROVIDER', 'ANTHROPIC_API_KEY', 'RRS_LLM_BASE_URL', 'RRS_LLM_MODEL']:
        monkeypatch.delenv(variable, raising=False)


def test_backend_export_is_reproducible_run_with_cq_coverage():
    dataset = export_rq1_dataset(AnalysisRequest(text=SOURCE_TEXT, strategy='rules', user_tasks=TASKS))
    assert dataset['schema_version'] == 'rq1-requirement-dataset-v1'
    assert dataset['export_kind'] == 'reproducible_run'
    coverage = dataset['summary_metrics']['competency_question_coverage']
    assert coverage['task_count'] == 2
    assert 'cq-uncovered' in coverage['uncovered_task_ids']
    assert coverage['covered_task_count'] == 1
    assert dataset['evidence_units']
    assert dataset['duplicate_groups'] is not None


def test_actions_carry_constraint_hint_and_source_requirement_id():
    response = analyze_payload(AnalysisRequest(text=SOURCE_TEXT, strategy='rules'))
    for requirement in response.requirements:
        for action in requirement.candidate_metadata_actions:
            assert action.constraint_hint is not None
            assert action.constraint_hint.obligation == requirement.normalized_intent.obligation_hint
            assert action.constraint_hint.value_kind == requirement.normalized_intent.value_kind
            assert action.source_requirement_id == requirement.id
