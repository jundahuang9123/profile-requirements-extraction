from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ArtifactKind = Literal[
    'text',
    'ifc',
    'aas-json',
    'aas-xml',
    'aasx',
    'dcat-rdf',
    'profile-spec',
    'use-case',
    'unknown',
]

RequirementType = Literal[
    'descriptive_metadata',
    'semantic_anchor',
    'technical_metadata',
    'access_policy',
    'quality_provenance',
    'lifecycle_context',
    'controlled_vocabulary',
    'validation_constraint',
    'competency_question',
    'unknown',
]

ResourceType = Literal['Catalog', 'Dataset', 'Distribution', 'DataService', 'Agent', 'Concept', 'Unknown']
ValueKind = Literal['literal', 'uri', 'controlled_concept', 'class_reference', 'date', 'agent', 'distribution', 'unknown']
ObligationHint = Literal['mandatory', 'recommended', 'optional', 'unknown']
ReviewStatus = Literal['candidate', 'approved', 'rejected', 'merged', 'needs_review']
ValidationStatus = Literal['valid', 'missing_evidence', 'invalid_schema', 'unknown_term', 'resource_mismatch', 'needs_review']
RequirementScope = Literal[
    'profile_element',
    'obligation_level',
    'controlled_vocabulary',
    'validation_constraint',
    'documentation_guidance',
    'example_requirement',
    'unknown',
]
FairDimension = Literal['F', 'A', 'I', 'R']
ExtractionStrategy = Literal['rules', 'llm', 'hybrid', 'multi_agent']
UserTaskKind = Literal['competency_question', 'user_task', 'stakeholder_need']
StudyMode = Literal['formative', 'summative']
EvidenceSupportLevel = Literal['explicit', 'evidence_supported_inference', 'unsupported']
StudyPhase = Literal[
    'development',
    'formative_review',
    'workflow_frozen',
    'summative_review_open',
    'summative_review_closed',
    'post_evaluation_revision',
    'consensus_validation',
    'validated',
]
ReviewDecision = Literal['accept', 'accept_with_revision', 'reject', 'out_of_scope', 'cannot_assess']

# RQ2: profile change proposal types.
ProfileChangeType = Literal[
    'reuse_property',
    'specialize_property',
    'create_extension_property',
    'create_profile_class',
    'add_constraint',
    'add_usage_note',
    'add_controlled_vocabulary',
]
ProfileChangeReviewStatus = Literal['candidate', 'accepted', 'rejected', 'needs_review']
ObligationLevel = Literal['mandatory', 'recommended', 'optional', 'unknown']

# RQ2 minimal-profile selection mode.
#  - ``minimal``      one primary profile action per approved requirement (default);
#                     candidate terms are ranked and only the best reusable one is
#                     selected. This keeps the generated application profile minimal.
#  - ``exploratory``  every candidate term/action becomes a ProfileChange (debugging
#                     / full-recall view); nothing is filtered away.
ProfileGenerationMode = Literal['minimal', 'exploratory']


class ArtifactPayload(BaseModel):
    name: str = 'artifact'
    media_type: str | None = None
    content: str
    content_encoding: Literal['text', 'base64'] = 'text'


class UserTask(BaseModel):
    """A predefined competency question, corpus-derived task, or declared need.

    Requirements link back to user tasks via ``supports_user_tasks`` so that
    competency-question coverage can be computed during evaluation (RQ1).
    """

    id: str
    statement: str
    kind: UserTaskKind = 'competency_question'
    stakeholder: str | None = None
    source: str = 'predefined input corpus'


class AgentRoleConfig(BaseModel):
    id: str
    label: str
    phase: Literal['extraction', 'consolidation', 'criticism', 'revision']
    panel_order: int
    purpose: str
    focus_questions: list[str] = Field(default_factory=list)
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    prompt_version: str
    enabled: bool = True
    max_output_tokens: int | None = None


