# -*- coding: utf-8 -*-
"""PreStep 比分命中导向信号回测（2026-09-11·用户要求"侧重比分命中兼顾方向"）
方法: Matches.csv 时间分割（前80%建比分表 / 后20%测试）
  对每个候选「赛前可得」信号档 → 计算该档内【比分 Top1/Top2 命中率】+【方向命中率】
  基准 = 全局比分Top2命中率 / 全局方向命中率（热门基准）
判据: 档内比分Top2命中率显著高于基准 → 该信号赋正分（分值 ∝ 增量 pp）
"""
import os, sys, io, csv, math
from collections import Counter, defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Matches.csv')
LIMIT = 60000

def load():
    rows = []
    with open(SRC, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            try:
                oh = float(r['OddHome']); od = float(r['OddDraw']); oa = float(r['OddAway'])
                hs = float(r['HandiSize'] or 0); o25 = float(r['Over25'] or 1.9)
                h = int(float(r['FTHome'])); a = int(float(r['FTAway']))
            except Exception:
                continue
            if not (oh > 1 and od > 1 and oa > 1):
                continue
            inv = {1: 1/oh, 0: 1/od, 2: 1/oa}; t = sum(inv.values())
            mk = {k: v/t for k, v in inv.items()}
            top = max(mk, key=mk.get)
            rows.append({'d': r['MatchDate'], 'oh': oh, 'od': od, 'oa': oa, 'hs': hs, 'o25': o25,
                         'score': '%d:%d' % (h, a),
                         'dir': 1 if h > a else (2 if a > h else 0),
                         'fav': top, 'gap': (mk[top] - sorted(mk.values())[-2]) * 100,
                         'top_p': mk[top] * 100})
            if len(rows) >= LIMIT:
                break
    rows.sort(key=lambda x: x['d'])   # 🔴按日期排序（正确时间分割）
    return rows

def score_table(train):
    """按「方向 + 让球层」建比分表（赛前可得的分组键）"""
    tbl = defaultdict(Counter)
    for r in train:
        key = (r['fav'], round(r['hs'] * 2) / 2, 'O1' if r['o25'] < 1.8 else ('O2' if r['o25'] < 2.1 else 'O3'))
        tbl[key][r['score']] += 1
    return tbl

def top2(tbl, r):
    key = (r['fav'], round(r['hs'] * 2) / 2, 'O1' if r['o25'] < 1.8 else ('O2' if r['o25'] < 2.1 else 'O3'))
    c = tbl.get(key)
    if not c:
        return []
    return [s for s, _ in c.most_common(2)]

def main():
    rows = load(); n = len(rows); split = int(n * 0.8)
    tbl = score_table(rows[:split])
    test = rows[split:]
    # 全局基准
    N = len(test); s1 = s2 = dhit = 0
    for r in test:
        t = top2(tbl, r)
        if t and t[0] == r['score']: s1 += 1
        if r['score'] in t[:2]: s2 += 1
        if r['fav'] == r['dir']: dhit += 1
    base1, base2, based = s1/N*100, s2/N*100, dhit/N*100
    print('测试 %d 场 | 全局基准: 比分Top1 %.2f%% / Top2 %.2f%% / 方向 %.2f%%' % (N, base1, base2, based))
    print('※ 信号档内比较（比分Top2 为主指标·方向为辅）\n')
    print('%-30s %-7s %-11s %-11s %-11s %s' % ('信号档', '样本', '比分Top1', '比分Top2', '方向', '比分Top2增量'))

    def stat(name, cond):
        sub = [r for r in test if cond(r)]
        if len(sub) < 80:
            return
        a1 = a2 = ad = 0
        for r in sub:
            t = top2(tbl, r)
            if t and t[0] == r['score']: a1 += 1
            if r['score'] in t[:2]: a2 += 1
            if r['fav'] == r['dir']: ad += 1
        m = len(sub)
        print('%-30s %-7d %-11s %-11s %-11s %+.2fpp' % (
            name, m, '%.2f%%' % (a1/m*100), '%.2f%%' % (a2/m*100), '%.2f%%' % (ad/m*100), (a2/m*100 - base2)))

    print('--- A. 热门集中度（比分可预测性）---')
    stat('主赔<1.30（超深）', lambda r: r['oh'] < 1.30)
    stat('主赔1.30-1.50', lambda r: 1.30 <= r['oh'] < 1.50)
    stat('主赔1.50-1.80', lambda r: 1.50 <= r['oh'] < 1.80)
    stat('主赔1.80-2.20', lambda r: 1.80 <= r['oh'] < 2.20)
    stat('隐含差>25pp（悬殊）', lambda r: r['gap'] > 25)
    stat('隐含差15-25pp', lambda r: 15 <= r['gap'] <= 25)
    stat('隐含差<10pp（接近）', lambda r: r['gap'] < 10)
    print('--- B. 大小球共识（进球档明确度）---')
    stat('O25<1.45（极强大球）', lambda r: r['o25'] < 1.45)
    stat('O25 1.45-1.65', lambda r: 1.45 <= r['o25'] < 1.65)
    stat('O25 1.65-1.90（中性）', lambda r: 1.65 <= r['o25'] < 1.90)
    stat('O25>2.10（强小球）', lambda r: r['o25'] > 2.10)
    print('--- C. 让球深度（净胜档明确度）---')
    stat('让≥2（超深）', lambda r: r['hs'] <= -2.0)
    stat('让1.5（深）', lambda r: r['hs'] <= -1.5)
    stat('让0.75-1.25', lambda r: -1.25 <= r['hs'] <= -0.75)
    stat('平手/浅让', lambda r: r['hs'] > -0.5)
    print('--- D. 组合（多信号共振）---')
    stat('主<1.5 + O25<1.6', lambda r: r['oh'] < 1.5 and r['o25'] < 1.6)
    stat('主<1.5 + 让≥1.5', lambda r: r['oh'] < 1.5 and r['hs'] <= -1.5)
    stat('隐含差>25 + O25<1.7', lambda r: r['gap'] > 25 and r['o25'] < 1.7)
    stat('O25<1.5 + 让≥1.5', lambda r: r['o25'] < 1.5 and r['hs'] <= -1.5)
    stat('贴水浅让(主<1.5+让<1)', lambda r: r['oh'] < 1.5 and r['hs'] > -1.0)
    print('\n→ 比分Top2增量>0 的信号 = 比分可预测性高 → 赋正分（分值 ∝ 增量）')
    print('→ 增量≈0 = 对方向有贡献但对比分无贡献（降权或仅作方向分）')

if __name__ == '__main__':
    main()
