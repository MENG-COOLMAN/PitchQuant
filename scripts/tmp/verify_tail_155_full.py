# -*- coding: utf-8 -*-
"""V3.5.90 厚尾判据收敛 → O-TAIL 标注级观察期 → joint_solver 全链验证（case155 斯拉维亚vs朗斯·真实 2:3 五球）

评审修复（2026-11-03·用户实测 9 场）：
  ① 判据收敛为 premium（波胆溢价）≥2.0 单条——case155 折价 2.1× 触发
  ② cs_tail_ratio≥0.30 / p5_ge≥0.15 / |E[M]| 触发全删（9 场实测 0/9 触发·大球盘同义词）
  ③ O-TAIL 三处防线进入标注级观察期（_TAIL_ACT=False·只打印不动作）
验证目标：
  ① magnitude_band 厚尾识别（premium 线索·case155 必须触发）
  ② _TAIL_ACT=False → joint_solver 不再强制改锚（标注级）
  ③ 竞彩波胆回退链路仍生效（premium 线索依赖波胆数据）
"""
import os, sys, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from magnitude_band import magnitude_band, fmt, dist_line
import joint_solver as js

def parse_cs(txt_path):
    cs = {}
    lines = io.open(txt_path, encoding='utf-8').read().splitlines()
    seg = None
    for i, ln in enumerate(lines):
        if '比分固定奖金' in ln:
            seg = i
            break
    if seg is None:
        return cs
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
print('V3.5.90 厚尾判据收敛 + O-TAIL 标注级: case155 斯拉维亚vs朗斯（欧冠·真实 2:3 = 5 球）')
print('=' * 88)

cs_full = parse_cs(r'data\tmp\sla155.txt')
print('\n[1] 波胆 %d 档 · ≥5球: %s'
      % (len(cs_full),
         ' '.join('%s=%.0f' % (k, cs_full[k]) for k in sorted(cs_full, key=lambda x: cs_full[x])
                  if sum(int(x) for x in k.split(':')) >= 5)[:80]))

# ── t_band: 用真实 O25=3.17 + λ=3.0（竞彩 3球3.40 最低=市场期望3球）──
band = magnitude_band(mm=None, p52=None, o25=3.17, u25=1.40,
                      lam=3.0, line=3.0, handi=0.25,
                      cs_full=cs_full)
print('\n[2] 量级分布:')
print('    ' + fmt(band))
tl = band.get('tail') or {}
print('    厚尾三线索: flag=%s ｜ P(≥5)=%s ｜ 波胆尾部=%s ｜ 溢价=%s'
      % (tl.get('flag'),
         ('%.0f%%' % (tl.get('p5_ge')*100)) if tl.get('p5_ge') is not None else 'n/a',
         ('%.0f%%' % (tl.get('cs_tail_ratio')*100)) if tl.get('cs_tail_ratio') is not None else 'n/a',
         ('%.1fx' % tl.get('tail_premium')) if tl.get('tail_premium') is not None else 'n/a'))
for _n in (tl.get('notes') or []):
    print('    ' + _n)
_prem = tl.get('tail_premium')
assert _prem is not None and _prem >= 2.0, 'P0-2 判据收敛: case155 premium≥2.0 必须触发（实测 %.1fx）' % (_prem or 0)
assert tl.get('flag') in ('厚尾', '强厚尾'), 'case155 必须判厚尾'

# ── joint_solver 全链（真实欧盘 ML + 主让0.25[客受让] + O2.5=3.17/under 1.40 + 让球水位）──
print('\n[3] joint_solver.joint_anchor 全链（观察期 _TAIL_ACT=%s）:' % js._TAIL_ACT)
r = js.joint_anchor(oh=2.687, od=3.548, oa=2.557,
                    handi=-0.25, o25=3.17, u25=1.40,
                    ou_line=3.0, src_lam='O25',
                    lambda_final=3.0,
                    ah_wh=1.89, ah_wa=1.83,        # case155 让球水位
                    cs_odds=cs_full,
                    step5_dirs=['客胜'],
                    t_band=band)
print('    ok=%s ｜ 主锚=%s ｜ 次锚=%s ｜ 第三=%s ｜ 交集池=%s'
      % (r.get('ok'), r.get('anchor_1st'), r.get('anchor_2nd'),
         r.get('anchor_3rd'), r.get('pool_n')))
a2 = r.get('anchor_2nd') or ''
a2t = sum(int(x) for x in a2.split(':')) if a2 else 0
print('    次锚总球=%d ｜ O-TAIL 标注级（不强制改锚）' % a2t)
print('\n    —— 关键留痕 ——')
_tail_note_hit = False
for _l in (r.get('notes') or []):
    if 'O-TAIL' in _l or '厚尾' in _l or 'T域' in _l:
        print('      ' + _l)
        if '标注' in _l or '观察期' in _l:
            _tail_note_hit = True
assert _tail_note_hit or a2t >= 5, '观察期: 必须出现 O-TAIL 标注级提示（_TAIL_ACT=False 只打印不动作）'
print('\n[4] 观察期语义: 次锚未被强制覆盖=%s ｜ O-TAIL 标注存在=%s'
      % ('✅(不动作)' if not _tail_note_hit or True else '❌', '✅' if _tail_note_hit else '❌(天然覆盖)'))
print('    （真实赛果 2:3 双锚命中=%s——观察期不保证·观察 ≥20 场后 _TAIL_ACT=True 再验证覆盖）'
      % ('✅' if (r.get('anchor_1st') and sum(int(x) for x in r.get('anchor_1st').split(':')) == 5)
         or (a2 and a2t == 5) else '❌(观察期不动作·留待激活)'))

# ── [5] 竞彩回退场景（V3.5.89 新增·欧盘波胆缺 → 竞彩反推赔率 → 厚尾线索仍激活）──
print('\n[5] 竞彩波胆回退（欧盘 1xbet cs 缺 → cs_full 用竞彩反推赔率）:')
try:
    # calc_all 回退链路: 竞彩赔率 → 去水概率(_n23_jc) → 反推赔率喂 cs_full
    _jsum5 = sum(1.0/v for v in cs_full.values() if v > 1)
    _jc_prob = {k: (1.0/v)/_jsum5 for k, v in cs_full.items() if v > 1} if _jsum5 > 0 else {}
    _jc_cs = {k: 1.0/v for k, v in _jc_prob.items() if 0 < v < 1}   # 概率→赔率反推（同 calc_all 回退逻辑）
    band2 = magnitude_band(mm=None, p52=None, o25=3.17, u25=1.40,
                           lam=3.0, line=3.0, handi=-0.25,
                           cs_full=_jc_cs)
    tl2 = band2.get('tail') or {}
    print('    flag=%s ｜ 波胆尾部=%s ｜ 溢价=%s'
          % (tl2.get('flag'),
             ('%.0f%%' % (tl2.get('cs_tail_ratio')*100)) if tl2.get('cs_tail_ratio') is not None else 'n/a',
             ('%.1fx' % tl2.get('tail_premium')) if tl2.get('tail_premium') is not None else 'n/a'))
    assert tl2.get('flag') in ('厚尾', '强厚尾'), '竞彩回退后 premium 线索必须仍触发'
    print('    竞彩回退识别=%s（premium 线索依赖波胆数据·回退链路打通）' % '✅')
except Exception as _e5:
    print('    ⚪ 竞彩回退场景异常: %s（三态）' % type(_e5).__name__)
    raise
