#!/usr/bin/env python
# 验证: 首回合大胜(净胜≥3)的领先方，次回合是否"放松"(被逼平/输)
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

# 首回合领先方次回合结果分布
bins = defaultdict(lambda: [0,0,0,0])  # [对数, 次回合领先方赢, 平, 输]
for first, second in tie_pairs:
    margin = abs(first['gh'] - first['ga'])
    if margin >= 4:
        key = '净胜4+'
    elif margin == 3:
        key = '净胜3'
    elif margin == 2:
        key = '净胜2'
    elif margin == 1:
        key = '净胜1'
    else:
        key = '净胜0'
    
    if first['gh'] >= first['ga']:
        lead = first['home_name']
    else:
        lead = first['away_name']
    
    if second['home_name'] == lead:
        lg = second['gh']; tg = second['ga']
    else:
        lg = second['ga']; tg = second['gh']
    
    bins[key][0] += 1
    if lg > tg:
        bins[key][1] += 1  # 领先方次回合赢
    elif lg == tg:
        bins[key][2] += 1  # 平
    else:
        bins[key][3] += 1  # 领先方次回合输

print('=== 首回合领先方次回合结果分布(是否放松) ===')
print(f'{"首回合净胜":<10} {"对数":>6} {"次回合赢":>8} {"平":>8} {"输":>8} {"平+输率":>8}')
for key in ['净胜0', '净胜1', '净胜2', '净胜3', '净胜4+']:
    g = bins[key]
    n = g[0]
    if n == 0:
        continue
    print(f'{key:<10} {n:>6} {g[1]/n*100:>7.1f}% {g[2]/n*100:>7.1f}% {g[3]/n*100:>7.1f}% {(g[2]+g[3])/n*100:>7.1f}%')
