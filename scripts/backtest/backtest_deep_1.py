import csv
from collections import defaultdict

# 1. 穿盘深度分层分析
asian = defaultdict(lambda: [0, 0])  # [total, cover]
asian_league = defaultdict(lambda: defaultdict(lambda: [0, 0]))
asian_skew = defaultdict(lambda: [0, 0])

total_asian = 0
with open('data/Matches.csv', 'r', encoding='utf-8', errors='ignore') as f:
    for row in csv.DictReader(f):
        hsz = row.get('HandiSize', '')
        hho = row.get('HandiHome', '')
        hao = row.get('HandiAway', '')
        if not hsz or not hho or not hao:
            continue
        try:
            sz = float(hsz)
            hh = float(hho)
            ha = float(hao)
        except:
            continue
        if sz == 0:
            continue
        fhg_s = row.get('FTHome', '0')
        fag_s = row.get('FTAway', '0')
        if not fhg_s or not fag_s:
            continue
        try:
            fhg = int(float(fhg_s))
            fag = int(float(fag_s))
        except:
            continue
        diff = fhg - fag

        # 方向判定
        if hh < ha:
            fav_dir = 'H'
            cov_margin = sz
        else:
            fav_dir = 'A'
            cov_margin = -sz

        if fav_dir == 'H':
            if diff > sz:
                cover = 1
            elif diff == sz:
                cover = -1  # push
            else:
                cover = 0
        else:
            if -diff > abs(sz):
                cover = 1
            elif -diff == abs(sz):
                cover = -1
            else:
                cover = 0

        total_asian += 1
        a_sz = abs(sz)
        if a_sz <= 0.25:
            k = '0.25'
        elif a_sz <= 0.5:
            k = '0.5'
        elif a_sz <= 0.75:
            k = '0.75'
        elif a_sz <= 1.0:
            k = '1.0'
        elif a_sz <= 1.5:
            k = '1.5'
        else:
            k = '1.75+'

        asian[k][0] += 1
        if cover == 1:
            asian[k][1] += 1

        # 按联赛
        div = row.get('Division', '')
        if div:
            asian_league[div][k][0] += 1
            if cover == 1:
                asian_league[div][k][1] += 1

        # 按共识
        oh = row.get('OddHome', '')
        oa = row.get('OddAway', '')
        if oh and oa:
            try:
                h = float(oh)
                a = float(oa)
                skew = abs(h - a) / min(h, a)
                if skew <= 1.0:
                    sk = 'no_cons'
                elif skew <= 2.0:
                    sk = 'mild'
                else:
                    sk = 'extreme'
                asian_skew[sk][0] += 1
                if cover == 1:
                    asian_skew[sk][1] += 1
            except:
                pass

print('=' * 50)
print('1. 穿盘深度分析')
print('总场次: %d' % total_asian)
print()

# 让球深度
print('--- 让球深度穿盘率 ---')
for k in ['0.25', '0.5', '0.75', '1.0', '1.5', '1.75+']:
    t, c = asian[k]
    if t > 0:
        print('  %-6s %8d  %.1f%%' % (k, t, c / t * 100))

# 联赛Top5
print()
print('--- 联赛穿盘率(1.0球) ---')
league_stats = []
for div, depths in asian_league.items():
    if '1.0' in depths and depths['1.0'][0] > 100:
        t, c = depths['1.0']
        league_stats.append((div, t, c / t * 100))
league_stats.sort(key=lambda x: x[2], reverse=True)
names = {'E0': 'PL', 'D1': 'BL', 'I1': 'SA', 'SP1': 'LL', 'F1': 'L1',
         'N1': 'ED', 'P1': 'PT', 'SP2': 'LL2', 'E1': 'CH', 'E2': 'CH2',
         'E3': 'L1_2', 'SC0': 'SC0', 'SC1': 'SC1'}
for div, t, acc in league_stats[:15]:
    if t > 300:
        print('  %-8s %6d  %.1f%%' % (names.get(div, div), t, acc))

# 共识分层
print()
print('--- 共识分层穿盘率(全部深度) ---')
for k, lab in [('extreme', '极端共识'), ('mild', '温和共识'), ('no_cons', '无共识')]:
    t, c = asian_skew[k]
    if t > 0:
        print('  %s: %8d  %.1f%%' % (lab, t, c / t * 100))
