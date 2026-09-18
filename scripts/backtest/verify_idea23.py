#!/usr/bin/env python
# 验证想法2/3: 欧战两回合次回合规律
# 想法2: 首回合大幅领先 → 次回合领先方进球下降、落后方进球上升
# 想法3: 首回合差距不大 → 次回合大概率大球
import json
from collections import defaultdict

with open('data/fixture_index.json', 'r', encoding='utf-8') as f:
    idx = json.load(f)

# 欧战赛事 league_name (数字=league_id)
EURO = {'2': '欧冠', '3': '欧联杯', '848': '欧协联'}

# 提取欧战比赛
euro_matches = []
for r in idx:
    if r.get('league_name') in EURO:
        try:
            date = r['date']
            home = r['home_name']
            away = r['away_name']
            gh = r['gh']
            ga = r['ga']
            euro_matches.append({
                'date': date, 'home': home, 'away': away,
                'gh': gh, 'ga': ga, 'season': r.get('season',''),
                'league': EURO[r.get('league_name')]
            })
        except:
            continue

print(f'欧战比赛总数: {len(euro_matches)}')

# 配对两回合: 找到 (A主B客) 和 (B主A客) 的镜像，日期接近
# 用 (home, away) 排序后的无序对作为key
from collections import defaultdict as dd
pairs = dd(list)
for m in euro_matches:
    key = tuple(sorted([m['home'], m['away']]))
    pairs[key].append(m)

# 筛选: 恰好2场（主客互换）且日期差≤14天
tie_pairs = []
for key, ms in pairs.items():
    if len(ms) != 2:
        continue
    m1, m2 = ms[0], ms[1]
    # 确认主客互换
    if m1['home'] == m2['home']:  # 同一队两次主场，不是两回合
        continue
    d1 = m1['date']; d2 = m2['date']
    # 日期差(天)
    from datetime import datetime
    dt1 = datetime.strptime(d1[:10], '%Y-%m-%d')
    dt2 = datetime.strptime(d2[:10], '%Y-%m-%d')
    diff = abs((dt2-dt1).days)
    if diff > 14:
        continue
    # 确定首/次回合
    if dt1 < dt2:
        first, second = m1, m2
    else:
        first, second = m2, m1
    tie_pairs.append((first, second))

print(f'成功配对的两回合: {len(tie_pairs)}对')

# 分析
idea2 = {'首回合净胜≥2': [0,0,0,0,0],  # [对数, 次回合领先方场均进球, 落后方场均进球, 次回合大球数(≥3), 次回合平局数]
         '首回合净胜=1': [0,0,0,0,0],
         '首回合净胜=0': [0,0,0,0,0]}
idea3 = {'首回合净胜≤1': [0,0,0],  # [对数, 次回合大球数, 次回合总进球和]
         '首回合净胜≥2': [0,0,0]}

for first, second in tie_pairs:
    # 首回合净胜球
    margin1 = abs(first['gh'] - first['ga'])
    # 首回合领先方
    if first['gh'] >= first['ga']:
        lead_team = first['home']
    else:
        lead_team = first['away']
    
    # 次回合: 领先方在这场的进球
    if second['home'] == lead_team:
        lead_goals_2nd = second['gh']
        trail_goals_2nd = second['ga']
    else:
        lead_goals_2nd = second['ga']
        trail_goals_2nd = second['gh']
    
    total_2nd = second['gh'] + second['ga']
    
    if margin1 >= 2:
        key = '首回合净胜≥2'
    elif margin1 == 1:
        key = '首回合净胜=1'
    else:
        key = '首回合净胜=0'
    
    g = idea2[key]
    g[0] += 1
    g[1] += lead_goals_2nd
    g[2] += trail_goals_2nd
    if total_2nd >= 3:
        g[3] += 1
    if second['gh'] == second['ga']:
        g[4] += 1
    
    # 想法3
    if margin1 <= 1:
        k3 = '首回合净胜≤1'
    else:
        k3 = '首回合净胜≥2'
    idea3[k3][0] += 1
    idea3[k3][1] += (1 if total_2nd >= 3 else 0)
    idea3[k3][2] += total_2nd

print()
print('=== 想法2: 首回合领先幅度 vs 次回合进球 ===')
print(f'{"分组":<14} {"对数":>6} {"次回合领先方场均进球":>12} {"落后方场均进球":>12} {"大球率(≥3)":>10} {"平局率":>8}')
for key in ['首回合净胜≥2', '首回合净胜=1', '首回合净胜=0']:
    g = idea2[key]
    n = g[0]
    if n == 0:
        continue
    print(f'{key:<14} {n:>6} {g[1]/n:>12.2f} {g[2]/n:>12.2f} {g[3]/n*100:>9.1f}% {g[4]/n*100:>7.1f}%')

print()
print('=== 想法3: 首回合差距 vs 次回合大球 ===')
print(f'{"分组":<14} {"对数":>6} {"次回合大球率(≥3)":>12} {"次回合场均总进球":>12}')
for key in ['首回合净胜≤1', '首回合净胜≥2']:
    g = idea3[key]
    n = g[0]
    if n == 0:
        continue
    print(f'{key:<14} {n:>6} {g[1]/n*100:>11.1f}% {g[2]/n:>12.2f}')
