#!/usr/bin/env python
# 验证: 平赔是否有独立增量(控制skew后)
import csv

# 均势盘(skew<50%)里，平赔分层 vs 平局率
bins = {}
with open('data/Matches.csv','r',encoding='utf-8',errors='ignore') as f:
    for row in csv.DictReader(f):
        oh=row.get('OddHome',''); od=row.get('OddDraw',''); oa=row.get('OddAway','')
        ft=row.get('FTResult','')
        if not oh or not od or not oa: continue
        try:
            oh_f=float(oh); od_f=float(od); oa_f=float(oa)
            if oh_f<1.01 or od_f<1.01 or oa_f<1.01: continue
        except: continue
        if ft not in ('H','D','A'): continue
        skew=abs(oh_f-oa_f)/min(oh_f,oa_f)
        if skew>0.5: continue  # 只取均势盘
        
        if od_f<3.0: k='平赔<3.0'
        elif od_f<3.5: k='平赔3.0-3.5'
        elif od_f<4.0: k='平赔3.5-4.0'
        else: k='平赔>4.0'
        if k not in bins: bins[k]=[0,0]
        bins[k][0]+=1
        if ft=='D': bins[k][1]+=1

print('=== 均势盘(skew<50%)里，平赔分层 vs 平局率 ===')
print(f'{"平赔分层":<12} {"样本":>9} {"平局率":>8}')
for k in ['平赔<3.0','平赔3.0-3.5','平赔3.5-4.0','平赔>4.0']:
    if k in bins:
        g=bins[k]; print(f'{k:<12} {g[0]:>9,} {g[1]/g[0]*100:>7.1f}%')
