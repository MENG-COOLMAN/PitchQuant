# -*- coding: utf-8 -*-
"""R-POOL-BIG 宽池大球分级策略（2026-10-30 用户指令固化·数据驱动）

用户原话：「明确大球的场次，数据越明确越应该把 4、5、6 球放进宽池」

🔴 与回测的关系（重要·不冲突）：
   · 回测否决的是「改锚/改候选池上界来影响 Top2 排序」（全放宽 −0.60/−0.77pp·强制高分档 −0.24~−1.79pp）
   · 本策略只作用于 **宽池（展示池·不参与 Top2 排序）** → 零代价扩大覆盖
   · 数据依据：5-6 球累计概率 20-31%，但单比分仅 0.2-0.5% → **不适合占锚位，但完全适合进宽池**

分级（全部由本场 P(T≥k) 分布决定·禁写死）：
   L0 非大球      P(T≥4) < 35%           → 宽池无需强制档
   L1 大球强      P(T≥4) ≥ 35%           → 宽池必含 **4 球档**
   L2 大球很强    P(T≥5) ≥ 20%           → 宽池必含 **4 + 5 球档**
   L3 极强大球    P(T≥6) ≥ 12%           → 宽池必含 **4 + 5 + 6 球档**

用法:
  python data/tmp/big_pool_policy.py --o25 1.406          # 按 O2.5 查表出策略
  python data/tmp/big_pool_policy.py --o25 1.406 --pool "2:1,3:1,2:0,3:2,1:2"  # 同时校验宽池
"""
import argparse
import io
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

LEVELS = [
    # (level, 名称, 触发条件(lambda tail, line, o25), 必含档)
    # 🔴P52(2026-10-31 用户指令「增设超大球档位·研究设立超大球门槛·大球与超大球混在一起太泛化」)
    #   门槛全部来自 **Matches.csv 148,397 场（2005-2025）时间分割**（非拍脑袋）:
    #   L5 极超大球 O2.5≤1.30 / 均衡线≥3.9 → 均球 4.02 · P≥4 58.1% · P≥5 38.3%（n=914）
    #   L4 超大球   O2.5≤1.40 / 均衡线≥3.5 → 均球 3.55 · P≥4 47.6% · P≥5 28.8%（n=1938）
    #   L3 大球很强 O2.5≤1.60 / 均衡线≥3.1 → 均球 3.21 · P≥4 40.1% · P≥5 22.1%（n=13311）
    #   L2 大球     O2.5≤1.90 / 均衡线≥2.6 → 均球 2.80 · P≥4 30.7% · P≥5 15.1%（n=49827）
    #   L0 非大球   >1.90 / <2.6        → 均球 2.41 · P≥4 22.5%（n=82407）
    #   🔴超大球门槛 = **O2.5≤1.40**：train 均3.71/P≥4 51.0% vs test 均3.69/51.0%
    #     → Δ均 0.02 球 · ΔP≥4 0.0pp（5 个候选门槛里唯一完全稳定；≤1.30 档 Δ 2.6pp 略不稳，故单列顶层）
    ('L5', '极超大球', lambda tail, line, o25: ((o25 is not None and float(o25) <= 1.30)
                                              or (line is not None and float(line) >= 3.9)
                                              or tail[6] >= 0.20), [4, 5, 6, 7],
     'O2.5 ≤1.30 或 均衡线 ≥3.9 或 P(T≥6) ≥20%（均球 4.02·P≥4 58.1%）'),
    ('L4', '超大球', lambda tail, line, o25: ((o25 is not None and float(o25) <= 1.40)
                                            or (line is not None and float(line) >= 3.5)
                                            or tail[5] >= 0.28), [4, 5, 6],
     'O2.5 ≤1.40 或 均衡线 ≥3.5 或 P(T≥5) ≥28%（均球 3.55·P≥4 47.6%）'),
    ('L3', '大球很强', lambda tail, line, o25: ((o25 is not None and float(o25) <= 1.60)
                                            or (line is not None and float(line) >= 3.1)
                                            or tail[5] >= 0.20), [4, 5],
     'O2.5 ≤1.60 或 均衡线 ≥3.1 或 P(T≥5) ≥20%（均球 3.21·P≥4 40.1%）'),
    ('L2', '大球', lambda tail, line, o25: ((o25 is not None and float(o25) <= 1.90)
                                        or (line is not None and float(line) >= 2.6)
                                        or tail[4] >= 0.30), [4],
     'O2.5 ≤1.90 或 均衡线 ≥2.6 或 P(T≥4) ≥30%（均球 2.80）'),
    ('L1', '弱大球', lambda tail, line, o25: (tail[4] >= 0.35), [4],
     'P(T≥4) ≥35%（边缘兜底·无 O2.5/均衡线时）'),
]

