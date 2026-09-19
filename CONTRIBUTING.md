# Contributing · 参与贡献

感谢关注 PitchQuant！欢迎任何形式的参与。

---

## 🎯 我们欢迎什么

| 类型 | 建议方式 |
|:--|:--|
| **Bug 报告** | 开 Issue：复现步骤 / 期望 vs 实际 / 环境信息 |
| **方法论讨论** | 开 Issue：回测发现 · 统计质疑 · 数据源建议 |
| **文档改进** | PR 或 Issue：错别字 / 表述不清 / 翻译 |
| **代码贡献** | 建议**先开 Issue 讨论**，再提 PR |

---

## ✅ 提交前检查（CI 会自动跑这三项）

```bash
# 1) 语法
python -m compileall -q scripts/ templates/

# 2) 数据表完整性
python -c "import json,glob; [json.load(open(f,encoding='utf-8')) for f in glob.glob('tables/*.json')]; print('tables OK')"

# 3) 密钥残留扫描（CI 里等价命令）
grep -rIlE "(api[_-]?key|apikey|secret|token)\s*[:=]\s*['\"][A-Za-z0-9]{16,}['\"]" . \
  --include='*.py' --include='*.md' --include='*.json'
```

---

## 📐 代码约定

1. **确定性优先** —— 核心计算必须"同输入 ⇒ 同输出"（不得使用未固定种子的随机）
2. **禁硬编码密钥** —— 一律走环境变量（`.env`，已在 `.gitignore` 排除）
3. **禁提交原始数据** —— `*.sql`、大型 CSV、私有数据集（体积 + 来源条款限制）
4. **异常不静默** —— 禁止 `except Exception: pass`（必须打印错误或显式降级标注）
5. **中文注释可接受** —— 项目原生日志为中文，中英混合无需强行统一

---

## ⚖️ 法律前提（重要·提交即表示同意）

- 本项目**仅用于学术交流与技术学习**，**严禁博彩/投注用途**（见 [DISCLAIMER.md](DISCLAIMER.md)）
- 你的贡献将按 **MIT License** 授权
- 🔴 **不得提交任何含个人信息的数据**（手机号 / 密码 / 订单 / 用户表等）
- 若引入新的第三方数据或代码，**必须**在 PR 中说明其来源与许可

---

## 💬 联系方式

📧 **jiekefalali@gmail.com** · 或直接开 [Issue](https://github.com/MENG-COOLMAN/PitchQuant/issues)

---

> ⚠️ **FOR ACADEMIC & EDUCATIONAL USE ONLY** · 仅用于学术交流与技术学习 · **严禁用于博彩/投注**
