import re, html, json, sys
s=open(sys.argv[1],encoding='utf-8').read()
s=re.sub(r'<script.*?</script>','',s,flags=re.S)
def txt(x):
    x=re.sub(r'<br\s*/?>','\n',x); x=re.sub(r'</p>','\n',x)
    x=re.sub(r'<[^>]+>','',x); x=html.unescape(x)
    return re.sub(r'[ \t]+',' ',x).strip()
# split into sections by h3/h4 headings with positions
heads=[(m.start(), m.group(1), txt(m.group(2))) for m in re.finditer(r'<(h[2-4])[^>]*>(.*?)</\1>', s, re.S)]
tables=[(m.start(), m.group(0)) for m in re.finditer(r'<table.*?</table>', s, re.S)]
rows_out=[]
for pos, t in tables:
    # nearest preceding h3 and h4
    h3=[h for h in heads if h[0]<pos and h[1]=='h3']; h4=[h for h in heads if h[0]<pos and h[1]=='h4']
    h3=h3[-1][2] if h3 else ''; h4c=h4[-1] if h4 else None
    h4=h4c[2] if h4c and (not h3 or h4c[0]> [h for h in heads if h[0]<pos and h[1]=='h3'][-1][0]) else ''
    trs=re.findall(r'<tr.*?</tr>', t, re.S)
    hdr=[txt(c) for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', trs[0], re.S)] if trs else []
    if 'URI' not in hdr: continue
    for tr in trs[1:]:
        cells=[txt(c) for c in re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', tr, re.S)]
        if len(cells)!=len(hdr): continue
        rows_out.append(dict(section=h3, sub=h4, **{hdr[i]:cells[i] for i in range(len(hdr))}))
json.dump(rows_out, open(sys.argv[2],'w'), indent=1, ensure_ascii=False)
print(len(rows_out))
for r in rows_out:
    print(r['section'][:30],'|',r['sub'][:45],'|',r.get('Property','')[:40],'|',r.get('URI',''),'|',r.get('Range','')[:40],'|',r.get('Card.',''))
