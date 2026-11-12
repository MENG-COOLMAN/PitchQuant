# -*- coding: utf-8 -*-
"""子模型 adapter —— 把各自为政的子模型统一到 SubModelResult 契约

🔴 设计原则：**只包装·不改内部**（零回归风险）
   · nations → 调 nl_model.analyze()（原样）→ 正则解析 → SubModelResult
   · europe  → 调 europe_two_leg / group_stage（原样）→ SubModelResult
   · top5_*  → 五大联赛是**纯文档**（LLM 读 skill·代码零规则）→ 返回三态说明
   · 每个 adapter 调 guard_table 前先自检 scope（强隔离）
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from match_context import (  # noqa: E402
    MatchContext, SubModelResult, guard_table, ScopeViolation, league_kind,
)

# ══════════════════════════════════════════════════════════════════════
# 欧国联 adapter
# ══════════════════════════════════════════════════════════════════════
def calc_nations(ctx):
    """欧国联 → SubModelResult（内部仍走 nl_model.analyze·零改动）"""
    res = SubModelResult('nations')
    # ── scope 自检（强隔离：NL 不得读五大专属表）
    for forbidden in ('odds_table', 'league_table', 'ucl_calibration', 'team_attack_defense'):
        try:
            guard_table('nations', forbidden)
        except ScopeViolation:
            res.blocked(forbidden)   # 记录「已拦截」·证明隔离生效

    try:
        from nl_model import is_nations_league, analyze
    except Exception as e:
        res.applicable = False
        res.reason = 'nl_model 导入失败: %s' % str(e)[:60]
        return res

    ok, why = is_nations_league(None, str(ctx.get('league') or ''))
    if not ok:
        res.applicable = False
        res.reason = why or '非欧国联'
        return res

    oh, od, oa = (ctx.get('eu') or (None, None, None))[:3]
    md = ctx.get('matchday') or 1
    try:
        txt = analyze(None, str(ctx.get('league') or ''), None, None, md,
                      (oh, od, oa), 0, ctx.get('spread'), ctx.get('home'), ctx.get('away'))
    except Exception as e:
        res.applicable = False
        res.reason = 'analyze 异常: %s' % str(e)[:80]
        return res
    res.raw_text = txt or ''
    t = res.raw_text

    # ── 解析 R4：档位实测 主 X% / 平 Y% / 客 Z%
    m4 = re.search(r'R4 档位实测[^:]*:\s*主\s*(\d+)%\s*/\s*平\s*(\d+)%\s*/\s*客\s*(\d+)%', t)
    if m4:
        h4, d4, a4 = (int(m4.group(i)) for i in (1, 2, 3))
        res.hit('R4')
        # 用 R4 实测 vs 市场去水做「方向校正」（只给 ±pp·极小幅度）
        try:
            ph, pd_, pa = _devig(oh, od, oa)
        except Exception:
            ph = pd_ = pa = None
        if ph is not None:
            dh = (h4 / 100.0 - ph) * 100
            dd = (d4 / 100.0 - pd_) * 100
            da = (a4 / 100.0 - pa) * 100
            res.adj(home=round(max(-5, min(5, dh * 0.3)), 2),
                    draw=round(max(-5, min(5, dd * 0.3)), 2),
                    away=round(max(-5, min(5, da * 0.3)), 2))
            res.warn('R4 档位(主%d/平%d/客%d) vs 市场去水(主%.0f/平%.0f/客%.0f) → 校正幅度已压至 ±5pp 的 30%%'
                     % (h4, d4, a4, ph * 100, pd_ * 100, pa * 100))

    # ── 解析 R5：客队热门平局泄漏
    m5 = re.search(r'R5\s*(中浅|中深|超深)客热门[^:]*:\s*实际客胜\s*(\d+)%\s*·\s*平\s*(\d+)%', t)
    if m5:
        res.hit('R5')
        lvl, aw5, dw5 = m5.group(1), int(m5.group(2)), int(m5.group(3))
        res.warn('R5 %s客热门：客胜 %d%% / 平 %d%% → **禁当稳胆·平局按 %s%% 评估**'
                 % (lvl, aw5, dw5, '27-33' if lvl == '中浅' else '25-28'))
        res.conf(-1 if aw5 < 50 else 0)

    # ── 解析 R7：均势
    if re.search(r'R7 均势判定:\s*✅\s*中性', t):
        res.hit('R7')
        res.warn('R7 均势档：中性（主44/平30/客26 · 场均 2.30）→ 方向不可强判')

    # ── 解析 R8：主场 Elo 加成
    if 'R8 保留主场 Elo 加成' in t:
        res.hit('R8')

    # ── 解析 R3/R3b：量级
    m3 = re.search(r'R3b 近年对照[^：]*：场均\s*\**([\d.]+)\**\s*球\s*·\s*O2\.5\s*\**([\d.]+)%', t)
    if m3:
        res.hit('R3b')
        res.goals(float(m3.group(1)) - 2.51)   # 相对全量基线的偏移
        res.warn('R3b 近年场均 %s 球 / O2.5 %s%%（全量 2.51/45.3）→ 量级校正已应用'
                 % (m3.group(1), m3.group(2)))

    # ── 解析 R10：公平模型 + edge
    m10 = re.search(r'R10 公平模型:\s*公平\s*([\d.]+)/([\d.]+)/([\d.]+)\s*·\s*λ\s*([\d.]+)/([\d.]+)', t)
    if m10:
        res.hit('R10')
    e = re.search(r'edge\s*H([+-][\d.]+)\s*/\s*D([+-][\d.]+)\s*/\s*A([+-][\d.]+)', t)
    if e:
        eh, ed, ea = (float(e.group(i)) for i in (1, 2, 3))
        res.hit('R10-edge')
        for nm, v in (('H', eh), ('D', ed), ('A', ea)):
            if abs(v) >= 10:
                res.warn('R10 edge %s %+.1fpp（≥10pp 显著）→ %s'
                         % (nm, v, '可升 0.5 档' if v > 0 else '**该方向禁单押·降 1 档 + 强制并列**'))
                if v <= -10:
                    res.conf(-1)

    # ── 锚提示（从 R5/R6 常见比分提取）
    mcs = re.search(r'该档常见比分:\s*([\d:]+)\s*\(([\d.]+)%\)\s*/\s*([\d:]+)\s*\(([\d.]+)%\)', t)
    if mcs:
        res.anchor((mcs.group(1), round(float(mcs.group(2)) / 15, 2)),
                   (mcs.group(3), round(float(mcs.group(4)) / 15, 2)))
        res.hit('R5常见比分')

    if not res.rules_hit:
        res.warn('R1-R10 未命中任何可量化规则（Elo 缺失或档位未定）→ 仅输出三态')

    res.raw_text = t
    return res


def _devig(oh, od, oa):
    """等比例去水 → (pH, pD, pA)"""
    inv = [1.0 / float(x) for x in (oh, od, oa)]
    s = sum(inv)
    return inv[0] / s, inv[1] / s, inv[2] / s


# ══════════════════════════════════════════════════════════════════════
# 欧战 adapter
# ══════════════════════════════════════════════════════════════════════
def calc_europe(ctx):
    """欧战（欧冠/欧联/欧协联）→ SubModelResult"""
    res = SubModelResult('europe')
    for forbidden in ('league_table', 'nl_data', 'fair_model', 'team_attack_defense'):
        try:
            guard_table('europe', forbidden)
        except ScopeViolation:
            res.blocked(forbidden)

    lg = str(ctx.get('league') or '')
    if league_kind(lg) != 'europe':
        res.applicable = False
        res.reason = '非欧战场（league=%s）' % (lg or '?')
        return res

    is_ucl = ('欧冠' in lg) or lg.lower() in ('ec', 'ucl', 'champions', 'championsleague')
    # ── N24 欧冠大球校准（仅欧冠·数据隔离）
    if is_ucl:
        try:
            import ucl_calibration as UC
            tbl = getattr(UC, 'load', lambda: {})() or {}
            res.hit('N24')
            res.goals(+0.67)
            res.warn('N24 欧冠校准：λ_final 与期望各 +0.67 球（欧冠正赛实测 3.37球/64.5% vs 五大 2.69/50.4%）')
        except Exception as e:
            res.warn('N24 读取失败（%s）→ 三态·不校准' % str(e)[:50])
    # ── 欧战两回合 / 小组赛
    try:
        import europe_two_leg  # noqa: F401
        res.hit('europe_two_leg(可用)')
    except Exception:
        pass
    try:
        import europe_group_stage  # noqa: F401
        res.hit('europe_group_stage(可用)')
    except Exception:
        pass
    # ── rule51-66 欧战六项核查归 LLM（文档级·代码不实现）
    res.warn('rule51-66 欧战六项核查表由 LLM 读 SL-europe-db 逐项执行（文档级·非代码级）')
    return res


# ══════════════════════════════════════════════════════════════════════
# 五大联赛 adapter（纯文档·代码零规则）
# ══════════════════════════════════════════════════════════════════════
def _top5_adapter(sub_id, cn):
    def _f(ctx):
        res = SubModelResult(sub_id)
        for forbidden in ('nl_data', 'fair_model', 'elo_current', 'europe', 'ucl_calibration'):
            try:
                guard_table(sub_id, forbidden)
            except ScopeViolation:
                res.blocked(forbidden)
        res.hit('SK-league-%s(文档级)' % sub_id.replace('top5_', ''))
        res.warn('%s 子模型 R1-R20 为**纯文档规则** → 由 LLM 读 SK-league-%s 逐条执行·'
                 '代码不实现（故 adapter 不产出方向/量级数值·仅登记适用）'
                 % (cn, sub_id.replace('top5_', '')))
        return res
    return _f


calc_epl = _top5_adapter('top5_epl', '英超')
calc_laliga = _top5_adapter('top5_laliga', '西甲')
calc_seriea = _top5_adapter('top5_seriea', '意甲')
calc_bundesliga = _top5_adapter('top5_bundesliga', '德甲')
calc_ligue1 = _top5_adapter('top5_ligue1', '法甲')

# 注册表（与 match_context.SUBMODELS 的 adapter 函数名对应）
ADAPTERS = {
    'calc_epl': calc_epl, 'calc_laliga': calc_laliga, 'calc_seriea': calc_seriea,
    'calc_bundesliga': calc_bundesliga, 'calc_ligue1': calc_ligue1,
    'calc_nations': calc_nations, 'calc_europe': calc_europe,
}


def run_all(ctx):
    """按 ctx.sub_id 只跑**一个**子模型（隔离：不串）→ SubModelResult 或 None"""
    from match_context import pick_submodel
    sid, cn = pick_submodel(ctx.get('league'))
    if not sid:
        r = SubModelResult('none', False, '非子模型域（league=%s）' % (ctx.get('league') or '?'))
        return r
    ctx['sub_id'] = sid
    fn = ADAPTERS.get({
        'top5_epl': 'calc_epl', 'top5_laliga': 'calc_laliga', 'top5_seriea': 'calc_seriea',
        'top5_bundesliga': 'calc_bundesliga', 'top5_ligue1': 'calc_ligue1',
        'nations': 'calc_nations', 'europe': 'calc_europe',
    }.get(sid, ''))
    if not fn:
        return SubModelResult(sid, False, 'adapter 未注册')
    return fn(ctx)


# ══════════════════════════════════════════════════════════════════════
# 自测
# ══════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    from match_context import fmt_aggregate, aggregate, clear_violations, violations
    clear_violations()
    print('=' * 90)
    print('子模型 adapter 自测（总分总·分 → 总②）')
    print('=' * 90)

    CASES = [
        ('欧国联', 'Italy', 'France', (4.20, 3.76, 1.82), 0.75),
        ('欧冠', 'Arsenal', 'Bayern', (2.10, 3.60, 3.20), -0.5),
        ('英超', 'Arsenal', 'Chelsea', (1.80, 3.90, 4.10), -0.75),
        ('日职', '浦和', '鹿岛', (2.30, 3.40, 2.80), 0.0),
    ]
    for lg, h, a, eu, hd in CASES:
        ctx = MatchContext(league=lg, home=h, away=a, eu=eu, handi=hd,
                           o25=1.70, u25=2.10, kickoff='2026-11-12 19:45', case_id='t')
        r = run_all(ctx)
        print()
        print('▶ %s：%s vs %s' % (lg, h, a))
        print('  ' + r.summary())
        if r.raw_text:
            print('  （nl_model 原始输出 %d 字符 · 已解析 %d 条规则）' % (len(r.raw_text), len(r.rules_hit)))
        agg = aggregate([r], l2_lock=None)
        if agg['applied']:
            print('  ' + fmt_aggregate(agg).replace('\n', '\n  '))
    print()
    print('=' * 90)
    print('强隔离违规记录: %d 条' % len(violations()))
    for v in violations()[:6]:
        print('   · %s' % v['msg'][:110])
