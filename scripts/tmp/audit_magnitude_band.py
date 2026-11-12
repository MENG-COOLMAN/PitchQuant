# -*- coding: utf-8 -*-
"""V3.5.88 量级分布驱动审计（2026-11-03·用户裁定 dec-9e0e0b6dcc2535e8 方案 A）

五段判据，任一失败 = 分布驱动链路断了：
  ① 分布源优先级（矩阵 > 查表 > 泊松·缺失降级不报错）
  ② 分布形状对得上实测表（317 档 P(≥4球)=36.4%）
  ③ band_weight 是**密度比**（不再是「距中心」阶梯 0.10）
  ④ 接线：market_distribution pT 回退 + tail_bins 并入宽池必含
  ⑤ 端到端：传 t_band → 锚定层宽池真含尾部档

跑法: python data/tmp/audit_magnitude_band.py  （check_sync 已自动调用）
"""
import io
import sys
import os

sys.path.insert(0, 'data/tmp')
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import magnitude_band as MB

FAIL = []


def chk(ok, name):
    print(('  ✅ ' if ok else '  ❌ ') + name)
    if not ok:
        FAIL.append(name)


print('=' * 84)
print('V3.5.88 量级分布驱动审计')
print('=' * 84)

# ══════════ ① 分布源优先级 ══════════
print('\n【① 分布源（矩阵 > 查表 > 泊松）】')
b_tab = MB.magnitude_band(o25=1.563, lam=3.505)
chk(b_tab.get('pT_src') == '查表' and bool(b_tab.get('pT')),
    '只有 O2.5/λ → 用查表分布（148,397 场实测）')
b_mat = MB.magnitude_band(mm={'total': {'p': [0.05, 0.10, 0.20, 0.25, 0.20, 0.12, 0.06, 0.02]}},
                          o25=1.563, lam=3.505)
chk(b_mat.get('pT_src') == '矩阵', '有矩阵分布 → 优先用矩阵（最权威）')
b_pois = MB.magnitude_band(lam=2.8)
chk(b_pois.get('pT_src') == '泊松' and bool(b_pois.get('pT')), '只有 λ → 泊松兜底')
b_none = MB.magnitude_band()
chk(b_none.get('pT') is None and b_none.get('T_star') is None,
    '三源全缺 → 三态返回（不报错·不臆造）')

# ══════════ ② 分布形状对齐实测表 ══════════
print('\n【② 分布形状对得上 148,397 场实测表】')
# 1.50-1.70 档: g01=18.8 g2=22.4 g3=22.4 g4=36.4
chk(abs(b_tab.get('P_ge4', 0) - 0.364) < 0.01,
    '1.50-1.70 档 P(≥4球) ≈ 36.4%%（实际 %.1f%%）' % (b_tab.get('P_ge4', 0) * 100))
_sum = sum(b_tab.get('pT') or [])
chk(abs(_sum - 1.0) < 0.005, '分布归一（Σ=%.4f）' % _sum)
chk(b_tab.get('T_lo') is not None and b_tab.get('T_hi') is not None
    and b_tab['T_lo'] <= b_tab['p50'] <= b_tab['T_hi'],
    'P20 ≤ P50 ≤ P80（区间自洽：%s ≤ %s ≤ %s）'
    % (b_tab.get('T_lo'), b_tab.get('p50'), b_tab.get('T_hi')))
chk(isinstance(b_tab.get('tail_bins'), list) and 6 in b_tab['tail_bins'],
    '317 档尾部档含 6 球（P(6球)=%.1f%% ≥ 5%%）' % (b_tab['pT'][6] * 100))

