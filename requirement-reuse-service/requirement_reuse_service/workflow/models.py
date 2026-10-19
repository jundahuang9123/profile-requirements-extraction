from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import ArtifactPayload, NormalizedIntent as LegacyIntent, RequirementType, UserTask
from ..llm.step_models import ModelID, StepName

WORKFLOW_VERSION = 'rq1-nine-stage-v2'
SCHEMA_VERSION = 'rq1-requirement-dataset-v2'
ELICITATION_POLICY_VERSION = 'rq1-independent-elicitation-v3.3'
NEEDS_ELICITATION_POLICY = 'rq1-independent-elicitation-v3.3'
NEEDS_NORMALIZATION_POLICY = 'rq1-need-normalization-v1'
NORMALIZATION_POLICY_VERSION = 'rq1-normalization-v3'
ExtensionKind = Literal['new_information_need', 'stricter_obligation', 'value_constraint',
                        'new_class_or_relation', 'not_an_extension']
WorkflowResourceType = Literal['Catalog', 'CatalogRecord', 'Dataset', 'DatasetSeries',
    'Distribution', 'DataService', 'Agent', 'Concept', 'ConceptScheme', 'Resource',
    'Relationship', 'Role', 'PeriodOfTime', 'Location', 'Checksum', 'Identifier',
    'LicenseDocument', 'Unknown']
STAGES = ['acquisition', 'decomposition', 'role_selection', 'elicitation', 'normalization',
          'verification', 'consolidation', 'deliberation', 'adjudication', 'baseline']


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class NormalizedIntent(LegacyIntent):
    """V2 never supplies an unstated Dataset scope or discovery need."""
    model_config = ConfigDict(extra='forbid')
    resource_type: WorkflowResourceType = 'Unknown'
    metadata_need: str = ''


class TextSelector(Contract):
    kind: Literal['text'] = 'text'
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    representation_hash: str
    page: int | None = None


class JSONSelector(Contract):
    kind: Literal['json'] = 'json'
    pointer: str
    value_hash: str


class XMLSelector(Contract):
    kind: Literal['xml'] = 'xml'
    child_indices: list[int]
    tag: str
    value_hash: str


class RDFSelector(Contract):
    kind: Literal['rdf'] = 'rdf'
    quads: list[str]
    canonicalization: Literal['URDNA2015'] = 'URDNA2015'


class IFCSelector(Contract):
    kind: Literal['ifc'] = 'ifc'
    step_id: int
    global_id: str | None = None
    entity_type: str
    property_step_id: int | None = None
    relationship_ids: list[int] = Field(default_factory=list)
    attribute: str | None = None
    value_hash: str


Selector = Annotated[TextSelector | JSONSelector | XMLSelector | RDFSelector | IFCSelector,
                     Field(discriminator='kind')]


class SourceRequest(Contract):
    artifact: ArtifactPayload
    source_id: str | None = None
    source_role: Literal['normative_spec', 'stakeholder_need', 'example', 'observation', 'background', 'evaluation_reference'] = 'observation'
    authority: str = ''
    origin_uri: str | None = None


class SourceArtifact(Contract):
    source_id: str
    source_version_id: str
    name: str
    media_type: str | None = None
    source_role: str
    authority: str = ''
    origin_uri: str | None = None
    raw_sha256: str
    byte_length: int
    raw_base64: str
    artifact_kind: str
    parser_version: str
    parser_dependencies: dict[str, str] = Field(default_factory=dict)
    parse_status: Literal['parsed', 'failed', 'unsupported']
    diagnostics: list[str] = Field(default_factory=list)
    representation: str = ''
    representation_hash: str = ''
    parent_source_version_id: str | None = None
    package_entry_path: str | None = None
    child_source_version_ids: list[str] = Field(default_factory=list)
    acquired_at: str


class EvidenceUnit(Contract):
    evidence_id: str
    source_id: str
    source_version_id: str
    kind: str
    selector: Selector
    content: str
    content_hash: str
    structural_context: dict[str, Any] = Field(default_factory=dict)
    source_claim_kind: str
    parser_version: str


class UseCaseInput(Contract):
    file: str
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class SnapshotRequest(Contract):
    source_version_ids: list[str] = Field(min_length=1)
    user_tasks: list[UserTask] = Field(default_factory=list)
    name: str = 'Research corpus'
    use_case_input: UseCaseInput | None = None


