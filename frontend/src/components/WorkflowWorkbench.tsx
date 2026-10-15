import { useEffect, useState } from 'react';
import { NeedSummaryView } from './NeedSummaryView';
import { BaseCatalogueReview } from './BaseCatalogueReview';
import { NeedAsidesView } from './NeedAsidesView';
import { RoleManifestView } from './RoleManifestView';
import { StepModelsSettings } from './StepModelsSettings';
import { BaseCheck, BaseProfileSummary, Baseline, BenchmarkImport, BenchmarkSummary, Case, commandKey, Evidence, EvidenceSummary, Snapshot, Link, Requirement, Run, RunSummary, SetAside, Source, workflowApi } from '../lib/workflowApi';

const stages = ['acquisition', 'decomposition', 'role_selection', 'elicitation', 'normalization', 'verification', 'consolidation', 'deliberation', 'adjudication', 'baseline'];
const labels = ['Sources & scope', 'Evidence units', 'Stakeholder roles', 'Independent extraction', 'Normalized candidates', 'Original-source checks', 'Grouped needs & scope', 'Discussion', 'Human review', 'Validated baseline'];
const stageNumbers = ['1', '2', '3a', '3b', '4', '5', '6', '7', '8', '9'];
const perspectives = ['standards_conformance', 'dcat_reuse', 'construction_domain', 'aas_idta', 'ifc_bim', 'dataspace_interoperability', 'publisher_feasibility', 'consumer_discovery', 'stewardship_governance', 'access_rights_policy', 'fair_quality_provenance', 'minimality_scope'];
const humanLabel = (value: string) => value.replace(/_/g, ' ');
const roleLabel = (run: Run, id: string) => run.role_manifest?.selected_roles.find(role => role.role_id === id)?.label ?? humanLabel(id);
const asideReasons: Record<SetAside['reason'], string> = { source_check_failed: 'Source check failed', not_supported_by_quote: 'Not supported by quote', rewrite_rejected: 'Rewrite rejected', no_source_link: 'No source link', inherited_from_base: 'Inherited from the base', declared_not_extension: 'Declared not an extension', base_specification_only: 'Base specification only', generic_need_served_by_base: 'Generic need served by base', no_use_case: 'No necessary use-case link' };
// Routed discussions that resume runs again; reviewer-requested ones are never repeated.
const unfinishedCase = (item: Case) => ['queued', 'running', 'failed', 'cancelled'].includes(item.status) && !item.triggers.some(trigger => trigger.startsWith('human_request: '));
const leaseActive = (run: Run) => Boolean(run.worker_id) && (run.job_lease_until ?? 0) * 1000 > Date.now();
const resumable = (run: Run) => ['failed', 'cancelled'].includes(run.status)
  || (run.status === 'awaiting_human' && !run.decisions?.length && !leaseActive(run)
      && (run.role_runs.some(role => role.status === 'failed') || run.deliberations.some(unfinishedCase)));
const stageState = (run: Run, stage: string) => stage === 'elicitation' && run.stages[stage] === 'completed' && run.role_runs.some(role => role.status === 'failed') ? 'partial' : stage === 'role_selection' && run.stages[stage] !== 'completed' && ['failed', 'cancelled'].includes(run.status) ? run.status : run.stages[stage] ?? 'pending';

