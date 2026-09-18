import csv
from collections import defaultdict

# 2. 方向+大小球正确时的比分差异分析
dir_ou = defaultdict(lambda: [0, 0, 0])  # [total, dir_ok, ou_ok]
dir_ou_both = []  # (pred, hg, ag, actual_score, pred_total_range)

total = 0
with open('data/Matches.csv', 'r', encoding='utf-8', errors='ignore') as f:
    for row in csv.DictReader(f):
        oh = row.get('OddHome', '')
        oa = row.get('OddAway', '')
        od = row.get('OddDraw', '')
        o25 = row.get('Over25', '')
        u25 = row.get('Under25', '')
        result = row.get('FTResult', '')
        if not oh or not oa or not od:
            continue
        try:
            h = float(oh)
            a = float(oa)
            d = float(od)
            fhg = int(float(row.get('FTHome', '0') or 0))
            fag = int(float(row.get('FTAway', '0') or 0))
            o25f = float(o25) if o25 else 0
            u25f = float(u25) if u25 else 0
        except:
            continue
        if result not in ('H', 'D', 'A'):
            continue

        total += 1

        # 方向预测
        if h < a and h < d:
            pred = 'H'
        elif a < h and a < d:
            pred = 'A'
        else:
            pred = 'D'

        dir_ok = (pred == result)

        # O/U预测
        tg = fhg + fag
        if o25f > 0 and u25f > 0:
            if o25f < u25f:
                ou_pred = 'O'
            else:
                ou_pred = 'U'
            ou_ok = ((ou_pred == 'O' and tg > 2.5) or (ou_pred == 'U' and tg < 2.5))
        else:
            ou_ok = False
            ou_pred = '?'

        # 比分差距分析
        if dir_ok and ou_ok:
            # 方向对了，大小球也对了
            actual = '%d-%d' % (fhg, fag)
            # 分类比分差异
            if fhg + fag <= 1:
                score_type = '0-0/1-0/0-1'
            elif fhg + fag == 2:
                score_type = '2-0/1-1/0-2'
            elif fhg + fag == 3:
                score_type = '2-1/1-2/3-0/0-3'
            elif fhg + fag == 4:
                score_type = '2-2/3-1/1-3/4-0/0-4'
            else:
                score_type = '5+ goals'
            print('%s %s %s O/U=%s actual=%s (%s)' % (pred, result, 'OK', ou_pred, actual, score_type))

        # 按联赛分组
        div = row.get('Division', '')
        key = div
        if key not in dir_ou:
            dir_ou[key] = [0, 0, 0, 0]
        dir_ou[key][0] += 1
        if dir_ok:
            dir_ou[key][1] += 1
        if ou_ok:
            dir_ou[key][2] += 1
        if dir_ok and ou_ok:
            dir_ou[key][3] += 1

        if total > 10000:
            break  # sample first 10K for analysis

print()
print('=' * 50)
print('2. 方向+O/U 同时正确率 (10K sample)')
print('=' * 50)

names = {'E0': 'PL', 'D1': 'BL', 'I1': 'SA', 'SP1': 'LL', 'F1': 'L1',
         'N1': 'ED', 'P1': 'PT'}

for div, (t, d_ok, o_ok, both) in sorted(dir_ou.items(), key=lambda x: x[1][0], reverse=True)[:15]:
    if t > 200:
        both_rate = both / t * 100 if t > 0 else 0
        dir_rate = d_ok / t * 100 if t > 0 else 0
        print('  %-6s %5d  dir:%.1f%% ou:%.1f%% both:%.1f%%' % (
            names.get(div, div), t, dir_rate,
            o_ok / t * 100 if t > 0 else 0, both_rate))