# 各档典型比分（供宽池提示·按「该档内常见 + 双方进球优先」排序）
TYPICAL = {
    4: ['3:1', '2:2', '4:0', '1:3'],
    5: ['3:2', '4:1', '2:3', '1:4'],
    6: ['4:2', '3:3', '5:1', '2:4'],
    7: ['4:3', '5:2', '3:4', '2:5'],
}


def pmf_from_o25(o25):
    """O2.5 → 8 档 PMF（goal_count_table·148,396 场实测）"""
    import goal_count_table as GCT
    r = GCT.lookup(o25)
    p = r.get('p') or r.get('probs') or {}
    out = [0.0] * 8
    for k, v in (p or {}).items():
        try:
            kk = int(k)
        except (ValueError, TypeError):
            continue
        if 0 <= kk < 8:
            out[kk] = v if v <= 1 else v / 100
    s = sum(out)
    return [x / s for x in out] if s > 0 else None


def pmf_from_lam(lam, n=8):
    """本场 λ（六源融合）→ 泊松 PMF（比查表档位平均更精确·响应「数据越明确越放宽」）"""
    try:
        lam = float(lam)
    except (TypeError, ValueError):
        return None
    if not (0.3 < lam < 8):
        return None
    out = [math.exp(-lam) * lam ** k / math.factorial(k) for k in range(n)]
    s = sum(out)
    return [x / s for x in out] if s > 0 else None


RANK = {'L0': 0, 'L1': 1, 'L2': 2, 'L3': 3, 'L4': 4, 'L5': 5}


def _classify_one(pT, src, line=None, o25=None):
    if not pT:
        return None
    tail = {k: sum(pT[k:]) for k in range(len(pT))}
    for lv, name, cond, need, basis in LEVELS:
        if cond(tail, line, o25):
            return dict(level=lv, name=name, required=need, src=src,
                        basis='%s（P(T≥4)=%.1f%% / P(T≥5)=%.1f%% / P(T≥6)=%.1f%%）'
                              % (basis, tail[4] * 100, tail[5] * 100, tail[6] * 100),
                        tail={k: round(v, 4) for k, v in tail.items()})
    return dict(level='L0', name='非大球', required=[], src=src,
                basis='P(T≥4)=%.1f%% < 35%%（未达大球强）' % (tail[4] * 100),
                tail={k: round(v, 4) for k, v in tail.items()})


def classify(pT, pT_pois=None, line=None, o25=None):
    """双源分级：查表（档位平均）+ 本场 λ 泊松 → **取更严（更明确）者**
       🔴 用户指令「数据越明确越应该把 4/5/6 球放进宽池」→ λ 更贴合本场时以 λ 为准
    """
    cands = [c for c in (_classify_one(pT, '查表O2.5档', line, o25),
                         _classify_one(pT_pois, '本场λ泊松', line, o25)) if c]
    if not cands:
        return dict(level='L0', name='无法判定', required=[], basis='⚪无分布', tail={})
    cands.sort(key=lambda c: RANK[c['level']], reverse=True)
    best = cands[0]
    if len(cands) > 1:
        best['basis'] += ' ｜ 双源对比：' + ' vs '.join('%s(%s)' % (c['level'], c['src']) for c in cands)
    return best


def check_pool(pool, policy):
    """校验宽池是否覆盖 required 档；返回缺口"""
    got = set()
    for s in pool or []:
        try:
            h, a = [int(x) for x in str(s).replace('：', ':').split(':')]
        except (ValueError, AttributeError):
            continue
        got.add(h + a)
    miss = [t for t in policy['required'] if t not in got]
    return miss


