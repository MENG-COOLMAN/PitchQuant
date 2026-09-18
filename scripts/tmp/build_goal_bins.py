# -*- coding: utf-8 -*-
"""build_goal_bins.py — 生成 goal_bins_table.json（总进球档查表·Step6/Step7 量级消费）

数据源: data/Matches.csv（有 Over25 赔率且有比分的全部场次）
统计: 按 O2.5 赔率分档 → 0-1/2/3/4+球分布 + 净胜3+率 + 典型比分 Top-N
版本: v2（2026-09-15·大小球精细化升级）
  · 全量样本（此前表为 8 万场子集）
  · 保留细分档（1.0-1.3 与 1.3-1.5 差异 11.3pp·合并损失精度）
  · 新增 top 字段（典型比分 Top4·供候选池分配）
  · 末档改为开区间 2.60-99.00（修旧表 3.2 上限越界归并）
用法: python data/tmp/build_goal_bins.py [--out data/tmp/goal_bins_table.json]
"""
import sys, os, csv, json, argparse
from collections import Counter

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(os.path.dirname(HERE))
MATCHES = os.path.join(BASE, 'data', 'Matches.csv')

# 档位边界（细分·保留 1.0-1.3 精度）
BANDS = [
    ('1.00-1.30', 1.00, 1.30),
    ('1.30-1.50', 1.30, 1.50),
    ('1.50-1.70', 1.50, 1.70),
    ('1.70-1.90', 1.70, 1.90),
    ('1.90-2.10', 1.90, 2.10),
    ('2.10-2.30', 2.10, 2.30),
    ('2.30-2.60', 2.30, 2.60),
    ('2.60-99.00', 2.60, 99.00),
]


def band_of(o):
    for name, lo, hi in BANDS:
        if lo <= o < hi:
            return name
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(HERE, 'goal_bins_table.json'))
    ap.add_argument('--top', type=int, default=4)
    a = ap.parse_args()

    agg = {name: {'n': 0, 'g01': 0, 'g2': 0, 'g3': 0, 'g4': 0, 'net3': 0, 'scores': Counter()}
           for name, _, _ in BANDS}
    total = 0
    with open(MATCHES, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            try:
                o = float(row['Over25'])
                fh = float(row['FTHome']); fa = float(row['FTAway'])
            except (TypeError, ValueError):
                continue
            if o <= 1.0 or o > 100:
                continue
            b = band_of(o)
            if b is None:
                continue
            g = fh + fa
            d = abs(fh - fa)
            s = agg[b]
            s['n'] += 1
            if g <= 1:
                s['g01'] += 1
            elif g == 2:
                s['g2'] += 1
            elif g == 3:
                s['g3'] += 1
            else:
                s['g4'] += 1
            if d >= 3:
                s['net3'] += 1
            s['scores']['%d:%d' % (int(fh), int(fa))] += 1
            total += 1

    out = {}
    for name, _, _ in BANDS:
        s = agg[name]
        n = s['n']
        if not n:
            continue
        top = [[k, round(v / n * 100, 1)] for k, v in s['scores'].most_common(a.top)]
        out[name] = {
            'n': n,
            'g01': round(s['g01'] / n * 100, 1),
            'g2': round(s['g2'] / n * 100, 1),
            'g3': round(s['g3'] / n * 100, 1),
            'g4': round(s['g4'] / n * 100, 1),
            'net3': round(s['net3'] / n * 100, 1),
            'top': top,
        }
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print('样本: %d 场 (Matches 有 O2.5 赔率+比分全部)' % total)
    print('%-12s %8s %7s %7s %7s %7s %7s  %s' % ('档位', 'n', '0-1', '2', '3', '4+', '净3+', 'Top4'))
    for k, v in out.items():
        print('%-12s %8d %6.1f%% %6.1f%% %6.1f%% %6.1f%% %6.1f%%  %s'
              % (k, v['n'], v['g01'], v['g2'], v['g3'], v['g4'], v['net3'],
                 ' '.join('%s(%.1f%%)' % (s, p) for s, p in v['top'])))
    print('\n已写入: %s' % a.out)


if __name__ == '__main__':
    main()
