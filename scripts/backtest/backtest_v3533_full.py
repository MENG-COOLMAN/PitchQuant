#!/usr/bin/env python3
"""V3.5.33 全模型回测 —— 方向+比分范围预测 vs 真实结果"""

import csv
from collections import defaultdict
import json

PATH = 'data/Matches.csv'
ODDS_MIN = 1.01
MIN_GROUP = 200

# ════════════════════════════════════════════
# 最新模型规则（）
# ════════════════════════════════════════════

# 修正14（回测修正）：超深盘+10%
# 修正32（分级）：温和共识(100-200%)降级，极端共识(>200%)不降
# 修正33：信号去噪声

# ── 数据结构 ──
results = {
    'overall': defaultdict(lambda: [0,0]),  # [total, correct] by direction
    'deep': {'<1.30':[0,0], '1.30-1.50':[0,0], '1.50-1.70':[0,0], '1.70-2.00':[0,0], '2.00+':[0,0]},
    'consensus_mild': [0,0],  # skew 100-200%
    'consensus_extreme': [0,0],  # skew >200%
    'no_consensus': [0,0],
    'asian': {'cover':[0,0], 'no_cover':[0,0], 'push':0},  # 穿盘/不穿/走水
    'asian_by_size': defaultdict(lambda: [0,0]),  # by handicap size
    'ou': defaultdict(lambda: [0,0]),  # Over/Under accuracy
    'score_range': defaultdict(lambda: [0,0,0,0,0]),  # [t, exact, ±1, ±2, miss]
    'league_dir': defaultdict(lambda: [0,0]),
    'league_ou': defaultdict(lambda: [0,0]),
    'league_cover': defaultdict(lambda: [0,0]),
}

total = 0
matches_with_asian = 0
matches_with_ou = 0

