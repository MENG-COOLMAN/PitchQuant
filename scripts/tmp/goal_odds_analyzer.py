# -*- coding: utf-8 -*-
"""goal_odds_analyzer.py — 竞彩总进球数赔率反推模块（2026-09-06·用户方案《阈值优化版》落地）
功能: 依据竞彩txt【总进球固定奖金】0-7+八档赔率 → 返奖率校验/各档概率/大小球三盘口单调/五级量级/与泊松KL融合/偏差信号/投注EV参考
依据: 竞彩网官方数据返奖率78-83%·英超λ=2.604·五大联赛场均2.5-2.9球——阈值全部采用方案第八节汇总表
用法: python goal_odds_analyzer.py <0球,1球,2球,3球,4球,5球,6球,7+球赔率> [--poisson p0,p1,...p7]
     或 from goal_odds_analyzer import analyze_goal_odds
"""
import sys, math

if hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding', '').lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')  # 🔴仅独立CLI时包装·避免被import时二次包装致I/O closed

# ── 第八节阈值表 ──
ODD_RANGE = {'0': (7.0, 25.0), '1': (3.5, 7.0), '2': (2.8, 4.5), '3': (3.0, 4.5),
             '4': (4.5, 8.0), '5': (7.0, 15.0), '6': (12.0, 30.0), '7+': (15.0, 45.0)}
SUM_RANGE = (1.18, 1.30)          # 倒数和(返奖率77-85%)
P_RANGE = {'0': (0.03, 0.12), '1': (0.10, 0.22), '2': (0.18, 0.30), '3': (0.16, 0.28),
           '4': (0.08, 0.20), '5': (0.03, 0.12), '6': (0.015, 0.07), '7+': (0.01, 0.06)}
OV_STRONG_BIG, OV_BIG, OV_MID, OV_SMALL = 0.58, 0.53, 0.47, 0.42   # 强烈大/大/中性47-53/小
# 信号强度三档（大小球精细化升级·Matches 148,397场时间分割实测）
# 实测命中率（test 44,479场·欧盘 O2.5 隐含概率口径·train/test 差异≤1.5pp）：
# 强(≥58%/≤42%) 63.85% > 基线(53%阈值全档) 59.54% > 中(55-58%/42-45%) 57.56% > 弱(53-55%/45-47%) 54.39%
# → 分层价值 = 识别弱信号（仅 54.4% ≈ 随机）·禁把弱信号当强信号消费
# 注：中/弱档低于基线是"基线含强信号拉高平均"所致·非分层无效（分层单调·train/test 一致）
OV_MED_BIG, OV_WEAK_BIG = 0.55, 0.53      # 大球：中 55-58% / 弱 53-55%
OV_MED_SML, OV_WEAK_SML = 0.45, 0.47      # 小球：中 42-45% / 弱 45-47%
SIGNAL_HIT = {'强大球': 65.0, '强大球_小球': 62.6, '中大球': 57.0, '中小球': 58.0,
              '弱大球': 54.8, '弱小球': 54.1}   # 分侧实测命中率(%)
BASE_HIT_53 = 59.54                        # 53% 阈值基线（全档平均·test 集 19103/32084）
SIGNAL_HIT_MERGED = {'强': 63.85, '中': 57.56, '弱': 54.39}
KL_HI, KL_BASE, KL_LOW, KL_EXT = 0.03, 0.08, 0.15, 0.20            # 高度/基本/轻度/显著/极端
ALPHA_BASE, ALPHA_MIN, ALPHA_MAX = 0.5, 0.40, 0.60
GAMMA = 0.7

