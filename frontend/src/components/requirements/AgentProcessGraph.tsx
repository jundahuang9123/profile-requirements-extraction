import type { AgentContextTrace, AgentRunRecord } from '../../lib/requirementApi';
import { ALL_AGENT_ROLES, EXTRACTION_ROLES, SYNTHESIS_ROLES } from './agentRoles';

type Props = {
  runs?: AgentRunRecord[];
  contexts?: AgentContextTrace[];
  configuredContextRoleIds?: string[];
};

export function AgentProcessGraph({ runs = [], contexts = [], configuredContextRoleIds = [] }: Props) {
  const runByRole = new Map(runs.map((run) => [run.role_id, run]));
  const contextRoleIds = new Set([
    ...configuredContextRoleIds,
    ...contexts
      .filter((context) => context.background || context.rag_queries.length || context.retrieved_items.length)
      .map((context) => context.role_id),
  ]);
  const consolidation = SYNTHESIS_ROLES.find((role) => role.phase === 'consolidation');
  const critics = SYNTHESIS_ROLES.filter((role) => role.phase === 'criticism');

  return (
    <section className="agent-process" aria-label="Traceable 15-agent process">
      <header>
        <div>
          <h4>Bounded interaction and handoff graph</h4>
          <p>Agents 1–12 run independently. Their preserved outputs flow to Agent 13, then Agents 14–15 audit the same consolidated set.</p>
        </div>
        <span>fan-out → fan-in → independent critique</span>
      </header>

      <div className="agent-process__flow">
        <ProcessNode className="agent-process__source" title="Frozen inputs" meta="corpus · tasks · per-role context" />
        <FlowArrow label="same corpus + role package" />

        <div className="agent-process__phase agent-process__phase--extraction">
          <PhaseHeader step="Phase 1" title="12 independent extraction agents" note="No agent sees another extraction output" />
          <div className="agent-process__role-grid">
            {EXTRACTION_ROLES.map((role) => (
              <RoleNode
                contextConfigured={contextRoleIds.has(role.id)}
                key={role.id}
                role={role}
                run={runByRole.get(role.id)}
              />
            ))}
          </div>
        </div>

        <FlowArrow label="raw candidate lists + evidence links" />

        {consolidation ? (
          <div className="agent-process__phase agent-process__phase--single">
            <PhaseHeader step="Phase 2" title="One consolidation pass" note="Merge, retain, discard unsupported, or flag conflict" />
            <RoleNode
              contextConfigured={contextRoleIds.has(consolidation.id)}
              role={consolidation}
              run={runByRole.get(consolidation.id)}
            />
          </div>
        ) : null}

        <FlowArrow label="canonical candidates + complete provenance" />

        <div className="agent-process__phase agent-process__phase--critics">
          <PhaseHeader step="Phase 3" title="Two independent critics" note="Findings are appended; requirements are not silently mutated" />
          <div className="agent-process__critic-grid">
            {critics.map((role) => (
              <RoleNode
                contextConfigured={contextRoleIds.has(role.id)}
                key={role.id}
                role={role}
                run={runByRole.get(role.id)}
              />
            ))}
          </div>
        </div>

        <FlowArrow label="machine output + critic findings" />

        <div className="agent-process__human-path">
          <ProcessNode title="Freeze evaluation package" meta="immutable hashes + full trace" />
          <span aria-hidden="true">→</span>
          <ProcessNode title="3 independent human experts" meta="ratings held apart until close" />
          <span aria-hidden="true">→</span>
          <ProcessNode title="Aggregate · revise · consensus" meta="only accepted requirements enter RQ2" />
        </div>
      </div>
      <p className="agent-process__legend">
        Role prompting supplies an analytical perspective, not decision authority. Supplemental RAG is recorded separately from citable corpus evidence.
      </p>
    </section>
  );
}

function PhaseHeader({ step, title, note }: { step: string; title: string; note: string }) {
  return <header><span>{step}</span><div><strong>{title}</strong><small>{note}</small></div></header>;
}

function RoleNode({
  role,
  run,
  contextConfigured,
}: {
  role: (typeof ALL_AGENT_ROLES)[number];
  run?: AgentRunRecord;
  contextConfigured: boolean;
}) {
  const status = run?.status ?? 'configured';
  return (
    <article className={`agent-process__role agent-process__role--${status}`} title={role.purpose}>
      <span>{role.order}</span>
      <div><strong>{role.label}</strong><small>{role.id}</small></div>
      <div className="agent-process__badges">
        <em>{status}{run?.cache_hit ? ' · cache' : ''}</em>
        {contextConfigured ? <em>custom context</em> : <em>role defaults</em>}
      </div>
    </article>
  );
}

function ProcessNode({ title, meta, className = '' }: { title: string; meta: string; className?: string }) {
  return <article className={`agent-process__node ${className}`}><strong>{title}</strong><small>{meta}</small></article>;
}

function FlowArrow({ label }: { label: string }) {
  return <div className="agent-process__arrow" aria-label={label}><span>↓</span><small>{label}</small></div>;
}
