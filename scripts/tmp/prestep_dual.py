# -*- coding: utf-8 -*-
"""prestep_dual.py —— PreStep 双向评级（2026-09-11·用户要求）
每次 PreStep 同时输出【方向评分】与【比分评分】两套独立评级。

🔴2026-09-20 分值体系重标（数据驱动·Matches.csv 227,518 场消融回测·前80%定/后20%验）:
  方向分 = 「方向可判性」评分·分值 = 触发组 vs 未触发组命中率边际差 Δ 映射（1分≈3-5pp）:
    D1 深盘主胜(主<1.5)          Δ+27.2 → +2
    D2 深盘客胜(亚盘客让0.75+)    Δ+14.4 → +2
    H2 穿盘(主让1.25-1.75)       Δ+23.8 → +2.0（升权）
    N3 中深盘主胜(1.5-1.8+客>4.5) Δ+10.4 → +1.5
    N4 客队热门(客<2.2+主>3.0)    Δ+6.0(孤立+2.3) → +1.0（降权）
    G1 大球(O25<1.7)             Δ+13.2(孤立-3.1·共线依赖) → +1.0（降权）
    D3 均势必平(隐含差5-10pp+平≥27) Δ-12.0(孤立-10.2) → -1.5（🔴原+1.5符号错误·改负分）
    G2 小球(O25>2.1)             Δ-7.5 → 0（🔴移出方向分·小球归 Step6 进球信号·小球兑现 60.2% 有效）
    H3 反直觉(西甲1.5-1.8/法甲深盘) Δ+13.2 → 0（🔴原-1被数据证伪·改仅标注不扣分）
    O10 浅让降权(主让0.25-0.75)   → -1（🔴严格口径·D1/N3子集: 浅让57.9% vs 深让80.1%·差22.2pp）
    H1 水位背离(水位差>0.2)       → +1（Matches 无水位列·保留待实盘验证）

  🔴2026-09-20 新增信号（严格协议: Δ≥2pp & 时间分割两段同向 & 4段≥3段同号 & z>2.24(Bonferroni k=4) & n≥500）:
    E1 ELO 强优势(主赔<1.8 且 ELO差>150)  Δ+14.0pp·z=27.3 → +1.5
    E2 ELO 优势(主赔<1.8 且 ELO差>100)    Δ+11.0pp·z=20.9 → +1.0
    E3 ELO 反向(主赔<1.8 且 ELO差<0)      镜像负向·4段全负 → -0.5
    W1 主水诱主(主赔<1.8 且 主水>2.05)     Δ-2.1pp·z=-2.5 → -0.5（轻度·效应小）
    O11 客队不弱(主赔<1.8 且 客赔<5.0)     Δ-10.8pp·z=-23.0 → -1.5（🔴与 N3 互斥·防双重计数）
    F1 近期状态(主赔<1.8 且 Form5差≥1.0)  Δ+4.2pp·z=9.6 → +0.5（🔴仅正向·F2 Form差<0 仅标注不扣分——负向未单独验证·防过拟合）
    ✅ Form5 数据源: Bzzoiro v1 home_form/away_form.points_last_n ÷ matches_played（场均积分 0-3·2026-10-29 换源·原 api-football 停用·口径变更待前瞻复核）
    ⚠️ 诚实边界: Form5 对【比分/量级】无增量（实测 O25 各档内总进球差 ≤0.12 球）→ 仅用于方向

  阈值（V3.1·2026-09-20 新增信号后重标）: ≥3.5 推荐(73.22%命中·8.68%覆盖)
    · ≥3.0 观察(70.65%·12.08%) · <3.0 不推荐
    🔴阈值上调原因: 新信号(E1-E3)使分值右移·≥3.0 覆盖由 9.44% 升至 12.08% → 门槛须同步上调以维持质量

比分分（V3·2026-09-20 调整·回测 227518 场）:
  O25>2.10强小球=+0.5（🔴原+1.5→+0.5·实测小球场锚Top2仅+2.8pp: 22.70% vs 19.93%）
  主赔1.80-2.20=+1.0 · 让≥1.5=+1.0 · 主赔1.50-1.80=+0.5
  O25中性1.65-1.90=-1.0 · O25<1.65大球侧=-2.5 · 极端共振(O25<1.5+让≥1.5)=-5.0
  贴水浅让(主<1.5+让<1)=-5.0 · O25<1.7+隐含差>25=-2.0 · 🔴悬殊场(|主隐−客隐|>40pp)=-1.0（2026-09-27·回测 Top2 集中度 20.7% vs 均线 23.9%）
  阈值: ≥2.0 强推荐(锚Top2 24.51%·7.24%覆盖) / ≥1.0 参考(21.99%·17.66%) / <0 不可预测
    （🔴原 ≥1.5 = 20.24% < 全样本基准 21.18% 无增益·实测证伪）

双向评级:
  🔴双推荐(方向≥3.5+比分≥2.0) | ✅方向优先(仅方向≥3.5) | ⚡比分优先(仅比分≥2.0)
  | ⏸️比分不可预测(比分<0 或 锚不可信) | 其余参考

用法（🔴2026-11-11 口径修正·P-TOOL-1: 第 1 位是【场次标签】·第 2 位起必须是赔率·**没有队名字段**）:
  python data/tmp/prestep_dual.py --match "费内巴切vs罗马,3.32,3.55,1.83,1,3.09"
  python data/tmp/prestep_dual.py --file data/tmp/_prestep_input.txt
  字段: 场次标签,主赔,平赔,客赔,让球,O25[,水位差,联赛[,elo差,主水[,form差]]]
  例:   "日联赛杯 神户vs町田,2.30,3.26,2.957,-0.25,1.95,0,日联赛杯,,1.958"
  🔴把队名写进赔率位 → float() 失败 → 该行判「解析失败」并显式报错（不再静默跳过）
  🔴标签含「欧国联」→ 自动走 NL 超域区（不打正式分·判定走 SK-league-nations）
"""
import sys, io, os, argparse
sys.stdout.reconfigure(encoding='utf-8')

