#!/usr/bin/env python
# 验证: 让球深度HandiSize vs 主胜准确率 + ELO差距分层
import csv

# 让球深度 vs 主胜准确率
handi = {}
# ELO差距分层 vs 主胜准确率(全样本)
elo = {}

with open('data/Matches.csv','r',encoding='utf-8',errors='ignore') as f:
    for row in csv.DictReader(f):
        ft=row.get('FTResult','')
        if ft not in ('H','D','A'): continue
        hs=row.get('HandiSize',''); hh=row.get('HandiHome','')
        eh=row.get('HomeElo',''); ea=row.get('AwayElo','')
        
        # 让球深度(绝对值)
        if hs and hh:
            try:
                sz=abs(float(hs)); hh_f=float(hh)
                if sz>0 and hh_f>0:
                    if sz<=0.25: k='让≤0.25'
                    elif sz<=0.5: k='让0.5'
                    elif sz<=0.75: k='让0.75'
                    elif sz<=1.0: k='让1.0'
                    else: k='让>1.0'
                    if k not in handi: handi[k]=[0,0]
                    handi[k][0]+=1
                    if ft=='H': handi[k][1]+=1
            except: pass
        
        # ELO差距
        if eh and ea:
            try:
                gap=float(eh)-float(ea)
                if gap < -100: k='ELO差<-100'
                elif gap < -50: k='ELO差-100~-50'
                elif gap < 0: k='ELO差-50~0'
                elif gap < 50: k='ELO差0~50'
                elif gap < 100: k='ELO差50~100'
                else: k='ELO差>100'
                if k not in elo: elo[k]=[0,0]
                elo[k][0]+=1
                if ft=='H': elo[k][1]+=1
            except: pass

print('=== 让球深度 vs 主胜准确率 ===')
print(f'{"让球深度":<10} {"样本":>9} {"主胜率":>8}')
for k in ['让≤0.25','让0.5','让0.75','让1.0','让>1.0']:
    if k in handi:
        g=handi[k]; print(f'{k:<10} {g[0]:>9,} {g[1]/g[0]*100:>7.1f}%')

print()
print('=== ELO差距分层 vs 主胜率 ===')
print(f'{"ELO差距":<14} {"样本":>9} {"主胜率":>8}')
for k in ['ELO差<-100','ELO差-100~-50','ELO差-50~0','ELO差0~50','ELO差50~100','ELO差>100']:
    if k in elo:
        g=elo[k]; print(f'{k:<14} {g[0]:>9,} {g[1]/g[0]*100:>7.1f}%')
