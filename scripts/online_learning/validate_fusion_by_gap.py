# -*- coding: utf-8 -*-
"""融合优势场景验证（2026-09-11·用户要求"学习成果必须加入判定"）
目标: 找出现在融合理应【主导判定】的具体场景（而非全局覆盖·避免噪音）
方法: 按「市场最高概率」分档（0-38/38-45/45-50/50+）→ 各档内比较 基准 vs 融合 命中率
判据: 某档内融合显著优于基准(z>1.96) → 该档采纳融合方向为主方向（写入规则）
"""
import os, sys, io, csv, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from river import linear_model, preprocessing, compose, optim
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Matches.csv')
KEYS = ['home_odds','draw_odds','away_odds','handicap','o25_odds','league_id','elo_diff','handicap_layer',
        'form3h','form5h','form3a','form5a','shots_h','shots_a','target_h','target_a',
        'corners_h','corners_a','fouls_h','fouls_a','yellow_h','yellow_a','red_h','red_a','ht_goals','ht_result']
def f(v,d=0.0):
    try: return float(v)
    except: return d
rows=[]
with open(SRC, encoding='utf-8-sig') as fh:
    for r in csv.DictReader(fh):
        try:
            oh=float(r['OddHome']);od=float(r['OddDraw']);oa=float(r['OddAway']);h=int(float(r['FTHome']));a=int(float(r['FTAway']))
        except: continue
        if not(oh>1 and od>1 and oa>1): continue
        rows.append({'date':r['MatchDate'],'home_odds':oh,'draw_odds':od,'away_odds':oa,
          'handicap':f(r['HandiSize']),'o25_odds':f(r['Over25'],1.9),'league_id':0,'elo_diff':f(r.get('HomeElo'))-f(r.get('AwayElo')),'handicap_layer':0,
          'form3h':f(r.get('Form3Home')),'form5h':f(r.get('Form5Home')),'form3a':f(r.get('Form3Away')),'form5a':f(r.get('Form5Away')),
          'shots_h':f(r.get('HomeShots')),'shots_a':f(r.get('AwayShots')),'target_h':f(r.get('HomeTarget')),'target_a':f(r.get('AwayTarget')),
          'corners_h':f(r.get('HomeCorners')),'corners_a':f(r.get('AwayCorners')),'fouls_h':f(r.get('HomeFouls')),'fouls_a':f(r.get('AwayFouls')),
          'yellow_h':f(r.get('HomeYellow')),'yellow_a':f(r.get('AwayYellow')),'red_h':f(r.get('HomeRed')),'red_a':f(r.get('AwayRed')),
          'ht_goals':f(r.get('HTHome'))+f(r.get('HTAway')),'ht_result':1 if f(r.get('HTHome'))>f(r.get('HTAway')) else (2 if f(r.get('HTAway'))>f(r.get('HTHome')) else 0),
          '_y':1 if h>a else (2 if a>h else 0),'_o':oh,'_d':od,'_a':oa})
        if len(rows)>=30000: break
rows.sort(key=lambda x:x['date']); n=len(rows); split=int(n*0.8)
m=compose.Pipeline(preprocessing.StandardScaler(), linear_model.SoftmaxRegression(optimizer=optim.SGD(0.05)))
Y={0:'draw',1:'home',2:'away'}
for r in rows[:split]:
    try: m.learn_one({k:r[k] for k in KEYS}, Y[r['_y']])
    except: pass
W=0.10
buckets={'<38%':[0,0,0,0],'38-45%':[0,0,0,0],'45-50%':[0,0,0,0],'>=50%':[0,0,0,0]}
def bucket(mk):
    t=max(mk.values())*100
    if t<38: return '<38%'
    if t<45: return '38-45%'
    if t<50: return '45-50%'
    return '>=50%'
for r in rows[split:]:
    inv={1:1/r['_o'],0:1/r['_d'],2:1/r['_a']}; tot=sum(inv.values()); mk={k:v/tot for k,v in inv.items()}
    b=max(mk,key=mk.get)
    try:
        p=m.predict_proba_one({k:r[k] for k in KEYS}); ml={0:p.get('draw',0),1:p.get('home',0),2:p.get('away',0)}
    except: ml={0:0,1:0,2:0}
    fu={k:mk[k]*(1-W)+ml.get(k,0)*W for k in (0,1,2)}; fm=max(fu,key=fu.get)
    bk=bucket(mk)
    st=buckets[bk]
    st[0]+=1
    if b==r['_y']: st[1]+=1
    if fm==r['_y']: st[2]+=1
    if fm==r['_y'] and b!=r['_y']: st[3]+=1
    if b==r['_y'] and fm!=r['_y']: st[3]-=1   # 净配对优势
    try: m.learn_one({k:r[k] for k in KEYS}, Y[r['_y']])
    except: pass
print('%-10s %-8s %-12s %-12s %-10s %s' % ('市场最高档','样本','基准命中','融合命中','差','净配对(融-基)'))
for k,(c,bh,fh,net) in buckets.items():
    if c==0: continue
    print('%-10s %-8d %-12s %-12s %-10s %d' % (k, c, '%.2f%%'%(bh/c*100), '%.2f%%'%(fh/c*100), '%+.2fpp'%((fh-bh)/c*100), net))
print('\n→ 净配对>0 且样本足够 = 融合在该档有优势 → 可采纳融合方向为主方向(tie-break/或主方向)')
print('→ 净配对<=0 = 该档不采纳(融合无优势)')
