#!/usr/bin/env python
# 验证想法一(重新定义): 首回合差距不大，次回合率先追平大比分 → 比分追逐 → 大球
import json
from collections import defaultdict
from datetime import datetime

with open('data/euro_halftime.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 配对两回合
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

print(f'两回合配对: {len(tie_pairs)}对')

# 场景A: 首回合打平(净胜0)
# 场景B: 首回合净胜1
chase = {
    '首回合平局_次回合半场已进球': [0,0,0],  # [对数, 全场大球数, 全场总进球和]
    '首回合平局_次回合半场0:0':  [0,0,0],
    '首回合净胜1_次回合半场追平': [0,0,0],  # 半场时总比分追平
    '首回合净胜1_次回合半场未追平': [0,0,0],
}

for first, second in tie_pairs:
    # 首回合净胜(首回合主队视角)
    margin1 = first['gh'] - first['ga']
    
    # 次回合半场(次回合主队=首回合客队)
    # 次回合主队B, 客队A
    # B半场净胜 = hth2 - hta2
    b_ht_margin = second['hth'] - second['hta']
    
    # 总比分净胜(半场时, 首回合主队A视角) = margin1 + (A次回合半场净胜)
    # A是次回合客队, A次回合半场净胜 = hta2 - hth2 = -b_ht_margin
    total_margin_ht = margin1 - b_ht_margin
    
    total2 = second['gh'] + second['ga']
    is_over = total2 >= 3
    
    if margin1 == 0:
        # 首回合平局
        if second['hth'] + second['hta'] > 0:  # 次回合半场有人进球
            key = '首回合平局_次回合半场已进球'
        else:
            key = '首回合平局_次回合半场0:0'
        chase[key][0] += 1
        if is_over: chase[key][1] += 1
        chase[key][2] += total2
    elif abs(margin1) == 1:
        # 首回合净胜1
        if total_margin_ht == 0:  # 半场时总比分追平
            key = '首回合净胜1_次回合半场追平'
        else:
            key = '首回合净胜1_次回合半场未追平'
        chase[key][0] += 1
        if is_over: chase[key][1] += 1
        chase[key][2] += total2

print()
print('=== 想法一: 次回合率先追平大比分 → 比分追逐(大球) ===')
print(f'{"场景":<26} {"对数":>6} {"全场大球率≥3":>10} {"场均总进球":>10}')
for key in ['首回合平局_次回合半场已进球', '首回合平局_次回合半场0:0',
            '首回合净胜1_次回合半场追平', '首回合净胜1_次回合半场未追平']:
    g = chase[key]
    n = g[0]
    if n == 0:
        print(f'{key:<26} {n:>6}  (无样本)')
        continue
    print(f'{key:<26} {n:>6} {g[1]/n*100:>9.1f}% {g[2]/n:>10.2f}')
