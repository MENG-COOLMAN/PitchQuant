# -*- coding: utf-8 -*-
"""signal_landing.py —— 信号落地强制传导层（2026-10-29 建立 / 同日修订：三向覆盖作废·最多两向）

背景（实证）:
  case290/292 复盘发现: calc_all 的告警信号（诱主嫌疑 / M1 伤停仍热门 / Q2 诱盘）
  **全部已写进 raw**（审计 4/4 ✅已提及），但方向结论没随之改变 →
  根因不是「没写」，而是「**写了没动作**」，且旧审计 `audit_consumption` 只判关键词出现 = 拦不住。

🔴 2026-10-29 用户指令修订: 「三向覆盖完全没有帮助，强制每场比赛最多两向」
  → 删除原「须三向覆盖」信号；新增**最多两向**硬约束 + `max_two_check()` 超标检测。
  → 第二向取值规则（🔴2026-11-12 P-COVER-1 修正）:
      诱主/M1/Q2/强诱盘 → **对手方**（P30 硬动作·优先级最高）；
      其余（含弱共识）  → **次低赔方向**（L2 铁律: 默认覆盖=最低+次低 77.68% > 最低+平局 76.51%）。
      🔴 弱共识只强制「禁单押首选」= **必须两向**，**不指定**第二向必须是平局
         （平局只在赔率 ≤ 次低赔时自然入选；要押平局须在 raw 说明理由）。
      背景实证: case346 原硬编码「弱共识→平局」→ 用最高赔平局 3.08 挤掉次低赔客胜 2.82
                → 真实 0:1 客胜 → 方向 ❌（按 L2 则 ✅）；对照 case345 合规 → 主锚 1:2 精确命中。

本模块提供三道校验:
  ① signals(calc_text)   —— 从 calc_all 输出解析本场触发信号（结构化）
  ② check(raw_text)      —— 逐条校验 raw 是否给出**动作**（动作词），未给出=未落地
  ③ max_two_check(raw)   —— 「预测方向」字段是否 ≤2 向（列 3 向=违规·2026-10-29）

CLI:
  python data/tmp/signal_landing.py --calc data/tmp/_pipe_calc_XXX.txt [--raw auto]
  python data/tmp/signal_landing.py --calc <calc> --simulate
"""
import argparse
import glob
import io
import os
import re
import sys

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

MAX_DIRS = 2   # 🔴 用户 2026-10-29 指令：每场最多两向

# ── 信号规则表（name, 匹配正则, 等级, 强制动作）──────────────────────────
# 🔴 等级 H=硬动作（必须改变方向/锚/覆盖）· M=必须留痕处置（可"不适用"+理由）
RULES = [
    ('诱主嫌疑', r'诱主嫌疑|诱主信号', 'H',
     '热门方降为并列 + **并列对手方方向**（非平局；平局并列须修正53分组分≥2.5）'),
    ('M1伤停仍热门', r'M1[客主]?队?伤停≥15仍热门|M1主队伤停|M1客队伤停', 'H',
     '该热门方 −1 档 + **强制并列对手方方向**（逆基本面→热门打不动）'),
    ('Q2诱盘确认', r'Q2 诱盘(确认|警报)', 'H',
     '热门方 −1 档 + **强制并列对手方方向**'),
    ('P12强诱盘/矛盾', r'强诱盘|矛盾待查', 'H',
     '被诱方 −1 档 + 强制并列（覆盖写入预测方向字段·**最多两向**）'),
    ('弱共识skew<150', r'弱共识场\(skew=\d', 'H',
     '必须**两向覆盖**（禁单押首选）·第二向取**次低赔方向**（L2 铁律·非固定平局）'),
    ('单押不准入', r'禁单押|单押准入', 'H',
     '必须 ≥2 向覆盖（不得单押）·上限 2 向'),
    ('锚可信度不可信', r'锚可信度[^\n]{0,6}不可信|🔴不可信', 'H',
     '宽候选池（≥4）+ 禁单锚 + 标注比分不可预测'),
    ('H3+出口', r'H3\+', 'H',
     '候选池必须含净胜≥2 比分（3:0/3:1 类）'),
    ('零封直盘冲突', r'R11|零封直盘', 'M',
     '比分锚须与零封谱系一致（BTTS≥60% 禁零封锚 / 强零封须含零封锚）'),
    ('N26低分出口', r'N26|低分出口', 'M',
     '低分出口须落在 N26 指定进球档（O2.5≤1.70→2球 / >1.70→0-1球）'),
    ('极端共振/贴水浅让', r'极端共振|贴水浅让', 'M',
     '标注比分不可预测 + 禁主锚精细锚定'),
    ('大小球信号强度', r'大小球信号强度|弱信号档', 'M',
     '弱信号档（53-55%/45-47%）禁进串关/禁单押依据'),
]