def report(o25, pool=None, lam=None, line=None):
    pT = pmf_from_o25(o25)
    pol = classify(pT, pmf_from_lam(lam) if lam else None, line, o25)
    lines = []
    lines.append('🔴 宽池大球策略(R-POOL-BIG·P48 五级·2026-10-31 用户指正「只有大球没有超大球」)')
    lines.append('   O2.5=%.3f%s → **%s %s**'
                 % (o25, ('·均衡线%.2f' % line) if line is not None else '·无均衡线(仅O2.5单档)',
                    pol['level'], pol['name']))
    lines.append('   依据: %s' % pol['basis'])
    if pol['required']:
        lines.append('   → 宽池**必含**进球档: %s 球' % ' / '.join(str(t) for t in pol['required']))
        for t in pol['required']:
            lines.append('      %d 球典型比分（该档占 %.1f%%）: %s'
                         % (t, (pol['tail'].get(t, 0) - pol['tail'].get(t + 1, 0)) * 100,
                            ' / '.join(TYPICAL[t])))
        lines.append('   🔴 铁律: 宽池**不占锚位**·不参与 Top2 排序 → 只扩覆盖·零代价')
        lines.append('   🔴 禁: 因宽池扩档而改动主锚/次锚（回测证明改锚 −0.24~−1.79pp）')
    else:
        lines.append('   → 非大球场·宽池无强制档（按常规 2-4 个覆盖）')
    if pool:
        miss = check_pool(pool, pol)
        if miss:
            lines.append('   ❌ **宽池缺档**: %s 球 — 须补入: %s'
                         % ('/'.join(str(t) for t in miss),
                            ' ; '.join('%d球建议 %s' % (t, '/'.join(TYPICAL[t][:3])) for t in miss)))
        else:
            lines.append('   ✅ 宽池已覆盖全部必含档（%s）' % '/'.join(str(t) for t in pol['required']))
    return '\n'.join(lines), pol


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--o25', type=float, required=True, help='本场 O2.5 赔率')
    ap.add_argument('--pool', default=None, help='宽池比分，逗号分隔，如 "2:1,3:1,3:2"')
    ap.add_argument('--lam', type=float, default=None, help='本场 λ_final（六源·更精确·优先于查表）')
    a = ap.parse_args()
    pool = [x.strip() for x in a.pool.split(',')] if a.pool else None
    txt, pol = report(a.o25, pool, a.lam)
    print(txt)
    if '--json' in sys.argv:
        print(json.dumps(pol, ensure_ascii=False, indent=2))


# ══════════════════════════════════════════════════════════════════
# R-ANCHOR-BIG（2026-10-30 用户指令「也必须改锚定」·执行并标注代价）
# ══════════════════════════════════════════════════════════════════
ANCHOR_RULES = {
    # level: (次锚最低进球档表达式, 说明, 实测代价)
    'L5': ('ceil(E+1.0)', '次锚须 ≥ ⌈E+1.0⌉（极超大球·均球 4.02·P≥5 38.3%）',
           '未单独回测（P48 口径实测代价 −0.09~−1.79pp 区间内）'),
    'L4': ('ceil(E+0.5)', '次锚须 ≥ ⌈E+0.5⌉（超大球·均球 3.55·P≥5 28.8%）',
           '未单独回测（同上区间）'),
    'L3': ('ceil(E+0.5)', '次锚须 ≥ ⌈E+0.5⌉（大球很强·均球 3.21）',
           '回测代价 −0.09 ~ −0.64pp（over≥58% / O2.5≤1.50 子集）'),
    'L2': ('0', '次锚不受限（仅宽池含 4 球档）', '无代价'),
    'L1': ('0', '次锚不受限（仅宽池含 4 球档）', '无代价'),
    'L0': ('0', '非大球·次锚不受限', '无代价'),
}


# 🔴2026-11-01 主锚最低球数（P52 六级分级·原表只有「次锚」要求 → 主锚无约束 = 假实现）
#   用户质疑「极端大球你还主锚 2:1」「你不是有六级分档吗」→ 分级必须约束主锚，不能只管次锚
FIRST_MIN = {'L5': 4, 'L4': 3, 'L3': 3, 'L2': 2, 'L1': 0, 'L0': 0}


def first_requirement(level):
    """→ (主锚最低总进球, 说明)。L0/L1 返回 0 = 不受限"""
    n = FIRST_MIN.get(str(level or '').upper(), 0)
    if not n:
        return 0, '主锚不受限（%s）' % (level or '?')
    return n, '主锚须 ≥ %d 球（%s 档·分级驱动）' % (n, level)


def level_from_line(line=None, o25=None):
    """均衡线 / O2.5 → 层级（🔴P52 单一入口·供 calc_all / anchor_select 调用）

    🔴为什么必须是函数：2026-10-31 端到端审计发现
      `anchor_select` 内部**自己复制了一套**「max(主锚+1, round(均衡线))」硬编码，
      与 span_requirement 形成**双副本** → 改分级对锚零影响（P52 首版即此病）。
      统一从此函数取 level，禁调用方各自写 if-else 链。
    """
    try:
        _z = {k: 0.0 for k in range(8)}
        for _lv, _nm, _cond, _need, _basis in LEVELS:
            if _cond(_z, line, o25):
                return _lv
        return 'L0'
    except Exception:
        return 'L0'


