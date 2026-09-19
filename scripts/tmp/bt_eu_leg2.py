# -*- coding: utf-8 -*-
"""
欧冠/欧战第二回合回测 (V3.5.72+ 欧战精算升级·2026-08-25)
维度A 统计学: 方向/总进球/大球/比分谱系/净胜/半场/首回合传导
维度B 精算类: 欧赔档位/隐含校准/抽水/亚盘盘口/水位/水位×盘口/欧亚背离/价值档
用法: PYTHONIOENCODING=utf-8 python scripts/tmp/bt_eu_leg2.py [--all]
"""
import csv, collections, re, sys, json, os
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')  # 🔴2026-09-04链路优化: 默认GBK控制台防UnicodeEncodeError崩溃/乱码
except Exception:
    pass


BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'europe')

# ---------- 盘口中文→数值 ----------
HANDI_MAP = {
    '平手': 0.0, '平/半': 0.25, '半球': 0.5, '半/一': 0.75, '一球': 1.0,
    '一/球半': 1.25, '球半': 1.5, '球半/两': 1.75, '两球': 2.0, '两/两半': 2.25,
    '两半': 2.5, '两半/三': 2.75, '三球': 3.0, '三/三半': 3.25, '三半': 3.5,
    '三半/四': 3.75,
}

def parse_handi(s):
    s = (s or '').strip()
    if not s:
        return None
    neg = False
    if s.startswith('受'):
        neg = True
        s = s[1:]
    if s in HANDI_MAP:
        v = HANDI_MAP[s]
        return -v if neg else v
    return None

def parse_score(s):
    m = re.match(r'^(\d+):(\d+)$', (s or '').strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))

def load_csv(path):
    rows = list(csv.DictReader(open(path, encoding='utf-8-sig')))
    out = []
    for r in rows:
        sc = parse_score(r['score'])
        ht = parse_score(r['ht'])
        if sc is None:
            continue
        try:
            oh, od, oa = float(r['odd99_h']), float(r['odd99_d']), float(r['odd99_a'])
            wh, wa = float(r['handi_h']), float(r['handi_a'])
        except (ValueError, TypeError):
            continue
        hc = parse_handi(r['handi_hc'])
        if hc is None:
            continue
        out.append({
            'league': r['league'], 'round': r['round'], 'date': r['date'],
            'home': r['home'], 'away': r['away'], 'sc': sc, 'ht': ht,
            'oh': oh, 'od': od, 'oa': oa, 'wh': wh, 'wa': wa, 'hc': hc,
        })
    return out

def pair_legs(rows):
    """按对阵对配对·同组≥2场按日期取最早两场 → (leg1, leg2)"""
    groups = collections.defaultdict(list)
    for r in rows:
        groups[frozenset([r['home'], r['away']])].append(r)
    pairs = []
    for g in groups.values():
        if len(g) < 2:
            continue
        g2 = sorted(g, key=lambda x: x['date'])[:2]
        l1, l2 = g2[0], g2[1]
        # 校验主客互换（真两回合）
        if (l1['home'], l1['away']) == (l2['away'], l2['home']):
            pairs.append((l1, l2))
    return pairs

def outcome(r):
    """以行 home 视角: H/D/A"""
    h, a = r['sc']
    if h > a: return 'H'
    if h < a: return 'A'
    return 'D'

def total_goals(r):
    return r['sc'][0] + r['sc'][1]

def net_win(r):
    """主队视角净胜"""
    return r['sc'][0] - r['sc'][1]

def implied(oh, od, oa):
    ih, id_, ia = 1/oh, 1/od, 1/oa
    s = ih + id_ + ia
    return ih/s, id_/s, ia/s, s  # 去水H/D/A + 抽水倍数

def pct(x, n):
    return f"{100.0*x/n:.1f}%" if n else "—"

