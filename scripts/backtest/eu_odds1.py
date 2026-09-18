# -*- coding: utf-8 -*-
"""欧战赔率底层逻辑回测1：99家终赔分档 → 方向/净胜球/总进球条件分布（修正50精算仓位口径）"""
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
print(f"有效(含终赔): {len(valid)}")

def vig_free(oh, od, oa):
    inv = 1/oh + 1/od + 1/oa
    return (1/oh)/inv, (1/od)/inv, (1/oa)/inv

# 1. 主胜赔率分档 → 主胜率/净胜球/大球
print("\n=== 主胜赔率分档 → 主胜率·净胜球·大球（修正50 精算仓位） ===")
buckets = [('<1.40', lambda o: o < 1.40), ('1.40-1.60', lambda o: 1.40 <= o < 1.60),
           ('1.60-1.80', lambda o: 1.60 <= o < 1.80), ('1.80-2.10', lambda o: 1.80 <= o < 2.10),
           ('2.10-2.60', lambda o: 2.10 <= o < 2.60), ('>2.60', lambda o: o >= 2.60)]
for name, fn in buckets:
    sub = [(r, h, a, oh) for r, h, a, oh, od, oa in valid if fn(oh)]
    if len(sub) < 10: continue
    n = len(sub)
    hw = sum(1 for _, x, y, _ in sub if x > y)
    # 净胜球（主胜时）
    ns = collections.Counter()
    for _, x, y, _ in sub:
        if x > y: ns[min(x-y, 3)] += 1
    o3 = sum(1 for _, x, y, _ in sub if x + y >= 3)
    avg = sum(x + y for _, x, y, _ in sub) / n
    imp = 1/ (sum(1/oh for _, _, _, oh in sub) / n)  # 平均隐含
    ns_str = ' '.join(f"{k}球{100*v/max(1,sum(ns.values())):.0f}%" for k, v in sorted(ns.items()))
    print(f"  {name}(n={n}): 主胜{100*hw/n:.0f}% · 主胜净胜[{ns_str}] · 大球{100*o3/n:.0f}% · 场均{avg:.2f}")

# 2. 客胜赔率分档 → 客胜率（修正34 客胜方向）
print("\n=== 客胜赔率分档 → 客胜率 ===")
ab = [('<2.0', lambda o: o < 2.0), ('2.0-2.5', lambda o: 2.0 <= o < 2.5),
      ('2.5-3.0', lambda o: 2.5 <= o < 3.0), ('3.0-4.0', lambda o: 3.0 <= o < 4.0), ('>4.0', lambda o: o >= 4.0)]
for name, fn in ab:
    sub = [(r, h, a, oa) for r, h, a, oh, od, oa in valid if fn(oa)]
    if len(sub) < 10: continue
    n = len(sub)
    aw = sum(1 for _, x, y, _ in sub if x < y)
    print(f"  {name}(n={n}): 客胜{100*aw/n:.0f}%")

# 3. 主胜赔率档 → 主胜比分分布（结合比分深度修正43/50+）
print("\n=== 主胜赔率档 → 主胜比分 Top（比分深度） ===")
for name, fn in [('<1.50', lambda o: o < 1.50), ('1.50-1.80', lambda o: 1.50 <= o < 1.80),
                 ('1.80-2.30', lambda o: 1.80 <= o < 2.30), ('>2.30', lambda o: o >= 2.30)]:
    sub = [(r, h, a) for r, h, a, oh, od, oa in valid if fn(oh)]
    if len(sub) < 10: continue
    n = len(sub)
    sc = collections.Counter(f"{x}:{y}" for _, x, y in sub if x > y)
    top = sc.most_common(4)
    print(f"  {name}(n={n}·主胜{len(sc)}): " + ' '.join(f"{k}={100*v/max(1,sum(sc.values())):.0f}%" for k, v in top))

# 4. 平赔档 → 平局比分（观察项A 欧战口径）
print("\n=== 平赔档 → 平局比分 Top ===")
for name, fn in [('<3.2', lambda o: o < 3.2), ('3.2-3.6', lambda o: 3.2 <= o < 3.6), ('>3.6', lambda o: o >= 3.6)]:
    sub = [(r, h, a) for r, h, a, oh, od, oa in valid if fn(od)]
    if len(sub) < 10: continue
    n = len(sub)
    sc = collections.Counter(f"{x}:{y}" for _, x, y in sub if x == y)
    top = sc.most_common(3)
    print(f"  {name}(n={n}·平局{len(sc)}): " + ' '.join(f"{k}={100*v/max(1,sum(sc.values())):.0f}%" for k, v in top))
