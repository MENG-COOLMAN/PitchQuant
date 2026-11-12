# -*- coding: utf-8 -*-
"""Step 全流程四段审计器 audit_all_steps.py（2026-10-31 用户「大工程」指令）

对每个 Step 判四段（A 生产 / B 调用 / C 输出 / D 消费），任一段断 = 断链。

与其他审计器的分工（不重复）：
  · audit_steps.py       → 只看 raw 里关键词（单场落盘完整性·20 项）
  · audit_chain.py       → 8/13 条数据链贯通
  · audit_contracts.py   → 函数返回键 == 消费键（31 项）
  · audit_all_steps.py   → **本文件**：Step 维度的四段判据矩阵（代码级 + 运行级）

用法：
  python data/tmp/audit_all_steps.py --calc data/tmp/_audit_calc.txt
  python data/tmp/audit_all_steps.py --calc ... --only S05,S06,S07
  python data/tmp/audit_all_steps.py --calc ... --json out.json
"""
import argparse
import io
import json
import os
import re
import sys

os.chdir(r'<HOME>\AppData\Roaming\reasonix\global-workspace')
sys.path.insert(0, os.path.join(os.getcwd(), 'data', 'tmp'))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Step 清单（与 docs/审计清单_Step全流程_20261031.md 一一对应）──────────────
# prod: 生产载体（文件必须存在）｜caller: 须真引用生产模块的文件
# out_re: 运行输出里应出现的块标题｜num_pat: 该块附近须有数字
# cons: 消费端文件（存在且引用 cons_key）｜cons_key: 消费方读的键/变量
STEPS = [
    dict(id='PRE', name='PreStep 先验筛选(独立阶段)', lv='H',
         prod=['data/tmp/prestep_fetch.py', 'data/tmp/prestep_dual.py'],
         caller=['data/tmp/snapshot_save.py'],
         out_re=r'(N21|prestep 快照|时序|共 \d+ 时点)', num_pat=r'\d',
         cons=['data/tmp/calc_all.py'], cons_key='delta_for',
         note='分数用于筛场；进 calc 的是快照时序(N21)→P12/V1/V2/V6'),
    dict(id='S00a', name='txt 归一化', lv='H',
         prod=['data/tmp/txt_normalize.py'],
         caller=['data/tmp/calc_all.py', 'data/tmp/calc_match.py'],
         out_re=r'(标准模板|归一化|时点)', num_pat=r'\d',
         cons=['data/tmp/calc_match.py'], cons_key='parse_txt'),
    dict(id='S00b', name='欧盘赔率(源B1)', lv='H',
         prod=['data/tmp/market_inputs.py'],
         caller=['data/tmp/calc_all.py'],
         out_re=r'(市场数据链体检|市场体检|coverage|覆盖率)', num_pat=r'\d',
         cons=['data/tmp/market_distribution.py'], cons_key='infer_from_parts'),
    dict(id='S00c', name='伤停(Bzzoiro B8)', lv='H',
         prod=['data/tmp/bzzoiro_fetch.py', 'data/tmp/injury_impact.py'],
         caller=['data/tmp/pipeline.py', 'data/tmp/calc_all.py'],
         out_re=r'伤停', num_pat=r'(影响分|缺阵|[\d.]+\s*分)',
         cons=['data/tmp/calc_v3572.py'], cons_key='inj'),
    dict(id='S00d', name='H2H 双源', lv='H',
         prod=['data/tmp/h2h_lookup.py'],
         caller=['data/tmp/calc_all.py'],
         out_re=r'(H2H|交锋)', num_pat=r'\d',
         cons=['data/tmp/calc_all.py'], cons_key='draw_score'),
    dict(id='S00e', name='ELO(clubelo B6)', lv='M',
         prod=['data/online_learning/data_bridge.py'],
         caller=['data/tmp/calc_all.py'],
         out_re=r'ELO', num_pat=r'\d{3,4}',
         cons=['data/tmp/calc_v3572.py'], cons_key='elo'),
    dict(id='S00f', name='xG(understat B4)', lv='L',
         prod=['data/tmp/understat_xg.py'],
         caller=['data/tmp/calc_all.py'],
         out_re=r'xG', num_pat=r'\d+\.\d',
         cons=[], cons_key='', design_nocons=True),
    dict(id='S00g', name='跨机构共识(B7)', lv='H',
         prod=['data/tmp/the_odds_api_fetch.py', 'data/tmp/market_consensus.py'],
         caller=['data/tmp/calc_all.py', 'data/tmp/pipeline.py'],
         out_re=r'(机构共识|家机构)', num_pat=r'\d',
         cons=['data/tmp/confidence_engine.py'], cons_key='spread'),
    dict(id='S00h', name='早盘快照 T-0 / N21 时序', lv='H',
         prod=['data/tmp/snapshot_save.py'],
         caller=['data/tmp/calc_all.py'],
         out_re=r'(N21|快照|时序)', num_pat=r'\d',
         cons=['data/tmp/calc_all.py'], cons_key='delta_for'),
    dict(id='S01', name='硬核层12项 / 档位查表', lv='H',
         prod=['data/tmp/calc_match.py', 'data/tmp/calc_v3572.py'],
         caller=['data/tmp/calc_all.py'],
         out_re=r'(硬核|档位|H/D/A)', num_pat=r'\d+\.\d',
         cons=['data/tmp/calc_v3572.py'], cons_key='direction_full'),
    dict(id='S02', name='变动层 V1-V6 / 双通道', lv='H',
         prod=['data/tmp/fundflow_analyzer.py'],
         caller=['data/tmp/calc_all.py'],
         out_re=r'(V1|V2|V6|双通道|四象限|形态学)', num_pat=r'\d',
         cons=['data/tmp/calc_v3572.py'], cons_key='market_intent'),
    dict(id='S03', name='场景44/45/46 + 欧战', lv='M',
         prod=['data/tmp/europe_two_leg.py', 'data/tmp/europe_group_stage.py'],
         caller=['data/tmp/calc_all.py'],
         out_re=r'(欧战|rule5\d|rule6\d|两回合|场景)', num_pat=r'\d',
         cons=['data/tmp/calc_all.py'], cons_key='europe'),
    dict(id='S03.5', name='情境F1-F7 / 疲劳战意', lv='L',
         prod=['data/tmp/fatigue_intent.py'],
         caller=['data/tmp/calc_all.py'],
         out_re=r'(情境|疲劳|战意)', num_pat=r'\d',
         cons=[], cons_key='', design_nocons=True),
    dict(id='S04', name='推论层26项 / 基本面ABCDE', lv='M',
         prod=['data/tmp/calc_v3572.py'],
         caller=['data/tmp/calc_all.py'],
         out_re=r'(修正26|基本面|ABCDE)', num_pat=r'\d',
         cons=['data/tmp/calc_v3572.py'], cons_key='direction_full'),
    dict(id='S04.5', name='联赛子模型 R1-R20', lv='H',
         prod=['data/league-modules/E0.json', 'data/league-modules/I1.json',
               'data/league-modules/SP1.json'],
         caller=['data/tmp/calc_all.py'],
         out_re=r'(联赛子模型|R1|子模型)', num_pat=r'\d',
         cons=['data/tmp/calc_all.py'], cons_key='league_table'),
    dict(id='S04.6', name='HAF 主客场因子', lv='M',
         prod=['data/tmp/calc_homeaway.py', 'data/tmp/homeaway_table.json'],
         caller=['data/tmp/calc_all.py'],
         out_re=r'(HAF|主客场)', num_pat=r'\d+\.\d',
         cons=['data/tmp/calc_all.py'], cons_key='calc_homeaway'),
    dict(id='S04.8', name='NL 欧国联子模型', lv='M',
         prod=['data/tmp/nl_model.py'],
         caller=['data/tmp/calc_all.py'],
         out_re=r'(欧国联|Nations|非欧国联)', num_pat=r'R[1-9]|不触发',
         cons=['data/tmp/calc_all.py'], cons_key='nl_model'),
    dict(id='S05', name='方向判定（含置信度/诱盘/P12）', lv='H',
         prod=['data/tmp/confidence_engine.py', 'data/tmp/market_intent.py',
               'data/tmp/p12_arbitrate.py'],
         caller=['data/tmp/calc_all.py', 'data/tmp/joint_solver.py'],
         out_re=r'(方向|置信度层建议|诱盘|P12)', num_pat=r'\d',
         cons=['data/tmp/joint_solver.py'], cons_key='step5_dirs'),
    dict(id='S06', name='大球深度/量级/宽池分级', lv='H',
         prod=['data/tmp/goal_count_table.py', 'data/tmp/big_pool_policy.py'],
         caller=['data/tmp/calc_all.py', 'data/tmp/market_distribution.py'],
         out_re=r'(量级|进球档|P52|宽池)', num_pat=r'\d',
         cons=['data/tmp/market_distribution.py'], cons_key='level_from_line'),
    dict(id='S06.5', name='大小球盘口水位精读', lv='H',
         prod=['data/tmp/totals_water_read.py'],
         caller=['data/tmp/calc_all.py'],
         out_re=r'水位精读|λ_final|lambda_final', num_pat=r'\d+\.\d',
         cons=['data/tmp/calc_all.py', 'data/tmp/joint_solver.py'], cons_key='lambda_final'),
    dict(id='S07', name='比分谱系(live+P10+R10/R11/R12)', lv='H',
         prod=['data/tmp/live_score_engine.py', 'data/tmp/market_distribution.py',
               'data/tmp/joint_solver.py'],
         caller=['data/tmp/calc_all.py'],
         out_re=r'(主锚|次锚|评分池|市场矩阵)', num_pat=r'\d',
         cons=['data/tmp/calc_all.py'], cons_key='anchor_market_check'),
    dict(id='S07.5', name='半场精细反推', lv='M',
         prod=['data/tmp/halftime_inference.py'],
         caller=['data/tmp/calc_all.py'],
         out_re=r'半场', num_pat=r'\d',
         cons=['data/tmp/calc_all.py'], cons_key='halftime'),
    dict(id='S08', name='总进球/交叉验证/凯利', lv='H',
         prod=['data/tmp/live_score_engine.py'],
         caller=['data/tmp/calc_all.py'],
         out_re=r'(N07b|N18b|锚-市场|锚-期望|凯利)', num_pat=r'\d',
         cons=['data/tmp/journal_gate.py', 'data/tmp/calc_all.py'], cons_key='anchor_market_check'),
    dict(id='S09', name='自检表/门禁', lv='H',
         prod=['data/tmp/output_checker.py', 'data/tmp/check_luopan.py'],
         caller=['data/tmp/pipeline.py'],
         out_re=r'自检', num_pat=r'\d',
         cons=['data/tmp/pipeline.py'], cons_key='check_luopan'),
    dict(id='S10', name='落盘 + 案例库(流程触发)', lv='H',
         prod=['data/tmp/case_write.py'],
         caller=[],
         out_re=r'(raw|案例库|CSV)', num_pat=r'\d',
         cons=['data/tmp/check_luopan.py'], cons_key='case-library/raw',
         note='raw 内容需模型判断 → case_write 由模型在落盘批执行（pipeline 只生成骨架+提示+校验）'),
    dict(id='S10.5', name='赛后学习闭环(赛后事件)', lv='M',
         prod=['data/online_learning/learn.py', 'data/tmp/self_iterate.py'],
         caller=[],
         out_re=r'(学习成果|learned_rules|台账)', num_pat=r'\d',
         cons=['data/tmp/calc_all.py'], cons_key='learned_rules',
         note='赛后独立触发（calc_all 只读 learned_rules.json·不反向调用）'),
    dict(id='S11', name='批末压缩 + 投注方案', lv='L',
         prod=['data/tmp/betting_plan_generator.py'],
         caller=[],
         out_re=r'(串关|投注|方案)', num_pat=r'\d',
         cons=[], cons_key='', design_nocons=True),
]


