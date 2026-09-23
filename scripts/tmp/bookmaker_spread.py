# -*- coding: utf-8 -*-
"""P0-1 跨机构赔率分歧模块（资金盘升级 2026-09-21）

数据通道（按精度排序，自动选择）
  A. api-football 13 家**逐家**赔率   → 真·跨机构（median/min/max/spread）★首选
  B. Odds-API 1xbet + B365（常仅 2 家）→ 2 家通道（spread 用两家差/均值）
  C. Matches.csv 静态代理（Odd 均值 + Max 最高价）→ 回测校准通道（(Max-均值)/均值）

覆盖市场：方向（H/D/A）· 大小球（O25 / U25）

🔴 回测依据（Matches.csv 227,510 场 · 时间分割 80/20）：
  - 方向 spread <2% → 52.67%(train) / 62.57%(test)；>10% → 43.95% / 44.97%（跨幅 +8.7/+17.6pp）
  - 深盘(fav<1.50) + 一致(<2%) → 80.00% / 81.45% vs 深盘基准 74.00% / 75.38%（+6.0/+6.1pp）
  - 深盘 + 分歧(>5%) → 73.09% / 73.71%（仅 -0.91/-1.67pp）→ 🔴 **不达 >3pp 门禁·禁止降档**
🔴 未验证部分（O25/U25 spread 分档阈值）→ 仅输出与标注，**不进入判定链**（三态标注 pending_backtest）
"""
import json
import statistics
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# ── 共识等级阈值（方向·已回测）──
CONSENSUS_T = 0.02
NORMAL_T = 0.05
DIVERGED_T = 0.10

def consensus_label(spread_pct):
    """共识等级（方向市场·阈值已回测）"""
    if spread_pct < CONSENSUS_T:
        return 'CONSENSUS'      # 机构一致 → sharp 定价共识（升权依据）
    if spread_pct < NORMAL_T:
        return 'NORMAL'
    if spread_pct < DIVERGED_T:
        return 'DIVERGED'
    return 'CHAOS'              # 极大分歧 → 仅标注（🔴不降档·无门禁支撑）


def calc_spread_from_books(books, keys=('h', 'd', 'a')):
    """通道 A：api-football 逐家赔率 → 真跨机构分歧

    books: [{'bookmaker': 'Pinnacle', 'h': 1.85, 'd': 3.6, 'a': 4.2}, ...]
    返回 {outcome: {n, median, min, max, spread_pct, consensus, channel:'books'}}
    """
    out = {}
    for oc, k in zip(('H', 'D', 'A'), keys):
        vals = sorted(float(b[k]) for b in books if b.get(k) and float(b[k]) > 1.01)
        if len(vals) < 3:
            out[oc] = {'status': 'insufficient', 'n': len(vals), 'channel': 'books'}
            continue
        med = statistics.median(vals)
        mx, mn = vals[-1], vals[0]
        sp = (mx - med) / med
        out[oc] = {'n': len(vals), 'median': round(med, 3), 'min': mn, 'max': mx,
                   'spread_pct': round(sp, 4), 'consensus': consensus_label(sp),
                   'channel': 'books'}
    return out


def calc_spread_proxy(odd, mx, market='1x2'):
    """通道 C：均值 + 最高价 代理 spread = (Max - 均值)/均值

    🔴 该口径即回测所用口径（Matches.csv: OddHome/Draw/Away + MaxHome/Draw/Away）
    market: '1x2' | 'o25' | 'u25'
    """
    if not odd or not mx or odd <= 1.01 or mx <= 1.01:
        return {'status': 'na', 'channel': 'proxy', 'reason': 'Max 或均值缺失'}
    sp = (mx - odd) / odd
    return {'odd': odd, 'max': mx, 'spread_pct': round(sp, 4),
            'consensus': consensus_label(sp), 'channel': 'proxy', 'market': market}


def calc_spread_two_books(o1, o2):
    """通道 B：两家机构（Odds-API 常见：1xbet + B365）"""
    if not o1 or not o2 or min(o1, o2) <= 1.01:
        return {'status': 'na', 'channel': 'two_books', 'reason': '机构数不足'}
    lo, hi = min(o1, o2), max(o1, o2)
    sp = (hi - lo) / lo
    return {'n': 2, 'low': lo, 'high': hi, 'spread_pct': round(sp, 4),
            'consensus': consensus_label(sp), 'channel': 'two_books'}


