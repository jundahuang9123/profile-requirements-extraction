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
export type Run = RunSummary & { stages: Record<string, string>; evidence_ids: string[]; active_revision_ids: string[]; requirements: Requirement[]; conflicts: Conflict[]; deliberations: Case[]; role_runs: { role_id: string; status: string; error?: string; context_hash?: string; observation_ids?: string[] }[]; diagnostics: string[]; metrics: Record<string, unknown>; baselines?: Baseline[] };
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
