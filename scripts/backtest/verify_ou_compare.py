#!/usr/bin/env python
# 补充: 欧战首回合 vs 次回合 大球率对比
import json
from collections import defaultdict
from datetime import datetime

with open('data/fixture_index.json', 'r', encoding='utf-8') as f:
    idx = json.load(f)

EURO = {'2': '欧冠', '3': '欧联杯', '848': '欧协联'}
euro = []
for r in idx:
    if r.get('league_name') in EURO:
        euro.append(r)

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

# 首回合 vs 次回合 对比
first_stats = [0, 0, 0]  # [对数, 大球数(≥3), 总进球和]
second_stats = [0, 0, 0]
first_ou = [0,0]  # [总, 大球]
second_ou = [0,0]

for first, second in tie_pairs:
    g1 = first['gh'] + first['ga']
    g2 = second['gh'] + second['ga']
    first_stats[0] += 1
    first_stats[2] += g1
    second_stats[0] += 1
    second_stats[2] += g2
    if g1 >= 3:
        first_stats[1] += 1
        first_ou[1] += 1
    if g2 >= 3:
        second_stats[1] += 1
        second_ou[1] += 1
    first_ou[0] += 1
    second_ou[0] += 1

print(f'两回合对数: {len(tie_pairs)}')
print()
print('=== 首回合 vs 次回合 大球对比 ===')
n1 = first_stats[0]; n2 = second_stats[0]
print(f'首回合: 大球率 {first_stats[1]/n1*100:.1f}% | 场均总进球 {first_stats[2]/n1:.2f}')
print(f'次回合: 大球率 {second_stats[1]/n2*100:.1f}% | 场均总进球 {second_stats[2]/n2:.2f}')
print()

# 首回合进球分布
print('=== 首回合总进球分布(次回合大球率) ===')
dist = defaultdict(lambda: [0,0])  # 首回合进球数 -> [对数, 次回合大球数]
for first, second in tie_pairs:
    g1 = first['gh'] + first['ga']
    g2 = second['gh'] + second['ga']
    dist[g1][0] += 1
    if g2 >= 3:
        dist[g1][1] += 1

for g1 in sorted(dist.keys()):
    n = dist[g1][0]
    print(f'首回合{g1}球: {n}对 | 次回合大球率 {dist[g1][1]/n*100:.1f}%')
