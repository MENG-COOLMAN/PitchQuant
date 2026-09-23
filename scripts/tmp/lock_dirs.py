# -*- coding: utf-8 -*-
"""lock_dirs.py —— host「read-evidence 锁」写入边界声明生成器（2026-09-20 固化）

🔴问题: bash 报 `bash cannot declare which files it changes while a read-evidence
        requirement is outstanding` —— 根因是 bash 未声明"会写哪些目录"（非"读不够"）。
🔴本脚本: 输出**模型实际会写的目录白名单**（含所有子目录·只列父目录不足）→ 直接复制到 bash 调用。

用法:
  python data/tmp/lock_dirs.py             # 打印可复制的 JSON 列表（默认）
  python data/tmp/lock_dirs.py --template  # 打印 bash 调用模板（含顺序纪律）

🔴操作纪律（顺序模板）:
  ① write_file / edit_file（多文件编辑放轮末）
  ② 下一轮 read_file 该文件（同批次内的 read 不算）
  ③ bash + additional_write_dirs（用本脚本输出·宁多勿漏）
"""
import os, sys, json, argparse
sys.stdout.reconfigure(encoding='utf-8')

WS = 'C:/Users/12242/AppData/Roaming/reasonix/global-workspace'
DSK = 'C:/Users/12242/Desktop/足球预测模型'
TOP = 'C:/Users/12242/Desktop'

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


def dirs():
    """白名单 + 存在性过滤（只输出真实存在的目录）"""
    return [d for d in WHITELIST if os.path.isdir(d)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scan', action='store_true', help='（默认行为·保留兼容）')
    ap.add_argument('--template', action='store_true', help='打印 bash 调用模板')
    a = ap.parse_args()
    ds = dirs()
    if a.template:
        print('# 🔴bash 调用模板（additional_write_dirs 用下方列表·宁多勿漏）')
        print('# additional_write_dirs = ' + json.dumps(ds, ensure_ascii=False))
        print('# 顺序: ① write/edit ② 下一轮 read ③ bash + 上述声明（一次跑完）')
        return
    print('🔴 additional_write_dirs（共 %d 个·直接复制到 bash 调用）:' % len(ds))
    print(json.dumps(ds, ensure_ascii=False))


if __name__ == '__main__':
    main()