with open(PATH, 'r', encoding='utf-8', errors='ignore') as f:
    reader = csv.DictReader(f)
    for row in reader:
        oh, od, oa = row.get('OddHome',''), row.get('OddDraw',''), row.get('OddAway','')
        if not oh or not od or not oa: continue
        try:
            h = float(oh); d = float(od); a = float(oa)
            if h < ODDS_MIN or d < ODDS_MIN or a < ODDS_MIN: continue
        except: continue
        
        result = row.get('FTResult','')
        if result not in ('H','D','A'): continue
        div = row.get('Division','')
        
        try:
            fhg = int(row.get('FTHome','0') or 0)
            fag = int(row.get('FTAway','0') or 0)
            total_goals = fhg + fag
            goal_diff = fhg - fag
        except:
            continue
        
        total += 1
        
        # ══ 模型预测 ══
        
        # 1. 方向预测（赔率最低方向）
        if h < a and h < d: predicted_dir = 'H'
        elif a < h and a < d: predicted_dir = 'A'
        else: predicted_dir = 'D'
        
        dir_correct = (predicted_dir == result)
        results['overall'][predicted_dir][0] += 1
        if dir_correct: results['overall'][predicted_dir][1] += 1
        results['league_dir'][div][0] += 1
        if dir_correct: results['league_dir'][div][1] += 1
        
        # 2. 深盘分级
        min_odd = min(h, a)
        if min_odd < 1.30: band = '<1.30'
        elif min_odd < 1.50: band = '1.30-1.50'
        elif min_odd < 1.70: band = '1.50-1.70'
        elif min_odd < 2.00: band = '1.70-2.00'
        else: band = '2.00+'
        results['deep'][band][0] += 1
        if dir_correct: results['deep'][band][1] += 1
        
        # 3. 共识分级（修正32）
        if predicted_dir != 'D':
            skew = abs(h - a) / min(h, a)
            if skew > 2.0:
                results['consensus_extreme'][0] += 1
                if dir_correct: results['consensus_extreme'][1] += 1
            elif skew > 1.0:
                results['consensus_mild'][0] += 1
                if dir_correct: results['consensus_mild'][1] += 1
            else:
                results['no_consensus'][0] += 1
                if dir_correct: results['no_consensus'][1] += 1
        
        # 4. 亚洲让球穿盘预测
        hsz = row.get('HandiSize','')
        hho = row.get('HandiHome','')
        hao = row.get('HandiAway','')
        if hsz and hho and hao:
            try:
                sz = float(hsz)
                hh = float(hho); ha = float(hao)
                if sz != 0 and hh > 0 and ha > 0:
                    matches_with_asian += 1
                    # 让球方 = 赔率低的一方（机构定价方向）
                    if hh < ha:
                        handicap_dir = 'H'  # 主队是让球方
                        cover_margin = sz
                    else:
                        handicap_dir = 'A'  # 客队是让球方
                        cover_margin = -sz
                    
                    # 判定穿盘
                    if handicap_dir == 'H':
                        # 主队让球，需赢>sz才穿盘
                        if goal_diff > sz: outcome = 'cover'
                        elif goal_diff == sz: outcome = 'push'
                        else: outcome = 'no_cover'
                    else:
                        # 客队让球
                        if -goal_diff > abs(sz): outcome = 'cover'
                        elif -goal_diff == abs(sz): outcome = 'push'
                        else: outcome = 'no_cover'
                    
                    if outcome == 'cover':
                        results['asian']['cover'][0] += 1
                        results['asian']['cover'][1] += 1
                        results['league_cover'][div][0] += 1
                        results['league_cover'][div][1] += 1
                    elif outcome == 'no_cover':
                        results['asian']['no_cover'][0] += 1
                        results['asian']['no_cover'][1] += 1  # 不穿盘=被让方赢
                        results['league_cover'][div][0] += 1
                    else:
                        results['asian']['push'] += 1
                    
                    # 按让球深度分组
                    abs_sz = abs(sz)
                    if abs_sz <= 0.25: sz_key = '0.25'
                    elif abs_sz <= 0.5: sz_key = '0.5'
                    elif abs_sz <= 0.75: sz_key = '0.75'
                    elif abs_sz <= 1.0: sz_key = '1.0'
                    elif abs_sz <= 1.5: sz_key = '1.5'
                    else: sz_key = '1.75+'
                    results['asian_by_size'][sz_key][0] += 1
                    if outcome == 'cover': results['asian_by_size'][sz_key][1] += 1
            except: pass
        
        # 5. 大小球预测
        o25 = row.get('Over25','')
        u25 = row.get('Under25','')
        if o25 and u25:
            try:
                o25f = float(o25); u25f = float(u25)
                if o25f > 0 and u25f > 0:
                    matches_with_ou += 1
                    ou_pred = 'O' if o25f < u25f else 'U'
                    ou_actual = 'O' if total_goals > 2.5 else 'U'
                    ou_correct = (ou_pred == ou_actual)
                    ou_key = 'Over' if ou_pred == 'O' else 'Under'
                    results['ou'][ou_key][0] += 1
                    if ou_correct: results['ou'][ou_key][1] += 1
                    results['league_ou'][div][0] += 1
                    if ou_correct: results['league_ou'][div][1] += 1
            except: pass
        
        # 6. 比分范围预测（方向+穿盘+大小球综合）
        # 预测逻辑：方向 + 让球方向 → 比分差范围
        if predicted_dir != 'D':
            # 预测比分差
            if hsz and hho and hao:
                try:
                    sz = float(hsz); hh = float(hho); ha = float(hao)
                    favor_home = (hh < ha)
                    if favor_home:
                        pred_diff_min = max(1, int(sz))  # 让球方至少赢sz球
                        pred_diff_max = pred_diff_min + 2
                    else:
                        pred_diff_min = max(1, int(abs(sz)))
                        pred_diff_max = pred_diff_min + 2
                except:
                    pred_diff_min = 1; pred_diff_max = 3
            else:
                pred_diff_min = 1; pred_diff_max = 3
            
            # 检查实际比分差是否在预测范围内
            actual_diff = abs(goal_diff)
            in_range = (pred_diff_min <= actual_diff <= pred_diff_max)
            # 比分范围预测
            if actual_diff == pred_diff_min: results['score_range']['total'][0] += 1  # t
            elif pred_diff_min <= actual_diff <= pred_diff_max: results['score_range']['total'][1] += 1  # near
            else: results['score_range']['total'][2] += 1  # miss

# ════════════════════════════════════════════
# 输出报告
# ════════════════════════════════════════════

print('=' * 65)
print('V3.5.33 全模型回测报告（最新修正）')
print(f'总比赛数：{total:,}')
print(f'亚洲让球数据：{matches_with_asian:,} 场')
print(f'大小球数据：{matches_with_ou:,} 场')
print('=' * 65)

