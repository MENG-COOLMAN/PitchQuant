# -*- coding: utf-8 -*-
"""欧战数据回测1：基础统计（主客胜率/平局率/大球率·确认观察项+44C基准）"""
import io, sys, csv, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

rows = list(csv.DictReader(open('data/europe/欧战全量.csv', encoding='utf-8-sig')))
print(f"欧战记录: {len(rows)} 条")

def parse_score(s):
    try:
        h, a = s.split(':')
        return int(h), int(a)
    except Exception:
        return None

valid = [(r, parse_score(r['score'])) for r in rows]
valid = [(r, sc) for r, sc in valid if sc]
print(f"有效比分: {len(valid)}")

# 1. 总体主客胜率/平局率/大球率
home = sum(1 for _, (h, a) in valid if h > a)
draw = sum(1 for _, (h, a) in valid if h == a)
away = sum(1 for _, (h, a) in valid if h < a)
over = sum(1 for _, (h, a) in valid if h + a >= 3)
avg = sum(h + a for _, (h, a) in valid) / len(valid)
print(f"\n=== 欧战总体 (n={len(valid)}) ===")
print(f"主胜 {100*home/len(valid):.1f}% · 平局 {100*draw/len(valid):.1f}% · 客胜 {100*away/len(valid):.1f}%")
print(f"大球(≥3) {100*over/len(valid):.1f}% · 场均 {avg:.2f}球")

# 2. 按赛事
print("\n=== 按赛事 ===")
for league in ['欧冠', '欧联', '欧协联']:
    sub = [(r, sc) for r, sc in valid if league in r['league']]
    if not sub: continue
    h = sum(1 for _, (x, y) in sub if x > y); d = sum(1 for _, (x, y) in sub if x == y)
    o = sum(1 for _, (x, y) in sub if x + y >= 3)
    av = sum(x + y for _, (x, y) in sub) / len(sub)
    print(f"{league} (n={len(sub)}): 主{100*h/len(sub):.1f}% 平{100*d/len(sub):.1f}% 客{100*(len(sub)-h-d)/len(sub):.1f}% · 大球{100*o/len(sub):.1f}% · 场均{av:.2f}球")

# 3. 平局赔率分层（修正46 欧战口径）
print("\n=== 欧战平局赔率分层（对标修正46） ===")
buckets = [('<3.0', lambda o: o < 3.0), ('3.0-3.5', lambda o: 3.0 <= o < 3.5),
           ('3.5-4.0', lambda o: 3.5 <= o < 4.0), ('>4.0', lambda o: o >= 4.0)]
for name, fn in buckets:
    sub = [(r, sc) for r, sc in valid if r['odd99_d'] and fn(float(r['odd99_d']))]
    if not sub: continue
    d = sum(1 for _, (x, y) in sub if x == y)
    print(f"平赔 {name}: 平局率 {100*d/len(sub):.1f}% (n={len(sub)})")

# 4. 大球方向 2球/3球/4球 分布
print("\n=== 总进球分布 ===")
tg = collections.Counter(h + a for _, (h, a) in valid)
for k in sorted(tg):
    print(f"  {k}球: {tg[k]} ({100*tg[k]/len(valid):.1f}%)")

# 5. 观察项确认：欧战低比分倾向（0:0/1:1/1:0/0:1 占比）
low = sum(1 for _, (h, a) in valid if h + a <= 2)
print(f"\n≤2球(低比分): {100*low/len(valid):.1f}%")
