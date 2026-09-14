from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from statistics import mean, median
from typing import Any

from pydantic import BaseModel

from .agents.roles import WORKFLOW_VERSION, resolve_panel
from .agents.revision import propose_revisions
from .llm import LLMConfig, LLMError, create_client
from .models import (
    AggregateExpertReviewsRequest,
    CandidateRequirement,
    ConsensusDecision,
    EvaluationPackage,
    ExpertReviewSubmission,
    FinalizeConsensusRequest,
    FreezeEvaluationPackageRequest,
    MissingRequirementProposal,
    RequirementReviewAggregate,
    ReviewAggregation,
    RevisionRecord,
    RevisionResponse,
    ReviseAfterEvaluationRequest,
    SourceEvidence,
    StudyPhase,
    ValidatedRequirementBaseline,
    ValidateReviewSubmissionRequest,
)
from .service import stable_id


STUDY_TRANSITIONS: dict[str, str] = {
    'development': 'formative_review',
    'formative_review': 'workflow_frozen',
    'workflow_frozen': 'summative_review_open',
    'summative_review_open': 'summative_review_closed',
    'summative_review_closed': 'post_evaluation_revision',
    'post_evaluation_revision': 'consensus_validation',
    'consensus_validation': 'validated',
}


def assert_study_transition(current: StudyPhase, target: StudyPhase, *, allow_skip_formative: bool = False) -> None:
    if allow_skip_formative and current == 'development' and target == 'workflow_frozen':
        return
    expected = STUDY_TRANSITIONS.get(current)
    if expected != target:
        raise ValueError(f"Invalid study phase transition: {current} -> {target}; expected {expected or 'terminal state'}.")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)


def hash_payload(value: BaseModel | dict[str, Any], excluded_field: str) -> str:
    data = value.model_dump(mode='json', exclude_none=False) if isinstance(value, BaseModel) else dict(value)
    data.pop(excluded_field, None)
    return hashlib.sha256(canonical_json(data).encode('utf-8')).hexdigest()


