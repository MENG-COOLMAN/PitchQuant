# -*- coding: utf-8 -*-
"""死代码扫描 v4（最终）：+ import 检测 + DEPRECATED 豁免"""
import ast
import glob
import io
import os
import re
import sys

os.chdir(r'<HOME>\AppData\Roaming\reasonix\global-workspace')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

FILES = sorted(glob.glob('data/tmp/*.py') + glob.glob('data/online_learning/*.py'))

ALLOWLIST = {'main', 'cli', '__init__', '__enter__', '__exit__', '__repr__', '__str__',
             'adjust_by_team_half', 'shin_devig', 'score_pool_with_big',
             # 🔴嵌套函数（定义时带 _ 前缀·调用时不带）
             '_books', '_inj'}

defs = {}
called = set()
src_all = {}

for f in FILES:
    try:
        s = io.open(f, encoding='utf-8', errors='replace').read()
        src_all[f] = s
        tree = ast.parse(s)
    except Exception:
        continue
    # 🔴P40-5: 识别**嵌套函数**（父函数内定义 → 随父调用·不算死代码）
    _nested = set()
    for _p in ast.walk(tree):
        if isinstance(_p, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for _c in _p.body:
                for _n2 in ast.walk(_c):
                    if isinstance(_n2, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        _nested.add(_n2.name)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in _nested:
                called.add(node.name)      # 嵌套 → 视为可达
            defs[(f, node.name)] = (node.lineno, ast.get_docstring(node) or '',
                                    bool(node.decorator_list))
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                called.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                called.add(fn.attr)
        # from X import name → 视为调用
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                called.add(a.name)
                called.add(a.asname or a.name)
        if isinstance(node, ast.Import):
            for a in node.names:
                called.add(a.name.split('.')[-1])
        # set_defaults(func=X) / getattr(obj,'X')
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ('set_defaults', 'getattr'):
                for kw in (node.keywords or []):
                    if isinstance(kw.value, ast.Name):
                        called.add(kw.value.id)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'getattr':
            for a in (node.args or [])[1:]:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    called.add(a.value)

DEF_LINE = re.compile(r'^\s*(async\s+)?def\s+([A-Za-z_]\w{1,60})\s*\(')
for f, s in src_all.items():
    for line in s.split('\n'):
        if DEF_LINE.match(line) or line.strip().startswith('#'):
            continue
        for m in re.finditer(r'\b([A-Za-z_]\w{1,60})\s*\(', line):
            called.add(m.group(1))
        for m in re.finditer(r'func\s*=\s*([A-Za-z_]\w{1,60})', line):
            called.add(m.group(1))

dead = []
for (f, name), (ln, doc, has_dec) in sorted(defs.items()):
    if name in ALLOWLIST or name.startswith('_test'):
        continue
    if name in called:
        continue
    # DEPRECATED 标记 → 已明确废弃·不算问题
    ctx = src_all.get(f, '')
    idx = ctx.find('def %s(' % name)
    prev = ctx[max(0, idx - 400):idx] if idx > 0 else ''
    if 'DEPRECATED' in prev or 'DEPRECATED' in doc:
        continue
    dead.append((f, name, ln))

CRIT = ('calc_all.py', 'calc_v3572.py', 'joint_solver.py', 'market_distribution.py',
        'calc_match.py', 'live_score_engine.py', 'pipeline.py', 'prestep_fetch.py',
        'snapshot_save.py', 'team_attack_defense.py', 'confidence_engine.py',
        'calc_poisson.py', 'big_pool_policy.py', 'market_inputs.py')
crit = [(f, n, l) for f, n, l in dead if os.path.basename(f) in CRIT]

print('=' * 100)
print('死代码 v4（含 import + DEPRECATED 豁免）：定义 %d ｜ 零调用 %d ｜ 主链 %d'
      % (len(defs), len(dead), len(crit)))
print('=' * 100)
if crit:
    print('\n🔴 主链（需逐个核实）:')
    for f, n, l in crit:
        print('  %-24s L%-5d %s' % (os.path.basename(f), l, n))
else:
    print('  ✅ 主链无未登记死代码')
print('\n非主链（%d）:' % (len(dead) - len(crit)))
for f, n, l in dead:
    if os.path.basename(f) not in CRIT:
        print('  %-26s L%-5d %s' % (os.path.basename(f), l, n))
