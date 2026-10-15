import { useState } from 'react';
import { workflowApi } from '../lib/workflowApi';

const steps = [
  ['role_selection', 'Stakeholder role selection'], ['extraction', 'Independent extraction'],
  ['proposal_support', 'Proposal support'], ['grouping', 'Grouping'],
  ['writer', 'Need writer'], ['rewrite_critic', 'Rewrite critic'],
  ['membership', 'Group membership'], ['classification', 'Base classification'],
  ['use_case_linker', 'Use-case linking'], ['link_critic', 'Use-case link critic'],
  ['assessment', 'Support assessment'], ['discussion', 'Discussion'],
];

export function StepModelsSettings({ value, onChange, saved = false }: {
  value: Record<string, string>; onChange?: (value: Record<string, string>) => void; saved?: boolean;
}) {
  const [models, setModels] = useState<string[]>([]);
  const [configured, setConfigured] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const load = async () => {
    setLoading(true); setError('');
    try {
      const result = await workflowApi<{ generation_models: string[]; selected_model: string }>('/provider-models', {});
      setModels(result.generation_models); setConfigured(result.selected_model);
    } catch (error) { setError(error instanceof Error ? error.message : 'Could not load models.'); }
    finally { setLoading(false); }
  };
  return <details className="workflow-step-models">
    <summary>{saved ? 'Saved models per step' : 'Advanced · model per step'}</summary>
    {saved ? <p>These model choices were frozen when this run was created. Reused extraction keeps its original model audit.</p>
      : <><p>Leave every step on the configured model, or choose different models for selected steps. Choices are checked and saved when you create the run. Loading the list does not run a model.</p>
        <button type="button" disabled={loading} onClick={() => void load()}>{loading ? 'Loading models…' : 'Load provider models'}</button>
        {error && <p className="workflow-error" role="alert">{error}</p>}</>}
    {steps.map(([step, label]) => <label key={step}>{label}{saved ? <span>{value[step] ?? 'Configured model (legacy run)'}</span>
      : <select value={value[step] ?? ''} onChange={event => {
        const next = { ...value };
        if (event.target.value) next[step] = event.target.value; else delete next[step];
        onChange?.(next);
      }}>
        <option value="">Configured model{configured ? ` · ${configured}` : ''}</option>
        {value[step] && !models.includes(value[step]) && <option value={value[step]}>{value[step]} · load list to verify</option>}
        {models.map(model => <option key={model} value={model}>{model}</option>)}
      </select>}</label>)}
  </details>;
}