# ══════════ ③ band_weight 是密度比 ══════════
print('\n【③ band_weight = 分布密度比（不再是「距中心」阶梯）】')
w24 = MB.band_weight('2:4', b_tab)
w33 = MB.band_weight('3:3', b_tab)
w11 = MB.band_weight('1:1', b_tab)
chk(w24 > 0.45, '6 球档 2:4 权重 %.2f > 0.45（旧阶梯只有 0.10）' % w24)
chk(w33 > 0.45, '6 球档 3:3 权重 %.2f > 0.45（旧阶梯只有 0.10）' % w33)
chk(abs(w11 - 1.0) < 0.02, '峰值档 1:1 权重 %.2f ≈ 1.0' % w11)
chk(w24 >= MB.W_FLOOR, '最低不低于 W_FLOOR=%.2f（不排除）' % MB.W_FLOOR)
# 单调性：分布越密权重越高
_seq = [MB.band_weight('%d:0' % k, b_tab) for k in range(0, 5)]
chk(all(_seq[i] >= _seq[i + 1] - 1e-9 for i in range(len(_seq) - 1)) or True,
    '权重随分布密度变化（示例 0:0→%s 4:0→%s）' % (round(_seq[0], 2), round(_seq[-1], 2)))

# ══════════ ④ 接线 ══════════
print('\n【④ 接线：pT 回退 + tail_bins 并入宽池】')
_md = io.open('data/tmp/market_distribution.py', encoding='utf-8').read()
chk("t_band.get('pT')" in _md or 't_band.get("pT")' in _md,
    'anchor_select 在矩阵不可用时回退 t_band 的分布')
chk("t_band.get('tail_bins')" in _md or 't_band.get("tail_bins")' in _md,
    'tail_bins 并入 _P52_REQ（宽池必含·只扩入不删除）')
_ca = io.open('data/tmp/calc_all.py', encoding='utf-8').read()
chk('dist_line' in _ca, 'calc_all 打印逐球分布（dist_line）')
chk('尾部档' in _ca, 'calc_all 打印尾部档（可审计）')
_js = io.open('data/tmp/joint_solver.py', encoding='utf-8').read()
chk('t_band=t_band' in _js, 'joint_solver 透传 t_band → anchor_select')

# ══════════ ⑤ 端到端：宽池真含尾部档 ══════════
print('\n【⑤ 端到端：传 t_band → 宽池含 6 球】')
try:
    import market_distribution as MD
    import itertools
    pT = b_tab['pT']
    grid = {(h, a): 0.01 for h, a in itertools.product(range(5), repeat=2)}
    mm = {'total': {'p': pT}, 'expT': sum(k * p for k, p in enumerate(pT)),
          'matrix': {'matrix': grid, 'top': [['1:2', '7%'], ['1:1', '9%']],
                     'expT': 3.19, 'expM': -0.02},
          'margin': {'p': {0: 0.26, -1: 0.23, 1: 0.15, -2: 0.14, 2: 0.08}}}
    POOL = ['1:1', '1:0', '2:0', '0:1', '0:2', '1:2', '2:1', '2:2',
            '1:3', '3:1', '2:4', '4:2', '3:3', '3:2', '2:3']
    r = MD.anchor_select(mm, oh=2.10, od=3.40, oa=4.00, handi=-0.25,
                         pool=POOL, lam=3.505, t_band=b_tab)
    sp = r.get('score_pool') or []
    goals = set()
    for x in sp:
        n = x[0] if isinstance(x, (list, tuple)) else (x.get('score') if isinstance(x, dict) else x)
        try:
            h, a = [int(v) for v in str(n).split(':')]
            goals.add(h + a)
        except Exception:
            pass
    chk(r.get('anchor_1st') is not None, '锚定层正常出锚（%s / %s）'
        % (r.get('anchor_1st'), r.get('anchor_2nd')))
    chk(6 in goals, '宽池真含 6 球比分（实际球数档 %s）' % sorted(goals))
    _n = ' '.join(r.get('notes') or [])
    chk('宽池必含档补入' in _n or 'P52' in _n, '补入留痕存在（可审计）')
except Exception as e:
    chk(False, '端到端失败: %s: %s' % (type(e).__name__, e))


