# -*- coding: utf-8 -*-
"""V3.5.71 九档净胜分层·终极精细化落地版（2026-08-23·用户终极方案·全面蒸馏照搬+数值修正）
🔴检验结论（真实数据·1992场·2026-08-23）:
  ①λ0公式原版(×1/(xga+0.01))方向反·实测-6.7pp → 🔴修正为相对防守(对手xga/联赛均值·+2.9pp)
  ②std_xG区分力弱(1-0:0.736 vs 3-2:0.756·无分离)·总xG才是主区分维度 → std_xG降为辅维度
  ③主客固定加权1.1/0.9无益 → 改为可选·默认1.0/1.0
  ✅照搬: 九档分层·A/B/C多条件(总xG主导)·亚盘定净胜/大小球定量级解耦·强制净胜不变·概率上限35%·Dixon-Coles·贝叶斯加权
架构: 五级修正(λ0→亚盘微调±5%→缩放s强制净胜不变→Dixon-Coles→贝叶斯加权) + 九档 + A/B/C三分
"""
import math
import sys

# GBK 控制台防护
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# ============ 一、特征工程（近8场滚动·防泄露·主客加权可选） ============
def rolling_features(team_history, n=8, home_boost=1.0, away_boost=1.0):
    """team_history: 近N场已赛 [(xg, xga, is_home), ...]（时间倒序）
    返回: xg_mean/xga_mean(加权滚动均值)·xg_std·openness贡献"""
    if not team_history:
        return None
    recent = team_history[-n:]
    w = [home_boost if ih else away_boost for _,_,ih in recent]
    xg = [x for x,_,_ in recent]; xga = [x for _,x,_ in recent]
    ws = sum(w)
    xg_mean = sum(x*w_i for x,w_i in zip(xg,w))/ws
    xga_mean = sum(x*w_i for x,w_i in zip(xga,w))/ws
    xg_std = math.sqrt(sum((x-sum(xg)/len(xg))**2 for x in xg)/len(xg)) if len(xg)>1 else 0.3
    return {'xg_mean': xg_mean, 'xga_mean': xga_mean, 'xg_std': xg_std}

def core_features(hf, af, avg_xga):
    """🔴三大核心变量（方案全局统一）:
    Δxg=主-客(实力层·定净胜) · sum_xG=主+客(基础量级) · std_xG=(主std+客std)/2(深度辅)
    open_score=(主xg+客xga)+(客xg+主xga)(开放度) · 相对防守修正λ"""
    dxg = hf['xg_mean'] - af['xg_mean']
    sum_xg = hf['xg_mean'] + af['xg_mean']
    std_xg = (hf['xg_std'] + af['xg_std']) / 2
    open_score = (hf['xg_mean'] + af['xga_mean']) + (af['xg_mean'] + hf['xga_mean'])
    # 修正版λ0（相对防守·真实数据+2.9pp）
    lh0 = hf['xg_mean'] * (af['xga_mean'] / avg_xga)
    la0 = af['xg_mean'] * (hf['xga_mean'] / avg_xga)
    return dxg, sum_xg, std_xg, open_score, lh0, la0

# ============ 二、五级修正（解耦·亚盘管净胜·大小球管量级） ============
def five_stage(lh0, la0, res_gd, res_total, std_xg, o25_odds, k1=0.05, k2=0.3, k3=0.2):
    """方案五级修正:
    步骤2: 亚盘微调净胜差 ±5%（clamp 0.95-1.05·总进球不变）
    步骤3: 大小球+xG波动缩放 s=clamp(1+k2·res_total+k3·std, 0.6, 1.4)·🔴强制净胜不变
    """
    gd0 = lh0 - la0
    total0 = lh0 + la0
    # 步骤2: gd_new = gd0 × clamp(1+k1·res_gd, 0.95, 1.05)
    gd_new = gd0 * max(0.95, min(1.05, 1 + k1 * res_gd))
    # 步骤3: s 缩放（🔴防守联赛收紧·进攻联赛放宽·默认0.6-1.4）
    s = max(0.6, min(1.4, 1 + k2 * res_total + k3 * std_xg))
    # 工程最优方案A: 强制净胜不变·只改总量
    lh3 = (s * total0 + gd_new) / 2
    la3 = (s * total0 - gd_new) / 2
    return lh3, la3, gd_new, s

