---
name: SL-footballcharts-fetch
description: footballcharts 五大联赛基本面（源B5·Step0⑩）——积分榜(含expected_points/luck/大球率/ROI)+赛程(Dixon-Coles λ期望进球+校准概率+BTTS/over)+蒙特卡洛赛季预测·🔴仅五大联赛(无欧战/美职联)·外部模型仅交叉验证禁混主判·→Step5/6/7消费
---

# SL-footballcharts-fetch — footballcharts 五大联赛基本面（V3.5.71接入·2026-08-23实测）

> 🔴触发条件: **Step0 第⑩步**，仅五大联赛（premier/spain1/germany1/italy1/france1）+ 荷甲等无 xG 联赛
> 🔴欧战/美职联不查（93 联赛无欧冠/欧联/欧协联·无 MLS）
> 数据源: MCP `footballcharts-mcp`（npx·reasonix.toml env 已配 FC_API_KEY·经代理 7897·代理关闭时直连可用）

## 调用工具与用途

| 工具 | 数据 | 消费点 |
|:--|:--|:--|
| get_league_table(league,season) | 积分榜：position/points/W-D-L/GD/last_5_form/**expected_points**/luck_difference/clean_sheets/**over_25_percentage**/ROI | Step0 基本面·Step4.5 联赛子模型输入参考 |
| get_fixtures(league,season) | 🔴Dixon-Coles v2：**expected_home_goals/expected_away_goals（λ）**+ calibrated(home/draw/away/btts/over_2.5)+ratings(attack/defence)+data_status(stale:false) | Step5 方向(校准概率交叉)·Step6 大球(over 参考)·Step7 比分(λ 辅助 xG 深度·无 xG 联赛可用) |
| get_season_projection(league,season) | 蒙特卡洛 10000 模拟：title/top4/bottom3/mean_pts/position_matrix | Step7 独立比分分布参考（辅助·不入主判） |
| get_team / get_goal_timing / get_rankings | 球队赛程日志/进球时段/运气调整排名 | Step0 可选深度基本面 |

## 联赛 key 对照（93 联赛中五大联赛）

| 联赛 | key | 联赛 | key |
|:--|:--|:--|:--|
| 英超 | premier | 西甲 | spain1 |
| 德甲 | germany1 | 意甲 | italy1 |
| 法甲 | france1 | 荷甲(无xG) | holland1 |
| 苏超 | scot-premier | 日职 | japan1 |

## 输出规范（→Step5/6/7）

```
λ_home / λ_away（expected goals·Dixon-Coles）
calibrated: P_home / P_draw / P_away / P_btts_yes / P_over2.5
积分榜: 两队 position/points/last5/expected_points/luck/大球率
蒙特卡洛: 两队 title概率/top4/mean_pts（赛季预测·非单场）
```

## 🔴边界（必须遵守）

- 🔴**仅五大联赛+欧战需求**：欧战不查（无数据·用 SL-europe-db rule51-66）；美职联不需要
- 🔴外部模型输出**仅交叉验证·禁止混入主判**（主判=赔率水位+基本面·V3.5.67）
- λ/校准概率仅作 Step6 大球/Step7 比分**辅助参考**·不替代源B1 赔率·不写入回测规律库（方法论铁律：禁止单场固化规则）
- get_fixtures 的 data_status 需核对：`stale:true` 或 `matches_behind>0` → 标「数据滞后·参考降级」
- 免费 FC_API_KEY 5000 次/日（占位邮箱注册）·够用

## 错误处理

| 情况 | 处理 |
|:--|:--|
| `Error: No football-charts API key` | FC_API_KEY 缺失/无效 → 检查 reasonix.toml |
| `fetch failed`（代理关闭） | 移除代理直连重试（后端 onrender.com 直连可达·实测） |
| 工具返回空 | 赛季参数错误→换 season（2026-2027/2025-2026） |

## 🔴消费判定标准（2026-08-23·🔴基于真实回测·未回测项标注「待回测」·禁止当作固化规则）

> 🔴回测依据: footballcharts get_track_record(365天·546信号·官方模型已结算对账·2026-08-23实取):
> 总 hit_rate 46.67% · 1x2(方向) **30.95%**(n=129) · ft_ou_25 50.0%(n=146) · ft_ou_35 57.45%(n=94) · ht_ou_15 56.57%(n=100) · bts 40.26%(n=77)
> 🔴铁则: 外部模型仅交叉验证·判定标准需≥20-30场同向回测支撑才固化(方法论铁律)

### D. footballcharts 校准概率/大球率/λ（Step5/6/7·回测支撑分级）
| 数据 | 回测状态 | 判定（仅作弱参考·不改变主判） |
|:--|:--|:--|
| calibrated P_home/P_draw/P_away | ✅回测(1x2 hit 30.95%·n=129·显著低于50%基准) | 🔴官方方向概率本身命中率低→仅作**弱方向参考**·与模型主方向一致→**不增强**·冲突→**不降级**·只标注「外部方向分歧」(防低质信号干扰主判) |
| calibrated over_2.5 | ✅回测(ft_ou_25 hit 50.0%·n=146) | 与市场基准(约50%含抽水)相当→**中性参考**·与 Step6 大球同向→维持·冲突→标注不降级(50%无区分度) |
| calibrated over_3.5 / ht_over_1.5 | ✅回测(57.45%/56.57%) | 略高于50%→**弱增强参考**(同向时可+0.5档观察·不固化) |
| λ = expected_home/away_goals | ⏳待回测(需历史已完赛λ数据) | 暂仅标注「λ参考」·λ_home-λ_away>0.5 的净胜关联**待20-30场回测验证后才启用** |
| 无 xG 联赛 λ 替代 xG 基线 | ⏳待回测 | 暂标「λ替代(未验证)」·不改变 Step7 主锚流程 |
| get_league_table over_25_percentage | ✅回测(联赛级统计·历史赛季) | Step4.5 联赛子模型输入参考(大球率先验·与既有联赛基准一致) |

### E. 蒙特卡洛赛季预测（get_season_projection·Step7 辅助）
- ⏳待回测(赛季级·需赛季完结对比)·暂仅标注「赛季预测参考(未验证)」·🔴不用于单场比分判定
