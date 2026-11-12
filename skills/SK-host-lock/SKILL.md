---
name: SK-host-lock
description: >-
  执行宿主（host）「read-evidence 锁」解法（2026-09-27 四方案实测固化）。🔴触发条件（遇到即读本 skill，禁反复试探）：
  bash 报错 —— `bash cannot declare which files it changes while a read-evidence requirement is outstanding (<paths>)`，
  或 `edit_file/write_file cannot declare which files it changes while a read-evidence requirement is outstanding`。
  内容：锁的本质（不是"读不够"，是**写入证据义务未结清**）+ **四方案优先级决策树**（方案0 轮次拆分=首选 / 方案1 合并单次 edit / 方案2 文件工具替代 bash / 方案3 全程只读）+ 操作模板 + 实测证据 + 反模式。
  🔴与 AGENTS「host 工具链 read-evidence 锁解法」节 / 迁移文档同源；本 skill 是**主动查询入口**（脚本 `data/tmp/lock_dirs.py --decide` 亦可直接打印决策树）。
---

# SK-host-lock — host 执行宿主「read-evidence 锁」解法

> 🔴**被动触发型 skill**：仅在**出现锁报错**时读取执行；正常任务**不触发**。
> 🔴**铁律：遇到即按决策树处理，禁反复试探**（反复 read 清锁 / 反复无声明 bash / 反复重跑同一命令 = 浪费 token，且无效）。

## 一、触发信号（精确匹配）

| 工具 | 报错原文（关键子串） |
|:--|:--|
| `bash` | `bash cannot declare which files it changes while a read-evidence requirement is outstanding (<paths>); use the exact file tool for those paths` |
| `edit_file` / `write_file` | `edit_file/write_file cannot declare which files it changes while a read-evidence requirement is outstanding (<paths>)` |

**辅助信号**：报错后紧跟的 `<paths>` 即「未结清路径清单」（常为刚编辑过、尚未读回的文件）。

---

## 二、本质（决定性认知·勿误判）

🔴 **根因不是「读得不够」，而是「写入证据义务未结清」**：

- 任何 `write_file` / `edit_file` **成功写入某路径**后，该路径进入 **outstanding（未结清）** 状态；
- 结清前，**有副作用的工具**（`bash`，因为 host 无法静态判定它会改哪些文件）被**网关拒绝**；
- 因此 **`additional_write_dirs` 声明在有 outstanding 时无效**——声明只在"账本干净"时被采纳；
- 只读工具（`read_file`）不受影响，且是结清手段之一（但见下方反模式 ①）。

**它不是什么**：❌ OS 文件锁/flock ❌ ACL 权限 ❌ 杀软占用 ❌ git 锁（工区常非 git 仓库）❌ 磁盘占用。
**它是什么**：✅ 执行宿主在**工具调用网关层**实现的**写前证据门禁**（post-edit evidence obligation / per-path ledger）。

---

## 三、🔴 决策树（按优先级执行·首选即最优）

```
出现锁报错
  │
  ├─【方案 0 · 首选·最稳】轮次拆分：本轮只做 write/edit → 提交 → 下一个 turn 直跑 bash
  │     · 机制：跨对话轮次 outstanding 自动重置（账本清空）
  │     · 何时用：绝大多数任务（脚本执行/构建/测试/同步/校验）
  │     · 代价：多一轮交互
  │
  ├─【方案 1 · 减少条目】同文件多处修改一次性合并为【单次 write/edit】
  │     · 机制：只产生 1 条 outstanding，降低锁死概率
  │     · ⚠️不能突破「同 turn edit+bash 混跑」限制——本轮有 outstanding 时 bash 仍被拦
  │     · 何时用：改同一文件的多个位置 / 一批多文件连续编辑
  │
  ├─【方案 2 · 同 turn 兜底】用文件工具替代 bash 做「文件变更」
  │     · `edit_file` / `write_file` **不受该门禁拦截**（即使存在 outstanding 亦可调用）
  │     · 适用：追加/替换/补丁类文本修改
  │     · ⚠️不能替代编译、运行、测试、git 等 shell 业务命令
  │
  └─【方案 3 · 预防】全程只读（read_file / ls / cat）不写文件 → 账本恒净，bash 随时可跑
        · 何时用：探查/静态阅读/分析阶段；**预先规划**「先读够再写」可完全避免踩锁
```

