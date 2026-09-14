export type ArtifactPayload = {
  name: string;
  media_type?: string;
  content: string;
  content_encoding?: 'text' | 'base64';
};

export type ExtractionStrategy = 'rules' | 'llm' | 'hybrid' | 'multi_agent';
export type StudyMode = 'formative' | 'summative';
export type StudyPhase =
  | 'development'
  | 'formative_review'
  | 'workflow_frozen'
  | 'summative_review_open'
  | 'summative_review_closed'
  | 'post_evaluation_revision'
  | 'consensus_validation'
  | 'validated';
export type EvidenceSupportLevel = 'explicit' | 'evidence_supported_inference' | 'unsupported';
export type ValidationStatus = 'valid' | 'missing_evidence' | 'invalid_schema' | 'unknown_term' | 'resource_mismatch' | 'needs_review';
export type RequirementScope =
  | 'profile_element'
  | 'obligation_level'
  | 'controlled_vocabulary'
  | 'validation_constraint'
  | 'documentation_guidance'
  | 'example_requirement'
  | 'unknown';

export type UserTask = {
  id: string;
  statement: string;
  kind: 'competency_question' | 'user_task' | 'stakeholder_need';
  stakeholder?: string | null;
  source?: string;
};

export type ExtractionProvenance = {
  strategy: ExtractionStrategy;
  extractor: string;
  model_id?: string | null;
  prompt_version?: string | null;
  created_at?: string | null;
  evidence_verified?: boolean | null;
  notes: string[];
  editor_history: Array<Record<string, unknown>>;
  workflow_id?: string | null;
  workflow_version?: string | null;
  agent_run_id?: string | null;
  agent_role?: string | null;
  agent_phase?: string | null;
  input_hash?: string | null;
  source_candidate_ids?: string[];
};

export type AgentRoleConfig = {
  id: string;
  label: string;
  phase: 'extraction' | 'consolidation' | 'criticism' | 'revision';
  panel_order: number;
  purpose: string;
  focus_questions: string[];
  include: string[];
  exclude: string[];
  prompt_version: string;
  enabled: boolean;
  max_output_tokens?: number | null;
};

export type AgentContextInput = {
  role_id: string;
  background: string;
  rag_queries: string[];
  rag_artifact_names: string[];
  rag_material: string;
  rag_top_k: number;
};

export type RetrievedContextItem = {
  id: string;
  source_kind: 'corpus_artifact' | 'supplemental_material';
  source_ref: string;
  content: string;
  content_hash: string;
  score: number;
  evidence_unit_id?: string | null;
  eligible_as_evidence: boolean;
};

export type AgentContextTrace = {
  role_id: string;
  context_hash: string;
  background: string;
  background_hash?: string | null;
  rag_queries: string[];
  requested_rag_artifact_names: string[];
  shared_evidence_unit_ids: string[];
  retrieved_items: RetrievedContextItem[];
  boundary_notice: string;
};

export type WorkflowTraceEvent = {
  id: string;
  sequence: number;
  event_type: 'context_assembled' | 'cache_reused' | 'run_completed' | 'run_failed' | 'run_skipped';
  phase: string;
  role_id: string;
  agent_run_id: string;
  timestamp?: string | null;
  dependency_role_ids: string[];
  input_artifact_ids: string[];
  output_artifact_ids: string[];
  context_hash?: string | null;
  details: Record<string, unknown>;
};

export type AgentRunRecord = {
  id: string;
  role_id: string;
  phase: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  model_id?: string | null;
  prompt_version?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  candidate_requirement_ids: string[];
  warnings: string[];
  cache_hit: boolean;
  dependency_role_ids: string[];
  input_artifact_ids: string[];
  output_artifact_ids: string[];
  context_trace?: AgentContextTrace | null;
};

export type AgentContribution = {
  agent_run_id: string;
  role_id: string;
  source_candidate_id: string;
  contribution_kind: 'originated' | 'supported' | 'merged' | 'challenged' | 'revised';
  statement?: string | null;
  evidence_unit_ids: string[];
  notes: string[];
};

