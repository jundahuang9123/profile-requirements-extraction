import { useEffect, useState } from 'react';
import { Baseline, Case, commandKey, Evidence, Link, Requirement, Run, RunSummary, Source, workflowApi } from '../lib/workflowApi';

const stages = ['acquisition', 'decomposition', 'elicitation', 'normalization', 'verification', 'consolidation', 'deliberation', 'adjudication', 'baseline'];
const labels = ['Sources', 'Evidence units', 'Independent elicitation', 'Normalization', 'Verification & qualification', 'Consolidation', 'Selective deliberation', 'Human adjudication', 'RQ2 baseline'];
const perspectives = ['standards_conformance', 'dcat_reuse', 'construction_domain', 'aas_idta', 'ifc_bim', 'dataspace_interoperability', 'publisher_feasibility', 'consumer_discovery', 'stewardship_governance', 'access_rights_policy', 'fair_quality_provenance', 'minimality_scope'];
const humanLabel = (value: string) => value.replace(/_/g, ' ');

export function WorkflowWorkbench({ onStatus }: { onStatus: (value: string) => void }) {
  const [sources, setSources] = useState<Source[]>([]);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [text, setText] = useState('Each dataset must identify the construction asset it represents.\nEach dataset should include its access rights.');
  const [sourceRole, setSourceRole] = useState('stakeholder_need');
  const [authority, setAuthority] = useState('');
  const [tasks, setTasks] = useState('Which datasets represent this construction asset?');
  const [strategy, setStrategy] = useState('rules');
  const [roles, setRoles] = useState(['consumer_discovery', 'construction_domain']);
  const [allowLive, setAllowLive] = useState(false);
  const [selectedRevisions, setSelectedRevisions] = useState<string[]>([]);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [activeRecord, setActiveRecord] = useState<string | null>(null);

  const refreshLists = async () => {
    const [sourceList, runList] = await Promise.all([workflowApi<Source[]>('/sources'), workflowApi<RunSummary[]>('/runs')]);
    setSources(sourceList); setRuns(runList);
  };
  const loadRun = async (id: string) => {
    const loaded = await workflowApi<Run>(`/runs/${id}`); setRun(loaded); setRuns(previous => previous.map(item => item.run_id === id ? { ...item, status: loaded.status, version: loaded.version } : item)); localStorage.setItem('rq1-v2-last-run', id); return loaded;
  };
  const act = async (work: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await work(); }
    catch (cause) { const message = cause instanceof Error ? cause.message : String(cause); setError(message); onStatus(message); }
    finally { setBusy(false); }
  };

  useEffect(() => { void act(async () => {
    await refreshLists(); const saved = localStorage.getItem('rq1-v2-last-run');
    if (saved) { try { await loadRun(saved); } catch { localStorage.removeItem('rq1-v2-last-run'); } }
  }); }, []);

  useEffect(() => {
    if (!run || (!['created', 'eliciting', 'normalizing', 'verifying', 'consolidating', 'routing'].includes(run.status)
      && !run.deliberations.some(item => item.status === 'running'))) return;
    const timer = window.setInterval(() => { void loadRun(run.run_id).catch(cause => setError(String(cause))); }, 1500);
    return () => window.clearInterval(timer);
  }, [run?.run_id, run?.status, run?.deliberations.some(item => item.status === 'running')]);

  const addArtifact = async (name: string, content: string, encoding = 'text', mediaType?: string) => {
    const source = await workflowApi<Source>('/sources', { artifact: { name, content, content_encoding: encoding, media_type: mediaType }, source_role: sourceRole, authority });
    await refreshLists();
    if (source.parse_status === 'parsed') setSelectedSources(previous => [...new Set([...previous, source.source_version_id])]);
    onStatus(source.parse_status === 'parsed' ? `Saved and decomposed ${name}.` : `Saved ${name}; inspect parsing diagnostics.`);
  };
  const upload = async (files: FileList | null) => {
    if (!files) return;
    await act(async () => {
      for (const file of Array.from(files)) {
        const content = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader(); reader.onerror = () => reject(new Error(`Cannot read ${file.name}`));
          reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.readAsDataURL(file);
        });
        await addArtifact(file.name, content, 'base64', file.type || undefined);
      }
    });
  };
  const startRun = async () => act(async () => {
    const snapshot = await workflowApi<{ snapshot_id: string }>('/snapshots', {
      source_version_ids: selectedSources, user_tasks: tasks.split('\n').filter(line => line.trim()).map((statement, i) => ({ id: `CQ-${i + 1}`, statement, kind: 'competency_question' })), name: 'Workbench corpus',
    });
    const created = await workflowApi<Run>('/runs', { snapshot_id: snapshot.snapshot_id, strategy, role_ids: roles, allow_live_provider: allowLive, name: 'Requirements extraction' });
    setSelectedRevisions([]); setActiveRecord(null); await loadRun(created.run_id); await refreshLists(); onStatus('Workflow saved. Independent elicitation is running.');
  });
  const command = async (path: string, payload: unknown) => {
    if (!run) return;
    const result = await workflowApi<{ run: Run }>(`/runs/${run.run_id}${path}`, payload); setRun(result.run); setRuns(previous => previous.map(item => item.run_id === run.run_id ? { ...item, status: result.run.status, version: result.run.version } : item)); onStatus('Changes saved.');
  };
  const inspectEvidence = (id: string) => act(async () => setEvidence(await workflowApi<Evidence>(`/evidence/${id}`)));
  const currentRecords = run?.requirements.filter(record => run.active_revision_ids.includes(record.revision_id)) ?? [];
  const record = currentRecords.find(item => item.revision_id === activeRecord);
  const accepted = currentRecords.filter(item => item.lifecycle_state === 'accepted').map(item => item.revision_id);

  return <main className="workflow-workbench">
    <div className="workflow-intro"><div><h1>Extract, inspect, and validate requirements</h1><p>Preserve source evidence, independent perspectives, disagreement, and every human decision.</p></div><span className="workflow-pill">Persistent workflow · v2</span></div>
    {error && <div className="workflow-error" role="alert">{error}</div>}
    <div className="workflow-layout">
      <aside className="workflow-panel">
        <h2>1–2 · Sources and evidence</h2>
        <label>Source role<select value={sourceRole} onChange={event => setSourceRole(event.target.value)}>
          {['stakeholder_need', 'normative_spec', 'example', 'observation', 'background'].map(role => <option key={role} value={role}>{humanLabel(role)}</option>)}
        </select></label>
        <label>Authority or stakeholder<input value={authority} onChange={event => setAuthority(event.target.value)} placeholder="Who provided this source?" /></label>
        <label>Source text<textarea rows={5} value={text} onChange={event => setText(event.target.value)} /></label>
        <button disabled={busy || !text.trim()} onClick={() => void act(() => addArtifact('stakeholder-needs.md', text))}>Save text source</button>
        <label className="workflow-upload">Upload documents or structured sources<input type="file" multiple accept=".txt,.md,.csv,.tsv,.pdf,.json,.xml,.aas,.aasx,.ttl,.trig,.nq,.nt,.rdf,.jsonld,.ifc" disabled={busy} onChange={event => { void upload(event.target.files); event.target.value = ''; }} /></label>
        <p className="workflow-muted">Text, PDF, AAS, RDF/DCAT, IFC. Background material cannot substantiate requirements.</p>
        <div className="workflow-sources">{sources.filter(source => !source.parent_source_version_id).map(source => <article key={source.source_version_id}>
          <label className="workflow-check"><input type="checkbox" disabled={source.parse_status !== 'parsed' || source.source_role === 'background'} checked={selectedSources.includes(source.source_version_id)} onChange={event => setSelectedSources(previous => event.target.checked ? [...previous, source.source_version_id] : previous.filter(id => id !== source.source_version_id))} /><strong>{source.name}</strong></label>
          <small>{source.artifact_kind} · {humanLabel(source.source_role)} · {source.parse_status}</small>
          <details><summary>Version and diagnostics</summary><code>{source.raw_sha256}</code>{source.diagnostics.map((message, i) => <p key={i}>{message}</p>)}</details>
        </article>)}</div>
        <h2>3 · Independent elicitation</h2>
        <label>Competency questions / user tasks<textarea rows={3} value={tasks} onChange={event => setTasks(event.target.value)} placeholder="One task per line" /></label>
        <label>Execution<select value={strategy} onChange={event => { setStrategy(event.target.value); setAllowLive(false); }}>
          <option value="rules">Rules baseline · offline</option><option value="mock">Perspective demo · offline mock</option><option value="multi_agent">Independent agents · configured provider</option>
        </select></label>
        {strategy !== 'rules' && <details><summary>{roles.length} selected perspectives</summary>{perspectives.map(role => <label key={role} className="workflow-check"><input type="checkbox" checked={roles.includes(role)} onChange={event => setRoles(previous => event.target.checked ? [...previous, role] : previous.filter(value => value !== role))} />{humanLabel(role)}</label>)}</details>}
        {strategy === 'multi_agent' && <label className="workflow-check"><input type="checkbox" checked={allowLive} onChange={event => setAllowLive(event.target.checked)} />Allow calls to the configured model provider for this run</label>}
        <p className="workflow-muted">Offline modes require human semantic and quality assessment. Agent mode sends the selected corpus to your configured provider.</p>
        <button className="workflow-primary" disabled={busy || !selectedSources.length || (strategy !== 'rules' && !roles.length)} onClick={() => void startRun()}>Start saved workflow</button>
      </aside>
      <section className="workflow-main">
        <div className="workflow-toolbar"><label>Saved run<select value={run?.run_id ?? ''} onChange={event => void act(async () => { setActiveRecord(null); setSelectedRevisions([]); await loadRun(event.target.value); })}><option value="">Select a saved run</option>{runs.map(item => <option key={item.run_id} value={item.run_id}>{item.name} · {item.status} · {item.run_id.slice(-6)}</option>)}</select></label>
          {run && <><button disabled={busy} onClick={() => void act(async () => { await loadRun(run.run_id); })}>Refresh</button><a className="workflow-download" href={`/api/rq1/v2/runs/${run.run_id}/export?download=true`}>Export saved review</a></>}
        </div>
        {!run ? <div className="workflow-empty"><h2>Begin with a source</h2><p>Save or upload evidence, select sources, and start a workflow. Completed runs and review decisions restore after reloading.</p></div> : <>
          <ol className="workflow-stages">{stages.map((stage, index) => <li key={stage} data-state={run.stages[stage]}><span>{index + 1}</span><div><strong>{labels[index]}</strong><small>{humanLabel(run.stages[stage] ?? 'pending')}</small></div></li>)}</ol>
          <div className="workflow-toolbar"><span className="workflow-pill">{humanLabel(run.status)} · saved revision {run.version}</span><span>{run.evidence_ids.length} evidence units · {currentRecords.length} candidates · {accepted.length} accepted</span>
            {(['created', 'eliciting', 'normalizing', 'verifying', 'consolidating', 'routing'].includes(run.status) || run.deliberations.some(item => ['queued','running'].includes(item.status))) && <button disabled={busy} onClick={() => void act(async () => { await command('/cancel', { expected_version: run.version }); })}>Stop ongoing work</button>}
            {['failed', 'cancelled'].includes(run.status) && <button disabled={busy} onClick={() => void act(async () => { await workflowApi(`/runs/${run.run_id}/resume`, { expected_version: run.version }); await loadRun(run.run_id); })}>Resume interrupted run</button>}
          </div>
          {run.diagnostics.map((message, i) => <p className="workflow-error" key={i}>{message}</p>)}
          <details className="workflow-panel"><summary>Evidence and independent contributions</summary><p>Each perspective reads the frozen corpus independently. The process trace is separate from later discussion.</p>
            <div className="workflow-role-list">{run.role_runs.map(role => <article key={role.role_id}><strong>{humanLabel(role.role_id)}</strong><span>{role.status}</span><small>{role.observation_ids?.length ?? 0} proposals</small>{role.error && <p>{role.error}</p>}<details><summary>Recorded context</summary><code>{role.context_hash}</code></details></article>)}</div>
            <div className="workflow-evidence-list">{run.evidence_ids.map(id => <button key={id} onClick={() => void inspectEvidence(id)}>{id.slice(0, 15)}…</button>)}</div>
          </details>
          <section className="workflow-panel"><h2>4–6 · Candidates, qualification, and consolidation</h2>
            {!currentRecords.length && <p>No requirements proposed. Empty outputs and source evidence remain available for review.</p>}
            <div className="workflow-candidates">{currentRecords.map(item => <article key={item.revision_id} data-selected={activeRecord === item.revision_id}>
              <label className="workflow-check"><input type="checkbox" checked={selectedRevisions.includes(item.revision_id)} onChange={event => setSelectedRevisions(previous => event.target.checked ? [...previous, item.revision_id] : previous.filter(id => id !== item.revision_id))} /><strong>{item.normalized_statement}</strong></label>
              <div className="workflow-tags"><span>{humanLabel(item.lifecycle_state)}</span><span>Source {item.verification?.status ?? 'pending'}</span><span>Support {item.qualification?.support ?? 'pending'}</span></div>
              <small>{humanLabel(item.requirement_type)} · {item.contributing_roles.map(humanLabel).join(', ')}</small>
              <button onClick={() => setActiveRecord(item.revision_id)}>Inspect and adjudicate</button>
            </article>)}</div>
            {selectedRevisions.length > 1 && <MergeEditor records={currentRecords.filter(r => selectedRevisions.includes(r.revision_id))} busy={busy} submit={(draft) => act(async () => { await command('/decisions', { expected_version: run.version, idempotency_key: commandKey(), action: 'merge', revision_ids: selectedRevisions, rationale: draft.rationale, drafts: [draft] }); setSelectedRevisions([]); setActiveRecord(null); })} />}
            {['awaiting_human', 'completed'].includes(run.status) && <AdditionEditor run={run} busy={busy} submit={draft => act(async () => { await command('/requirements', { expected_version: run.version, idempotency_key: commandKey(), draft, rationale: draft.rationale }); })} />}
          </section>
          {record && <RequirementEditor key={record.revision_id} record={record} run={run} busy={busy} inspect={id => void inspectEvidence(id)} submit={(path, payload) => act(async () => { await command(path, payload); })} />}
          <section className="workflow-panel"><h2>6–7 · Disagreement and selective deliberation</h2>
            {!run.conflicts.length && <p>No potential conflicts detected by the current policy.</p>}
            {run.conflicts.map(conflict => <article className="workflow-conflict" key={conflict.conflict_id}><strong>{humanLabel(conflict.kind)} · {conflict.status}</strong><p>{conflict.rationale}</p>{conflict.revision_ids.map(id => <p key={id}>{run.requirements.find(r => r.revision_id === id)?.normalized_statement}</p>)}</article>)}
            {run.deliberations.map(item => <CaseView key={item.case_id} item={item} run={run} busy={busy} inspect={id => void inspectEvidence(id)} submit={(path, payload) => act(() => command(path, payload))} />)}
          </section>
          <section className="workflow-panel"><h2>9 · Validated baseline for RQ2</h2><p>Publish accepted current revisions with their evidence, assessments, human decisions, and unresolved appendix.</p>
            <button className="workflow-primary" disabled={busy || !accepted.length} onClick={() => void act(async () => {
              const result = await workflowApi<{ run: Run; result: Baseline }>(`/runs/${run.run_id}/baselines`, { expected_version: run.version, idempotency_key: commandKey(), revision_ids: accepted, name: 'Validated profile requirements' }); setRun(result.run); setRuns(previous => previous.map(item => item.run_id === run.run_id ? { ...item, status: result.run.status, version: result.run.version } : item)); onStatus('Validated baseline saved.');
            })}>Publish {accepted.length} accepted requirements</button>
            {run.baselines?.map(baseline => <div className="workflow-toolbar" key={baseline.baseline_id}><span>{baseline.name}</span><a className="workflow-download" href={`/api/rq1/v2/runs/${run.run_id}/baselines/${baseline.baseline_id}?download=true`}>Download baseline</a></div>)}
          </section>
          <details className="workflow-panel"><summary>Revision history and evaluation hooks</summary><a className="workflow-download" href={`/api/rq1/v2/runs/${run.run_id}/evaluation?download=true`}>Download machine and human review metrics</a><pre>{JSON.stringify({ metrics: run.metrics, revisions: run.requirements.map(r => ({ revision_id: r.revision_id, parent_revision_ids: r.parent_revision_ids, state: r.lifecycle_state })) }, null, 2)}</pre></details>
        </>}
      </section>
    </div>
    {evidence && <div className="workflow-evidence-overlay" role="dialog" aria-modal="true" aria-label="Evidence inspector"><section className="workflow-panel"><button onClick={() => setEvidence(null)}>Close evidence inspector</button><h2>{humanLabel(evidence.unit.kind)}</h2><p>{humanLabel(evidence.unit.source_claim_kind)} · source {evidence.resolution.status}</p><pre>{evidence.unit.content}</pre><details open><summary>Address and structural context</summary><pre>{JSON.stringify({ selector: evidence.unit.selector, context: evidence.unit.structural_context, resolution: evidence.resolution }, null, 2)}</pre></details></section></div>}
  </main>;
}

