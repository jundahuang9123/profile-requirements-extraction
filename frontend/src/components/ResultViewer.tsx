import { ReactNode, useEffect, useRef, useState } from 'react';
import { TraceLink, loadResultFile, pointerKeys, resolvePointer, resultHref } from '../lib/traceApi';

type SourceDocument = { name?: string; text: string; units: Record<string, { kind: string; content: string; span: [number, number] | null }> };
const ID_FIELDS = ['revision_id', 'need_id', 'proposal_id', 'observation_id', 'case_id', 'action_id', 'call_id', 'group_id', 'evidence_id', 'role_id', 'chunk_key'];
const TEXT_FIELDS = ['need_statement', 'statement', 'normalized_statement', 'label', 'action', 'step', 'reason', 'rationale', 'question'];
const escapeKey = (key: string) => key.replace(/~/g, '~0').replace(/\//g, '~1');

// The quotation inside a text, marked: exactly, else with its spacing folded (as the source check accepts it).
function markText(text: string, mark?: string, span?: [number, number] | null): ReactNode {
  let range = span && text.length >= span[1] ? span : null;
  if (!range && mark) {
    const at = text.indexOf(mark);
    if (at >= 0) range = [at, at + mark.length];
    else {
      const words = mark.split(/\s+/).filter(Boolean).map(word => word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
      const found = words.length ? new RegExp(words.join('\\s+')).exec(text) : null;
      if (found) range = [found.index, found.index + found[0].length];
    }
  }
  if (!range) return text;
  return <>{text.slice(0, range[0])}<mark data-mark>{text.slice(range[0], range[1])}</mark>{text.slice(range[1])}</>;
}

// Opens a saved result file (a step download, a model call, a source document) at the part a trace entry links to,
// with that part highlighted and scrolled into view.
export function ResultViewer({ link, onClose }: { link: TraceLink; onClose?: () => void }) {
  const [file, setFile] = useState<unknown>(undefined);
  const [error, setError] = useState('');
  const body = useRef<HTMLDivElement>(null);
  const shown = useRef('');
  useEffect(() => {
    // Every click reads the file again (step files come from a short cache; the current saved state is always
    // fetched), so a link followed after a reviewer's action shows the state after it.
    let active = true; setError('');
    if (shown.current !== link.file) setFile(undefined);
    shown.current = link.file;
    loadResultFile(link.file).then(value => { if (active) setFile(value); })
      .catch(cause => { if (active) setError(cause instanceof Error ? cause.message : String(cause)); });
    return () => { active = false; };
  }, [link]);
  useEffect(() => {
    // A marked quotation is centred; a highlighted row is shown from its first line.
    const mark = body.current?.querySelector('[data-mark]');
    if (mark) mark.scrollIntoView({ block: 'center' });
    else body.current?.querySelector('[data-target]')?.scrollIntoView({ block: 'start' });
  }, [file, link]);
  const download = `/api/rq1/v2${link.file}${link.file.includes('?') ? '&' : '?'}download=true`;
  const isDocument = link.file.startsWith('/sources/') && typeof file === 'object' && file !== null && 'units' in file;
  const found = file !== undefined && resolvePointer(file, link.pointer) !== undefined;
  return <section className="result-viewer" aria-label="Saved result">
    <header><div><strong>{link.label}</strong>{link.need && <small className="result-need">For the need: {link.need}</small>}<code>{link.file}{link.pointer && ` · ${link.pointer}`}</code></div>
      <div className="workflow-toolbar"><a href={resultHref(link)} target="_blank" rel="noreferrer">Open in new tab</a><a href={download}>Download file</a>{onClose && <button onClick={onClose}>Close</button>}</div></header>
    {error && <p className="workflow-error" role="alert">{error}</p>}
    {file === undefined && !error && <p>Loading the saved result…</p>}
    {file !== undefined && !found && <p className="workflow-error">This file does not hold {link.pointer} any more; it is shown whole.</p>}
    <div ref={body} className="result-body">{file !== undefined && (isDocument ? <DocumentView doc={file as SourceDocument} link={link} /> : <JsonView value={file} link={link} />)}</div>
  </section>;
}

function DocumentView({ doc, link }: { doc: SourceDocument; link: TraceLink }) {
  const [all, setAll] = useState(false);
  // Reset while rendering a new link (not in an effect), so the unit is shown before the viewer scrolls to it.
  const [forLink, setForLink] = useState(link);
  if (forLink !== link) { setForLink(link); setAll(false); }
  const evidenceId = pointerKeys(link.pointer)[1];
  const unit = doc.units[evidenceId];
  if (unit?.span && doc.text.slice(unit.span[0], unit.span[1]) === unit.content) {
    // The unit in the parsed text of the whole source, the quotation marked inside it.
    const [start, end] = unit.span;
    return <><p className="result-legend"><span className="result-unit">Blue</span> the evidence unit · <mark>yellow</mark> the quotation, in the parsed text of {doc.name ?? 'the source'}</p>
      <pre className="result-document">{doc.text.slice(0, start)}<span className="result-target" data-target>{markText(unit.content, link.mark, link.quote_span)}</span>{doc.text.slice(end)}</pre></>;
  }
  // A source without one parsed text (structured data) is shown unit by unit: the linked unit and its neighbours.
  const units = Object.entries(doc.units);
  const at = units.findIndex(([id]) => id === evidenceId);
  const shown = all || units.length <= 60 ? units : at >= 0 ? units.slice(Math.max(0, at - 10), at + 11) : units.slice(0, 40);
  return <div className="result-document">{shown.map(([id, item]) => <article key={id} className={id === evidenceId ? 'result-target' : undefined} data-target={id === evidenceId ? '' : undefined}>
    <small>{id} · {item.kind}</small><pre>{id === evidenceId ? markText(item.content, link.mark, link.quote_span) : item.content}</pre></article>)}
    {shown.length < units.length && <button className="result-more" onClick={() => setAll(true)}>Show all {units.length} units ({units.length - shown.length} hidden)</button>}</div>;
}

type Context = { target: string; mark?: string; open: Record<string, boolean>; toggle: (pointer: string, value: boolean) => void };

function JsonView({ value, link }: { value: unknown; link: TraceLink }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  // A node the reviewer collapsed opens again for a new click while rendering it, so the row is there to scroll to.
  const [forLink, setForLink] = useState(link);
  if (forLink !== link) { setForLink(link); setOpen({}); }
  const context: Context = { target: link.pointer, mark: link.mark, open, toggle: (pointer, next) => setOpen(previous => ({ ...previous, [pointer]: next })) };
  return <div className="result-json"><JsonNode name={null} value={value} pointer="" context={context} /></div>;
}

function preview(value: unknown) {
  if (Array.isArray(value)) return `[${value.length} items]`;
  if (value === null || typeof value !== 'object') return '';
  const record = value as Record<string, unknown>;
  const id = ID_FIELDS.map(key => record[key]).find(item => typeof item === 'string');
  const text = TEXT_FIELDS.map(key => record[key]).find(item => typeof item === 'string' && item);
  const label = [id, text].filter(Boolean).join(' · ');
  return label ? (label.length > 140 ? `${label.slice(0, 140)}…` : label) : `{${Object.keys(record).length} keys}`;
}

function JsonNode({ name, value, pointer, context }: { name: string | null; value: unknown; pointer: string; context: Context }) {
  const isTarget = pointer === context.target;
  const inTarget = isTarget || context.target === '' || pointer.startsWith(`${context.target}/`);
  const onPath = context.target.startsWith(`${pointer}/`);
  const depthBelow = inTarget ? pointerKeys(pointer).length - pointerKeys(context.target).length : 99;
  const label = name === null ? null : <span className="result-key">{name}: </span>;
  const flag = isTarget ? { className: 'result-target', 'data-target': '' } : {};
  if (value === null || typeof value !== 'object') {
    const text = typeof value === 'string' ? value : JSON.stringify(value);
    const long = typeof value === 'string' && (value.length > 100 || value.includes('\n'));
    return <div {...flag} className={`result-leaf${isTarget ? ' result-target' : ''}${long ? ' result-long' : ''}`}>{label}
      <span className={`result-${value === null ? 'null' : typeof value}`}>{typeof value === 'string' && inTarget ? markText(text, context.mark) : text}</span></div>;
  }
  const entries: [string, unknown][] = Array.isArray(value) ? value.map((item, i) => [String(i), item]) : Object.entries(value as Record<string, unknown>);
  const isOpen = context.open[pointer] ?? (name === null || onPath || (inTarget && depthBelow < 3));
  const childPointer = (key: string) => `${pointer}/${escapeKey(key)}`;
  // Long lists show the neighbourhood of the traced row; the rest is a click away.
  const all = context.open[`${pointer}#all`] ?? false;
  let shown = entries;
  if (!all && entries.length > 60) {
    const focus = entries.findIndex(([key]) => context.target === childPointer(key) || context.target.startsWith(`${childPointer(key)}/`));
    shown = focus >= 0 ? entries.slice(Math.max(0, focus - 10), focus + 11) : entries.slice(0, 40);
  }
  return <div {...flag}>
    <button className="result-toggle" aria-expanded={isOpen} onClick={() => context.toggle(pointer, !isOpen)}>{isOpen ? '▾' : '▸'} {label ?? <span className="result-key">file</span>}<span className="result-preview">{isOpen ? (Array.isArray(value) ? `[${entries.length} items]` : '') : preview(value)}</span></button>
    {isOpen && <div className="result-children">
      {shown.map(([key, item]) => <JsonNode key={key} name={key} value={item} pointer={childPointer(key)} context={context} />)}
      {shown.length < entries.length && <button className="result-more" onClick={() => context.toggle(`${pointer}#all`, true)}>Show all {entries.length} {Array.isArray(value) ? 'items' : 'keys'} ({entries.length - shown.length} hidden)</button>}
    </div>}
  </div>;
}
