---
name: SL-match-data-crawl
description: 批量爬取联赛历史对战、近期6场战绩、攻防均值、盘口水位，自动规整为规范CSV，首行强制写入主队、客队字段
---

# SL-match-data-crawl — 赛事数据自动化爬取

调用 API-Football (v3.football.api-sports.io) 批量拉取比赛数据，自动规整为规范 CSV。

**API Key**: `$API_FOOTBALL_KEY`（已内置，环境变量 x-apisports-key）

---

## 输入参数

Arguments 中需包含一个 JSON，格式如下：
```json
{
  "date": "2026-08-04",
  "fixture_id": null,
  "output": "data/match_data.csv"
}
```

- `date`: 比赛日期（YYYY-MM-DD），与 fixture_id 二选一
- `fixture_id`: 指定单场比赛 ID，与 date 二选一
- `output`: 输出 CSV 路径（默认 data/match_data.csv）

---

## 执行流程

### Step 1: 拉取 Fixtures

```bash
# 按日期拉取
curl -s "https://v3.football.api-sports.io/fixtures?date={date}" \
  -H "x-apisports-key: $API_FOOTBALL_KEY" > /tmp/fixtures.json

# 或按 fixture_id
curl -s "https://v3.football.api-sports.io/fixtures?id={fixture_id}" \
  -H "x-apisports-key: $API_FOOTBALL_KEY" > /tmp/fixtures.json
```

### Step 2: 拉取每个 Fixture 的赔率

对于每个 fixture，获取 odds：
```bash
curl -s "https://v3.football.api-sports.io/odds?fixture={id}" \
  -H "x-apisports-key: $API_FOOTBALL_KEY" > /tmp/odds_{id}.json
```

### Step 3: 拉取球队近况

对于每个 fixture 的 home/away team：
```bash
curl -s "https://v3.football.api-sports.io/fixtures?team={team_id}&last=6" \
  -H "x-apisports-key: $API_FOOTBALL_KEY" > /tmp/team_{id}_form.json
```

### Step 4: Python 解析 → CSV

写一个临时 Python 脚本处理 JSON → CSV，首行写入主队、客队名称：

```python
import json, csv, sys

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def extract_odds(odds_data, bookmaker_name="10Bet"):
    """从 odds JSON 提取指定 bookmaker 的关键赔率"""
    result = {}
    for r in odds_data.get('response', []):
        for bm in r.get('bookmakers', []):
            if bm['name'] == bookmaker_name:
                for bet in bm['bets']:
                    bid = bet['id']
                    if bid == 1:  # Match Winner
                        for v in bet['values']:
                            result[f'欧赔_{v["value"]}'] = v['odd']
                    elif bid == 4:  # Asian Handicap
                        vals = {v['value']: v['odd'] for v in bet['values']}
                        best = sorted(vals.items(), key=lambda x: len(x[0]))[0]
                        result[f'亚盘_{best[0]}'] = best[1]
                    elif bid == 5:  # Goals Over/Under
                        for v in bet['values']:
                            result[f'大小球_{v["value"]}'] = v['odd']
                    elif bid == 7:  # HT/FT Double
                        for v in bet['values']:
                            result[f'半全场_{v["value"]}'] = v['odd']
                    elif bid == 10:  # Exact Score
                        for v in bet['values'][:30]:
                            result[f'比分_{v["value"]}'] = v['odd']
                break
        break
    return result

def parse_fixtures(fixtures_path, odds_dir):
    fixtures = load_json(fixtures_path)
    rows = []
    for r in fixtures.get('response', []):
        fid = r['fixture']['id']
        row = {
            'fixture_id': fid,
            '日期': r['fixture']['date'][:10],
            '联赛': r['league']['name'],
            '主队': r['teams']['home']['name'],
            '客队': r['teams']['away']['name'],
            '主队ID': r['teams']['home']['id'],
            '客队ID': r['teams']['away']['id'],
        }
        # 加载该场的赔率
        odds_path = f"{odds_dir}/odds_{fid}.json"
        try:
            odds = load_json(odds_path)
            row.update(extract_odds(odds))
        except:
            pass
        rows.append(row)
    return rows

def write_csv(rows, output_path):
    if not rows:
        return
    keys = rows[0].keys()
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)

if __name__ == '__main__':
    rows = parse_fixtures('/tmp/fixtures.json', '/tmp')
    write_csv(rows, sys.argv[1] if len(sys.argv) > 1 else 'data/match_data.csv')
    print(f"✅ 已导出 {len(rows)} 场比赛到 CSV")
```

### Step 5: 输出结构

CSV 列：fixture_id、日期、联赛、主队、客队、主队ID、客队ID、欧赔_Home、欧赔_Draw、欧赔_Away、亚盘_*、大小球_Over 2.5、大小球_Under 2.5、半全场_Home/Home、半全场_Draw/Draw、半全场_Away/Away、比分_1:0、比分_2:0、比分_2:1、比分_0:0、比分_1:1、比分_0:1、...（全部比分）

---

## 约束

- 每日 API 额度 100 次，每场比赛消耗约 2-3 次（fixtures + odds + team form）
- Bookmaker 优先 10Bet，备用 Bet365
- 输出 CSV 使用 UTF-8 BOM 编码（Excel 兼容）
- 必须在脚本执行完成后输出确认信息
