# -*- coding: utf-8 -*-
"""失效模式扫描 #3+#4：单位不匹配 + 队名匹配方向
   ③ 单位不匹配：同一变量既与「<10 常数」又与「>10 常数」比较 → 小数/百分数混用嫌疑
   ④ 队名匹配方向：find/match/lookup 类函数是否支持双向子串
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
UNIT_VARS = ('pct', 'prob', 'p_max', 'pmax', 'skew', 'rate', 'ratio', 'p_over',
             'p_home', 'p_away', 'p_draw', 'odds', 'odds_', '_sk', 'ph', 'pd', 'pa')

print('=' * 104)
print('③ 单位不匹配扫描（同一变量既比 <10 又比 >10 常数）')
print('=' * 104)

hits = []
for f in FILES:
    try:
        src = io.open(f, encoding='utf-8', errors='replace').read()
        tree = ast.parse(src)
    except Exception:
        continue
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # 收集 (变量名, 比较常数)
        cmps = {}
        for node in ast.walk(fn):
            if not isinstance(node, ast.Compare):
                continue
            # 左值变量名
            left = node.left
            name = None
            if isinstance(left, ast.Name):
                name = left.id
            elif isinstance(left, ast.Attribute):
                name = left.attr
            elif isinstance(left, ast.Call):
                # float(x) / int(x) → 看参数
                if left.args and isinstance(left.args[0], ast.Name):
                    name = left.args[0].id
            if not name:
                continue
            for c in node.comparators:
                # 常数（含一元负）
                val = None
                if isinstance(c, ast.Constant) and isinstance(c.value, (int, float)):
                    val = float(c.value)
                elif isinstance(c, ast.UnaryOp) and isinstance(c.op, ast.USub) \
                        and isinstance(c.operand, ast.Constant):
                    val = -float(c.operand.value)
                if val is not None:
                    cmps.setdefault(name, []).append(val)
        for name, vals in cmps.items():
            small = [v for v in vals if 0 < abs(v) <= 10]
            big = [v for v in vals if abs(v) >= 30]
            if small and big:
                # 只报含单位可疑关键词的变量
                low = name.lower()
                if any(k in low for k in UNIT_VARS):
                    hits.append((f, fn.name, fn.lineno, name, small[:2], big[:2]))

if hits:
    for f, fnname, ln, name, sm, bg in hits:
        print('  🔴 %-24s %-22s L%-5d 变量 %-10s 小数档 %s / 百分数档 %s'
              % (os.path.basename(f), fnname[:22], ln, name, sm, bg))
else:
    print('  ✅ 未发现同变量跨量级比较')

print()
print('=' * 104)
print('④ 队名匹配方向扫描（find/match/lookup 类函数）')
print('=' * 104)

NAME_FUNCS = []
for f in FILES:
    try:
        src = io.open(f, encoding='utf-8', errors='replace').read()
        tree = ast.parse(src)
    except Exception:
        continue
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if re.match(r'^(find|match|lookup|_lookup|_find|_match|resolve)', fn.name):
            body = ast.get_source_segment(src, fn) or ''
            has_fwd = bool(re.search(r'lower\(\)\s+in\s+|in\s+en\.lower\(\)|name\s+in\s+', body))
            has_rev = bool(re.search(r'en\.lower\(\)\s+in\s+|lower\(\)\s+in\s+low', body))
            has_cn = bool(re.search(r'cn2en|TEAM_ALIAS|中|中文', body))
            NAME_FUNCS.append((f, fn.name, fn.lineno, has_fwd, has_rev, has_cn))

print('%-26s %-24s %-6s %-6s %-6s %s' % ('文件', '函数', '行', '正向子串', '反向子串', '中文'))
print('-' * 104)
risk = []
for f, n, ln, fw, rv, cn in NAME_FUNCS:
    flag = ''
    if fw and not rv:
        flag = '🔴 只正向（全称会匹配不到）'
        risk.append((f, n, ln))
    print('%-26s %-24s %-6d %-6s %-6s %-6s %s'
          % (os.path.basename(f)[:26], n[:24], ln,
             '✅' if fw else '—', '✅' if rv else '—', '✅' if cn else '—', flag))

print()
if risk:
    print('🔴 需补反向子串的匹配函数（%d 个）:' % len(risk))
    for f, n, ln in risk:
        print('   %-24s %-22s L%d' % (os.path.basename(f), n, ln))
else:
    print('  ✅ 所有匹配函数均支持双向子串')