def freeze_evaluation_package(request: FreezeEvaluationPackageRequest) -> EvaluationPackage:
    analysis = request.analysis
    if analysis.study_phase == 'development':
        assert_study_transition('development', 'workflow_frozen', allow_skip_formative=True)
    elif analysis.study_phase == 'formative_review':
        assert_study_transition('formative_review', 'workflow_frozen')
    elif analysis.study_phase != 'workflow_frozen':
        raise ValueError(f'Cannot freeze machine output from study phase {analysis.study_phase!r}.')
    if request.target_reviewer_count < 1:
        raise ValueError('target_reviewer_count must be positive')
    if analysis.strategy == 'multi_agent' and analysis.panel_preset == 'full_15' and analysis.panel_status != 'completed':
        raise ValueError('An incomplete full-panel run cannot be frozen as a completed full_15 evaluation condition.')
    include_ids = set(request.include_requirement_ids)
    unknown_inclusions = include_ids - {item.id for item in analysis.requirements}
    if unknown_inclusions:
        raise ValueError(f"Unknown coordinator inclusion ids: {', '.join(sorted(unknown_inclusions))}")

    raw = [freeze_requirement(item) for item in analysis.raw_agent_requirements]
    machine = [
        freeze_requirement(item)
        for item in analysis.requirements
        if (
            item.id in include_ids
            or (item.support_level != 'unsupported' and bool(item.source_evidence))
        )
    ]
    if not machine:
        raise ValueError('The default evaluation queue is empty; no supported, evidence-linked requirements can be frozen.')
    workflow_version = analysis.workflow_version or WORKFLOW_VERSION
    role_configuration = []
    if analysis.strategy == 'multi_agent':
        configured_ids = {run.role_id for run in analysis.agent_runs}
        role_configuration = [
            role for role in resolve_panel(analysis.panel_preset or 'full_15')
            if role.id in configured_ids
        ]
    input_hash = analysis.input_hash or hashlib.sha256(canonical_json({
        'evidence_units': [unit.model_dump(mode='json') for unit in analysis.evidence_units],
        'user_tasks': [task.model_dump(mode='json') for task in analysis.user_tasks],
    }).encode('utf-8')).hexdigest()
    now = utc_now()
    package = EvaluationPackage(
        id=stable_id('eval', input_hash, workflow_version, *(item.id for item in machine)),
        created_at=now,
        target_reviewer_count=request.target_reviewer_count,
        study_phase='workflow_frozen',
        source_corpus_id=str(analysis.study_setup.get('source_corpus_id') or '') or None,
        input_hash=input_hash,
        workflow_version=workflow_version,
        strategy_used=analysis.strategy,
        model_configuration={
            'models': sorted({run.model_id for run in analysis.agent_runs if run.model_id}),
            'prompt_versions': sorted({run.prompt_version for run in analysis.agent_runs if run.prompt_version}),
            'panel_preset': analysis.panel_preset,
            'panel_status': analysis.panel_status,
            'completed_roles': [run.role_id for run in analysis.agent_runs if run.status == 'completed'],
        },
        role_configuration=role_configuration,
        agent_runs=[run.model_copy(deep=True) for run in analysis.agent_runs],
        agent_contexts=[context.model_copy(deep=True) for context in analysis.agent_contexts],
        workflow_trace=[event.model_copy(deep=True) for event in analysis.workflow_trace],
        evidence_units=[unit.model_copy(deep=True) for unit in analysis.evidence_units],
        user_tasks=[task.model_copy(deep=True) for task in analysis.user_tasks],
        raw_agent_requirements=raw,
        machine_requirements=machine,
        consolidation_events=[event.model_copy(deep=True) for event in analysis.consolidation_events],
        critique_findings=[finding.model_copy(deep=True) for finding in analysis.critique_findings],
        warnings=list(analysis.warnings),
        package_hash='',
    )
    return package.model_copy(update={'package_hash': hash_payload(package, 'package_hash')})


def freeze_requirement(requirement: CandidateRequirement) -> CandidateRequirement:
    frozen = requirement.model_copy(deep=True)
    frozen.machine_output_frozen = True
    frozen.machine_original_statement = (
        requirement.machine_original_statement
        or requirement.normalized_statement
        or requirement.description
        or requirement.title
        or requirement.id
    )
    return frozen


def validate_evaluation_package(package: EvaluationPackage) -> None:
    actual = hash_payload(package, 'package_hash')
    if actual != package.package_hash:
        raise ValueError('Evaluation package hash mismatch; the frozen machine output or metadata was modified.')


def validate_review_submission(request: ValidateReviewSubmissionRequest) -> dict[str, Any]:
    package = request.evaluation_package
    submission = request.review_submission
    validate_evaluation_package(package)
    if submission.evaluation_package_id != package.id or submission.evaluation_package_hash != package.package_hash:
        raise ValueError('Review submission references a different evaluation package id or hash.')
    known_ids = {item.id for item in package.machine_requirements}
    unknown = sorted({review.requirement_id for review in submission.reviews} - known_ids)
    if unknown:
        raise ValueError(f"Review submission references unknown requirement ids: {', '.join(unknown)}")
    known_evidence = {unit.id for unit in package.evidence_units}
    bad_evidence = sorted({
        evidence_id
        for proposal in submission.missing_requirements
        for evidence_id in proposal.evidence_unit_ids
        if evidence_id not in known_evidence
    })
    if bad_evidence:
        raise ValueError(f"Missing-requirement proposals reference unknown evidence ids: {', '.join(bad_evidence)}")
    actual_hash = hash_payload(submission, 'submission_hash')
    if actual_hash != submission.submission_hash:
        raise ValueError('Review submission hash mismatch; reviewer data was modified after signing.')
    return {
        'valid': True,
        'reviewer_id': submission.reviewer_id,
        'reviewed_requirement_count': len(submission.reviews),
        'complete': {review.requirement_id for review in submission.reviews} == known_ids,
        'submission_hash': submission.submission_hash,
    }