function AdditionEditor({ run, busy, submit }: { run: Run; busy: boolean; submit: (draft: { statement: string; rationale: string; evidence_links: Link[]; scope: string }) => Promise<void> }) {
  const [statement, setStatement] = useState(''); const [rationale, setRationale] = useState('');
  const [scope, setScope] = useState(''); const [quote, setQuote] = useState('');
  const [evidenceId, setEvidenceId] = useState(run.evidence_ids[0]);
  return <details><summary>Add a requirement missed by extraction</summary><p>A human proposal is tracked separately from machine output. It starts unaccepted; inspect it to set its type, resource, obligation, and assessment.</p>
    <label>Atomic requirement<textarea value={statement} onChange={event => setStatement(event.target.value)} /></label><label>Applicability / scope<input value={scope} onChange={event => setScope(event.target.value)} /></label>
    <label>Supporting evidence<select value={evidenceId} onChange={event => setEvidenceId(event.target.value)}>{run.evidence_ids.map(id => <option key={id}>{id}</option>)}</select></label><label>Exact supporting quote<textarea value={quote} onChange={event => setQuote(event.target.value)} /></label>
    <label>Reason for this addition<textarea value={rationale} onChange={event => setRationale(event.target.value)} /></label><button disabled={busy || !statement.trim() || !quote.trim() || !scope.trim() || !rationale.trim()} onClick={() => void submit({ statement, scope, rationale, evidence_links: [{ evidence_id: evidenceId, quote, relation: 'supports', component: 'statement' }] })}>Save human proposal for verification</button>
  </details>;
}

