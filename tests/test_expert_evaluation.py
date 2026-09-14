import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / 'requirement-reuse-service'
sys.path.insert(0, str(SERVICE_ROOT))

from requirement_reuse_service.evaluation import (  # noqa: E402
    aggregate_expert_reviews,
    assert_study_transition,
    finalize_consensus,
    freeze_evaluation_package,
    hash_payload,
    revise_after_evaluation,
    validate_evaluation_package,
    validate_review_submission,
)
from requirement_reuse_service.models import (  # noqa: E402
    AggregateExpertReviewsRequest,
    AnalysisRequest,
    ConsensusDecision,
    ExpertCriterionRatings,
    ExpertRequirementReview,
    ExpertReviewSubmission,
    FinalizeConsensusRequest,
    FreezeEvaluationPackageRequest,
    MissingRequirementProposal,
    ReviseAfterEvaluationRequest,
    ValidateReviewSubmissionRequest,
)
from requirement_reuse_service.service import analyze_payload  # noqa: E402


SOURCE = (
    'Each dataset must carry a license or access rights statement. '
    'Datasets should expose their format and schema version.'
)


def package():
    analysis = analyze_payload(AnalysisRequest(text=SOURCE, strategy='rules', study_mode='summative'))
    return freeze_evaluation_package(FreezeEvaluationPackageRequest(analysis=analysis))


def submission(pkg, reviewer_id, decisions=None, missing=None):
    decisions = decisions or {}
    reviews = [
        ExpertRequirementReview(
            requirement_id=requirement.id,
            decision=decisions.get(requirement.id, 'accept'),
            ratings=ExpertCriterionRatings(
                evidence_fidelity=5, correctness=5, relevance=4, necessity=4,
                clarity=4, atomicity=4, reuse_potential=5, extension_necessity=3,
            ),
            comment='Clear evidence-linked candidate.',
            proposed_statement=(
                f'{requirement.normalized_statement} Reviewed wording.'
                if decisions.get(requirement.id) == 'accept_with_revision' else None
            ),
            feedback_categories=['clarity'] if decisions.get(requirement.id) == 'accept_with_revision' else [],
        )
        for requirement in pkg.machine_requirements
    ]
    value = ExpertReviewSubmission(
        id=f'sub-{reviewer_id}',
        evaluation_package_id=pkg.id,
        evaluation_package_hash=pkg.package_hash,
        reviewer_id=reviewer_id,
        started_at='2026-07-15T10:00:00Z',
        completed_at='2026-07-15T10:10:00Z',
        reviews=reviews,
        missing_requirements=missing or [],
        submission_hash='',
    )
    return value.model_copy(update={'submission_hash': hash_payload(value, 'submission_hash')})


def aggregate(pkg, submissions):
    return aggregate_expert_reviews(AggregateExpertReviewsRequest(
        evaluation_package=pkg,
        review_submissions=submissions,
    ))


def test_frozen_package_is_immutable_and_hash_detects_nested_modification():
    pkg = package()
    with pytest.raises(ValidationError):
        pkg.package_hash = 'changed'
    pkg.machine_requirements[0].normalized_statement = 'tampered'
    with pytest.raises(ValueError, match='hash mismatch'):
        validate_evaluation_package(pkg)


def test_study_phase_transitions_are_bounded_and_formative_may_be_skipped_for_tests():
    assert_study_transition('development', 'workflow_frozen', allow_skip_formative=True)
    assert_study_transition('summative_review_closed', 'post_evaluation_revision')
    with pytest.raises(ValueError, match='Invalid study phase transition'):
        assert_study_transition('summative_review_open', 'post_evaluation_revision')


def test_review_submission_rejects_unknown_ids_duplicates_bad_ratings_and_missing_revision_explanation():
    pkg = package()
    valid = submission(pkg, 'E1')
    bad = valid.model_copy(deep=True)
    bad.reviews[0].requirement_id = 'unknown'
    bad = bad.model_copy(update={'submission_hash': hash_payload(bad, 'submission_hash')})
    with pytest.raises(ValueError, match='unknown requirement'):
        validate_review_submission(ValidateReviewSubmissionRequest(evaluation_package=pkg, review_submission=bad))
    with pytest.raises(ValidationError, match='duplicate reviews'):
        ExpertReviewSubmission(**{**valid.model_dump(), 'reviews': [valid.reviews[0], valid.reviews[0]]})
    with pytest.raises(ValidationError, match='1 to 5'):
        ExpertCriterionRatings(correctness=6)
    with pytest.raises(ValidationError, match='requires a proposed statement'):
        ExpertRequirementReview(requirement_id='r', decision='accept_with_revision', ratings={})


