# -*- coding: utf-8 -*-
"""建欧战历史数据库：解析3场欧冠 bsls → data/zgzcw_eu_history.csv"""
import io, sys, re, csv, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

files = {
    '4608831': 'data/tmp/eu_bsls_4608831.html',
    '4608845': 'data/tmp/fx_bsls.html',
    '4608838': 'data/tmp/eu_bsls_4608838.html',
}
records = []
for mid, f in files.items():
    if not os.path.exists(f):
        print(f"{mid}: 文件缺失·跳过")
        continue
    t = open(f, encoding='utf-8', errors='replace').read()
    tables = re.findall(r'<table[^>]*>(.*?)</table>', t, re.S)
    n = 0
    for tb in tables:
        trs = re.findall(r'<tr[^>]*>(.*?)</tr>', tb, re.S)
        if len(trs) < 10: continue
        # 表头行=本场信息
        hdr = [c.strip() for c in re.sub(r'<[^>]+>', '|', trs[0]).split('|') if c.strip()]
        cur_match = ' '.join(hdr[:5]) if len(hdr) >= 5 else mid
        for r in trs[1:]:
            cells = [c.strip() for c in re.sub(r'<[^>]+>', '|', r).split('|') if c.strip()]
            if len(cells) >= 14:
                records.append({
                    'source_match': cur_match, 'source_id': mid,
                    'league': cells[0], 'round': cells[1], 'date': cells[2],
                    'home': cells[3], 'score': cells[4], 'away': cells[5], 'ht': cells[6],
                    'odd_h': cells[7], 'odd_d': cells[8], 'odd_a': cells[9],
                    'water_h': cells[10], 'handicap': cells[11], 'water_a': cells[12],
                    'result': cells[13] if len(cells) > 13 else '',
                })
                n += 1
    print(f"{mid}: {n} 条历史记录")

# 去重（同一历史比赛可能多场引用）
seen = set()
uniq = []
for r in records:
    k = (r['date'], r['home'], r['away'])
    if k not in seen:
        seen.add(k)
        uniq.append(r)
print(f"\n总记录: {len(records)} · 去重后: {len(uniq)}")

# 保存 CSV
out = 'data/zgzcw_eu_history.csv'
with open(out, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(uniq[0].keys()))
    w.writeheader()
    w.writerows(uniq)
print(f"✅ 已保存 {out} ({len(uniq)} 行)")

# 统计
import collections
leagues = collections.Counter(r['league'] for r in uniq)
print("\n联赛分布:", dict(leagues.most_common(10)))
# 欧冠记录
cl = [r for r in uniq if '欧冠' in r['league'] or '冠军' in r['league']]
print(f"欧冠记录: {len(cl)} 条")
for r in cl[:5]:
    print(f"  {r['date']} {r['home']} {r['score']} {r['away']} · 欧赔{r['odd_h']}/{r['odd_d']}/{r['odd_a']} · 亚盘{r['water_h']}/{r['handicap']}/{r['water_a']}")
