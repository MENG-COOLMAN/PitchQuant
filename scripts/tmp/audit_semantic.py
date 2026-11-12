# -*- coding: utf-8 -*-
"""audit_semantic.py —— **语义级**审计（calc 权威值 vs raw 声明值）

🔴 为什么需要（2026-11-01·audit_judgment 的诚实边界）：
   audit_judgment 是**关键词级** —— 能拦「完全没提」，**拦不住「提了但判断错」**。
   例：raw 写了「SK-league」就算 PASS，但模型可能根本没按规则判。

判据（三态）:
   ✅ CONSISTENT —— raw 声明 == calc 权威值
   ⚠️ EXPLAINED  —— 不一致但 raw **给了理由/依据**（模型有权判断·须留痕）
   🔴 CONFLICT   —— 不一致且**没给理由** = 判断与计算脱节（最危险·比"没提"更坏）
   ⚪ MISSING    —— raw 没写该项

用法: python data/tmp/audit_semantic.py --calc <calc> --raw <raw> [--json]
"""
import argparse
import io
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# ── calc 权威值提取器 ──
CALC_PAT = {
    '方向':       r'方向\(欧亚综合\):\s*(主胜|平局|客胜)\(([A-Z][A-Z\-]*)\)',
    '置信度':     r'调整后\s*\*\*([A-Z][A-Z\-]*)\*\*',
    '主锚':       r'主锚\s*(\d+\s*[:：]\s*\d+)',
    '次锚':       r'次锚\s*(\d+\s*[:：]\s*\d+)',
    'λ_final':    r'λ_final=([\d.]+)\s*→\s*九档量级「([^」]+)」',
    'O2.5档':     r'O2\.5=([\d.]+)档',
    '伤停主':     r'主队\s*([\d.]+)\s*分',
    '伤停客':     r'客队\s*([\d.]+)\s*分',
    'R11客零封':  r'客被零封\s*(\d+)%',
    'R11主零封':  r'主被零封\s*(\d+)%',
}

# ── raw 声明提取器 ──
RAW_PAT = {
    '方向':   [r'预测方向[^\n]*?[:：|]\s*\**\s*([^\n|*]{2,40})',
               r'\|\s*\*{0,2}方向\*{0,2}\s*\|\s*([^|\n]{2,40})'],
    '置信度': [r'置信度层\s*[:：|]\s*\**\s*([A-Z][A-Z\-]*)',
               r'置信度\s*[:：|]\s*\**\s*([A-Z][A-Z\-]*)'],
    '主锚':   [r'主锚\s*[:：|]?\s*\**\s*(\d+\s*[:：]\s*\d+)'],
    '次锚':   [r'次锚\s*[:：|]?\s*\**\s*(\d+\s*[:：]\s*\d+)'],
}
# 🔴2026-11-01 严格化：必须是**显式改判说明**，不能用泛泛的「依据/理由」
#   原实现看全文 → raw 骨架里到处有「附数值依据」「模型可改须给理由」→ 一律误判 EXPLAINED
REASON_PAT = [
    r'改判理由\s*[:：]',
    r'改锚理由\s*[:：]',
    r'偏离说明\s*[:：]',
    r'与calc不符\s*[:：]',
    r'不采纳.{0,12}(calc|计算|程序|脚本)',
    r'(模型|本人)改判\s*[:：]',
    r'override\s*[:：]',
]

# 方向归一
DIR_MAP = {'主胜': '主胜', '主': '主胜', '平局': '平局', '平': '平局',
           '客胜': '客胜', '客': '客胜'}


def norm_dir(s):
    s = (s or '').strip()
    out = []
    for k, v in DIR_MAP.items():
        if k in s and v not in out:
            out.append(v)
    return out


def grab(text, pat):
    if not text:
        return None
    m = re.search(pat, text)
    return m.groups() if (m and m.groups()) else (m.group(0) if m else None)


def grab_multi(text, pats):
    for p in pats:
        r = grab(text, p)
        if r:
            return r if isinstance(r, tuple) else (r,)
    return None


def has_reason(raw, around=''):
    """找显式改判说明（两级判据·P41-2026-11-02）

    ① 就近优先：around **前 3 处**出现的前后 400 字符内命中 REASON_PAT
    ② 就近失败 → 回落全文「显式改判措辞」（改锚理由/改判理由/偏离说明/与calc不符…）
       🔴为什么必须回落：raw 第二/三节是 1xbet 全量赔率表（波胆 31 档 + 亚盘 17 档 + 大小球多档），
       「1:0 / 2:1」这类比分数字密集出现数十次 → 前 3 处必然落在赔率表内，
       就近窗口永远不含理由 → 即使结论段写清「改锚理由:」也恒判 CONFLICT（case319 实证）。
    ③ 全文也无显式措辞 → False（保持 CONFLICT 强度·不接受泛泛「依据/理由」）
    """
    blob = raw or ''
    if not blob:
        return False
    if around:
        for m in list(re.finditer(re.escape(around), blob))[:3]:
            seg = blob[max(0, m.start() - 400):m.end() + 400]
            if any(re.search(p, seg) for p in REASON_PAT):
                return True
        # ② 回落全文（仅认**显式**改判措辞）
        return any(re.search(p, blob) for p in REASON_PAT)
    return any(re.search(p, blob) for p in REASON_PAT)


