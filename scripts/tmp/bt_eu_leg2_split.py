# -*- coding: utf-8 -*-
"""分赛事对比: 欧冠/欧联/欧协联 次回合关键规律差异确认"""
import csv, collections, re, os, sys

# GBK 控制台防护
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bt_eu_leg2 import load_csv, pair_legs, outcome, total_goals, net_win, implied, pct

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'europe')

def analyze(pairs, tag):
    n = len(pairs)
    if n < 30:
        print(f"【{tag}】样本 {n} < 30 · 仅参考")
    L1, L2 = zip(*pairs)
    l2, l1 = list(L2), list(L1)
    tg2 = [total_goals(r) for r in l2]; tg1 = [total_goals(r) for r in l1]
    ov2 = sum(1 for t in tg2 if t >= 3); ov1 = sum(1 for t in tg1 if t >= 3)
    oc2 = collections.Counter(outcome(r) for r in l2)
    print(f"\n{'='*60}\n【{tag}】两回合组 n={n}")
    print(f"  次回合方向 H:{pct(oc2['H'],n)} D:{pct(oc2['D'],n)} A:{pct(oc2['A'],n)}")
    print(f"  总进球 次回合 {sum(tg2)/n:.2f}(O2.5 {pct(ov2,n)}) vs 首回合 {sum(tg1)/n:.2f}(O2.5 {pct(ov1,n)}) | 差 {sum(tg2)/n-sum(tg1)/n:+.2f}球")
    # 44B 领先方
    for k, name in [('A', '首回合客胜'), ('D', '首回合平局'), ('H', '首回合主胜')]:
        idxs = [i for i in range(n) if outcome(l1[i]) == k]
        if not idxs: continue
        oc = collections.Counter(outcome(l2[i]) for i in idxs)
        # 首回合客胜→次回合主队=首回合客队(回主场)·首回合主胜→次回合主队=首回合客队(做客)
        note = '→次回合回主场H' if k == 'A' else ('→次回合(双平)' if k == 'D' else '→次回合(做客方)')
        print(f"  {name}(n={len(idxs)}) {note}: H:{pct(oc['H'],len(idxs))} D:{pct(oc['D'],len(idxs))} A:{pct(oc['A'],len(idxs))}")
    # 水位梯度
    for wname, wlo, whi in [('低水<0.90', 0, 0.90), ('中水0.90-0.95', 0.90, 0.95), ('高水>0.95', 0.95, 99)]:
        idxs = [i for i in range(n) if wlo <= l2[i]['wh'] < whi]
        if not idxs: continue
        h = sum(1 for i in idxs if outcome(l2[i]) == 'H')
        print(f"  主{wname}(n={len(idxs)}) → H {pct(h,len(idxs))}")
    # 关键赔率档
    for name, lo, hi in [('<1.50', 0, 1.5), ('1.50-1.80', 1.5, 1.8), ('1.80-2.10', 1.8, 2.1), ('2.10-2.50', 2.1, 2.5), ('2.50-3.50', 2.5, 3.5), ('>3.50', 3.5, 99)]:
        idxs = [i for i in range(n) if lo <= l2[i]['oh'] < hi]
        if len(idxs) < 8: continue
        oc = collections.Counter(outcome(l2[i]) for i in idxs)
        hit = oc['H']
        avi = sum(implied(l2[i]['oh'], l2[i]['od'], l2[i]['oa'])[0] for i in idxs)/len(idxs)
        print(f"  主赔{name}(n={len(idxs)}) H:{pct(hit,len(idxs))} D:{pct(oc['D'],len(idxs))} A:{pct(oc['A'],len(idxs))} (隐含{100*avi:.0f}%·差{100*hit/len(idxs)-100*avi:+.1f}pp)")
    # 深盘水位
    sub = [i for i in range(n) if l2[i]['hc'] >= 1.25]
    if sub:
        for wname, wlo, whi in [('低水', 0, 0.90), ('高水', 0.95, 99)]:
            idxs = [i for i in sub if wlo <= l2[i]['wh'] < whi]
            if len(idxs) < 5: continue
            h = sum(1 for i in idxs if outcome(l2[i]) == 'H')
            print(f"  深盘+{wname}(n={len(idxs)}) → H {pct(h,len(idxs))}")

for f, tag in [('欧冠_历史.csv', '欧冠'), ('欧联_历史.csv', '欧联'), ('欧协联_历史.csv', '欧协联')]:
    rows = load_csv(os.path.join(BASE, f))
    pairs = pair_legs(rows)
    print(f"{f}: 行{len(rows)} → 配对 {len(pairs)}")
    analyze(pairs, tag)
