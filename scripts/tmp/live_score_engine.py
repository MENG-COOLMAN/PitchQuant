# -*- coding: utf-8 -*-
"""live_score_engine.py — 现场动态比分概率引擎（V3.5.74·2026-09-07）
🔴核心原则：不机械锚定比分·所有概率基于本场比赛实时数据现场计算·多源动态权重融合

计算流程（每场比赛独立执行）：
  1. 泊松现场反推 → 49格比分概率矩阵（基础分布）
  2. CS比分盘现场去抽水 → 市场对比分的直接定价（最强信号·如有数据）
  3. 亚盘现场约束 → 净胜球分布约束
  4. 大小球现场约束 → 总进球分布约束
  5. 半全场现场约束 → 半场比分约束（如有数据）
  6. 动态权重计算 → 基于各源数据完整度+一致性现场计算权重
  7. 贝叶斯融合 → 最终比分概率分布
  8. 输出Top10比分 + 各源贡献分解 + 置信度 + 不确定性标注

用法: python live_score_engine.py --home 1.8 --draw 3.5 --away 4.2 --o25 1.85 --u25 1.95 --handi -0.75
      [--cs "1:0=7.5,2:1=8.0,1:1=6.5,..."] [--bqc "胜胜=3.0,平平=5.0,..."]
"""
import sys, math, json, argparse
from collections import defaultdict
try:
    sys.stdout.reconfigure(encoding='utf-8')
except: pass

# ═══════════════════════════════════════════════════════════════
# 1. 泊松现场反推（基础分布·49格）
# ═══════════════════════════════════════════════════════════════
def pois(k, l):
    return math.exp(-l) * l**k / math.factorial(k)

def solve_lambda_live(oh, od, oa, o25, u25=None):
    """现场反推λ：欧盘去水主胜概率 + O2.5总进球期望 → λh/λa
    完全基于本场赔率，不查任何表"""
    if u25 is None:
        u25 = max(1.01, 1/(1.04 - 1/o25))
    if min(oh, od, oa, o25, u25) <= 1.01:
        return None, None
    inv = [1/oh, 1/od, 1/oa]
    ph = inv[0] / sum(inv)
    # O2.5→总进球期望t
    po, pu = 1/o25, 1/u25
    p_over = po / (po + pu)
    t = 2.5
    for _ in range(40):
        p3 = 1 - math.exp(-t) * (1 + t + t*t/2)
        t += (p_over - p3) * 1.2
        if t < 0.5 or t > 6: break
    t = max(0.5, min(6, t))
    # 网格搜索λ分配
    lo, hi = 0.05*t, 0.95*t
    best, besterr = None, 9
    for k in range(80):
        lh = lo + (hi-lo)*k/79; la = t - lh
        if la <= 0.05: continue
        ph_calc = sum(pois(i,lh)*pois(j,la) for i in range(7) for j in range(7) if i>j)
        err = abs(ph_calc - ph)
        if err < besterr: besterr, best = err, (lh, la)
    return best if best else (t*0.6, t*0.4)

def poisson_matrix(oh, od, oa, o25, u25=None, dc_rho=-0.12):
    """现场计算49格比分概率矩阵（Dixon-Coles修正）
    输出: {(h,a): prob} 归一化"""
    lh, la = solve_lambda_live(oh, od, oa, o25, u25)  # 🔴2026-09-07评审修复: 原漏传o25(参数错位·u25当o25)·λ反推失真
    if lh is None: return None
    P = {}
    for i in range(7):
        for j in range(7):
            p = pois(i, lh) * pois(j, la)
            if dc_rho:
                if i==0 and j==0: p *= (1 - lh*la*dc_rho)
                elif i==1 and j==0: p *= (1 + la*dc_rho)
                elif i==0 and j==1: p *= (1 + lh*dc_rho)
                elif i==1 and j==1: p *= (1 - dc_rho)
            P[(i,j)] = p
    tot = sum(P.values())
    return {k: v/tot for k, v in P.items()}, lh, la

# ═══════════════════════════════════════════════════════════════
# 2. CS比分盘现场去抽水（市场直接定价·最强信号）
# ═══════════════════════════════════════════════════════════════
def market_net_band(oh, od, oa):
    """🔴市场净胜期望档（2026-09-13·回测: 市场定净胜档 ±1球覆盖 68.3%）
    欧赔去水 → 期望净胜 → 档(H3+/H2/H1/D0/A1/A2/A3+)
    返回 (档名, 期望净胜, (净胜下界, 净胜上界))——上下界按"±1球"口径定锚允许范围"""
    try:
        _inv = {'H': 1/oh, 'D': 1/od, 'A': 1/oa}
    except Exception:
        return None, None, (None, None)
    _t = sum(_inv.values())
    p = {k: v/_t for k, v in _inv.items()}
    en = p['H']*1.35 + p['A']*(-1.35) + p['D']*(-0.05)
    if en >= 1.8:      band, rng = 'H3+', (2, 6)
    elif en >= 0.9:    band, rng = 'H2', (1, 3)
    elif en >= 0.35:   band, rng = 'H1', (0, 2)
    elif en >= -0.35:  band, rng = 'D0', (-1, 1)
    elif en >= -0.9:   band, rng = 'A1', (-2, 0)
    elif en >= -1.8:   band, rng = 'A2', (-3, -1)
    else:              band, rng = 'A3+', (-6, -2)
    return band, en, rng