# 动作词：raw 中该信号行必须出现其一，才算「落地」
ACTION_WORDS = ('降', '并列', '排除', '不适用', '宽池', '宽候选', '禁止', '禁单押',
                '必须', '覆盖', '改取', '上调', '下调', '取', '剔除', '保留')

DIR_WORDS = ('主胜', '平局', '客胜')


def signals(calc_text):
    """从 calc_all 输出解析本场触发信号 → [{name, level, action}]"""
    out = []
    for name, pat, level, action in RULES:
        if re.search(pat, calc_text):
            out.append({'name': name, 'level': level, 'action': action, 'pat': pat})
    return out


def _lines_with(text, pat):
    return [l for l in text.splitlines() if re.search(pat, l)]


def check(raw_text, sigs):
    """逐条校验 raw 是否给出动作 → (ok_list, fail_list)"""
    ok, fail = [], []
    raw = raw_text or ''
    for s in sigs:
        ls = _lines_with(raw, s['pat'])
        if not ls:
            fail.append((s, 'raw 完全未提及'))
            continue
        acted = [l for l in ls if any(w in l for w in ACTION_WORDS)]
        if acted:
            ok.append((s, acted[0].strip()[:110]))
        else:
            fail.append((s, 'raw 提及但无动作词（识别未落地）'))
    return ok, fail


def max_two_check(raw_text):
    """🔴 2026-10-29 用户指令：每场最多两向。
    检查 raw 的「预测方向 / 方向」行是否列了 3 个方向 → 返回 (ok, bad_lines)"""
    bad = []
    for l in (raw_text or '').splitlines():
        s = l.strip()
        if not s:
            continue
        if ('预测方向' in s) or ('**方向**' in s) or s.startswith('| 方向') or s.startswith('| **方向'):
            n = sum(1 for w in DIR_WORDS if w in s)
            if n >= 3:
                bad.append(s[:130])
    return (len(bad) == 0), bad


def min_cover_check(raw_text, sim):
    """🔴2026-11-01 方向覆盖**下限**门禁（原只有 max_two_check 只查「不超过2向」）

    缺陷实证（科莫场 / case304/306）：程序已推导「应覆盖 主胜＋客胜」并写进 raw 骨架，
    但 raw 的「预测方向」只写主胜 → **没有任何门禁抓**（check 只校信号处置·max_two 只管上限）。

    → 返回 (ok, need, got, miss)。raw「预测方向」必须包含 sim['dirs'] 的全部方向。
    """
    need = [d for d in (sim.get('dirs') or []) if d in DIR_WORDS]
    got = []
    for _l in (raw_text or '').splitlines():
        _s = _l.strip()
        if ('预测方向' in _s) or _s.startswith('| 方向') or _s.startswith('| **方向'):
            for _w in DIR_WORDS:
                if _w in _s and _w not in got:
                    got.append(_w)
    miss = [d for d in need if d not in got]
    return (len(miss) == 0), need, got, miss


