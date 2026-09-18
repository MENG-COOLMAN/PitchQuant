# -*- coding: utf-8 -*-
"""最终建库：欧战历史数据库（字段修正+去重+统计+JSON）"""
import io, sys, csv, os, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SRC = 'data/zgzcw_eu_history_full.csv'
OUT_CSV = 'data/zgzcw_eu_history.csv'
OUT_JSON = 'data/zgzcw_eu_history.json'

rows = list(csv.DictReader(open(SRC, encoding='utf-8-sig')))
print(f"原始: {len(rows)} 条")

# 字段修正：odd_ao_* → 亚盘 handi_*
FIELDS = ['source_mid','source_time','source_match','league','round','date','home','score','away','ht',
          'odd99_h','odd99_d','odd99_a','handi_h','handi_hc','handi_a','panlu']
clean = []
for r in rows:
    nr = {
        'source_mid': r['source_mid'], 'source_time': r['source_time'], 'source_match': r['source_match'],
        'league': r['league'], 'round': r['round'], 'date': r['date'],
        'home': r['home'], 'score': r['score'], 'away': r['away'], 'ht': r['ht'],
        'odd99_h': r['odd99_h'], 'odd99_d': r['odd99_d'], 'odd99_a': r['odd99_a'],
        'handi_h': r['odd_ao_h'], 'handi_hc': r['odd_ao_d'], 'handi_a': r['odd_ao_a'],
        'panlu': r['panlu'],
    }
    clean.append(nr)

# 去重
seen = set(); uniq = []
for r in clean:
    k = (r['date'], r['home'], r['away'])
    if k not in seen:
        seen.add(k); uniq.append(r)
print(f"去重后: {len(uniq)} 条")

# 亚盘完整率
with_asia = [r for r in uniq if r['handi_hc']]
print(f"含亚盘盘口: {len(with_asia)} 条 ({100*len(with_asia)/len(uniq):.0f}%)")

# 欧战统计
eu = [r for r in uniq if any(k in r['league'] for k in ['欧冠','欧联','欧协'])]
print(f"欧战记录: {len(eu)} 条")
for l, n in collections.Counter(r['league'] for r in eu).most_common(5):
    print(f"  {l}: {n}")

# 保存
with open(OUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader(); w.writerows(uniq)
json.dump(uniq, open(OUT_JSON, 'w', encoding='utf-8'), ensure_ascii=False)
print(f"\n✅ 最终库: {OUT_CSV} ({len(uniq)} 条) + {OUT_JSON}")

# 时间跨度
dates = []
for r in uniq:
    p = r['date'].split('-')
    if len(p) == 3:
        dates.append((int(p[0])+2000 if int(p[0])<100 else int(p[0]), int(p[1]), int(p[2])))
dates.sort()
print(f"时间跨度: {dates[0]} ~ {dates[-1]}")
