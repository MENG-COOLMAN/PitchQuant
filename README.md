<div align="center">

# ⚽ PitchQuant

### 足球赔率分析模型 · Public Release v1.3.1 ｜ Core Model V3.5.94（模型本体 · 不含案例库）

> ### 🎯 A football-odds pipeline where the LLM **executes** a 1,160-check auditable workflow — and every weight is **earned from 227k-match backtests**.
> ### 🎯 一条由 **1,160 道校验**锁定的 LLM 分析流水线 —— 每一个权重都来自 **22.7 万场回测**。

**Pitch**（绿茵场）× **Quant**（量化）—— 用量化研究的方式对待足球数据，但始终记得：**足球是混沌的，市场是高效的**。

**LLM as runtime · Backtests as discipline**
**把 LLM 当运行时 · 把回测当纪律**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Skills](https://img.shields.io/badge/Skills-37-green)
![Scripts](https://img.shields.io/badge/Scripts-203-yellow)
![Auto--Checks](https://img.shields.io/badge/Auto--Checks-1160-orange)
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
PitchQuant:    Data ──▶ Scripts (math) ──▶ Checklist ──▶ LLM (judgement) ──▶ 7 Gates (1,160 checks) ──▶ Archive
                        ▲ deterministic                 ▲ constrained            ▲ enforced
```

The result is not a better crystal ball. It is an **auditable analysis system that is allowed to reject itself**:

- our **online-ML layer** was **formally rejected** (`rejected_leak`) once we discovered its +0.68pp gain came from **label leakage** (17 of 26 features were post-match statistics) — with pre-match features only, the gain was **+0.01pp**;
- a "five-source λ fusion" was **abandoned** when pairwise correlations turned out to be **r = 0.97–0.99** (it was averaging the same number five times);
- an equal-weight probability ranking of scorelines was **replaced** once we proved it structurally anchors on low scores.

A system that can *falsify its own components* is the actual engineering claim here.

### 📟 What the output actually looks like

```
$ python scripts/tmp/calc_all.py examples/sample-odds.txt 意甲 \
    --eu 2.10,3.40,3.60 --o25 1.91 --u25 1.95 --handi -1 --net

🔴 分析时间: 2026-11-15 14:32:07 (北京) ｜ 本场状态: 距开赛 743 分钟
去水(欧盘) 主 42.3% / 平 26.1% / 客 31.6%   ｜ skew 162% → 高共识·禁单押
🔴P52 超大球分级: L3（均衡线 3.14 · 宽池必含 1/2/3/4/5/7 球）
量级分布(矩阵+查表尾部): 众数 3 球 ｜ P(≥4球) 37.2% ｜ 尾部档 0/1/2/3/4/5/6
市场三源矩阵(P10): OU 22 档 · AH 16 档 · CS 24 档 → E[T]=3.19 · E[M]=-0.42
让球水位(P1): 上盘覆盖 53.2%（中）→ 净胜档上移 → 支持穿盘
比分池(信号支持度): 1) 1:2 0.87   2) 1:3 0.81   3) 0:2 0.74   4) 2:2 0.68 …
🔴锚-市场/期望复校验(N07b/N18b): ✅ 通过（可落盘）
```

*Real output (trimmed) — the deterministic core means same input ⇒ same numbers.*

## The Core Idea: LLM as Runtime, Not Oracle

| Dimension | LLM-as-Oracle (common) | **PitchQuant (LLM-as-Runtime)** |
|:--|:--|:--|
| Who computes | The LLM (probabilities, arithmetic) | **Scripts** — de-vig, Poisson, lookup tables, market matrix |
| Who judges | The LLM, freely | The LLM, **constrained** by generated checklists + a 4-level priority hierarchy |
| Reproducibility | Non-deterministic | **Deterministic core** — same input ⇒ same numbers |
| Auditability | None | **Every analysis archived** (8 sections) + 4-layer audit trail |
| Failure mode | Silent hallucination | **Gate failure** (1,160 assertions · 7 delivery gates) |
| Self-correction | Rare | **Built-in falsification gates** (backtest + significance + rollback) |

### 🧰 Tech Stack & Keywords

| Area | Technologies / terms |
|:--|:--|
| **Statistics** | **Poisson** modelling · **Dixon-Coles** low-score correction (ρ=−0.12) · **de-vigging** (proportional + calibration) · **Kelly criterion** · **time-split backtesting** · calibration curves · **quantile-adaptive magnitude bands** |
| **Markets** | **Asian handicap** (full ladder + water level) · Over/Under **full ladder** · **correct-score (CS)** matrices · BTTS · Team Total · half-time/full-time · **odds-movement morphology** · **cross-bookmaker divergence** (21–40 books) · **IPF market matrix** (OU × AH × CS) |
| **Engineering** | deterministic Python core · **LLM orchestration** · script-generated checklists · **1,160 consistency assertions** · anti-overfitting gates · tri-state evidence tagging · reproducible archives · **sub-model scope isolation** (`ScopeViolation`) |
| **Data sources** | odds-api (European markets) · **the-odds-api** (21–40 books · cross-book divergence) · **Bzzoiro** (structured injuries / squads / form) · ClubElo (ELO) · Understat (xG) · Chinese Sports Lottery public odds · **Zhipu GLM** (screenshot → odds text) |

> ⚠️ `api-football` was **deprecated in Oct 2026** and removed from the data chain (replacements: the-odds-api for prices, Bzzoiro for injuries, Odds-API for event lookup).

## What Makes It Different

1. **📉 Market-first by evidence, not by taste** — a 227k-match backtest shows the de-vigged market is the best-calibrated signal (±5pp, with systematic favourite undervaluation of +2–4pp). Market gets the largest weight; when the **five-source λ fusion** was measured, correlation was r=0.97–0.99 — so it now takes **the single most reliable distribution** and uses the rest only as a conflict check.
2. **🧱 Hard constraints that no weight can override (L0)** — (a) no home-win score anchor on receiving-handicap matches; (b) single-outcome bets require **skew ≥ 200% AND favourite odds < 1.30**, otherwise **two-way coverage is mandatory**; (c) anchor must match market expected goals (|total − E| ≤ 1.0, and at least one anchor inside E±1.0); (d) deep handicap ⇒ main anchor must clear the line; (e) never reverse the L2 hardcore direction.
3. **🧭 Four-level decision priority (L0 > L1 > L2 > L3)** — hard constraints ▸ this match's full market ladder ▸ domain backtest tables ▸ un-backtested experience weights (tie-break only, ≤2pp). On out-of-domain competitions (cups / minor leagues) L2 is *tri-state tagged* and does **not** participate in ranking.
4. **🕸️ Context → Sub-models → Aggregate (V3.5.94)** — `MatchContext` is the single context per match; 7 sub-model adapters return a unified `SubModelResult`; `aggregate()` merges with an **L2 lock** (sub-models may downgrade confidence, never reverse direction). Scope violations are **enforced in code** (`ScopeViolation`), not by documentation discipline.
5. **🎲 No mechanical anchoring** — scorelines are not ranked by probability (that structurally anchors on 1:1). The pool is **never pruned**; candidates are ranked by **market-signal support** (expected-goals match / O-U direction / handicap depth / clean-sheet-BTTS direct pricing / **correct-score market rank**), with **zero probability terms** in the selection chain.
6. **📊 Magnitude as a distribution, not a point** — mean ± fixed band deleted 36% of the fat tail (4+ goals occur in 44% of matches, yet the main anchor was 2 goals in 98%). Now: full distribution `pT[0..7]` → quantile-adaptive range → **density-ratio weighting** (never excludes, floors at 0.35) → tails with `P(k) ≥ 5%` **must** enter the wide pool.
7. **🛡️ Anti-overfitting gates (four layers)** — any new feature/weight/"learned rule" must pass **(a)** time-split backtest **p<0.05**, **(b)** sample thresholds, **(c)** rolling 20-match deviation >10pp ⇒ auto-rollback, **(d)** out-of-range clipping. No evidence ⇒ no decision authority.
8. **🧾 Evidence-bound self-check** — "**no number = not done**". Every item must be tri-state tagged (`triggered(value)` / `not-triggered(reason)` / `no-data(reason)`). Silent skipping is structurally impossible — and the audit layer catches **"computed but not written"** and even **"written but judged wrong"**.
9. **🧠 37 domain skills** — referee rules (`rule51–70`), five league sub-models distilled from 8,700–9,300 matches each, **Nations League** sub-model (658 matches / 4 editions), European two-leg logic, UCL calibration, team attack-defense profiles (312 teams). Knowledge is versioned and auditable.
10. **📚 Self-falsifying archive** — the project keeps an in-house replay archive (346 reviewed matches) purely to falsify its own rules; **the raw records are private research data and are NOT distributed** with this repository.

## Architecture

### Context → Sub-models → Aggregate

```
                    ┌──────────────────────────────────────────┐
   ① Context       │  match_context.MatchContext              │
                    │  the single context of ONE match         │
                    └───────────────┬──────────────────────────┘
                                    │  read-only ctx · no global file access
        ┌───────────────┬───────────┼───────────┬───────────────┐
        ▼               ▼           ▼           ▼               ▼
   ② Sub-models    top5_epl    nations     europe      none (tri-state)
   7 adapters      laliga/bundesliga/seriea/ligue1
        │
        │  unified contract — SubModelResult:
        │  applicable / reason / dir_adj / conf_adj / goals_adj /
        │  anchor_hints / rules_hit / warnings / scope_blocked
        ▼
   ③ Aggregate     aggregate(): L2 hardcore > sub-model > L3 movement layer
                   + L2 lock (downgrade only, never reverse)
                   + ScopeViolation (code-enforced table whitelist)
