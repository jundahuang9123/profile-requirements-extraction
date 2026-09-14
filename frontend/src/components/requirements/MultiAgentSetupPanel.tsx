import type { Dispatch, SetStateAction } from 'react';

import type { AgentContextInput, ArtifactPayload, StudyMode } from '../../lib/requirementApi';
import { AgentProcessGraph } from './AgentProcessGraph';
import { ALL_AGENT_ROLES, EXTRACTION_ROLES } from './agentRoles';

type Props = {
  studyMode: StudyMode;
  setStudyMode: (mode: StudyMode) => void;
  preset: 'full_15' | 'extraction_12' | 'pilot_core';
  setPreset: (preset: 'full_15' | 'extraction_12' | 'pilot_core') => void;
  selectedRoleIds: string[];
  setSelectedRoleIds: (ids: string[]) => void;
  agentContexts: Record<string, AgentContextInput>;
  setAgentContexts: Dispatch<SetStateAction<Record<string, AgentContextInput>>>;
  artifacts: ArtifactPayload[];
};

const PILOT_EXTRACTION_IDS = new Set([
  'standards_conformance',
  'dcat_reuse',
  'construction_domain',
  'consumer_discovery',
  'minimality_scope',
]);

export function MultiAgentSetupPanel({
  studyMode,
  setStudyMode,
  preset,
  setPreset,
  selectedRoleIds,
  setSelectedRoleIds,
  agentContexts,
  setAgentContexts,
  artifacts,
}: Props) {
  const defaultIds = preset === 'pilot_core'
    ? EXTRACTION_ROLES.filter((role) => PILOT_EXTRACTION_IDS.has(role.id)).map((role) => role.id)
    : EXTRACTION_ROLES.map((role) => role.id);
  const effective = new Set(selectedRoleIds.length ? selectedRoleIds : defaultIds);
  const configuredContextRoleIds = Object.values(agentContexts)
    .filter(hasConfiguredContext)
    .map((context) => context.role_id);
  const artifactNames = Array.from(new Set(artifacts.map((artifact) => artifact.name)));

  const toggle = (id: string) => {
    const next = new Set(effective);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelectedRoleIds(EXTRACTION_ROLES.map((role) => role.id).filter((roleId) => next.has(roleId)));
  };
  const updateContext = (roleId: string, patch: Partial<AgentContextInput>) => {
    setAgentContexts((current) => ({
      ...current,
      [roleId]: { ...emptyContext(roleId), ...current[roleId], ...patch },
    }));
  };

  return (
    <section className="multi-agent-setup" aria-label="Role-conditioned panel setup">
      <div className="multi-agent-setup__controls">
        <label>
          Study mode
          <select onChange={(event) => setStudyMode(event.target.value as StudyMode)} value={studyMode}>
            <option value="formative">Formative</option>
            <option value="summative">Summative</option>
          </select>
        </label>
        <label>
          Panel preset
          <select
            onChange={(event) => {
              setPreset(event.target.value as Props['preset']);
              setSelectedRoleIds([]);
            }}
            value={preset}
          >
            <option value="full_15">Full 15 (formal condition)</option>
            <option value="pilot_core">Pilot core (reduced cost)</option>
            <option value="extraction_12">Extraction 12 (no synthesis)</option>
          </select>
        </label>
        <div className="multi-agent-setup__context-count">
          <strong>{configuredContextRoleIds.length}</strong>
          <span>custom context package(s)</span>
        </div>
      </div>

      <AgentProcessGraph configuredContextRoleIds={configuredContextRoleIds} />

      <div className="agent-context-boundary">
        <strong>Traceability boundary</strong>
        <p>
          Every role receives the frozen corpus, its versioned role prompt, and the context package configured below.
          Pasted background/RAG can guide interpretation, but only verified corpus evidence can substantiate a requirement.
        </p>
      </div>

      <div className="agent-context-list">
        {ALL_AGENT_ROLES.map((role) => {
          const context = agentContexts[role.id] ?? emptyContext(role.id);
          const active = role.phase === 'extraction'
            ? effective.has(role.id)
            : preset !== 'extraction_12';
          return (
            <details className={`agent-context-card agent-context-card--${role.phase}`} key={role.id}>
              <summary>
                {role.phase === 'extraction' ? (
                  <input
                    aria-label={`Enable ${role.label}`}
                    checked={active}
                    onChange={() => toggle(role.id)}
                    onClick={(event) => event.stopPropagation()}
                    type="checkbox"
                  />
                ) : <span className="agent-context-card__required">{active ? 'active' : 'not in preset'}</span>}
                <span className="agent-context-card__number">{role.order}</span>
                <span><strong>{role.label}</strong><small>{role.phase} · {role.id}</small></span>
                {hasConfiguredContext(context) ? <em>custom context</em> : <em>role defaults</em>}
              </summary>
              <div className="agent-context-card__body">
                <p>{role.purpose}</p>
                <div className="agent-context-actions">
                  <button onClick={() => updateContext(role.id, { background: role.suggestedBackground })} type="button">
                    Use suggested background
                  </button>
                  <button onClick={() => updateContext(role.id, emptyContext(role.id))} type="button">Clear context</button>
                </div>
                <label>
                  Role background and interpretive guidance
                  <textarea
                    aria-label={`${role.label} background`}
                    onChange={(event) => updateContext(role.id, { background: event.target.value })}
                    placeholder={role.suggestedBackground}
                    rows={4}
                    value={context.background}
                  />
                </label>
                <label>
                  Retrieval queries (one per line)
                  <textarea
                    aria-label={`${role.label} RAG queries`}
                    onChange={(event) => updateContext(role.id, {
                      rag_queries: event.target.value.split('\n').map((line) => line.trim()).filter(Boolean),
                    })}
                    placeholder="DCAT-AP obligation dataset licence\nconstruction lifecycle discovery"
                    rows={3}
                    value={context.rag_queries.join('\n')}
                  />
                </label>
                <label>
                  Supplemental RAG material
                  <textarea
                    aria-label={`${role.label} supplemental RAG material`}
                    onChange={(event) => updateContext(role.id, { rag_material: event.target.value })}
                    placeholder="Paste role-specific notes or reference excerpts. Separate chunks with a blank line. This material is non-evidentiary unless it is also part of the declared corpus."
                    rows={5}
                    value={context.rag_material}
                  />
                </label>
                <div className="agent-context-retrieval-settings">
                  <label>
                    Top-K chunks
                    <input
                      aria-label={`${role.label} RAG top K`}
                      max={20}
                      min={1}
                      onChange={(event) => updateContext(role.id, { rag_top_k: Number(event.target.value) })}
                      type="number"
                      value={context.rag_top_k}
                    />
                  </label>
                  <div>
                    <strong>Retrieve from uploaded corpus artifacts</strong>
                    {artifactNames.length ? artifactNames.map((name) => (
                      <label className="agent-context-artifact" key={name}>
                        <input
                          checked={context.rag_artifact_names.includes(name)}
                          onChange={() => {
                            const selected = new Set(context.rag_artifact_names);
                            if (selected.has(name)) selected.delete(name); else selected.add(name);
                            updateContext(role.id, { rag_artifact_names: Array.from(selected) });
                          }}
                          type="checkbox"
                        />
                        {name}
                      </label>
                    )) : <small>Add files above to make corpus artifacts available for role-specific retrieval.</small>}
                  </div>
                </div>
              </div>
            </details>
          );
        })}
      </div>
      {selectedRoleIds.length && selectedRoleIds.length !== 12 ? (
        <p className="input-boundary-note">Custom extraction-role selection is exported explicitly and is not reported as the full-panel condition.</p>
      ) : null}
    </section>
  );
}

function emptyContext(roleId: string): AgentContextInput {
  return {
    role_id: roleId,
    background: '',
    rag_queries: [],
    rag_artifact_names: [],
    rag_material: '',
    rag_top_k: 6,
  };
}

function hasConfiguredContext(context: AgentContextInput) {
  return Boolean(
    context.background.trim()
    || context.rag_queries.length
    || context.rag_artifact_names.length
    || context.rag_material.trim(),
  );
}
