import csv

# vs 对比回测
OUT = {
    'total': [0, 0],
    'v40_high': [0, 0],  # V3.5.40 high confidence
    'v40_mid': [0, 0],   # V3.5.40 medium confidence
    'v40_low': [0, 0],   # V3.5.40 low confidence
    'v41_high': [0, 0],  # V3.5.41 high (ELO agree added)
    'v41_mid': [0, 0],
    'v41_low': [0, 0],
    'elo_agree': [0, 0],  # ELO agree only
    'elo_disagree': [0, 0],
    'elo_form_odds': [0, 0],  # triple: ELO+Form+Odds agree
    'deep': [0, 0],
    'extreme': [0, 0],
    'mild': [0, 0],
    'no_cons': [0, 0],
    'max_deep': [0, 0],
}

with open('data/Matches.csv', 'r', encoding='utf-8', errors='ignore') as f:
    for row in csv.DictReader(f):
        oh = row.get('OddHome', '')
        oa = row.get('OddAway', '')
        od = row.get('OddDraw', '')
        mh = row.get('MaxHome', '')
        ma = row.get('MaxAway', '')
        eh = row.get('HomeElo', '')
        ea = row.get('AwayElo', '')
        f3h = row.get('Form3Home', '').strip()
        f3a = row.get('Form3Away', '').strip()
        result = row.get('FTResult', '')
        if not oh or not oa or not od:
            continue
        try:
            h = float(oh)
            a = float(oa)
            d = float(od)
            if h < 1.01 or a < 1.01:
                continue
        except:
            continue
        if result not in ('H', 'D', 'A'):
            continue

        # Direction
        if h < a and h < d:
            pred = 'H'
            fav = h
        elif a < h and a < d:
            pred = 'A'
            fav = a
        else:
            pred = 'D'
            continue
        correct = (pred == result)
        OUT['total'][0] += 1
        OUT['total'][1] += int(correct)

        # Hard signals
        is_deep = (min(h, a) < 1.30)
        skew = abs(h - a) / min(h, a)
        is_extreme = (skew > 2.0)
        is_mild = (1.0 < skew <= 2.0)
        is_no_cons = (skew <= 1.0)

        max_div = False
        max_high = False
        if mh and ma:
            try:
                mhf = float(mh)
                maf = float(ma)
                if mhf > h and maf > a:
                    spread = (mhf - h) / h + (maf - a) / a
                    if spread < 0.05:
                        max_div = True
                    if spread > 0.10:
                        max_high = True
            except:
                pass

        max_deep_sig = max_high and fav < 1.50

        # ELO signal
        elo_ok = False
        elo_bad = False
        form_ok = False
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
        if f3h and f3a:
            try:
                fh = float(f3h)
                fa = float(f3a)
                if (fh > fa and pred == 'H') or (fa > fh and pred == 'A'):
                    form_ok = True
            except:
                pass

        # confidence
        v40_conf = 'mid'
        if is_deep or is_extreme or max_deep_sig:
            v40_conf = 'high'
        elif is_no_cons or max_div:
            v40_conf = 'low'
        elif is_mild and fav < 1.70:
            v40_conf = 'high'

        OUT['v40_' + v40_conf][0] += 1
        OUT['v40_' + v40_conf][1] += int(correct)

        # confidence (adds ELO)
        v41_conf = v40_conf
        if elo_ok:
            if v41_conf == 'mid':
                v41_conf = 'high'
            elif v41_conf == 'low':
                v41_conf = 'mid'
        if elo_bad:
            if v41_conf == 'high':
                v41_conf = 'mid'
            elif v41_conf == 'mid':
                v41_conf = 'low'

        OUT['v41_' + v41_conf][0] += 1
        OUT['v41_' + v41_conf][1] += int(correct)

        # Subs
        if is_deep:
            OUT['deep'][0] += 1
            OUT['deep'][1] += int(correct)
        if is_extreme:
            OUT['extreme'][0] += 1
            OUT['extreme'][1] += int(correct)
        if is_mild:
            OUT['mild'][0] += 1
            OUT['mild'][1] += int(correct)
        if is_no_cons:
            OUT['no_cons'][0] += 1
            OUT['no_cons'][1] += int(correct)
        if max_deep_sig:
            OUT['max_deep'][0] += 1
            OUT['max_deep'][1] += int(correct)
        if elo_ok:
            OUT['elo_agree'][0] += 1
            OUT['elo_agree'][1] += int(correct)
        if elo_bad:
            OUT['elo_disagree'][0] += 1
            OUT['elo_disagree'][1] += int(correct)
        if elo_ok and form_ok:
            OUT['elo_form_odds'][0] += 1
            OUT['elo_form_odds'][1] += int(correct)