```

### The pipeline (Step 0 → 11)

| Stage | What happens |
|:--|:--|
| **PreStep** (optional) | Dual-track scoring (direction + scoreline) over a time window → keeps only strong-signal fixtures |
| **Step 0** | Data acquisition (11 source classes, tri-state tagged) |
| **Step 1** | [L2] 12 hardcore items, unified European-odds convention |
| **Step 2** | Movement layer V1–V6: dual-source drift · trap/block 4-step · actuary cross-check · water linkage · cross-market divergence · handicap linkage |
| **Step 3** | Scenario rules 44/45/46 (European cups trigger `rule51–70` six-item checklist) |
| **Step 4** | Inference layer: fundamentals ABCDE cross-validation |
| **Step 4.5 / 4.6 / 4.8** | League sub-models · Home-away factor layer (HAF) · Nations League sub-model |
| **Step 5** | Direction (computed result → odds cross-check → coverage discipline) |
| **Step 6 / 6.5** | Over/Under depth · magnitude (P52 six-level) · totals water-level reading (6 sources) |
| **Step 7 / 7.5** | Score anchoring (market 3-source matrix → signal-support pool) · half-time inference |
| **Step 8 / 9 / 10** | Total goals · 22-item self-check · archive (8 sections + 15-column CSV) |
| **Step 11** | Batch compression / betting-plan module (user-triggered) |

### The gates (7 delivery gates)

```
[1/7] no leftover placeholders      [2/7] output_checker
[3/7] check_luopan                   [4/7] audit_steps   (data layer · 20 items)
[5/7] audit_judgment (computed→written)  [6/7] audit_chain (8 chains)
[7/7] audit_semantic (calc vs claimed) + audit_consumption + audit_matrix (38 steps · 0 blind spots)
```

## Backtest Evidence

| Finding | Number |
|:--|:--|
| Market calibration (favourite) | implied 70%+ ⇒ actual **80.6%** (systematic **+2 to +4.4pp** undervaluation) |
| Single-outcome bet, all matches | **50.1%** — a coin flip (227,495 matches, time-split) |
| Two-way coverage (lowest + 2nd-lowest odds) | **77.7%** (+27.6pp, train/test identical) |
| Weak consensus (skew < 150%) favourite hit rate | **36–43%** ⇒ draw must be listed as co-primary |
| Deep favourite + tight book spread (<2%) | **80.0% / 81.5%** (train/test) |
| Over/Under signal strength tiers | strong **65.0%** / medium 57.0% / weak 54.8% (≈random) |
| Magnitude: 4+ goals frequency | **44.4%** of matches (vs 2.0% in naive main anchors) |
| UCL main-competition goals | **3.37 / O2.5 64.5%** vs big-5 baseline 2.69 / 50.4% (calibration **+0.67 goals**) |
| In-house replay archive (346 reviewed · **not distributed**) | direction **≈73%** (any-coverage) · scoreline **≈27%** (main **or** secondary anchor) · perfect **≈18%** |

> ⚠️ These are **methodology-validation** numbers, not profit claims. See [DISCLAIMER.md](DISCLAIMER.md).

## Quick Start

```bash
git clone https://github.com/MENG-COOLMAN/PitchQuant.git
cd PitchQuant
pip install -r requirements.txt          # requests · numpy · scipy · pyyaml

