#!/usr/bin/env python3
"""Validate the evaluator-only audit against its frozen benchmark corpus."""
import argparse, collections, csv, hashlib, json
from pathlib import Path

def validate(audit, corpus):
    errors=[]
    def check(ok,message):
        if not ok: errors.append(message)
    def load(n):return json.loads((audit/n).read_text())
    def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    snapshot=load('snapshot.json'); data=load('expansion-candidates.json'); rows=data['requirements']
    legacy=load('legacy-row-review.json')['rows']; atoms=load('mobility-clause-draft.json')['atoms']
    check(data['scoring_enabled'] is False,'Expansion scoring must remain disabled')
    ids=[r['id'] for r in rows];check(len(ids)==len(set(ids)),'Duplicate candidate IDs')
    check(dict(collections.Counter(r['benchmark'] for r in rows))==snapshot['audit_counts'],'Candidate counts differ')
    check(len(legacy)==snapshot['legacy_count'],'Legacy count differs')
    known={}
    for rel,expected in snapshot['legacy_reference_files'].items():
        f=corpus/rel
        check(f.exists() and digest(f)==expected,'Legacy source changed: '+rel)
        if f.exists():
            for r in json.loads(f.read_text())['requirements']:known[(rel.split('/')[0],r['id'])]=r
    check({(r['benchmark'],r['reference_id']) for r in legacy}==set(known),'Legacy identities differ')
    runtime=json.loads((corpus/'runtime-inputs.json').read_text())
    check(digest(corpus/'runtime-inputs.json')==snapshot['runtime_allowlist_sha256'],'Runtime allowlist changed')
    allowed={x for b in runtime['benchmarks'].values() for k,v in b.items() if k in ('raw','consolidation','background') for x in v}
    for rel,info in snapshot['sources'].items():
        f=corpus/rel;check(f.exists() and digest(f)==info['sha256'],'Reference source changed: '+rel)
        check(rel not in allowed,'Evaluator source is allowlisted: '+rel)
    pages={'healthdcat':98,'geodcat':87,'statdcat':94}
    for r in rows:
        label=r['id']+': '
        check(r['scoring_enabled'] is False,label+'scoring enabled without adjudication')
        check(r['independent_adjudication']=='pending',label+'false independent-review claim')
        check(r['raw_evidence_coverage']=='unassessed' and r['consolidation_evidence_coverage']=='unassessed',label+'unsupported input-coverage label')
        check(bool(r['statement'] and r['source_locator'] and r['applicability']),label+'missing content or locator')
        check(r['source_path'] in snapshot['sources'],label+'unregistered source')
        for parent in r['legacy_parent_ids']:check((r['benchmark'],parent) in known,label+'unknown parent '+parent)
        if r['benchmark'] in pages:
            check(bool(r['pdf_pages']),label+'missing PDF pages')
            check(all(isinstance(p,int) and 1<=p<=pages[r['benchmark']] for p in r['pdf_pages']),label+'invalid PDF page')
            check(r['source_sha256']==snapshot['sources'][r['source_path']]['sha256'],label+'source hash differs')
        else:
            check(r['source_content_sha256'] is None,label+'citation hash must not masquerade as content hash')
    for r in legacy:
        check(r['statement']==known[(r['benchmark'],r['reference_id'])]['statement'],'Legacy statement changed')
        check(set(r['related_candidate_ids'])<=set(ids),'Unknown candidate in ledger')
    check(len(atoms)==snapshot['mobility_decomposition_clauses'],'Mobility clause count differs')
    check({r['parent_id'] for r in atoms}=={f'Req-{i}' for i in range(1,41)},'Mobility parent coverage incomplete')
    check(len({r['id'] for r in atoms})==len(atoms),'Duplicate mobility clause IDs')
    for r in atoms:
        check(r['scoring_enabled'] is False,'Mobility draft scoring enabled')
        check(r['importance']==known[('mobilitydcat',r['parent_id'])]['importance'],'Mobility importance changed')
    with (audit/'review-queue.csv').open(newline='') as f:queue=list(csv.DictReader(f))
    check([r['id'] for r in queue]==ids,'CSV and JSON ordering/IDs differ')
    check([r['statement'] for r in queue]==[r['statement'] for r in rows],'CSV and JSON statements differ')
    return {'status':'passed' if not errors else 'failed','legacy_rows':len(legacy),'expansion_candidates':len(rows),'mobility_draft_clauses':len(atoms),'errors':errors,'semantic_adjudication_performed':False,'historical_corpus_complete':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--corpus',type=Path,required=True);p.add_argument('--report',type=Path)
    a=p.parse_args();r=validate(Path(__file__).resolve().parent,a.corpus);s=json.dumps(r,indent=2)+'\n';print(s)
    if a.report:a.report.write_text(s)
    raise SystemExit(bool(r['errors']))
