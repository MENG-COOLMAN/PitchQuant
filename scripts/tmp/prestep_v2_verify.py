# -*- coding: utf-8 -*-
"""PreStep V2.0 方案验证（2026-09-12·用户要求验证并升级）
验证三版：①方案原版(handi=-hs·含符号bug) ②修正版(handi=hs) ③本模型双向评级(比分分)
判据：分组比分Top2是否单调 + 强推荐组增量 + 方向增量
"""
import os, sys, io, csv
from collections import Counter, defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Matches.csv')
DRAW_L = {'I1', 'F1'}

def load():
    rows = []
    with open(SRC, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            try:
                oh = float(r['OddHome']); od = float(r['OddDraw']); oa = float(r['OddAway'])
                hs = float(r['HandiSize'] or 0); o25 = float(r['Over25'] or 1.9)
                h = int(float(r['FTHome'])); a = int(float(r['FTAway'])); div = r['Division']
            except Exception:
                continue
            if not (oh > 1 and od > 1 and oa > 1):
                continue
            inv = {1: 1/oh, 0: 1/od, 2: 1/oa}; t = sum(inv.values())
            mk = {k: v/t for k, v in inv.items()}
            rows.append({'oh': oh, 'od': od, 'oa': oa, 'hs': hs, 'o25': o25, 'div': div,
                         'dir': 1 if h > a else (2 if a > h else 0),
                         'fav': max(mk, key=mk.get),
                         'gap': (mk[max(mk, key=mk.get)] - sorted(mk.values())[-2]) * 100,
                         'score': '%d:%d' % (h, a)})
    return rows[-12000:]

def score_v2(r, flip):
    """方案 V2.0 评分·flip=True 用修正符号(handi=hs)"""
    oh, hs, ov, div = r['oh'], r['hs'], r['o25'], r['div']
    handi = (-hs) if flip is False else hs      # 方案原版 handi=-hs · 修正版 handi=hs
    diff = r['gap'] / 100
    sp = 0.0
    if ov > 2.1: sp += 2.0
    if handi <= -2.0: sp += 1.5
    elif -1.75 <= handi <= -1.25: sp += 1.0
    if 1.80 <= oh < 2.20: sp += 1.5
    elif 1.50 <= oh < 1.80: sp += 1.0
    if 0.15 <= diff <= 0.25: sp += 0.5
    if ov < 1.7: sp -= 1.5
    if oh < 1.30: sp -= 1.0
    if -1.25 < handi <= -0.75: sp -= 0.5
    if oh < 1.5 and handi > -1.0: sp -= 2.0
    if ov < 1.5 and handi <= -1.5: sp -= 2.0
    ds = {'H': 0, 'D': 0, 'A': 0}
    if oh < 1.5: ds['H'] += 1.5
    if handi < -0.74: ds['A'] += 1.5
    if 0.05 <= diff <= 0.10 and div in DRAW_L: ds['D'] += 1.0
    if r['oa'] < 2.2 and oh > 3.0: ds['A'] += 1.0
    if abs(handi) < 0.25: ds['H'] += 0.5
    if (div == 'SP1' and 1.5 <= oh < 1.8) or (div == 'F1' and oh < 1.8):
        ds['H'] -= 0.5; ds['A'] += 0.5
    bd = max(ds, key=ds.get)
    pred = 1 if bd == 'H' else (2 if bd == 'A' else 0)
    return sp + ds[bd], pred

def score_dual(r):
    """本模型双向评级的「比分分」(参照 prestep_dual 分值)"""
    oh, hs, ov = r['oh'], r['hs'], r['o25']
    handi = hs
    s = 0.0
    if ov > 2.10: s += 3
    elif ov < 1.65: s -= 4
    if 1.80 <= oh < 2.20: s += 2.5
    elif 1.50 <= oh < 1.80: s += 1
    if handi <= -1.5: s += 2
    if 1.65 <= ov <= 1.90: s -= 2
    if ov < 1.5 and handi <= -1.5: s -= 6
    if oh < 1.5 and handi > -1.0: s -= 6
    if ov < 1.7 and r['gap'] > 25: s -= 3
    return s

def table(train):
    t = defaultdict(Counter)
    for r in train:
        k = (r['fav'], round(r['hs'] * 2) / 2, 'O1' if r['o25'] < 1.8 else ('O2' if r['o25'] < 2.1 else 'O3'))
        t[k][r['score']] += 1
    return t

def hit2(t, r):
    k = (r['fav'], round(r['hs'] * 2) / 2, 'O1' if r['o25'] < 1.8 else ('O2' if r['o25'] < 2.1 else 'O3'))
    c = t.get(k)
    return r['score'] in [s for s, _ in c.most_common(2)] if c else False

def main():
    rows = load(); n = len(rows); split = int(n * 0.8)
    train, test = rows[:split], rows[split:]
    t = table(train)
    base2 = sum(1 for r in test if hit2(t, r)) / len(test) * 100
    based = sum(1 for r in test if r['fav'] == r['dir']) / len(test) * 100
    print('测试 %d 场 | 基准: 比分Top2 %.2f%% / 方向 %.2f%%\n' % (len(test), base2, based))

    def group_report(name, scorer, cuts):
        gs = defaultdict(lambda: [0, 0, 0])   # n, hit2, dhit
        for r in test:
            tot, pred = scorer(r)
            for lo, hi, label in cuts:
                if lo <= tot < hi:
                    g = gs[label]
                    g[0] += 1
                    if hit2(t, r): g[1] += 1
                    if pred == r['dir']: g[2] += 1
                    break
        print('【%s】' % name)
        print('  %-16s %-7s %-11s %-11s %s' % ('分组', '样本', '比分Top2', '增量', '方向'))
        for lo, hi, label in cuts:
            g = gs[label]
            if not g[0]: continue
            acc = g[1] / g[0] * 100
            print('  %-16s %-7d %-11s %+-9.2fpp %.2f%%' % (label, g[0], '%.2f%%' % acc, acc - base2, g[2] / g[0] * 100))
        print()

    cuts = [(3.5, 99, '强推荐≥3.5'), (2.0, 3.5, '推荐2.0-3.5'), (0.5, 2.0, '观察0.5-2.0'), (-99, 0.5, '回避<0.5')]
    group_report('方案原版(handi=-hs·符号bug)', lambda r: score_v2(r, False), cuts)
    group_report('修正版(handi=hs)', lambda r: score_v2(r, True), cuts)
    # 本模型比分分分档（≥2.5 / 0-2.5 / -3-0 / ≤-3）
    group_report('本模型比分分(prestep_dual)', lambda r: (score_dual(r), 1), [(2.5, 99, '比分推荐≥2.5'), (0, 2.5, '中性0-2.5'), (-3, 0, '偏弱-3-0'), (-99, -3, '不可预测≤-3')])

if __name__ == '__main__':
    main()
