import { useState } from 'react';
import { workflowApi } from '../lib/workflowApi';

const steps = [
  ['role_selection', 'Stakeholder role selection'], ['extraction', 'Independent extraction'],
  ['proposal_support', 'Proposal support'], ['grouping', 'Grouping'],
  ['writer', 'Need writer'], ['rewrite_critic', 'Rewrite critic'],
  ['membership', 'Group membership'], ['classification', 'Base classification'],
  ['dataset_categories', 'Dataset categories from sources'], ['profile_scope', 'Profile scope and category applicability'],
  ['selection', 'Compact coverage selection'],
  ['use_case_linker', 'Use-case linking'], ['link_critic', 'Use-case link critic'],
  ['assessment', 'Support assessment'], ['discussion', 'Discussion default'],
  ['stakeholder_review', 'Stakeholder positions and responses'], ['mediation', 'Mediator'], ['mediation_check', 'Independent mediation check'],
];

export function StepModelsSettings({ value, onChange, saved = false, options = {}, onOptionsChange }: {
  value: Record<string, string>; onChange?: (value: Record<string, string>) => void; saved?: boolean;
  options?: Record<string, { reasoning_effort?: string | null }>; onOptionsChange?: (value: Record<string, { reasoning_effort?: string | null }>) => void;
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
  const substep = (step: string) => ['stakeholder_review','mediation','mediation_check'].includes(step);
  const effectiveModel = (step: string) => value[step] || (substep(step) ? value.discussion : '') || configured;
  const efforts = (step: string) => { const model = effectiveModel(step).toLowerCase(); return model.includes('gpt-oss') ? ['low','medium','high'] : /qwen3[.-]8/.test(model) ? ['low','medium','xhigh'] : []; };
  return <details className="workflow-step-models">
    <summary>{saved ? 'Saved models per step' : 'Advanced · model per step'}</summary>
    {saved ? <p>These model choices were frozen when this run was created. Reused extraction keeps its original model audit.</p>
      : <><p>Leave every step on the configured model, or choose different models for selected steps. Choices are checked and saved when you create the run. Loading the list does not run a model.</p>
        <button type="button" disabled={loading} onClick={() => void load()}>{loading ? 'Loading models…' : 'Load provider models'}</button>
        <button type="button" disabled={!models.includes('inferenz-gpt-oss-120b') || !models.includes('inferenz-qwen3-8-27b')} onClick={() => { onChange?.(Object.fromEntries(steps.map(([step]) => [step, step === 'mediation' ? 'inferenz-qwen3-8-27b' : 'inferenz-gpt-oss-120b']))); onOptionsChange?.({ mediation: { reasoning_effort: 'low' } }); }}>Use GPT-OSS with Qwen mediator</button><p>The hybrid preset is available after both exact model IDs are verified in the provider list. Qwen quality and output budget still need a controlled pilot.</p>
        {error && <p className="workflow-error" role="alert">{error}</p>}</>}
    {steps.map(([step, label]) => <label key={step}>{label}{saved ? <span>{value[step] ?? 'Configured model (legacy run)'}</span>
      : <select value={value[step] ?? ''} onChange={event => {
        const next = { ...value };
        if (event.target.value) next[step] = event.target.value; else delete next[step];
        onChange?.(next);
      }}>
        <option value="">{substep(step) ? 'Discussion default' : 'Configured model'}{effectiveModel(step) ? ` · ${effectiveModel(step)}` : ''}</option>
        {value[step] && !models.includes(value[step]) && <option value={value[step]}>{value[step]} · load list to verify</option>}
        {models.map(model => <option key={model} value={model}>{model}</option>)}
      </select>}{saved ? (options[step]?.reasoning_effort && <small>Reasoning: {options[step].reasoning_effort}</small>) : onOptionsChange && <select aria-label={`${label} reasoning effort`} value={options[step]?.reasoning_effort ?? ''} onChange={event => { const next = { ...options }; if (event.target.value) next[step] = { reasoning_effort: event.target.value }; else delete next[step]; onOptionsChange(next); }}><option value="">Provider default reasoning</option>{efforts(step).map(effort => <option key={effort}>{effort}</option>)}</select>}</label>)}
  </details>;
}
