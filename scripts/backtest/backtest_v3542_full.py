import csv
from collections import defaultdict

# ==================== V3.5.42 完整回测 ====================
import time
t0 = time.time()

OUT = defaultdict(lambda: [0, 0])  # [total, correct]
SCORE = defaultdict(int)  # both OK score distribution
LEAGUE = defaultdict(lambda: [0, 0, 0])  # [total, dir_ok, both_ok]
ASIAN = 0
ASIAN_COVER = 0
ASIAN_BY_DEPTH = defaultdict(lambda: [0, 0])

TOTAL = 0
with open('data/Matches.csv', 'r', encoding='utf-8', errors='ignore') as f:
    for row in csv.DictReader(f):
        oh = row.get('OddHome', '')
        oa = row.get('OddAway', '')
        od = row.get('OddDraw', '')
        o25 = row.get('Over25', '')
        u25 = row.get('Under25', '')
        mh = row.get('MaxHome', '')
        ma = row.get('MaxAway', '')
        eh = row.get('HomeElo', '')
        ea = row.get('AwayElo', '')
        f3h = row.get('Form3Home', '').strip()
        f3a = row.get('Form3Away', '').strip()
        hsz = row.get('HandiSize', '')
        hho = row.get('HandiHome', '')
        hao = row.get('HandiAway', '')
        result = row.get('FTResult', '')

        try:
            h = float(oh)
            a = float(oa)
            d = float(od)
            o25f = float(o25) if o25 else 0
            u25f = float(u25) if u25 else 0
        except:
            continue
        if h < 1.01 or a < 1.01:
            continue
        if result not in ('H', 'D', 'A'):
            continue
        try:
            fhg = int(float(row.get('FTHome', '0') or 0))
            fag = int(float(row.get('FTAway', '0') or 0))
        except:
            continue

        TOTAL += 1
        tg = fhg + fag
        div = row.get('Division', '')

        # === DIRECTION ===
        if h < a and h < d:
            pred = 'H'
            fav = h
        elif a < h and a < d:
            pred = 'A'
            fav = a
        else:
            pred = 'D'
        dir_ok = (pred == result)

        # === O/U ===
        if o25f > 0 and u25f > 0:
            ou_pred = 'O' if o25f < u25f else 'U'
            ou_ok = ((ou_pred == 'O' and tg > 2.5) or (ou_pred == 'U' and tg < 2.5))
        else:
            ou_ok = False
            ou_pred = '?'
        both_ok = (dir_ok and ou_ok)

        # === HARDCORE TIER (V3.5.40 base) ===
        is_deep = (min(h, a) < 1.30)
        skew = abs(h - a) / min(h, a)
        v40_high = is_deep or skew > 2.0
        v40_low = skew <= 1.0
        max_div = False
        max_high = False
        if mh and ma:
            try:
                mhf = float(mh)
                maf = float(ma)
                if mhf > h and maf > a:
                    s = (mhf - h) / h + (maf - a) / a
                    if s < 0.05:
                        max_div = True
                        v40_low = True
                    if s > 0.10:
                        max_high = True
            except:
                pass
        max_deep_sig = max_high and fav < 1.50
        if max_deep_sig:
            v40_high = True

        is_mild = (1.0 < skew <= 2.0)

        tier = 'high' if v40_high else ('low' if v40_low else 'mid')

        # === ELO CROSS-CHECK (修正41) ===
        elo_ok = False
        elo_bad = False
        if eh and ea:
            try:
                he = float(eh)
                ae = float(ea)
                elo_pred = 'H' if he > ae else 'A'
                if elo_pred == pred:
                    elo_ok = True
                else:
                    elo_bad = True
            except:
                pass

        form_ok = False
        if f3h and f3a:
            try:
                fh = float(f3h)
                fa = float(f3a)
                if (fh > fa and pred == 'H') or (fa > fh and pred == 'A'):
                    form_ok = True
            except:
                pass

        # === COUNT ===
        OUT['total'][0] += 1
        OUT['total'][1] += int(dir_ok)
        OUT['total_ou'][0] += 1
        OUT['total_ou'][1] += int(ou_ok)
        OUT['total_both'][0] += 1
        OUT['total_both'][1] += int(both_ok)

        for t in [tier, 'all']:
            OUT[t + '_dir'][0] += 1
            OUT[t + '_dir'][1] += int(dir_ok)
            OUT[t + '_both'][0] += 1
            OUT[t + '_both'][1] += int(both_ok)
            OUT[t + '_ou'][0] += 1
            OUT[t + '_ou'][1] += int(ou_ok)

        # 修正41 signals
        if elo_ok:
            OUT['elo_agree'][0] += 1
            OUT['elo_agree'][1] += int(dir_ok)
            if tier == 'high':
                OUT['high_elo_agree'][0] += 1
                OUT['high_elo_agree'][1] += int(dir_ok)
            elif tier == 'low':
                OUT['low_elo_agree'][0] += 1
                OUT['low_elo_agree'][1] += int(dir_ok)
        if elo_bad:
            OUT['elo_disagree'][0] += 1
            OUT['elo_disagree'][1] += int(dir_ok)
            if tier == 'high':
                OUT['high_elo_disagree'][0] += 1
                OUT['high_elo_disagree'][1] += int(dir_ok)

        # 三重确认
        if elo_ok and form_ok:
            OUT['triple'][0] += 1
            OUT['triple'][1] += int(dir_ok)

        # Both scores
        if both_ok:
            sk = '%d-%d' % (fhg, fag)
            SCORE[sk] += 1

        # Asian handicap
        if hsz and hho and hao:
            try:
                sz = float(hsz)
                hh = float(hho)
                ha = float(hao)
                if sz != 0 and hh > 0 and ha > 0:
                    diff = fhg - fag
                    if hh < ha:
                        cov_margin = sz
                    else:
                        cov_margin = -sz
                    if (hh < ha and diff > sz) or (hh > ha and -diff > abs(sz)):
                        cover = 1
                    elif diff == cov_margin:
                        cover = -1
                    else:
                        cover = 0

                    ASIAN += 1
                    if cover == 1:
                        ASIAN_COVER += 1

                    a_sz = abs(sz)
                    if a_sz <= 0.25:
                        dk = '0.25'
                    elif a_sz <= 0.5:
                        dk = '0.5'
                    elif a_sz <= 0.75:
                        dk = '0.75'
                    elif a_sz <= 1.0:
                        dk = '1.0'
                    elif a_sz <= 1.5:
                        dk = '1.5'
                    else:
                        dk = '1.75+'
                    ASIAN_BY_DEPTH[dk][0] += 1
                    if cover == 1:
                        ASIAN_BY_DEPTH[dk][1] += 1
            except:
                pass

        # League stats
        LEAGUE[div][0] += 1
        LEAGUE[div][1] += int(dir_ok)
        LEAGUE[div][2] += int(both_ok)