D5 = ('英超', 'E0', '西甲', 'SP1', '意甲', 'I1', '德甲', 'D1', '法甲', 'F1')
FRA = ('法甲', 'F1')
ESP = ('西甲', 'SP1')


def probs(oh, od, oa):
    inv = {1: 1 / oh, 0: 1 / od, 2: 1 / oa}
    t = sum(inv.values())
    return {k: v / t for k, v in inv.items()}


def score_direction(oh, od, oa, handi, o25, water_gap=0, league='', elo_diff=None, home_water=None, form_diff=None):
    """方向评分（V3·2026-09-20 重标 + 新增 ELO/水位/赔率细分信号·见模块 docstring）"""
    p = probs(oh, od, oa)
    top = max(p, key=p.get)
    gap = (p[top] - sorted(p.values())[-2]) * 100
    s = 0.0
    tags = []
    if oh < 1.5:
        s += 2; tags.append('D1深盘主胜+2')
    if handi >= 0.75 and oa < 2.5:  # 亚盘客让0.75+（handi>0 = 客队让球）
        s += 2; tags.append('D2深盘客胜+2')
    if 5 <= gap <= 10 and od >= 3.0:
        s -= 1.5; tags.append('D3均势必平-1.5(方向不可判·平局价值见修正53/R20)')
    n3 = 1.5 <= oh < 1.8 and oa > 4.5
    if n3:
        s += 1.5; tags.append('N3中深盘主胜+1.5')
    if oa < 2.2 and oh > 3.0:
        s += 1.0; tags.append('N4客队热门+1.0')
    if o25 < 1.7:
        s += 1.0; tags.append('G1大球+1.0')
    if o25 > 2.1:
        tags.append('G2小球(不进方向分·归Step6进球信号)')
    if abs(water_gap) > 0.2:
        s += 1; tags.append('H1水位背离+1')
    if -1.75 <= handi <= -1.25:
        s += 2.0; tags.append('H2穿盘+2.0')
    if ((1.5 <= oh < 1.8) and league in ESP) or (league in FRA and handi <= -1.5):
        tags.append('H3反直觉(仅标注·实测正向Δ+13.2)')
    # 🔴 O10 浅让降权（严格口径·仅主让0.25-0.75·排除平手/受让）
    if (oh < 1.5 or n3) and (-1.0 < handi < 0):
        s -= 1; tags.append('O10浅让降权-1')
    # 🔴 2026-09-20 新增：ELO 优势（严格协议通过·z=20.9/27.3）
    if elo_diff is not None and oh < 1.8:
        if elo_diff > 150:
            s += 1.5; tags.append('E1-ELO强优势+1.5(差>150·Δ+14.0pp)')
        elif elo_diff > 100:
            s += 1.0; tags.append('E2-ELO优势+1.0(差>100·Δ+11.0pp)')
        elif elo_diff < 0:
            s -= 0.5; tags.append('E3-ELO反向-0.5(差<0·镜像负向)')
    # 🔴 2026-09-20 新增：主水诱主（轻度·效应 -2.1pp）
    if home_water is not None and oh < 1.8 and home_water > 2.05:
        s -= 0.5; tags.append('W1-主水诱主-0.5(>2.05·Δ-2.1pp)')
    # 🔴 2026-09-20 新增：客队不弱（与 N3 互斥·防双重计数）
    if oh < 1.8 and oa < 5.0 and not n3:
        s -= 1.5; tags.append('O11-客队不弱-1.5(客赔<5.0·Δ-10.8pp)')
    # 🔴 2026-09-20 新增：近期状态（Form5差·Δ+4.2pp·z=9.6·仅正向加分·F2 仅标注防过拟合）
    if form_diff is not None and oh < 1.8:
        if form_diff >= 1.0:
            s += 0.5; tags.append('F1-近期状态+0.5(Form差>=1.0·Δ+4.2pp)')
        elif form_diff < 0:
            tags.append('F2-近期状态弱(Form差<0·仅标注·未验证负向)')
    return round(s, 1), {0: '平', 1: '主胜', 2: '客胜'}[top], tags


