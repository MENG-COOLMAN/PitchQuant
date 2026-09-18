# -*- coding: utf-8 -*-
"""欧战赔率底层逻辑回测2：隐含概率 vs 实际（定价偏差·价值信号）+ 精算仓位组合"""
import io, sys, csv, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

rows = list(csv.DictReader(open('data/europe/欧战全量.csv', encoding='utf-8-sig')))
valid = []
for r in rows:
    try:
        h, a = map(int, r['score'].split(':'))
        oh, od, oa = float(r['odd99_h']), float(r['odd99_d']), float(r['odd99_a'])
        if oh > 0 and od > 0 and oa > 0:
            valid.append((r, h, a, oh, od, oa))
    except Exception:
        pass
print(f"有效: {len(valid)}")

def vig(oh, od, oa):
    inv = 1/oh + 1/od + 1/oa
    return (1/oh)/inv, (1/od)/inv, (1/oa)/inv

# 1. 隐含概率 vs 实际（定价偏差·分档）
print("=== 主胜隐含概率 → 实际主胜率（定价偏差·找价值区间） ===")
for lo, hi, name in [(0.30,0.45,'30-45%'), (0.45,0.55,'45-55%'), (0.55,0.65,'55-65%'),
                     (0.65,0.75,'65-75%'), (0.75,1.0,'>75%')]:
    sub = [(r,h,a,oh,od,oa) for r,h,a,oh,od,oa in valid if lo <= vig(oh,od,oa)[0] < hi]
    if len(sub) < 10: continue
    n = len(sub)
    hw = sum(1 for _,x,y,_,_,_ in sub if x > y)
    mid = (lo+hi)/2
    print(f"  隐含{name}: 实际主胜{100*hw/n:.0f}% · 偏差{100*hw/n-mid*100:+.1f}pp (n={n})")

# 2. 客胜隐含 → 实际客胜率
print("\n=== 客胜隐含概率 → 实际客胜率 ===")
for lo, hi, name in [(0.20,0.30,'20-30%'), (0.30,0.40,'30-40%'), (0.40,0.55,'40-55%'), (0.55,1.0,'>55%')]:
    sub = [(r,h,a,oh,od,oa) for r,h,a,oh,od,oa in valid if lo <= vig(oh,od,oa)[2] < hi]
    if len(sub) < 10: continue
    n = len(sub)
    aw = sum(1 for _,x,y,_,_,_ in sub if x < y)
    mid = (lo+hi)/2
    print(f"  隐含{name}: 实际客胜{100*aw/n:.0f}% · 偏差{100*aw/n-mid*100:+.1f}pp (n={n})")

# 3. 平局隐含 → 实际平局率
print("\n=== 平局隐含概率 → 实际平局率 ===")
for lo, hi, name in [(0.20,0.25,'20-25%'), (0.25,0.30,'25-30%'), (0.30,0.35,'30-35%'), (0.35,1.0,'>35%')]:
    sub = [(r,h,a,oh,od,oa) for r,h,a,oh,od,oa in valid if lo <= vig(oh,od,oa)[1] < hi]
    if len(sub) < 10: continue
    n = len(sub)
    dw = sum(1 for _,x,y,_,_,_ in sub if x == y)
    mid = (lo+hi)/2
    print(f"  隐含{name}: 实际平局{100*dw/n:.0f}% · 偏差{100*dw/n-mid*100:+.1f}pp (n={n})")

# 4. 组合：主胜隐含≥60% + 客胜隐含≥25%（势均力敌 vs 一边倒）→ 平局率
print("\n=== 组合信号：势均力敌 → 平局率 ===")
combos = [
    ('主隐含45-60% + 客隐含25-40%(均势)', lambda h, d, a: 0.45 <= vig(h,d,a)[0] < 0.60 and 0.25 <= vig(h,d,a)[2] < 0.40),
    ('主隐含<45% + 客隐含<25%(无热门)', lambda h, d, a: vig(h,d,a)[0] < 0.45 and vig(h,d,a)[2] < 0.25),
    ('主隐含>60%(一边倒主)', lambda h, d, a: vig(h,d,a)[0] > 0.60),
]
for name, fn in combos:
    sub = [(r,x,y,oh,od,oa) for r,x,y,oh,od,oa in valid if fn(oh,od,oa)]
    if len(sub) < 10: continue
    n = len(sub)
    d = sum(1 for _,x,y,_,_,_ in sub if x == y)
    h = sum(1 for _,x,y,_,_,_ in sub if x > y)
    print(f"  {name} (n={n}): 平局{100*d/n:.0f}% · 主胜{100*h/n:.0f}%")

# 5. 精算仓位组合：主胜赔率档 × 大球（O3.5 隐含）—— 用总进球分布近似
print("\n=== 主胜档 × 比分深度（结合盈亏矩阵·2球/3球/4球） ===")
for name, fn in [('<1.50', lambda o: o < 1.50), ('1.50-1.80', lambda o: 1.50 <= o < 1.80),
                 ('1.80-2.30', lambda o: 1.80 <= o < 2.30), ('>2.30', lambda o: o >= 2.30)]:
    sub = [(r,x,y) for r,x,y,oh,od,oa in valid if fn(oh)]
    if len(sub) < 10: continue
    n = len(sub)
    tg = collections.Counter(x+y for _,x,y in sub)
    print(f"  {name}(n={n}): " + ' '.join(f"{k}球{100*tg[k]/n:.0f}%" for k in sorted(tg) if tg[k]/n >= 0.08))
