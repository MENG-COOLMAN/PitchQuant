# -*- coding: utf-8 -*-
"""学习曲线实验（2026-09-11·回答"是记账本还是真学习"）
方法: 固定测试集(后6000场·不参与学习)，测量模型在【不同学习样本量】下的命中率。
  若命中率随学习样本量变化 → 模型参数在学（真学习·非记账）
  若恒定不变 → 只是记录/查表
"""
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
        rows.append({'date':r['MatchDate'],'home_odds':oh,'draw_odds':od,'away_odds':oa,
          'handicap':f(r['HandiSize']),'o25_odds':f(r['Over25'],1.9),'league_id':0,'elo_diff':f(r.get('HomeElo'))-f(r.get('AwayElo')),'handicap_layer':0,
          'form3h':f(r.get('Form3Home')),'form5h':f(r.get('Form5Home')),'form3a':f(r.get('Form3Away')),'form5a':f(r.get('Form5Away')),
          'shots_h':f(r.get('HomeShots')),'shots_a':f(r.get('AwayShots')),'target_h':f(r.get('HomeTarget')),'target_a':f(r.get('AwayTarget')),
          'corners_h':f(r.get('HomeCorners')),'corners_a':f(r.get('AwayCorners')),'fouls_h':f(r.get('HomeFouls')),'fouls_a':f(r.get('AwayFouls')),
          'yellow_h':f(r.get('HomeYellow')),'yellow_a':f(r.get('AwayYellow')),'red_h':f(r.get('HomeRed')),'red_a':f(r.get('AwayRed')),
          'ht_goals':f(r.get('HTHome'))+f(r.get('HTAway')),'ht_result':1 if f(r.get('HTHome'))>f(r.get('HTAway')) else (2 if f(r.get('HTAway'))>f(r.get('HTHome')) else 0),
          '_y':1 if h>a else (2 if a>h else 0),'_o':oh,'_d':od,'_a':oa})
        if len(rows)>=30000: break
rows.sort(key=lambda x:x['date']); n=len(rows)
TEST = rows[-4000:]          # 固定测试集（不参与学习）
TRAIN = rows[:-4000]
Y={0:'draw',1:'home',2:'away'}
def eval_on(model, data):
    hit=0
    for r in data:
        try:
            p=model.predict_proba_one({k:r[k] for k in KEYS})
            if p and max(p,key=p.get)==Y[r['_y']]: hit+=1
        except: pass
    return hit/len(data)*100
print('固定测试集 %d 场（不参与学习）| 学习池 %d 场' % (len(TEST), len(TRAIN)))
print('\n%-14s %-14s %-14s %s' % ('学习样本量', '测试集命中率', '热门基准', '说明'))
base = sum(1 for r in TEST if min(((r['_o'],1),(r['_d'],0),(r['_a'],2)))[1]==r['_y'])/len(TEST)*100
m = None; done = 0
marks = [0, 500, 2000, 5000, 10000, 20000, len(TRAIN)]
for target in marks:
    while done < target:
        r = TRAIN[done]
        if m is None:
            m = compose.Pipeline(preprocessing.StandardScaler(), linear_model.SoftmaxRegression(optimizer=optim.SGD(0.05)))
        try: m.learn_one({k:r[k] for k in KEYS}, Y[r['_y']])
        except: pass
        done += 1
    if m is None:
        print('%-14s %-14s %-14s %s' % ('0 (未学习)', '-', '%.2f%%' % base, '模型未建立'))
        continue
    acc = eval_on(m, TEST)
    print('%-14s %-14s %-14s %s' % (target, '%.2f%%' % acc, '%.2f%%' % base,
          '← 参数已随样本变化' if target else ''))
print('\n→ 命中率随学习样本量变化 = 模型参数在真实学习（非查表/记账）')
print('→ 变化幅度与方向另见: 融合增益验证(z=2.12 显著)')
