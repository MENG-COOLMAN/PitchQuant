<div align="center">

# ⚽ PitchQuant

### 足球赔率分析模型 · Public Release v1.0 ｜ Core Model V3.5.74

> ### 🎯 A football-odds pipeline where the LLM **executes** a 238-check auditable workflow — and every weight is **earned from 227k-match backtests**.
> ### 🎯 一条由 **238 道校验**锁定的 LLM 分析流水线 —— 每一个权重都来自 **22.7 万场回测**。

**Pitch**（绿茵场）× **Quant**（量化）—— 用量化研究的方式对待足球数据，但始终记得：**足球是混沌的，市场是高效的**。

**LLM as runtime · Backtests as discipline**
**把 LLM 当运行时 · 把回测当纪律**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Skills](https://img.shields.io/badge/Skills-34-green)
![Scripts](https://img.shields.io/badge/Scripts-139-yellow)
![Auto--Checks](https://img.shields.io/badge/Auto--Checks-238-orange)
![Backtest](https://img.shields.io/badge/Backtest-227k%20matches-purple)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

> ## ⚠️ 重要声明 · IMPORTANT NOTICE
>
> **本项目仅用于学术交流与技术学习。严禁用于任何博彩、投注、赌博用途。不构成任何投注建议。**
> **FOR ACADEMIC & EDUCATIONAL USE ONLY. Use for gambling/betting is strictly PROHIBITED. NOT betting advice.**
>
> 📄 完整法律条款（禁止用途 / 无保证声明 / 第三方权利 / 责任限制 / 使用者合规责任）：**[DISCLAIMER.md](DISCLAIMER.md)**
> 📄 Full legal terms: **[DISCLAIMER.md](DISCLAIMER.md)**
>
> 作者**诚实披露**：竞彩串关长期 **EV 为负**（结构性特征，与任何模型无关）。历史回测数字**仅用于方法论验证**，不代表未来表现。

</div>

---

# 🇬🇧 English

## What is PitchQuant?

Most "AI prediction" projects treat the LLM as an **oracle**: feed it data, ask for an answer, trust the black box.

**PitchQuant does the opposite.** It treats the LLM as a **runtime** — an executor that follows a locked-down pipeline, while every deterministic computation is handled by auditable Python scripts and every judgement is bound to machine-checkable evidence.

```
Traditional:   Data ──▶ LLM ──▶ "Prediction"        (black box · unreproducible)
PitchQuant:    Data ──▶ Scripts (math) ──▶ Checklist ──▶ LLM (judgement) ──▶ Gates (238 checks) ──▶ Archive
                        ▲ deterministic                 ▲ constrained            ▲ enforced
```

The result is not a better crystal ball. It is an **auditable analysis system that is allowed to reject itself** — when our own online-learning layer failed its backtest (−14.2 pp vs baseline), we disabled it and demoted it to "logging only". Most projects only ship their successes; a system that can *falsify its own components* is the actual engineering claim here.

### 📟 What the output actually looks like

```
$ python scripts/tmp/calc_poisson.py --home 2.50 --draw 3.40 --away 2.80 --o25 1.90 --u25 1.85 --top 5

λh=1.34  λa=1.31      |  Direction: Home 37.6% / Draw 26.1% / Away 36.2%
Convergence: converged  (multi-init deviation 0.00 · Dixon-Coles ρ=-0.12)
Net-margin probs:  Home+1 19.1% · Home+2 11.0% · Home+3 6.0% · Draw 29.1% · Away+1 18.7% ...
Over 2.5: 49.3%       |  Expected total goals: 2.65
Score Top-5:  1:1 13.9% (main) │ 0:0 8.6% (secondary) │ 2:1 8.3% │ 1:2 8.1% │ 1:0 8.0%
```

*Real output — not a mock-up. The core is deterministic: same input ⇒ same numbers.*

## The Core Idea: LLM as Runtime, Not Oracle

| Dimension | LLM-as-Oracle (common) | **PitchQuant (LLM-as-Runtime)** |
|:--|:--|:--|
| Who computes | The LLM (probabilities, arithmetic) | **Scripts** — de-vig, Poisson, Kelly, lookup tables |
| Who judges | The LLM, freely | The LLM, **constrained** by a generated checklist + rule hierarchy |
| Reproducibility | Non-deterministic | **Deterministic core** — same input ⇒ same numbers |
| Auditability | None | **Every analysis archived** with 8 sections + evidence trail |
| Failure mode | Silent hallucination | **Compile-time failure** (238 automated checks) |
| Self-correction | Rare | **Built-in falsification gates** (backtest + significance + rollback) |

### 🧰 Tech Stack & Keywords

| Area | Technologies / terms |
|:--|:--|
| **Statistics** | **Poisson distribution** modelling · **Dixon-Coles** low-score correction (ρ=−0.12) · **de-vigging** (proportional + calibration-table) · **Kelly criterion** · **time-split backtesting** · probability calibration curves |
| **Markets** | **Asian handicap** (spread + water level) · Over/Under totals · correct-score (CS) matrices · BTTS · half-time/full-time · **odds-movement morphology** (drift pattern classification) |
| **Engineering** | deterministic Python core · **LLM orchestration** (runtime, not oracle) · script-generated checklists · **238 automated consistency checks** · anti-overfitting gates · tri-state evidence tagging · reproducible archives |
| **Data sources** | odds-api (European markets) · api-football (official predictions / injuries) · ClubElo (ELO) · Understat (xG) · Chinese Sports Lottery official public odds |

## What Makes It Different

1. **📉 Market-first by evidence, not by taste** — a 227k-match backtest shows the de-vigged market is the best-calibrated signal (±5pp, with a systematic *favourite undervaluation* of +2–4pp). So the market gets the **largest weight (0.30)** in the live fusion engine — and our own Poisson model was *downgraded* to 0.07 to make room. Architecture follows data, not intuition.
2. **🎲 Weak-consensus rule** — when market skew <150%, the favourite hits only **36–43%** (a coin flip). The system therefore **forces the draw to be listed as a co-primary outcome** instead of confidently picking the favourite.
3. **⚓ Anchor consistency, machine-enforced** — score anchors (main/secondary) are automatically checked against market net-goal band, O/U direction, and the Asian line. Contradictions raise warnings and produce a *corrected anchor suggestion*; blindly copying the model's Top-1 output is forbidden by rule.
4. **🛡️ Anti-overfitting gates (four layers)** — any new feature, weight or "learned rule" must pass: **(a)** time-split backtest with **p<0.05**, **(b)** sample-size thresholds, **(c)** rolling 20-match deviation >10pp ⇒ auto-rollback to display-only, **(d)** out-of-range value clipping. No evidence ⇒ no decision authority.
5. **🧾 Evidence-bound self-check** — "**no number = not done**". Every judgement carries a value; every inapplicable item must be explicitly tri-state-tagged (`triggered(value)` / `not-triggered(reason)` / `no-data(reason)`). Silent skipping is structurally impossible.
6. **🚦 Three-layer data-chain risk policy** — changes are classified as ① input/parsing (🔴 dangerous) ② data tables (🔴 rename = silent downstream failure) ③ display/audit (🟢 safe). New annotations may **only** go into layer ③. This policy exists because all three of our historical incidents were layer-① bugs (format mismatches that failed *silently*).
7. **🧠 34 domain skills, not one prompt** — referee rules (`rule51–70`), five league sub-models distilled from 8,700–9,300 matches each, home/away factor tables for 139 teams, European two-leg logic. Knowledge is versioned, auditable files — not vibes inside a prompt.
8. **📚 Auditable archive** — every analysis is persisted with source odds, computed probabilities, rule traces, learning-loop markers and (later) the actual result, enabling long-run calibration studies on your own history.

## Architecture

### Four layers + four gates

```
┌──────────────────────────────────────────────────────────────────────┐
│  RUNTIME      LLM executes AGENTS.md pipeline step-by-step           │
│               (no ad-hoc steps · checklist-driven · tri-state tags)  │
├──────────────────────────────────────────────────────────────────────┤
│  KNOWLEDGE    34 × SKILL.md                                          │
│               rule hierarchy L1–L5 · 5 league sub-models ·           │
│               referee rules · audit & maintenance discipline         │
├──────────────────────────────────────────────────────────────────────┤
│  COMPUTE      139 × Python (deterministic)                           │
│               de-vig · Kelly · Poisson(λ) + Dixon-Coles ·            │
│               score-depth lookup · live multi-source fusion engine   │
├──────────────────────────────────────────────────────────────────────┤
│  DATA         distilled JSON tables (backtest artifacts)             │
│               league baselines · goal-bins · score-depth ·           │
│               water-level intent · draw-temperature · HT/FT matrix   │
├──────────────────────────────────────────────────────────────────────┤
│  GATES        ① calc_all   → precompute + generated checklist        │
│               ② output_checker → 35 required blocks                  │
│               ③ check_luopan   → archive structure & trace           │
│               ④ check_sync     → 238 consistency checks              │
└──────────────────────────────────────────────────────────────────────┘
```

### The pipeline (Step 0 → 11)

```
PreStep ──▶ ① Data acquisition (multi-source · tri-state tagged)
            ② Hardcore layer (12 items: de-vig → calibration → skew → Kelly)
            ③ Movement layer (V1–V6: odds drift · trap detection · water levels)
            ④ Scenario rules (44/45/46 + European rule-set)
            ⑤ Inferences (26 correction items, each trigger-justified)
            ⑥ League sub-model (R1–R20, per-league)
            ⑦ Home/Away factor (HAF: venue-specific λ coupling)
            ⑧ Direction verdict (market + draw-signal aggregation + skew rule)
            ⑨ Goals depth (O2.5 → goal distribution → signal strength tiers)
            ⑩ Score spectrum (Poisson + lookup fusion + anchor consistency)
            ⑪ Totals + cross-validation ──▶ Self-check (22+ items) ──▶ Archive
```

**Design decisions worth noting**

| Decision | Why |
|:--|:--|
| Compute split from judgement | The LLM never does arithmetic → no precision hallucination |
| Checklist generated *by script* | The executor cannot forget a step it never chose |
| Rule hierarchy L1–L5 | 150+ rules cannot conflict unpredictably; lower layers may only adjust confidence, never reverse direction |
| Live fusion engine (7 sources) | Market .30 / HT .24 / CS .20 / halftime .10 / Poisson .07 / handicap .06 / totals .06 — weights **optimised on 20k matches**, not guessed |
| Everything archived | Research must be reproducible; post-hoc analysis is the only honest feedback loop |

## Backtest Evidence

| Finding | Data | Result |
|:--|:--|:--|
| Market calibration | 227k matches | Highest-probability band hits **+0.3 … +4.4 pp above implied** (favourites systematically undervalued) |
| Weak-consensus breakpoints | 227k matches | skew <110%: **36.4%** · 110–130%: 38.6% · 130–150%: **43.0%** · ≥200%: **64.6%** |
| Anchor trustworthiness | 157-case library | Actual total ≤3 goals: anchor hit **36.4%** · ≥4 goals: **2.9%** · ≥5 goals: **0%** |
| Over/Under signal tiers | 148,397 matches (time-split) | Strong(≥58%): **65.0%** · Medium(55–58%): 57.0% · Weak(53–55%): 54.8% ≈ random |
| Fusion weight search | 20,000 matches | market .7 + poisson .15 optimum: **Top-1 14.37%** vs 12.32% without market source |

*All figures are methodology-validation only — see [docs/methodology.md](docs/methodology.md).*

## Quick Start

> **⚠️ 运行时说明**：本项目不是独立 CLI 工具，而是一套 **LLM as runtime** 分析流水线。Python 脚本只做确定性计算（去水/泊松/查表），规则判断与逐步推理由 LLM（Claude / GPT / 豆包等）按 `skills/` 下的 SKILL.md 执行。你需要一个支持文件读写的 LLM 环境来驱动它。

**Step 1 — Python 3.10+**
```bash
python --version        # 3.10 or newer
pip install -r requirements.txt   # optional: river (online-learning module)
```

**Step 2 — Get the code**
```bash
git clone <your-repo-url>
cd PitchQuant
```

**Step 3 — Configure API keys** (free tiers are enough)
```bash
cp .env.example .env
# edit .env: ODDS_API_KEY (odds-api.io) / API_FOOTBALL_KEY (api-football.com)
```
> Optional: a local proxy (`HTTPS_PROXY`) helps reach some sources on restricted networks.
> 📋 Full checklist (what you must provide / which APIs / free tiers / graceful degradation): **[docs/data-and-apis.md](docs/data-and-apis.md)**

**Step 4 — Prepare your input** — a plain-text odds file (Chinese lottery format):
```
【胜平负】2.67,3.22,2.25 → 2.75,3.22,2.20 → 2.67,3.22,2.25
【让球+1】1.47,3.95,5.10 → ... → 1.48,3.95,5.00
【总进球】... → 15.00,5.90,3.30,3.40,5.45,9.50,20.00,31.00
【比分】1:1=6.25 1:2=8.00 2:1=9.00 ...
```
(`→` separates timestamps — the model reads the whole movement series.)

**Step 5 — Run the pipeline**
```bash
python scripts/tmp/calc_all.py <your-odds.txt> 英超 --eu 1.55,4.20,6.00 --handi -1 --o25 1.90
```
Outputs: de-vig probabilities → hardcore items → direction engine → live score engine (multi-source fusion) → consistency checks (anchor vs market / magnitude) → a generated checklist you must walk through.

**Step 6 — Verify the environment**
```bash
python -m compileall -q scripts/ templates/          # syntax check
python scripts/tmp/calc_poisson.py --home 2.50 --draw 3.40 --away 2.80 --o25 1.90 --u25 1.85 --top 5
# Expected: λh/λa values + score Top5 table printed
```

## Project Structure

```
PitchQuant/
├── skills/          34 × SKILL.md   — rules, league sub-models, audit discipline
├── scripts/
│   ├── tmp/         core pipeline (calc_all · calc_poisson · live engine · gates)
│   ├── online_learning/   post-match learning loop (5 layers)
│   └── backtest/    backtest & data-building utilities
├── tables/          9 distilled JSON tables (league baselines, goal-bins, …)
├── templates/       analysis output template + case template
├── docs/            architecture · methodology · getting-started · data-and-apis
├── examples/        anonymised real case (including a mis-prediction post-mortem)
└── DISCLAIMER.md · NOTICE.md · LICENSE
```

## Data Notice

| Data | Included? | Why |
|:--|:--|:--|
| `tables/*.json` (distilled) | ✅ | Our **statistical derivatives** (hit rates / ratios) — free to use |
| Raw 227k-match CSV / SQL / European DB | ❌ | Size + source terms — see below for full credits |
| API keys | ❌ never | Env vars only |

**Backtest data sources** (publicly available, used for research):
**Football-Data.co.uk** (results / stats / odds) · **ClubElo** (ELO ratings) · integrated dataset **xgabora/Club-Football-Match-Data** (Gábor, A.) · **China Sports Lottery** official public odds.

📄 Full credits, citation and compliance statement: **[NOTICE.md](NOTICE.md)**

## Disclaimer

Research/engineering use only. Long-term EV is negative. Comply with local laws and data-source ToS.

## Scope & Limitations

| Item | Detail |
|:--|:--|
| **Primary leagues** | Premier League, La Liga, Bundesliga, Serie A, Ligue 1 + Champions League / Europa League |
| **Other leagues** | Not calibrated — use at your own risk |
| **Input required** | Manual plain-text odds file (Chinese lottery format) — no auto-scraping |
| **Backtest size** | 227k league matches + 1,174 European fixtures |
| **No guarantee** | Historical backtest results are methodology validation only, not future performance promises |
| **Known issue** | `check_sync.py` requires the full model's AGENTS.md (not included in public release) |

---

# 🇨🇳 中文

## PitchQuant 是什么？

大多数"AI 预测"项目把大模型当**预言机**：喂数据、要答案、信黑盒。

**PitchQuant 反其道而行。** 它把大模型当**运行时**——一个沿着锁定流水线执行的执行器；所有确定性计算交给**可审计的 Python 脚本**，所有判断都要绑定**机器可查的证据**。

```
传统做法:   数据 ──▶ 大模型 ──▶ "预测结果"        （黑盒 · 不可复现）
PitchQuant: 数据 ──▶ 脚本(算) ──▶ 必核清单 ──▶ 大模型(判) ──▶ 四道门(238校验) ──▶ 存档
                     ▲ 确定性              ▲ 受约束          ▲ 强制执行
```

它给出的不是更好的水晶球，而是一套**可审计、且允许自我否决的分析系统**——当我们的在线学习层没有通过回测（较基准 −14.2 个百分点）时，**我们把它关掉了**，降级为"仅记录"。多数项目只展示成功；**一个能证伪自己组件的系统**，才是这里真正的工程主张。

### 📟 实际输出长什么样

```
$ python scripts/tmp/calc_poisson.py --home 2.50 --draw 3.40 --away 2.80 --o25 1.90 --u25 1.85 --top 5

λh=1.34  λa=1.31      |  方向: 主 37.6% / 平 26.1% / 客 36.2%
收敛状态: converged    （多初始值偏差 0.00 · Dixon-Coles ρ=-0.12）
净胜档概率: 主胜1球 19.1% · 主胜2球 11.0% · 主胜3+球 6.0% · 平局 29.1% · 客胜1球 18.7% …
大球 O2.5: 49.3%      |  总进球期望: 2.65
比分 Top5:  1:1 13.9%（主锚）│ 0:0 8.6%（次锚）│ 2:1 8.3% │ 1:2 8.1% │ 1:0 8.0%
```

*这是真实输出（非示意图）。内核是确定性的：同输入 ⇒ 同数字。*

## 核心理念：把 LLM 当运行时，而不是预言机

| 维度 | LLM 即预言机（常见） | **PitchQuant（LLM 即运行时）** |
|:--|:--|:--|
| 谁来算 | 大模型（概率、算术） | **脚本** —— 去水 / 泊松 / 凯利 / 查表 |
| 谁来判 | 大模型，自由发挥 | 大模型，**受生成清单 + 规则层级约束** |
| 可复现性 | 非确定性 | **确定性内核** —— 同输入 ⇒ 同数字 |
| 可审计性 | 无 | **每场分析全量存档**（八节 + 证据链） |
| 失效模式 | 静默幻觉 | **编译期失败**（238 条自动校验） |
| 自我修正 | 罕见 | **内建证伪门禁**（回测 + 显著性 + 自动回滚） |

### 🧰 技术栈与关键词

| 领域 | 技术 / 术语 |
|:--|:--|
| **统计学** | **泊松分布**建模 · **Dixon-Coles** 低比分修正（ρ=−0.12）· **去水**（等比例 + 校准表）· **凯利公式** · **时间分割回测** · 概率校准曲线 |
| **盘口市场** | **亚盘让球/水位** · 大小球 · 比分盘矩阵 · BTTS · 半全场 · **赔率变动形态学**（漂移形态分类） |
| **工程** | 确定性 Python 内核 · **LLM 编排**（运行时而非预言机）· 脚本生成必核清单 · **238 条自动一致性校验** · 防过拟合门禁 · 三态证据标注 · 可复现存档 |
| **数据源** | odds-api（欧盘）· api-football（官方概率/伤停）· ClubElo（ELO）· Understat（xG）· 中国体育彩票官方公开赔率 |

## 核心优势（为什么值得一读）

1. **📉 市场优先：由证据决定，而非口味** —— 22.7 万场回测证实欧赔去水是**校准最好**的信号（±5pp 内，且系统性**低估热门 2–4pp**）。于是市场在实时融合引擎里拿到**最大权重（0.30）**——而我们自己的泊松模型被**降权到 0.07** 给它让路。**架构跟着数据走，不跟着直觉走。**
2. **🎲 弱共识铁律** —— 市场分歧度 skew <150% 时，热门方向命中仅 **36–43%**（等同抛硬币）。系统因此**强制把平局列为并列主方向**，而不是自信单押。
3. **⚓ 锚定一致性：机器强制** —— 比分锚（主锚/次锚）自动与市场净胜档、大小球方向、亚盘方向三项交叉校验；矛盾即告警并生成**修正建议锚**。规则明确禁止照搬模型 Top1 输出。
4. **🛡️ 四层防过拟合门禁** —— 任何新特征/权重/"学习成果"必须通过：**（a）** 时间分割回测且 **p<0.05**；**（b）** 样本量门槛；**（c）** 滚动 20 场偏差 >10pp ⇒ **自动回滚**为仅展示；**（d）** 超范围值裁剪。**无证据 = 无判定权。**
5. **🧾 证据绑定自检** —— "**没有数字 = 没有执行**"。每条判定附数值；每个不适用项必须显式三态标注（`触发(数值)` / `不触发(原因)` / `无数据(原因)`）。**静默跳过在结构上不可能发生。**
6. **🚦 数据链三层风险纪律** —— 改动分三类：①输入/解析（🔴 高危）②数据表（🔴 改键名=下游静默失效）③展示/留痕（🟢 安全区）。**新增标注只允许放第③层**。这条纪律的由来：本项目历史上三起事故**全部**是①层的格式不匹配——而且是**静默**失败。
7. **🧠 34 个领域技能，而不是一段提示词** —— 裁判规则（rule51–70）、五大联赛子模型（每个蒸馏自 8,700–9,300 场）、139 支球队的主客场因子表、欧战两回合逻辑……知识是**可版本化的文件**，不是提示词里的"感觉"。
8. **📚 可审计存档** —— 每场分析持久化：原始赔率、计算概率、规则触发痕迹、学习闭环标记，以及（赛后）真实结果——让你能在**自己的历史**上做长期校准研究。

## 架构详解

### 四层结构 + 四道质量门

```
┌──────────────────────────────────────────────────────────────────────┐
│  运行层    LLM 按 AGENTS.md 流水线逐步执行                              │
│            （不自创步骤 · 清单驱动 · 三态标注）                          │
├──────────────────────────────────────────────────────────────────────┤
│  知识层    34 × SKILL.md                                              │
│            规则层级 L1–L5 · 五大联赛子模型 · 裁判规则 · 审计与维护纪律    │
├──────────────────────────────────────────────────────────────────────┤
│  计算层    139 × Python（确定性）                                       │
│            去水 · 凯利 · 泊松(λ)+Dixon-Coles · 比分深度查表 ·           │
│            现场多源动态融合引擎                                         │
├──────────────────────────────────────────────────────────────────────┤
│  数据层    蒸馏表 JSON（回测产物）                                       │
│            联赛基准 · 进球档 · 比分深度 · 水位意图 ·                     │
│            平局温度 · 半全场条件矩阵                                    │
├──────────────────────────────────────────────────────────────────────┤
│  质量门    ① calc_all   → 预计算 + 生成必核清单                         │
│            ② output_checker → 35 个必填块                               │
│            ③ check_luopan   → 存档结构与留痕                            │
│            ④ check_sync     → 238 条一致性校验                          │
└──────────────────────────────────────────────────────────────────────┘
```

### 完整管线（Step 0 → 11）

```
PreStep ──▶ ① 数据获取（多源 · 三态标注）
            ② 硬核层（12 项：去水 → 校准 → skew → 凯利）
            ③ 变动层（V1–V6：赔率漂移 · 诱阻识别 · 水位联动）
            ④ 场景规则（44/45/46 + 欧战规则集）
            ⑤ 推论层（26 项修正，逐项给触发理由）
            ⑥ 联赛子模型（R1–R20 · 每联赛独立）
            ⑦ 主客场因子（HAF：按场地子集的 λ 耦合）
            ⑧ 方向判定（市场 + 平局信号聚合 + 弱共识规则）
            ⑨ 大小球深度（O2.5 → 进球分布 → 信号强度三档）
            ⑩ 比分谱系（泊松 + 查表融合 + 锚定一致性）
            ⑪ 总进球 + 交叉验证 ──▶ 自检（22+ 项）──▶ 落盘存档
```

### 值得注意的设计决策

| 决策 | 为什么 |
|:--|:--|
| **计算与判断分离** | 大模型永远不做算术 → 根除"精度幻觉" |
| **清单由脚本生成** | 执行者无法遗漏一个"不是他自己选的"步骤 |
| **规则层级 L1–L5** | 150+ 条规则不会不可预测地冲突；低层级只能调置信度，**永不反转方向** |
| **现场融合引擎（7 源）** | 市场 .30 / 半场 .24 / 比分盘 .20 / 半全场 .10 / 泊松 .07 / 亚盘 .06 / 大小球 .06 —— 权重在 **2 万场**上寻优得出，不是拍脑袋 |
| **一切皆存档** | 研究必须可复现；赛后分析是唯一诚实的反馈回路 |

## 回测证据

| 发现 | 数据量 | 结果 |
|:--|:--|:--|
| 市场校准度 | 22.7 万场 | 最高概率档实际命中 **比隐含高 0.3–4.4pp**（热门被系统性低估） |
| 弱共识分档断点 | 22.7 万场 | skew <110%：**36.4%** · 110–130%：38.6% · 130–150%：**43.0%** · ≥200%：**64.6%** |
| 比分锚可信度 | 157 场案例库 | 实际总进球 ≤3 球：锚命中 **36.4%** · ≥4 球：**2.9%** · ≥5 球：**0%** |
| 大小球信号分层 | 148,397 场（时间分割） | 强(≥58%)：**65.0%** · 中(55–58%)：57.0% · 弱(53–55%)：54.8% ≈ 随机 |
| 融合权重寻优 | 20,000 场 | 市场 .7 + 泊松 .15 最优：**Top-1 14.37%** vs 无市场源 12.32% |

*以上数字仅用于方法论验证 —— 详见 [docs/methodology.md](docs/methodology.md)。*

## 快速开始（每一步）

> **⚠️ 运行时说明**：本项目不是独立命令行工具，而是一套 **LLM as runtime** 分析流水线。Python 脚本只做确定性计算（去水/泊松/查表），规则判断与逐步推理由 LLM（Claude / GPT / 豆包等）按 `skills/` 下的 SKILL.md 执行。你需要一个支持文件读写的 LLM 环境来驱动它。

**第 1 步 · 环境（Python 3.10+）**
```bash
python --version        # 需 3.10 或更新
pip install -r requirements.txt   # 可选依赖: river（在线学习模块）
```

**第 2 步 · 获取代码**
```bash
git clone <你的仓库地址>
cd PitchQuant
```

**第 3 步 · 配置 API key**（免费额度即可）
```bash
cp .env.example .env
# 编辑 .env: ODDS_API_KEY（odds-api.io）/ API_FOOTBALL_KEY（api-football.com）
```
> 可选：本地代理（`HTTPS_PROXY`）——在受限网络环境下访问部分数据源需要。

> 📋 **完整清单**（你必须自备哪些数据 / 需要哪些 API / 免费额度 / 没有 key 时的降级行为）：**[docs/data-and-apis.md](docs/data-and-apis.md)**

**第 4 步 · 准备输入**——一个纯文本赔率文件（竞彩格式）：
```
【胜平负】2.67,3.22,2.25 → 2.75,3.22,2.20 → 2.67,3.22,2.25
【让球+1】1.47,3.95,5.10 → ... → 1.48,3.95,5.00
【总进球】... → 15.00,5.90,3.30,3.40,5.45,9.50,20.00,31.00
【比分】1:1=6.25 1:2=8.00 2:1=9.00 ...
```
（`→` 分隔不同时间点的赔率 —— 模型会读取**整条变动序列**，这正是"形态学"分析的输入。）

**第 5 步 · 跑流水线**
```bash
python scripts/tmp/calc_all.py <你的赔率.txt> 英超 --eu 1.55,4.20,6.00 --handi -1 --o25 1.90
```
输出包含：去水概率 → 硬核 12 项 → 方向引擎 → **实时比分引擎**（多源动态融合）→ 一致性检查（锚 vs 市场 / 锚 vs 量级）→ 一份**必核清单**（LLM 必须逐项走完）。

**第 6 步 · 验证环境**
```bash
python -m compileall -q scripts/ templates/          # 语法检查
python scripts/tmp/calc_poisson.py --home 2.50 --draw 3.40 --away 2.80 --o25 1.90 --u25 1.85 --top 5
# 预期输出: λh/λa + 比分Top5表
```

## 目录结构

```
PitchQuant/
├── skills/          34 × SKILL.md  —— 规则 · 联赛子模型 · 审计纪律
├── scripts/
│   ├── tmp/         核心流水线（calc_all · calc_poisson · 现场引擎 · 校验器）
│   ├── online_learning/  赛后学习闭环（5 层）
│   └── backtest/    回测与数据构建工具
├── tables/          9 张蒸馏表（联赛基准 · 进球档 · …）
├── templates/       分析输出模板 + 案例模板
├── docs/            架构 · 方法论 · 操作手册 · 数据与API清单
├── examples/        脱敏真实案例（含一次误判复盘）
└── DISCLAIMER.md · NOTICE.md · LICENSE
```

## 数据说明

| 数据 | 是否包含 | 原因 |
|:--|:--|:--|
| `tables/*.json`（蒸馏表） | ✅ 已包含 | 本项目**统计衍生结果**（命中率/比率），可自由使用 |
| 22.7 万场原始 CSV / SQL / 欧战库 | ❌ 未包含 | 体积 + 来源条款（**完整致谢见 [NOTICE.md](NOTICE.md) §二**） |
| API keys | ❌ 绝不含 | 一律走环境变量 |
| **竞彩赔率（输入数据）** | — | 取自 **中国体育彩票官方网站**（<https://www.lottery.gov.cn/jc/index.html>）**每日公开数据**（使用者自行抄录 · 本项目不内置）· 详见 [DISCLAIMER.md](DISCLAIMER.md) §4.5 |

**回测数据来源**（均为公开数据 · 用于研究）：
**Football-Data.co.uk**（赛果/统计/赔率）· **ClubElo**（ELO 评分）· 整合数据集 **xgabora/Club-Football-Match-Data**（Gábor, A.）· **中国体育彩票**官方公开赔率。

> 本仓库**不含**任何来源的原始数据文件；`tables/` 仅为统计衍生结果（事实性数据）。
> 完整致谢、引用格式与合规声明：**[NOTICE.md](NOTICE.md) §二**

## 免责声明

仅供研究与工程学习。长期串关 EV 为负。请遵守当地法律法规与数据源服务条款。

## 适用范围与限制

| 项目 | 说明 |
|:--|:--|
| **主打联赛** | 英超、西甲、德甲、意甲、法甲 + 欧冠/欧联 |
| **其他联赛** | 未校准，自行评估风险 |
| **输入方式** | 手动准备纯文本赔率文件（竞彩格式），不自动抓取 |
| **回测规模** | 联赛 22.7 万场 + 欧战 1,174 场 |
| **不保证收益** | 历史回测数字仅验证方法论，不代表未来表现 |
| **已知问题** | `check_sync.py` 需要完整版模型的 AGENTS.md（公开版不含） |

---

## 📚 Further Reading · 延伸阅读

| Document | 内容 / What's inside |
|:--|:--|
| 🔴 **[`prompts/`](prompts/README.md)** | **Prompt 规范集**——分析执行 / 自查补充 / 独立审计 / 模型体检（四件套闭环）<br>Prompt specification set — analyze · self-check · audit · model health |
| [`docs/getting-started.md`](docs/getting-started.md) | 操作手册——输入格式 / 参数解读 / 输出解读 / FAQ / 故障排查<br>Hands-on walkthrough — input format, CLI flags, reading the output, FAQ |
| 🔴 **[`docs/data-and-apis.md`](docs/data-and-apis.md)** | **数据与 API 清单**——你必须自备什么 / 哪些 API / 免费额度 / 降级行为<br>Required data & APIs — what you must provide, free tiers, graceful degradation |
| [`docs/architecture.md`](docs/architecture.md) | 架构与规则优先级——四层结构 / L1–L5 优先级体系 / 四道质量门<br>Architecture & rule priorities — four layers, priority system, quality gates |
| [`docs/methodology.md`](docs/methodology.md) | 方法论——关键回测结论 + 数学公式 + 复现步骤<br>Methodology — backtest findings, formulas, reproduction steps |
| [`examples/`](examples/) | 脱敏完整案例（含一次误判复盘）<br>Anonymized real case, including a mis-prediction post-mortem |
| **[`DISCLAIMER.md`](DISCLAIMER.md)** | ⚠️ **法律免责声明**——学术用途 / 禁止博彩 / 无保证 / 责任限制<br>Legal disclaimer — academic use only, prohibitions, limitation of liability |
| **[`NOTICE.md`](NOTICE.md)** | 第三方商标与数据来源归属<br>Third-party trademarks & data attribution |

**License**: MIT · Contributions & issues welcome · 欢迎 Issue 与 PR

---

## 💬 Contact · 交流

有任何问题、想法或合作意向，欢迎邮件交流：

**📧 jiekefalali@gmail.com**

> 欢迎讨论：**方法论细节 · 回测复现 · 工程实践 · 数据源建议** —— 任何你感兴趣的切入点。
> 也欢迎直接开 [Issue](https://github.com/MENG-COOLMAN/PitchQuant/issues)，公开讨论能让更多人受益。

*Questions, ideas, or collaboration? Feel free to reach out: **jiekefalali@gmail.com** — or [open an issue](https://github.com/MENG-COOLMAN/PitchQuant/issues).*

---

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=MENG-COOLMAN/PitchQuant&type=Date)](https://star-history.com/#MENG-COOLMAN/PitchQuant&Date)

---

> ⚠️ **FOR ACADEMIC & EDUCATIONAL USE ONLY** · 仅用于学术交流与技术学习 · **严禁用于博彩/投注** · 完整法律条款见 [DISCLAIMER.md](DISCLAIMER.md)
