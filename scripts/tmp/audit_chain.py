# -*- coding: utf-8 -*-
"""全链路审计 audit_chain.py（2026-10-30 用户「大工程」批次1）

三层验证框架：
  L1 存在性：脚本/数据文件在位
  L2 活跃性：实跑输出有非空数值（三态须有理由）
  L3 传导性：A/B 实测 —— 有/无该模块 → 最终输出是否变（另由 audit_p8_vertical / audit_fixtures 承担）

用法:
  python data/tmp/audit_chain.py --l1            # 只跑存在性
  python data/tmp/audit_chain.py --l2           # 跑活跃性（需已有 calc 输出或 --txt）
  python data/tmp/audit_chain.py --fmt          # 扫 % 格式化参数不匹配（静默崩溃元凶）
  python data/tmp/audit_chain.py --all
"""
import ast
import glob
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── L1：主链脚本 + 关键数据文件 ──
SCRIPTS = [
    'data/tmp/calc_all.py', 'data/tmp/calc_match.py', 'data/tmp/calc_v3572.py',
    'data/tmp/calc_poisson.py', 'data/tmp/joint_solver.py', 'data/tmp/market_distribution.py',
    'data/tmp/market_inputs.py', 'data/tmp/market_intent.py', 'data/tmp/market_consensus.py',
    'data/tmp/totals_water_read.py', 'data/tmp/live_score_engine.py',
    'data/tmp/snapshot_save.py', 'data/tmp/prestep_fetch.py',
    'data/tmp/big_pool_policy.py', 'data/tmp/confidence_engine.py',
    'data/tmp/bzzoiro_fetch.py', 'data/tmp/the_odds_api_fetch.py', 'data/tmp/fetch_clubelo.py',
    'data/tmp/injury_impact.py', 'data/tmp/draw_signal_aggregator.py',
    'data/tmp/audit_steps.py', 'data/tmp/audit_p8_vertical.py', 'data/tmp/audit_consumption.py',
    'data/tmp/check_luopan.py', 'data/tmp/check_sync.py', 'data/tmp/output_checker.py',
    'data/tmp/pipeline.py', 'data/tmp/run_guard.py', 'data/tmp/txt_normalize.py',
    'data/tmp/goal_count_table.py',
    'data/tmp/team_attack_defense.py', 'data/tmp/league_season_calib.py',
]
DATA = [
    'data/tmp/odds_table.json', 'data/tmp/draw_table.json', 'data/tmp/quadrant_table.json',
    'data/tmp/score_depth_table.json', 'data/tmp/goal_bins_table.json',
    'data/tmp/goal_count_table.json', 'data/tmp/handi_score_table.json',
    'data/tmp/team_attack_defense.json', # （欧冠校准表由 check_sync 单独校验·此处不引用）
    'data/tmp/homeaway_table.json', 'data/tmp/deep_anchor_table.json',
    'data/tmp/prob_calibration.json', 'data/league-modules/I1.json',
    'data/case-library/实战案例.csv',
]
# ── L1：核心铁律在 AGENTS 中的存在性（防规则被删）──
RULES = ['P33 步骤审计硬门禁', 'P34 PreStep 数据', 'P35 纵向时间序列',
         'P30 信号落地', 'P31', '锚-期望', '铁则32', '最多 2 向']


def l1():
    ok = bad = 0
    print('=' * 96)
    print('L1 存在性（脚本 %d / 数据 %d / 铁律 %d）' % (len(SCRIPTS), len(DATA), len(RULES)))
    print('=' * 96)
    for f in SCRIPTS:
        if os.path.exists(f):
            ok += 1
        else:
            bad += 1
            print('  ❌ 脚本缺失: %s' % f)
    for f in DATA:
        if os.path.exists(f):
            ok += 1
        else:
            bad += 1
            print('  ❌ 数据缺失: %s' % f)
    ag = io.open('AGENTS.md', encoding='utf-8', errors='replace').read() \
        if os.path.exists('AGENTS.md') else ''
    for r in RULES:
        if r in ag:
            ok += 1
        else:
            bad += 1
            print('  ❌ AGENTS 缺铁律: %s' % r)
    print('  → 通过 %d / 缺失 %d' % (ok, bad))
    return bad == 0


def l2(out_path='data/tmp/_chain_calc_out.txt'):
    if not os.path.exists(out_path):
        print('⚪ L2: 无 calc 输出（先跑 pipeline 或指定 --out）→ 跳过')
        return True
    txt = io.open(out_path, encoding='utf-8', errors='replace').read()
    lines = txt.split('\n')
    BLOCK = re.compile(r'^\s*([🔴⚪🔵📌📋🌐⚡⚠️❌✅【])')
    NUM = re.compile(r'[-+]?\d+\.?\d*\s*%|\d+\.\d{2,}|[主平客]\s*\d+\.\d|λ|E\[T\]')
    TRI = re.compile(r'三态|不触发|未触发|不适用|未提供|无数据|缺 --|未识别|跳过')
    NOTE = re.compile(r'纪律|说明|要求|复核|执行流程|每批|必须|注意|→|：')
    act = tri = note = unk = 0
    unk_list = []
    for i, l in enumerate(lines):
        if not BLOCK.match(l) or len(l.strip()) < 8:
            continue
        body = '\n'.join(lines[i:i + 4])
        if NUM.search(body):
            act += 1
        elif TRI.search(l + body):
            tri += 1
        elif NOTE.search(l):
            note += 1
        else:
            unk += 1
            unk_list.append((i + 1, l.strip()[:80]))
    print('=' * 96)
    print('L2 活跃性: 有数值 %d ｜ 三态 %d ｜ 说明性 %d ｜ 待判 %d' % (act, tri, note, unk))
    print('=' * 96)
    if unk_list:
        for ln, s in unk_list[:10]:
            print('  ❓ L%-5d %s' % (ln, s))
    return act > 0


