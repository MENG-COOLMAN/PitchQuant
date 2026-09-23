# -*- coding: utf-8 -*-
"""P2 案例库 strict 口径校准（2026-09-20·含 strict 完美口径）

从 CSV 推导 strict/any 双口径 + strict 完美（不改列·脚本推导）→ 输出置信度校准表 + 落盘跟踪文件
strict = 实际 ∈ {主方向}（预测方向列的第一项）· any = 实际 ∈ 全部列出方向
🔴 案例库「完美」列 = case_write 的 any 口径；规范定义 = strict✅+锚✅ → 本脚本同时输出两者
"""
import csv, re, sys, os
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')

BASE = 'C:/Users/12242/AppData/Roaming/reasonix/global-workspace/data'
RES2CN = {'H': '主胜', 'D': '平局', 'A': '客胜'}


def parse_pred(s):
    """'客胜+平局并列' / '主胜(平参考)' / '平局+客胜并列' → [主方向, ...次方向]"""
    s = s.replace('（', '(').split('(')[0]
    out = []
    for tok in re.split(r'[+·/、]', s):
        t = tok.strip()
        for k in ('主胜', '平局', '客胜'):
            if k in t and k not in out:
                out.append(k)
    return out


def main():
    rows = list(csv.reader(open(BASE + '/case-library/实战案例.csv', encoding='utf-8', errors='ignore')))
    data = [r for r in rows[1:] if len(r) >= 12 and r[0].strip().isdigit()]
    recs = []
    for r in data:
        real = r[7].strip()
        if not re.match(r'^\d+:\d+$', real):
            continue
        h, a = map(int, real.split(':'))
        actual = '主胜' if h > a else ('平局' if h == a else '客胜')
        preds = parse_pred(r[5])
        if not preds:
            continue
        strict = 1 if actual == preds[0] else 0
        any_ = 1 if actual in preds else 0
        score = 1 if r[9].strip() in ('是', '✅') else 0
        perf = 1 if r[10].strip() in ('是', '✅') else 0
        recs.append(dict(case=r[0].strip(), league=r[2].strip(), conf=r[11].strip() or '?',
                         pred='+'.join(preds), actual=actual, strict=strict, any=any_, score=score, perf=perf))
    n = len(recs)
    print('已复盘案例 n=%d（含预测方向+真实比分）' % n)
    st = sum(r['strict'] for r in recs)
    an = sum(r['any'] for r in recs)
    sc = sum(r['score'] for r in recs)
    pf = sum(r['perf'] for r in recs)
    spf = sum(1 for r in recs if r['strict'] and r['score'])
    print('双口径: strict %d/%d=%.1f%% · any %d=%.1f%% · 比分锚 %d=%.1f%% · 完美any %d=%.1f%% · 🔴完美strict %d=%.1f%%' % (
        st, n, 100.0 * st / n, an, 100.0 * an / n, sc, 100.0 * sc / n, pf, 100.0 * pf / n, spf, 100.0 * spf / n))
    print('🔴口径说明: 案例库「完美」列 = case_write 的 **any 口径**（方向any✅+比分✅）；模型规范定义为 **strict✅+锚✅** → 两者差 %d 场（any 虚高）' % (pf - spf))

    print('\n-- 置信度校准（三口径对照·标称 vs 实际 strict）--')
    std = {'HIGH': (70, 100), 'MID': (55, 70), 'MID-HIGH': (55, 70), 'MID-LOW': (45, 55), 'LOW': (0, 45)}
    byc = defaultdict(lambda: [0, 0, 0, 0])
    for r in recs:
        b = byc[r['conf']]
        b[0] += 1
        b[1] += r['strict']
        b[2] += r['any']
        b[3] += r['score']
    lines = ['置信度,n,strict,any,比分锚,标称区间,校准判定']
    print('%-10s %5s %9s %9s %9s   %s' % ('置信度', 'n', 'strict', 'any', '比分锚', '标称/判定'))
    for c, (t, s_, a_, sc_) in sorted(byc.items(), key=lambda kv: -kv[1][0]):
        lo, hi = std.get(c, (0, 100))
        sr = 100.0 * s_ / t
        ok = '✅在区间' if lo <= sr <= hi else ('⚠️低于' if sr < lo else '⚠️高于')
        print('%-10s %5d %8.1f%% %8.1f%% %8.1f%%   %s / %s' % (c, t, sr, 100.0 * a_ / t, 100.0 * sc_ / t, '%d-%d%%' % (lo, hi), ok))
        lines.append('%s,%d,%.1f,%.1f,%.1f,%d-%d,%s' % (c, t, sr, 100.0 * a_ / t, 100.0 * sc_ / t, lo, hi, ok.replace('✅', '').replace('⚠️', '')))

    print('\n-- 按联赛（strict）--')
    byl = defaultdict(lambda: [0, 0])
    for r in recs:
        byl[r['league']][0] += 1
        byl[r['league']][1] += r['strict']
    for l, (t, h) in sorted(byl.items(), key=lambda kv: -kv[1][0])[:8]:
        print('  %-10s n=%3d strict %5.1f%%' % (l, t, 100.0 * h / t))

    p = BASE + '/case-library/置信度校准.csv'
    open(p, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('\n✅ 已落盘: data/case-library/置信度校准.csv（脚本 data/tmp/conf_calib.py 重跑更新）')


if __name__ == '__main__':
    main()
