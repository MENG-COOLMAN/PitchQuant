# -*- coding: utf-8 -*-
"""先验筛选信号标准回测：Matches.csv 五大联赛·PreStep 8信号打分→分数分组方向命中率→阈值调优"""
import csv
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')  # 🔴2026-09-04链路优化: 默认GBK控制台防UnicodeEncodeError崩溃/乱码
except Exception:
    pass

from collections import Counter, defaultdict

LEAGUES = {'E0':'英超','SP1':'西甲','D1':'德甲','I1':'意甲','F1':'法甲'}
# 联赛平率基准（≥27% 才 D3 均势必平）
DRAW_BASE = {'E0':24.6,'SP1':25.2,'D1':24.7,'I1':27.0,'F1':27.8}

def load():
    rows = []
    with open('data/Matches.csv', encoding='utf-8', errors='replace') as f:
        r = csv.reader(f); h = next(r)
        idx = {k: h.index(k) for k in ['Division','FTHome','FTAway','FTResult','OddHome','OddDraw','OddAway','Over25','HandiSize','HandiHome','HandiAway']}
        for row in r:
            if row[idx['Division']] not in LEAGUES: continue
            try:
                gh, ga = int(float(row[idx['FTHome']])), int(float(row[idx['FTAway']]))
                oh = float(row[idx['OddHome']]); od = float(row[idx['OddDraw']]); oa = float(row[idx['OddAway']])
                o25 = float(row[idx['Over25']] or 0); hs = float(row[idx['HandiSize']] or 0)
                hh = float(row[idx['HandiHome']] or 0); ha = float(row[idx['HandiAway']] or 0)
                rows.append({'div':row[idx['Division']],'gh':gh,'ga':ga,'res':row[idx['FTResult']],
                             'oh':oh,'od':od,'oa':oa,'o25':o25,'hs':hs,'hh':hh,'ha':ha})
            except: pass
    return rows

rows = load()
print(f"样本: {len(rows)} 场五大联赛\n")

def score_match(r):
    div = r['div']
    # 隐含概率
    ih, id_, ia = 1/r['oh'], 1/r['od'], 1/r['oa']
    s = ih+id_+ia
    ih, id_, ia = 100*ih/s, 100*id_/s, 100*ia/s
    sigs = {'主胜':0,'客胜':0,'平局':0}
    # D1 深盘主胜 +2
    if r['oh'] < 1.5: sigs['主胜'] += 2
    # D2 深盘客胜 +2（客让0.75+ = HandiSize>0.75）
    if r['hs'] > 0.75: sigs['客胜'] += 2
    # D3 均势必平 +1.5（主客隐含差5-10pp + 联赛平率≥27）
    if 5 <= abs(ih-ia) <= 10 and DRAW_BASE[div] >= 27: sigs['平局'] += 1.5
    # D4 平手主胜 +1（|HandiSize|<0.25）
    if abs(r['hs']) < 0.25: sigs['主胜'] += 1
    # G1 大球确认 +1.5（O25<1.7）→ 进球信号不直接定方向·计入总分
    g1 = 1.5 if 0 < r['o25'] < 1.7 else 0
    g2 = 1.0 if r['o25'] > 2.1 else 0
    # H1 水位背离 +1（主水位 vs 客水位差>0.2·V6修正55简化）
    h1 = 1.0 if r['hh']>0 and r['ha']>0 and abs(r['hh']-r['ha'])>0.2 else 0
    # H2 穿盘区间 +1（主让1.25-1.75 → HandiSize -1.75~-1.25）
    h2 = 1.0 if -1.75 <= r['hs'] <= -1.25 else 0
    # H3 反直觉降级 -1（西甲1.5-1.8档 或 法甲深盘<1.5 → 主胜降级=客胜加分）
    if (div=='SP1' and 1.5<=r['oh']<1.8) or (div=='F1' and r['oh']<1.5):
        sigs['主胜'] -= 1; sigs['客胜'] += 1
    total = sigs['主胜'] + sigs['客胜'] + sigs['平局'] + g1 + g2 + h1 + h2
    # 预测方向 = 分数最高的方向类
    pred = max(sigs, key=sigs.get)
    return total, pred, sigs

# 分组统计
groups = defaultdict(lambda: {'n':0,'hit':0})
by_threshold = {}
for r in rows:
    total, pred, _ = score_match(r)
    # 真实方向
    if r['res']=='H': real='主胜'
    elif r['res']=='A': real='客胜'
    else: real='平局'
    hit = (pred==real)
    # 分组: 强(≥3)/中(2-2.5)/弱(<2)
    for gname, cond in [('强≥3', total>=3), ('中2-2.5', 2<=total<3), ('弱<2', total<2)]:
        if cond:
            groups[gname]['n']+=1; groups[gname]['hit']+=hit
    # 阈值对比（只统计有方向信号的场·总分按含方向分）
    for th in [2, 2.5, 3, 3.5, 4, 4.5, 5]:
        if total >= th:
            by_threshold.setdefault(th, {'n':0,'hit':0})
            by_threshold[th]['n']+=1; by_threshold[th]['hit']+=hit

print("=== 分数分组方向命中率（预测方向=分数最高的方向信号）===")
for g in ['强≥3','中2-2.5','弱<2']:
    d = groups[g]
    if d['n']: print(f"  {g}: n={d['n']} · 命中率 {100*d['hit']/d['n']:.1f}%")
    else: print(f"  {g}: n=0")
base = sum(1 for r in rows if (r['res']=='H') or (r['res']=='A') or (r['res']=='D'))
print(f"  全样本基准: {len(rows)}场 (方向随机基准≈33.3%)")

print("\n=== 阈值对比（≥T 的场·方向命中率与覆盖率）===")
for th in [2, 2.5, 3, 3.5, 4, 4.5, 5]:
    d = by_threshold[th]
    print(f"  ≥{th}分: n={d['n']} ({100*d['n']/len(rows):.1f}%覆盖) · 命中率 {100*d['hit']/d['n']:.1f}%")
