export type Source = { source_version_id: string; source_id: string; name: string; artifact_kind: string; parse_status: string; source_role: string; raw_sha256: string; diagnostics: string[]; parent_source_version_id?: string };
export type Link = { evidence_id: string; quote: string; relation: 'supports' | 'contradicts' | 'contextualizes'; component: string; quote_start?: number | null };
export type Intent = { resource_type: string; metadata_need: string; value_kind: string; obligation_hint: string };
export type Finding = { criterion: string; severity: string; message: string };
export type Qualification = { support: string; rationale: string; findings: Finding[]; assessor: string; revision_hash: string };
export type Requirement = { requirement_id: string; revision_id: string; revision_number: number; content_hash: string; normalized_statement: string; raw_statement: string; requirement_type: string; normalized_intent: Intent; scope: string; evidence_links: Link[]; contributing_roles: string[]; parent_revision_ids: string[]; lifecycle_state: string; verification?: { status: string; links: { evidence_id: string; status: string; message?: string; method: string }[] }; qualification?: Qualification };
export type Message = { message_id: string; role_id: string; body: string; evidence_ids: string[]; proposed_statement?: string; round?: number };
export type Case = { case_id: string; revision_ids: string[]; triggers: string[]; status: string; participants: string[]; messages: Message[]; stop_reason?: string; max_rounds: number; max_calls: number };
export type Conflict = { conflict_id: string; revision_ids: string[]; kind: string; rationale: string; status: string };
export type RunSummary = { run_id: string; name: string; status: string; strategy: string; version: number };
export type Baseline = { baseline_id: string; baseline_hash: string; name: string };
export type RoleProposal = { label: string; stakeholders: string[]; basis: 'documented' | 'inferred' | 'proposed'; rationale: string; purpose: string; focus_questions: string[]; evidence_links: { evidence_id: string; quote: string; quote_start?: number | null }[]; task_ids: string[] };
export type RoleValidationAttempt = { batch_index: number; phase: string; status: string; error?: string; validation_report?: { candidate_index: number; label: string; status: string; errors: { code: string; evidence_id?: string; message: string }[] }[] };
export type RoleManifest = { policy_version: string; mode: string; status: string; max_roles: number; selected_roles: (RoleProposal & { role_id: string; selection_rationale: string })[]; execution?: string; total_batches?: number; processed_evidence_ids: string[]; candidates: unknown[]; selection_rounds: unknown[]; omissions: unknown[]; limitations: string[]; validation_attempts?: RoleValidationAttempt[]; last_error?: string; manifest_hash?: string; fallback_reason?: string; override?: { actor: string; rationale: string; based_on_run_id: string } };
export type Run = RunSummary & { snapshot_id: string; request?: { execution_mode?: 'automatic' | 'stepwise'; discussion?: 'automatic' | 'on_request' }; worker_id?: string | null; job_lease_until?: number; decisions?: unknown[]; role_manifest?: RoleManifest | null; stages: Record<string, string>; stage_results?: Record<string, { requirements?: Requirement[] }>; evidence_ids: string[]; observations?: { role_id: string; statement: string }[]; active_revision_ids: string[]; requirements: Requirement[]; conflicts: Conflict[]; deliberations: Case[]; role_runs: { role_id: string; status: string; error?: string; context_hash?: string; observation_ids?: string[]; evidence_unit_count?: number; processed_unit_count?: number }[]; diagnostics: string[]; metrics: Record<string, unknown>; baselines?: Baseline[]; attempt_history?: unknown[] };
export type Evidence = { unit: { evidence_id: string; content: string; kind: string; source_version_id: string; selector: unknown; structural_context: unknown; source_claim_kind: string }; resolution: { status: string; message?: string; method: string } };

export async function workflowApi<T>(path: string, payload?: unknown): Promise<T> {
  const response = await fetch(`/api/rq1/v2${path}`, payload === undefined ? undefined : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail));
  return body as T;
}

export const commandKey = () => crypto.randomUUID();
export function downloadWorkflow(name: string, value: unknown) {
  const href = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a'); link.href = href; link.download = name; link.click(); URL.revokeObjectURL(href);
}

export type Snapshot = { snapshot_id: string; source_version_ids: string[]; evidence_ids: string[]; user_tasks: { id: string; statement: string; kind: string }[] };
export type EvidenceSummary = { evidence_id: string; kind: string; source_version_id: string; preview: string };
