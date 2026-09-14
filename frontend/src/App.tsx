import { useState } from 'react';
import { RequirementWorkbench } from './components/RequirementWorkbench';
export function App() {
  const [status, setStatus] = useState('Ready. Add domain evidence and user tasks to begin.');
  return <>
    <header className="rq1-header"><div><strong>RQ1 Blackboard</strong><span>Evidence · requirements · review</span></div><a href="https://github.com/U0iS112/654321" target="_blank" rel="noreferrer">Based on Sebastian’s Blackboard ↗</a></header>
    <RequirementWorkbench initialView="requirements" onStatus={setStatus} />
    <footer className="rq1-status" role="status" aria-live="polite">{status}</footer>
  </>;
}
