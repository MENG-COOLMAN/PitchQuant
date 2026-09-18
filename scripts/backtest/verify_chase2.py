#!/usr/bin/env python
# 补充: 次回合半场比分形态 vs 全场大球(验证"追逐"是否持续)
import json
from collections import defaultdict
from datetime import datetime

with open('data/euro_halftime.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

pairs = defaultdict(list)
for m in data.values():
    key = tuple(sorted([m['home'], m['away']]))
    pairs[key].append(m)

tie_pairs = []
for key, ms in pairs.items():
    if len(ms) != 2:
        continue
    if ms[0]['home'] == ms[1]['home']:
        continue
    dt1 = datetime.strptime(ms[0]['date'][:10], '%Y-%m-%d')
    dt2 = datetime.strptime(ms[1]['date'][:10], '%Y-%m-%d')
    if abs((dt2-dt1).days) > 14:
        continue
    first, second = (ms[0], ms[1]) if dt1 < dt2 else (ms[1], ms[0])
    tie_pairs.append((first, second))

# 首回合差距不大的次回合，按半场比分形态分组
# 半场0:0 / 半场1:0或0:1(单方) / 半场1:1(双方) / 半场2球+(大)
groups = defaultdict(lambda: [0,0,0])  # [对数, 大球数, 总进球和]
for first, second in tie_pairs:
    margin1 = abs(first['gh'] - first['ga'])
    if margin1 > 1:
        continue  # 只关注首回合差距不大
    hth = second['hth']; hta = second['hta']
    ht_total = hth + hta
    ft_total = second['gh'] + second['ga']
    is_over = ft_total >= 3
    
    if ht_total == 0:
        key = '半场0:0'
    elif ht_total == 1:
        key = '半场1:0(单方)'
    elif ht_total == 2 and (hth == 2 or hta == 2):
        key = '半场2:0(单方)'
    elif ht_total == 2:
        key = '半场1:1(双方)'
    else:
        key = '半场3球+(已大)'
    
    groups[key][0] += 1
    if is_over: groups[key][1] += 1
    groups[key][2] += ft_total

print('=== 首回合差距≤1 的次回合: 半场形态 vs 全场 ===')
print(f'{"半场形态":<16} {"对数":>6} {"全场大球率≥3":>10} {"场均总进球":>10}')
order = ['半场0:0', '半场1:0(单方)', '半场2:0(单方)', '半场1:1(双方)', '半场3球+(已大)']
for key in order:
    g = groups[key]
    n = g[0]
    if n == 0:
        print(f'{key:<16} {n:>6}  (无样本)')
        continue
    print(f'{key:<16} {n:>6} {g[1]/n*100:>9.1f}% {g[2]/n:>10.2f}')