class AgentContextInput(BaseModel):
    """User-declared, role-specific context supplied in addition to the frozen corpus.

    Background and free-form RAG material are analytical aids, not evidence.  An
    uploaded artifact can be selected for retrieval, but a requirement may cite it
    only through its normal corpus ``EvidenceUnit`` identifier.
    """

    role_id: str
    background: str = Field(default='', max_length=20_000)
    rag_queries: list[str] = Field(default_factory=list, max_length=24)
    rag_artifact_names: list[str] = Field(default_factory=list, max_length=64)
    rag_material: str = Field(default='', max_length=100_000)
    rag_top_k: int = Field(default=6, ge=1, le=20)


class RetrievedContextItem(BaseModel):
    id: str
    source_kind: Literal['corpus_artifact', 'supplemental_material']
    source_ref: str
    content: str
    content_hash: str
    score: float = 0.0
    evidence_unit_id: str | None = None
    eligible_as_evidence: bool = False


class AgentContextTrace(BaseModel):
    role_id: str
    context_hash: str
    background: str = ''
    background_hash: str | None = None
    rag_queries: list[str] = Field(default_factory=list)
    requested_rag_artifact_names: list[str] = Field(default_factory=list)
    shared_evidence_unit_ids: list[str] = Field(default_factory=list)
    retrieved_items: list[RetrievedContextItem] = Field(default_factory=list)
    boundary_notice: str = (
        'Supplemental background and RAG material guide analysis but do not independently substantiate '
        'requirements; only verified corpus evidence may be cited.'
    )


class WorkflowTraceEvent(BaseModel):
    id: str
    sequence: int
    event_type: Literal['context_assembled', 'cache_reused', 'run_completed', 'run_failed', 'run_skipped']
    phase: str
    role_id: str
    agent_run_id: str
    timestamp: str | None = None
    dependency_role_ids: list[str] = Field(default_factory=list)
    input_artifact_ids: list[str] = Field(default_factory=list)
    output_artifact_ids: list[str] = Field(default_factory=list)
    context_hash: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AgentRunRecord(BaseModel):
    id: str
    role_id: str
    phase: str
    status: Literal['pending', 'running', 'completed', 'failed', 'skipped']
    model_id: str | None = None
    prompt_version: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    candidate_requirement_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    cache_hit: bool = False
    dependency_role_ids: list[str] = Field(default_factory=list)
    input_artifact_ids: list[str] = Field(default_factory=list)
    output_artifact_ids: list[str] = Field(default_factory=list)
    context_trace: AgentContextTrace | None = None


class AgentContribution(BaseModel):
    agent_run_id: str
    role_id: str
    source_candidate_id: str
    contribution_kind: Literal['originated', 'supported', 'merged', 'challenged', 'revised']
    statement: str | None = None
    evidence_unit_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ConsolidationEvent(BaseModel):
    id: str
    source_candidate_ids: list[str]
    consolidated_requirement_id: str | None = None
    action: Literal['merge', 'keep_separate', 'discard_unsupported', 'flag_conflict']
    rationale: str
    performed_by: str
    created_at: str


class CritiqueFinding(BaseModel):
    id: str
    requirement_id: str
    critic_role_id: str
    category: Literal[
        'grounding',
        'scope',
        'atomicity',
        'obligation',
        'duplicate',
        'conflict',
        'reuse',
        'minimality',
        'resource_compatibility',
        'other',
    ]
    severity: Literal['info', 'warning', 'blocking']
    message: str
    evidence_unit_ids: list[str] = Field(default_factory=list)
    suggested_action: str | None = None


class ExtractionProvenance(BaseModel):
    """Records how a requirement candidate was produced, for reproducibility.

    ``editor_history`` accumulates human corrections (field, old value, new
    value) so that expert editing effort can be measured (H1 / Section 6.2).
    """

    strategy: ExtractionStrategy = 'rules'
    extractor: str = 'rule-based-v1'
    model_id: str | None = None
    prompt_version: str | None = None
    created_at: str | None = None
    evidence_verified: bool | None = None
    notes: list[str] = Field(default_factory=list)
    editor_history: list[dict[str, Any]] = Field(default_factory=list)
    workflow_id: str | None = None
    workflow_version: str | None = None
    agent_run_id: str | None = None
    agent_role: str | None = None
    agent_phase: str | None = None
    input_hash: str | None = None
    source_candidate_ids: list[str] = Field(default_factory=list)


