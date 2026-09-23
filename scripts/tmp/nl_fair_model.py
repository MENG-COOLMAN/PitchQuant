# -*- coding: utf-8 -*-
"""欧国联公平赔率模型 v2 —— P0-2（修正 v1 共线不可辨识问题）
v1 问题: base 与 adv 共线(均作用λ斜率) → 网格边界解
v2 方案: ①固定 adv=60.7(A先验/国际赛事常规) 只拟合 base/sh/sa  ②全参数大网格多起点对照
"""
import csv, io, math, json, sys, os
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
D = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(D, 'nl_data', 'nl_with_elo.csv')


def load(path=DATA):
    R = []
    for r in csv.DictReader(io.open(path, encoding='utf-8')):
        try:
            R.append({'date': r['date'], 'hs': int(r['hs']), 'as': int(r['sa']),
                      'eh': float(r['eh']), 'ea': float(r['ea'])})
        except Exception:
            continue
    R.sort(key=lambda x: x['date'])
    return R


def lam(r, p):
    d = (r['eh'] + p['adv']) - r['ea']
    return max(math.exp(p['base'] + p['sh'] * d), 1e-6), max(math.exp(p['base'] + p['sa'] * (-d)), 1e-6)


def loglik(rows, p):
    s = 0.0
    for r in rows:
        lh, la = lam(r, p)
        s += -lh + r['hs'] * math.log(lh) - la + r['as'] * math.log(la)
    return s


def fit(rows, free_adv, grids, starts, rounds=6):
    best_p, best_s = None, -1e18
    for st in starts:
        p = dict(st)
        s = loglik(rows, p)
        for _ in range(rounds):
            for k in (('base', 'sh', 'sa', 'adv') if free_adv else ('base', 'sh', 'sa')):
                cur = p[k]
                for v in grids[k]:
                    p[k] = v
                    t = loglik(rows, p)
                    if t > s:
                        s, cur = t, v
                p[k] = cur
        if s > best_s:
            best_p, best_s = dict(p), s
    return best_p, best_s


def pmf(k, l):
    return math.exp(-l) * l ** k / math.factorial(k)


def predict(r, p, maxg=9):
    lh, la = lam(r, p)
    H = Dd = A = 0.0
    for i in range(maxg):
        for j in range(maxg):
            q = pmf(i, lh) * pmf(j, la)
            if i > j: H += q
            elif i == j: Dd += q
            else: A += q
    t = H + Dd + A
    return H / t, Dd / t, A / t, lh, la


def evaluate(te, p):
    hit = 0
    bk = {'<0.40': [0, 0], '0.40-0.50': [0, 0], '0.50-0.60': [0, 0], '≥0.60': [0, 0]}
    o_ok = o_n = 0
    for r in te:
        ph, pd, pa, lh, la = predict(r, p)
        b = max(ph, pd, pa)
        act = 'H' if r['hs'] > r['as'] else ('D' if r['hs'] == r['as'] else 'A')
        pr = 'H' if b == ph else ('D' if b == pd else 'A')
        hit += (pr == act)
        k = '<0.40' if b < .4 else ('0.40-0.50' if b < .5 else ('0.50-0.60' if b < .6 else '≥0.60'))
        bk[k][1] += 1; bk[k][0] += (pr == act)
        ov = sum(pmf(i, lh) * pmf(j, la) for i in range(9) for j in range(9) if i + j >= 3)
        if ov > 0.5:
            o_n += 1
            o_ok += (r['hs'] + r['as'] >= 3)
    return hit, len(te), bk, (o_ok, o_n)


