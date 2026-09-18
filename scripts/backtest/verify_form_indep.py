#!/usr/bin/env python
# 验证: Form状态 是否独立于赔率(增量价值)
# 在均势盘(赔率接近)里，Form高的球队是否胜率更高
import csv

def pf(v):
    try: return float(v)
    except: return None

# 均势盘(主客赔率接近, skew<50%) 里，Form3主-Form3客 差异 vs 主胜率
groups = {'form差<0(主队状态差)': [0,0], 'form差0(状态相当)': [0,0], 'form差>0(主队状态好)': [0,0]}

with open('data/Matches.csv','r',encoding='utf-8',errors='ignore') as f:
    for row in csv.DictReader(f):
        oh = pf(row.get('OddHome','')); oa = pf(row.get('OddAway',''))
        if not oh or not oa: continue
        if oh<1.01 or oa<1.01: continue
        skew = abs(oh-oa)/min(oh,oa)
        if skew > 0.5: continue  # 只取均势盘
        ft = row.get('FTResult','')
        if ft not in ('H','D','A'): continue
        f3h = pf(row.get('Form3Home','')); f3a = pf(row.get('Form3Away',''))
        if f3h is None or f3a is None: continue
        diff = f3h - f3a
        if diff < -1:
            key = 'form差<0(主队状态差)'
        elif diff > 1:
            key = 'form差>0(主队状态好)'
        else:
            key = 'form差0(状态相当)'
        groups[key][0]+=1
        if ft=='H': groups[key][1]+=1

print('=== 均势盘(赔率接近)下，Form状态差异 vs 主胜率 ===')
print(f'{"分组":<22} {"样本":>8} {"主胜率":>8}')
for key in ['form差<0(主队状态差)','form差0(状态相当)','form差>0(主队状态好)']:
    g=groups[key]; n=g[0]
    if n==0: continue
    print(f'{key:<22} {n:>8,} {g[1]/n*100:>7.1f}%')
