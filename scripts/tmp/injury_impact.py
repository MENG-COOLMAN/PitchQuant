"""伤停影响评分（2026-08-29评审固化·P0-5·位置级+重要性级·替代铁则32粗糙"伤停≥3"）
用法: python injury_impact.py --home "前锋,主力;门将,主力" --away "中后卫,轮换"
输出: injury_impact_score(主/客) + lambda_adjustment(主/客±x球) + 触发判定
"""
import argparse, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

POS_WEIGHT = {'门将': 3.0, '中后卫': 2.5, '后腰': 2.0, '边后卫': 1.8, '前腰': 1.8, '边锋': 1.8, '前锋': 2.2, '替补': 0.5, '未知': 1.0}
IMP_MULT = {'主力': 1.5, '轮换': 1.0, '替补': 0.5, '未知': 1.0}

def parse(items):
    score = 0
    for it in items:
        parts = it.split(',')
        pos = parts[0].strip() if parts else '未知'
        imp = parts[1].strip() if len(parts) > 1 else '未知'
        pw = POS_WEIGHT.get(pos, 1.0)
        im = IMP_MULT.get(imp, 1.0)
        score += pw * im
    return score

def lambda_adj(score, is_attack):
    """伤停影响分→λ调整: 攻击线伤停降本方进球·防线伤停升对手进球"""
    if is_attack:
        return -min(score * 0.12, 0.6)   # 前锋缺→进球预期降0.3-0.6
    return min(score * 0.12, 0.6)        # 防线缺→失球预期升(对手λ升)

def verdict(score):
    if score >= 6.0: return '极端影响·重新评估方向(考虑反向)'
    if score >= 4.0: return '重度影响·方向置信度降1-2档·可触发R2伤停豁免'
    if score >= 2.0: return '轻度影响·方向置信度降1档·不触发D1豁免'
    return '无显著影响'

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--home', default=''); ap.add_argument('--away', default='')
    ap.add_argument('--home_attack', action='store_true', help='主队伤停主要在攻击线(前锋/边锋/前腰)')
    ap.add_argument('--away_attack', action='store_true')
    a = ap.parse_args()
    hs = parse([x for x in a.home.split(';') if x])
    as_ = parse([x for x in a.away.split(';') if x])
    print('🔴伤停影响评分(P0-5·位置×重要性·替代铁则32"伤停≥3"):')
    print(f'  主队: 影响分{hs:.1f} → {verdict(hs)}')
    print(f'  客队: 影响分{as_:.1f} → {verdict(as_)}')
    print(f'  λ调整: 主队{(lambda_adj(hs, a.home_attack) if a.home_attack else 0):+.2f}球·客队{(lambda_adj(as_, a.away_attack) if a.away_attack else 0):+.2f}球(±0.6上限)')
    print(f'  铁则32触发: {"是(≥4.0·重度)" if hs >= 4.0 or as_ >= 4.0 else "否"}')
