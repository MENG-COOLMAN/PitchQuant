# -*- coding: utf-8 -*-
"""先验筛选 8 信号逐独立回测：每个信号触发时的命中率 vs 全局基准"""
import csv
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')  # 🔴2026-09-04链路优化: 默认GBK控制台防UnicodeEncodeError崩溃/乱码
except Exception:
    pass

from collections import Counter

LEAGUES = {'E0':'英超','SP1':'西甲','D1':'德甲','I1':'意甲','F1':'法甲'}
DRAW_BASE = {'E0':24.6,'SP1':25.2,'D1':24.7,'I1':27.0,'F1':27.8}

def load():
    rows = []
    with open('data/Matches.csv', encoding='utf-8', errors='replace') as f:
        r = csv.reader(f); h = next(r)
        idx = {k: h.index(k) for k in ['Division','FTHome','FTAway','FTResult','OddHome','OddDraw','OddAway','Over25','HandiSize','HandiHome','HandiAway']}
        for row in r:
            if row[idx['Division']] not in LEAGUES: continue
            try:
                rows.append({'div':row[idx['Division']],'gh':int(float(row[idx['FTHome']])),'ga':int(float(row[idx['FTAway']])),
                    'res':row[idx['FTResult']],'oh':float(row[idx['OddHome']]),'od':float(row[idx['OddDraw']]),'oa':float(row[idx['OddAway']]),
                    'o25':float(row[idx['Over25']] or 0),'hs':float(row[idx['HandiSize']] or 0),
                    'hh':float(row[idx['HandiHome']] or 0),'ha':float(row[idx['HandiAway']] or 0)})
            except: pass
    return rows

rows = load(); N = len(rows)
# 全局基准
res_c = Counter(r['res'] for r in rows)
over_c = sum(1 for r in rows if r['gh']+r['ga']>=3)
print(f"样本 {N} 场 · 全局基准: 主胜{100*res_c['H']/N:.1f}% 平{100*res_c['D']/N:.1f}% 客胜{100*res_c['A']/N:.1f}% · 大球{100*over_c/N:.1f}%\n")

def stat(sub, pred_dir, label):
    n = len(sub)
    if not n: return
    if pred_dir == '主胜': hit = sum(1 for r in sub if r['res']=='H')
    elif pred_dir == '客胜': hit = sum(1 for r in sub if r['res']=='A')
    elif pred_dir == '平局': hit = sum(1 for r in sub if r['res']=='D')
    elif pred_dir == '大球': hit = sum(1 for r in sub if r['gh']+r['ga']>=3)
    else: hit = sum(1 for r in sub if r['gh']+r['ga']<3)
    rate = 100*hit/n
    base = {'主胜':46.2,'客胜':28.5,'平局':25.3,'大球':50.0,'小球':50.0}[pred_dir]
    tag = '🔴有效' if rate - base >= 8 else ('有效' if rate - base >= 4 else ('⚠️弱' if rate - base > -2 else '❌无效'))
    print(f"  {label}: n={n} · 命中率 {rate:.1f}% (基准{pred_dir}{base}%) · 差{rate-base:+.1f}pp {tag}")

print("=== 方向类信号 ===")
stat([r for r in rows if r['oh']<1.5], '主胜', 'D1 深盘主胜(主赔<1.5)')
stat([r for r in rows if r['hs']>0.75], '客胜', 'D2 深盘客胜(客让0.75+)')
d3 = [r for r in rows if 5<=abs(100/r['oh']/(1/r['oh']+1/r['od']+1/r['oa'])*100 - 100/r['oa']/(1/r['oh']+1/r['od']+1/r['oa'])*100)<=10 and DRAW_BASE[r['div']]>=27]
stat(d3, '平局', 'D3 均势必平(隐含差5-10pp+平率≥27)')
stat([r for r in rows if abs(r['hs'])<0.25], '主胜', 'D4 平手主胜(|盘|<0.25)')
stat([r for r in rows if -1.75<=r['hs']<=-1.25], '主胜', 'H2 穿盘区间(主让1.25-1.75)')
h3 = [r for r in rows if (r['div']=='SP1' and 1.5<=r['oh']<1.8) or (r['div']=='F1' and r['oh']<1.5)]
stat(h3, '客胜', 'H3 反直觉降级(西甲1.5-1.8/法甲深盘→客胜)')

print("\n=== 进球类信号 ===")
stat([r for r in rows if 0<r['o25']<1.7], '大球', 'G1 大球确认(O25<1.7)')
stat([r for r in rows if r['o25']>2.1], '小球', 'G2 小球确认(O25>2.1)')

print("\n=== 盘口类信号 ===")
h1a = [r for r in rows if r['hh']>=2.0 and 0<r['o25']<=1.9]  # 主高水+大低水→2-1/1-2类
h1b = [r for r in rows if r['hh']>=2.0 and r['o25']>=2.0]    # 主高水+小低水→0-0/1-0类
stat(h1a, '大球', 'H1a 主高水+大低水→进球')
stat(h1b, '小球', 'H1b 主高水+小低水→小球')
EOF
