"""Rebuild the two static manuscript figures: python build_figures.py (ReportLab)."""
from pathlib import Path
import json, math, hashlib
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon
from reportlab.graphics import renderPDF, renderSVG
from reportlab.lib.colors import HexColor, Color
from reportlab.pdfbase.pdfmetrics import stringWidth

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
INK='#172D3E'; MUTED='#526372'; RULE='#CCD5DC'
BLUE='#21618B'; TEAL='#16756C'; AMBER='#956114'
PALE_BLUE='#EDF5FA'; PALE_TEAL='#EDF7F3'; PALE_AMBER='#FCF5E8'; PALE='#F4F6F8'
checks=[]
def rect(d,x,y,w,h,fill='#FFFFFF',stroke=None,r=0):
    d.add(Rect(x,d.height-y-h,w,h,rx=r,ry=r,fillColor=HexColor(fill),strokeColor=HexColor(stroke) if stroke else None,strokeWidth=.7))
def txt(d,x,y,s,size=10,color=INK,bold=False,align='start'):
    font='Helvetica-Bold' if bold else 'Helvetica'
    d.add(String(x,d.height-y-size*.80,s,fontName=font,fontSize=size,fillColor=HexColor(color),textAnchor=align))
def lines(d,x,y,ss,size=10,color=INK,bold=False,leading=None,width=None):
    leading=leading or size*1.28
    if isinstance(ss,str): ss=ss.split('\n')
    for i,s in enumerate(ss):
        if width:
            measured=stringWidth(s,'Helvetica-Bold' if bold else 'Helvetica',size)
            checks.append({'text':s,'fits':measured<=width,'width':round(measured,2),'available':width})
        txt(d,x,y+i*leading,s,size,color,bold)
    return y+len(ss)*leading

def line(d,x1,y1,x2,y2,color=RULE,dash=None,width=.8):
    o=Line(x1,d.height-y1,x2,d.height-y2,strokeColor=HexColor(color),strokeWidth=width)
    if dash:o.strokeDashArray=dash
    d.add(o)
def arrow(d,x1,y1,x2,y2,color=INK,dash=None):
    line(d,x1,y1,x2,y2,color,dash,1)
    a=math.atan2(y2-y1,x2-x1); n=5
    pts=[x2,d.height-y2,x2-n*math.cos(a)+2.3*math.sin(a),d.height-(y2-n*math.sin(a)-2.3*math.cos(a)),x2-n*math.cos(a)-2.3*math.sin(a),d.height-(y2-n*math.sin(a)+2.3*math.cos(a))]
    d.add(Polygon(pts,fillColor=HexColor(color),strokeColor=None))
def box(d,x,y,w,h,title,body,c=BLUE,bg=PALE_BLUE):
    rect(d,x,y,w,h,bg,r=5); rect(d,x,y,3,h,c)
    txt(d,x+12,y+11,title,11,c,True)
    lines(d,x+12,y+30,body,10,leading=13,width=w-24)
def save(d,name,title):
    renderPDF.drawToFile(d,str(OUT/(name+'.pdf')),title=title,author='RQ1 benchmark corpus')
    renderSVG.drawToFile(d,str(OUT/(name+'.svg')))

allow=json.loads((ROOT/'runtime-inputs.json').read_text())['benchmarks']
counts={c:{k:len(v) for k,v in modes.items()} for c,modes in allow.items()}
refs={
 'mobilitydcat':('reference-requirements/consolidated-requirements.json','requirements'),
 'healthdcat':('reference-requirements/curated-requirements.json','requirements'),
 'statdcat':('reference-requirements/requirements-and-resolutions.json','requirements'),
 'geodcat':('reference-requirements/alignment-requirements.json','requirements'),
 'jrc-research':('reference-requirements/core-requirements.json','requirements')}
for c,(f,k) in refs.items():
 data=json.loads((ROOT/c/f).read_text()); counts[c]['reference_entries']=len(data[k])
assert [counts[c]['raw'] for c in ['mobilitydcat','healthdcat','statdcat','geodcat','jrc-research','epos']]==[17,5,2,5,3,0]
assert [counts[c]['reference_entries'] for c in ['mobilitydcat','healthdcat','statdcat','geodcat','jrc-research']]==[40,16,7,7,5]
assert len(json.loads((ROOT/'healthdcat/input-preconsolidation/twg-observations.json').read_text())['observations'])==8
assert len(json.loads((ROOT/'mobilitydcat/input-preconsolidation/partner-requirements.json').read_text())['candidates'])==60

