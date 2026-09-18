# -*- coding: utf-8 -*-
"""在线学习真实性验证（方案12.3 A/B）
方法: Matches.csv 按日期顺序 → 前80% 顺序 learn_one（模拟逐场进化）·每块记录滚动命中率
      → 后20% 只预测不学习（样本外）→ 对比热门基准与累积学习效果
输出: 学习曲线（是否逐场进化）+ 样本外命中率（是否真有效·防过拟合自证）
"""
import os, sys, io, csv, math
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import config as C
import river_models as RM

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Matches.csv')
LIMIT = 30000


def load():
    rows = []
    with open(SRC, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            try:
                oh = float(r['OddHome']); od = float(r['OddDraw']); oa = float(r['OddAway'])
                hs = float(r['HandiSize'] or 0)
                o25 = float(r['Over25'] or 0) or 1.9
                h = int(float(r['FTHome'])); a = int(float(r['FTAway']))
                elo = float(r['HomeElo'] or 0) - float(r['AwayElo'] or 0)
            except Exception:
                continue
            if not (oh > 1.0 and od > 1.0 and oa > 1.0):
                continue
            rows.append((r['MatchDate'], oh, od, oa, hs, o25, elo, h, a, r.get('Division', '?')))
            if len(rows) >= LIMIT:
                break
    rows.sort(key=lambda x: x[0])
    return rows


def feat(oh, od, oa, hs, o25, elo, div):
    return {'home_odds': oh, 'draw_odds': od, 'away_odds': oa, 'handicap': hs,
            'o25_odds': o25, 'league': div, 'league_id': C.LEAGUE_ID.get(div, 9),
            'is_top5': 1 if div in ('E0', 'SP1', 'I1', 'D1', 'F1') else 0,
            'is_europe': 0, 'elo_diff': elo, 'handicap_layer': 0}


def direction(h, a):
    return 1 if h > a else (2 if a > h else 0)


def main():
    rows = load()
    n = len(rows)
    split = int(n * 0.8)
    print('样本 %d 场（时间排序·前80%%学习 / 后20%%样本外测试）' % n)
    m = RM.load_models()
    block = max(500, n // 20)
    hits = 0; seen = 0
    curve = []
    base_hits = 0  # 热门基准（最低赔率方向）
    for i, (d, oh, od, oa, hs, o25, elo, h, a, div) in enumerate(rows[:split]):
        f = feat(oh, od, oa, hs, o25, elo, div)
        ad = direction(h, a)
        pred = RM.predict_before_learn(m, f)
        if pred:
            seen += 1
            if max(pred, key=pred.get) == ad: hits += 1
        # 热门基准
        fav = min(((oh, 1), (od, 0), (oa, 2)))[1]
        if fav == ad: base_hits += 1
        RM.learn_one(m, f, ad, h + a)
        if (i + 1) % block == 0 and seen:
            curve.append((i + 1, round(hits / seen, 4), round(base_hits / (i + 1), 4)))
    RM.save_models(m)
    print('\n=== 学习曲线（训练期·每%d场累计命中率）===' % block)
    print('%-8s %-12s %-12s' % ('场次', '在线模型', '热门基准'))
    for idx, acc, base in curve:
        flag = ' ↑' if acc > base else '  '
        print('%-8d %-12s %-12s%s' % (idx, '%.1f%%' % (acc * 100), '%.1f%%' % (base * 100), flag))

    # 样本外（后20%·只预测）
    oos_hit = oos_n = oos_base = 0
    per_block = []
    bh = bn = 0
    for j, (d, oh, od, oa, hs, o25, elo, h, a, div) in enumerate(rows[split:]):
        f = feat(oh, od, oa, hs, o25, elo, div)
        ad = direction(h, a)
        pred = RM.predict_before_learn(m, f)
        oos_n += 1
        if pred and max(pred, key=pred.get) == ad: oos_hit += 1
        if min(((oh, 1), (od, 0), (oa, 2)))[1] == ad: oos_base += 1
        if (j + 1) % 1000 == 0:
            per_block.append((j + 1, round(oos_hit / oos_n, 4), round(oos_base / (j + 1), 4)))
    print('\n=== 样本外测试（后20%%·学习期未见过）===')
    print('在线模型: %d/%d = %.2f%%' % (oos_hit, oos_n, oos_hit / oos_n * 100))
    print('热门基准: %d/%d = %.2f%%' % (oos_base, oos_n, oos_base / oos_n * 100))
    print('差值: %+.2fpp' % ((oos_hit / oos_n - oos_base / oos_n) * 100))
    st = RM.status()
    print('\n在线样本量: %d | 权重: 方向=%.2f 进球=%.2f | 漂移: %s' % (
        st['n_direction'], st['weight_dir'], st['weight_goals'], st['drift']))
    print('⚠️ 诚实说明: 若样本外无提升 → 在线ML在该特征集上增益有限(仅作低权重源)·不可声称进化')


if __name__ == '__main__':
    main()