def anchor_market_check(top_scores, oh, od, oa, o25=None, u25=None, handi=None):
    """🔴锚-市场一致性检查（2026-09-13·用户要求"模型锚定一定要与市场信号一致"·脚本级强制）

    锚（主锚/次锚）必须与市场信号一致，三项逐条核查:
      ① 净胜档: 锚净胜球 ∈ 市场净胜期望档允许范围（±1 球·market_net_band）
      ② 大小球: O25<1.70(市场大球强) → 锚总进球须 ≥3; O25>2.10(市场小球强) → ≤2; 中性可跨档(须标注)
      ③ 盘口方向: handi<0(市场主让) → 锚不应是客胜; handi>0(市场受让) → 锚不应是主胜
    🔴矛盾处理: 以市场为准给出【建议锚】（从候选中筛满足全部约束的最高概率比分）
               → LLM 必须按建议取锚·禁机械照搬 Top1（市场是最校准信号·回测±5pp）
    返回 dict(ok, band, exp_net, checks[], conflicts[], suggestion[])
    """
    band, en, rng = market_net_band(oh, od, oa)
    res = {'ok': True, 'band': band,
           'exp_net': (round(en, 2) if en is not None else None),
           'checks': [], 'conflicts': [], 'suggestion': []}
    if not top_scores:
        return res
    lo, hi = rng
    _big = (o25 is not None and o25 < 1.70)      # 市场大球强
    _small = (o25 is not None and o25 > 2.10)    # 市场小球强
    for lbl, sc in (('主锚', top_scores[0]), ('次锚', top_scores[1] if len(top_scores) > 1 else None)):
        if sc is None:
            continue
        try:
            h, a = map(int, (sc.split(':') if isinstance(sc, str) else sc))
        except Exception:
            continue
        net, tot = h - a, h + a
        msgs = []
        if lo is not None and not (lo <= net <= hi):
            msgs.append('净胜%+d 不在市场档 %s 允许范围 [%+d,%+d]' % (net, band, lo, hi))
        if _big and tot <= 2:
            msgs.append('总进球%d 与市场大球强(O25=%.2f)矛盾(应≥3)' % (tot, o25))
        if _small and tot >= 3:
            msgs.append('总进球%d 与市场小球强(O25=%.2f)矛盾(应≤2)' % (tot, o25))
        if handi is not None:
            if handi < 0 and net < 0:
                msgs.append('客胜锚与市场主让(handi=%.2f)矛盾' % handi)
            if handi > 0 and net > 0:
                msgs.append('主胜锚与市场受让(handi=%.2f)矛盾' % handi)
        if msgs:
            res['ok'] = False
            res['conflicts'].append('%s %s: %s' % (lbl, sc, '; '.join(msgs)))
        else:
            res['checks'].append('%s %s ✅与市场一致' % (lbl, sc))
    if not res['ok']:      # 建议锚: 筛满足全部市场约束的最高概率比分（按传入序即概率序）
        for sc in top_scores:
            try:
                h, a = map(int, (sc.split(':') if isinstance(sc, str) else sc))
            except Exception:
                continue
            net, tot = h - a, h + a
            if lo is not None and not (lo <= net <= hi): continue
            if _big and tot <= 2: continue
            if _small and tot >= 3: continue
            if handi is not None and ((handi < 0 and net < 0) or (handi > 0 and net > 0)): continue
            res['suggestion'].append(sc)
            if len(res['suggestion']) >= 3:
                break
        if not res['suggestion']:
            # 候选池内全不满足市场约束 → 按市场净胜档给基准锚（大球/小球侧修正），提示须扩展候选池
            _base = {'H3+': ['3:0', '3:1'], 'H2': ['2:0', '2:1'], 'H1': ['1:0', '2:1'], 'D0': ['1:1', '0:0'],
                     'A1': ['0:1', '1:2'], 'A2': ['0:2', '1:3'], 'A3+': ['0:3', '1:4']}.get(band, [])
            if _big:
                _base = {'H3+': ['3:1', '4:1'], 'H2': ['2:1', '3:1'], 'H1': ['2:1', '3:2'],
                         'D0': ['2:2', '1:1'], 'A1': ['1:2', '1:3']}.get(band, _base)
            elif _small:
                _base = {'H3+': ['2:0', '3:0'], 'H2': ['2:0', '1:0'], 'H1': ['1:0', '2:0'],
                         'D0': ['0:0', '1:1'], 'A1': ['0:1', '1:0']}.get(band, _base)
            res['suggestion'] = _base[:2]
            res['note'] = '候选池内无满足市场约束者 → 按市场档基准给出（须扩展候选池）'
    return res


