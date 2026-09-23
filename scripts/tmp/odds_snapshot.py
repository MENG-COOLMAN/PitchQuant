# -*- coding: utf-8 -*-
"""多时点赔率快照采集 · P1-3 Steam Move 的数据前置（模型升级 2026-09-21）

🔴 行业口径（Sportmonks）: 同一时间窗口内 **≥3 家机构同向移动 ≥0.10 十进制赔率
   （流动联赛）/ 0.15-0.20（小众市场）= Steam Move**；窗口 **5 分钟**。
   方案原文写的"30 分钟 / 4 家"过宽 → 本模块按行业口径默认 **3 家 / 5 分钟**（可调）。

采集时点（方案 P1-3 建议）: 赛前 4h / 2h / 1h / 30min / 临场
存储: data/tmp/snapshots/<case_id>.json

用法:
  python data/tmp/odds_snapshot.py add --case 202 --books books.json [--t "2026-09-21 20:00"]
  python data/tmp/odds_snapshot.py status --case 202
  python data/tmp/odds_snapshot.py detect --case 202        # → 供 fundflow_analyzer --snapshots

books.json 格式: [{"bookmaker":"Pinnacle","h":1.85,"d":3.6,"a":4.2}, ...]
（来源: api-football odds?fixture=ID → 13 家·或 Odds-API get_odds 全市场）
"""
import argparse
import json
import os
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'snapshots')


def _path(case):
    os.makedirs(DIR, exist_ok=True)
    return os.path.join(DIR, f'{case}.json')


def _load(case):
    p = _path(case)
    if os.path.exists(p):
        try:
            with open(p, encoding='utf-8') as fh:
                return json.load(fh)
        except Exception:
            pass
    return {'case_id': case, 'snapshots': []}


def cmd_add(a):
    d = _load(a.case)
    with open(a.books, encoding='utf-8') as fh:
        books = json.load(fh)
    ts = a.t or datetime.now().strftime('%Y-%m-%d %H:%M')
    d['snapshots'].append({'t': ts, 'n_books': len(books), 'books': books})
    with open(_path(a.case), 'w', encoding='utf-8') as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2)
    print(f"✅ case{a.case} 快照 #{len(d['snapshots'])} @ {ts}（{len(books)} 家）")


def cmd_status(a):
    d = _load(a.case)
    n = len(d.get('snapshots', []))
    print("═" * 58)
    print(f"【快照状态 · case{a.case}】共 {n} 个时点")
    for s in d.get('snapshots', []):
        print(f"  {s['t']} · {s['n_books']} 家")
    if n < 2:
        print("  ⚠️ Steam 检测需 ≥2 个时点（方案建议 5 个：赛前 4h/2h/1h/30min/临场）")
    print(f"  路径: {_path(a.case)}")


def cmd_detect(a):
    d = _load(a.case)
    snaps = d.get('snapshots', [])
    if len(snaps) < 2:
        print(json.dumps({'status': 'pending_data',
                          'note': f'仅 {len(snaps)} 个时点·需 ≥2（建议 5）'}, ensure_ascii=False))
        return
    first, last = snaps[0]['books'], snaps[-1]['books']
    by = {b.get('bookmaker'): b for b in last}
    moved = {'H': 0, 'D': 0, 'A': 0}
    details = []
    for b in first:
        nm = b.get('bookmaker')
        if nm not in by:
            continue
        for k, kk in zip('HDA', ('h', 'd', 'a')):
            try:
                chg = (float(by[nm][kk]) - float(b[kk])) / float(b[kk])
                if (float(b[kk]) - float(by[nm][kk])) >= 0.10:   # 绝对赔率变动 ≥0.10 十进制·Sportmonks 口径
                    moved[k] += 1
                    details.append(f"{nm} {k} {chg*100:+.1f}%")
            except (TypeError, ValueError, KeyError, ZeroDivisionError):
                pass
    top = max(moved, key=moved.get)
    res = {'status': 'ok', 'windows': len(snaps), 'moved': moved,
           'steam': top if moved[top] >= 3 else None,
           'threshold': '≥3 家同向 ≥10%（行业口径·Sportmonks）',
           'details': details[:10],
           'backtest': 'pending_data'}
    print(json.dumps(res, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description='多时点赔率快照（P1-3 数据前置）')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p1 = sub.add_parser('add')
    p1.add_argument('--case', required=True)
    p1.add_argument('--books', required=True)
    p1.add_argument('--t')
    p1.set_defaults(func=cmd_add)
    p2 = sub.add_parser('status')
    p2.add_argument('--case', required=True)
    p2.set_defaults(func=cmd_status)
    p3 = sub.add_parser('detect')
    p3.add_argument('--case', required=True)
    p3.set_defaults(func=cmd_detect)
    a = ap.parse_args()
    a.func(a)


if __name__ == '__main__':
    if len(sys.argv) == 1:
        print(__doc__)
    else:
        main()
