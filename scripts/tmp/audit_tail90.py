# -*- coding: utf-8 -*-
"""V3.5.90 厚尾真消费消融 v2（2026-11-03）
关键：必须构造 premium≥2.0 才能测出 _TAIL_ACT 激活路径
"""
import sys
sys.path.insert(0, 'data/tmp')
sys.stdout.reconfigure(encoding='utf-8')

import magnitude_band as MB
import joint_solver as JS

BASE = {'0:0': 9.0, '1:0': 8.0, '0:1': 9.5, '1:1': 7.0, '2:0': 12.0, '0:2': 14.0,
        '2:1': 10.0, '1:2': 11.0, '2:2': 18.0, '3:0': 26.0, '0:3': 30.0, '3:1': 24.0,
        '1:3': 28.0, '3:2': 32.0, '2:3': 23.0, '4:0': 45.0, '0:4': 55.0, '4:1': 50.0,
        '1:4': 60.0, '3:3': 60.0, '4:2': 80.0, '2:4': 90.0}


def scale_tail(cs, k):
    out = {}
    for key, v in cs.items():
        t = sum(int(x) for x in key.split(':'))
        out[key] = round(v * k, 2) if t >= 5 else v
    return out


def mk(cs):
    return MB.magnitude_band(mm=None, p52=None, o25=3.17, u25=1.40,
                             lam=3.0, line=3.0, handi=0.25, cs_full=cs)


def tot(s):
    try:
        return sum(int(x) for x in str(s).split(':'))
    except Exception:
        return 0


print('=' * 94)
print('V3.5.90 厚尾真消费消融 v2')
print('=' * 94)

# 找能判厚尾的构造（逐步压低 ≥5 球档赔率）
print('\n[0] 构造扫描（目标 premium ≥ 2.0 = 判厚尾）')
cs_hit = None
for k in (1.0, 0.85, 0.75, 0.65, 0.55, 0.45):
    cs = scale_tail(BASE, k)
    b = mk(cs)
    t = b.get('tail') or {}
    prem = t.get('tail_premium')
    print('    ≥5球档赔率×%.2f → cs尾部=%s P(≥5)=%s 溢价=%s flag=%s'
          % (k, ('%.0f%%' % (t['cs_tail_ratio'] * 100)) if t.get('cs_tail_ratio') else 'n/a',
             ('%.0f%%' % (t['p5_ge'] * 100)) if t.get('p5_ge') else 'n/a',
             ('%.2fx' % prem) if prem else 'n/a', t.get('flag')))
    if prem and prem >= 2.0 and cs_hit is None:
        cs_hit = cs
        band_hit = b

if cs_hit is None:
    print('    🔴 无法构造 premium≥2.0（判据可能过严或 p5_ge 口径问题）')
    sys.exit(1)

t_hit = band_hit.get('tail') or {}
print('\n[1] 厚尾场判据: flag=%s ｜ 溢价=%.2fx ｜ cs尾部=%.0f%% ｜ P(≥5)=%.0f%%'
      % (t_hit.get('flag'), t_hit['tail_premium'],
         t_hit['cs_tail_ratio'] * 100, t_hit['p5_ge'] * 100))

# 诚实降级
b_none = mk(None)
t_none = b_none.get('tail') or {}
print('[2] 无波胆: flag=%s ｜ 溢价=%s → %s'
      % (t_none.get('flag'), t_none.get('tail_premium'),
         '✅ 诚实降级' if t_none.get('flag') == '正常' and t_none.get('tail_premium') is None else '🔴'))

# ── A/B ──
print('\n[3] _TAIL_ACT A/B（真消费硬判据）')
ARGS = dict(oh=2.687, od=3.548, oa=2.557, handi=-0.25, o25=3.17, u25=1.40,
            ou_line=3.0, src_lam='O25', lambda_final=3.0,
            ah_wh=1.89, ah_wa=1.83, cs_odds=cs_hit,
            step5_dirs=['客胜'], t_band=band_hit)

JS._TAIL_ACT = False
rA = JS.joint_anchor(**ARGS)
a1A, a2A = rA.get('anchor_1st'), rA.get('anchor_2nd')
print('    A False(观察期): 主锚=%s(%d球) 次锚=%s(%d球) 池=%s'
      % (a1A, tot(a1A), a2A, tot(a2A), rA.get('pool_n')))

JS._TAIL_ACT = True
rB = JS.joint_anchor(**ARGS)
a1B, a2B = rB.get('anchor_1st'), rB.get('anchor_2nd')
print('    B True (激活态): 主锚=%s(%d球) 次锚=%s(%d球) 池=%s'
      % (a1B, tot(a1B), a2B, tot(a2B), rB.get('pool_n')))
JS._TAIL_ACT = False

changed = (a1A, a2A) != (a1B, a2B)
print('    → 锚改变:', '✅ 真消费' if changed else '🔴 完全相同（激活路径死代码）')
print('    → 激活后次锚 ≥5 球:', '✅' if tot(a2B) >= 5 else '🔴 (%s=%d球)' % (a2B, tot(a2B)))

# 留痕对比
print('\n    A 留痕(O-TAIL):')
for l in (rA.get('notes') or []):
    if 'O-TAIL' in l or '厚尾' in l:
        print('      A| ' + l[:110])
print('    B 留痕(O-TAIL):')
for l in (rB.get('notes') or []):
    if 'O-TAIL' in l or '厚尾' in l:
        print('      B| ' + l[:110])

# ── 闸门 ──
print('\n[4] 闸门双向')
import output_checker as OC
m_with = [x for x in OC.check_output('## 分析\n🔴🔴厚尾三线索(V3.5.90): 正常 ｜ 溢价=1.0×\n') if 'TAIL90' in str(x)]
m_wo = [x for x in OC.check_output('## 分析\n（无厚尾块）\n') if 'TAIL90' in str(x)]
print('    有厚尾块报缺=%d（应0）｜ 无厚尾块报缺=%d（应≥1）→ %s'
      % (len(m_with), len(m_wo), '✅' if len(m_with) == 0 and len(m_wo) >= 1 else '🔴'))

print('\n' + '=' * 94)
print('汇总: 厚尾识别 ✅(%.1fx) ｜ 降级 %s ｜ A/B %s ｜ 闸门 %s'
      % (t_hit['tail_premium'],
         '✅' if t_none.get('flag') == '正常' else '🔴',
         '✅' if changed else '🔴',
         '✅' if len(m_with) == 0 and len(m_wo) >= 1 else '🔴'))
