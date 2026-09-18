import csv
res={}; ALL='ALL'
with open('data/Matches.csv','r',encoding='utf-8',errors='ignore') as f:
    for row in csv.DictReader(f):
        oh=row.get('OddHome',''); od=row.get('OddDraw',''); oa=row.get('OddAway','')
        mh=row.get('MaxHome',''); ma=row.get('MaxAway','')
        if not oh or not od or not oa or not mh or not ma: continue
        try:
            h=float(oh); d=float(od); a=float(oa); mhf=float(mh); maf=float(ma)
            if h<1.01 or d<1.01 or a<1.01: continue
        except: continue
        result=row.get('FTResult','')
        if result not in ('H','D','A'): continue
        if h<a and h<d: pred='H'; fav=h
        elif a<h and a<d: pred='A'; fav=a
        else: continue
        spread=(mhf-h)/h+(maf-a)/a
        if spread<=0.10: continue
        correct=(pred==result)
        r=res; r[ALL]=r.get(ALL,[0,0]); r[ALL][0]+=1; r[ALL][1]+=int(correct)
        if fav<1.50: k='f150'
        elif fav<1.70: k='f170'
        elif fav<2.00: k='f200'
        else: k='f201'
        r[k]=r.get(k,[0,0]); r[k][0]+=1; r[k][1]+=int(correct)
        if d>4.0: k='d4a'
        elif d<3.0: k='d3b'
        else: k='d3x'
        r[k]=r.get(k,[0,0]); r[k][0]+=1; r[k][1]+=int(correct)
        ov=1/h+1/d+1/a-1
        if ov<0.06: k='ovA'
        elif ov<0.08: k='ovB'
        else: k='ovC'
        r[k]=r.get(k,[0,0]); r[k][0]+=1; r[k][1]+=int(correct)
        o25=row.get('Over25',''); u25=row.get('Under25','')
        try: fhg=int(float(row.get('FTHome','0') or 0)); fag=int(float(row.get('FTAway','0') or 0))
        except: continue
        tg=fhg+fag
        if o25 and u25:
            try:
                o25f=float(o25); u25f=float(u25)
                ou_pred='O' if o25f<u25f else 'U'
                ou_act='O' if tg>2.5 else 'U'
                r['ou_t']=r.get('ou_t',[0,0]); r['ou_t'][0]+=1
                if correct and r['ou_t'][1]>=0: r['ou_t'][1]+=1
                if correct and ou_pred==ou_act:
                    k='d_ou'; r[k]=r.get(k,[0,0]); r[k][0]+=1; r[k][1]+=1
            except: pass

base=res[ALL][1]/res[ALL][0]*100
print('Max divergence >10%')
print('---')
print('base: %d games, %.1f%%' % (res[ALL][0], base))
for k,lab in [('f150','fav<1.50'),('f170','fav<1.70'),('f200','fav<2.00'),('f201','fav>2.00')]:
    if k in res: t,c=res[k]; print('  %s: %d, %.1f%% (%+.1fpp)' % (lab,t,c/t*100,c/t*100-base))
for k,lab in [('d3b','draw<3'),('d3x','draw3-4'),('d4a','draw>4')]:
    if k in res: t,c=res[k]; print('  %s: %d, %.1f%% (%+.1fpp)' % (lab,t,c/t*100,c/t*100-base))
for k,lab in [('ovA','ovr<6%%'),('ovB','ovr6-8%%'),('ovC','ovr>8%%')]:
    if k in res: t,c=res[k]; print('  %s: %d, %.1f%% (%+.1fpp)' % (lab,t,c/t*100,c/t*100-base))
if 'd_ou' in res: t,c=res['d_ou']; print('  dir+OUbothOK: %d, %.1f%%' % (t,c/t*100))
if 'ou_t' in res: print('  ou_total+dirOK: %d, %.1f%%' % (res['ou_t'][0],res['ou_t'][1]/res['ou_t'][0]*100))
