# -*- coding: utf-8 -*-
"""ucl_ou_monitor.py — O-UCL-2 监测：欧冠小球场是否该豁免 N24 的 +0.67 球（2026-10-21·用户指令）

## 背景

用户 2026-10-21 指令「欧战子模型校准·尤其欧冠·大球显著」→ 落地 **N24**：欧冠正赛/淘汰赛 λ 与期望 E
各 **+0.67 球**（点估计·全额）。但欧冠小球场（如 case260 O2.5=1.41 实际 2 球）会因全局平移被**更明显高估**。
→ 用户要求做成**监测记录**，且「一定要对市场信号敏感」。

## 为什么必须「市场敏感」（本脚本的核心设计）

单纯看「实际 − N24后期望」不行 —— 若市场本身就把这场判为大球（隐含 65%），实际出小球的偏差
**不是 N24 的错**，是市场定价里的 34%。所以本脚本把偏差**拆成两个**：

    dev_vs_market = 实际 − 市场期望(_o25_expect)        ← 市场的偏差（N24 无关）
    dev_vs_n24    = 实际 − (市场期望 + 0.67)           ← N24 的增量偏差

判据（区分责任）:

| dev_vs_market | dev_vs_n24 | 结论 |
|:--|:--|:--|
| ≈0 | ≤−0.5 | 🔴 **N24 高估**（市场对）→ 该考虑小球场豁免 |
| ≤−0.5 | ≤−0.5 | 🟡 市场也高估（非 N24 问题）→ **不建议豁免**（会掩盖市场问题） |
| ≥+0.5 | ≥0 | 🟢 市场低估，N24 方向正确 → 维持 |

## 用法

    # 每场欧冠分析完（有赛果后）记录
    python data/tmp/ucl_ou_monitor.py record --case 261 --o25 1.41 --u25 2.64 --actual 2 --note "受让浅盘"
    # 查看监测状态（含门槛判定）
    python data/tmp/ucl_ou_monitor.py status
    # 导入历史场次（回溯·标 retrospective）
    python data/tmp/ucl_ou_monitor.py record --case 260 --o25 1.41 --u25 2.64 --actual 2 --retro

## 门槛（固化条件）

- **小球场** = 实际总进球 ≤2
- 达标复核条件：小球场 **n ≥ 10** 且 `avg(dev_vs_n24) ≤ −0.5` 且 `avg(dev_vs_market) > −0.5`
  （即：偏差主要来自 N24 而非市场）
- 达标后 → 提示「建议 N24 改为条件化（仅大球场加成）」→ 需用户确认 + 时间分割回测才可改
- 未达门槛 → 仅累积，**禁改规则**

## 数据隔离（用户「严禁数据外流」）

- 本表**只记欧冠场次**（`--league` 非欧冠 → 拒绝写入，防污染）
- 独立 CSV `data/case-library/ucl_ou_monitor.csv`，不被任何联赛子模型读取
- 不修改 magnitude_ledger / 学习台账 / 案例库主表
"""
import csv
import json
import os
import sys
import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))
CSV_PATH = os.path.join(ROOT, 'data', 'case-library', 'ucl_ou_monitor.csv')
N24_ADJ = 0.67
THRESHOLD_N = 10
THRESHOLD_DEV = -0.5

HDR = ['case_id', '日期', '联赛', 'O25', 'U25', '市场隐含大球%', '市场期望', 'N24后期望',
       '实际总进球', '是否大球(≥3)', '偏差vs市场', '偏差vsN24', 'N24已应用', '回溯', '备注']


def _o25_expect(o25):
    """与 live_score_engine._o25_expect 同口径（goal_bins 反推）"""
    try:
        import sys as _s, os as _o
        _d = _o.path.dirname(_o.path.abspath(__file__))
        if _d not in _s.path:
            _s.path.insert(0, _d)
        from live_score_engine import _o25_expect as _f
        return float(_f(o25))
    except Exception:
        pass
    if o25 is None:
        return None
    if o25 < 1.75:
        return 3.05
    if o25 < 2.05:
        return 2.70
    return 2.28


def _market_over(o25, u25):
    try:
        inv_o, inv_u = 1.0 / float(o25), 1.0 / float(u25)
        return inv_o / (inv_o + inv_u) * 100
    except Exception:
        return None


def load():
    if not os.path.exists(CSV_PATH):
        return []
    with open(CSV_PATH, encoding='utf-8-sig') as f:
        return list(csv.reader(f))