def test_submission_hash_detects_changes_and_validation_response_exposes_no_other_reviews():
    pkg = package()
    valid = submission(pkg, 'E1')
    result = validate_review_submission(ValidateReviewSubmissionRequest(evaluation_package=pkg, review_submission=valid))
    assert result['valid'] is True
    assert 'review_submissions' not in result
    changed = valid.model_copy(deep=True)
    changed.reviews[0].comment = 'changed after signing'
    with pytest.raises(ValueError, match='submission hash mismatch'):
        validate_review_submission(ValidateReviewSubmissionRequest(evaluation_package=pkg, review_submission=changed))


def test_three_reviews_aggregate_unanimity_majority_disagreement_and_agreement_metrics():
    pkg = package()
    target = pkg.machine_requirements[0].id
    submissions = [
        submission(pkg, 'E1'),
        submission(pkg, 'E2'),
        submission(pkg, 'E3', {target: 'reject'}),
    ]
    result = aggregate(pkg, submissions)
    assert result.complete is True
    item = next(value for value in result.requirement_aggregates if value.requirement_id == target)
    assert item.majority_decision == 'accept'
    assert item.disagreement is True
    assert result.summary_metrics['disagreement_count'] == 1
    assert result.summary_metrics['raw_exact_agreement'] < 1
    assert result.summary_metrics['pairwise_decision_agreement'] < 1
    assert result.summary_metrics['fleiss_kappa'] is not None


def test_incomplete_panel_and_cannot_assess_are_handled_without_false_completion():
    pkg = package()
    target = pkg.machine_requirements[0].id
    result = aggregate(pkg, [submission(pkg, 'E1', {target: 'cannot_assess'}), submission(pkg, 'E2')])
    assert result.complete is False
    assert result.summary_metrics['cannot_assess_count'] == 1
    assert result.summary_metrics['fleiss_kappa'] is None


def test_revision_is_blocked_for_incomplete_panel_and_preserves_original_machine_output():
    pkg = package()
    target = pkg.machine_requirements[0].id
    incomplete_submissions = [submission(pkg, 'E1', {target: 'accept_with_revision'})]
    incomplete = aggregate(pkg, incomplete_submissions)
    with pytest.raises(ValueError, match='complete review panel'):
        revise_after_evaluation(ReviseAfterEvaluationRequest(
            evaluation_package=pkg,
            aggregation=incomplete,
            review_submissions=incomplete_submissions,
        ))
    complete_submissions = [
        submission(pkg, 'E1', {target: 'accept_with_revision'}),
        submission(pkg, 'E2', {target: 'accept_with_revision'}),
        submission(pkg, 'E3', {target: 'accept_with_revision'}),
    ]
    complete = aggregate(pkg, complete_submissions)
    original_metrics = complete.summary_metrics.copy()
    revision = revise_after_evaluation(ReviseAfterEvaluationRequest(
        evaluation_package=pkg,
        aggregation=complete,
        review_submissions=complete_submissions,
    ))
    record = next(item for item in revision.revisions if item.requirement_id == target)
    original = next(item for item in pkg.machine_requirements if item.id == target)
    assert record.original_statement == original.machine_original_statement
    assert complete.summary_metrics == original_metrics
    validate_evaluation_package(pkg)


def test_expert_added_requirements_are_labeled_and_need_consensus():
    pkg = package()
    proposal = MissingRequirementProposal(
        id='missing-1',
        statement='A dcat:Dataset should identify its publisher.',
        rationale='The frozen set omitted publisher accountability.',
        evidence_unit_ids=[pkg.evidence_units[0].id],
        requirement_type='descriptive_metadata',
    )
    submissions = [submission(pkg, 'E1', missing=[proposal]), submission(pkg, 'E2'), submission(pkg, 'E3')]
    agg = aggregate(pkg, submissions)
    revision = revise_after_evaluation(ReviseAfterEvaluationRequest(
        evaluation_package=pkg,
        aggregation=agg,
        review_submissions=submissions,
    ))
    assert revision.expert_added_requirements[0].origin_kind == 'expert_added'
    assert revision.expert_added_requirements[0].status == 'candidate'


def test_final_consensus_exports_validated_baseline():
    pkg = package()
    target = pkg.machine_requirements[0].id
    submissions = [submission(pkg, reviewer) for reviewer in ['E1', 'E2', 'E3']]
    agg = aggregate(pkg, submissions)
    decisions = [
        ConsensusDecision(
            requirement_id=requirement.id,
            decision='accepted' if requirement.id == target else 'rejected',
            rationale='Human expert panel consensus.',
            participant_reviewer_ids=['E1', 'E2', 'E3'],
            decided_at='2026-07-15T11:00:00Z',
        )
        for requirement in pkg.machine_requirements
    ]
    baseline = finalize_consensus(FinalizeConsensusRequest(
        evaluation_package=pkg,
        aggregation=agg,
        consensus_decisions=decisions,
    ))
    assert len(baseline.requirements) == 1
    assert baseline.requirements[0].formal_consensus_decision == 'accepted'
