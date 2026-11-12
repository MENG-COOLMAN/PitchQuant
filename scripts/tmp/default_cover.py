# -*- coding: utf-8 -*-
"""P-COVER-1 默认覆盖校验（2026-11-12·case346 复盘驱动·用户指令「做」）

════════════════════════════════════════════════════════════════════
背景（真实事故·不是假想）
════════════════════════════════════════════════════════════════════
AGENTS L2 铁律（227,495 场时间分割回测·用户 2026-09-27 固化）：

    默认覆盖 = 「最低赔率方向 + 次低赔率方向」   77.68%
             > 「最低赔率方向 + 平局」           76.51%

case346（神户 0:1 町田）违反该铁律：
    赔率  主胜 2.46（最低）/ 客胜 2.82（次低）/ 平局 3.08（**最高**）
    应覆盖 主胜 + 客胜
    实际写 主胜 + 平局   ← 用**最高赔**的平局挤掉了次低赔方向
    真实   0:1 客胜       ← 若按铁律则方向 ✅
    连带   市场矩阵 Top2 就是 0:1(10.4%)·被方向域整块屏蔽 → 锚也跟着错

同一批 case345 对照（合规 → 完美命中）：
    赔率  客胜 2.23（最低）/ 主胜 2.842（次低）/ 平局 3.58（最高）
    实际   客胜 + 主胜 ← 次向取的正是次低赔方向
    真实   1:2 → **主锚 1:2 精确命中**

════════════════════════════════════════════════════════════════════
判据（纯函数·无副作用·只警告不改方向）
════════════════════════════════════════════════════════════════════
  OK            已覆盖「最低赔 + 次低赔」两向 → 合规
  SINGLE        只给了一个方向（且含最低赔方向）→ 两向覆盖不适用
                → 须由**单押准入**把关（skew≥200% 且最低赔<1.30·否则必须两向）
  VIOLATION     次低赔方向被排除（且用其它方向替换）→ 违规
                → 落盘须在 raw 说明理由（Q2诱盘 / 诱主 / M1伤停仍热门 等硬动作）
  VIOLATION_FAV 连**最低赔方向**都没覆盖 → 严重偏离
  NODIR         未传方向 或 无欧盘赔率 → 三态（无法校验）

🔴 铁律：本模块**只输出判据与建议**，不改方向、不改锚、不反转 L2。
   违规 ≠ 必错（case347 违规但客胜命中），但会**削弱两向覆盖保障**——
   弱共识三方接近均分时，次低赔与平局的概率差被放大（case346: 客胜 32.7% > 平局 29.9%）。

用法：
    python data/tmp/default_cover.py --eu 2.46,3.08,2.82 --dirs "主胜,平局"    # → VIOLATION
    python data/tmp/default_cover.py --eu 2.842,3.58,2.23 --dirs "客胜,主胜"   # → OK
"""

import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

DIRS = ('主胜', '平局', '客胜')

_ALIAS = {
    '主胜': '主胜', '主': '主胜', 'h': '主胜', 'home': '主胜', 'win': '主胜', '1': '主胜',
    '平局': '平局', '平': '平局', 'd': '平局', 'draw': '平局', 'x': '平局', '0': '平局',
    '客胜': '客胜', '客': '客胜', 'a': '客胜', 'away': '客胜', '2': '客胜',
}


def norm_dirs(raw):
    """把任意写法的方向串归一成 ['主胜','平局','客胜'] 子集（去重保序）。"""
    if isinstance(raw, str):
        s = raw.replace('，', ',').replace('、', ',').replace('+', ',').replace('/', ',')
        parts = [x.strip() for x in s.split(',')]
    elif isinstance(raw, (list, tuple)):
        parts = [str(x).strip() for x in raw]
    else:
        parts = []
    out, seen = [], set()
    for p in parts:
        if not p:
            continue
        k = _ALIAS.get(p.lower()) or _ALIAS.get(p)
        if k and k not in seen:
            out.append(k)
            seen.add(k)
    return out


def devig(odds):
    """等比例去水 → [p主, p平, p客]（仅用于展示，不参与判据）。"""
    try:
        inv = [1.0 / float(x) for x in odds]
        s = sum(inv)
        return [x / s for x in inv] if s > 0 else [None, None, None]
    except Exception:
        return [None, None, None]


