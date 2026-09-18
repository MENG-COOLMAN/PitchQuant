import csv
from collections import defaultdict

T = defaultdict(lambda: defaultdict(int))

with open('data/Matches.csv', 'r', encoding='utf-8', errors='ignore') as f:
    for row in csv.DictReader(f):
        oh = row.get('OddHome', '')
        oa = row.get('OddAway', '')
        od = row.get('OddDraw', '')
        o25 = row.get('Over25', '')
        u25 = row.get('Under25', '')
        result = row.get('FTResult', '')
        try:
            h = float(oh)
            a = float(oa)
            d = float(od)
            o25f = float(o25)
            u25f = float(u25)
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
        tg = fhg + fag

        if h < a and h < d:
            pred = 'H'
        elif a < h and a < d:
            pred = 'A'
        else:
            pred = 'D'
        ou_pred = 'O' if o25f < u25f else 'U'
        dir_ok = (pred == result)
        ou_ok = ((ou_pred == 'O' and tg > 2.5) or (ou_pred == 'U' and tg < 2.5))

        m = min(h, a)
        if m <= 0:
            continue
        is_deep = (m < 1.30)
        skew = abs(h - a) / m
        v40_high = is_deep or skew > 2.0
        v40_low = skew <= 1.0
        tier = 'high' if v40_high else ('low' if v40_low else 'mid')

        score = '%d-%d' % (fhg, fag)

        # 全量: 方向×O/U
        key_all = pred + '+' + ou_pred
        T[key_all][score] += 1

        # Both OK
        if dir_ok and ou_ok:
            key_both = pred + '+' + ou_pred + '_OK'
            T[key_both][score] += 1

        # Tier × Both OK
        if dir_ok and ou_ok:
            key_tier = tier + '+' + pred + '+' + ou_pred
            T[key_tier][score] += 1


def show(key, topn=5):
    if key not in T:
        return
    total = sum(c for _, c in T[key].items())
    if total < 100:
        return
    scores = sorted(T[key].items(), key=lambda x: x[1], reverse=True)[:topn]
    top_cum = sum(c for _, c in scores)
    print('  %s (%d场): Top%d=%.0f%%' % (key, total, topn, top_cum / total * 100))
    for s, c in scores:
        print('    %6s %5d  %4.1f%%' % (s, c, c / total * 100))


print('=' * 55)
print('比分条件概率表 (方向×O/U 全量)')
print('=' * 55)
for combo in ['H+O', 'H+U', 'A+O', 'A+U', 'D+O', 'D+U']:
    show(combo)
    print()

print('=== Both OK: 方向×O/U ===')
for combo in ['H+O_OK', 'H+U_OK', 'A+O_OK', 'A+U_OK']:
    show(combo)
    print()

print('=== Tier × Both OK (HIGH only) ===')
for combo in ['high+H+O', 'high+H+U', 'high+A+O', 'high+A+U']:
    show(combo)
    print()

print('=== Tier × Both OK (LOW only) ===')
for combo in ['low+H+O', 'low+H+U', 'low+A+O', 'low+A+U']:
    show(combo)
    print()