def _o25_expect(o25):
    """🔴2026-09-13 修复: O25赔率 → 期望总进球（替代原硬编码三档 2.35/2.70/2.55）

    根因（回测 Matches 148,397 场实测）: 原三档非单调且系统性低估强攻场——
       O2.5 < 1.75   实测场均 3.156 球（原给 2.35 → 低估 0.81 球）
       O2.5 1.75-2.05 实测场均 ≈2.65 球（原给 2.70 → 接近）
       O2.5 ≥ 2.05   实测场均 2.279 球（原给 2.55 → 高估 0.27 球）
       实测场均随 O2.5 赔率单调递减: 4.06/3.44/3.05/2.75/2.55/2.35/2.19/2.02/1.66 球
    修法: 由 goal_bin_probs(goal_bins_table.json·148,397 场实测档分布·2026-09-15 全量重建) 反推期望，
          4+ 档期望取 5.2 球（对 Matches 实测拟合·各档误差 ≤0.15 球）→ 随表自动更新
    兜底: 无表/异常 → 单调近似 3.05/2.70/2.28（Matches 实测三档·仍优于旧值）
    """
    try:
        import os as _os, sys as _sys
        _d = _os.path.dirname(_os.path.abspath(__file__))
        if _d not in _sys.path:
            _sys.path.insert(0, _d)
        from calc_v3572 import goal_bin_probs as _gbp
        _g = _gbp(o25)
        if _g:
            return (_g['prob_01']*0.5 + _g['prob_2']*2 + _g['prob_3']*3 + _g['prob_4']*5.2)
    except Exception:
        pass
    return 3.05 if o25 < 1.75 else (2.70 if o25 < 2.05 else 2.28)


def market_matrix(oh, od, oa, o25, u25=None):
    """🔴市场源矩阵（2026-09-13·用户建议·回测验证: 市场导向权重0.7时Top1+2.09pp/Top2+3.24pp）
    由欧赔去水(净胜期望) + 大小球(总进球期望) 生成比分分布——**参数完全由市场定·非迭代反推**
    与 poisson 源的区别: poisson 用主胜概率迭代解 λh/λa；本源用净胜期望直接定 λ 差（更贴市场）
    """
    inv = {1: 1/oh, 0: 1/od, 2: 1/oa}
    t = sum(inv.values())
    p = {k: v/t for k, v in inv.items()}
    # 总进球期望: O25→期望（🔴2026-09-13 修复: 原硬编码 2.35/2.70/2.55 非单调·低估强攻场 0.81 球
    #   → 改由 goal_bin_probs(148397场实测档分布·2026-09-15重建) 动态反推·随表更新·兜底单调近似·详见 _o25_expect）
    tot = _o25_expect(o25)
    # 净胜期望: 主胜≈+1.4球·客胜≈-1.4球·平≈0
    exp_net = p[1]*1.35 + p[2]*(-1.35) + p[0]*(-0.05)
    lh = max(0.15, (tot + exp_net)/2)
    la = max(0.15, (tot - exp_net)/2)
    import math as _m
    m = {}
    for i in range(7):
        for j in range(7):
            m[(i, j)] = (_m.exp(-lh)*lh**i/_m.factorial(i)) * (_m.exp(-la)*la**j/_m.factorial(j))
    s = sum(m.values())
    return {k: v/s for k, v in m.items()}, (lh, la)


def cs_market_matrix(cs_odds_str):
    """现场解析CS比分盘赔率→去抽水→各比分概率
    cs_odds_str: "1:0=7.5,2:1=8.0,1:1=6.5,0:0=10.0,..."
    输出: {(h,a): prob} + 抽水率"""
    if not cs_odds_str: return None, 0
    import re
    odds = {}
    for kv in re.finditer(r'(\d+:\d+)=([\d.]+)', cs_odds_str):
        odds[kv.group(1)] = float(kv.group(2))
    for kv in re.finditer(r'(胜其他|平其他|负其他|胜其它|平其它|负其它)=([\d.]+)', cs_odds_str):
        odds[kv.group(1)] = float(kv.group(2))
    if len(odds) < 5: return None, 0
    inv = {k: 1/v for k, v in odds.items() if v > 1}
    total = sum(inv.values())
    vig = total - 1
    probs = {k: v/total for k, v in inv.items()}
    # 转换为(h,a)格式
    P = {}
    for k, v in probs.items():
        if ':' in k and '其他' not in k and '其它' not in k:
            h, a = map(int, k.split(':'))
            if h < 7 and a < 7:
                P[(h,a)] = v
    # "其他"概率分配到7+比分（简化：均匀分配到边界）
    other_p = sum(v for k, v in probs.items() if '其他' in k or '其它' in k)
    if other_p > 0 and P:
        # 分配到6:x和x:6的边界格
        boundary = [(6,j) for j in range(7)] + [(i,6) for i in range(6)]
        per = other_p / len(boundary)
        for b in boundary:
            P[b] = P.get(b, 0) + per
    tot = sum(P.values())
    return {k: v/tot for k, v in P.items()}, vig

