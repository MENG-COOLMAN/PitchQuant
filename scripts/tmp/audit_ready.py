# -*- coding: utf-8 -*-
"""V3.5.90 就绪校验（2026-11-03·全面梳理）"""
import glob
import hashlib
import io
import os
import py_compile
import subprocess
import sys
sys.stdout.reconfigure(encoding='utf-8')

WS = os.getcwd()
CP = r'<HOME>\Desktop\足球预测模型'


def md5(p):
    h = hashlib.md5()
    with io.open(p, 'rb') as f:
        for b in iter(lambda: f.read(65536), b''):
            h.update(b)
    return h.hexdigest()


print('=' * 100)
print('V3.5.90 就绪校验')
print('=' * 100)

# ① 版本一致性
print('\n① 版本一致性')
import re
VER_RE = re.compile(r'V3\.5\.\d+(?![0-9])')
ag = io.open('AGENTS.md', encoding='utf-8').readline()
sk = io.open('.reasonix/skills/<REDACTED_SK>/SKILL.md', encoding='utf-8').read().splitlines()
tx = io.open('data/足球分析模型.txt', encoding='utf-8').read().splitlines()
ck = io.open('data/tmp/check_sync.py', encoding='utf-8').read()
exp = re.search(r"EXPECT_VER\s*=\s*'(V3\.5\.\d+)'", ck)
vers = {
    'AGENTS.md': (VER_RE.search(ag) or [None]) and VER_RE.search(ag).group(0),
    '主技能': next((VER_RE.search(x).group(0) for x in reversed(sk[:8]) if VER_RE.search(x)), None),
    'txt': next((VER_RE.search(x).group(0) for x in reversed(tx[:3]) if VER_RE.search(x)), None),
    'EXPECT_VER': exp.group(1) if exp else None,
}
for k, v in vers.items():
    print('   %-12s %s' % (k, v))
print('   → 一致:', '✅' if len(set(vers.values())) == 1 else '🔴 ' + str(vers))

# ② 关键脚本语法
print('\n② 关键脚本语法（全仓 data/tmp + 审计脚本）')
files = sorted(glob.glob('data/tmp/*.py'))
bad = []
for f in files:
    try:
        py_compile.compile(f, doraise=True)
    except Exception as e:
        bad.append((os.path.basename(f), str(e)[:80]))
print('   共 %d 个 py ｜ 失败 %d' % (len(files), len(bad)))
for f, e in bad:
    print('     🔴 %s: %s' % (f, e))
if not bad:
    print('   ✅ 全部语法通过')

# ③ 关键审计脚本在位
print('\n③ 关键审计/工具脚本在位')
NEED = ['audit_steps.py', 'audit_judgment.py', 'audit_chain.py', 'audit_semantic.py',
        'audit_consumption.py', 'audit_magnitude_band.py', 'audit_p52_chain.py',
        'audit_p8_vertical.py', 'audit_p12.py', 'audit_tail90.py', 'audit_fixtures.py',
        'audit_alignment.py', 'audit_contracts.py', 'pipeline.py', 'calc_all.py',
        'check_sync.py', 'output_checker.py', 'check_luopan.py', 'europe_check.py',
        'magnitude_band.py', 'market_distribution.py', 'joint_solver.py', 'time_guard.py']
miss = [f for f in NEED if not os.path.exists(os.path.join('data', 'tmp', f))]
print('   需 %d 个 ｜ 缺 %d' % (len(NEED), len(miss)))
if miss:
    print('   🔴 缺:', ', '.join(miss))
else:
    print('   ✅ 全在')

# ④ 双端关键文件一致性
print('\n④ 双端关键文件 md5')
KEY = ['data/tmp/pipeline.py', 'data/tmp/calc_all.py', 'data/tmp/check_sync.py',
       'data/tmp/output_checker.py', 'data/tmp/audit_consumption.py', 'data/tmp/audit_tail90.py',
       'data/tmp/magnitude_band.py', 'data/tmp/joint_solver.py', 'data/tmp/market_distribution.py',
       'data/tmp/europe_check.py', 'AGENTS.md', '.reasonix/skills/<REDACTED_SK>/SKILL.md']
diff = []
for rel in KEY:
    a = os.path.join(WS, rel.replace('/', os.sep))
    b = os.path.join(CP, rel.replace('/', os.sep))
    if not os.path.exists(b):
        diff.append((rel, '副本缺'))
        continue
    if md5(a) != md5(b):
        diff.append((rel, 'md5 不一致'))
print('   比对 %d 个 ｜ 差异 %d' % (len(KEY), len(diff)))
for rel, why in diff:
    print('     🔴 %s: %s' % (rel, why))
if not diff:
    print('   ✅ 全部一致')

# ⑤ txt 三处
print('\n⑤ txt 三处 md5')
t = [os.path.join(WS, 'data', '足球分析模型.txt'),
     os.path.join(CP, 'data', '足球分析模型.txt'),
     r'<HOME>\Desktop\足球分析模型.txt']
ms = [md5(p) if os.path.exists(p) else 'MISSING' for p in t]
print('   ', [m[:12] for m in ms])
print('   → 一致:', '✅' if len(set(ms)) == 1 else '🔴')

# ⑥ 案例库/raw 统计
print('\n⑥ 案例库统计')
csv = 'data/case-library/实战案例.csv'
n_case = 0
if os.path.exists(csv):
    import csv as _csv
    n_case = len(list(_csv.DictReader(io.open(csv, encoding='utf-8-sig'))))
n_raw = len(glob.glob('data/case-library/raw/case*.md'))
print('   CSV 场次: %d ｜ raw 篇数: %d' % (n_case, n_raw))
print('   测试场残留(case90x):', [os.path.basename(p) for p in glob.glob('data/case-library/raw/case90[0-9]*.md')] or '无')

# ⑦ 数据文件在位
print('\n⑦ 核心数据文件')
DATA = ['data/Matches.csv', 'data/tmp/homeaway_table.json', 'data/tmp/odds_table.json',
        'data/tmp/score_depth_table.json', 'data/tmp/goal_bins_table.json',
        'data/tmp/draw_table.json', 'data/tmp/quadrant_table.json',
        'data/tmp/deep_anchor_table.json', 'data/tmp/team_attack_defense.json',
        'data/tmp/ucl_calibration.json', 'data/tmp/goal_count_table.json',
        'data/tmp/cn2en_extra.json', 'data/europe/欧战全量.csv']
for d in DATA:
    ok = os.path.exists(d)
    sz = ('%.1f KB' % (os.path.getsize(d) / 1024.0)) if ok else '—'
    print('   %s %-40s %s' % ('✅' if ok else '🔴', d, sz))