def analyze_goal_odds(odds, poisson=None):
    """odds: 8档赔率[0,1,2,3,4,5,6,7+]·poisson可选8档泊松概率"""
    if len(odds) != 8 or any(o <= 1.0 for o in odds):
        return {'error': '赔率须8档且>1.0'}
    inv = [1.0 / o for o in odds]
    s = sum(inv)
    ret = 78.0 / s  # 返奖率 ≈ 1/s 归一化后(去水)各档占比·实际返奖率=1/s 归一化损失? 竞彩返奖率≈77-85%由倒数和体现
    # 去抽水概率 = inv/s(归一)
    p = [i / s for i in inv]
    keys = ['0', '1', '2', '3', '4', '5', '6', '7+']
    out = {'返奖率': 100.0 / s, '倒数和': round(s, 4), '概率': dict(zip(keys, [round(x * 100, 1) for x in p]))}
    # 校验: 单档范围/概率范围
    anomaly = []
    for k, o, pp in zip(keys, odds, p):
        lo, hi = ODD_RANGE[k]
        if not (lo <= o <= hi): anomaly.append(f"{k}球赔率{o}超范围({lo}-{hi})")
        plo, phi = P_RANGE[k]
        if not (plo <= pp <= phi): anomaly.append(f"{k}球概率{pp*100:.1f}%超合理带")
    out['异常'] = anomaly if anomaly else '无'
    if not (SUM_RANGE[0] <= s <= SUM_RANGE[1]): out['返奖率提示'] = '倒数和%.3f超带(1.18-1.30)' % s
    # 7+ 平滑(去水前概率<0.01时平滑·此处用去水后标注)
    if p[7] < 0.01: out['提示'] = ['7+球概率<1%·按1%平滑参考']
    # 统计量: mean(7+取7)/mode/五级量级
    mean = sum(k * pp for k, pp in enumerate(p[:7])) + 7 * p[7]
    mode = max(range(8), key=lambda i: p[i])
    # 大小球三盘口: over1.5=P2+·over2.5=P3+·over3.5=P4+
    ov15, ov25, ov35 = sum(p[2:]), sum(p[3:]), sum(p[4:])
    mono = ov15 > ov25 > ov35
    out.update({'mean': round(mean, 2), 'mode': f'{mode}球' if mode < 7 else '7+球',
                'over1.5': round(ov15 * 100, 1), 'over2.5': round(ov25 * 100, 1), 'over3.5': round(ov35 * 100, 1),
                '大小球单调': '✓' if mono else '✗非单调(数据异常·大小球信号不使用)'})
    # 五级量级(8.3·🔴修正: 以mean连续主判据·mode仅mean异常回退——原mode∈{2,3}误挡mean3.6大球场)
    if mean >= 4.5 or mean < 1.0:  # 均值异常→回退mode
        mode_i = max(range(8), key=lambda i: p[i])
        if mode_i == 0: mag = '极小进球(0-1球)'
        elif mode_i == 1: mag = '小进球(1-2球)'
        elif mode_i in (2, 3): mag = '中进球(2-3球)'
        elif mode_i == 4: mag = '大进球(3-5球)'
        else: mag = '极大进球(5+球)'
        out['均值异常回退mode'] = True
    elif mean < 1.5: mag = '极小进球(0-1球)'
    elif mean < 2.2: mag = '小进球(1-2球)'
    elif mean < 3.0: mag = '中进球(2-3球)'
    elif mean < 3.8: mag = '大进球(3-5球)'
    else: mag = '极大进球(5+球)'
    out['量级'] = mag
    # 大小球倾向(3.1): 五级 + 🔴信号强度三档（精细化升级）
    if not mono:
        out['大小球倾向'] = '不判(非单调·数据异常·大小球信号不使用)'
        out['信号强度'] = '不判'
    elif ov25 >= OV_STRONG_BIG:
        out['大小球倾向'] = '强烈大球(≥58%)'
        out['信号强度'] = '🔴强信号 大球(实测 65.0%·>基线59.5%)'
    elif ov25 >= OV_MED_BIG:
        out['大小球倾向'] = '大球-中信号(55-58%)'
        out['信号强度'] = '🟡中信号 大球(实测 57.0%·<基线59.5%)'
    elif ov25 >= OV_BIG:
        out['大小球倾向'] = '大球-弱信号(53-55%)'
        out['信号强度'] = '⚪弱信号 大球(实测 54.8%·≈随机·仅参考·不进串关)'
    elif ov25 >= OV_MID:
        out['大小球倾向'] = '中性(47-53%)'
        out['信号强度'] = '⚫中性·不判方向'
    elif ov25 >= OV_MED_SML:
        out['大小球倾向'] = '小球-弱信号(45-47%)'
        out['信号强度'] = '⚪弱信号 小球(实测 54.1%·≈随机·仅参考·不进串关)'
    elif ov25 >= OV_SMALL:
        out['大小球倾向'] = '小球-中信号(42-45%)'
        out['信号强度'] = '🟡中信号 小球(实测 58.0%·<基线59.5%)'
    else:
        out['大小球倾向'] = '强烈小球(≤42%)'
        out['信号强度'] = '🔴强信号 小球(实测 62.6%)'
    # 极端档高估提示（发现·Matches 148,397场·train/test 一致稳健）
    # 含义：隐含大球≥65% 的场次实际仅 70.9%/71.4% → 65-75% 区间系统性高估 5-6pp
    # （75-85% 区间校准良好·80.3%/81.4%）→ 禁按隐含值线性外推大胜比分
    if ov25 is not None and ov25 >= 0.65:
        out['极端档提示'] = ('隐含大球≥65%档实际仅 70.9-71.4%(train/test)——65-75%区间系统性高估 5-6pp·'
                             '禁按隐含值线性外推大胜比分·大胜型比分按 goal_bins 档分布消费')
    # KL + α融合(与泊松)
    if poisson and len(poisson) == 8:
        kl = sum(pp * math.log(pp / max(qq, 1e-12), 2) for pp, qq in zip(p, poisson) if pp > 0)
        if kl < KL_HI: agree = '高度一致(KL<0.03)'
        elif kl < KL_BASE: agree = '基本一致(0.03-0.08)'
        elif kl < KL_LOW: agree = '轻度分歧(0.08-0.15)·需关注'
        elif kl < KL_EXT: agree = '显著分歧(≥0.15)·市场有额外信息'
        else: agree = '极端分歧(≥0.20)·不融合分别输出'
        alpha = ALPHA_BASE
        if kl < KL_HI: alpha += 0.03
        elif kl >= KL_EXT: alpha -= 0.05
        alpha = max(ALPHA_MIN, min(ALPHA_MAX, alpha))
        out['一致度'] = agree
        out['KL'] = round(kl, 3)
        out['α'] = alpha
        # 偏差信号(5.4)
        dev = []
        mp345, pp345 = p[3] + p[4] + p[5], poisson[3] + poisson[4] + poisson[5]
        if kl >= 0.08 and mp345 > pp345 + 0.06: dev.append('市场诱大球(市场P3-5>泊松>6pp)·小球+0.05权重')
        mp012 = p[0] + p[1] + p[2]
        if kl >= 0.08 and mp012 > (poisson[0] + poisson[1] + poisson[2]) + 0.06: dev.append('市场诱小球(市场P0-2>泊松>6pp)·大球+0.05权重')
        # 价值档: 市场单档 < 泊松-4pp 且该档EV≥-0.05
        val = [k for k, pp in enumerate(p) if pp < poisson[k] - 0.04 and 1 / odds[k] * poisson[k] - 1 >= -0.05]
        if val: dev.append(f"价值档位: {val}球(市场低估>4pp·EV≥-0.05)")
        out['偏差信号'] = dev if dev else '无'
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    odds = [float(x) for x in sys.argv[1].split(',')]
    poisson = None
    if '--poisson' in sys.argv:
        i = sys.argv.index('--poisson')
        poisson = [float(x) for x in sys.argv[i + 1].split(',')]
    r = analyze_goal_odds(odds, poisson)
    if 'error' in r:
        print(r['error']); return
    print('=' * 60)
    print('🔴竞彩总进球赔率反推(goal_odds_analyzer·2026-09-06·方案阈值优化版)')
    print('=' * 60)
    print('  返奖率: %.1f%% (倒数和%.4f·合理带1.18-1.30)' % (r['返奖率'], r['倒数和']))
    print('  各档概率: ' + ' '.join('%s球%.1f%%' % (k, v) for k, v in r['概率'].items()))
    print('  校验: %s' % (r['异常'] if r['异常'] != '无' else '8档赔率/概率均在合理带'))
    print('  mean=%.2f球 mode=%s | 量级: %s' % (r['mean'], r['mode'], r['量级']))
    print('  大小球: over1.5=%.1f%% over2.5=%.1f%% over3.5=%.1f%% | %s | 倾向: %s' % (
        r['over1.5'], r['over2.5'], r['over3.5'], r['大小球单调'], r['大小球倾向']))
    if r.get('信号强度'):
        print('  🔴信号强度: %s' % r['信号强度'])
    if r.get('极端档提示'):
        print('  ⚠️%s' % r['极端档提示'])
    if '一致度' in r:
        print('  与泊松: KL=%.3f %s | α=%.2f' % (r['KL'], r['一致度'], r['α']))
        print('  偏差信号: %s' % (r['偏差信号'] if r['偏差信号'] != '无' else '无'))
    print('  消费: Step6大小球(五级倾向+🔴信号强度三档·强63.9%/中57.6%/弱54.4%·基线59.5%·'
          '弱信号≈随机仅参考不进串关·中性47-53%不判)·Step7比分量级(五级量级+goal_bins典型比分)')

if __name__ == '__main__':
    main()
