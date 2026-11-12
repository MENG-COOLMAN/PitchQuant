# -*- coding: utf-8 -*-
"""
p12_arbitrate.py — P12.1 方向层调档仲裁纯函数（封装式·可独立单测）
====================================================================
背景（2026-10-26 全量扫描发现）
--------------------------------------------------------------------
direction_full 内方向置信度会被多层信号顺序调整，落地版 P12 放在最后一道，
但存在两个真实的协同缺陷：

  C1 资金盘 P0-1「只升不降」（calc_v3572 ~L657-660）先把置信度 +1 档，
     随后 P12 强诱盘/矛盾（~L701-714）再降/并列 —— 最终档位虽被 P12 拉回，
     但两条 hints 同时残留（一条"+1档"、一条"强诱盘降档"），报告自相矛盾。
     根因：集体诱盘时"跨机构一致(spread<2%)"≠ 看多，而是机构集体诱，
     资金盘升档应被 P12 覆盖。

  C2 静态诱主（浅让 L545 直接降 2 档 / 高水 L549 仅提示 / 平手高水 D6 L647 降 1）
     与 P12 强诱盘是"同源信号"（都在说诱主）。若 P12 再机械降 1 档，
     同一场可能累计降 2~3 档到 LOW（重复计数）；且静态诱主只降 conf、
     不自动 parallel（并列靠 calc_all Step3 打印让 LLM 执行），
     而 P12 强诱盘在代码层直接 parallel=yes —— 两者并列处理不一致。

设计原则（铁律不变）
--------------------------------------------------------------------
  * 永不反转 L2 硬核 1x2 方向；只调置信度 / 扩覆盖（并列）。
  * 强诱盘 / 矛盾属"防守动作"，auto 模式也执行（与 on 无关）；
    真正的"+1 档"仍只有「真信号+亚盘强确认+engage(on)」才能给。
  * 本函数只做"档位 + 并列 + 覆盖标注"的仲裁，不改概率、不选方向。
    方向仍取 intent_fusion 返回的 fav（强诱盘 shift 已反号），
    严禁 max(shift) —— 该铁律在调用方（direction_full）保持。

接口
--------------------------------------------------------------------
p12_arbitrate(conf_after_static, static_trap_touched, spread_raised,
              gate, conf_before_spread=None) -> dict

入参（均由 direction_full 在对应时点如实记录，禁止在本函数内模拟）：
  conf_after_static : str  静态诱主 / 联赛 / D1-D6 全部作用完、"资金盘 P0-1
                          之前"的真实置信度（如 'LOW' / 'MID'）。
  static_trap_touched : bool  本场静态诱主是否已触发（浅让/高水/欧亚背离，
                          即 trap 含"诱主/欧亚背离/高水"）—— 用于同源去重。
  spread_raised : bool       资金盘 P0-1 是否实际 +1 档（spread<2% 且未到顶）。
  gate : str                 intent_fusion 的 gate 字段（真信号/中性/🔴强诱盘/矛盾）。
  conf_before_spread : 兼容别名（缺省 = conf_after_static）。

返回：
  {
    'conf': 'LOW'/'MID-LOW'/... ,   # 仲裁后最终置信度
    'parallel': 'yes'/'no',         # 是否强制并列（扩覆盖）
    'overrides_spread': bool,       # 是否覆盖了资金盘 P0-1 的升档
    'notes': [...],                 # 可读理由（写入 hints，消除矛盾）
  }
"""

ORDER_UP = ['LOW', 'MID-LOW', 'MID', 'MID-HIGH', 'HIGH']
ORDER_DN = ['HIGH', 'MID-HIGH', 'MID', 'MID-LOW', 'LOW']


def _shift(lst, cur):
    """沿档位链移动一格；已到端点则原地不动。"""
    i = lst.index(cur) if cur in lst else -1
    return lst[i + 1] if 0 <= i < len(lst) - 1 else cur


# 触发"防守覆盖"的闸门：强诱盘、矛盾（信号不支持热门，不允许资金盘加档）
DEFENSIVE_GATES = ('🔴强诱盘', '强诱盘')


def _is_defensive(gate):
    g = gate or ''
    return g.startswith('🔴强诱盘') or g.startswith('强诱盘') or g.startswith('矛盾')


