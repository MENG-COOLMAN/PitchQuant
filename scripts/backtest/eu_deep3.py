# -*- coding: utf-8 -*-
"""首回合×次回合盘口（显式索引）"""
import io, sys, csv, collections, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
rows = list(csv.DictReader(open('data/europe/欧战全量.csv', encoding='utf-8-sig')))

def norm_hc(hc):
    hc = hc.replace(' ', '')
    sign = -1 if '受' in hc else 1
    hc = hc.replace('受', '')
    grade = {'平手': 0, '平/半': 0.25, '平半': 0.25, '半球': 0.5, '半/一': 0.75, '一球': 1.0,
             '一/球半': 1.25, '一球/球半': 1.25, '球半': 1.5, '球半/两': 1.75, '两球': 2.0}
    for g, v in grade.items():
        if g in hc: return sign * v
    if '/' in hc:
        parts = hc.split('/')
        if len(parts) == 2:
            v1, v2 = grade.get(parts[0], 0), grade.get(parts[1], 0)
            if v1 or v2: return sign * (v1 + v2) / 2
    return None

valid = []
for r in rows:
    try:
        h, a = map(int, r['score'].split(':'))
        g = norm_hc(r['handi_hc'])
        if float(r['odd99_h']) > 0 and g is not None:
            valid.append((r['home'], r['away'], r['date'], h, a, g))
    except Exception:
        pass

def dt(d):
    p = d.split('-'); y = int(p[0])+2000 if int(p[0])<100 else int(p[0])
    return datetime.date(y, int(p[1]), int(p[2]))

pairs = []
used = set()
for i, (hn, an, da, h, a, g) in enumerate(valid):
    for j in range(i+1, len(valid)):
        hn2, an2, da2, h2, a2, g2 = valid[j]
        if hn == an2 and an == hn2:
            try:
                d1, d2 = dt(da), dt(da2)
                if 3 <= abs((d2-d1).days) <= 14 and (i, j) not in used:
                    used.add((i, j))
                    f, s = (hn, an, h, a, g), (hn2, an2, h2, a2, g2)
                    if da > da2: f, s = s, f
                    pairs.append((f, s))
            except Exception:
                pass
print(f"配对: {len(pairs)}")

for label, cond in [('首回合主胜', lambda h, a: h > a), ('首回合客胜', lambda h, a: h < a),
                    ('首回合平局', lambda h, a: h == a)]:
    sub = [(f, s) for f, s in pairs if cond(f[2], f[3])]
    if not sub: continue
    n = len(sub)
    g2 = collections.Counter()
    hw = d = 0
    for f, s in sub:
        g = s[4]
        g2['主让' if g > 0 else ('主受' if g < 0 else '平手')] += 1
        if s[2] > s[3]: hw += 1
        elif s[2] == s[3]: d += 1
    print(f"{label}(n={n}): 次回合盘口 " + ' '.join(f"{k}{100*v/n:.0f}%" for k, v in g2.most_common(4)))
    print(f"  → 次回合主队: 胜{100*hw/n:.0f}% 平{100*d/n:.0f}% 负{100*(n-hw-d)/n:.0f}%")
