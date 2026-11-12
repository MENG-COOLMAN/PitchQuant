# -*- coding: utf-8 -*-
"""量级机制诊断工具（2026-11-03·用户质疑「量级把控差点意思·是市场不准还是机制有问题」）

三段判据：
  ① 市场期望是否无偏（案例库台账 期望分布 反推 vs 实际层）
  ② 「五源」是否真独立（两两相关系数 + 极差）
  ③ 「均值+固定带宽」是否削掉了真实尾部（分布 P(≥4球) vs 档内容量）
用法: python data/tmp/magnitude_diag.py [--cases N]
"""
import io, csv, sys, argparse, statistics as st
sys.path.insert(0, 'data/tmp')
sys.stdout.reconfigure(encoding='utf-8')

BIN_MID = {'0-1球': 0.8, '2球': 2.0, '3球': 3.0, '4+球': 4.8}


def _parse_dist(s):
    try:
        a = [float(x) for x in str(s).replace('%', '').split('/')]
        if len(a) != 4:
            return None
        return (a[0] * 0.8 + a[1] * 2.0 + a[2] * 3.0 + a[3] * 4.8) / 100.0
    except Exception:
        return None


def part1_bias():
    """① 市场期望 vs 我的锚 vs 实际 —— 谁偏、偏多少"""
    rows = list(csv.DictReader(io.open('data/case-library/量级台账.csv', encoding='utf-8-sig')))
    E, A, M = [], [], []
    for r in rows:
        e = _parse_dist(r.get('期望分布(0-1/2/3/4+%)'))
        a = BIN_MID.get(str(r.get('实际层', '')).strip())
        m = BIN_MID.get(str(r.get('预测层(众数)', '')).strip())
        if e is None or a is None:
            continue
        E.append(e); A.append(a); M.append(m)
    print('=== ① 市场期望 / 我的锚 / 实际（n=%d）===' % len(E))
    if not E:
        print('  ⚪ 台账无可用分布'); return
    for nm, arr in (('市场期望E', E), ('我的锚(众数)', M)):
        d = [p - a for p, a in zip(arr, A) if p is not None]
        if not d:
            continue
        print('  %-12s 偏差均值 %+.3f ｜ σ %.3f ｜ MAE %.3f ｜ |偏差|≤1.0 %.1f%%'
              % (nm, st.mean(d), st.pstdev(d), st.mean(abs(x) for x in d),
                 sum(1 for x in d if abs(x) <= 1.0) / len(d) * 100))
    print('  实际均值 %.3f ｜ 市场E均值 %.3f ｜ 锚均值 %.3f'
          % (st.mean(A), st.mean(E), st.mean(x for x in M if x is not None)))
    be = sum(1 for e, a, m in zip(E, A, M) if m is not None and abs(e - a) < abs(m - a) - 1e-9)
    bm = sum(1 for e, a, m in zip(E, A, M) if m is not None and abs(m - a) < abs(e - a) - 1e-9)
    print('  逐场更准: 市场 %d ｜ 我的锚 %d' % (be, bm))
    print('  形态(σ / ≥4球占比): 市场E %.3f / %.0f%% ｜ 锚 %.3f / %.0f%% ｜ 实际 %.3f / %.0f%%'
          % (st.pstdev(E), sum(1 for x in E if x > 3.5) / len(E) * 100,
             st.pstdev([x for x in M if x is not None]),
             sum(1 for x in M if x is not None and x > 3.5) / len([x for x in M if x is not None]) * 100,
             st.pstdev(A), sum(1 for x in A if x > 3.5) / len(A) * 100))


def part2_sources():
    """② 五源独立性 —— 相关系数 >0.9 即证明伪多源"""
    import magnitude_band as MB
    print('\n=== ② 「五源」独立性（r>0.9 = 同一信号的副本）===')
    combos = [(1.40, 3.60, 3.55), (1.56, 3.13, 3.43), (1.77, 2.90, 2.85),
              (2.10, 2.40, 2.35), (2.28, 2.36, 2.20), (2.50, 2.10, 2.10)]
    rows = []
    for o25, lam, line in combos:
        r = MB.magnitude_band(o25=o25, lam=lam, line=line)
        src = {k: v for k, v in (r.get('sources') or {}).items() if isinstance(v, (int, float)) and v > 0}
        rows.append((o25, src, r.get('center')))
        rng = (max(src.values()) - min(src.values())) if len(src) > 1 else 0
        print('  O2.5=%.2f → %s ｜ 极差 %.3f' % (o25, {k: round(v, 2) for k, v in src.items()}, rng))
    keys = sorted(set().union(*[set(x[1].keys()) for x in rows])) if rows else []
    for i, k1 in enumerate(keys):
        for k2 in keys[i + 1:]:
            xs = [x[1].get(k1) for x in rows]
            ys = [x[1].get(k2) for x in rows]
            if None in xs or None in ys:
                continue
            mx, my = st.mean(xs), st.mean(ys)
            sx, sy = st.pstdev(xs), st.pstdev(ys)
            if sx > 1e-9 and sy > 1e-9:
                cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / len(xs)
                r_ = cov / (sx * sy)
                flag = '🔴伪独立' if r_ > 0.9 else ('⚠️偏高' if r_ > 0.7 else '✅独立')
                print('  %-9s vs %-9s r=%+.4f %s' % (k1, k2, r_, flag))


def part3_tail():
    """③ 固定带宽 ±1 是否削掉真实尾部"""
    print('\n=== ③ 「均值+固定带宽」vs 真实尾部 ===')
    try:
        import goal_bin_probs_data as _  # noqa: F401  (占位·防误 import)
    except Exception:
        pass
    import json
    try:
        t = json.load(io.open('data/tmp/goal_bins_table.json', encoding='utf-8'))
    except Exception as e:
        print('  ⚪ goal_bins_table 不可用:', e); return
    print('  %-8s %-8s %-10s %-10s %-10s' % ('O2.5档', '期望E', 'P(2-3球)', 'P(≥4球)', '「±1」漏掉'))
    for band in list(t.keys())[:8]:
        v = t[band]
        if not isinstance(v, dict):
            continue
        p01 = v.get('0-1') or v.get('0_1') or 0
        p2 = v.get('2') or 0
        p3 = v.get('3') or 0
        p4 = v.get('4+') or v.get('4') or 0
        try:
            p01, p2, p3, p4 = float(p01), float(p2), float(p3), float(p4)
        except Exception:
            continue
        if p01 < 1:
            p01, p2, p3, p4 = p01 * 100, p2 * 100, p3 * 100, p4 * 100
        E = (p01 * 0.8 + p2 * 2 + p3 * 3 + p4 * 4.8) / 100
        print('  %-8s %-8.2f %-10.1f %-10.1f %-10.1f'
              % (band, E, p2 + p3, p4, p01 + p4))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases', type=int, default=0, help='仅显示最近 N 场明细')
    a = ap.parse_args()
    part1_bias()
    part2_sources()
    part3_tail()