def sharp_grade(fav_spread, fav_odds, backtested=True):
    """热门方向的资金标签（P0-1 判定规则）

    返回 (label, action, status)
      SHARP_DEEP      → 深盘 + 一致 → 🔴 置信度 +1 档（已回测 80.0/81.5%）
      SHARP_CONSENSUS → 一致（非深盘）→ 置信度 +0.5 档（已回测 52.7/62.6%）
      DIVERGED/CHAOS  → 仅标注（🔴 不降档：实测仅 -0.9pp，不达 >3pp 门禁）
    """
    if fav_spread is None:
        return ('NA', '不调整（spread 不可得）', 'na')
    if fav_spread < CONSENSUS_T:
        if fav_odds < 1.50:
            return ('SHARP_DEEP', '🔴 置信度 +1 档（深盘+机构一致）', 'backtested' if backtested else 'pending')
        return ('SHARP_CONSENSUS', '置信度 +0.5 档（机构一致）', 'backtested' if backtested else 'pending')
    if fav_spread < NORMAL_T:
        return ('NEUTRAL', '不调整', 'backtested')
    if fav_spread < DIVERGED_T:
        return ('DIVERGED', '⚠️ 仅标注（机构分歧·不降档）', 'annotate_only')
    return ('CHAOS', '⚠️ 仅标注（极大分歧·建议回避串关·不降档）', 'annotate_only')


def analyze(books=None, odd=None, mx=None, o25=None, max_o25=None,
            u25=None, max_u25=None, fav_odd=None, fav_dir=None,
            odd_h=None, odd_a=None, max_h=None, max_a=None):
    """统一入口 → dict（供 calc_all / fundflow_analyzer 消费）"""
    res = {'status': 'ok', 'direction': {}, 'totals': {}, 'errors': []}

    # 通道选择
    if books and len(books) >= 3:
        res['channel'] = 'books(api-football 逐家)'
        res['direction'] = calc_spread_from_books(books)
    elif books and len(books) == 2:
        # 🔴2026-09-21 收尾修复: 2 家时启用 two_books 通道
        #   （原 calc_spread_two_books 已定义但从未被调用 = 存在≠活跃 → 2 家场景退化 na）
        res['channel'] = 'two_books(2家·Odds-API 常见)'
        _tb = {}
        for _oc, _k in (('H', 'h'), ('D', 'd'), ('A', 'a')):
            _vals = [float(x[_k]) for x in books if x.get(_k) and float(x[_k]) > 1.01]
            _tb[_oc] = calc_spread_two_books(_vals[0], _vals[1]) if len(_vals) >= 2 else {
                'status': 'na', 'channel': 'two_books', 'reason': '该方向不足2家'}
        res['direction'] = _tb
    elif odd is not None and mx is not None:
        res['channel'] = 'proxy(均值+Max·回测口径)'
        res['direction'] = {'fav': calc_spread_proxy(odd, mx, '1x2')}
    else:
        res['channel'] = 'na'
        res['errors'].append('方向 spread 不可得：既无 13 家逐家赔率，也无均值+Max')

    # 大小球 spread（🔴 待回测 → 仅输出）
    if o25 and max_o25:
        res['totals']['o25'] = calc_spread_proxy(o25, max_o25, 'o25')
        res['totals']['o25']['status'] = 'pending_backtest'
    if u25 and max_u25:
        res['totals']['u25'] = calc_spread_proxy(u25, max_u25, 'u25')
        res['totals']['u25']['status'] = 'pending_backtest'

    # 🔴口径区分（2026-09-21 审计修复·防与「修正35」混用）:
    #   fav_spread（本模块主用） = 热门侧单侧 (Max_fav − Odd_fav)/Odd_fav
    #       → 语义: 热门方向机构定价是否稳固 → 227,510 场回测: <2% 62.57% / >10% 44.97%
    #       → 用途: 方向置信度升权（+1/+0.5 档·🔴唯一可进判定的资金盘信号）
    #   divergence_sum（修正35 口径·双侧之和） = (MaxH−OddH)/OddH + (MaxA−OddA)/OddA
    #       → 语义: 整体市场离散度（主客两侧合计）→ 历史 3,847/185,323 场: <5% 44.5% 报警 / >10% 51.6%
    #       → 用途: 共识过热/反向警报（修正32 联动）·🔴与 fav_spread 语义不同·禁混用
    if odd_h and odd_a and max_h and max_a:
        try:
            _dh = (float(max_h) - float(odd_h)) / float(odd_h)
            _da = (float(max_a) - float(odd_a)) / float(odd_a)
            _dv = _dh + _da
            res['divergence_sum'] = {
                'value': round(_dv, 4),
                'fix35_band': ('<5%' if _dv < 0.05 else ('5-10%' if _dv < 0.10 else '>10%')),
                'fix35_rule': ('🔴共识过热警报（修正32 联动·平局出口+20%/反向+15%）' if _dv < 0.05
                               else ('>10% 共识可信·不降级（修正35 历史 51.6%）' if _dv > 0.10 else '正常分歧')),
                'note': '修正35 口径（双侧之和）·非热门单侧·禁与 fav_spread 混用',
            }
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    # 热门方向标签
    if fav_odd is not None:
        sp = None
        if isinstance(res['direction'].get('fav'), dict) and 'spread_pct' in res['direction']['fav']:
            sp = res['direction']['fav']['spread_pct']
        elif fav_dir:
            d = res['direction'].get(fav_dir)
            if isinstance(d, dict) and 'spread_pct' in d:
                sp = d['spread_pct']
        res['fav_grade'] = sharp_grade(sp, fav_odd)
    return res


