"""伤停影响评分（2026-08-29评审固化·P0-5·位置级+重要性级·替代铁则32粗糙"伤停≥3"）
用法:
  A. 位置明细（推荐）: python injury_impact.py --home "前锋,主力;门将,主力" --away "中后卫,轮换"
  B. 直传影响分:        python injury_impact.py --home-score 6.0 --away-score 1.5
  C. 混用:              python injury_impact.py --home "前锋,主力;6.0"   （位置明细 + 追加分）
输出: injury_impact_score(主/客) + lambda_adjustment(主/客±x球) + 触发判定

🔴2026-09-27 修复（case209 raw P2 观察项）: 原实现把纯数字条目当未识别位置名 →
   `--home 6.0` 静默输出影响分 **1.0**（应为 6.0）·与规则不一致。
   现支持直传影响分（纯数字条目 / --home-score / --away-score），
   且未识别位置名改为**显式告警**（不再静默按 1.0 记账）。
"""
import argparse, io, sys
try:                       # 🔴2026-09-27: 原为无条件 TextIOWrapper 重包 → 被 calc_all import 时产生 stdout 副作用
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

POS_WEIGHT = {'门将': 3.0, '中后卫': 2.5, '后腰': 2.0, '边后卫': 1.8, '前腰': 1.8, '边锋': 1.8, '前锋': 2.2, '替补': 0.5, '未知': 1.0}
IMP_MULT = {'主力': 1.5, '轮换': 1.0, '替补': 0.5, '未知': 1.0}


def parse(items):
    """解析伤停条目 → (影响分, 未识别位置列表)

    🔴 条目三态（2026-09-27 扩展·后向兼容）:
      ① "位置,重要性"（如 "门将,主力"）→ 位置权重 × 重要性倍数（原口径·不变）
      ② 纯数字（如 "6.0"）            → 直传影响分（🔴原实现误当位置名→记 1.0）
      ③ 未识别位置名                   → 按 1.0 计 + 记入告警列表（🔴不静默）
    """
    score = 0.0
    unknown = []
    # 🔴2026-11-01 位置统计（消融审计抓出：λ 调整原靠 --home_attack 开关，不传就恒 0）
    pos_n = {'F': 0, 'M': 0, 'D': 0, 'G': 0}
    for it in items:
        it = str(it).strip()
        if not it:
            continue
        try:                                  # ② 直传影响分
            score += float(it)
            continue
        except ValueError:
            pass
        parts = it.split(',')
        pos = parts[0].strip() if parts else '未知'
        imp = parts[1].strip() if len(parts) > 1 else '未知'
        if pos not in POS_WEIGHT:             # ③ 未识别 → 告警（不静默）
            unknown.append(pos)
        for _k, _g in (('前锋', 'F'), ('边锋', 'F'), ('前腰', 'F'),
                       ('后腰', 'M'), ('中场', 'M'),
                       ('中后卫', 'D'), ('边后卫', 'D'), ('门将', 'G')):
            if _k in pos:
                pos_n[_g] += 1
                break
        score += POS_WEIGHT.get(pos, 1.0) * IMP_MULT.get(imp, 1.0)
    return score, unknown, pos_n


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
    ap.add_argument('--home-score', type=float, default=None,
                    help='🔴直传主队影响分(与 --home 叠加·2026-09-27)')
    ap.add_argument('--away-score', type=float, default=None,
                    help='🔴直传客队影响分(与 --away 叠加·2026-09-27)')
    ap.add_argument('--home_attack', action='store_true', help='主队伤停主要在攻击线(前锋/边锋/前腰)')
    ap.add_argument('--away_attack', action='store_true')
    a = ap.parse_args()
    hs, hu, hp = parse([x for x in a.home.split(';') if x])
    as_, au, ap_ = parse([x for x in a.away.split(';') if x])
    if a.home_score is not None:
        hs += a.home_score
    if a.away_score is not None:
        as_ += a.away_score
    print('🔴伤停影响评分(P0-5·位置×重要性·替代铁则32"伤停≥3"):')
    print(f'  主队: 影响分{hs:.1f} → {verdict(hs)}')
    print(f'  客队: 影响分{as_:.1f} → {verdict(as_)}')
    # 🔴2026-11-01 λ 调整改为**按位置自动判定**（原 --home_attack store_true 开关 → 不传恒 0）
    def _side_adj(score, pn, force=None):
        """→ (λ调整值, 说明)。攻击线为主 → 本方λ降；防线为主 → 对手λ升；中性 → 0"""
        if force is not None:
            return (lambda_adj(score, force), '显式指定')
        _f = pn.get('F', 0)
        _d = pn.get('D', 0) + pn.get('G', 0)
        if not score:
            return 0.0, '无伤停'
        if _f > 0 and _f >= _d:
            return -min(score * 0.12, 0.6), '攻击线(%d人)→本方λ降' % _f
        if _d > 0:
            return min(score * 0.12, 0.6), '防线(%d人)→对手λ升' % _d
        if pn.get('M', 0) > 0:
            return -min(score * 0.06, 0.3), '中场(%d人)→本方λ微降' % pn['M']
        return 0.0, '无位置明细'

    _ha = True if a.home_attack else None
    _aa = True if a.away_attack else None
    _h_adj, _h_why = _side_adj(hs, hp, _ha)
    _a_adj, _a_why = _side_adj(as_, ap_, _aa)
    print(f'  λ调整: 主队{_h_adj:+.2f}球（{_h_why}）·客队{_a_adj:+.2f}球（{_a_why}）(±0.6上限)')
    print(f'  铁则32触发: {"是(≥4.0·重度)" if hs >= 4.0 or as_ >= 4.0 else "否"}')
    for _label, _unk in (('主队', hu), ('客队', au)):
        if _unk:
            print(f'  ⚠️ {_label}未识别位置: {", ".join(_unk)}（按1.0计·请用「位置,重要性」或 --home-score/--away-score 直传影响分）')
