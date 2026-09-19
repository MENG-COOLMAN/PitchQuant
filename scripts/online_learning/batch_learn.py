# -*- coding: utf-8 -*-
"""batch_learn.py —— 批量学习（2026-09-12·用户指令"请你进行学习"）
用案例库中【有特征 + 有真实比分 + 未学过】的案例 → learning_loop 逐场学习
  → L1 River 参数更新 + L2 增量表 + L3 误差模式 + L4 案例库 + 融合监测
防重复: 查 learning_log 已有 case 列表
用法:
  python scripts/online_learning/batch_learn.py            # 执行批量学习
  python scripts/online_learning/batch_learn.py --dry-run  # 仅预览哪些场会被学
"""
import os, sys, io, json, argparse, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import config as C
import persistence as P
import river_models as RM
import learning_loop as LL


def _nums(f):
    return len([v for v in (f or {}).values() if v is not None])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', dest='dry')
    ap.add_argument('--min-features', type=int, default=12, help='最低非空特征数')
    a = ap.parse_args()

    cases = P.load_json('cases/case_library.json', []) or []
    learned = set()
    for r in P.read_log():
        if r.get('case'):
            learned.add(str(r['case']))

    todo = []
    for c in cases:
        cid = str(c.get('case_id'))
        act = (c.get('actual') or {})
        if not act.get('score'):
            continue
        if _nums(c.get('features')) < a.min_features:
            continue
        key = cid.replace('case', '').lstrip('0') or cid
        if cid in learned or key in learned:
            continue
        todo.append(c)

    st0 = RM.status()
    print('=== 批量学习 ===')
    print('案例库 %d | 已学 %d | 待学 %d（有特征≥%d 且未学过）' % (
        len(cases), len(learned), len(todo), a.min_features))
    print('学习前: L1 方向样本 %d | 权重 %.2f' % (st0['n_direction'], st0['weight_dir']))
    if a.dry:
        for c in todo[:20]:
            print('  待学: %s %s（%d 特征）' % (c.get('case_id'), (c.get('actual') or {}).get('score'), _nums(c.get('features'))))
        print('  ... 共 %d 场' % len(todo))
        return

    ok = fail = 0
    reports = []
    for c in todo:
        try:
            pred = c.get('prediction') or {}
            rep = LL.learn_from_result(str(c.get('case_id')), c['actual']['score'],
                                       c.get('features') or {}, pred, do_backup=False)
            reports.append(rep)
            ok += 1
        except Exception as e:
            fail += 1
            print('  ⚠️ %s 学习失败: %s' % (c.get('case_id'), str(e)[:60]))
    st1 = RM.status()
    print('\n学习完成: 成功 %d · 失败 %d' % (ok, fail))
    print('学习后: L1 方向样本 %d | 权重 %.2f | 漂移 %s' % (
        st1['n_direction'], st1['weight_dir'], st1['drift']))
    # 归档
    P.save_json('batch_learn_report.json', {
        'ts': time.strftime('%Y-%m-%d %H:%M'), 'learned': ok, 'failed': fail,
        'n_before': st0['n_direction'], 'n_after': st1['n_direction'],
        'cases': [str(c.get('case_id')) for c in todo]})
    print('报告已存: state/batch_learn_report.json')


if __name__ == '__main__':
    main()
