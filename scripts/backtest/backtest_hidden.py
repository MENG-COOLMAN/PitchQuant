import csv
from collections import defaultdict

# [total,correct, H_t,H_c, A_t,A_c]
div_acc=defaultdict(lambda: [0,0,0,0,0,0])
max_div={'low_div':[0,0],'mid_div':[0,0],'high_div':[0,0]}
draw_sig=defaultdict(lambda: [0,0])

with open('data/Matches.csv','r',encoding='utf-8',errors='ignore') as f:
    for row in csv.DictReader(f):
        oh=row.get('OddHome',''); od=row.get('OddDraw',''); oa=row.get('OddAway','')
        mh=row.get('MaxHome',''); md=row.get('MaxDraw',''); ma=row.get('MaxAway','')
        if not oh or not od or not oa: continue
        try:
            h=float(oh); d=float(od); a=float(oa)
            if h<1.01 or d<1.01 or a<1.01: continue
        except: continue
        result=row.get('FTResult','')
        if result not in ('H','D','A'): continue
        div=row.get('Division','')
        
        if h<a and h<d: pred='H'
        elif a<h and a<d: pred='A'
        else: pred='D'
        correct=(pred==result)
        
        drow=div_acc[div]
        drow[0]+=1
        if correct: drow[1]+=1
        if pred=='H': drow[2]+=1; drow[3]+=int(correct)
        if pred=='A': drow[4]+=1; drow[5]+=int(correct)
        
        # Max赔率分歧
        if mh and ma:
            try:
                mhf=float(mh); maf=float(ma)
                if mhf>h and maf>a:
                    spread=(mhf-h)/h+(maf-a)/a
                    if spread<0.05: k='low'
                    elif spread<0.10: k='mid'
                    else: k='high'
                    max_div[k][0]+=1
                    if correct: max_div[k][1]+=1
            except: pass
        
        # 平局条件: odds within 15%
        if pred!='D' and abs(h-a)/min(h,a)<0.15:
            draw_sig['close'][0]+=1
            if result=='D': draw_sig['close'][1]+=1

names={'E0':'PL','D1':'BL','I1':'SA','SP1':'LL','F1':'L1','N1':'ED','P1':'PT','SWE':'SE','NOR':'NO','FIN':'FI','JAP':'J1','CHN':'CS'}
print('== 隐藏1: H vs A 准确率不对称 ==')
for div,d in sorted(div_acc.items(),key=lambda x:x[1][0],reverse=True):
    if d[0]<2000: continue
    n=names.get(div,div)
    ha=d[3]/d[2]*100 if d[2]>0 else 0
    aa=d[5]/d[4]*100 if d[4]>0 else 0
    print(f'{n:<6} H:{d[2]:>6,} @{ha:.1f}% A:{d[4]:>6,} @{aa:.1f}% gap={ha-aa:+.1f}%')

print('\n== 隐藏2: Max赔率分歧度 vs 准确率 ==')
for k in ['low','mid','high']:
    t,c=max_div[k]
    if t: print(f'{k:<10} {t:>8,}  {c/t*100:>5.1f}%')

print('\n== 隐藏3: 势均力敌(odds<15%差异) 平局率 ==')
t,c=draw_sig['close']
print(f'{t:,}场势均力敌, 其中平局{c}场({c/t*100:.1f}%)')
