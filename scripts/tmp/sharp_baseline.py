# -*- coding: utf-8 -*-
"""P0-2 Sharp 基准模块（Pinnacle sharp vs soft books · 资金盘升级 2026-09-21）

原理：Pinnacle 为行业公认 sharp book（margin 2-3%·效率误差约 0.24%），
      软庄（面向散户）被迫跟随其定价 → **sharp 与 soft 的方向背离 = RLM 候选**。

🔴 数据可得性（三态标注·诚实边界）：
  - api-football `odds?fixture=ID` 返回 13 家 → 若含 Pinnacle/betfair/matchbook → 通道 ok
  - Odds-API 免费 tier 常仅 1xbet（+B365 ML）→ status='no_pinnacle'
  - 无 sharp 数据时 → **降级用 spread 指标替代**（P0-1 不依赖单机构）
🔴 回测状态：**pending_backtest**（需 ≥1000 场同时含 sharp 与 soft 的比赛）
  → 当前仅输出提示，**不进入判定链**
"""
import statistics
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

SHARP_KEYS = {'pinnacle', 'ps', 'betfair', 'betfair exchange', 'matchbook', 'smarkets',
              'pinnacle sports', 'asianodds', 'isn'}
SOFT_KEYS = {'bet365', '1xbet', 'bwin', 'william hill', 'williamhill', 'betway', 'unibet',
             'marathonbet', 'sbobet', '10bet', '188bet', 'betsson', 'dafabet', 'interwetten',
             'nordicbet', 'betano', 'betwinner', 'melbet', '1xstavka', 'sportingbet', 'marathon'}


def _norm(name):
    return (name or '').strip().lower()


def is_sharp(name):
    n = _norm(name)
    return any(k in n for k in SHARP_KEYS)


def is_soft(name):
    n = _norm(name)
    return any(k in n for k in SOFT_KEYS)


def _devig(h, d, a):
    inv = [1 / h, 1 / d, 1 / a]
    t = sum(inv)
    return {'H': inv[0] / t, 'D': inv[1] / t, 'A': inv[2] / t}


def sharp_vs_soft(books):
    """对比 sharp vs soft 的去水概率方向

    books: [{'bookmaker':..,'h':..,'d':..,'a':..}, ...]
    返回 dict（含 status 三态）
    """
    if not books:
        return {'status': 'na', 'reason': '无逐家赔率数据'}
    sharp = [b for b in books if is_sharp(b.get('bookmaker', ''))]
    soft = [b for b in books if is_soft(b.get('bookmaker', ''))]
    if not sharp:
        return {'status': 'no_sharp', 'fallback': 'use_spread(替代 P0-1)',
                'reason': '13 家中无 Pinnacle/betfair/matchbook 等 sharp 机构'}
    if not soft:
        return {'status': 'no_soft', 'fallback': 'use_sharp_only',
                'reason': '仅有 sharp 机构，无 soft 对照'}

    sp = sharp[0]
    try:
        pin_p = _devig(float(sp['h']), float(sp['d']), float(sp['a']))
        soft_p = _devig(statistics.median(float(b['h']) for b in soft),
                        statistics.median(float(b['d']) for b in soft),
                        statistics.median(float(b['a']) for b in soft))
    except (ValueError, TypeError, KeyError):
        return {'status': 'na', 'reason': '赔率解析失败'}

    div = {k: round((pin_p[k] - soft_p[k]) * 100, 1) for k in 'HDA'}
    sharp_lean = max(pin_p, key=pin_p.get)
    soft_lean = max(soft_p, key=soft_p.get)
    conf = abs(div[sharp_lean]) >= 3.0
    return {
        'status': 'ok',
        'sharp_book': sp.get('bookmaker'), 'sharp_n': len(sharp), 'soft_n': len(soft),
        'sharp_probs': {k: round(v * 100, 1) for k, v in pin_p.items()},
        'soft_probs': {k: round(v * 100, 1) for k, v in soft_p.items()},
        'divergence_pp': div,
        'sharp_lean': sharp_lean, 'soft_lean': soft_lean,
        'rlm_candidate': bool(sharp_lean != soft_lean and conf),
        'annotation': (f"🔴 RLM 候选：sharp 偏 {sharp_lean}（{div[sharp_lean]:+.1f}pp）vs soft 偏 {soft_lean}"
                       if (sharp_lean != soft_lean and conf) else
                       f"sharp 与 soft 方向一致（{sharp_lean}）→ 增强置信"),
        'backtest': 'pending_backtest',
    }


def render(res):
    L = ['【Sharp 基准 · P0-2】']
    st = res.get('status')
    if st != 'ok':
        L.append(f"  ⚠️ 不可用: status={st} · {res.get('reason', '')}")
        if res.get('fallback'):
            L.append(f"  降级方案: {res['fallback']}")
        return "\n".join(L)
    L.append(f"  sharp: {res['sharp_book']}（n={res['sharp_n']}） {res['sharp_probs']}")
    L.append(f"  soft(n={res['soft_n']}): {res['soft_probs']}")
    L.append(f"  背离 pp: {res['divergence_pp']}")
    L.append(f"  {res['annotation']}")
    L.append(f"  ⚠️ 回测状态: {res['backtest']} → 仅提示·不进入判定链")
    return "\n".join(L)


if __name__ == '__main__':
    demo = [{'bookmaker': 'Pinnacle', 'h': 1.90, 'd': 3.55, 'a': 4.10},
            {'bookmaker': 'Bet365', 'h': 1.95, 'd': 3.50, 'a': 4.00},
            {'bookmaker': '1xBet', 'h': 1.96, 'd': 3.48, 'a': 3.95}]
    print(render(sharp_vs_soft(demo)))
    print()
    print(render(sharp_vs_soft([{'bookmaker': '1xBet', 'h': 1.9, 'd': 3.5, 'a': 4.1}])))
