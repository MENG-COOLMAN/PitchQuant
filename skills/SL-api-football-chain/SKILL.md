---
name: SL-api-football-chain
description: api-football 三端点链（源B3·Step0⑨）——fixtures?date 定位当前赛季 fixture id → predictions(官方模型概率)/odds(13家博彩赔率)/injuries(本场伤停) 按 fixture 查·补 Odds-API 未覆盖赔率+伤停交叉验证·仅五大联赛+欧战·免费 key 限制处理
---

# SL-api-football-chain — api-football 三端点链（V3.5.71接入）

> 🔴触发条件: **Step0 第⑨步**，所有分析场次（仅五大联赛+欧战·其他联赛不查）
> 数据源: 自建轻量 MCP server `data/tmp/api_football_mcp.py`（零依赖 Python stdio·9工具·key 已配 reasonix.toml `API_FOOTBALL_KEY`·直连不走代理）
> 也可直连 REST: `https://v3.football.api-sports.io` + header `x-apisports-key`

## 🔴使用链（必须按此顺序·免费 key 限制决定）

```
① fixtures?date=YYYY-MM-DD（当日·不带 league）
   → 定位本场 fixture id（返回含五大联赛全量·实测753场含英超28场·欧战比赛日周二/四含欧冠/欧联/欧协联）
   🔴调用规范(2026-08-26用户实证修正): fixtures 只用 date(YYYY-MM-DD)定位当日(带league/team触发Season要求报错)·按 fixture id 查 predictions/odds/injuries 全可用·2026赛季可查(实证: La Liga fixture 1570340)·禁止 league+season 组合或 team 单独查 fixtures(Season required)
   🔴date 时区(2026-09-03实证): api-football date=UTC 日·北京 09-04 02:45/03:00 开球场次(UTC 09-03 18:45/19:00)属 date=2026-09-03·非北京日·误用北京日会 count=0/漏场
   🔴MCP 截断降级(2026-09-03实证·大日必用): fixtures?date 大日(单日>100场·如162/464场)MCP 返回仅显示前~50条截断→无法翻页定位晚场→降级直连 REST:
     python -c "urllib.request GET https://v3.football.api-sports.io/fixtures?date=YYYY-MM-DD header x-apisports-key=<KEY> → 全量JSON本地过滤两队→fixture id"
     🔴key 获取: reasonix.toml [[server]] api-football env.API_FOOTBALL_KEY(实测 $API_FOOTBALL_KEY)·直连不走代理·免费 100次/天 够用
     实证: 2026-09-03 图卢兹vs里尔 fixture 1552754·皇家社会vs塞尔塔 fixture 1570392(MCP截断·直连过滤秒得)
② predictions?fixture=<id> → 官方模型概率（winner/win_or_draw/percent home-draw-away/advice）
③ odds?fixture=<id> → 🔴13家博彩赔率（Match Winner/Home-Away/Asian Handicap/Goals Over-Under/BTTS/半场市场·update 实时）
④ injuries?fixture=<id> → 本场伤停（player/team/type: Injury|Suspended/reason/date）
```

## 输入参数

| 参数 | 必填 | 说明 |
|:--|:--|:--|
| date | ✅ | 比赛日期 YYYY-MM-DD（fixtures 定位用） |
| home/away 队名 | ✅ | 从 fixture 列表匹配本场（注意同名队：Serie A 巴西 vs 意甲 135·按 league id 区分） |
| fixture_id | ①输出 | ②③④ 共用 |

## 输出规范（→Step5/6/7 消费）

```
fixture_id / 主客队
predictions: winner=队名·percent(H/D/A%)·advice → Step5 方向外部交叉验证
odds: 13家 Match Winner 均值/极值·亚盘·大小球盘 → Step5-7 与源B1/zgzcw 交叉（🔴补 Odds-API 未覆盖）
injuries: 本场伤停清单（Injury/Suspended·reason）→ Step0④ 与 SL-news-crawl 交叉验证·不改唯一源地位
```

## 🔴边界与错误处理（免费 key）

