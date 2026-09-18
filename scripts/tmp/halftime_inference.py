# -*- coding: utf-8 -*-
"""halftime_inference.py — 半场比分反推模块（Top2=40%核心）
🔴角色标注(2026-09-07审计V2.0): 半场反推已并入 live_score_engine.halftime_precise_matrix(同读 ht_ft_cond.json·同算法·现场引擎主链)·本文件保留为独立CLI工具(单场半场反推/回测校验·python halftime_inference.py --bqc "...")·主流程不依赖本文件
原理：
  1. 用半全场赔率(9格)反推半场方向概率(主胜/平/客胜)
  2. 用历史数据计算半场方向→具体半场比分的分布
  3. 得到半场比分的完整概率分布 P(HT=h:a)
  4. 用175476场数据计算的条件概率矩阵 P(FT|HT)
  5. 加权求和得到全场比分概率 P(FT) = Σ P(HT) * P(FT|HT)
  6. 与泊松/CS融合，输出最终Top2

这是最大的单一增益源：已知半场时Top2=41.8%，反推半场方向后预期Top2≈37-39%
"""
import sys, csv, math, json
from collections import defaultdict, Counter
sys.stdout.reconfigure(encoding='utf-8')

DATA = 'data/Matches.csv'

# ═══════════════════════════════════════════════════════════════
# 1. 从历史数据构建条件概率矩阵 P(FT | HT)
# ═══════════════════════════════════════════════════════════════
def _load_cache():
    """读条件矩阵缓存(2026-09-07构建·ht_ft_cond.json·防每场22万重算)"""
    import os, json
    fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ht_ft_cond.json')
    if os.path.exists(fp):
        try:
            d = json.load(open(fp, encoding='utf-8'))
            cond = {}
            for k, v in d.get('cond', {}).items():
                hh, aa = map(int, k.split(':'))
                cond[(hh, aa)] = {tuple(map(int, kk.split(':'))): pp for kk, pp in v.items()}
            dd = {}
            for dr, v in d.get('dir_dist', {}).items():
                dd[dr] = {tuple(map(int, kk.split(':'))): pp for kk, pp in v.items()}
            return cond, dd
        except Exception:
            return None, None
    return None, None