TOTAL = OUT['total'][0]
BASE = OUT['total'][1] / TOTAL * 100

print('=' * 55)
print('V3.5.40 vs V3.5.41 Backtest')
print('Total: %d | Baseline: %.1f%%' % (TOTAL, BASE))
print('=' * 55)

# Confidence comparison
print()
print('--- Confidence Tier Comparison ---')
for ver, key in [('V3.5.40', 'v40'), ('V3.5.41', 'v41')]:
    print('%s:' % ver)
    for conf in ['high', 'mid', 'low']:
        k = key + '_' + conf
        t, c = OUT[k]
        if t > 0:
            print('  %s: %8d  %.1f%%' % (conf, t, c / t * 100))
    # separation
    h_acc = OUT[key + '_high'][1] / max(1, OUT[key + '_high'][0]) * 100
    l_acc = OUT[key + '_low'][1] / max(1, OUT[key + '_low'][0]) * 100
    h_cov = OUT[key + '_high'][0] / TOTAL * 100
    l_cov = OUT[key + '_low'][0] / TOTAL * 100
    print('  separation: %.1fpp | high coverage: %.1f%% | low coverage: %.1f%%' % (h_acc - l_acc, h_cov, l_cov))

# Delta
print()
print('--- V3.5.41 vs V3.5.40 Delta ---')
for conf in ['high', 'mid', 'low']:
    v40_t, v40_c = OUT['v40_' + conf]
    v41_t, v41_c = OUT['v41_' + conf]
    if v40_t > 0 and v41_t > 0:
        d_acc = v41_c / v41_t * 100 - v40_c / v40_t * 100
        d_cnt = v41_t - v40_t
        print('  %s: acc %+.1fpp | count %+d' % (conf, d_acc, d_cnt))

# ELO detail
print()
print('--- ELO Signal Detail ---')
t, c = OUT['elo_agree']
print('ELO+Odds AGREE: %8d  %.1f%%' % (t, c / t * 100))
t, c = OUT['elo_disagree']
print('ELO+Odds DISAGREE: %5d  %.1f%%' % (t, c / t * 100))

# Triple
t, c = OUT['elo_form_odds']
if t > 0:
    print('ELO+Form+Odds (Triple): %5d  %.1f%%' % (t, c / t * 100))

# Overall upgrade
print()
print('--- V3.5.40 -> V3.5.41 Upgrade Summary ---')
v40_h = OUT['v40_high'][1] / max(1, OUT['v40_high'][0]) * 100
v41_h = OUT['v41_high'][1] / max(1, OUT['v41_high'][0]) * 100
v40_l = OUT['v40_low'][1] / max(1, OUT['v40_low'][0]) * 100
v41_l = OUT['v41_low'][1] / max(1, OUT['v41_low'][0]) * 100
v40_sep = v40_h - v40_l
v41_sep = v41_h - v41_l
print('Separation: %.1fpp -> %.1fpp (%+.1fpp)' % (v40_sep, v41_sep, v41_sep - v40_sep))
print('High acc:   %.1f%% -> %.1f%% (%+.1fpp)' % (v40_h, v41_h, v41_h - v40_h))
print('Low acc:    %.1f%% -> %.1f%% (%+.1fpp)' % (v40_l, v41_l, v41_l - v40_l))