class CorpusSnapshot(Contract):
    use_case_input: UseCaseInput | None = None
    snapshot_id: str
    name: str
    source_version_ids: list[str]
    evidence_ids: list[str]
    user_tasks: list[UserTask]
    manifest_hash: str
    exclusions: list[dict[str, str]] = Field(default_factory=list)
    created_at: str


class EvidenceLink(Contract):
    evidence_id: str
    quote: str
    relation: Literal['supports', 'contradicts', 'contextualizes'] = 'supports'
    component: Literal['statement', 'obligation', 'scope', 'condition', 'value_kind'] = 'statement'
    quote_start: int | None = Field(default=None, ge=0)


class RQ2Hint(Contract):
    term: str = Field(min_length=1)
    kind: Literal['vocabulary_term', 'code_list', 'standard', 'other']
    origin: Literal['proposal', 'evidence']
    evidence_id: str | None = None
    revision_id: str | None = None


class TaskJustification(Contract):
    task_id: str = Field(min_length=1)
    justification: str = Field(min_length=1, max_length=600)


class ObligationAlternative(Contract):
    obligation: Literal['mandatory', 'recommended', 'optional', 'unknown']
    count: int = Field(ge=1)
    revision_ids: list[str] = Field(min_length=1)


class UnbackedObligation(Contract):
    label: Literal['mandatory', 'recommended', 'optional']
    reason: Literal['no_quote', 'quote_does_not_state_it']


class Observation(Contract):
    observation_id: str
    role_id: str
    statement: str
    requirement_type: RequirementType = 'unknown'
    intent: NormalizedIntent = Field(default_factory=lambda: NormalizedIntent(resource_type='Unknown'))
    scope: str = 'Unspecified'
    evidence_links: list[EvidenceLink]
    rationale: str = ''
    assumptions: list[str] = Field(default_factory=list)
    supports_user_tasks: list[str] = Field(default_factory=list)
    support_level: Literal['explicit', 'evidence_supported_inference', 'unsupported'] = 'evidence_supported_inference'
    rq2_hints: list[RQ2Hint] = Field(default_factory=list)
    task_justifications: list[TaskJustification] = Field(default_factory=list)
    # Older frozen extractions have neither field; their raw saved rows stay valid.
    extension_kind: ExtensionKind | None = None
    base_property: str | None = None


class ElicitationResult(Contract):
    observations: list[Observation] = Field(default_factory=list)


class SetAside(Contract):
    observation_id: str
    role_id: str
    reason: Literal['no_source_link', 'inherited_from_base', 'declared_not_extension', 'base_specification_only', 'generic_need_served_by_base', 'no_use_case', 'not_supported_by_quote', 'source_check_failed', 'rewrite_rejected',
                    'not_find_or_access', 'not_catalogue_level', 'not_commonly_agreed'] = 'no_source_link'
    base_check: dict[str, Any] | None = None
    revision_id: str | None = None
    need_id: str | None = None
    rationale: str = ''
    matched_base_need_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    restored: bool = False


class CandidateGroup(Contract):
    member_ids: list[str] = Field(min_length=1, max_length=40)
    join_group_id: str | None = None
    rationale: str = Field(default='', max_length=240)


class SemanticGrouping(Contract):
    groups: list[CandidateGroup] = Field(default_factory=list, max_length=40)


class SourceSpanLink(Contract):
    source_span_id: str = Field(min_length=1)
    relation: Literal['supports', 'contradicts', 'contextualizes'] = 'supports'
    component: Literal['statement', 'obligation', 'scope', 'condition', 'value_kind'] = 'statement'


class SpanObservation(Observation):
    """Provider-only contract; original quotations are materialized by the server."""
    evidence_links: list[SourceSpanLink] = Field(default_factory=list, max_length=12)
    extension_kind: ExtensionKind = Field(...)
    base_property: str | None = Field(...)


class SpanElicitationResult(Contract):
    observations: list[SpanObservation] = Field(default_factory=list)


class ExtractionTaskJustification(Contract):
    """Untrusted extraction hint; empty reasons are audited and dropped before storage."""
    task_id: str
    justification: str = Field(default='', max_length=600)


class NeedSpanObservation(Contract):
    """Current provider contract: needs and citations, never extension solution labels."""
    observation_id: str
    role_id: str
    statement: str
    requirement_type: RequirementType = 'unknown'
    intent: NormalizedIntent = Field(default_factory=NormalizedIntent)
    scope: str = 'Unspecified'
    evidence_links: list[SourceSpanLink] = Field(default_factory=list, max_length=12)
    rationale: str = ''
    assumptions: list[str] = Field(default_factory=list)
    supports_user_tasks: list[str] = Field(default_factory=list)
    task_justifications: list[ExtractionTaskJustification] = Field(default_factory=list)
    rq2_hints: list[RQ2Hint] = Field(default_factory=list)
    support_level: Literal['explicit', 'evidence_supported_inference', 'unsupported'] = 'evidence_supported_inference'


