# -*- coding: utf-8 -*-
"""317 萨索洛 2:4（6球）归因：市场没反映出极大球？还是我没分析出市场信号？
判据：
  ① 市场对「6 球」定价多少（goal_bins_table 1.50-1.70 档拆解）
  ② 历史上该档实际打出 6 球的频率（Matches.csv 21,724 场）
  ③ 若实际 >> 市场隐含 → 市场系统性低估尾部（市场信号不准）
     若实际 ≈ 市场隐含 → 市场准，6 球是单场方差（不可预测）
  ④ 若实际 6 球与「市场大球强」高度相关 → 我没做条件化（我的错）
"""
import csv, io, sys, os
from collections import Counter
sys.path.insert(0, 'data/tmp')
sys.stdout.reconfigure(encoding='utf-8')

CSV = 'data/Matches.csv'
if not os.path.exists(CSV):
    print('❌ 缺 Matches.csv'); sys.exit(1)

rows = []
with io.open(CSV, encoding='utf-8', errors='ignore') as f:
    rd = csv.DictReader(f)
    cols = rd.fieldnames or []
    need = [c for c in ('FTHome', 'FTAway', 'Over25') if c in cols]
    print('列存在:', need)
    for r in rd:
        try:
            h = int(float(r['FTHome'])); a = int(float(r['FTAway']))
            o25 = float(r['Over25'])
        except (ValueError, TypeError, KeyError):
            continue
        if o25 <= 1.0 or o25 > 20:
            continue
        rows.append((o25, h + a))

print('有效场次:', len(rows))

BANDS = [('1.00-1.30', 1.00, 1.30), ('1.30-1.50', 1.30, 1.50), ('1.50-1.70', 1.50, 1.70),
         ('1.70-1.90', 1.70, 1.90), ('1.90-2.10', 1.90, 2.10), ('2.10-2.30', 2.10, 2.30)]
print('\n=== ① 历史实际总进球分布 vs 市场查表（goal_bins_table）===')
try:
    import json
    T = json.load(io.open('data/tmp/goal_bins_table.json', encoding='utf-8'))
except Exception:
    T = {}

print('%-10s %-7s %-8s %-8s %-8s %-8s %-8s %-8s' %
      ('O2.5档', 'n', '均球', 'P(4球)', 'P(5球)', 'P(6球)', 'P(7+球)', 'P(≥6球)'))
for name, lo, hi in BANDS:
    sub = [t for o, t in rows if lo <= o < hi]
    if len(sub) < 300:
        continue
    c = Counter(sub)
    n = len(sub)
    mean = sum(sub) / n
    p4, p5, p6 = [c.get(k, 0) / n * 100 for k in (4, 5, 6)]
    p7p = sum(c.get(k, 0) for k in range(7, 15)) / n * 100
    p6p = p6 + p7p
    tb = T.get(name) or {}
    t_g4 = tb.get('g4')
    print('%-10s %-7d %-8.2f %-8.1f %-8.1f %-8.1f %-8.1f %-8.1f%s' %
          (name, n, mean, p4, p5, p6, p7p, p6p,
           ('  ← 表 g4(≥4球)=%.1f%%' % t_g4) if t_g4 else ''))

print('\n=== ② 1.50-1.70 档（=317 本场）尾部逐球：实际 vs 泊松 λ=3.5 拆解 ===')
sub = [t for o, t in rows if 1.50 <= o < 1.70]
c = Counter(sub); n = len(sub)
import math
L = 3.5
pois = [math.exp(-L) * L ** k / math.factorial(k) for k in range(8)]
g4 = 0.364                     # 表 g4
tail = [pois[4], pois[5], pois[6], pois[7]]
ts = sum(tail)
tab = [g4 * x / ts for x in tail]      # 表拆解后的 4/5/6/7+ 隐含
print('%-6s %-10s %-10s %-10s' % ('总球', '实际%', '表隐含%', '差(pp)'))
for k in (4, 5, 6):
    act = c.get(k, 0) / n * 100
    imp = tab[k - 4] * 100
    print('%-6d %-10.1f %-10.1f %+-10.1f' % (k, act, imp, act - imp))
act7 = sum(c.get(k, 0) for k in range(7, 15)) / n * 100
print('%-6s %-10.1f %-10.1f %+-10.1f' % ('7+', act7, tab[3] * 100, act7 - tab[3] * 100))

print('\n=== ③ 关键：市场「大球强」档里，6 球到底占多少 ===')
for name, lo, hi in [('≤1.40（超大球）', 1.0, 1.40), ('1.40-1.50', 1.40, 1.50),
                     ('1.50-1.70', 1.50, 1.70), ('1.70-1.90', 1.70, 1.90)]:
    sub = [t for o, t in rows if lo <= o < hi]
    if len(sub) < 200:
        print('%-16s n=%d 样本不足' % (name, len(sub))); continue
    c = Counter(sub); n = len(sub)
    p6p = sum(c.get(k, 0) for k in range(6, 15)) / n * 100
    p4p = sum(c.get(k, 0) for k in range(4, 15)) / n * 100
    print('%-16s n=%-6d  均球 %.2f ｜ P(≥4球) %5.1f%% ｜ **P(≥6球) %5.1f%%** ｜ 实际出现 6+ 球占该档 1/%.0f'
          % (name, n, sum(sub) / n, p4p, p6p, 100 / p6p if p6p else 0))