def cmd_record(args):
    def g(k, d=None):
        return args[args.index(k) + 1] if k in args else d

    cid = str(g('--case', '')).strip()
    if not cid:
        print('❌ 必须给 --case'); return 1
    league = g('--league', '欧冠')
    if '欧冠' not in str(league):
        print('🔴 拒写: 本监测表只记欧冠场次（--league=%s）→ 防数据外流污染' % league)
        return 2
    try:
        o25 = float(g('--o25')); u25 = float(g('--u25')); actual = int(g('--actual'))
    except Exception:
        print('❌ 需 --o25 --u25 --actual（数值）'); return 1
    mk = _market_over(o25, u25)
    exp_mkt = _o25_expect(o25)
    exp_n24 = round(exp_mkt + N24_ADJ, 2)
    retro = '--retro' in args
    row = [cid, g('--date', datetime.date.today().isoformat()), league,
           o25, u25,
           round(mk, 1) if mk is not None else '',
           round(exp_mkt, 2), exp_n24, actual,
           '是' if actual >= 3 else '否',
           round(actual - exp_mkt, 2), round(actual - exp_n24, 2),
           '是', '是' if retro else '否', g('--note', '')]

    rows = load()
    if not rows:
        rows = [HDR]
    # upsert（按 case_id·防重复行）
    idx = None
    for i, r in enumerate(rows[1:], 1):
        if r and r[0].strip() == cid:
            idx = i
            break
    if idx is not None:
        rows[idx] = row
        print('🔁 已更新 case%s（upsert）' % cid)
    else:
        rows.append(row)
        print('✅ 已记录 case%s' % cid)
    with open(CSV_PATH, 'w', encoding='utf-8-sig', newline='') as f:
        csv.writer(f).writerows(rows)
    print('   市场隐含大球 %.1f%% ｜ 市场期望 %.2f → N24后 %.2f ｜ 实际 %d 球（%s）'
          % (mk or 0, exp_mkt, exp_n24, actual, '大球' if actual >= 3 else '小球'))
    print('   偏差 vs 市场 %+.2f 球 ｜ vs N24 %+.2f 球' % (actual - exp_mkt, actual - exp_n24))
    return 0


def cmd_status(args):
    rows = load()
    if len(rows) <= 1:
        print('O-UCL-2 监测表为空 → 尚无记录（先用 record 写入欧冠场次）')
        return 0
    data = [r for r in rows[1:] if r and r[0]]
    small = [r for r in data if int(float(r[8])) <= 2]
    big = [r for r in data if int(float(r[8])) >= 3]

    def avg(lst, i):
        v = [float(r[i]) for r in lst if r[i] not in ('', None)]
        return sum(v) / len(v) if v else None

    print('=' * 74)
    print('O-UCL-2 监测：欧冠小球场是否该豁免 N24 +%.2f 球' % N24_ADJ)
    print('=' * 74)
    print('  总记录 %d 场 ｜ 大球(≥3) %d ｜ 小球(≤2) %d' % (len(data), len(big), len(small)))

    if small:
        print('\n  【小球场】n=%d' % len(small))
        print('    平均偏差 vs 市场 : %+.2f 球  ← 市场的偏差（N24 无关）' % (avg(small, 10) or 0))
        print('    平均偏差 vs N24  : %+.2f 球  ← N24 的增量偏差' % (avg(small, 11) or 0))
        print('    平均市场隐含大球 : %.1f%%  ← 市场事前怎么说' % (avg(small, 5) or 0))
    if big:
        print('\n  【大球场】n=%d' % len(big))
        print('    平均偏差 vs 市场 : %+.2f 球' % (avg(big, 10) or 0))
        print('    平均偏差 vs N24  : %+.2f 球' % (avg(big, 11) or 0))
        print('    平均市场隐含大球 : %.1f%%' % (avg(big, 5) or 0))

    # 市场校准度（对市场敏感的核心指标）
    mk_ok = [r for r in data if r[5] not in ('', None)]
    if mk_ok:
        pred_big = sum(1 for r in mk_ok if float(r[5]) >= 50)
        act_big = sum(1 for r in mk_ok if int(float(r[8])) >= 3)
        print('\n  【市场校准】市场判大球(隐含≥50%%) %d 场 → 实际大球 %d 场（差 %+d）'
              % (pred_big, act_big, act_big - pred_big))

    # 门槛判定（区分责任）
    print('\n  【门槛判定】小球场需 n≥%d 且 avg(dev_vs_N24)≤%.1f 且 avg(dev_vs_MARKET)>%.1f' % (
        THRESHOLD_N, THRESHOLD_DEV, THRESHOLD_DEV))
    d24 = avg(small, 11) if small else None
    dmk = avg(small, 10) if small else None
    if len(small) < THRESHOLD_N:
        print('    ⚪ 样本不足（%d/%d）→ 仅累积·禁改规则' % (len(small), THRESHOLD_N))
    elif d24 is not None and dmk is not None and d24 <= THRESHOLD_DEV and dmk > THRESHOLD_DEV:
        print('    🔴 达标 → 偏差主要来自 N24（市场基本无偏）→ **建议 N24 改为条件化（仅大球场加成）**')
        print('       须用户确认 + 时间分割回测 p<0.05 才可改规则')
    elif d24 is not None and dmk is not None and d24 <= THRESHOLD_DEV and dmk <= THRESHOLD_DEV:
        print('    🟡 偏差同时来自市场 → **不建议豁免 N24**（豁免会掩盖市场自身偏差）')
    else:
        print('    🟢 未见 N24 系统性高估 → 维持现行 +%.2f' % N24_ADJ)

    print('\n  纪律: 本表只记欧冠·不参与判定·不写其它台账（防数据外流）·门槛未达禁改规则')
    return 0


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); return 0
    cmd = args[0]
    if cmd == 'record':
        return cmd_record(args)
    if cmd == 'status':
        return cmd_status(args)
    print(__doc__)
    return 0


if __name__ == '__main__':
    sys.exit(main())