function RequirementEditor({ record, run, busy, submit, inspect }: { record: Requirement; run: Run; busy: boolean; submit: (path: string, payload: unknown) => Promise<void>; inspect: (id: string) => void }) {
  const [statement, setStatement] = useState(record.normalized_statement);
  const [scope, setScope] = useState(record.scope);
  const [rationale, setRationale] = useState('');
  const [support, setSupport] = useState('explicit');
  const [checked, setChecked] = useState(false);
  const [split, setSplit] = useState('');
  const [links, setLinks] = useState<Link[]>(record.evidence_links);
  const [type, setType] = useState(record.requirement_type);
  const [resource, setResource] = useState(record.normalized_intent.resource_type);
  const [obligation, setObligation] = useState(record.normalized_intent.obligation_hint);
  const [metadataNeed, setMetadataNeed] = useState(record.normalized_intent.metadata_need);
  const [valueKind, setValueKind] = useState(record.normalized_intent.value_kind);
  const [question, setQuestion] = useState('');
  const payload = { expected_version: run.version, idempotency_key: commandKey(), revision_ids: [record.revision_id], rationale };
  const applicable = run.conflicts.filter(c => c.revision_ids.includes(record.revision_id) && c.status !== 'resolved');
  const draft = () => ({ statement, evidence_links: links, requirement_type: type, intent: { ...record.normalized_intent, metadata_need: metadataNeed, value_kind: valueKind, resource_type: resource, obligation_hint: obligation }, scope, rationale });
  return <section className="workflow-panel"><h2>8 · Inspect and adjudicate</h2><p>{record.normalized_statement}</p><div className="workflow-tags"><span>Source {record.verification?.status}</span><span>Support {record.qualification?.support}</span><span>{humanLabel(record.lifecycle_state)}</span></div>
    {record.evidence_links.map((link, i) => <blockquote key={i}><p>{link.quote}</p><button onClick={() => inspect(link.evidence_id)}>{link.relation} · {link.component} · inspect original evidence</button></blockquote>)}
    {record.verification?.links.filter(link => link.status !== 'pass').map((link, i) => <p className="workflow-error" key={i}>{link.message}</p>)}
    <p>{record.qualification?.rationale}</p>{record.qualification?.findings.map((finding, i) => <p key={i}><strong>{finding.criterion}:</strong> {finding.message}</p>)}
    <label>Decision / assessment rationale<textarea value={rationale} onChange={event => setRationale(event.target.value)} /></label>
    <details open><summary>Semantic and quality assessment</summary><label>Evidence support<select value={support} onChange={event => setSupport(event.target.value)}>{['explicit', 'inferred', 'unsupported', 'contradicted', 'uncertain'].map(value => <option key={value}>{value}</option>)}</select></label>
      <label className="workflow-check"><input type="checkbox" checked={checked} onChange={event => setChecked(event.target.checked)} />I assessed support, atomicity, clarity, scope, obligation, relevance, and implementation neutrality.</label>
      <button disabled={busy || !checked || !rationale.trim() || record.verification?.status !== 'pass'} onClick={() => void submit('/assessments', { expected_version: run.version, idempotency_key: commandKey(), revision_id: record.revision_id, qualification: { support, rationale, findings: [], assessor: 'human', revision_hash: record.content_hash } })}>Save human assessment</button>
    </details>
    <div className="workflow-toolbar"><button disabled={busy || !rationale.trim()} onClick={() => void submit('/decisions', { ...payload, action: 'accept', conflict_ids: applicable.map(c => c.conflict_id) })}>Accept this revision</button><button disabled={busy || !rationale.trim()} onClick={() => void submit('/decisions', { ...payload, action: 'reject' })}>Reject</button><button disabled={busy || !rationale.trim()} onClick={() => void submit('/decisions', { ...payload, action: 'defer' })}>Defer</button><button disabled={busy || !rationale.trim()} onClick={() => void submit('/decisions', { ...payload, action: 'out_of_scope' })}>Out of scope</button></div>
    <details><summary>Edit or split · creates unaccepted revisions</summary><label>Revised statement<textarea value={statement} onChange={event => setStatement(event.target.value)} /></label><label>Scope<input value={scope} onChange={event => setScope(event.target.value)} /></label>
      <label>Requirement type<select value={type} onChange={event => setType(event.target.value)}>{['descriptive_metadata','semantic_anchor','technical_metadata','access_policy','quality_provenance','lifecycle_context','controlled_vocabulary','validation_constraint','competency_question','unknown'].map(value => <option key={value}>{value}</option>)}</select></label>
      <label>Resource<select value={resource} onChange={event => setResource(event.target.value)}>{['Catalog','Dataset','Distribution','DataService','Agent','Concept','Unknown'].map(value => <option key={value}>{value}</option>)}</select></label>
      <label>Intended metadata need<input value={metadataNeed} onChange={event => setMetadataNeed(event.target.value)} /></label>
      <label>Expected value kind<select value={valueKind} onChange={event => setValueKind(event.target.value)}>{['literal','uri','controlled_concept','class_reference','date','agent','distribution','unknown'].map(value => <option key={value}>{value}</option>)}</select></label>
      <label>Obligation<select value={obligation} onChange={event => setObligation(event.target.value)}>{['mandatory','recommended','optional','unknown'].map(value => <option key={value}>{value}</option>)}</select></label>
      <div><h3>Cited evidence</h3>{links.map((link, index) => <div key={index} className="workflow-panel"><label>Evidence unit<select value={link.evidence_id} onChange={event => setLinks(previous => previous.map((item, i) => i === index ? { ...item, evidence_id: event.target.value } : item))}>{run.evidence_ids.map(id => <option key={id}>{id}</option>)}</select></label><label>Exact quoted text<textarea value={link.quote} onChange={event => setLinks(previous => previous.map((item, i) => i === index ? { ...item, quote: event.target.value } : item))} /></label><label>Claim supported<select value={link.component} onChange={event => setLinks(previous => previous.map((item, i) => i === index ? { ...item, component: event.target.value } : item))}>{['statement','obligation','scope','condition','value_kind'].map(value => <option key={value}>{value}</option>)}</select></label><label>Evidence relation<select value={link.relation} onChange={event => setLinks(previous => previous.map((item, i) => i === index ? { ...item, relation: event.target.value as Link['relation'] } : item))}>{['supports','contradicts','contextualizes'].map(value => <option key={value}>{value}</option>)}</select></label><button onClick={() => setLinks(previous => previous.filter((_, i) => i !== index))}>Remove citation from new revision</button></div>)}<button onClick={() => setLinks(previous => [...previous, { evidence_id: run.evidence_ids[0], quote: '', relation: 'supports', component: 'statement' }])}>Add citation</button></div>
      <button disabled={busy || !rationale.trim() || !statement.trim()} onClick={() => void submit('/decisions', { ...payload, action: 'edit', drafts: [draft()], conflict_ids: applicable.map(c => c.conflict_id) })}>Save revised requirement</button>
      <label>Split into atomic needs · one per line<textarea value={split} onChange={event => setSplit(event.target.value)} /></label><button disabled={busy || !rationale.trim() || split.split('\n').filter(line => line.trim()).length < 2} onClick={() => void submit('/decisions', { ...payload, action: 'split', drafts: split.split('\n').filter(line => line.trim()).map(statement => ({ ...draft(), statement })), conflict_ids: applicable.map(c => c.conflict_id) })}>Create child requirements</button>
    </details>
    <label>Question for a targeted discussion<input value={question} onChange={event => setQuestion(event.target.value)} /></label><button disabled={busy || !question.trim()} onClick={() => void submit('/deliberations', { expected_version: run.version, revision_ids: [record.revision_id], question })}>Open deliberation case</button>
  </section>;
}

