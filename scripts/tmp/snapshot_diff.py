# -*- coding: utf-8 -*-
"""全档时点 diff（2026-11-02 · 用户裁定 dec-89ecf96e243c7665）

🔴 为什么需要（真实事故·不是假想）
    `snapshot_save._extract()` 每场只返回 ML 一行 + **均衡档亚盘一条** + **O2.5 一条** + 波胆 1-1 一条。
    用它做「两时点对比」→ 只要变动不落在这 4 个点上，就会得出「完全没变」。
    实测 2026-11-02（T0 06:53 vs T1 18:05·五大联赛 5 场）：
        · 我按 _extract 对比 → 报「4 场零变动」
        · raw 全量 diff → **5 场全部有变动**：
            纽卡   ML 变 + 亚盘 15/15 全动 + 大小球 7 档 + 单队进球 主10/客9 + 波胆 11 档
            亚特兰大 主市场未动 + 单队进球 主10/客5 + 波胆 15 档
            其余三场 主市场未动 + 波胆 4-9 档（拉科鲁尼亚 1:1 6→5.5 = 平局被打压）
    → 单截面 ≠ 全量。本模块按【市场名】逐档对齐比较 raw_1xbet 全量。

设计铁律
  ① 只**标注**不改判定：不写任何打分权重、不反转方向（与 P30/P46 同级纪律）
  ② 占位档不计方向：1xbet Correct Score 固定 120 档中约 100 档赔率恰=100 为占位 → 过滤
  ③ 缺失/异常 → 三态返回，绝不静默当「没变」
  ④ 档位按 key 对齐（hdp / line / label），不按数组下标（档位会增删）

用法
    python data/tmp/snapshot_diff.py                       # 最近一份快照 vs 上一份（全部场次）
    python data/tmp/snapshot_diff.py --home X --away Y      # 指定场次跨全部时点
    python data/tmp/snapshot_diff.py --file <snap.json>     # 指定「本时点」文件
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

# 模型真正消费的市场（角球/双重机会等不参与判定 → 只做记录，不产生信号）
CORE = ['ML', 'Double Chance', 'Spread', 'Totals',
        'Both Teams To Score', 'Team Total Home', 'Team Total Away', 'Correct Score']
SIGNAL_MKTS = ['ML', 'Spread', 'Totals', 'Team Total Home', 'Team Total Away', 'Correct Score']

PLACEHOLDER = 100.0   # CS 占位档标志值
EPS = 1e-9


# ────────────────────────── 基础工具 ──────────────────────────
def markets(raw):
    """raw_1xbet → {市场名: market_dict}"""
    out = {}
    for m in ((raw or {}).get('bookmakers', {}) or {}).get('1xbet', []) or []:
        nm = m.get('name')
        if nm:
            out[nm] = m
    return out


def _norm(x):
    """把一档赔率归一成 (key, signature)，按 key 对齐（不用数组下标）。"""
    if isinstance(x, dict):
        if x.get('label') is not None:
            return ('L:%s' % x['label'],
                    tuple(sorted((k, str(v)) for k, v in x.items() if k != 'label')))
        if 'hdp' in x:
            return ('H:%s' % x['hdp'],
                    tuple(sorted((k, str(v)) for k, v in x.items() if k != 'hdp')))
        return ('K:%s' % ','.join(sorted(x.keys())),
                tuple(sorted((k, str(v)) for k, v in x.items())))
    if isinstance(x, list):
        head = str(x[0]) if x else '?'
        return ('L:%s' % head, tuple(str(v) for v in x[1:]))
    return ('?', str(x))


def _f(v):
    try:
        return float(str(v).replace(',', ''))
    except Exception:
        return None


def _tiers(mkt):
    """market → {key: (sig, raw_item)}"""
    out = {}
    for it in (mkt or {}).get('odds', []) or []:
        k, sig = _norm(it)
        out[k] = (sig, it)
    return out


def _is_placeholder(item):
    """波胆占位档：单值且=100（或 >=100 视为未定价）"""
    vals = []
    if isinstance(item, dict):
        vals = [_f(v) for k, v in item.items() if k != 'label']
    elif isinstance(item, list):
        vals = [_f(v) for v in item[1:]]
    vals = [v for v in vals if v is not None]
    return bool(vals) and all(v >= PLACEHOLDER - EPS for v in vals)


# ────────────────────────── 单市场 diff ──────────────────────────
def diff_market(m0, m1):
    """→ {'changed':n,'added':n,'removed':n,'detail':[(key,a,b)],'total':n}"""
    t0, t1 = _tiers(m0), _tiers(m1)
    changed, detail = 0, []
    for k in t1:
        if k in t0:
            if t0[k][0] != t1[k][0]:
                changed += 1
                detail.append((k, _vals(t0[k][1]), _vals(t1[k][1])))
    added = len([k for k in t1 if k not in t0])
    removed = len([k for k in t0 if k not in t1])
    return {'changed': changed, 'added': added, 'removed': removed,
            'detail': detail, 'total': max(len(t0), len(t1)),
            'n0': len(t0), 'n1': len(t1)}


def _vals(item):
    if isinstance(item, dict):
        if item.get('label') is not None:
            return [item[k] for k in item if k != 'label']
        if 'hdp' in item:
            return [item[k] for k in item if k != 'hdp']
        return [item[k] for k in ('home', 'draw', 'away') if k in item]
    if isinstance(item, list):
        return list(item[1:])
    return [item]


# ────────────────────────── 方向性信号 ──────────────────────────
def _ml_pct(m0, m1):
    o0 = (_tiers(m0).get('K:away,draw,home') or _tiers(m0).get('K:draw,home,away') or (None, None))[1]
    o1 = (_tiers(m1).get('K:away,draw,home') or _tiers(m1).get('K:draw,home,away') or (None, None))[1]
    if not o0 or not o1:
        # 退化：直接取首档
        l0 = ((m0 or {}).get('odds') or [{}])[0]
        l1 = ((m1 or {}).get('odds') or [{}])[0]
        o0, o1 = l0, l1
    out = {}
    for k, lab in (('home', '主'), ('draw', '平'), ('away', '客')):
        a, b = _f(o0.get(k)), _f(o1.get(k))
        if a and b:
            out[lab] = round((b - a) / a * 100, 1)
    return out


def _spread_signal(m0, m1):
    """亚盘：找两时点各自的最均衡档（|主-客| 最小），比较主/客水位；并统计全档主队赔率方向。"""
    def bal(m):
        best, bd = None, 1e9
        for it in ((m or {}).get('odds') or []):
            h, a = _f(it.get('home')), _f(it.get('away'))
            if h and a:
                d = abs(h - a)
                if d < bd:
                    bd, best = d, (it.get('hdp'), h, a)
        return best

    b0, b1 = bal(m0), bal(m1)
    res = {'hdp0': None, 'hdp1': None, '主水': None, '客水': None,
           'up_n': 0, 'down_n': 0, 'hdp_moved': False}
    if b0 and b1:
        res.update(hdp0=b0[0], hdp1=b1[0])
        try:
            _moved = abs(float(b0[0]) - float(b1[0])) > 1e-9
        except Exception:
            _moved = str(b0[0]) != str(b1[0])
        res['hdp_moved'] = _moved
        if not _moved:
            if b0[1] and b1[1]:
                res['主水'] = round((b1[1] - b0[1]) / b0[1] * 100, 1)
            if b0[2] and b1[2]:
                res['客水'] = round((b1[2] - b0[2]) / b0[2] * 100, 1)
        else:
            # 🔴 盘口切换（如 平手 → 主让 0.25）时，两时点的「均衡档」是**不同档位** →
            #   直接比水位 = 比不同档位 → 假剪刀差（实测洛里昂 主水 +15.4%/客水 −13.5%
            #   推出「亚盘偏客」，而同场「全档 13 档主降」明确偏主 → 自相矛盾）。
            #   修：改**同档对齐**（用本时点均衡档在两时点各自的水位比）。
            k = 'H:%s' % b1[0]
            t0_, t1_ = _tiers(m0), _tiers(m1)
            if k in t0_ and k in t1_:
                it0, it1 = t0_[k][1], t1_[k][1]
                h0, h1 = _f(it0.get('home')), _f(it1.get('home'))
                a0, a1 = _f(it0.get('away')), _f(it1.get('away'))
                if h0 and h1:
                    res['主水'] = round((h1 - h0) / h0 * 100, 1)
                if a0 and a1:
                    res['客水'] = round((a1 - a0) / a0 * 100, 1)
    # 全档主队赔率方向（同向 = 盘口整体移动）
    t0, t1 = _tiers(m0), _tiers(m1)
    for k in t1:
        if k in t0:
            v0, v1 = _vals(t0[k][1]), _vals(t1[k][1])
            if len(v0) >= 2 and len(v1) >= 2:
                a0, a1 = _f(v0[0]), _f(v1[0])
                if a0 and a1:
                    if a1 < a0 - EPS:
                        res['down_n'] += 1
                    elif a1 > a0 + EPS:
                        res['up_n'] += 1
    return res


def _totals_signal(m0, m1):
    """总进球：全档 over 的平均变动%（负 = 更看好大球）"""
    ds = []
    t0, t1 = _tiers(m0), _tiers(m1)
    for k in t1:
        if k in t0:
            a0 = _f((t0[k][1] or {}).get('over'))
            a1 = _f((t1[k][1] or {}).get('over'))
            if a0 and a1:
                ds.append((a1 - a0) / a0 * 100)
    if not ds:
        return {'n': 0, 'avg': None}
    return {'n': len(ds), 'avg': round(sum(ds) / len(ds), 2)}


def _tt_signal(m0, m1):
    """单队进球：该队各档 over 平均变动%（负 = 该队进球预期上调）"""
    ds = []
    t0, t1 = _tiers(m0), _tiers(m1)
    for k in t1:
        if k in t0:
            v0, v1 = _vals(t0[k][1]), _vals(t1[k][1])
            if len(v0) >= 2 and len(v1) >= 2:
                a0, a1 = _f(v0[0]), _f(v1[0])
                if a0 and a1:
                    ds.append((a1 - a0) / a0 * 100)
    if not ds:
        return {'n': 0, 'avg': None}
    return {'n': len(ds), 'avg': round(sum(ds) / len(ds), 2)}


CS_DIRECT_MAX = 18.0   # 波胆方向标签只看低赔档（隐含概率 ≥ ~5.5%）

# 🔴 阈值为什么从 26 收到 18（2026-11-02 实跑抓）：
#   26 时洛里昂场同时给「波胆看好 1-3」和「看好 3-1」（客队大胜 + 主队大胜都被"看好"）
#   = 大比分档薄盘抖动，方向自相矛盾 → 收紧到 18，只保留主流比分档
#   （主干 1:0/1:1/2:1/0:1/2:0 通常在 6-14；纽卡 3-1 13→14 这类真信号仍在范围内）


def _cs_signal(m0, m1, max_price=CS_DIRECT_MAX):
    """波胆：降水档（被看好）/ 升水档（被看淡）

    🔴 只对低赔档（默认 ≤26.0·隐含 ≥~4%）产出方向标签 ——
       大比分档（如 2-4=75、4-3=90）是薄盘，赔率抖动 ±10-15% 属噪声；
       拿它当方向会得出「波胆看好客队大胜」这种反直觉结论（实测纽卡 2-4 75→65 即此类）。
    """
    t0, t1 = _tiers(m0), _tiers(m1)
    down, up, noise = [], [], 0
    for k in t1:
        if k not in t0:
            continue
        it0, it1 = t0[k][1], t1[k][1]
        if _is_placeholder(it0) or _is_placeholder(it1):
            continue
        a0, a1 = _f(_vals(it0)[0] if _vals(it0) else None), _f(_vals(it1)[0] if _vals(it1) else None)
        if not a0 or not a1:
            continue
        p = (a1 - a0) / a0 * 100
        if abs(p) < 3.0:      # 3% 以内视为抖动
            continue
        if min(a0, a1) > max_price:   # 薄盘大比分档 → 只计数·不给方向
            noise += 1
            continue
        lab = k[2:] if k.startswith('L:') else k
        if p < 0:
            down.append((lab, a0, a1, round(p, 1)))
        else:
            up.append((lab, a0, a1, round(p, 1)))
    down.sort(key=lambda x: x[3])
    up.sort(key=lambda x: -x[3])
    return {'down': down, 'up': up, 'n_down': len(down), 'n_up': len(up), 'noise_n': noise}


def signals_of(r0, r1):
    """一场比赛的综合变动信号（只标注·不改判定）"""
    m0, m1 = markets(r0), markets(r1)
    ml = _ml_pct(m0.get('ML'), m1.get('ML'))
    sp = _spread_signal(m0.get('Spread'), m1.get('Spread'))
    to = _totals_signal(m0.get('Totals'), m1.get('Totals'))
    tth = _tt_signal(m0.get('Team Total Home'), m1.get('Team Total Home'))
    tta = _tt_signal(m0.get('Team Total Away'), m1.get('Team Total Away'))
    cs = _cs_signal(m0.get('Correct Score'), m1.get('Correct Score'))

    tags = []
    h, a = ml.get('主'), ml.get('客')
    if h is not None and a is not None:
        if h <= -2 and a >= 2:
            tags.append('主队加强')
        elif h >= 2 and a <= -2:
            tags.append('客队加强')
    if sp.get('hdp_moved'):
        # 盘口切换 → 用「盘口移动方向」判偏向（水位已改同档对齐·不再据此判偏主/偏客）
        try:
            _gap = float(sp.get('hdp1')) - float(sp.get('hdp0'))
        except Exception:
            _gap = 0.0
        if _gap < 0:
            tags.append('盘口升级(主队加让·偏主)')
        elif _gap > 0:
            tags.append('盘口降级(主队减让·偏客)')
    elif sp.get('主水') is not None and sp.get('客水') is not None:
        if sp['主水'] <= -1.5 and sp['客水'] >= 1.5:
            tags.append('亚盘偏主')
        elif sp['主水'] >= 1.5 and sp['客水'] <= -1.5:
            tags.append('亚盘偏客')
    if sp.get('down_n') is not None:
        _sp_tot = sp['down_n'] + sp['up_n']
        # 🔴 样本门槛（2026-11-02 实跑抓）：变动档数 <4 时不判「全档」方向 ——
        #   实测萨索洛亚盘只动 2/17 档却被判「全档偏客」，而同场波胆在买 3-2/2-1（主队胜）
        #   → 2 档抖动 ≠ 全档移动。全档判向须 ≥4 档参与且单向占比 ≥70%。
        if _sp_tot >= 4:
            if sp['down_n'] >= 0.7 * _sp_tot:
                tags.append('亚盘全档偏主')
            elif sp['up_n'] >= 0.7 * _sp_tot:
                tags.append('亚盘全档偏客')
    if to.get('avg') is not None:
        if to['avg'] <= -1.5:
            tags.append('大球加强')
        elif to['avg'] >= 1.5:
            tags.append('小球加强')
    if tth.get('avg') is not None and tth['avg'] <= -1.5:
        tags.append('主队进球上调')
    if tta.get('avg') is not None and tta['avg'] <= -1.5:
        tags.append('客队进球上调')
    if cs['down']:
        tags.append('波胆看好%s' % '/'.join(x[0] for x in cs['down'][:2]))
    if cs['up']:
        tags.append('波胆看淡%s' % '/'.join(x[0] for x in cs['up'][:2]))

    core_moved = bool(ml) and (abs(ml.get('主', 0)) >= 2 or abs(ml.get('客', 0)) >= 2)
    return {'ml': ml, 'spread': sp, 'totals': to, 'tt_home': tth, 'tt_away': tta,
            'cs': cs, 'tags': tags, 'core_moved': core_moved,
            'summary': ' ｜ '.join(tags) if tags else '无方向性变动'}


def diff_pair(r0, r1):
    """一场比赛的分市场明细"""
    m0, m1 = markets(r0), markets(r1)
    out = {}
    for nm in CORE:
        if nm in m0 or nm in m1:
            out[nm] = diff_market(m0.get(nm), m1.get(nm))
    out['_signals'] = signals_of(r0, r1)
    return out


# ────────────────────────── 快照级入口 ──────────────────────────
def _snapshots_dir(here=None):
    base = here or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'snapshots')


def _list_snaps(d):
    """快照列表·按 **mtime** 升序（🔴 禁字典序）

    🔴 2026-11-02 实跑踩坑：`sorted(fs)` 字典序会把 `prestep_seriea_t3_20261027_*.json`
       排在 `prestep_20261102_*.json` 之后（'s' > '2'）→ 基线取到 10-27 的旧文件
       → 场次全对不上 → `diff_against_prev` 返回 0 场 → 打印「无上一时点基线」= 假三态。
       故一律按文件修改时间排序。
    """
    if not os.path.isdir(d):
        return []
    fs = [f for f in os.listdir(d) if f.startswith('prestep_') and f.endswith('.json')]
    fs.sort(key=lambda f: os.path.getmtime(os.path.join(d, f)))
    return fs


def _prev_snapshot(here=None):
    """snapshots/ 里**时间上**最新的 prestep 快照（= 上一时点；调用须在本时点落盘之前）"""
    d = _snapshots_dir(here)
    fs = _list_snaps(d)
    if not fs:
        return None, []
    return os.path.join(d, fs[-1]), fs


LAST_BASELINE = {}


def _has_movement(dmap):
    """该批 diff 是否含任何真实变动（档位变动/增删）"""
    for v in (dmap or {}).values():
        for k, m in v.items():
            if k == '_signals':
                continue
            if m.get('changed') or m.get('added') or m.get('removed'):
                return True
    return False


def _diff_vs(path, rows):
    try:
        prev = json.load(open(path, encoding='utf-8'))
    except Exception:
        return {}
    idx = {}
    for g in prev.get('games', []):
        idx[(g.get('home'), g.get('away'))] = g.get('raw_1xbet') or {}
    out = {}
    for r in rows:
        raw0 = idx.get((r.get('home'), r.get('away')))
        raw1 = r.get('_raw')
        if not raw0 or not raw1:
            continue
        try:
            out[(r.get('home'), r.get('away'))] = diff_pair(raw0, raw1)
        except Exception:
            continue
    return out


def _saved_at(path):
    try:
        return json.load(open(path, encoding='utf-8')).get('saved_at')
    except Exception:
        return None


def diff_against_prev(rows, here=None, lookback=6):
    """rows（含 home/away/_raw 的 prestep 行）vs 快照基线 → {(home,away): {signals, markets}}

    🔴2026-11-02 加**回溯**（实跑抓）：原实现只比「时间上最近一份」→
      若两次 prestep 只隔几分钟且市场没动，摘要就是「无方向性变动」，
      把几小时前那轮真实变动**丢掉**了（实测 21:14→21:18 仅隔 3.5 分钟 → 五场全「无变动」，
      而 18:14→21:14 其实有强信号：纽卡/拉科鲁尼亚/洛里昂三场主队加强 + 洛里昂盘口升级）。
      现改为：从新到旧最多回溯 lookback 份，取**第一个真的有变动**的基线；
      全都没动 → 用最新那份 + 记 `no_move_across`（如实说明「最近 N 个时点均无变动」）。
    基线信息写入模块级 LAST_BASELINE 供调用方打印（不改返回结构，向后兼容）。
    三态：无任何快照 / 场次不匹配 → 该场不进返回（调用方按「无基线」标注）。
    """
    d = _snapshots_dir(here)
    fs = _list_snaps(d)
    if not fs:
        LAST_BASELINE.clear()
        return {}
    paths = [os.path.join(d, f) for f in fs[-max(1, lookback):]][::-1]   # 新 → 旧
    fallback, fallback_path = None, None
    for p in paths:
        cur = _diff_vs(p, rows)
        if not cur:
            continue
        if fallback is None:
            fallback, fallback_path = cur, p
        if _has_movement(cur):
            LAST_BASELINE.clear()
            LAST_BASELINE.update(path=p, saved_at=_saved_at(p), lookback_used=paths.index(p) + 1)
            return cur
    LAST_BASELINE.clear()
    if fallback is not None:
        LAST_BASELINE.update(path=fallback_path, saved_at=_saved_at(fallback_path),
                             lookback_used=1, no_move_across=len(paths))
    return fallback or {}


def fmt_one(name_h, name_a, dp, base_at='上一时点', now_at='本时点'):
    """单场格式化（中文友好）"""
    sig = dp.get('_signals') or {}
    L = []
    moved = [nm for nm in CORE if dp.get(nm) and (dp[nm]['changed'] or dp[nm]['added'] or dp[nm]['removed'])]
    head = '🔴' if sig.get('core_moved') else ('🟡' if moved else '⚪')
    L.append('%s %s vs %s' % (head, name_h, name_a))
    if not moved:
        L.append('   全档无变动（%s → %s 逐档一致）' % (base_at, now_at))
        return '\n'.join(L)
    for nm in moved:
        d = dp[nm]
        extra = []
        if d['added']:
            extra.append('+%d 档' % d['added'])
        if d['removed']:
            extra.append('-%d 档' % d['removed'])
        L.append('   %-20s 变动 %d/%d 档%s' % (nm, d['changed'], d['total'],
                                              ('（%s）' % ' '.join(extra)) if extra else ''))
    ml = sig.get('ml') or {}
    if ml:
        L.append('   1x2：主 %+.1f%% ｜ 平 %+.1f%% ｜ 客 %+.1f%%' %
                 (ml.get('主', 0), ml.get('平', 0), ml.get('客', 0)))
    sp = sig.get('spread') or {}
    if sp.get('hdp_moved'):
        L.append('   亚盘：均衡档 %s→%s ⚠️**盘口切换**（水位改同档对齐·禁跨档比）｜ 同档主水 %s 客水 %s ｜ 全档主降 %d / 主升 %d'
                 % (sp.get('hdp0'), sp.get('hdp1'),
                    ('%+.1f%%' % sp['主水']) if sp.get('主水') is not None else '—',
                    ('%+.1f%%' % sp['客水']) if sp.get('客水') is not None else '—',
                    sp.get('down_n', 0), sp.get('up_n', 0)))
    elif sp.get('主水') is not None:
        L.append('   亚盘：均衡档 %s→%s ｜ 主水 %+.1f%% 客水 %+.1f%% ｜ 全档主降 %d / 主升 %d'
                 % (sp.get('hdp0'), sp.get('hdp1'), sp.get('主水'),
                    sp.get('客水') if sp.get('客水') is not None else 0.0,
                    sp.get('down_n', 0), sp.get('up_n', 0)))
    to = sig.get('totals') or {}
    if to.get('avg') is not None:
        L.append('   总进球：全档 over 均值 %+.2f%%（%d 档·负=更看大球）' % (to['avg'], to['n']))
    th, ta = (sig.get('tt_home') or {}), (sig.get('tt_away') or {})
    if th.get('avg') is not None or ta.get('avg') is not None:
        L.append('   单队进球：主 %s（%s 档）｜ 客 %s（%s 档）·负=该队进球预期上调'
                 % (('%+.2f%%' % th['avg']) if th.get('avg') is not None else '—', th.get('n', 0),
                    ('%+.2f%%' % ta['avg']) if ta.get('avg') is not None else '—', ta.get('n', 0)))
    cs = sig.get('cs') or {}
    if cs.get('down'):
        L.append('   波胆看好（降水≥3%%·低赔档）：%s' %
                 ' · '.join('%s %.2f→%.2f(%+.1f%%)' % x for x in cs['down'][:4]))
    if cs.get('up'):
        L.append('   波胆看淡（升水≥3%%·低赔档）：%s' %
                 ' · '.join('%s %.2f→%.2f(%+.1f%%)' % x for x in cs['up'][:3]))
    if cs.get('noise_n'):
        L.append('   （另 %d 个大比分档（赔率>%.0f）有抖动 = 薄盘噪声·不计方向）'
                 % (cs['noise_n'], CS_DIRECT_MAX))
    L.append('   ➡️ %s' % sig.get('summary', '—'))
    return '\n'.join(L)


def fmt_batch(dmap, base_at='上一时点', now_at='本时点'):
    if not dmap:
        return '⚪ 全档时点 diff：无上一时点基线（首次采集·仅本时点）'
    L = ['', '=' * 100,
         '🔴 全档时点变动（snapshot_diff·%s → %s·按市场逐档对比 raw 全量）' % (base_at, now_at),
         '   🔴=主方向市场动 ｜ 🟡=仅次级市场动（波胆/单队进球/角球）｜ ⚪=逐档一致',
         '   🔴 铁律：本块只标注·不改方向分/比分分（分数仍以 1x2/让球/O2.5/ELO/Form 计算）',
         '=' * 100]
    for (h, a), dp in dmap.items():
        L.append(fmt_one(h, a, dp, base_at, now_at))
        L.append('')
    hot = [(k, v['_signals']['summary']) for k, v in dmap.items() if v.get('_signals', {}).get('tags')]
    if hot:
        L.append('📌 方向性变动汇总（供人工判断·不进分数）：')
        for (h, a), s in hot:
            L.append('   · %s vs %s：%s' % (h, a, s))
    return '\n'.join(L)


# ────────────────────────── CLI ──────────────────────────
def _load(path):
    return json.load(open(path, encoding='utf-8'))


def cmd_latest(file_path=None, home=None, away=None):
    d = _snapshots_dir()
    fs = _list_snaps(d)          # 🔴 mtime 排序（禁字典序·见 _list_snaps 注释）
    if len(fs) < 2 and not file_path:
        print('⚪ 快照不足 2 份（当前 %d）→ 无法做时点 diff（三态·非「无变动」）' % len(fs))
        return 1
    cur = file_path or os.path.join(d, fs[-1])
    if file_path:
        # 🔴传 --file 时必须排除自身：否则自己比自己 → 恒报「无变动」= 假绿
        _base = os.path.basename(cur)
        if _base in fs:
            _i = fs.index(_base)
            prevs = [os.path.join(d, f) for f in fs[:_i]]
        else:
            _mt = os.path.getmtime(cur)
            prevs = [os.path.join(d, f) for f in fs
                     if os.path.getmtime(os.path.join(d, f)) < _mt]
    else:
        prevs = [os.path.join(d, f) for f in fs[:-1]]
    cur_d = _load(cur)
    prev_path = prevs[-1] if prevs else None
    if not prev_path:
        print('⚪ 无上一时点')
        return 1
    prev_d = _load(prev_path)
    idx = {(g.get('home'), g.get('away')): g.get('raw_1xbet') or {}
           for g in prev_d.get('games', [])}
    out = {}
    for g in cur_d.get('games', []):
        k = (g.get('home'), g.get('away'))
        if home and away and k != (home, away):
            continue
        raw0 = idx.get(k)
        if not raw0:
            continue
        out[k] = diff_pair(raw0, g.get('raw_1xbet') or {})
    print(fmt_batch(out, prev_d.get('saved_at', prev_path), cur_d.get('saved_at', cur)))
    print('\n📄 基线: %s' % os.path.basename(prev_path))
    print('📄 本点: %s' % os.path.basename(cur))
    return 0


def cmd_all_points(home, away):
    """某场跨全部时点的赔率链（ML/O2.5/均衡档）"""
    d = _snapshots_dir()
    fs = _list_snaps(d)          # 🔴 mtime 排序（禁字典序）
    rows = []
    for f in fs:
        try:
            snap = _load(os.path.join(d, f))
        except Exception:
            continue
        for g in snap.get('games', []):
            if (g.get('home'), g.get('away')) == (home, away):
                mk = markets(g.get('raw_1xbet'))
                ml = _ml_pct(mk.get('ML'), mk.get('ML'))
                it0 = ((mk.get('ML') or {}).get('odds') or [{}])[0]
                to = ((mk.get('Totals') or {}).get('odds') or [])
                o25 = next((_f(x.get('over')) for x in to if _f(x.get('hdp')) == 2.5), None)
                rows.append((snap.get('saved_at'), _f(it0.get('home')), _f(it0.get('draw')),
                             _f(it0.get('away')), o25, os.path.basename(f)))
    if not rows:
        print('⚪ 该场无任何快照'); return 1
    print('%s vs %s 跨时点链（%d 点）' % (home, away, len(rows)))
    print('%-21s %-8s %-8s %-8s %-8s' % ('时点', '主', '平', '客', 'O2.5'))
    for r in rows:
        print('%-21s %-8s %-8s %-8s %-8s  %s' % (r[0], r[1], r[2], r[3], r[4], r[5]))
    return 0


def main():
    import argparse
    ap = argparse.ArgumentParser(description='全档时点 diff（只标注·不改判定）')
    ap.add_argument('--home')
    ap.add_argument('--away')
    ap.add_argument('--file', help='指定「本时点」快照 json（默认取 snapshots/ 最新一份）')
    ap.add_argument('--all-points', action='store_true', help='打印该场跨全部时点链')
    a = ap.parse_args()
    if a.all_points:
        if not (a.home and a.away):
            print('--all-points 需同时给 --home/--away'); return 2
        return cmd_all_points(a.home, a.away)
    return cmd_latest(a.file, a.home, a.away)


if __name__ == '__main__':
    sys.exit(main())
