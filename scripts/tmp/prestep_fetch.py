# -*- coding: utf-8 -*-
"""prestep_fetch.py —— PreStep 赛事拉取+赔率解析（2026-09-12·脚本化·反复使用）
拉 pending 赛事 → 按时间窗口过滤 → 取 1xbet 赔率(均衡线+2.5线/插值) → 调 prestep_dual 双向评级

用法:
  python data/tmp/prestep_fetch.py --from 2026-09-12T15:00 --to 2026-09-12T19:00   # UTC 窗口
  python data/tmp/prestep_fetch.py --bj "23:00-03:00"                               # 北京窗口(今日23点→次日3点)
  python data/tmp/prestep_fetch.py --bj "22:00-06:00" --leagues 西甲,欧联            # 只筛指定联赛

🔴2026-09-17: 补欧战 slug（实测 Odds-API 已收录·旧记录「欧战未收录404」已过时）：
  international-clubs-uefa-europa-league（欧联·pending 99 场）/ ...-champions-league（欧冠·90 场）
"""
import json, sys, io, os, re, argparse, subprocess, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
KEY = os.environ.get('ODDS_API_KEY', '')
PROXY = 'http://127.0.0.1:7897'
LG = {'england-premier-league': '英超', 'spain-laliga': '西甲', 'germany-bundesliga': '德甲',
      'italy-serie-a': '意甲', 'france-ligue-1': '法甲',
      'international-clubs-uefa-europa-league': '欧联',
      'international-clubs-uefa-champions-league': '欧冠'}
# 🔴2026-09-12: Odds-API 实测**可直连**（无需 VPN）→ 优先直连·失败回退代理
_op_direct = urllib.request.build_opener()
_op_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY}))


def get(u, tries=2):
    last = None
    for op in (_op_direct, _op_proxy):          # 直连优先 → 代理备选
        for _ in range(tries):
            try:
                with op.open(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=25) as r:
                    raw = r.read()
                    # 🔴2026-09-15修复: Odds-API 返回 Content-Encoding: gzip，而 urllib **不自动解压**
                    # → json.loads(gzip字节) 报 "Expecting value: line 1 column 1"（伪装成空响应/接口不可用）
                    if raw[:2] == b'\x1f\x8b':
                        import gzip
                        raw = gzip.decompress(raw)
                    return json.loads(raw.decode('utf-8', errors='replace'))
            except Exception as e:
                last = e
    raise last


def window_from_bj(bj):
    """bj: 'HH:MM-HH:MM' → (utc_from, utc_to)  ISO 字符串"""
    import datetime as dt
    m = re.match(r'(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})', bj)
    if not m:
        raise SystemExit('--bj 格式应为 HH:MM-HH:MM')
    now = dt.datetime.now()
    h0, m0, h1, m1 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    w0 = now.replace(hour=h0, minute=m0, second=0, microsecond=0)
    w1 = now.replace(hour=h1, minute=m1, second=0, microsecond=0)
    if w1 <= w0:
        w1 += dt.timedelta(days=1)
    u0 = (w0 - dt.timedelta(hours=8)).strftime('%Y-%m-%dT%H:%M')
    u1 = (w1 - dt.timedelta(hours=8)).strftime('%Y-%m-%dT%H:%M')
    return u0, u1, ('%s → %s' % (w0.strftime('%m-%d %H:%M'), w1.strftime('%m-%d %H:%M')))