cp .env.example .env                     # then fill YOUR OWN keys
#   ODDS_API_KEY       → odds-api.io      (European prices · primary source)
#   THE_ODDS_API_KEY   → the-odds-api.com (21–40 books · cross-book divergence)
#   BZZOIRO_KEY        → bzzoiro.com      (structured injuries / squads / form)
#   ZHIPU_API_KEY      → bigmodel.cn      (optional: screenshot → odds text)

# 1) deterministic core only
python scripts/tmp/calc_poisson.py --home 2.50 --draw 3.40 --away 2.80 --o25 1.90 --u25 1.85 --top 5
#    Expected: λh/λa + direction % + score Top-5 table

# 2) full single-match pipeline
python scripts/tmp/pipeline.py examples/sample-odds.txt \
    --teams "Home Team,Away Team" --league seriea --kickoff "2026-11-15 03:45"

# 3) OPTIONAL: workspace consistency self-check (maintainers only)
#    NOTE: check_sync.py validates the ORIGINAL authoring workspace
#    (.reasonix/skills + AGENTS.md + data/足球分析模型.txt must stay in sync).
#    It is expected to FAIL in this release layout — see "Cross-agent usage" below.
```

**Input**: Chinese Sports Lottery odds text (1X2 / handicap / total goals / HT-FT / correct score, with per-timestamp series).
`pipeline.py` also accepts **screenshots** (auto OCR → standard text).

> ⚠️ **All three market parameters are required** (`--eu` / `--o25` / `--handi`). Omit them and ~20 blocks degrade to tri-state — that is *expected behaviour*, not a failure.

**Two traps that silently corrupt everything**:
- `--eu` must be the **real European market**, never the Chinese lottery's last price (it would make cross-market divergence identically 0 — a *fake consensus*).
- `--handi` must be the **European balanced line**, not the lottery's fixed ±1 (otherwise net-margin band, water-level reading and the receiving-handicap anchor ban are all wrong).

## Project Structure

```
AGENTS.md / prompts/             workflow specification (analyze · self-check · audit · model health)
skills/                          37 domain skills (rules, league sub-models, audit, maintenance)
scripts/tmp/                     129 deterministic scripts (core pipeline + audits + market matrix)
scripts/online_learning/         21 learning-layer scripts (gated · L1 rejected)
scripts/backtest/                53 backtest & verification scripts
tables/                          20 distilled lookup tables (league / goals / score depth / water / draw …)
data/                            compatibility layer — clone & run, no path rewriting
templates/                       analysis template
docs/                            architecture · methodology · getting-started · data-and-apis
examples/                        odds-format sample only (no case records)
.github/workflows/ci.yml         syntax compile · table integrity · secret-leak scan
```

## Data Notice

This repository ships **the model only** — rules, algorithms, distilled tables, docs.
`Matches.csv` (227k matches), European historical databases, and the **entire case library** (templates · raw archives · replay records — private research data) have been **removed**.
All API keys, cookies, snapshots and personal paths have been **removed** — you must supply your own keys in `.env`.

## Disclaimer

For **academic & educational use only**. Gambling/betting use is **prohibited**. No warranty. Full terms: [DISCLAIMER.md](DISCLAIMER.md).

## Scope & Limitations

- **Single-match variance is irreducible**: total-goals σ ≈ 1.6, so even a perfectly calibrated expectation misses by ≥1 goal in ~26% of matches.
- **Scoreline prediction is a coverage problem, not a point-prediction problem** — a 5.3% event cannot be "predicted", only *covered* by a pool.
- **Some layers are explicitly un-backtested** (wide-pool bin injection, some weighting coefficients) — they are tagged `⏳ pending backtest` in-code rather than presented as validated.
- **Out-of-domain competitions** (cups, minor leagues) have **no** domain table; thresholds are tri-state tagged and excluded from ranking.
## Cross-agent usage (non-Reasonix hosts)

**Short answer: the model itself is host-agnostic; the workspace shell is not.**

| Layer | Portable? | Why |
|:--|:--|:--|
| `scripts/tmp/*.py` (129) | ✅ **Yes** (verified) | Pure CLI; `sys.path` derived from `__file__`. Ran end-to-end from a clean clone: `calc_all.py examples/sample-odds.txt seriea` → exit 0, 253 lines |
| `tables/*.json` (20) | ✅ Yes | Plain JSON, no host coupling |
| `skills/*/SKILL.md` (37) + `prompts/*.md` (5) | ✅ Content yes | Markdown + frontmatter (`name` / `description` only) |
| `AGENTS.md` wording | ⚠️ Rewrite verbs | Contains host verbs: `read_skill` ×4, `调 /SK-*` ×6, `调 /SL-*` ×2 — map them to "read this file" |
| `check_sync.py` / `scripts/audit_*` | ❌ No (by design) | They validate the **original authoring workspace**: `.reasonix/skills` (79 refs) + `AGENTS.md` ↔ `data/足球分析模型.txt` triple-sync + 15 lines with an authoring-only absolute path |

**To run under Cursor / Claude Code / Codex / Copilot (any agent with file-read + shell):**

1. Point the agent at **`prompts/01-analyze-a-match.md`** (workflow) and `AGENTS.md` (rules) as system context; replace `调 /SK-xxx` with "read `skills/SK-xxx/SKILL.md`";
2. Let the agent call **`scripts/tmp/pipeline.py`** (or `calc_all.py`) — all determinism lives there;
3. Skip the `check_sync.py` / `audit_*` layer unless you recreate the authoring layout.

> Verified: Windows / Python 3.14 / clean clone — `calc_poisson.py` prints λh/λa + Top-3 correctly; `calc_all.py` on the sample odds → **exit 0 / 253 lines / 62 s** (network sources degrade to tri-state without keys; local math is unaffected).

---


---

# 🇨🇳 中文

## PitchQuant 是什么？

大多数 "AI 预测" 项目把 LLM 当 **预言机**：喂数据、要答案、信黑箱。

**PitchQuant 反过来做** —— 它把 LLM 当 **运行时**：一个按锁定流程执行的执行器，所有确定性计算交给可审计的 Python 脚本，所有判断都绑定到可机器校验的证据上。

```
传统做法:  数据 ──▶ LLM ──▶ "预测"            （黑箱 · 不可复现）
PitchQuant: 数据 ──▶ 脚本(数学) ──▶ 清单 ──▶ LLM(判断) ──▶ 七道闸门(1160 校验) ──▶ 存档
                      ▲ 确定性              ▲ 受约束          ▲ 强制
```

它交付的不是更好的水晶球，而是一套**允许自我否证**的分析系统：

- **在线 ML 层被正式否决**（`rejected_leak`）—— 其 +0.68pp 增益经查是**标签泄露**（26 个特征里 17 个是赛后统计），只用赛前特征时增益仅 **+0.01pp**；
- **「五源 λ 加权」被废弃** —— 实测五源两两相关 **r = 0.97~0.99**（等于把同一个数平均五次）；
- **按概率排序比分被替换** —— 已证明它结构性地锚定低比分。

系统能**否证自己的组件**，这才是这里的工程主张。

### 📟 实际输出长什么样

```
$ python scripts/tmp/calc_all.py examples/sample-odds.txt 意甲 \
    --eu 2.10,3.40,3.60 --o25 1.91 --u25 1.95 --handi -1 --net

🔴 分析时间: 2026-11-15 14:32:07 (北京) ｜ 本场状态: 距开赛 743 分钟
去水(欧盘) 主 42.3% / 平 26.1% / 客 31.6%   ｜ skew 162% → 高共识·禁单押
🔴P52 超大球分级: L3（均衡线 3.14 · 宽池必含 1/2/3/4/5/7 球）
量级分布(矩阵+查表尾部): 众数 3 球 ｜ P(≥4球) 37.2% ｜ 尾部档 0/1/2/3/4/5/6
市场三源矩阵(P10): OU 22 档 · AH 16 档 · CS 24 档 → E[T]=3.19 · E[M]=-0.42
让球水位(P1): 上盘覆盖 53.2%（中）→ 净胜档上移 → 支持穿盘
比分池(信号支持度): 1) 1:2 0.87   2) 1:3 0.81   3) 0:2 0.74   4) 2:2 0.68 …
🔴锚-市场/期望复校验(N07b/N18b): ✅ 通过（可落盘）
```

*真实输出（已截断）—— 确定性内核意味着同输入必得同数字。*

## 核心理念：把 LLM 当运行时，而不是预言机

| 维度 | LLM 当预言机（常见） | **PitchQuant（LLM 当运行时）** |
|:--|:--|:--|
| 谁计算 | LLM 自己（概率、算术） | **脚本** —— 去水 / 泊松 / 查表 / 市场矩阵 |
| 谁判断 | LLM 自由判断 | LLM **受**生成式清单 + **四级优先级体系**约束 |
| 可复现性 | 不确定 | **确定性内核** —— 同输入必得同数字 |
| 可审计性 | 无 | **每场都存档**（八节）+ 四层审计留痕 |
| 失效方式 | 静默幻觉 | **闸门失败**（1160 条断言 · 七道交付闸门） |
| 自我纠错 | 罕见 | **内建否证门禁**（回测 + 显著性 + 回滚） |

### 🧰 技术栈与关键词

| 领域 | 技术 / 关键词 |
|:--|:--|
| **统计** | **泊松分布** · **Dixon-Coles** 低比分修正（ρ=−0.12）· **去水**（等比例 + 校准表）· **凯利** · **时间分割回测** · 概率校准曲线 · **分位数自适应量级带** |
| **盘口** | **亚盘**（全档盘口 + 水位）· 大小球**全档** · **波胆矩阵** · BTTS · 单队进球 · 半全场 · **赔率形态学** · **跨机构分歧**（21–40 家）· **IPF 市场矩阵**（OU × AH × CS） |
| **工程** | 确定性 Python 内核 · **LLM 编排** · 脚本生成清单 · **1160 条一致性断言** · 防过拟合门禁 · 三态证据标注 · 可复现存档 · **子模型作用域强隔离**（`ScopeViolation`） |
| **数据源** | odds-api（欧盘）· **the-odds-api**（21–40 家 · 跨机构分歧）· **Bzzoiro**（结构化伤停 / 名单 / 近况）· ClubElo（ELO）· Understat（xG）· 中国竞彩公开赔率 · **智谱 GLM**（截图 → 赔率文本） |

> ⚠️ `api-football` 已于 2026-10 **停用并从数据链中剔除**（替代：the-odds-api 供赔率、Bzzoiro 供伤停、Odds-API 供赛事定位）。

## 核心优势（为什么值得一读）

1. **📉 市场优先有据可依** —— 22.7 万场回测显示去水市场是校准最好的信号（±5pp，且系统性低估热门 +2~+4pp）。市场拿最大权重；**五源 λ 加权**实测两两相关 **r=0.97~0.99** → 改为「取最可靠的一条分布，其余仅作冲突校验」。
2. **🧱 任何权重都不得覆盖的硬约束（L0）** —— ①受让场禁设主胜比分锚 ②单押须**同时**满足 skew ≥200% 且最低赔 <1.30，否则**强制两向覆盖** ③锚须匹配市场期望进球（|总进球−E| ≤1.0，且至少一锚落在 E±1.0）④深盘须穿盘 ⑤永不反转 L2 硬核方向。
3. **🧭 四级判定优先级（L0 > L1 > L2 > L3）** —— 硬约束 ▸ 本场市场全档 ▸ 域内回测档表 ▸ 无回测经验权重（仅平手时 tie-break，≤2pp）。**超域赛事**（杯赛 / 小联赛）L2 三态标注、**不参与排序**。
4. **🕸️ 上下文 → 子模型 → 聚合（V3.5.94）** —— `MatchContext` 是一场唯一上下文；7 个子模型适配器返回统一 `SubModelResult`；`aggregate()` 合并时施加 **L2 锁**（子模型只降档、永不反转方向）。越界读表**在代码层直接抛 `ScopeViolation`**，不靠文档纪律。
5. **🎲 反机械锚定** —— 比分不按概率排序（那会结构性锚死 1:1）。候选池**不淘汰**，按**市场信号支持度**排序（期望进球匹配 / 大小球方向 / 让球深度 / 零封-BTTS 直盘 / **波胆市场排名**），选择链**零概率项**。
6. **📊 量级是分布，不是点** —— 「均值 ± 固定带宽」曾削掉 36% 的厚尾（真实 4+ 球占 44%，主锚却 98% 落在 2 球）。现在：完整分布 `pT[0..7]` → 分位数自适应区间 → **密度比权重**（永不排除，下限 0.35）→ `P(k) ≥ 5%` 的尾部档**必进宽池**。
7. **🛡️ 防过拟合四道门禁** —— 任何新特征/新权重/"学习成果"必须通过 ①时间分割回测 **p<0.05** ②样本量门槛 ③滚动 20 场偏差 >10pp 自动回滚 ④越界裁剪。**无证据即无判定权**。
8. **🧾 证据绑定的自检** —— 「**没有数值 = 没做**」。每项必须三态标注（`触发(值)` / `不触发(原因)` / `无数据(原因)`）。并且审计层能抓出**「算了没写」**，甚至**「写了但判断错」**。
9. **🧠 37 个领域知识模块** —— 裁判规则（`rule51–70`）、五大联赛子模型（各 8,700–9,300 场蒸馏）、**欧国联子模型**（658 场 / 四届）、欧战两回合逻辑、欧冠校准、312 队攻防档案。知识是**版本化、可审计的文件**，不是提示词里的感觉。
10. **📚 可否证的档案** —— 项目内部维护复盘档案（346 场）专用于否证自己的规则；**原始记录属私人研究数据，不随仓库分发**。

## 架构详解

### 上下文 → 子模型 → 聚合

```
                    ┌──────────────────────────────────────────┐
   ① 上下文        │  match_context.MatchContext              │
                    │  一场比赛的唯一上下文                     │
                    └───────────────┬──────────────────────────┘
                                    │  只读 ctx · 禁读全局文件
        ┌───────────────┬───────────┼───────────┬───────────────┐
        ▼               ▼           ▼           ▼               ▼
   ② 子模型       top5_epl     nations     europe      none(三态)
   7 个 adapter   laliga/bundesliga/seriea/ligue1
        │
        │  统一契约 SubModelResult:
        │  applicable / reason / dir_adj / conf_adj / goals_adj /
        │  anchor_hints / rules_hit / warnings / scope_blocked
        ▼
   ③ 聚合         aggregate(): L2 硬核 > 子模型 > L3 变动层
                  + L2 锁（只降档 · 永不反转）
                  + ScopeViolation（代码级表白名单）
```

### 完整管线（Step 0 → 11）

| 阶段 | 内容 |
|:--|:--|
| **PreStep**（可选） | 时间窗内双轨打分（方向分 + 比分分）→ 只保留强信号场次 |
| **Step 0** | 数据获取（11 类源 · 三态标注） |
| **Step 1** | [L2] 硬核层 12 项（统一欧盘口径） |
| **Step 2** | 变动层 V1–V6：双源变动 · 诱阻四步 · 精算交叉 · 水位联动 · 跨市场分歧 · 盘口联动 |
| **Step 3** | 场景规则 44/45/46（欧战触发 `rule51–70` 六项核查表） |
| **Step 4** | 推论层：基本面 ABCDE 交叉验证 |
| **Step 4.5 / 4.6 / 4.8** | 联赛子模型 · 主客场因子层（HAF）· 欧国联子模型 |
| **Step 5** | 方向（计算结果定方向 → 赔率对照 → 覆盖纪律） |
| **Step 6 / 6.5** | 大球深度 · 量级（P52 六级）· 大小球水位精读（六源） |
| **Step 7 / 7.5** | 比分锚定（市场三源矩阵 → 信号支持度池）· 半场精细反推 |
| **Step 8 / 9 / 10** | 总进球 · 22 项自检 · 落盘（八节 + 15 列 CSV） |
| **Step 11** | 批末压缩 / 投注方案模块（用户触发） |

### 得分锚定：为什么不用「概率 Top1」

足球比分概率**天然低分偏置**（0:0 / 1:0 / 1:1 / 2:0 永远排前面），按概率取 Top 必然锚小球 —— 与「期望 3.0 球 + 大球盘」直接冲突。

现行方案：
1. **候选池不淘汰**（宽池必含档由 P52 六级决定，如 L4 必含 4/5/6 球）；
2. **按市场信号支持度排序**，五项：期望进球匹配 / 大小球方向 / 让球深度 / 零封-双方进球（Team Total 直盘）/ 波胆市场排名；
3. **整条选择链零概率项**（矩阵概率只用于边缘 E[T]、E[M] 校验，不参与排序）；
4. 输出**比分池 + 逐项依据**，而非只给一个数字。

### 七道交付闸门

```
[1/7] 无残留待填          [2/7] output_checker
[3/7] check_luopan         [4/7] audit_steps（数据层 · 20 步）
[5/7] audit_judgment（算了没写）  [6/7] audit_chain（8 条传导链）
[7/7] audit_semantic（calc 值 vs raw 声明）+ audit_consumption + audit_matrix（38 步 · 盲区 0）
```

## 回测证据

| 结论 | 数值 |
|:--|:--|
| 市场校准（热门） | 隐含 70%+ ⇒ 实际 **80.6%**（系统性低估 +2~+4.4pp） |
| 单押最低赔率（全样本） | **50.1%** —— 等于抛硬币（227,495 场 · 时间分割） |
| 两向覆盖（最低 + 次低赔） | **77.7%**（+27.6pp · train/test 完全一致） |
| 弱共识（skew <150%）热门命中 | **36–43%** ⇒ 平局必须并列 |
| 深盘 + 机构分歧 <2% | **80.0% / 81.5%**（train/test） |
| 大小球信号三档 | 强 **65.0%** / 中 57.0% / 弱 54.8%（≈随机） |
| 量级：真实 4+ 球占比 | **44.4%**（而朴素主锚仅 2.0%） |
| 欧冠正赛进球 | **3.37 球 / O2.5 64.5%**（五大基线 2.69 / 50.4% → 校准 **+0.67 球**） |
| 内部复盘档案（346 场·**不随仓库分发**） | 方向 **≈73%**（两向覆盖口径）· 比分 **≈27%**（主锚**或**次锚）· 完美 **≈18%** |

> ⚠️ 这些是**方法论验证**数字，不是盈利承诺。详见 [DISCLAIMER.md](DISCLAIMER.md)。

## 快速开始（每一步）

```bash
git clone https://github.com/MENG-COOLMAN/PitchQuant.git
cd PitchQuant
pip install -r requirements.txt          # requests · numpy · scipy · pyyaml

cp .env.example .env                     # 然后填入你自己的 key
#   ODDS_API_KEY       → odds-api.io      （欧盘 · 主数据源）
#   THE_ODDS_API_KEY   → the-odds-api.com （21–40 家 · 跨机构分歧）
#   BZZOIRO_KEY        → bzzoiro.com      （结构化伤停 / 名单 / 近况）
#   ZHIPU_API_KEY      → bigmodel.cn      （可选：截图 → 赔率文本）

# ① 只跑确定性内核
python scripts/tmp/calc_poisson.py --home 2.50 --draw 3.40 --away 2.80 --o25 1.90 --u25 1.85 --top 5
#    预期输出: λh/λa + 方向概率 + 比分 Top5 表

# ② 单场全流程
python scripts/tmp/pipeline.py examples/sample-odds.txt \
    --teams "主队,客队" --league seriea --kickoff "2026-11-15 03:45"

# ③ （可选 · 仅维护者）工作区一致性自检
#    注意: check_sync.py 校验的是「原始创作工作区」
#    （.reasonix/skills + AGENTS.md + data/足球分析模型.txt 三处同步）
#    在本发布版布局下它会**预期失败** —— 详见下方「跨 agent 兼容性」
```

**输入**：竞彩赔率文本（胜平负 / 让球 / 总进球 / 半全场 / 比分，含逐时点序列）。
`pipeline.py` 也接受**截图**（自动 OCR → 标准文本）。

> ⚠️ **三个市场参数必须给全**（`--eu` / `--o25` / `--handi`）。缺了会有约 20 个块退化为三态 —— 这是**预期行为**，不是模型坏了。

**两个会静默污染全部结论的陷阱**：
- `--eu` 必须是**真实欧盘**，禁用竞彩末盘冒充（会让跨市场分歧恒为 0 —— **假一致**）；
- `--handi` 必须是**欧盘均衡线**，不是竞彩固定 ±1（否则净胜档 / 让球水位 / 受让禁锚判断全部失真）。

## 目录结构

```
AGENTS.md / prompts/            流程规范（分析 · 自检 · 审计 · 模型体检）
skills/                         37 个领域技能（规则 / 联赛子模型 / 审计 / 维护）
scripts/tmp/                    129 个确定性脚本（核心流水线 + 审计 + 市场矩阵）
scripts/online_learning/        21 个学习层脚本（受门禁控制 · L1 已否决）
scripts/backtest/               53 个回测与验证脚本
tables/                         20 张蒸馏查表（联赛 / 进球档 / 比分深度 / 水位 / 平局 …）
data/                           兼容层 —— clone 即跑，无需改路径
templates/                      分析模板
docs/                           架构 · 方法论 · 快速开始 · 数据与 API
examples/                       仅赔率格式样例（不含案例记录）
.github/workflows/ci.yml        语法编译 · 表完整性 · 密钥残留扫描
```

## 数据说明

本仓库**只发布模型本体** —— 规则 · 算法 · 蒸馏表 · 文档。
`Matches.csv`（22.7 万场）、欧战历史库，以及**整个案例库**（模板 · raw 存档 · 复盘记录 —— 私人研究数据）均已**移除**。
所有 API Key、Cookie、快照与个人路径均已**移除** —— 你需要在 `.env` 里自备密钥。

## 免责声明

**仅用于学术交流与技术学习**。**严禁用于博彩/投注**。无任何保证。完整条款见 [DISCLAIMER.md](DISCLAIMER.md)。

## 适用范围与限制

- **单场方差不可消除**：总进球 σ≈1.6，即使期望完全校准，也有约 26% 的场次偏离 ≥1 球。
- **比分预测是覆盖问题，不是点预测问题** —— 5.3% 的事件不可能"预测"，只能被候选池**覆盖**。
- **部分层明确未回测**（宽池必含档补入、若干权重系数）—— 代码里标 `⏳ 待回测`，不冒充已验证。
- **超域赛事**（杯赛 / 小联赛）**没有**本域档表；阈值一律三态标注并**排除在排序之外**。

## 跨 agent 兼容性（非 Reasonix 宿主）

**一句话：模型本体与宿主无关，工作区外壳不是。**

| 层 | 可移植？ | 原因 |
|:--|:--|:--|
| `scripts/tmp/*.py`（129） | ✅ **可以**（实测） | 纯 CLI；`sys.path` 取自 `__file__`。**干净 clone 实测跑通**：`calc_all.py examples/sample-odds.txt seriea` → exit 0 / 253 行 |
| `tables/*.json`（20） | ✅ 可以 | 纯 JSON，无宿主耦合 |
| `skills/*/SKILL.md`（37）+ `prompts/*.md`（5） | ✅ 内容可以 | Markdown + frontmatter（只有 `name` / `description`） |
| `AGENTS.md` 措辞 | ⚠️ 需替换 | 含宿主动词：`read_skill` ×4、`调 /SK-*` ×6、`调 /SL-*` ×2 → 理解为「读这个文件」即可 |
| `check_sync.py` / `scripts/audit_*` | ❌ 不可用（设计使然） | 它们校验的是**原始创作工作区**：`.reasonix/skills`（79 处引用）+ `AGENTS.md` 与 `data/足球分析模型.txt` 三处同步 + 15 行仅作者可用的绝对路径 |

**换到 Cursor / Claude Code / Codex / Copilot（任何能读文件 + 执行命令的 agent）：**

1. 把 **`prompts/01-analyze-a-match.md`**（流程）与 `AGENTS.md`（规则）作为系统上下文；把「调 /SK-xxx」理解为「读 `skills/SK-xxx/SKILL.md`」；
2. 让 agent 调用 **`scripts/tmp/pipeline.py`**（或 `calc_all.py`）—— 所有确定性计算都在这里；
3. `check_sync.py` / `audit_*` 层可跳过（除非你重建原工作区布局）。

> 实测环境：Windows / Python 3.14 / 干净 clone —— `calc_poisson.py` 正常输出 λh/λa + Top3；`calc_all.py` 跑示例赔率 → **exit 0 / 253 行 / 62 秒**（无 key 时网络源三态降级，不阻断本地计算）。

---

---

## 📚 Further Reading · 延伸阅读

| Document | 内容 / What's inside |
|:--|:--|
| 🔴 **[`prompts/`](prompts/README.md)** | **Prompt 规范集**——分析执行 / 自查补充 / 独立审计 / 模型体检（四件套闭环）<br>Prompt specification set — analyze · self-check · audit · model health |
| [`docs/getting-started.md`](docs/getting-started.md) | 操作手册——输入格式 / 参数解读 / 输出解读 / FAQ / 故障排查<br>Hands-on walkthrough — input format, CLI flags, reading the output, FAQ |
| 🔴 **[`docs/data-and-apis.md`](docs/data-and-apis.md)** | **数据与 API 清单**——你必须自备什么 / 哪些 API / 免费额度 / 降级行为<br>Required data & APIs — what you must provide, free tiers, graceful degradation |
| [`docs/architecture.md`](docs/architecture.md) | 架构与规则优先级——分层结构 / 子模型隔离 / 判定优先级体系 / 七道质量门<br>Architecture & priorities — layers, sub-model isolation, priority hierarchy, seven gates |
| [`docs/methodology.md`](docs/methodology.md) | 方法论——关键回测结论 + 数学公式 + 复现步骤<br>Methodology — backtest findings, formulas, reproduction steps |
| [`examples/`](examples/) | 赔率输入格式样例（不含任何真实案例记录）<br>Odds input format sample only — no case records |
| **[`DISCLAIMER.md`](DISCLAIMER.md)** | ⚠️ **法律免责声明**——学术用途 / 禁止博彩 / 无保证 / 责任限制<br>Legal disclaimer — academic use only, prohibitions, limitation of liability |
| **[`NOTICE.md`](NOTICE.md)** | 第三方商标与数据来源归属<br>Third-party trademarks & data attribution |
| **[`CHANGELOG.md`](CHANGELOG.md)** | 更新日志（版本变更与维护记录）<br>Changelog — release history & maintenance log |
| **[`CONTRIBUTING.md`](CONTRIBUTING.md)** | 贡献指南（代码约定 / 法律前提）<br>Contributing guide — code conventions & legal prerequisites |

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