def score_score(oh, od, oa, handi, o25):
    """比分评分 V4.1（2026-10-26 升级·五大联赛 35,879 场实测重标）

    数据来源: `data/tmp/_bt_score_v2.py` / `_bt_score_v3.py` / `_bt_score_v4.py`
      基线 Top2 命中 24.65%（train 24.67 / test 24.57·时间分割）
      分档单调: ≥2.0 +3.5pp > 1.0-2.0 +2.7 > 0-1.0 -0.2 > -1-0 -0.9 > -3~-1 -2.4 > <-3 -4.1
    与 V3 的关键差异（均为实测纠错·非拍脑袋）:
      ① 主赔 1.50-1.80 由 **+0.5 改 -0.3**（实测 23.9%/-0.8pp·原加分=符号错）
      ② 平赔 od<3.10 **新增 +1.5**（实测 28.4%/29.1% = +3.8/+4.5pp）
      ③ 大球侧细分为三档（1.55-1.65 仅 -0.5·原 -2.5 过重；<1.40 -2.5）
      ④ 「深让≤-1.5 +1.0」**删除**（train +1.3 / test -1.7 = 不稳定）
      ⑤ 「悬殊 gap>40pp -1.0」**删除**（实测 +0.1pp = 无效·旧值源于近似 bug）
      ⑥ 小球组合细化（小球+中盘 / 小球+弱主 各 +0.5·实测 +3.4/+3.0pp）
      ⑦ 大球+弱主 **-2.0**（实测 -4.9/+3.8pp 负向）
      ⑧ 极端档 -5.0 → **-3.0**（实测 -2.7/-4.3pp）
    案例库交叉印证（142 场/37 命中·仅方向层面）: 命中组 2 球占 41%·未中组 ≥5 球占 30%
      → 与「低量级更可测」一致；主赔维度案例库与大样本相反（案例库含策略偏倚·n=37 不显著）→ 以本函数（大样本）为准
    """
    s = 0.0
    tags = []
    # ① 量级维（最强·两源一致）
    if o25 > 2.20:
        s += 1.5; tags.append('极强小球+1.5')
    elif o25 > 2.10:
        s += 1.0; tags.append('强小球+1.0')
    elif o25 < 1.40:
        s -= 2.5; tags.append('超强攻-2.5')
    elif o25 < 1.55:
        s -= 1.5; tags.append('强攻-1.5')
    elif o25 < 1.65:
        s -= 0.5; tags.append('偏攻-0.5')
    elif o25 <= 1.90:
        s -= 1.0; tags.append('中性-1.0')
    # ② 平赔维（V4 新增）
    if od < 3.10:
        s += 1.5; tags.append('低平赔+1.5')
    # ③ 主赔维（V4 修正符号）
    if 1.80 <= oh < 2.20:
        s += 0.5; tags.append('中盘+0.5')
    elif 1.50 <= oh < 1.80:
        s -= 0.3; tags.append('主赔1.5-1.8 -0.3')
    # ④ 组合维（与①互补·不重复计价）
    if o25 > 2.10:
        if 1.80 <= oh < 2.20:
            s += 0.5; tags.append('小球+中盘+0.5')
        elif oh >= 2.20:
            s += 0.5; tags.append('小球+弱主+0.5')
    if o25 < 1.65 and oh >= 2.20:
        s -= 2.0; tags.append('大球+弱主-2.0')
    # ⑤ 极端不可测（实测保留·幅度校准）
    if o25 < 1.5 and handi <= -1.5:
        s -= 3.0; tags.append('🔴极端共振-3.0')
    if oh < 1.5 and handi > -1.0:
        s -= 3.0; tags.append('🔴贴水浅让-3.0')
    return round(s, 1), tags


