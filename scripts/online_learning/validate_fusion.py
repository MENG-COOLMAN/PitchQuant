# -*- coding: utf-8 -*-
"""融合增益验证（2026-09-11·最后判据）: 热门基准 vs 热门+在线ML融合(权重0.10)
判据: 融合 > 基准(p<0.05) → 启用 ENABLE_ONLINE_FUSION; 否则不启用

🔴🔴2026-09-30 作废声明（L1 泄露裁决专项·本结论已被推翻）:
  本脚本报出的 +0.68pp(z=2.12) 是**数据泄露**的产物，**不得再作为任何启用依据**。
  根因: KEYS 的 26 个特征中有 17 个是「该场赛后才知道的」——
        shots_h/shots_a(射门) · target_h/target_a(射正) · corners_h/corners_a(角球) ·
        fouls_h/fouls_a(犯规) · yellow_h/yellow_a · red_h/red_a(牌) · ht_goals/ht_result(半场比分)
        → 用赛后统计预测该场胜负 = 看答案答题（泄露越大·增益越大）。
  对照实测（227,518 场·时间分割 182014/45504·2026-09-30）:
        仅赛前可得(8特征)  融合 50.35% vs 基准 50.34% = **+0.01pp（≈0·真实水平）**
        含赛后统计(26特征)  融合 52.23% vs 基准 50.34% = +1.89pp（泄露）
        纯赔率(4特征)       融合 50.32% vs 基准 50.34% = −0.02pp
  裁决: L1 在线 ML **否决**（旁证: 融合监测 n=48 融合21=基准21 · 历史 30000 场 −14.2pp）。
  用途: 本脚本仅保留作「泄露量级对照」的教学/审计用例；禁止把其 KEYS 当生产特征集。"""
import os, sys, io, csv
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
        ht=f(r.get('HTHome'))+f(r.get('HTAway'))
        rows.append({'date':r['MatchDate'],'home_odds':oh,'draw_odds':od,'away_odds':oa,
          'handicap':f(r['HandiSize']),'o25_odds':f(r['Over25'],1.9),'league_id':0,'elo_diff':f(r.get('HomeElo'))-f(r.get('AwayElo')),'handicap_layer':0,
          'form3h':f(r.get('Form3Home')),'form5h':f(r.get('Form5Home')),'form3a':f(r.get('Form3Away')),'form5a':f(r.get('Form5Away')),
          'shots_h':f(r.get('HomeShots')),'shots_a':f(r.get('AwayShots')),'target_h':f(r.get('HomeTarget')),'target_a':f(r.get('AwayTarget')),
          'corners_h':f(r.get('HomeCorners')),'corners_a':f(r.get('AwayCorners')),'fouls_h':f(r.get('HomeFouls')),'fouls_a':f(r.get('AwayFouls')),
          'yellow_h':f(r.get('HomeYellow')),'yellow_a':f(r.get('AwayYellow')),'red_h':f(r.get('HomeRed')),'red_a':f(r.get('AwayRed')),
          'ht_goals':ht,'ht_result':1 if f(r.get('HTHome'))>f(r.get('HTAway')) else (2 if f(r.get('HTAway'))>f(r.get('HTHome')) else 0),
          '_y':1 if h>a else (2 if a>h else 0),'_o':oh,'_d':od,'_a':oa})
        if len(rows)>=30000: break
rows.sort(key=lambda x:x['date']); n=len(rows); split=int(n*0.8)
m=compose.Pipeline(preprocessing.StandardScaler(), linear_model.SoftmaxRegression(optimizer=optim.SGD(0.05)))
Y={0:'draw',1:'home',2:'away'}
for r in rows[:split]:
    try: m.learn_one({k:r[k] for k in KEYS}, Y[r['_y']])
    except: pass
W=0.10
base_hit=ml_hit=fus_hit=fus_only_ml_win=base_only_win=0; N=0
for r in rows[split:]:
    N+=1
    inv={1:1/r['_o'],0:1/r['_d'],2:1/r['_a']}; tot=sum(inv.values())
    mk={k:v/tot for k,v in inv.items()}
    b=max(mk,key=mk.get)
    try:
        p=m.predict_proba_one({k:r[k] for k in KEYS}); ml={0:p.get('draw',0),1:p.get('home',0),2:p.get('away',0)}
    except: ml={0:0,1:0,2:0}
    fu={k:mk[k]*(1-W)+ml.get(k,0)*W for k in (0,1,2)}
    fmax=max(fu,key=fu.get)
    if b==r['_y']: base_hit+=1
    if max(ml,key=ml.get)==r['_y']: ml_hit+=1
    if fmax==r['_y']: fus_hit+=1
    if fmax==r['_y'] and b!=r['_y']: fus_only_ml_win+=1
    if b==r['_y'] and fmax!=r['_y']: base_only_win+=1
    try: m.learn_one({k:r[k] for k in KEYS}, Y[r['_y']])
    except: pass
import math
print('测试 n=%d（热门/在线ML/融合 权重%.2f）' % (N, W))
print('热门基准: %.2f%% | 在线ML: %.2f%% | 🔴融合: %.2f%%' % (base_hit/N*100, ml_hit/N*100, fus_hit/N*100))
print('融合 vs 基准: %+.2fpp' % ((fus_hit-base_hit)/N*100))
if fus_only_ml_win+base_only_win:
    disc=fus_only_ml_win+base_only_win; z=(fus_only_ml_win-disc/2)/math.sqrt(disc*0.25)
    print('配对: 融合赢%d / 基准赢%d → z=%.2f' % (fus_only_ml_win, base_only_win, z))
    print('判定: %s' % ('融合有显著增益 → 可启用(权重%.2f)' % W if z>1.96 else ('融合显著更差 → 不启用' if z<-1.96 else '无显著差异 → 不启用(无证据)')))
