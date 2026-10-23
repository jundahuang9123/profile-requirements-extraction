"""Extract text from every allowlisted runtime input (raw + consolidation + background) for evidence labelling."""
import json, os, subprocess, re
from bs4 import BeautifulSoup
BD = '/home/claude/jundahuang9123/profile-requirements-extraction/benchmark-data'
OUT = '/home/claude/merge/inputs'
allow = json.load(open(f'{BD}/runtime-inputs.json'))['benchmarks']
manifest = {}
for case, cfg in allow.items():
    for role in ('raw', 'consolidation', 'background'):
        for rel in cfg.get(role, []) or []:
            src = f'{BD}/{rel}'
            dst = f'{OUT}/{rel}.txt'
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if rel.endswith('.pdf'):
                txt = subprocess.run(['pdftotext', '-layout', src, '-'], capture_output=True, text=True).stdout
                pages = txt.split('\f')
                txt = ''.join(f'\n=== [page {i}] ===\n{p}' for i, p in enumerate(pages, start=1) if p.strip())
            elif rel.endswith('.html'):
                soup = BeautifulSoup(open(src, encoding='utf-8', errors='replace').read(), 'lxml')
                for t in soup(['script', 'style', 'nav', 'header', 'footer']):
                    t.decompose()
                txt = soup.get_text('\n')
                txt = re.sub(r'\n\s*\n+', '\n\n', txt)
            elif rel.endswith('.json'):
                txt = json.dumps(json.load(open(src, encoding='utf-8')), indent=1, ensure_ascii=False)
            else:
                txt = open(src, encoding='utf-8', errors='replace').read()
            open(dst, 'w', encoding='utf-8').write(txt)
            manifest.setdefault(case, {}).setdefault(role, []).append(dict(path=rel, text=dst, chars=len(txt)))
json.dump(manifest, open(f'{OUT}/manifest.json', 'w'), indent=1)
for case, roles in manifest.items():
    for role, docs in roles.items():
        print(case, role, [(os.path.basename(d['path']), d['chars']) for d in docs])
