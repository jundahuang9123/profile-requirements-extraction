import { FormEvent, useEffect, useState } from 'react';

type Settings = { provider: string; preset?: string; model: string; base_url?: string; credential_configured: boolean; source: string };
type Discovery = { connected: boolean; models: string[]; selected_model: string };

const urls: Record<string, string> = {
  openai: 'https://api.openai.com/v1',
  kiconnect: 'https://chat.kiconnect.nrw/api/v1',
  ollama: 'http://localhost:11434/v1',
  anthropic: '',
  custom: '',
  disabled: '',
};
const defaults: Record<string, string> = {
  openai: 'gpt-5.5',
  kiconnect: 'inferenz-gpt-oss-120b',
  ollama: 'blackboard-qwen27b:latest',
  anthropic: 'claude-opus-4-8',
  custom: '',
  disabled: '',
};

async function request<T>(path: string, payload?: unknown): Promise<T> {
  const response = await fetch(`/api/rq1/v2${path}`, payload === undefined ? undefined : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Provider settings request failed.');
  return body as T;
}

export function ProviderSettings({ onStatus }: { onStatus: (status: string) => void }) {
  const [provider, setProvider] = useState('kiconnect');
  const [model, setModel] = useState(defaults.kiconnect);
  const [baseUrl, setBaseUrl] = useState(urls.kiconnect);
  const [apiKey, setApiKey] = useState('');
  const [saved, setSaved] = useState<Settings | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    void request<Settings>('/provider-settings').then(value => {
      setSaved(value);
      const preset = inferPreset(value);
      setProvider(preset);
      setModel(value.model === 'disabled' ? (defaults[preset] || '') : value.model);
      setBaseUrl(value.base_url || urls[preset] || '');
    }).catch(cause => setError(cause instanceof Error ? cause.message : String(cause)));
  }, []);

  const changeProvider = (value: string) => {
    setProvider(value);
    setApiKey('');
    setBaseUrl(urls[value] || '');
    setModel(defaults[value] || '');
    setModels([]);
    setError('');
  };

  const save = async (event?: FormEvent) => {
    event?.preventDefault();
    setBusy(true); setError('');
    try {
      const value = await request<Settings>('/provider-settings', {
        provider, model, base_url: baseUrl, api_key: apiKey, clear_api_key: false,
      });
      setSaved(value); setApiKey(''); onStatus(`Model settings saved for ${providerLabel(provider)}.`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };

  const discover = async () => {
    setBusy(true); setError('');
    try {
      const value = await request<Discovery>('/provider-models', {});
      setModels(value.models); setModel(current => value.models.includes(current) ? current : value.selected_model);
      onStatus(value.models.length ? `Loaded ${value.models.length} model IDs from ${providerLabel(provider)}.` : 'Provider connected; its model list was empty. Enter a model ID manually.');
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };

  return <details className="provider-settings">
    <summary>Model provider · {saved ? `${providerLabel(inferPreset(saved))} · ${saved.model}` : 'choose a provider'}</summary>
    <form onSubmit={save}>
      <p className="workflow-muted">Select where RQ1 sends model requests. Keys are held in this running service only; they are not saved in the browser or in run exports. Restarting the service clears a key entered here.</p>
      <div className="provider-settings-grid">
        <label>Provider<select value={provider} onChange={event => changeProvider(event.target.value)}>
          <option value="kiconnect">KI:connect</option><option value="ollama">Local Ollama</option><option value="openai">OpenAI API</option><option value="anthropic">Anthropic API</option><option value="custom">Other OpenAI-compatible endpoint</option><option value="disabled">No live model · offline only</option>
        </select></label>
        {provider !== 'disabled' && <label>Model ID<input required list="rq1-model-options" value={model} onChange={event => setModel(event.target.value)} placeholder="Choose or enter a model ID" /><datalist id="rq1-model-options">{models.map(item => <option key={item} value={item} />)}</datalist></label>}
        {['ollama', 'custom'].includes(provider) && <label>Endpoint base URL<input required value={baseUrl} onChange={event => setBaseUrl(event.target.value)} placeholder={provider === 'ollama' ? 'http://host.docker.internal:11434/v1' : 'https://your-endpoint/v1'} /></label>}
        {provider !== 'disabled' && provider !== 'ollama' && <label>API key<input type="password" autoComplete="new-password" value={apiKey} onChange={event => setApiKey(event.target.value)} placeholder={saved?.credential_configured && provider === saved.preset ? 'Saved for this session · leave blank to keep' : 'Paste provider key'} /></label>}
      </div>
      <div className="provider-settings-actions">
        <button type="submit" disabled={busy}>{provider === 'disabled' ? 'Use offline mode' : 'Save provider'}</button>
        {provider !== 'disabled' && <button type="button" disabled={busy || !saved || provider !== inferPreset(saved) || model !== saved.model || (['ollama', 'custom'].includes(provider) && baseUrl !== saved.base_url)} onClick={() => void discover()}>Load available models</button>}
        <span className="workflow-muted">{saved ? `${saved.credential_configured ? 'Credential configured' : 'No API key detected'} · ${saved.source === 'session' ? 'session setting' : 'environment setting'}` : 'Loading current settings…'}</span>
      </div>
      {error && <p className="workflow-error" role="alert">{error}</p>}
      {models.length > 0 && <p className="workflow-muted">Loaded model IDs are suggestions. You can still enter any model ID accepted by the provider.</p>}
    </form>
  </details>;
}

function providerLabel(value: string) {
  return ({ kiconnect: 'KI:connect', ollama: 'Local Ollama', openai: 'OpenAI', anthropic: 'Anthropic', custom: 'Custom endpoint', disabled: 'offline mode', 'openai-compatible': 'OpenAI-compatible provider' } as Record<string, string>)[value] || value;
}

function inferPreset(value: Settings) {
  if (value.provider === 'disabled') return 'disabled';
  if (value.provider === 'anthropic') return 'anthropic';
  const match = Object.entries(urls).find(([key, url]) => ['openai', 'kiconnect', 'ollama'].includes(key) && url === value.base_url);
  return match?.[0] || 'custom';
}
