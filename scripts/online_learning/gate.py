# -*- coding: utf-8 -*-
"""gate.py —— 接入门禁 + 回滚监测（2026-09-11·学习结果接入预测的质量控制）

🔴设计原则（防过拟合/防噪音）：
  1) 回测门禁: 任何新接入(特征组/层/权重变更)必须先通过时间分割回测 + 配对显著性 p<0.05
  2) 样本门禁: n<50 → 权重 0；50-200 → 0.05；>=200 → 0.10（封顶）
  3) 回滚门禁: 滚动 20 场实测偏差 >10pp → 自动降级为"仅记录"
  4) 输出裁剪: 超合理范围丢弃、缺失填 0 不计入、无数据三态标注

用法:
  python data/online_learning/gate.py --status           # 当前门禁状态
  python data/online_learning/gate.py --log --case 158 --pred-fused 1 --actual 0   # 记录融合预测 vs 实际
  python data/online_learning/gate.py --rollback-check   # 滚动偏差检查（超阈值自动降级）
"""
import os, sys, io, json, argparse, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
STATE = os.path.join(HERE, 'state')
GATE = os.path.join(STATE, 'gate.json')
MON = os.path.join(STATE, 'fusion_monitor.json')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROLLING_N = 20          # 滚动窗口
DEGRADE_PP = 0.10       # 偏差阈值（10pp）


def _load(p, d):
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding='utf-8'))
        except Exception:
            pass
    return d