def aggregate_expert_reviews(request: AggregateExpertReviewsRequest) -> ReviewAggregation:
    package = request.evaluation_package
    validate_evaluation_package(package)
    submissions = request.review_submissions
    reviewer_ids = [submission.reviewer_id for submission in submissions]
    if len(reviewer_ids) != len(set(reviewer_ids)):
        raise ValueError('Only one independent submission per pseudonymous reviewer id is allowed.')
    for submission in submissions:
        validate_review_submission(ValidateReviewSubmissionRequest(
            evaluation_package=package,
            review_submission=submission,
        ))

    reviews_by_requirement = {
        requirement.id: [
            (submission.reviewer_id, review)
            for submission in submissions
            for review in submission.reviews
            if review.requirement_id == requirement.id
        ]
        for requirement in package.machine_requirements
    }
    aggregates: list[RequirementReviewAggregate] = []
    for requirement in package.machine_requirements:
        reviews = reviews_by_requirement[requirement.id]
        decision_counts = Counter(review.decision for _, review in reviews)
        unanimous = bool(reviews) and len(decision_counts) == 1
        majority = None
        if decision_counts:
            decision, count = decision_counts.most_common(1)[0]
            if count > len(reviews) / 2:
                majority = decision
        rating_names = list(package_rating_names())
        median_ratings = {
            name: float(median(values)) if (values := [
                value
                for _, review in reviews
                if (value := getattr(review.ratings, name)) is not None
            ]) else None
            for name in rating_names
        }
        aggregates.append(RequirementReviewAggregate(
            requirement_id=requirement.id,
            reviewer_count=len(reviews),
            decisions=dict(decision_counts),
            unanimous=unanimous,
            majority_decision=majority,
            disagreement=len(decision_counts) > 1,
            median_ratings=median_ratings,
            comments=[{
                'reviewer_id': reviewer_id,
                'comment': review.comment,
                'proposed_statement': review.proposed_statement,
                'feedback_categories': review.feedback_categories,
                'proposed_merge_with': review.proposed_merge_with,
                'proposed_split_statements': review.proposed_split_statements,
            } for reviewer_id, review in reviews if (
                review.comment or review.proposed_statement or review.feedback_categories
                or review.proposed_merge_with or review.proposed_split_statements
            )],
        ))

    requirement_count = len(package.machine_requirements)
    complete = (
        len(reviewer_ids) == package.target_reviewer_count
        and all(aggregate.reviewer_count == package.target_reviewer_count for aggregate in aggregates)
    )
    decisions_matrix = [
        [review.decision for _, review in reviews_by_requirement[requirement.id]]
        for requirement in package.machine_requirements
    ]
    all_rating_values: dict[str, list[int]] = {
        name: [
            value
            for submission in submissions
            for review in submission.reviews
            if (value := getattr(review.ratings, name)) is not None
        ]
        for name in package_rating_names()
    }
    unanimous_accepted = sum(
        aggregate.unanimous and aggregate.majority_decision == 'accept' for aggregate in aggregates
    )
    majority_accepted = sum(
        aggregate.majority_decision in {'accept', 'accept_with_revision'} for aggregate in aggregates
    )
    summary = {
        'requirement_count': requirement_count,
        'reviewer_count': len(reviewer_ids),
        'unanimously_accepted_count': unanimous_accepted,
        'unanimously_accepted_percentage': percentage(unanimous_accepted, requirement_count),
        'majority_accepted_count': majority_accepted,
        'majority_accepted_percentage': percentage(majority_accepted, requirement_count),
        'accepted_with_revision_count': sum(
            aggregate.decisions.get('accept_with_revision', 0) > 0 for aggregate in aggregates
        ),
        'rejected_count': sum(aggregate.decisions.get('reject', 0) > 0 for aggregate in aggregates),
        'out_of_scope_count': sum(aggregate.decisions.get('out_of_scope', 0) > 0 for aggregate in aggregates),
        'cannot_assess_count': sum(aggregate.decisions.get('cannot_assess', 0) > 0 for aggregate in aggregates),
        'disagreement_count': sum(aggregate.disagreement for aggregate in aggregates),
        'average_ratings': {name: mean(values) if values else None for name, values in all_rating_values.items()},
        'median_ratings': {name: median(values) if values else None for name, values in all_rating_values.items()},
        'raw_exact_agreement': exact_agreement(decisions_matrix),
        'pairwise_decision_agreement': pairwise_agreement(submissions, package.machine_requirements),
        'fleiss_kappa': fleiss_kappa(decisions_matrix) if complete else None,
        'performance_basis': 'frozen_original_machine_requirements',
    }
    missing = [proposal for submission in submissions for proposal in submission.missing_requirements]
    return ReviewAggregation(
        evaluation_package_id=package.id,
        evaluation_package_hash=package.package_hash,
        reviewer_ids=sorted(reviewer_ids),
        expected_reviewer_count=package.target_reviewer_count,
        complete=complete,
        requirement_aggregates=aggregates,
        missing_requirement_proposals=missing,
        summary_metrics=summary,
    )


