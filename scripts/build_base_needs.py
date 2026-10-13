#!/usr/bin/env python3
"""Build frozen generic-need catalogues solely from pinned base registries, offline.

No benchmark sources or reference rows are read. Deterministic label-based phrasing
is a draft for human review, not evidence that an optional property is populated.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'requirement-reuse-service/config/base_profiles'
POLICY='rq1-base-needs-catalogue-v1'


def words(value):
    local=value.split(':')[-1]
    return re.sub(r'([a-z])([A-Z])', r'\1 \2', local).lower()


def build(path):
    raw=path.read_bytes();profile=json.loads(raw);entries=[]
    for cls, properties in sorted(profile['classes'].items()):
        resource=words(cls)
        entries.append({'id':'base-'+hashlib.sha256((cls).encode()).hexdigest()[:20],
            'need':f'Identify and describe a {resource}.','class':cls,'property':None,'rq2_term':cls,
            'label':resource,'definition':None,'base_obligation':None})
        for prop, entry in sorted(properties.items()):
            labels=[str(s) for s in entry.get('labels',[]) if s and ' - ' not in str(s)]
            label=labels[0] if labels else words(prop)
            label=re.sub(r'([a-z])([A-Z])',r'\1 \2',label).lower()
            definition=entry.get('definition') or entry.get('description')
            # A property phrase describes what information the vocabulary can
            # express; it does not invent a base guarantee or domain condition.
            entries.append({'id':'base-'+hashlib.sha256((cls+'/'+prop).encode()).hexdigest()[:20],
                'need':f'Find the {label} of a {resource}.','class':cls,'property':prop,
                'rq2_term':prop,'label':label,'definition':definition,
                'base_obligation':entry.get('obligation'), 'vocabulary':entry.get('vocabulary')})
    result={'base_profile_id':profile['id'],'base_profile_sha256':hashlib.sha256(raw).hexdigest(),
        'policy_version':POLICY,'phrasing':'deterministic labels; definitions retained where registry provides them',
        'review':{'status':'unreviewed','reviewer':None,'reviewed_at':None},'entries':entries}
    result['catalogue_hash']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    return json.dumps(result,indent=2,ensure_ascii=False)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    for path in sorted(DIRECTORY.glob('*.json')):
        if path.name.endswith('.needs.json'): continue
        target=path.with_name(path.stem+'.needs.json');value=build(path)
        if args.check:
            if not target.exists() or target.read_text()!=value: parser.error(f'Stale base needs catalogue: {target.name}')
        else: target.write_text(value)


if __name__=='__main__': main()