def anchor_hint(oh, od, oa, handi, o25, league=''):
    """比分锚建议（按 方向+让球层+O25档 查表·实测 Top2 21.2%）"""
    p = probs(oh, od, oa)
    top = max(p, key=p.get)
    if top == 1:            # 主胜倾向
        if o25 < 1.65: return '2:1 / 2:0（大球侧·净胜分散）', '~19%'
        if o25 > 2.1:  return '1:0 / 2:0（小球·零封倾向）', '~27%'
        return '2:1 / 1:0', '~26%'
    if top == 2:            # 客胜倾向
        if o25 < 1.65: return '1:2 / 0:2', '~19%'
        return '0:1 / 1:2', '~25%'
    return '1:1 / 0:0', '~25%'


def anchor_trust(o25, handi=None):
    """🔴锚可信度分级（2026-09-13·案例库 157 场锚命中回测固化）"""
    if o25 is None:
        return '未知', '无 O25 数据'
    if o25 < 1.50:
        return '🔴不可信', '预期总进球>=3.4球(实测锚命中2.9-6.5%·5+球0%)'
    if o25 < 1.65:
        return '⚠️弱', '预期总进球约3.0球(实测约32%·临界档)'
    if handi is not None and handi <= -2.0:
        return '🔴不可信', '深盘大胜(净胜档>=3·实测锚命中5.4%)'
    return '✅可信', '预期总进球<=2.9球(实测锚命中26-50%·低分小净胜40%)'