_DEF_POS = ('中后卫', '中卫', '后卫', '后腰', '门将', '清道夫', '边卫', 'CB', 'LB', 'RB', 'DM', 'GK')


def def_dual_from_lists(h_list, a_list):
    """两侧伤停清单 → (是否「双方防线各 ≥2 人伤」, 主防线伤数, 客防线伤数)

    🔴2026-11-03 O-BIG-1（case317 实证）：伤停清单形如 ``"中后卫,未知;后腰,未知"``，
      只数**防线/后腰/门将**位（前锋/中场伤停不计入防守侧）。
    """
    def _cnt(lst):
        if not lst:
            return 0
        items = lst if isinstance(lst, (list, tuple)) else str(lst).split(';')
        n = 0
        for it in items:
            s = str(it).strip()
            if not s:
                continue
            pos = s.split(',')[0].strip()
            if pos in _DEF_POS or any(k in pos for k in ('后卫', '后腰', '中卫', '门将', '边卫')):
                n += 1
        return n
    nh, na = _cnt(h_list), _cnt(a_list)
    return (nh >= 2 and na >= 2), nh, na


def required_bins(level, def_dual=False):
    """层级 → 宽池必含进球档（如 L5 → [4,5,6,7]）

    🔴2026-11-03 O-BIG-1（case317 萨索洛 2:4 实证·用户裁定「两个都修」）：
      **L3 大球很强 + 双方防线各 ≥2 人伤 → 宽池扩 6 球**（[4,5] → [4,5,6]）
      **L2 大球 + 双伤 → 补 5 球**（[4] → [4,5]·不跳档·守 P27 谱系连续性）
      依据: 「大球强 + 双方防线均重伤」是 6 球高发场（本场正是 2:4）；
      **宽池不占锚位 → 零代价**（R-POOL-BIG 铁律：不改主锚/次锚）。
    """
    _need = []
    for _lv, _nm, _cond, _need0, _basis in LEVELS:
        if _lv == str(level):
            _need = list(_need0)
            break
    if def_dual:
        if str(level) == 'L3' and 6 not in _need:
            _need = sorted(set(_need) | {6})     # [4,5] → [4,5,6]
        elif str(level) == 'L2' and 5 not in _need:
            _need = sorted(set(_need) | {5})     # [4] → [4,5]
    return _need


def span_requirement(line, level, a1_goals):
    """🔴P47/P52 **跨度式**次锚要求（数据驱动·不硬限主锚）

    L5 极超大球 → max(主锚+2, round(均衡线)+1)   （均球 4.02·P≥5 38.3%）
    L4 超大球   → max(主锚+1, round(均衡线))      （均球 3.55·P≥5 28.8%）
    L3 大球很强 → max(主锚+1, round(均衡线)-1)    （均球 3.21）
    L2 大球及以下 → 不限（仅宽池）
    理由: 主锚保命中(低位) · 次锚覆盖市场指向的上沿；**超大球单独加力度**（用户「大球与超大球混在一起太泛化」）
    """
    try:
        if line is None or float(line) < 2.6:
            return 0
        _lv = str(level)
        if _lv == 'L5':
            return max(int(a1_goals) + 2, int(round(float(line))) + 1)
        if _lv == 'L4':
            return max(int(a1_goals) + 1, int(round(float(line))))
        if _lv == 'L3':
            return max(int(a1_goals) + 1, int(round(float(line))) - 1)
        return 0
    except (TypeError, ValueError):
        return 0


def anchor_requirement(E, policy):
    """返回 (次锚最低进球档, 说明, 代价) —— 供 calc_all / 人工消费"""
    lv = policy.get('level', 'L0')
    expr, note, cost = ANCHOR_RULES.get(lv, ('0', '', ''))
    if expr == '0':
        return 0, note, cost
    import math as _m
    need = int(_m.ceil(E + 0.5))
    # 上限保护：不得高于 E+2（防死锚）
    need = min(need, int(_m.ceil(E)) + 2)
    return need, note, cost


# 🔴P40 DEPRECATED（2026-10-30 批次5）: 全库零调用。报告函数·未接线（CLI --report 可手调）
#   → 保留备查·不接入
def anchor_report(E, policy):
    need, note, cost = anchor_requirement(E, policy)
    if need <= 0:
        return '   🔹 R-ANCHOR-BIG: %s（%s）' % (note or '次锚不受限', policy.get('level'))
    return ('   🔹 R-ANCHOR-BIG(次锚上探): 本场 E=%.2f → **次锚须 ≥ %d 球** ｜ %s\n'
            '      代价：%s ｜ 🔴 主锚不动（保主命中率）' % (E, need, note, cost))
