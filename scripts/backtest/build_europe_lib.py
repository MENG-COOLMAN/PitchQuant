# -*- coding: utf-8 -*-
"""建欧战独立库：data/europe/（欧冠/欧联/欧协联拆分 + 全量 + 背景 + README）"""
import io, sys, csv, os, json, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SRC = 'data/zgzcw_eu_history.csv'
OUT = 'data/europe'
os.makedirs(OUT, exist_ok=True)

rows = list(csv.DictReader(open(SRC, encoding='utf-8-sig')))
print(f"源库: {len(rows)} 条")

FIELDS = list(rows[0].keys())

def save(name, recs):
    p = os.path.join(OUT, name)
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader(); w.writerows(recs)
    return p

# 按赛事拆分（欧战）
eu_types = {'欧冠': [], '欧联': [], '欧协联': []}
background = []
for r in rows:
    l = r['league']
    matched = False
    for t in eu_types:
        if t in l:
            eu_types[t].append(r); matched = True; break
    if not matched:
        background.append(r)

print(f"欧冠: {len(eu_types['欧冠'])} · 欧联: {len(eu_types['欧联'])} · 欧协联: {len(eu_types['欧协联'])} · 背景(国内/友谊): {len(background)}")

paths = {}
paths['欧冠_历史.csv'] = save('欧冠_历史.csv', eu_types['欧冠'])
paths['欧联_历史.csv'] = save('欧联_历史.csv', eu_types['欧联'])
paths['欧协联_历史.csv'] = save('欧协联_历史.csv', eu_types['欧协联'])
eu_all = eu_types['欧冠'] + eu_types['欧联'] + eu_types['欧协联']
paths['欧战全量.csv'] = save('欧战全量.csv', eu_all)
paths['背景_国内联赛.csv'] = save('背景_国内联赛.csv', background)

# README
readme = """# 欧战历史数据库（SL-europe-db 数据源）

> 2026-08-19 建立 · 来源 zgzcw（fenxi/{{matchId}}/bsls）· Playwright 批次采集（穿透WAF）· V3.5.54 接入

## 覆盖范围
- 欧冠 2026-27（资格赛1-3轮+附加赛·90场）· 欧联（80场）· 欧协联（258场）· 共428场欧战比赛
- 每场两队近10场历史（含交锋）→ 时间跨度 2024-05-14 ~ 2026-08-19

## 文件
| 文件 | 记录 | 内容 |
|:--|:--|:--|
| 欧冠_历史.csv | {cl} | 欧冠历史（含资格赛/正赛） |
| 欧联_历史.csv | {el} | 欧联历史 |
| 欧协联_历史.csv | {ecl} | 欧协联历史 |
| 欧战全量.csv | {ea} | 三大欧战合并 |
| 背景_国内联赛.csv | {bg} | 各队国内联赛近10场背景 |

## 字段（17列）
league | round | date | home | score | away | ht |
odd99_h | odd99_d | odd99_a（99家平均终赔·胜平负）|
handi_h | handi_hc | handi_a（亚盘主水/盘口/客水）| panlu（盘路）|
source_mid | source_time | source_match（来源欧战比赛）

## 触发调用（Step3 场景44）
检测到欧冠/欧联/欧协联赛事 → 调用 /SL-europe-db 技能：
1. 查两队历史交锋（date+home+away 匹配）
2. 查欧战赔率分层（对标修正46·欧战口径）
3. 修正44 场景验证（44A 比分追逐/44B 领先方·终盘赔率 vs 赛果）

## 限制
- 时间跨度约2.3年（每场近10场自然覆盖）·非全历史赛季
- 扩展完整历史（2020-2025）需 saishi 赛季切换（pw_cl46_batch.py 支持）
""".format(cl=len(eu_types['欧冠']), el=len(eu_types['欧联']), ecl=len(eu_types['欧协联']),
       ea=len(eu_all), bg=len(background))
open(os.path.join(OUT, 'README.md'), 'w', encoding='utf-8').write(readme)

# 汇总 JSON 索引
json.dump({k: len(v) for k, v in {
    '欧冠': eu_types['欧冠'], '欧联': eu_types['欧联'], '欧协联': eu_types['欧协联'],
    '欧战全量': eu_all, '背景': background}.items()},
    open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

print("\n✅ data/europe/ 独立库建成:")
for p in sorted(os.listdir(OUT)):
    sz = os.path.getsize(os.path.join(OUT, p))
    print(f"  {p} ({sz//1024}KB)")