class NeedSpanElicitationResult(Contract):
    observations: list[NeedSpanObservation] = Field(default_factory=list)


class Finding(Contract):
    criterion: str
    severity: Literal['blocking', 'review', 'info']
    message: str


class Qualification(Contract):
    support: Literal['explicit', 'inferred', 'unsupported', 'contradicted', 'uncertain']
    rationale: str
    findings: list[Finding] = Field(default_factory=list)
    assessor: str
    revision_hash: str = ''


class RequirementRecord(Contract):
    requirement_id: str
    revision_id: str
    revision_number: int
    content_hash: str
    group_id: str | None = None
    base_check: dict[str, Any] | None = None
    base_check_findings: list[Finding] = Field(default_factory=list)
    extension_kind: ExtensionKind | None = None
    base_property: str | None = None
    raw_statement: str
    normalized_statement: str
    requirement_type: RequirementType
    normalized_intent: NormalizedIntent
    scope: str
    evidence_links: list[EvidenceLink]
    assumptions: list[str] = Field(default_factory=list)
    rationale: str = ''
    support_level: str
    supports_user_tasks: list[str] = Field(default_factory=list)
    parent_revision_ids: list[str] = Field(default_factory=list)
    observation_ids: list[str] = Field(default_factory=list)
    contributing_roles: list[str] = Field(default_factory=list)
    lifecycle_state: str = 'verification_pending'
    verification: dict[str, Any] | None = None
    qualification: Qualification | None = None
    conflict_ids: list[str] = Field(default_factory=list)
    decision_id: str | None = None
    rq2_hints: list[RQ2Hint] = Field(default_factory=list)
    need_statement: str | None = None
    obligation_alternatives: list[ObligationAlternative] = Field(default_factory=list)
    unbacked_obligation: UnbackedObligation | None = None
    proposal_support: dict[str, Any] | None = None
    processing_flags: list[str] = Field(default_factory=list)
    task_justifications: list[TaskJustification] = Field(default_factory=list)
    need_class: Literal['generic', 'domain_use_of_base', 'domain'] | None = None
    matched_base_need_ids: list[str] = Field(default_factory=list)
    base_need_matches: list[dict[str, Any]] = Field(default_factory=list)
    # D5 profile-scope judgement of a source-derived need (rq1-profile-scope-v1/v2).
    profile_scope: dict[str, Any] | None = None
    # Base-gap status from versioned full-catalogue search: negative claims are only
    # confirmed after every pinned entry was searched; positive base matches may stop early.
    base_gap: dict[str, Any] | None = None
    dataset_coverage: dict[str, Any] | None = None
    # Linker's necessity annotation per kept use-case link (task ID -> necessary).
    use_case_necessity: dict[str, bool] = Field(default_factory=dict)
    need_condition: str = ''
    need_integrity_hash: str | None = None
    fa_scope: dict[str, Any] | None = None
    rank: int | None = Field(default=None, ge=1)
    rank_keys: dict[str, Any] = Field(default_factory=dict)


class ConflictRecord(Contract):
    conflict_id: str
    revision_ids: list[str]
    kind: str
    rationale: str
    status: Literal['open', 'resolved', 'deferred'] = 'open'
    decision_id: str | None = None


class DeliberationCase(Contract):
    case_id: str
    revision_ids: list[str]
    triggers: list[str]
    context_hash: str
    model: str | None = None
    participants: list[str]
    policy_version: str = 'rq1-selective-v5'
    status: str = 'queued'
    messages: list[dict[str, Any]] = Field(default_factory=list)
    stop_reason: str | None = None
    max_rounds: int = 3
    max_calls: int = 12
    max_output_tokens: int = 4000
    max_retry_output_tokens: int = 8000
    total_output_budget: int = 48000
    max_seconds: int = 300
    output_tokens_reserved: int = 0
    model_attempts: int = 0
    model_seconds: float = 0
    frozen_requirements: list[dict[str, Any]] = Field(default_factory=list)
    mediation: dict[str, Any] | None = None
    discussion_trace: dict[str, Any] = Field(default_factory=dict)