export type ConsolidationEvent = {
  id: string;
  source_candidate_ids: string[];
  consolidated_requirement_id?: string | null;
  action: 'merge' | 'keep_separate' | 'discard_unsupported' | 'flag_conflict';
  rationale: string;
  performed_by: string;
  created_at: string;
};

export type CritiqueFinding = {
  id: string;
  requirement_id: string;
  critic_role_id: string;
  category: 'grounding' | 'scope' | 'atomicity' | 'obligation' | 'duplicate' | 'conflict' | 'reuse' | 'minimality' | 'resource_compatibility' | 'other';
  severity: 'info' | 'warning' | 'blocking';
  message: string;
  evidence_unit_ids: string[];
  suggested_action?: string | null;
};

export type AnalysisRequest = {
  source_corpus_id?: string | null;
  text?: string;
  artifacts: ArtifactPayload[];
  user_tasks?: UserTask[];
  strategy?: ExtractionStrategy;
  llm_model?: string | null;
  cq_guided?: boolean;
  study_mode?: StudyMode;
  study_phase?: StudyPhase;
  agent_role_ids?: string[];
  panel_preset?: 'full_15' | 'extraction_12' | 'pilot_core';
  workflow_version?: string | null;
  rerun_role_ids?: string[];
  agent_contexts?: AgentContextInput[];
};

export type ArtifactSummary = {
  name: string;
  kind: string;
  evidence_count: number;
  notes: string[];
};

export type EvidenceUnit = {
  id: string;
  source_id: string;
  artifact_name: string;
  artifact_kind: string;
  locator?: string | null;
  content: string;
  extracted_facts: string[];
  confidence: number;
};

export type SourceEvidence = {
  evidence_unit_id: string;
  source_id: string;
  artifact_name: string;
  artifact_kind: string;
  locator?: string | null;
  evidence_text: string;
  extracted_facts: string[];
};

export type NormalizedIntent = {
  resource_type: 'Catalog' | 'Dataset' | 'Distribution' | 'DataService' | 'Agent' | 'Concept' | 'Unknown';
  metadata_need: string;
  value_kind: 'literal' | 'uri' | 'controlled_concept' | 'class_reference' | 'date' | 'agent' | 'distribution' | 'unknown';
  obligation_hint: 'mandatory' | 'recommended' | 'optional' | 'unknown';
};

export type CandidateMetadataAction = {
  action:
    | 'reuse_existing_term'
    | 'specialize_existing_term'
    | 'create_extension'
    | 'add_constraint'
    | 'add_usage_note'
    | 'no_action';
  target_class?: string | null;
  candidate_terms: string[];
  rationale: string;
  constraint_hint?: {
    cardinality?: string | null;
    value_kind: NormalizedIntent['value_kind'];
    datatype_or_class?: string | null;
    obligation: NormalizedIntent['obligation_hint'];
  } | null;
  source_requirement_id?: string | null;
};

export type CandidateRequirement = {
  id: string;
  raw_statement?: string | null;
  normalized_statement?: string | null;
  requirement_type:
    | 'descriptive_metadata'
    | 'semantic_anchor'
    | 'technical_metadata'
    | 'access_policy'
    | 'quality_provenance'
    | 'lifecycle_context'
    | 'controlled_vocabulary'
    | 'validation_constraint'
    | 'competency_question'
    | 'unknown';
  source_evidence: SourceEvidence[];
  normalized_intent: NormalizedIntent;
  fair_dimensions: Array<'F' | 'A' | 'I' | 'R'>;
  fair_rationale?: string | null;
  candidate_metadata_actions: CandidateMetadataAction[];
  supports_user_tasks: string[];
  requires_multiple_elements?: boolean;
  validation_evidence: string[];
  validation_status: ValidationStatus;
  requirement_scope: RequirementScope;
  provenance?: ExtractionProvenance | null;
  status: 'candidate' | 'approved' | 'rejected' | 'merged' | 'needs_review';
  review_notes?: string | null;
  merged_from: string[];
  support_level?: EvidenceSupportLevel;
  origin_kind?: 'rule_extracted' | 'single_llm_extracted' | 'agent_extracted' | 'agent_consolidated' | 'expert_added' | 'human_guided_revision' | null;
  origin_agent_role?: string | null;
  contributing_agent_roles?: string[];
  agent_contributions?: AgentContribution[];
  consolidated_from?: string[];
  critique_finding_ids?: string[];
  machine_output_frozen?: boolean;
  machine_original_statement?: string | null;
  formal_consensus_decision?: 'accepted' | 'accepted_with_revision' | 'rejected' | 'out_of_scope' | 'merged' | 'split' | null;
  title?: string | null;
  description?: string | null;
  category?: string | null;
  source?: string | null;
  evidence: string[];
  confidence: number;
};

