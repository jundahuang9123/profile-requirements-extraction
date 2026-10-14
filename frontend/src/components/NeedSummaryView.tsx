import { Requirement, Run } from '../lib/workflowApi';

export function NeedSummaryView({ record, run, inspect }: { record: Requirement; run: Run; inspect: (id: string) => void }) {
  if (!record.need_statement) return null;
  const claims = [record, ...record.parent_revision_ids.map(id => run.requirements.find(r => r.revision_id === id)).filter((r): r is Requirement => !!r)].filter(r => r.unbacked_obligation);
  return <div className="workflow-need-summary">
    <div className="workflow-tags"><span>{record.rank ? `Rank ${record.rank}` : 'Added / restored for review'}</span><span>{record.need_class?.replace(/_/g, ' ') ?? 'Classification needs review'}</span><span>Obligation: {record.normalized_intent.obligation_hint === 'unknown' ? 'not stated by sources' : record.normalized_intent.obligation_hint}</span></div>
    {(record.obligation_alternatives?.length ?? 0) > 1 && <p>Source obligations differ: {record.obligation_alternatives!.map(a => `${a.obligation} (${a.count} proposals)`).join('; ')}. A reviewer decides.</p>}
    {!!claims.length && <p>{[...new Set(claims.map(r => r.unbacked_obligation!.label))].map(label => `${claims.filter(r => r.unbacked_obligation!.label === label).length} proposals claimed ${label} without a quote stating that level`).join('; ')}.</p>}
    {record.need_condition && <p>Condition: {record.need_condition}</p>}
    <details><summary>Use cases · {record.task_justifications?.length ?? 0} necessary links</summary>{record.task_justifications?.map(link => <p key={link.task_id}><strong>{link.task_id}</strong> · {link.justification}</p>)}{!record.task_justifications?.length && <p>{run.request?.scoping === 'off' ? 'Scoping is off for this run. No necessity claim is made.' : 'No verified use-case link. Human revisions and restored needs require review.'}</p>}</details>
    <details><summary>Supporting candidates · {record.parent_revision_ids.length}</summary>{record.parent_revision_ids.map(id => { const member = run.requirements.find(r => r.revision_id === id); return <article key={id}><p>{member?.normalized_statement ?? id}</p><small>{member?.contributing_roles.join(', ')} · Source {member?.verification?.status ?? 'pending'} · {member?.normalized_intent.obligation_hint}</small><details><summary>Member citations</summary>{member?.evidence_links.map((link,index) => <blockquote key={index}><p className="workflow-quote">{link.quote}</p><button onClick={() => inspect(link.evidence_id)}>Inspect member source · {link.component}</button></blockquote>)}</details></article>; })}</details>
    <details><summary>Source evidence · {record.evidence_links.length} cited excerpts</summary>{record.evidence_links.map((link, index) => <blockquote key={index}><p className="workflow-quote">{link.quote}</p><button onClick={() => inspect(link.evidence_id)}>Inspect original · {link.component} · {link.relation}</button></blockquote>)}</details>
    {!!record.base_need_matches?.length && <details><summary>Matching base needs · {record.base_need_matches.length}</summary>{record.base_need_matches.map(match => <p key={match.id}>{match.need} · base obligation {match.base_obligation ?? 'unspecified'}<br />{match.rationale}</p>)}<p>Base catalogue: {run.base_needs_catalogue?.review?.status ?? 'unreviewed'}. These are machine classifications.</p></details>}
    <details><summary>For RQ2 · vocabulary and modelling hints</summary>
      <p>Observed spellings are preserved here; they are separate from the RQ1 need.</p>
      {[...new Set(record.rq2_hints?.map(hint => hint.term) ?? [])].map(term => <details key={term}><summary><code>{term}</code> · {record.rq2_hints?.filter(h => h.term === term).length} provenance records</summary>{record.rq2_hints?.filter(h => h.term === term).map((hint,index) => <p key={index}>{hint.kind.replace(/_/g, ' ')} · observed in {hint.origin} · revision {hint.revision_id}{hint.evidence_id && <> · <button onClick={() => inspect(hint.evidence_id!)}>Inspect evidence</button></>}</p>)}</details>)}
      {!!record.base_need_matches?.length && <><p>Catalogue suggestions · separate provenance:</p>{record.base_need_matches.map(match => <p key={match.id}><code>{match.rq2_term}</code> · {match.id}</p>)}</>}
      {!record.rq2_hints?.length && !record.base_need_matches?.length && <p>No observed terms or catalogue suggestions.</p>}
    </details>
  </div>;
}