def main():
    R = load()
    cut = int(len(R) * .8)
    tr, te = R[:cut], R[cut:]
    print('═══ 数据 ═══  总 %d | 训练 %d (%s~%s) | 验证 %d (%s~%s)' % (
        len(R), len(tr), tr[0]['date'], tr[-1]['date'], len(te), te[0]['date'], te[-1]['date']))

    print('\n═══ 方案① 固定 adv=60.7（A 先验）只拟合 base/sh/sa ═══')
    g1 = {'base': [0.80 + i * 0.005 for i in range(141)],
          'sh': [0.0005 + i * 0.00002 for i in range(151)],
          'sa': [0.0005 + i * 0.00002 for i in range(151)]}
    s1 = [{'base': 1.13, 'sh': .002, 'sa': .0017, 'adv': 60.7},
          {'base': .95, 'sh': .001, 'sa': .002, 'adv': 60.7},
          {'base': 1.25, 'sh': .003, 'sa': .001, 'adv': 60.7}]
    p1, l1 = fit(tr, False, g1, s1)
    print('  base=%.4f  slope主=%.5f  slope客=%.5f  adv=%.1f  LL=%.1f' % (p1['base'], p1['sh'], p1['sa'], p1['adv'], l1))
    h, n, bk, (oo, on) = evaluate(te, p1)
    print('  → 方向 %d/%d = %.1f%% | ≥0.60档 %s | O2.5 %s' % (
        h, n, h / n * 100,
        '%.1f%%(n=%d)' % (bk['≥0.60'][0] / bk['≥0.60'][1] * 100, bk['≥0.60'][1]) if bk['≥0.60'][1] else '—',
        '%.1f%%(n=%d)' % (oo / on * 100, on) if on else '—'))
    for k in ('<0.40', '0.40-0.50', '0.50-0.60', '≥0.60'):
        o, t = bk[k]
        print('     %-10s n=%3d → %s' % (k, t, '%.1f%%' % (o / t * 100) if t else '—'))

    print('\n═══ 方案② 全参数大网格多起点（对照）═══')
    g2 = {'base': [0.7 + i * 0.01 for i in range(91)],
          'sh': [0.0002 + i * 0.00004 for i in range(96)],
          'sa': [0.0002 + i * 0.00004 for i in range(96)],
          'adv': [0.0 + i * 10.0 for i in range(16)]}
    s2 = [{'base': 1.13, 'sh': .002, 'sa': .0017, 'adv': 60}, {'base': 1.0, 'sh': .001, 'sa': .002, 'adv': 0},
          {'base': 1.4, 'sh': .003, 'sa': .001, 'adv': 100}]
    p2, l2 = fit(tr, True, g2, s2, rounds=4)
    print('  base=%.4f  slope主=%.5f  slope客=%.5f  adv=%.1f  LL=%.1f' % (p2['base'], p2['sh'], p2['sa'], p2['adv'], l2))
    h2, n2, bk2, (oo2, on2) = evaluate(te, p2)
    print('  → 方向 %d/%d = %.1f%% | O2.5 %s' % (h2, n2, h2 / n2 * 100,
                                                  '%.1f%%(n=%d)' % (oo2 / on2 * 100, on2) if on2 else '—'))

    print('\n═══ 基准对照 ═══')
    base_hit = sum(1 for r in te if (r['hs'] > r['as'])) / len(te)
    print('  验证集主胜率(恒押主) = %.1f%% | 热门基准需赔率(无历史赔率·不可算)' % (base_hit * 100))
    print('  A 报告声称: 方向 53.8%% / ≥0.60 档 74.4%% / O2.5 60.9%%')

    # 选择方案①（参数可辨识）保存
    out = {'version': 'v2', 'params': p1, 'params_free': p2, 'cut': cut, 'n': len(R),
           'train_ll': l1, 'valid': {'hit': h, 'n': n, 'acc': h / n,
                                     'buckets': {k: {'ok': v[0], 'n': v[1]} for k, v in bk.items()},
                                     'o25': {'ok': oo, 'n': on}},
           'baseline_home': base_hit,
           'gate': {'dir_min': 0.538, 'hi_min': 0.70, 'passed': bool(h / n >= 0.538 and (bk['≥0.60'][1] and bk['≥0.60'][0] / bk['≥0.60'][1] >= 0.70))}}
    dst = os.path.join(D, 'nl_data', 'fair_model.json')
    json.dump(out, io.open(dst, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n🔴 门禁判定(方向≥53.8%% 且 ≥0.60档≥70%%): %s' % ('✅ 通过' if out['gate']['passed'] else '❌ 未通过'))
    print('✅ 已保存 %s' % dst)


if __name__ == '__main__':
    main()
