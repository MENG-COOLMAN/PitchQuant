# -*- coding: utf-8 -*-
"""H2H 双源查询 h2h_lookup.py（2026-10-31 建立·P19 要求落地）

P19（2026-10-28 固化）要求「H2H 必须双源，缺一即三态」：
  源1 = 竞彩 txt「特征分析·近N场交锋」（口径未知·由模型从 txt 提取）
  源2 = **Matches.csv 逐场记录**（可核对·含日期/比分）← **本脚本负责**

🔴 修复的断链（2026-10-31 Step 全流程审计 S00d）：
   审计实测 calc_all 里**零 H2H 计算代码**，只有 C33 清单文本 + 「修正53 需外部补 S6」提示
   → H2H 全靠 LLM 手工查 skill + 手工传 --draw-score（P16③ 同款「靠人记得」缺陷）
   → 本脚本把源2 变成**确定性计算**，calc_all 直接调用并自动补 S6 证据

用法:
  python data/tmp/h2h_lookup.py --home "勒阿弗尔" --away "巴黎圣日耳曼"
  python data/tmp/h2h_lookup.py --home "Le Havre" --away "Paris SG" --n 8 --json
"""
import argparse
import csv
import io
import json
import os
import sys

os.chdir(r'<HOME>\AppData\Roaming\reasonix\global-workspace')
sys.path.insert(0, os.path.join(os.getcwd(), 'data', 'tmp'))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

MATCHES = 'data/Matches.csv'
_CACHE = '_h2h_cache.json'


def _cn2en(name):
    """中→英多候选（复用统一别名层·2026-09-29 根治版）"""
    out = []
    try:
        import snapshot_save as SS
        out = list(SS.cn2en_list(name) or [])
    except Exception:
        pass
    if name and name not in out:
        out.append(name)
    return out


def _norm(s):
    try:
        import data_bridge as DB
        return DB.normalize_name(s or '')
    except Exception:
        return (s or '').strip().lower()


def lookup(home, away, n=6, league=None):
    """返回 {'ok', 'n', 'rows', 'h_win/d/a', 'draw_rate', 'avg_goals', 'src', 'note'}"""
    ch = _cn2en(home)
    ca = _cn2en(away)
    nh = set(_norm(x) for x in ch)
    na = set(_norm(x) for x in ca)
    rows = []
    if not os.path.exists(MATCHES):
        return dict(ok=False, n=0, rows=[], src='Matches.csv',
                    note='Matches.csv 不存在')
    try:
        with io.open(MATCHES, encoding='utf-8', errors='replace') as f:
            for d in csv.DictReader(f):
                h, a = _norm(d.get('HomeTeam')), _norm(d.get('AwayTeam'))
                if not h or not a:
                    continue
                pair = None
                if h in nh and a in na:
                    pair = 'H'
                elif h in na and a in nh:
                    pair = 'A'
                if not pair:
                    continue
                try:
                    hg, ag = int(float(d['FTHome'])), int(float(d['FTAway']))
                except (TypeError, ValueError, KeyError):
                    continue
                if league and d.get('Division') and str(league) not in str(d.get('Division')):
                    pass          # 不过滤（跨赛事交锋也算·留痕标注）
                rows.append(dict(date=d.get('MatchDate', ''), div=d.get('Division', ''),
                                 home=d.get('HomeTeam', ''), away=d.get('AwayTeam', ''),
                                 hg=hg, ag=ag, pair=pair))
    except Exception as e:
        return dict(ok=False, n=0, rows=[], src='Matches.csv',
                    note='扫描异常: %s' % str(e)[:60])
    if not rows:
        return dict(ok=False, n=0, rows=[], src='Matches.csv',
                    note='Matches.csv 无两队交锋记录（超域/新队/队名未匹配·三态）')
    rows.sort(key=lambda r: r['date'], reverse=True)
    recent = rows[:n]
    # 主队视角（统一换算）
    hw = dr = aw = 0
    for r in recent:
        hg, ag = (r['hg'], r['ag']) if r['pair'] == 'H' else (r['ag'], r['hg'])
        if hg > ag:
            hw += 1
        elif hg == ag:
            dr += 1
        else:
            aw += 1
    tot = len(recent)
    goals = sum(r['hg'] + r['ag'] for r in recent)
    return dict(
        ok=True, n=tot, total_all=len(rows), rows=recent,
        h_win=hw, draw=dr, a_win=aw,
        draw_rate=round(dr / tot * 100, 1) if tot else None,
        avg_goals=round(goals / tot, 2) if tot else None,
        src='Matches.csv(逐场可核对)',
        note='主队视角换算（跨赛事含杯赛·Division 已留痕）')


def draw_score(res, recent_k=2, rate_thr=30.0):
    """→ (S6 是否满足, 说明)。修正53 S6 = 近2场平局≥1 或 近3场平局≥2"""
    if not res.get('ok'):
        return False, 'H2H 无数据（三态·S6 不计）'
    rs = res['rows']
    k2 = rs[:2]
    k3 = rs[:3]
    d2 = sum(1 for r in k2 if r['hg'] == r['ag'])
    d3 = sum(1 for r in k3 if r['hg'] == r['ag'])
    if d2 >= 1:
        return True, '近2场交锋含 %d 场平局 → S6 满足' % d2
    if d3 >= 2:
        return True, '近3场交锋 %d 场平局 → S6 满足' % d3
    return False, '近3场交锋仅 %d 场平局 → S6 不满足' % d3


def report(home, away, n=6, league=None):
    r = lookup(home, away, n=n, league=league)
    L = []
    if not r.get('ok'):
        L.append('🔴H2H 双源(Matches.csv·源2): %s' % r.get('note'))
        L.append('   源1(竞彩txt 特征分析) 仍需模型从 txt 提取 → 双源缺一 = 三态')
        return '\n'.join(L), r
    L.append('🔴H2H 双源[源2=Matches.csv 逐场可核对] 共 %d 场交锋（近 %d 场）'
             % (r['total_all'], r['n']))
    for x in r['rows']:
        L.append('   %s %-4s %s %d:%d %s' % (x['date'], x['div'], x['home'], x['hg'], x['ag'], x['away']))
    L.append('   主队视角: %d胜 %d平 %d负 ｜ 平局率 %.1f%% ｜ 场均总进球 %.2f'
             % (r['h_win'], r['draw'], r['a_win'], r['draw_rate'], r['avg_goals']))
    ok6, why = draw_score(r)
    L.append('   修正53 S6: %s（%s）' % ('✅' if ok6 else '✗', why))
    if r['n'] < 3:
        L.append('   ⚠️样本 <3 场 → 仅参考·禁作定量依据')
    return '\n'.join(L), r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--home', required=True)
    ap.add_argument('--away', required=True)
    ap.add_argument('--n', type=int, default=6)
    ap.add_argument('--league', default=None)
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    txt, r = report(a.home, a.away, n=a.n, league=a.league)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(txt)
    return 0 if r.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main())
