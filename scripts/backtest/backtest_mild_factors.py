import csv
from collections import defaultdict

# 温和共识(100-200% skew) + 额外因子回测
mild_extra = defaultdict(lambda: [0,0])

with open('data/Matches.csv','r',encoding='utf-8',errors='ignore') as f:
    for row in csv.DictReader(f):
        oh=row.get('OddHome',''); od=row.get('OddDraw',''); oa=row.get('OddAway','')
        if not oh or not od or not oa: continue
        try:
            h=float(oh); d=float(od); a=float(oa)
            if h<1.01 or d<1.01 or a<1.01: continue
        except: continue
        result=row.get('FTResult','')
        if result not in ('H','D','A'): continue
        div=row.get('Division','')
        
        if h<a and h<d: pred='H'; fav_odd=h; dog_odd=a
        elif a<h and a<d: pred='A'; fav_odd=a; dog_odd=h
        else: continue
        
        skew=abs(h-a)/min(h,a)
        if not (1.0<skew<=2.0): continue  # only mild consensus
        
        correct=(pred==result)
        
        # 基础统计
        mild_extra['ALL'][0]+=1; mild_extra['ALL'][1]+=int(correct)
        
        # Factor 1: odds level
        if fav_odd<1.50: mild_extra['fav<1.50'][0]+=1; mild_extra['fav<1.50'][1]+=int(correct)
        elif fav_odd<1.70: mild_extra['fav<1.70'][0]+=1; mild_extra['fav<1.70'][1]+=int(correct)
        elif fav_odd<2.00: mild_extra['fav<2.00'][0]+=1; mild_extra['fav<2.00'][1]+=int(correct)
        else: mild_extra['fav>2.00'][0]+=1; mild_extra['fav>2.00'][1]+=int(correct)
        
        # Factor 2: O/U direction
        o25=row.get('Over25',''); u25=row.get('Under25','')
        if o25 and u25:
            try:
                o25f=float(o25); u25f=float(u25)
                if o25f<u25f: mild_extra['mild+Over'][0]+=1; mild_extra['mild+Over'][1]+=int(correct)
                else: mild_extra['mild+Under'][0]+=1; mild_extra['mild+Under'][1]+=int(correct)
            except: pass
        
        # Factor 3: Asian handicap agreement
        hsz=row.get('HandiSize',''); hho=row.get('HandiHome',''); hao=row.get('HandiAway','')
        if hsz and hho and hao:
            try:
                sz=float(hsz); hh=float(hho); ha=float(hao)
                if sz!=0:
                    asian_fav='H' if hh<ha else 'A'
                    if asian_fav==pred: mild_extra['mild+AsianOK'][0]+=1; mild_extra['mild+AsianOK'][1]+=int(correct)
                    else: mild_extra['mild+AsianNG'][0]+=1; mild_extra['mild+AsianNG'][1]+=int(correct)
            except: pass
        
        # Factor 4: Division (top 5 vs lower)
        top5=('E0','D1','I1','SP1','F1')
        if div in top5: mild_extra['mild+Big5'][0]+=1; mild_extra['mild+Big5'][1]+=int(correct)
        else: mild_extra['mild+Other'][0]+=1; mild_extra['mild+Other'][1]+=int(correct)

        # Factor 5: draw odds level
        if d<3.0: mild_extra['draw_short'][0]+=1; mild_extra['draw_short'][1]+=int(correct)
        elif d<4.0: mild_extra['draw_mid'][0]+=1; mild_extra['draw_mid'][1]+=int(correct)
        else: mild_extra['draw_long'][0]+=1; mild_extra['draw_long'][1]+=int(correct)
        
        # Factor 6: overround (抽水)
        ov=1/h+1/d+1/a-1
        if ov<0.06: mild_extra['low_ov'][0]+=1; mild_extra['low_ov'][1]+=int(correct)
        elif ov<0.08: mild_extra['mid_ov'][0]+=1; mild_extra['mid_ov'][1]+=int(correct)
        else: mild_extra['high_ov'][0]+=1; mild_extra['high_ov'][1]+=int(correct)

print('=== 温和共识(46K场) + 额外因子 ===')
print(f'ALL: {mild_extra["ALL"][0]:,}场  {mild_extra["ALL"][1]/mild_extra["ALL"][0]*100:.1f}%')
print()

for label,key in [
    ('--- 赔率层级 ---',None),
    ('热门<1.50','fav<1.50'),('热门<1.70','fav<1.70'),('热门<2.00','fav<2.00'),('热门>2.00','fav>2.00'),
    ('--- O/U方向 ---',None),
    ('+大球倾向','mild+Over'),('+小球倾向','mild+Under'),
    ('--- 亚盘一致 ---',None),
    ('+亚盘同向','mild+AsianOK'),('+亚盘反向','mild+AsianNG'),
    ('--- 联赛 ---',None),
    ('+五大联赛','mild+Big5'),('+非五大','mild+Other'),
    ('--- 平赔 ---',None),
    ('平赔<3.0','draw_short'),('平赔3-4','draw_mid'),('平赔>4.0','draw_long'),
    ('--- 抽水 ---',None),
    ('低抽<6%','low_ov'),('中抽6-8%','mid_ov'),('高抽>8%','high_ov'),
]:
    if key is None: print(label); continue
    if key in mild_extra:
        t,c=mild_extra[key]
        acc=c/t*100
        gap=acc-mild_extra['ALL'][1]/mild_extra['ALL'][0]*100
        print(f'  {label:<20} {t:>7,}  {acc:>5.1f}%  ({gap:+.1f}pp)')