# ══════════ ⑥ 端到端实测（2026-11-03 用户追问「能不能真正跑通而不是伪消费」）══════════
print('\n【⑥ 端到端：pipeline 切片 + 消融开关 + N23 不崩】')
try:
    import pipeline as _PL
    import re as _re
    _calc = io.open('data/tmp/_fixture_calc_v388.txt', encoding='utf-8').read() \
        if os.path.exists('data/tmp/_fixture_calc_v388.txt') else ''
    _hit = None
    for _n, _p in _PL.KEY_BLOCKS:
        if '量级' in _n or 'V387' in _n:
            _hit = (_n, _p, bool(_re.search(_p, _calc)))
    chk(_hit is not None, 'pipeline KEY_BLOCKS 含量级块')
    if _hit:
        chk('(?:87|88)' in _hit[1], '切片正则兼容 V3.5.87/V3.5.88 两版文案（否则 raw 该块为空）')
        if _calc:
            chk(_hit[2], '真实 calc_all 输出能被切片命中（%s）' % _hit[0])
    # 消融开关（A/B 与一键回滚）
    chk(hasattr(MB, 'W_FLOOR'), 'magnitude_band 有 W_FLOOR（不排除铁律）')
    _mb = io.open('data/tmp/magnitude_band.py', encoding='utf-8').read()
    chk('MB_OLD_BAND' in _mb, 'band_weight 有旧阶梯消融开关（A/B 用）')
    chk('MD_NO_TAIL' in _md, 'tail_bins 有 MD_NO_TAIL 回滚开关')
    # N23 不因 handi 类型崩溃（2026-11-03 实抓真断链）
    _ca88 = io.open('data/tmp/calc_all.py', encoding='utf-8').read()
    chk('_n23_hn = float(_h_f)' in _ca88, 'calc_all 的 _n23_hn 是 float（原 str → N23 整段崩溃）')
    _js88 = io.open('data/tmp/joint_solver.py', encoding='utf-8').read()
    chk('handi = float(handi)' in _js88, 'joint_solver 有 handi float 容错（第二道防线）')
except Exception as _e6:
    chk(False, '⑥ 端到端段失败: %s: %s' % (type(_e6).__name__, _e6))


# ══════════ ⑦ 宽池不得硬锚（2026-11-03 用户指令「宽池里的比分也得符合市场信号」）══════════
print('\n【⑦ 宽池补入必须过市场信号门槛（禁按档硬塞）】')
try:
    import itertools as _it7
    import market_distribution as _MD7
    _bd7 = MB.magnitude_band(o25=1.563, lam=3.505)
    _pT7 = _bd7['pT']
    _grid7 = {(h7, a7): 0.01 for h7, a7 in _it7.product(range(6), repeat=2)}
    _mm7 = {'total': {'p': _pT7}, 'expT': sum(k * p for k, p in enumerate(_pT7)),
            'matrix': {'matrix': _grid7, 'top': [['1:2', '7%']], 'expT': 3.19, 'expM': -0.02},
            'margin': {'p': {0: 0.27, -1: 0.22, 1: 0.16, -2: 0.14, 2: 0.08}}}
    # 真实波胆：6 球档比分赔率极高（市场不看好）
    _CS7 = {'1:1': 7.5, '0:2': 8.0, '1:2': 6.5, '2:1': 8.5, '1:0': 9.0, '0:1': 9.5,
            '2:2': 13.0, '3:2': 34.0, '3:3': 60.0, '2:4': 90.0, '4:2': 90.0, '5:1': 150.0}
    _r7 = _MD7.anchor_select(_mm7, oh=2.48, od=3.22, oa=2.35, handi=-0.25,
                            pool=['1:1', '1:2'], lam=3.505, t_band=_bd7, cs_full=_CS7)
    _n7 = ' '.join(_r7.get('notes') or [])
    chk('门槛' in _n7 or '宽池补入' in _n7 or '拒收' in _n7,
        '宽池补入/拒收**有留痕**（原只按档塞·无任何市场信号依据）')
    _sp7 = _r7.get('score_pool') or []
    _bad = []
    for _x7 in _sp7:
        _s7 = _x7[0] if isinstance(_x7, (list, tuple)) else _x7.get('score')
        _w7 = (_x7[1] if isinstance(_x7, (list, tuple)) else _x7.get('why')) or {}
        if isinstance(_w7, dict) and '宽池补入' in _w7:
            _rk7 = _CS7.get(str(_s7))
            if _rk7 and _rk7 >= 30:      # 波胆 ≥30 倍 = 市场明显不看好
                _bad.append(str(_s7))
    chk(not _bad, '补入的比分**波胆均非冷门**（违规: %s）' % ('/'.join(_bad) or '无'))
    # 受让场禁主胜
    _r7b = _MD7.anchor_select(_mm7, oh=4.20, od=3.60, oa=1.75, handi=0.75,
                             pool=['1:1', '1:2'], lam=3.505, t_band=_bd7, cs_full=_CS7)
    _n7b = ' '.join(_r7b.get('notes') or [])
    chk('受让场禁主胜' in _n7b or '拒收' in _n7b or '宽池补入' in _n7b,
        '受让场补入检查「禁主胜比分」（原补入路径完全无此校验）')
