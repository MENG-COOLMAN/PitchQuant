# -*- coding: utf-8 -*-
"""
R14 v2 条件化比分量级（2026-08-25·五大联赛 43,254 场·替代死板主锚）
维度A: 隐含差档(接近/中等/悬殊) × 方向(H/D/A) → 比分Top5/净胜分布/O2.5 → 主锚按方向条件选
维度B: 盘口档(-HandiSize主让深度) × 方向 → 净胜分布 → 比分量级按盘口校准
输出: data/tmp/r19_conditional_scores.json（合并+分联赛）
用法: PYTHONIOENCODING=utf-8 python scripts/tmp/bt_r14_cond.py
"""
import csv, json, collections
import sys

# GBK console guard (2026-09-15)
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


LG = {'E0': '英超', 'SP1': '西甲', 'D1': '德甲', 'I1': '意甲', 'F1': '法甲'}

def scene_of(gap):
    return '接近<10pp' if gap < 0.10 else ('悬殊>50pp' if gap >= 0.50 else '中等')

def handi_band(h):
    """h = 主让深度(-HandiSize): 正=主让·负=主受让"""
    if h <= -0.75: return '主受让≥0.75'
    if h <= -0.25: return '主受让0.25-0.5'
    if h < 0.25: return '平手盘'
    if h < 0.75: return '主让0.25-0.5'
    if h < 1.25: return '主让0.75-1'
    if h < 1.75: return '主让1.25-1.5'
    if h < 2.25: return '主让1.75-2'
    return '主让≥2.25'

def load():
    rows = []
    with open('data/Matches.csv', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            div = r['Division']
            if div not in LG: continue
            try:
                fh, fa = float(r['FTHome']), float(r['FTAway'])
                oh, od, oa = float(r['OddHome']), float(r['OddDraw']), float(r['OddAway'])
                hs = r['HandiSize'].strip()
            except (ValueError, TypeError): continue
            if fh < 0 or fa < 0 or oh <= 1 or oa <= 1: continue
            gap = abs(1/oh - 1/oa) / (1/oh + 1/od + 1/oa)
            nw = fh - fa
            direc = '主胜' if nw > 0 else ('平局' if nw == 0 else '客胜')
            rec = {'div': div, 'tg': fh+fa, 'nw': nw, 'gap': gap, 'dir': direc,
                   'sc': f"{int(fh)}:{int(fa)}"}
            if hs:
                try: rec['handi'] = -float(hs)  # 主让深度
                except ValueError: pass
            rows.append(rec)
    return rows

def agg(rows, keyfn, extra=None):
    """按 keyfn 分组·统计比分/净胜/O2.5"""
    g = collections.defaultdict(lambda: {'n': 0, 'o25': 0, 'nw1h': 0, 'nw2h': 0, 'nw3h': 0,
                                          'nw1a': 0, 'nw3a': 0, 'sc': collections.Counter()})
    for r in rows:
        k = keyfn(r)
        if extra: k = (k, extra(r))
        b = g[k]
        b['n'] += 1
        if r['tg'] >= 3: b['o25'] += 1
        if r['nw'] == 1: b['nw1h'] += 1
        if r['nw'] == 2: b['nw2h'] += 1
        if r['nw'] >= 3: b['nw3h'] += 1
        if r['nw'] == -1: b['nw1a'] += 1
        if r['nw'] <= -3: b['nw3a'] += 1
        b['sc'][r['sc']] += 1
    return g

def fmt_band(b):
    n = b['n']
    top = [f"{k}:{v}({round(100.0*v/n,1)}%)" for k, v in b['sc'].most_common(5)]
    return {'n': n, 'O2.5%': round(100.0*b['o25']/n, 1),
            '主净1%': round(100.0*b['nw1h']/n, 1), '主净2%': round(100.0*b['nw2h']/n, 1), '主净3+%': round(100.0*b['nw3h']/n, 1),
            '客净1%': round(100.0*b['nw1a']/n, 1), '客净3+%': round(100.0*b['nw3a']/n, 1),
            '比分Top5': top}

def main():
    rows = load()
    print(f"样本: {len(rows)}")
    out = {}
    for div, cn in LG.items():
        sub = [r for r in rows if r['div'] == div]
        # A: 隐含差档 × 方向
        A = {}
        g = agg(sub, lambda r: (scene_of(r['gap']), r['dir']))
        for (scene, direc), b in sorted(g.items()):
            A.setdefault(scene, {})[direc] = fmt_band(b)
        # B: 盘口档(合并隐含差) → 净胜/比分
        subh = [r for r in sub if 'handi' in r]
        B = {}
        gh = agg(subh, lambda r: handi_band(r['handi']))
        for band, b in sorted(gh.items()):
            B[band] = fmt_band(b)
        out[cn] = {'A_方向×隐含差': A, 'B_盘口档': B}
        print(f"\n【{cn}】A方向×隐含差(主胜场) | B盘口(主让深度)")
        for scene in ['接近<10pp', '中等', '悬殊>50pp']:
            if scene in A and '主胜' in A[scene]:
                a = A[scene]['主胜']
                print(f"  A {scene} 主胜(n={a['n']}): 主净1/2/3+={a['主净1%']}/{a['主净2%']}/{a['主净3+%']}% Top3={a['比分Top5'][:3]}")
        for band in ['主受让≥0.75', '主让0.75-1', '主让1.25-1.5', '主让≥2.25']:
            if band in B:
                b = B[band]
                print(f"  B {band}(n={b['n']}): 主净1/2/3+={b['主净1%']}/{b['主净2%']}/{b['主净3+%']}% Top3={b['比分Top5'][:3]}")
    json.dump(out, open('data/tmp/r19_conditional_scores.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"\n已保存: data/tmp/r19_conditional_scores.json")

if __name__ == '__main__':
    main()
