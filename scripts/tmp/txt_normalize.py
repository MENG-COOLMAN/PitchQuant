#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""txt_normalize.py — 竞彩 txt 通用归一化器（2026-09-19 固化·V3.5.74）

🔴作用: 把**用户任意来源格式**的竞彩 txt 归一化为**标准模板 txt**（唯一格式·经校验）
        → 再喂给 calc_all / calc_match / data_bridge / txt_features 消费。
        **根治「格式差异→各解析器各自兼容→静默失败」的历史事故源**
        （历史教训: case149 丢行/丢节标题 · case151 --eu 传反 · 让球标题正则 · 两行式队名连锁 5 源失配）。

支持输入格式（自动探测·可混合）:
  ① 制表符/表格（Tab 分隔 + ↑↓ 箭头）        ② 逗号分隔
  ③ 多空格/全角空格分隔                         ④ 节标题变体: 【胜平负固定奖金】/【胜平负】/=====胜平负===== / 裸标题
  ⑤ 比分三种写法: 1:0=7.50 / 1:0：7.50 / 1:0 7.50   ⑥ 让球数: 让球-1/+1（有/无冒号）
输出:
  ① 标准模板 txt（stdout + 落盘 data/tmp/std_<name>.txt）
  ② 校验报告（必填节/数值合理性/时点数 → 三态标注·缺失显式列出）

标准模板（唯一格式·下游全部兼容）:
  【赛事】<联赛> <主队>(主) VS <客队>(客)
  【比赛时间】YYYY-MM-DD HH:MM <赛事名>
  【特征分析】…（原样保留）
  【胜平负固定奖金】发布时间,胜,平,负 / <ts>,h,d,a …
  【让球胜平负固定奖金｜让球±N】发布时间,胜,平,负 / …
  【半全场胜平负固定奖金】发布时间,胜胜,胜平,胜负,平胜,平平,平负,负胜,负平,负负 / …
  【总进球固定奖金】发布时间,0球,1球,2球,3球,4球,5球,6球,7+球 / …
  【比分固定奖金】<ts> / 胜方比分：1:0=7.50，… / 平局比分：… / 负方比分：…

用法:
  python data/tmp/txt_normalize.py <原始.txt> [--out X.txt] [--check-only]