export type DuplicateGroup = {
  id: string;
  requirement_ids: string[];
  suggested_merged_statement: string;
  reason: string;
  confidence: number;
};

export type SemanticCandidate = {
  id: string;
  label: string;
  kind: string;
  identifier?: string | null;
  source: string;
  evidence: string[];
  confidence: number;
};

export type ExtractedAttribute = {
  id: string;
  source: string;
  path: string;
  label: string;
  value: string;
  category: string;
  value_type: string;
  confidence: number;
};

export type MetadataCandidate = {
  id: string;
  property: string;
  label: string;
  category: string;
  range: string;
  requirement_level: 'mandatory' | 'recommended' | 'optional';
  source: string;
  evidence: string[];
  confidence: number;
};

export type CompetencyQuestion = {
  id: string;
  question: string;
  category: string;
  source: string;
  evidence?: string | null;
};

export type AnalysisResponse = {
  strategy: ExtractionStrategy;
  study_setup: Record<string, unknown>;
  user_tasks: UserTask[];
  artifacts: ArtifactSummary[];
  evidence_units: EvidenceUnit[];
  extracted_attributes: ExtractedAttribute[];
  requirements: CandidateRequirement[];
  duplicate_groups: DuplicateGroup[];
  semantic_candidates: SemanticCandidate[];
  metadata_candidates: MetadataCandidate[];
  competency_questions: CompetencyQuestion[];
  funnel_metrics: Record<string, unknown>;
  warnings: string[];
  workflow_id?: string | null;
  workflow_version?: string | null;
  study_mode?: StudyMode | null;
  study_phase?: StudyPhase | null;
  input_hash?: string | null;
  panel_preset?: string | null;
  panel_status?: 'completed' | 'incomplete_full_panel' | 'not_applicable' | null;
  extraction_agent_count?: number;
  synthesis_agent_count?: number;
  total_agent_count?: number;
  agent_runs?: AgentRunRecord[];
  raw_agent_requirements?: CandidateRequirement[];
  consolidation_events?: ConsolidationEvent[];
  critique_findings?: CritiqueFinding[];
  agent_contexts?: AgentContextTrace[];
  workflow_trace?: WorkflowTraceEvent[];
};

export type ReviewDecision = 'accept' | 'accept_with_revision' | 'reject' | 'out_of_scope' | 'cannot_assess';

export type ExpertCriterionRatings = {
  evidence_fidelity?: number | null;
  correctness?: number | null;
  relevance?: number | null;
  necessity?: number | null;
  clarity?: number | null;
  atomicity?: number | null;
  reuse_potential?: number | null;
  extension_necessity?: number | null;
};

export type ExpertRequirementReview = {
  requirement_id: string;
  decision: ReviewDecision;
  ratings: ExpertCriterionRatings;
  comment?: string | null;
  proposed_statement?: string | null;
  feedback_categories: string[];
  proposed_merge_with: string[];
  proposed_split_statements: string[];
};

export type MissingRequirementProposal = {
  id: string;
  statement: string;
  rationale: string;
  evidence_unit_ids: string[];
  requirement_type?: string | null;
};