# Figure 1: workflow plus corpus matrix, composed at double-column proportions.
d=Drawing(720,615)
rect(d,0,0,720,615)
txt(d,18,15,'DCAT extension benchmarks: evidence and reference layers',17,INK,True)
txt(d,18,40,'Historical snapshot: 7 October 2026  |  All six reconstructed corpora are partial',10,MUTED)
txt(d,18,65,'a',12,INK,True);txt(d,36,65,'Two evaluation entry points',12,INK,True)
box(d,18,87,172,67,'A  Raw evidence',['Standards, policy, landscape','reports and source synopses'])
box(d,18,164,172,67,'B  Preconsolidation',['Partner requirements and','curated workshop observations'],TEAL,PALE_TEAL)
box(d,230,87,166,67,'Full workflow',['Extract, normalize, consolidate','and review requirements'],BLUE,PALE)
box(d,230,164,166,67,'Later workflow stages',['Normalize, consolidate','and review requirements'],TEAL,PALE)
arrow(d,191,120,228,120,BLUE);arrow(d,191,197,228,197,TEAL)
rect(d,427,96,109,123,PALE,r=5)
lines(d,439,111,['Predicted','requirements'],11,INK,True,width=87)
lines(d,439,150,['Separate outputs','for A and B runs'],9.6,MUTED,width=87)
arrow(d,398,120,425,120,BLUE);arrow(d,398,197,425,197,TEAL)
line(d,553,86,553,246,AMBER,[3,3])
box(d,574,87,128,67,'C  References',['Published requirement','rows / curated subsets'],AMBER,PALE_AMBER)
box(d,574,183,128,61,'Semantic matching',['Coverage, meaning,','novel supported needs'],AMBER,PALE_AMBER)
arrow(d,638,155,638,181,AMBER);arrow(d,538,211,572,211,INK)
txt(d,632,163,'Evaluator only',8.8,AMBER,True,'end')
txt(d,18,245,'A and B are separate runs; reference requirements and target profiles never enter runtime inputs.',9.7,MUTED)

txt(d,18,273,'b',12,INK,True);txt(d,36,273,'What is available in this snapshot',12,INK,True)
cols=[18,147,346,508,702]
rect(d,18,296,684,30,INK)
for x,s in [(27,'Benchmark'),(156,'A  Raw inputs'),(355,'B  Preconsolidation'),(517,'C  Reference scope')]:txt(d,x,305,s,10,'#FFFFFF',True)
rows=[
('mobilityDCAT-AP','Primary case',['17 files: policy, DCAT/INSPIRE,','FAIR, SPRINT and CMC'],['3 files: 60 partner rows','+ review / expert observations'],['40 published Table 1 rows','All IDs; curator paraphrases']),
('HealthDCAT-AP','Heterogeneous sources',['5 files: landscape analysis,','EHDS proposal, GDPR, DCAT'],['1 file: 8 curated TWG','observations; partial subset'],['16 curated rationale entries','Original D6.2 also retained']),
('StatDCAT-AP','Standards-derived',['2 files: DCAT and Data Cube','Use-case reconstruction excluded*'],['Unavailable'],['7 requirement / resolution pairs','Scoped selection from 2016 report']),
('GeoDCAT-AP','Standards alignment',['5 files: INSPIRE legislation,','public guidance and DCAT'],['Unavailable'],['7 curated alignment constraints','ISO standards are citation-only']),
('JRC research','Small sanity case',['3 files: data policy, DCAT,','DataCite field synopsis'],['Unavailable'],['5 enumerated core needs','Curator paraphrases']),
('EPOS-DCAT-AP','Exploratory only',['No scored raw run enabled','Public context is available'],['Unavailable'],['No reconstructed requirement set','Frozen specification + context'])]
for i,(name,kind,a,b,c) in enumerate(rows):
 y=326+i*38
 rect(d,18,y,684,38,'#FFFFFF' if i%2==0 else PALE)
 rect(d,147,y,199,38,PALE_BLUE)
 rect(d,346,y,162,38,PALE_TEAL if i<2 else '#F4F6F8')
 rect(d,508,y,194,38,PALE_AMBER if i<5 else '#F4F6F8')
 txt(d,27,y+6,name,10.2,INK,True);txt(d,27,y+21,kind,9.2,MUTED)
 lines(d,156,y+6,a,9.7,leading=13,width=185)
 lines(d,355,y+6,b,9.7,leading=13,width=149)
 lines(d,517,y+6,c,9.7,leading=13,width=180)
 line(d,18,y+38,702,y+38,'#DEE4E8',width=.5)
lines(d,18,566,[
 'Counts refer to allowlisted files in A/B and reference entries in C; they are not directly comparable.',
 '*StatDCAT use cases are available as a separate retrospective variant. Curated entries await independent review.',
 'Source: frozen corpus manifests, runtime allowlists and reference inventories. No workflow results are shown.'
],9.3,MUTED,leading=13,width=684)
save(d,'01-benchmark-evidence-map','DCAT benchmark evidence and reference layers')