# ═══════════════════════════════════════════════════════════════
# 3. 亚盘现场约束（净胜球分布）
# ═══════════════════════════════════════════════════════════════
def halftime_precise_matrix(bqc_odds_str, base_matrix):
    """🔴精细半场反推源(V3.5.74 Top2=40版·2026-09-07): 9格赔率→半场方向→方向内具体比分分布→
    P(FT|HT)条件矩阵(ht_ft_cond.json·175476场实测)→全场FT分布·与方向级约束(仅+2pp)本质不同(具体比分+8.9pp@70%)
    输出: {(h,a): prob}或None(无缓存/无bqc/样本不足)"""
    if not bqc_odds_str or base_matrix is None: return None
    import re, os, json as _j
    fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ht_ft_cond.json')
    if not os.path.exists(fp): return None
    try:
        d = _j.load(open(fp, encoding='utf-8'))
        cond = {tuple(map(int,k.split(':'))): {tuple(map(int,kk.split(':'))): pp for kk,pp in v.items()} for k,v in d['cond'].items()}
        dird = d['dir_dist']
        odds = {}
        for kv in re.finditer(r'(胜胜|胜平|胜负|平胜|平平|平负|负胜|负平|负负)=([\d.]+)', bqc_odds_str):
            odds[kv.group(1)] = float(kv.group(2))
        if len(odds) < 6: return None
        inv = {k: 1/v for k, v in odds.items() if v > 1}
        tot = sum(inv.values())
        pr = {k: v/tot for k, v in inv.items()}
        htd = {'H': pr.get('胜胜',0)+pr.get('胜平',0)+pr.get('胜负',0),
               'D': pr.get('平胜',0)+pr.get('平平',0)+pr.get('平负',0),
               'A': pr.get('负胜',0)+pr.get('负平',0)+pr.get('负负',0)}
        st = htd['H']+htd['D']+htd['A']
        if st <= 0: return None
        htd = {k: v/st for k, v in htd.items()}
        # 半场比分分布 = Σ方向概率×方向内具体比分分布
        ht_dist = {}
        for dr, pd_ in htd.items():
            for ks, pv in dird.get(dr, {}).items():
                hh, aa = map(int, ks.split(':'))
                ht_dist[(hh, aa)] = ht_dist.get((hh, aa), 0) + pd_*pv
        if not ht_dist: return None
        # 全场 = Σ P(HT)×P(FT|HT)
        ft = {}
        for ht, ph in ht_dist.items():
            for ftk, pf in cond.get(ht, {}).items():
                ft[ftk] = ft.get(ftk, 0) + ph*pf
        t2 = sum(ft.values())
        if t2 <= 0: return None
        return {k: v/t2 for k, v in ft.items()}
    except Exception:
        return None


def _bqc_to_ht_dist(bqc_odds_str):
    """🔴公共: 9格半全场赔率→半场方向(归一)→半场具体比分分布ht_dist(2026-09-09 DRY重构)
    返回 (ht_dist{(h,a):p}, htd{H/D/A:p}, odds{9格}) 或 None
    halftime_precise_matrix / extract_ht_goals_layer 共用·逻辑单一来源"""
    if not bqc_odds_str:
        return None
    import re, os, json as _j
    fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ht_ft_cond.json')
    if not os.path.exists(fp):
        return None
    try:
        d = _j.load(open(fp, encoding='utf-8'))
        dird = d['dir_dist']
        odds = {}
        for kv in re.finditer(r'(胜胜|胜平|胜负|平胜|平平|平负|负胜|负平|负负)=([\d.]+)', bqc_odds_str):
            odds[kv.group(1)] = float(kv.group(2))
        if len(odds) < 6:
            return None
        inv = {k: 1 / v for k, v in odds.items() if v > 1}
        tot = sum(inv.values())
        if tot <= 0:
            return None
        pr = {k: v / tot for k, v in inv.items()}
        htd = {'H': pr.get('胜胜', 0) + pr.get('胜平', 0) + pr.get('胜负', 0),
               'D': pr.get('平胜', 0) + pr.get('平平', 0) + pr.get('平负', 0),
               'A': pr.get('负胜', 0) + pr.get('负平', 0) + pr.get('负负', 0)}
        st = htd['H'] + htd['D'] + htd['A']
        if st <= 0:
            return None
        htd = {k: v / st for k, v in htd.items()}
        ht_dist = {}
        for dr, pd_ in htd.items():
            for ks, pv in dird.get(dr, {}).items():
                hh, aa = map(int, ks.split(':'))
                ht_dist[(hh, aa)] = ht_dist.get((hh, aa), 0) + pd_ * pv
        if not ht_dist:
            return None
        return ht_dist, htd, odds
    except Exception:
        return None


def extract_ht_goals_layer(bqc_odds_str):
    """🔴半场进球推断→全场5层量级(V3.0方案F1·2026-09-09·上限验证43.8% vs O25 26.9%·+16.9pp)
    链路: _bqc_to_ht_dist(公共·9格→半场方向→半场比分分布) → 进球数聚合(0/1/2/3+) →
    ht_ft_cond 175476场 P(FT|HT) 按5层聚合 → 全场5层[L1..L5](0-1/2/3/4/5+球) + 期望 + 置信
    输出: {'layers':[p0..p4], 'ht_goals':{'0':p,'1':p,'2':p,'3':p}, 'confidence':0-1, 'mean_ft':期望球}
    confidence(方案3.4离散): 9格最小赔率 <3.0→1.0(强信号) / <4→0.7 / <5→0.5 / else 0.3(分散·仅参考)
    边界: 半场推断=统计均值型(无法捕捉下半场事件如红牌/防线崩→归O14双向调节+量级台账)"""
    r = _bqc_to_ht_dist(bqc_odds_str)
    if not r:
        return None
    ht_dist, htd, odds = r
    import os, json as _j
    fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ht_ft_cond.json')
    d = _j.load(open(fp, encoding='utf-8'))
    cond = {tuple(map(int, k.split(':'))): {tuple(map(int, kk.split(':'))): pp for kk, pp in v.items()}
            for k, v in d['cond'].items()}
    # 半场进球数分布(0/1/2/3+)
    hg = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0}
    for (hh, aa), ph in ht_dist.items():
        hg[min(hh + aa, 3)] += ph
    # 半场比分→全场5层(0-1/2/3/4/5+·tg<=1/2/3/4/5+)
    layers = [0.0, 0.0, 0.0, 0.0, 0.0]
    for ht, ph in ht_dist.items():
        for (fh, fa), pf in cond.get(ht, {}).items():
            tg = fh + fa
            li = 0 if tg <= 1 else (1 if tg == 2 else (2 if tg == 3 else (3 if tg == 4 else 4)))
            layers[li] += ph * pf
    t2 = sum(layers)
    if t2 <= 0:
        return None
    layers = [x / t2 for x in layers]
    _minodd = min(odds.values())
    conf = 1.0 if _minodd < 3.0 else (0.7 if _minodd < 4.0 else (0.5 if _minodd < 5.0 else 0.3))
    mean_ft = sum((i + 1) * layers[i] for i in range(4)) + 5.5 * layers[4]  # 层中心近似
    return {'layers': [round(x, 4) for x in layers], 'ht_goals': {str(k): round(v, 4) for k, v in hg.items()},
            'confidence': round(conf, 3), 'mean_ft': round(mean_ft, 2)}


