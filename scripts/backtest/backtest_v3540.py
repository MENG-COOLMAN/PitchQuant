import csv
from collections import defaultdict

# 硬核层8项修正回测
HARDCORE = {
    'total': [0,0],        # 全部
    'deep': [0,0],          # 修正14: <1.30深盘
    'no_cons': [0,0],       # 修正32: 无共识<100%降级
    'mild': [0,0],          # 修正32: 温和共识100-200%不降
    'extreme': [0,0],       # 修正32: 极端共识>200%不降
    'max_low': [0,0],       # 修正35: Max<5%降级
    'max_high': [0,0],      # 修正35: Max>10%
    'mild_fav': [0,0],      # 修正36: 温和+热门<1.70
    'max_deep': [0,0],      # 修正37: Max>10%+热门<1.50
    'overturn': [0,0],      # 修正40: U2.5<1.60反转率
    'overturn_hit': [0,0],  # 修正40: 跨方向出口实际打出
    # 硬核层综合：应用所有硬核修正后的方向预测
    'hardcore_dir': [0,0],
}

league = defaultdict(lambda: [0,0])
overturn_by_league = defaultdict(lambda: [0,0,0])

with open('data/Matches.csv','r',encoding='utf-8',errors='ignore') as f:
    for row in csv.DictReader(f):
        oh=row.get('OddHome',''); od=row.get('OddDraw',''); oa=row.get('OddAway','')
        mh=row.get('MaxHome',''); ma=row.get('MaxAway','')
        o25=row.get('Over25',''); u25=row.get('Under25','')
        if not oh or not od or not oa: continue
        try:
            h=float(oh); d=float(od); a=float(oa)
            if h<1.01 or d<1.01 or a<1.01: continue
        except: continue
        result=row.get('FTResult','')
        if result not in ('H','D','A'): continue
        div=row.get('Division','')
        try: fhg=int(float(row.get('FTHome','0') or 0)); fag=int(float(row.get('FTAway','0') or 0))
        except: continue
        tg=fhg+fag

        # 方向
        if h<a and h<d: pred='H'; fav=h; dog=a
        elif a<h and a<d: pred='A'; fav=a; dog=h
        else: pred='D'; fav=min(h,a); dog=max(h,a)
        correct=(pred==result)
        HARDCORE['total'][0]+=1; HARDCORE['total'][1]+=int(correct)
        league[div][0]+=1
        if correct: league[div][1]+=1

        # 修正14
        is_deep = (min(h,a) < 1.30)
        if is_deep: HARDCORE['deep'][0]+=1; HARDCORE['deep'][1]+=int(correct)

        # 修正32 共识分级
        if pred!='D':
            skew=abs(h-a)/min(h,a)
            if skew<=1.0: HARDCORE['no_cons'][0]+=1; HARDCORE['no_cons'][1]+=int(correct)
            elif skew<=2.0: HARDCORE['mild'][0]+=1; HARDCORE['mild'][1]+=int(correct)
            else: HARDCORE['extreme'][0]+=1; HARDCORE['extreme'][1]+=int(correct)

        # 修正35 Max分歧
        if mh and ma:
            try:
                mhf=float(mh); maf=float(ma)
                if mhf>h and maf>a:
                    spread=(mhf-h)/h+(maf-a)/a
                    if spread<0.05: HARDCORE['max_low'][0]+=1; HARDCORE['max_low'][1]+=int(correct)
                    if spread>0.10: HARDCORE['max_high'][0]+=1; HARDCORE['max_high'][1]+=int(correct)
            except: pass

        # 修正36 温和+热门<1.70
        if pred!='D' and 1.0<abs(h-a)/min(h,a)<=2.0 and fav<1.70:
            HARDCORE['mild_fav'][0]+=1; HARDCORE['mild_fav'][1]+=int(correct)

        # 修正37 Max>10%+热门<1.50
        if mh and ma and fav<1.50:
            try:
                mhf=float(mh); maf=float(ma)
                if mhf>h and maf>a and (mhf-h)/h+(maf-a)/a>0.10:
                    HARDCORE['max_deep'][0]+=1; HARDCORE['max_deep'][1]+=int(correct)
            except: pass

        # 修正40 O/U极端确信反转
        if o25 and u25:
            try:
                u25f=float(u25); o25f=float(o25)
                if u25f<1.60:
                    HARDCORE['overturn'][0]+=1
                    if tg>2.5: HARDCORE['overturn'][1]+=1
                    overturn_by_league[div][0]+=1
                    if tg>2.5: overturn_by_league[div][1]+=1
                if o25f<1.60:
                    overturn_by_league[div][0]+=1
                    if tg<2.5: overturn_by_league[div][1]+=1
            except: pass

        # === 硬核层综合方向判定 ===
        hc_dir = pred  # 基准=赔率最低方向
        if is_deep:
            pass  # 深盘不降级
        if pred!='D':
            skew=abs(h-a)/min(h,a)
            if skew<=1.0:
                # 无共识→方向不可靠
                pass  # 修正32: 降级标注
            elif skew<=2.0 and fav<1.70:
                pass  # 修正36: 温和+热门→升级
            # Max分歧检查
            if mh and ma:
                try:
                    mhf=float(mh); maf=float(ma)
                    if mhf>h and maf>a:
                        spread=(mhf-h)/h+(maf-a)/a
                        if spread<0.05:
                            pass  # 修正35: Max<5%降级
                        if spread>0.10 and fav<1.50:
                            pass  # 修正37: 双重升级
                except: pass
        HARDCORE['hardcore_dir'][0]+=1
        HARDCORE['hardcore_dir'][1]+=int(correct)