def p12_arbitrate(conf_after_static, static_trap_touched, spread_raised, gate,
                  conf_before_spread=None):
    base = conf_before_spread or conf_after_static      # 资金盘升档前的真实档位
    conf = conf_after_static
    notes = []

    # 1) 先回放资金盘 P0-1 的升档（direction_full 调用处已经做过；这里只是终态对齐）
    if spread_raised:
        conf = _shift(ORDER_UP, conf)

    # 2) 防守型闸门（强诱盘 / 矛盾）：覆盖资金盘 + 同源去重 + 强制并列
    if _is_defensive(gate):
        overrides = False
        if spread_raised:
            conf = base                                   # 净抵消资金盘升档（集体诱盘·一致≠看多）
            overrides = True
            notes.append('P12 覆盖资金盘 P0-1 升档（集体诱盘·跨机构一致≠看多）→ 回到 %s' % base)
        is_strong = (gate or '').startswith('🔴强诱盘') or (gate or '').startswith('强诱盘')
        if is_strong:
            if static_trap_touched:
                notes.append('静态诱主已降档（浅让/高水）· P12 同源不重复降档 · 仅补强制并列')
            else:
                conf = _shift(ORDER_DN, conf)
                notes.append('P12 强诱盘：置信度 -1 档 → %s' % conf)
        # 矛盾：不额外降档，只并列（不跟单）
        if (gate or '').startswith('矛盾'):
            notes.append('P12 机构分歧(矛盾)：不跟单 · 维持置信度但强制并列')
        return {'conf': conf, 'parallel': 'yes', 'overrides_spread': overrides, 'notes': notes}

    # 3) 真信号 / 中性：本函数不处理（真信号 +1 档由 direction_full 在 engage(on) 下做；
    #    中性只留痕）。保持资金盘升档后的状态，原样返回。
    return {'conf': conf, 'parallel': 'no', 'overrides_spread': False, 'notes': []}


# ───────────────────────── fixture 单元测试（落地后由 check_sync 调用） ─────────────────────────
def unit_tests():
    n = 0

    def check(name, got_conf, want_conf, got_par, want_par, got_ov, want_ov):
        nonlocal n
        assert got_conf == want_conf and got_par == want_par and got_ov == want_ov, \
            '❌ %s: got(%s,%s,ov=%s) want(%s,%s,ov=%s)' % (
                name, got_conf, got_par, got_ov, want_conf, want_par, want_ov)
        n += 1
        print('  ✅ %s -> %s 并列=%s 覆盖=%s' % (name, got_conf, got_par, got_ov))

    # 场景D：浅让 MID→LOW(降2)，资金盘 LOW→MID-LOW，P12 强诱盘
    r = p12_arbitrate('LOW', True, True, '🔴强诱盘')
    check('浅让+资金盘+P12强诱盘', r['conf'], 'LOW', r['parallel'], 'yes', r['overrides_spread'], True)
    # 仅浅让+P12（无资金盘）：同源不重复降
    r = p12_arbitrate('LOW', True, False, '🔴强诱盘')
    check('浅让+P12(无资金盘)', r['conf'], 'LOW', r['parallel'], 'yes', r['overrides_spread'], False)
    # 资金盘+P12（无静态诱主）：覆盖升档后再降1
    r = p12_arbitrate('MID', False, True, '🔴强诱盘')
    check('资金盘+P12(无浅让)', r['conf'], 'MID-LOW', r['parallel'], 'yes', r['overrides_spread'], True)
    # 仅 P12 强诱盘（无静态、无资金盘）：降1
    r = p12_arbitrate('MID', False, False, '🔴强诱盘')
    check('仅P12强诱盘', r['conf'], 'MID-LOW', r['parallel'], 'yes', r['overrides_spread'], False)
    # 矛盾：覆盖资金盘但不额外降档
    r = p12_arbitrate('LOW', True, True, '矛盾待查')
    check('矛盾(浅让+资金盘)', r['conf'], 'LOW', r['parallel'], 'yes', r['overrides_spread'], True)
    # 中性：不动资金盘、不并列
    r = p12_arbitrate('MID', False, True, '中性')
    check('中性(资金盘升档保留)', r['conf'], 'MID-HIGH', r['parallel'], 'no', r['overrides_spread'], False)
    # 边界：已到最低档
    r = p12_arbitrate('LOW', False, False, '🔴强诱盘')
    check('强诱盘已到LOW不越界', r['conf'], 'LOW', r['parallel'], 'yes', r['overrides_spread'], False)

    print('  p12_arbitrate 单元测试全部通过：%d/%d' % (n, 7))


if __name__ == '__main__':
    unit_tests()
