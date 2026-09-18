# -*- coding: utf-8 -*-
"""L2 增量表增益验证（2026-09-11·公平 A/B·时间分割）
设计:
  前80% = 建表期  → 得到"冻结表"(静态·仅用前80%统计·模拟现有 score_depth_table)
  后20% = 测试期·两种预测并行:
    A 冻结表(静态): 始终用前80%统计的 Top2
    B 在线表(增量): 每场用"截至当前"的统计(含前80%+已流过的测试场) → 模拟逐场更新
  指标: 比分 Top2 命中率 / Top1 命中率
结论判据: B 显著高于 A(p<0.05·二项) → 增量有增益·可谈接入; 否则不接入
"""
import os, sys, io, csv, math, json
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Matches.csv')
LIMIT = 60000


def cell(oh, od, oa, hs, o25):
    """格子键: 热门档|让球档|O25档（与 bayes_updater 一致思路）"""
    if oh < 1.5: hb = 'H1'
    elif oh < 2.1: hb = 'H2'
    elif oh < 3.0: hb = 'H3'
    else: hb = 'H4'
    if hs <= -1.75: db = 'D3'
    elif hs <= -0.75: db = 'D2'
    elif hs <= -0.25: db = 'D1'
    elif hs < 0.25: db = 'D0'
    elif hs < 0.75: db = 'A1'
    elif hs < 1.75: db = 'A2'
    else: db = 'A3'
    ob = 'O1' if o25 < 1.8 else ('O2' if o25 < 2.1 else 'O3')
    return '%s|%s|%s' % (hb, db, ob)


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
            rows.append((r['MatchDate'], cell(oh, od, oa, hs, o25), '%d:%d' % (h, a)))
            if len(rows) >= LIMIT:
                break
    rows.sort(key=lambda x: x[0])
    return rows


def top2(table, key, fallback):
    c = table.get(key)
    if not c or c['n'] < 20:
        c = fallback
    if not c or c['n'] == 0:
        return []
    return [s for s, _ in c['c'].most_common(2)]


def main():
    rows = load()
    n = len(rows); split = int(n * 0.8)
    print('样本 %d 场（时间排序·前80%%建表 / 后20%%测试）' % n)

    # 前 80% 建表（冻结）
    frozen = defaultdict(lambda: {'c': Counter(), 'n': 0})
    for _, k, sc in rows[:split]:
        frozen[k]['c'][sc] += 1; frozen[k]['n'] += 1
    global_c = Counter(sc for _, _, sc in rows[:split])
    global_fb = {'c': global_c, 'n': split}
    print('冻结表格子数: %d | 全局基准 top2: %s' % (len(frozen), [s for s, _ in global_c.most_common(2)]))

    # 测试期：A 冻结 / B 在线（在线表从冻结表副本开始·随测试场更新）
    online = {k: {'c': Counter(v['c']), 'n': v['n']} for k, v in frozen.items()}
    hitA1 = hitA2 = hitB1 = hitB2 = 0
    N = 0
    for _, k, sc in rows[split:]:
        N += 1
        ta = top2(frozen, k, global_fb)
        tb = top2(online, k, global_fb)
        if ta:
            if ta[0] == sc: hitA1 += 1
            if sc in ta[:2]: hitA2 += 1
        if tb:
            if tb[0] == sc: hitB1 += 1
            if sc in tb[:2]: hitB2 += 1
        # 在线更新
        if k not in online:
            online[k] = {'c': Counter(), 'n': 0}
        online[k]['c'][sc] += 1; online[k]['n'] += 1
        global_fb['c'][sc] += 1; global_fb['n'] += 1

    def pct(x): return x / N * 100
    print('\n=== 测试期命中率（n=%d）===' % N)
    print('%-22s %-12s %-12s %s' % ('指标', 'A冻结(静态)', 'B在线(增量)', '差'))
    print('%-22s %-12s %-12s %+.2fpp' % ('比分 Top1', '%.2f%%' % pct(hitA1), '%.2f%%' % pct(hitB1), pct(hitB1) - pct(hitA1)))
    print('%-22s %-12s %-12s %+.2fpp' % ('比分 Top2', '%.2f%%' % pct(hitA2), '%.2f%%' % pct(hitB2), pct(hitB2) - pct(hitA2)))

    # 简单显著性（Top2 配对差异·二项近似）
    b_only = 0; a_only = 0
    online2 = {k: {'c': Counter(v['c']), 'n': v['n']} for k, v in frozen.items()}
    gf = {'c': Counter(global_c), 'n': split}
    for _, k, sc in rows[split:]:
        ta = top2(frozen, k, global_fb)
        tb = top2(online2, k, gf)
        inA = sc in ta[:2] if ta else False
        inB = sc in tb[:2] if tb else False
        if inB and not inA: b_only += 1
        if inA and not inB: a_only += 1
        if k not in online2: online2[k] = {'c': Counter(), 'n': 0}
        online2[k]['c'][sc] += 1; online2[k]['n'] += 1
        gf['c'][sc] += 1; gf['n'] += 1
    disc = b_only + a_only
    if disc:
        z = (b_only - disc / 2) / math.sqrt(disc * 0.25)
        print('\n配对差异: 仅B中=%d / 仅A中=%d → z=%.2f（|z|>1.96 即 p<0.05）' % (b_only, a_only, z))
        verdict = '有显著增益·可考虑接入' if z > 1.96 else ('显著更差·不接入' if z < -1.96 else '无显著差异·不接入（增量无增益）')
        print('判定: %s' % verdict)
    else:
        print('\n无配对差异·判定: 不接入')
    print('\n⚠️ 诚实说明: 该验证模拟"逐场更新查表"·若 B 不优于 A → 增量表价值仅在长周期(跨赛季)数据更新·非短期预测增益')


if __name__ == '__main__':
    main()
