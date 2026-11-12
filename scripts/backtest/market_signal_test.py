# -*- coding: utf-8 -*-
"""检验：市场信号在方向判定中的占比（纯回测·时间分割·2026-09-13）"""
import sys, io, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
rows = []
with open('data/Matches.csv', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        try:
            oh = float(r['OddHome']); od = float(r['OddDraw']); oa = float(r['OddAway'])
            h = int(float(r['FTHome'])); a = int(float(r['FTAway']))
        except Exception:
            continue
        if not (oh > 1 and od > 1 and oa > 1):
            continue
        inv = {1: 1/oh, 0: 1/od, 2: 1/oa}; t = sum(inv.values())
        p = {k: v/t for k, v in inv.items()}
        top = max(p, key=p.get); srt = sorted(p.values(), reverse=True)
        rows.append({'p': p, 'top': top, 'skew': srt[0]/srt[1]*100,
                     'real': 1 if h > a else (2 if a > h else 0)})
n = len(rows)
print('样本 %d 场' % n)
print()
print('%-28s %-10s %-10s %-10s %s' % ('策略', '全样本', 'skew<150', 'skew>=150', '说明'))
def ev(fn, pool):
    return sum(1 for r in pool if fn(r)) / max(len(pool), 1) * 100
pools = {'all': rows, 'w': [r for r in rows if r['skew'] < 150], 's': [r for r in rows if r['skew'] >= 150]}
# S1 纯市场首选
f1 = lambda r: r['top'] == r['real']
# S2 市场首选 + 平局并列（弱共识场）
f2 = lambda r: (r['top'] == r['real']) or (r['skew'] < 150 and r['real'] == 0)
# S3 市场首选 + 平局并列（全档）
f3 = lambda r: (r['top'] == r['real']) or (r['real'] == 0)
# S4 平局优先（平赔最低时选平·否则市场首选）
f4 = lambda r: (0 if r['p'][0] == max(r['p'].values()) else r['top']) == r['real']
for label, fn, note in (
    ('S1 纯市场首选', f1, '市场单方向'),
    ('S2 市场+平局并列(仅弱共识)', f2, '今日新铁律'),
    ('S3 市场+平局并列(全档)', f3, '宽松口径'),
    ('S4 平赔最低优先', f4, '平局优先策略'),
):
    print('%-28s %-10s %-10s %-10s %s' % (
        label, '%.1f%%' % ev(fn, pools['all']), '%.1f%%' % ev(fn, pools['w']),
        '%.1f%%' % ev(fn, pools['s']), note))
print()
print('=== 关键: 纯市场 vs 热门基准 ===')
hot = sum(1 for r in rows if (1 if r['p'][1] >= max(r['p'].values()) else 0) == r['real'])
print('  随机基准 33.3%% | 纯市场首选 %.1f%%' % ev(f1, rows))
print()
print('=== 市场隐含概率的校准度（是否可信）===')
for lo, hi in ((0, .25), (.25, .35), (.35, .45), (.45, .55), (.55, .70), (.70, 1.01)):
    sub = [r for r in rows if lo <= r['p'][r['top']] < hi]
    if len(sub) < 200:
        continue
    pred = sum(r['p'][r['top']] for r in sub) / len(sub) * 100
    act = sum(1 for r in sub if r['top'] == r['real']) / len(sub) * 100
    print('  市场最高概率 %.0f-%.0f%% (n=%d): 预测 %.1f%% → 实际 %.1f%% (差 %+.1fpp)' % (
        lo*100, hi*100, len(sub), pred, act, act - pred))