def handi_constraint_matrix(handi, base_matrix):
    """用本场亚盘盘口约束净胜球分布
    原理：盘口反映庄家对净胜球的预期，对偏离盘口的比分降权
    handi: 负=主让，如-0.75
    输出: 约束权重矩阵（与base_matrix同shape）"""
    if handi is None or base_matrix is None: return None
    # 盘口→预期净胜球（主让0.5→预期净胜+0.5左右）
    expected_net = -handi  # 主让0.5→expected_net=+0.5
    # 正态分布权重：净胜球越接近期望，权重越高
    sigma = 1.2  # 净胜球标准差（基于23万场数据约1.2）
    W = {}
    for (h, a), p in base_matrix.items():
        net = h - a
        w = math.exp(-0.5 * ((net - expected_net) / sigma) ** 2)
        W[(h,a)] = w
    # 归一化权重
    wsum = sum(W.values())
    return {k: v/wsum for k, v in W.items()}

# ═══════════════════════════════════════════════════════════════
# 4. 大小球现场约束（总进球分布）
# ═══════════════════════════════════════════════════════════════
def total_goals_constraint_matrix(o25, u25, base_matrix):
    """用本场大小球赔率约束总进球分布
    原理：O2.5隐含大球率，对总进球偏离的比分降权"""
    if not o25 or not base_matrix: return None
    if u25 is None: u25 = max(1.01, 1/(1.04 - 1/o25))
    po, pu = 1/o25, 1/u25
    p_over = po / (po + pu)  # 大球率
    p_under = 1 - p_over
    # 计算基础分布的大球率
    base_over = sum(p for (h,a), p in base_matrix.items() if h+a >= 3)
    # 调整因子：如果市场大球率>基础大球率，对大比分升权
    ratio_over = p_over / max(base_over, 0.01)
    ratio_under = p_under / max(1 - base_over, 0.01)
    W = {}
    for (h, a), p in base_matrix.items():
        if h + a >= 3:
            W[(h,a)] = ratio_over
        else:
            W[(h,a)] = ratio_under
    wsum = sum(W.values())
    return {k: v/wsum for k, v in W.items()}

# ═══════════════════════════════════════════════════════════════
# 5. 半全场现场约束（半场比分）
# ═══════════════════════════════════════════════════════════════
def halftime_constraint_matrix(bqc_odds_str, base_matrix):
    """用本场半全场赔率约束半场比分，进而约束全场比分
    简化：半场主胜/平/客概率→全场比分的方向性约束"""
    if not bqc_odds_str or not base_matrix: return None
    import re
    odds = {}
    for kv in re.finditer(r'(胜胜|胜平|胜负|平胜|平平|平负|负胜|负平|负负)=([\d.]+)', bqc_odds_str):
        odds[kv.group(1)] = float(kv.group(2))
    if len(odds) < 6: return None
    inv = {k: 1/v for k, v in odds.items() if v > 1}
    total = sum(inv.values())
    probs = {k: v/total for k, v in inv.items()}
    # 半场方向概率
    ht_home = probs.get('胜胜',0) + probs.get('胜平',0) + probs.get('胜负',0)
    ht_draw = probs.get('平胜',0) + probs.get('平平',0) + probs.get('平负',0)
    ht_away = probs.get('负胜',0) + probs.get('负平',0) + probs.get('负负',0)
    # 半场领先方最终胜率更高（半场主胜→全场主胜概率升）
    W = {}
    for (h, a), p in base_matrix.items():
        if h > a:  # 全场主胜
            w = 0.5 + ht_home * 0.5  # 半场主胜概率高→全场主胜升权
        elif h == a:
            w = 0.5 + ht_draw * 0.3
        else:
            w = 0.5 + ht_away * 0.5
        W[(h,a)] = max(w, 0.1)
    wsum = sum(W.values())
    return {k: v/wsum for k, v in W.items()}

# ═══════════════════════════════════════════════════════════════
# 6. 动态权重计算（基于数据完整度+一致性）
# ═══════════════════════════════════════════════════════════════
def kl_divergence(p, q):
    """两个分布的KL散度（用于衡量一致性）"""
    kl = 0
    keys = set(p) | set(q)
    for k in keys:
        pk = p.get(k, 1e-6)
        qk = q.get(k, 1e-6)
        if pk > 0 and qk > 0:
            kl += pk * math.log(pk / qk)
    return kl