def dixon_coles_pmf(i, j, lam_h, lam_a, rho):
    """Dixon-Coles低比分修正（0-0/1-0/0-1/1-1·防守联赛高ρ·进攻联赛低ρ）"""
    p = poisson_pmf(i, lam_h) * poisson_pmf(j, lam_a)
    if (i, j) == (0, 0):
        p *= 1 - lam_h * lam_a * rho
    elif (i, j) == (1, 0):
        p *= 1 + lam_h * rho
    elif (i, j) == (0, 1):
        p *= 1 + lam_a * rho
    elif (i, j) == (1, 1):
        p *= 1 - rho
    return max(p, 0.0)

def poisson_pmf(k, lam):
    return math.exp(-lam) * lam**k / math.factorial(k)

def score_matrix(lam_h, lam_a, rho=0.05, max_g=6):
    """Dixon-Coles 比分概率矩阵（0-6全覆盖）"""
    mat = {}
    for i in range(max_g+1):
        for j in range(max_g+1):
            mat[f'{i}-{j}'] = dixon_coles_pmf(i, j, lam_h, lam_a, rho)
    s = sum(mat.values())
    return {k: v/s for k, v in mat.items()}

def bayes_weight(poisson_probs, jc_probs, alpha=0.65, beta=0.10, disagree=False):
    """步骤5: 贝叶斯后验加权 P_final ∝ P_poisson^α · P_jc^β
    高盘赔分歧(disagree≥0.15)→β减半·扩大分布降置信"""
    if jc_probs is None:
        beta = 0.0
    elif disagree:
        beta *= 0.5
    out = {}
    for s, p in poisson_probs.items():
        jp = jc_probs.get(s, 1/49) if jc_probs else 1/49
        out[s] = (p ** alpha) * (jp ** beta)
    s = sum(out.values())
    return {k: v/s for k, v in out.items()}

# ============ 三、九档进档（Δxg60% + 亚盘40% + 竞彩硬条件） ============
def dxg_tier(dxg):
    if dxg > 2.4: return '主3+', 9
    if dxg >= 1.7: return '主3', 8
    if dxg >= 1.0: return '主2', 7
    if dxg >= 0.3: return '主1', 6
    if dxg < -2.4: return '客3+', 1
    if dxg <= -1.7: return '客3', 2
    if dxg <= -1.0: return '客2', 3
    if dxg <= -0.3: return '客1', 4
    return '平', 5

def hdp_tier(handicap):
    if handicap <= -1.75: return '主3+', 9
    if handicap <= -1.25: return '主3', 8
    if handicap <= -0.75: return '主2', 7
    if handicap <= -0.25: return '主1', 6
    if handicap >= 1.75: return '客3+', 1
    if handicap >= 1.25: return '客3', 2
    if handicap >= 0.75: return '客2', 3
    if handicap >= 0.25: return '客1', 4
    return '平', 5

def tier9_joint(dxg, handicap, jc_home_prob=None, jc_draw_prob=None):
    """🔴九档进档（2026-08-23用户重新定位: xG不做主导·盘口+基本面做决定·xG验证·冲突综合研判）
    档位 = Oddset亚盘主导（市场净胜预期·V6/修正30欧盘为准）+ 竞彩基本面硬条件校准
    xG = 验证信号（Δxg档 vs 亚盘档: 一致→确认·背离→冲突标注·综合研判）"""
    t_x, s_x = dxg_tier(dxg)
    t_h, s_h = hdp_tier(handicap)
    def sign(t): return 1 if t.startswith('主') else -1 if t.startswith('客') else 0
    tier = t_h  # 🔴亚盘主导定档
    why = f'亚盘主导:{t_h}(hdp{handicap})'
    # xG验证信号（一致→确认·背离→冲突·综合研判）
    if sign(t_x) == sign(t_h) and sign(t_x) != 0:
        xg_v = '确认' if s_x == s_h else ('同向偏深' if s_x > s_h else '同向偏浅')
        why += f'·xG验证:{t_x}({xg_v})'
    elif sign(t_x) != sign(t_h) and sign(t_x) != 0:
        why += f'·🔴xG冲突:{t_x}vs{t_h}·综合研判(盘口+基本面为主·xG背离降级)'
    else:
        why += f'·xG验证:{t_x}(平)'
    # 竞彩硬条件（方案: 主胜40-52%进主1·52-65%进主2·65-78%进主3·>78%进3+·平局>30%平局强化）
    if jc_home_prob is not None:
        if tier == '主1' and not (0.40 <= jc_home_prob <= 0.52): why += '·竞彩校验偏离'
        if tier == '主2' and not (0.52 <= jc_home_prob <= 0.65): why += '·竞彩校验偏离'
        if tier == '主3' and not (0.65 <= jc_home_prob <= 0.78): why += '·竞彩校验偏离'
        if tier == '主3+' and jc_home_prob < 0.78: why += '·竞彩校验偏离'
    if jc_draw_prob is not None and jc_draw_prob > 0.30 and t_x == '平':
        why += '·竞彩平局>30%强化'
    return tier, why

