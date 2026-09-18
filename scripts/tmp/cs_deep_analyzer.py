# -*- coding: utf-8 -*-
"""cs_deep_analyzer.py — CS比分盘深度分析模块（V3.5.74）
超越简单去抽水：
1. 抽水率偏差分析：低抽水比分=庄家更有信心=升权
2. CS与泊松分歧检测：分歧大时CS降权
3. CS盘Top1/Top2/Top3覆盖率计算
"""
import sys, math, re, json
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')

def parse_cs_odds(cs_str):
    """解析CS比分盘赔率字符串
    cs_str: "1:0=7.5,2:1=8.0,1:1=6.5,0:0=10.0,胜其他=15.0,..."
    返回: dict {(h,a): odds} 和 dict {other_type: odds}
    """
    if not cs_str: return {}, {}
    exact = {}
    other = {}
    for m in re.finditer(r'(\d+:\d+)=([\d.]+)', cs_str):
        h, a = map(int, m.group(1).split(':'))
        if h < 7 and a < 7:
            exact[(h,a)] = float(m.group(2))
    for m in re.finditer(r'(胜其他|平其他|负其他|胜其它|平其它|负其它)=([\d.]+)', cs_str):
        other[m.group(1)] = float(m.group(2))
    return exact, other

def dejuice(exact_odds, other_odds=None):
    """去抽水，返回各比分概率"""
    if not exact_odds: return {}
    inv = {k: 1/v for k, v in exact_odds.items() if v > 1}
    if other_odds:
        for k, v in other_odds.items():
            if v > 1: inv[k] = 1/v
    total = sum(inv.values())
    vig = total - 1
    probs = {k: v/total for k, v in inv.items()}
    return probs, vig

def cs_vig_analysis(cs_str):
    """🔴抽水率偏差分析：低抽水比分升权，高抽水降权
    原理：庄家对某个比分抽水特别低=需要控制风险=认为该比分概率高"""
    exact, other = parse_cs_odds(cs_str)
    if len(exact) < 5: return None, 0
    probs, vig = dejuice(exact, other)
    # 计算每个比分的抽水率
    inv = {k: 1/exact.get(k, 99) for k in exact}
    total_inv = sum(inv.values())
    per_score_vig = {}
    for k in exact:
        # 该比分的隐含概率（去抽水前）
        raw_prob = inv[k]
        # 该比分承担的抽水率
        score_vig = raw_prob * vig / total_inv if total_inv > 0 else 0
        per_score_vig[k] = score_vig
    avg_vig = sum(per_score_vig.values()) / len(per_score_vig) if per_score_vig else 0
    # 调整：低抽水升权，高抽水降权
    adjusted = {}
    for k, p in probs.items():
        if k in per_score_vig:
            vig_dev = per_score_vig[k] - avg_vig
            # 抽水率低于平均→升权，高于平均→降权
            weight = 1.0 - vig_dev * 5.0
            adjusted[k] = p * max(0.5, min(2.5, weight))
        else:
            adjusted[k] = p
    # 归一化
    tot = sum(adjusted.values())
    result = {k: v/tot for k, v in adjusted.items()}
    return result, vig

def cs_poisson_divergence(cs_probs, poisson_probs):
    """计算CS盘与泊松的KL散度，判断是否分歧"""
    if not cs_probs or not poisson_probs: return 0, False
    kl = 0
    keys = set(cs_probs) | set(poisson_probs)
    for k in keys:
        pk = cs_probs.get(k, 1e-6)
        qk = poisson_probs.get(k, 1e-6)
        if pk > 0 and qk > 0:
            kl += pk * math.log(pk / qk)
    is_divergent = kl > 0.3
    return kl, is_divergent

def cs_topn_coverage(cs_probs, n=3):
    """计算CS盘TopN覆盖率"""
    if not cs_probs: return 0, []
    topn = sorted(cs_probs.items(), key=lambda x: -x[1])[:n]
    coverage = sum(p for _, p in topn)
    return coverage, [(f"{h}:{a}", round(p*100,1)) for (h,a), p in topn]

def analyze_cs_deep(cs_str, poisson_probs=None):
    """CS比分盘深度分析主入口"""
    result = {'status': 'ok', 'warnings': []}
    # 解析
    exact, other = parse_cs_odds(cs_str)
    if len(exact) < 5:
        return {'status': 'error', 'message': 'CS比分盘数据不足(<5个比分)'}
    result['n_scores'] = len(exact)
    result['n_other'] = len(other)
    # 简单去抽水
    simple_probs, vig = dejuice(exact, other)
    result['simple_vig'] = f'{vig*100:.1f}%'
    # 抽水率偏差调整
    deep_probs, _ = cs_vig_analysis(cs_str)
    if deep_probs is None:
        deep_probs = simple_probs
        result['warnings'].append('抽水率偏差分析失败，使用简单去抽水')
    # Top3覆盖率
    cov3, top3 = cs_topn_coverage(deep_probs, 3)
    result['top3_coverage'] = f'{cov3*100:.1f}%'
    result['top3'] = top3
    result['top1'] = top3[0] if top3 else None
    result['top2'] = [s for s, _ in top3[:2]]
    # 与泊松分歧检测
    if poisson_probs:
        kl, divergent = cs_poisson_divergence(deep_probs, poisson_probs)
        result['kl_divergence'] = round(kl, 3)
        result['is_divergent'] = divergent
        if divergent:
            result['warnings'].append(f'CS与泊松显著分歧(KL={kl:.3f})，CS权重应降30%')
            result['cs_weight_factor'] = 0.7
        else:
            result['cs_weight_factor'] = 1.0
    else:
        result['cs_weight_factor'] = 1.0
    # 输出完整概率分布（Top10）
    top10 = sorted(deep_probs.items(), key=lambda x: -x[1])[:10]
    result['top10'] = [{'score': f'{h}:{a}', 'prob': round(p*100,1)} for (h,a), p in top10]
    return result

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='CS比分盘深度分析')
    ap.add_argument('--cs', type=str, required=True, help='比分盘赔率 如 "1:0=7.5,2:1=8.0,1:1=6.5"')
    a = ap.parse_args()
    r = analyze_cs_deep(a.cs)
    print(json.dumps(r, ensure_ascii=False, indent=2))