def evaluate(name, oh, od, oa, handi, o25, water_gap=0, league='', elo_diff=None, home_water=None, form_diff=None):
    ds, dtend, dtags = score_direction(oh, od, oa, handi, o25, water_gap, league, elo_diff, home_water, form_diff)
    ss, stags = score_score(oh, od, oa, handi, o25)
    anc, hit = anchor_hint(oh, od, oa, handi, o25, league)
    at, at_reason = anchor_trust(o25, handi)
    # 🔴2026-09-20 阈值重标（V3 分值·Matches 227518 场实测）
    #   方向 ≥3.5 = 73.22%(8.68%覆盖·含新信号后重标) · ≥3.0 = 70.65%(12.08%) 观察
    #   比分 ≥2.0 = 锚Top2 24.51%(7.24%覆盖) · ≥1.0 = 21.99%(17.66%) 参考
    # 🔴V4.1 档位（2026-10-26·实测单调）: ≥2.0 +3.5pp / ≥1.0 +2.7 / ≥-1.0 ≈基线 / <-1.0 -2.4~-4.1pp
    if ss >= 2.0:   grade = '强推荐(比分)'
    elif ss >= 1.0: grade = '推荐(比分)'
    elif ss >= -1.0: grade = '参考(比分·近基线)'
    else:           grade = '不可预测'
    # 🔴2026-10-26 审计补: 方向档三档（AGENTS 早已声明·代码此前只有 verdict 用 3.5·无独立字段）
    if ds >= 3.5:   dgrade = '推荐(方向)'
    elif ds >= 3.0: dgrade = '观察(方向)'
    else:           dgrade = '不推荐(方向)'
    if ds >= 3.5 and ss >= 2.0:
        verdict = '🔴双推荐(方向+比分)'
    elif ss >= 2.0:
        verdict = '⚡比分优先(方向弱)'
    elif ds >= 3.5:
        verdict = '✅方向优先(比分参考)'
    elif ss >= -1.0:
        verdict = '⚡比分参考(方向弱)'
    else:
        verdict = '⏸️比分难测(仅方向参考)'
    if at.startswith('🔴'):      # 🔴锚不可信 → 强制标注
        verdict = '⏸️比分不可预测(锚可信度:不可信)'
    return {'名': name, '方向档': dgrade, '比分档': grade, '锚可信度': at, '锚可信度依据': at_reason,
            '方向分': ds, '方向': dtend, '方向信号': dtags,
            '比分分': ss, '比分信号': stags, '比分锚': anc, '比分命中率': hit, '评级': verdict}


