# -*- coding: utf-8 -*-
"""消费审计 v2：命中判定加「关键词白名单」，消除假阴性（2026-10-28）
v1 缺陷：tag 名（如「单押准入纪律」）在 raw 中写成「单押准入」→ 误判未消费
"""
import os, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# (正则, 名称, raw 中应出现的任一关键词)
MUST = [
    (r'⚠️', '通用警告', ['⚠️', '警告', '注意']),
    (r'提示[:：]', 'direction_full 提示', ['提示']),
    (r'小概率管理', 'O9 小概率管理', ['小概率管理', 'M1', 'M2', 'M3']),
    (r'H3\+', 'H3+ 净胜双出口', ['H3+', '净胜双出口']),
    (r'诱盘', '诱盘信号', ['诱盘']),
    (r'conflicts|建议锚|suggestion|必须替换', '锚冲突/建议', ['建议锚', '冲突', '替换']),
    (r'锚可信度|N08', '锚可信度', ['锚可信度', 'N08']),
    (r'单押准入', '单押准入', ['单押准入', '单押']),
    (r'R10-\d|R10判定层', 'R10判定层', ['R10', 'R10-1', 'R10-4', 'R10-5']),
    (r'R11', 'R11 零封', ['R11']),
    (r'禁单独作锚|尾桶挤压', 'P10 尾桶警告', ['尾桶', '禁单独作锚']),
    (r'分布跨度|禁锁单中心', '量级不确定度', ['分布跨度', '禁锁单中心', '宽候选', '宽池']),
    (r'低分出口|进球数细分|N26', 'N26 进球数细分', ['N26', '低分出口', '进球数细分']),
    # 🔴 2026-11-03 V3.5.90 厚尾三线索（观察期标注级·不动锚但必须被消费）
    (r'厚尾三线索', '厚尾三线索(V3.5.90)', ['厚尾', '溢价', 'O-TAIL']),
    (r'未匹配|缺输入|三态|无数据', '三态/未匹配', ['三态', '未匹配', '无数据', '缺输入', '不触发']),
    (r'双通道|Q[1-4] ', '双通道四象限', ['双通道', 'Q1', 'Q2', 'Q3', 'Q4']),
    (r'P0-[123]|Sharp|RLM|Steam', '资金盘 P0/P1', ['P0-1', 'P0-2', 'P0-3', 'P1-3', 'RLM', 'Steam', '资金盘']),
    (r'BSD|P0-a|P0-b|movement', 'BSD 增强层', ['BSD', 'movement', 'P0-a', 'P0-b']),
    (r'背离', '背离检测', ['背离', 'D1']),
    (r'L4 CBR|相似案例', 'L4 CBR 案例辅助', ['CBR', 'L4']),
    (r'欧国联|Nations', 'NL 子模型三态', ['非欧国联', '欧国联', 'NL']),
    (r'市场排序基线|S1 |S2 |S3 ', 'P5 市场排序基线', ['市场排序基线', 'S1', 'S2', 'S3']),
    (r'让球水位|上盘覆盖', '让球水位强度', ['让球水位', '上盘覆盖']),
    (r'期望三源|三源联动', 'N19 期望三源', ['三源', 'N19']),
]
TOK = re.compile(r'(N\d{2}[a-z]?|R\d{1,2}-\d|S\d{1,2}|P0-[123]|P1-\d|P2-\d|Q[1-4]|H3\+|M[1-5]|E\d{1,2})')


def audit(out_p, raw_p):
    out = open(out_p, encoding='utf-8', errors='ignore').read()
    raw = open(raw_p, encoding='utf-8', errors='ignore').read()
    items, seen = [], set()
    for i, ln in enumerate(out.split('\n'), 1):
        s = ln.strip()
        if not s or len(s) < 6:
            continue
        tag = keys = None
        for pat, name, ks in MUST:
            if re.search(pat, s):
                tag, keys = name, ks
                break
        if not tag:
            continue
        toks = set(TOK.findall(s))
        key = (tag, tuple(sorted(toks)[:3]))
        if key in seen:
            continue
        seen.add(key)
        hit = any(k in raw for k in keys) or any(t in raw for t in toks)
        items.append(dict(line=i, tag=tag, toks=sorted(toks), hit=hit, text=s[:140]))
    miss = [x for x in items if not x['hit']]
    print('=' * 78)
    print('消费审计: %-16s 必须 %d ｜ ✅%d ｜ 🔴%d' % (
        os.path.basename(out_p), len(items), len(items) - len(miss), len(miss)))
    print('=' * 78)
    for x in miss:
        print('  🔴 L%-4d [%-16s] %s' % (x['line'], x['tag'], x['text']))
    if not miss:
        print('  ✅ 全部已消费')
    return miss


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    if len(a) < 2:
        print('用法: audit_consumption.py <out.txt> <raw.md>'); sys.exit(1)
    sys.exit(1 if audit(a[0], a[1]) else 0)