class AnalysisRequest(BaseModel):
    source_corpus_id: str | None = None
    text: str | None = None
    artifacts: list[ArtifactPayload] = Field(default_factory=list)
    user_tasks: list[UserTask] = Field(default_factory=list)
    strategy: ExtractionStrategy = 'rules'
    llm_model: str | None = None
    cq_guided: bool = True
    study_mode: StudyMode = 'formative'
    study_phase: StudyPhase = 'development'
    agent_role_ids: list[str] = Field(default_factory=list)
    panel_preset: str = 'full_15'
    workflow_version: str | None = None
    rerun_role_ids: list[str] = Field(default_factory=list)
    agent_contexts: list[AgentContextInput] = Field(default_factory=list)

    @model_validator(mode='after')
    def agent_context_role_ids_are_unique(self) -> 'AnalysisRequest':
        role_ids = [context.role_id for context in self.agent_contexts]
        if len(role_ids) != len(set(role_ids)):
            raise ValueError('agent_contexts may contain at most one context package per role_id')
        return self


class ArtifactSummary(BaseModel):
    name: str
    kind: str
    evidence_count: int = 0
    notes: list[str] = Field(default_factory=list)


class EvidenceUnit(BaseModel):
    id: str
    source_id: str
    artifact_name: str
    artifact_kind: ArtifactKind = 'unknown'
    locator: str | None = None
    content: str
    extracted_facts: list[str] = Field(default_factory=list)
    confidence: float = 0.7


class SourceEvidence(BaseModel):
    evidence_unit_id: str
    source_id: str
    artifact_name: str
    artifact_kind: str
    locator: str | None = None
    evidence_text: str
    extracted_facts: list[str] = Field(default_factory=list)


class NormalizedIntent(BaseModel):
    resource_type: ResourceType = 'Dataset'
    metadata_need: str = 'describe dataset for discovery'
    value_kind: ValueKind = 'unknown'
    obligation_hint: ObligationHint = 'unknown'


class ConstraintHint(BaseModel):
    """Structured constraint hint for RQ2 profile generation (RQ1 -> RQ2 handoff)."""

    cardinality: str | None = None  # e.g. '0..n', '1..1', '0..1', '1..n'
    value_kind: ValueKind = 'unknown'
    datatype_or_class: str | None = None
    obligation: ObligationHint = 'unknown'


class CandidateMetadataAction(BaseModel):
    """Proposed profile-design action - the primary RQ1 -> RQ2 handoff object."""

    action: Literal[
        'reuse_existing_term',
        'specialize_existing_term',
        'create_extension',
        'add_constraint',
        'add_usage_note',
        'no_action',
    ]
    target_class: str | None = None
    candidate_terms: list[str] = Field(default_factory=list)
    rationale: str
    constraint_hint: ConstraintHint | None = None
    source_requirement_id: str | None = None


class SemanticCandidate(BaseModel):
    id: str
    label: str
    kind: str
    identifier: str | None = None
    source: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float = 0.6


class ExtractedAttribute(BaseModel):
    id: str
    source: str
    path: str
    label: str
    value: str
    category: str
    value_type: str = 'string'
    confidence: float = 0.7


class MetadataCandidate(BaseModel):
    id: str
    property: str
    label: str
    category: str
    range: str = 'string'
    requirement_level: Literal['mandatory', 'recommended', 'optional'] = 'recommended'
    source: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float = 0.6


