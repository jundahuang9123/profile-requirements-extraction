import json, sys
sys.path.insert(0,'.')
from codes import CODES
base=json.load(open('base_registry.json'))
CASE_BASE={'Req':'2.0.1','H':'3.0.0','S':'1.1.0','G':'1.1.0','JRC':'1.1.0'}
def case(i): return 'Req' if i.startswith('Req') else i.split('-')[0]
def anywhere(v,t): return any(t in ps for ps in base[v].values())
def on(v,t,c): return t in base[v].get(c,[])
problems=[]
for rid,c in CODES.items():
    v=CASE_BASE[case(rid)]
    for term,cls,kind in c['terms']:
        if kind in ('gap','proposed','cvext') or cls=='(class)' or ' ' in term: continue
        if kind in ('minted','imported') and anywhere(v,term): problems.append((rid,term,cls,kind,'term exists in base '+v))
        if kind=='newclass' and (on(v,term,cls) or not anywhere(v,term)): problems.append((rid,term,cls,kind,'newclass claim wrong'))
        if kind in ('constrained','asis') and not on(v,term,cls): problems.append((rid,term,cls,kind,'not on class in base '+v))
print('claims checked; problems:',len(problems))
for p in problems: print(p)
# base-version sensitivity: which rows' new/expanded terms are in later DCAT-AP releases on the same class
later={'1.1.0':['2.0.1','2.1.1','3.0.0','3.0.1'],'2.0.1':['2.1.1','3.0.0','3.0.1'],'3.0.0':['3.0.1']}
print()
for rid,c in CODES.items():
    v=CASE_BASE[case(rid)]
    for term,cls,kind in c['terms']:
        if kind in ('imported','newclass'):
            hits=[w for w in later[v] if on(w,term,cls)]
            if hits: print('LATER BASE', rid, term, cls, kind, '-> on class in', hits[0], '(primary resp', c['resp'],')')