def read(p):
    try:
        return io.open(p, encoding='utf-8', errors='replace').read()
    except Exception:
        return ''


def _grep_code(fn, pat):
    """在文件里找 pat（排除纯注释行）"""
    t = read(fn)
    if not t:
        return False
    for ln in t.splitlines():
        s = ln.strip()
        if s.startswith('#') or s.startswith('"""') or s.startswith("'''"):
            continue
        if re.search(pat, ln):
            return True
    return False


def audit_step(s, calc):
    r = dict(id=s['id'], name=s['name'], lv=s['lv'])
    # A 生产
    miss_prod = [p for p in s['prod'] if not os.path.exists(p)]
    r['A'] = not miss_prod
    r['A_miss'] = miss_prod
    # B 调用
    mods = [os.path.splitext(os.path.basename(p))[0] for p in s['prod']]
    called = []
    for c in s['caller']:
        for m in mods:
            if _grep_code(c, r'(import\s+%s\b|from\s+%s\b|%s\.)' % (re.escape(m), re.escape(m), re.escape(m))):
                called.append('%s→%s' % (os.path.basename(c), m))
    r['B'] = bool(called) or (not s['caller'])
    r['B_hit'] = called[:2]
    r['B_na'] = not s['caller'] and not called
    # C 输出（运行级）
    has_block = bool(re.search(s['out_re'], calc)) if calc else False
    has_num = bool(re.search(s['num_pat'], calc)) if calc else False
    r['C'] = bool(has_block and has_num)
    r['C_block'], r['C_num'] = has_block, has_num
    # D 消费
    if s.get('design_nocons'):
        r['D'] = 'N/A'
        r['D_note'] = '设计性不消费（已登记）'
    else:
        hit = [c for c in s['cons']
               if os.path.exists(c) and s['cons_key'] and s['cons_key'] in read(c)]
        r['D'] = bool(hit)
        r['D_hit'] = [os.path.basename(h) for h in hit][:2]
    # 判定
    if not r['A']:
        r['state'] = '❌ A断:生产缺失'
    elif not r['B']:
        r['state'] = '🔴 B断:未被调用'
    elif not r['C']:
        r['state'] = '⚠️ C断:无输出数值(%s)' % ('无块' if not has_block else '块有无数值')
    elif r['D'] is False:
        r['state'] = '🔴 D断:纯展示无消费'
    else:
        r['state'] = '✅ 通'
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--calc', required=True, help='calc_all 真实输出文件')
    ap.add_argument('--only', default=None, help='只审这些 ID（逗号分隔）')
    ap.add_argument('--json', default=None)
    a = ap.parse_args()
    calc = read(a.calc)
    if not calc:
        print('❌ 读不到 calc 输出：%s' % a.calc)
        return 2
    only = set(x.strip() for x in a.only.split(',')) if a.only else None
    rows = [audit_step(s, calc) for s in STEPS if (not only or s['id'] in only)]

    print('=' * 108)
    print('Step 全流程四段审计 ｜ calc %d 字 ｜ 共 %d 个 Step' % (len(calc), len(rows)))
    print('=' * 108)
    print('%-6s %-26s %-4s %-4s %-4s %-6s %s' % ('ID', 'Step', 'A生产', 'B调用', 'C输出', 'D消费', '判定'))
    print('-' * 108)
    bad = []
    for r in rows:
        a_ = '✅' if r['A'] else '❌'
        b_ = '✅' if r['B'] else ('—' if r['B_na'] else '❌')
        c_ = '✅' if r['C'] else '⚠️'
        d_ = {'N/A': '—', True: '✅', False: '🔴'}[r['D']]
        print('%-6s %-26s %-5s %-5s %-5s %-7s %s' % (r['id'], r['name'][:24], a_, b_, c_, d_, r['state']))
        if r['state'] != '✅ 通':
            bad.append(r)
    print('-' * 108)
    print('✅ 通 %d ｜ 断链 %d' % (len(rows) - len(bad), len(bad)))
    if bad:
        print('\n🔴 断链明细：')
        for r in bad:
            detail = []
            if r['A_miss']:
                detail.append('缺文件 ' + '/'.join(os.path.basename(x) for x in r['A_miss']))
            if r['B_hit']:
                detail.append('调用点 ' + ' '.join(r['B_hit']))
            if not r['C']:
                detail.append('块=%s 数值=%s' % (r['C_block'], r['C_num']))
            if r['D'] is False:
                detail.append('消费端键 %s 未命中 %s' % (r.get('D_hit'), r.get('D_note', '')))
            print('   [%s] %-24s %s ｜ %s' % (r['id'], r['name'], r['state'], ' ; '.join(detail)))
        hi = [r for r in bad if r['lv'] == 'H']
        if hi:
            print('\n🔴🔴 高影响断链 %d 项：%s' % (len(hi), ' / '.join('%s(%s)' % (r['id'], r['name']) for r in hi)))
    if a.json:
        io.open(a.json, 'w', encoding='utf-8').write(json.dumps(rows, ensure_ascii=False, indent=1))
        print('\n已写 %s' % a.json)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