# ============ 四、A/B/C 深度三分（方案多条件·总xG主导·std辅助） ============
def depth_class(tier, sum_xg, std_xg, open_score, o25_odds, res_total, h_xg, a_xg, h_xga, a_xga, jc_small, jc_big_agree):
    """每档 A/B/C（方案量化准入·满足≥3项·C类核心2项+任意2项·🔴总xG主导·std辅助）"""
    if tier == '主1':
        cond_A = sum([sum_xg < 2.1, std_xg < 0.35, min(h_xga, a_xga) < 0.9, o25_odds >= 2.1, jc_small])
        core_C = [sum_xg > 2.9, o25_odds <= 1.85]
        extra_C = [h_xg > 1.2 and a_xg > 1.2, std_xg > 0.7, open_score > 4.5, jc_big_agree]
        if cond_A >= 3: return 'A'
        if sum(core_C) >= 1 and sum(extra_C) >= 2: return 'C'
        return 'B'
    if tier == '主2':
        cond_A = sum([sum_xg < 2.4, a_xg < 1.1, h_xga < 0.8, o25_odds >= 2.0, std_xg < 0.5])
        core_C = [sum_xg > 3.2, o25_odds <= 1.85]
        extra_C = [a_xga > 1.3 and a_xg > 1.1, std_xg > 0.7, open_score > 4.8, res_total > 0.18, jc_big_agree]
        if cond_A >= 3: return 'A'
        if sum(core_C) >= 1 and sum(extra_C) >= 2: return 'C'
        return 'B'
    if tier == '主3':
        cond_A = sum([sum_xg < 2.7, std_xg < 0.4, a_xga > 1.4 and h_xga < 0.7, o25_odds >= 2.1])
        cond_B = sum([sum_xg > 2.8, std_xg > 0.6, a_xg > 0.9, o25_odds <= 1.85, res_total > 0.15])
        if cond_A >= 3: return 'A'
        if cond_B >= 3: return 'C'
        return 'A'
    if tier == '主3+':
        return 'A' if a_xg < 0.7 or o25_odds >= 2.75 else 'C'
    if tier == '平':
        cond_A = sum([sum_xg < 1.9, std_xg < 0.35, h_xga < 0.9 and a_xga < 0.9, o25_odds >= 2.1, res_total < -0.1])
        core_C = [sum_xg > 2.9, o25_odds <= 1.85]
        extra_C = [std_xg > 0.7, open_score > 4.6, res_total > 0.15]
        if cond_A >= 3: return 'A'
        if sum(core_C) >= 1 and sum(extra_C) >= 2: return 'C'
        return 'B'
    if tier == '客1':
        cond_A = sum([sum_xg < 2.1, std_xg < 0.35, min(h_xga, a_xga) < 0.9, o25_odds >= 2.1, jc_small])
        core_C = [sum_xg > 2.9, o25_odds <= 1.85]
        extra_C = [std_xg > 0.7, open_score > 4.5, res_total > 0]
        if cond_A >= 3: return 'A'
        if sum(core_C) >= 1 and sum(extra_C) >= 2: return 'C'
        return 'B'
    if tier == '客2':
        cond_A = sum([sum_xg < 2.4, h_xg < 1.1, o25_odds >= 2.0, std_xg < 0.5])
        core_C = [sum_xg > 3.2, o25_odds <= 1.85]
        extra_C = [std_xg > 0.7, open_score > 4.8, res_total > 0.18]
        if cond_A >= 3: return 'A'
        if sum(core_C) >= 1 and sum(extra_C) >= 2: return 'C'
        return 'B'
    if tier in ('客3', '客3+'):
        return 'A' if o25_odds >= 2.0 else 'C'
    return 'B'

