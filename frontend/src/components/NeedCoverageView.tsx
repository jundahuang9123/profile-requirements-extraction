import { Run } from '../lib/workflowApi';

type Citation = { evidence_id: string; source_name: string; quote: string; rationale: string };
type Category = { category_id: string; label: string; citations: Citation[] };
type Registry = { reason?: string; categories: Category[]; examined_count: number; input_count: number; unchecked_evidence_ids: string[]; scan_complete: boolean };
type Selection = { selected_need_ids: string[]; selected_revision_ids: string[]; represented_need_ids: string[]; covered_by: Record<string,string>; protected_needs: Record<string,string[]>; uncovered_category_ids: string[]; optimal_for_recorded_coverage: boolean; input_count: number };

export function NeedCoverageView({ run, inspect, review }: { run: Run; inspect: (id: string) => void; review: (id: string) => void }) {
  const registry = run.need_steps?.dataset_categories as Registry | undefined;
  const selection = run.need_steps?.selection as Selection | undefined;
  if (!registry && !selection) return null;
  const categories = registry?.categories ?? [];
  const categoryLabel = (id: string) => categories.find(c => c.category_id === id)?.label ?? id;
  const record = (id: string) => run.requirements.find(r => r.requirement_id === id && selection?.selected_revision_ids.includes(r.revision_id));
  return <section className="workflow-panel">
    <h2>Dataset kinds and compact requirements</h2>
    <p>These are source-linked machine proposals. Category labels describe the supplied sources; they do not establish community agreement or an exhaustive taxonomy.</p>
    {registry && <>{registry.reason && <p>{registry.reason}</p>}<p>{registry.examined_count} of {registry.input_count} evidence units checked · {categories.length} dataset kinds. {!registry.scan_complete && 'The scan is incomplete; uncertain needs stay in the list.'}</p>
      <details><summary>Dataset kinds and their sources</summary>{categories.length ? categories.map(category => <article key={category.category_id}>
        <h3>{category.label}</h3>{category.citations.map((citation,index) => <blockquote key={index}>
          <p>{citation.quote}</p><p>{citation.rationale}</p><button onClick={() => inspect(citation.evidence_id)}>Inspect source · {citation.source_name}</button>
        </blockquote>)}
      </article>) : <p>No dataset kinds were identified. No applicability is assumed; all needs remain available for review.</p>}</details></>}
    {selection && <>
      <p><strong>{selection.selected_need_ids.length} selected from {selection.input_count} atomic needs.</strong> Every retained need has a representative; conditions, obligations, dataset applicability and use-case links are preserved by the recorded checks. The complete review list remains below.</p>
      <p>This selection is frozen before human edits. {selection.optimal_for_recorded_coverage ? 'It is the smallest cover of the recorded equivalence links.' : 'It is a compact cover; the bounded search did not establish the smallest size.'} Unexamined equivalences and model errors can change the result.</p>
      {selection.uncovered_category_ids.length > 0 && <p>Dataset kinds with no retained linked need: {selection.uncovered_category_ids.map(categoryLabel).join(', ')}. This is a coverage gap to review, not a reason to invent a requirement.</p>}
      <ol>{selection.selected_need_ids.map(id => {
        const need = record(id);
        const represented = Object.entries(selection.covered_by).filter(([target,representative]) => representative === id && target !== id).map(([target]) => target);
        return <li key={id}><p>{need?.need_statement ?? id}</p>{need && (run.active_revision_ids.includes(need.revision_id) ? <button onClick={() => review(need.revision_id)}>Review need</button> : <p>This original machine version has been reviewed or replaced; use the current full review list below.</p>)}
          {!!selection.protected_needs[id]?.length && <p>Retained for review: {selection.protected_needs[id].map(r => r.replace(/_/g,' ')).join(', ')}.</p>}
          {!!represented.length && <details><summary>Also represents {represented.length} equivalent needs</summary>{represented.map(target => <p key={target}>{run.requirements.find(r => r.requirement_id === target)?.need_statement ?? target}</p>)}</details>}
        </li>;
      })}</ol>
    </>}
  </section>;
}
