# -*- coding: utf-8 -*-
"""L2 贝叶斯层：增量表更新（比分/让球层/联赛校准）
🔴诚实修正：**静态大样本表不被单场污染**——增量独立累积·n>=MERGE_N(50) 才标记可合并·
  n<SHRINK_N 时向静态/全局先验收缩（贝叶斯收缩）·预测时静态表仍旧主导·
  **合并动作由批量更新流程执行（非单场）**。
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import persistence as P


def _inc_path(kind):
    return f'tables/{kind}_incremental.json'


def _load_inc(kind):
    return P.load_json(_inc_path(kind), {'cells': {}, 'n': 0, 'updated': ''})


def _save_inc(kind, obj):
    P.save_json(_inc_path(kind), obj)


def update(kind, cell_key, observed, n_inc=1):
    """赛后更新增量表：cell_key 定位格子，observed=本次观测（比分/进球数等）
    返回该格子的收缩后概率分布（供报告显示）"""
    obj = _load_inc(kind)
    cells = obj.setdefault('cells', {})
    key = str(cell_key)
    c = cells.setdefault(key, {'counts': {}, 'total': 0})
    s = str(observed)
    c['counts'][s] = c['counts'].get(s, 0) + n_inc
    c['total'] += n_inc
    obj['n'] = obj.get('n', 0) + n_inc
    import time
    obj['updated'] = time.strftime('%Y-%m-%d %H:%M')
    # 贝叶斯收缩：小样本格向该 kind 全局增量分布收缩（防小样本过拟合）
    if c['total'] < C.SHRINK_N:
        global_counts = {}
        for cc in cells.values():
            for k2, v2 in cc['counts'].items():
                global_counts[k2] = global_counts.get(k2, 0) + v2
        gt = sum(global_counts.values()) or 1
        shrink = 1 - c['total'] / C.SHRINK_N
        adj = {}
        allk = set(c['counts']) | set(global_counts)
        for k2 in allk:
            own = c['counts'].get(k2, 0) / c['total']
            glob = global_counts.get(k2, 0) / gt
            adj[k2] = round(own * (1 - shrink) + glob * shrink, 4)
        c['shrunk_probs'] = adj
    else:
        tot = sum(c['counts'].values()) or 1
        c['shrunk_probs'] = {k2: round(v2 / tot, 4) for k2, v2 in c['counts'].items()}
    c['merge_ready'] = c['total'] >= C.MERGE_N
    _save_inc(kind, obj)
    return {'kind': kind, 'cell': key, 'total': c['total'], 'merge_ready': c['merge_ready'],
            'top': sorted(c['shrunk_probs'].items(), key=lambda x: -x[1])[:5]}


def update_league_calibration(league, total_goals, direction):
    """联赛校准：滑动窗口 + 指数衰减（只保留窗口内等效样本量）"""
    calib = P.load_json('tables/league_calibration.json', {})
    c = calib.setdefault(league, {'n': 0, 'goals_sum': 0.0, 'home': 0.0, 'draw': 0.0, 'away': 0.0,
                                  'o25': 0.0, 'avg_goals': 0.0, 'home_rate': 0.0, 'draw_rate': 0.0,
                                  'away_rate': 0.0, 'o25_rate': 0.0})
    # 衰减
    if c['n'] > C.WINDOW:
        for k in ('goals_sum', 'home', 'draw', 'away', 'o25'):
            c[k] *= C.DECAY
        c['n'] = c['n'] * C.DECAY
    c['n'] += 1
    c['goals_sum'] += total_goals
    c['home'] += 1 if direction == 1 else 0
    c['draw'] += 1 if direction == 0 else 0
    c['away'] += 1 if direction == 2 else 0
    c['o25'] += 1 if total_goals >= 3 else 0
    n = c['n'] or 1
    c['avg_goals'] = round(c['goals_sum'] / n, 3)
    c['home_rate'] = round(c['home'] / n, 4)
    c['draw_rate'] = round(c['draw'] / n, 4)
    c['away_rate'] = round(c['away'] / n, 4)
    c['o25_rate'] = round(c['o25'] / n, 4)
    P.save_json('tables/league_calibration.json', calib)
    return {'league': league, 'n': round(c['n'], 1), 'avg_goals': c['avg_goals'],
            'home_rate': c['home_rate'], 'o25_rate': c['o25_rate']}


def propose_merge():
    """列出达可合并条件的增量格子（**合并须走批量更新流程**·非单场）"""
    out = []
    for kind in ('handicap', 'score_depth', 'goal_bins'):
        obj = _load_inc(kind)
        ready = [k for k, v in (obj.get('cells') or {}).items() if v.get('total', 0) >= C.MERGE_N]
        if obj.get('n'):
            out.append({'kind': kind, 'n_total': obj['n'], 'cells_ready': ready})
    return out


def status():
    out = {}
    for kind in ('handicap', 'score_depth', 'goal_bins'):
        obj = _load_inc(kind)
        out[kind] = {'n': obj.get('n', 0), 'cells': len(obj.get('cells') or {}),
                     'updated': obj.get('updated', '')}
    out['league_calibration'] = P.load_json('tables/league_calibration.json', {})
    return out