function savedSetup() {
  try { return JSON.parse(localStorage.getItem('rq1-needs-setup') ?? '{}'); } catch { return {}; }
}
function currentRoute() {
  const match = window.location.hash.match(/^#\/workflow\/([^/]+)\/([^/]+)$/);
  return { runId: match?.[1], page: match && stages.includes(match[2]) ? match[2] : 'acquisition' };
}

export function WorkflowWorkbench({ onStatus }: { onStatus: (value: string) => void }) {
  const [setup] = useState(savedSetup);
  const [page, setPage] = useState(currentRoute().page);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [previewUnits, setPreviewUnits] = useState<EvidenceSummary[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [baseProfiles, setBaseProfiles] = useState<BaseProfileSummary[]>([]);
  const [benchmarks, setBenchmarks] = useState<BenchmarkSummary[]>([]);
  const [selectedSources, setSelectedSources] = useState<string[]>(setup.selectedSources ?? []);
  const [benchmarkCaseId, setBenchmarkCaseId] = useState<string>(setup.benchmarkCaseId ?? '');
  const [baseProfileId, setBaseProfileId] = useState<string>(setup.baseProfileId ?? '');
  const [baseCheck, setBaseCheck] = useState<boolean>(setup.baseCheck ?? true);
  const [treatBaseAsBackground, setTreatBaseAsBackground] = useState<boolean>(setup.treatBaseAsBackground ?? true);
  const [benchmarkImport, setBenchmarkImport] = useState<{ caseId: string; treatBaseAsBackground: boolean; sourceVersionIds: string[]; userTasks?: Snapshot['user_tasks']; useCaseInput?: Snapshot['use_case_input'] } | null>(setup.benchmarkImport ?? null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [text, setText] = useState('Data publishers must describe the geographic coverage of each dataset.\nEach dataset should include its access rights.');
  const [sourceRole, setSourceRole] = useState<string>(setup.sourceRole ?? 'stakeholder_need');
  const [authority, setAuthority] = useState<string>(setup.authority ?? '');
  const [tasks, setTasks] = useState<string>(setup.tasks ?? '');
  const [scoping, setScoping] = useState<string>(setup.scoping ?? 'auto');
  const [deriveScoping, setDeriveScoping] = useState<string>('auto');
  const [strategy, setStrategy] = useState<string>(setup.strategy ?? 'multi_agent');
  const [roles, setRoles] = useState<string[]>(setup.roles ?? ['consumer_discovery', 'publisher_feasibility']);
  const [roleSelection, setRoleSelection] = useState<string>(setup.roleSelection ?? 'automatic');
  const [maxRoles, setMaxRoles] = useState<number>(setup.maxRoles ?? 4);
  const [executionMode, setExecutionMode] = useState<string>(setup.executionMode ?? 'stepwise');
  const [consolidation, setConsolidation] = useState<string>(setup.consolidation ?? 'semantic');
  const [discussion, setDiscussion] = useState<string>(setup.discussion ?? 'on_request');
  const [showDerive, setShowDerive] = useState(false);
  const [deriveStartFrom, setDeriveStartFrom] = useState('normalization');
  const [deriveExecutionMode, setDeriveExecutionMode] = useState('automatic');
  const [deriveName, setDeriveName] = useState('Reprocessed requirements');
  const [deriveDiscussion, setDeriveDiscussion] = useState('on_request');
  const [deriveConsolidation, setDeriveConsolidation] = useState('semantic');
  const [deriveLive, setDeriveLive] = useState(false);
  const [stepModels, setStepModels] = useState<Record<string, string>>(setup.stepModels ?? {});
  const [deriveStepModels, setDeriveStepModels] = useState<Record<string, string>>({});
  const [deriveBaseProfileId, setDeriveBaseProfileId] = useState('');
  const [deriveBaseCheck, setDeriveBaseCheck] = useState(true);
  const [deriveCaseId, setDeriveCaseId] = useState('');
  const [asideFilter, setAsideFilter] = useState('all');
  const [allowLive, setAllowLive] = useState(false);
  const [selectedRevisions, setSelectedRevisions] = useState<string[]>([]);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [activeRecord, setActiveRecord] = useState<string | null>(null);

  const refreshLists = async () => {
    const [sourceList, runList, profiles, cases] = await Promise.all([workflowApi<Source[]>('/sources'), workflowApi<RunSummary[]>('/runs'), workflowApi<BaseProfileSummary[]>('/base-profiles'), workflowApi<BenchmarkSummary[]>('/benchmarks')]);
    setSources(sourceList); setRuns(runList); setBaseProfiles(profiles); setBenchmarks(cases);
  };
  const loadRun = async (id: string) => {
    const loaded = await workflowApi<Run>(`/runs/${id}?audit=false`); setRun(loaded);
    setSnapshot(await workflowApi<Snapshot>(`/snapshots/${loaded.snapshot_id}`));
    setRuns(previous => previous.some(item => item.run_id === id)
      ? previous.map(item => item.run_id === id ? { ...item, status: loaded.status, version: loaded.version } : item)
      : [loaded, ...previous]);
    localStorage.setItem('rq1-v2-last-run', id); return loaded;
  };
  const act = async (work: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await work(); }
    catch (cause) { const message = cause instanceof Error ? cause.message : String(cause); setError(message); onStatus(message); }
    finally { setBusy(false); }
  };

  useEffect(() => { void act(async () => {
    await refreshLists(); const route = currentRoute(); const saved = route.runId === 'new' ? null : route.runId ?? localStorage.getItem('rq1-v2-last-run');
    if (saved) { try { await loadRun(saved); } catch { localStorage.removeItem('rq1-v2-last-run'); } }
  }); }, []);

  useEffect(() => {
    if (!run || (!['created', 'selecting_roles', 'eliciting', 'normalizing', 'verifying', 'consolidating', 'routing'].includes(run.status)
      && !run.deliberations.some(item => item.status === 'running') && !run.worker_id)) return;
    // Poll again only after the previous response arrived, so slow responses never pile up.
    let stopped = false; let timer: number | undefined;
    const poll = async () => {
      try { await loadRun(run.run_id); } catch (cause) { setError(String(cause)); }
      if (!stopped) timer = window.setTimeout(() => void poll(), 1500);
    };
    timer = window.setTimeout(() => void poll(), 1500);
    return () => { stopped = true; window.clearTimeout(timer); };
  }, [run?.run_id, run?.status, run?.deliberations.some(item => item.status === 'running'), run?.worker_id]);

  const navigate = (next: string, runId = run?.run_id ?? 'new') => {
    setPage(next); setEvidence(null); window.location.hash = `/workflow/${runId}/${next}`;
    localStorage.setItem(`rq1-workflow-page-${runId}`, next);
  };
  const newWorkflow = () => { setRun(null); setSnapshot(null); setActiveRecord(null); setSelectedRevisions([]); localStorage.removeItem('rq1-v2-last-run'); navigate('acquisition', 'new'); };
  useEffect(() => {
    const change = () => {
      const route = currentRoute(); setPage(route.page); setEvidence(null);
      if (route.runId === 'new') { setRun(null); setSnapshot(null); }
      else if (route.runId && route.runId !== run?.run_id) void act(async () => { await loadRun(route.runId!); });
    };
    window.addEventListener('hashchange', change);
    return () => window.removeEventListener('hashchange', change);
  }, [run?.run_id]);
  useEffect(() => { localStorage.setItem('rq1-needs-setup', JSON.stringify({ selectedSources, tasks, stepModels, scoping, strategy, roles, roleSelection, maxRoles, sourceRole, authority, executionMode, discussion, consolidation, benchmarkCaseId, baseProfileId, baseCheck, treatBaseAsBackground, benchmarkImport })); }, [selectedSources, tasks, stepModels, scoping, strategy, roles, roleSelection, maxRoles, sourceRole, authority, executionMode, discussion, consolidation, benchmarkCaseId, baseProfileId, baseCheck, treatBaseAsBackground, benchmarkImport]);
  useEffect(() => {
    setShowDerive(false); setAsideFilter('all');
    setDeriveStepModels({});
    setDeriveBaseProfileId(run?.base_profile_id ?? run?.request?.base_profile_id ?? '');
    setDeriveBaseCheck(run?.request?.base_check ?? true);
    setDeriveCaseId(run?.request?.benchmark_case_id ?? '');
  }, [run?.run_id]);
  useEffect(() => {
    if (page !== 'decomposition' || run) return;
    let active = true;
    const evidenceSources = selectedSources.filter(id => !['background', 'evaluation_reference'].includes(sources.find(source => source.source_version_id === id)?.source_role ?? ''));
    void Promise.all(evidenceSources.map(id => workflowApi<EvidenceSummary[]>(`/sources/${id}/evidence`)))
      .then(groups => { if (active) setPreviewUnits(groups.flat()); })
      .catch(cause => { if (active) setError(String(cause)); });
    return () => { active = false; };
  }, [page, run?.run_id, selectedSources, sources]);

  const selectedBenchmark = benchmarks.find(item => item.case_id === benchmarkCaseId);
  const benchmarkNeedsImport = Boolean(benchmarkCaseId && (benchmarkImport?.caseId !== benchmarkCaseId || benchmarkImport?.treatBaseAsBackground !== treatBaseAsBackground || !benchmarkImport?.sourceVersionIds?.length));
  const chooseBenchmark = (caseId: string) => {
    const selected = benchmarks.find(item => item.case_id === caseId);
    setBenchmarkCaseId(caseId); setBaseProfileId(selected?.base_profile_id ?? '');
    setBaseCheck(Boolean(selected?.base_profile_id));
    setTreatBaseAsBackground(Boolean(selected?.background_source_names.length));
  };
  const importBenchmark = () => act(async () => {
    const imported = await workflowApi<BenchmarkImport>(`/benchmarks/${benchmarkCaseId}/load`, { treat_base_as_background: treatBaseAsBackground });
    await refreshLists(); setSelectedSources(imported.sources.map(source => source.source_version_id));
    setBenchmarkImport({ caseId: imported.case_id, treatBaseAsBackground: imported.treat_base_as_background, sourceVersionIds: imported.sources.map(source => source.source_version_id), userTasks: imported.snapshot.user_tasks, useCaseInput: imported.snapshot.use_case_input });
    setSnapshot(imported.snapshot);
    setTasks(imported.snapshot.user_tasks.map(task => task.statement).join('\n'));
    setScoping('auto');
    onStatus(`Loaded ${imported.sources.length} sources and ${imported.snapshot.evidence_ids.length} evidence units. Scope and questions are frozen when you start the run.`);
  });

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
    if (benchmarkNeedsImport) throw new Error('Load the selected benchmark again to apply its source settings before starting.');
    if (benchmarkCaseId && selectedSources.some(id => !benchmarkImport?.sourceVersionIds.includes(id))) throw new Error('A benchmark uses only its loaded raw inputs. Select Custom documents to use additional sources.');
    const importedTasks = benchmarkImport?.caseId === benchmarkCaseId ? benchmarkImport.userTasks : undefined;
    const unchangedTasks = importedTasks && tasks === importedTasks.map(task => task.statement).join('\n');
    const snapshot = await workflowApi<{ snapshot_id: string }>('/snapshots', {
      source_version_ids: selectedSources, user_tasks: unchangedTasks ? importedTasks : tasks.split('\n').filter(line => line.trim()).map((statement, i) => ({ id: `CQ-${i + 1}`, statement, kind: 'competency_question' })), use_case_input: unchangedTasks ? benchmarkImport?.useCaseInput : null, name: 'Workbench corpus',
    });
    const created = await workflowApi<Run>('/runs', { output_form: strategy === 'multi_agent' ? 'needs' : 'candidates', scoping: scoping === 'auto' ? null : scoping, snapshot_id: snapshot.snapshot_id, step_models: strategy === 'multi_agent' ? stepModels : {}, execution_mode: executionMode, strategy, role_ids: roles, role_selection: strategy === 'rules' ? 'manual' : roleSelection, max_roles: maxRoles, consolidation: strategy === 'rules' ? 'exact' : consolidation, discussion: strategy === 'multi_agent' ? discussion : 'automatic', base_profile_id: baseProfileId || null, base_check: Boolean(baseProfileId) && baseCheck, benchmark_case_id: benchmarkCaseId || null, allow_live_provider: allowLive, name: 'Requirements extraction' });
    setSelectedRevisions([]); setActiveRecord(null); await loadRun(created.run_id); await refreshLists(); navigate('role_selection', created.run_id); onStatus('Workflow saved. Results persist while you browse the steps.');
  });
  const command = async (path: string, payload: unknown) => {
    if (!run) return;
    const result = await workflowApi<{ run: Run }>(`/runs/${run.run_id}${path}`, payload); setRun(result.run); setRuns(previous => previous.map(item => item.run_id === run.run_id ? { ...item, status: result.run.status, version: result.run.version } : item)); onStatus('Changes saved.');
  };
  const inspectEvidence = (id: string) => act(async () => setEvidence(await workflowApi<Evidence>(`/evidence/${id}`)));
  const currentRecords = (run?.requirements.filter(record => run.request?.output_form === 'needs' ? run.active_revision_ids.includes(record.revision_id) : run.active_revision_ids.length ? run.active_revision_ids.includes(record.revision_id) : !record.parent_revision_ids.length) ?? []).sort((a,b) => (a.rank ?? Number.MAX_SAFE_INTEGER) - (b.rank ?? Number.MAX_SAFE_INTEGER) || a.requirement_id.localeCompare(b.requirement_id));
  const record = currentRecords.find(item => item.revision_id === activeRecord) ?? run?.requirements.find(item => item.revision_id === activeRecord);
  const accepted = currentRecords.filter(item => item.lifecycle_state === 'accepted').map(item => item.revision_id);

  const pageIndex = stages.indexOf(page);
  const savedStageRecords = run?.stage_results?.[page]?.requirements;
  const resultRecords = page === 'consolidation' && savedStageRecords
    ? savedStageRecords.filter(item => (run?.stage_results?.consolidation?.active_revision_ids ?? run?.active_revision_ids ?? []).includes(item.revision_id))
    : ['normalization', 'verification'].includes(page) && savedStageRecords ? savedStageRecords : ['normalization', 'verification'].includes(page) ? run?.requirements.filter(item => !item.parent_revision_ids.length) ?? [] : currentRecords;
  const consolidationEvents = run?.stage_results?.consolidation?.consolidation_events ?? run?.consolidation_events ?? [];
  const mergeEvents = consolidationEvents.filter(event => event.action === 'semantic_merge');
  const mergedGroupIds = new Set(mergeEvents.map(event => event.group_id));
  const groupIds = [...new Set(consolidationEvents.map(event => event.group_id).filter((id): id is string => Boolean(id)))];
  const groupMembers = (groupId: string) => run?.requirements.filter(item => item.group_id === groupId && !item.parent_revision_ids.length) ?? [];
  const variantsFor = (item: Requirement) => currentRecords.filter(record => record.group_id && record.group_id === item.group_id);
  const setAside = run?.request?.output_form === 'needs' ? run.set_aside_observations ?? [] : run?.stage_results?.normalization?.set_aside_observations ?? run?.set_aside_observations ?? [];
  const filteredAside = setAside.filter(item => asideFilter === 'all' || item.reason === asideFilter);
  const baseSummary = run?.stage_results?.normalization?.base_check ?? run?.metrics.base_check;

  return <main className="workflow-workbench">
    <div className="workflow-intro"><div><h1>{stageNumbers[pageIndex]} · {labels[pageIndex]}</h1><p>Each step has saved results. Step by step for human review, or automatic processing for tests. Results save to the run; review actions save when submitted.</p></div><button onClick={newWorkflow}>New workflow</button></div>
    {error && <div className="workflow-error" role="alert">{error}</div>}
    <div className="workflow-toolbar"><label>Saved run<select value={run?.run_id ?? ''} onChange={event => void act(async () => {
      setActiveRecord(null); setSelectedRevisions([]);
      if (event.target.value) { await loadRun(event.target.value); navigate(localStorage.getItem(`rq1-workflow-page-${event.target.value}`) ?? 'role_selection', event.target.value); }
      else newWorkflow();
    })}><option value="">New workflow</option>{runs.map(item => <option key={item.run_id} value={item.run_id}>{item.name} · {humanLabel(item.status)} · {item.run_id.slice(-6)}</option>)}</select></label>
      {run && <><button disabled={busy} onClick={() => void act(async () => { await loadRun(run.run_id); })}>Refresh saved results</button><a className="workflow-download" href={`/api/rq1/v2/runs/${run.run_id}/export?download=true`}>Download full run</a>{run.request?.output_form === 'needs' && <a className="workflow-download" href={`/api/rq1/v2/runs/${run.run_id}/needs?download=true`}>Download needs.json</a>}<a className="workflow-download" href={`/api/rq1/v2/runs/${run.run_id}/stages/${page}?download=true`}>Download this step</a></>}
    </div>
    <nav aria-label="Workflow steps"><ol className="workflow-stages">{stages.map((stage, index) => <li key={stage} data-state={run ? stageState(run, stage) : 'pending'} data-current={stage === page}><button aria-current={stage === page ? 'step' : undefined} onClick={() => navigate(stage)}><span>{stageNumbers[index]}</span><div><strong>{labels[index]}</strong><small>{run ? humanLabel(stageState(run, stage)) : 'setup'}</small></div></button></li>)}</ol></nav>
    {run && <div className="workflow-toolbar"><span className="workflow-pill">{humanLabel(run.status)} · saved revision {run.version}</span><span>{run.evidence_ids.length} evidence units · {currentRecords.length} {run.request?.output_form === 'needs' ? 'needs' : 'candidates'} · {accepted.length} accepted</span>
      {(['created', 'selecting_roles', 'eliciting', 'normalizing', 'verifying', 'consolidating', 'routing'].includes(run.status) || run.deliberations.some(item => ['queued','running'].includes(item.status))) && <button disabled={busy} onClick={() => void act(() => command('/cancel', { expected_version: run.version }))}>Stop ongoing work</button>}
      {resumable(run) && <button disabled={busy} title="Repeats only unfinished extraction units and discussions; finished results are kept." onClick={() => void act(async () => { await workflowApi(`/runs/${run.run_id}/resume`, { expected_version: run.version }); await loadRun(run.run_id); })}>{['failed', 'cancelled'].includes(run.status) ? 'Resume interrupted run' : 'Retry unfinished work'}</button>}
    </div>}
    {run && !leaseActive(run) && ((page === 'normalization' && run.stages.elicitation === 'completed' && run.role_runs.length > 0 && run.role_runs.every(role => role.status === 'completed')) || (page === 'role_selection' && run.role_manifest?.mode === 'automatic' && run.role_manifest.status === 'completed')) && <section className="workflow-panel">
      <button disabled={busy} onClick={() => { setDeriveStartFrom(page === 'role_selection' ? 'role_selection' : 'normalization'); setDeriveExecutionMode(page === 'role_selection' ? 'stepwise' : 'automatic'); setShowDerive(value => !value); }}>{page === 'role_selection' ? 'Choose a new panel from this saved discovery scan' : 'Reprocess from saved extraction in a separate trial'}</button>
      {showDerive && <div><p>{deriveStartFrom === 'role_selection' ? 'Creates a separate trial using the saved discovery candidates and citation checks. It rebuilds the registry and selects a panel without reading sources again. Extraction starts afresh after the new panel. The original run stays unchanged.' : "Creates a new run that reuses this run's extraction, with no extraction calls. This run stays unchanged."}</p>
        <label>Progression<select value={deriveExecutionMode} onChange={event => setDeriveExecutionMode(event.target.value)}><option value="stepwise">Step by step · review the saved panel before extraction</option><option value="automatic">Automatic · run through machine stages</option></select></label>
        <label>Name<input value={deriveName} onChange={event => setDeriveName(event.target.value)} /></label>
        <label>Benchmark source context<select value={deriveCaseId} onChange={event => {
          const selected = benchmarks.find(item => item.case_id === event.target.value);
          setDeriveCaseId(event.target.value); setDeriveBaseProfileId(selected?.base_profile_id ?? ''); setDeriveBaseCheck(Boolean(selected?.base_profile_id));
        }}><option value="">Custom or unspecified case</option>{benchmarks.map(item => <option key={item.case_id} value={item.case_id}>{humanLabel(item.case_id)}</option>)}</select></label>
        <p className="workflow-muted">For an older saved extraction, select its case to identify which cited documents are base specifications.</p>
        <BaseProfileField profiles={baseProfiles} value={deriveBaseProfileId} onChange={value => { setDeriveBaseProfileId(value); setDeriveBaseCheck(Boolean(value)); }} />
        <label className="workflow-check"><input type="checkbox" disabled={!deriveBaseProfileId} checked={Boolean(deriveBaseProfileId) && deriveBaseCheck} onChange={event => setDeriveBaseCheck(event.target.checked)} />Filter proposals supported only by the base specification</label>
        <label>Consolidation<select value={deriveConsolidation} onChange={event => setDeriveConsolidation(event.target.value)}><option value="semantic">Merge candidates with the same meaning</option><option value="exact">Exact copies only (earlier behaviour)</option></select></label>
        <label>Discussion<select value={deriveDiscussion} onChange={event => setDeriveDiscussion(event.target.value)}><option value="on_request">Only when a reviewer asks</option><option value="automatic">Discuss flagged needs automatically</option></select></label>
        <p>Needs are assessed after grouping and scoping; old per-candidate assessments are not reused.</p><label>Use-case scoping<select value={deriveScoping} onChange={event => setDeriveScoping(event.target.value)}><option value="auto">Use declared tasks when present; otherwise off</option><option value="use_cases">Only needs necessary for declared use cases</option><option value="off">Off · retain needs without a use-case claim</option></select></label>
        {run.strategy === 'multi_agent' && <label className="workflow-check"><input type="checkbox" checked={deriveLive} onChange={event => setDeriveLive(event.target.checked)} />Allow calls to the configured provider for this new trial</label>}
        {run.strategy === 'multi_agent' && <StepModelsSettings value={deriveStepModels} onChange={setDeriveStepModels} />}
        <button className="workflow-primary" disabled={busy || !deriveName.trim() || (run.strategy === 'multi_agent' && !deriveLive)} onClick={() => void act(async () => {
          const created = await workflowApi<Run>(`/runs/${run.run_id}/derive`, { start_from: deriveStartFrom, step_models: deriveStepModels, output_form: 'needs', scoping: deriveScoping === 'auto' ? null : deriveScoping, expected_version: run.version, name: deriveName, consolidation: deriveConsolidation, discussion: deriveDiscussion, execution_mode: deriveExecutionMode, reuse_assessments: false, base_profile_id: deriveBaseProfileId || null, base_check: Boolean(deriveBaseProfileId) && deriveBaseCheck, benchmark_case_id: deriveCaseId || null, allow_live_provider: deriveLive, rationale: deriveStartFrom === 'role_selection' ? 'Rebuild the registry and panel from compatible saved discovery; extract afresh.' : 'Reprocess saved extraction with the selected downstream settings.' });
          setShowDerive(false); setActiveRecord(null); setSelectedRevisions([]); await loadRun(created.run_id); await refreshLists(); navigate(deriveStartFrom === 'role_selection' ? 'role_selection' : 'normalization', created.run_id); onStatus(deriveStartFrom === 'role_selection' ? 'Separate panel trial created from the saved discovery scan.' : 'New run created from the saved extraction.');
        })}>Create reprocessed run</button>
      </div>}
    </section>}
    {run && <StepModelsSettings saved value={run.step_models ?? {}} />}
    {run?.derived_from && <p className="workflow-notice">{run.derived_from.stage === 'discovery' ? 'Discovery scan reused from' : run.derived_from.stage === 'role_selection' ? 'Sources and stakeholder panel reused from' : 'Extraction reused from'} <a href={`#/workflow/${run.derived_from.run_id}/${['role_selection', 'discovery'].includes(run.derived_from.stage ?? '') ? 'role_selection' : 'elicitation'}`}>{run.derived_from.run_id}</a>, saved revision {run.derived_from.version}. {run.derived_from.stage === 'discovery' ? 'The registry and panel are rebuilt; extraction starts afresh. The source run stays saved.' : run.derived_from.stage === 'role_selection' ? 'Extraction starts afresh under the current policy; the original run stays saved.' : "New call counts exclude the source run's extraction."}</p>}
    {run?.base_profile_id && <section className="workflow-panel"><p>Starting from <strong>{baseProfiles.find(profile => profile.id === run.base_profile_id)?.label ?? run.base_profile_id}</strong>{run.base_check_policy_version && <> · base check {run.base_check_policy_version}</>}.</p>{baseSummary?.by_relation && <><div className="workflow-tags">{Object.entries(baseSummary.by_relation).map(([relation, count]) => <span key={relation}>{humanLabel(relation)}: {count}</span>)}</div><p>{baseSummary.set_aside_inherited} inherited proposals set aside.</p></>}<details><summary>Pinned base-profile file</summary><code>{run.base_profile_sha256 ?? 'No saved hash'}</code></details>{run.request?.output_form === 'needs' && <p><BaseCatalogueReview review={run.base_needs_catalogue?.review} /> · <a href={`/api/rq1/v2/base-profiles/${run.base_profile_id}/needs?download=true`}>Download for review</a></p>}</section>}
    {run?.status === 'paused' && <section className="workflow-panel"><h2>Results saved — ready for review</h2><p>Review the completed step, then continue. No processing runs while this workflow is paused.</p><button className="workflow-primary" disabled={busy || Boolean(run.worker_id)} onClick={() => void act(async () => { await workflowApi(`/runs/${run.run_id}/continue`, { expected_version: run.version }); const updated = await loadRun(run.run_id); navigate(stages.find(stage => !['completed', 'partial'].includes(updated.stages[stage])) ?? 'adjudication'); })}>Continue to next processing step</button></section>}
    {run?.diagnostics.map((message, i) => <p className="workflow-error" key={i}>{message}</p>)}
    {page === 'acquisition' && <section className="workflow-panel">
      {run ? <><h2>Frozen input sources</h2><p>These inputs belong to this saved run. Start a new workflow to change them.</p>{snapshot?.source_version_ids.map(id => <article key={id}><strong>{sources.find(source => source.source_version_id === id)?.name ?? id}</strong></article>)}{!!snapshot?.exclusions?.length && <details><summary>Material retained outside the evidence corpus</summary>{snapshot.exclusions.map(item => <p key={item.source_version_id}>{sources.find(source => source.source_version_id === item.source_version_id)?.name ?? item.source_version_id} · {humanLabel(item.reason)}</p>)}</details>}<h3>Scope & competency questions</h3>{snapshot?.user_tasks.map(task => <p key={task.id}>{task.id} · {task.statement}{task.author && <small> · {task.author} · {task.written_at} · {task.basis}</small>}</p>)}</> : <><h2>Add source material & scope</h2>
        <label>Input case<select value={benchmarkCaseId} onChange={event => chooseBenchmark(event.target.value)}><option value="">Custom documents</option>{benchmarks.map(item => <option key={item.case_id} value={item.case_id} disabled={!item.raw_file_count}>{humanLabel(item.case_id)} · {item.raw_file_count} raw files</option>)}</select></label>
        <BaseProfileField profiles={baseProfiles} value={baseProfileId} onChange={value => { setBaseProfileId(value); setBaseCheck(Boolean(value)); }} />
        <p className="workflow-muted">Choose the version the profile originally extended to reproduce it. For a new profile, select the version you plan to extend.</p>
        {benchmarkCaseId === 'mobilitydcat' && <p className={baseProfileId === 'dcat-ap-2.0.1' ? 'workflow-muted' : 'workflow-notice'}>Mobility reproduction uses DCAT-AP 2.0.1.{baseProfileId !== 'dcat-ap-2.0.1' && ' This selection creates a comparison against a different base.'}</p>}
        <label className="workflow-check"><input type="checkbox" disabled={!baseProfileId} checked={Boolean(baseProfileId) && baseCheck} onChange={event => setBaseCheck(event.target.checked)} />Filter proposals supported only by the base specification (needs); inherited candidates in offline modes</label>
        {selectedBenchmark && <div>
          <p>{selectedBenchmark.raw_file_count} allowlisted raw documents. {selectedBenchmark.base_profile_id ? `Default base: ${selectedBenchmark.base_profile_id}.` : 'A base version has not been selected for this case.'}</p>
          {!!selectedBenchmark.background_source_names.length && <label className="workflow-check"><input type="checkbox" checked={treatBaseAsBackground} onChange={event => setTreatBaseAsBackground(event.target.checked)} />Treat base specifications as background</label>}
          {!!selectedBenchmark.background_source_names.length && <p className="workflow-muted">Background: {selectedBenchmark.background_source_names.join(', ')}. These files stay available for provenance and their text is excluded from extraction.</p>}
          <button disabled={busy || !selectedBenchmark.raw_file_count} onClick={() => void importBenchmark()}>{benchmarkImport?.caseId === benchmarkCaseId ? 'Reload benchmark sources' : 'Load benchmark sources'}</button>
          {benchmarkNeedsImport && <p className="workflow-notice">Load this case with the selected background setting before starting. Reloading creates source versions for these settings.</p>}
          {!benchmarkNeedsImport && <p className="workflow-notice">Sources loaded for this case. Starting also saves the scope and questions below.</p>}
        </div>}
        <label>Use-case scoping<select value={scoping} onChange={event => setScoping(event.target.value)}><option value="auto">Use declared tasks when present; otherwise off</option><option value="use_cases">Only needs necessary for declared use cases</option><option value="off">Off · retain needs without a use-case claim</option></select></label><label>Competency questions / user tasks<textarea rows={3} value={tasks} onChange={event => setTasks(event.target.value)} placeholder="One task per line" /></label>
        {benchmarkImport?.caseId === benchmarkCaseId && !!benchmarkImport?.userTasks?.length && <details><summary>Imported use cases · author, date and purpose</summary>{benchmarkImport.userTasks.map(task => <p key={task.id}>{task.id} · {humanLabel(task.kind)} · {task.author} · {task.written_at}<br />{task.basis}</p>)}<p>{benchmarkImport.useCaseInput?.file} · {benchmarkImport.useCaseInput?.sha256}</p><p>Editing the text creates manual tasks and removes the imported file provenance.</p></details>}
        {!benchmarkCaseId && <><label>Source role<select value={sourceRole} onChange={event => setSourceRole(event.target.value)}>
          {['stakeholder_need', 'normative_spec', 'example', 'observation', 'background', 'evaluation_reference'].map(role => <option key={role} value={role}>{humanLabel(role)}</option>)}
        </select></label>
        <label>Authority or stakeholder<input value={authority} onChange={event => setAuthority(event.target.value)} placeholder="Who provided this source?" /></label>
        <label>Source text<textarea rows={5} value={text} onChange={event => setText(event.target.value)} /></label>
        <button disabled={busy || !text.trim()} onClick={() => void act(() => addArtifact('stakeholder-needs.md', text))}>Save text source</button>
        <label className="workflow-upload">Upload documents or structured sources<input type="file" multiple accept=".html,.htm,.txt,.md,.csv,.tsv,.pdf,.json,.xml,.aas,.aasx,.ttl,.trig,.nq,.nt,.rdf,.jsonld,.ifc" disabled={busy} onChange={event => { void upload(event.target.files); event.target.value = ''; }} /></label>
        <p className="workflow-muted">Text, PDF, AAS, RDF/DCAT, IFC. Background material and evaluation references are excluded from model inputs.</p></>}
        <div className="workflow-sources">{sources.filter(source => !source.parent_source_version_id && (!benchmarkCaseId || (!benchmarkNeedsImport && benchmarkImport?.sourceVersionIds.includes(source.source_version_id)))).map(source => <article key={source.source_version_id}>
          <label className="workflow-check"><input type="checkbox" disabled={source.parse_status !== 'parsed' || ['background', 'evaluation_reference'].includes(source.source_role)} checked={selectedSources.includes(source.source_version_id)} onChange={event => setSelectedSources(previous => event.target.checked ? [...previous, source.source_version_id] : previous.filter(id => id !== source.source_version_id))} /><strong>{source.name}</strong></label>
          <small>{source.artifact_kind} · {humanLabel(source.source_role)} · {source.parse_status}</small>
          <details><summary>Version and diagnostics</summary><code>{source.raw_sha256}</code>{source.diagnostics.map((message, i) => <p key={i}>{message}</p>)}</details>
        </article>)}</div>
      </>}
    </section>}
    {page === 'decomposition' && <section className="workflow-panel"><h2>Saved evidence units</h2><p>Inspect extracted text and its original-source address before relying on it.</p>
      {run ? <div className="workflow-evidence-list">{run.evidence_ids.map(id => <button key={id} onClick={() => void inspectEvidence(id)}>{id.slice(0, 18)}…</button>)}</div> : <>{!previewUnits.length && <p>Select and save sources on the Sources page first.</p>}{previewUnits.map(unit => <article key={unit.evidence_id}><p>{unit.preview}</p><button onClick={() => void inspectEvidence(unit.evidence_id)}>Inspect {humanLabel(unit.kind)}</button></article>)}</>}
    </section>}
    {page === 'role_selection' && (run ? <>
          <RoleManifestView key={`${run.run_id}-${run.role_manifest?.manifest_hash ?? 'pending'}`} run={run} busy={busy} inspect={id => void inspectEvidence(id)} override={(roleOverrides, rationale, limit, live) => act(async () => {
            const created = await workflowApi<Run>('/runs', { output_form: 'needs', scoping: run.request?.scoping ?? null, snapshot_id: run.snapshot_id, execution_mode: run.request?.execution_mode ?? 'stepwise', discussion: run.request?.discussion ?? 'automatic', consolidation: run.request?.consolidation ?? 'exact', base_profile_id: run.base_profile_id ?? null, base_check: run.request?.base_check ?? false, benchmark_case_id: run.request?.benchmark_case_id ?? null, strategy: run.strategy, role_selection: 'override', role_overrides: roleOverrides, based_on_run_id: run.run_id, override_rationale: rationale, max_roles: limit, allow_live_provider: live, name: 'Requirements extraction · edited panel' });
            setActiveRecord(null); setSelectedRevisions([]); await loadRun(created.run_id); await refreshLists(); onStatus('New run saved with your panel override.');
          })} />
      {run.role_manifest?.status === 'not_applicable' && <section className="workflow-panel"><h2>Rules baseline</h2><p>This offline baseline does not select stakeholder agents. Continue to extract rule-based observations.</p></section>}
    </> : <section className="workflow-panel"><h2>Configure & start the saved workflow</h2><p>{selectedSources.length} selected sources. Starting freezes the sources and questions together.</p>
        {benchmarkNeedsImport && <p className="workflow-error">The benchmark input settings changed. <button onClick={() => navigate('acquisition')}>Return to Sources and reload this case</button></p>}
        <p>Starting version: <strong>{baseProfiles.find(profile => profile.id === baseProfileId)?.label ?? 'No base selected'}</strong>. <button onClick={() => navigate('acquisition')}>Change starting version on Sources & scope</button></p>
        {baseProfileId && <p className="workflow-muted">Extraction states source-supported needs; the selected base is compared after grouping. This choice is saved with the run.</p>}
        <label>Progression<select value={executionMode} onChange={event => setExecutionMode(event.target.value)}><option value="stepwise">Step by step · pause for review</option><option value="automatic">Automatic · test run</option></select></label>
        <label>Execution<select value={strategy} onChange={event => { setStrategy(event.target.value); setAllowLive(false); }}>
          <option value="rules">Rules candidates · offline legacy</option><option value="mock">Perspective candidates · offline demo</option><option value="multi_agent">Needs workflow · independent agents</option>
        </select></label>
        {strategy !== 'rules' && <><label>Stakeholder panel<select value={roleSelection} onChange={event => setRoleSelection(event.target.value)}><option value="automatic">Select roles from sources and CQs</option><option value="manual">Use a fixed panel</option></select></label>{roleSelection === 'automatic' && <label>Maximum stakeholder roles<input type="number" min={1} max={8} value={maxRoles} onChange={event => setMaxRoles(Number(event.target.value))} /></label>}</>}
        {strategy !== 'rules' && roleSelection === 'manual' && <details><summary>{roles.length} selected perspectives</summary>{perspectives.map(role => <label key={role} className="workflow-check"><input type="checkbox" checked={roles.includes(role)} onChange={event => setRoles(previous => event.target.checked ? [...previous, role] : previous.filter(value => value !== role))} />{humanLabel(role)}</label>)}</details>}
        {strategy !== 'rules' && <label>Consolidation<select value={consolidation} onChange={event => setConsolidation(event.target.value)}><option value="semantic">Merge candidates with the same meaning</option><option value="exact">Exact copies only (earlier behaviour)</option></select></label>}
        {strategy === 'multi_agent' && <label>Discussion<select value={discussion} onChange={event => setDiscussion(event.target.value)}><option value="automatic">Discuss flagged needs automatically</option><option value="on_request">Only when a reviewer asks · fewer model calls</option></select></label>}
        {strategy === 'multi_agent' && <label className="workflow-check"><input type="checkbox" checked={allowLive} onChange={event => setAllowLive(event.target.checked)} />Allow calls to the configured model provider for this run</label>}
        {strategy === 'multi_agent' && <StepModelsSettings value={stepModels} onChange={setStepModels} />}
        <p className="workflow-muted">Offline modes require human semantic and quality assessment. Agent mode sends the selected corpus to your configured provider.</p>
        <p className="workflow-muted">Upload original documents and describe your scope or tasks. Check parsing diagnostics and proposed stakeholder perspectives; you do not need to extract roles or retype PDF passages first.</p>
        <button className="workflow-primary" disabled={busy || benchmarkNeedsImport || !selectedSources.length || (strategy !== 'rules' && roleSelection === 'manual' && !roles.length)} onClick={() => void startRun()}>Start saved workflow</button>
    </section>)}
    {run && page === 'elicitation' && <section className="workflow-panel"><h2>Independent extraction results</h2><p>Each perspective reads the frozen input independently.</p>{run.role_runs.some(role => role.status === 'failed') && <p className="workflow-error">Extraction is incomplete: {run.role_runs.filter(role => role.status === 'completed').length} of {run.role_runs.length} roles completed. Retained proposals do not establish full input coverage.</p>}
            <div className="workflow-role-list">{run.role_runs.map(role => <article key={role.role_id} className="workflow-role-run"><strong>{roleLabel(run, role.role_id)}</strong><span>{role.status}</span><small>{role.observation_ids?.length ?? run.observations?.filter(item => item.role_id === role.role_id).length ?? 0} proposals</small>{role.evidence_unit_count != null && <small>{role.processed_unit_count ?? 0} of {role.evidence_unit_count} evidence units processed</small>}{role.error && <p>{role.error}</p>}<details><summary>Recorded context</summary><code>{role.context_hash}</code></details></article>)}</div>
    <details><summary>Saved observations and batch audit</summary><pre>{JSON.stringify({ observations: run.observations, role_runs: run.role_runs }, null, 2)}</pre></details></section>}
    {run && run.request?.output_form !== 'needs' && page === 'normalization' && run.normalization_policy_version && <section className="workflow-panel">
      <p>{setAside.length} of {run.observations?.length ?? 0} proposals were set aside before evidence and quality checks. They remain in this audit.</p>
      {!!setAside.length && <details><summary>Show set-aside proposals</summary><label>Reason<select value={asideFilter} onChange={event => setAsideFilter(event.target.value)}><option value="all">All reasons · {setAside.length}</option>{Object.entries(asideReasons).map(([reason, label]) => <option key={reason} value={reason}>{label} · {setAside.filter(item => item.reason === reason).length}</option>)}</select></label>{filteredAside.map(item => {
        const observation = run.observations?.find(o => o.observation_id === item.observation_id);
        return <article key={item.observation_id}><strong>{observation?.statement ?? item.observation_id}</strong><p>{asideReasons[item.reason]} · {roleLabel(run, item.role_id)} · extractor support: {humanLabel(observation?.support_level ?? 'unknown')}</p>{item.base_check && <BaseCheckView check={item.base_check} />}</article>;
      })}<p>A reviewer can add a requirement with supporting evidence through the existing requirement editor.</p></details>}
    </section>}
    {run && page === 'consolidation' && run.consolidation_policy_version?.startsWith('rq1-semantic-consolidation-') && <section className="workflow-panel">
      <p>{run.metrics.normalized_count as number ?? run.stage_results?.normalization?.requirements?.length ?? 0} candidates → {resultRecords.length} review items: {mergedGroupIds.size} merged groups, {run.conflicts.filter(c => c.kind === 'obligation').length} obligation conflicts, {mergeEvents.reduce((n, e) => n + (e.attached_failed?.length ?? 0), 0)} failed duplicates attached, {consolidationEvents.filter(e => e.action === 'semantic_grouping_unavailable').length} chunks fell back to exact merging.</p>
      <p>Grouping is a model judgment. Members and differing obligation variants remain available for review and splitting.</p>
      {groupIds.map(id => { const members = groupMembers(id); const variants = resultRecords.filter(item => item.group_id === id); return <details key={id}>
        <summary>{variants[0]?.normalized_statement ?? id} · {members.length} proposals · {variants.length} obligation variants</summary>
        <p>Roles: {[...new Set(members.flatMap(item => item.contributing_roles))].map(role => roleLabel(run, role)).join(', ')}</p>
        {variants.map(item => <p key={item.revision_id}>{humanLabel(item.normalized_intent.obligation_hint)} · {members.filter(member => member.normalized_intent.obligation_hint === item.normalized_intent.obligation_hint).length} proposals · {humanLabel(item.lifecycle_state)}</p>)}
        {members.map(item => <article key={item.revision_id}><strong>{item.normalized_statement}</strong><p>Source {item.verification?.status ?? 'pending'} · {humanLabel(item.normalized_intent.obligation_hint)} · {item.contributing_roles.map(role => roleLabel(run, role)).join(', ')}</p>{item.base_check && <BaseCheckView check={item.base_check} />}</article>)}
      </details>; })}
    </section>}
    {run && ['normalization', 'verification', 'consolidation', 'adjudication'].includes(page) && <>
          <section className="workflow-panel"><h2>{labels[stages.indexOf(page)]}</h2>
            {!resultRecords.length && <p>No saved candidates for this step yet. Empty outputs and source evidence remain available for review.</p>}
            <div className="workflow-candidates">{resultRecords.map(item => <article key={item.revision_id} data-selected={activeRecord === item.revision_id}>
              <label className="workflow-check"><input type="checkbox" checked={selectedRevisions.includes(item.revision_id)} onChange={event => setSelectedRevisions(previous => event.target.checked ? [...previous, item.revision_id] : previous.filter(id => id !== item.revision_id))} /><strong>{item.normalized_statement}</strong></label>
              <div className="workflow-tags"><span>{humanLabel(item.lifecycle_state)}</span><span>Source {item.verification?.status ?? 'pending'}</span><span>Support {item.qualification?.support ?? 'pending'}</span></div>
              {item.base_check && <BaseCheckView check={item.base_check} />}
              {item.need_statement && <NeedSummaryView record={item} run={run} inspect={id => void inspectEvidence(id)} />}<small>{item.need_statement ? 'Perspectives: ' : humanLabel(item.requirement_type) + ' · '}{item.contributing_roles.map(id => roleLabel(run, id)).join(', ')}</small>
              {!item.need_statement && !!item.parent_revision_ids.length && <details><summary>Merged from {item.parent_revision_ids.length} proposals (roles: {item.contributing_roles.map(id => roleLabel(run, id)).join(', ')}) · Show members</summary>{item.parent_revision_ids.map(id => { const member = run.requirements.find(r => r.revision_id === id); return <p key={id}>{member?.normalized_statement ?? id} · Source {member?.verification?.status ?? 'pending'}</p>; })}</details>}
              {item.group_id && !!consolidationEvents.find(e => e.group_id === item.group_id && e.attached_failed?.length) && <details><summary>Show failed members retained for evidence repair</summary>{groupMembers(item.group_id).filter(member => member.verification?.status === 'fail').map(member => <p key={member.revision_id}>{member.normalized_statement} · Source fail</p>)}</details>}
              {item.group_id && variantsFor(item).length > 1 && <p><a href={`#/workflow/${run.run_id}/deliberation`}>Obligation variant: {humanLabel(item.normalized_intent.obligation_hint)} · {variantsFor(item).findIndex(variant => variant.revision_id === item.revision_id) + 1} of {variantsFor(item).length} · View conflict</a></p>}
              <button onClick={() => { setActiveRecord(currentRecords.find(current => current.revision_id === item.revision_id || current.parent_revision_ids.includes(item.revision_id))?.revision_id ?? item.revision_id); navigate('adjudication'); }}>Inspect and review</button>
            </article>)}</div>
            {page === 'adjudication' && selectedRevisions.length > 1 && <MergeEditor records={currentRecords.filter(r => selectedRevisions.includes(r.revision_id))} busy={busy || !['awaiting_human', 'completed'].includes(run.status)} submit={(draft) => act(async () => { await command('/decisions', { expected_version: run.version, idempotency_key: commandKey(), action: 'merge', revision_ids: selectedRevisions, rationale: draft.rationale, drafts: [draft] }); setSelectedRevisions([]); setActiveRecord(null); })} />}
            {page === 'adjudication' && ['awaiting_human', 'completed'].includes(run.status) && <AdditionEditor run={run} busy={busy} submit={draft => act(async () => { await command('/requirements', { expected_version: run.version, idempotency_key: commandKey(), draft, rationale: draft.rationale }); })} />}
          </section>
    </>}
    <div hidden={page !== 'adjudication'}>
          {run && record && <RequirementEditor key={record.revision_id} record={record} run={run} busy={busy || !['awaiting_human', 'completed'].includes(run.status) || record.lifecycle_state === 'set_aside'} inspect={id => void inspectEvidence(id)} submit={(path, payload) => act(async () => { await command(path, payload); })} />}
    </div>
    {run?.request?.output_form === 'needs' && ['normalization','consolidation','adjudication'].includes(page) && <NeedAsidesView run={run} busy={busy} review={id => { setActiveRecord(id); navigate('adjudication'); }} restore={(item,rationale) => act(async () => { await command('/restore', { expected_version:run.version, idempotency_key:commandKey(), observation_id:item.observation_id, reason:item.reason, need_id:item.need_id ?? null, rationale }); })} />}
    {run && page === 'deliberation' && <>
          <section className="workflow-panel"><h2>Discussion & disagreement</h2>
            {run.request?.discussion === 'on_request' && <p className="workflow-notice">Automatic discussion is off for this run. Candidates with review findings and flagged pairs went straight to human review with their reasons. A reviewer can still request a targeted discussion for a candidate.</p>}
            {!run.conflicts.length && <p>No potential conflicts detected by the current policy.</p>}
            {run.conflicts.map(conflict => <article className="workflow-conflict" key={conflict.conflict_id}><strong>{humanLabel(conflict.kind)} · {conflict.status}</strong><p>{conflict.rationale}</p>{conflict.revision_ids.map(id => <p key={id}>{run.requirements.find(r => r.revision_id === id)?.normalized_statement}</p>)}</article>)}
            {run.deliberations.map(item => <CaseView key={item.case_id} item={item} run={run} busy={busy} inspect={id => void inspectEvidence(id)} submit={(path, payload) => act(() => command(path, payload))} />)}
          </section>
    </>}
    {run && page === 'baseline' && <>
          <section className="workflow-panel"><h2>Validated baseline</h2><p>Publish accepted current revisions with their evidence, assessments, human decisions, and unresolved appendix.</p>
            <button className="workflow-primary" disabled={busy || !accepted.length} onClick={() => void act(async () => {
              const result = await workflowApi<{ run: Run; result: Baseline }>(`/runs/${run.run_id}/baselines`, { expected_version: run.version, idempotency_key: commandKey(), revision_ids: accepted, name: 'Validated profile requirements' }); setRun(result.run); setRuns(previous => previous.map(item => item.run_id === run.run_id ? { ...item, status: result.run.status, version: result.run.version } : item)); onStatus('Validated baseline saved.');
            })}>Publish {accepted.length} accepted requirements</button>
            {run.baselines?.map(baseline => <div className="workflow-toolbar" key={baseline.baseline_id}><span>{baseline.name}</span><a className="workflow-download" href={`/api/rq1/v2/runs/${run.run_id}/baselines/${baseline.baseline_id}?download=true`}>Download baseline</a></div>)}
          </section>
    </>}
    {!run && !['acquisition', 'decomposition', 'role_selection'].includes(page) && <section className="workflow-empty"><h2>No saved run selected</h2><p>Choose a saved run above, or configure roles to start a new workflow.</p><button onClick={() => navigate('role_selection')}>Configure workflow</button></section>}
    {run?.request?.output_form === 'needs' && <section className="workflow-panel"><h2>Needs processing progress</h2><p>Source-checked proposals become grouped needs before classification, use-case scoping and support assessment. No automatic result is a human approval.</p><div className="workflow-tags">{Object.entries(run.need_steps ?? {}).map(([step, result]) => <span key={step}>{humanLabel(step)} · {String(result.retained_count ?? result.need_count ?? result.passed_count ?? result.group_count ?? result.input_count ?? 'saved')}</span>)}</div><details><summary>Saved needs policies</summary><pre>{JSON.stringify(run.needs_policies, null, 2)}</pre></details></section>}
    {run && <details className="workflow-panel"><summary>Saved history & metrics</summary><a className="workflow-download" href={`/api/rq1/v2/runs/${run.run_id}/evaluation?download=true`}>Download metrics</a><pre>{JSON.stringify({ metrics: run.metrics, attempts: run.attempt_history }, null, 2)}</pre></details>}
    <div className="workflow-toolbar workflow-page-footer"><button disabled={pageIndex === 0} onClick={() => navigate(stages[pageIndex - 1])}>Previous step</button><span>{pageIndex + 1} of {stages.length} views · saved results stay with this run</span><button disabled={pageIndex === stages.length - 1} onClick={() => navigate(stages[pageIndex + 1])}>Next step</button></div>
    {evidence && <div className="workflow-evidence-overlay" role="dialog" aria-modal="true" aria-label="Evidence inspector"><section className="workflow-panel"><button onClick={() => setEvidence(null)}>Close evidence inspector</button><h2>{humanLabel(evidence.unit.kind)}</h2><p>{humanLabel(evidence.unit.source_claim_kind)} · source {evidence.resolution.status}</p><pre>{evidence.unit.content}</pre><details open><summary>Address and structural context</summary><pre>{JSON.stringify({ selector: evidence.unit.selector, context: evidence.unit.structural_context, resolution: evidence.resolution }, null, 2)}</pre></details></section></div>}
  </main>;
}

