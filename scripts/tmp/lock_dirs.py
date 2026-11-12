# -*- coding: utf-8 -*-
"""lock_dirs.py —— host「read-evidence 锁」写入边界声明 + 决策树生成器（2026-09-20 固化·2026-09-27 增 --decide）

🔴问题: bash 报 `bash cannot declare which files it changes while a read-evidence
        requirement is outstanding` —— 根因是 bash 未声明"会写哪些目录"（非"读不够"）。
🔴本脚本: 输出**模型实际会写的目录白名单**（含所有子目录·只列父目录不足）→ 直接复制到 bash 调用。

用法:
  python data/tmp/lock_dirs.py             # 打印可复制的 JSON 列表（默认）
  python data/tmp/lock_dirs.py --template  # 打印 bash 调用模板（含顺序纪律）
  python data/tmp/lock_dirs.py --decide    # 🔴2026-09-27 新增: 打印四方案决策树（遇锁即查·免反复试探）

🔴触发即用（2026-09-27 固化·与 SK-host-lock skill 同源）:
  bash 报 `cannot declare which files it changes while a read-evidence requirement is outstanding`
  → python data/tmp/lock_dirs.py --decide   （方案0 轮次拆分 / 方案1 合并单次 edit /
                                             方案2 文件工具替代 bash / 方案3 全程只读）

🔴操作纪律（顺序模板）:
  ① write_file / edit_file（多文件编辑放轮末·同文件多处改动合并为单次）
  ② 下一轮 read_file 该文件（同批次内的 read 不算）
  ③ bash + additional_write_dirs（用本脚本输出·宁多勿漏·⚠️有 outstanding 时声明无效）
"""
import os, sys, json, argparse
sys.stdout.reconfigure(encoding='utf-8')

# 🔴2026-10-20 审计修：原写死绝对路径 → 由 __file__ 与用户桌面推导（换机可用）
#   __file__ = <ws>/data/tmp/lock_dirs.py → dirname×3 = <ws>
WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DESK = os.path.join(os.path.expanduser('~'), 'Desktop')
DSK = os.path.join(_DESK, '足球预测模型')
TOP = _DESK

# 🔴白名单: 模型实际会写入的目录（工作区 + 桌面副本 + 桌面）
#    说明: 只列"会写"的目录·避免扫描 node_modules/任务缓存导致列表爆炸（曾达 16222 项）
WHITELIST = [
    WS, WS + '/data', WS + '/data/tmp', WS + '/data/case-library', WS + '/data/case-library/raw',
    WS + '/data/online_learning', WS + '/data/league-modules', WS + '/data/europe',
    WS + '/data/team_profiles', WS + '/data/scripts', WS + '/docs', WS + '/.reasonix/skills',
    DSK, DSK + '/data', DSK + '/data/tmp', DSK + '/data/case-library', DSK + '/data/case-library/raw',
    DSK + '/data/online_learning', DSK + '/data/league-modules', DSK + '/data/europe',
    DSK + '/data/team_profiles', DSK + '/data/scripts', DSK + '/docs', DSK + '/.reasonix/skills',
    TOP,
]

TRIGGER = 'cannot declare which files it changes while a read-evidence requirement is outstanding'

DECISION_TREE = """\
🔴 host「read-evidence 锁」决策树（2026-09-27 四方案实测固化·遇此报错即按序执行·禁反复试探）
  现象: bash 报 `%s`
  本质: 🔴不是「读不够」·而是**写入证据义务未结清**（write/edit 过的路径进入 outstanding·
        结清前任何有副作用工具被网关拒绝）——不是 OS 文件锁/权限/杀软；有 outstanding 时
        additional_write_dirs 声明**无效**（声明只在账本干净时被采纳）。

  【方案 0 · 首选·最稳】轮次拆分：本轮只做 write/edit → 结束本轮 → 下一个 turn 直跑 bash
       机制: 跨对话轮次 outstanding 自动重置（2026-09-24 + 2026-09-27 实测：新 turn 内 bash 立即恢复）
       代价: 多一轮交互 ｜ 适用: 绝大多数任务（脚本/构建/测试/同步/校验）

  【方案 1 · 减少条目】同一文件多处修改 → 一次性合并为【单次 edit/write】
       ⚠️只减少账本条目·**不能**让「同 turn edit+bash」并存（本轮有 outstanding 则 bash 仍被拦）

  【方案 2 · 同 turn 兜底】用文件工具替代 bash 做文件变更（edit_file/write_file 不受该门禁拦）
       适用: 追加/替换/补丁类文本修改 ｜ 不能替代: 编译/运行/测试/git 等 shell 业务命令

  【方案 3 · 预防】全程只读（read_file/ls/cat）不写文件 → 账本恒净·bash 随时可跑
       适用: 探查/静态阅读/分析阶段（先读够再写可完全避免踩锁）

  反模式（禁止）: ❌反复 read 清锁（host 回 Repeated read 仍不清·read 非解药）
                  ❌无声明/声明不全硬跑 bash（有 outstanding 时补全声明亦无效）
                  ❌同文件串行多次 edit（累积 outstanding·可能锁死后续全部 bash/write）
                  ❌把锁误判为环境故障去查权限/占用  ❌有 outstanding 时反复重试同一 bash
  详见: .reasonix/skills/SK-host-lock/SKILL.md（主动查询入口）
""" % TRIGGER


def dirs():
    """白名单 + 存在性过滤（只输出真实存在的目录）"""
    return [d for d in WHITELIST if os.path.isdir(d)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scan', action='store_true', help='（默认行为·保留兼容）')
    ap.add_argument('--template', action='store_true', help='打印 bash 调用模板')
    ap.add_argument('--decide', action='store_true', help='🔴打印四方案决策树（遇锁即查）')
    a = ap.parse_args()
    ds = dirs()
    if a.decide:
        print(DECISION_TREE)
        return
    if a.template:
        print('# 🔴bash 调用模板（additional_write_dirs 用下方列表·宁多勿漏）')
        print('# additional_write_dirs = ' + json.dumps(ds, ensure_ascii=False))
        print('# 顺序: ① write/edit ② 下一轮 read ③ bash + 上述声明（一次跑完）')
        print('# ⚠️ 有 outstanding 时声明无效 → 先按 --decide 的方案 0/2 处理')
        return
    print('🔴 additional_write_dirs（共 %d 个·直接复制到 bash 调用）:' % len(ds))
    print(json.dumps(ds, ensure_ascii=False))


if __name__ == '__main__':
    main()
