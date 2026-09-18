# -*- coding: utf-8 -*-
"""深挖2：组合信号（盘口×赔率 / 首回合×盘口 / 穿盘 / 均势盘·可固化铁则候选）"""
import io, sys, csv, collections, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
rows = list(csv.DictReader(open('data/europe/欧战全量.csv', encoding='utf-8-sig')))

def norm_hc(hc):
    hc = hc.replace(' ', '')
    sign = -1 if '受' in hc else 1
    hc = hc.replace('受', '')
    grade = {'平手': 0, '平/半': 0.25, '平半': 0.25, '半球': 0.5, '半/一': 0.75, '半球/一球': 0.75,
             '一球': 1.0, '一/球半': 1.25, '一球/球半': 1.25, '球半': 1.5, '球半/两': 1.75,
             '两球': 2.0, '两/两半': 2.25, '两半': 2.5, '三球': 3.0}
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
        oh, od, oa = float(r['odd99_h']), float(r['odd99_d']), float(r['odd99_a'])
        g = norm_hc(r['handi_hc'])
        if oh > 0 and od > 0 and oa > 0 and g is not None:
            valid.append((r, h, a, oh, od, oa, g))
    except Exception:
        pass
print(f"有效(赔率+盘口): {len(valid)}")

# 1. 组合：让球盘 ≥1.5 且 主胜赔率<1.6（双确认超深）→ 主胜率
print("=== 组合：让球盘深度 × 主胜赔率 → 主胜率 ===")
combos = [
    ('让≥1.5球 + 主赔<1.6', lambda oh, g: g >= 1.5 and oh < 1.6),
    ('让≥1.5球 + 主赔<1.4', lambda oh, g: g >= 1.5 and oh < 1.4),
    ('让≥1球 + 主赔<1.5', lambda oh, g: g >= 1.0 and oh < 1.5),
    ('受让 + 主赔>2.5(主队受让深+高赔)', lambda oh, g: g < 0 and oh > 2.5),
]
for name, fn in combos:
    sub = [(r, h, a) for r, h, a, oh, od, oa, g in valid if fn(oh, g)]
    if len(sub) < 10: continue
    n = len(sub)
    hw = sum(1 for _, x, y in sub if x > y)
    d = sum(1 for _, x, y in sub if x == y)
    print(f"  {name} (n={n}): 主胜{100*hw/n:.0f}% 平{100*d/n:.0f}%")

# 2. 穿盘（panlu 字段：赢/输/走）
print("\n=== 穿盘统计（panlu） ===")
pl = collections.Counter(r['panlu'] for r, *_ in valid)
for k, v in pl.most_common(6):
    print(f"  {k}: {v} ({100*v/len(valid):.0f}%)")

# 3. 均势盘（主客隐含差距<6pp·修正32欧战）→ 平局率
print("\n=== 均势盘（|主隐含-客隐含|<6pp）→ 平局率 ===")
def vf(oh, od, oa):
    inv = 1/oh + 1/od + 1/oa
    return (1/oh)/inv, (1/od)/inv, (1/oa)/inv
for lo, hi, name in [(0, 3, '差距<3pp(极限均势)'), (3, 6, '差距3-6pp'), (6, 12, '差距6-12pp'), (12, 99, '差距>12pp')]:
    sub = []
    for r, h, a, oh, od, oa, g in valid:
        ph, pd, pa = vf(oh, od, oa)
        gap = abs(ph - pa)
        if lo <= gap < hi:
            sub.append((r, h, a))
    if len(sub) < 10: continue
    n = len(sub)
    d = sum(1 for _, x, y in sub if x == y)
    h = sum(1 for _, x, y in sub if x > y)
    print(f"  {name} (n={n}): 平局{100*d/n:.0f}% 主胜{100*h/n:.0f}% 客胜{100*(n-h-d)/n:.0f}%")

# 4. 客胜赔率档 → 客队净胜球（客队大胜特征·修正34）
print("\n=== 客胜赔率档 → 客队净胜 ===")
for lo, hi, name in [(0, 2.0, '<2.0'), (2.0, 2.5, '2.0-2.5'), (2.5, 3.5, '2.5-3.5'), (3.5, 99, '>3.5')]:
    sub = [(r, x, y) for r, x, y, oh, od, oa, g in valid if lo <= oa < hi]
    if len(sub) < 10: continue
    n = len(sub)
    aw = sum(1 for _, x, y in sub if x < y)
    # 客胜净胜球
    ns = collections.Counter()
    for _, x, y in sub:
        if x < y: ns[min(y-x, 3)] += 1
    ns_str = ' '.join(f"{k}球{100*v/max(1,sum(ns.values())):.0f}%" for k, v in sorted(ns.items()))
    print(f"  {name}(n={n}): 客胜{100*aw/n:.0f}% · 客胜净胜[{ns_str}]")

# 5. 首回合×盘口：首回合主胜方次回合盘口
print("\n=== 首回合结果 × 次回合盘口（配对·组合规律） ===")
def dt(d):
    p = d.split('-'); y = int(p[0])+2000 if int(p[0])<100 else int(p[0])
    return datetime.date(y, int(p[1]), int(p[2]))
by_key = {}
for r, h, a, oh, od, oa, g in valid:
    by_key[(r['home'], r['away'], r['date'])] = (r, h, a, g)
pairs = []
for r1, h1, a1, oh1, od1, oa1, g1 in valid:
    # 找次回合（主客互换）
    for r2, h2, a2, oh2, od2, oa2, g2 in valid:
        if r1['home'] == r2['away'] and r1['away'] == r2['home']:
            try:
                d1, d2 = dt(r1['date']), dt(r2['date'])
                if 3 <= abs((d2-d1).days) <= 14 and r1['date'] < r2['date']:
                    pairs.append(((r1, h1, a1, g1), (r2, h2, a2, g2)))
            except Exception:
                pass
print(f"配对: {len(pairs)}")
for label, fn in [('首回合主胜', lambda s: s[0] > s[1]), ('首回合客胜', lambda s: s[0] < s[1])]:
    sub = [(f, s) for f, s in pairs if fn(f[1])]
    if not sub: continue
    n = len(sub)
    # 次回合盘口（主队=首回合客队）
    g2 = collections.Counter()
    for _, s in sub:
        g = s[3]
        g2['让' if g > 0 else ('受' if g < 0 else '平手')] += 1
    print(f"  {label}(n={n}): 次回合盘口分布 " + ' '.join(f"{k}{100*v/n:.0f}%" for k, v in g2.most_common(4)))
