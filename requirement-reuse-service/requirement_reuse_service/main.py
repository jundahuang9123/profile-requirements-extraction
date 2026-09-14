from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .llm import LLMConfig
from .models import (
    AggregateExpertReviewsRequest,
    AnalysisRequest,
    FinalizeConsensusRequest,
    FreezeEvaluationPackageRequest,
    RequirementSetLoadRequest,
    RequirementSetSaveRequest,
    ReviseAfterEvaluationRequest,
    ValidateReviewSubmissionRequest,
)
from .evaluation import (
    aggregate_expert_reviews,
    finalize_consensus,
    freeze_evaluation_package,
    revise_after_evaluation,
    validate_review_submission,
)
from .agents.roles import role_health
from .registry import list_requirement_sets, load_requirement_set, save_requirement_set
from .service import analyze_payload, export_rq1_dataset, extract_requirements

app = FastAPI(
    title='RQ1 Blackboard Requirement Service',
    version='0.4.0',
    description=(
        'RQ1: semi-automated, reuse-first requirement extraction for DCAT/DCAT-AP profile '
        'engineering (rule-based baseline, LLM-assisted with verbatim evidence verification, '
        'hybrid, and bounded role-conditioned multi-agent strategies). '
        'Exports reviewed requirements for downstream profile engineering in VPE.'
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5174', 'http://127.0.0.1:5174'],
    allow_credentials=False,
    allow_methods=['*'],
    allow_headers=['*'],
)


router = APIRouter()


@router.get('/health')
def health() -> dict[str, object]:
    config = LLMConfig.from_env()
    try:
        model = config.resolved_model()
    except ValueError:
        model = None
    return {
        'status': 'ok',
        'llm': {'provider': config.provider, 'model': model, 'base_url': config.base_url},
        'multi_agent': role_health(),
    }


@router.post('/analyze-artifacts')
def analyze_artifacts(payload: AnalysisRequest):
    try:
        return analyze_payload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/analyze')
def analyze(payload: AnalysisRequest):
    try:
        return analyze_payload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/extract-requirements')
def extract_requirement_candidates(payload: AnalysisRequest):
    try:
        return extract_requirements(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/export-rq1-dataset')
def export_rq1_requirement_dataset(payload: AnalysisRequest):
    try:
        return export_rq1_dataset(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/freeze-evaluation-package')
def freeze_package(payload: FreezeEvaluationPackageRequest):
    try:
        return freeze_evaluation_package(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/validate-review-submission')
def validate_submission(payload: ValidateReviewSubmissionRequest):
    try:
        return validate_review_submission(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/aggregate-expert-reviews')
def aggregate_reviews(payload: AggregateExpertReviewsRequest):
    try:
        return aggregate_expert_reviews(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/revise-after-evaluation')
def revise_after_review(payload: ReviseAfterEvaluationRequest):
    try:
        return revise_after_evaluation(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/finalize-consensus')
def finalize_review_consensus(payload: FinalizeConsensusRequest):
    try:
        return finalize_consensus(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/save-requirement-set')
def save_set(payload: RequirementSetSaveRequest):
    return save_requirement_set(payload)


@router.post('/list-requirement-sets')
def list_sets():
    return {'requirement_sets': [info.model_dump() for info in list_requirement_sets()]}


@router.post('/load-requirement-set')
def load_set(payload: RequirementSetLoadRequest):
    requirement_set = load_requirement_set(payload.id)
    if requirement_set is None:
        raise HTTPException(status_code=404, detail=f'Requirement set not found: {payload.id}')
    return requirement_set


app.include_router(router, prefix="/api/requirements")
app.include_router(router, include_in_schema=False)

# Serve the standalone UI after npm run build; APIs remain registered first.
from pathlib import Path
from fastapi.staticfiles import StaticFiles

_ui_dist = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
if _ui_dist.is_dir():
    app.mount('/', StaticFiles(directory=str(_ui_dist), html=True), name='ui')
