#!/usr/bin/env python
# 验证: 半场结果 HT-FT 传导 + 红牌影响
import csv

# HT-FT 传导
ht_ft = {'H':[0,0,0], 'D':[0,0,0], 'A':[0,0,0]}  # [总, FT主胜, FT平, FT客胜] 实际用 [总,H,D,A]
ht_ft = {'H':[0,0,0,0], 'D':[0,0,0,0], 'A':[0,0,0,0]}

# 红牌影响
red_home = [0,0]  # [总, 主队输]  主队有红牌
red_away = [0,0]
no_red = [0,0]    # 无红牌对照

with open('data/Matches.csv','r',encoding='utf-8',errors='ignore') as f:
    for row in csv.DictReader(f):
        ht = row.get('HTResult','')
        ft = row.get('FTResult','')
        if ht in ('H','D','A') and ft in ('H','D','A'):
            ht_ft[ht][0]+=1
            if ft=='H': ht_ft[ht][1]+=1
            elif ft=='D': ht_ft[ht][2]+=1
            else: ht_ft[ht][3]+=1
        # 红牌
        try:
            hr = float(row.get('HomeRed','0'))
            ar = float(row.get('AwayRed','0'))
        except:
            continue
        if ft not in ('H','D','A'):
            continue
        if hr > 0:
            red_home[0]+=1
            if ft != 'H': red_home[1]+=1  # 主队红牌且没赢
        elif ar > 0:
            red_away[0]+=1
            if ft != 'A': red_away[1]+=1  # 客队红牌且没赢
        else:
            no_red[0]+=1
            # 无红牌对照(主队视角)
            if ft=='H': no_red[1]+=1

print('=== HT-FT 半场传导 ===')
print(f'{"半场":<6} {"样本":>10} {"全场主胜":>10} {"全场平":>10} {"全场客胜":>10}')
for ht in ['H','D','A']:
    g = ht_ft[ht]
    n = g[0]
    print(f'{ht:<6} {n:>10,} {g[1]/n*100:>9.1f}% {g[2]/n*100:>9.1f}% {g[3]/n*100:>9.1f}%')

print()
print('=== 红牌影响 ===')
print(f'主队有红牌: {red_home[0]:,}场, 主队未赢(平/输)率 {red_home[1]/red_home[0]*100:.1f}%')
print(f'客队有红牌: {red_away[0]:,}场, 客队未赢(平/输)率 {red_away[1]/red_away[0]*100:.1f}%')
print(f'无红牌对照: {no_red[0]:,}场, 主队胜率 {no_red[1]/no_red[0]*100:.1f}%')
