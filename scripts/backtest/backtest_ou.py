import csv
from collections import defaultdict

ou_acc=defaultdict(lambda: [0,0])  # [t,c]
league_ou=defaultdict(lambda: [0,0])

with open('data/Matches.csv','r',encoding='utf-8',errors='ignore') as f:
    for row in csv.DictReader(f):
        o25=row.get('Over25',''); u25=row.get('Under25','')
        if not o25 or not u25: continue
        try:
            o25f=float(o25); u25f=float(u25)
            fhg=int(float(row.get('FTHome','0') or 0))
            fag=int(float(row.get('FTAway','0') or 0))
        except: continue
        tg=fhg+fag
        div=row.get('Division','')
        ou_pred='O' if o25f<u25f else 'U'
        ou_actual='O' if tg>2.5 else 'U'
        correct=(ou_pred==ou_actual)
        ou_acc[ou_pred][0]+=1
        if correct: ou_acc[ou_pred][1]+=1
        league_ou[div][0]+=1
        if correct: league_ou[div][1]+=1

names={'E0':'英超','D1':'德甲','I1':'意甲','SP1':'西甲','F1':'法甲',
    'N1':'荷甲','P1':'葡超','SWE':'瑞超','NOR':'挪超','FIN':'芬超',
    'JAP':'日职','CHN':'中超','B1':'比甲','T1':'土超','G1':'希腊超','SC0':'苏超'}
total=sum(v[0] for v in ou_acc.values())
print(f'== 5. 大小球预测 ({total:,}场) ==')
for k in ['Over','Under']:
    t,c=ou_acc[k]
    if t: print(f'{k:<8} {t:>8,}场  {c/t*100:>5.1f}%  {"█"*int(c/t*40)}')
print(f'== 5+. 联赛大小球准确率(前15) ==')
for div,(t,c) in sorted(league_ou.items(),key=lambda x:x[1][0],reverse=True)[:15]:
    if t<500: continue
    print(f'{names.get(div,div):<10} {t:>6,}场  {c/t*100:>5.1f}%')