class CandidateRequirement(BaseModel):
    id: str

    raw_statement: str | None = None
    normalized_statement: str | None = None
    requirement_type: RequirementType = 'unknown'
    source_evidence: list[SourceEvidence] = Field(default_factory=list)
    normalized_intent: NormalizedIntent = Field(default_factory=NormalizedIntent)
    fair_dimensions: list[FairDimension] = Field(default_factory=list)
    fair_rationale: str | None = None
    candidate_metadata_actions: list[CandidateMetadataAction] = Field(default_factory=list)
    supports_user_tasks: list[str] = Field(default_factory=list)
    # When False (default) the requirement contributes ONE primary profile action
    # in minimal mode; its candidate terms are treated as interchangeable
    # suggestions. Set True only when the requirement explicitly mandates several
    # distinct profile elements (then minimal mode keeps the best term per slot).
    requires_multiple_elements: bool = False
    validation_evidence: list[str] = Field(default_factory=list)
    validation_status: ValidationStatus = 'needs_review'
    requirement_scope: RequirementScope = 'unknown'
    provenance: ExtractionProvenance | None = None
    status: ReviewStatus = 'candidate'
    review_notes: str | None = None
    merged_from: list[str] = Field(default_factory=list)
    support_level: EvidenceSupportLevel = 'explicit'
    origin_kind: Literal[
        'rule_extracted',
        'single_llm_extracted',
        'agent_extracted',
        'agent_consolidated',
        'expert_added',
        'human_guided_revision',
    ] | None = None
    origin_agent_role: str | None = None
    contributing_agent_roles: list[str] = Field(default_factory=list)
    agent_contributions: list[AgentContribution] = Field(default_factory=list)
    consolidated_from: list[str] = Field(default_factory=list)
    critique_finding_ids: list[str] = Field(default_factory=list)
    machine_output_frozen: bool = False
    machine_original_statement: str | None = None
    formal_consensus_decision: Literal['accepted', 'accepted_with_revision', 'rejected', 'out_of_scope', 'merged', 'split'] | None = None

    # Backward-compatible fields used by earlier recommendation/UI code.
    title: str | None = None
    description: str | None = None
    category: str | None = None
    source: str | None = None
    evidence: list[str] = Field(default_factory=list)
    confidence: float = 0.6


class DuplicateGroup(BaseModel):
    id: str
    requirement_ids: list[str]
    suggested_merged_statement: str
    reason: str
    confidence: float = 0.7


class CompetencyQuestion(BaseModel):
    id: str
    question: str
    category: str
    source: str
    evidence: str | None = None


class AnalysisResponse(BaseModel):
    strategy: ExtractionStrategy = 'rules'
    study_setup: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[ArtifactSummary] = Field(default_factory=list)
    evidence_units: list[EvidenceUnit] = Field(default_factory=list)
    extracted_attributes: list[ExtractedAttribute] = Field(default_factory=list)
    requirements: list[CandidateRequirement] = Field(default_factory=list)
    duplicate_groups: list[DuplicateGroup] = Field(default_factory=list)
    semantic_candidates: list[SemanticCandidate] = Field(default_factory=list)
    metadata_candidates: list[MetadataCandidate] = Field(default_factory=list)
    competency_questions: list[CompetencyQuestion] = Field(default_factory=list)
    user_tasks: list[UserTask] = Field(default_factory=list)
    funnel_metrics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    workflow_id: str | None = None
    workflow_version: str | None = None
    study_mode: str | None = None
    study_phase: StudyPhase | None = None
    input_hash: str | None = None
    panel_preset: str | None = None
    panel_status: Literal['completed', 'incomplete_full_panel', 'not_applicable'] | None = None
    extraction_agent_count: int = 0
    synthesis_agent_count: int = 0
    total_agent_count: int = 0
    agent_runs: list[AgentRunRecord] = Field(default_factory=list)
    raw_agent_requirements: list[CandidateRequirement] = Field(default_factory=list)
    consolidation_events: list[ConsolidationEvent] = Field(default_factory=list)
    critique_findings: list[CritiqueFinding] = Field(default_factory=list)
    agent_contexts: list[AgentContextTrace] = Field(default_factory=list)
    workflow_trace: list[WorkflowTraceEvent] = Field(default_factory=list)