function BaseProfileField({ profiles, value, onChange }: { profiles: BaseProfileSummary[]; value: string; onChange: (value: string) => void }) {
  const selected = profiles.find(profile => profile.id === value);
  return <><label>Starting DCAT / DCAT-AP version<select value={value} onChange={event => onChange(event.target.value)}><option value="">No base profile selected · exploratory extraction</option>{value && !selected && <option value={value}>{value} · saved selection</option>}{(['DCAT-AP', 'DCAT'] as const).map(family => <optgroup key={family} label={family === 'DCAT-AP' ? 'DCAT-AP application profiles' : 'W3C DCAT vocabularies'}>{profiles.filter(profile => profile.family === family).map(profile => <option key={profile.id} value={profile.id}>{profile.label}</option>)}</optgroup>)}</select></label>{selected && <p className="workflow-muted">{selected.description}</p>}</>;
}

function BaseCheckView({ check }: { check: BaseCheck }) {
  const relation = check.relation === 'loosened' ? 'Loosened · conflicts with base' : humanLabel(check.relation);
  return <div>
    <div className="workflow-tags"><span>{relation}</span>{check.property && <span>{check.property}</span>}{check.requires_review && <span>Provisional base mapping · needs review</span>}</div>
    <p className={check.relation === 'loosened' ? 'workflow-error' : 'workflow-muted'}>{check.class || 'Unresolved class'}{check.property ? ` / ${check.property}` : ''} · base obligation {check.base_obligation ?? 'no base property'} · candidate obligation {check.candidate_obligation}.</p>
    <details><summary>Base comparison audit</summary><p>{check.base_profile} · matched by {humanLabel(check.resolved_via)}.</p>{!!check.constraint_signals.length && <p>Added constraints: {check.constraint_signals.map(humanLabel).join(', ')}.</p>}{check.notes?.map((note, i) => <p key={i}>{note}</p>)}</details>
  </div>;
}

