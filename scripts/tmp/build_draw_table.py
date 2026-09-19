# -*- coding: utf-8 -*-
"""生成 data/tmp/draw_table.json —— R20 平局温度计查表（Matches.csv 23万场）"""
import csv, json, io, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

rows = []
with open('data/Matches.csv', encoding='utf-8') as f:
    rd = csv.reader(f); hdr = next(rd)
    idx = {k: hdr.index(k) for k in ['Division','FTResult','OddHome','OddDraw','OddAway','HandiSize','Over25','HomeElo','AwayElo','HTHome','HTAway']}
    for r in rd:
        if len(r) < len(hdr): continue
        rows.append({k: r[i] for k,i in idx.items()})

def b(v, edges, labels):
    try: f = float(v)
    except: return None
    for e,l in zip(edges,labels):
        if f < e: return l
    return labels[-1]

def rate(fn, cond=None):
    agg = defaultdict(lambda:[0,0])
    for d in rows:
        if d['FTResult'] not in ('H','D','A'): continue
        if cond and not cond(d): continue
        g = fn(d)
        if g is None: continue
        agg[g][1]+=1
        if d['FTResult']=='D': agg[g][0]+=1
    return {g: {'n': t, 'draw%': round(dh/t*100,1)} for g,(dh,t) in agg.items() if t>=300}

T = {
 'S9_大小球→平局率': rate(lambda d: b(d['Over25'],[1.7,1.85,2.0,2.15,2.3],['大球强<1.7','偏大1.7-1.85','中性1.85-2.0','偏小2.0-2.15','小球2.15-2.3','小球强>2.3'])),
 'S10_亚盘→平局率(全量)': rate(lambda d: b(d['HandiSize'],[-1.0,-0.5,-0.25,0.0,0.25,0.5,1.0,1.5],['受让>1','受让0.5-1','受让0.25-0.5','平手盘0','让0.25','让0.5','让0.75-1','让1-1.5','让≥1.5'])),
 'S11_主胜档→平局率': rate(lambda d: b(d['OddHome'],[1.5,1.8,2.1,2.5,3.0],['<1.5','1.5-1.8','1.8-2.1','2.1-2.5','2.5-3.0','>3.0'])),
 'S11b_客胜档→平局率': rate(lambda d: b(d['OddAway'],[2.2,2.6,3.0,3.5,4.5],['<2.2','2.2-2.6','2.6-3.0','3.0-3.5','3.5-4.5','>4.5'])),
 'S12_ELO差→平局率': rate(lambda d: b(str(float(d['HomeElo'])-float(d['AwayElo'])) if d['HomeElo'].strip() and d['AwayElo'].strip() else None,[-200,-100,-50,50,100,200],['客强>200','客强100-200','客强50-100','接近<50','主强50-100','主强100-200','主强>200'])),
 'S3_半场状态→全场平率': rate(lambda d: '半场平' if f"{d['HTHome']}:{d['HTAway']}" in ('0.0:0.0','1.0:1.0','2.0:2.0') else '半场分胜负'),
 '组合_主胜1.8-2.1+平赔': rate(lambda d: b(d['OddDraw'],[3.0,3.5,4.0],['平<3.0','平3.0-3.5','平3.5-4.0','平>4.0']), cond=lambda d: b(d['OddHome'],[1.8,2.1],['','x'])=='x'),
 '组合_主胜1.5-1.8+亚盘': rate(lambda d: b(d['HandiSize'],[0.0,0.5,1.0],['平手/受让','让0.5','让0.75-1','让≥1']), cond=lambda d: b(d['OddHome'],[1.5,1.8],['','x'])=='x'),
 '组合_盘口×大小球': rate(lambda d: f"{b(d['HandiSize'],[-0.5,0.0,0.5,1.0],['受让','平手/让0.25','让0.5','让0.75-1','让≥1'])}/{b(d['Over25'],[1.85,2.0,2.15],['大球','中性','偏小','小球'])}"),
 '联赛基准': rate(lambda d: {'E0':'英超','SP1':'西甲','D1':'德甲','I1':'意甲','F1':'法甲'}.get(d['Division'])),
 '联赛×小球': rate(lambda d: b(d['Over25'],[2.15],['≤2.15','小球>2.15']), cond=lambda d: d['Division'] in ('F1','I1')),
 '主胜2.1-3.0×亚盘': rate(lambda d: b(d['HandiSize'],[-0.5,0.0,0.5,1.0],['受让','平手','让0.25-0.5','让0.75-1','让≥1']), cond=lambda d: b(d['OddHome'],[2.1,3.0],['','x'])=='x'),
 '客强50-200×平赔': rate(lambda d: b(d['OddDraw'],[3.0,3.5],['平<3.0','平3.0-3.5','平>3.5']), cond=lambda d: d['HomeElo'].strip() and d['AwayElo'].strip() and 50<=float(d['AwayElo'])-float(d['HomeElo'])<200),
}
T['_meta'] = {'来源': 'Matches.csv 230557场·2026-08-25·R20平局温度计查表·生成脚本 scripts/tmp/build_draw_table.py', '基准': {'n': 230554, 'draw%': 26.5}}
with open('data/tmp/draw_table.json','w',encoding='utf-8') as f:
    json.dump(T, f, ensure_ascii=False, indent=1)
print('draw_table.json 已生成')
print('节数:', len(T)-1)
for k in ['S9_大小球→平局率','S11_主胜档→平局率','S12_ELO差→平局率','组合_主胜1.8-2.1+平赔','联赛基准','联赛×小球']:
    print(k, json.dumps(T[k], ensure_ascii=False))