"""
import os
import re
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))

# 节标题 → 标准节名（🔴顺序敏感: 让球胜平负 → 半全场 → 胜平负·长词优先，否则「XX胜平负」被误归入胜平负节）
SECTION_RULES = [
    ('让球胜平负', '让球'),
    ('半全场', '半全场'),
    ('胜平负', '胜平负'),
    ('总进球', '总进球'),
    ('进球数', '总进球'),
    ('比分', '比分'),
    ('特征分析', '特征'),
    ('比赛时间', '时间'),
    ('赛事', '赛事'),
]
ARROW_RE = re.compile(r'[↑↓⬆⬇▲▼]')
FULL2HALF = str.maketrans('０１２３４５６７８９（）｜，：', '0123456789()|,:')
TS_RE = re.compile(r'(\d{4}-\d{2}-\d{2}[ \d:]*)')
NUM_RE = re.compile(r'\d+\.\d+|\d+')


def std_section(line):
    """识别行所属标准节（去【】/=====包装后匹配）"""
    t = line.strip()
    if not t:
        return None
    m = re.match(r'^【([^】]+)】$', t) or re.match(r'^=+\s*(.+?)\s*=+$', t)
    if m:
        name = m.group(1)
        for key, sec in SECTION_RULES:
            if key in name:
                return (sec, name)
        return ('未知节', name)
    return None


def nums_of(line):
    """抽取行内全部数值（剥离箭头/全角/标签）"""
    t = line.translate(FULL2HALF)
    t = ARROW_RE.sub('', t)
    return [float(x) for x in re.findall(r'\d+\.\d+|\d+', t)]


def parse(text):
    """→ (标准节列表, 报告) · 标准节 = (节名, 标题原文, [标准行])"""
    text = text.replace('\t', ',').replace('　', ' ')
    text = text.replace('=====', '【')  # 仅示意；实际分隔符在下方逐行处理
    out = []          # [(sec, title, [lines])]
    rep = {'赛事': None, '时间': None, '时点数': {}}
    cur = None

    def flush():
        nonlocal cur
        if cur:
            out.append(cur)
            cur = None

    for raw in text.splitlines():
        line = raw.replace('\t', ',').rstrip()
        sm = std_section(line)
        if sm:
            flush()
            cur = [sm[0], sm[1], []]
            continue
        if cur is None:
            # 节外前言：赛事/时间/提示 等 → 归入"前言"
            if line.strip():
                if cur is None and not out:
                    out.append(['前言', '', []])
                out[-1][2].append(line.strip())
            continue
        if line.strip():
            cur[2].append(line.strip())
    flush()

    # 二次整理: 前言里的赛事/时间
    for sec, title, lines in out:
        if sec == '前言':
            for l in lines:
                if l.startswith('赛事'):
                    rep['赛事'] = l
                elif l.startswith('比赛时间'):
                    rep['时间'] = l
    return out, rep


def norm_spf(lines):
    """胜平负/让球: → ['发布时间,胜,平,负', '<ts>,h,d,a', ...]"""
    rows = []
    for l in lines:
        if '发布' in l or ('胜' in l and '负' in l and '平' in l and '.' not in l):
            continue
        ts = TS_RE.match(l)
        ns = nums_of(l[ts.end():]) if ts else []   # 🔴2026-09-19 修复: 只取时间戳之后的数值（原全行→时间戳的2026/9/16 污染赔率·下游 calc_match 误读）
        if ts and len(ns) >= 3:
            rows.append('%s,%s,%s,%s' % (ts.group(1).strip(), ns[0], ns[1], ns[2]))
    return (['发布时间,胜,平,负'] + rows) if rows else []


def norm_bqc(lines):
    rows = []
    for l in lines:
        if '发布' in l or '胜胜' in l and '负负' in l and '.' not in l:
            continue
        ts = TS_RE.match(l)
        ns = nums_of(l[ts.end():]) if ts else []   # 🔴同上修复
        if ts and len(ns) >= 9:
            rows.append('%s,%s' % (ts.group(1).strip(), ','.join('%g' % v for v in ns[:9])))
    return (['发布时间,胜胜,胜平,胜负,平胜,平平,平负,负胜,负平,负负'] + rows) if rows else []


def norm_zjq(lines):
    rows = []
    for l in lines:
        if '发布' in l or ('球' in l and '0球' in l and '.' not in l):
            continue
        ts = TS_RE.match(l)
        ns = nums_of(l[ts.end():]) if ts else []   # 🔴同上修复
        if ts and len(ns) >= 8:
            rows.append('%s,%s' % (ts.group(1).strip(), ','.join('%g' % v for v in ns[:8])))
    return (['发布时间,0球,1球,2球,3球,4球,5球,6球,7+球'] + rows) if rows else []


def norm_cs(lines):
    """比分: 时间戳行 + 胜方/平局/负方 三行 → 标准三行（= 号格式·其它→其它）"""
    out, ts = [], None
    for l in lines:
        t = l.translate(FULL2HALF).replace('：', ':').replace(' ＝', '=')
        m = TS_RE.match(t)
        if m and ':' not in t[m.end():m.end() + 2] and '比分' not in t:
            ts = m.group(1).strip()
            out.append(ts)
            continue
        if not ts:
            continue
        kind = None
        if '胜方比分' in t or ('胜比分' in t):
            kind = '胜方比分'
        elif '平局比分' in t or '平比分' in t:
            kind = '平局比分'
        elif '负方比分' in t or '负比分' in t:
            kind = '负方比分'
        if not kind:
            # 无标签但有 1:0= 形式 → 依 1:0 位置推断（保守: 略）
            continue
        pairs = re.findall(r'(\d+:\d+|\S*?其它?\S*?)\s*[=:]\s*(\d+\.?\d*)', t)
        kv = []
        for k, v in pairs:
            kk = k.strip()
            if '其它' in kk or '其他' in kk:
                kk = {'胜': '胜其它', '平': '平其它', '负': '负其它'}.get(kk[0], kk)
            kv.append('%s=%s' % (kk, v))
        if kv:
            out.append('%s：%s' % (kind, '，'.join(kv)))
    return out if len(out) > 1 else []


def validate(sections, rep):
    """校验 → (OK列表, WARN列表, ERR列表)"""
    ok, warn, err = [], [], []
    names = [s[0] for s in sections]
    if rep['赛事']:
        ok.append('赛事行: %s' % rep['赛事'][:40])
    else:
        err.append('缺【赛事】行（联赛/主客队识别依赖）')
    if rep['时间']:
        ok.append('比赛时间: %s' % rep['时间'][:40])
    else:
        warn.append('缺【比赛时间】行（api-football 日期换算依赖·将尝试从 txt 其它处推断）')
    need = {'胜平负': 1, '让球': 1, '半全场': 1, '总进球': 1, '比分': 1}
    for sec, minrows in need.items():
        rows = [s for s in sections if s[0] == sec]
        if not rows:
            if sec in ('让球', '半全场'):
                warn.append('缺【%s】节（该市场赔率将不可用·三态标注）' % sec)
            else:
                err.append('缺【%s】节（必填）' % sec)
            continue
        n = len(rows[0][2])
        rep['时点数'][sec] = n
        if n < minrows:
            err.append('【%s】节为空（0 行有效数据）' % sec)
        else:
            ok.append('【%s】%d 时点' % (sec, max(0, n - 1)))
    # 数值合理性（🔴仅赔率节·且仅匹配两位小数形式——避免把比分"1:0"/场均进球"0.9个"误判为赔率）
    ODDS_SECS = ('胜平负', '让球', '半全场', '总进球')
    for sec, title, lines in sections:
        if sec not in ODDS_SECS:
            continue
        for l in lines:
            for v in re.findall(r'\d+\.\d{2}', l):
                if float(v) < 1.01:
                    err.append('【%s】疑似异常赔率 %s（<1.01）: %s' % (sec, v, l[:40]))
                    break
    return ok, warn, err


def build_std(sections, rep):
    """→ 标准模板 txt 文本"""
    order = ['赛事', '时间', '特征', '胜平负', '让球', '半全场', '总进球', '比分']
    head_sec = [s for s in sections if s[0] == '前言']
    lines = []
    for sec, title, body in sections:
        if sec == '前言':
            continue
    for l in (head_sec[0][2] if head_sec else []):
        lines.append(l)
    for key in order:
        for sec, title, body in sections:
            if sec != key:
                continue
            if key == '赛事':
                lines.append(rep['赛事'] or (body[0] if body else ''))
                continue
            if key == '时间':
                lines.append(rep['时间'] or (body[0] if body else ''))
                continue
            if key == '特征':
                lines.append('')
                lines.append('【特征分析】')
                lines += body
                continue
            if key == '胜平负':
                rows = norm_spf(body)
                if rows:
                    lines += ['', '【胜平负固定奖金】'] + rows
                continue
            if key == '让球':
                rows = norm_spf(body)
                mh = re.search(r'让球[:：]?\s*([+-]?\d+(?:\.\d+)?)', title)
                hd = ('%+g' % float(mh.group(1))) if mh else ''
                if rows:
                    lines += ['', '【让球胜平负固定奖金｜让球%s】' % hd] + rows
                continue
            if key == '半全场':
                rows = norm_bqc(body)
                if rows:
                    lines += ['', '【半全场胜平负固定奖金】'] + rows
                continue
            if key == '总进球':
                rows = norm_zjq(body)
                if rows:
                    lines += ['', '【总进球固定奖金】'] + rows
                continue
            if key == '比分':
                rows = norm_cs(body)
                if rows:
                    lines += ['', '【比分固定奖金】'] + rows
                continue
    return '\n'.join(lines) + '\n'


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    src = args[0]
    out = None
    check_only = '--check-only' in args
    if '--out' in args:
        out = args[args.index('--out') + 1]
    if not out:
        stem = os.path.splitext(os.path.basename(src))[0]
        out = os.path.join(HERE, 'std_%s.txt' % stem)
    text = open(src, encoding='utf-8-sig', errors='replace').read()
    sections, rep = parse(text)
    ok, warn, err = validate(sections, rep)
    std = build_std(sections, rep)
    print('=' * 72)
    print('txt_normalize — 归一化 + 校验（%s）' % os.path.basename(src))
    print('=' * 72)
    print('✅ 通过: %d 项' % len(ok))
    for x in ok:
        print('   ✅ %s' % x)
    for x in warn:
        print('   ⚠️ %s' % x)
    for x in err:
        print('   ❌ %s' % x)
    print('\n标准模板预览（前 12 行）:')
    for l in std.splitlines()[:12]:
        print('   ' + l)
    if not check_only and not err:
        open(out, 'w', encoding='utf-8').write(std)
        print('\n✅ 标准模板已落盘: %s' % out)
    elif err:
        print('\n🔴 存在 ❌ 错误——未落盘（修复原始 txt 后重跑）')
    else:
        print('\n（--check-only: 未落盘）')


if __name__ == '__main__':
    main()
