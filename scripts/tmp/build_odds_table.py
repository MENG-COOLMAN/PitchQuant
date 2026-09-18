# -*- coding: utf-8 -*-
"""赔率档查表生成（2026-08-24·rule56/57/60 防手算·结构性机制）
用法: python build_odds_table.py [联赛key]  # 缺省=五大联赛全部
从 Matches.csv 按主胜赔率档统计: 实际H/D/A率·大球率(O2.5)·净胜1球/2+/3+率·主胜档实际映射
输出: data/tmp/odds_table.json（模型分析时查表·不手算/不凭记忆）
"""
import csv, json, sys

# GBK console guard (2026-09-15)
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from collections import defaultdict

DIVS = {'E0': '英超', 'SP1': '西甲', 'D1': '德甲', 'I1': '意甲', 'F1': '法甲'}
BANDS = [(0, 1.30, '<1.30超深盘'), (1.30, 1.50, '1.30-1.50深盘'), (1.50, 1.80, '1.50-1.80中深'),
         (1.80, 2.10, '1.80-2.10中盘'), (2.10, 2.50, '2.10-2.50中浅'), (2.50, 3.00, '2.50-3.00浅盘'),
         (3.00, 99, '3.00+均势')]

def band(o):
    for lo, hi, name in BANDS:
        if lo <= o < hi:
            return name
    return '?'

def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    agg = defaultdict(lambda: {'n': 0, 'H': 0, 'D': 0, 'A': 0, 'O25': 0, 'nO25': 0, 'net1': 0, 'net2': 0, 'net3': 0, 'goals': 0})
    with open('data/Matches.csv', encoding='utf-8-sig', errors='replace') as f:
        r = csv.DictReader(f)
        for row in r:
            div = row.get('Division', '')
            if div not in DIVS:
                continue
            if only and div != only:
                continue
            try:
                oh = float(row['OddHome'])
                res = row['FTResult']
                fh = float(row['FTHome']); fa = float(row['FTAway'])
            except (ValueError, KeyError, TypeError):
                continue
            b = band(oh)
            key = (div, b)
            agg[key]['n'] += 1
            agg[key][res if res in 'HDA' else ('H' if fh > fa else ('A' if fh < fa else 'D'))] += 1
            o25 = row.get('Over25', '')
            if o25:
                agg[key]['nO25'] += 1
            # 实际大球率: 总进球≥3(与赔率值无关·用赛果统计)
            if fh + fa >= 3:
                agg[key]['O25'] += 1
            net = fh - fa
            agg[key]['goals'] += fh + fa
            if net >= 1: agg[key]['net1'] += 1
            if net >= 2: agg[key]['net2'] += 1
            if net >= 3: agg[key]['net3'] += 1
    out = {}
    for (div, b), s in sorted(agg.items()):
        if s['n'] < 100:
            continue
        out[f"{DIVS[div]}|{b}"] = {
            'n': s['n'],
            'H': round(s['H']/s['n']*100, 1), 'D': round(s['D']/s['n']*100, 1), 'A': round(s['A']/s['n']*100, 1),
            'O25': round(s['O25']/s['nO25']*100, 1) if s['nO25'] else 0, 'nO25': s['nO25'],
            'net1': round(s['net1']/s['n']*100, 1), 'net2': round(s['net2']/s['n']*100, 1), 'net3': round(s['net3']/s['n']*100, 1),
            'avg_goals': round(s['goals']/s['n'], 2),
        }
    json.dump(out, open('data/tmp/odds_table.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"生成 data/tmp/odds_table.json · {len(out)} 档位")
    # 打印样例（英超 1.30-1.50 等核心档）
    for k, v in list(out.items())[:12]:
        print(f"  {k}: n={v['n']} H/D/A={v['H']}/{v['D']}/{v['A']}% O25={v['O25']}%(n={v['nO25']}) net1/2/3={v['net1']}/{v['net2']}/{v['net3']}% 均球{v['avg_goals']}")

if __name__ == '__main__':
    main()
