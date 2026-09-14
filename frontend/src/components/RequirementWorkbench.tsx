import { useCallback, useEffect, useMemo, useState, type DragEvent } from 'react';
import { AlertTriangle, CheckCircle2, Download, FileCode, FileSearch, GitMerge, RefreshCw, Search, SplitSquareHorizontal, Wand2, XCircle } from 'lucide-react';
import {
  analyzeArtifacts,
  extractRequirements,
  type AnalysisRequest,
  type AnalysisResponse,
  type AgentContextInput,
  type ArtifactPayload,
  type CandidateMetadataAction,
  type CandidateRequirement,
  type ExtractedAttribute,
  type ExtractionStrategy,
  type ExtractionProvenance,
  type NormalizedIntent,
  type RequirementScope,
  type Rq1DatasetExport,
  type Rq1LocalMergeEvent,
  type Rq1LocalSplitEvent,
  type SourceEvidence,
  type StudyMode,
  type UserTask,
  type ValidationStatus,
} from '../lib/requirementApi';
import { AgentContributionView, CritiqueFindingsView } from './requirements/AgentContributionView';
import { AgentRunSummary } from './requirements/AgentRunSummary';
import { EvaluationWorkflowPanel } from './requirements/EvaluationWorkflowPanel';
import { MultiAgentSetupPanel } from './requirements/MultiAgentSetupPanel';
import { downloadText } from '../lib/download';

type RequirementWorkbenchProps = {
  initialView: 'requirements';
  onStatus: (status: string) => void;
};

type WorkbenchView = 'requirements' | 'evaluation';
type RequirementStatus = CandidateRequirement['status'];
type RequirementType = CandidateRequirement['requirement_type'];
type FairDimension = CandidateRequirement['fair_dimensions'][number];
type EditorHistoryAction = 'edit' | 'approve' | 'reject' | 'mark_needs_review' | 'edit_candidate_metadata_action';

const SAMPLE_TEXT =
  'Datasets should indicate the construction asset type they describe. Metadata should include lifecycle phase, access conditions, format, schema version, and semantic anchors to AAS submodels or IFC entities.';

