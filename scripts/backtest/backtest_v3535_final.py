#!/usr/bin/env python3
"""V3.5.35 全模型回测——模拟方向决策+修正34/35/32/14"""

import csv
from collections import defaultdict

# 分层跟踪：修正触发后的准确率变化
results = {
    'baseline': [0,0],           # 全部
    'mild_consensus': [0,0],     # 修正32温和共识
    'extreme_consensus': [0,0],  # 修正32极端共识
    'deep_odds': [0,0],          # 修正14 <1.30深盘
    'away_dir': [0,0],           # 修正34 客胜方向
    'away_deep': [0,0],          # 修正34+14 客胜深盘=互相抵消
    'max_low': [0,0],            # 修正35 Max分歧<5%
    'max_high': [0,0],           # 修正35 Max分歧>10%
    'away_mild': [0,0],          # 修正34+32 客胜+温和共识=两级降
    'away_max_low': [0,0],       # 修正34+35 客胜+Max<5%=两重
    'triple_warn': [0,0],        # 修正34+32+35 三级全触发
    'clean': [0,0],              # 无任何修正触发
}

league = defaultdict(lambda: [0,0])

with open('data/Matches.csv','r',encoding='utf-8',errors='ignore') as f:
    for row in csv.DictReader(f):
        oh=row.get('OddHome',''); od=row.get('OddDraw',''); oa=row.get('OddAway','')
        mh=row.get('MaxHome',''); ma=row.get('MaxAway','')
        if not oh or not od or not oa: continue
        try:
            h=float(oh); d=float(od); a=float(oa)
            if h<1.01 or d<1.01 or a<1.01: continue
        except: continue
        result=row.get('FTResult','')
        if result not in ('H','D','A'): continue
        div=row.get('Division','')
        
        # 方向
        if h<a and h<d: pred='H'
        elif a<h and a<d: pred='A'
        else: pred='D'
        correct=(pred==result)
        results['baseline'][0]+=1; results['baseline'][1]+=int(correct)
        league[div][0]+=1
        if correct: league[div][1]+=1
        
        # 修正信号
        is_deep=(min(h,a)<1.30)
        is_away=(pred=='A')
        is_mild=(pred!='D' and 1.0<abs(h-a)/min(h,a)<=2.0)
        is_extreme=(pred!='D' and abs(h-a)/min(h,a)>2.0)
        
        max_div=False; max_high=False
        if mh and ma:
            try:
                mhf=float(mh); maf=float(ma)
                if mhf>h and maf>a:
                    spread=(mhf-h)/h+(maf-a)/a
                    if spread<0.05: max_div=True
                    if spread>0.10: max_high=True
            except: pass
        
        # 分层统计
        if is_deep:
            results['deep_odds'][0]+=1; results['deep_odds'][1]+=int(correct)
        if is_away:
            results['away_dir'][0]+=1; results['away_dir'][1]+=int(correct)
        if is_mild:
            results['mild_consensus'][0]+=1; results['mild_consensus'][1]+=int(correct)
        if is_extreme:
            results['extreme_consensus'][0]+=1; results['extreme_consensus'][1]+=int(correct)
        if max_div:
            results['max_low'][0]+=1; results['max_low'][1]+=int(correct)
        if max_high:
            results['max_high'][0]+=1; results['max_high'][1]+=int(correct)
        
        # 组合触发
        if is_away and is_deep:
            results['away_deep'][0]+=1; results['away_deep'][1]+=int(correct)
        if is_away and is_mild:
            results['away_mild'][0]+=1; results['away_mild'][1]+=int(correct)
        if is_away and max_div:
            results['away_max_low'][0]+=1; results['away_max_low'][1]+=int(correct)
        if is_away and is_mild and max_div:
            results['triple_warn'][0]+=1; results['triple_warn'][1]+=int(correct)
        if not is_away and not is_mild and not is_deep and not max_div:
            results['clean'][0]+=1; results['clean'][1]+=int(correct)

print('='*50)
print('V3.5.35 新模型回测——信号分层准确率')
print('='*50)
print(f'总场次: {results["baseline"][0]:,}')
print(f'基准(赔率最低方向): {results["baseline"][1]/results["baseline"][0]*100:.1f}%')
print()

print(f'{"信号层":<20} {"场次":>8} {"准确率":>8}')
print('-'*40)
for label,key in [
    ('[深盘] <1.30', 'deep_odds'),
    ('[极端] 共识>200%', 'extreme_consensus'),
    ('[分歧] Max>10%', 'max_high'),
    ('[纯净] 无修正', 'clean'),
    ('[抵消] 客胜+深盘', 'away_deep'),
    ('[W1] 客胜方向', 'away_dir'),
    ('[W2] 温和共识', 'mild_consensus'),
    ('[W3] Max分歧<5%', 'max_low'),
    ('[W4] 客胜+温和', 'away_mild'),
    ('[W5] 客胜+Max低', 'away_max_low'),
    ('[W6] 三级全触发', 'triple_warn'),
]:
    t,c=results[key]
    if t>0:
        bar='█'*int(c/t*30)
        flag='OK' if c/t*100>55 else ('??' if c/t*100>47 else 'XX')
        print(f'{flag} {label:<16} {t:>7,}  {c/t*100:>5.1f}%  {bar}')

print()
print('='*50)
print('结论: 模型信号分层有效性')
print('='*50)
# 计算分层效果
if results['clean'][0]>0:
    clean_acc=results['clean'][1]/results['clean'][0]*100
    print(f'无修正触发(clean):      {clean_acc:.1f}% (基准)')
if results['triple_warn'][0]>100:
    tw=results['triple_warn'][1]/results['triple_warn'][0]*100
    print(f'三级全触发(最差case):    {tw:.1f}% (应降级)')
    print(f'分层效果: clean vs triple = {clean_acc-tw:+.1f}pp')
