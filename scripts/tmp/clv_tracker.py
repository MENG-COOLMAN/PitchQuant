# -*- coding: utf-8 -*-
"""P2-1 CLV（Closing Line Value）追踪 · 模型升级 2026-09-21

🔴 定位修正（重要·诚实边界）:
  CLV **不是"预测长期价值的金标准"**。Whelan 用 3,670 场 NBA / 34,944 条报价证明：
  **5 个正 CLV 十分位中有 3 个平均不盈利**（第 9 分位均 +5% CLV 也仅"勉强回本"）。
  → 本模块定位 = **模型健康度监测指标**（趋势预警 + 触发人工评审），
    **不作为单场/中期盈利保证**，也不参与单场判定。

记录字段:
  case_id / date / direction / anchor / opening_odds / closing_odds / clv_pp
用法:
  python data/tmp/clv_tracker.py record --case 199 --dir H --open 1.759 [--close 1.72] [--anchor "1:1|1:0"]
  python data/tmp/clv_tracker.py close  --case 199 --close 1.72
  python data/tmp/clv_tracker.py status [--last 50]
存储: data/tmp/clv_log.json
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

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'clv_log.json')


def _load():
    if os.path.exists(LOG):
        try:
            with open(LOG, encoding='utf-8') as fh:
                return json.load(fh)
        except Exception:
            return {'records': []}
    return {'records': []}


def _save(d):
    with open(LOG, 'w', encoding='utf-8') as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2)


def _clv(opened, closed):
    """CLV: 推荐方向赔率下降 = 正 CLV（我方拿到比收盘更好的价）"""
    if not opened or not closed or opened <= 1.01:
        return None
    return round((opened - closed) / opened * 100, 2)


def cmd_record(a):
    d = _load()
    rec = next((r for r in d['records'] if r['case_id'] == a.case), None)
    if rec is None:
        rec = {'case_id': a.case, 'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
               'direction': a.dir, 'anchor': a.anchor}
        d['records'].append(rec)
    rec['opening_odds'] = a.open
    if a.close:
        rec['closing_odds'] = a.close
        rec['clv_pp'] = _clv(a.open, a.close)
    _save(d)
    print(f"✅ 记录 case{a.case}: 方向={a.dir} 开盘={a.open} "
          f"收盘={a.close or '待补'} CLV={rec.get('clv_pp', '待算')}")


def cmd_close(a):
    d = _load()
    rec = next((r for r in d['records'] if r['case_id'] == a.case), None)
    if not rec:
        print(f"⚠️ case{a.case} 无记录（先用 record 建）")
        return
    rec['closing_odds'] = a.close
    rec['clv_pp'] = _clv(rec.get('opening_odds'), a.close)
    _save(d)
    print(f"✅ case{a.case} 收盘={a.close} → CLV={rec['clv_pp']}%")


def cmd_status(a):
    d = _load()
    rs = [r for r in d['records'] if r.get('clv_pp') is not None]
    print("═" * 58)
    print("【CLV 健康度监测 · P2-1】")
    print("═" * 58)
    if not rs:
        print("  暂无完整记录（需 opening + closing）")
        print("  🔴 定位提醒: CLV = 模型健康度指标·非盈利保证（Whelan: 正 CLV 十分位 3/5 不盈利）")
        return
    last = rs[-a.last:] if a.last else rs
    pos = sum(1 for r in last if r['clv_pp'] > 0)
    avg = sum(r['clv_pp'] for r in last) / len(last)
    print(f"  样本 {len(last)} 场（累计 {len(rs)}）· 正 CLV {pos}/{len(last)} = {pos/len(last)*100:.1f}% · 平均 CLV {avg:+.2f}%")
    print(f"  最近 5 场: " + " | ".join(f"case{r['case_id']}({r['direction']}) {r['clv_pp']:+.1f}%"
                                       for r in last[-5:]))
    print("  🔴 门禁（方案 P2-1）: 连续 50 场负 CLV → 模型降级 + 强制人工评审")
    print(f"  → 当前状态: {'⚠️ 需关注（近 ' + str(len(last)) + ' 场平均为负）' if avg < 0 and len(last) >= 50 else '正常/样本不足'}")
    print("  ⚠️ 定位: 健康度监测·不参与单场判定·非盈利保证")


def main():
    ap = argparse.ArgumentParser(description='CLV 追踪（P2-1·定位=健康度监测）')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p1 = sub.add_parser('record')
    p1.add_argument('--case', required=True)
    p1.add_argument('--dir', required=True)
    p1.add_argument('--open', type=float, required=True)
    p1.add_argument('--close', type=float)
    p1.add_argument('--anchor')
    p1.set_defaults(func=cmd_record)
    p2 = sub.add_parser('close')
    p2.add_argument('--case', required=True)
    p2.add_argument('--close', type=float, required=True)
    p2.set_defaults(func=cmd_close)
    p3 = sub.add_parser('status')
    p3.add_argument('--last', type=int, default=50)
    p3.set_defaults(func=cmd_status)
    a = ap.parse_args()
    a.func(a)


if __name__ == '__main__':
    main()
