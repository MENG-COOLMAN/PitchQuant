#!/usr/bin/env python
# 验证想法一(正确版): 首回合与次回合之间的总比分追逐
# 场景: 首回合差距不大(平/1球/2球)，次回合落后方追平总比分 → 双方继续进球(追逐) → 次回合大球
import json
from collections import defaultdict
from datetime import datetime

with open('data/fixture_index.json', 'r', encoding='utf-8') as f:
    idx = json.load(f)

EURO = {'2': '欧冠', '3': '欧联杯', '848': '欧协联'}
euro = [r for r in idx if r.get('league_name') in EURO]

pairs = defaultdict(list)
for m in euro:
    key = tuple(sorted([m['home_name'], m['away_name']]))
    pairs[key].append(m)

tie_pairs = []
for key, ms in pairs.items():
    if len(ms) != 2:
        continue
    if ms[0]['home_name'] == ms[1]['home_name']:
        continue
    dt1 = datetime.strptime(ms[0]['date'][:10], '%Y-%m-%d')
    dt2 = datetime.strptime(ms[1]['date'][:10], '%Y-%m-%d')
    if abs((dt2-dt1).days) > 14:
        continue
    first, second = (ms[0], ms[1]) if dt1 < dt2 else (ms[1], ms[0])
    tie_pairs.append((first, second))

print(f'两回合配对: {len(tie_pairs)}对')

# 核心: 首回合差距不大时，次回合"比分追逐"(双方都进球/落后方追平) vs 次回合大球
# 定义"追逐"触发:
# 首回合净胜0: 次回合双方都进球(gh2>=1 且 ga2>=1) = 追逐
# 首回合净胜1: 次回合落后方进球(追平/反超趋势)
# 首回合净胜2: 次回合落后方进球>=2(追平)

groups = {
    '净胜0_次回合双方进球': [0,0,0],
    '净胜0_次回合一方零封': [0,0,0],
    '净胜1_次回合落后方进球': [0,0,0],
    '净胜1_次回合落后方零封': [0,0,0],
    '净胜2_次回合落后方追平(≥2球)': [0,0,0],
    '净胜2_次回合落后方未追平': [0,0,0],
}

for first, second in tie_pairs:
    margin1 = first['gh'] - first['ga']  # 首回合主队A净胜
    # 首回合领先方
    if margin1 > 0:
        lead = first['home_name']  # A领先
    elif margin1 < 0:
        lead = first['away_name']  # B领先
    else:
        lead = None
    
    # 次回合: 落后方进球
    if lead is None:
        # 首回合平局, 无落后方
        gh2 = second['gh']; ga2 = second['ga']
        total2 = gh2 + ga2
        if gh2 >= 1 and ga2 >= 1:
            key = '净胜0_次回合双方进球'
        else:
            key = '净胜0_次回合一方零封'
    else:
        # 落后方在次回合的进球
        if second['home_name'] == lead:
            trail_goals = second['ga']  # 落后方是客队
            lead_goals = second['gh']
        else:
            trail_goals = second['gh']  # 落后方是主队
            lead_goals = second['ga']
        total2 = second['gh'] + second['ga']
        
        amargin = abs(margin1)
        if amargin == 1:
            if trail_goals >= 1:
                key = '净胜1_次回合落后方进球'
            else:
                key = '净胜1_次回合落后方零封'
        elif amargin == 2:
            if trail_goals >= 2:
                key = '净胜2_次回合落后方追平(≥2球)'
            else:
                key = '净胜2_次回合落后方未追平'
        else:
            continue
    
    groups[key][0] += 1
    if total2 >= 3:
        groups[key][1] += 1
    groups[key][2] += total2

print()
print('=== 想法一(正确版): 首回合vs次回合总比分追逐 ===')
print(f'{"场景":<30} {"对数":>6} {"次回合大球率≥3":>11} {"次回合场均总进球":>12}')
for key in ['净胜0_次回合双方进球', '净胜0_次回合一方零封',
            '净胜1_次回合落后方进球', '净胜1_次回合落后方零封',
            '净胜2_次回合落后方追平(≥2球)', '净胜2_次回合落后方未追平']:
    g = groups[key]
    n = g[0]
    if n == 0:
        print(f'{key:<30} {n:>6}  (无样本)')
        continue
    print(f'{key:<30} {n:>6} {g[1]/n*100:>10.1f}% {g[2]/n:>12.2f}')
