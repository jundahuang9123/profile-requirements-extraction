import { MouseEvent, ReactNode, useEffect, useState } from 'react';
import { Run, workflowApi } from '../lib/workflowApi';
import { NeedTrace, TraceLink, resolvePointer, resultHref } from '../lib/traceApi';

const humanLabel = (value: string) => value.replace(/_/g, ' ');
const short = (text: string | null | undefined, limit: number) => { const value = (text ?? '').replace(/\s+/g, ' ').trim(); return value.length > limit ? `${value.slice(0, limit)}…` : value; };

// A link to a saved result: opens beside the trace; a middle click or "open in new tab" opens it on its own page.
function ResultLink({ link, open, children }: { link: TraceLink; open: (link: TraceLink) => void; children?: ReactNode }) {
  const click = (event: MouseEvent) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault(); open(link);
    // Opening the result narrows the page; the link the reviewer followed stays in view.
    const anchor = event.currentTarget;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const box = anchor.getBoundingClientRect();
      if (box.top < 0 || box.bottom > window.innerHeight - 80) anchor.scrollIntoView({ block: 'center' });
    }));
  };
  return <a className="trace-link" href={resultHref(link)} onClick={click} title={`${link.label} · ${link.file}${link.pointer}`}>{children ?? link.label}</a>;
}

function Links({ links, open }: { links: TraceLink[]; open: (link: TraceLink) => void }) {
  return <span className="trace-links">{links.map((link, i) => <ResultLink key={i} link={link} open={open} />)}</span>;
}

// The chain behind one need (rq1-need-trace-v1): the reviewer card, every phrase linked to the saved result it
// reports, and the full chain with a link on every entry.
export function NeedTraceView({ run, revisionId, open }: { run: Run; revisionId: string; open: (link: TraceLink) => void }) {
  const [trace, setTrace] = useState<NeedTrace | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true; setTrace(null); setError('');
    workflowApi<NeedTrace>(`/runs/${run.run_id}/needs/${revisionId}/trace`).then(value => { if (active) setTrace(value); })
      .catch(cause => { if (active) setError(cause instanceof Error ? cause.message : String(cause)); });
    return () => { active = false; };
  }, [run.run_id, run.version, revisionId]);
  if (error) return <p className="workflow-error">Trace unavailable: {error}</p>;
  if (!trace) return <p className="workflow-muted">Loading the trace…</p>;
  const role = (id: string) => run.role_manifest?.selected_roles.find(item => item.role_id === id)?.label ?? humanLabel(id);
  const first = (ref: string | null) => {
    const entry = ref ? resolvePointer(trace, ref) as { links?: TraceLink[] } | undefined : undefined;
    return entry?.links?.[0];
  };
  return <section className="need-trace">
    <h3>Where this need comes from {trace.completeness.solid ? <span className="trace-solid">chain complete</span> : <span className="trace-incomplete">chain incomplete</span>}</h3>
    <dl className="trace-card">{trace.summary_parts.map(line => <div key={line.label}><dt>{line.label}</dt><dd>{line.parts.map((part, i) => {
      const link = first(part.ref);
      return link ? <ResultLink key={i} link={link} open={open}>{part.text}</ResultLink> : <span key={i}>{part.text}</span>;
    })}</dd></div>)}</dl>
    <p className="workflow-muted">Each link opens the saved result of the step that made it, at the highlighted row.</p>
    <details><summary>Full chain · {trace.sources.length} quotations · {trace.origin.length} extracted proposals · {trace.decisions.length} decisions · {trace.discussion.length} discussions</summary>
      <ol className="trace-chain">
        <li><strong>Need</strong> {trace.statement} <small>{trace.revision_id} · {humanLabel(trace.state)}</small> <Links links={trace.links} open={open} /></li>
        {trace.sources.map((source, i) => <li key={`s${i}`}><strong>Quotation</strong> {source.source ?? source.evidence_id}: “{short(source.quote, 220)}”{!source.found && <span className="trace-incomplete"> not found in its unit</span>} <Links links={source.links} open={open} /></li>)}
        {trace.origin.map(origin => <li key={origin.observation_id}><strong>Extracted</strong> {origin.agent_name ?? origin.agent ?? 'the discussion'}: {short(origin.statement, 220) || origin.observation_id}{origin.prompt_version && <small> · {origin.prompt_version}{origin.model ? ` · ${origin.model}` : ''}</small>} <Links links={origin.links} open={open} /></li>)}
        {trace.decisions.map((decision, i) => <li key={`d${i}`}><strong>{humanLabel(decision.step)}</strong> {decision.decision ?? '—'}{decision.reason && <>: {short(decision.reason, 260)}</>} <small>{decision.revision_id}{decision.call_link !== 'not_applicable' ? ` · model call ${decision.call_link}` : ''}</small> <Links links={decision.links} open={open} /></li>)}
        {trace.discussion.map(item => <li key={item.case_id}><strong>Discussion</strong> {item.case_id}{item.stop_reason && ` · stopped: ${humanLabel(item.stop_reason)}`} <Links links={item.links.slice(0, 1)} open={open} />
          {item.links.length > 1 && <details><summary>{item.links.length - 1} model calls of this discussion</summary><Links links={item.links.slice(1)} open={open} /></details>}
          <ul>{item.outcomes.map((outcome, i) => <li key={`o${i}`}>{outcome.action} ({outcome.status}): {short(outcome.rationale, 260)}{outcome.question && <> · asks: {short(outcome.question, 200)}</>} <Links links={outcome.links} open={open} /></li>)}
            {item.concerns.map((concern, i) => <li key={`c${i}`}>Concern of {role(concern.role_id)}{concern.round ? ` (round ${concern.round})` : ''}: {short(concern.statement, 200)}</li>)}</ul></li>)}
      </ol>
      {!trace.completeness.solid && <p className="workflow-error">Missing: {trace.completeness.missing.map(m => m.detail).join('; ')}</p>}
    </details>
  </section>;
}