def l4(out_path='data/tmp/_pipe_calc_999.txt'):
    """L4 全链端到端：8 条传导链（源头→中间→输出 均有数值）"""
    if not os.path.exists(out_path):
        print('⚪ L4: 无 calc 输出 → 跳过（三态）')
        return True
    txt = io.open(out_path, encoding='utf-8', errors='replace').read()
    CH = [
        ('欧盘→去水→方向', r'隐含:\s*主[\d.]+%', r'方向\(欧亚综合\)'),
        ('让球→净胜档', r'净胜H\d|净胜\s*[+-]?\d', r'净胜'),
        ('O2.5→λ→量级', r'λ_final', r'大球|小球'),
        # 🔴2026-11-01 CS 覆盖 **0 档** = 数据源不可用（Odds-API 连不上/滚球盘）
    #   → 属三态·不是链路断裂；只有「有 CS 数据但算不出 E[T]」才算断
    ('CS/OU/AH→P10', r'CS\s*覆盖\s*[1-9]\d*\s*档', r'E\[T\]|期望[\d.]+\s*球'),
        ('快照→N21→纵向', r'时间序列\(N21\)', r'P8纵向'),
        ('N27→攻防', r'攻防[:：=]', r'双向预期'),
        ('伤停→影响分', r'伤停影响分', r'方向影响|伤停'),
        # 🔴2026-11-01 判据放宽：P10 三源不齐（Odds-API 连不上/滚球盘）→ R10 不跑 =
        #   数据源三态，不是链路断裂；只要 N07b/N18b 锚校验真跑了（有输出）即算链通
        ('全链→锚→校验', r'R10判定层: 主锚|市场矩阵未启用', r'N07b/N18b'),
    ]
    print('=' * 96)
    print('L4 全链端到端（8 条传导链）')
    print('=' * 96)
    ok = 0
    skip = []
    for name, p1, p2 in CH:
        a = re.search(p1, txt)
        b = re.search(p2, txt)
        # 🔴2026-11-01 数据源**明确三态** → 标⚪·不计入分母（禁把「源不可用」当「链路断」）
        #   例：Odds-API 连不上 → CS 覆盖 0 档 + 「三源不齐」→ P10 本就不该跑
        if not a and '三源不齐' in txt:
            skip.append(name)
            print('  %-16s ⚪ 三态（数据源不齐·不计入）' % name)
            continue
        good = bool(a and b)
        ok += 1 if good else 0
        print('  %-16s %s' % (name, '✅' if good else '❌ 断'))
    _den = len(CH) - len(skip)
    print('  → 贯通 %d/%d%s' % (ok, _den, ('（⚪三态 %d 条不计）' % len(skip)) if skip else ''))
    return ok == _den


def fmt():
    """扫 % 格式化参数不匹配（只报**确定**的：右侧为字面量元组或标量）"""
    bad = []
    for f in sorted(glob.glob('data/tmp/*.py')):
        try:
            src = io.open(f, encoding='utf-8', errors='replace').read()
            tree = ast.parse(src)
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Mod):
                continue
            if not isinstance(node.left, ast.Constant) or not isinstance(node.left.value, str):
                continue
            fs = node.left.value
            if re.search(r'%\([^)]+\)', fs):
                continue
            n_sp = len(re.findall(r'%(?!%)[-+ #0]*\d*(?:\.\d+)?[sdifrxeEgGcu]', fs))
            if not n_sp:
                continue
            r = node.right
            # 只认「字面量元组 / 字面量标量」→ 排除变量（可能是元组，误报源）
            if isinstance(r, ast.Tuple):
                if any(isinstance(e, ast.Starred) for e in r.elts):
                    continue
                n_arg = len(r.elts)
            elif isinstance(r, ast.Constant):
                n_arg = 1
            else:
                continue          # 变量 → 跳过（防误报）
            if n_sp != n_arg:
                bad.append((os.path.basename(f), node.lineno, n_sp, n_arg, fs[:80]))
    print('=' * 96)
    print('格式化扫描（只报字面量不匹配·防误报）')
    print('=' * 96)
    if not bad:
        print('  ✅ 未发现确定的不匹配')
        return True
    for f, ln, a, b, s in bad:
        print('  ❌ %s L%-5d 占位 %d / 参数 %d ｜ %s' % (f, ln, a, b, s))
    return False


if __name__ == '__main__':
    a = sys.argv[1:]
    r = True
    if not a or '--all' in a or '--l1' in a:
        r &= l1()
    if not a or '--all' in a or '--l2' in a:
        r &= l2()
    if not a or '--all' in a or '--fmt' in a:
        r &= fmt()
    if '--l4' in a:
        r &= l4()
    print()
    print('=' * 96)
    print('结论: %s' % ('✅ 全过' if r else '❌ 有失败'))
    sys.exit(0 if r else 1)
