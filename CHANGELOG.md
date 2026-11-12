# Changelog · 更新日志

所有重要变更记录于此。格式参考 [Keep a Changelog](https://keepachangelog.com/)。
All notable changes to this project are documented here.

---

## [1.3.0] — 2026-11-13 · Core Model V3.5.94

### ✨ Added · 新增

**架构：Context → Sub-models → Aggregate（总分总）**
- `scripts/tmp/match_context.py` — `MatchContext`：一场比赛的**唯一上下文**（case / 联赛类型 / 全量数据）
- `scripts/tmp/submodel_adapters.py` — **7 个 adapter** 统一契约 `SubModelResult`（applicable / dir_adj / conf_adj / goals_adj / anchor_hints / rules_hit / warnings / scope_blocked）
- `aggregate()` 合并 + **L2 锁**（子模型只降档，永不反转方向）
- 🔴 **强隔离（代码强制）**：`SUBMODEL_SCOPE` 白名单 + `guard_table()` → 越界读表**直接抛 `ScopeViolation`**（欧国联读五大阈值 = 口径污染，被拒）

**锚定：市场三源矩阵 + 信号支持度池（反机械锚定）**
- `market_distribution.py` — **P10 市场三源矩阵**（OU 全档 × AH 全档 × CS 波胆 → NNLS + **IPF** 投影，E[T]/E[M] 精确成立）
- **R10 判定层**（主锚/次锚/零封/大球/异动/深盘/集中度/方向一致）+ **R11 单队进球直盘**（Team Total under 0.5 权威于矩阵后验）+ **R12 双锚联合覆盖**
- **P28/P29**：罚分制 → **信号支持度评分池**（期望 / 大小球 / 让球 / 零封-BTTS / **波胆市场排名**），**选择链零概率项**，候选池**不淘汰**

**量级：分布驱动 + 六级分级**
- `magnitude_band.py` — 完整分布 `pT[0..7]` + 分位数自适应区间 + **密度比权重**（`0.35+0.65×密度`，永不排除）+ 尾部档 `P(k)≥5%` 必进宽池
- `big_pool_policy.py` — **P52 六级**（L5 ≤1.30 / L4 ≤1.40 / L3 ≤1.60 / L2 ≤1.90 / L1 / L0），门槛由 148,397 场时间分割确定
- `goal_count_table.py` — N26 进球数细分（8 档 × 0–7+ 球概率）
- `totals_water_read.py` — Step6.5 大小球盘口水位**六源**精读（盘口线 / 静态水位 / 盘口移动 8 象限 / 碾压局陷阱 / 让球深度 / 市场）

**新增数据源与能力**
- `the_odds_api_fetch.py` — 21–40 家机构（跨市场分歧 · **key 池轮转**：用完才换 / 30 天自动恢复 / INVALID_KEY 切下一个）
- `bsd_layer.py` + `bzzoiro_fetch.py` — **Bzzoiro 结构化伤停**（位置 G/D/M/F · 回归日 · Form5 场均积分）
- `image2txt.py` / `ocr2std.py` / `latest_images.py` — **截图 → 标准赔率文本**（GLM-OCR / GLM-4.6V 双通道分流 · 按批隔离防串场）
- `time_guard.py` — 单一时间入口 + 数据新鲜度分级 + 比赛状态（治「模型时间漂移」）
- 欧冠校准（`ucl_calibration.py` · 正赛 **+0.67 球**）+ 312 队攻防档案（`team_attack_defense.py`）+ 欧冠/欧联/欧协联网站核查表（`europe_check.py`）
- 反机械锚定辅助：`match_params.py`（参数标准化）· `default_cover.py`（默认两向覆盖校验）· `signal_landing.py`（信号落地门禁）· `snapshot_diff.py`（全档时点 diff）

**审计体系（四层 + 矩阵）**
- `audit_steps`（20 步数据层）· `audit_judgment`（算了没写）· `audit_chain`（8 条传导链）· `audit_semantic`（calc 值 vs raw 声明）· `audit_consumption`（信号是否被消费）· `audit_matrix`（38 步 × 审计器 · **盲区 0**）
- 专项：`audit_p52_chain` · `audit_p8_vertical` · `audit_magnitude_band` · `audit_p10` · `audit_p12` · `audit_contracts` · `audit_deadcode`
- `pipeline.py` — **单场全流程入口**（7 Stage）+ **七道交付闸门**

**新增 skills（37 个 · +4）**
- `SK-image-to-txt`（截图入口）· `SK-time-guard`（时间模块）· `SK-run-orchestrator`（开场 preflight）· `SL-totals-water-read`（大小球水位精读）

**新增查表（tables/ 9 → 20）**
- `quadrant_table`（亚盘×大小球四象限 · 148,129 场）· `goal_count_table` · `handi_score_table` · `ucl_calibration` · `canonical_sources` · `scope_registry` · `rule_registry` · `league_season_calib` · `prob_calibration` · `league_red_rate` · `r19_conditional_scores`

### 🔄 Changed · 变更

- **判定优先级改为四级**（L0 硬约束 > L1 本场市场全档 > L2 域内档表 > L3 无回测经验权重仅 tie-break）；超域赛事 L2 三态标注、不参与排序
- **单押准入收紧**：须**同时**满足 skew ≥200% 且最低赔 <1.30，否则强制两向（三向覆盖已废止）
- **量级不再「均值 ± 固定带宽」**（削掉 36% 厚尾）→ 分布驱动；5/6 球档权重 0.10 → 0.54
- **五源 λ 加权 → 取最可靠单条分布**（实测五源 r=0.97~0.99 = 伪多源）
- **`api-football` 停用**（2026-10）→ 赔率 the-odds-api / 伤停 Bzzoiro / 定位 Odds-API / 官方概率与首发 ⚪ 无替代
- **`--handi` 口径防线**：与欧盘均衡线差 ≥0.5 档自动改用均衡线（防竞彩固定 ±1 冒充）
- **完整度封顶**：≤3/7 源 → MID-LOW · 4/7 → MID
- **README 重构**（v1.3）：双轨（EN/ZH）· 补齐架构/回测/口径/局限

### 🗑 Removed · 移除

- `SL-news-crawl`（网页新闻伤停 · 改 Bzzoiro 结构化）· `SL-api-football-chain` · `SL-match-data-crawl`
- `scripts/tmp/api_football_mcp.py` / `fetch_books.py` / `lineups_fetch.py`（随 api-football 停用归档）

### 🔬 数据 · 口径（诚实边界）

- 实战案例库 **346 场**全复盘：方向 ≈73%（两向覆盖口径）/ 比分 ≈27%（主锚**或**次锚）/ 完美 ≈18%
- 量级台账 188 条 · 学习台账 214 条
- ⚠️ **在线 ML（L1）已被正式否决**（`rejected_leak`）：+0.68pp 增益实为标签泄露（26 特征含 17 个赛后统计），仅赛前特征增益 **+0.01pp**
- ⚠️ 宽池必含档补入、部分权重系数**未回测**，代码内标 `⏳ 待回测`

---

## [1.2.0] — 2026-09-29 · Core Model V3.5.76

> 双通道动态判定（竞彩公众 vs 欧亚机构四象限）· 赔率快照时序 · 跨机构共识层 · 审计 fixture 体系

---

## [1.1.0] — 2026-09-24 · Core Model V3.5.75

> 欧国联 / 国家队子模型（658 场四届 R1–R10）· 跨机构分歧层 · 预检实操六项落地

---

## [1.0.0] — 2026-09-19 · 首个公开发布 / First Public Release

### ✨ Added · 新增

**核心组件**
- **34 个 knowledge skills**（规则体系 / 五大联赛子模型 / 裁判规则 / 审计与维护纪律）
- **139 个确定性计算脚本**（去水 · 凯利 · 泊松 + Dixon-Coles · 比分深度查表 · 现场多源融合引擎 · 一致性校验）
- **9 张回测蒸馏表**（联赛基准 / 进球档 / 比分深度 / 水位意图 / 平局温度 / 深度锚 / 半全场条件矩阵…）
- **分析输出模板 + 案例模板**

**Prompt 规范集**（`prompts/`·本项目最具辨识度的部分）
- `01-analyze-a-match.md` — 9 步分析执行规范 + 七条铁律
- `02-self-check-and-patch.md` — 完成度自查与补充（含**历史高频遗漏黑名单**）
- `03-independent-audit.md` — 分析结果独立审计
- `04-audit-the-model.md` — 模型工程审计（12 探查 + 8 维含**实际运行验证**）

**文档**（中英双语 · bilingual）
- `docs/architecture.md` — 四层架构 + 规则优先级 L1–L5 + 四道质量门
- `docs/methodology.md` — 关键回测结论 + **数学公式**（de-vigging / Poisson / Dixon-Coles τ / Kelly）
- `docs/getting-started.md` — 操作手册（输入格式 / 参数 / 输出解读 / FAQ / 故障排查）
- `docs/data-and-apis.md` — **数据与 API 清单**（你需自备什么 / 免费额度 / 降级行为）

**工程**
- `examples/sample-odds.txt` — **真实格式样例**（9 节 · 逐 T 变动 · 全功能激活）
- `examples/case-monza-vs-sassuolo.md` — 脱敏真实案例（含一次误判复盘）
- **`data/` 兼容层** — 使 `git clone` 后即可直接运行（无需调整目录结构）
- CI（`.github/workflows/ci.yml`）：语法检查 + 数据表完整性 + **密钥残留扫描**
- `.gitattributes`（统一行尾）· `.gitignore`（排除密钥/原始数据/运行产物）

**法律文件**
- `DISCLAIMER.md` — 8 条法律条款（项目性质 / 禁止用途 / 无保证 / 第三方权利 / 合规责任 / 责任限制 / 版权 / 效力）
- `NOTICE.md` — 数据来源与致谢 + 第三方商标归属 + **竞彩数据来源合法性声明**
- `LICENSE` — MIT

### 🔄 Changed · 变更

- **项目命名**：`football-odds-model` → **`PitchQuant`**（Pitch × Quant）
- **README 重构**：电梯 pitch · **真实输出预览**（替代 GIF）· 技术关键词块（SEO）· Star History · 联系方式 · 全站双语
- **methodology 强化**：补充公式与复现步骤（3.5KB → 9KB）
- **Further Reading 表**：改为逐条中英对照

### 🗑️ Removed · 移除

- **全部私有数据依赖**：SQL 相关脚本（7 个）与 skills 中的相关描述（已改为通用表述）
- **遗留临时/测试脚本**（10 个：`_verify_*` / `_plan*` / `*_test` / 内部维护工具）
- **原始数据**（`Matches.csv` 43MB · SQL dump · 欧战库 —— 体积与来源条款限制，不发布）

### 🔐 Security & Compliance · 安全与合规

- **全量敏感清洗**：明文 API key → 环境变量 · 本机路径 → 占位符 · 失效旧 key → 前缀掩码（三扫归零）
- **完整数据致谢**：Football-Data.co.uk（赛果/赔率）· ClubElo（ELO）· xgabora/Club-Football-Match-Data（整合数据集·**按作者要求正式引用**）· 中国体育彩票官网（公开赔率）
- **合规边界声明**：学术用途 · 禁止博彩 · **博彩用途许可责任明确转移**（Football DataCo / Genius Sports）

### ✅ Verified · 验证

- **端到端实测**：从 GitHub 重新 clone → CI 三项检查全过 → README 承诺命令全部跑通 → 样例全功能激活
- 语法编译 exit=0 · 9 张表 JSON 可读 · 数据文件 6/6 可读

---

## 关于版本编号 / Versioning Notes

- **本仓库 = Core Model V3.5.74 的公开快照**（`Public Release v1.0 | Core Model V3.5.74`）
- 内部模型版本与公开发布版本**独立演进**：
  - **Core Model V3.5.74** = 完整研究系统的内部版本（含私有数据集与运行环境）
  - **Public Release v1.x** = 面向公开分享的快照（去除私有数据 · 补充文档与合规声明）
- 后续公开发布将在本文件追加条目；内部模型演进不逐条同步至此

---

> ⚠️ **FOR ACADEMIC & EDUCATIONAL USE ONLY** · 仅用于学术交流与技术学习 · **严禁用于博彩/投注** · 完整法律条款: [DISCLAIMER.md](DISCLAIMER.md)