# ============ 输出 ============
TOTAL=HARDCORE['total'][0]
BASE=HARDCORE['total'][1]/TOTAL*100

print('='*55)
print('V3.5.40 硬核层回测')
print(f'总场次: {TOTAL:,} | 基准: {BASE:.1f}%')
print('='*55)

print('\n--- 修正14 深盘 ---')
t,c=HARDCORE['deep']; print(f'  <1.30: {t:,} {c/t*100:.1f}%')

print('\n--- 修正32 共识分级 ---')
for k,lab in [('extreme','极端>200%'),('mild','温和100-200%'),('no_cons','无共识<100%')]:
    t,c=HARDCORE[k]; print(f'  {lab:<16} {t:>8,} {c/t*100:>5.1f}%')

print('\n--- 修正35/36/37 增强因子 ---')
for k,lab in [('max_low','Max<5%降级'),('max_high','Max>10%'),('mild_fav','温和+热<1.70'),('max_deep','Max+热<1.50')]:
    t,c=HARDCORE[k]
    if t>0: print(f'  {lab:<18} {t:>8,} {c/t*100:>5.1f}%')

print('\n--- 修正40 O/U极端确信反转 ---')
t,c=HARDCORE['overturn']
print(f'  U2.5<1.60: {t:,} 反转率{c/t*100:.1f}%')
# 联赛分组
ov_items=sorted(overturn_by_league.items(),key=lambda x:x[1][0],reverse=True)[:10]
names={'E0':'PL','D1':'BL','I1':'SA','SP1':'LL','F1':'L1','N1':'ED','P1':'PT','SP2':'LL2'}
print('   联赛排名:')
for div,(tot,rev) in ov_items:
    if tot>300: print(f'     {names.get(div,div):<6} {tot:>6,} {rev/tot*100:>5.1f}%')

print('\n--- 硬核层信号分层效果 ---')
# 分层准确率对比
BAD=HARDCORE['no_cons'][1]/HARDCORE['no_cons'][0]*100
GOOD=HARDCORE['extreme'][1]/HARDCORE['extreme'][0]*100
print(f'  无共识(降级): {BAD:.1f}%  vs  极端共识(不降): {GOOD:.1f}%  gap={GOOD-BAD:.1f}pp')
DEEP=HARDCORE['deep'][1]/HARDCORE['deep'][0]*100
print(f'  深盘(不降): {DEEP:.1f}%')
MAXG=HARDCORE['max_deep'][1]/max(1,HARDCORE['max_deep'][0])*100
print(f'  Max+热门<1.50(升级): {MAXG:.1f}%')
print(f'  整体分层分离度: {GOOD-BAD:.1f}pp')
print('='*55)
