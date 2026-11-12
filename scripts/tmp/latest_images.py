# -*- coding: utf-8 -*-
"""latest_images.py —— 按「最近一批」抓竞彩截图（替代手工时间窗）

🔴 根因（2026-11-01 实抓）：我用 `-12 分钟` 时间窗 → 22:45 那批（利物浦 vs 阿森纳）
   在 23:45 才被用户提起 → **整批漏掉**。固定时间窗必然漏「发早了但晚问」的批次。

用法:
  python data/tmp/latest_images.py              # 最近一批
  python data/tmp/latest_images.py --n 2        # 最近 2 批
  python data/tmp/latest_images.py --list       # 列全部批次
"""
import argparse
import datetime as dt
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

DIRS = ['.reasonix/attachments',
        os.path.expanduser('~/.reasonix/attachments')]


def batches():
    """→ [(批次时间, [文件路径...])]，按时间升序

    🔴2026-11-01 修：原按**秒**切批 → 同一批 4 张图若跨秒（如 224512 ×3 + 224513 ×1）
       会被拆成 2 批 → `latest(1)` 只拿到 1 张（实测漏了利物浦场的胜平负/让球页）
       → 改「**±5 秒内合并为同一批**」
    """
    raw = []
    for d in DIRS:
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            p = os.path.join(d, f)
            if not os.path.isfile(p):
                continue
            m = re.search(r'clipboard-(\d{8})-(\d{6})', f)
            if not m:
                continue
            ts = dt.datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M%S')
            raw.append((ts, p))
    raw.sort()
    out = []
    GAP = 30          # ±5 秒内算同一批
    cur_ts, cur_fs = None, []
    for ts, p in raw:
        if cur_ts is None or (ts - cur_ts).total_seconds() > GAP:
            if cur_fs:
                out.append((cur_ts.strftime('%Y%m%d-%H%M%S'), cur_fs))
            cur_ts, cur_fs = ts, [p]
        else:
            cur_fs.append(p)
    if cur_fs:
        out.append((cur_ts.strftime('%Y%m%d-%H%M%S'), cur_fs))
    return out


def latest(n=1):
    bs = batches()
    return bs[-n:] if n > 0 else bs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=1)
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--print', action='store_true', help='只打印路径（供 shell 用）')
    a = ap.parse_args()

    bs = batches()
    if not bs:
        print('⚪ 无附件', file=sys.stderr)
        return 1

    if a.list:
        print('共 %d 批：' % len(bs))
        for k, fs in bs:
            print('  %-16s %d 张  首: %s' % (k, len(fs), os.path.basename(fs[0])))
        return 0

    sel = latest(a.n)
    if a.print:
        for _, fs in sel:
            for f in fs:
                print(f)
        return 0

    print('最近 %d 批：' % len(sel))
    for k, fs in sel:
        print('  %-16s %d 张' % (k, len(fs)))
        for f in fs:
            print('     %s  %.0fKB' % (os.path.basename(f), os.path.getsize(f) / 1024))
    print('\n建议命令:')
    paths = ' '.join('"%s"' % f for _, fs in sel for f in fs)
    print('  python data/tmp/image2txt.py %s --league <联赛> --teams "主,客" --kickoff "YYYY-MM-DD HH:MM"'
          % paths[:200] + ('...' if len(paths) > 200 else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
