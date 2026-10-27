import { useState } from 'react';
import { Run, Requirement } from '../lib/workflowApi';
import { TraceLink } from '../lib/traceApi';
import { NeedTraceView } from './NeedTraceView';

type Route = { evidence_id: string; kind: string; role_ids: string[]; rationale: string };
export default function RunTraceView({ run, stage, inspect, openResult }: { run: Run; stage: string; inspect: (id: string) => void; openResult: (link: TraceLink) => void }) {
  const [selected, setSelected] = useState('');
  const audit = run.stakeholder_audit ?? {};
  const plan = audit.routing_plan as { routes?: Route[]; source_unit_count?: number; assignment_count?: number } | undefined;
  const byId = new Map(run.requirements.map(r => [r.revision_id, r]));
  const node = (record: Requirement, seen: Set<string>): JSX.Element => {
    if (seen.has(record.revision_id)) return <p key={record.revision_id}>Previously shown: {record.revision_id}</p>;
    const next = new Set([...seen, record.revision_id]);
    return <article key={record.revision_id}><strong>{record.need_statement ?? record.normalized_statement}</strong>
      <p>{record.lifecycle_state} · {record.revision_id}</p>{record.need_condition && <p>Condition: {record.need_condition}</p>}
      {record.evidence_links.map((link, i) => <details key={i}><summary>{link.component} · {link.evidence_id}</summary>
        <blockquote>{link.quote}</blockquote><button onClick={() => inspect(link.evidence_id)}>Open source and location</button></details>)}
      {!!record.parent_revision_ids.length && <details><summary>Earlier revisions and extraction</summary>
        {record.parent_revision_ids.map(id => { const parent = byId.get(id); return parent ? node(parent, next) : <p key={id}>Saved parent: {id}</p>; })}</details>}
      <details><summary>Checks, concerns and decisions for this revision</summary><pre>{JSON.stringify({
        verification: record.verification, qualification: record.qualification,
        observations: run.observations?.filter(o => record.observation_ids?.includes(o.observation_id)),
        discussions: run.deliberations.filter(c => c.revision_ids.includes(record.revision_id) || JSON.stringify(c.mediation ?? {}).includes(record.revision_id)),
        humanDecisions: run.decisions?.filter(d => JSON.stringify(d).includes(record.revision_id)),
        base: record.base_gap, scope: record.profile_scope, flags: record.processing_flags,
      }, null, 2)}</pre></details></article>;
  };
  return <section className="workflow-panel"><h2>Run trace · {stage.replace(/_/g, ' ')}</h2>
    <p>Every saved proposal, change and exclusion remains linked to its source. Machine mediation is provisional; human approval is recorded separately.</p>
    <a className="workflow-download" href={`/api/rq1/v2/runs/${run.run_id}/trace?download=true`}>Download complete trace</a>
    {plan && <details open={stage === 'elicitation'}><summary>Source assignments · {plan.source_unit_count} sections · {plan.assignment_count} assignments</summary>
      <table><thead><tr><th>Source section</th><th>Assigned perspective</th><th>Reason</th></tr></thead><tbody>{plan.routes?.map(r => <tr key={r.evidence_id}>
        <td><button onClick={() => inspect(r.evidence_id)}>{r.evidence_id}</button></td><td>{r.kind} · {r.role_ids.map(id => run.role_manifest?.selected_roles.find(s => s.role_id === id)?.label ?? id).join(', ')}</td><td>{r.rationale}</td>
      </tr>)}</tbody></table></details>}
    <label>Follow a need back to its sources<select value={selected} onChange={e => setSelected(e.target.value)}><option value="">Choose a current need</option>
      {run.requirements.filter(r => run.active_revision_ids.includes(r.revision_id)).map(r => <option key={r.revision_id} value={r.revision_id}>{r.need_statement ?? r.normalized_statement}</option>)}</select></label>
    {selected && byId.get(selected)?.need_statement && <NeedTraceView run={run} revisionId={selected} open={openResult} />}
    {selected && byId.get(selected) && <details><summary>Saved revisions and checks of this need</summary>{node(byId.get(selected)!, new Set())}</details>}
    <details><summary>Saved stage inputs, outputs, routing and mediation audit</summary><pre>{JSON.stringify(audit, null, 2)}</pre></details>
    <details><summary>Saved results for this stage</summary><pre>{JSON.stringify(run.stage_results?.[stage] ?? { status: run.stages[stage], message: 'No completed stage output yet.' }, null, 2)}</pre></details>
  </section>;
}