def run(calc, raw):
    C = {}
    for k, p in CALC_PAT.items():
        C[k] = grab(calc, p)

    R = {}
    for k, ps in RAW_PAT.items():
        R[k] = grab_multi(raw, ps)

    rows = []

    # ① 方向：calc 主方向须 ∈ raw 声明方向集
    c_dir = C['方向'][0] if C.get('方向') else None
    r_dirs = norm_dir(' '.join(R['方向'])) if R.get('方向') else []
    if not r_dirs:
        rows.append(('方向', c_dir or '?', '⚪ MISSING', 'raw 未声明方向'))
    elif c_dir and c_dir in r_dirs:
        rows.append(('方向', c_dir, '✅ CONSISTENT', 'raw 含 %s' % c_dir))
    elif c_dir:
        rows.append(('方向', c_dir, '⚠️ EXPLAINED' if has_reason(raw, c_dir) else '🔴 CONFLICT',
                     'raw=%s vs calc=%s' % ('+'.join(r_dirs), c_dir)))

    # ② 置信度
    c_cl = C['置信度'][0] if C.get('置信度') else None
    r_cl = R['置信度'][0] if R.get('置信度') else None
    if not r_cl:
        rows.append(('置信度', c_cl or '?', '⚪ MISSING', 'raw 未写置信度层'))
    elif c_cl and r_cl == c_cl:
        rows.append(('置信度', c_cl, '✅ CONSISTENT', ''))
    elif c_cl:
        rows.append(('置信度', c_cl, '⚠️ EXPLAINED' if has_reason(raw, r_cl) else '🔴 CONFLICT',
                     'raw=%s vs calc=%s' % (r_cl, c_cl)))

    # ③ 主锚 / 次锚
    for k in ('主锚', '次锚'):
        c_v = C[k][0] if C.get(k) else None
        r_v = R[k][0] if R.get(k) else None
        c_n = re.sub(r'\s+', '', str(c_v)) if c_v else None
        r_n = re.sub(r'\s+', '', str(r_v)) if r_v else None
        if not r_n:
            rows.append((k, c_n or '?', '⚪ MISSING', 'raw 未写%s' % k))
        elif c_n and r_n == c_n:
            rows.append((k, c_n, '✅ CONSISTENT', ''))
        elif c_n:
            rows.append((k, c_n, '⚠️ EXPLAINED' if has_reason(raw, r_n) else '🔴 CONFLICT',
                         'raw=%s vs calc=%s' % (r_n, c_n)))

    # ④ 量级（λ_final 九档 + O2.5 档）—— raw 只作参考，须引用
    if C.get('λ_final'):
        lam, band = C['λ_final']
        if band and band in (raw or ''):
            rows.append(('量级', '%s(%s)' % (lam, band), '✅ CONSISTENT', 'raw 引用了同量级档'))
        elif lam and lam in (raw or ''):
            rows.append(('量级', '%s(%s)' % (lam, band), '✅ CONSISTENT', 'raw 引用了 λ'))
        else:
            rows.append(('量级', '%s(%s)' % (lam, band), '⚪ MISSING',
                         'raw 未引用 λ/量级档'))

    # ⑤ 伤停（判定铁依据·须引用）
    ih = C['伤停主'][0] if C.get('伤停主') else None
    ia = C['伤停客'][0] if C.get('伤停客') else None
    if ih or ia:
        if (ih and ih in (raw or '')) or (ia and ia in (raw or '')):
            rows.append(('伤停', '主%s/客%s' % (ih, ia), '✅ CONSISTENT', 'raw 引用了分值'))
        else:
            rows.append(('伤停', '主%s/客%s' % (ih, ia), '⚪ MISSING',
                         'raw 未引用伤停影响分'))

    # ⑥ R11 零封
    az = C['R11客零封'][0] if C.get('R11客零封') else None
    hz = C['R11主零封'][0] if C.get('R11主零封') else None
    if az or hz:
        if (az and ('%s%%' % az) in (raw or '')) or (hz and ('%s%%' % hz) in (raw or '')):
            rows.append(('R11零封', '主%s%%/客%s%%' % (hz, az), '✅ CONSISTENT', ''))
        else:
            rows.append(('R11零封', '主%s%%/客%s%%' % (hz, az), '⚪ MISSING',
                         'raw 未引用零封率'))

    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--calc')
    ap.add_argument('--raw')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    calc = io.open(a.calc, encoding='utf-8', errors='replace').read() if (a.calc and os.path.exists(a.calc)) else ''
    raw = io.open(a.raw, encoding='utf-8', errors='replace').read() if (a.raw and os.path.exists(a.raw)) else ''
    if not calc or not raw:
        print('❌ 需 --calc 和 --raw 同时存在')
        return 2

    rows = run(calc, raw)
    nc = sum(1 for r in rows if r[2].startswith('✅'))
    ne = sum(1 for r in rows if r[2].startswith('⚠️'))
    nx = sum(1 for r in rows if r[2].startswith('🔴'))
    nm = sum(1 for r in rows if r[2].startswith('⚪'))

    if a.json:
        print(json.dumps({'rows': rows, 'consistent': nc, 'explained': ne,
                          'conflict': nx, 'missing': nm}, ensure_ascii=False))
        return 0 if nx == 0 else 1

    print('=' * 100)
    print('语义级审计（audit_semantic）｜ calc 权威值 vs raw 声明值')
    print('=' * 100)
    for k, v, st, why in rows:
        print('  %-9s calc=%-16s %-14s %s' % (k, str(v)[:16], st, why[:56]))
    print('-' * 100)
    print('  ✅ 一致 %d ｜ ⚠️ 已说明 %d ｜ 🔴 **冲突 %d** ｜ ⚪ 未写 %d'
          % (nc, ne, nx, nm))
    if nx:
        print('\n🔴 **判断与计算脱节**（raw 写了但与 calc 不符·且未给理由）:')
        for k, v, st, why in rows:
            if st.startswith('🔴'):
                print('   %-9s %s' % (k, why))
        print('\n   → 这比「没提」更危险：看起来做了判断，实际与程序计算相悖')
    else:
        print('\n✅ 无语义冲突（凡改判均已说明理由）')
    return 0 if nx == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
