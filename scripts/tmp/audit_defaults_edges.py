# -*- coding: utf-8 -*-
"""失效模式扫描 #5+#6：默认参数路径 + 边界值
   ⑤ 默认参数：`def f(x=None)` 内部直接 `x.attr` / `x[0]` 而无 None 检查 → 潜在 AttributeError/TypeError
   ⑥ 边界值：同一变量既有 `<` 又有 `<=`（或 `>`/`>=`）且常数相同 → 边界不一致嫌疑
"""
import ast
import glob
import io
import os
import re
import sys

os.chdir(r'<HOME>\AppData\Roaming\reasonix\global-workspace')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

FILES = sorted(glob.glob('data/tmp/*.py') + glob.glob('data/online_learning/*.py'))

print('=' * 104)
print('⑤ 默认参数（None）未防护的直接属性/下标访问')
print('=' * 104)

risks = []
for f in FILES:
    try:
        src = io.open(f, encoding='utf-8', errors='replace').read()
        tree = ast.parse(src)
    except Exception:
        continue
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # 默认值 None 的参数
        none_params = set()
        args = fn.args
        defaults = list(args.defaults or [])
        all_params = list(args.args or []) + list(args.kwonlyargs or [])
        # 默认值对应最后 N 个位置参数
        pos = list(args.args or [])
        nd = len(defaults)
        for i, d in enumerate(defaults):
            if isinstance(d, ast.Constant) and d.value is None:
                idx = len(pos) - nd + i
                if 0 <= idx < len(pos):
                    none_params.add(pos[idx].arg)
        for kw, d in zip((args.kwonlyargs or []), (args.kw_defaults or [])):
            if isinstance(d, ast.Constant) and d.value is None:
                none_params.add(kw.arg)
        if not none_params:
            continue
        # 该参数是否被 None 检查过
        body_src = ast.get_source_segment(src, fn) or ''
        for p in none_params:
            guarded = bool(re.search(
                r'(if\s+.*\b%s\b\s+is\s+(not\s+)?None'
                r'|\b%s\b\s+and\s|\b%s\b\s+or\s|not\s+%s\b'
                r'|isinstance\(\s*%s\s*,'
                r'|if\s+%s\s*:'
                r'|%s\s+or\s+\{\}'
                r'|\(\s*%s\s+or\s)' % (p, p, p, p, p, p, p, p), body_src))
            if guarded:
                continue
            # 找直接属性访问 / 下标
            bad = re.search(r'\b%s\s*\.\s*\w' % p, body_src) or \
                  re.search(r'\b%s\s*\[' % p, body_src)
            if bad:
                risks.append((f, fn.name, fn.lineno, p, bad.group(0)[:20]))

if risks:
    for f, fnname, ln, p, pat in risks:
        print('  🔴 %-24s %-20s L%-5d 参数 %-12s 直接访问 %s'
              % (os.path.basename(f), fnname[:20], ln, p, pat))
else:
    print('  ✅ 未发现「默认 None 且未防护」的直接访问')

print()
print('=' * 104)
print('⑥ 边界值一致性（同变量同常数的 < 与 <= 混用）')
print('=' * 104)

edge = []
for f in FILES:
    try:
        src = io.open(f, encoding='utf-8', errors='replace').read()
        tree = ast.parse(src)
    except Exception:
        continue
    ops_seen = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        left = node.left
        name = left.id if isinstance(left, ast.Name) else (
            left.attr if isinstance(left, ast.Attribute) else None)
        if not name:
            continue
        for op, c in zip(node.ops, node.comparators):
            if isinstance(c, ast.Constant) and isinstance(c.value, (int, float)):
                t = type(op).__name__
                key = (name, float(c.value))
                ops_seen.setdefault(key, set()).add(t)
    for (name, const), ts in ops_seen.items():
        if ('Lt' in ts and 'LtE' in ts) or ('Gt' in ts and 'GtE' in ts):
            edge.append((f, name, const, ts))

if edge:
    for f, name, const, ts in edge[:20]:
        print('  ⚠️ %-24s 变量 %-12s 常数 %-6g 运算符 %s'
              % (os.path.basename(f), name, const, ts))
else:
    print('  ✅ 未发现同常数边界混用')

print()
print('=' * 104)
print('结论')
print('=' * 104)
print('  ⑤ 默认参数风险: %d 处' % len(risks))
print('  ⑥ 边界值混用: %d 处（多为不同业务场景·需人工判读）' % len(edge))
