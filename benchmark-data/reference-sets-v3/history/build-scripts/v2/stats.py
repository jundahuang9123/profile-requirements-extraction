import json, sys, collections
sys.path.insert(0,'.')
from codes import CODES, DERIV, NAP
B='/home/claude/jundahuang9123/profile-requirements-extraction/benchmark-data/'
files={'Mobility':'mobilitydcat/reference-requirements/consolidated-requirements.json','Health':'healthdcat/reference-requirements/curated-requirements.json',
'Stat':'statdcat/reference-requirements/requirements-and-resolutions.json','Geo':'geodcat/reference-requirements/alignment-requirements.json','JRC':'jrc-research/reference-requirements/core-requirements.json'}
rows=[]
for case,f in files.items():
    d=json.load(open(B+f))
    for r in d['requirements']:
        c=CODES[r['id']]
        rows.append(dict(case=case,id=r['id'],statement=r['statement'],locator=r.get('source_locator',''),
            napType=r.get('type'),importance=r.get('importance'),**c,deriv=DERIV[r['id']],nap=NAP.get(r['id'])))
assert len(rows)==75
json.dump(rows,open('rows.json','w'),indent=1,ensure_ascii=False)
def grp(r):
    if r['resp'] in ('A','B'): return 'new-'+r['sub']
    if r['resp']=='C': return 'new-minted'   # code lists minted (Req-21)
    return {'D':'changed','E':'changed','F':'base','G':'none','H':'open'}[r['resp']]
cases=list(files)+['All']
print('RESPONSE GROUPS')
for cs in cases:
    rs=[r for r in rows if cs=='All' or r['case']==cs]
    print(cs,len(rs),dict(collections.Counter(grp(r) for r in rs)))
print('\nRESP raw'); 
for cs in cases:
    rs=[r for r in rows if cs=='All' or r['case']==cs]; print(cs,dict(sorted(collections.Counter(r['resp']+('-'+r.get('sub','') if r['resp'] in 'AB' else '') for r in rs).items())))
print('\nLEVEL')
for cs in cases:
    rs=[r for r in rows if cs=='All' or r['case']==cs]; print(cs,dict(collections.Counter(r['level'] for r in rs)))
print('\nRESP among level M')
rs=[r for r in rows if r['level']=='M']; print(len(rs),dict(collections.Counter(grp(r) for r in rs)), dict(collections.Counter(r['resp'] for r in rs)))
print('RESP among G/S'); rs=[r for r in rows if r['level']!='M']; print(len(rs),dict(collections.Counter(r['resp'] for r in rs)))
print('\nPROBLEM')
for cs in cases:
    rs=[r for r in rows if cs=='All' or r['case']==cs]; print(cs,dict(sorted(collections.Counter(r['problem'] for r in rs).items())))
print('\nDERIV (rows citing)')
for cs in cases:
    rs=[r for r in rows if cs=='All' or r['case']==cs]; print(cs,dict(sorted(collections.Counter(d for r in rs for d in r['deriv']).items())))
print('\nATOMS')
for cs in cases:
    rs=[r for r in rows if cs=='All' or r['case']==cs]; a=[r['atoms'] for r in rs]
    print(cs,'mean %.2f'%(sum(a)/len(a)),'max',max(a),'compound',sum(1 for x in a if x>1),'of',len(a))
print('\nRQ2 flagged', [r['id'] for r in rows if r['rq2']])
print('\nfirst words', collections.Counter(r['statement'].split()[0] for r in rows).most_common())
print('\nMobility doc vs exp-only:')
mob=[r for r in rows if r['case']=='Mobility']
doc=[r['id'] for r in mob if set(r['deriv'])&{'std','proj'}]; print(len(doc),'doc-based;',len(mob)-len(doc),'experience/meeting only')
print('content rows (M) doc-based', sum(1 for r in mob if r['level']=='M' and set(r['deriv'])&{'std','proj'}), 'of', sum(1 for r in mob if r['level']=='M'))
print('new-term rows citing CMC/std', [r['id'] for r in mob if r['resp'] in 'AB' and 'std' in r['deriv']], [r['id'] for r in mob if r['resp'] in 'AB' and 'std' not in r['deriv']])
print('\nNAPCORE type x level'); print(collections.Counter((r['napType'],r['level']) for r in mob))
print('NAPCORE importance x resp'); print(collections.Counter((r['importance'],grp(r)) for r in mob))
print('\nconfidence', collections.Counter(r['conf'] for r in rows))
# atoms of change across all rows
kinds=collections.Counter(k for r in rows for _,_,k in r['terms'])
print('\nterm atoms by kind', kinds)
print('rows with any constrained/newclass/cvext atom:', sum(1 for r in rows if any(k in ('constrained','newclass','cvext') for _,_,k in r['terms'])))