def calculate_dynamic_weights(matrices, data_completeness):
    """现场计算各源权重
    原则：
    - 数据完整度高的源权重高
    - 与其他源一致性高的源权重高（离群源降权）
    - CS比分盘权重上限0.35（抽水高，信息直接但噪声大）
    - 泊松基础权重0.25-0.35（平滑可靠）
    - 约束源（亚盘/大小球/半全场）各0.1-0.15
    """
    sources = list(matrices.keys())
    # 初始权重基于数据完整度
    base_w = {
        'market': 0.30,   # 🔴🔴市场源(2026-09-13·用户建议+回测寻优: 市场应占~70%·Top1 14.37%@市场.7/泊松.15/约束.075)
        'poisson': 0.07,  # 下调(与market同源冗余·仅保留平滑·回测: 泊松>30%反而降准确)
        'ht': 0.24 if data_completeness.get('ht', 0) > 0.5 else 0,          # 精细半场反推(19类·独立信息源·保留)
        'cs': 0.20 if data_completeness.get('cs', 0) > 0.5 else 0,          # CS比分盘(独立信息·独立市场)
        'handi': 0.06 if data_completeness.get('handi', 0) > 0 else 0,       # 🔴约束源下调(回测: 高斯近似是噪声源·原0.13→0.06)
        'total': 0.06 if data_completeness.get('total', 0) > 0 else 0,       # 🔴约束源下调(原0.12→0.06)
        'halftime': 0.10 if data_completeness.get('halftime', 0) > 0.5 else 0,  # 退化方向级(精细不可用时)
    }
    # 一致性调整：计算各源与泊松的KL散度，离群源降权
    if 'poisson' in matrices and 'cs' in matrices:
        kl = kl_divergence(matrices['poisson'], matrices['cs'])
        if kl > 0.3:  # 显著偏离
            base_w['cs'] *= 0.7  # CS离群降权30%
            base_w['poisson'] *= 1.1
    # 归一化
    total = sum(base_w.values())
    if total == 0:
        return {'poisson': 1.0}
    return {k: round(v/total, 3) for k, v in base_w.items() if v > 0}

# ═══════════════════════════════════════════════════════════════
# 7. 贝叶斯融合
# ═══════════════════════════════════════════════════════════════
def bayesian_fusion(matrices, weights):
    """多源贝叶斯融合：P_final ∝ ∏ P_source^w
    所有源基于本场数据现场计算，不查固定表"""
    if not matrices: return None
    keys = set()
    for m in matrices.values():
        keys |= set(m.keys())
    post = {}
    for k in keys:
        p = 1.0
        for src, w in weights.items():
            pk = matrices.get(src, {}).get(k, 1e-6)
            p *= pk ** w
        post[k] = p
    tot = sum(post.values())
    return {k: v/tot for k, v in post.items()}

