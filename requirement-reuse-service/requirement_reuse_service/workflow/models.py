from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import ArtifactPayload, NormalizedIntent as LegacyIntent, RequirementType, ResourceType, UserTask

WORKFLOW_VERSION = 'rq1-nine-stage-v2'
SCHEMA_VERSION = 'rq1-requirement-dataset-v2'
ELICITATION_POLICY_VERSION = 'rq1-independent-elicitation-v3.0'
NORMALIZATION_POLICY_VERSION = 'rq1-normalization-v3'
ExtensionKind = Literal['new_information_need', 'stricter_obligation', 'value_constraint',
                        'new_class_or_relation', 'not_an_extension']
STAGES = ['acquisition', 'decomposition', 'role_selection', 'elicitation', 'normalization',
          'verification', 'consolidation', 'deliberation', 'adjudication', 'baseline']


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class NormalizedIntent(LegacyIntent):
    """V2 never supplies an unstated Dataset scope or discovery need."""
    model_config = ConfigDict(extra='forbid')
    resource_type: ResourceType = 'Unknown'
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


class SnapshotRequest(Contract):
    source_version_ids: list[str] = Field(min_length=1)
    user_tasks: list[UserTask] = Field(default_factory=list)
    name: str = 'Research corpus'


class CorpusSnapshot(Contract):
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
    # Older frozen extractions have neither field; their raw saved rows stay valid.
    extension_kind: ExtensionKind | None = None
    base_property: str | None = None


class ElicitationResult(Contract):
    observations: list[Observation] = Field(default_factory=list)


class SetAside(Contract):
    observation_id: str
    role_id: str
    reason: Literal['no_source_link', 'inherited_from_base', 'declared_not_extension'] = 'no_source_link'
    base_check: dict[str, Any] | None = None


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
    rq2_hints: list[dict[str, Any]] = Field(default_factory=list)


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
    frozen_requirements: list[dict[str, Any]] = Field(default_factory=list)


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


class RunRequest(Contract):
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
    run_id: str
    name: str
    snapshot_id: str
    workflow_version: str = WORKFLOW_VERSION
    elicitation_policy_version: str = ELICITATION_POLICY_VERSION
    normalization_policy_version: str | None = None
    consolidation_policy_version: str | None = None
    base_profile_id: str | None = None
    base_profile_sha256: str | None = None
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
