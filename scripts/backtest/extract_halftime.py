#!/usr/bin/env python
# 提取欧战比赛的半场比分(halftime_home/away)，用于验证"比分追逐"
import json, csv, io

SQL_PATH = r'football-api.sql (path via env SQL_PATH)'

with open('data/fixture_index.json', 'r', encoding='utf-8') as f:
    idx = json.load(f)

EURO = {'2': '欧冠', '3': '欧联杯', '848': '欧协联'}
euro = [r for r in idx if r.get('league_name') in EURO]
print(f'欧战比赛: {len(euro)}场')

# 字段索引: goals_home=26, goals_away=27, halftime_home=28, halftime_away=29
result = {}
count = 0
with open(SQL_PATH, 'rb') as f:
    for r in euro:
        bp = r.get('byte_pos')
        if bp is None:
            continue
        f.seek(bp)
        line = f.readline()  # 读取该 INSERT 行
        # 找到 VALUES ( 之后
        s = line.decode('utf-8', 'ignore')
        vi = s.find('VALUES')
        if vi < 0:
            continue
        # 提取括号内容
        start = s.find('(', vi)
        end = s.rfind(')')
        if start < 0 or end <= start:
            continue
        content = s[start+1:end]
        # 用 csv 解析
        try:
            fields = list(csv.reader([content]))[0]
        except:
            continue
        if len(fields) < 30:
            continue
        try:
            hth = int(fields[28]) if fields[28] not in ('NULL', '', None) else None
            hta = int(fields[29]) if fields[29] not in ('NULL', '', None) else None
            gh = int(fields[26]) if fields[26] not in ('NULL','',None) else None
            ga = int(fields[27]) if fields[27] not in ('NULL','',None) else None
        except:
            continue
        if hth is None or hta is None:
            continue
        result[r['id']] = {
            'date': r['date'], 'home': r['home_name'], 'away': r['away_name'],
            'gh': gh, 'ga': ga, 'hth': hth, 'hta': hta,
            'league': EURO.get(r.get('league_name'), '')
        }
        count += 1

print(f'成功提取半场比分: {count}场')

with open('data/euro_halftime.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False)
print('已保存 data/euro_halftime.json')