**决策速查**：
| 情境 | 采用 |
|:--|:--|
| 已编辑完，需要跑命令 | **方案 0**（下个 turn 跑） |
| 要改同一文件多处 | **方案 1**（合并成一次） |
| 本轮既要改文件又要跑命令 | 拆分：编辑走**方案 2** 的文件工具；命令留到**方案 0** 的下一轮 |
| 只想读代码/查状态 | **方案 3**（根本不写，不产生锁） |

---

## 四、操作模板（复制即用）

```bash
# ① 生成写入边界声明（宁多勿漏·只列父目录不足）
python data/tmp/lock_dirs.py            # → additional_write_dirs 的 JSON 列表
python data/tmp/lock_dirs.py --template # → bash 调用模板 + 顺序纪律
python data/tmp/lock_dirs.py --decide   # → 四方案决策树（本 skill 的脚本化入口）

# ② 标准顺序
#   [turn N]   write_file / edit_file（多文件编辑集中在轮末）
#   [turn N+1] read_file（被改文件）           ← 结清 outstanding
#   [turn N+2] bash + additional_write_dirs（一次跑完 编译/测试/同步/校验）
```

**轮末编辑原则**：多文件 write/edit 尽量放在**同一轮末尾**，缩短"待结清窗口"。

---

## 五、实测证据（可复现）

| 方案 | 实测结论 | 证据来源 |
|:--|:--|:--|
| 方案 0（跨 turn 重置） | ✅ 成立：新 turn 内 bash 立即恢复 | 2026-09-24 实测（纪律④④）+ **2026-09-27 本会话连续两次实证** |
| 方案 1（合并单次 edit） | ✅ 成立且必要：同文件分批 edit 会累积 outstanding → 锁死后续写入通道 | 2026-09-24 实测固化（纪律④）；2026-09-27 本会话把 calc_all 5 处改动合并为 1 次 edit |
| 方案 2（文件工具不受拦） | ✅ 成立：`edit_file` 在 outstanding 存在时仍可成功调用（唯一"同 turn 可用"的写通道） | 2026-09-27 本会话：bash 被拦的同轮/次轮仍成功执行 edit_file |
| 方案 3（全程只读） | ✅ 成立：探查轮仅 read/ls → bash 全部一次通过 | 2026-09-20 固化 + 2026-09-27 本会话多次探查轮 |
| 声明有效性边界 | 🔴 **有 outstanding 时 additional_write_dirs 无效**（声明只在账本干净时被采纳） | 2026-09-27 本会话：带全量声明仍被同一路径拦 |

---

## 六、反模式（禁止·均在会话中验证为无效）

1. ❌ **反复 `read_file` 清锁** —— host 可能回 `Repeated read … already satisfied`，账本不清；read 不是解药（尤其与 bash 同批次时"同批 read 不算"）。
2. ❌ **无声明或声明不全硬跑 bash** —— 直接拦；且"声明补全"在有 outstanding 时也无效。
3. ❌ **同一文件串行多次 edit** —— 累积 outstanding，可能锁死后续**全部** bash/write。
4. ❌ **把锁误判为"环境故障"去排查文件权限/占用** —— 层级判断错误，浪费时间。
5. ❌ **在有 outstanding 时反复重试同一条 bash** —— 结果必然相同；应转方案 0/2。

---

## 七、与既有规则的关系（避免重复）

- **AGENTS.md**「host 工具链 read-evidence 锁解法」节 = 规则源头（三处同步：AGENTS / 主技能 / txt / 迁移文档）
- **纪律④**（2026-09-24）= 本 skill 的**方案 1** 的具体化（合并编辑 + 轮末编辑）
- **本 skill** = **主动查询入口 + 完整决策树**（四方案 + 优先级 + 反模式 + 证据），遇到锁报错时**直接读本 skill 即可，禁再试探**

---

## 八、使用示例

```
bash 报: bash cannot declare which files it changes while a read-evidence requirement is outstanding (data/tmp/calc_all.py)
→ 读本 skill →
  ① 本轮编辑已结束 → 采用【方案 0】：结束本轮，下个 turn 直跑 bash（含 additional_write_dirs）
  ② 若本轮还需改文件 → 采用【方案 2】：用 edit_file 继续（不受拦）
  ③ 若本轮还要跑命令且不想等 → 拆：文件改动走方案 2，命令留待下轮（方案 0）
```
