#!/usr/bin/env python
# 验证想法1: 双方实力差距不大时，一方先进球(半场1:0/0:1)，落后方追平概率
import csv
from collections import defaultdict

# 分组统计
groups = {
    'skew<1.0(实力差距小)': [0,0,0,0,0],  # [总, 落后方追平, 落后方反超, 下半场有进球, 全场总进球≥3]
    'skew1.0-2.0(差距中)':  [0,0,0,0,0],
    'skew>2.0(差距大)':     [0,0,0,0,0],
}

total_half_lead = 0

with open('data/Matches.csv', 'r', encoding='utf-8', errors='ignore') as f:
    for row in csv.DictReader(f):
        hth = row.get('HTHome',''); hta = row.get('HTAway','')
        oh = row.get('OddHome',''); oa = row.get('OddAway','')
        fth = row.get('FTHome',''); fta = row.get('FTAway','')
        ft = row.get('FTResult','')
        if not hth or not hta or not oh or not oa or not fth or not fta:
            continue
        try:
            hth_i = int(float(hth)); hta_i = int(float(hta))
            oh_f = float(oh); oa_f = float(oa)
            fth_i = int(float(fth)); fta_i = int(float(fta))
        except:
            continue
        # 只取半场1:0或0:1（一方先进1球）
        if not ((hth_i==1 and hta_i==0) or (hth_i==0 and hta_i==1)):
            continue
        if oh_f < 1.01 or oa_f < 1.01:
            continue
        total_half_lead += 1
        
        # skew = |oh-oa|/min(oh,oa)
        skew = abs(oh_f-oa_f)/min(oh_f,oa_f)
        if skew < 1.0:
            key = 'skew<1.0(实力差距小)'
        elif skew <= 2.0:
            key = 'skew1.0-2.0(差距中)'
        else:
            key = 'skew>2.0(差距大)'
        
        g = groups[key]
        g[0] += 1
        
        # 半场领先方
        if hth_i > hta_i:
            leader = 'H'  # 主队领先
        else:
            leader = 'A'  # 客队领先
        
        # 全场结果
        ftd = fth_i - fta_i
        # 落后方追平(全场平局)
        if ftd == 0:
            g[1] += 1
        # 落后方反超
        if leader == 'H' and ftd < 0:
            g[2] += 1
        elif leader == 'A' and ftd > 0:
            g[2] += 1
        # 下半场有进球(全场总进球>半场总进球1球)
        if (fth_i+fta_i) > (hth_i+hta_i):
            g[3] += 1
        # 全场总进球≥3(小球变大球)
        if (fth_i+fta_i) >= 3:
            g[4] += 1

print(f'半场1:0或0:1的样本总数: {total_half_lead:,}')
print()
print('=== 想法1验证: 先进球后落后方追平/反超率 ===')
print(f'{"分组":<22} {"样本":>8} {"追平率":>8} {"反超率":>8} {"下半场进球":>10} {"变3球+":>8}')
for key in ['skew<1.0(实力差距小)', 'skew1.0-2.0(差距中)', 'skew>2.0(差距大)']:
    g = groups[key]
    n = g[0]
    if n == 0:
        continue
    print(f'{key:<22} {n:>8,} {g[1]/n*100:>7.1f}% {g[2]/n*100:>7.1f}% {g[3]/n*100:>9.1f}% {g[4]/n*100:>7.1f}%')
