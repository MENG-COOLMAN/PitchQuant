# -*- coding: utf-8 -*-
"""
audit_p12.py — P12 机构意图补丁的断言型自检（接入 check_sync 每次必跑）
用法: python data/tmp/audit_p12.py   （exit 0=全绿；非 0=有 P0）
断言内容：
  A. market_intent 可 import 且关键函数齐全
  B. 6 个合成 fixture 全过（降返还率/剪刀差/防平/强诱盘/真信号/盘升水阻）
  C. calc_all 已接入 build_market_intent（存在≠活跃：必须真实调用并传参）
  D. calc_v3572.direction_full 签名含 market_intent
  E. 三态：无快照场次不得抛异常、不得编造方向
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
errs = []


def E(m):
    errs.append(m)


# A. import + 函数齐全
try:
    import market_intent as MI
    for fn in ('ml_vert_analyze', 'eu_ah_cross', 'fundamental_gate',
               'intent_fusion', 'build_market_intent'):
        if not hasattr(MI, fn):
            E('A: market_intent 缺函数 %s' % fn)
except Exception as e:
    E('A: market_intent 无法 import: %r' % e)
    print('\n'.join('❌ ' + x for x in errs))
    sys.exit(1)


# B. 合成 fixture（与 market_intent.unit_tests 同源·断言型）
def pts(o0, o1):
    return [{'saved_at': '2026-10-20 18:00', 'kickoff_bj': '2026-10-20 22:00',
             'extract': {'ml': '%.2f/%.2f/%.2f' % o0}},
            {'saved_at': '2026-10-20 21:00', 'kickoff_bj': '2026-10-20 22:00',
             'extract': {'ml': '%.2f/%.2f/%.2f' % o1}}]


mv = MI.ml_vert_analyze(pts((2.00, 3.40, 3.80), (1.94, 3.30, 3.68)))
if not (mv['pattern'].startswith('降返还率') and mv['intent'] == {'H': 0, 'D': 0, 'A': 0}):
    E('B1 降返还率误报: %s %s' % (mv['pattern'], mv['intent']))
mv = MI.ml_vert_analyze(pts((2.00, 3.40, 3.80), (1.82, 3.78, 4.05)))
if not (mv['pattern'].startswith('剪刀差') and mv['intent']['H'] == 1):
    E('B2 剪刀差漏判: %s' % mv['pattern'])
mv = MI.ml_vert_analyze(pts((2.00, 3.60, 3.50), (1.85, 3.30, 4.10)))
if not (mv['pattern'].startswith('主胜+防平') and mv['intent']['D'] == 1):
    E('B3 防平漏判: %s' % mv['pattern'])
mv = MI.ml_vert_analyze(pts((1.40, 4.80, 7.00), (1.32, 5.30, 7.60)))
fu = MI.intent_fusion(mv, ah_vert={'line0': -1.5, 'line1': -1.5, 'w0': 1.85, 'w1': 1.98,
                                   'combo': '盘稳·主水升', 'shift': -1, 'up_side': '主队(主让场)'},
                      fund={'home_inj': 6.0, 'away_inj': 0, 'home_rotation': True},
                      dual={'C1': {'fav': 'H', 'pct': -4.0}})
if not (fu['gate'].startswith('🔴强诱盘') and fu['cross'].startswith('🔴真诱上') and fu.get('fav') == 'H'):
    E('B4 国米型强诱盘漏判/被诱方向错误: %s | %s | fav=%s' % (fu['gate'], fu['cross'], fu.get('fav')))
mv = MI.ml_vert_analyze(pts((2.00, 3.40, 3.80), (1.82, 3.78, 4.05)))
fu = MI.intent_fusion(mv, ah_vert={'line0': -1.0, 'line1': -1.25, 'w0': 1.90, 'w1': 1.78,
                                   'combo': '升盘降水', 'shift': 1, 'up_side': '主队(主让场)'},
                      fund={'home_inj': 0, 'away_inj': 6.0})
if not (fu['gate'].startswith('真信号') and fu['cross'].startswith('强确认') and fu.get('fav') == 'H'):
    E('B5 真信号漏判/方向错误: %s | %s | fav=%s' % (fu['gate'], fu['cross'], fu.get('fav')))
cr = MI.eu_ah_cross(mv, {'line0': -1.0, 'line1': -1.25, 'w0': 1.806, 'w1': 1.924,
                         'combo': '升盘升水', 'shift': -1, 'up_side': '主队(主让场)'})
if not (cr['cross'].startswith('盘升水阻') and cr['conf'] == 0.3):
    E('B6 升盘升水误判为诱上: %s' % cr['cross'])

# C. calc_all 接线（存在≠活跃：必须调用 build_market_intent 且传入 direction_full）
ca = os.path.join(HERE, 'calc_all.py')
if os.path.exists(ca):
    src = open(ca, encoding='utf-8').read()
    if 'build_market_intent' not in src:
        E('C: calc_all 未调用 build_market_intent（P12 不活跃）')
    if 'market_intent=' not in src:
        E('C: calc_all 未把 market_intent 传入 direction_full（断链）')
else:
    E('C: calc_all.py 不存在（路径基准错误？）')

# D. direction_full 签名
cv = os.path.join(HERE, 'calc_v3572.py')
if os.path.exists(cv):
    vsrc = open(cv, encoding='utf-8').read()
    if 'def direction_full(' in vsrc and 'market_intent=None' not in vsrc:
        E('D: direction_full 签名未加 market_intent=None')
else:
    E('D: calc_v3572.py 不存在')

# E. 三态：无快照 build_market_intent 必须返回结构、不抛异常
try:
    r = MI.build_market_intent('不存在的球队ZZZ', '不存在的球队YYY')
    if not isinstance(r, dict) or ('ok' not in r):
        E('E: 无快照时返回结构非法（应三态 dict）')
except Exception as e:
    E('E: 无快照时 build_market_intent 抛异常: %r' % e)

if errs:
    print('❌ P12 自检发现 %d 个问题：' % len(errs))
    for x in errs:
        print('  ❌ ' + x)
    sys.exit(1)
print('✅ P12 自检全绿：import/6 fixture/接线/签名/三态 全部通过')
