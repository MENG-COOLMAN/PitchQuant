# -*- coding: utf-8 -*-
"""audit_judgment.py —— **判定层**审计（补 7 个盲区）

🔴 为什么需要它（2026-11-01 覆盖矩阵实证）：
   现有 17 个审计器覆盖「数据层 / 传导层 / 消费层 / 契约层」，
   但 **Step3 / 3.5 / 4 / 4.5 / 4.6 / 7.5 / 9 七步没有任何审计器** →
   这正是「意甲子模型没调」「自检表没做」反复遗漏的结构性根源。

判据：每步必须三态之一
   ✅ PASS  —— 有实质判定留痕（含数值/规则编号）
   ⚪ TRI   —— 显式标注「不适用/无数据 + 原因」
   ❌ MISS  —— 既无留痕也无三态 = 遗漏

用法: python data/tmp/audit_judgment.py --calc <calc输出> [--raw <raw.md>] [--json]
"""
import argparse
import io
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# (编号, 名称, 必含判据[任一命中=有留痕], 三态判据[任一命中=合规不适用])
CHECKS = [
    ('S3', '欧战场景 44/45/46',
     [r'rule5[1-9]', r'rule6\d', r'44[ABCD]', r'欧战基准', r'SL-europe-db'],
     [r'非欧战', r'44\s*不适用', r'欧战.{0,6}不适用']),

    ('S3.5', '情境因子 F1-F7',
     [r'F[1-7][：: ]', r'情境因子', r'疲劳分', r'战意分'],
     [r'情境.{0,10}不触发', r'F1-F7.{0,10}不适用', r'无赛程.{0,10}排名']),

    ('S4', '推论层 26 项',
     [r'修正2[6-9]', r'修正3\d', r'修正4[0-3]', r'推论层', r'战术风格'],
     [r'推论层.{0,10}(不适用|无数据)']),

    ('S4.5', '联赛子模型 SK-league-*',
     [r'SK-league', r'\bR[1-9]\b.*规则', r'R1[0-9]\b', r'联赛子模型',
      r'子模型.{0,12}(校正|规则)'],
     [r'子模型.{0,14}不触发', r'非五大联赛', r'超域.{0,10}仅参考']),

    ('S4.6', 'HAF 主客场因子',
     [r'HAF', r'主客场因子', r'λh_home', r'对抗耦合', r'homeaway'],
     [r'HAF.{0,14}(无数据|缺失|不触发)', r'无主客场档案']),

    ('S7.5', '半场精细反推',
     [r'半场.{0,6}(方向|比分).{0,10}[Top\d主平客]', r'HT-FT', r'_bqc_to_ht_dist',
      r'半场主.{0,4}\d+%'],
     [r'半场.{0,12}(无数据|不可用|不触发)']),

    ('S9', '自检表 22 项',
     [r'自检表', r'□\s*1[\.、 ]', r'self.?check', r'必核清单.*C\d\d'],
     [r'自检.{0,12}(未执行|不适用)']),
]

# 赛后/批末场景（分析时不该要求）
AFTER_MATCH = {'S10.5': '赛后学习', 'S11': '批末压缩/投注方案'}


def _grab(text, pats):
    if not text:
        return None
    for p in pats:
        m = re.search(p, text)
        if m:
            return m.group(0)[:56]
    return None


def check(calc_text, raw_text):
    """🔴 calc 层 vs raw 层**分开判**（2026-11-01）
        calc 有 + raw 有 → PASS（真落地）
        calc 有 + raw 无 → UNCONSUMED（**算了没写 = 模型没消费** ← 我反复遗漏的位置）
        calc 无 + raw 有 → ODD（来源不明·可能是模型自造）
        两无 + 有三态   → TRI（合规不适用）
        两无            → MISS（遗漏）
    """
    res = []
    for cid, name, pats, tri in CHECKS:
        c_hit = _grab(calc_text, pats)
        r_hit = _grab(raw_text, pats)
        if c_hit and r_hit:
            res.append((cid, name, 'PASS', 'calc+raw: %s' % r_hit))
        elif c_hit and not r_hit:
            res.append((cid, name, 'UNCONSUMED',
                        'calc 有(%s) 但 raw 未写' % c_hit[:40]))
        elif r_hit and not c_hit:
            res.append((cid, name, 'ODD', 'raw 有(%s) calc 无' % r_hit[:40]))
        else:
            c_tri = _grab(calc_text, tri) or _grab(raw_text, tri)
            if c_tri:
                res.append((cid, name, 'TRI', c_tri))
            else:
                res.append((cid, name, 'MISS', ''))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--calc')
    ap.add_argument('--raw')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    calc = io.open(a.calc, encoding='utf-8', errors='replace').read() if (a.calc and os.path.exists(a.calc)) else ''
    raw = io.open(a.raw, encoding='utf-8', errors='replace').read() if (a.raw and os.path.exists(a.raw)) else ''
    if not calc and not raw:
        print("❌ 需 --calc 或 --raw（至少一个）")
        return 2

    res = check(calc, raw)
    nmiss = sum(1 for r in res if r[2] == 'MISS')
    npass = sum(1 for r in res if r[2] == 'PASS')
    ntri = sum(1 for r in res if r[2] == 'TRI')
    nunc = sum(1 for r in res if r[2] == 'UNCONSUMED')
    nodd = sum(1 for r in res if r[2] == 'ODD')

    if a.json:
        print(json.dumps({'results': res, 'pass': npass, 'tri': ntri, 'miss': nmiss},
                         ensure_ascii=False))
        return 0 if nmiss == 0 else 1

    print('=' * 100)
    print('判定层审计（audit_judgment）｜ 补 7 个原无审计的步骤')
    print('=' * 100)
    ICON = {'PASS': '✅ 落地', 'TRI': '⚪ 三态', 'MISS': '❌ 遗漏',
            'UNCONSUMED': '🔴 算了没写', 'ODD': '⚠️ 来源不明'}
    for cid, name, st, ev in res:
        print('  %-7s %-26s %-8s %s' % (cid, name, ICON[st], ev[:50]))
    print('-' * 100)
    print('  ✅ 落地 %d ｜ 🔴 算了没写 %d ｜ ⚪ 三态 %d ｜ ❌ 遗漏 %d ｜ ⚠️ 来源不明 %d'
          % (npass, nunc, ntri, nmiss, nodd))
    if nmiss == 0 and nunc == 0:
        print('\n✅ 判定层全落地（calc 算了 → raw 都写了 · 或显式三态）')
    if nunc:
        print('\n🔴 **算了没写**（程序有数值但 raw 没留痕 = 模型未消费）:')
        for cid, name, st, ev in res:
            if st == 'UNCONSUMED':
                print('   %-7s %-24s %s' % (cid, name, ev))
    if nmiss:
        print('\n❌ 遗漏（既无留痕也无三态）:')
        for cid, name, st, _ in res:
            if st == 'MISS':
                print('   %-7s %s' % (cid, name))
    print('\n（赛后场景不审：%s）' % ' / '.join('%s %s' % (k, v) for k, v in AFTER_MATCH.items()))
    return 0 if nmiss == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
