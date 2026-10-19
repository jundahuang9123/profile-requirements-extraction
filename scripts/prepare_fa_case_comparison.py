#!/usr/bin/env python3
"""Prepare matched discussion inputs from a saved trace; never run inference."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def prepare(trace,limit=12):
    cases=trace.get('discussions',trace.get('deliberations',[]))
    if not cases:raise ValueError('Export has no saved discussion cases.')
    if trace.get('workflow',trace.get('request',{}).get('stakeholder_workflow'))!='fa_mediated':
        raise ValueError('Use an F/A workflow trace, not a historical extraction or reference file.')
    selected=[]
    for case in cases:
        saved=case.get('discussion_trace',{})
        packet=saved.get('packet')
        if packet is None or saved.get('packet_hash')!=sha(packet):
            raise ValueError('Frozen case packet is missing or changed.')
        selected.append({'case_id':case['case_id'],'packet':packet,'packet_hash':sha(packet),
            'participants':case['participants'],'requirements':case['frozen_requirements'],
            'no_discussion_working_revision_ids':saved.get('working_before_revision_ids',[]),
            'requirements_hash':sha(case['frozen_requirements']),
            'budgets':{k:case[k] for k in ('max_calls','total_output_budget','max_seconds')}})
    # Deliberately deterministic selection; no reference answers or output-quality selection.
    selected.sort(key=lambda c:c['case_id'])
    roles=trace.get('stakeholder_audit',{}).get('fa_discussion_plan',{}).get('roles')
    if not roles:raise ValueError('Saved panel definitions are required for matched replay.')
    return {'schema_version':'rq1-fa-matched-case-preparation-v1','source_run_id':trace['run_id'],
        'roles':roles,'roles_hash':sha(roles),'case_count_available':len(selected),'cases':selected[:limit],
        'selection_rule':'case_id ascending; no reference/outcome selection',
        'arms':{'no_discussion':{'inference':False},'gpt_oss':{'stakeholder_review':'inferenz-gpt-oss-120b',
            'mediation':'inferenz-gpt-oss-120b','mediation_check':'inferenz-gpt-oss-120b','assessment':'inferenz-gpt-oss-120b'},
            'qwen_mediator':{'stakeholder_review':'inferenz-gpt-oss-120b','mediation':'inferenz-qwen3-8-27b',
            'mediation_check':'inferenz-gpt-oss-120b','assessment':'inferenz-gpt-oss-120b'}},
        'limitations':['Preparation only; no inference or quality judgement performed.',
            'Validate exact model aliases/options and use identical packets, roles and budgets in a separate authorised replay.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--limit',type=int,default=12)
    args=parser.parse_args()
    if not 1<=args.limit<=12:parser.error('Limit must be between one and twelve.')
    data=prepare(json.loads(args.trace.read_text()),args.limit)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')

if __name__=='__main__':main()
