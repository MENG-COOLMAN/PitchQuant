"""比分深度决策表生成器（2026-08-29·score_depth_table.json v2.0·Matches.csv 23万场可复现）
九档位(H4+/H3/H2/H1/D0/A1/A2/A3/A4+) × 5档Over25(S1-S5) = 45单元格·每格Top3比分+条件概率
用法: python build_score_depth_table.py
"""
import csv, io, sys, json
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BUCKETS = ['H4+','H3','H2','H1','D0','A1','A2','A3','A4+']
BINS = {'S1': (0,1.60,'大球极强'), 'S2': (1.60,1.80,'大球强'), 'S3': (1.80,2.00,'中性偏大'), 'S4': (2.00,2.20,'中性偏小'), 'S5': (2.20,99,'小球强')}

def bucket(margin):
    if margin >= 4: return 'H4+'
    if margin == 3: return 'H3'
    if margin == 2: return 'H2'
    if margin == 1: return 'H1'
    if margin == 0: return 'D0'
    if margin == -1: return 'A1'
    if margin == -2: return 'A2'
    if margin == -3: return 'A3'
    return 'A4+'

def sbin(ov):
    for k, (lo, hi, _) in BINS.items():
        if lo <= ov < hi: return k
    return 'S5'

rows = []
with open('data/Matches.csv', encoding='utf-8-sig') as f:
    rd = csv.reader(f); hdr = next(rd)
    idx = {h: i for i, h in enumerate(hdr)}
    for r in rd:
        if len(r) < 36: continue
        try:
            gh, ga = float(r[idx['FTHome']]), float(r[idx['FTAway']])
            oh, od, oa = float(r[idx['OddHome']]), float(r[idx['OddDraw']]), float(r[idx['OddAway']])
            ov = float(r[idx['Over25']])
        except: continue
        if not (ov > 1 and od > 1): continue
        rows.append((int(gh+0.1), int(ga+0.1), oh, od, oa, ov, r[idx['Division']].strip()))

cell = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
# D2: 平局档加 OddDraw 3 档子维度(<3.0/3.0-3.5/>3.5·验证0:0差10.4pp显著)
dcell = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # [sbin][dbin][score]
wcell = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(int))))  # [bucket][wbin][sbin][score]·D1
def dbin(od):
    if od < 3.0: return 'DL'
    if od < 3.5: return 'DM'
    return 'DH'
def wbin(w):
    if w < 1.5: return 'W1'   # 深盘
    if w < 2.0: return 'W2'   # 中盘
    return 'W3'               # 浅盘/冷门
for gh, ga, oh, od, oa, ov, div in rows:
    b = bucket(gh-ga)
    s = sbin(ov)
    win = oh if b in ('H1','H2','H3','H4+') else (oa if b in ('A1','A2','A3','A4+') else od)
    w = wbin(win)
    wcell[b][w][s][f'{gh}:{ga}'] += 1
    if b == 'D0':
        dcell[s][dbin(od)][f'{gh}:{ga}'] += 1

def shrink(cell_dist, parent_dist, TH=1000):
    """E1 贝叶斯收缩(2026-08-29): 样本<TH时向父级(同档全合并)收缩·p'=(n*p + n_p*p_p)/(n+n_p)"""
    n = sum(cell_dist.values()); np_ = sum(parent_dist.values())
    if n >= TH or np_ == 0:
        return None, n, False
    merged = {}
    for k in set(cell_dist) | set(parent_dist):
        p = (cell_dist.get(k,0) + parent_dist.get(k,0)) / (n + np_)
        merged[k] = p
    top = sorted(merged.items(), key=lambda x: -x[1])[:3]
    return top, n, True

out = {"version": "3.0", "data_source": "Matches.csv 230554场(有效148397·Over25>1·D1胜方赔率3维+E1收缩)", "generated": "2026-08-29 15:33:23",
       "over25_bins": {k: {"label": v[2], "min": v[0], "max": v[1]} for k, v in BINS.items()}, "buckets": {}}