# ═══════════════════════════════════════════════════════════════
# 8. 主入口：现场分析
# ═══════════════════════════════════════════════════════════════
def analyze_live(oh, od, oa, o25, u25=None, handi=None, cs_odds=None, bqc_odds=None):
    """🔴现场比分分析主入口
    所有概率基于本场比赛实时数据计算，不查固定表
    输出: Top10比分 + 各源贡献 + 动态权重 + 置信度 + 不确定性"""
    result = {'status': 'ok', 'sources_used': [], 'warnings': []}

    # 步骤1：泊松现场反推（必须有）
    pm = poisson_matrix(oh, od, oa, o25, u25)
    if pm is None:
        return {'status': 'error', 'message': '泊松反推失败（赔率无效）'}
    poisson_P, lh, la = pm
    matrices = {'poisson': poisson_P}
    # 🔴市场源（2026-09-13·用户建议+回测验证）
    try:
        _mkt, _lam = market_matrix(oh, od, oa, o25, u25)
        matrices['market'] = _mkt
        result['market_lambda'] = {'home': round(_lam[0], 2), 'away': round(_lam[1], 2)}
    except Exception as _e:
        result['warnings'].append('市场源失败:' + str(_e)[:40])
    result['lambda'] = {'home': round(lh,2), 'away': round(la,2), 'total': round(lh+la,2)}
    result['sources_used'].append('poisson')

    # 步骤2：CS比分盘(优先cs_deep_analyzer抽水偏差·V3.5.74审计: 原简单去水弱化CS深度·深接·退化简单)
    cs_P, cs_vig = None, 0
    try:
        import sys as _sy2, os as _os2
        _sy2.path.insert(0, _os2.path.dirname(_os2.path.abspath(__file__)))
        from cs_deep_analyzer import cs_vig_analysis
        _dP, _vig = cs_vig_analysis(cs_odds)
        if _dP:
            cs_P, cs_vig = _dP, (_vig or 0)
    except Exception:
        pass
    if cs_P is None:
        cs_P, cs_vig = cs_market_matrix(cs_odds)
    if cs_P:
        matrices['cs'] = cs_P
        result['cs_vig'] = f'{cs_vig*100:.1f}%'
        result['sources_used'].append('cs')
    else:
        result['warnings'].append('无CS比分盘数据·降级为泊松+约束')

    # 步骤3：亚盘约束（如有）
    if handi is not None:
        hw = handi_constraint_matrix(handi, poisson_P)
        if hw:
            matrices['handi'] = hw
            result['sources_used'].append('handi')

    # 步骤4：大小球约束
    tw = total_goals_constraint_matrix(o25, u25, poisson_P)
    if tw:
        matrices['total'] = tw
        result['sources_used'].append('total')

    # 步骤5：精细半场反推源(优先·ht_ft_cond.json 19类·最大增益源·方案Top2=40) 失败退化方向级约束
    ht_P = halftime_precise_matrix(bqc_odds, poisson_P)
    if ht_P:
        matrices['ht'] = ht_P
        result['sources_used'].append('ht(精细半场反推)')
    else:
        htw = halftime_constraint_matrix(bqc_odds, poisson_P)
        if htw:
            matrices['halftime'] = htw
            result['sources_used'].append('halftime(方向级退化)')

    # 步骤6：动态权重
    data_comp = {
        'cs': 1.0 if cs_P else 0,
        'handi': 1.0 if handi is not None else 0,
        'total': 1.0,
        'ht': 1.0 if ht_P else 0,
        'halftime': 1.0 if ('halftime' in matrices) else 0,
    }
    weights = calculate_dynamic_weights(matrices, data_comp)
    result['dynamic_weights'] = weights

    # 步骤5.5：16格先验表弱先验(2026-09-07·降级·🔴禁机械锚定·仅弱平滑/数据不足兜底)
    try:
        import json as _json, os as _os
        _fp = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'odds_score_prior.json')
        if _os.path.exists(_fp):
            _pr = _json.load(open(_fp, encoding='utf-8'))['bins']
            # 定位格: 按主胜赔率+O2.5 (od档近似)
            def _bin_find(v, lo, hi): return lo <= v < hi
            _key = None
            for _k, _g in _pr.items():
                _o, _q = _g['odd'], _g['o25']
                if _o[0] <= oh < _o[1] and _q[0] <= o25 < _q[1]: _key = _k; break
            if _key is None:  # 边界兜底(找最近档)
                for _k, _g in _pr.items():
                    _o, _q = _g['odd'], _g['o25']
                    if abs((_o[0]+_o[1])/2-oh) < 0.3 and abs((_q[0]+_q[1])/2-o25) < 0.6: _key = _k; break
            if _key:
                _prior = {}
                for _sc, _p in _pr[_key]['top5']:
                    _hh, _aa = map(int, _sc.split(':'))
                    _prior[(_hh, _aa)] = float(_p)/100
                _t = sum(_prior.values())
                _prior = {k: v/_t for k, v in _prior.items()}
                result['prior_bin'] = _key
                # 权重: 数据足(≥4源)→0.08弱平滑·数据不足(≤2源)→0.25兜底
                _pw = 0.08 if len(matrices) >= 4 else (0.25 if len(matrices) <= 2 else 0.15)
                matrices['prior'] = _prior
                weights['prior'] = _pw
                _wt = sum(weights.values())
                weights = {k: round(v/_wt, 3) for k, v in weights.items()}
                result['dynamic_weights'] = weights
    except Exception as _e:
        result['warnings'].append('先验表加载失败:' + str(_e)[:50])

    # 步骤7：贝叶斯融合
    final_P = bayesian_fusion(matrices, weights)
    if final_P is None:
        return {'status': 'error', 'message': '融合失败'}

    # 🔴步骤7.5：量级一致性重排（2026-09-13·用户指出"判大球却机械锚定1:1"根因修复）
    #   问题: 融合后直接按概率排序 → CS/半场/泊松共同倾向 1:1 → 1:1 惯性主导
    #        导致"大球判定 + 小球锚(1:1)"的逻辑不自洽（case164: 大球4+36.9% 却锚1:1·真实2:2）
    #   修正: 按大小球判定对候选**降权重排**（不排除·只降权·保留全谱）
    _tot = sum(final_P.values()) or 1
    _over_p = sum(p for (h, a), p in final_P.items() if h + a >= 3) / _tot
    # 🔴判据优先级: O25 市场直读（最可靠）→ 融合 over_p 兜底
    #   O25<1.70=大球强 · O25>2.10=小球强（与 goalbins 分档一致）
    _mag_tag = ''
    _big = (o25 is not None and o25 < 1.70) or (o25 is None and _over_p >= 0.55)
    _small = (o25 is not None and o25 > 2.10) or (o25 is None and _over_p <= 0.42)
    if _big:                     # 大球强 → 低分比分降权
        for _k in list(final_P):
            _s = sum(_k)
            if _s <= 1:
                final_P[_k] *= 0.60      # 0:0/1:0/0:1 降权 40%
            elif _s == 2:
                final_P[_k] *= 0.85      # 1:1/2:0/0:2 降权 15%
        _mag_tag = '大球强(O25=%.2f)→低分降权' % (o25 or 0)
    elif _small:                 # 小球强 → 高分比分降权
        for _k in list(final_P):
            if sum(_k) >= 3:
                final_P[_k] *= 0.60
        _mag_tag = '小球强(O25=%.2f)→高分降权' % (o25 or 0)
    if _mag_tag:
        _t2 = sum(final_P.values()) or 1
        final_P = {k: v / _t2 for k, v in final_P.items()}
        result['magnitude_rerank'] = _mag_tag

    # 步骤8：输出Top10
    ranked = sorted(final_P.items(), key=lambda x: -x[1])[:10]
    # 🔴量级-锚一致性告警（2026-09-13）: Top1 总进球与量级判定矛盾时显式告警
    if ranked:
        _top1 = ranked[0][0]
        _g1 = sum(_top1)
        _big_cands = [f'{h}:{a}' for (h, a), _p in sorted(final_P.items(), key=lambda x: -x[1]) if sum((h, a)) >= 3][:3]
        _small_cands = [f'{h}:{a}' for (h, a), _p in sorted(final_P.items(), key=lambda x: -x[1]) if sum((h, a)) <= 2][:3]
        if _big and _g1 <= 2:
            result['warnings'].append(
                '⚠️锚-量级矛盾: 大球强(O25=%.2f)但Top1=%d:%d(%d球) → 主锚应取≥3球比分: %s'
                % (o25 or 0, _top1[0], _top1[1], _g1, ' / '.join(_big_cands) or '无'))
        elif _small and _g1 >= 3:
            result['warnings'].append(
                '⚠️锚-量级矛盾: 小球强(O25=%.2f)但Top1=%d:%d(%d球) → 主锚应取≤2球比分: %s'
                % (o25 or 0, _top1[0], _top1[1], _g1, ' / '.join(_small_cands) or '无'))
    result['top10'] = [{'score': f'{h}:{a}', 'prob': round(p*100,1)} for (h,a), p in ranked]

    # 🔴步骤8.5：锚-市场一致性检查（2026-09-13·用户要求"模型锚定一定要与市场信号一致"·脚本级强制）
    #   锚(主锚/次锚)须与市场信号三项一致: ①净胜档∈市场净胜期望档±1球 ②总进球方向 vs 市场大小球 ③方向 vs 亚盘
    #   矛盾 → 以市场为准给【建议锚】（LLM 必须按建议取锚·禁机械照搬 Top1）
    _amc = anchor_market_check([f'{h}:{a}' for (h, a), _p in ranked], oh, od, oa,
                               o25=o25, u25=u25, handi=handi)
    result['market_anchor_check'] = _amc
    if not _amc['ok']:
        result['warnings'].append(
            '⚠️锚-市场矛盾: ' + ' | '.join(_amc['conflicts'])
            + ' → 以市场档 %s(净胜%+.2f球) 为基准取锚 · 🔴建议锚: %s（LLM 必须按建议取锚·禁机械照搬 Top1）'
            % (_amc['band'], _amc['exp_net'] or 0, ' / '.join(_amc['suggestion']) or '无候选'))

    # 各源Top3对比（贡献分解）
    result['source_top3'] = {}
    for src, m in matrices.items():
        top3 = sorted(m.items(), key=lambda x: -x[1])[:3]
        result['source_top3'][src] = [f'{h}:{a}({p*100:.1f}%)' for (h,a), p in top3]

    # 聚合统计
    home_p = sum(p for (h,a), p in final_P.items() if h > a)
    draw_p = sum(p for (h,a), p in final_P.items() if h == a)
    away_p = sum(p for (h,a), p in final_P.items() if h < a)
    over_p = sum(p for (h,a), p in final_P.items() if h+a >= 3)
    result['aggregated'] = {
        'home_win': f'{home_p*100:.1f}%', 'draw': f'{draw_p*100:.1f}%', 'away_win': f'{away_p*100:.1f}%',
        'over25': f'{over_p*100:.1f}%', 'under25': f'{(1-over_p)*100:.1f}%',
        'mean_goals': round(sum((h+a)*p for (h,a),p in final_P.items()),2)
    }

    # 置信度：基于Top1概率和源数量
    top1_p = ranked[0][1] if ranked else 0
    n_src = len(matrices)
    if top1_p > 0.15 and n_src >= 4:
        conf = 'HIGH'
    elif top1_p > 0.12 and n_src >= 3:
        conf = 'MID'
    elif top1_p > 0.10:
        conf = 'MID-LOW'
    else:
        conf = 'LOW'
    result['confidence'] = conf
    result['top1_prob'] = f'{top1_p*100:.1f}%'

    # 不确定性标注
    if n_src <= 2:
        result['uncertainty'] = '数据源不足(≤2)·建议多覆盖Top3-5'
    elif top1_p < 0.10:
        result['uncertainty'] = '比分高度分散(Top1<10%)·建议覆盖Top5'
    elif cs_P and kl_divergence(poisson_P, cs_P) > 0.3:
        result['uncertainty'] = '泊松与CS显著分歧·市场与模型观点冲突·谨慎单选'
    else:
        result['uncertainty'] = '多源一致·可聚焦Top2-3'

    return result

# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='现场动态比分概率引擎')
    ap.add_argument('--home', type=float, required=True)
    ap.add_argument('--draw', type=float, required=True)
    ap.add_argument('--away', type=float, required=True)
    ap.add_argument('--o25', type=float, required=True)
    ap.add_argument('--u25', type=float)
    ap.add_argument('--handi', type=float)
    ap.add_argument('--cs', type=str, help='比分盘赔率 如 "1:0=7.5,2:1=8.0,1:1=6.5"')
    ap.add_argument('--bqc', type=str, help='半全场赔率 如 "胜胜=3.0,平平=5.0"')
    a = ap.parse_args()
    r = analyze_live(a.home, a.draw, a.away, a.o25, a.u25, a.handi, a.cs, a.bqc)
    print(json.dumps(r, ensure_ascii=False, indent=2))
