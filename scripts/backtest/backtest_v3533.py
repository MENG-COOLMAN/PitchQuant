#!/usr/bin/env python3
"""V3.5.33 全模型回测 —— 基于GitHub Matches.csv 10万+场"""

import csv, json
from collections import defaultdict

PATH = 'data/Matches.csv'
ODDS_CUTOFF = 1.01
MIN_MATCHES = 100  # per group

DIV_NAMES = {'E0':'英超','D1':'德甲','I1':'意甲','SP1':'西甲','F1':'法甲',
    'N1':'荷甲','P1':'葡超','SWE':'瑞超','NOR':'挪超','FIN':'芬超',
    'JAP':'日职','CHN':'中超','EC':'欧锦赛','B1':'比甲','T1':'土超',
    'G1':'希腊超','SC0':'苏超','BRA':'巴甲','ARG':'阿甲','USA':'MLS'}

# ── 数据结构 ──
# 1. 方向准确率: {league: [total, correct]}
# 2. 深盘准确率: {'<1.3','1.3-1.5','1.5-1.7','1.7-2.0','>2.0': [t,c]}
# 3. 联赛抽水校准: {league: [sum_ov, count]}
# 4. 大小球准确率: {league: [t,c, ovr_t, ovr_c]}
# 5. 共识过热: [total, correct, wrong] + 反转细节
# 6. 亚洲让球穿盘率: {handi_size: {dir: [t,c]}}
# 7. 平局独立频率: {league: [t, draw_t]}

dir_acc = defaultdict(lambda: [0,0])
deep_acc = {'<1.30':[0,0],'1.30-1.50':[0,0],'1.50-1.70':[0,0],'1.70-2.00':[0,0],'2.00+':[0,0]}
league_ov = defaultdict(lambda: [0.0,0])
ou_acc = defaultdict(lambda: [0,0, 0,0])  # [t,c] for O25, [t,c] for U25 avg ovr
consensus = [0,0,0]  # total, correct_consensus, wrong_consensus
asian_acc = defaultdict(lambda: defaultdict(lambda: [0,0]))  # {size: {dir: [t,c]}}
draw_rate = defaultdict(lambda: [0,0])  # league: [total_matches, draw_count]
score_avg = defaultdict(lambda: [0.0,0])  # league: [goals_sum, count]

# ── 主循环 ──
with open(PATH, 'r', encoding='utf-8', errors='ignore') as f:
    reader = csv.DictReader(f)
    for row in reader:
        # ── 基础校验 ──
        oh, od, oa = row.get('OddHome',''), row.get('OddDraw',''), row.get('OddAway','')
        if not oh or not od or not oa: continue
        try:
            h = float(oh); d = float(od); a = float(oa)
            if h < ODDS_CUTOFF or d < ODDS_CUTOFF or a < ODDS_CUTOFF: continue
        except: continue
        
        result = row.get('FTResult','')
        if not result or result not in ('H','D','A'): continue
        div = row.get('Division','')
        
        # 进球数
        try:
            fhg = int(row.get('FTHome','0') or 0)
            fag = int(row.get('FTAway','0') or 0)
            total_goals = fhg + fag
            score_avg[div][0] += total_goals
            score_avg[div][1] += 1
        except: pass
        
        # ── 1. 方向准确率（按联赛） ──
        if h < a and h < d: predicted = 'H'
        elif a < h and a < d: predicted = 'A'
        else: predicted = 'D'
        
        correct_dir = (predicted == result)
        dir_acc[div][0] += 1
        if correct_dir: dir_acc[div][1] += 1
        
        # ── 2. 深盘准确率 ──
        min_odd = min(h, a)
        if min_odd < 1.30: band = '<1.30'
        elif min_odd < 1.50: band = '1.30-1.50'
        elif min_odd < 1.70: band = '1.50-1.70'
        elif min_odd < 2.00: band = '1.70-2.00'
        else: band = '2.00+'
        deep_acc[band][0] += 1
        if correct_dir: deep_acc[band][1] += 1
        
        # ── 3. 抽水校准 ──
        ov = 1/h + 1/d + 1/a - 1
        league_ov[div][0] += ov
        league_ov[div][1] += 1
        
        # ── 4. 大小球准确率 ──
        o25, u25 = row.get('Over25',''), row.get('Under25','')
        if o25 and u25:
            try:
                o25f = float(o25); u25f = float(u25)
                # Predict O2.5 if O25 odds < U25 odds
                ou_pred = 'O' if o25f < u25f else 'U'
                ou_actual = 'O' if total_goals > 2.5 else 'U'
                ou_correct = (ou_pred == ou_actual)
                ou_acc[div][0] += 1
                if ou_correct: ou_acc[div][1] += 1
                if ou_actual == 'O': ou_acc[div][2] += 1
                else: ou_acc[div][3] += 1
            except: pass
        
        # ── 5. 共识过热 ──
        # Proxy: odds skew > 200% (home odds < 1/3 of away = extreme consensus)
        if predicted != 'D':
            skew = abs(h - a) / min(h, a)
            if skew > 2.0:  # very strong consensus
                consensus[0] += 1
                if correct_dir: consensus[1] += 1
                else: consensus[2] += 1
        
        # ── 6. 亚洲让球 ──
        hsz = row.get('HandiSize','')
        hho = row.get('HandiHome','')
        hao = row.get('HandiAway','')
        if hsz and hho and hao:
            try:
                sz = float(hsz)
                if sz != 0:
                    dir_key = 'H' if float(hho) < float(hao) else 'A'
                    asian_acc[sz][dir_key][0] += 1
                    # 穿盘判定: 让球方赢盘
                    h_cover = (predicted == 'H')  # simplified
                    # Actually need proper handicap calculation
            except: pass
        
        # ── 7. 平局频率 ──
        draw_rate[div][0] += 1
        if result == 'D': draw_rate[div][1] += 1