| 情况 | 处理 |
|:--|:--|
| `league+season=2026` | 无权→必须走 fixtures?date 定位（禁止改查历史赛季代替当前分析） |
| `odds?date=` | 仅最近3天窗口且多为非五大联赛（MLS/巴西甲）→ 不用此路径 |
| `last/next` 参数 | 免费无权（"Free plans do not have access to the Last parameter"）→ 用 date 查询 |
| rate_limit(429) | 返回结构化 `{found:false,reason:"rate_limit"}` → 当日已满·标「api-football 配额耗尽·跳过」·伤停/赔率以其他源为主 |
| auth_failed(401/403) | key 无效→检查 reasonix.toml API_FOOTBALL_KEY |
| 免费日限 100 次 | 每场三端点约 4-5 次调用（fixtures1+predictions1+odds1+injuries1-2）·单日约 20 场预算 |

## 与模型其余部分的关系

- 🔴外部模型输出（predictions 官方概率）**仅交叉验证·禁止混入主判**（Step5 方向以赔率水位+基本面为准）
- 🔴伤停主源仍为 SL-news-crawl（VPN 新闻）·本 skill 仅交叉验证补充
- odds 13 家赔率与源B1 Odds-API/源B2 zgzcw 42家 交叉·冲突以欧盘口径处理（修正30/44D）
- 官方 @pipeworx/mcp-api-football 包无 bin 无法启动+无伤停工具·已弃用·勿再使用

## 🔴消费判定标准（🔴待回测验证·非固化规则·方法论铁律: 判定标准需≥20-30场同向回测支撑才固化）

### A. 伤停交叉验证（api-football injuries vs SL-news-crawl·Step0④/修正58/铁则32）
| 情形 | 判定 | 状态 |
|:--|:--|:--|
| 双方一致（都报某球员伤/停） | 确认·按修正58 位置级执行（射手净胜-1/后腰中卫+BTTS/门将总进球+1） | ✅修正58为既有回测规则·api仅数据输入 |
| api 独有（新闻漏·尤其 Suspended 停赛） | 纳入判定·停赛确定性强补新闻缺口 | ⏳待回测(补录逻辑) |
| 新闻独有（api 无）/ 人数冲突 | 以新闻为准（唯一主源）·标注「伤停源分歧」 | ✅既有铁则(新闻唯一主源) |
| api+新闻合计伤停 ≥3 人 | 🔴触发铁则32（平局上调检查·与修正53 联动） | ✅铁则32为既有回测规则 |
| 🔴伤停位置级→比分锚消费（实证) | 进攻核心缺阵(射手/前腰/边锋)→λh/λa降·该队进球比分权重降(实证: 图卢兹 Francis缺阵→0:1升/1:2降)·主力后防缺→失球比分(0:1/1:2场景)升·门将缺→总进球+1参考·🟡按位置调候选权重·禁机械套规则 | ✅位置级修正58延伸·api提供具体球员位置信息 |
| 盘口未响应伤停（V6 窗口） | 修正58 判定诱盘 | ✅既有规则 |

### B. 三源赔率冲突优先级（api-football 13家 vs 源B1 vs 源B2·Step5）
```
方向基准: zgzcw 42家均值(主) → api-football 13家均值(次) → Odds-API 1xbet+B365(辅)  ⏳待回测
一致 → 增强确认（置信度维持）                                    ⏳待回测
分歧(胜平负主向不一致) → 标注「三源赔率分歧」·置信度-1档(最高MID)·以zgzcw为准  ⏳待回测
api 亚盘/大小球 → V6联动(修正54-58)补充数据源·与Odds-API Spread/Totals交叉   ✅既有V6规则
```

### C. predictions 官方概率交叉（Step5 方向）✅回测（2024英超15场抽样)
> 🔴回测结论: 官方概率命中率 93.3%(14/15) **但全部为双机会命中**(draw+away或home+draw·45%并列·纯单方向命中率 **0/15=0%**)——官方预测**从不给出单一强方向**·本质=双机会保守模型
> 🔴推论: 官方概率**无单方向判别力**→ 不能支撑方向增强/降级判定·仅作「双机会弱参考」
| 情形 | 判定（回测支撑） |
|:--|:--|
| 官方双机会含模型主方向 | 标注「外部双机会一致」·不改置信度 |
| 官方双机会不含模型主方向 | 标注「外部双机会分歧」·**不降级**（官方无单方向判别力·样本n=15·差异待更大样本验证） |
| 官方平局 percent ≥30% | 修正53 平局序列 S 系补充信号 +1（观察项·回测中 draw 常在双机会内） |
| ⏳持续积累 | 每场分析记录 predictions 对账·≥20-30场后复核「双机会命中率 vs 66.7% 随机基准」是否显著>基准才可升级为方向信号 |
