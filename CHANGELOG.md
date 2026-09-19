# Changelog · 更新日志

所有重要变更记录于此。格式参考 [Keep a Changelog](https://keepachangelog.com/)。
All notable changes to this project are documented here.

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
