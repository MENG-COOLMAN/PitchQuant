# -*- coding: utf-8 -*-
"""欧冠校准复核 v2：严格按 N24 口径（只用正赛「联赛」76 场做控制分档）
修正 v1 两处：①轮次键是「联赛」不是「联赛阶段」 ②控制分档须只用正赛（混入资格赛会稀释）
"""
import csv, io, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')


def load(path):
    out = []
    for r in csv.DictReader(io.open(path, encoding='utf-8-sig')):
        sc = (r.get('score') or '').strip()
        if ':' not in sc:
            continue
        try:
            h, a = [int(x) for x in sc.split(':')[:2]]
            oh = float(r.get('odd99_h') or 0)
        except (ValueError, TypeError):
            continue
        out.append({'round': (r.get('round') or '').strip(), 'tot': h + a, 'oh': oh,
                    'h': h, 'a': a})
    return out


def st(rows, tag):
    n = len(rows)
    if not n:
        print('  %-24s n=0' % tag); return None
    m = sum(x['tot'] for x in rows) / n
    o25 = sum(1 for x in rows if x['tot'] >= 3) / n * 100
    o35 = sum(1 for x in rows if x['tot'] >= 4) / n * 100
    p6 = sum(1 for x in rows if x['tot'] >= 6) / n * 100
    print('  %-24s n=%-4d 均球 %5.2f ｜ O2.5 %5.1f%% ｜ O3.5 %5.1f%% ｜ P(≥6球) %4.1f%%'
          % (tag, n, m, o25, o35, p6))
    return {'n': n, 'mean': m, 'o25': o25, 'o35': o35, 'p6': p6}


ucl = load('data/europe/欧冠_历史.csv')
print('欧冠历史库 %d 场' % len(ucl))
print('\n=== ① 按轮次精确分层（关键：正赛 = round「联赛」）===')
MAIN = [x for x in ucl if x['round'] == '联赛']
QUAL = [x for x in ucl if any(k in x['round'] for k in ('资格', '附加'))]
KO = [x for x in ucl if x['round'] not in ('联赛',) and not any(k in x['round'] for k in ('资格', '附加'))]
main_s = st(MAIN, '★正赛(联赛阶段)')
st(KO, '淘汰赛/附加赛次回合')
st(QUAL, '资格赛+附加赛')
print('  合计 %d + %d + %d = %d' % (len(MAIN), len(KO), len(QUAL), len(MAIN) + len(KO) + len(QUAL)))

print('\n=== ② 五大基线（Matches.csv 148,397 场实测参考）===')
print('  五大联赛基线              n=148397 均球  2.69 ｜ O2.5  50.4% ｜ O3.5  28.8%')

print('\n=== ③ 未控制分档的原始差（会高估·因欧冠强队为主）===')
if main_s:
    print('  欧冠正赛 %.2f vs 五大 2.69 → 未控制差 **%+.2f 球** ｜ O2.5 %+.1fpp'
          % (main_s['mean'], main_s['mean'] - 2.69, main_s['o25'] - 50.4))

print('\n=== ④ 🔴控制主胜赔率档（N24 的正确口径·只用正赛 76 场）===')
mrows = []
for r in csv.DictReader(io.open('data/Matches.csv', encoding='utf-8', errors='ignore')):
    try:
        h = int(float(r['FTHome'])); a = int(float(r['FTAway'])); oh = float(r['OddHome'])
    except (ValueError, TypeError, KeyError):
        continue
    if 1.0 < oh < 30:
        mrows.append({'oh': oh, 'tot': h + a})

BANDS = [(0, 1.50), (1.50, 1.80), (1.80, 2.10), (2.10, 2.50), (2.50, 99)]
print('  %-11s %-20s %-20s %-9s %s' % ('主胜赔率档', '欧冠正赛', '五大同档', '差(球)', '差(O2.5)'))
wsum = wtot = 0.0
for lo, hi in BANDS:
    u = [x for x in MAIN if lo <= x['oh'] < hi]
    m = [x for x in mrows if lo <= x['oh'] < hi]
    if len(u) < 3 or len(m) < 200:
        print('  %-11s n不足(欧冠%d)' % ('%g-%g' % (lo, hi), len(u)))
        continue
    um = sum(x['tot'] for x in u) / len(u)
    mm = sum(x['tot'] for x in m) / len(m)
    u25 = sum(1 for x in u if x['tot'] >= 3) / len(u) * 100
    m25 = sum(1 for x in m if x['tot'] >= 3) / len(m) * 100
    print('  %-11s n=%-3d 均球 %5.2f   n=%-6d 均球 %5.2f  %+.2f     %+.1fpp'
          % ('%g-%g' % (lo, hi), len(u), um, len(m), mm, um - mm, u25 - m25))
    wsum += (um - mm) * len(u)
    wtot += len(u)
if wtot:
    print('\n  🔴 按欧冠样本加权平均差 = **%+.2f 球**（N24 现用 +0.67）' % (wsum / wtot))

print('\n=== ⑤ 判定 ===')
if wtot:
    d = wsum / wtot
    if 0.4 <= d <= 1.0:
        print('  ✅ N24 (+0.67) 仍在合理区间（控制后差 %+.2f）' % d)
    elif d < 0.4:
        print('  ⚠️ 控制后差仅 %+.2f 球 → 显著低于 N24 +0.67 → **建议下调或改为分档校准**' % d)
    else:
        print('  ⚠️ 控制后差 %+.2f 球 → 高于 N24 → 建议上调' % d)
print('\n  ⚠️ 诚实边界: 正赛仅 %d 场（单赛季 2025-10~2026-01）·无法时间分割' % len(MAIN))
