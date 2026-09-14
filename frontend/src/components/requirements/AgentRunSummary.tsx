import type { AgentRunRecord, AnalysisResponse } from '../../lib/requirementApi';
import { AgentProcessGraph } from './AgentProcessGraph';
import { ALL_AGENT_ROLES } from './agentRoles';

export function AgentRunSummary({ analysis }: { analysis: AnalysisResponse }) {
  if (analysis.strategy !== 'multi_agent') return null;
  const runs = analysis.agent_runs ?? [];
  const raw = analysis.raw_agent_requirements ?? [];
  const contexts = analysis.agent_contexts ?? [];
  const trace = [...(analysis.workflow_trace ?? [])].sort((left, right) => left.sequence - right.sequence);
  const verifiedByRole = new Map<string, { verified: number; total: number }>();
  raw.forEach((requirement) => {
    const role = requirement.origin_agent_role ?? 'unknown';
    const current = verifiedByRole.get(role) ?? { verified: 0, total: 0 };
    current.total += 1;
    if (requirement.provenance?.evidence_verified) current.verified += 1;
    verifiedByRole.set(role, current);
  });
  const blocking = (analysis.critique_findings ?? []).filter((finding) => finding.severity === 'blocking').length;

  return (
    <section className="agent-run-summary" aria-label="Role-conditioned agent run summary">
      <header>
        <div>
          <h3>Traceable role-conditioned panel</h3>
          <p>{analysis.panel_preset} · {analysis.panel_status} · input {shortHash(analysis.input_hash)}</p>
        </div>
        <span>{analysis.extraction_agent_count ?? 0} extraction + {analysis.synthesis_agent_count ?? 0} synthesis = {analysis.total_agent_count ?? runs.length}</span>
      </header>

      <AgentProcessGraph contexts={contexts} runs={runs} />

      <div className="agent-run-metrics">
        <span><strong>{raw.length}</strong> raw candidates</span>
        <span><strong>{analysis.requirements.length}</strong> consolidated</span>
        <span><strong>{analysis.duplicate_groups.length}</strong> duplicate groups</span>
        <span><strong>{blocking}</strong> blocking critiques</span>
        <span><strong>{runs.filter((run) => run.status === 'failed').length}</strong> role failures</span>
        <span><strong>{contexts.filter(hasCustomContext).length}</strong> custom contexts</span>
        <span><strong>{trace.length}</strong> trace events</span>
      </div>

      <div className="agent-run-grid">
        {runs.map((run) => (
          <AgentRunCard key={run.id} run={run} verified={verifiedByRole.get(run.role_id)} />
        ))}
      </div>

      <details className="workflow-trace-ledger" open>
        <summary>Ordered workflow trace ledger · {trace.length} events</summary>
        <p>Each event records dependencies, exact input/output identifiers, the context hash, prompt version, model, and status.</p>
        <ol>
          {trace.map((event) => (
            <li key={event.id}>
              <span>{event.sequence}</span>
              <div>
                <strong>{event.role_id} · {event.event_type.split('_').join(' ')}</strong>
                <small>{event.phase} · {event.timestamp ?? 'timestamp unavailable'} · context {shortHash(event.context_hash)}</small>
                <small>
                  depends on {event.dependency_role_ids.join(', ') || 'frozen input'} · {event.input_artifact_ids.length} input id(s) → {event.output_artifact_ids.length} output id(s)
                </small>
              </div>
            </li>
          ))}
        </ol>
      </details>
    </section>
  );
}

function AgentRunCard({ run, verified }: { run: AgentRunRecord; verified?: { verified: number; total: number } }) {
  const verifiedPercent = verified?.total ? Math.round(100 * verified.verified / verified.total) : null;
  const role = ALL_AGENT_ROLES.find((item) => item.id === run.role_id);
  const context = run.context_trace;
  return (
    <article className={`agent-run-card agent-run-card--${run.status}`}>
      <div><strong>{role ? `${role.order}. ${role.label}` : run.role_id}</strong><span>{run.status}{run.cache_hit ? ' · cache hit' : ''}</span></div>
      <small>{run.role_id} · {run.phase}</small>
      <small>{run.candidate_requirement_ids.length} candidate(s){verifiedPercent === null ? '' : ` · ${verifiedPercent}% verified evidence`}</small>
      <small>{run.model_id ?? 'no model'} · {run.prompt_version ?? 'no prompt version'}</small>
      <small>depends on: {run.dependency_role_ids.join(', ') || 'frozen inputs'}</small>
      <small>{run.input_artifact_ids.length} input id(s) → {run.output_artifact_ids.length} output id(s)</small>
      {context ? (
        <details className="agent-context-trace">
          <summary>Context package · {shortHash(context.context_hash)}</summary>
          <dl>
            <div><dt>Shared corpus</dt><dd>{context.shared_evidence_unit_ids.length} evidence unit(s)</dd></div>
            <div><dt>Background</dt><dd>{context.background || 'Role prompt only'}</dd></div>
            <div><dt>Queries</dt><dd>{context.rag_queries.join(' · ') || 'None'}</dd></div>
            <div><dt>Retrieved</dt><dd>{context.retrieved_items.length} chunk(s)</dd></div>
          </dl>
          {context.retrieved_items.map((item) => (
            <details className="retrieved-context-item" key={item.id}>
              <summary>{item.source_ref} · score {item.score} · {item.eligible_as_evidence ? 'corpus evidence' : 'supplemental only'}</summary>
              <small>{item.id} · hash {shortHash(item.content_hash)}{item.evidence_unit_id ? ` · ${item.evidence_unit_id}` : ''}</small>
              <pre>{item.content}</pre>
            </details>
          ))}
          <p className="agent-context-trace__boundary">{context.boundary_notice}</p>
        </details>
      ) : null}
      {run.warnings.length ? <details><summary>{run.warnings.length} warning(s)</summary>{run.warnings.map((warning) => <p key={warning}>{warning}</p>)}</details> : null}
    </article>
  );
}

function hasCustomContext(context: NonNullable<AnalysisResponse['agent_contexts']>[number]) {
  return Boolean(context.background || context.rag_queries.length || context.retrieved_items.length);
}

function shortHash(value?: string | null) {
  return value ? value.slice(0, 12) : 'unavailable';
}
