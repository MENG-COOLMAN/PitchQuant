import csv
asian={'cover':[0,0],'no_cover':[0,0],'push':0}
asian_sz={}

with open('data/Matches.csv','r',encoding='utf-8',errors='ignore') as f:
    for row in csv.DictReader(f):
        hsz=row.get('HandiSize',''); hho=row.get('HandiHome',''); hao=row.get('HandiAway','')
        if not hsz or not hho or not hao: continue
        try: sz=float(hsz); hh=float(hho); ha=float(hao)
        except: continue
        if sz==0 or hh<=0 or ha<=0: continue
        try: fhg=int(float(row.get('FTHome','0') or 0)); fag=int(float(row.get('FTAway','0') or 0))
        except: continue
        diff=fhg-fag
        
        if hh<ha: f_dir='H'; cov_margin=sz
        else: f_dir='A'; cov_margin=-sz
        
        if f_dir=='H':
            if diff>sz: out='cover'
            elif diff==sz: out='push'
            else: out='no_cover'
        else:
            if -diff>abs(sz): out='cover'
            elif -diff==abs(sz): out='push'
            else: out='no_cover'
        
        if out=='cover': asian['cover'][0]+=1; asian['cover'][1]+=1
        elif out=='no_cover': asian['no_cover'][0]+=1
        else: asian['push']+=1
        
        a_sz=abs(sz)
        if a_sz<=0.25: k='0.25'
        elif a_sz<=0.5: k='0.5'
        elif a_sz<=0.75: k='0.75'
        elif a_sz<=1.0: k='1.0'
        elif a_sz<=1.5: k='1.5'
        else: k='1.75+'
        if k not in asian_sz: asian_sz[k]=[0,0]
        asian_sz[k][0]+=1
        if out=='cover': asian_sz[k][1]+=1

tc=asian['cover']; tn=asian['no_cover']; tp=asian['push']
ta=tc[0]+tn[0]+tp
print(f'== 4. 亚洲让球穿盘 ({ta:,}场) ==')
print(f'穿盘:   {tc[0]:>8,}场  {tc[0]/ta*100:>5.1f}%')
print(f'不穿:   {tn[0]:>8,}场  {tn[0]/ta*100:>5.1f}%')
print(f'走水:   {tp:>8,}场  {tp/ta*100:>5.1f}%')
print(f'== 4+. 让球深度 ==')
for k in ['0.25','0.5','0.75','1.0','1.5','1.75+']:
    if k in asian_sz:
        t,c=asian_sz[k]
        print(f'让{k}球: {t:>8,}场  {c/t*100:>5.1f}% 穿盘')
