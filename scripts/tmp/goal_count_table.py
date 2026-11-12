# -*- coding: utf-8 -*-
"""goal_count_table.py — 进球数细分表（2026-10-21·用户指令「今晚这种极端大球/大球盘实际小球市场能否反映」）

## 为什么需要这张表

`goal_bins_table.json` 只给 **4 档聚合**（0-1球 / 2球 / 3球 / 4+球），
而实测（Matches 148,396 场）显示 **4+ 球内部差异极大**：

  O2.5 ≤1.20 档:  1球 5.7% | 2球 12.1% | 3球 14.6% | 4球 20.4% | 5球 **21.7%** | 6球 9.6% | 7+球 **15.3%**
  → 「4+球 59.2%」这个聚合值掩盖了「5 球 21.7% / 7+球 15.3%」的厚尾
  → 模型据此只能锚到 2:2 / 1:2 这类 4 球型，而该档众数其实是 **5 球**

## 实测核心结论（148,396 场·O2.5 原始赔率分档）

  ① **市场能反映「方向」**：各档 市场隐含大球 vs 实际大球 校准差 **−1.3 ~ +1.8pp**（≤2pp）
     → 「这场是不是大球」没有可利用偏差
  ② **市场不能反映「幅度」**：同档内 3/4/5/6+ 球概率同量级（相差 ≤7pp）→ 单场不可预测
  ③ **「大球盘实际小球」= 该档固有概率**：1.40-1.50 档打 ≤2 球 **34.2%**（非市场失灵）
  ④ 🔴 **低分出口应按档选**（本表新规则）:
       O2.5 **≤1.70（大球侧）→ 低分优选「2 球」**（1.40-1.50 档: 2球 19.8% > 0-1球 14.4%）
       O2.5 **>1.70（小球侧）→ 低分优选「0-1 球」**（2.10-2.50 档: 0-1球 32.5% > 2球 27.0%）
     → **分界点 1.70 恰为 AGENTS 既有「大球强阈值」O25<1.70**（口径自动对齐·非新增阈值）
  ⑤ 🔴 **最大档（众数）按档递降**:
       ≤1.20 → **5 球** ｜ 1.20-1.30 → **4 球** ｜ 1.30-1.50 → **3 球** ｜ ≥1.50 → **2 球**

## 用法

    python data/tmp/goal_count_table.py build     # 从 Matches.csv 重建 goal_count_table.json
    python data/tmp/goal_count_table.py show      # 打印表
    python data/tmp/goal_count_table.py lookup 1.141   # 查某 O2.5 的细分分布

## 消费纪律

- 本表**只决定「开哪些进球档候选 / 低分出口选哪个档」**，**不改 L2 硬核方向**
- 与 `goal_bins_table.json`（4 档聚合·`calc_v3572.goal_bin_probs`）**并存互补**：聚合表定量级中心，本表定候选谱系与出口
- 极端档（≤1.30）**必须打开 5-6 球候选**（5球+6球+7+ 合计 36.6% @≤1.20），否则尾部结构性缺失
- 禁止把本表概率当「单场预测」—— 同档内 3-6 球概率接近，只有「方向 + 尾部是否存在」可用
"""
import csv
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))
MATCHES = os.path.join(ROOT, 'data', 'Matches.csv')
OUT = os.path.join(_HERE, 'goal_count_table.json')

# 档边界（上界，含）·最后一档开区间
BOUNDS = [1.20, 1.30, 1.40, 1.50, 1.70, 2.10, 2.50]
LABELS = ['<=1.20', '1.20-1.30', '1.30-1.40', '1.40-1.50',
          '1.50-1.70', '1.70-2.10', '2.10-2.50', '>2.50']
LOW_CUT = 1.70   # 🔴低分优选的档位分界 = AGENTS 既有「大球强阈值」


def band_of(o25):
    for i, b in enumerate(BOUNDS):
        if o25 <= b:
            return LABELS[i]
    return LABELS[-1]


