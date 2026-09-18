#!/usr/bin/env python
# 想法二扩展: 首回合净胜球分层到5球+
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

# 净胜球分层: 0, 1, 2, 3, 4, 5+
bins = defaultdict(lambda: [0,0,0,0])  # [对数, 次回合领先方进球和, 落后方进球和, 次回合大球数]
for first, second in tie_pairs:
    margin = abs(first['gh'] - first['ga'])
    if margin >= 5:
        key = '净胜5+'
    elif margin == 4:
        key = '净胜4'
    elif margin == 3:
        key = '净胜3'
    elif margin == 2:
        key = '净胜2'
    elif margin == 1:
        key = '净胜1'
    else:
        key = '净胜0(平局)'
    
    if first['gh'] >= first['ga']:
        lead = first['home_name']
    else:
        lead = first['away_name']
    
    if second['home_name'] == lead:
        lg = second['gh']; tg = second['ga']
    else:
        lg = second['ga']; tg = second['gh']
    total2 = second['gh'] + second['ga']
    
    bins[key][0] += 1
    bins[key][1] += lg
    bins[key][2] += tg
    if total2 >= 3:
        bins[key][3] += 1

print('=== 想法二扩展: 首回合净胜球分层 vs 次回合 ===')
print(f'{"首回合净胜":<12} {"对数":>6} {"次回合领先方场均":>10} {"落后方场均":>10} {"大球率≥3":>9}')
order = ['净胜0(平局)', '净胜1', '净胜2', '净胜3', '净胜4', '净胜5+']
for key in order:
    g = bins[key]
    n = g[0]
    if n == 0:
        print(f'{key:<12} {n:>6}  (无样本)')
        continue
    print(f'{key:<12} {n:>6} {g[1]/n:>10.2f} {g[2]/n:>10.2f} {g[3]/n*100:>8.1f}%')