ShortRoleText = Annotated[str, Field(min_length=1, max_length=240)]


class RoleCitation(Contract):
    evidence_id: str
    quote: str = Field(min_length=1, max_length=400, description=(
        'Literal contiguous substring of this evidence unit content. Copy all spaces, line breaks '
        'and hyphens exactly; never join text from separate units.'))
    quote_start: int | None = Field(default=None, ge=0, description=(
        'Zero-based character offset inside the cited unit content. Omit/null for a unique quote; '
        'required only when that exact quote appears more than once.'))


class RoleCitationCorrection(Contract):
    candidate_index: int = Field(ge=0, le=7)
    source_span_ids: list[str] = Field(max_length=2, description='Choose exact IDs from the supplied source_spans. Empty if no supporting excerpt exists.')
    unresolved_reason: str = Field(default='', max_length=600)


class RoleCitationCorrections(Contract):
    corrections: list[RoleCitationCorrection] = Field(min_length=1, max_length=8)


class RoleProposal(Contract):
    label: str = Field(min_length=1, max_length=120)
    stakeholders: list[ShortRoleText] = Field(min_length=1, max_length=4)
    basis: Literal['documented', 'inferred', 'proposed']
    rationale: str = Field(min_length=1, max_length=600)
    purpose: str = Field(min_length=1, max_length=600)
    focus_questions: list[ShortRoleText] = Field(min_length=1, max_length=3)
    evidence_links: list[RoleCitation] = Field(default_factory=list, max_length=2)
    task_ids: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode='after')
    def grounded_basis(self) -> 'RoleProposal':
        if self.basis == 'documented' and not self.evidence_links:
            raise ValueError('Documented stakeholders require source citations.')
        if self.basis == 'inferred' and not (self.evidence_links or self.task_ids):
            raise ValueError('Inferred perspectives require source citations or declared task IDs.')
        if any(not value.strip() for value in [self.label, self.purpose, self.rationale, *self.stakeholders, *self.focus_questions]):
            raise ValueError('Role descriptions cannot be blank.')
        return self


class SelectedRole(RoleProposal):
    role_id: str
    candidate_ids: list[str] = Field(default_factory=list)
    selection_rationale: str = ''
    filled_via: Literal['documented', 'fallback_inferred', 'fallback_proposed', 'default'] | None = None
    registry_entry_id: str | None = None
    source_support: list[dict[str, str]] = Field(default_factory=list)


class RoleCandidates(Contract):
    candidates: list[RoleProposal] = Field(default_factory=list, max_length=8)


class RoleGroup(Contract):
    representative_id: str
    member_ids: list[str] = Field(min_length=1, max_length=16)
    rationale: str = Field(min_length=1, max_length=600)


class OmittedRole(Contract):
    candidate_id: str
    reason: str = Field(min_length=1, max_length=600)


class RolePanel(Contract):
    groups: list[RoleGroup] = Field(min_length=1, max_length=8)
    omitted: list[OmittedRole] = Field(default_factory=list, max_length=16)


class RegistryGroup(Contract):
    representative_id: str
    member_ids: list[str] = Field(min_length=1, max_length=1024)
    rationale: str = Field(min_length=1, max_length=600)


class RoleRegistry(Contract):
    """Lossless equivalence groups, sized for a full scan rather than a panel."""
    groups: list[RegistryGroup] = Field(min_length=1, max_length=1024)
    omitted: list[OmittedRole] = Field(default_factory=list, max_length=0)


class StakeholderVerdict(Contract):
    # The label comes first and is copied from the entry, so a verdict that drifts to a
    # neighbouring entry's ID can be detected; answers saved before it existed have none.
    label: str | None = Field(default=None, max_length=200,
                              description="The exact label of the entry this verdict judges, copied from that entry.")
    entry_id: str
    relevant: bool
    reason: str = Field(min_length=1, max_length=600)


class StakeholderPanel(Contract):
    verdicts: list[StakeholderVerdict] = Field(min_length=1, max_length=1024)
    kept_ids: list[str] = Field(default_factory=list, max_length=8)


class StepModelOptions(Contract):
    reasoning_effort: Literal['low', 'medium', 'high', 'xhigh'] | None = None


