#!/usr/bin/env python3
"""Read-only report of saved procedural base judgements and discussion outcomes."""
import argparse,csv,json,urllib.request
from pathlib import Path
from collections import Counter

def get(url):
    with urllib.request.urlopen(url,timeout=60) as response:return json.load(response)

def check_summary(check):
    if not check:return ''
    # These fields have different meanings; never relabel an old result as a new verdict check.
    field='verdict_supported' if 'verdict_supported' in check else 'entries_express_need'
    return f'{field}: {check.get(field)}; nothing_lost: {check.get("nothing_lost")}; {check.get("rationale", "")}'

def label_removed(r):
    # rq1-base-expert-v3 wrote "dispute" for a removed label (JRC run-fd39639e: 11); later
    # policies write flag_removed and keep "dispute" for a kept label (v1/v2).
    return r['effect']=='flag_removed' or (r['effect']=='dispute' and r['policy']=='rq1-base-expert-v3')

def main():
    p=argparse.ArgumentParser();p.add_argument('--api',required=True);p.add_argument('--run',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    root=a.api.rstrip('/')+'/api/rq1/v2/runs/'+a.run
    run=get(root+'?audit=true');coverage=get(root+'/coverage');out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    records={r['revision_id']:r for r in run['requirements']};entries={}
    for c in run.get('deliberations',[]):entries.update(c.get('discussion_trace',{}).get('packet',{}).get('base_entries',{}))
    # Entry terms are also frozen on classifier matches; never load another catalogue.
    for r in records.values():
        entries.update({e['id']:e for e in r.get('base_need_matches',[])})
        entries.update({e['id']:e for e in (r.get('base_relation') or {}).get('entries',[])})
    rows=[]
    for r in records.values():
        if not r.get('need_statement'):continue
        relation=r.get('base_relation') or {};state=relation.get('classifier_state',{})
        rows.append({'revision_id':r['revision_id'],'need':r.get('need_statement') or r['normalized_statement'],
            'classifier':state.get('need_class',r.get('need_class')),'reviewer':relation.get('verdict',''),
            'active':r['revision_id'] in run.get('active_revision_ids',[]),'policy':relation.get('policy',''),'reason':relation.get('reason',''),'phase':relation.get('phase',''),'status':relation.get('status',''),'effect':relation.get('effect',''),
            'errors':'; '.join(relation.get('errors',[])),'isolated':json.dumps(relation['isolated_from_failed_batch']) if relation.get('isolated_from_failed_batch') else '',
            'flags':', '.join(r.get('processing_flags',[])),'entries':'; '.join(' '.join(filter(None,[entries.get(i,{}).get('class'),entries.get(i,{}).get('property')])) or i for i in relation.get('entry_ids',[])),
            'addition':relation.get('addition',''),'rationale':relation.get('rationale',''),'check':json.dumps(relation.get('check')) if relation else '','check_summary':check_summary(relation.get('check'))})
    with (out/'base-review.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['revision_id','need']);w.writeheader();w.writerows(rows)
    matrix=Counter((r['classifier'],r['reviewer']) for r in rows if r['active'])
    lines=['# Procedural base review',f'Run: `{a.run}` · status: {run["status"]}',
        'Machine judgements only; no human acceptance or accuracy claim. CSV includes historical need revisions with an active column. Usage below covers this run’s new calls, not ancestral calls.','\n## Classifier × reviewer (current inventory)',
        *[f'- {c or "not checked"} × {v or "not reviewed"}: {n}' for (c,v),n in sorted(matrix.items(),key=lambda x:str(x[0]))]]
    for title,predicate in [('Flags added',lambda r:r['effect']=='flag_added'),('Labels removed',label_removed),
        ('Disputes (label kept; rq1-base-expert-v1/v2)',lambda r:r['effect']=='dispute' and not label_removed(r)),
        ('Domain uses',lambda r:r['reviewer']=='domain_use_of_base'),('Not reviewed',lambda r:r['status']=='not_reviewed'),
        ('After discussion',lambda r:r['phase']=='after_discussion')]:
        lines+=['\n## '+title]
        for r in rows:
            if predicate(r):lines += [f'- {r["need"]} — {r["entries"]}; {r["addition"]}; {r["rationale"] or r["reason"]}; check: {r["check_summary"]}'+(f'; errors: {r["errors"]}' if r['errors'] else '')]
    lines+=['\n## Discussion actions on labelled needs']
    for c in run.get('deliberations',[]):
        frozen={r['revision_id']:r for r in c.get('frozen_requirements',[])}
        for action in (c.get('mediation') or {}).get('outcomes',[]):
            if action.get('action')=='covered_by_base' or any('covered_by_base' in frozen.get(i,{}).get('processing_flags',[]) for i in action.get('parent_revision_ids',[])):
                lines.append('- '+json.dumps({'case':c['case_id'],**action},ensure_ascii=False))
    # Salvage (rq1-fa-salvage-v1, v2) shows the actions it dropped as unapplied review rows; v2 also salvages
    # a plan that keeps no mediator action, which the metrics count apart.
    lines+=['\n## Mediator actions rejected by salvage (not applied)',
        f'Salvaged cases (metrics): {(run.get("metrics") or {}).get("salvaged_cases","not recorded")}; mediator actions rejected by salvage: '
        f'{sum(bool(o.get("salvage_rejected")) for c in run.get("deliberations",[]) for o in (c.get("mediation") or {}).get("outcomes",[]))}. '
        f'Salvaged with no mediator action kept (metrics): {(run.get("metrics") or {}).get("salvaged_nothing_kept","not recorded")}; '
        f'lost after such a salvage (budget or invalid output; v11 stopped these earlier as invalid output): '
        f'{(run.get("metrics") or {}).get("lost_after_salvage_nothing_kept","not recorded")}.']
    for c in run.get('deliberations',[]):
        for action in (c.get('mediation') or {}).get('outcomes',[]):
            if action.get('salvage_rejected'):lines.append(f'- {c["case_id"]} · {action.get("action")} {action.get("action_id")}: '+'; '.join(action.get('validation_errors',[])))
    # v13: the check rule ignores checks of IDs that are not actions of the plan; the runs before it have no count.
    lines+=['\n## Checks of IDs outside the plan (ignored)',
        f'Ignored checks (metrics): {(run.get("metrics") or {}).get("ignored_checks","not recorded")}.']
    for c in run.get('deliberations',[]):
        if (c.get('mediation') or {}).get('ignored_check_ids'):
            lines.append(f'- {c["case_id"]}: '+', '.join(c['mediation']['ignored_check_ids']))
    # Scope contract v1 (rq1-profile-scope-v7, rq1-fa-dialogue-v13): what the catalogue-record test set aside at
    # normalisation, and the changes the scope tests blocked at apply, each counted apart.
    record_reasons=('not_catalogue_level','not_find_or_access','operational_data_processing')
    asides=[a for a in run.get('set_aside_observations',[]) if a.get('reason') in record_reasons]
    def stated(revision_id,fallback=''):
        r=records.get(revision_id) or {}
        return r.get('need_statement') or r.get('normalized_statement') or fallback
    lines+=['\n## Scope contract v1: set aside by the record test at normalisation',
        f'{len(asides)} needs ({dict(Counter(a["reason"] for a in asides))}); set aside by the F/A test: '
        f'{sum(a.get("reason")=="fa_scope_set_aside" for a in run.get("set_aside_observations",[]))}.']
    for a in asides:
        scope=(a.get('details') or {}).get('profile_scope') or {}
        confirmed=' (failed again alone)' if (scope.get('confirmation') or {}).get('outcome')=='confirmed' else ''
        lines.append(f'- {stated(a.get("revision_id"),a.get("need_id",""))} — {a["reason"]}{confirmed}; record: {scope.get("record_resource","not recorded")}; {a.get("rationale","")}')
    # rq1-profile-scope-v8: a failure counts only when the need, judged again alone, fails too; the needs kept
    # against their first judgement are flagged profile_scope_disputed.
    def first_verdict(r):
        # disputed: the first judgement is in confirmation.verdict; not_checked: profile_scope is the first
        # judgement and confirmation.reason says why the second is missing.
        scope=r.get('profile_scope') or {};c=scope.get('confirmation') or {}
        if c.get('outcome')=='not_checked':
            return {'failed_tests':c.get('first_failed_tests',[]),'rationale':scope.get('rationale',''),'second_missing':c.get('reason','')}
        return c.get('verdict') or {}
    disputed=[r for r in records.values() if 'profile_scope_disputed' in r.get('processing_flags',[])]
    lines+=['\n## Scope contract v1: kept against a first failed record test (profile_scope_disputed)',
        f'{len(disputed)} need revisions ({sum(r["revision_id"] in run.get("active_revision_ids",[]) for r in disputed)} active); '
        f'second judgements by outcome at normalisation: {(run.get("need_steps",{}).get("profile_scope") or {}).get("confirmation_counts","not recorded")}.']
    for r in disputed:
        first=first_verdict(r);outcome=((r.get('profile_scope') or {}).get('confirmation') or {}).get('outcome')
        lines.append(f'- {stated(r["revision_id"])} — second judgement: {outcome}; record now: {(r.get("profile_scope") or {}).get("record_resource")}; '
                     f'first: {", ".join(first.get("failed_tests") or [])}; {first.get("rationale","")}'
                     +(f'; second missing: {first["second_missing"]}' if first.get('second_missing') else ''))
    outcomes=[(c['case_id'],o) for c in run.get('deliberations',[]) for o in (c.get('mediation') or {}).get('outcomes',[])]
    blocked=[(case,o) for case,o in outcomes if o.get('scope_block')]
    unjudged=[t for _,o in outcomes if o.get('applied') for t in o.get('scope_tests',[]) if (t.get('profile_scope') or {}).get('status')!='checked']
    lines+=['\n## Scope contract v1: changes blocked by the scope tests at apply',
        f'{len(blocked)} changes blocked by a failed test (first failure by test: '
        f'{dict(Counter(o["scope_block"][0]["test"] for _,o in blocked))}; other blocked changes: '
        f'{sum(o.get("status")=="blocked_change" for _,o in outcomes)-len(blocked)}); '
        f'{sum(bool(o.get("scope_tests")) for _,o in outcomes)} changes tested; {len(unjudged)} applied needs without a record judgement (kept, flagged).']
    for case,o in blocked:
        for b in o['scope_block']:
            lines.append(f'- {case} · {o.get("action")} {o.get("action_id")}: {b["statement"]} — {b["test"]}; record: {b.get("record_resource") or "not recorded"}; {b["rationale"]}')
    calls=[c for c in run.get('model_calls',[]) if c.get('step') in {'base_review','base_review_check'}]
    lines+=['\n## Reviewer usage',f'{len(calls)} calls ({dict(Counter(c.get("step") for c in calls))}); {sum((c.get("token_usage") or {}).get("total_tokens",0) or 0 for c in calls)} reported tokens ({sum(bool(c.get("token_usage")) for c in calls)} calls supplied usage); {sum(c.get("latency_seconds",0) or 0 for c in calls):.1f} seconds.',
        '\n## Case stop reasons',json.dumps(dict(Counter(c.get('stop_reason') for c in run.get('deliberations',[]))),indent=2),
        '\n## Coverage',json.dumps({k:coverage.get(k) for k in ['counts','base_relation_counts','base_dispute_revision_ids','base_label_removed_revision_ids','base_recheck_revision_ids','base_review_pending_revision_ids']},indent=2)]
    (out/'base-review.md').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')
if __name__=='__main__':main()