def render(res):
    """人类可读输出块（calc_all 消费）"""
    L = ['【跨机构分歧 · P0-1】']
    L.append(f"  数据通道: {res.get('channel')}")
    d = res.get('direction', {})
    for k in ('H', 'D', 'A'):
        v = d.get(k)
        if isinstance(v, dict) and 'spread_pct' in v:
            _med = v.get('median', v.get('odd', v.get('low')))
            _mx = v.get('max', v.get('high'))
            L.append(f"  {k}: median={_med} max={_mx} "
                     f"spread={v['spread_pct']*100:.1f}% {v['consensus']}")
    if 'fav' in d and isinstance(d['fav'], dict) and 'spread_pct' in d['fav']:
        v = d['fav']
        L.append(f"  热门方向(代理): odd={v['odd']} max={v['max']} spread={v['spread_pct']*100:.1f}% {v['consensus']}")
    t = res.get('totals', {})
    for k, v in t.items():
        L.append(f"  {k.upper()}: odd={v.get('odd')} max={v.get('max')} spread={v['spread_pct']*100:.1f}% "
                 f"{v['consensus']} ⚠️待回测(仅参考)")
    g = res.get('fav_grade')
    if g:
        L.append(f"  热门标签: {g[0]} → {g[1]} [{g[2]}]")
    dv = res.get('divergence_sum')
    if dv:
        L.append(f"  🔴修正35口径（双侧和·与上方热门单侧 spread 语义不同·禁混用）: {dv['value']*100:.1f}% "
                 f"[{dv['fix35_band']}] → {dv['fix35_rule']}")
    else:
        L.append("  ⚠️ 修正35口径不可算（需主客双侧 Max）→ 三态标注·不适用")
    for e in res.get('errors', []):
        L.append(f"  ⚠️ {e}")
    return "\n".join(L)

def load_books(path):
    """🔴2026-09-21 修复(P0 格式契约): 统一解包 fundflow_books.json
    fetch_books.py 输出为 {"status":"ok","n_books":N,"books":[...]}；旧版本可能已是裸 list。
    返回: list[dict] 或 None（status!=ok/解析失败/空）→ 调用方三态标注，禁崩溃。
    """
    import json as _j, os as _o
    if not path or not _o.path.exists(path):
        return None
    try:
        raw = _j.load(open(path, encoding='utf-8'))
    except Exception:
        return None
    if isinstance(raw, dict):
        if raw.get('status') != 'ok':
            return None
        b = raw.get('books')
        return b if isinstance(b, list) and b else None
    if isinstance(raw, list):
        return raw or None
    return None


if __name__ == '__main__':
    # 自检（演示两种通道）
    demo_books = [{'bookmaker': 'Pinnacle', 'h': 1.85, 'd': 3.60, 'a': 4.20},
                  {'bookmaker': 'Bet365', 'h': 1.84, 'd': 3.65, 'a': 4.25},
                  {'bookmaker': '1xBet', 'h': 1.83, 'd': 3.62, 'a': 4.30}]
    r1 = analyze(books=demo_books, fav_odd=1.85, fav_dir='H')
    print(render(r1))
    print()
    r2 = analyze(odd=1.85, mx=1.92, o25=1.95, max_o25=2.02, fav_odd=1.85)
    print(render(r2))