def revise_after_evaluation(request: ReviseAfterEvaluationRequest) -> RevisionResponse:
    package = request.evaluation_package
    aggregation = request.aggregation
    validate_evaluation_package(package)
    validate_aggregation(package, aggregation)
    assert_study_transition('summative_review_closed', 'post_evaluation_revision')
    if not aggregation.complete:
        raise ValueError('Post-evaluation revision requires a complete review panel and closed summative evaluation.')
    submissions = request.review_submissions
    for submission in submissions:
        validate_review_submission(ValidateReviewSubmissionRequest(
            evaluation_package=package,
            review_submission=submission,
        ))
    selected = set(request.selected_feedback_items)
    requirements_by_id = {item.id: item for item in package.machine_requirements}
    revisions: list[RevisionRecord] = []
    feedback_items: list[dict[str, Any]] = []
    proposal_sources: dict[str, list[tuple[str, str, Any]]] = {}
    for requirement_id, requirement in requirements_by_id.items():
        proposals = [
            (submission.id, submission.reviewer_id, review)
            for submission in submissions
            for review in submission.reviews
            if review.requirement_id == requirement_id and review.proposed_statement
            and (
                not selected
                or requirement_id in selected
                or selected.intersection(review.feedback_categories)
            )
        ]
        if not proposals:
            continue
        proposals.sort(key=lambda item: (item[1], item[0]))
        proposal_sources[requirement_id] = proposals
        feedback_items.append({
            'requirement_id': requirement_id,
            'original_statement': requirement.machine_original_statement or requirement.normalized_statement,
            'proposed_statements': [review.proposed_statement for _, _, review in proposals if review.proposed_statement],
            'comments': [
                {'reviewer_id': reviewer_id, 'comment': review.comment}
                for _, reviewer_id, review in proposals if review.comment
            ],
            'feedback_categories': sorted({
                category for _, _, review in proposals for category in review.feedback_categories
            }),
        })

    revision_warnings: list[str] = []
    client = None
    if feedback_items:
        try:
            client = create_client(LLMConfig.from_env())
        except LLMError as exc:
            revision_warnings.append(
                f'Revision LLM unavailable; selected human proposed statements were retained without agent rewriting: {exc}'
            )
    suggestions, performed_by = propose_revisions(feedback_items, client)
    for feedback in feedback_items:
        requirement_id = feedback['requirement_id']
        proposed_statement = suggestions.get(requirement_id)
        if not proposed_statement:
            revision_warnings.append(f'No controlled revision proposal was produced for {requirement_id}.')
            continue
        requirement = requirements_by_id[requirement_id]
        proposals = proposal_sources[requirement_id]
        revisions.append(RevisionRecord(
            id=stable_id('rev', package.id, requirement_id, proposed_statement),
            requirement_id=requirement_id,
            original_statement=requirement.machine_original_statement or requirement.normalized_statement or requirement.id,
            proposed_statement=proposed_statement,
            feedback_categories=feedback['feedback_categories'],
            source_review_submission_ids=sorted({submission_id for submission_id, _, _ in proposals}),
            expert_comments=feedback['comments'],
            performed_by=performed_by,
            created_at=utc_now(),
        ))

    expert_added = [
        expert_added_requirement(proposal, package)
        for proposal in aggregation.missing_requirement_proposals
    ]
    unique_expert_added = {item.id: item for item in expert_added}
    return RevisionResponse(
        evaluation_package_id=package.id,
        revisions=revisions,
        expert_added_requirements=sorted(unique_expert_added.values(), key=lambda item: item.id),
        warnings=revision_warnings,
    )


