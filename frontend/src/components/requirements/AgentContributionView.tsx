import type { CandidateRequirement, CritiqueFinding } from '../../lib/requirementApi';

export function AgentContributionView({ requirement }: { requirement: CandidateRequirement }) {
  const contributions = requirement.agent_contributions ?? [];
  if (!contributions.length) return null;
  return (
    <details className="agent-contributions">
      <summary>Raw agent contributions ({requirement.consolidated_from?.length ?? contributions.length})</summary>
      {contributions.filter((item) => item.contribution_kind !== 'challenged').map((item, index) => (
        <article key={`${item.agent_run_id}-${item.source_candidate_id}-${index}`}>
          <strong>{item.role_id}</strong>
          <small>{item.contribution_kind} · {item.source_candidate_id}</small>
          {item.statement ? <p>{item.statement}</p> : null}
          <small>{item.evidence_unit_ids.length} evidence link(s)</small>
        </article>
      ))}
    </details>
  );
}

export function CritiqueFindingsView({ findings }: { findings: CritiqueFinding[] }) {
  if (!findings.length) return null;
  return (
    <section className="critique-findings">
      <h4>Independent critic findings</h4>
      {findings.map((finding) => (
        <article className={`critique-finding critique-finding--${finding.severity}`} key={finding.id}>
          <div><strong>{finding.category}</strong><span>{finding.severity} · {finding.critic_role_id}</span></div>
          <p>{finding.message}</p>
          {finding.suggested_action ? <small>{finding.suggested_action}</small> : null}
        </article>
      ))}
    </section>
  );
}