def build():
    buckets = {lb: [] for lb in LABELS}
    with open(MATCHES, encoding='utf-8', errors='replace') as f:
        for r in csv.DictReader(f):
            try:
                o = float(r['Over25'])
                u = float(r['Under25'])
                t = int(float(r['FTHome'])) + int(float(r['FTAway']))
            except Exception:
                continue
            if o <= 1.0 or u <= 1.0:
                continue
            buckets[band_of(o)].append(t)

    bands = {}
    for lb, g in buckets.items():
        n = len(g)
        if n < 50:
            bands[lb] = {'n': n, 'skip': '样本<50·不采用'}
            continue
        p = {str(k): round(sum(1 for x in g if x == k) / n * 100, 1) for k in range(7)}
        p['7+'] = round(sum(1 for x in g if x >= 7) / n * 100, 1)
        low01 = round(p['0'] + p['1'], 1)
        mode_k = max(list(range(7)) + ['7+'],
                     key=lambda k: p[str(k)] if str(k) in p else p['7+'])
        low_pick = '2球' if p['2'] > low01 else '0-1球'
        bands[lb] = {
            'n': n,
            'p': p,
            'mode': ('%s球' % mode_k) if mode_k != '7+' else '7+球',
            'mode_pct': p[str(mode_k)] if str(mode_k) in p else p['7+'],
            'low01_pct': low01,
            'low2_pct': p['2'],
            'low_pick': low_pick,
            'low_pick_pct': max(low01, p['2']),
            'tail6_pct': round(p['6'] + p['7+'], 1),
            'over25_pct': round(sum(1 for x in g if x >= 3) / n * 100, 1),
        }

    doc = {
        'generated': '2026-10-21',
        'source': 'data/Matches.csv · O2.5/U2.5 有效 148,396 场（五大+英冠等 Division 全量）',
        'note': ('与 goal_bins_table.json（4档聚合）并存互补: 聚合表定量级中心, 本表定候选谱系与低分出口。'
                 '单场不可预测——同档内 3/4/5/6+ 球概率同量级，只有「方向」与「尾部是否存在」可用。'),
        'low_cut': LOW_CUT,
        'rule': {
            'low_pick': 'O2.5 <=1.70（大球侧）→ 低分优选 2 球（1:1/2:0/0:2）；O2.5 >1.70（小球侧）→ 低分优选 0-1 球（0:0/1:0/0:1）',
            'mode_use': '最大档（众数）用于定量级中心; 极端档（<=1.30）须同时打开 5-6 球候选（tail6_pct）',
            'hard': '只定候选谱系/出口·不改 L2 硬核方向',
        },
        'bands': bands,
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    return doc


def _load():
    if not os.path.exists(OUT):
        return build()
    with open(OUT, encoding='utf-8') as f:
        return json.load(f)


def lookup(o25):
    """O2.5 赔率 → 本档细分分布（供 calc_all 消费）"""
    d = _load()
    lb = band_of(float(o25))
    b = (d.get('bands') or {}).get(lb) or {}
    out = {'band': lb, 'n': b.get('n'), 'ok': bool(b.get('p'))}
    if not out['ok']:
        out['reason'] = b.get('skip', '无本档数据')
        return out
    out.update({
        'p': b['p'],
        'mode': b['mode'], 'mode_pct': b['mode_pct'],
        'low_pick': b['low_pick'], 'low_pick_pct': b['low_pick_pct'],
        'low01_pct': b['low01_pct'], 'low2_pct': b['low2_pct'],
        'tail6_pct': b['tail6_pct'], 'over25_pct': b['over25_pct'],
        'tail_required': float(b['tail6_pct']) >= 10.0,
    })
    return out


def show():
    d = _load()
    print('进球数细分表（goal_count_table.json）generated=%s' % d['generated'])
    print('  源: %s' % d['source'])
    print()
    print('  档            n     | 0球  1球  2球  3球  4球  5球  6球  7+球 | 众数 | 低分优选 | 6+球尾部')
    for lb in LABELS:
        b = (d['bands'] or {}).get(lb) or {}
        if not b.get('p'):
            print('  %-12s %5s | %s' % (lb, b.get('n', '-'), b.get('skip', '无')))
            continue
        p = b['p']
        print('  %-12s %5d | ' % (lb, b['n'])
              + ' '.join('%4.1f' % p[str(k)] for k in range(7))
              + ' %4.1f | %-4s | %-7s | %4.1f%%'
              % (p['7+'], b['mode'], b['low_pick'], b['tail6_pct']))
    print()
    print('  🔴规则: %s' % d['rule']['low_pick'])
    print('  🔴规则: %s' % d['rule']['mode_use'])
    print('  🔴铁律: %s' % d['rule']['hard'])


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'show'
    if cmd == 'build':
        d = build()
        print('✅ 已生成 %s（%d 档）' % (OUT, len(d['bands'])))
        show()
    elif cmd == 'show':
        show()
    elif cmd == 'lookup':
        o = float(sys.argv[2]) if len(sys.argv) > 2 else 1.40
        r = lookup(o)
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