def finalize_consensus(request: FinalizeConsensusRequest) -> ValidatedRequirementBaseline:
    package = request.evaluation_package
    aggregation = request.aggregation
    validate_evaluation_package(package)
    validate_aggregation(package, aggregation)
    assert_study_transition('consensus_validation', 'validated')
    if not aggregation.complete:
        raise ValueError('Consensus validation requires a complete independent review aggregation.')
    decisions = request.consensus_decisions
    decision_ids = [decision.requirement_id for decision in decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise ValueError('Consensus contains duplicate decisions for one requirement.')
    machine_by_id = {item.id: item for item in package.machine_requirements}
    expert_added_by_id = {
        item.id: item
        for item in (request.revision_response.expert_added_requirements if request.revision_response else [])
    }
    unknown = set(decision_ids) - set(machine_by_id) - set(expert_added_by_id)
    if unknown:
        raise ValueError(f"Consensus references unknown requirement ids: {', '.join(sorted(unknown))}")
    missing_machine = set(machine_by_id) - set(decision_ids)
    if missing_machine:
        raise ValueError(f"Every frozen machine requirement needs a consensus decision: {', '.join(sorted(missing_machine))}")
    reviewer_ids = set(aggregation.reviewer_ids)
    revision_by_id = {
        revision.id: revision
        for revision in (request.revision_response.revisions if request.revision_response else [])
    }
    baseline: list[CandidateRequirement] = []
    for decision in decisions:
        if not decision.participant_reviewer_ids:
            raise ValueError(f'Consensus decision for {decision.requirement_id} has no participating human reviewers.')
        if not set(decision.participant_reviewer_ids).issubset(reviewer_ids):
            raise ValueError(f'Consensus decision for {decision.requirement_id} names a reviewer outside the panel.')
        if decision.decision not in {'accepted', 'accepted_with_revision'}:
            continue
        original = machine_by_id.get(decision.requirement_id) or expert_added_by_id[decision.requirement_id]
        requirement = original.model_copy(deep=True)
        requirement.status = 'approved'
        requirement.formal_consensus_decision = decision.decision
        if decision.decision == 'accepted_with_revision':
            revision = revision_by_id.get(decision.revision_record_id or '')
            if revision is None and original.id in machine_by_id:
                raise ValueError(f'Accepted-with-revision decision for {original.id} must reference a RevisionRecord.')
            statement = decision.final_statement or (revision.proposed_statement if revision else None)
            if not statement:
                raise ValueError(f'Accepted-with-revision decision for {original.id} needs final wording.')
            requirement.machine_original_statement = (
                original.machine_original_statement or original.normalized_statement or original.id
            ) if original.id in machine_by_id else None
            requirement.normalized_statement = statement
            requirement.description = statement
            if requirement.origin_kind != 'expert_added':
                requirement.origin_kind = 'human_guided_revision'
        baseline.append(requirement)
    return ValidatedRequirementBaseline(
        evaluation_package_id=package.id,
        evaluation_package_hash=package.package_hash,
        requirements=sorted(baseline, key=lambda item: item.id),
        consensus_decisions=decisions,
        original_machine_requirement_ids=[item.id for item in package.machine_requirements],
    )


def expert_added_requirement(proposal: MissingRequirementProposal, package: EvaluationPackage) -> CandidateRequirement:
    evidence_by_id = {unit.id: unit for unit in package.evidence_units}
    evidence = [
        SourceEvidence(
            evidence_unit_id=unit.id,
            source_id=unit.source_id,
            artifact_name=unit.artifact_name,
            artifact_kind=unit.artifact_kind,
            locator=unit.locator,
            evidence_text=unit.content,
            extracted_facts=unit.extracted_facts,
        )
        for evidence_id in proposal.evidence_unit_ids
        if (unit := evidence_by_id.get(evidence_id)) is not None
    ]
    return CandidateRequirement(
        id=stable_id('req', 'expert-added', package.id, proposal.id, proposal.statement),
        raw_statement=proposal.statement,
        normalized_statement=proposal.statement,
        description=proposal.statement,
        title=proposal.statement[:100],
        requirement_type=proposal.requirement_type if proposal.requirement_type in {
            'descriptive_metadata', 'semantic_anchor', 'technical_metadata', 'access_policy',
            'quality_provenance', 'lifecycle_context', 'controlled_vocabulary',
            'validation_constraint', 'competency_question', 'unknown',
        } else 'unknown',
        source_evidence=evidence,
        evidence=[item.evidence_text for item in evidence],
        validation_status='needs_review',
        support_level='explicit' if evidence else 'unsupported',
        origin_kind='expert_added',
        status='candidate',
        review_notes=proposal.rationale,
        confidence=0.5,
    )


def validate_aggregation(package: EvaluationPackage, aggregation: ReviewAggregation) -> None:
    if (
        aggregation.evaluation_package_id != package.id
        or aggregation.evaluation_package_hash != package.package_hash
    ):
        raise ValueError('Aggregation does not belong to the supplied frozen evaluation package.')


def package_rating_names() -> tuple[str, ...]:
    return (
        'evidence_fidelity', 'correctness', 'relevance', 'necessity',
        'clarity', 'atomicity', 'reuse_potential', 'extension_necessity',
    )


def exact_agreement(matrix: list[list[str]]) -> float | None:
    complete_rows = [row for row in matrix if row]
    if not complete_rows:
        return None
    return sum(len(set(row)) == 1 for row in complete_rows) / len(complete_rows)


def pairwise_agreement(
    submissions: list[ExpertReviewSubmission],
    requirements: list[CandidateRequirement],
) -> float | None:
    if len(submissions) < 2:
        return None
    agreements: list[float] = []
    requirement_ids = {item.id for item in requirements}
    for left, right in combinations(submissions, 2):
        left_map = {review.requirement_id: review.decision for review in left.reviews}
        right_map = {review.requirement_id: review.decision for review in right.reviews}
        common = sorted(requirement_ids & set(left_map) & set(right_map))
        if common:
            agreements.append(sum(left_map[item] == right_map[item] for item in common) / len(common))
    return mean(agreements) if agreements else None


def fleiss_kappa(matrix: list[list[str]]) -> float | None:
    if not matrix or not matrix[0] or any(len(row) != len(matrix[0]) for row in matrix):
        return None
    raters = len(matrix[0])
    if raters < 2:
        return None
    categories = sorted({value for row in matrix for value in row})
    if not categories:
        return None
    proportions = {
        category: sum(row.count(category) for row in matrix) / (len(matrix) * raters)
        for category in categories
    }
    observed_per_item = [
        (sum(count * count for count in Counter(row).values()) - raters) / (raters * (raters - 1))
        for row in matrix
    ]
    observed = mean(observed_per_item)
    expected = sum(value * value for value in proportions.values())
    if expected == 1:
        return 1.0 if observed == 1 else None
    return (observed - expected) / (1 - expected)


def percentage(numerator: int, denominator: int) -> float:
    return round((100 * numerator / denominator), 2) if denominator else 0.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')
