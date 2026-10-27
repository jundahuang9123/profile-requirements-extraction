import { useEffect, useState } from 'react';
import { WorkflowWorkbench } from './components/WorkflowWorkbench';
import { ProviderSettings } from './components/ProviderSettings';
import { ResultViewer } from './components/ResultViewer';
import { linkFromHash } from './lib/traceApi';
export function App() {
  const [status, setStatus] = useState('Ready. Add domain evidence and user tasks to begin.');
  // A trace link opened in its own tab shows only the saved result it points to.
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const change = () => setHash(window.location.hash);
    window.addEventListener('hashchange', change);
    return () => window.removeEventListener('hashchange', change);
  }, []);
  const link = linkFromHash(hash);
  if (link) return <main className="result-page"><ResultViewer link={link} /></main>;
  return <>
    <header className="rq1-header"><div><strong>Profile Requirements Extraction</strong><span>Evidence · requirements · review</span></div><a href="https://github.com/U0iS112/654321" target="_blank" rel="noreferrer">Based on Sebastian’s Blackboard ↗</a></header>
    <ProviderSettings onStatus={setStatus} />
    <WorkflowWorkbench onStatus={setStatus} />
    <footer className="rq1-status" role="status" aria-live="polite">{status}</footer>
  </>;
}
