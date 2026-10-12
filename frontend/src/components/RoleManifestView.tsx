import { useState } from 'react';
import { downloadWorkflow, RoleProposal, Run } from '../lib/workflowApi';

type Props = {
  run: Run;
  busy: boolean;
  inspect: (id: string) => void;
  override: (roles: RoleProposal[], rationale: string, maxRoles: number, allowLive: boolean) => Promise<void>;
};

export function RoleManifestView({ run, busy, inspect, override }: Props) {
  const manifest = run.role_manifest;
  const [editing, setEditing] = useState(false);
  const [roles, setRoles] = useState<RoleProposal[]>((manifest?.selected_roles ?? []).map(role => ({
    label: role.label, stakeholders: role.stakeholders, basis: role.basis, rationale: role.rationale,
    purpose: role.purpose, focus_questions: role.focus_questions, evidence_links: role.evidence_links, task_ids: role.task_ids,
  })));
  const [reason, setReason] = useState('');
  const [allowLive, setAllowLive] = useState(false);
  const [maxRoles, setMaxRoles] = useState(Math.min(manifest?.max_roles ?? 4, 8));
  if (!manifest || manifest.mode === 'rules') return null;
  const update = (index: number, patch: Partial<RoleProposal>) => setRoles(previous => previous.map((role, i) => i === index ? { ...role, ...patch } : role));
  const complete = manifest.status === 'completed';
  // Historical failed runs may retain a pre-fix "running" manifest; render the
  // terminal run state without rewriting their saved audit records.
  const selectionStatus = !complete && ['failed', 'cancelled'].includes(run.status) ? run.status : manifest.status;
  const inProgress = ['created', 'selecting_roles', 'eliciting', 'normalizing', 'verifying', 'consolidating', 'routing'].includes(run.status)
    || run.deliberations.some(item => item.status === 'running');
  return <section className="workflow-panel">
    <h2>3a · Stakeholders and role selection</h2>
    <p>{manifest.mode} · {selectionStatus} · {manifest.selected_roles.length} perspectives</p>
    {selectionStatus === 'failed' && <p className="workflow-error">Role selection stopped before the panel was completed. Check the source citations and recorded attempts below.</p>}
    {run.strategy === 'mock' && <p className="workflow-notice">Offline demonstration: requirements use mock proposals. No model is called for this run.</p>}
    {manifest.mode === 'automatic' && <p>{manifest.processed_evidence_ids.length} of {run.evidence_ids.length} evidence units processed · {manifest.selection_rounds.length} of {manifest.total_batches ?? '?'} batches assembled.</p>}
    {manifest.mode === 'automatic' && manifest.total_batches != null && <p>The scan reads the whole corpus in {manifest.total_batches} source {manifest.total_batches === 1 ? 'batch' : 'batches'}, with up to {manifest.total_batches * 4} selector calls.</p>}
    <p>Documented and inferred labels are selection judgements. Exact quotations can be checked; they do not establish stakeholder endorsement. Every extracted requirement still needs its own evidence.</p>
    {manifest.fallback_reason && <p className="workflow-notice">{manifest.fallback_reason}</p>}
    {manifest.override && <p>Human override by {manifest.override.actor}: {manifest.override.rationale}. Based on run {manifest.override.based_on_run_id}.</p>}
    <div className="workflow-role-list">{manifest.selected_roles.map(role => <article key={role.role_id}>
      <strong>{role.label}</strong><span className="workflow-pill">{role.basis}</span>
      <p>Stakeholders: {role.stakeholders.join(', ')}</p><p>{role.purpose}</p>
      <ul>{role.focus_questions.map((question, i) => <li key={i}>{question}</li>)}</ul>
      <p>{role.rationale}</p><small>{role.selection_rationale}</small>
      {role.evidence_links.map((link, i) => <blockquote key={i}><p className="workflow-quote">{link.quote}</p><button onClick={() => inspect(link.evidence_id)}>Inspect stakeholder evidence</button></blockquote>)}
      {!!role.task_ids.length && <small>CQs / tasks: {role.task_ids.join(', ')}</small>}
    </article>)}</div>
    <p className="workflow-muted">Source verification, support/scope assessment and the grounding critic remain procedural responsibilities. Automatic selection changes the stakeholder perspectives.</p>
    {!!manifest.validation_attempts?.length && <details open={selectionStatus === 'failed'}><summary>Citation and panel checks and corrections</summary>
      {manifest.validation_attempts.map((attempt, index) => <article key={index}>
        <strong>Batch {attempt.batch_index + 1} · {attempt.phase === 'citation_repair' ? 'Citation correction' : attempt.phase === 'panel_correction' ? 'Panel correction' : 'Initial proposals'} · {attempt.status}</strong>
        {attempt.error && <p className="workflow-error">{attempt.error}</p>}
        {(attempt.remaining_problems?.length ? attempt.remaining_problems : attempt.problems)?.map((problem, i) => <p key={i}>{problem}</p>)}
        {attempt.validation_report?.filter(candidate => candidate.status === 'invalid').map(candidate => <div key={candidate.candidate_index}>
          <p>{candidate.label}</p>{candidate.errors.map((error, i) => <p key={i}>{error.message} {error.evidence_id && run.evidence_ids.includes(error.evidence_id) && <button onClick={() => inspect(error.evidence_id!)}>Inspect cited passage</button>}</p>)}
        </div>)}
      </article>)}
    </details>}
    <details><summary>Selection audit and omitted perspectives</summary>
      <p>Policy: {manifest.policy_version}</p><code>{manifest.manifest_hash ?? (['failed', 'cancelled'].includes(selectionStatus) ? 'No completed panel manifest.' : 'Manifest is still being assembled.')}</code>
      <pre>{JSON.stringify({ candidates: manifest.candidates, validation_attempts: manifest.validation_attempts, rounds: manifest.selection_rounds, omissions: manifest.omissions, limitations: manifest.limitations }, null, 2)}</pre>
    </details>
    {complete && <div className="workflow-toolbar">
      <button onClick={() => downloadWorkflow('rq1-role-manifest.json', manifest)}>Download role manifest</button>
      <button disabled={busy || inProgress} onClick={() => setEditing(value => !value)}>{editing ? 'Close panel editor' : 'Override panel in a new run'}</button>
    </div>}
    {editing && <div className="workflow-role-editor">
      <h3>New run with an edited panel</h3><p>This reuses the same frozen sources and CQs. The original panel, outputs and reviews remain saved. Starting the new run repeats extraction.</p>
      {roles.map((role, index) => <fieldset key={index}><legend>Perspective {index + 1}</legend>
        <label>Role name<input maxLength={120} value={role.label} onChange={event => update(index, { label: event.target.value })} /></label>
        <label>Stakeholder groups · one per line<textarea value={role.stakeholders.join('\n')} onChange={event => update(index, { stakeholders: event.target.value.split('\n') })} /></label>
        <label>Basis<select value={role.basis} onChange={event => update(index, { basis: event.target.value as RoleProposal['basis'] })}>{['documented', 'inferred', 'proposed'].map(value => <option key={value}>{value}</option>)}</select></label>
        <label>Why this perspective belongs<input maxLength={600} value={role.rationale} onChange={event => update(index, { rationale: event.target.value })} /></label>
        <label>Purpose<textarea maxLength={600} value={role.purpose} onChange={event => update(index, { purpose: event.target.value })} /></label>
        <label>Focus questions · up to three, one per line<textarea value={role.focus_questions.join('\n')} onChange={event => update(index, { focus_questions: event.target.value.split('\n') })} /></label>
        {role.evidence_links.map((link, linkIndex) => <div key={linkIndex}>
          <label>Supporting evidence<select value={link.evidence_id} onChange={event => update(index, { evidence_links: role.evidence_links.map((item, i) => i === linkIndex ? { ...item, evidence_id: event.target.value, quote_start: null } : item) })}>{run.evidence_ids.map(id => <option key={id}>{id}</option>)}</select></label>
          <label>Exact quote<textarea maxLength={400} value={link.quote} onChange={event => update(index, { evidence_links: role.evidence_links.map((item, i) => i === linkIndex ? { ...item, quote: event.target.value, quote_start: null } : item) })} /></label>
          <label>Quote offset · optional for a unique quote<input type="number" min={0} value={link.quote_start ?? ''} onChange={event => update(index, { evidence_links: role.evidence_links.map((item, i) => i === linkIndex ? { ...item, quote_start: event.target.value === '' ? null : Number(event.target.value) } : item) })} /></label>
          <button onClick={() => update(index, { evidence_links: role.evidence_links.filter((_, i) => i !== linkIndex) })}>Remove role citation</button>
        </div>)}
        <button disabled={role.evidence_links.length >= 2} onClick={() => update(index, { evidence_links: [...role.evidence_links, { evidence_id: run.evidence_ids[0], quote: '' }] })}>Add role citation</button>
        <button onClick={() => setRoles(previous => previous.filter((_, i) => i !== index))}>Remove perspective</button>
      </fieldset>)}
      <button disabled={roles.length >= 8} onClick={() => setRoles(previous => [...previous, { label: '', stakeholders: [''], basis: 'proposed', rationale: '', purpose: '', focus_questions: [''], evidence_links: [], task_ids: [] }])}>Add proposed perspective</button>
      <label>Maximum panel size<input type="number" min={1} max={8} value={maxRoles} onChange={event => setMaxRoles(Number(event.target.value))} /></label>
      <label>Reason for the override<textarea value={reason} maxLength={2000} onChange={event => setReason(event.target.value)} /></label>
      {run.strategy === 'multi_agent' && <label className="workflow-check"><input type="checkbox" checked={allowLive} onChange={event => setAllowLive(event.target.checked)} />Allow the configured model to run extraction and discussion again</label>}
      <button className="workflow-primary" disabled={busy || inProgress || !roles.length || roles.length > maxRoles || !reason.trim() || (run.strategy === 'multi_agent' && !allowLive)} onClick={() => void override(roles.map(role => ({ ...role, stakeholders: role.stakeholders.map(value => value.trim()).filter(Boolean), focus_questions: role.focus_questions.map(value => value.trim()).filter(Boolean) })), reason, maxRoles, allowLive)}>Start new run with this panel</button>
    </div>}
  </section>;
}