# 1. 方向预测
print('\n## 1. 方向预测准确率')
print(f'{"预测方向":<10} {"总场次":<10} {"正确":<10} {"准确率":<10}')
for dir_key in ['H','D','A']:
    t, c = results['overall'][dir_key]
    if t > 0:
        print(f'{dir_key:<10} {t:<10,} {c:<10,} {c/t*100:>6.1f}%')

# 2. 深盘分级（修正14新版：+10%）
print(f'\n## 2. 深盘准确率（修正14：<1.30→+10%，回测验证82.4%）')
for band in ['<1.30','1.30-1.50','1.50-1.70','1.70-2.00','2.00+']:
    t, c = results['deep'][band]
    if t > 0:
        bar = '█' * int(c/t*50)
        print(f'  {band:<12} {t:>6,}场  {c/t*100:>5.1f}%  {bar}')

# 3. 共识分级（修正32新版：分级触发）
print(f'\n## 3. 共识分级（修正32：温和→降级 / 极端→不降）')
for key, label in [('consensus_extreme','极端共识(>200%)'), ('consensus_mild','温和共识(100-200%)'), ('no_consensus','无共识(<100%)')]:
    t, c = results[key]
    if t > 0:
        print(f'  {label:<22} {t:>6,}场  {c/t*100:>5.1f}%')
    if key == 'consensus_mild' and t > 0:
        print(f'    → 修正32触发（降级+平局出口）：{t:,}场中{(1-c/t)*100:.1f}%需反向出口')

# 4. 亚洲让球穿盘
print(f'\n## 4. 亚洲让球穿盘率（{matches_with_asian:,}场）')
tc = results['asian']['cover']; tn = results['asian']['no_cover']; tp = results['asian']['push']
total_asian = tc[0] + tn[0] + tp
if total_asian > 0:
    print(f'  穿盘(cover):    {tc[0]:>6,}场  {tc[0]/total_asian*100:>5.1f}%')
    print(f'  不穿(no cover):  {tn[0]:>6,}场  {tn[0]/total_asian*100:>5.1f}%')
    print(f'  走水(push):     {tp:>6,}场  {tp/total_asian*100:>5.1f}%')

print(f'\n## 4+. 让球深度vs穿盘率')
for sz_key in ['0.25','0.5','0.75','1.0','1.5','1.75+']:
    t, c = results['asian_by_size'][sz_key]
    if t > 0:
        bar = '█' * int(c/t*50)
        print(f'  让{sz_key}球:    {t:>6,}场  {c/t*100:>5.1f}% 穿盘 {bar}')

# 5. 大小球
print(f'\n## 5. 大小球预测（{matches_with_ou:,}场）')
for key in ['Over','Under']:
    t, c = results['ou'][key]
    if t > 0:
        print(f'  {key:<8} {t:>8,}场  {c/t*100:>5.1f}%')

# 6. 联赛方向
print(f'\n## 6. 联赛方向准确率（前15联赛）')
s_top = sorted(results['league_dir'].items(), key=lambda x: x[1][0], reverse=True)[:15]
names = {'E0':'英超','D1':'德甲','I1':'意甲','SP1':'西甲','F1':'法甲','N1':'荷甲',
    'P1':'葡超','SWE':'瑞超','NOR':'挪超','FIN':'芬超','JAP':'日职','CHN':'中超',
    'B1':'比甲','T1':'土超','G1':'希腊超','SC0':'苏超','EC':'欧锦赛','BRA':'巴甲','ARG':'阿甲'}
for div, (t,c) in s_top:
    name = names.get(div, div)
    print(f'  {name:<10} {t:>6,}场  {c/t*100:>5.1f}%')

# 7. 比分范围汇总
if results['score_range']['total'][0] > 0:
    print(f'\n## 7. 比分差范围预测（方向+让球综合）')
    t_exact, t_near, t_miss = results['score_range']['total']
    total_score = t_exact + t_near + t_miss
    print(f'  精确命中: {t_exact/total_score*100:.1f}%')
    print(f'  接近(±1球): {t_near/total_score*100:.1f}%')
    print(f'  偏离(>2球): {t_miss/total_score*100:.1f}%')

print('\n' + '=' * 65)
print('V3.5.33 回测结束')