# ==================== OUTPUT ====================
BASE_DIR = OUT['total'][1] / TOTAL * 100
BASE_OU = OUT['total_ou'][1] / OUT['total_ou'][0] * 100
BASE_BOTH = OUT['total_both'][1] / OUT['total_both'][0] * 100

print('=' * 60)
print('V3.5.42 完整回测报告')
print('=' * 60)
print('总场次: %d | 基准方向: %.1f%% | 基准O/U: %.1f%% | 基准Both: %.1f%%' % (
    TOTAL, BASE_DIR, BASE_OU, BASE_BOTH))
print()

# 1. DIRECTION TIERS
print('--- 1. 方向分层准确率 (V3.5.40基座·V3.5.42沿用) ---')
hl = {}
for tier in ['high', 'mid', 'low']:
    k = tier + '_dir'
    t, c = OUT[k]
    acc = c / t * 100 if t > 0 else 0
    hl[tier] = (t, acc)
    print('  %-6s %8d  %.1f%%' % (tier.upper(), t, acc))
h_acc = hl['high'][1]
l_acc = hl['low'][1]
sep_dir = h_acc - l_acc
h_cov = hl['high'][0] / TOTAL * 100
l_cov = hl['low'][0] / TOTAL * 100
print('  分离度: %.1fpp | 高置信覆盖: %.1f%% | 低置信覆盖: %.1f%%' % (sep_dir, h_cov, l_cov))

# 2. BOTH TIERS (NEW in V3.5.42)
print()
print('--- 2. Both(方向+O/U)分层准确率 (V3.5.42新增) ---')
bl = {}
for tier in ['high', 'mid', 'low']:
    k = tier + '_both'
    t, c = OUT[k]
    acc = c / t * 100 if t > 0 else 0
    bl[tier] = (t, acc)
    print('  %-6s %8d  %.1f%%' % (tier.upper(), t, acc))
sep_both = bl['high'][1] - bl['low'][1]
print('  Both分离度: %.1fpp' % sep_both)

