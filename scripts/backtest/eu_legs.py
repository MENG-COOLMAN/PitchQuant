# -*- coding: utf-8 -*-
"""欧战回测2：首回合-次回合配对 + 44A/44B 规律验证"""
import io, sys, csv, collections, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

rows = list(csv.DictReader(open('data/europe/欧战全量.csv', encoding='utf-8-sig')))

def parse_score(s):
    try:
        h, a = s.split(':')
        return int(h), int(a)
    except Exception:
        return None

def parse_date(d):
    try:
        p = d.split('-')
        y = int(p[0]) + 2000 if int(p[0]) < 100 else int(p[0])
        return datetime.date(y, int(p[1]), int(p[2]))
    except Exception:
        return None

valid = [(r, parse_score(r['score']), parse_date(r['date'])) for r in rows]
valid = [(r, sc, dt) for r, sc, dt in valid if sc and dt]
print(f"有效: {len(valid)}")

# 配对：同一对阵两回合（主客互换·间隔3-14天）
pairs = []
used = set()
for i, (r1, sc1, dt1) in enumerate(valid):
    for j in range(i+1, len(valid)):
        r2, sc2, dt2 = valid[j]
        # 主客互换
        if r1['home'] == r2['away'] and r1['away'] == r2['home']:
            gap = abs((dt2 - dt1).days)
            if 3 <= gap <= 14 and (i, j) not in used:
                used.add((i, j))
                first, second = (r1, sc1, dt1), (r2, sc2, dt2)
                if dt1 > dt2:
                    first, second = (r2, sc2, dt2), (r1, sc1, dt1)
                pairs.append((first, second))

print(f"两回合配对: {len(pairs)} 组")

# 1. 首回合结果 → 次回合总进球（44A 比分追逐）
print("\n=== 44A: 首回合差距 → 次回合大球率 ===")
for label, fn in [('首回合平局', lambda s: s[0] == s[1]),
                   ('首回合差距1球', lambda s: abs(s[0]-s[1]) == 1),
                   ('首回合差距2球', lambda s: abs(s[0]-s[1]) == 2),
                   ('首回合差距≥3', lambda s: abs(s[0]-s[1]) >= 3)]:
    sub = [(f, s) for f, s in pairs if fn(f[1])]
    if not sub: continue
    o3 = sum(1 for _, s in sub if s[1][0] + s[1][1] >= 3)
    avg = sum(s[1][0] + s[1][1] for _, s in sub) / len(sub)
    print(f"  {label} (n={len(sub)}): 次回合大球(≥3) {100*o3/len(sub):.0f}% · 场均{avg:.2f}球")

# 2. 44B: 首回合领先方 → 次回合表现
print("\n=== 44B: 首回合领先方 → 次回合 ===")
for label, fn in [('首回合主胜', lambda s: s[0] > s[1]),
                   ('首回合客胜', lambda s: s[0] < s[1]),
                   ('首回合平局', lambda s: s[0] == s[1])]:
    sub = [(f, s) for f, s in pairs if fn(f[1])]
    if not sub: continue
    # 次回合：同队再赢/平/输
    same = 0; draw = 0; lose = 0
    for f, s in sub:
        # f 首回合主队（若首回合主胜·主队领先）
        leader_is_home = f[1][0] > f[1][1]
        if leader_is_home:
            if s[1][0] > s[1][1]: same += 1
            elif s[1][0] == s[1][1]: draw += 1
            else: lose += 1
        else:
            if s[1][0] < s[1][1]: same += 1
            elif s[1][0] == s[1][1]: draw += 1
            else: lose += 1
    n = len(sub)
    print(f"  {label} (n={n}): 领先方次回合 再赢{100*same/n:.0f}% 平{100*draw/n:.0f}% 输{100*lose/n:.0f}%")

# 3. 首回合结果 → 次回合结果
print("\n=== 首回合 → 次回合 分布 ===")
ft = collections.Counter()
for f, s in pairs:
    fs = '主胜' if f[1][0] > f[1][1] else ('平' if f[1][0] == f[1][1] else '客胜')
    ss = '主胜' if s[1][0] > s[1][1] else ('平' if s[1][0] == s[1][1] else '客胜')
    ft[(fs, ss)] += 1
for k in sorted(ft):
    print(f"  首回合{k[0]} → 次回合{k[1]}: {ft[k]}")

# 4. 首回合平局（0:0/1:1/2:2）→ 次回合
print("\n=== 首回合平局细分 → 次回合 ===")
for label, fn in [('0:0', lambda s: s == (0, 0)), ('1:1', lambda s: s == (1, 1)),
                  ('2:2+', lambda s: s[0] == s[1] and s[0] >= 2)]:
    sub = [(f, s) for f, s in pairs if fn(f[1])]
    if not sub: continue
    o3 = sum(1 for _, s in sub if s[1][0] + s[1][1] >= 3)
    avg = sum(s[1][0] + s[1][1] for _, s in sub) / len(sub)
    print(f"  首回合{label} (n={len(sub)}): 次回合大球{100*o3/len(sub):.0f}% · 场均{avg:.2f}球")

# 5. 首回合 vs 次回合 主胜率/平局率（主场优势变化）
print("\n=== 首回合 vs 次回合 主胜率/平局率 ===")
for label, idx in [('首回合', 0), ('次回合', 1)]:
    sub = [s[idx] for s in pairs]
    h = sum(1 for sc in sub if sc[0] > sc[1]); d = sum(1 for sc in sub if sc[0] == sc[1])
    n = len(sub)
    print(f"  {label} (n={n}): 主胜{100*h/n:.1f}% 平{100*d/n:.1f}% 客{100*(n-h-d)/n:.1f}%")
