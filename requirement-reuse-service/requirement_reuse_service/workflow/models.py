from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import ArtifactPayload, NormalizedIntent as LegacyIntent, RequirementType, UserTask

WORKFLOW_VERSION = 'rq1-nine-stage-v2'
SCHEMA_VERSION = 'rq1-requirement-dataset-v2'
STAGES = ['acquisition', 'decomposition', 'elicitation', 'normalization',
          'verification', 'consolidation', 'deliberation', 'adjudication', 'baseline']


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class NormalizedIntent(LegacyIntent):
    """V2 never supplies an unstated Dataset scope or discovery need."""
    model_config = ConfigDict(extra='forbid')
    resource_type: Literal['Catalog', 'Dataset', 'Distribution', 'DataService', 'Agent', 'Concept', 'Unknown'] = 'Unknown'
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
    source_role: Literal['normative_spec', 'stakeholder_need', 'example', 'observation', 'background'] = 'observation'
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


class ElicitationResult(Contract):
    observations: list[Observation] = Field(default_factory=list)


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
    policy_version: str = 'rq1-selective-v2'
    status: str = 'queued'
    messages: list[dict[str, Any]] = Field(default_factory=list)
    stop_reason: str | None = None
    max_rounds: int = 3
    max_calls: int = 12
    max_output_tokens: int = 1000
    total_output_budget: int = 12000
    max_seconds: int = 300
    output_tokens_reserved: int = 0
    frozen_requirements: list[dict[str, Any]] = Field(default_factory=list)


class RunRequest(Contract):
    snapshot_id: str
    strategy: Literal['rules', 'mock', 'multi_agent'] = 'rules'
    role_ids: list[str] = Field(default_factory=lambda: ['consumer_discovery', 'construction_domain'])
    allow_live_provider: bool = False
    name: str = 'RQ1 workflow'


class WorkflowRun(Contract):
    run_id: str
    name: str
    snapshot_id: str
    workflow_version: str = WORKFLOW_VERSION
    schema_version: str = SCHEMA_VERSION
    strategy: str
    request: RunRequest
    status: str = 'created'
    version: int = 1
    stages: dict[str, str] = Field(default_factory=lambda: {stage: 'pending' for stage in STAGES})
    evidence_ids: list[str] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    requirements: list[RequirementRecord] = Field(default_factory=list)
    active_revision_ids: list[str] = Field(default_factory=list)
    role_runs: list[dict[str, Any]] = Field(default_factory=list)
    consolidation_events: list[dict[str, Any]] = Field(default_factory=list)
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