def _save(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(o, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def default_gate():
    # 🔴2026-09-30 泄露裁决（默认值必须与 state/gate.json 一致·防 gate.json 重建时复活错误状态）:
    #   原默认 = L1 'active'/enabled=True/weight=0.10 → 一旦 gate.json 被删或重建，已否决的 L1 会复活
    #   并再次以权重 0.10 混入融合（融合≡市场 → 弱共识场被硬推）→ 故默认即 rejected_leak
    return {
        'L1_online_ml': {'enabled': False, 'weight': 0.0, 'status': 'rejected_leak',
                         'evidence': '🔴数据泄露裁决(2026-09-30): 原依据 +0.68pp 证实为泄露(validate_fusion 26特征含17个赛后统计)·赛前可得特征仅 +0.01pp·旁证 n=48 融合21=基准21 / 历史30000场 -14.2pp',
                         'since': '2026-09-11', 'rejected_since': '2026-09-30',
                         'restore_condition': '需在「仅赛前可得特征」下时间分割增益≥热门基准且 p<0.05'},
        'L1_fusion_in_decision': {'enabled': False, 'status': 'rejected_leak',
                                  'since': '2026-09-16',
                                  'evidence': 'L1 已 rejected_leak → 融合权重 0 → 融合≡市场 → 数学上无增益(n=48 融合21=基准21)'},
        'L2_incremental': {'enabled': False, 'weight': 0.0, 'status': 'rejected',
                           'evidence': '60000场公平A/B: Top2 24.70% vs 24.94% (z=1.59 p>0.05 不显著)'},
        'L3_error_rules': {'enabled': True, 'weight': None, 'status': 'gated',
                           'evidence': '门槛≥30样本自动生成·命中时仅提示/序微调(概率差<2pp)'},
        'L4_cbr': {'enabled': False, 'weight': 0.0, 'status': 'cold_start',
                   'evidence': '案例<10 冷启动·需 ≥30 案例且有回测证据'},
        'learned_rules': {'enabled': True, 'weight': None, 'status': 'active',
                          'evidence': '复发≥2自动提示·仅影响置信度判断·不反转方向'},
    }


def ensure_gate():
    """gate.json 不存在则用默认值初始化（2026-09-11 审计修复: 状态须持久化）"""
    if not os.path.exists(GATE):
        _save(GATE, default_gate())
    return _load(GATE, default_gate())


def cmd_status(a):
    g = _load(GATE, default_gate())
    print('=== 学习结果接入门禁状态 ===')
    print('%-18s %-8s %-8s %-12s %s' % ('组件', '启用', '权重', '状态', '依据'))
    for k, v in g.items():
        print('%-18s %-8s %-8s %-12s %s' % (k, v.get('enabled'), v.get('weight'), v.get('status'), (str(v.get('apply_mode', '')) + ' ' + str(v.get('evidence'))[:36]) if v.get('apply_mode') else str(v.get('evidence'))[:44]))
    m = _load(MON, {'n': 0, 'fusion_hits': 0, 'base_hits': 0, 'history': []})
    print('\n=== 融合监测（滚动 %d 场）===' % ROLLING_N)
    print('累计记录 %d 场 | 融合命中 %d | 基准命中 %d' % (m['n'], m['fusion_hits'], m['base_hits']))
    if m['n']:
        print('融合 vs 基准: %+.2fpp' % ((m['fusion_hits'] - m['base_hits']) / m['n'] * 100))
    print('回滚阈值: 滚动偏差 >%.0fpp → 自动降级为仅记录' % (DEGRADE_PP * 100))


def cmd_log(a):
    """记录一场（融合预测结果 vs 实际）→ 用于滚动监测"""
    m = _load(MON, {'n': 0, 'fusion_hits': 0, 'base_hits': 0, 'history': []})
    rec = {'case': a.case, 'fused_pred': a.pred_fused, 'base_pred': getattr(a, 'pred_base', None),
           'actual': a.actual, 'date': time.strftime('%Y-%m-%d')}
    if a.pred_fused is not None and a.actual is not None:
        rec['fused_hit'] = (int(a.pred_fused) == int(a.actual))
        m['fusion_hits'] += 1 if rec['fused_hit'] else 0
    if getattr(a, 'pred_base', None) is not None and a.actual is not None:
        rec['base_hit'] = (int(a.pred_base) == int(a.actual))
        m['base_hits'] += 1 if rec['base_hit'] else 0
    m['n'] += 1
    m['history'].append(rec)
    m['history'] = m['history'][-200:]
    _save(MON, m)
    print('已记录: case%s 融合预测=%s 实际=%s → %s' % (
        a.case, a.pred_fused, a.actual, '✅' if rec.get('fused_hit') else '❌'))
    cmd_rollback_check(a)


def cmd_rollback_check(a=None):
    """滚动偏差检查: 超阈值自动降级"""
    m = _load(MON, {'n': 0, 'history': []})
    g = _load(GATE, default_gate())
    hist = [h for h in m['history'] if 'fused_hit' in h][-ROLLING_N:]
    if len(hist) < ROLLING_N:
        print('滚动样本不足(%d/%d)·不回滚检查' % (len(hist), ROLLING_N))
        return
    fh = sum(1 for h in hist if h['fused_hit'])
    bh = sum(1 for h in hist if h.get('base_hit'))
    dev = (fh - bh) / len(hist)
    print('滚动%d场: 融合 %.2f%% vs 基准 %.2f%% → %+.2fpp' % (
        len(hist), fh / len(hist) * 100, bh / len(hist) * 100, dev * 100))
    if dev < -DEGRADE_PP:
        g['L1_online_ml']['status'] = 'degraded'
        g['L1_online_ml']['weight'] = 0.0
        g['L1_online_ml']['degraded_at'] = time.strftime('%Y-%m-%d')
        g['L1_online_ml']['degrade_reason'] = '滚动%d场偏差 %+.2fpp 超阈值' % (len(hist), dev * 100)
        _save(GATE, g)
        print('🔴 已自动降级 L1 为仅记录(权重 0)·原因: 滚动偏差超 -10pp')
    else:
        print('✅ 未触发回滚（阈值 -%.0fpp）' % (DEGRADE_PP * 100))
    # 同步写入 config 可读的门禁状态
    _save(os.path.join(STATE, 'gate_status.json'),
          {'L1_weight': g['L1_online_ml']['weight'], 'L1_status': g['L1_online_ml']['status'],
           'rolling_dev_pp': round(dev * 100, 2), 'rolling_n': len(hist)})


def main():
    ensure_gate()
    ap = argparse.ArgumentParser()
    ap.add_argument('--status', action='store_true'); ap.add_argument('--init', action='store_true')
    ap.add_argument('--log', action='store_true')
    ap.add_argument('--rollback-check', action='store_true', dest='rb')
    ap.add_argument('--case'); ap.add_argument('--pred-fused', type=int, dest='pred_fused')
    ap.add_argument('--pred-base', type=int, dest='pred_base'); ap.add_argument('--actual', type=int)
    a = ap.parse_args()
    if a.init: print('gate.json 已初始化:', ensure_gate() and GATE)
    elif a.log: cmd_log(a)
    elif a.rb: cmd_rollback_check(a)
    else: cmd_status(a)


if __name__ == '__main__':
    main()
