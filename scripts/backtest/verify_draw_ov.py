#!/usr/bin/env python
# 验证: 平赔OddDraw单独信号 + ELO差距分层 + 抽水率vs准确率
import csv

# 1. 平赔分层 vs 平局率
draw_bins = {}
# 2. ELO差距分层 vs 主胜率(控制赔率后)
elo_bins = {}
# 3. 抽水率 vs 方向准确率
ov_bins = {}

with open('data/Matches.csv','r',encoding='utf-8',errors='ignore') as f:
    for row in csv.DictReader(f):
        oh=row.get('OddHome',''); od=row.get('OddDraw',''); oa=row.get('OddAway','')
        eh=row.get('HomeElo',''); ea=row.get('AwayElo','')
        ft=row.get('FTResult','')
        if not oh or not od or not oa: continue
        try:
            oh_f=float(oh); od_f=float(od); oa_f=float(oa)
            if oh_f<1.01 or od_f<1.01 or oa_f<1.01: continue
        except: continue
        if ft not in ('H','D','A'): continue
        
        # 1. 平赔分层
        if od_f < 3.0: dk='平赔<3.0'
        elif od_f < 3.5: dk='平赔3.0-3.5'
        elif od_f < 4.0: dk='平赔3.5-4.0'
        else: dk='平赔>4.0'
        if dk not in draw_bins: draw_bins[dk]=[0,0]
        draw_bins[dk][0]+=1
        if ft=='D': draw_bins[dk][1]+=1
        
        # 2. 抽水率 vs 方向准确率
        ov = 1/oh_f + 1/od_f + 1/oa_f - 1
        if ov < 0.05: ok='抽水<5%'
        elif ov < 0.08: ok='抽水5-8%'
        else: ok='抽水>8%'
        # 方向(赔率最低)
        if oh_f<oa_f and oh_f<od_f: pred='H'
        elif oa_f<oh_f and oa_f<od_f: pred='A'
        else: pred='D'
        if ok not in ov_bins: ov_bins[ok]=[0,0]
        ov_bins[ok][0]+=1
        if pred==ft: ov_bins[ok][1]+=1

print('=== 1. 平赔OddDraw分层 vs 平局率 ===')
print(f'{"平赔分层":<12} {"样本":>9} {"平局率":>8}')
for k in ['平赔<3.0','平赔3.0-3.5','平赔3.5-4.0','平赔>4.0']:
    if k in draw_bins:
        g=draw_bins[k]; print(f'{k:<12} {g[0]:>9,} {g[1]/g[0]*100:>7.1f}%')

print()
print('=== 2. 抽水率 vs 方向准确率 ===')
print(f'{"抽水分层":<10} {"样本":>9} {"方向准确率":>10}')
for k in ['抽水<5%','抽水5-8%','抽水>8%']:
    if k in ov_bins:
        g=ov_bins[k]; print(f'{k:<10} {g[0]:>9,} {g[1]/g[0]*100:>9.1f}%')