for b in BUCKETS:
    out['buckets'][b] = {"label": {'H4+':'主胜4+','H3':'主胜3球','H2':'主胜2球','H1':'主胜1球','D0':'平局','A1':'客胜1球','A2':'客胜2球','A3':'客胜3球','A4+':'客胜4+'}[b], "bins": {}}
    if b == 'D0':
        out['buckets'][b]['draw_bins'] = {}
        for db in ('DL', 'DM', 'DH'):
            out['buckets'][b]['draw_bins'][db] = {}
            for s in BINS:
                dist = dcell[s][db]
                n = sum(dist.values())
                if n == 0:
                    out['buckets'][b]['draw_bins'][db][s] = {"n": 0}; continue
                parent = defaultdict(int)
                for db2 in ('DL','DM','DH'):
                    for k, v in dcell[s][db2].items(): parent[k] += v
                st, ns, shr = shrink(dist, parent)
                top = st if shr else sorted(dist.items(), key=lambda x: -x[1])[:3]
                conf = 'high' if n >= 1000 else ('medium' if n >= 500 else 'low')
                out['buckets'][b]['draw_bins'][db][s] = {
                    "n": n, "anchor": top[0][0], "anchor_pct": round(top[0][1]*100, 1) if shr else round(top[0][1]/n*100, 1),
                    "second": top[1][0] if len(top) > 1 else None, "second_pct": round(top[1][1]*100, 1) if shr else (round(top[1][1]/n*100, 1) if len(top) > 1 else None),
                    "third": top[2][0] if len(top) > 2 else None, "third_pct": round(top[2][1]*100, 1) if shr else (round(top[2][1]/n*100, 1) if len(top) > 2 else None),
                    "confidence": conf, "shrinkage_applied": shr}
    else:
        out['buckets'][b]['win_bins'] = {}
        for w in ('W1', 'W2', 'W3'):
            out['buckets'][b]['win_bins'][w] = {}
            for s in BINS:
                dist = wcell[b][w][s]
                n = sum(dist.values())
                if n == 0:
                    out['buckets'][b]['win_bins'][w][s] = {"n": 0}; continue
                # E1: 样本<1000收缩到父级(同bucket全win_bin合并)
                parent = defaultdict(int)
                for w2 in ('W1','W2','W3'):
                    for s2 in BINS:
                        for k, v in wcell[b][w2][s2].items(): parent[k] += v
                st, ns, shr = shrink(dist, parent)
                top = st if shr else sorted(dist.items(), key=lambda x: -x[1])[:3]
                conf = 'high' if n >= 1000 else ('medium' if n >= 500 else 'low')
                out['buckets'][b]['win_bins'][w][s] = {
                    "n": n, "anchor": top[0][0], "anchor_pct": round(top[0][1]*100, 1) if shr else round(top[0][1]/n*100, 1),
                    "second": top[1][0] if len(top) > 1 else None, "second_pct": round(top[1][1]*100, 1) if shr else (round(top[1][1]/n*100, 1) if len(top) > 1 else None),
                    "third": top[2][0] if len(top) > 2 else None, "third_pct": round(top[2][1]*100, 1) if shr else (round(top[2][1]/n*100, 1) if len(top) > 2 else None),
                    "confidence": conf, "shrinkage_applied": shr}
json.dump(out, open('data/tmp/score_depth_table.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('score_depth_table.json 已生成')
# 验证45单元格
cnt = sum(1 for b in BUCKETS if b != 'D0' for w in ('W1','W2','W3') for s in BINS if out['buckets'][b]['win_bins'][w][s].get('n'))
cnt_draw = sum(1 for db in ('DL','DM','DH') for s in BINS if out['buckets']['D0']['draw_bins'][db][s].get('n'))
print('非空单元格: %d/45' % cnt)
# 关键点抽查
d = out['buckets']
print('H1 W1 S1(深盘):', d['H1']['win_bins']['W1']['S1'])
print('H1 W3 S1(浅盘):', d['H1']['win_bins']['W3']['S1'])
print('win_bins格数:', cnt, '+ draw_bins:', cnt_draw, '= 总计', cnt + cnt_draw, '/135')
print('H1 W3 S1(浅盘):', d['H1']['win_bins']['W3']['S1'])
print('win_bins格数:', cnt, '+ draw_bins:', cnt_draw, '= 总计', cnt + cnt_draw, '/135')
print('D0 DL S1(低平赔):', d['D0']['draw_bins']['DL']['S1'])
print('D0 DH S1(高平赔):', d['D0']['draw_bins']['DH']['S1'])
print('平局draw_bins格数:', cnt_draw)
print('H2 W2 S1:', d['H2']['win_bins']['W2']['S1'])
print('H4+ W1 S1:', d['H4+']['win_bins']['W1']['S1'])
