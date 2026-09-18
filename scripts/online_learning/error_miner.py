# -*- coding: utf-8 -*-
"""L3 误差规则层 + L4 案例库(CBR)
L3: 场景分组统计误差 → 样本>=30 自动生成修正规则（方向/大小球）→ 预测时应用（提示级）
L4: 案例库检索相似案例（含错误案例）→ CBR 辅助预测（权重低·冷启动0）
"""
import os, sys, math, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import persistence as P


# ---------------- L3 误差模式 ----------------
def scenario_key(f):
    """场景离散化键（联赛/让球层/是否五大/是否欧战/O25档/热门度档）"""
    def bucket(v, cuts):
        for i, c in enumerate(cuts):
            if v < c: return i + 1
        return len(cuts) + 1
    o25 = float(f.get('o25_odds') or 0) or 1.9
    oh = float(f.get('home_odds') or 0) or 2.5
    return '%s|L%s|T%s|E%s|O%s|H%s' % (
        f.get('league', '?'), f.get('handicap_layer', '?'),
        f.get('is_top5', 0), f.get('is_europe', 0),
        bucket(o25, [1.7, 2.0, 2.2]), bucket(oh, [1.5, 2.5]))


def update_pattern(features, pred_dir, actual_dir, pred_total, actual_total):
    patterns = P.load_json('rules/error_patterns.json', {})
    k = scenario_key(features)
    p = patterns.setdefault(k, {'count': 0, 'dir_wrong': 0, 'goal_bias': 0.0,
                                'dir_home_over': 0, 'dir_away_over': 0, 'last': ''})
    p['count'] += 1
    if pred_dir is not None and int(pred_dir) != int(actual_dir):
        p['dir_wrong'] += 1
        if int(pred_dir) == 1: p['dir_home_over'] += 1
        if int(pred_dir) == 2: p['dir_away_over'] += 1
    if pred_total is not None:
        p['goal_bias'] += float(pred_total) - float(actual_total)
    if p['count'] > 100:
        for kk in ('dir_wrong', 'dir_home_over', 'dir_away_over', 'goal_bias'):
            p[kk] *= 0.99
        p['count'] = 100
    p['last'] = time.strftime('%Y-%m-%d')
    patterns[k] = p
    P.save_json('rules/error_patterns.json', patterns)
    return k, p


def generate_rules():
    """样本>=MIN_RULE_N 且错误率超阈值 → 生成修正规则（偏差方向决定动作）"""
    patterns = P.load_json('rules/error_patterns.json', {}) or {}
    rules = []
    for k, p in patterns.items():
        n = p.get('count', 0)
        if n < C.MIN_RULE_N:
            continue
        dir_err = p.get('dir_wrong', 0) / n
        bias = p.get('goal_bias', 0.0) / n
        if dir_err > C.DIR_ERR_THRESHOLD:
            if p.get('dir_home_over', 0) > p.get('dir_away_over', 0):
                rules.append({'scenario': k, 'type': 'direction', 'action': 'reduce_home',
                              'magnitude': round(min(0.15, dir_err * 0.3), 3),
                              'confidence': round(min(0.9, n / 200), 3), 'n': round(n)})
            else:
                rules.append({'scenario': k, 'type': 'direction', 'action': 'reduce_away',
                              'magnitude': round(min(0.15, dir_err * 0.3), 3),
                              'confidence': round(min(0.9, n / 200), 3), 'n': round(n)})
        if bias > 0.5:
            rules.append({'scenario': k, 'type': 'goals', 'action': 'reduce_over',
                          'magnitude': round(min(0.12, abs(bias) * 0.1), 3),
                          'confidence': round(min(0.9, n / 200), 3), 'n': round(n)})
        elif bias < -0.5:
            rules.append({'scenario': k, 'type': 'goals', 'action': 'increase_over',
                          'magnitude': round(min(0.12, abs(bias) * 0.1), 3),
                          'confidence': round(min(0.9, n / 200), 3), 'n': round(n)})
    P.save_json('rules/correction_rules.json', rules)
    return rules


def rules_for(features):
    """预测时匹配规则（仅提示/微调·置信度>0.5 才建议参考）"""
    rules = P.load_json('rules/correction_rules.json', []) or []
    k = scenario_key(features)
    return [r for r in rules if r.get('scenario') == k and r.get('confidence', 0) > 0.5]


# ---------------- L4 案例库 CBR ----------------
WEIGHTS = {'handicap_layer': 2.5, 'league_id': 3.0, 'is_top5': 2.0, 'is_europe': 2.0,
           'home_odds': 1.5, 'o25_odds': 1.5, 'elo_diff': 1.0}


def add_case(case):
    """🔴2026-09-12 修复: 按 case_id+date 去重（原直接 append 致 case158 重复 3 次）"""
    cases = P.load_json('cases/case_library.json', [])
    cid, cd = str(case.get('case_id')), str(case.get('date'))
    cases = [c for c in cases if not (str(c.get('case_id')) == cid and str(c.get('date')) == cd)]
    cases.append(case)
    P.save_json('cases/case_library.json', cases)
    return len(cases)


def _num(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def retrieve(features, top_k=10, errors_only=False):
    cases = P.load_json('cases/case_library.json', []) or []
    scored = []
    for c in cases:
        cf = c.get('features', {})
        if errors_only and c.get('error', {}).get('direction_correct'):
            continue
        d = 0.0
        for f, w in WEIGHTS.items():
            if f in features and f in cf:
                d += w * (_num(features[f]) - _num(cf[f])) ** 2
        d = math.sqrt(d)
        days = 0
        _d = c.get('date')
        if _d:
            try:
                from datetime import datetime
                days = max(0, (datetime.now() - datetime.strptime(str(_d)[:10], '%Y-%m-%d')).days)
            except Exception:
                days = 0
        sim = (1 / (1 + d)) * (C.DECAY ** days)
        scored.append((sim, c))
    scored.sort(key=lambda x: -x[0])
    return scored[:top_k]


def cbr_predict(features, top_k=15):
    """案例辅助预测（案例<CBR_MIN_CASES 不启用）"""
    sims = retrieve(features, top_k=top_k)
    if len(sims) < C.CBR_MIN_CASES:
        return {'enabled': False, 'n_cases': len(sims)}
    votes = {0: 0.0, 1: 0.0, 2: 0.0}
    for s, c in sims:
        votes[int(c.get('actual', {}).get('direction', 1))] += s
    tot = sum(votes.values()) or 1
    probs = {k: round(v / tot, 4) for k, v in votes.items()}
    errs = retrieve(features, top_k=10, errors_only=True)
    warn = None
    if errs:
        # 🔴2026-09-12 修复: None 安全（导入案例 prediction.direction 可能为 None）
        home_over = sum(1 for _, c in errs
                        if int(c.get('prediction', {}).get('direction') or -1) == 1
                        and int(c.get('actual', {}).get('direction') or -1) != 1)
        if home_over >= max(3, len(errs) // 2):
            warn = 'similar_cases_often_overestimate_home'
    return {'enabled': True, 'n_cases': len(sims), 'direction_probs': probs,
            'error_warning': warn, 'error_cases': len(errs),
            'weight': C.CBR_COLD if len(sims) < 30 else C.CBR_NORMAL}


def total_cases():
    return len(P.load_json('cases/case_library.json', []) or [])
