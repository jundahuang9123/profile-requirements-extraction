import { useState } from 'react';
import { RequirementWorkbench } from './components/RequirementWorkbench';
import { WorkflowWorkbench } from './components/WorkflowWorkbench';
export function App() {
  const [status, setStatus] = useState('Ready. Add domain evidence and user tasks to begin.');
  const [view, setView] = useState('workflow');
  return <>
    <header className="rq1-header"><div><strong>Profile Requirements Extraction</strong><span>Evidence · requirements · review</span></div><a href="https://github.com/U0iS112/654321" target="_blank" rel="noreferrer">Based on Sebastian’s Blackboard ↗</a></header>
    <nav className="workflow-nav"><button aria-pressed={view === 'workflow'} onClick={() => setView('workflow')}>Persistent nine-stage workflow</button><button aria-pressed={view === 'legacy'} onClick={() => setView('legacy')}>Original study workbench · v1</button></nav>
    {view === 'workflow' ? <WorkflowWorkbench onStatus={setStatus} /> : <RequirementWorkbench initialView="requirements" onStatus={setStatus} />}
    <footer className="rq1-status" role="status" aria-live="polite">{status}</footer>
  </>;
}
