# ⚠️ 免责声明与使用限制 · DISCLAIMER & TERMS OF USE

> 中英双语 · 最后更新：2026-09-19 · 适用于本仓库全部内容（代码/文档/数据表/示例）
> Bilingual · Last updated: 2026-09-19 · Applies to all repository content

---

## 🔴 一句话摘要 / TL;DR

**本项目是计算机科学与统计学的技术研究项目，仅用于学术交流与技术学习。它不是博彩工具，不构成任何投注建议，也不得被用于任何形式的赌博或博彩决策。**
**This is a technical research project for academic exchange only. It is NOT a betting tool, provides NO betting advice, and must NOT be used for gambling or wagering decisions of any kind.**

---

# 中文版

## 第 1 条 · 项目性质

1.1 本项目（含全部代码、文档、数据表、示例）为**个人技术研究项目**，研究主题为：
- 大语言模型（LLM）作为运行时的工作流编排；
- 统计学与概率模型在体育数据上的工程实践；
- 软件工程质量保障机制（自动化校验、防过拟合门禁等）。

1.2 本项目的**唯一目的**是**学术交流与技术学习**，包括但不限于：阅读源码、研究方法论、复现统计回测、借鉴工程实践。

1.3 本项目**不是**、也不得被理解为：
- 博彩工具、投注辅助软件、赔率预测服务；
- 任何形式的投资建议、财务建议或收益承诺；
- 对任何赛事结果的保证性预测。

## 第 2 条 · 明示禁止用途

**禁止**将本项目及其任何部分（代码、输出、数据、结论）用于：

2.1 任何形式的**赌博、博彩、投注、下注**行为或为其提供决策依据；
2.2 面向他人的**博彩推荐、付费荐彩、代购彩票**等任何经营性活动；
2.3 向**未成年人**传播或提供；
2.4 任何违反使用者所在地法律法规的用途；
2.5 声称本项目"可预测比赛结果""可稳定盈利"等误导性宣传。

**使用者的使用行为即视为同意本条款。**

## 第 3 条 · 无任何保证

3.1 本项目按 **"现状"（AS IS）** 提供，不附带任何明示或默示的保证，包括但不限于：准确性、完整性、时效性、适销性、特定用途适用性、不侵权。

3.2 **作者实测结论（诚实披露）**：竞彩串关的**长期期望值为负数**（EV < 0）——这是体育博彩的结构性特征（返奖率 < 100%），与任何模型无关。本项目**不会改变这一事实**。

3.3 本项目的历史回测数据（如准确率、命中率）**仅用于方法论验证**：
- 回测 ≠ 未来表现；
- 历史统计规律可能失效（市场结构会变化）；
- 任何逆推"因为回测 70%，所以未来会 70%"的推断都是**错误的**。

## 第 4 条 · 数据与第三方权利

4.1 本仓库**不包含**任何原始赔率数据库、博彩公司数据或第三方版权数据。`tables/` 目录中的 JSON 文件均为本项目**基于公开数据自行回测计算的衍生结果**。

4.2 文档中提及的一切第三方名称——包括但不限于赔率数据商、博彩公司（如 1xbet、Bet365 等）、数据服务（如 api-football、Odds-API、Understat、ClubElo、football-data 等）——**均为其各自所有者的商标或注册商标**。

4.3 本项目的使用、提及**不构成**与上述第三方的任何**关联、赞助、背书或合作**关系。

4.4 使用者若接入任何第三方数据源或 API，**须自行**：
- 阅读并遵守该服务的**服务条款（ToS）**与使用政策；
- 承担其配额限制、费用及合规义务；
- 不得利用本项目绕过任何服务方的技术或条款限制。

4.5 **竞彩数据来源的合法性**：本项目的竞彩赔率输入数据来源于**中国体育彩票官方网站**（<https://www.lottery.gov.cn/jc/index.html>）的**每日公开数据**——该数据面向社会公众公开发布，本项目**仅作信息参考与研究引用**，不涉及非授权获取，不进行再分发与商业化利用。中国体育彩票为国务院批准、财政部监管、国家体育总局体育彩票管理中心依法发行的**国家公益彩票**；本项目**不提供**任何彩票销售、代购、兑奖或有偿荐彩服务，亦**不参与**任何形式的非法赌博活动。

## 第 5 条 · 使用者合规责任

5.1 **使用者须自行确认并遵守其所在地的全部适用法律。**

5.2 部分司法管辖区对赌博、博彩信息传播、赔率数据采集有严格规定。例如（仅作一般提示，不构成法律意见）：
- 中国大陆地区：赌博属违法行为（见《中华人民共和国刑法》相关条款），私彩、代购亦属违法；
- 其他地区：规定各异，须自行查证。

5.3 本项目**在任何情况下均不提供**：
- 实际投注、购彩、代购服务；
- 任何形式的中介、撮合或支付服务；
- 针对具体赛事的具体投注金额建议。

5.4 **本文不构成法律意见。** 若对本项目使用的合规性存疑，请咨询专业法律人士。

## 第 6 条 · 责任限制