class RunRequest(Contract):
    stakeholder_workflow: Literal['independent', 'routed_mediated', 'fa_mediated'] = 'independent'
    requirements_scope: Literal['find_access_v1'] | None = None
    step_models: dict[StepName, ModelID] = Field(default_factory=dict)
    step_model_options: dict[StepName, StepModelOptions] = Field(default_factory=dict)
    output_form: Literal['needs', 'candidates'] | None = None
    scoping: Literal['use_cases', 'off'] | None = None
    snapshot_id: str
    base_profile_id: str | None = None
    base_check: bool = True
    benchmark_case_id: str | None = None
    background_source_names: list[str] = Field(default_factory=list)
    strategy: Literal['rules', 'mock', 'multi_agent'] = 'rules'
    role_ids: list[str] = Field(default_factory=lambda: ['consumer_discovery', 'construction_domain'])
    role_selection: Literal['manual', 'automatic', 'override'] = 'manual'
    max_roles: int = Field(default=4, ge=1, le=8)
    role_overrides: list[RoleProposal] = Field(default_factory=list, max_length=8)
    based_on_run_id: str | None = None
    override_rationale: str = Field(default='', max_length=2000)
    execution_mode: Literal['automatic', 'stepwise'] = 'automatic'
    # automatic: every grounded candidate with a review finding, and every flagged pair,
    # gets a bounded discussion after consolidation. on_request: these go straight to
    # human review, and a reviewer can still open a targeted discussion per candidate.
    discussion: Literal['automatic', 'on_request'] = 'automatic'
    consolidation: Literal['exact', 'semantic'] = 'semantic'
    allow_live_provider: bool = False
    name: str = 'RQ1 workflow'

    @model_validator(mode='after')
    def panel_mode(self) -> 'RunRequest':
        if self.stakeholder_workflow == 'fa_mediated':
            self.requirements_scope = 'find_access_v1'
        if (self.step_models or self.step_model_options) and self.strategy != 'multi_agent':
            raise ValueError('Per-step model choices require the multi_agent strategy.')
        if self.output_form is None:
            self.output_form = 'needs' if self.strategy == 'multi_agent' else 'candidates'
        if self.output_form == 'needs' and self.strategy != 'multi_agent':
            raise ValueError('Needs output requires the multi_agent strategy; use candidates for rules or mock.')
        if self.strategy == 'rules':
            self.consolidation = 'exact'
        if self.strategy == 'rules' and self.role_selection != 'manual':
            raise ValueError('Rules baseline does not use role selection.')
        if self.role_selection == 'override':
            if not self.role_overrides or not self.based_on_run_id or not self.override_rationale.strip():
                raise ValueError('A panel override needs roles, its original run and a rationale.')
            if len(self.role_overrides) > self.max_roles:
                raise ValueError('Override exceeds the configured panel limit.')
        elif self.role_overrides or self.based_on_run_id or self.override_rationale:
            raise ValueError('Override fields require override mode.')
        return self


class DeriveRequest(Contract):
    stakeholder_workflow: Literal['independent', 'routed_mediated', 'fa_mediated'] | None = None
    requirements_scope: Literal['find_access_v1'] | None = None
    step_models: dict[StepName, ModelID] = Field(default_factory=dict)
    step_model_options: dict[StepName, StepModelOptions] = Field(default_factory=dict)
    start_from: Literal['normalization', 'elicitation', 'role_selection'] = 'normalization'
    output_form: Literal['needs', 'candidates'] | None = None
    scoping: Literal['use_cases', 'off'] | None = None
    expected_version: int = Field(ge=1)
    name: str = Field(default='Reprocessed requirements', min_length=1)
    consolidation: Literal['exact', 'semantic'] = 'semantic'
    discussion: Literal['automatic', 'on_request'] = 'on_request'
    execution_mode: Literal['automatic', 'stepwise'] = 'automatic'
    allow_live_provider: bool = False
    reuse_assessments: bool = True
    base_profile_id: str | None = None
    base_check: bool = True
    benchmark_case_id: str | None = None
    rationale: str = Field(min_length=1, max_length=2000)