def dist_counter(counter, n, top=None):
    items = sorted(counter.items(), key=lambda x: -x[1])
    if top:
        items = items[:top]
    return '  '.join(f"{k}:{v}({pct(v, n)})" for k, v in items)

def analyze(pairs, tag):
    print(f"\n{'='*70}\n【{tag}】两回合组数: {len(pairs)}")
    if not pairs:
        return
    L1, L2 = zip(*pairs)
    l2 = list(L2)
    l1 = list(L1)
    n = len(l2)

    # ---------- A 统计学 ----------
    print(f"\n--- A1 次回合方向基准 (次回合行home视角) ---")
    oc2 = collections.Counter(outcome(r) for r in l2)
    print(f"  次回合 H:{pct(oc2['H'], n)} D:{pct(oc2['D'], n)} A:{pct(oc2['A'], n)}")
    tg2 = [total_goals(r) for r in l2]
    tg1 = [total_goals(r) for r in l1]
    ov2 = sum(1 for t in tg2 if t >= 3)
    ov1 = sum(1 for t in tg1 if t >= 3)
    print(f"  次回合 总进球均值 {sum(tg2)/n:.2f} | O2.5率 {pct(ov2, n)} | 分布 {dist_counter(collections.Counter(tg2), n)}")
    print(f"  首回合 总进球均值 {sum(tg1)/n:.2f} | O2.5率 {pct(ov1, n)} | 分布 {dist_counter(collections.Counter(tg1), n)}")

    print(f"\n--- A2 次回合比分谱系 (Top6) ---")
    sc2 = collections.Counter(f"{r['sc'][0]}:{r['sc'][1]}" for r in l2)
    print("  " + dist_counter(sc2, n, 6))
    draw_sc = {k: v for k, v in sc2.items() if k.split(':')[0] == k.split(':')[1]}
    print(f"  平局比分合计: {pct(sum(draw_sc.values()), n)} | 其中 {dist_counter(draw_sc, n)}")

    print(f"\n--- A3 次回合净胜分布 (主队视角) ---")
    nw = [net_win(r) for r in l2]
    nw_c = collections.Counter('主胜1' if x==1 else '主胜2' if x==2 else '主胜3+' if x>=3 else
                               '客胜1' if x==-1 else '客胜2' if x==-2 else '客胜3+' if x<=-3 else '平局'
                               for x in nw)
    print("  " + dist_counter(nw_c, n))
    hw = [x for x in nw if x > 0]; aw = [x for x in nw if x < 0]
    print(f"  主胜净胜1:{pct(sum(1 for x in hw if x==1), n)} 净胜2:{pct(sum(1 for x in hw if x==2), n)} 净胜3+:{pct(sum(1 for x in hw if x>=3), n)}")
    print(f"  客胜净胜1:{pct(sum(1 for x in aw if x==-1), n)} 净胜2:{pct(sum(1 for x in aw if x==-2), n)} 净胜3+:{pct(sum(1 for x in aw if x<=-3), n)}")

    print(f"\n--- A4 半场 vs 全场 (次回合) ---")
    ht_c = collections.Counter(outcome({'sc': r['ht']}) for r in l2)
    print(f"  半场 H:{pct(ht_c['H'], n)} D:{pct(ht_c['D'], n)} A:{pct(ht_c['A'], n)}")
    ht_draw_ft_draw = sum(1 for r in l2 if r['ht'][0]==r['ht'][1] and r['sc'][0]==r['sc'][1])
    ht_draw_n = sum(1 for r in l2 if r['ht'][0]==r['ht'][1])
    print(f"  半场平→全场平: {pct(ht_draw_ft_draw, ht_draw_n)} (半场平样本 {ht_draw_n})")
    ht_h_ft_h = sum(1 for r in l2 if r['ht'][0]>r['ht'][1] and r['sc'][0]>r['sc'][1])
    ht_h_n = sum(1 for r in l2 if r['ht'][0]>r['ht'][1])
    print(f"  半场主胜→全场主胜: {pct(ht_h_ft_h, ht_h_n)} (样本 {ht_h_n})")

    print(f"\n--- A5 首回合结果 → 次回合 (44B 领先方占优验证) ---")
    # 首回合结果: leg1 home视角
    groups = {'H': [], 'D': [], 'A': []}
    for i in range(n):
        r1 = l1[i]
        groups[outcome(r1)].append(i)
    for k, idxs in groups.items():
        if not idxs: continue
        oc2g = collections.Counter(outcome(l2[i]) for i in idxs)
        # 领先方 (首回合胜者) 在次回合的表现: 若首回合H胜→领先方=leg1主队=leg2客队→次回合A(客胜)为领先方赢
        print(f"  首回合{'主胜' if k=='H' else '平局' if k=='D' else '客胜'}(n={len(idxs)}) → 次回合 H:{pct(oc2g['H'], len(idxs))} D:{pct(oc2g['D'], len(idxs))} A:{pct(oc2g['A'], len(idxs))}")

    print(f"\n--- A6 首回合净胜/总进球 → 次回合大球 (44A 比分追逐验证) ---")
    for cond, fn in [('首回合≤2球', lambda r: total_goals(r)<=2), ('首回合≥3球', lambda r: total_goals(r)>=3),
                     ('首回合主胜净胜1球', lambda r: net_win(r)==1), ('首回合主胜净胜2+球', lambda r: net_win(r)>=2)]:
        idxs = [i for i in range(n) if fn(l1[i])]
        if not idxs: continue
        ov = sum(1 for i in idxs if total_goals(l2[i])>=3)
        oc = collections.Counter(outcome(l2[i]) for i in idxs)
        print(f"  {cond}(n={len(idxs)}) → 次回合O2.5:{pct(ov, len(idxs))} 次回合H:{pct(oc['H'],len(idxs))} D:{pct(oc['D'],len(idxs))} A:{pct(oc['A'],len(idxs))}")

    print(f"\n--- A7 次回合 落后方翻盘/主队强势? ---")
    # 首回合客胜(leg1 home输)→ 次回合(该队回主场)表现
    l1A = [i for i in range(n) if outcome(l1[i])=='A']
    if l1A:
        oc = collections.Counter(outcome(l2[i]) for i in l1A)
        print(f"  首回合客胜(主队首回合输·n={len(l1A)}) → 次回合该队回主场 H:{pct(oc['H'],len(l1A))} D:{pct(oc['D'],len(l1A))} A:{pct(oc['A'],len(l1A))}")
    l1H = [i for i in range(n) if outcome(l1[i])=='H']
    if l1H:
        oc = collections.Counter(outcome(l2[i]) for i in l1H)
        print(f"  首回合主胜(主队首回合赢·n={len(l1H)}) → 次回合该队做客 H:{pct(oc['H'],len(l1H))} D:{pct(oc['D'],len(l1H))} A:{pct(oc['A'],len(l1H))}")

    # ---------- B 精算类 ----------
    print(f"\n{'='*70}\n【{tag}】精算类 (欧盘99家终赔+亚盘)")

    print(f"\n--- B1 欧赔主胜档 → 实际 H/D/A (对标 odds_table 欧战口径) ---")
    bands = [(0, 1.5, '<1.50'), (1.5, 1.8, '1.50-1.80'), (1.8, 2.1, '1.80-2.10'), (2.1, 2.5, '2.10-2.50'), (2.5, 3.5, '2.50-3.50'), (3.5, 99, '>3.50')]
    for lo, hi, name in bands:
        idxs = [i for i in range(n) if lo <= l2[i]['oh'] < hi]
        if not idxs: continue
        oc = collections.Counter(outcome(l2[i]) for i in idxs)
        ih, id_, ia, vig = implied(l2[idxs[0]]['oh'], l2[idxs[0]]['od'], l2[idxs[0]]['oa'])
        print(f"  主赔{name}(n={len(idxs)}) → H:{pct(oc['H'],len(idxs))} D:{pct(oc['D'],len(idxs))} A:{pct(oc['A'],len(idxs))}")

    print(f"\n--- B2 隐含概率 vs 实际命中率校准 (去水·热门低估?) ---")
    imp_bands = [(0, 0.40, '隐含<40%'), (0.40, 0.50, '40-50%'), (0.50, 0.65, '50-65%'), (0.65, 1.01, '>65%')]
    for lo, hi, name in imp_bands:
        idxs = []
        for i in range(n):
            r = l2[i]
            ih, _, _, _ = implied(r['oh'], r['od'], r['oa'])
            if lo <= ih < hi:
                idxs.append(i)
        if not idxs: continue
        hit = sum(1 for i in idxs if outcome(l2[i]) == 'H')
        avg_imp = sum(implied(l2[i]['oh'], l2[i]['od'], l2[i]['oa'])[0] for i in idxs) / len(idxs)
        print(f"  {name}(n={len(idxs)}) 隐含均值{100*avg_imp:.1f}% → 实际主胜 {pct(hit, len(idxs))} (差 {(100.0*hit/len(idxs) - 100*avg_imp):+.1f}pp)")

    print(f"\n--- B3 抽水率 (odd99 1x2和·欧盘口径) ---")
    vigs = [implied(r['oh'], r['od'], r['oa'])[3] for r in l2]
    print(f"  抽水倍数均值 {sum(vigs)/len(vigs):.4f} (抽水率 {100*(sum(vigs)/len(vigs)-1):.1f}%) | 范围 {min(vigs):.3f}-{max(vigs):.3f}")

    print(f"\n--- B4 亚盘盘口 → 主胜率/净胜 (rule61-66 验证) ---")
    hc_bands = [(-99, -0.75, '受让≥0.75'), (-0.75, -0.25, '受让0.25-0.5'), (-0.25, 0.25, '平手盘'),
                (0.25, 0.75, '主让0.25-0.5'), (0.75, 1.25, '主让0.75-1'), (1.25, 1.75, '主让1.25-1.5'),
                (1.75, 2.25, '主让1.75-2'), (2.25, 99, '主让≥2.25')]
    for lo, hi, name in hc_bands:
        idxs = [i for i in range(n) if lo <= l2[i]['hc'] < hi]
        if not idxs: continue
        oc = collections.Counter(outcome(l2[i]) for i in idxs)
        nw = [net_win(l2[i]) for i in idxs]
        c3 = sum(1 for x in nw if x >= 3)
        print(f"  {name}(n={len(idxs)}) → H:{pct(oc['H'],len(idxs))} D:{pct(oc['D'],len(idxs))} A:{pct(oc['A'],len(idxs))} | 主净胜3+ {pct(c3, len(idxs))}")

    print(f"\n--- B5 主队水位 → 主胜率 (对标 water_table 低水防御) ---")
    wb = [(0, 0.90, '低水<0.90'), (0.90, 0.95, '中水0.90-0.95'), (0.95, 99, '高水>0.95')]
    for lo, hi, name in wb:
        idxs = [i for i in range(n) if lo <= l2[i]['wh'] < hi]
        if not idxs: continue
        oc = collections.Counter(outcome(l2[i]) for i in idxs)
        print(f"  主{name}(n={len(idxs)}) → H:{pct(oc['H'],len(idxs))} D:{pct(oc['D'],len(idxs))} A:{pct(oc['A'],len(idxs))}")

    print(f"\n--- B6 水位×盘口联合 (深盘低水 vs 深盘高水) ---")
    for hc_name, lo, hi in [('深盘(让≥1.25)', 1.25, 99), ('中盘(让0.5-1)', 0.5, 1.25), ('浅盘(让<0.5/平手)', -99, 0.5)]:
        sub = [i for i in range(n) if lo <= l2[i]['hc'] < hi]
        if not sub: continue
        for w_name, wlo, whi in [('低水<0.90', 0, 0.90), ('中水0.90-0.95', 0.90, 0.95), ('高水>0.95', 0.95, 99)]:
            idxs = [i for i in sub if wlo <= l2[i]['wh'] < whi]
            if len(idxs) < 5: continue
            oc = collections.Counter(outcome(l2[i]) for i in idxs)
            print(f"  {hc_name}+{w_name}(n={len(idxs)}) → H:{pct(oc['H'],len(idxs))} D:{pct(oc['D'],len(idxs))} A:{pct(oc['A'],len(idxs))}")

    print(f"\n--- B7 欧亚背离 (欧盘深 vs 亚盘浅) ---")
    for name, cond in [('欧亚同深(欧隐≥55%+让≥1.25)', lambda r: implied(r['oh'],r['od'],r['oa'])[0]>=0.55 and r['hc']>=1.25),
                       ('欧亚同浅(欧隐<55%+让<1.25)', lambda r: implied(r['oh'],r['od'],r['oa'])[0]<0.55 and r['hc']<1.25),
                       ('欧深亚浅(欧隐≥55%+让<0.75·背离)', lambda r: implied(r['oh'],r['od'],r['oa'])[0]>=0.55 and r['hc']<0.75)]:
        idxs = [i for i in range(n) if cond(l2[i])]
        if not idxs: continue
        oc = collections.Counter(outcome(l2[i]) for i in idxs)
        print(f"  {name}(n={len(idxs)}) → H:{pct(oc['H'],len(idxs))} D:{pct(oc['D'],len(idxs))} A:{pct(oc['A'],len(idxs))}")

    print(f"\n--- B8 价值档 (隐含vs实际差·精算正期望候选) ---")
    for lo, hi, name in bands:
        idxs = [i for i in range(n) if lo <= l2[i]['oh'] < hi]
        if not idxs: continue
        hit = sum(1 for i in idxs if outcome(l2[i]) == 'H')
        avg_imp = sum(implied(l2[i]['oh'], l2[i]['od'], l2[i]['oa'])[0] for i in idxs) / len(idxs)
        print(f"  主赔{name}(n={len(idxs)}) 隐含均值{100*avg_imp:.1f}% → 实际 {pct(hit, len(idxs))} (差 {(100.0*hit/len(idxs)-100*avg_imp):+.1f}pp)")

    # 次回合欧赔主胜档 → 平局率 (修正46 欧战平局校准)
    print(f"\n--- B9 欧赔平局档 → 平局率 (修正46 欧战口径) ---")
    db = [(0, 3.0, '<3.0'), (3.0, 3.5, '3.0-3.5'), (3.5, 4.0, '3.5-4.0'), (4.0, 99, '>4.0')]
    for lo, hi, name in db:
        idxs = [i for i in range(n) if lo <= l2[i]['od'] < hi]
        if not idxs: continue
        d = sum(1 for i in idxs if outcome(l2[i]) == 'D')
        print(f"  平赔{name}(n={len(idxs)}) → 平局率 {pct(d, len(idxs))}")


def main():
    all_mode = '--all' in sys.argv
    files = ['欧冠_历史.csv']
    if all_mode:
        files = ['欧冠_历史.csv', '欧联_历史.csv', '欧协联_历史.csv']
    all_pairs = []
    for f in files:
        rows = load_csv(os.path.join(BASE, f))
        pairs = pair_legs(rows)
        print(f"{f}: 行{len(rows)} → 配对两回合组 {len(pairs)}")
        all_pairs.extend(pairs)
    tag = '欧战全量(欧冠+欧联+欧协联)' if all_mode else '欧冠'
    analyze(all_pairs, tag)

if __name__ == '__main__':
    main()