export type EvaluationPackage = {
  schema_version: 'rq1-evaluation-package-v1';
  id: string;
  created_at: string;
  target_reviewer_count: number;
  study_phase: 'workflow_frozen' | 'summative_review_open';
  source_corpus_id?: string | null;
  input_hash: string;
  workflow_version: string;
  strategy_used: string;
  model_configuration: Record<string, unknown>;
  role_configuration: AgentRoleConfig[];
  agent_runs: AgentRunRecord[];
  agent_contexts: AgentContextTrace[];
  workflow_trace: WorkflowTraceEvent[];
  evidence_units: EvidenceUnit[];
  user_tasks: UserTask[];
  raw_agent_requirements: CandidateRequirement[];
  machine_requirements: CandidateRequirement[];
  consolidation_events: ConsolidationEvent[];
  critique_findings: CritiqueFinding[];
  warnings: string[];
  package_hash: string;
};

export type ExpertReviewSubmission = {
  schema_version: 'rq1-expert-review-v1';
  id: string;
  evaluation_package_id: string;
  evaluation_package_hash: string;
  reviewer_id: string;
  started_at: string;
  completed_at?: string | null;
  reviews: ExpertRequirementReview[];
  missing_requirements: MissingRequirementProposal[];
  submission_hash: string;
};

export type RequirementReviewAggregate = {
  requirement_id: string;
  reviewer_count: number;
  decisions: Record<string, number>;
  unanimous: boolean;
  majority_decision?: string | null;
  disagreement: boolean;
  median_ratings: Record<string, number | null>;
  comments: Array<Record<string, unknown>>;
};

export type ReviewAggregation = {
  schema_version: 'rq1-review-aggregation-v1';
  evaluation_package_id: string;
  evaluation_package_hash: string;
  reviewer_ids: string[];
  expected_reviewer_count: number;
  complete: boolean;
  requirement_aggregates: RequirementReviewAggregate[];
  missing_requirement_proposals: MissingRequirementProposal[];
  summary_metrics: Record<string, unknown>;
};

export type RevisionRecord = {
  id: string;
  requirement_id: string;
  original_statement: string;
  proposed_statement: string;
  feedback_categories: string[];
  source_review_submission_ids: string[];
  expert_comments: Array<Record<string, string>>;
  performed_by: string;
  created_at: string;
};

export type RevisionResponse = {
  schema_version: 'rq1-post-evaluation-revision-v1';
  evaluation_package_id: string;
  study_phase: 'post_evaluation_revision';
  revisions: RevisionRecord[];
  expert_added_requirements: CandidateRequirement[];
  warnings: string[];
};

export type ConsensusDecision = {
  requirement_id: string;
  decision: 'accepted' | 'accepted_with_revision' | 'rejected' | 'out_of_scope' | 'merged' | 'split';
  final_statement?: string | null;
  rationale: string;
  participant_reviewer_ids: string[];
  revision_record_id?: string | null;
  decided_at: string;
};

export type ValidatedRequirementBaseline = {
  schema_version: 'rq1-validated-requirement-baseline-v1';
  evaluation_package_id: string;
  evaluation_package_hash: string;
  study_phase: 'validated';
  requirements: CandidateRequirement[];
  consensus_decisions: ConsensusDecision[];
  original_machine_requirement_ids: string[];
};

export type Rq1LocalMergeEvent = {
  timestamp: string;
  source_requirement_ids: string[];
  merged_requirement_id: string;
  normalized_statement: string;
  suggested_statement_used: boolean;
};

export type Rq1LocalSplitEvent = {
  timestamp: string;
  source_requirement_id: string;
  split_requirement_ids: string[];
  source_statement: string;
};

