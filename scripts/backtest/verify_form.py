#!/usr/bin/env python
# 验证: 近期状态(Form3/Form5积分) vs 胜率
import csv

def parse_form(v):
    try:
        return float(v)
    except:
        return None

# Form3Home 分组(0-9分) -> 主胜率
f3 = {}  # 分值 -> [总, 主胜]
f5 = {}
with open('data/Matches.csv','r',encoding='utf-8',errors='ignore') as f:
    for row in csv.DictReader(f):
        ft = row.get('FTResult','')
        if ft not in ('H','D','A'):
            continue
        f3h = parse_form(row.get('Form3Home',''))
        f5h = parse_form(row.get('Form5Home',''))
        oh = row.get('OddHome',''); oa = row.get('OddAway','')
        if f3h is not None and f3h >= 0:
            if f3h not in f3: f3[f3h]=[0,0]
            f3[f3h][0]+=1
            if ft=='H': f3[f3h][1]+=1
        if f5h is not None and f5h >= 0:
            if f5h not in f5: f5[f5h]=[0,0]
            f5[f5h][0]+=1
            if ft=='H': f5[f5h][1]+=1

print('=== Form3Home(近3场积分) vs 主胜率 ===')
print(f'{"积分":<6} {"样本":>8} {"主胜率":>8}')
for k in sorted(f3.keys()):
    g=f3[k]; print(f'{k:<6} {g[0]:>8,} {g[1]/g[0]*100:>7.1f}%')

print()
print('=== Form5Home(近5场积分) vs 主胜率 ===')
print(f'{"积分":<6} {"样本":>8} {"主胜率":>8}')
for k in sorted(f5.keys()):
    g=f5[k]; print(f'{k:<6} {g[0]:>8,} {g[1]/g[0]*100:>7.1f}%')