def parse_odds(ev_id):
    """取 1xbet 赔率: ML / 均衡线 Spread / 2.5线(或插值) Totals"""
    d = get('https://api.odds-api.io/v3/odds?apiKey=%s&eventId=%s&bookmakers=1xbet' % (KEY, ev_id))
    mkts = (d.get('bookmakers') or {}).get('1xbet') or []
    ml = spr = tot = None
    for m in mkts:
        nm = m.get('name')
        if nm == 'ML': ml = m.get('odds') or []
        elif nm == 'Spread': spr = m.get('odds') or []
        elif nm == 'Totals': tot = m.get('odds') or []
    oh = od = oa = handi = o25 = None
    if ml:
        try:
            oh = float(ml[0].get('home') or 0) or None
            od = float(ml[0].get('draw') or 0) or None
            oa = float(ml[0].get('away') or 0) or None
        except Exception:
            pass
    if spr:
        try:
            best = min(spr, key=lambda x: abs(float(x.get('home') or 99) - float(x.get('away') or 99)))
            handi = float(best.get('hdp') or 0)
        except Exception:
            handi = None
    if tot:
        try:
            lines = sorted([(float(x.get('hdp') or 0), float(x.get('over') or 0)) for x in tot if x.get('over')], key=lambda t: t[0])
            ex = [l for l in lines if abs(l[0] - 2.5) < 0.01]
            if ex:
                o25 = ex[0][1]
            else:
                lo = [l for l in lines if l[0] <= 2.5]; hi = [l for l in lines if l[0] >= 2.5]
                if lo and hi and hi[0][0] > lo[-1][0]:
                    a, b = lo[-1], hi[0]
                    o25 = round(a[1] + (b[1] - a[1]) * ((2.5 - a[0]) / (b[0] - a[0])), 3)
                elif lines:
                    o25 = lines[0][1]
        except Exception:
            o25 = None
    return oh, od, oa, handi, o25


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='f'); ap.add_argument('--to', dest='t')
    ap.add_argument('--bj', help='北京窗口 HH:MM-HH:MM（如 23:00-03:00）')
    ap.add_argument('--leagues', help='只筛指定联赛(逗号分隔·如 西甲,欧联)·默认全部')
    ap.add_argument('--save', action='store_true')
    a = ap.parse_args()
    if a.bj:
        u0, u1, label = window_from_bj(a.bj)
    elif a.f and a.t:
        u0, u1, label = a.f, a.t, '%s → %s (UTC)' % (a.f, a.t)
    else:
        print(__doc__); return
    print('窗口: 北京 %s（UTC %s → %s）\n' % (label, u0, u1))
    rows = []
    only = [s.strip() for s in (a.leagues or '').split(',') if s.strip()]   # 🔴2026-09-17: 联赛过滤
    for slug, cn in LG.items():
        if only and cn not in only:
            continue
        try:
            evs = get('https://api.odds-api.io/v3/events?apiKey=%s&sport=football&league=%s&status=pending' % (KEY, slug))
        except Exception as e:
            print('  ⚠️ %s 拉取失败: %s' % (cn, str(e)[:60])); continue
        for e in (evs or []):
            d = (e.get('date') or '')
            # 🔴2026-09-13 修正: 含窗口上界（'到三点'须含 03:00 整开赛场次——Real Sociedad vs Atletico 曾被漏）
            if u0 <= d[:16] <= u1:
                rows.append({'cn': cn, 'id': e['id'], 'home': e['home'], 'away': e['away'], 'date': d})
    print('窗口内赛事: %d 场' % len(rows))
    for r in rows:
        try:
            oh, od, oa, handi, o25 = parse_odds(r['id'])
            r.update({'oh': oh, 'od': od, 'oa': oa, 'handi': handi, 'o25': o25})
        except Exception as e:
            r['err'] = str(e)[:50]
    print('%-6s %-6s %-32s %-6s %-6s %-6s %-7s %-7s' % ('北京', '联赛', '赛事', '主', '平', '客', '让球', 'O25'))
    for r in sorted(rows, key=lambda x: x['date']):
        bj = str(int(r['date'][11:13]) + 8).zfill(2) + r['date'][13:16]
        if int(bj[:2]) >= 24:
            bj = str(int(bj[:2]) - 24).zfill(2) + bj[2:]
        print('%-6s %-6s %-32s %-6s %-6s %-6s %-7s %-7s' % (bj, r['cn'], ('%s vs %s' % (r['home'], r['away']))[:30],
              r.get('oh'), r.get('od'), r.get('oa'), r.get('handi'), r.get('o25')))
    if a.save:
        p = os.path.join(HERE, 'prestep_window.json')
        json.dump(rows, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('\n已保存: data/tmp/prestep_window.json')
    args = []
    for r in rows:
        if r.get('oh') and r.get('o25'):
            args += ['--match', '%s %s vs %s,%s,%s,%s,%s,%s,%s,%s' % (
                r['cn'], r['home'], r['away'], r['oh'], r['od'], r['oa'],
                r.get('handi') or 0, r['o25'], 0, r['cn'])]
    if args:
        print()
        subprocess.run([sys.executable, os.path.join(HERE, 'prestep_dual.py')] + args,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))


if __name__ == '__main__':
    main()
# 🔴2026-09-17: LG 补欧联/欧冠 slug（Odds-API 实测已收录·旧记录已过时）+ 新增 --leagues 过滤（先验指令按联赛筛选用）
