# -*- coding: utf-8 -*-
"""V3.5.90 厚尾判据收敛 → O-TAIL 标注级观察期 端到端验证（case155 斯拉维亚vs朗斯·真实 2:3 五球）

评审修复（2026-11-03·用户实测 9 场）：
  ① 判据收敛为 premium（波胆溢价）≥2.0 单条——case155 2.1× 触发
  ② cs_tail_ratio / p5_ge / |E[M]| 触发全删（大球盘同义词·9 场 0/9）
  ③ O-TAIL 标注级（_TAIL_ACT=False·只打印不动作·观察 ≥20 场）
用途：证明「厚尾信号真实消费」——判据收敛后仍识别 case155（premium 线索），
      O-TAIL 进入标注级观察期（不再强制改锚）。
数据：case155 欧盘（raw md 实读）+ sla155.txt 竞彩波胆（真实文件）
"""
import os, sys, io, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from magnitude_band import magnitude_band, fmt, dist_line, tail_signal
import market_distribution as md
import joint_solver as js

def parse_cs(txt_path):
    """解析竞彩 txt 波胆（键值格式 比分=赔率·多时点·取最后时点）"""
    cs = {}
    lines = io.open(txt_path, encoding='utf-8').read().splitlines()
    # 定位比分段
    seg = None
    for i, ln in enumerate(lines):
        if '比分固定奖金' in ln:
            seg = i
            break
    if seg is None:
        return cs
    # 收集所有 比分=赔率 行（键值格式），用最后出现值
    for ln in lines[seg+1:]:
        s = ln.strip()
        if s.startswith('【'):
            break
        if '=' in s and ':' in s:
            k, v = s.split('=', 1)
            k = k.strip()
            try:
                fv = float(v.strip())
            except ValueError:
                continue
            if 1 < fv < 100:
                cs[k] = fv
    return cs

print('=' * 88)
print('V3.5.90 厚尾判据收敛 → O-TAIL 标注级观察期 端到端验证')
print('案例: case155 斯拉维亚vs朗斯（欧冠·真实 2:3 = 5 球）')
print('=' * 88)

# ── 1. 欧盘（raw md 实读: ML 主2.687/平3.548/客2.557 · O25=3.17 · 客受让 0/浅让）──
oh, od, oa = 2.687, 3.548, 2.557
ou_full = {'3.5': (3.17, 1.40)}   # O3.5? 实读是 O25=3.17 → 用 O2.5 单档近似
# case155 无多档 OU → 用竞彩总进球8档补全档
jc_goal8 = None

# ── 2. 竞彩波胆（sla155.txt 实读）──
cs_full = parse_cs(r'data\tmp\sla155.txt')
print('\n[1] 波胆解析: %d 档' % len(cs_full))
_tail_cs = [k for k, v in cs_full.items() if sum(int(x) for x in k.split(':')) >= 5]
if _tail_cs:
    print('    ≥5球谱系: %s' % ' '.join('%s=%.0f倍' % (k, cs_full[k]) for k in sorted(_tail_cs, key=lambda x: cs_full[x])[:6]))

# ── 3. 调 magnitude_band（含厚尾三线索）──
mm = None  # 无矩阵（欧盘不齐）→ 分布走查表/泊松
# case155 实读: O25=3.17（高进球盘）+ 竞彩总进球 3球3.40 最低 → 市场期望≈3 球
band = magnitude_band(mm=mm, p52=None, o25=3.17, u25=1.40,
                      lam=3.0, line=3.0, handi=0.0,
                      cs_full=cs_full)
print('\n[2] 量级分布:')
print('    ' + fmt(band))
print(dist_line(band))
tl = band.get('tail') or {}
print('\n[3] 🔴厚尾三线索(V3.5.90·判据收敛):')
print('    flag=%s ｜ P(≥5)=%s ｜ P(≥6)=%s ｜ 波胆尾部=%s ｜ 溢价=%s ｜ 净胜=%s'
      % (tl.get('flag'),
         ('%.0f%%' % (tl.get('p5_ge')*100)) if tl.get('p5_ge') is not None else 'n/a',
         ('%.0f%%' % (tl.get('p6_ge')*100)) if tl.get('p6_ge') is not None else 'n/a',
         ('%.0f%%' % (tl.get('cs_tail_ratio')*100)) if tl.get('cs_tail_ratio') is not None else 'n/a',
         ('%.1fx' % tl.get('tail_premium')) if tl.get('tail_premium') is not None else 'n/a',
         ('%+.1f' % tl.get('margin_m')) if tl.get('margin_m') is not None else 'n/a'))