def check(odds, dirs):
    """核心判据。odds=[主,平,客] 赔率；dirs=预测方向（str 或 list）。

    返回 dict: level / fav / second / odds_map / probs / suggestion / msg
    """
    try:
        o = [float(x) for x in odds]
        if len(o) != 3 or any(x <= 1.0 for x in o):
            raise ValueError('odds invalid')
    except Exception:
        return {'level': 'NODIR', 'fav': None, 'second': None,
                'msg': '欧盘赔率缺失/非法 → 无法校验（三态）'}

    dd = norm_dirs(dirs)
    if not dd:
        return {'level': 'NODIR', 'fav': None, 'second': None,
                'msg': '未传 --step5-dirs → 无法校验（三态·须补方向后重跑该段）'}

    pr = devig(o)
    order = sorted(range(3), key=lambda i: o[i])
    i_fav, i_sec = order[0], order[1]
    fav, sec = DIRS[i_fav], DIRS[i_sec]

    res = {'fav': fav, 'second': sec,
           'odds_map': dict(zip(DIRS, o)),
           'probs': dict(zip(DIRS, pr)),
           'suggestion': [fav, sec]}

    if fav not in dd:
        res['level'] = 'VIOLATION_FAV'
        res['msg'] = ('连最低赔方向 **%s %.2f** 都未覆盖（预测=%s）→ 严重偏离默认覆盖'
                      % (fav, o[i_fav], '+'.join(dd)))
        return res

    if len(dd) == 1:
        res['level'] = 'SINGLE'
        res['msg'] = ('单押 %s（=最低赔方向）→ 两向覆盖不适用·须由**单押准入**把关'
                      '（skew≥200%% 且最低赔<1.30·不满足则必须两向）' % fav)
        return res

    if sec in dd:
        res['level'] = 'OK'
        res['msg'] = ('已覆盖 最低赔(%s %.2f) + 次低赔(%s %.2f) → 合规'
                      % (fav, o[i_fav], sec, o[i_sec]))
        return res

    fill = [x for x in dd if x != fav]
    _f0 = fill[0] if fill else None
    res['level'] = 'VIOLATION'
    res['msg'] = ('次低赔方向 **%s %.2f**（去水 %.1f%%）被排除，实际用 %s（%.2f / 去水 %.1f%%）替换'
                  ' → 建议覆盖 %s + %s'
                  % (sec, o[i_sec], (pr[i_sec] or 0) * 100,
                     '+'.join(fill) or '无第二向',
                     o[DIRS.index(_f0)] if _f0 else 0.0,
                     ((pr[DIRS.index(_f0)] or 0) * 100) if _f0 else 0.0,
                     fav, sec))
    return res


def fmt(r):
    """单行输出（供 calc_all / CLI 共用）。"""
    lv = r.get('level') or 'NODIR'
    if lv == 'OK':
        head = '✅【默认覆盖建议】P-COVER-1 OK'
    elif lv == 'SINGLE':
        head = '⚪【默认覆盖建议】P-COVER-1 SINGLE'
    elif lv == 'NODIR':
        head = '⚪【默认覆盖建议】P-COVER-1 NODIR'
    elif lv == 'VIOLATION_FAV':
        head = '🔴🔴【默认覆盖建议】P-COVER-1 VIOLATION_FAV'
    else:
        head = '🔴【默认覆盖建议】P-COVER-1 %s' % lv
    if lv == 'NODIR':
        return '%s ｜ %s' % (head, r.get('msg'))
    om, pb = r.get('odds_map') or {}, r.get('probs') or {}
    detail = ' ｜ '.join('%s %.2f/去水%.1f%%' % (d, om.get(d, 0), (pb.get(d) or 0) * 100)
                        for d in DIRS)
    sug = ' + '.join(r.get('suggestion') or [])
    return '%s ｜ 赔率 %s ｜ 建议覆盖 **%s** ｜ %s' % (head, detail, sug, r.get('msg'))


def is_violation(r):
    return (r or {}).get('level') in ('VIOLATION', 'VIOLATION_FAV')


def main():
    import argparse
    ap = argparse.ArgumentParser(description='P-COVER-1 默认覆盖校验（只警告·不改方向）')
    ap.add_argument('--eu', required=True, help='欧盘赔率 "主,平,客"（真实欧盘·禁竞彩末盘）')
    ap.add_argument('--dirs', required=True, help='预测方向 "主胜,平局"（--step5-dirs 口径）')
    a = ap.parse_args()
    try:
        odds = [float(x) for x in a.eu.replace('，', ',').split(',')]
    except Exception:
        print('❌ --eu 解析失败（须 "主,平,客" 三个数）')
        return 2
    r = check(odds, a.dirs)
    print(fmt(r))
    print('  level=%s  fav=%s  second=%s  suggestion=%s'
          % (r.get('level'), r.get('fav'), r.get('second'), r.get('suggestion')))
    return 1 if is_violation(r) else 0


if __name__ == '__main__':
    sys.exit(main())