def build_ht_ft_matrix():
    """构建半场→全场条件概率矩阵（优先读缓存·175476场真实数据）"""
    _c, _d = _load_cache()
    if _c:
        return _c, None
    ht_to_ft = defaultdict(Counter)
    ht_count = Counter()
    with open(DATA, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                hth = int(float(row['HTHome'])); hta = int(float(row['HTAway']))
                fth = int(float(row['FTHome'])); fta = int(float(row['FTAway']))
                if hth > 4 or hta > 4: continue
                if fth > 6 or fta > 6: continue
                ht_to_ft[(hth,hta)][(fth,fta)] += 1
                ht_count[(hth,hta)] += 1
            except:
                continue
    # 转换为条件概率
    cond_prob = {}
    for ht, ft_counter in ht_to_ft.items():
        n = ht_count[ht]
        if n < 50: continue  # 样本太少的半场比分用方向级替代
        cond_prob[ht] = {ft: c/n for ft, c in ft_counter.items()}
    return cond_prob, ht_count

# ═══════════════════════════════════════════════════════════════
# 2. 半场方向→具体半场比分的分布
# ═══════════════════════════════════════════════════════════════
def build_ht_dir_dist():
    """半场方向(主胜/平/客胜)→具体半场比分的概率分布(优先读缓存)"""
    _c, _d = _load_cache()
    if _d:
        return _d
    dir_dist = {'H': Counter(), 'D': Counter(), 'A': Counter()}
    with open(DATA, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                hth = int(float(row['HTHome'])); hta = int(float(row['HTAway']))
                if hth > 4 or hta > 4: continue
                if hth > hta: d = 'H'
                elif hth == hta: d = 'D'
                else: d = 'A'
                dir_dist[d][(hth,hta)] += 1
            except:
                continue
    # 归一化
    result = {}
    for d, cnt in dir_dist.items():
        n = sum(cnt.values())
        result[d] = {ht: c/n for ht, c in cnt.items()}
    return result

# ═══════════════════════════════════════════════════════════════
# 3. 半全场赔率反推半场方向概率
# ═══════════════════════════════════════════════════════════════
def infer_ht_direction_from_bqc(bqc_odds):
    """从半全场赔率反推半场方向概率
    bqc_odds: dict like {'胜胜':3.0, '胜平':5.0, '胜负':8.0, '平胜':4.0, '平平':3.5, '平负':6.0, '负胜':10, '负平':7, '负负':4.5}
    半场主胜概率 = P(胜胜)+P(胜平)+P(胜负)
    半场平概率 = P(平胜)+P(平平)+P(平负)
    半场客胜概率 = P(负胜)+P(负平)+P(负负)
    """
    if not bqc_odds or len(bqc_odds) < 6:
        return None
    # 去抽水
    inv = {k: 1/v for k, v in bqc_odds.items() if v > 1}
    total = sum(inv.values())
    probs = {k: v/total for k, v in inv.items()}
    # 半场方向
    ht_home = probs.get('胜胜',0) + probs.get('胜平',0) + probs.get('胜负',0)
    ht_draw = probs.get('平胜',0) + probs.get('平平',0) + probs.get('平负',0)
    ht_away = probs.get('负胜',0) + probs.get('负平',0) + probs.get('负负',0)
    # 归一化
    s = ht_home + ht_draw + ht_away
    if s <= 0: return None
    return {'H': ht_home/s, 'D': ht_draw/s, 'A': ht_away/s}

# ═══════════════════════════════════════════════════════════════
# 4. 半场比分概率分布（方向→具体比分）
# ═══════════════════════════════════════════════════════════════
def ht_score_distribution(ht_dir_prob, ht_dir_dist):
    """由半场方向概率 + 方向内比分分布 → 半场比分完整概率分布"""
    if ht_dir_prob is None: return None
    dist = {}
    for d, p_dir in ht_dir_prob.items():
        for ht, p_ht_given_dir in ht_dir_dist.get(d, {}).items():
            dist[ht] = dist.get(ht, 0) + p_dir * p_ht_given_dir
    return dist

# ═══════════════════════════════════════════════════════════════
# 5. 全场比分概率 = Σ P(HT) * P(FT|HT)
# ═══════════════════════════════════════════════════════════════
def ft_prob_from_ht(ht_dist, cond_prob):
    """由半场比分分布 + 条件概率矩阵 → 全场比分概率分布"""
    if not ht_dist: return None
    ft_prob = defaultdict(float)
    for ht, p_ht in ht_dist.items():
        if ht in cond_prob:
            for ft, p_ft_given_ht in cond_prob[ht].items():
                ft_prob[ft] += p_ht * p_ft_given_ht
        else:
            # 样本不足的半场比分，用方向级条件概率替代
            d = 'H' if ht[0]>ht[1] else 'D' if ht[0]==ht[1] else 'A'
            # 找同方向的其他半场比分的平均
            for ht2, cp in cond_prob.items():
                d2 = 'H' if ht2[0]>ht2[1] else 'D' if ht2[0]==ht2[1] else 'A'
                if d2 == d:
                    for ft, p in cp.items():
                        ft_prob[ft] += p_ht * p * 0.3  # 稀释
    # 归一化
    tot = sum(ft_prob.values())
    if tot <= 0: return None
    return {k: v/tot for k, v in ft_prob.items()}

# ═══════════════════════════════════════════════════════════════
# 6. 主入口：半场反推比分分析
# ═══════════════════════════════════════════════════════════════
def analyze_with_halftime(bqc_odds, cond_prob, ht_dir_dist):
    """半场反推完整流程"""
    # 步骤1：反推半场方向
    ht_dir = infer_ht_direction_from_bqc(bqc_odds)
    if ht_dir is None:
        return {'status': 'error', 'message': '半全场赔率不足'}
    # 步骤2：半场比分分布
    ht_dist = ht_score_distribution(ht_dir, ht_dir_dist)
    # 步骤3：全场比分概率
    ft_prob = ft_prob_from_ht(ht_dist, cond_prob)
    if ft_prob is None:
        return {'status': 'error', 'message': '条件概率计算失败'}
    # Top10
    top10 = sorted(ft_prob.items(), key=lambda x: -x[1])[:10]
    # 聚合
    home_p = sum(p for (h,a),p in ft_prob.items() if h>a)
    draw_p = sum(p for (h,a),p in ft_prob.items() if h==a)
    away_p = sum(p for (h,a),p in ft_prob.items() if h<a)
    return {
        'status': 'ok',
        'ht_direction': {k: f'{v*100:.1f}%' for k,v in ht_dir.items()},
        'ht_top5': [f'{h}:{a}({p*100:.1f}%)' for (h,a),p in sorted(ht_dist.items(), key=lambda x:-x[1])[:5]],
        'ft_top10': [{'score': f'{h}:{a}', 'prob': round(p*100,1)} for (h,a),p in top10],
        'ft_top2': [f'{h}:{a}' for (h,a),_ in top10[:2]],
        'aggregated': {'home': f'{home_p*100:.1f}%', 'draw': f'{draw_p*100:.1f}%', 'away': f'{away_p*100:.1f}%'},
        'top1_prob': f'{top10[0][1]*100:.1f}%',
        'top2_coverage': f'{sum(p for _,p in top10[:2])*100:.1f}%',
    }

# ═══════════════════════════════════════════════════════════════
# 7. 回测验证：半场反推 vs 纯泊松
# ═══════════════════════════════════════════════════════════════
def backtest():
    """用Matches.csv回测：模拟半全场赔率反推半场方向，验证Top2增益
    由于Matches.csv无半全场赔率，用真实半场比分的方向作为"完美反推"上限
    再用75%准确率模拟实际反推效果"""
    print("构建条件概率矩阵...")
    cond_prob, ht_count = build_ht_ft_matrix()
    ht_dir_dist = build_ht_dir_dist()
    print(f"条件矩阵覆盖 {len(cond_prob)} 种半场比分")

    # 完美半场信息的Top2（上限）
    print("\n回测：完美半场信息 vs 75%准确反推 vs 纯泊松")
    perfect_hit = 0; infer75_hit = 0; poisson_hit = 0
    total = 0
    with open(DATA, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                date = row['MatchDate']
                if not date.startswith('2024') and not date.startswith('2025'): continue
                oh = float(row['OddHome']); od = float(row['OddDraw']); oa = float(row['OddAway'])
                o25 = float(row['Over25'])
                hth = int(float(row['HTHome'])); hta = int(float(row['HTAway']))
                fth = int(float(row['FTHome'])); fta = int(float(row['FTAway']))
                if min(oh,od,oa,o25) <= 1.01: continue
                if fth > 6 or fta > 6 or hth > 4 or hta > 4: continue
                actual = (fth, fta)
                total += 1
                # 完美半场：直接用真实半场比分查条件概率Top2
                if (hth,hta) in cond_prob:
                    cp = cond_prob[(hth,hta)]
                    top2 = sorted(cp, key=cp.get, reverse=True)[:2]
                    if actual in top2: perfect_hit += 1
                # 75%准确反推：75%用真实半场方向，25%用随机方向
                import random
                if random.random() < 0.75:
                    true_dir = 'H' if hth>hta else 'D' if hth==hta else 'A'
                else:
                    true_dir = random.choice(['H','D','A'])
                # 用方向级半场分布
                ht_dist = {}
                for ht, p in ht_dir_dist[true_dir].items():
                    ht_dist[ht] = p
                ft_p = ft_prob_from_ht(ht_dist, cond_prob)
                if ft_p:
                    top2 = sorted(ft_p, key=ft_p.get, reverse=True)[:2]
                    if actual in top2: infer75_hit += 1
                # 纯泊松
                from calc_poisson import solve_lambda, score_dist
                r = solve_lambda(oh, od, oa, o25)
                if r[0]:
                    dist = score_dist(r[0], r[1])
                    top2 = [s for s,_ in dist[:2]]
                    if actual in top2: poisson_hit += 1
            except:
                continue

    print(f"\n回测完成: {total}场(2024-2025)")
    print(f"  纯泊松Top2:      {poisson_hit/total*100:.1f}%")
    print(f"  75%准确半场反推: {infer75_hit/total*100:.1f}% (增益+{(infer75_hit-poisson_hit)/total*100:.1f}pp)")
    print(f"  完美半场信息:    {perfect_hit/total*100:.1f}% (增益+{(perfect_hit-poisson_hit)/total*100:.1f}pp)")
    print(f"\n  半全场赔率反推半场方向的实际准确率通常在70-85%")
    print(f"  因此半场反推模块的预期增益: +{(infer75_hit-poisson_hit)/total*100:.1f}pp")

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--backtest', action='store_true')
    ap.add_argument('--bqc', type=str, help='半全场赔率 如 "胜胜=3.0,平平=3.5,负负=4.5"')
    a = ap.parse_args()
    if a.backtest:
        backtest()
    elif a.bqc:
        import re
        bqc = {}
        for m in re.finditer(r'(胜胜|胜平|胜负|平胜|平平|平负|负胜|负平|负负)=([\d.]+)', a.bqc):
            bqc[m.group(1)] = float(m.group(2))
        cond_prob, _ = build_ht_ft_matrix()
        ht_dir_dist = build_ht_dir_dist()
        r = analyze_with_halftime(bqc, cond_prob, ht_dir_dist)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print("用法: python halftime_inference.py --backtest")
        print("      python halftime_inference.py --bqc '胜胜=3.0,平平=3.5,负负=4.5'")
