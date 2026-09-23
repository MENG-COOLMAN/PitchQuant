# -*- coding: utf-8 -*-
"""资金盘信号统一入口（模型升级 V3.5.75 · 2026-09-21）

覆盖方案全模块：
  P0-1 跨机构分歧（方向/O25/U25）  → bookmaker_spread.py（已回测·可进判定）
  P0-2 Pinnacle sharp 基准          → sharp_baseline.py（待回测·仅提示）
  P0-3 RLM 反向线移动               → 本模块（竞彩逐T vs 亚盘跟进·待回测·仅提示）
  P1-1 全盘 vig 诊断                → 本模块（已回测：无方向信息 → 降级依据）
  P1-3 Steam Move                   → 本模块（需多时点快照·待积累）
  P2-2 比分盘赔率变动               → 本模块（竞彩 txt 逐T·待积累·仅提示）
  P2-3 临场时间权重                 → 本模块（txt 时间戳）

🔴 铁律：所有资金盘信号**只调置信度·永不反转 L2 硬核方向**·最多 ±1 档
🔴 状态分级：backtested（可进判定） / pending_backtest（仅提示） / pending_data（待积累）

CLI:
  python data/tmp/fundflow_analyzer.py --jc-txt <txt> [--fav-odd X] [--books <json>]
  python data/tmp/fundflow_analyzer.py --odd 1.85 --max 1.92 --o25 1.95 --max-o25 2.02
  python data/tmp/fundflow_analyzer.py --jc-txt <txt> --eu-books <json> --fav-odd 1.85 --fav-dir H
"""
import argparse
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bookmaker_spread as BS      # noqa: E402
import sharp_baseline as SB        # noqa: E402

SECTIONS = {
    '1x2': r'【胜平负[^】]*】',
    'handi': r'【让球胜平负[^】]*】',
    'goals': r'【总进球[^】]*】',
    'htft': r'【半全场[^】]*】',
    'cs': r'【比分[^】]*】',
}


def _parse_section(text, key):
    """解析竞彩 txt 某节 → [(时间, [值...]), ...]"""
    m = re.search(SECTIONS[key], text)
    if not m:
        return []
    seg = text[m.end():]
    nxt = re.search(r'【', seg)
    if nxt:
        seg = seg[:nxt.start()]
    out = []
    for line in seg.splitlines():
        line = line.strip()
        mm = re.match(r'^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)\s*[,，\t]\s*(.+)$', line)
        if not mm:
            continue
        vals = [v.strip() for v in re.split(r'[,，\t]+', mm.group(2)) if v.strip()]
        try:
            nums = [float(v) for v in vals]
        except ValueError:
            continue
        out.append((mm.group(1), nums))
    return out


def _devig3(h, d, a):
    inv = 1 / h + 1 / d + 1 / a
    return (1 / h / inv, 1 / d / inv, 1 / a / inv), inv - 1


