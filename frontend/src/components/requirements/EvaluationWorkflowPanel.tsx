import { useEffect, useMemo, useState, type ChangeEvent, type Dispatch, type SetStateAction } from 'react';
import { CheckCircle2, Download, FileSearch, ShieldCheck } from 'lucide-react';
import {
  aggregateExpertReviews,
  finalizeConsensus,
  freezeEvaluationPackage,
  reviseAfterEvaluation,
  validateReviewSubmission,
  type AnalysisResponse,
  type ConsensusDecision,
  type EvaluationPackage,
  type ExpertCriterionRatings,
  type ExpertRequirementReview,
  type ExpertReviewSubmission,
  type ReviewAggregation,
  type ReviewDecision,
  type RevisionResponse,
  type ValidatedRequirementBaseline,
} from '../../lib/requirementApi';
import { downloadText } from '../../lib/download';

const RATING_FIELDS: Array<keyof ExpertCriterionRatings> = [
  'evidence_fidelity', 'correctness', 'relevance', 'necessity',
  'clarity', 'atomicity', 'reuse_potential', 'extension_necessity',
];

type DraftReview = {
  decision?: ReviewDecision;
  ratings: ExpertCriterionRatings;
  comment: string;
  proposedStatement: string;
  feedbackCategories: string;
  mergeWith: string;
  splitStatements: string;
};

type Props = {
  analysis: AnalysisResponse | null;
  onStatus: (message: string) => void;
  onValidatedBaseline: (baseline: ValidatedRequirementBaseline) => void;
};

