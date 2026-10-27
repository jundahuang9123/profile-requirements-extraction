// A need's trace (rq1-need-trace-v1) with links to the saved results each entry comes from.
// A link names a saved file (an API path) and a JSON pointer to the traced part; a quotation also names its text.
export type TraceLink = { label: string; file: string; pointer: string; mark?: string; quote_span?: [number, number] | null };
export type TraceSource = { evidence_id: string; source_version_id?: string | null; source?: string | null; quote: string; quote_start?: number | null; component?: string; found: boolean; links: TraceLink[] };
export type TraceOrigin = { observation_id: string; statement?: string | null; agent?: string | null; agent_name?: string | null; prompt_version?: string | null; model?: string | null; extraction_run_id?: string | null; call_ids: string[]; call_link: string; links: TraceLink[] };
export type TraceDecision = { step: string; revision_id: string; decision: string | null; reason: string; policy_version?: string | null; call_ids: string[]; call_link: string; links: TraceLink[] };
export type TraceOutcome = { action_id: string; action: string; status: string; applied?: boolean | null; rationale?: string | null; question?: string | null; result_revision_ids: string[]; links: TraceLink[] };
export type TraceCase = { case_id: string; stop_reason?: string | null; roles: string[]; concerns: { role_id: string; round?: number; kind?: string; statement?: string }[]; outcomes: TraceOutcome[]; questions: string[]; summary?: string | null; call_ids: string[]; links: TraceLink[] };
export type SummaryLine = { label: string; parts: { text: string; ref: string | null }[] };
export type NeedTrace = {
  policy_version: string; revision_id: string; requirement_id: string; statement: string; state: string; lifecycle_state: string; flags: string[];
  sources: TraceSource[]; origin: TraceOrigin[]; decisions: TraceDecision[]; discussion: TraceCase[]; links: TraceLink[];
  completeness: { solid: boolean; missing: { link: string; detail: string }[]; call_links: Record<string, number> };
  summary: string; summary_parts: SummaryLine[];
};

// A JSON pointer (RFC 6901) as keys and indices.
export const pointerKeys = (pointer: string) => pointer ? pointer.split('/').slice(1).map(key => key.replace(/~1/g, '/').replace(/~0/g, '~')) : [];

export function resolvePointer(value: unknown, pointer: string): unknown {
  let node = value;
  for (const key of pointerKeys(pointer)) {
    if (node === null || typeof node !== 'object') return undefined;
    node = (node as Record<string, unknown>)[key];
  }
  return node;
}

// The workbench route that opens a link's file on its own page.
export function resultHref(link: TraceLink) {
  const query = new URLSearchParams({ file: link.file, pointer: link.pointer, label: link.label });
  if (link.mark) query.set('mark', link.mark);
  if (link.quote_span) query.set('span', link.quote_span.join(','));
  return `#/result?${query.toString()}`;
}

// The saved results a link may open; a crafted #/result link cannot point the viewer at any other path.
const RESULT_FILE = /^\/(runs\/[\w.-]+(\/stages\/\w+|\/calls\/[\w.-]+|\/traceability|\?audit=false)|sources\/[\w.-]+\/document)$/;
export const isResultFile = (file: string) => RESULT_FILE.test(file);

export function linkFromHash(hash: string): TraceLink | null {
  if (!hash.startsWith('#/result?')) return null;
  const query = new URLSearchParams(hash.slice('#/result?'.length));
  const file = query.get('file');
  if (!file || !isResultFile(file)) return null;
  const span = query.get('span')?.split(',').map(Number);
  return { file, pointer: query.get('pointer') ?? '', label: query.get('label') ?? file, mark: query.get('mark') ?? undefined,
           quote_span: span?.length === 2 && span.every(Number.isFinite) ? [span[0], span[1]] : null };
}

const files = new Map<string, { at: number; body: Promise<unknown> }>();
// Files of the current saved state change whenever a reviewer acts, and are always read afresh.
const current = (file: string) => file.endsWith('/stages/adjudication') || file.endsWith('?audit=false') || file.endsWith('/traceability');
// Following a trace opens the same few step files again and again; they are kept for a minute, and only the most
// recent six (step files run to several megabytes).
export function loadResultFile(file: string): Promise<unknown> {
  const cached = current(file) ? undefined : files.get(file);
  if (cached && Date.now() - cached.at < 60_000) return cached.body;
  const body = fetch(`/api/rq1/v2${file}`).then(async response => {
    const value = await response.json();
    if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : JSON.stringify(value.detail));
    return value;
  });
  body.catch(() => files.delete(file));
  files.delete(file); files.set(file, { at: Date.now(), body });
  if (files.size > 6) files.delete(files.keys().next().value as string);
  return body;
}