export type Rq1DatasetExport = {
  schema_version: string;
  export_kind?: 'reviewed_frontend_state' | 'service_generated';
  generated_at: string;
  source_corpus_id?: string | null;
  reviewer_id?: string;
  session_id?: string;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  study_setup?: Record<string, unknown>;
  rq1_codebook?: Record<string, unknown>;
  strategy_requested: ExtractionStrategy;
  strategy_used: ExtractionStrategy;
  summary_metrics: Record<string, unknown>;
  requirements: CandidateRequirement[];
  evidence_units: EvidenceUnit[];
  duplicate_groups: DuplicateGroup[];
  duplicate_groups_original?: DuplicateGroup[];
  local_merge_events?: Rq1LocalMergeEvent[];
  local_split_events?: Rq1LocalSplitEvent[];
  user_tasks: UserTask[];
  funnel_metrics?: Record<string, unknown>;
  warnings: string[];
  review_editor_history: Array<Record<string, unknown>>;
  workflow_id?: string | null;
  workflow_version?: string | null;
  study_mode?: StudyMode | null;
  study_phase?: StudyPhase | null;
  input_hash?: string | null;
  panel_preset?: string | null;
  panel_status?: string | null;
  agent_runs?: AgentRunRecord[];
  raw_agent_requirements?: CandidateRequirement[];
  machine_requirements?: CandidateRequirement[];
  consolidation_events?: ConsolidationEvent[];
  critique_findings?: CritiqueFinding[];
  agent_contexts?: AgentContextTrace[];
  workflow_trace?: WorkflowTraceEvent[];
  original_machine_output?: CandidateRequirement[];
};

async function postJson<T>(endpoint: string, payload: unknown): Promise<T> {
  const response = await fetch(`/api/requirements/${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());
  return (await response.json()) as T;
}

export function analyzeArtifacts(payload: AnalysisRequest) {
  return postJson<AnalysisResponse>('analyze-artifacts', payload);
}

export function extractRequirements(payload: AnalysisRequest) {
  return postJson<AnalysisResponse>('extract-requirements', payload);
}

export function exportRq1Dataset(payload: AnalysisRequest) {
  return postJson<Rq1DatasetExport>('export-rq1-dataset', payload);
}

export function freezeEvaluationPackage(analysis: AnalysisResponse, targetReviewerCount = 3, includeRequirementIds: string[] = []) {
  return postJson<EvaluationPackage>('freeze-evaluation-package', {
    analysis,
    target_reviewer_count: targetReviewerCount,
    include_requirement_ids: includeRequirementIds,
  });
}

export function validateReviewSubmission(evaluationPackage: EvaluationPackage, reviewSubmission: ExpertReviewSubmission) {
  return postJson<{ valid: boolean; reviewer_id: string; reviewed_requirement_count: number; complete: boolean; submission_hash: string }>(
    'validate-review-submission',
    { evaluation_package: evaluationPackage, review_submission: reviewSubmission },
  );
}

export function aggregateExpertReviews(evaluationPackage: EvaluationPackage, reviewSubmissions: ExpertReviewSubmission[]) {
  return postJson<ReviewAggregation>('aggregate-expert-reviews', {
    evaluation_package: evaluationPackage,
    review_submissions: reviewSubmissions,
  });
}

export function reviseAfterEvaluation(
  evaluationPackage: EvaluationPackage,
  aggregation: ReviewAggregation,
  reviewSubmissions: ExpertReviewSubmission[],
  selectedFeedbackItems: string[] = [],
) {
  return postJson<RevisionResponse>('revise-after-evaluation', {
    evaluation_package: evaluationPackage,
    aggregation,
    review_submissions: reviewSubmissions,
    selected_feedback_items: selectedFeedbackItems,
    study_phase: 'summative_review_closed',
  });
}

export function finalizeConsensus(
  evaluationPackage: EvaluationPackage,
  aggregation: ReviewAggregation,
  consensusDecisions: ConsensusDecision[],
  revisionResponse?: RevisionResponse | null,
) {
  return postJson<ValidatedRequirementBaseline>('finalize-consensus', {
    evaluation_package: evaluationPackage,
    aggregation,
    revision_response: revisionResponse,
    consensus_decisions: consensusDecisions,
    study_phase: 'consensus_validation',
  });
}
