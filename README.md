<div align="center">

# ⚽ PitchQuant
### 足球赔率分析模型 · V3.5.74

**Pitch**（绿茵场）× **Quant**（量化）—— 用量化研究的方式对待足球数据，但始终记得：**足球是混沌的，市场是高效的**。

**LLM as runtime · Backtests as discipline**
**把 LLM 当运行时 · 把回测当纪律**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Skills](https://img.shields.io/badge/Skills-34-green)
![Scripts](https://img.shields.io/badge/Scripts-139-yellow)
![Checks](https://img.shields.io/badge/Auto--Checks-238-orange)
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

## What is this?

Not a "prediction oracle" — an **auditable analysis pipeline**. It organizes domain knowledge, deterministic computation, and strict self-checking into a workflow that an LLM executes step by step.

| Layer | Size | What it is |
|:--|:--|:--|
| **Rule system** | 12 + 5 + 26 items | Derived from large-sample backtests (227k matches / 1,174 European fixtures) |
| **Skills** | 34 × `SKILL.md` | Domain knowledge, referee rules, 5 league sub-models, audit & maintenance discipline |
| **Scripts** | 139 × Python | Deterministic math: de-vigging, Kelly, Poisson, score lookups, live fusion engine… |
| **Quality gate** | **238 auto-checks** | `check_sync` — any rule/doc/data drift fails immediately |

## Why it's interesting

1. **Market-first** — 227k-match backtest shows the de-vigged market is the best-calibrated signal (±5pp); it gets the largest weight (0.30) in the live engine.
2. **Weak-consensus rule** — when market skew <150%, the favourite hits only 36–43% (≈ coin flip) → the draw **must** be listed as a co-primary outcome.
3. **Anchor consistency** — score anchors are machine-checked against market handicap / O-U direction / Asian line; contradictions raise warnings and suggest a corrected anchor.
4. **Anti-overfitting gates** — any "learning" must pass time-split backtest + p<0.05 + sample thresholds, or it is demoted to "display only".
5. **Three-layer data-chain risk policy** — changes are classified as ① input/parsing (dangerous) ② data tables (dangerous) ③ display/audit (safe). New annotations may only go into layer ③.
6. **Evidence-bound self-check** — "no number = not done". Every claim carries a value; inapplicable conditions must be explicitly marked.

## Architecture

```
┌───────────────────────────────────────────────────────┐
│ Runtime  : LLM executing AGENTS.md pipeline (no ad-hoc steps) │
├───────────────────────────────────────────────────────┤
│ Knowledge: 34 × SKILL.md      (rules / referees / leagues)    │
│ Compute  : 139 × Python       (deterministic — LLM only judges)│
│ Data     : distilled JSON     (backtest artifacts, lookup-only)│
├───────────────────────────────────────────────────────┤
│ Gates    : check_sync 238 + output_checker 35 + check_luopan  │
└───────────────────────────────────────────────────────┘
```

Pipeline: **PreStep** → Data acquisition → Hardcore (12) → Movement (V1-V6) → Scenarios → Inferences (26) → League sub-model → Home/Away factor → **Direction** → **Goals depth** → **Score spectrum** → Totals → Self-check → Archive → (Compression / bet plan).

## Quick Start

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
python scripts/tmp/check_sync.py      # 238 checks
python scripts/tmp/output_checker.py <your-analysis.txt>   # 35 required blocks
```

## Data Notice

| Data | Included? | Why |
|:--|:--|:--|
| `tables/*.json` (distilled) | ✅ | Our backtest artifacts — free to use |
| Raw 227k-match CSV / SQL / European DB | ❌ | Size + source terms |
| API keys | ❌ never | Env vars only |

## Disclaimer

Research/engineering use only. Long-term EV is negative. Comply with local laws and data-source ToS.

---

# 🇨🇳 中文

## 这是什么？

不是"预测神器"，而是一套**可审计的分析流水线**——把领域知识、确定性计算与严格自检组织成一条由 LLM 逐步执行的工作流。

| 层 | 规模 | 是什么 |
|:--|:--|:--|
| **规则体系** | 硬核 12 + 变动 5 + 推论 26 | 全部来自大样本回测（22.7 万场 / 欧战 1174 场） |
| **Skills** | 34 × `SKILL.md` | 领域知识、裁判规则、五大联赛子模型、审计与维护纪律 |
| **脚本** | 139 × Python | 确定性计算：去水 / 凯利 / 泊松 / 比分查表 / 现场融合引擎… |
| **质量门** | **238 条自动校验** | `check_sync` —— 规则/文档/数据漂移立即报错 |

## 核心亮点（为什么值得一读）

1. **市场源优先** —— 22.7 万场回测证实：欧赔去水是校准最好的信号（±5pp 内）→ 在实时引擎中占最大权重（0.30）。
2. **弱共识铁律** —— 市场分歧度 skew <150% 时，热门方向命中仅 36–43%（≈抛硬币）→ **平局必须与首选并列**，禁单押。
3. **锚定一致性机器校验** —— 比分锚须与市场净胜档 / 大小球方向 / 亚盘方向一致；矛盾即告警并给出建议锚（禁机械照搬 Top1）。
4. **防过拟合门禁** —— 任何"学习成果进入判定"必须通过时间分割回测 + p<0.05 + 样本量门槛；不达标一律降级为"仅展示"。
5. **数据链三层风险纪律** —— 改动分①输入解析（高危）②数据表（高危）③展示留痕（安全区）；**新增标注只允许放第③层**。
6. **证据绑定自检** —— "无数字 = 未执行"：每条判定附数值；条件不适用必须显式三态标注（触发/不触发原因/无数据原因）。

## 架构

```
┌───────────────────────────────────────────────────────┐
│ 运行层: LLM 按 AGENTS.md 流程编排（不自创步骤）           │
├───────────────────────────────────────────────────────┤
│ 知识层: 34 × SKILL.md     （规则 / 裁判 / 联赛子模型）    │
│ 计算层: 139 × Python      （确定性·脚本算·LLM 只判断）    │
│ 数据层: 蒸馏表 JSON        （回测产物·查表禁凭记忆）       │
├───────────────────────────────────────────────────────┤
│ 校验层: check_sync 238 + output_checker 35 + check_luopan │
└───────────────────────────────────────────────────────┘
```

流程：**PreStep** → 数据获取 → 硬核层(12) → 变动层(V1-V6) → 场景 → 推论层(26) → 联赛子模型 → 主客场因子 → **方向判定** → **大小球深度** → **比分谱系** → 总进球 → 自检 → 落盘 →（批末压缩 / 投注方案）

## 快速开始（每一步）

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

**第 6 步 · 验证环境完整**
```bash
python scripts/tmp/check_sync.py                          # 238 条一致性校验
python scripts/tmp/output_checker.py <你的分析输出.txt>     # 35 个必填块校验
```

## 数据说明

| 数据 | 是否包含 | 原因 |
|:--|:--|:--|
| `tables/*.json`（蒸馏表） | ✅ 已包含 | 本项目回测产物，可自由使用 |
| 22.7 万场原始 CSV / SQL / 欧战库 | ❌ 未包含 | 体积 + 数据来源条款 |
| API keys | ❌ 绝不含 | 一律走环境变量 |
| **竞彩赔率（输入数据）** | — | 取自 **中国体育彩票官方网站**（<https://www.lottery.gov.cn/jc/index.html>）**每日公开数据**（使用者自行抄录 · 本项目不内置）· 详见 [DISCLAIMER.md](DISCLAIMER.md) §4.5 |

## 免责声明

仅供研究与工程学习。长期串关 EV 为负。请遵守当地法律法规与数据源服务条款。

---

## 📚 Further Reading · 延伸阅读

| Doc | 内容 |
|:--|:--|
| [`docs/data-and-apis.md`](docs/data-and-apis.md) | 🔴 **数据与 API 清单**（你必须自备什么 / 哪些 API / 免费额度）· Required data & APIs |
| [`docs/getting-started.md`](docs/getting-started.md) | 详细操作手册（含输出解读与常见问题）· Detailed walkthrough |
| [`docs/architecture.md`](docs/architecture.md) | 架构与规则优先级 · Architecture & rule priorities |
| [`docs/methodology.md`](docs/methodology.md) | 关键回测结论 · Key backtest findings |
| [`examples/`](examples/) | 脱敏完整案例（含误判复盘）· Anonymized real case |
| **[`DISCLAIMER.md`](DISCLAIMER.md)** | ⚠️ **法律免责声明**（学术用途 / 禁止博彩 / 无保证 / 责任限制 / 合规责任）· Legal disclaimer |
| **[`NOTICE.md`](NOTICE.md)** | 第三方商标与数据来源归属 · Third-party trademark & data attribution |

**License**: MIT · Contributions & issues welcome · 欢迎 Issue 与 PR
