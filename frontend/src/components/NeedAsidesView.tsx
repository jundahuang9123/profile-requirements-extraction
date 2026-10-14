import { useState } from 'react';
import { Run, SetAside } from '../lib/workflowApi';

const reasons: Record<string, string> = { no_source_link:'No source link', source_check_failed:'Source check failed', not_supported_by_quote:'Not supported by quote', base_specification_only:'Base specification only', inherited_from_base:'Inherited from base', declared_not_extension:'Declared not an extension', generic_need_served_by_base:'Generic need served by base', no_use_case:'No necessary use-case link' };
export function NeedAsidesView({ run, busy, review, restore }: { run: Run; busy: boolean; review: (id: string) => void; restore: (item: SetAside, rationale: string) => Promise<void> }) {
  const [rationales, setRationales] = useState<Record<string, string>>({});
  const asides = run.set_aside_observations ?? [];
  return <section className="workflow-panel"><h2>Set aside · available for review</h2><p>Restoring an item adds it to human review. It remains unaccepted and still needs source and support checks.</p>
    {Object.entries(reasons).map(([reason, label]) => { const items = asides.filter(a => a.reason === reason); return <details key={reason}><summary>{label} · {items.length}</summary>{items.map(item => {
      const key = `${item.need_id ?? item.observation_id}:${reason}`;
      const record = run.requirements.find(r => r.requirement_id === item.need_id);
      const observation = run.observations?.find(o => o.observation_id === item.observation_id);
      return <article key={key}><strong>{record?.need_statement ?? observation?.statement ?? item.observation_id}</strong><p>{item.rationale}</p>
        {!!record?.base_need_matches?.length && record.base_need_matches.map(match => <p key={match.id}>Matches base: {match.need} · <code>{match.rq2_term}</code></p>)}
        {record && <button onClick={() => review(record.revision_id)}>Inspect need and evidence</button>}
        {item.restored ? <p>Restored for human review.</p> : <><label>Reason to restore<input value={rationales[key] ?? ''} onChange={event => setRationales(old => ({ ...old, [key]:event.target.value }))} /></label><button disabled={busy || !['awaiting_human','completed'].includes(run.status) || !rationales[key]?.trim()} onClick={() => void restore(item, rationales[key])}>Restore for review</button></>}
      </article>;
    })}</details>; })}
  </section>;
}
