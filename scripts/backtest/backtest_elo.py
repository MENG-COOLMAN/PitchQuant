import csv

# ELO+赔率联合回测
results = {'total':[0,0,0,0,0]}  # [total, odds_ok, elo_ok, both_ok, elo_odds_agree]

elo_bins = {}  # elo gap bins

with open('data/Matches.csv','r',encoding='utf-8',errors='ignore') as f:
    for row in csv.DictReader(f):
        oh=row.get('OddHome',''); oa=row.get('OddAway',''); od=row.get('OddDraw','')
        eh=row.get('HomeElo',''); ea=row.get('AwayElo','')
        result=row.get('FTResult','')
        if not oh or not oa or not eh or not ea: continue
        try:
            h=float(oh); a=float(oa); d=float(od)
            he=float(eh); ae=float(ea)
            if h<1.01 or a<1.01: continue
        except: continue
        if result not in ('H','D','A'): continue
        
        # direction
        if h<a and h<d: odds_pred='H'
        elif a<h and a<d: odds_pred='A'
        else: odds_pred='D'
        odds_ok=(odds_pred==result)
        
        elo_pred='H' if he>ae else 'A'
        elo_ok=(elo_pred==result)
        
        both_ok=(odds_ok and elo_ok)
        agree=(odds_pred==elo_pred)
        
        r=results; r['total'][0]+=1
        r['total'][1]+=int(odds_ok); r['total'][2]+=int(elo_ok)
        r['total'][3]+=int(both_ok); r['total'][4]+=int(agree)
        
        gap=he-ae
        if gap<-300: kb='elo<-300'
        elif gap<-150: kb='elo-300~-150'
        elif gap<-50: kb='elo-150~-50'
        elif gap<50: kb='elo-50~50'
        elif gap<150: kb='elo50~150'
        elif gap<300: kb='elo150~300'
        else: kb='elo>300'
        if kb not in elo_bins: elo_bins[kb]=[0,0,0,0,0]
        elo_bins[kb][0]+=1; elo_bins[kb][1]+=int(odds_ok); elo_bins[kb][2]+=int(elo_ok)
        elo_bins[kb][3]+=int(both_ok); elo_bins[kb][4]+=int(agree)

r=results['total']
print('='*60)
print(f'ELO vs Odds: {r[0]:,} matches')
print(f'Odds direction:    {r[1]/r[0]*100:.1f}%')
print(f'ELO direction:     {r[2]/r[0]*100:.1f}%')
print(f'Both agree:        {r[4]/r[0]*100:.1f}%')
print(f'Both correct:      {r[3]/r[0]*100:.1f}%')
print()

# When they agree
agree_ok=0; agree_total=0; disagree_ok=0; disagree_total=0
with open('data/Matches.csv','r',encoding='utf-8',errors='ignore') as f:
    for row in csv.DictReader(f):
        oh=row.get('OddHome',''); oa=row.get('OddAway',''); od=row.get('OddDraw','')
        eh=row.get('HomeElo',''); ea=row.get('AwayElo','')
        result=row.get('FTResult','')
        try:
            h=float(oh); a=float(oa); d=float(od); he=float(eh); ae=float(ea)
        except: continue
        if result not in ('H','D','A'): continue
        if h<a and h<d: odds_pred='H'
        elif a<h and a<d: odds_pred='A'
        else: odds_pred='D'; continue
        elo_pred='H' if he>ae else 'A'
        both=(odds_pred==elo_pred)
        if both:
            agree_total+=1
            if odds_pred==result: agree_ok+=1
        else:
            disagree_total+=1
            if odds_pred==result: disagree_ok+=1

print(f'When ELO+Odds AGREE: {agree_ok/agree_total*100:.1f}% ({agree_total:,})')
print(f'When ELO+Odds DISAGREE: {disagree_ok/disagree_total*100:.1f}% ({disagree_total:,})')
print()

# ELO gap bins
print('Elo gap bins:')
for kb in ['elo<-300','elo-300~-150','elo-150~-50','elo-50~50','elo50~150','elo150~300','elo>300']:
    if kb in elo_bins:
        b=elo_bins[kb]; t=b[0]
        print(f'  {kb:<16} {t:>8,} odds:{b[1]/t*100:.1f}% elo:{b[2]/t*100:.1f}% agree:{b[4]/t*100:.0f}%')