6.1 在适用法律允许的最大范围内，**作者及贡献者不对**因使用或无法使用本项目而产生的任何**直接、间接、附带、特殊、惩罚性或后果性损失**承担责任，包括但不限于：财产损失、利润损失、数据损失、精神损害。

6.2 使用者**自行承担**使用本项目的**全部风险与后果**。

6.3 使用本项目即表示**承认并接受**上述全部条款。

## 第 7 条 · 版权与许可

| 内容 | 许可 |
|:--|:--|
| **源代码**（`scripts/`） | MIT License（见 `LICENSE`） |
| **文档与知识库**（`README.md` / `docs/` / `skills/` / `templates/`） | MIT License（亦可按 **CC BY 4.0** 引用） |
| **蒸馏数据表**（`tables/*.json`） | MIT License（本项目回测衍生结果） |

7.1 **本免责声明不修改、不替代上述许可证**；许可证授予的权利，以遵守本免责声明的全部条款为前提。

7.2 转载、引用、二次分发本项目内容时，**必须保留本免责声明文件**（`DISCLAIMER.md`），不得删除或弱化其中的限制条款。

## 第 8 条 · 条款效力与更新

8.1 若本声明部分条款被认定无效或不可执行，其余条款**依然全部有效**。

8.2 作者保留随时更新本声明的权利；以仓库中的最新版本为准。

---

# English Version

## Section 1 · Nature of the Project

1.1 This project (all code, docs, data tables, examples) is a **personal technical research project** on: LLM-as-runtime orchestration; engineering practice of statistics/probability on sports data; software quality assurance (automated checks, anti-overfitting gates).

1.2 Its **sole purpose** is **academic exchange and technical learning** — reading source code, studying methodology, reproducing backtests, learning engineering practices.

1.3 It is **NOT**, and must not be construed as: a betting tool, wagering assistant, odds-prediction service, investment advice, or any guarantee of match outcomes.

## Section 2 · Prohibited Uses

You **must NOT** use this project (code, outputs, data, conclusions) for:

2.1 Any form of **gambling, betting, or wagering**, or as a basis for such decisions;
2.2 Any commercial activity such as paid tipster services, betting recommendations to others, or lottery proxy purchasing;
2.3 Distribution to **minors**;
2.4 Any use violating applicable laws in your jurisdiction;
2.5 Misleading claims that this project "predicts results" or "earns stable profit".

**Use of this project constitutes acceptance of these terms.**

## Section 3 · No Warranty

3.1 Provided **"AS IS"**, without warranty of any kind — accuracy, completeness, timeliness, merchantability, fitness for purpose, or non-infringement.

3.2 **Honest disclosure**: long-term parlay **EV is negative** — a structural property of sports betting (payout ratio < 100%), independent of any model. This project does not change that fact.

3.3 Historical backtest figures are for **methodology validation only**. Backtests ≠ future performance; inferred returns from backtests are **invalid**.

## Section 4 · Data & Third-Party Rights

4.1 This repository contains **no raw odds databases** or third-party copyrighted data. `tables/*.json` are our own derived backtest artifacts.

4.2 All third-party names mentioned (data vendors, bookmakers such as 1xbet / Bet365, services such as api-football, Odds-API, Understat, ClubElo, football-data) are **trademarks of their respective owners**.

4.3 No **affiliation, sponsorship, endorsement, or partnership** with any of them is implied.

4.4 If you connect any third-party API/source, you **must** comply with their Terms of Service, quotas, fees and obligations, and must not circumvent any technical or contractual limits.

## Section 5 · User Compliance Responsibility

5.1 **You must comply with all applicable laws in your jurisdiction.**

5.2 Rules on gambling and odds-data usage vary by jurisdiction (e.g., gambling is illegal in mainland China). **This document is not legal advice** — consult a professional if unsure.

5.3 The project provides **no** betting/purchasing services, no intermediary or payment services, and no stake-size recommendations for specific matches.

## Section 6 · Limitation of Liability

6.1 To the maximum extent permitted by law, the **authors and contributors are not liable** for any direct, indirect, incidental, special, punitive, or consequential damages arising from use of (or inability to use) this project.

6.2 **You bear all risk** of using this project.

## Section 7 · Copyright & License

| Content | License |
|:--|:--|
| Source code (`scripts/`) | MIT (see `LICENSE`) |
| Docs & knowledge base (`README.md`, `docs/`, `skills/`, `templates/`) | MIT (may also be cited as **CC BY 4.0**) |
| Distilled tables (`tables/*.json`) | MIT (our derived backtest artifacts) |

7.1 This disclaimer does **not** modify those licenses; licensed rights are conditioned on compliance with this disclaimer.

7.2 Any redistribution **must retain this `DISCLAIMER.md`** in full.

## Section 8 · Severability & Updates

8.1 If any provision is held invalid, the remaining provisions **remain in full force**.

8.2 The latest version in this repository governs.

---

<div align="center">

**使用本项目即表示您已阅读、理解并同意上述全部条款。**
**By using this project you acknowledge that you have read, understood, and agreed to all terms above.**

</div>