# ════════════════════════════════════════════
# 输出报告
# ════════════════════════════════════════════

print('='*60)
print('V3.5.33 全模型回测报告')
print('='*60)

# 1. 方向准确率
print('\n## 1. 方向准确率（按联赛，赔率最低方向）')
print(f'{"联赛":<8} {"场次":<8} {"准确率":<10} {"均抽水":>8}')
for div in sorted(dir_acc.keys(), key=lambda d: dir_acc[d][0], reverse=True):
    t, c = dir_acc[div]
    if t < MIN_MATCHES: continue
    name = DIV_NAMES.get(div, div)
    acc = c/t*100
    avg_ov = league_ov[div][0]/league_ov[div][1]*100 if league_ov[div][1]>0 else 0
    print(f'{name:<8} {t:<8} {acc:>6.1f}%   {avg_ov:>6.2f}%')

# 2. 深盘准确率
print('\n## 2. 深盘准确率（按赔率区间）')
print(f'{"区间":<12} {"场次":<8} {"准确率":<10}')
for band in ['<1.30','1.30-1.50','1.50-1.70','1.70-2.00','2.00+']:
    t, c = deep_acc[band]
    if t > 0:
        print(f'{band:<12} {t:<8} {c/t*100:>6.1f}%')

# 3. 共识过热
print('\n## 3. 共识过热（赔率偏差>200%）')
t, c, w = consensus
if t > 0:
    print(f'总场次: {t}')
    print(f'正确(共识方向): {c} ({c/t*100:.1f}%)')
    print(f'反转(冷门): {w} ({w/t*100:.1f}%)')
    print(f'> 修正32支撑: 反转率 {w/t*100:.1f}%')

# 4. 大小球
print('\n## 4. 大小球准确率（O2.5/U2.5）')
ou_top = sorted(ou_acc.items(), key=lambda x: x[1][0], reverse=True)[:15]
for div, (t,c,o_u) in ou_top:
    if t < MIN_MATCHES: continue
    name = DIV_NAMES.get(div, div)
    print(f'{name:<8} {t:<8} {c/t*100:>6.1f}%')

# 5. 联赛基础统计
print('\n## 5. 联赛基础统计（进球+平局率）')
for div in sorted(score_avg.keys(), key=lambda d: score_avg[d][1], reverse=True):
    t = score_avg[div][1]
    if t < 500: continue
    name = DIV_NAMES.get(div, div)
    avg_g = score_avg[div][0]/t
    dr = draw_rate[div][1]/draw_rate[div][0]*100 if draw_rate[div][0]>0 else 0
    print(f'{name:<8} {t:<8} 均进球{avg_g:.2f}  平局率{dr:.1f}%')

print('\n' + '='*60)
print('回测完成')