# 3. O/U by tier
print()
print('--- 3. O/U准确率分层 (O/U不受共识影响·验证) ---')
for tier in ['high', 'mid', 'low']:
    k = tier + '_ou'
    t, c = OUT[k]
    acc = c / t * 100 if t > 0 else 0
    print('  %-6s %8d  %.1f%%' % (tier.upper(), t, acc))

# 4. ELO CROSS-CHECK
print()
print('--- 4. 修正41 ELO交叉检查 ---')
t, c = OUT['elo_agree']
print('  ELO+Odds AGREE:      %8d  %.1f%%' % (t, c / t * 100))
t, c = OUT['elo_disagree']
print('  ELO+Odds DISAGREE:   %8d  %.1f%%' % (t, c / t * 100 if t > 0 else 0))
t, c = OUT['triple']
print('  三重确认(ELO+Form+Odds): %5d  %.1f%%' % (t, c / t * 100 if t > 0 else 0))
t, c = OUT['high_elo_agree']
print('  HIGH+ELO agree:      %8d  %.1f%%' % (t, c / t * 100 if t > 0 else 0))
t, c = OUT['high_elo_disagree']
if t > 0:
    print('  HIGH+ELO disagree(极罕见): %3d  %.1f%%' % (t, c / t * 100))

# 5. ASIAN HANDICAP
print()
print('--- 5. 修正42 穿盘深度 ---')
print('  全部穿盘: %d/%d = %.1f%%' % (ASIAN_COVER, ASIAN, ASIAN_COVER / ASIAN * 100 if ASIAN > 0 else 0))
for dk in ['0.5', '1.0', '1.5', '1.75+']:
    t, c = ASIAN_BY_DEPTH[dk]
    if t > 0:
        print('  让%-6s %8d  %.1f%%' % (dk, t, c / t * 100))

# 6. BOTH OK SCORE DISTRIBUTION
print()
print('--- 6. Both OK 比分分布 (修正42) ---')
sorted_scores = sorted(SCORE.items(), key=lambda x: x[1], reverse=True)[:15]
total_both_ok = OUT['total_both'][1]
for sk, cnt in sorted_scores:
    print('  %-6s %6d  %5.1f%%' % (sk, cnt, cnt / total_both_ok * 100))
cumulative = sum(c for _, c in sorted_scores)
print('  Top15累计: %.1f%%' % (cumulative / total_both_ok * 100))

# 7. VERSION COMPARISON
print()
print('=' * 60)
print('V3.5.40 vs V3.5.42 版本对比')
print('=' * 60)
print()
print('%-20s %12s %12s %12s' % ('指标', 'V3.5.40', 'V3.5.42', '变化'))
print('-' * 56)
print('%-20s %11.1f%% %11.1f%% %+11.1fpp' % ('方向基准', BASE_DIR, BASE_DIR, 0.0))
print('%-20s %11.1f%% %11.1f%% %+11.1fpp' % ('方向HIGH', 66.6, h_acc, h_acc - 66.6))
print('%-20s %11.1f%% %11.1f%% %+11.1fpp' % ('方向LOW', 41.9, l_acc, l_acc - 41.9))
print('%-20s %11.1fpp %11.1fpp %+11.1fpp' % ('方向分离度', 24.7, sep_dir, sep_dir - 24.7))
print('%-20s %11s %11.1f%% %+11s' % ('Both HIGH', '—', bl['high'][1], '新增'))
print('%-20s %11s %11.1f%% %+11s' % ('Both LOW', '—', bl['low'][1], '新增'))
print('%-20s %11s %11.1fpp %+11s' % ('Both分离度', '—', sep_both, '新增'))
elo_a = OUT['elo_agree'][1] / OUT['elo_agree'][0] * 100
elo_d = OUT['elo_disagree'][1] / OUT['elo_disagree'][0] * 100
print('%-20s %11s %11.1f%% %+11s' % ('ELO一致', '—', elo_a, '新增'))
print('%-20s %11s %11.1f%% %+11s' % ('ELO背离', '—', elo_d, '新增'))
triple_acc = OUT['triple'][1] / OUT['triple'][0] * 100
print('%-20s %11s %11.1f%% %+11s' % ('三重确认', '—', triple_acc, '新增'))
print('%-20s %11s %11s %+11.1fpp' % ('硬核修正数', '8', '10', 2))

elapsed = time.time() - t0
print()
print('回测耗时: %.0fs' % elapsed)
print('=' * 60)