class ExpertCriterionRatings(BaseModel):
    evidence_fidelity: int | None = None
    correctness: int | None = None
    relevance: int | None = None
    necessity: int | None = None
    clarity: int | None = None
    atomicity: int | None = None
    reuse_potential: int | None = None
    extension_necessity: int | None = None

    @field_validator('*')
    @classmethod
    def ratings_are_one_to_five(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= 5:
            raise ValueError('criterion ratings must be integers from 1 to 5')
        return value


class ExpertRequirementReview(BaseModel):
    requirement_id: str
    decision: ReviewDecision
    ratings: ExpertCriterionRatings = Field(default_factory=ExpertCriterionRatings)
    comment: str | None = None
    proposed_statement: str | None = None
    feedback_categories: list[str] = Field(default_factory=list)
    proposed_merge_with: list[str] = Field(default_factory=list)
    proposed_split_statements: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def revision_requires_explanation(self) -> 'ExpertRequirementReview':
        if self.decision == 'accept_with_revision' and not (self.proposed_statement or self.comment):
            raise ValueError('accept_with_revision requires a proposed statement or explanatory comment')
        return self


class MissingRequirementProposal(BaseModel):
    id: str
    statement: str
    rationale: str
    evidence_unit_ids: list[str] = Field(default_factory=list)
    requirement_type: str | None = None


class ExpertReviewSubmission(BaseModel):
    schema_version: Literal['rq1-expert-review-v1'] = 'rq1-expert-review-v1'
    id: str
    evaluation_package_id: str
    evaluation_package_hash: str
    reviewer_id: str
    started_at: str
    completed_at: str | None = None
    reviews: list[ExpertRequirementReview]
    missing_requirements: list[MissingRequirementProposal] = Field(default_factory=list)
    submission_hash: str

    @model_validator(mode='after')
    def reviewer_has_one_decision_per_requirement(self) -> 'ExpertReviewSubmission':
        ids = [review.requirement_id for review in self.reviews]
        if len(ids) != len(set(ids)):
            raise ValueError('a reviewer submission contains duplicate reviews for one requirement')
        if not self.reviewer_id.strip():
            raise ValueError('reviewer_id must be a non-empty pseudonymous identifier')
        return self


class EvaluationPackage(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal['rq1-evaluation-package-v1'] = 'rq1-evaluation-package-v1'
    id: str
    created_at: str
    target_reviewer_count: int = 3
    study_phase: Literal['workflow_frozen', 'summative_review_open'] = 'workflow_frozen'
    source_corpus_id: str | None = None
    input_hash: str
    workflow_version: str
    strategy_used: str
    model_configuration: dict[str, Any] = Field(default_factory=dict)
    role_configuration: list[AgentRoleConfig] = Field(default_factory=list)
    agent_runs: list[AgentRunRecord] = Field(default_factory=list)
    agent_contexts: list[AgentContextTrace] = Field(default_factory=list)
    workflow_trace: list[WorkflowTraceEvent] = Field(default_factory=list)
    evidence_units: list[EvidenceUnit] = Field(default_factory=list)
    user_tasks: list[UserTask] = Field(default_factory=list)
    raw_agent_requirements: list[CandidateRequirement] = Field(default_factory=list)
    machine_requirements: list[CandidateRequirement] = Field(default_factory=list)
    consolidation_events: list[ConsolidationEvent] = Field(default_factory=list)
    critique_findings: list[CritiqueFinding] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    package_hash: str


class RequirementReviewAggregate(BaseModel):
    requirement_id: str
    reviewer_count: int
    decisions: dict[str, int] = Field(default_factory=dict)
    unanimous: bool
    majority_decision: str | None = None
    disagreement: bool
    median_ratings: dict[str, float | None] = Field(default_factory=dict)
    comments: list[dict[str, Any]] = Field(default_factory=list)


class ReviewAggregation(BaseModel):
    schema_version: Literal['rq1-review-aggregation-v1'] = 'rq1-review-aggregation-v1'
    evaluation_package_id: str
    evaluation_package_hash: str
    reviewer_ids: list[str]
    expected_reviewer_count: int
    complete: bool
    requirement_aggregates: list[RequirementReviewAggregate] = Field(default_factory=list)
    missing_requirement_proposals: list[MissingRequirementProposal] = Field(default_factory=list)
    summary_metrics: dict[str, Any] = Field(default_factory=dict)


class RevisionRecord(BaseModel):
    id: str
    requirement_id: str
    original_statement: str
    proposed_statement: str
    feedback_categories: list[str] = Field(default_factory=list)
    source_review_submission_ids: list[str] = Field(default_factory=list)
    expert_comments: list[dict[str, str]] = Field(default_factory=list)
    performed_by: str
    created_at: str


class ConsensusDecision(BaseModel):
    requirement_id: str
    decision: Literal['accepted', 'accepted_with_revision', 'rejected', 'out_of_scope', 'merged', 'split']
    final_statement: str | None = None
    rationale: str
    participant_reviewer_ids: list[str] = Field(default_factory=list)
    revision_record_id: str | None = None
    decided_at: str


class FreezeEvaluationPackageRequest(BaseModel):
    analysis: AnalysisResponse
    target_reviewer_count: int = 3
    include_requirement_ids: list[str] = Field(default_factory=list)


class ValidateReviewSubmissionRequest(BaseModel):
    evaluation_package: EvaluationPackage
    review_submission: ExpertReviewSubmission


class AggregateExpertReviewsRequest(BaseModel):
    evaluation_package: EvaluationPackage
    review_submissions: list[ExpertReviewSubmission]


class ReviseAfterEvaluationRequest(BaseModel):
    evaluation_package: EvaluationPackage
    aggregation: ReviewAggregation
    review_submissions: list[ExpertReviewSubmission] = Field(default_factory=list)
    selected_feedback_items: list[str] = Field(default_factory=list)
    study_phase: Literal['summative_review_closed', 'post_evaluation_revision'] = 'summative_review_closed'


class RevisionResponse(BaseModel):
    schema_version: Literal['rq1-post-evaluation-revision-v1'] = 'rq1-post-evaluation-revision-v1'
    evaluation_package_id: str
    study_phase: Literal['post_evaluation_revision'] = 'post_evaluation_revision'
    revisions: list[RevisionRecord] = Field(default_factory=list)
    expert_added_requirements: list[CandidateRequirement] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FinalizeConsensusRequest(BaseModel):
    evaluation_package: EvaluationPackage
    aggregation: ReviewAggregation
    revision_response: RevisionResponse | None = None
    consensus_decisions: list[ConsensusDecision]
    study_phase: Literal['consensus_validation'] = 'consensus_validation'


class ValidatedRequirementBaseline(BaseModel):
    schema_version: Literal['rq1-validated-requirement-baseline-v1'] = 'rq1-validated-requirement-baseline-v1'
    evaluation_package_id: str
    evaluation_package_hash: str
    study_phase: Literal['validated'] = 'validated'
    requirements: list[CandidateRequirement] = Field(default_factory=list)
    consensus_decisions: list[ConsensusDecision] = Field(default_factory=list)
    original_machine_requirement_ids: list[str] = Field(default_factory=list)


class RequirementSetSaveRequest(BaseModel):
    name: str
    description: str | None = None
    analysis: AnalysisResponse | None = None
    requirements: list[CandidateRequirement] = Field(default_factory=list)
    user_tasks: list[UserTask] = Field(default_factory=list)


class RequirementSetInfo(BaseModel):
    id: str
    name: str
    description: str | None = None
    created_at: str
    strategy: ExtractionStrategy | None = None
    requirement_count: int = 0


class RequirementSet(BaseModel):
    id: str
    name: str
    description: str | None = None
    created_at: str
    strategy: ExtractionStrategy | None = None
    requirements: list[CandidateRequirement] = Field(default_factory=list)
    user_tasks: list[UserTask] = Field(default_factory=list)
    analysis: AnalysisResponse | None = None


class RequirementSetListResponse(BaseModel):
    requirement_sets: list[RequirementSetInfo] = Field(default_factory=list)


class RequirementSetLoadRequest(BaseModel):
    id: str


class RecommendationRequest(BaseModel):
    analysis: AnalysisResponse | None = None
    requirements: list[CandidateRequirement] = Field(default_factory=list)
    semantic_candidates: list[SemanticCandidate] = Field(default_factory=list)
    metadata_candidates: list[MetadataCandidate] = Field(default_factory=list)


class ReuseRecommendation(BaseModel):
    id: str
    label: str
    vocabulary: str
    term_uri: str
    priority: int
    action: Literal['reuse', 'profile', 'extension'] = 'reuse'
    requirement_id: str | None = None
    candidate_id: str | None = None
    rationale: str
    confidence: float = 0.6


class RecommendationResponse(BaseModel):
    recommendations: list[ReuseRecommendation] = Field(default_factory=list)
    extension_candidates: list[MetadataCandidate] = Field(default_factory=list)


class ConstraintGenerationRequest(BaseModel):
    analysis: AnalysisResponse | None = None
    requirements: list[CandidateRequirement] = Field(default_factory=list)
    recommendations: list[ReuseRecommendation] = Field(default_factory=list)
    selected_recommendation_ids: list[str] = Field(default_factory=list)


class ConstraintGenerationResponse(BaseModel):
    shacl: str
    profile_draft: dict[str, Any]
    validation_notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# RQ2: profile change proposals and profile generation
# ---------------------------------------------------------------------------

RQ2_SCHEMA_VERSION = 'rq2-profile-generation-package-v1'


class ProfileChange(BaseModel):
    """A single reviewable profile change proposal derived from an approved requirement."""

    id: str
    requirement_id: str
    change_type: ProfileChangeType
    target_class: str  # prefixed base class, e.g. dcat:Dataset
    term_uri: str | None = None
    slot_name: str | None = None
    class_name: str | None = None
    range: str | None = None
    required: bool | None = None
    multivalued: bool | None = None
    obligation_level: ObligationLevel = 'unknown'
    rationale: str = ''
    source_vocabulary: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    source_requirement_ids: list[str] = Field(default_factory=list)
    review_status: ProfileChangeReviewStatus = 'candidate'
    # True when this change is part of the minimal selection. In exploratory mode
    # every candidate term yields a change; the one that minimal mode would have
    # picked is flagged ``selected=True`` so the UI can distinguish primary actions
    # from the additional exploratory suggestions.
    selected: bool = True
    # Other candidate terms that were discovered for the same slot/requirement but
    # not chosen as the primary action. Surfaced as suggestions, not review items.
    alternative_terms: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProfileChangeSet(BaseModel):
    id: str
    source_requirement_set_id: str | None = None
    created_at: str = ''
    profile_base: str = 'DCAT-AP'
    profile_namespace: str = 'https://w3id.org/cx#'
    profile_prefix: str = 'cx'
    mode: ProfileGenerationMode = 'minimal'
    changes: list[ProfileChange] = Field(default_factory=list)
    # Every candidate term discovered across the approved requirements, kept as
    # suggestions/evidence (not as items the reviewer must individually validate).
    discovered_candidate_terms: list[str] = Field(default_factory=list)
    review_history: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_metrics: dict[str, Any] = Field(default_factory=dict)


class GenerateProfileChangesRequest(BaseModel):
    requirement_set: RequirementSet | None = None
    requirements: list[CandidateRequirement] = Field(default_factory=list)
    approved_only: bool = True
    # 'minimal' (default) selects one primary, reuse-first action per requirement;
    # 'exploratory' generates every candidate action for debugging / full recall.
    mode: ProfileGenerationMode = 'minimal'
    base_profile: str = 'DCAT-AP'
    profile_namespace: str = 'https://w3id.org/cx#'
    profile_prefix: str = 'cx'
    approval_context: Literal['manual', 'formal_consensus'] = 'manual'


class GenerateProfileDraftRequest(BaseModel):
    profile_change_set: ProfileChangeSet
    base_schema: dict[str, Any] | None = None
    accepted_only: bool = True


class ProfileGenerationResponse(BaseModel):
    profile_change_set: ProfileChangeSet
    profile_draft: dict[str, Any] = Field(default_factory=dict)
    shacl: str = ''
    validation_notes: list[str] = Field(default_factory=list)


class ProvenanceMappingEntry(BaseModel):
    requirement_id: str
    profile_element: str
    change_id: str
    evidence_unit_ids: list[str] = Field(default_factory=list)


class RQ2ExportRequest(BaseModel):
    profile_change_set: ProfileChangeSet
    base_schema: dict[str, Any] | None = None
    source_requirement_set_id: str | None = None
    approved_requirement_count: int | None = None
    accepted_only: bool = True


class RQ2Package(BaseModel):
    schema_version: str = RQ2_SCHEMA_VERSION
    generated_at: str = ''
    base_profile: str = 'DCAT-AP'
    source_requirement_set_id: str | None = None
    approved_requirement_count: int = 0
    profile_change_set: ProfileChangeSet
    profile_draft_linkml: dict[str, Any] = Field(default_factory=dict)
    shacl: str = ''
    provenance_mapping: list[ProvenanceMappingEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    validation_notes: list[str] = Field(default_factory=list)
