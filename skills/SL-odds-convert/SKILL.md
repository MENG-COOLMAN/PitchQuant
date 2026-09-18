---
name: SL-odds-convert
description: 多家机构赔率剔除抽水、计算隐含胜平负概率、凯利指数、盘口偏离度，量化机构倾向
---

# SL-odds-convert — 赔率去抽水 & 凯利计算

多家机构赔率剔除抽水、计算隐含胜平负概率、凯利指数、盘口偏离度，量化机构倾向。

---

## 数据源2：Odds-API（欧战赔率 + 变动线）🔴欧战分析必用

> 触发条件：分析欧战（欧冠/欧联/欧协联）时启用。Matches.csv 无欧战、SQL 无赔率字段，
> Odds-API（mcp__odds-api__*，免费 tier）补这个缺口——当前赔率 + 机构变动线。

### 能力边界（免费 tier·已实测 2026-08-15）

| 能力 | 状态 |
|:--|:--|
| 欧战当前赔率（1X2/让球/大小球/半全场/比分/BTTS） | ✅ |
| 赔率变动线（opening→latest 带时间戳） | ⚠️ 免费tier 404不可用（2026-08-20实测）·改用 get_odds 自带 updatedAt 时间戳 + zgzcw 初即盘口对比 |
| 历史赔率（/historical/*） | ❌ 需付费 |
| 博彩公司 | 仅 2 家（1xbet 全市场 + Bet365 仅ML），无 Pinnacle/Betfair |
| 限流 | 100 请求/小时 |

### 调用流程（MCP 工具 mcp__odds-api__*）

🔴平台澄清（2026-08-23实测）: 本 MCP = **odds-api.io**（基址 `https://api2.odds-api.io/v3`·认证 query param `apiKey`）·**不是 the-odds-api.com**（勿用旧平台测 key·会 401 INVALID_KEY）·必须走代理 127.0.0.1:7897（无代理 HTTP:000 被墙）。

🔴REST 直连降级方案（MCP 不可用时·防跳过·2026-08-23实测可用）:
```bash
# 事件列表（RFC3339 时间·非 epoch）
curl --proxy http://127.0.0.1:7897 "https://api2.odds-api.io/v3/events?apiKey=$ODDS_API_KEY&sport=football&league=italy-serie-a&from=2026-08-23T14:00:00Z&to=2026-08-23T22:00:00Z&status=pending"
# 单场赔率（bookmakers=1xbet·全市场 ML/Spread/Totals/Double Chance）
curl --proxy http://127.0.0.1:7897 "https://api2.odds-api.io/v3/odds?apiKey=$ODDS_API_KEY&eventId=<id>&bookmakers=1xbet"
# 联赛列表
curl --proxy http://127.0.0.1:7897 "https://api2.odds-api.io/v3/leagues?apiKey=$ODDS_API_KEY&sport=football"
```

1. **选博彩公司**（首次会话）：`mcp__odds-api__select_bookmakers` 选 `1xbet,Bet365`
2. **拿欧战比赛**：`mcp__odds-api__get_events`（sport=football, league=欧战 slug）
   - 欧冠：`international-clubs-uefa-champions-league-playoff-round`
   - 欧联：`international-clubs-uefa-europa-league-playoff-round`
   - 欧协联：`international-clubs-uefa-conference-league-playoff-round`
   - 联赛全量：`mcp__odds-api__get_leagues`（sport=football，共857个）
3. **拿赔率**：`mcp__odds-api__get_odds`（eventId）→ 1X2(ML)/让球(Spread)/大小球(Totals)/半全场(HT/FT)/比分(Correct Score)/BTTS
4. **拿变动线**（🔴变动层V1核心）：`mcp__odds-api__get_odds_movements`（eventId, bookmaker=Bet365, market=ML）→ 开盘→最新完整序列带时间戳

### 融入流水线

- 「欧盘赔率(Odds-API)」作为 Step0 数据源之一，与竞彩/API-Football 并列

---

## 数据源2b：zgzcw 三页面（🔴数据补充·2026-08-20主从升级·Odds-API不可用时替代源B）

> 触发：Odds-API 网络不可达（VPN未开）或需要多机构交叉验证时。
> 脚本：`data/tmp/pw_odds_v2.py <mid>` → 输出 `data/tmp/zgzcw_{mid}_pw.json`

| 页面 | 内容 | 结构 |
|:--|:--|:--|
| bjop（欧赔） | 44行机构 | [序号,机构,初胜,初平,初负,即胜↑↓,即平,即负,主%,平%,客%,凯利x3] |
| ypdb（亚盘） | 17行机构 | [序号,机构,初主水,初盘口,初客水,即主水↑↓,即盘口,即客水,主%,客%,凯利x3] |
| dxdb（大小球） | 18行机构 | [序号,机构,初大水,初盘口(2/2.5球等),初小水,即大水↑↓,即盘口,即小水,大%,小%,凯利x3] |

- 数据带初/即双时点+升降箭头（V6 修正54-58 联动数据完备）
- 冲突处理：Odds-API vs zgzcw 冲突 → 以 zgzcw 多机构均值(42家>2家)定方向基准·Odds-API 变动线作动态信号
- WAF 限流：连续请求会触发人机验证·批次间间隔 8s+·失败冷却 300s 重试
- 变动线序列 → 直接喂变动层 V1（逐T列出变动%，替代手工竞彩粘贴）
- 跨机构分歧（1xbet vs Bet365）→ 修正35/37 Max分歧（⚠️仅2家，样本窄需标注）

---

## 输入

Arguments 中指定输入 CSV 路径（由 SL-match-data-crawl 产出），例如：
```
data/match_data.csv
```

---

## 执行流程

### Step 1: 读取 CSV，写入 Python 脚本

```python
import csv, json, math, sys

def read_csv(path):
    with open(path, 'r', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def decimal_odds(frac_str):
    """处理分数赔率如 '9/4' → 3.25 或直接返回小数"""
    try:
        if '/' in str(frac_str):
            num, den = str(frac_str).split('/')
            return float(num) / float(den) + 1
        return float(frac_str)
    except:
        return None

# ============ 1. 去抽水公平概率 ============
def fair_probability(odds_list):
    """
    odds_list: [home_odds, draw_odds, away_odds]
    返回去抽水后的公平概率 [P_home, P_draw, P_away]
    """
    valid = [o for o in odds_list if o is not None]
    if len(valid) < 3:
        return [None, None, None]
    
    inv_sum = sum(1/o for o in odds_list)
    overround = inv_sum - 1  # 抽水率
    
    fair = [(1/o) / inv_sum for o in odds_list]
    return fair, overround

# ============ 2. 凯利指数 ============
def kelly_index(odds, fair_prob, bankroll_pct=1.0):
    """
    凯利公式: f* = (b*p - q) / b
    b = 赔率 - 1 (净赔率), p = 公平概率, q = 1-p
    返回凯利比例，负值代表不投注
    """
    b = odds - 1
    p = fair_prob
    q = 1 - p
    kelly = (b * p - q) / b if b > 0 else -1
    return round(kelly * bankroll_pct, 4)

# ============ 3. 盘口偏离度 ============
def odds_deviation(market_odds, fair_prob):
    """
    盘口偏离度 = (隐含概率 - 公平概率) / 公平概率 × 100%
    正值代表机构高估该方向，负值代表低估
    """
    implied = 1 / market_odds
    return round((implied - fair_prob) / fair_prob * 100, 2)

# ============ 4. 主处理 ============
def process_match(row):
    """处理单场比赛数据，计算全部指标"""
    result = {
        'fixture_id': row.get('fixture_id', ''),
        '日期': row.get('日期', ''),
        '联赛': row.get('联赛', ''),
        '主队': row.get('主队', ''),
        '客队': row.get('客队', ''),
    }
    
    # 欧赔
    home_odds = decimal_odds(row.get('欧赔_Home'))
    draw_odds = decimal_odds(row.get('欧赔_Draw'))
    away_odds = decimal_odds(row.get('欧赔_Away'))
    
    if home_odds and draw_odds and away_odds:
        fair, overround = fair_probability([home_odds, draw_odds, away_odds])
        result.update({
            '欧赔_主胜': home_odds,
            '欧赔_平局': draw_odds,
            '欧赔_客胜': away_odds,
            '抽水率': round(overround * 100, 2),
            '公平概率_主胜': round(fair[0] * 100, 2) if fair[0] else '',
            '公平概率_平局': round(fair[1] * 100, 2) if fair[1] else '',
            '公平概率_客胜': round(fair[2] * 100, 2) if fair[2] else '',
            '凯利_主胜': kelly_index(home_odds, fair[0]) if fair[0] else '',
            '凯利_平局': kelly_index(draw_odds, fair[1]) if fair[1] else '',
            '凯利_客胜': kelly_index(away_odds, fair[2]) if fair[2] else '',
            '偏离度_主胜': odds_deviation(home_odds, fair[0]) if fair[0] else '',
            '偏离度_平局': odds_deviation(draw_odds, fair[1]) if fair[1] else '',
            '偏离度_客胜': odds_deviation(away_odds, fair[2]) if fair[2] else '',
        })
    
    # 半全场分析
    hh_odds = decimal_odds(row.get('半全场_Home/Home'))
    dd_odds = decimal_odds(row.get('半全场_Draw/Draw'))
    aa_odds = decimal_odds(row.get('半全场_Away/Away'))
    
    if hh_odds:
        result['半全场_胜胜'] = hh_odds
        result['半全场_胜胜_信号'] = '⚠️极端' if hh_odds < 2.00 else ('普通' if hh_odds < 3.00 else '无')
    if aa_odds:
        result['半全场_负负'] = aa_odds
        result['半全场_负负_信号'] = '⚠️极端' if aa_odds < 2.00 else ('普通' if aa_odds < 3.00 else '无')
    
    # 大小球
    over25 = decimal_odds(row.get('大小球_Over 2.5'))
    under25 = decimal_odds(row.get('大小球_Under 2.5'))
    if over25 and under25:
        result['大小球_大2.5赔率'] = over25
        result['大小球_小2.5赔率'] = under25
        big_fair, _ = fair_probability([over25, under25, over25])  # 用两个选项近似
        big_prob = 1/(1+over25/under25)  # 简化去抽水
        result['大球概率'] = round(big_prob * 100, 2)
    
    return result

def main(input_path, output_path=None):
    rows = read_csv(input_path)
    results = [process_match(r) for r in rows]
    
    if not output_path:
        output_path = input_path.replace('.csv', '_odds_analysis.csv')
    
    if results:
        keys = results[0].keys()
        with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(results)
    
    print(f"✅ 赔率分析完成！处理 {len(results)} 场比赛")
    print(f"   抽水率范围: {min(r['抽水率'] for r in results if r.get('抽水率') is not None)}% - {max(r['抽水率'] for r in results if r.get('抽水率') is not None)}%")
    
    # 凯利正值统计
    pos_kelly_home = sum(1 for r in results if isinstance(r.get('凯利_主胜'), (int,float)) and r['凯利_主胜'] > 0)
    pos_kelly_away = sum(1 for r in results if isinstance(r.get('凯利_客胜'), (int,float)) and r['凯利_客胜'] > 0)
    print(f"   凯利正值: 主胜{pos_kelly_home}场 / 客胜{pos_kelly_away}场")
    
    return output_path

if __name__ == '__main__':
    input_file = sys.argv[1] if len(sys.argv) > 1 else 'data/match_data.csv'
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    main(input_file, output_file)
```

### Step 2: 输出 CSV 结构

| 字段 | 含义 |
|:---|:---|
| 抽水率 | 机构利润率（越低越公平） |
| 公平概率_主胜/平局/客胜 | 去抽水后真实概率 |
| 凯利_主胜/平局/客胜 | 正值=有投注价值，负值=无价值 |
| 偏离度_主胜/平局/客胜 | 正值=机构高估，负值=机构低估 |
| 半全场_胜胜/负负_信号 | ⚠️极端(<2.00) / 普通(<3.00) / 无 |
| 大球概率 | 大2.5球的去抽水概率 |

---

## 关键指标解读

| 指标 | 强信号 | 弱信号 |
|:---|:---|:---|
| **凯利 > 0.05** | 高投注价值，机构可能低估 | — |
| **凯利 < -0.05** | 负期望值，坚决避开 | — |
| **偏离度 < -10%** | 机构低估该方向 | — |
| **抽水率 > 8%** | 机构利润高，赔率可能失真 | 抽水率 < 5% 较可靠 |
| **半全场 < 2.00** | V3.5.24 ⚠️极端信号 | 触发修正7+修正15 |
