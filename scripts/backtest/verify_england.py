#!/usr/bin/env python
# 计算英格兰各级联赛(E0英超/E1英冠/E2英甲/E3英乙)的抽水率
import csv
from collections import defaultdict

# 联赛名映射
names = {'E0':'英超', 'E1':'英冠', 'E2':'英甲', 'E3':'英乙'}

# 每个联赛: [场次, 抽水和, 大球率和, 主胜率]
stats = defaultdict(lambda: [0, 0.0, 0, 0])

with open('data/Matches.csv','r',encoding='utf-8',errors='ignore') as f:
    for row in csv.DictReader(f):
        div = row.get('Division','')
        if div not in names:
            continue
        oh=row.get('OddHome',''); od=row.get('OddDraw',''); oa=row.get('OddAway','')
        ft=row.get('FTResult','')
        try:
            oh_f=float(oh); od_f=float(od); oa_f=float(oa)
            if oh_f<1.01 or od_f<1.01 or oa_f<1.01: continue
        except: continue
        stats[div][0] += 1
        stats[div][1] += (1/oh_f + 1/od_f + 1/oa_f - 1)
        # 大球率(总进球>=3)
        try:
            fh=int(float(row.get('FTHome','0'))); fa=int(float(row.get('FTAway','0')))
            if fh+fa>=3: stats[div][2]+=1
        except: pass
        if ft=='H': stats[div][3]+=1

print('=== 英格兰各级联赛抽水基准 ===')
print(f'{"联赛":<6} {"场次":>8} {"平均抽水":>8} {"大球率":>8} {"主胜率":>8}')
for div in ['E0','E1','E2','E3']:
    s=stats[div]
    n=s[0]
    if n==0: continue
    print(f'{names[div]:<6} {n:>8,} {s[1]/n*100:>7.2f}% {s[2]/n*100:>7.1f}% {s[3]/n*100:>7.1f}%')