def rlm_detect(jc_1x2, jc_handi):
    """P0-3 RLM（代理口径：竞彩热门降赔 × 亚盘是否跟进）

    竞彩不公开投注比例 → 用「竞彩热门方向移动」代理公众情绪，
    「亚盘让球是否跟进」代理 sharp 意愿。
    """
    res = {'status': 'na', 'signals': [], 'note': ''}
    if len(jc_1x2) < 2:
        res['note'] = '竞彩时点不足（<2）→ 不可判移动'
        return res
    t0, v0 = jc_1x2[0]
    t1, v1 = jc_1x2[-1]
    if len(v0) < 3 or len(v1) < 3:
        res['note'] = '赔率列不完整'
        return res
    fav_i = min(range(3), key=lambda i: v0[i])
    fav_name = ('H', 'D', 'A')[fav_i]
    drop = (v1[fav_i] - v0[fav_i]) / v0[fav_i] * 100
    res['status'] = 'ok'
    res['jc_move'] = {'fav': fav_name, 'from': v0[fav_i], 'to': v1[fav_i], 'pct': round(drop, 2),
                      't0': t0, 't1': t1}
    # 亚盘让球跟进判定（竞彩让球胜平负：让胜降赔 ≈ 升盘/看好主队穿盘）
    if len(jc_handi) >= 2:
        h0, h1 = jc_handi[0][1], jc_handi[-1][1]
        if len(h0) >= 3 and len(h1) >= 3:
            follow = (h1[0] - h0[0]) / h0[0] * 100   # 让胜赔率变动
            res['handi_move'] = {'from': h0[0], 'to': h1[0], 'pct': round(follow, 2)}
            if drop <= -2 and follow > 0:
                res['signals'].append({
                    'type': 'RLM_JC_VS_HANDI', 'severity': 'P0',
                    'desc': f'竞彩 {fav_name} 降赔 {drop:.1f}% 但让球盘未跟进（让胜赔率 {follow:+.1f}%）→ 热门陷阱嫌疑',
                    'action': '待回测·当前不调整（仅记录·禁用）', 'status': 'pending_backtest'})
            elif drop <= -2 and follow < 0:
                res['signals'].append({
                    'type': 'JC_HANDI_CONFIRM', 'severity': 'P1',
                    'desc': f'竞彩 {fav_name} 降赔且让球盘同向跟进（{follow:+.1f}%）→ 资金确认',
                    'action': '不调整（一致）', 'status': 'pending_backtest'})
    if not res['signals']:
        res['note'] = '无 RLM 触发'
    return res


def steam_detect(snapshots):
    """P1-3 Steam（需多时点多机构快照）
    snapshots: [{'t':.., 'books':[{bookmaker,h,d,a}, ...]}, ...]
    行业口径：同窗口内 ≥3 家同向移动 ≥ 阈值
    """
    if not snapshots or len(snapshots) < 2:
        return {'status': 'pending_data', 'note': '无多时点快照 → 待积累（需赛前 4h/2h/1h/30min/临场 定时抓取）'}
    first, last = snapshots[0]['books'], snapshots[-1]['books']
    by = {b.get('bookmaker'): b for b in last}
    moved = {'H': 0, 'D': 0, 'A': 0}
    for b in first:
        n = b.get('bookmaker')
        if n not in by:
            continue
        for k, kk in zip('HDA', ('h', 'd', 'a')):
            try:
                if abs(float(by[n][kk]) - float(b[kk])) >= 0.10:
                    moved[k] += 1
            except (TypeError, ValueError, KeyError, ZeroDivisionError):
                pass
    top = max(moved, key=moved.get)
    if moved[top] >= 3:
        return {'status': 'ok', 'steam': top, 'books_moved': moved[top],
                'action': '置信度 +1 档（同向）', 'backtest': 'pending_data'}
    return {'status': 'ok', 'steam': None, 'books_moved': moved[top],
            'note': f'同向机构数 {moved[top]} < 3 → 不构成 steam'}


