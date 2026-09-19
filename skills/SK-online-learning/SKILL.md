---
name: SK-online-learning
description: 在线学习模块（data/online_learning/·轻封装）——赛后自学习 5 层 + 8 源数据自动接入 + 学习成果提示。🔴赛果后统一入口 learn.py（一条命令·复盘+接入+学习+报告）；L1/L2 已实测无增益→默认不接入预测（仅记录/提示级）；L2 增量合并走批量流程。由主技能在「复盘/赛果」环节调用。
---

# SK-online-learning —— 在线学习模块（轻封装）

## 模块结构（自包含·data/online_learning/）
| 文件 | 职责 |
|:--|:--|
| **learn.py** | 🔴统一入口（赛果→复盘+接入+5层学习+报告·推荐 `--txt`）|
| data_bridge.py | 统一数据接入（8 源·三态标注·完整度）|
| txt_features.py | 竞彩 txt 特征提取（赔率/让球/总进球→O25/半全场/场均进失）|
| river_models.py | L1 River 在线 ML（方向/进球/量级 + ADWIN 漂移）|
| bayes_updater.py | L2 贝叶斯增量表 + 联赛校准（**静态表防污染**·合并走批量）|
| error_miner.py | L3 误差模式→规则 + L4 案例库 CBR |
| learning_loop.py / learn_result.py | 5 步闭环 / 单场学习执行体 |
| validate_learning.py / validate_incremental.py | 真实性验证（时间分割 A/B）|
| state/ · prediction_log/ · docs/ | 状态持久化 / 预测日志 / 验证报告 |

## 使用（一条命令）
```bash
python data/online_learning/learn.py --case <id> --real <比分> \
    --txt <竞彩txt> --league <联赛> --pred "<方向>" --anchor "<主锚>|<次锚>" --center <进球中心>
python data/online_learning/learn.py --status          # 汇总
```
（`data/tmp/learn_from_result.py` 为兼容转发入口）

## 🔴 实测裁决（禁止无回测增益声称）
| 层 | 验证 | 结论 |
|:--|:--|:--|
| L1 River 在线 ML | ①纯赔率 42.23% ②+非赔率特征 47.10%(+4.87pp) ③**融合(热门0.90+ML0.10)=49.43% vs 基准 48.75%(+0.68pp·z=2.12 p<0.05)** | 🔴**特征增强后启用**(权重0.10·仅第6源·不覆盖判定) |
| L2 贝叶斯增量表 | 60000 场公平 A/B（冻结 vs 在线增量·比分 Top2 24.70% vs 24.94%）| 配对 **z=1.59·p>0.05 不显著** → 不接入（价值仅跨赛季长周期）|
| L3 误差规则 | 门槛≥30 样本（尚未达标）| 观察中·与 learned_rules 协同提示 |
| L4 CBR | 案例库 4 场（<10 冷启动）| 未启用 |

## 🔴 学习结果如何接入预测（用户要求"必须影响预测"）
calc_all 输出「🔴融合方向概率(市场0.90+在线ML0.10·门禁=X)」→ **Step5 消费规则**：
| 情况 | 处理 |
|:--|:--|
| 融合与市场同向 | 不改方向建议 |
| 异向差>5pp·**市场弱方向(<45%)** | 🔴建议将融合方向列为**并列候选**(tie-break·不反转主方向) |
| 异向差>5pp·市场强方向(≥45%) | 仅置信度降 1 档·绝不反转方向 |
| 异向且差 ≤5pp | 视作噪声·不调整 |
| 门禁 degraded/权重0 | 忽略融合·仅记录 |

🔴**融合「进入判定」已加**独立门禁 `L1_fusion_in_decision`**（`state/gate.json`·**默认 `enabled=false`**）→ **默认「仅提示·不进入判定」·判定权归【市场+盘口+基本面】**（依据: 融合监测 n=22 融合命中8=基准8 无增益 + L1 已 degraded）；仅当门禁开启（需 n≥50 且增益≥基准 且 p<0.05）才适用下述规则。👇

🔴 **学习成果进入判定（用户要求·分档验证）**：市场最高 **<45%**（弱判定场）→ **学习成果进入主方向判定**（同向→采纳为判定依据；异向差>5pp→融合方向列**并列主方向**）；市场最高 **≥45%**（强判定场）→ **不参与判定**（分档实测净优势=0）。实测: <38% +2.43pp / 38-45% +0.99pp / ≥45% 0。

🔴 **P1-1/P1-2 修复**：①回测中融合以 argmax 决定方向（+0.68pp 来自弱判定场纠偏），故 calc_all 在**弱判定场给并列建议**使增益真正发挥；强判定场严格不反转（铁律优先）②融合不再依赖 `--eu`——自动 fallback 竞彩 txt 末盘去水（`_mk_src` 标注来源）。
**四道门禁**：①回测门禁(p<0.05 才接入) ②样本门禁(50/200 分级权重) ③回滚门禁(滚动20场偏差>10pp 自动降级) ④输出裁剪(超范围丢弃/缺失不计/三态标注)。
命令：`gate.py --status`（状态）/`--log --case X --pred-fused N --pred-base N --actual N`（记录）/`--rollback-check`（回滚检查）。

## 🔴 特征传递铁律（防特征丢失）
**问题根因（已修）**: `learn.py` 原经 subprocess + `--oh/--od/--oa` 命令行传参 → `make_features` 只重建 **A 类 11 特征** → **B/C/D/E 类 24 特征全部丢失**（case_library 24 个 null）。
**修复**: `learn.py` **直接 import learning_loop 传完整特征 dict**（不再命令行传参）·实测 34 键/非空 34·B/C/D/E 非空 12-15。
**铁律**: ①赛后学习必须走 `--txt`（data_bridge 全量）或 `--from-log`（prediction_log 回溯）②**禁止**用 `--oh/--od/--oa` 做生产学习（仅调试）③check_sync 校验 learn.py 直传路径存在。
**CBR 案例库**: add_case 已按 `case_id+date` 去重（原 append 致重复）；已导入 145 个 raw 历史案例 → 案例库 149·**解除冷启动**（方向投票有效·特征缺则相似度退化）。

## 与主模型的边界（🔴 不可越界）
- ⚠️ L1 已按证据启用(权重0.10 第6源·经融合验证+0.68pp)——仍**不主导**判定·不覆盖硬核 L2
- ❌ 不接入 Step5/Step7 判定链（引入噪声）
- 🔴 特征集 34 个（A11+B10+C8+D3+E3·方案000055）·B/C/D 类需 prediction_log 积累后复核
- ❌ 不覆盖硬核 L2（规则判定权在旧模型）
- ✅ 只做：学习台账累积 · 复发自动提示 · calc_all 输出「⚡ 学习成果提示」· 长周期数据更新

## 数据接入（8 源）
`txt`(必得) · `haf`(139 队) · `clubelo`(ELO·中英别名) · `xg`(understat) · `api_football`(官方概率/13家赔率/伤停·日期自动换算 UTC) · `h2h`(Matches.csv) · `news`(需 VPN) · `euro_odds`(需 VPN)
实测本机 **4/8 可用**（txt+clubelo+xg+api_football）·缺失如实三态标注·不臆造。
