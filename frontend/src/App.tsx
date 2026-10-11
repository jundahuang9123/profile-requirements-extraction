import { useState } from 'react';
import { WorkflowWorkbench } from './components/WorkflowWorkbench';
import { ProviderSettings } from './components/ProviderSettings';
export function App() {
  const [status, setStatus] = useState('Ready. Add domain evidence and user tasks to begin.');
  return <>
    <header className="rq1-header"><div><strong>Profile Requirements Extraction</strong><span>Evidence · requirements · review</span></div><a href="https://github.com/U0iS112/654321" target="_blank" rel="noreferrer">Based on Sebastian’s Blackboard ↗</a></header>
    <ProviderSettings onStatus={setStatus} />
    <WorkflowWorkbench onStatus={setStatus} />
    <footer className="rq1-status" role="status" aria-live="polite">{status}</footer>
  </>;
}
