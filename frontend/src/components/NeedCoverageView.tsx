import { Run } from '../lib/workflowApi';

type Citation = { evidence_id: string; source_name: string; quote: string; rationale: string };
type Category = { category_id: string; label: string; dimension?: string; labels?: string[]; citations: Citation[] };
type Registry = { attempted_count?: number; rejected_mentions?: unknown[]; reason?: string; categories: Category[]; examined_count: number; input_count: number; unchecked_evidence_ids: string[]; scan_complete: boolean };
type Selection = { selected_need_ids: string[]; selected_revision_ids: string[]; represented_need_ids: string[]; covered_by: Record<string,string>; protected_needs: Record<string,string[]>; uncovered_category_ids: string[]; optimal_for_recorded_coverage: boolean; input_count: number; review_only_equivalences?: { need_ids: string[]; reason: string; coverage_substitution: boolean }[]; comparison_need_count?: number };

export function NeedCoverageView({ run, inspect, review }: { run: Run; inspect: (id: string) => void; review: (id: string) => void }) {
  const registry = run.need_steps?.dataset_categories as Registry | undefined;
  const selection = run.need_steps?.selection as Selection | undefined;
  if (!registry && !selection) return null;
  const categories = registry?.categories ?? [];
  const steps = run.need_steps ?? {};
  const classification = steps.classification as { input_count?: number; retained_count?: number; generic_count?: number; base_gap_counts?: Record<string,number>; decisions?: { search_complete?: boolean }[] } | undefined;
  const scope = steps.profile_scope as { input_count?: number; retained_count?: number; set_aside_count?: number; set_aside_by_reason?: Record<string,number> } | undefined;
  const applicability = steps.dataset_applicability as { input_count?: number; checked_count?: number; not_checked_ids?: string[] } | undefined;
  const families = steps.families as { input_count?: number; grouped_count?: number; family_count?: number; grouping_unavailable_chunks?: number } | undefined;
  const grouping = steps.grouping as { input_count?: number; group_count?: number; audit?: unknown[] } | undefined;
  const rewrite = steps.need_statement as { input_count?: number; need_count?: number } | undefined;
  const categoryLabel = (id: string) => categories.find(c => c.category_id === id)?.label ?? id;
  const record = (id: string) => run.requirements.find(r => r.requirement_id === id && selection?.selected_revision_ids.includes(r.revision_id));
  return <section className="workflow-panel">
    <h2>Dataset kinds and compact requirements</h2>
    <p>These are source-linked machine proposals. Category labels describe the supplied sources; they do not establish community agreement or an exhaustive taxonomy.</p>
    {registry && <>{registry.reason && <p>{registry.reason}</p>}<p>{registry.attempted_count !== undefined && <>{registry.attempted_count} units attempted · </>}{registry.examined_count} of {registry.input_count} evidence units fully checked · {categories.length} dataset kinds. {!registry.scan_complete && 'The scan is incomplete; uncertain needs stay in the list. Equivalence can still be checked for needs with verified applicability.'}</p>
      {!!registry.rejected_mentions?.length && <p>{registry.rejected_mentions.length} rejected category mentions are recorded in the scan audit; valid mentions from partially checked units remain available.</p>}<details><summary>Dataset kinds and their sources</summary>{categories.length ? categories.map(category => <article key={category.category_id}>
        <h3>{category.label}</h3><p>Dimension: {category.dimension ?? 'unspecified'}. {!!category.labels && category.labels.length > 1 && <>Source labels: {category.labels.join(', ')}.</>}</p>{category.citations.map((citation,index) => <blockquote key={index}>
          <p>{citation.quote}</p><p>{citation.rationale}</p><button onClick={() => inspect(citation.evidence_id)}>Inspect source · {citation.source_name}</button>
        </blockquote>)}
      </article>) : <p>No dataset kinds were identified. No applicability is assumed; all needs remain available for review.</p>}</details></>}
    <details><summary>Stage counts and unresolved checks</summary>
      <p>{grouping?.input_count ?? '—'} proposals entered semantic grouping; {grouping?.group_count ?? '—'} groups were produced. {rewrite?.need_count ?? '—'} rewritten needs entered base comparison.</p>
      <p>Base comparison: {classification?.retained_count ?? '—'} retained from {classification?.input_count ?? '—'} rewritten needs. {classification?.base_gap_counts?.no_base_match ?? 0} no-match decisions followed complete catalogue searches; a positive full match can stop early. Dispositions: {Object.entries(classification?.base_gap_counts ?? {}).map(([key,value]) => `${key.replace(/_/g,' ')} ${value}`).join(' · ') || 'not saved'}.</p>
      <p>Catalogue scope: {scope?.retained_count ?? '—'} retained and {scope?.set_aside_count ?? '—'} set aside from {scope?.input_count ?? '—'} judged. Reasons: {Object.entries(scope?.set_aside_by_reason ?? {}).map(([key,value]) => `${key.replace(/_/g,' ')} ${value}`).join(' · ') || 'none recorded'}.</p>
      <p>Applicability: {applicability?.checked_count ?? '—'} checked of {applicability?.input_count ?? '—'}; {applicability?.not_checked_ids?.length ?? '—'} unresolved. Families: {families?.family_count ?? '—'} from {families?.grouped_count ?? families?.input_count ?? '—'} eligible needs; {families?.grouping_unavailable_chunks ?? 0} family-grouping chunks used exact-singleton fallback. Compact representatives: {selection?.selected_need_ids.length ?? '—'} of {selection?.input_count ?? '—'} atomic needs.</p>
    </details>
    {selection && <>
      <p><strong>{selection.selected_need_ids.length} compact representatives from {selection.input_count} atomic needs.</strong> Needs with incomplete support or applicability remain separate for human review; selected counts are not an accuracy or minimality claim. The complete atomic review list remains available.</p>
      <p>Equivalence comparisons covered {selection.comparison_need_count ?? 0} needs. {selection.optimal_for_recorded_coverage ? 'The selected cover is smallest for the safe equivalence links recorded.' : 'The bounded search did not establish the smallest cover.'} Unexamined comparisons and machine errors can change the result.</p>
      {!!selection.review_only_equivalences?.length && <details><summary>{selection.review_only_equivalences.length} possible equivalent pairs need review; no coverage was substituted</summary>{selection.review_only_equivalences.map((pair,index) => <p key={`${pair.need_ids.join('-')}-${index}`}>{pair.need_ids.map(id => run.requirements.find(item => item.requirement_id === id)?.need_statement ?? id).join(' ↔ ')} · {pair.reason.replace(/_/g,' ')}.</p>)}</details>}
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
