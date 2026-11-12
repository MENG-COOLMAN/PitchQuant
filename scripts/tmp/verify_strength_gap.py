# -*- coding: utf-8 -*-
"""
验证假设: 实力差距越大→大球+大比分越多·实力接近→小球或大球小比分
数据: Matches.csv 22.7万场(2000-2024+)·仅五大联赛(E0英超/SP1西甲/D1德甲/I1意甲/F1法甲)
度量: ①欧赔隐含差|P主-P客|(去水·市场口径) ②ELO差|HomeElo-AwayElo|(纯实力交叉)
指标: 总进球均值/O2.5率/O3.5率(≥4球)/净胜≥3率/大球小比分率(≥3球且净胜≤1)/方向
用法: PYTHONIOENCODING=utf-8 python data/tmp/verify_strength_gap.py
"""
import csv, collections, re
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')  # 🔴2026-09-04链路优化: 默认GBK控制台防UnicodeEncodeError崩溃/乱码
except Exception:
    pass


LG = {'E0': '英超', 'SP1': '西甲', 'D1': '德甲', 'I1': '意甲', 'F1': '法甲'}

def load():
    rows = []
    with open('data/Matches.csv', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            div = r['Division']
            if div not in LG:
                continue
            try:
                fh, fa = float(r['FTHome']), float(r['FTAway'])
                oh, od, oa = float(r['OddHome']), float(r['OddDraw']), float(r['OddAway'])
                he, ae = float(r['HomeElo']), float(r['AwayElo'])
            except (ValueError, TypeError):
                continue
            if fh < 0 or fa < 0 or oh <= 1 or oa <= 1:
                continue
            tg = fh + fa
            nw = fh - fa
            rows.append({
                'div': div, 'tg': tg, 'nw': nw,
                'imp_gap': abs(1/oh - 1/oa) / (1/oh + 1/od + 1/oa),  # 去水后隐含差
                'elo_gap': abs(he - ae),
            })
    return rows

def stats(rows, label):
    n = len(rows)
    if n == 0:
        return None
    tg = [r['tg'] for r in rows]
    o25 = sum(1 for t in tg if t >= 3)
    o35 = sum(1 for t in tg if t >= 4)
    nw3 = sum(1 for r in rows if abs(r['nw']) >= 3)
    big_small = sum(1 for r in rows if r['tg'] >= 3 and abs(r['nw']) <= 1)  # 大球小比分
    h = sum(1 for r in rows if r['nw'] > 0)
    d = sum(1 for r in rows if r['nw'] == 0)
    a = sum(1 for r in rows if r['nw'] < 0)
    return dict(n=n, avg=sum(tg)/n, o25=100.0*o25/n, o35=100.0*o35/n, nw3=100.0*nw3/n,
                bs=100.0*big_small/n, h=100.0*h/n, d=100.0*d/n, a=100.0*a/n)

def fmt(s):
    return f"n={s['n']:>7} 场均={s['avg']:.2f} O2.5={s['o25']:.1f}% O3.5={s['o35']:.1f}% 净胜≥3={s['nw3']:.1f}% 大球小比分={s['bs']:.1f}% H/D/A={s['h']:.0f}/{s['d']:.0f}/{s['a']:.0f}"

def gap_bands(rows, key, bands, names):
    out = []
    for (lo, hi), name in zip(bands, names):
        sub = [r for r in rows if lo <= r[key] < hi]
        s = stats(sub, name)
        if s:
            out.append((name, s))
    return out

def run(rows, key, bands, names, tag):
    print(f"\n{'='*78}\n【{tag}】按{'隐含差' if key=='imp_gap' else 'ELO差'}分层 (样本 {len(rows)})")
    print(f"{'差距档':<16}{'n':>8} {'场均':>6} {'O2.5':>7} {'O3.5':>7} {'净胜≥3':>8} {'大球小比分':>9} {'H/D/A':>16}")
    for name, s in gap_bands(rows, key, bands, names):
        print(f"{name:<16}{s['n']:>8} {s['avg']:>6.2f} {s['o25']:>6.1f}% {s['o35']:>6.1f}% {s['nw3']:>7.1f}% {s['bs']:>8.1f}% {s['h']:.0f}/{s['d']:.0f}/{s['a']:.0f}")
    # 线性趋势(首尾差)
    gs = gap_bands(rows, key, bands, names)
    if len(gs) >= 3:
        f0, l0 = gs[0][1], gs[-1][1]
        print(f"→ 趋势: O2.5 {f0['o25']:.1f}%→{l0['o25']:.1f}% (Δ{l0['o25']-f0['o25']:+.1f}pp) · 场均 {f0['avg']:.2f}→{l0['avg']:.2f} (Δ{l0['avg']-f0['avg']:+.2f}) · 净胜≥3 {f0['nw3']:.1f}%→{l0['nw3']:.1f}% (Δ{l0['nw3']-f0['nw3']:+.1f}pp)")

def main():
    rows = load()
    print(f"五大联赛有效样本: {len(rows)} 场 (仅含比分+欧赔+ELO)")
    print("分布:", dict(collections.Counter(r['div'] for r in rows)))

    imp_bands = [(0, 0.10, '接近(<10pp)'), (0.10, 0.20, '差10-20pp'), (0.20, 0.30, '差20-30pp'),
                 (0.30, 0.40, '差30-40pp'), (0.40, 0.50, '差40-50pp'), (0.50, 1.0, '悬殊(>50pp)')]
    imp_names = [b[2] for b in imp_bands]
    elo_bands = [(0, 100, '接近(<100)'), (100, 200, '差100-200'), (200, 300, '差200-300'),
                 (300, 400, '差300-400'), (400, 1e9, '悬殊(>400)')]
    elo_names = [b[2] for b in elo_bands]

    # 全五大联赛合并
    run(rows, 'imp_gap', [(b[0], b[1]) for b in imp_bands], imp_names, '五大联赛合并·市场隐含差')
    run(rows, 'elo_gap', [(b[0], b[1]) for b in elo_bands], elo_names, '五大联赛合并·ELO差')

    # 分联赛(隐含差口径)
    for div, name in LG.items():
        sub = [r for r in rows if r['div'] == div]
        run(sub, 'imp_gap', [(b[0], b[1]) for b in imp_bands], imp_names, f'{name}({div})·隐含差')

if __name__ == '__main__':
    main()
