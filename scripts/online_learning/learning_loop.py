# -*- coding: utf-8 -*-
"""学习闭环主流程（赛后比分 → 归因 → 5层更新 → 回归验证 → 报告）
🔴诚实修正：
  - 第4步回归验证用**历史日志重放**（真实可测）；命中率下降超阈值 → 自动回滚
  - 单场学习仅微调在线参数；**静态大样本表永不被单场改写**（增量表独立·合并走批量流程）
"""

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass

import os, sys, io, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import persistence as P
import river_models as RM
import bayes_updater as BU
import error_miner as EM


def _direction(h, a):
    return 1 if h > a else (2 if a > h else 0)


def _replay_accuracy(models, log_rows, n=20):
    """用日志中保存的 features 重放·计算在线方向命中率（不学习）"""
    sub = [r for r in log_rows if r.get('features')][-n:]
    if len(sub) < 5:
        return None
    hit = 0
    for r in sub:
        p = RM.predict_before_learn(models, r['features'])
        if not p:
            continue
        if max(p, key=p.get) == int(r.get('actual_direction', -1)):
            hit += 1
    return round(hit / len(sub), 4)


def learn_from_result(case_id, real_score, features, predicted=None, do_backup=True):
    """核心：一场赛果 → 全自动学习。features 需含赔率/让球/联赛等（见 config.FEATURE_KEYS）
    predicted: 模型预测（{'direction':1,'total':3,'top2':['3:0','2:0']}）·可空"""
    h, a = [int(x) for x in str(real_score).replace('：', ':').split(':')]
    actual_dir = _direction(h, a)
    actual_total = h + a
    predicted = predicted or {}

    log_before = P.read_log()
    models = RM.load_models()
    metrics_before = _replay_accuracy(models, log_before, C.VALIDATION_N)

    # 备份（回滚点）
    btag = None
    if do_backup:
        btag = P.backup_state('%s_case%s' % (time.strftime('%Y%m%d_%H%M%S'), case_id))

    # ---- 第3步：5层更新 ----
    l1 = RM.learn_one(models, features, actual_dir, actual_total)
    pred_before = (l1 or {}).get('pred_before')
    # L2 增量（格子键：让球层 + O25档 + 联赛；观测=比分/总进球）
    layer = features.get('handicap_layer', '?')
    o25b = 'O%s' % (int(float(features.get('o25_odds') or 1.9) * 10) // 2)
    l2_score = BU.update('score_depth', '%s|%s|%s' % (features.get('league', '?'), layer, o25b), real_score)
    l2_handi = BU.update('handicap', '%s|%s' % (features.get('league', '?'), layer), real_score)
    l2_goals = BU.update('goal_bins', '%s|%s|%s' % (features.get('league', '?'), layer, o25b), actual_total)
    l2_league = BU.update_league_calibration(features.get('league', '?'), actual_total, actual_dir)
    # L3 误差模式
    skey, pat = EM.update_pattern(features,
                                  predicted.get('direction'), actual_dir,
                                  predicted.get('total'), actual_total)
    rules = EM.generate_rules()
    # L4 案例库
    top2 = predicted.get('top2') or []
    case = {'case_id': str(case_id), 'date': time.strftime('%Y-%m-%d'),
            'league': features.get('league', '?'),
            'features': {k: features.get(k) for k in C.FEATURE_KEYS},
            'prediction': {'direction': predicted.get('direction'),
                           'top2': top2, 'total': predicted.get('total')},
            'actual': {'score': real_score, 'direction': actual_dir, 'total_goals': actual_total},
            'error': {'direction_correct': (predicted.get('direction') == actual_dir) if predicted.get('direction') is not None else None,
                      'score_top2_hit': (real_score in top2) if top2 else None,
                      'goal_error': (actual_total - float(predicted.get('total'))) if predicted.get('total') is not None else None}}
    n_cases = EM.add_case(case)

    # ---- 第4步：回归验证 + 回滚判定 ----
    RM.save_models(models)
    log_after = P.read_log()
    metrics_after = _replay_accuracy(models, log_after, C.VALIDATION_N)
    rolled = False
    if metrics_before is not None and metrics_after is not None:
        if metrics_after < metrics_before - C.ROLLBACK_DIR_DROP and len(log_after) >= C.VALIDATION_N:
            rolled = P.restore_state(os.path.basename(btag)) if btag else False

    # ---- 第5步：报告 + 日志 ----
    report = {
        'case': case_id, 'real': real_score, 'actual_direction': actual_dir, 'actual_total': actual_total,
        'online_pred_before': pred_before, 'online_n': (l1 or {}).get('n'),
        'drift': (l1 or {}).get('drift', []),
        'l2': {'score_cell': l2_score['cell'], 'merge_ready': l2_score['merge_ready'],
               'league': l2_league},
        'l3': {'scenario': skey, 'rules_total': len(rules)},
        'l4': {'cases_total': n_cases},
        'metrics_before': metrics_before, 'metrics_after': metrics_after, 'rolled_back': rolled,
        'layers_updated': ['L1_river', 'L2_bayes_incremental', 'L3_error_patterns', 'L4_case_library', 'L5_persisted'],
    }
    P.append_log({'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'), 'case': case_id,
                  'real': real_score, 'actual_direction': actual_dir, 'actual_total': actual_total,
                  'features': features, 'prediction': predicted,
                  'metrics_before': metrics_before, 'metrics_after': metrics_after,
                  'rolled_back': rolled})
    return report


def print_report(r):
    print('=' * 68)
    print('🧠 赛后自学习报告 — case%s (%s)' % (r['case'], r['real']))
    print('-' * 68)
    pb = r.get('online_pred_before')
    if pb:
        inv = {0: '平', 1: '主胜', 2: '客胜'}
        print('  在线模型赛前预测 : %s' % ' '.join('%s %.0f%%' % (inv[k], v * 100) for k, v in sorted(pb.items())))
    print('  实际             : %s (方向=%s 总进球=%d)' % (
        r['real'], {0: '平', 1: '主胜', 2: '客胜'}[r['actual_direction']], r['actual_total']))
    print('  已更新层         : %s' % ' / '.join(r['layers_updated']))
    print('  L1 在线样本量    : %s (漂移=%s)' % (r['online_n'], r.get('drift') or '无'))
    print('  L2 增量格子      : %s (可合并=%s) | 联赛校准 n=%s avg=%.2f 主胜率=%.0f%%' % (
        r['l2']['score_cell'], r['l2']['merge_ready'], r['l2']['league']['n'],
        r['l2']['league']['avg_goals'], r['l2']['league']['home_rate'] * 100))
    print('  L3 场景          : %s (规则总数=%d)' % (r['l3']['scenario'], r['l3']['rules_total']))
    print('  L4 案例库        : %d 场' % r['l4']['cases_total'])
    print('  回归验证         : 更新前=%s → 更新后=%s%s' % (
        r['metrics_before'], r['metrics_after'], '  ⚠️已回滚' if r['rolled_back'] else ''))
    print('-' * 68)
    print('  ⚠️ 诚实说明: 单场仅微调在线参数；静态大样本表未被改动（增量表独立·合并走批量流程）')
    print('=' * 68)


def gitignore_state():
    p = os.path.join(C.STATE, '.gitignore')
    os.makedirs(C.STATE, exist_ok=True)
    if not os.path.exists(p):
        open(p, 'w').write('*\n!.gitignore\n')
