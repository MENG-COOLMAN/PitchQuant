
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass

"""平局信号去相关聚合器（2026-08-29评审固化·P0-2）
修正53 S1-S8 + R20 S9-S12 共12信号按信息源分4组·组内不重复计数:
  组A 资金流: S1(CS平局资金流)·S2(平赔降赔)·S8(欧盘CS最低平局<4.5) —— 最多计1
  组B 盘口结构: S9(小球盘)·S10(亚盘浅让)·S11(主胜2.1-3.0档) —— 最多计1.5
  组C 基本面/历史: S4(主客平局倾向)·S6(历史交锋平局)·S12(客强ELO) —— 最多计1.5
  组D 赛事结构: S3(半场平联动·半场平≥45%)·S7(两回合首回合) —— 最多计1
  S5(|ELO差|<100) 仅参考不计数
触发: 并列 分组总分≥2.5 · 唯一 分组总分≥4 且 P_平≥25%
D1联动: D1主胜升赔 + 分组总分≥1.5 → 并列
"""
def draw_signal_aggregator(signals, p_draw, d1_up=False):
    """
    signals: dict of signal->bool/int (S1-S12)
    返回: (grouped_score, trigger, detail)
    """
    # 组A: S1/S2/S8
    a = max([signals.get('S1',0), signals.get('S2',0), signals.get('S8',0)])
    a_score = min(a, 1)
    # 组B: S9/S10/S11
    b = max([signals.get('S9',0), signals.get('S10',0), signals.get('S11',0)])
    b_score = min(b, 1.5)
    # 组C: S4/S6/S12
    c_ = max([signals.get('S4',0), signals.get('S6',0), signals.get('S12',0)])
    c_score = min(c_, 1.5)
    # 组D: S3/S7
    d_ = max([signals.get('S3',0), signals.get('S7',0)])
    d_score = min(d_, 1)
    total = a_score + b_score + c_score + d_score
    trigger = 'none'
    if total >= 4 and p_draw >= 0.25:
        trigger = 'sole'
    elif total >= 2.5 or (d1_up and total >= 1.5):
        trigger = 'parallel'
    return (round(total,1), trigger, {'组A资金': a_score, '组B盘口': b_score, '组C基本面': c_score, '组D赛事': d_score})

if __name__ == '__main__':
    # 回测: 浅盘主胜防反·原4信号触发并列·去相关后应不触发
    case96 = {'S1':1,'S2':1,'S4':1,'S6':1}  # S1+S2同组A·S4+S6同组C
    print('case96 去相关:', draw_signal_aggregator(case96, 0.273))
    # /44 回测: 平局信号全现·应仍触发并列
    case42 = {'S1':1,'S2':1,'S4':1,'S6':1,'S3':1,'S9':1}
    print('case42 去相关:', draw_signal_aggregator(case42, 0.30))
    # 全覆盖
    full = {'S1':1,'S2':1,'S8':1,'S9':1,'S10':1,'S11':1,'S4':1,'S6':1,'S12':1,'S3':1,'S7':1}
    print('全覆盖 去相关:', draw_signal_aggregator(full, 0.32))
