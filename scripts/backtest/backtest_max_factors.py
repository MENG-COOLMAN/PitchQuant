import csv
res={}
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
        res['ALL']=res.get('ALL',[0,0]); res['ALL'][0]+=1; res['ALL'][1]+=int(correct)

        if fav<1.50: k='f<150'
        elif fav<1.70: k='f<170'
        elif fav<2.00: k='f<200'
        else: k='f>200'
        res[k]=res.get(k,[0,0]); res[k][0]+=1; res[k][1]+=int(correct)

        if d>4.0: k='d>4'
        elif d<3.0: k='d<3'
        else: k='d3-4'
        res[k]=res.get(k,[0,0]); res[k][0]+=1; res[k][1]+=int(correct)

        ov=1/h+1/d+1/a-1
        if ov<0.06: k='ov<6'
        elif ov<0.08: k='ov6-8'
        else: k='ov>8'
        res[k]=res.get(k,[0,0]); res[k][0]+=1; res[k][1]+=int(correct)

        # score consistency check
        o25=row.get('Over25',''); u25=row.get('Under25','')
        try: fhg=int(float(row.get('FTHome','0') or 0)); fag=int(float(row.get('FTAway','0') or 0))
        except: continue
        tg=fhg+fag
        if o25 and u25:
            try:
                o25f=float(o25); u25f=float(u25)
                ou_pred='O' if o25f<u25f else 'U'
                ou_act='O' if tg>2.5 else 'U'
                # direction + O/U both correct
                if correct and ou_pred==ou_act:
                    k='dir+ou_ok'
                    res[k]=res.get(k,[0,0]); res[k][0]+=1; res[k][1]+=1
                if ou_pred==ou_act:
                    k='ou_only_ok'
                    res[k]=res.get(k,[0,0]); res[k][0]+=1; res[k][1]+=1
                k='ou_total'; res[k]=res.get(k,[0,0]); res[k][0]+=1
                res[k][1]+=int(correct)
            except: pass

base=res['ALL'][1]/res['ALL'][0]*100
print(f'Max>10% base: {res.get(chr(65)+chr(76)+chr(76),[0,0])[0]} fld {base:.1f}%')
for k,lab in [('f<150','fav<1.50'),('f<170','fav<1.70'),('f<200','fav<2.00'),('f>200','fav>2.00'),
    ('d<3','draw<3'),('d3-4','draw3-4'),('d>4','draw>4'),
    ('ov<6','ovr<6%'),('ov6-8','ovr6-8%'),('ov>8','ovr>8%'),
    ('dir+ou_ok','dir+OUcorrect'),('ou_only_ok','OUcorrect'),('ou_total','OUsum')]:
    if k in res:
        t,c=res[k]; acc=c/t*100
        print(f'  {lab:<20} {t:>7,}  {acc:>5.1f}%  ({acc-base:+.1f}pp)')
