# -*- coding: utf-8 -*-
"""学习成果进入判定(2026-09-11·用户要求): 弱判定场(<45%)融合方向参与主方向判定"""
p = 'scripts/tmp/calc_all.py'
s = open(p, encoding='utf-8').read()
old = """                                elif abs(_dpp) > 5:
                                    if _mk_top < 45:
                                        print('    → 🔴融合与市场异向且差 %.1fpp>5pp·**市场判定为弱方向(最高仅%.1f%%)** → 建议将「%s」列为并列候选(tie-break·不反转主方向)' % (
                                            abs(_dpp), _mk_top, _lab[_fm]))
                                    else:
                                        print('    → ⚠️融合与市场异向且差 %.1fpp>5pp·市场强方向(%.1f%%): 仅建议置信度降1档(不反转方向·硬核判定优先)' % (
                                            abs(_dpp), _mk_top))"""
new = """                                elif abs(_dpp) > 5:
                                    if _mk_top < 45:
                                        # 🔴学习成果进入判定(2026-09-11用户要求·分档验证: <38% +2.43pp/<45% +0.99pp·强档0)
                                        print('    → 🔴🔴学习成果进入判定: 市场弱方向(最高%.1f%%<45%%)且融合异向差%.1fpp>5pp → **「%s」进入主方向判定（列为并列主方向）**（分档验证支撑: 弱档+0.99~2.43pp）' % (
                                            _mk_top, abs(_dpp), _lab[_fm]))
                                    else:
                                        print('    → ⚠️融合与市场异向且差 %.1fpp>5pp·市场强方向(%.1f%%≥45%): 仅置信度降1档(**不参与判定**·分档验证强档净优势=0)' % (
                                            abs(_dpp), _mk_top))
                                else:
                                    print('    → 融合与市场异向但差 %.1fpp≤5pp: 视作噪声·不调整' % abs(_dpp))
                            # 同向但市场弱 → 融合强化(信息增益)
                            if _mk and _w > 0 and _fm == _mm and _mk[_mm] * 100 < 45:
                                print('    → 🔴学习成果进入判定: 市场弱方向(%.1f%%<45%%)·融合同向强化 → **采纳融合概率作为方向判定依据之一**（分档验证弱档优势）' % (_mk[_mm] * 100))"""
assert old in s, '判定段未匹配'
s = s.replace(old, new, 1)
open(p, 'w', encoding='utf-8').write(s)
import py_compile; py_compile.compile(p, doraise=True)
print('学习成果进入判定 OK')