# Figure 2: actual corpus content, with non-causal illustrative correspondences.
d=Drawing(720,542);rect(d,0,0,720,542)
txt(d,18,15,'Inside mobilityDCAT-AP: from source content to requirements',16,INK,True)
txt(d,18,40,'Selected corpus paraphrases; connectors show illustrative semantic correspondence',10,MUTED)
for x,w,t,sub,col,bg in [
 (18,218,'A  Raw-source content','SPRINT / CMC task and concept synopses',BLUE,PALE_BLUE),
 (262,218,'B  Partner requirements','NAPCORE Annex 1; national submissions',TEAL,PALE_TEAL),
 (506,196,'C  Consolidated references','NAPCORE Table 1',AMBER,PALE_AMBER)]:
 rect(d,x,67,w,45,bg,r=4);txt(d,x+10,77,t,11,col,True);txt(d,x+10,96,sub,8.8,MUTED)

# Theme 1
for x,w,bg in [(18,218,PALE_BLUE),(262,218,PALE_TEAL),(506,196,PALE_AMBER)]:rect(d,x,125,w,121,bg,r=4)
txt(d,28,136,'VALIDITY PERIOD',9,BLUE,True)
txt(d,28,156,'SPRINT CQ-9',10,INK,True)
lines(d,28,172,['Retrieve the beginning and end','of a dataset validity interval.'],10.2,width=197)
lines(d,28,205,['CMC-12 / CMC-13','Validity beginning / validity end'],9.8,MUTED,leading=14,width=197)
txt(d,272,136,'IT-17',10,TEAL,True)
lines(d,272,160,['Describe the interval in which','published data remain valid.'],10.5,width=197)
txt(d,272,220,'Original Italian row: Req-17',9.2,MUTED)
txt(d,516,136,'Req-22  |  mandatory',10,AMBER,True)
lines(d,516,160,['Represent the interval over','which the published data','remain valid.'],10.5,width=176)

# Theme 2
for x,w,bg in [(18,218,PALE_BLUE),(262,218,PALE_TEAL),(506,196,PALE_AMBER)]:rect(d,x,261,w,121,bg,r=4)
txt(d,28,272,'LICENSING AND CONDITIONS',9,BLUE,True)
txt(d,28,292,'SPRINT CQ-11',10,INK,True)
lines(d,28,308,['Determine the licence governing','use of a dataset.'],10.2,width=197)
lines(d,28,341,['CMC-20 / CMC-21','Licence/contract; other use conditions'],9.8,MUTED,leading=14,width=197)
txt(d,272,272,'IT-21',10,TEAL,True)
lines(d,272,296,['Describe contracts, licences','and other use conditions.'],10.5,width=197)
txt(d,272,356,'Original Italian row: Req-21',9.2,MUTED)
txt(d,516,272,'Req-27  |  mandatory',10,AMBER,True)
lines(d,516,296,['Describe contractual, licensing','and other conditions on','data use.'],10.5,width=176)
for y in [186,321]:
 line(d,238,y,260,y,MUTED,[2,3],1.2);line(d,482,y,504,y,MUTED,[2,3],1.2)

# Many-to-one example with genuine partner statements, no invented predictions.
rect(d,18,397,684,90,PALE,r=4)
txt(d,28,407,'ILLUSTRATIVE MANY-TO-ONE MATCH',9,MUTED,True)
lines(d,28,428,['BE-02: record applicable NAP regulatory categories.',
 'GR-01: associate datasets with ITS delegated regulations.'],10.1,leading=18,width=358)
line(d,389,446,452,446,MUTED,[2,3],1.2)
txt(d,462,425,'Req-20  |  mandatory',10,AMBER,True)
lines(d,462,443,['Indicate which ITS delegated regulations','apply to a resource.'],10.1,width=229)
lines(d,18,500,[
 'These are source and reference excerpts, not predictions or measured workflow results. Wording is paraphrased.',
 'The thematic links are curator interpretations, not verified historical derivations or adjudicated evaluation labels.'
],9.4,MUTED,leading=14,width=684)
save(d,'02-mobility-requirement-examples','MobilityDCAT source and requirement examples')

fail=[c for c in checks if not c['fits']]
(OUT/'figure-data.json').write_text(json.dumps({'corpus_snapshot':'2026-10-07','runtime_file_counts':counts,'example_reference_ids':['Req-22','Req-27','Req-20'],'link_status':'illustrative_curator_interpretation_not_adjudicated','text_width_checks':len(checks),'text_overflow':fail},indent=2)+'\n')
assert not fail,fail
print('Wrote 2 vector PDFs, 2 editable SVGs and figure-data.json; all text-width checks passed.')