export function EvaluationWorkflowPanel({ analysis, onStatus, onValidatedBaseline }: Props) {
  const [mode, setMode] = useState<'coordinator' | 'reviewer'>('coordinator');
  const [evaluationPackage, setEvaluationPackage] = useState<EvaluationPackage | null>(null);
  const [reviewerId, setReviewerId] = useState('E1');
  const [reviewStartedAt, setReviewStartedAt] = useState(new Date().toISOString());
  const [drafts, setDrafts] = useState<Record<string, DraftReview>>({});
  const [missingStatement, setMissingStatement] = useState('');
  const [missingRationale, setMissingRationale] = useState('');
  const [submissions, setSubmissions] = useState<ExpertReviewSubmission[]>([]);
  const [aggregation, setAggregation] = useState<ReviewAggregation | null>(null);
  const [revision, setRevision] = useState<RevisionResponse | null>(null);
  const [consensusDraft, setConsensusDraft] = useState<Record<string, ConsensusDecision['decision'] | ''>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!evaluationPackage || !reviewerId) return;
    const key = `rq1-review-progress:${evaluationPackage.id}:${reviewerId}`;
    const saved = window.localStorage.getItem(key);
    if (saved) {
      try { setDrafts(JSON.parse(saved) as Record<string, DraftReview>); } catch { setDrafts({}); }
    } else {
      setDrafts({});
      setReviewStartedAt(new Date().toISOString());
    }
  }, [evaluationPackage, reviewerId]);

  useEffect(() => {
    if (!evaluationPackage || !reviewerId) return;
    window.localStorage.setItem(`rq1-review-progress:${evaluationPackage.id}:${reviewerId}`, JSON.stringify(drafts));
  }, [drafts, evaluationPackage, reviewerId]);

  const machineRequirements = evaluationPackage?.machine_requirements ?? [];
  const completedDrafts = machineRequirements.filter((requirement) => drafts[requirement.id]?.decision).length;
  const revisionsByRequirement = useMemo(
    () => new Map((revision?.revisions ?? []).map((item) => [item.requirement_id, item])),
    [revision],
  );
  const consensusRequirements = useMemo(
    () => [...machineRequirements, ...(revision?.expert_added_requirements ?? [])],
    [machineRequirements, revision],
  );

  const freeze = async () => {
    if (!analysis) return;
    setBusy(true);
    try {
      const result = await freezeEvaluationPackage(analysis, 3);
      setEvaluationPackage(result);
      setSubmissions([]);
      setAggregation(null);
      setRevision(null);
      onStatus(`Frozen evaluation package ${result.id} with ${result.machine_requirements.length} unmodified machine requirement(s).`);
    } catch (error) {
      onStatus(`Evaluation package freeze failed: ${error instanceof Error ? error.message : 'unknown error'}`);
    } finally { setBusy(false); }
  };

  const importPackage = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text()) as EvaluationPackage;
      if (parsed.schema_version !== 'rq1-evaluation-package-v1') throw new Error('Unsupported evaluation package schema.');
      setEvaluationPackage(parsed);
      setSubmissions([]);
      setAggregation(null);
      setRevision(null);
      onStatus(`Opened frozen evaluation package ${parsed.id}.`);
    } catch (error) {
      onStatus(`Could not open evaluation package: ${error instanceof Error ? error.message : 'invalid JSON'}`);
    } finally { event.target.value = ''; }
  };

  const exportSubmission = async () => {
    if (!evaluationPackage) return;
    if (!reviewerId.trim() || completedDrafts !== machineRequirements.length) {
      onStatus('Enter a pseudonymous reviewer ID and decide every frozen machine requirement before export.');
      return;
    }
    const reviews: ExpertRequirementReview[] = machineRequirements.map((requirement) => {
      const draft = drafts[requirement.id];
      return {
        requirement_id: requirement.id,
        decision: draft.decision as ReviewDecision,
        ratings: completeRatings(draft.ratings),
        comment: draft.comment || null,
        proposed_statement: draft.proposedStatement || null,
        feedback_categories: splitValues(draft.feedbackCategories),
        proposed_merge_with: splitValues(draft.mergeWith),
        proposed_split_statements: (draft.splitStatements ?? '').split('\n').map((item) => item.trim()).filter(Boolean),
      };
    });
    const submission: ExpertReviewSubmission = {
      schema_version: 'rq1-expert-review-v1',
      id: `review-${evaluationPackage.id}-${reviewerId.trim()}`,
      evaluation_package_id: evaluationPackage.id,
      evaluation_package_hash: evaluationPackage.package_hash,
      reviewer_id: reviewerId.trim(),
      started_at: reviewStartedAt,
      completed_at: new Date().toISOString(),
      reviews,
      missing_requirements: missingStatement.trim() ? [{
        id: `missing-${evaluationPackage.id}-${reviewerId.trim()}-1`,
        statement: missingStatement.trim(),
        rationale: missingRationale.trim() || 'Proposed independently by the reviewer as missing from the frozen machine set.',
        evidence_unit_ids: [],
        requirement_type: null,
      }] : [],
      submission_hash: '',
    };
    submission.submission_hash = await sha256Canonical(submission, 'submission_hash');
    setBusy(true);
    try {
      await validateReviewSubmission(evaluationPackage, submission);
      downloadText(JSON.stringify(submission, null, 2), `${submission.id}.json`, 'application/json');
      onStatus(`Validated and exported independent submission for ${submission.reviewer_id}.`);
    } catch (error) {
      onStatus(`Review submission validation failed: ${error instanceof Error ? error.message : 'unknown error'}`);
    } finally { setBusy(false); }
  };

  const importSubmissions = async (event: ChangeEvent<HTMLInputElement>) => {
    if (!evaluationPackage) return;
    const files = [...(event.target.files ?? [])];
    const accepted: ExpertReviewSubmission[] = [];
    try {
      for (const file of files) {
        const parsed = JSON.parse(await file.text()) as ExpertReviewSubmission;
        await validateReviewSubmission(evaluationPackage, parsed);
        accepted.push(parsed);
      }
      setSubmissions((current) => {
        const byReviewer = new Map(current.map((item) => [item.reviewer_id, item]));
        accepted.forEach((item) => byReviewer.set(item.reviewer_id, item));
        return [...byReviewer.values()].sort((left, right) => left.reviewer_id.localeCompare(right.reviewer_id));
      });
      onStatus(`Imported ${accepted.length} valid independent review submission(s).`);
    } catch (error) {
      onStatus(`Review import failed: ${error instanceof Error ? error.message : 'invalid JSON'}`);
    } finally { event.target.value = ''; }
  };

  const aggregate = async () => {
    if (!evaluationPackage) return;
    setBusy(true);
    try {
      const result = await aggregateExpertReviews(evaluationPackage, submissions);
      setAggregation(result);
      onStatus(`Aggregated ${result.reviewer_ids.length}/${result.expected_reviewer_count} independent expert submissions.`);
    } catch (error) {
      onStatus(`Review aggregation failed: ${error instanceof Error ? error.message : 'unknown error'}`);
    } finally { setBusy(false); }
  };

  const closeAndRevise = async () => {
    if (!evaluationPackage || !aggregation) return;
    setBusy(true);
    try {
      const result = await reviseAfterEvaluation(evaluationPackage, aggregation, submissions);
      setRevision(result);
      onStatus(`Summative evaluation closed; ${result.revisions.length} controlled revision proposal(s) recorded separately.`);
    } catch (error) {
      onStatus(`Post-evaluation revision failed: ${error instanceof Error ? error.message : 'unknown error'}`);
    } finally { setBusy(false); }
  };

  const finalize = async () => {
    if (!evaluationPackage || !aggregation) return;
    const missing = consensusRequirements.filter((item) => !consensusDraft[item.id]);
    if (missing.length) {
      onStatus(`Record a human consensus decision for all ${evaluationPackage.machine_requirements.length} machine requirements.`);
      return;
    }
    const decisions: ConsensusDecision[] = consensusRequirements.map((requirement) => {
      const decision = consensusDraft[requirement.id] as ConsensusDecision['decision'];
      const matchingRevision = revisionsByRequirement.get(requirement.id);
      return {
        requirement_id: requirement.id,
        decision,
        final_statement: decision === 'accepted_with_revision' ? matchingRevision?.proposed_statement ?? null : null,
        rationale: 'Recorded by the coordinator after human expert consensus validation.',
        participant_reviewer_ids: aggregation.reviewer_ids,
        revision_record_id: decision === 'accepted_with_revision' ? matchingRevision?.id ?? null : null,
        decided_at: new Date().toISOString(),
      };
    });
    setBusy(true);
    try {
      const result = await finalizeConsensus(evaluationPackage, aggregation, decisions, revision);
      onValidatedBaseline(result);
      downloadText(JSON.stringify(result, null, 2), `${evaluationPackage.id}-validated-baseline.json`, 'application/json');
      onStatus(`Consensus validated ${result.requirements.length} requirement(s); only these are formally RQ2-eligible.`);
    } catch (error) {
      onStatus(`Consensus finalization failed: ${error instanceof Error ? error.message : 'unknown error'}`);
    } finally { setBusy(false); }
  };

  return (
    <section className="evaluation-workflow" aria-label="Three-expert evaluation workflow">
      <header>
        <div><h3>Three-expert evaluation</h3><p>Machine output stays immutable; reviews, revisions, and consensus are separate layers.</p></div>
        <div className="workflow-tabs">
          <button className={mode === 'coordinator' ? 'active' : undefined} onClick={() => setMode('coordinator')} type="button">Coordinator</button>
          <button className={mode === 'reviewer' ? 'active' : undefined} onClick={() => setMode('reviewer')} type="button">Independent reviewer</button>
        </div>
      </header>

      <div className="evaluation-toolbar">
        {mode === 'coordinator' ? <button disabled={!analysis || busy} onClick={() => void freeze()} type="button"><ShieldCheck size={16} />Freeze machine output</button> : null}
        <label className="file-picker"><FileSearch size={16} />Open package<input accept=".json" onChange={(event) => void importPackage(event)} type="file" /></label>
        {evaluationPackage ? <button onClick={() => downloadText(JSON.stringify(evaluationPackage, null, 2), `${evaluationPackage.id}.json`, 'application/json')} type="button"><Download size={16} />Package</button> : null}
      </div>

      {evaluationPackage ? (
        <div className="evaluation-package-summary">
          <span><strong>{evaluationPackage.machine_requirements.length}</strong> frozen requirements</span>
          <span><strong>{evaluationPackage.target_reviewer_count}</strong> target reviewers</span>
          <span><strong>{evaluationPackage.strategy_used}</strong> strategy</span>
          <span><strong>{evaluationPackage.workflow_version}</strong> workflow</span>
          <small>Package hash: {evaluationPackage.package_hash}</small>
        </div>
      ) : <p className="empty-state">Freeze the current run or open a versioned evaluation package.</p>}

      {mode === 'reviewer' && evaluationPackage ? (
        <section className="independent-review-panel">
          <label>Pseudonymous reviewer ID<input onChange={(event) => setReviewerId(event.target.value)} value={reviewerId} /></label>
          <p>{completedDrafts}/{machineRequirements.length} decisions. Other reviewers’ decisions, majority status, revisions, and consensus are not available in reviewer mode.</p>
          {machineRequirements.map((requirement, index) => {
            const draft = drafts[requirement.id] ?? { ratings: {}, comment: '', proposedStatement: '', feedbackCategories: '', mergeWith: '', splitStatements: '' };
            return (
              <article className="expert-review-card" key={requirement.id}>
                <header><strong>{index + 1}. {requirement.normalized_statement}</strong><small>{requirement.id}</small></header>
                <blockquote>{requirement.source_evidence.map((item) => item.evidence_text).join(' · ') || 'No verified evidence displayed.'}</blockquote>
                <label>Decision<select onChange={(event) => patchDraft(setDrafts, requirement.id, { decision: event.target.value as ReviewDecision })} value={draft.decision ?? ''}>
                  <option disabled value="">Select independently…</option>
                  <option value="accept">Accept</option><option value="accept_with_revision">Accept with revision</option>
                  <option value="reject">Reject</option><option value="out_of_scope">Out of scope</option><option value="cannot_assess">Cannot assess</option>
                </select></label>
                <div className="expert-rating-grid">{RATING_FIELDS.map((field) => <label key={field}>{humanize(field)}<input max={5} min={1} onChange={(event) => patchDraft(setDrafts, requirement.id, { ratings: { ...draft.ratings, [field]: event.target.value ? Number(event.target.value) : null } })} type="number" value={draft.ratings[field] ?? ''} /></label>)}</div>
                <label>Comment<textarea onChange={(event) => patchDraft(setDrafts, requirement.id, { comment: event.target.value })} value={draft.comment} /></label>
                <label>Proposed statement<textarea onChange={(event) => patchDraft(setDrafts, requirement.id, { proposedStatement: event.target.value })} value={draft.proposedStatement} /></label>
                <label>Feedback categories (comma separated)<input onChange={(event) => patchDraft(setDrafts, requirement.id, { feedbackCategories: event.target.value })} value={draft.feedbackCategories ?? ''} /></label>
                <label>Proposed merge requirement IDs<input onChange={(event) => patchDraft(setDrafts, requirement.id, { mergeWith: event.target.value })} value={draft.mergeWith ?? ''} /></label>
                <label>Proposed split statements (one per line)<textarea onChange={(event) => patchDraft(setDrafts, requirement.id, { splitStatements: event.target.value })} value={draft.splitStatements ?? ''} /></label>
              </article>
            );
          })}
          <section className="expert-review-card">
            <h4>Missing requirement proposal (optional)</h4>
            <label>Statement<textarea onChange={(event) => setMissingStatement(event.target.value)} value={missingStatement} /></label>
            <label>Rationale<textarea onChange={(event) => setMissingRationale(event.target.value)} value={missingRationale} /></label>
            <small>Missing requirements are labeled expert-added and require final human consensus; they are never counted as original machine extraction.</small>
          </section>
          <button disabled={busy || completedDrafts !== machineRequirements.length} onClick={() => void exportSubmission()} type="button"><Download size={16} />Validate and export submission</button>
        </section>
      ) : null}

      {mode === 'coordinator' && evaluationPackage ? (
        <section className="coordinator-review-panel">
          <div className="evaluation-toolbar">
            <label className="file-picker"><FileSearch size={16} />Import review submissions<input accept=".json" multiple onChange={(event) => void importSubmissions(event)} type="file" /></label>
            <button disabled={!submissions.length || busy} onClick={() => void aggregate()} type="button">Aggregate ({submissions.length}/{evaluationPackage.target_reviewer_count})</button>
            <button disabled={!aggregation?.complete || busy} onClick={() => void closeAndRevise()} type="button">Close review and propose revisions</button>
          </div>
          <p>Imported reviewer IDs: {submissions.map((item) => item.reviewer_id).join(', ') || 'none'}</p>
          {aggregation ? (
            <section className="aggregation-results">
              <h4>Original machine performance</h4>
              <p>These metrics are calculated only against the frozen, unmodified machine requirements.</p>
              <pre>{JSON.stringify(aggregation.summary_metrics, null, 2)}</pre>
              {aggregation.requirement_aggregates.map((item) => (
                <article key={item.requirement_id}>
                  <strong>{item.requirement_id}</strong><span>{item.majority_decision ?? 'no majority'} · {item.disagreement ? 'disagreement' : 'agreement'}</span>
                  <small>{JSON.stringify(item.decisions)}</small>
                </article>
              ))}
            </section>
          ) : null}
          {revision ? (
            <section className="consensus-panel">
              <h4>Consensus validation</h4>
              <p>{revision.revisions.length} agent-assisted proposal(s) are stored separately; human experts retain decision authority.</p>
              {consensusRequirements.map((requirement) => {
                const proposed = revisionsByRequirement.get(requirement.id);
                return (
                  <article key={requirement.id}>
                    <strong>{requirement.normalized_statement}</strong>
                    {requirement.origin_kind === 'expert_added' ? <small>Expert-added missing requirement; excluded from original machine metrics.</small> : null}
                    {proposed ? <p>Proposed revision: {proposed.proposed_statement}</p> : null}
                    <select onChange={(event) => setConsensusDraft((current) => ({ ...current, [requirement.id]: event.target.value as ConsensusDecision['decision'] }))} value={consensusDraft[requirement.id] ?? ''}>
                      <option disabled value="">Record expert consensus…</option>
                      <option value="accepted">Accepted</option>
                      <option disabled={!proposed} value="accepted_with_revision">Accepted with revision</option>
                      <option value="rejected">Rejected</option><option value="out_of_scope">Out of scope</option><option value="merged">Merged</option><option value="split">Split</option>
                    </select>
                  </article>
                );
              })}
              <button disabled={busy} onClick={() => void finalize()} type="button"><CheckCircle2 size={16} />Finalize validated baseline</button>
            </section>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}

function patchDraft(
  setDrafts: Dispatch<SetStateAction<Record<string, DraftReview>>>,
  requirementId: string,
  patch: Partial<DraftReview>,
) {
  setDrafts((current) => ({
    ...current,
    [requirementId]: {
      ...(current[requirementId] ?? { ratings: {}, comment: '', proposedStatement: '', feedbackCategories: '', mergeWith: '', splitStatements: '' }),
      ...patch,
    },
  }));
}

function completeRatings(ratings: ExpertCriterionRatings): ExpertCriterionRatings {
  return Object.fromEntries(RATING_FIELDS.map((field) => [field, ratings[field] ?? null])) as ExpertCriterionRatings;
}

async function sha256Canonical(value: object, excludedField: string) {
  const copy: Record<string, unknown> = { ...(value as Record<string, unknown>) };
  delete copy[excludedField];
  const data = new TextEncoder().encode(stableStringify(copy));
  const digest = await window.crypto.subtle.digest('SHA-256', data);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`).join(',')}}`;
}

function humanize(value: string) {
  return value.replace(/_/g, ' ');
}

function splitValues(value: string | undefined) {
  return (value ?? '').split(',').map((item) => item.trim()).filter(Boolean);
}