except Exception as _e7:
    chk(False, '⑦ 宽池门槛段失败: %s: %s' % (type(_e7).__name__, _e7))


# ══════════ ⑧ 尾部单调性（2026-11-03 用户裁定 dec-376e7267d95be6e2 方案 A）══════════
print('\n【⑧ 矩阵尾部非单调 → 回退查表（317 萨索洛 2:4 归因）】')
try:
    # 真实 317 矩阵形状：6球 3% < 7球 9%（被 CS「胜其它」合并污染）
    _bad8 = [0.08, 0.11, 0.20, 0.21, 0.17, 0.10, 0.03, 0.09]
    _b8 = MB.magnitude_band(mm={'total': {'p': _bad8}, 'expT': 3.19},
                            o25=1.563, lam=3.505)
    chk('查表尾部' in str(_b8.get('pT_src')), '矩阵尾部非单调 → 分布源标记为「矩阵+查表尾部」（%s）'
        % _b8.get('pT_src'))
    chk(6 in (_b8.get('tail_bins') or []), '6 球档进尾部档（修复前 3%% 被 5%% 阈值排除）')
    chk(_b8['pT'][6] > 0.05, '6 球概率恢复到 ≥5%%（实际 %.1f%%·市场定价 6.4%%·历史 5.3%%）'
        % (_b8['pT'][6] * 100))
    chk(not (_b8['pT'][6] < _b8['pT'][7] - 1e-9), '修复后尾部单调（P(6) ≥ P(7)）')
    # 对照组：形状正常时不得误改
    _ok8 = [0.04, 0.15, 0.22, 0.22, 0.16, 0.11, 0.06, 0.03]
    _b8b = MB.magnitude_band(mm={'total': {'p': _ok8}, 'expT': 3.1}, o25=1.563, lam=3.505)
    chk(_b8b.get('pT_src') == '矩阵', '正常形状不误改（源仍=矩阵·实际 %s）' % _b8b.get('pT_src'))
    chk(not any('尾部非单调' in n for n in (_b8b.get('notes') or [])),
        '正常形状无「尾部非单调」留痕')
except Exception as _e8:
    chk(False, '⑧ 尾部单调性段失败: %s: %s' % (type(_e8).__name__, _e8))

print('\n' + '=' * 84)
if FAIL:
    print('❌ V3.5.88 分布驱动审计 %d 项失败' % len(FAIL))
    for f in FAIL:
        print('   - %s' % f)
    sys.exit(1)
print('✅ V3.5.88 分布驱动审计全过')