def print_table(rows):
    # 🔴2026-11-11 P-TOOL-1: 0 行守卫 —— 空 rows 绝不能走到下方「NL 超域·参考分数」标题（那是 NL 场专用）
    if not rows:
        print('⚠️ 无有效场次（0 行）→ 未打分（不是「NL 超域」·请检查输入解析）')
        return
    # 🔴2026-09-24 修正(实操复盘 P0-1): NL 场与俱乐部场分流 —— 正式双轨表只列非 NL 场；
    #   NL 分值移入『NL 超域区·仅供参考·不参与判定』区块（此前『说不触发却照样出正式分』= 口径矛盾）
    _nl_rows = [r for r in rows if _is_nl(r.get('名') or '')]
    _cl_rows = [r for r in rows if not _is_nl(r.get('名') or '')]
    if _nl_rows:
        print('🔴 NL 超域区（%d 场）·PreStep 分值 **不参与判定**（阈值源自五大联赛 22.7 万场·NL 基线 O2.5 45.3%%）' % len(_nl_rows))
        for r in _nl_rows:
            print('   ⚪ %s | 方向分 %s(%s) · 比分分 %s | %s' % (r['名'], r['方向分'], r['方向'], r['比分分'], r['评级']))
            print('      → %s' % _is_nl(r['名']))
        print()
    if not _cl_rows:
        print('=' * 104)
        print('⚠️ NL 超域·参考分数（🔴 不可用于判定·仅存档·判定请用 SK-league-nations R1-R10）')
        print('=' * 104)
        print('%-20s %-6s %-12s %-6s %-6s %-12s %-10s %-16s %-8s %s' % ('赛事', '方向分', '方向档', '倾向', '比分分', '比分档', '锚可信度', '比分锚建议', '档命中率', '双向评级'))
        print('-' * 116)
        for r in sorted(_nl_rows, key=lambda x: -(x['方向分'] + x['比分分'])):
            print('%-20s %-6s %-12s %-6s %-6s %-12s %-10s %-16s %-8s %s' % (
                r['名'][:18], r['方向分'], r.get('方向档', ''), r['方向'], r['比分分'], r.get('比分档', ''), r.get('锚可信度', ''), r['比分锚'], r['比分命中率'], r['评级']))
        print('-' * 116)
        print()
        return
    rows = _cl_rows
    print('=' * 104)
    print('🔴 PreStep 双向评级（方向分 V3 · 比分分 **V4.1**·独立输出·2026-10-26）')
    print('=' * 104)
    print('%-20s %-6s %-12s %-6s %-6s %-12s %-10s %-16s %-8s %s' % ('赛事', '方向分', '方向档', '倾向', '比分分', '比分档', '锚可信度', '比分锚建议', '档命中率', '双向评级'))
    print('-' * 116)
    for r in sorted(rows, key=lambda x: -(x['方向分'] + x['比分分'])):
        print('%-20s %-6s %-12s %-6s %-6s %-12s %-10s %-16s %-8s %s' % (
            r['名'][:18], r['方向分'], r.get('方向档', ''), r['方向'], r['比分分'], r.get('比分档', ''), r.get('锚可信度', ''), r['比分锚'], r['比分命中率'], r['评级']))
    print('-' * 116)
    print('阈值: 方向分 ≥3.5 推荐(73.22%·8.68%覆盖) · ≥3.0 观察(70.65%·12.08%) · <3.0 不推荐 ｜ 比分分 V4.1 见下')
    print('      比分分 V4.1: ≥2.0 强推荐(train +3.5pp/test +6.2pp·16.4%覆盖) · ≥1.0 推荐(+2.7pp) · ≥-1.0 参考(≈基线) · <-1.0 不可预测(-2.4~-4.1pp)')
    print('🔴V3 新增信号(严格协议: Δ≥2pp·时间分割·4段稳健·z>2.24·Bonferroni k=4): E1-E3 ELO差 / W1 主水诱主 / O11 客队不弱')
    print('🔴锚可信度(2026-09-13·案例库157场回测): ✅可信(实际≤3球锚命中36.4%·低分小净胜40%) / ⚠️弱(≈32%) / 🔴不可信(≥4球2.9%·5+球0%·净胜≥3为5.4%)')
    print()
    for r in sorted(rows, key=lambda x: -(x['方向分'] + x['比分分'])):
        if r['方向分'] > 0 or r['比分分'] != 0 or r['方向信号']:
            print('【%s】方向%s(%s) | 比分%s(%s)' % (r['名'], r['方向分'], '·'.join(r['方向信号']) or '—',
                                                    r['比分分'], '·'.join(r['比分信号']) or '—'))