function AdditionEditor({ run, busy, submit }: { run: Run; busy: boolean; submit: (draft: { statement: string; rationale: string; evidence_links: Link[]; scope: string }) => Promise<void> }) {
  const [statement, setStatement] = useState(''); const [rationale, setRationale] = useState('');
  const [scope, setScope] = useState(''); const [quote, setQuote] = useState('');
  const [evidenceId, setEvidenceId] = useState(run.evidence_ids[0]);
  return <details><summary>Add a requirement missed by extraction</summary><p>A human proposal is tracked separately from machine output. It starts unaccepted. State a term-free need and inspect its source, scope, obligation and support.</p>
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
    {record.need_statement && <NeedSummaryView record={record} run={run} inspect={inspect} />}
    {record.base_check && <BaseCheckView check={record.base_check} />}
    {record.evidence_links.map((link, i) => <blockquote key={i}><p className="workflow-quote">{link.quote}</p><button onClick={() => inspect(link.evidence_id)}>{link.relation} · {link.component} · inspect original evidence</button></blockquote>)}
    {record.verification?.links.filter(link => link.status !== 'pass').map((link, i) => <p className="workflow-error" key={i}>{link.message}</p>)}
    <p>{record.qualification?.rationale}</p>{record.qualification?.findings.map((finding, i) => <p key={i}><strong>{finding.criterion}:</strong> {finding.message}</p>)}
    <label>Decision / assessment rationale<textarea value={rationale} onChange={event => setRationale(event.target.value)} /></label>
    <details open><summary>Semantic and quality assessment</summary><label>Evidence support<select value={support} onChange={event => setSupport(event.target.value)}>{['explicit', 'inferred', 'unsupported', 'contradicted', 'uncertain'].map(value => <option key={value}>{value}</option>)}</select></label>
      <label className="workflow-check"><input type="checkbox" checked={checked} onChange={event => setChecked(event.target.checked)} />I assessed support, atomicity, clarity, scope, obligation, relevance, and implementation neutrality.</label>
      <button disabled={busy || !checked || !rationale.trim() || record.verification?.status !== 'pass'} onClick={() => void submit('/assessments', { expected_version: run.version, idempotency_key: commandKey(), revision_id: record.revision_id, qualification: { support, rationale, findings: [], assessor: 'human', revision_hash: record.content_hash } })}>Save human assessment</button>
    </details>
    <div className="workflow-toolbar"><button disabled={busy || !rationale.trim()} onClick={() => void submit('/decisions', { ...payload, action: 'accept', conflict_ids: applicable.map(c => c.conflict_id) })}>Accept this revision</button><button disabled={busy || !rationale.trim()} onClick={() => void submit('/decisions', { ...payload, action: 'reject' })}>Reject</button><button disabled={busy || !rationale.trim()} onClick={() => void submit('/decisions', { ...payload, action: 'defer' })}>Defer</button><button disabled={busy || !rationale.trim()} onClick={() => void submit('/decisions', { ...payload, action: 'out_of_scope' })}>Out of scope</button></div>
    <details><summary>Edit or split · creates unaccepted revisions</summary><label>Revised statement<textarea value={statement} onChange={event => setStatement(event.target.value)} /></label><label>Scope<input value={scope} onChange={event => setScope(event.target.value)} /></label>
      {!record.need_statement && <><label>Requirement type<select value={type} onChange={event => setType(event.target.value)}>{['descriptive_metadata','semantic_anchor','technical_metadata','access_policy','quality_provenance','lifecycle_context','controlled_vocabulary','validation_constraint','competency_question','unknown'].map(value => <option key={value}>{value}</option>)}</select></label>
      <label>Resource<select value={resource} onChange={event => setResource(event.target.value)}>{['Catalog','CatalogRecord','Dataset','Distribution','DataService','Agent','Concept','Unknown'].map(value => <option key={value}>{value}</option>)}</select></label>
      <label>Intended metadata need<input value={metadataNeed} onChange={event => setMetadataNeed(event.target.value)} /></label>
      <label>Expected value kind<select value={valueKind} onChange={event => setValueKind(event.target.value)}>{['literal','uri','controlled_concept','class_reference','date','agent','distribution','unknown'].map(value => <option key={value}>{value}</option>)}</select></label></>}
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
  return <article className="workflow-case"><h3>{item.triggers.map(humanLabel).join(' · ')}</h3><p>{item.status} · {item.participants.map(id => roleLabel(run, id)).join(', ')} · bounded to {item.max_rounds} rounds / {item.max_calls} calls</p>
    {item.messages.map(message => <blockquote key={message.message_id}><strong>{roleLabel(run, message.role_id)}{message.round ? ` · round ${message.round}` : ''}</strong><p>{message.body}</p>{message.proposed_statement && <p>Proposed: {message.proposed_statement}</p>}{message.evidence_ids.map(id => <button key={id} onClick={() => inspect(id)}>Inspect cited evidence</button>)}</blockquote>)}
    {item.stop_reason && <p>Stopped: {humanLabel(item.stop_reason)}</p>}
    {item.status === 'unresolved' && <p>The participants have stopped contributing. This issue remains unresolved for your review.</p>}
    <p>Discussion proposals do not change or approve requirements. Review the evidence before applying a revision.</p>
    <label>Human contribution or closure rationale<textarea value={body} onChange={event => setBody(event.target.value)} /></label>
    <div className="workflow-toolbar"><button disabled={busy || !body.trim()} onClick={() => void submit(`/deliberations/${item.case_id}/messages`, { expected_version: run.version, idempotency_key: commandKey(), body, evidence_ids: [] })}>Add to saved thread</button><button disabled={busy || !body.trim() || item.status === 'running'} onClick={() => void submit(`/deliberations/${item.case_id}/close`, { expected_version: run.version, idempotency_key: commandKey(), body, evidence_ids: [] })}>Close for human adjudication</button></div>
  </article>;
}