def cs_series_detect(jc_cs, top_candidates=None):
    """P2-2 比分盘赔率变动（竞彩 txt 逐 T）

    规则（方案 4.3）：
      单比分降赔 >15% 且非系统性 → sharp 直接押该比分 → 进 Top4
      降赔 >10% 且与三源方向一致 → 双确认 → 提为主/次锚
      系统性集体降赔 → 忽略
    """
    res = {'status': 'na', 'moves': [], 'note': ''}
    if len(jc_cs) < 2:
        res['note'] = '比分盘时点不足（<2）→ 不可判变动'
        return res
    names = None
    hdr = jc_cs[0][1]
    # 竞彩比分盘列名顺序（标准模板）
    labels = ['1:0', '2:0', '2:1', '3:0', '3:1', '3:2', '4:0', '4:1', '4:2', '5:0', '5:1', '5:2',
              '胜其它', '0:0', '1:1', '2:2', '3:3', '平其它', '0:1', '0:2', '1:2', '0:3', '1:3',
              '2:3', '0:4', '1:4', '2:4', '0:5', '1:5', '2:5', '负其它']
    if len(hdr) != len(labels):
        res['note'] = f'比分列数 {len(hdr)} ≠ 标准 {len(labels)} → 跳过'
        return res
    names = labels
    first, last = jc_cs[0][1], jc_cs[-1][1]
    moved = 0
    for i, nm in enumerate(names):
        if first[i] <= 0 or last[i] <= 0:
            continue
        chg = (last[i] - first[i]) / first[i] * 100
        if chg <= -3:
            moved += 1
            res['moves'].append({'score': nm, 'from': first[i], 'to': last[i], 'pct': round(chg, 1)})
    res['status'] = 'ok'
    systemic = moved >= 6          # 系统性集体降赔 → 忽略
    res['systemic'] = systemic
    res['sharp_scores'] = [] if systemic else [m for m in res['moves'] if m['pct'] <= -10]
    if systemic:
        res['note'] = f'{moved} 个比分同步降赔 → 系统性调整（非 sharp 单点）→ 忽略'
    else:
        res['note'] = (f'单点降赔比分: {[m["score"] for m in res["sharp_scores"]]}'
                       if res['sharp_scores'] else '无单点显著降赔')
    res['backtest'] = 'pending_data'
    return res


def time_weight(jc_series, kickoff=None):
    """P2-3 临场时间权重（方案：>24h 0.5 / 4-24h 0.8 / 1-4h 1.0 / 60min 1.5 / 15min 2.0）"""
    if not jc_series:
        return {'status': 'na', 'note': '无时间戳'}
    t_last = jc_series[-1][0]
    if not kickoff:
        return {'status': 'ok', 'last_update': t_last, 'weight': 1.0,
                'note': '未提供开赛时间 → 默认权重 1.0（三态标注）'}
    return {'status': 'ok', 'last_update': t_last, 'kickoff': kickoff, 'weight': 1.5,
            'note': '临场窗口加权（示意·需精确时间差计算）'}


def analyze(jc_text=None, jc_path=None, books=None, odd=None, mx=None, o25=None,
            max_o25=None, u25=None, max_u25=None, fav_odd=None, fav_dir=None,
            snapshots=None, kickoff=None, odd_h=None, odd_a=None, max_h=None, max_a=None):
    if jc_path and not jc_text:
        with open(jc_path, encoding='utf-8', errors='replace') as fh:
            jc_text = fh.read()

    res = {'sections': {}, 'advice': [], 'status_note': []}

    # ── P0-1 + P0-2 ──
    res['P0-1'] = BS.analyze(books=books, odd=odd, mx=mx, o25=o25, max_o25=max_o25,
                             u25=u25, max_u25=max_u25, fav_odd=fav_odd, fav_dir=fav_dir,
                             odd_h=odd_h, odd_a=odd_a, max_h=max_h, max_a=max_a)
    if books:
        res['P0-2'] = SB.sharp_vs_soft(books)
    else:
        res['P0-2'] = {'status': 'no_books', 'fallback': 'use_spread(替代 P0-1)',
                       'reason': '未提供逐家赔率（需 api-football 13 家）'}

    # ── 竞彩序列类 ──
    if jc_text:
        s1x2 = _parse_section(jc_text, '1x2')
        shandi = _parse_section(jc_text, 'handi')
        scs = _parse_section(jc_text, 'cs')
        res['sections'] = {'1x2_points': len(s1x2), 'handi_points': len(shandi), 'cs_points': len(scs)}
        res['P0-3'] = rlm_detect(s1x2, shandi)
        res['P2-2'] = cs_series_detect(scs)
        res['P2-3'] = time_weight(s1x2, kickoff)
        # P1-1 诊断（vig 实测无方向信息 → 仅作降级说明）
        if len(s1x2) >= 1 and len(s1x2[0][1]) >= 3:
            _, (h, d, a) = s1x2[0][0], s1x2[0][1][:3]
            _, vig = _devig3(h, d, a)
            res['P1-1'] = {'status': 'ok', 'jc_vig': round(vig * 100, 2),
                           'note': '🔴 全盘 vig 经 227,510 场实测**无方向信息**（分档 47.9-52.6% 无单调）'
                                   '→ 禁止作为方向双确认；仅保留跨市场比值（SL-jc-reverse）与亚盘水位独立维度'}
    else:
        res['status_note'].append('未提供竞彩 txt → P0-3/P1-1/P2-2/P2-3 不触发')

    # ── P1-3 ──
    res['P1-3'] = steam_detect(snapshots)

    # ── 判定建议聚合（🔴 只调置信度·永不反转）──
    g = res['P0-1'].get('fav_grade')
    if g and g[2] == 'backtested' and g[0] in ('SHARP_DEEP', 'SHARP_CONSENSUS'):
        res['advice'].append(f"✅ {g[0]}: {g[1]}")
    elif g:
        res['advice'].append(f"ℹ️ {g[0]}: {g[1]} [{g[2]}]")
    for s in res.get('P0-3', {}).get('signals', []):
        res['advice'].append(f"⚠️ {s['type']}（{s['status']}）: {s['action']}")
    if res.get('P0-2', {}).get('rlm_candidate'):
        res['advice'].append("⚠️ P0-2 sharp/soft 方向背离 → RLM 候选（pending_backtest·仅提示）")
    if res.get('P2-2', {}).get('sharp_scores'):
        res['advice'].append(f"⚠️ P2-2 sharp 单点降赔比分: {[m['score'] for m in res['P2-2']['sharp_scores']]}"
                             "（pending_data·仅提示）")
    if not res['advice']:
        res['advice'].append('无资金盘信号触发（不调整）')
    return res


