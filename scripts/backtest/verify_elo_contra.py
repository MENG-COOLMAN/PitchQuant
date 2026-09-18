#!/usr/bin/env python
# 验证 case12 模式: 深盘主胜 + 基本面背离(主队ELO弱/状态差) 是否翻车
import csv

# 深盘主胜(<1.50) 分组: ELO一致 vs ELO背离
groups = {
    '深盘主胜_ELO支持': [0,0],      # [总, 主胜命中]
    '深盘主胜_ELO背离(主弱)': [0,0],
    '深盘主胜_ELO背离(主强很多)': [0,0],
}

with open('data/Matches.csv', 'r', encoding='utf-8', errors='ignore') as f:
    for row in csv.DictReader(f):
        oh = row.get('OddHome',''); oa = row.get('OddAway','')
        eh = row.get('HomeElo',''); ea = row.get('AwayElo','')
        ft = row.get('FTResult','')
        if not oh or not oa or not eh or not ea:
            continue
        try:
            oh_f = float(oh); oa_f = float(oa)
            eh_f = float(eh); ea_f = float(ea)
        except:
            continue
        if oh_f < 1.01 or oh_f >= 1.50:
            continue  # 只取深盘主胜
        if ft not in ('H','D','A'):
            continue
        
        elo_gap = eh_f - ea_f
        if elo_gap > 50:
            key = '深盘主胜_ELO背离(主强很多)'
        elif elo_gap < 0:
            key = '深盘主胜_ELO背离(主弱)'
        else:
            key = '深盘主胜_ELO支持'
        
        groups[key][0] += 1
        if ft == 'H':
            groups[key][1] += 1

print('=== case12模式验证: 深盘主胜(OddHome<1.50) + ELO背离 ===')
print(f'{"分组":<26} {"样本":>8} {"主胜准确率":>10}')
for key in ['深盘主胜_ELO支持', '深盘主胜_ELO背离(主弱)', '深盘主胜_ELO背离(主强很多)']:
    g = groups[key]
    n = g[0]
    if n == 0:
        print(f'{key:<26} {n:>8}  (无样本)')
        continue
    print(f'{key:<26} {n:>8} {g[1]/n*100:>9.1f}%')