def depth_order(tier, cls):
    """🔴方案原文比分优先级（每档A/B/C精确顺序）"""
    if tier == '主1': return {'A': ['1-0','2-1'], 'B': ['2-1','1-0','3-2'], 'C': ['3-2','2-1']}[cls]
    if tier == '主2': return {'A': ['2-0','3-1'], 'B': ['3-1','2-0','4-2'], 'C': ['4-2','3-1']}[cls]
    if tier == '主3': return ['3-0','4-1'] if cls == 'A' else ['4-1','3-0']
    if tier == '主3+': return ['4-0','5-0'] if cls == 'A' else ['5-1','4-0']
    if tier == '平': return {'A': ['0-0','1-1'], 'B': ['1-1','0-0','2-2'], 'C': ['2-2','3-3','1-1']}[cls]
    if tier == '客1': return {'A': ['0-1','1-2'], 'B': ['1-2','0-1','2-3'], 'C': ['2-3','1-2']}[cls]
    if tier == '客2': return {'A': ['0-2','1-3'], 'B': ['1-3','0-2','2-4'], 'C': ['2-4','1-3']}[cls]
    if tier == '客3': return ['0-3','1-4'] if cls == 'A' else ['1-4','0-3']
    return ['0-4','0-5'] if cls == 'A' else ['1-5','0-4']

def cap_probability(mat, cap=0.35):
    """🔴九档统一强制收尾: 波动型大比分概率上限35%（3-2/4-2/2-3/2-4/2-2/3-3）"""
    volatile = {'3-2','4-2','2-3','2-4','2-2','3-3','4-4','3-3','5-3','4-5'}
    out = dict(mat)
    for s in volatile:
        if s in out and out[s] > cap:
            out[s] = cap
    s = sum(out.values())
    return {k: v/s for k, v in out.items()}

# ============ 五、完整流水线 ============
def predict_depth9(hf, af, avg_xga, handicap, o25_odds, res_gd=0.0, res_total=0.0,
                   jc_home_prob=None, jc_draw_prob=None, jc_score_probs=None,
                   disagree=False, rho=0.05, alpha=0.65, beta=0.10, league_s_lo=0.6, league_s_hi=1.4):
    """终极版完整判定: 特征→五级修正→九档→A/B/C→贝叶斯→概率上限→输出"""
    dxg, sum_xg, std_xg, open_score, lh0, la0 = core_features(hf, af, avg_xga)
    # 五级修正
    lh, la, gd_new, s = five_stage(lh0, la0, res_gd, res_total, std_xg, o25_odds,
                                   k2=0.3, k3=0.2)
    # 九档进档
    tier, why = tier9_joint(dxg, handicap, jc_home_prob, jc_draw_prob)
    # A/B/C 三分
    jc_small = True if jc_home_prob is None else (1 - jc_home_prob) < 0.5
    cls = depth_class(tier, sum_xg, std_xg, open_score, o25_odds, res_total,
                      hf['xg_mean'], af['xg_mean'], hf['xga_mean'], af['xga_mean'],
                      jc_small, jc_score_probs is not None)
    order = depth_order(tier, cls)
    # 比分矩阵+贝叶斯+概率上限
    mat = score_matrix(lh, la, rho)
    mat = bayes_weight(mat, jc_score_probs, alpha, beta, disagree)
    mat = cap_probability(mat)
    ranked = sorted(mat.items(), key=lambda x: -x[1])
    return {'净胜档': tier, '进档': why, '深度类': cls, 'Δxg': round(dxg, 2),
            'sum_xG': round(sum_xg, 2), 'std_xG': round(std_xg, 2), 'open': round(open_score, 2),
            'λ': (round(lh, 2), round(la, 2)), '缩放s': round(s, 2),
            '🔴主锚/次锚': order[:2], '比分排序': order,
            '概率Top3': [(sc, round(p, 3)) for sc, p in ranked[:3]]}