def _is_nl(league):
    """🔴2026-09-23 接入·2026-09-24 更正(实操复盘): 欧国联/国家队 → PreStep **超域**（阈值源自五大联赛 Matches 22.7 万场·NL 基线 O2.5 45.3%）。Odds-API **已收录** NL（实测 16 slug·pending 156 场·勿信旧『未收录』结论）"""
    t = (league or '').lower()
    if any(k in t for k in ('nations', '欧国联', 'uefa-nations')):
        return ('NL 超域·PreStep 先验不触发（阈值源自五大联赛 Matches 22.7 万场·NL 基线 O2.5 45.3% ≠ 五大 53%+）'
                '→ 判定请走 SK-league-nations（R1-R10·658 场专属库·nl_model.py）')
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--match', action='append',
                    help='场次标签,主赔,平赔,客赔,让球,O25[,水位差,联赛[,elo差,主水[,form差]]]'
                         '（🔴第1位是场次标签·第2位起是赔率·没有队名字段）')
    ap.add_argument('--file', help='每行同上（空行 / # 注释行忽略）')
    a = ap.parse_args()
    lines = a.match or []
    if a.file and os.path.exists(a.file):
        # 🔴2026-11-11 P-TOOL-1b: utf-8-sig 自动吞 BOM（记事本/PowerShell 5.1 存的 txt 带 \ufeff
        #   → 原 utf-8 读会把首行变成 '\ufeff# ...' / '\ufeff标签,赔率…' → 注释误判 + 首场解析失败）
        lines += [l.strip().replace('\ufeff', '') for l in open(a.file, encoding='utf-8-sig')
                  if l.strip().replace('\ufeff', '') and not l.strip().replace('\ufeff', '').startswith('#')]
    if not lines:
        print(__doc__); return
    rows = []
    no_hw = 0
    bad = []   # 🔴2026-11-11 P-TOOL-1: 解析失败不再静默吞
    #   原实现 `except Exception: continue` → 按字面把队名写在赔率位的行被整体丢弃 →
    #   输出【空表】却打「NL 超域·参考分数」标题 = 把「我传错参数」伪装成「NL 场次」＝误导。
    for i, ln in enumerate(lines, 1):
        s = (ln or '').replace('\ufeff', '').strip()   # BOM 双保险（--match 手传/外部调用也可能带）
        if not s or s.startswith('#'):
            continue
        p = [x.strip() for x in s.split(',')]
        if len(p) < 6:
            bad.append((i, s, '字段不足（需 ≥6: 标签,主赔,平赔,客赔,让球,O25）·实得 %d' % len(p)))
            continue
        try:
            name, oh, od, oa = p[0], float(p[1]), float(p[2]), float(p[3])
            handi, o25 = float(p[4]), float(p[5])
        except Exception as e:
            bad.append((i, s, '赔率位非数字（%s）→ 第1位=场次标签·第2位起必须是 主赔,平赔,客赔,让球,O25' % e))
            continue
        try:
            wg = float(p[6]) if len(p) > 6 and p[6] else 0
            lg = p[7] if len(p) > 7 else ''
            ed = float(p[8]) if len(p) > 8 and p[8] else None
            hw = float(p[9]) if len(p) > 9 and p[9] else None
            fd = float(p[10]) if len(p) > 10 and p[10] else None
        except Exception as e:
            bad.append((i, s, '可选位解析失败（水位差/elo差/主水/form差须为数字·%s）' % e))
            continue
        if hw is None:
            no_hw += 1
        rows.append(evaluate(name, oh, od, oa, handi, o25, wg, lg, ed, hw, fd))
    if bad:
        print('🔴 解析失败 %d/%d 行（这些场次**未参与打分**·不静默丢弃）:' % (len(bad), len(bad) + len(rows)))
        for i, s, why in bad[:10]:
            print('   L%-3d %s' % (i, s[:78]))
            print('        → %s' % why)
        if len(bad) > 10:
            print('   …… 另 %d 行（同上）' % (len(bad) - 10))
        print('   正确格式: 场次标签,主赔,平赔,客赔,让球,O25[,水位差,联赛[,elo差,主水[,form差]]]')
        print('   例: "日联赛杯 神户vs町田,2.30,3.26,2.957,-0.25,1.95,0,日联赛杯,,1.958"')
        print()
    if not rows:
        print('🔴 无有效场次（0 行解析成功）→ 未打分。按上方提示修正参数后重跑。')
        sys.exit(2)
    if no_hw:
        print('⚠️ %d/%d 场未传主水 → W1(主水诱主 −0.5) 信号失效·方向分可能偏高（补第 10 位主水可修正）' % (no_hw, len(rows)))
        print()
    print_table(rows)


if __name__ == '__main__':
    main()