def simulate(calc_text, sigs):
    """按规则推导「应覆盖方向」——🔴最多两向（2026-10-29 修订）

    🔴2026-11-12 P-COVER-1 修正（case346 事故·用户指令「做」）：
      原实现把「弱共识 → 第二向 = 平局」**硬编码**，与 L2 铁律直接冲突——
        L2（227,495 场时间分割）: 默认覆盖=「最低赔+次低赔」77.68% > 「最低+平局」76.51%
        case346 神户 0:1 町田：主 2.46 / 客 2.82 / 平 3.08
          → 硬编码给「主胜+平局」（平局=最高赔）→ 方向 ❌
          → 按 L2 给「主胜+客胜」→ 方向 ✅
        case345 川崎 1:2 柏：主 2.842 / 客 2.23 / 平 3.58
          → 次向取次低赔 主胜 → **主锚 1:2 精确命中**（合规对照）
      → **第二向默认 = 次低赔方向**；弱共识的唯一强制是「禁单押首选」（=必须两向），
        **不指定**第二向必须是平局（平局只在赔率 ≤ 次低赔时自然入选）。
      硬动作（诱主/M1/Q2/P12）仍优先取对手方（P30 ⑤ 既有纪律·优先级高于默认覆盖）。
      要押平局作第二向 → 须在 raw 说明理由（check_luopan P-COVER-1 会核·case348+）。
    """
    names = {s['name'] for s in sigs}
    need_opposite = any(n in names for n in ('诱主嫌疑', 'M1伤停仍热门', 'Q2诱盘确认', 'P12强诱盘/矛盾'))
    need_draw = '弱共识skew<150' in names
    two_way = need_opposite or need_draw or '单押不准入' in names

    fav = None
    m = re.search(r'方向\(欧亚综合\):\s*(主胜|平局|客胜)', calc_text)
    if m:
        fav = m.group(1)
    opp = {'主胜': '客胜', '客胜': '主胜', '平局': None}.get(fav)

    # ── L2 默认覆盖：从 calc 输出读欧盘赔率 → 次低赔方向 ──
    _NAMES = ('主胜', '平局', '客胜')
    sec_l2, why_l2 = None, ''
    _mo = re.search(r'赔率\s*主胜\s*([\d.]+)[^\n]*?平局\s*([\d.]+)[^\n]*?客胜\s*([\d.]+)', calc_text)
    if _mo:
        try:
            _o = [float(_mo.group(1)), float(_mo.group(2)), float(_mo.group(3))]
            _ord = sorted(range(3), key=lambda i: _o[i])
            sec_l2 = _NAMES[_ord[1]]
            why_l2 = ('L2默认覆盖(最低+次低赔)→第二向=次低赔 %s %.2f'
                      '（弱共识只要求两向·不指定平局）' % (sec_l2, _o[_ord[1]]))
        except Exception:
            sec_l2, why_l2 = None, ''

    dirs = [fav] if fav else []
    second, why = None, ''
    if need_opposite and opp:
        # 诱主/M1/Q2/强诱盘：第二向=对手方（P30 ⑤·case290/292 实证·优先级高于默认覆盖）
        second, why = opp, '诱主/M1/Q2/强诱盘→第二向取对手方（P30 硬动作优先）'
    elif two_way and fav:
        if sec_l2:
            second, why = sec_l2, why_l2
        else:
            second = '平局' if fav != '平局' else opp
            why = '单押不准入→补第二向（⚪赔率缺失·退回平局待核）'
    if second and second not in dirs:
        dirs.append(second)
    dirs = dirs[:MAX_DIRS]

    return {
        'fav': fav, 'opposite': opp if need_opposite else None,
        'need_draw': need_draw, 'two_way': two_way, 'dirs': dirs,
        'second_why': why or '首选方向即可', 'max_dirs': MAX_DIRS,
        'l2_second': sec_l2,
        'reasons': [n for n in ('诱主嫌疑', 'M1伤停仍热门', 'Q2诱盘确认',
                                'P12强诱盘/矛盾', '弱共识skew<150', '单押不准入') if n in names],
    }


def report(calc_path, raw_path=None):
    calc = io.open(calc_path, encoding='utf-8', errors='ignore').read()
    sigs = signals(calc)
    print('=' * 100)
    print('信号落地核查 · %s ｜ 触发信号 %d 条（H 硬动作 %d / M 留痕 %d）'
          % (os.path.basename(calc_path), len(sigs),
             sum(1 for s in sigs if s['level'] == 'H'),
             sum(1 for s in sigs if s['level'] == 'M')))
    print('=' * 100)
    for i, s in enumerate(sigs, 1):
        print('  %-2d [%s] %-18s → 强制动作: %s' % (i, s['level'], s['name'], s['action']))
    sim = simulate(calc, sigs)
    print('\n【按规则应覆盖方向（最多 %d 向）】: %s ｜ 第二向依据: %s'
          % (MAX_DIRS, '＋'.join(sim['dirs']) or '—', sim['second_why'] or '不需要第二向'))
    rc = 0
    if raw_path:
        raw = io.open(raw_path, encoding='utf-8', errors='ignore').read()
        ok, fail = check(raw, sigs)
        print('\n【raw 落地校验】: ✅%d / ❌%d' % (len(ok), len(fail)))
        for s, ev in ok:
            print('  ✅ %-18s %s' % (s['name'], ev))
        for s, why in fail:
            print('  ❌ %-18s %s' % (s['name'], why))
        o2, bad = max_two_check(raw)
        if o2:
            print('\n【最多两向校验】: ✅ 预测方向字段 ≤2 向')
        else:
            print('\n【最多两向校验】: ❌ 检出 3 向声明（2026-10-29 用户指令禁止）:')
            for b in bad:
                print('   ', b)
        rc = 0 if (not fail and o2) else 1
        return rc
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--calc', required=True)
    ap.add_argument('--raw', default=None)
    ap.add_argument('--simulate', action='store_true')
    a = ap.parse_args()
    if a.simulate and not a.raw:
        calc = io.open(a.calc, encoding='utf-8', errors='ignore').read()
        print(simulate(calc, signals(calc)))
        return 0
    if a.raw == 'auto':
        m = re.search(r'case(\d{3})', a.calc) or re.search(r'_(\d{3,})', os.path.basename(a.calc))
        cid = m.group(1) if m else None
        cands = glob.glob('data/case-library/raw/case%s*.md' % cid) if cid else []
        a.raw = cands[0] if cands else None
    return report(a.calc, a.raw)


if __name__ == '__main__':
    sys.exit(main())