class WorkflowRun(Contract):
    stakeholder_audit: dict[str, dict[str, Any]] = Field(default_factory=dict)
    step_models: dict[StepName, ModelID] = Field(default_factory=dict)
    step_model_options: dict[StepName, StepModelOptions] = Field(default_factory=dict)
    run_id: str
    name: str
    snapshot_id: str
    workflow_version: str = WORKFLOW_VERSION
    elicitation_policy_version: str = ELICITATION_POLICY_VERSION
    needs_policies: dict[str, str] = Field(default_factory=dict)
    need_steps: dict[str, dict[str, Any]] = Field(default_factory=dict)
    need_chunks: dict[str, dict[str, Any]] = Field(default_factory=dict)
    base_needs_catalogue: dict[str, Any] | None = None
    normalization_policy_version: str | None = None
    consolidation_policy_version: str | None = None
    base_profile_id: str | None = None
    base_profile_sha256: str | None = None
    base_registry_policy_version: str | None = None
    base_check_policy_version: str | None = None
    base_check_audit: list[dict[str, Any]] = Field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    strategy: str
    derived_from: dict[str, Any] | None = None
    assessment_reuse: dict[str, dict[str, Any]] = Field(default_factory=dict)
    request: RunRequest
    status: str = 'created'
    version: int = 1
    stage_results: dict[str, dict[str, Any]] = Field(default_factory=dict)
    stages: dict[str, str] = Field(default_factory=lambda: {stage: 'pending' for stage in STAGES})
    evidence_ids: list[str] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    set_aside_observations: list[SetAside] = Field(default_factory=list)
    requirements: list[RequirementRecord] = Field(default_factory=list)
    active_revision_ids: list[str] = Field(default_factory=list)
    role_runs: list[dict[str, Any]] = Field(default_factory=list)
    role_manifest: dict[str, Any] | None = None
    consolidation_events: list[dict[str, Any]] = Field(default_factory=list)
    consolidation_chunks: dict[str, dict[str, Any]] = Field(default_factory=dict)
    conflicts: list[ConflictRecord] = Field(default_factory=list)
    deliberations: list[DeliberationCase] = Field(default_factory=list)
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    diagnostics: list[str] = Field(default_factory=list)
    created_at: str
    implementation_hash: str = ''
    assessment_history: list[dict[str, Any]] = Field(default_factory=list)
    attempt_history: list[dict[str, Any]] = Field(default_factory=list)
    baselines: list[dict[str, Any]] = Field(default_factory=list)
    machine_snapshot: dict[str, Any] = Field(default_factory=dict)
    model_calls: list[dict[str, Any]] = Field(default_factory=list)
    catalogues: dict[str, list[dict[str, Any]]] = Field(default_factory=dict, description=(
        'Extraction excerpt catalogues by catalogue hash, as referenced by role reports.'))
    worker_id: str | None = None
    job_lease_until: float = 0


class RevisionDraft(Contract):
    statement: str = Field(min_length=1)
    evidence_links: list[EvidenceLink]
    requirement_type: RequirementType = 'unknown'
    intent: NormalizedIntent = Field(default_factory=lambda: NormalizedIntent(resource_type='Unknown'))
    scope: str = 'Unspecified'
    rationale: str = ''


class DecisionRequest(Contract):
    expected_version: int
    idempotency_key: str = Field(min_length=1)
    revision_ids: list[str] = Field(min_length=1)
    action: Literal['accept', 'reject', 'defer', 'out_of_scope', 'edit', 'split', 'merge']
    rationale: str = Field(min_length=1)
    drafts: list[RevisionDraft] = Field(default_factory=list)
    conflict_ids: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_shape(self) -> 'DecisionRequest':
        if self.action == 'edit' and (len(self.drafts) != 1 or len(self.revision_ids) != 1):
            raise ValueError('Edit requires one parent and one draft.')
        if self.action == 'split' and (len(self.drafts) < 2 or len(self.revision_ids) != 1):
            raise ValueError('Split requires one parent and at least two drafts.')
        if self.action == 'merge' and (len(self.drafts) != 1 or len(self.revision_ids) < 2):
            raise ValueError('Merge requires at least two parents and one draft.')
        if self.action not in {'edit', 'split', 'merge'} and self.drafts:
            raise ValueError('Only revision actions accept drafts.')
        return self


class AssessmentRequest(Contract):
    expected_version: int
    idempotency_key: str
    revision_id: str
    qualification: Qualification


class AdditionRequest(Contract):
    expected_version: int
    idempotency_key: str = Field(min_length=1)
    draft: RevisionDraft
    rationale: str = Field(min_length=1)


class RestoreRequest(Contract):
    expected_version: int
    idempotency_key: str = Field(min_length=1)
    observation_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    rationale: str = Field(min_length=1, max_length=2000)
    need_id: str | None = None


class MessageRequest(Contract):
    expected_version: int
    idempotency_key: str
    body: str = Field(min_length=1, max_length=20000)
    evidence_ids: list[str] = Field(default_factory=list)


class BaselineRequest(Contract):
    expected_version: int
    idempotency_key: str
    revision_ids: list[str] = Field(min_length=1)
    name: str = 'Validated RQ1 baseline'