for _n in (tl.get('notes') or []):
    print('    ' + _n)
_prem = tl.get('tail_premium')
assert _prem is not None and _prem >= 2.0, 'P0-2: case155 premium≥2.0 必须触发（实测 %.1fx）' % (_prem or 0)

# ── 4. 调 anchor_select（O-TAIL 锚覆盖）──
# 构造最小 mm：pT 用 band 的分布（走 V3.5.88 回退路径）+ margin 构造净胜
pT = band.get('pT')
# 净胜分布：让球浅（客受让~0）→ 净胜主峰 0
margin_p = {m: 0.0 for m in range(-3, 4)}
margin_p[0] = 0.4; margin_p[-1] = 0.25; margin_p[1] = 0.2
margin_p[-2] = 0.08; margin_p[2] = 0.05; margin_p[-3] = 0.02
mm_min = {
    'matrix': {
        'matrix': {(h, a): 0.0 for h in range(7) for a in range(7)},
        'top': [],
    },
    'total': {'p': pT, 'exp': sum(k*p for k, p in enumerate(pT))},
    'margin': {'p': margin_p, 'exp': sum(m*margin_p[m] for m in margin_p)},
}
# 矩阵最小形状：波胆反推近似（1/v 归一）
for (h, a) in mm_min['matrix']['matrix']:
    k = '%d:%d' % (h, a)
    v = cs_full.get(k)
    mm_min['matrix']['matrix'][(h, a)] = (1.0/v) if v else 1e-6
_s = sum(mm_min['matrix']['matrix'].values())
mm_min['matrix']['matrix'] = {k: v/_s for k, v in mm_min['matrix']['matrix'].items()}
mm_min['matrix']['top'] = sorted([(k, 100*v) for k, v in mm_min['matrix']['matrix'].items()],
                                 key=lambda z: -z[1])[:8]

pool = ['%d:%d' % (h, a) for h in range(7) for a in range(7)]
r = md.anchor_select(mm_min, oh=oh, od=od, oa=oa, handi=0.0,
                     cs_full=cs_full, pool=pool,
                     t_band=band,
                     lam=3.0, dir_first='客胜')
print('\n[4] 🔴anchor_select 锚输出（观察期 _TAIL_ACT=%s）:' % js._TAIL_ACT)
print('    主锚=%s ｜ 次锚=%s ｜ trust=%s'
      % (r.get('anchor_1st'), r.get('anchor_2nd'), r.get('trust')))
a1t = sum(int(x) for x in r['anchor_1st'].split(':')) if r.get('anchor_1st') else 0
a2t = sum(int(x) for x in r['anchor_2nd'].split(':')) if r.get('anchor_2nd') else 0
print('    主锚总球=%d ｜ 次锚总球=%d' % (a1t, a2t))
print('    厚尾覆盖语义: %s' % ('✅ 双锚天然含 ≥5球谱系' if (a1t >= 5 or a2t >= 5)
                                else '🔸 标注级观察期（_TAIL_ACT=False·不强制覆盖·仅打印建议）'))
print('\n    厚尾相关留痕:')
_obsv_hit = False
for _n in (r.get('big_notes') or []):
    if 'O-TAIL' in _n or '厚尾' in _n:
        print('      ' + _n)
        if '标注' in _n or '观察期' in _n:
            _obsv_hit = True
assert _obsv_hit or (a1t >= 5 or a2t >= 5), '观察期: 必须出现 O-TAIL 标注级提示或天然覆盖'
print('\n    真实赛果: 2:3（5球）→ 双锚命中=%s'
      % ('✅ 命中（5球被锚覆盖）' if (a1t >= 5 or a2t >= 5) else '🔸 观察期不动作·留待 _TAIL_ACT=True'))
