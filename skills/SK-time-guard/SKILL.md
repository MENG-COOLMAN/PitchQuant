---
name: SK-time-guard
description: 模型时间模块（V3.5.86·2026-11-01·用户指令「模型的时间会漂移」）—— 单一时间入口 + 数据新鲜度分级 + 比赛状态/窗口语义。**触发条件（遇到即调 time_guard）**：收到竞彩 txt / 执行 PreStep / 复盘 / 任何涉及「今晚」「现在」的时间判断。零第三方依赖（标准库 zoneinfo）。
---

# SK-time-guard —— 模型时间模块

## 🔴 为什么需要它（实证·2026-11-01 会话踩坑）

| # | 坑 | 后果 |
|:-:|:--|:--|
| 1 | 不知道当前时间，要另跑 `python -c "datetime.now()"` | 每次多一次调用 |
| 2 | 「今晚 20 点到凌晨 4 点」手工换算 UTC | 算错就漏场 |
| 3 | **ELO 缓存是 8 天前的**，跑完才发现 | 用过期数据判定 |
| 4 | 比赛 **21:00 已开赛**，分析完才反应 | 时效性打折 |
| 5 | prestep 窗口跨日（20:00→次日 04:00） | 需额外判断 |
| 6 | 复盘时已跨日，场上日期还是前一天 | 「今晚」指代模糊 |

**根因**：全仓 **54 处时间调用 / 24 脚本**，各取各的；**11 脚本手工 `timedelta(hours=8)`**、2 脚本用已弃用 `utcnow`、仅 1 脚本用 zoneinfo → **口径不统一 + 无新鲜度标准**。

## 设计原则

1. **绝对时刻一律 UTC 存储**，只在展示层转北京（借鉴 `georgedouzas/sports-betting`：它踩过「20:00 UK = 19:00 UTC 夏天 / 20:00 UTC 冬天」）
2. **单一入口** —— 新代码用 `now_bj()/now_utc()`，禁再散落 `datetime.now()`
3. **新鲜度统一分级** —— 快照/盘口/ELO/赛季表各有阈值
4. **业务语义封装** —— 比赛状态、跨日窗口、时序跨度
5. **零依赖**（标准库 `zoneinfo`）—— 我们只有 UTC+8 与 UTC，中国无夏令时；`whenever/pendulum` 的 DST-safe 能力用不上却多一层依赖

## 🔴 强制触发点（三处必调）

| 触发 | 命令 | 目的 |
|:--|:--|:--|
| **收到竞彩 txt 第一件事** | `python data/tmp/time_guard.py --kickoff "<开赛时间>"` | 确认当前时间 + 比赛状态（未开赛/进行中/已结束）+ 数据年龄 |
| **执行 PreStep 前** | `python data/tmp/time_guard.py --window "<窗口描述>"` | 窗口 → UTC 区间（支持中文「今晚23点到凌晨4点」） |
| **复盘时** | `python data/tmp/time_guard.py` | 确认当前日期（防跨日指代错误） |

## 三层 API

### L1 时间源（唯一入口）
```python
from time_guard import now_bj, now_utc, today_bj, fmt_bj, to_bj, to_utc, parse_dt

now_bj()      # 当前北京（aware datetime·IANA Asia/Shanghai）
now_utc()     # 当前 UTC
today_bj()    # 今天（北京日期）
fmt_bj(t)     # → 'YYYY-MM-DD HH:MM:SS'
parse_dt(s)   # 多格式解析（naive 一律视为北京）
```

### L2 数据新鲜度
```python
from time_guard import freshness, sweep

freshness('data/tmp/prestep_window.json', kind='snapshot')
# → {path, mtime_bj, age_h, level, note}
sweep()       # 全量体检表
```

**分级阈值**（`KINDS`）：

| kind | fresh | ok | stale | expired |
|:--|--:|--:|--:|--:|
| `snapshot` 赔率快照 | ≤2h | ≤6h | ≤24h | >24h |
| `odds` 盘口文件 | ≤6h | ≤12h | ≤48h | >48h |
| `elo` ELO 缓存 | ≤3d | ≤7d | ≤14d | >14d |
| `table` 赛季表/基准 | ≤30d | ≤90d | ≤180d | >180d |
| `cache` 通用缓存 | ≤6h | ≤24h | ≤7d | >7d |

🔴 **判级规则**：`stale`/`expired` → **判定前须刷新，或在 raw 三态标注「数据年龄 Xh·已过期·仅参考」**（禁静默使用）

### L3 业务语义
```python
from time_guard import match_state, parse_window, time_span

match_state('2026-10-31 21:00')
# → {state: '已结束'/'进行中'/'未开赛'/'未知', minutes, note}

parse_window('今晚23点到凌晨4点')
# → {ok, start_bj, end_bj, start_utc, end_utc, cross_day, note}
# 支持: '20:00-04:00' / '20点到4点' / '今晚23点到凌晨4点'

time_span(['2026-10-31 17:12', '2026-10-31 19:53'])
# → {n:2, span_h:2.68, first, last, note}
```

## 已知坑与对策

| 坑 | 对策 |
|:--|:--|
| **naive datetime 混用** | `parse_dt()` 一律补北京时区；跨脚本传递时间**必须带时区** |
| **手工 `timedelta(hours=8)`** | 用 `to_bj()/to_utc()`，别自己算 |
| **`datetime.utcnow()` 已弃用** | 用 `now_utc()`（aware） |
| **跨日窗口** | `parse_window` 自动判 `cross_day` 并加一天 |
| **文件不存在 vs glob** | `freshness` 支持 `*` 通配（如 `clubelo_*.json`），但**glob 判定必须在 exists 之前** |
| **系统时钟被改** | `python data/tmp/time_guard.py --verify` 联网比对 HTTP Date header，偏差 >5min 告警 |

## 接入状态（2026-11-01）

| 阶段 | 内容 | 状态 |
|:--|:--|:--|
| P1 | `time_guard.py` + 本 skill | ✅ 完成 |
| P2 | `pipeline` Stage0 打印时间上下文 | ✅ 完成 |
| **P2b** | **`calc_all` 时间上下文**（所有完整分析必经·带 `--no-time` 开关供 pipeline 防重复） | ✅ **完成** |
| **P2c** | **`audit_steps` S00 门禁**（raw 缺「时间上下文」→ MISSING → 落盘失败） | ✅ **完成** |
| P3 | 关键 5 脚本改用 `now_bj()` / `parse_window()` | ⏸ 待做 |
| P4 | 剩余 19 脚本渐进替换 + check_sync 断言 | ⏸ 待做 |

🔴 **2026-11-01 教训（用户质疑「pipeline 接入就自动跟随了吗」）**：
「接入 pipeline」只覆盖**一条路径** —— 手工跑 `calc_all` / 执行 PreStep / 复盘时全部漏掉。
实测：299 篇 raw 含「时间上下文」**0 篇**。
→ 修法：**接入所有必经路径 + 加门禁**（`audit_steps` S00 缺失即判 MISSING），
不能只接入一条然后假设模型会走那条路（这正是 AGENTS 反复批评的「存在≠活跃」）。

**当前纪律**：新代码**必须**用 `time_guard`；旧代码保持原样（P3/P4 渐进替换，避免大改动引入回归）。

## 诚实边界

- 比赛状态按「开赛时间 + 120 分钟」粗判（**不含伤停补时/加时**）→ 临场 115-125 分钟区间可能误判
- `verify_clock` 依赖网络；离线时返回「跳过」不算失败
- 新鲜度阈值（2h/6h/24h 等）为**经验值·未回测** → 可按实际使用调整 `KINDS`