const ARTIFACT_ACCEPT = '.txt,.md,.json,.aasx,.jsonld,.ttl,.rdf,.owl,.ifc,.ifcspf';
const FAIR_DIMENSIONS: FairDimension[] = ['F', 'A', 'I', 'R'];
const REQUIREMENT_TYPES: RequirementType[] = [
  'descriptive_metadata',
  'semantic_anchor',
  'technical_metadata',
  'access_policy',
  'quality_provenance',
  'lifecycle_context',
  'controlled_vocabulary',
  'validation_constraint',
  'competency_question',
  'unknown',
];
const STATUS_OPTIONS: RequirementStatus[] = ['candidate', 'approved', 'needs_review', 'rejected', 'merged'];
const VALIDATION_STATUS_OPTIONS: ValidationStatus[] = ['valid', 'missing_evidence', 'invalid_schema', 'unknown_term', 'resource_mismatch', 'needs_review'];
const REQUIREMENT_SCOPE_OPTIONS: RequirementScope[] = [
  'profile_element',
  'obligation_level',
  'controlled_vocabulary',
  'validation_constraint',
  'documentation_guidance',
  'example_requirement',
  'unknown',
];
const RESOURCE_TYPES: NormalizedIntent['resource_type'][] = ['Dataset', 'Distribution', 'Catalog', 'DataService', 'Agent', 'Concept', 'Unknown'];
const VALUE_KINDS: NormalizedIntent['value_kind'][] = ['literal', 'uri', 'controlled_concept', 'class_reference', 'date', 'agent', 'distribution', 'unknown'];
const OBLIGATION_HINTS: NormalizedIntent['obligation_hint'][] = ['mandatory', 'recommended', 'optional', 'unknown'];
const METADATA_ACTIONS: CandidateMetadataAction['action'][] = [
  'reuse_existing_term',
  'specialize_existing_term',
  'create_extension',
  'add_constraint',
  'add_usage_note',
  'no_action',
];
const RQ1_CODEBOOK_SUMMARY = {
  schema_version: 'rq1-codebook-v1',
  valid_requirement_conditions: [
    'Describes catalog, dataset, distribution, data service, or profile metadata rather than internal source content.',
    'Supports discovery, assessment, comparison, access, reuse, or selection.',
    'Can be represented by DCAT/DCAT-AP reuse or a justified profile extension.',
  ],
  exclude_as_not_rq1: [
    'internal_instance_data',
    'per_object_attribute',
    'engineering_calculation',
    'geometry_detail',
    'sensor_measurement_value',
    'ontology_class_mirroring',
    'implementation_detail',
  ],
};
const WORKBENCH_STARTED_AT = new Date().toISOString();
const WORKBENCH_SESSION_ID = `session-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
const WORKBENCH_REVIEWER_ID = window.localStorage.getItem('rqReviewerId') || 'local-reviewer';

export function RequirementWorkbench({ initialView, onStatus }: RequirementWorkbenchProps) {
  const [view, setView] = useState<WorkbenchView>(initialView);
  const [sourceCorpusId, setSourceCorpusId] = useState('pilot-corpus');
  const [cqGuided, setCqGuided] = useState(true);
  const [text, setText] = useState(SAMPLE_TEXT);
  const [strategy, setStrategy] = useState<ExtractionStrategy>('rules');
  const [studyMode, setStudyMode] = useState<StudyMode>('formative');
  const [panelPreset, setPanelPreset] = useState<'full_15' | 'extraction_12' | 'pilot_core'>('full_15');
  const [selectedAgentRoleIds, setSelectedAgentRoleIds] = useState<string[]>([]);
  const [agentContexts, setAgentContexts] = useState<Record<string, AgentContextInput>>({});
  const [taskText, setTaskText] = useState('');
  const [artifacts, setArtifacts] = useState<ArtifactPayload[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [requirements, setRequirements] = useState<CandidateRequirement[]>([]);
  const [localMergeEvents, setLocalMergeEvents] = useState<Rq1LocalMergeEvent[]>([]);
  const [localSplitEvents, setLocalSplitEvents] = useState<Rq1LocalSplitEvent[]>([]);
  const [selectedRequirementId, setSelectedRequirementId] = useState<string | null>(null);
  const [mergeSelection, setMergeSelection] = useState<Record<string, boolean>>({});
  const [statusFilter, setStatusFilter] = useState<'all' | RequirementStatus>('all');
  const [typeFilter, setTypeFilter] = useState<'all' | RequirementType>('all');
  const [validationFilter, setValidationFilter] = useState<'all' | ValidationStatus>('all');
  const [scopeFilter, setScopeFilter] = useState<'all' | RequirementScope>('all');
  const [draggingArtifacts, setDraggingArtifacts] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setView(initialView);
  }, [initialView]);

  useEffect(() => {
    if (!analysis) return;
    setRequirements(analysis.requirements);
    setLocalMergeEvents([]);
    setLocalSplitEvents([]);
    setSelectedRequirementId((current) => current ?? analysis.requirements[0]?.id ?? null);
    setMergeSelection({});
  }, [analysis]);

  const userTasks = useMemo<UserTask[]>(
    () =>
      taskText
        .split('\n')
        .map((line) => line.trim())
        .filter((line) => line && !line.startsWith('#'))
        .map((statement, index) => ({
          id: `task-${index + 1}`,
          statement,
          kind: statement.endsWith('?') ? ('competency_question' as const) : ('user_task' as const),
          source: 'workbench input',
        })),
    [taskText],
  );

  const requestPayload = useMemo<AnalysisRequest>(
    () => ({
      source_corpus_id: sourceCorpusId,
      text,
      artifacts,
      strategy,
      user_tasks: userTasks,
      cq_guided: cqGuided,
      study_mode: studyMode,
      study_phase: 'development',
      panel_preset: panelPreset,
      agent_role_ids: selectedAgentRoleIds,
      agent_contexts: Object.values(agentContexts).filter((context) => (
        context.background.trim()
        || context.rag_queries.length
        || context.rag_artifact_names.length
        || context.rag_material.trim()
      )),
    }),
    [agentContexts, artifacts, cqGuided, panelPreset, selectedAgentRoleIds, sourceCorpusId, strategy, studyMode, text, userTasks],
  );

  const filteredRequirements = useMemo(
    () =>
      requirements.filter((requirement) => {
        if (statusFilter !== 'all' && requirement.status !== statusFilter) return false;
        if (typeFilter !== 'all' && requirement.requirement_type !== typeFilter) return false;
        if (validationFilter !== 'all' && requirement.validation_status !== validationFilter) return false;
        if (scopeFilter !== 'all' && requirement.requirement_scope !== scopeFilter) return false;
        return true;
      }),
    [requirements, scopeFilter, statusFilter, typeFilter, validationFilter],
  );

  const selectedRequirement = useMemo(
    () => requirements.find((requirement) => requirement.id === selectedRequirementId) ?? requirements[0] ?? null,
    [requirements, selectedRequirementId],
  );

  const runAnalyze = useCallback(async () => {
    setBusy(true);
    onStatus('Analyzing artifacts into evidence units...');
    try {
      const result = await analyzeArtifacts(requestPayload);
      setAnalysis(result);
      onStatus(`Analyzed ${result.evidence_units.length} evidence unit(s) and ${result.requirements.length} candidate requirement(s) [${result.strategy} strategy].`);
      return result;
    } catch (error) {
      onStatus(`Requirement analysis failed: ${error instanceof Error ? error.message : 'unknown error'}`);
    } finally {
      setBusy(false);
    }
  }, [onStatus, requestPayload]);

  const runExtract = useCallback(async () => {
    setBusy(true);
    setView('requirements');
    onStatus('Extracting traceable requirement candidates...');
    try {
      const result = await extractRequirements(requestPayload);
      setAnalysis(result);
      onStatus(`Extracted ${result.requirements.length} requirement candidate(s) from ${result.evidence_units.length} evidence unit(s) [${result.strategy} strategy].`);
      return result;
    } catch (error) {
      onStatus(`Requirement extraction failed: ${error instanceof Error ? error.message : 'unknown error'}`);
    } finally {
      setBusy(false);
    }
  }, [onStatus, requestPayload]);

  const importFiles = useCallback(async (files: FileList | File[] | null) => {
    if (!files?.length) return;
    const loaded = await Promise.all(Array.from(files).map(fileToArtifact));
    setArtifacts((current) => [...current, ...loaded]);
    onStatus(`Loaded ${loaded.length} artifact file(s) for requirement extraction.`);
  }, [onStatus]);

  const onDropArtifacts = useCallback(
    async (event: DragEvent<HTMLElement>) => {
      event.preventDefault();
      event.stopPropagation();
      setDraggingArtifacts(false);
      await importFiles(event.dataTransfer.files);
    },
    [importFiles],
  );

  const updateRequirement = useCallback((id: string, patch: Partial<CandidateRequirement>) => {
    setRequirements((current) => current.map((requirement) => (requirement.id === id ? applyRequirementPatch(requirement, patch) : requirement)));
  }, []);

  const updateIntent = useCallback((id: string, patch: Partial<NormalizedIntent>) => {
    setRequirements((current) =>
      current.map((requirement) =>
        requirement.id === id ? applyIntentPatch(requirement, patch) : requirement,
      ),
    );
  }, []);

  const exportRq1Dataset = useCallback(() => {
    if (!analysis) {
      onStatus('Run extraction before exporting an RQ1 dataset.');
      return;
    }
    const dataset = buildRq1DatasetExport(analysis, requirements, localMergeEvents, localSplitEvents);
    downloadText(JSON.stringify(dataset, null, 2), 'rq1-requirement-dataset.json', 'application/json');
    onStatus(`Exported RQ1 dataset with ${requirements.length} reviewed requirement(s).`);
  }, [analysis, localMergeEvents, localSplitEvents, onStatus, requirements]);

  const mergeRequirements = useCallback((ids: string[], suggestedStatement?: string) => {
    const selected = requirements.filter((requirement) => ids.includes(requirement.id));
    if (selected.length < 2) {
      onStatus('Select at least two requirements to merge.');
      return;
    }
    const base = selected[0];
    const statement = suggestedStatement || selected.map(requirementStatement).join(' ');
    const timestamp = new Date().toISOString();
    const merged: CandidateRequirement = {
      ...base,
      id: `req-merged-${Date.now()}`,
      raw_statement: selected.map(requirementStatement).join(' / '),
      normalized_statement: statement,
      title: 'Merged requirement',
      description: statement,
      status: 'candidate',
      review_notes: 'Merged locally in the Requirement Workbench.',
      merged_from: selected.map((requirement) => requirement.id),
      source_evidence: uniqueEvidence(selected.flatMap((requirement) => requirement.source_evidence)),
      evidence: uniqueStrings(selected.flatMap((requirement) => requirement.evidence)),
      confidence: Math.max(...selected.map((requirement) => requirement.confidence)),
    };
    setRequirements((current) =>
      current.map((requirement): CandidateRequirement => (ids.includes(requirement.id) ? applyRequirementPatch(requirement, { status: 'merged' }) : requirement)).concat(merged),
    );
    setLocalMergeEvents((current) => [
      ...current,
      {
        timestamp,
        source_requirement_ids: selected.map((requirement) => requirement.id),
        merged_requirement_id: merged.id,
        normalized_statement: statement,
        suggested_statement_used: Boolean(suggestedStatement),
      },
    ]);
    setSelectedRequirementId(merged.id);
    setMergeSelection({});
    onStatus(`Merged ${selected.length} requirement candidates for review.`);
  }, [onStatus, requirements]);

  const splitRequirement = useCallback(() => {
    if (!selectedRequirement) return;
    const textToSplit = requirementStatement(selectedRequirement);
    const pieces = textToSplit.split(/\s+and\s+|;/i).map((part) => part.trim()).filter(Boolean);
    const parts = pieces.length > 1 ? pieces.slice(0, 2) : [textToSplit, `${textToSplit} (additional review item)`];
    const timestamp = new Date().toISOString();
    const splitToken = Date.now();
    const splitItems = parts.map((part, index): CandidateRequirement => ({
      ...selectedRequirement,
      id: `${selectedRequirement.id}-split-${index + 1}-${splitToken}`,
      raw_statement: selectedRequirement.raw_statement,
      normalized_statement: part,
      title: `${selectedRequirement.title || 'Requirement'} split ${index + 1}`,
      description: part,
      status: 'needs_review',
      review_notes: `Split from ${selectedRequirement.id}.`,
      merged_from: [selectedRequirement.id],
    }));
    setRequirements((current) =>
      current
        .map((requirement): CandidateRequirement => (requirement.id === selectedRequirement.id ? applyRequirementPatch(requirement, { status: 'merged' }) : requirement))
        .concat(splitItems),
    );
    setLocalSplitEvents((current) => [
      ...current,
      {
        timestamp,
        source_requirement_id: selectedRequirement.id,
        split_requirement_ids: splitItems.map((requirement) => requirement.id),
        source_statement: textToSplit,
      },
    ]);
    setSelectedRequirementId(splitItems[0].id);
    onStatus('Split the selected requirement into review items.');
  }, [onStatus, selectedRequirement]);

  return (
    <main className="requirement-workbench">
      <WorkflowGuide analysis={analysis} />
      <section
        className={`requirement-input-panel ${draggingArtifacts ? 'requirement-input-panel--dragging' : ''}`}
        onDragEnter={(event) => {
          event.preventDefault();
          event.stopPropagation();
          setDraggingArtifacts(true);
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          event.stopPropagation();
          if (event.currentTarget === event.target) setDraggingArtifacts(false);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = 'copy';
        }}
        onDrop={(event) => void onDropArtifacts(event)}
      >
        <div className="requirement-input-panel__header">
          <div>
            <h2>Requirement Workbench</h2>
            <p>Extract, inspect, and review evidence-backed metadata requirements.</p>
          </div>
          <label className="file-picker">
            <FileSearch size={16} />
            Add files
            <input accept={ARTIFACT_ACCEPT} multiple onChange={(event) => void importFiles(event.target.files)} type="file" />
          </label>
        </div>

        <div className="artifact-drop-zone">
          <FileSearch size={18} />
          <span>Drop artifacts</span>
          <small>Text, AAS JSON, AASX, DCAT/RDF, IFC</small>
        </div>

        <div className="study-setup-grid">
          <label>
            Source corpus ID
            <input onChange={(event) => setSourceCorpusId(event.target.value)} value={sourceCorpusId} />
          </label>
          <label className="toggle-row">
            <input checked={cqGuided} onChange={(event) => setCqGuided(event.target.checked)} type="checkbox" />
            CQ-guided extraction
          </label>
        </div>

        <div className="input-boundary-note">
          <strong>Extraction input</strong>
          <span>declared source corpus and predefined competency questions or user tasks</span>
          <strong>Held out</strong>
          <span>expert ratings, expert reference requirements, expected answer sets, gold requirements, and post-run corrections</span>
        </div>

        <textarea aria-label="Requirement text" className="requirement-textarea" onChange={(event) => setText(event.target.value)} value={text} />

        <textarea
          aria-label="Competency questions and user tasks"
          className="requirement-textarea requirement-textarea--tasks"
          onChange={(event) => setTaskText(event.target.value)}
          placeholder={'Competency questions / user tasks (one per line), e.g.\nWhich datasets describe HVAC equipment in building X?'}
          rows={3}
          value={taskText}
        />

        <label className="requirement-strategy">
          Extraction strategy
          <select onChange={(event) => setStrategy(event.target.value as ExtractionStrategy)} value={strategy}>
            <option value="rules">Rule-based (baseline)</option>
            <option value="llm">LLM-assisted (verified evidence)</option>
            <option value="hybrid">Hybrid (LLM + rules)</option>
            <option value="multi_agent">Multi-agent panel (role-conditioned)</option>
          </select>
        </label>

        {strategy === 'multi_agent' ? (
          <MultiAgentSetupPanel
            agentContexts={agentContexts}
            artifacts={artifacts}
            preset={panelPreset}
            selectedRoleIds={selectedAgentRoleIds}
            setAgentContexts={setAgentContexts}
            setPreset={setPanelPreset}
            setSelectedRoleIds={setSelectedAgentRoleIds}
            setStudyMode={setStudyMode}
            studyMode={studyMode}
          />
        ) : null}

        {artifacts.length ? (
          <div className="artifact-list">
            {artifacts.map((artifact) => (
              <span key={`${artifact.name}-${artifact.content.length}`}>{artifact.name}</span>
            ))}
          </div>
        ) : null}

        <div className="requirement-actions">
          <button disabled={busy} onClick={() => void runAnalyze()} type="button">
            <Search size={16} />
            Analyze
          </button>
          <button disabled={busy} onClick={() => void runExtract()} type="button">
            <CheckCircle2 size={16} />
            Extract
          </button>
        </div>
      </section>

      {analysis ? <AgentRunSummary analysis={analysis} /> : null}

      <section className="requirement-review-panel">
        <div className="workflow-tabs">
          {[
            ['requirements', 'Requirement Review'],
            ['evaluation', 'Expert Evaluation'],
          ].map(([id, label]) => (
            <button className={view === id ? 'active' : undefined} key={id} onClick={() => setView(id as WorkbenchView)} type="button">
              {label}
            </button>
          ))}
        </div>

        {view === 'requirements' ? (
          <RequirementReview
            analysis={analysis}
            filteredRequirements={filteredRequirements}
            mergeRequirements={mergeRequirements}
            mergeSelection={mergeSelection}
            requirements={requirements}
            selectedRequirement={selectedRequirement}
            setMergeSelection={setMergeSelection}
            setSelectedRequirementId={setSelectedRequirementId}
            setScopeFilter={setScopeFilter}
            setStatusFilter={setStatusFilter}
            setTypeFilter={setTypeFilter}
            setValidationFilter={setValidationFilter}
            scopeFilter={scopeFilter}
            splitRequirement={splitRequirement}
            statusFilter={statusFilter}
            typeFilter={typeFilter}
            updateIntent={updateIntent}
            updateRequirement={updateRequirement}
            validationFilter={validationFilter}
            onExportRq1Dataset={exportRq1Dataset}
          />
        ) : view === 'evaluation' ? (
          <EvaluationWorkflowPanel
            analysis={analysis}
            onStatus={onStatus}
            onValidatedBaseline={(baseline) => {
              setRequirements(baseline.requirements);
              setSelectedRequirementId(baseline.requirements[0]?.id ?? null);
              setView('requirements');
            }}
          />
        ) : null}
      </section>
    </main>
  );
}

function WorkflowGuide({ analysis }: { analysis: AnalysisResponse | null }) {
  return (
    <section className="guided-workflow-shell" aria-label="RQ1 workflow">
      <div className="guided-workflow-shell__header">
        <div><h2>From evidence to reviewed requirements</h2><p>Trace each requirement through its source evidence, agent contributions, critiques, and human decisions.</p></div>
        <span>{analysis ? `${analysis.requirements.length} candidates` : 'Ready for a new study'}</span>
      </div>
      <div className="workflow-step-grid">
        {['Sources & questions', 'Extract & inspect', 'Review & evaluate', 'Export to VPE'].map((title, i) => <article key={title}><span>{i + 1}</span><h3>{title}</h3></article>)}
      </div>
      <p className="candidate-term-note">RQ1 ends with a reviewed requirement set. Profile generation continues in VPE.</p>
    </section>
  );
}

function RequirementReview({
  analysis,
  filteredRequirements,
  mergeRequirements,
  mergeSelection,
  requirements,
  selectedRequirement,
  setMergeSelection,
  setSelectedRequirementId,
  setScopeFilter,
  setStatusFilter,
  setTypeFilter,
  setValidationFilter,
  scopeFilter,
  splitRequirement,
  statusFilter,
  typeFilter,
  updateIntent,
  updateRequirement,
  validationFilter,
  onExportRq1Dataset,
}: {
  analysis: AnalysisResponse | null;
  filteredRequirements: CandidateRequirement[];
  mergeRequirements: (ids: string[], suggestedStatement?: string) => void;
  mergeSelection: Record<string, boolean>;
  requirements: CandidateRequirement[];
  selectedRequirement: CandidateRequirement | null;
  setMergeSelection: (selection: Record<string, boolean>) => void;
  setSelectedRequirementId: (id: string) => void;
  setScopeFilter: (scope: 'all' | RequirementScope) => void;
  setStatusFilter: (status: 'all' | RequirementStatus) => void;
  setTypeFilter: (type: 'all' | RequirementType) => void;
  setValidationFilter: (status: 'all' | ValidationStatus) => void;
  scopeFilter: 'all' | RequirementScope;
  splitRequirement: () => void;
  statusFilter: 'all' | RequirementStatus;
  typeFilter: 'all' | RequirementType;
  updateIntent: (id: string, patch: Partial<NormalizedIntent>) => void;
  updateRequirement: (id: string, patch: Partial<CandidateRequirement>) => void;
  validationFilter: 'all' | ValidationStatus;
  onExportRq1Dataset: () => void;
}) {
  if (!analysis) {
    return <EmptyState text="Run Extract to build evidence units and reviewable requirement records." />;
  }

  const selectedMergeIds = Object.entries(mergeSelection).filter(([, checked]) => checked).map(([id]) => id);

  return (
    <div className="review-workspace">
      <ReviewOverview analysis={analysis} requirements={requirements} />
      <FunnelMetrics metrics={analysis.funnel_metrics} />
      <Rq1CodebookPanel />
      <ValidationWarnings requirements={requirements} />
      <div className="requirement-review-grid">
        <section className="requirement-list-panel">
          <div className="panel-title-row">
            <div>
              <h3>Requirement Queue</h3>
              <small>{filteredRequirements.length} shown</small>
            </div>
            <button onClick={onExportRq1Dataset} type="button">
              <Download size={16} />
              Export RQ1 Dataset
            </button>
          </div>
          <div className="requirement-filters">
            <label>
              Status
              <select onChange={(event) => setStatusFilter(event.target.value as 'all' | RequirementStatus)} value={statusFilter}>
                <option value="all">All</option>
                {STATUS_OPTIONS.map((status) => (
                  <option key={status} value={status}>{humanize(status)}</option>
                ))}
              </select>
            </label>
            <label>
              Type
              <select onChange={(event) => setTypeFilter(event.target.value as 'all' | RequirementType)} value={typeFilter}>
                <option value="all">All</option>
                {REQUIREMENT_TYPES.map((type) => (
                  <option key={type} value={type}>{humanize(type)}</option>
                ))}
              </select>
            </label>
            <label>
              Validation
              <select onChange={(event) => setValidationFilter(event.target.value as 'all' | ValidationStatus)} value={validationFilter}>
                <option value="all">All</option>
                {VALIDATION_STATUS_OPTIONS.map((status) => (
                  <option key={status} value={status}>{humanize(status)}</option>
                ))}
              </select>
            </label>
            <label>
              Scope
              <select onChange={(event) => setScopeFilter(event.target.value as 'all' | RequirementScope)} value={scopeFilter}>
                <option value="all">All</option>
                {REQUIREMENT_SCOPE_OPTIONS.map((scope) => (
                  <option key={scope} value={scope}>{humanize(scope)}</option>
                ))}
              </select>
            </label>
          </div>

          <div className="review-list">
            {filteredRequirements.map((requirement, index) => (
              <article className={`review-list-item ${selectedRequirement?.id === requirement.id ? 'active' : ''}`} key={requirement.id}>
                <label className="merge-checkbox" title="Select for merge">
                  <input
                    checked={mergeSelection[requirement.id] === true}
                    onChange={(event) => setMergeSelection({ ...mergeSelection, [requirement.id]: event.target.checked })}
                    type="checkbox"
                  />
                </label>
                <button onClick={() => setSelectedRequirementId(requirement.id)} type="button">
                  <span className="queue-index">{index + 1}</span>
                  <strong>{shortStatement(requirement)}</strong>
                  <span>{humanize(requirement.requirement_type)} - {formatConfidence(requirement.confidence)}</span>
                  <RequirementMetaStrip requirement={requirement} />
                  <small className={`status-pill status-pill--${requirement.status}`}>{humanize(requirement.status)}</small>
                </button>
              </article>
            ))}
          </div>

          <div className="merge-actions">
            <button disabled={selectedMergeIds.length < 2} onClick={() => mergeRequirements(selectedMergeIds)} type="button">
              <GitMerge size={16} />
              Merge selected
            </button>
          </div>
        </section>

        <RequirementDetail
          analysis={analysis}
          mergeRequirements={mergeRequirements}
          requirement={selectedRequirement}
          requirements={requirements}
          splitRequirement={splitRequirement}
          updateIntent={updateIntent}
          updateRequirement={updateRequirement}
        />
      </div>
    </div>
  );
}

function ReviewOverview({ analysis, requirements }: { analysis: AnalysisResponse; requirements: CandidateRequirement[] }) {
  const approved = requirements.filter((requirement) => requirement.status === 'approved').length;
  const needsReview = requirements.filter((requirement) => requirement.status === 'needs_review').length;
  const rejected = requirements.filter((requirement) => requirement.status === 'rejected').length;

  return (
    <section className="review-overview" aria-label="Requirement review overview">
      <div>
        <h3>Review extracted requirements</h3>
        <p>Evidence-backed extraction results. Export the reviewed set for downstream VPE use; rejected and unresolved items remain traceable.</p>
      </div>
      <div className="review-overview__stats">
        <span><strong>{requirements.length}</strong> total</span>
        <span><strong>{approved}</strong> approved</span>
        <span><strong>{needsReview}</strong> needs review</span>
        <span><strong>{rejected}</strong> rejected</span>
        <span><strong>{analysis.evidence_units.length}</strong> evidence</span>
        <span><strong>{analysis.duplicate_groups.length}</strong> duplicate hints</span>
      </div>
    </section>
  );
}

function FunnelMetrics({ metrics }: { metrics: Record<string, unknown> }) {
  const metric = (key: string) => Number(metrics[key] ?? 0);
  return (
    <section className="funnel-metrics" aria-label="Extraction funnel metrics">
      <span><strong>{metric('evidence_unit_count')}</strong> evidence units</span>
      <span><strong>{metric('source_signal_count')}</strong> source signals</span>
      <span><strong>{metric('candidate_requirement_count')}</strong> candidate requirements</span>
      <span><strong>{metric('discarded_domain_content_count')}</strong> discarded domain-content signals</span>
      <span><strong>{metric('merged_duplicate_count')}</strong> duplicate reductions</span>
    </section>
  );
}

function Rq1CodebookPanel() {
  return (
    <details className="rq1-codebook-panel">
      <summary>What counts as an RQ1 requirement?</summary>
      <div>
        <p>Valid RQ1 candidates describe catalog/dataset/distribution metadata, support discovery or assessment tasks, and can be represented by DCAT/DCAT-AP reuse or a justified extension.</p>
        <ul>
          <li>Good: dataset exposes represented asset/entity types for discovery.</li>
          <li>Exclude: {RQ1_CODEBOOK_SUMMARY.exclude_as_not_rq1.map(humanize).join(', ')}.</li>
          <li>Held out: expert reference requirements and expected answer sets stay out of extraction and belong in validation.</li>
        </ul>
      </div>
    </details>
  );
}

function ValidationWarnings({ requirements }: { requirements: CandidateRequirement[] }) {
  const warnings = requirements.filter((requirement) => requirement.validation_status !== 'valid');
  if (!warnings.length) return null;

  return (
    <section className="validation-warning-panel" aria-label="Validation warnings">
      <div>
        <h3>Validation warnings</h3>
        <p>{warnings.length} requirement(s) need machine-validation review before RQ1 export.</p>
      </div>
      <div className="validation-warning-list">
        {warnings.map((requirement) => (
          <article key={requirement.id}>
            <strong>{shortStatement(requirement)}</strong>
            <span>{humanize(requirement.validation_status)}</span>
          </article>
        ))}
      </div>
    </section>
  );
}

function RequirementMetaStrip({ requirement }: { requirement: CandidateRequirement }) {
  return (
    <span className="requirement-meta-strip">
      <small>{humanize(requirement.validation_status)}</small>
      <small>{humanize(requirement.requirement_scope)}</small>
      <small>{requirement.provenance?.strategy ?? 'unknown strategy'}</small>
      <small>{requirement.provenance?.model_id ?? 'no model'}</small>
      <small>{formatEvidenceVerification(requirement.provenance?.evidence_verified)}</small>
      <small>{requirement.source_evidence.length} evidence</small>
    </span>
  );
}

function RequirementDetail({
  analysis,
  mergeRequirements,
  requirement,
  requirements,
  splitRequirement,
  updateIntent,
  updateRequirement,
}: {
  analysis: AnalysisResponse;
  mergeRequirements: (ids: string[], suggestedStatement?: string) => void;
  requirement: CandidateRequirement | null;
  requirements: CandidateRequirement[];
  splitRequirement: () => void;
  updateIntent: (id: string, patch: Partial<NormalizedIntent>) => void;
  updateRequirement: (id: string, patch: Partial<CandidateRequirement>) => void;
}) {
  if (!requirement) return <section className="requirement-detail-panel"><EmptyState text="Select a requirement to review." /></section>;

  return (
    <section className="requirement-detail-panel">
      <div className="detail-header">
        <div>
          <small>Selected requirement</small>
          <h3>{shortStatement(requirement)}</h3>
          <small>{requirement.id}</small>
        </div>
        <span className={`status-pill status-pill--${requirement.status}`}>{humanize(requirement.status)}</span>
      </div>

      <section className="requirement-machine-metadata" aria-label="Requirement machine metadata">
        <span><strong>Validation</strong>{humanize(requirement.validation_status)}</span>
        <span><strong>Scope</strong>{humanize(requirement.requirement_scope)}</span>
        <span><strong>Strategy</strong>{requirement.provenance?.strategy ?? 'unknown'}</span>
        <span><strong>Model</strong>{requirement.provenance?.model_id ?? 'none'}</span>
        <span><strong>Evidence</strong>{formatEvidenceVerification(requirement.provenance?.evidence_verified)}</span>
        <span><strong>Sources</strong>{requirement.source_evidence.length}</span>
        <span><strong>Support</strong>{humanize(requirement.support_level ?? 'explicit')}</span>
        <span><strong>Agent support</strong>{requirement.contributing_agent_roles?.length ?? 0} of 12 extraction roles</span>
        <span><strong>Frozen</strong>{requirement.machine_output_frozen ? 'yes' : 'no'}</span>
      </section>

      {requirement.contributing_agent_roles?.length ? (
        <div className="agent-role-chips">{requirement.contributing_agent_roles.map((role) => <span key={role}>{role}</span>)}</div>
      ) : null}
      {requirement.machine_original_statement ? (
        <div className="machine-original-statement"><strong>Original machine statement</strong><p>{requirement.machine_original_statement}</p></div>
      ) : null}

      <div className="review-actions review-actions--primary">
        <button onClick={() => updateRequirement(requirement.id, { status: 'approved' })} type="button">
          <CheckCircle2 size={16} />
          Approve
        </button>
        <button onClick={() => updateRequirement(requirement.id, { status: 'needs_review' })} type="button">
          <AlertTriangle size={16} />
          Needs review
        </button>
        <button onClick={() => updateRequirement(requirement.id, { status: 'rejected' })} type="button">
          <XCircle size={16} />
          Reject
        </button>
      </div>

      <label>
        Normalized statement
        <textarea
          className="statement-editor"
          onChange={(event) => updateRequirement(requirement.id, { normalized_statement: event.target.value, description: event.target.value })}
          value={requirement.normalized_statement || ''}
        />
      </label>

      <div className="detail-form-grid">
        <label>
          Requirement type
          <select onChange={(event) => updateRequirement(requirement.id, { requirement_type: event.target.value as RequirementType })} value={requirement.requirement_type}>
            {REQUIREMENT_TYPES.map((type) => <option key={type} value={type}>{humanize(type)}</option>)}
          </select>
        </label>
        <label>
          Requirement scope
          <select onChange={(event) => updateRequirement(requirement.id, { requirement_scope: event.target.value as RequirementScope })} value={requirement.requirement_scope}>
            {REQUIREMENT_SCOPE_OPTIONS.map((scope) => <option key={scope} value={scope}>{humanize(scope)}</option>)}
          </select>
        </label>
        <label>
          Resource type
          <select onChange={(event) => updateIntent(requirement.id, { resource_type: event.target.value as NormalizedIntent['resource_type'] })} value={requirement.normalized_intent.resource_type}>
            {RESOURCE_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
          </select>
        </label>
        <label>
          Value kind
          <select onChange={(event) => updateIntent(requirement.id, { value_kind: event.target.value as NormalizedIntent['value_kind'] })} value={requirement.normalized_intent.value_kind}>
            {VALUE_KINDS.map((kind) => <option key={kind} value={kind}>{humanize(kind)}</option>)}
          </select>
        </label>
        <label>
          Obligation
          <select onChange={(event) => updateIntent(requirement.id, { obligation_hint: event.target.value as NormalizedIntent['obligation_hint'] })} value={requirement.normalized_intent.obligation_hint}>
            {OBLIGATION_HINTS.map((hint) => <option key={hint} value={hint}>{humanize(hint)}</option>)}
          </select>
        </label>
      </div>

      <label>
        Metadata need
        <input onChange={(event) => updateIntent(requirement.id, { metadata_need: event.target.value })} value={requirement.normalized_intent.metadata_need} />
      </label>

      <label>
        Review notes
        <textarea
          onChange={(event) => updateRequirement(requirement.id, { review_notes: event.target.value })}
          value={requirement.review_notes || ''}
        />
      </label>

      <div className="supporting-sections">
        <AgentContributionView requirement={requirement} />
        <CritiqueFindingsView findings={(analysis.critique_findings ?? []).filter((finding) => finding.requirement_id === requirement.id)} />
        <details open>
          <summary>Evidence for this requirement ({requirement.source_evidence.length})</summary>
          <EvidencePanel requirement={requirement} />
        </details>
        <details>
          <summary>FAIR and metadata actions</summary>
          <FairAndActions requirement={requirement} updateRequirement={updateRequirement} />
        </details>
        <details>
          <summary>Raw extracted statement</summary>
          <label>
            Raw statement
            <textarea
              onChange={(event) => updateRequirement(requirement.id, { raw_statement: event.target.value })}
              value={requirement.raw_statement || ''}
            />
          </label>
        </details>
        <details>
          <summary>Duplicate suggestions ({analysis.duplicate_groups.length})</summary>
          <DuplicatePanel groups={analysis.duplicate_groups} mergeRequirements={mergeRequirements} requirements={requirements} />
        </details>
        <details>
          <summary>Extracted attributes ({analysis.extracted_attributes.length})</summary>
          <ExtractedAttributes attributes={analysis.extracted_attributes} />
        </details>
      </div>

      <div className="review-actions">
        <button onClick={splitRequirement} type="button">
          <SplitSquareHorizontal size={16} />
          Split requirement
        </button>
      </div>
    </section>
  );
}

function FairAndActions({
  requirement,
  updateRequirement,
}: {
  requirement: CandidateRequirement;
  updateRequirement: (id: string, patch: Partial<CandidateRequirement>) => void;
}) {
  function updateAction(index: number, patch: Partial<CandidateMetadataAction>) {
    const next = requirement.candidate_metadata_actions.map((action, actionIndex) =>
      actionIndex === index ? { ...action, ...patch } : action,
    );
    updateRequirement(requirement.id, { candidate_metadata_actions: next });
  }

  function updateConstraint(index: number, patch: Partial<NonNullable<CandidateMetadataAction['constraint_hint']>>) {
    const current = requirement.candidate_metadata_actions[index];
    updateAction(index, {
      constraint_hint: {
        value_kind: current.constraint_hint?.value_kind ?? requirement.normalized_intent.value_kind,
        obligation: current.constraint_hint?.obligation ?? requirement.normalized_intent.obligation_hint,
        ...current.constraint_hint,
        ...patch,
      },
    });
  }

  return (
    <div className="fair-action-panel">
      <div>
        <h4>FAIR dimensions</h4>
        <div className="fair-toggle-group" aria-label="FAIR dimensions">
          {FAIR_DIMENSIONS.map((dimension) => (
            <label key={dimension}>
              <input
                checked={requirement.fair_dimensions.includes(dimension)}
                onChange={(event) => {
                  const current = requirement.fair_dimensions;
                  updateRequirement(requirement.id, {
                    fair_dimensions: event.target.checked ? uniqueStrings([...current, dimension]) as FairDimension[] : current.filter((item) => item !== dimension),
                  });
                }}
                type="checkbox"
              />
              {dimension}
            </label>
          ))}
        </div>
      </div>

      <label>
        FAIR rationale
        <textarea
          onChange={(event) => updateRequirement(requirement.id, { fair_rationale: event.target.value })}
          value={requirement.fair_rationale || ''}
        />
      </label>

      <section className="metadata-action-list">
        <h4>Suggested metadata anchors</h4>
        {requirement.candidate_metadata_actions.map((action, index) => (
          <article key={`${action.action}-${index}`}>
            <details>
              <summary>
                <strong>{humanize(action.action)}</strong>
                <code>{action.candidate_terms.join(', ') || 'no term'}</code>
              </summary>
              <div className="metadata-action-editor">
                <label>
                  Action
                  <select onChange={(event) => updateAction(index, { action: event.target.value as CandidateMetadataAction['action'] })} value={action.action}>
                    {METADATA_ACTIONS.map((item) => <option key={item} value={item}>{humanize(item)}</option>)}
                  </select>
                </label>
                <label>
                  Target class
                  <select onChange={(event) => updateAction(index, { target_class: event.target.value })} value={action.target_class || requirement.normalized_intent.resource_type}>
                    {RESOURCE_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
                  </select>
                </label>
                <label>
                  Candidate terms
                  <input
                    onChange={(event) => updateAction(index, { candidate_terms: splitTerms(event.target.value) })}
                    value={action.candidate_terms.join(', ')}
                  />
                </label>
                <label>
                  Cardinality
                  <input
                    onChange={(event) => updateConstraint(index, { cardinality: event.target.value || null })}
                    placeholder="0..n"
                    value={action.constraint_hint?.cardinality || ''}
                  />
                </label>
                <label>
                  Constraint value kind
                  <select
                    onChange={(event) => updateConstraint(index, { value_kind: event.target.value as NormalizedIntent['value_kind'] })}
                    value={action.constraint_hint?.value_kind ?? requirement.normalized_intent.value_kind}
                  >
                    {VALUE_KINDS.map((kind) => <option key={kind} value={kind}>{humanize(kind)}</option>)}
                  </select>
                </label>
                <label>
                  Constraint obligation
                  <select
                    onChange={(event) => updateConstraint(index, { obligation: event.target.value as NormalizedIntent['obligation_hint'] })}
                    value={action.constraint_hint?.obligation ?? requirement.normalized_intent.obligation_hint}
                  >
                    {OBLIGATION_HINTS.map((hint) => <option key={hint} value={hint}>{humanize(hint)}</option>)}
                  </select>
                </label>
                <label className="metadata-action-editor__wide">
                  Rationale
                  <textarea onChange={(event) => updateAction(index, { rationale: event.target.value })} value={action.rationale} />
                </label>
              </div>
            </details>
          </article>
        ))}
      </section>
    </div>
  );
}

function EvidencePanel({ requirement }: { requirement: CandidateRequirement | null }) {
  if (!requirement) return null;

  return (
    <section className="evidence-section">
      <h3>Source Evidence</h3>
      {requirement.source_evidence.length ? (
        <div className="evidence-list">
          {requirement.source_evidence.map((evidence) => (
            <article className="evidence-item" key={evidence.evidence_unit_id}>
              <small>{evidence.artifact_name} - {evidence.artifact_kind}</small>
              {evidence.locator ? <code>{evidence.locator}</code> : null}
              <p>{evidence.evidence_text}</p>
              {evidence.extracted_facts.length ? <ul>{evidence.extracted_facts.map((fact) => <li key={fact}>{fact}</li>)}</ul> : null}
            </article>
          ))}
        </div>
      ) : (
        <EmptyState text="No source evidence is attached to this requirement." />
      )}
    </section>
  );
}

function DuplicatePanel({
  groups,
  mergeRequirements,
  requirements,
}: {
  groups: AnalysisResponse['duplicate_groups'];
  mergeRequirements: (ids: string[], suggestedStatement?: string) => void;
  requirements: CandidateRequirement[];
}) {
  if (!groups.length) return null;
  const byId = Object.fromEntries(requirements.map((requirement) => [requirement.id, requirement]));

  return (
    <section className="duplicate-section">
      <h3>Duplicate Suggestions</h3>
      {groups.map((group) => (
        <article className="duplicate-group" key={group.id}>
          <strong>{group.id}</strong>
          <p>{group.reason}</p>
          <code>{group.suggested_merged_statement}</code>
          <ul>
            {group.requirement_ids.map((id) => (
              <li key={id}>{byId[id]?.title || byId[id]?.normalized_statement || id}</li>
            ))}
          </ul>
          <div className="review-actions">
            <button onClick={() => mergeRequirements(group.requirement_ids, group.suggested_merged_statement)} type="button">
              <GitMerge size={16} />
              Merge
            </button>
          </div>
        </article>
      ))}
    </section>
  );
}

async function fileToArtifact(file: File): Promise<ArtifactPayload> {
  if (/\.aasx$/i.test(file.name)) {
    return {
      name: file.name,
      media_type: file.type || 'application/asset-administration-shell-package',
      content: arrayBufferToBase64(await file.arrayBuffer()),
      content_encoding: 'base64',
    };
  }

  return {
    name: file.name,
    media_type: file.type || undefined,
    content: await file.text(),
    content_encoding: 'text',
  };
}

function arrayBufferToBase64(buffer: ArrayBuffer) {
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  let binary = '';
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return window.btoa(binary);
}

function ExtractedAttributes({ attributes }: { attributes: ExtractedAttribute[] }) {
  if (!attributes.length) return null;

  return (
    <section className="result-section">
      <h3>Extracted Attributes</h3>
      <div className="attribute-table" role="table" aria-label="Extracted artifact attributes">
        <div className="attribute-table__header" role="row">
          <span>Attribute</span>
          <span>Value</span>
          <span>Path</span>
          <span>Source</span>
        </div>
        {attributes.map((attribute) => (
          <article className="attribute-row" key={attribute.id} role="row">
            <span>
              <strong>{attribute.label}</strong>
              <small>{attribute.category}</small>
            </span>
            <code>{attribute.value || 'empty'}</code>
            <code>{attribute.path}</code>
            <small>{attribute.source}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function SummaryStrip({ analysis, requirements }: { analysis: AnalysisResponse; requirements: CandidateRequirement[] }) {
  const approved = requirements.filter((requirement) => requirement.status === 'approved').length;
  return (
    <div className="summary-strip">
      <span>{analysis.artifacts.length} artifacts</span>
      <span>{analysis.evidence_units.length} evidence units</span>
      <span>{requirements.length} requirements</span>
      <span>{approved} approved</span>
      <span>{analysis.duplicate_groups.length} duplicate groups</span>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <p className="empty-state">{text}</p>;
}

function withRequirements(analysis: AnalysisResponse, requirements: CandidateRequirement[]): AnalysisResponse {
  return { ...analysis, requirements };
}

function applyRequirementPatch(requirement: CandidateRequirement, patch: Partial<CandidateRequirement>): CandidateRequirement {
  const updated = { ...requirement, ...patch };
  const fields: Array<keyof CandidateRequirement> = [
    'normalized_statement',
    'requirement_type',
    'requirement_scope',
    'candidate_metadata_actions',
    'fair_dimensions',
    'review_notes',
    'status',
  ];
  const history = fields
    .filter((field) => field in patch && !sameHistoryValue(requirement[field], patch[field]))
    .map((field) =>
      editorHistoryEntry(
        String(field),
        requirement[field],
        patch[field],
        field === 'status'
          ? actionForStatusChange(patch.status)
          : field === 'candidate_metadata_actions'
            ? 'edit_candidate_metadata_action'
            : 'edit',
      ),
    );
  return history.length ? { ...updated, provenance: appendEditorHistory(requirement.provenance, history) } : updated;
}

function applyIntentPatch(requirement: CandidateRequirement, patch: Partial<NormalizedIntent>): CandidateRequirement {
  const updatedIntent = { ...requirement.normalized_intent, ...patch };
  const fields: Array<keyof NormalizedIntent> = ['metadata_need', 'resource_type', 'value_kind', 'obligation_hint'];
  const history = fields
    .filter((field) => field in patch && !sameHistoryValue(requirement.normalized_intent[field], patch[field]))
    .map((field) => editorHistoryEntry(String(field), requirement.normalized_intent[field], patch[field], 'edit'));
  const updated = { ...requirement, normalized_intent: updatedIntent };
  return history.length ? { ...updated, provenance: appendEditorHistory(requirement.provenance, history) } : updated;
}

function appendEditorHistory(provenance: ExtractionProvenance | null | undefined, entries: Array<Record<string, unknown>>): ExtractionProvenance {
  const base: ExtractionProvenance = provenance ?? {
    strategy: 'rules',
    extractor: 'frontend-review',
    notes: [],
    editor_history: [],
  };
  return {
    ...base,
    notes: base.notes ?? [],
    editor_history: [...(base.editor_history ?? []), ...entries],
  };
}

function editorHistoryEntry(field: string, oldValue: unknown, newValue: unknown, action: EditorHistoryAction) {
  return {
    timestamp: new Date().toISOString(),
    reviewer_id: WORKBENCH_REVIEWER_ID,
    session_id: WORKBENCH_SESSION_ID,
    field,
    old_value: oldValue ?? null,
    new_value: newValue ?? null,
    action,
  };
}

function actionForStatusChange(status: RequirementStatus | undefined): EditorHistoryAction {
  if (status === 'approved') return 'approve';
  if (status === 'rejected') return 'reject';
  if (status === 'needs_review') return 'mark_needs_review';
  return 'edit';
}

function sameHistoryValue(left: unknown, right: unknown) {
  return JSON.stringify(left ?? null) === JSON.stringify(right ?? null);
}

function buildRq1DatasetExport(
  analysis: AnalysisResponse,
  requirements: CandidateRequirement[],
  localMergeEvents: Rq1LocalMergeEvent[],
  localSplitEvents: Rq1LocalSplitEvent[],
): Rq1DatasetExport {
  return {
    schema_version: analysis.strategy === 'multi_agent' ? 'rq1-multi-agent-dataset-v1' : 'rq1-requirement-dataset-v1',
    export_kind: 'reviewed_frontend_state',
    generated_at: new Date().toISOString(),
    source_corpus_id: analysis.study_setup?.source_corpus_id as string | null | undefined,
    reviewer_id: WORKBENCH_REVIEWER_ID,
    session_id: WORKBENCH_SESSION_ID,
    started_at: WORKBENCH_STARTED_AT,
    completed_at: new Date().toISOString(),
    duration_ms: Date.now() - Date.parse(WORKBENCH_STARTED_AT),
    study_setup: analysis.study_setup,
    rq1_codebook: RQ1_CODEBOOK_SUMMARY,
    strategy_requested: analysis.strategy,
    strategy_used: analysis.strategy,
    summary_metrics: {
      requirement_count: requirements.length,
      funnel_metrics: analysis.funnel_metrics,
      evidence_unit_count: analysis.evidence_units.length,
      duplicate_group_count: analysis.duplicate_groups.length,
      user_task_count: analysis.user_tasks.length,
      warning_count: analysis.warnings.length,
      requirements_by_type: countBy(requirements, (requirement) => requirement.requirement_type),
      requirements_by_scope: countBy(requirements, (requirement) => requirement.requirement_scope),
      requirements_by_validation_status: countBy(requirements, (requirement) => requirement.validation_status),
      requirements_by_review_status: countBy(requirements, (requirement) => requirement.status),
      requirements_with_editor_history: requirements.filter((requirement) => requirement.provenance?.editor_history?.length).length,
      requirements_approved_with_valid_validation: requirements.filter(
        (requirement) => requirement.status === 'approved' && requirement.validation_status === 'valid',
      ).length,
      requirements_approved_with_warnings: requirements.filter(
        (requirement) => requirement.status === 'approved' && requirement.validation_status !== 'valid',
      ).length,
      local_merge_event_count: localMergeEvents.length,
      local_split_event_count: localSplitEvents.length,
      competency_question_coverage: buildCqCoverage(requirements, analysis.user_tasks),
    },
    requirements,
    evidence_units: analysis.evidence_units,
    duplicate_groups: analysis.duplicate_groups,
    duplicate_groups_original: analysis.duplicate_groups,
    local_merge_events: localMergeEvents,
    local_split_events: localSplitEvents,
    user_tasks: analysis.user_tasks,
    funnel_metrics: analysis.funnel_metrics,
    warnings: analysis.warnings,
    review_editor_history: requirements.map((requirement) => ({
      requirement_id: requirement.id,
      review_status: requirement.status,
      validation_status: requirement.validation_status,
      review_notes: requirement.review_notes ?? null,
      editor_history: requirement.provenance?.editor_history ?? [],
    })),
    workflow_id: analysis.workflow_id,
    workflow_version: analysis.workflow_version,
    study_mode: analysis.study_mode,
    study_phase: analysis.study_phase,
    input_hash: analysis.input_hash,
    panel_preset: analysis.panel_preset,
    panel_status: analysis.panel_status,
    agent_runs: analysis.agent_runs,
    agent_contexts: analysis.agent_contexts,
    workflow_trace: analysis.workflow_trace,
    raw_agent_requirements: analysis.raw_agent_requirements,
    machine_requirements: requirements,
    consolidation_events: analysis.consolidation_events,
    critique_findings: analysis.critique_findings,
    original_machine_output: analysis.requirements,
  };
}

function buildCqCoverage(requirements: CandidateRequirement[], userTasks: UserTask[]) {
  const active = requirements.filter((requirement) => requirement.status !== 'rejected' && requirement.status !== 'merged');
  const covered = new Set(active.flatMap((requirement) => requirement.supports_user_tasks));
  return {
    task_count: userTasks.length,
    covered_task_count: userTasks.filter((task) => covered.has(task.id)).length,
    uncovered_task_ids: userTasks.filter((task) => !covered.has(task.id)).map((task) => task.id),
    requirements_without_task_links: active.filter((requirement) => !requirement.supports_user_tasks.length).map((requirement) => requirement.id),
  };
}

function countBy<T>(items: T[], getKey: (item: T) => string) {
  return items.reduce<Record<string, number>>((counts, item) => {
    const key = getKey(item);
    counts[key] = (counts[key] ?? 0) + 1;
    return counts;
  }, {});
}

function formatEvidenceVerification(value: boolean | null | undefined) {
  if (value === true) return 'evidence verified';
  if (value === false) return 'evidence unverified';
  return 'evidence unknown';
}

function requirementStatement(requirement: CandidateRequirement) {
  return requirement.normalized_statement || requirement.description || requirement.raw_statement || requirement.title || requirement.id;
}

function shortStatement(requirement: CandidateRequirement) {
  const statement = requirementStatement(requirement);
  return statement.length > 72 ? `${statement.slice(0, 69)}...` : statement;
}

function uniqueEvidence(items: SourceEvidence[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = `${item.evidence_unit_id}:${item.locator || ''}:${item.evidence_text}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function uniqueStrings<T extends string>(items: T[]) {
  return Array.from(new Set(items.filter(Boolean)));
}

function splitTerms(value: string) {
  return value.split(/[\s,]+/).map((term) => term.trim()).filter(Boolean);
}

function humanize(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (match) => match.toUpperCase());
}

function formatConfidence(confidence: number) {
  return `${Math.round(confidence * 100)}%`;
}