def render(res):
    L = ['═' * 62, '【资金盘信号总览 · 2026-09-21 升级模块】', '═' * 62]
    L.append(BS.render(res['P0-1']))
    L.append('')
    L.append(SB.render(res['P0-2']) if res.get('P0-2') else '【Sharp 基准 · P0-2】未提供逐家赔率')
    if 'P0-3' in res:
        r = res['P0-3']
        L.append('')
        L.append(f"【RLM 反向线移动 · P0-3】status={r['status']}")
        if r.get('jc_move'):
            L.append(f"  竞彩热门移动: {r['jc_move']['fav']} {r['jc_move']['from']}→{r['jc_move']['to']} "
                     f"({r['jc_move']['pct']:+.2f}%)")
        if r.get('handi_move'):
            L.append(f"  让球盘跟进: {r['handi_move']['pct']:+.2f}%")
        for s in r.get('signals', []):
            L.append(f"  🔴 {s['type']}: {s['desc']} → {s['action']}")
        if r.get('note'):
            L.append(f"  {r['note']}")
    if 'P1-1' in res:
        L.append('')
        L.append(f"【vig 诊断 · P1-1】竞彩抽水 {res['P1-1']['jc_vig']}%")
        L.append(f"  {res['P1-1']['note']}")
    if res.get('P2-2'):
        r = res['P2-2']
        L.append('')
        L.append(f"【比分盘变动 · P2-2】status={r['status']} {r.get('note', '')}")
    if res.get('P2-3'):
        L.append('')
        L.append(f"【临场时间权重 · P2-3】{res['P2-3'].get('note', '')}")
    L.append('')
    L.append(f"【P1-3 Steam】{res['P1-3'].get('note', res['P1-3'].get('steam'))}")
    for n in res.get('status_note', []):
        L.append(f"  ⚠️ {n}")
    L.append('')
    L.append('【判定建议】（🔴 只调置信度·永不反转方向·最多 ±1 档）')
    for a in res['advice']:
        L.append(f"  {a}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description='资金盘信号统一入口（P0-1/P0-2/P0-3/P1-1/P1-3/P2-2/P2-3）')
    ap.add_argument('--jc-txt', help='竞彩 txt 路径')
    ap.add_argument('--books', help='api-football 逐家赔率 JSON 路径（[{bookmaker,h,d,a}]）')
    ap.add_argument('--odd', type=float, help='方向均值赔率（热门或主）')
    ap.add_argument('--max', type=float, dest='mx', help='方向最高价（MaxHome）')
    ap.add_argument('--o25', type=float)
    ap.add_argument('--max-o25', type=float, dest='max_o25')
    ap.add_argument('--u25', type=float)
    ap.add_argument('--max-u25', type=float, dest='max_u25')
    ap.add_argument('--fav-odd', type=float, dest='fav_odd')
    ap.add_argument('--fav-dir', dest='fav_dir', choices=['H', 'D', 'A'])
    ap.add_argument('--snapshots', help='多时点快照 JSON（P1-3 Steam）')
    ap.add_argument('--kickoff', help='开赛时间（P2-3）')
    ap.add_argument('--json', action='store_true', help='输出 JSON')
    args = ap.parse_args()

    books = None
    if args.books:
        with open(args.books, encoding='utf-8') as fh:
            _rawbk = json.load(fh)
            if isinstance(_rawbk, dict):
                books = _rawbk.get('books') if _rawbk.get('status') == 'ok' else None
            else:
                books = _rawbk
            if books is not None and not isinstance(books, list):
                books = None
    snaps = None
    if args.snapshots:
        with open(args.snapshots, encoding='utf-8') as fh:
            snaps = json.load(fh)

    # 🔴2026-09-21 修复(半断链⑦): proxy 通道下 --odd 即热门侧；未传 --fav-odd 时自动补全
    if args.fav_odd is None and args.odd is not None and not books:
        args.fav_odd = args.odd
    res = analyze(jc_path=args.jc_txt, books=books, odd=args.odd, mx=args.mx, o25=args.o25,
                  max_o25=args.max_o25, u25=args.u25, max_u25=args.max_u25,
                  fav_odd=args.fav_odd, fav_dir=args.fav_dir, snapshots=snaps, kickoff=args.kickoff)
    print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else render(res))


