import csv
from collections import defaultdict
ou_acc={'Over':[0,0],'Under':[0,0]}
league_ou=defaultdict(lambda: [0,0])

with open('data/Matches.csv','r',encoding='utf-8',errors='ignore') as f:
    for row in csv.DictReader(f):
        o25=row.get('Over25',''); u25=row.get('Under25','')
        if not o25 or not u25: continue
        try:
            o25f=float(o25); u25f=float(u25)
            if o25f<1.01 or u25f<1.01: continue
            fhg=int(float(row.get('FTHome','0') or 0))
            fag=int(float(row.get('FTAway','0') or 0))
        except: continue
        tg=fhg+fag
        div=row.get('Division','')
        ou_pred='Over' if o25f<u25f else 'Under'
        ou_actual='Over' if tg>2.5 else 'Under'
        correct=(ou_pred==ou_actual)
        ou_acc[ou_pred][0]+=1
        if correct: ou_acc[ou_pred][1]+=1
        league_ou[div][0]+=1
        if correct: league_ou[div][1]+=1

names={'E0':'PL','D1':'BL','I1':'SA','SP1':'LL','F1':'L1','N1':'ED','P1':'PL','SWE':'AS','NOR':'ES','FIN':'VL','JAP':'J1','CHN':'CSL','B1':'JL','T1':'SL','G1':'GS','SC0':'SP'}
total=sum(v[0] for v in ou_acc.values())
print(f'== 5. O/U ({total:,}) ==')
for k in ['Over','Under']:
    t,c=ou_acc[k]
    print(f'{k:<8} {t:>8,}  {c/t*100:>5.1f}%')
print(f'== 5+. League O/U (top15) ==')
for div,(t,c) in sorted(league_ou.items(),key=lambda x:x[1][0],reverse=True)[:15]:
    if t<500: continue
    print(f'{names.get(div,div):<8} {t:>8,}  {c/t*100:>5.1f}%')
