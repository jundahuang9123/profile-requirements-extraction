import re, sys
def norm(s):
    s = (s.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
         .replace(' ', ' ').replace('‑', '-').replace('­', ''))
    return re.sub(r'\s+', ' ', s).strip()
SRC = {'health': ['d6.2-requirements-and-profile.txt', 'd62-raw.txt'], 'stat': ['stat-final.txt', 'stat-raw.txt'],
       'geo': ['geo-final.txt', 'geo-raw.txt']}
_cache = {}
def texts(case):
    if case not in _cache:
        ts = [norm(open('/home/claude/analysis/' + f, encoding='utf-8').read()) for f in SRC[case]]
        ts += [t.replace('- ', '-') for t in ts]
        _cache[case] = ts
    return _cache[case]
def found(case, anchor):
    a = norm(anchor)
    return any(a in t for t in texts(case))
def ctx(case, anchor, before=300, after=500):
    a = norm(anchor)
    for t in texts(case):
        i = t.find(a)
        if i >= 0:
            return t[max(0, i - before): i + len(a) + after]
    return None
if __name__ == '__main__':
    case = sys.argv[1]
    for a in sys.argv[2:]:
        print('===', a, '->', found(case, a)); print(ctx(case, a))