if __name__ == '__main__':
    if len(sys.argv) == 1:
        demo = """赛事：测试(主) VS 测试客(客)

【胜平负固定奖金】
发布时间,胜,平,负
2026-09-20 10:00:00,1.85,3.60,4.20
2026-09-20 20:00:00,1.78,3.65,4.40

【让球胜平负固定奖金 让球-1】
发布时间,胜,平,负
2026-09-20 10:00:00,2.90,3.40,2.05
2026-09-20 20:00:00,2.95,3.35,2.03

【比分固定奖金】
发布时间,1:0,2:0,2:1,3:0,3:1,3:2,4:0,4:1,4:2,5:0,5:1,5:2,胜其它,0:0,1:1,2:2,3:3,平其它,0:1,0:2,1:2,0:3,1:3,2:3,0:4,1:4,2:4,0:5,1:5,2:5,负其它
2026-09-20 10:00:00,7.5,7.8,7.0,12.5,12.0,22.0,25.0,26.0,50.0,60.0,75.0,150.0,50.0,13.0,7.0,15.0,75.0,500.0,13.0,25.0,13.0,75.0,50.0,50.0,350.0,200.0,200.0,750.0,550.0,650.0,250.0
2026-09-20 20:00:00,8.0,7.5,6.5,12.5,11.5,22.0,25.0,26.0,50.0,60.0,75.0,150.0,50.0,13.0,7.0,15.0,75.0,500.0,13.0,25.0,13.0,75.0,50.0,50.0,350.0,200.0,200.0,750.0,550.0,650.0,250.0
"""
        r = analyze(jc_text=demo, odd=1.85, mx=1.92, o25=1.95, max_o25=2.02, fav_odd=1.85, fav_dir='H')
        print(render(r))
    else:
        main()