function MergeEditor({ records, busy, submit }: { records: Requirement[]; busy: boolean; submit: (draft: { rationale: string; statement: string; evidence_links: Link[]; requirement_type: string; intent: Requirement['normalized_intent']; scope: string }) => Promise<void> }) {
  const [statement, setStatement] = useState(''); const [rationale, setRationale] = useState('');
  return <details><summary>Compare and propose a merge of {records.length} selected candidates</summary>{records.map(record => <p key={record.revision_id}>{record.normalized_statement} · {record.scope} · {record.normalized_intent.obligation_hint}</p>)}<label>Canonical atomic statement<textarea value={statement} onChange={event => setStatement(event.target.value)} /></label><label>Why the meanings and obligations are compatible<textarea value={rationale} onChange={event => setRationale(event.target.value)} /></label><button disabled={busy || !statement.trim() || !rationale.trim()} onClick={() => void submit({ statement, rationale, evidence_links: records.flatMap(record => record.evidence_links), requirement_type: records[0].requirement_type, intent: records[0].normalized_intent, scope: records[0].scope })}>Create merge for verification</button></details>;
}

function CaseView({ item, run, busy, submit, inspect }: { item: Case; run: Run; busy: boolean; submit: (path: string, payload: unknown) => Promise<void>; inspect: (id: string) => void }) {
  const [body, setBody] = useState('');
  return <article className="workflow-case"><h3>{item.triggers.map(humanLabel).join(' · ')}</h3><p>{item.status} · {item.participants.map(humanLabel).join(', ')} · bounded to {item.max_rounds} rounds / {item.max_calls} calls</p>
    {item.messages.map(message => <blockquote key={message.message_id}><strong>{humanLabel(message.role_id)}{message.round ? ` · round ${message.round}` : ''}</strong><p>{message.body}</p>{message.proposed_statement && <p>Proposed: {message.proposed_statement}</p>}{message.evidence_ids.map(id => <button key={id} onClick={() => inspect(id)}>Inspect cited evidence</button>)}</blockquote>)}
    {item.stop_reason && <p>Stopped: {item.stop_reason}</p>}<label>Human contribution or closure rationale<textarea value={body} onChange={event => setBody(event.target.value)} /></label>
    <div className="workflow-toolbar"><button disabled={busy || !body.trim()} onClick={() => void submit(`/deliberations/${item.case_id}/messages`, { expected_version: run.version, idempotency_key: commandKey(), body, evidence_ids: [] })}>Add to saved thread</button><button disabled={busy || !body.trim() || item.status === 'running'} onClick={() => void submit(`/deliberations/${item.case_id}/close`, { expected_version: run.version, idempotency_key: commandKey(), body, evidence_ids: [] })}>Close for human adjudication</button></div>
  </article>;
}
