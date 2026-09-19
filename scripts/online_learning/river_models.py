# -*- coding: utf-8 -*-
"""L1 在线 ML 层（River）：方向分类器 / 进球回归器 / 量级分类器 + 概念漂移检测
🔴诚实修正：三模型输出仅作第6/7源·权重封顶(方向0.15/比分0.10)·不覆盖硬核L2判定。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import persistence as P
from river import linear_model, preprocessing, compose, tree, drift, optim


def new_direction_model():
    return compose.Pipeline(preprocessing.StandardScaler(),
                            linear_model.SoftmaxRegression(optimizer=optim.SGD(C.LEARNING_RATE_DIR)))


def new_goals_model():
    return compose.Pipeline(preprocessing.StandardScaler(),
                            linear_model.LinearRegression(optimizer=optim.SGD(C.LEARNING_RATE_GOALS), intercept_lr=C.LEARNING_RATE_GOALS))


def new_magnitude_model():
    return tree.HoeffdingTreeClassifier(grace_period=50, max_depth=6)


def new_drift():
    return {'dir': drift.ADWIN(delta=C.ADWIN_DELTA),
            'goals': drift.ADWIN(delta=0.01),
            'home_win': drift.ADWIN(delta=C.ADWIN_DELTA)}


def load_models():
    return {
        'direction': P.load_pickle('river/direction.pkl', new_direction_model()),
        'goals': P.load_pickle('river/goals.pkl', new_goals_model()),
        'magnitude': P.load_pickle('river/magnitude.pkl', new_magnitude_model()),
        'drift': P.load_pickle('river/drift.pkl', new_drift()),
        'n': P.load_json('river/n.json', {'direction': 0, 'goals': 0, 'magnitude': 0}),
    }


def save_models(m):
    P.save_pickle('river/direction.pkl', m['direction'])
    P.save_pickle('river/goals.pkl', m['goals'])
    P.save_pickle('river/magnitude.pkl', m['magnitude'])
    P.save_pickle('river/drift.pkl', m['drift'])
    P.save_json('river/n.json', m['n'])


def magnitude_bucket(total):
    if total <= 1: return 0
    if total <= 3: return 1
    if total <= 6: return 2
    return 3


def weight_for(n, kind='dir'):
    if kind == 'dir':
        c, g, m = C.W_DIR_COLD, C.W_DIR_GROW, C.W_DIR_MATURE
    else:
        c, g, m = C.W_GOALS_COLD, C.W_GOALS_GROW, C.W_GOALS_MATURE
    if n < C.N_COLD: return c
    if n < C.N_MATURE: return g
    return m


# River Pipeline 需要数值特征；标签用字符串避免 0/1/2 被误判为回归
DIR_LABEL = {0: 'draw', 1: 'home', 2: 'away'}


def _safe_features(f):
    out = {}
    for k in C.FEATURE_KEYS:
        try:
            out[k] = float(f.get(k) or 0)
        except Exception:
            out[k] = 0.0
    return out


def predict_before_learn(m, features):
    """学习前预测（用于误差归因与回归验证）·返回 None 表示未就绪"""
    f = _safe_features(features)
    n = m['n'].get('direction', 0)
    if n < 1:
        return None
    try:
        p = m['direction'].predict_proba_one(f)
    except Exception:
        return None
    if not p:
        return None
    # 映射回 0/1/2
    inv = {v: k for k, v in DIR_LABEL.items()}
    probs = {inv.get(k, 1): v for k, v in p.items()}
    for i in (0, 1, 2):
        probs.setdefault(i, 0.0)
    tot = sum(probs.values()) or 1
    return {k: v / tot for k, v in probs.items()}


def learn_one(m, features, actual_direction, actual_total_goals):
    """赛后更新三模型 + 漂移检测"""
    f = _safe_features(features)
    pred = predict_before_learn(m, features)
    try:
        m['direction'].learn_one(f, DIR_LABEL[int(actual_direction)])
        m['goals'].learn_one(f, float(actual_total_goals))
        m['magnitude'].learn_one(f, magnitude_bucket(int(actual_total_goals)))
    except Exception as e:
        return {'ok': False, 'error': str(e)[:120]}
    m['n']['direction'] = m['n'].get('direction', 0) + 1
    m['n']['goals'] = m['n'].get('goals', 0) + 1
    m['n']['magnitude'] = m['n'].get('magnitude', 0) + 1
    # 漂移检测
    drift_hit = []
    try:
        if pred is not None:
            top = max(pred, key=pred.get)
            m['drift']['dir'].update(1 if top == int(actual_direction) else 0)
            if m['drift']['dir'].drift_detected: drift_hit.append('direction')
        m['drift']['goals'].update(float(actual_total_goals))
        if m['drift']['goals'].drift_detected: drift_hit.append('goals')
        m['drift']['home_win'].update(1 if int(actual_direction) == 1 else 0)
        if m['drift']['home_win'].drift_detected: drift_hit.append('home_win')
    except Exception:
        pass
    return {'ok': True, 'pred_before': pred, 'n': m['n']['direction'], 'drift': drift_hit}


def predict(m, features):
    """预测（供 calc_all 消费·第6/7源·🔴仅观察不参与判定）"""
    f = _safe_features(features)
    out = {'n': m['n'].get('direction', 0)}
    out['direction_probs'] = predict_before_learn(m, features)
    try:
        g = float(m['goals'].predict_one(f) or 0)
        # 修复: 线性回归未收敛会外推爆炸(实测 5e13) → 超合理范围标 None
        out['goals'] = round(g, 2) if 0 <= g <= 8 else None
        out['goals_note'] = '' if out['goals'] is not None else '未收敛(输出%.2g·已丢弃)' % g
    except Exception:
        out['goals'] = None
        out['goals_note'] = '异常'
    try:
        out['magnitude'] = m['magnitude'].predict_one(f)
    except Exception:
        out['magnitude'] = None
    out['weight'] = weight_for(out['n'], 'dir')
    return out


def status(m=None):
    m = m or load_models()
    return {'n_direction': m['n'].get('direction', 0),
            'n_goals': m['n'].get('goals', 0),
            'n_magnitude': m['n'].get('magnitude', 0),
            'weight_dir': weight_for(m['n'].get('direction', 0), 'dir'),
            'weight_goals': weight_for(m['n'].get('goals', 0), 'goals'),
            'drift': {k: getattr(v, 'drift_detected', False) for k, v in (m.get('drift') or {}).items()}}
