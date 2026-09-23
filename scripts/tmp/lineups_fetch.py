# -*- coding: utf-8 -*-
"""P3 首发阵容获取（api-football lineups·2026-09-20·观察项）

🔴定位: **观察项/信息源**——输出阵容供 LLM 综合判断（Step0 基本面/Step7 比分参考）
  🔴**不改任何分值/规则/判定**（符合「仅标注不量化」L3 原则）
  🔴**无法回测**（历史首发阵容数据不可得）→ 不作为规则上线·仅作信息源 + 三态标注
  🔴**赛前约 60 分钟才有** → 更早查询返回空 → 三态标注「未公布（赛前60min可查）」

用法:
  python data/tmp/lineups_fetch.py --date 2026-09-20 --home "Roma" --away "Inter"
  python data/tmp/lineups_fetch.py --fixture 1550128          # 已知 fixture id 直查
"""
import sys, os, json, argparse, urllib.request, urllib.parse
sys.stdout.reconfigure(encoding='utf-8')

KEY = os.environ.get('API_FOOTBALL_KEY', '')
BASE = 'https://v3.football.api-sports.io'


def api(path):
    req = urllib.request.Request(BASE + path, headers={'x-apisports-key': KEY, 'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode('utf-8', errors='replace'))


def _norm(s):
    import re
    return re.sub(r'[^a-z]', '', (s or '').lower())


def find_fixture(date, home, away):
    """🔴纯 date 定位（禁 league/season）→ 队名模糊匹配"""
    d = api('/fixtures?date=%s' % date)
    nh, na = _norm(home), _norm(away)
    for f in (d.get('response') or []):
        th = _norm(((f.get('teams') or {}).get('home') or {}).get('name'))
        ta = _norm(((f.get('teams') or {}).get('away') or {}).get('name'))
        if (nh and (nh in th or th in nh)) and (na and (na in ta or ta in na)):
            return f.get('fixture', {}).get('id'), f
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', help='UTC 日 YYYY-MM-DD')
    ap.add_argument('--home'); ap.add_argument('--away')
    ap.add_argument('--fixture', type=int)
    a = ap.parse_args()
    fid = a.fixture
    fxt = None
    if not fid:
        if not (a.date and a.home and a.away):
            print(__doc__); return
        fid, fxt = find_fixture(a.date, a.home, a.away)
        if not fid:
            print('🔴[三态] 未定位 fixture（date=%s %s vs %s）→ 阵容不可查' % (a.date, a.home, a.away))
            return
    if fxt:
        print('fixture %s: %s vs %s · %s · %s' % (
            fid, ((fxt.get('teams') or {}).get('home') or {}).get('name'),
            ((fxt.get('teams') or {}).get('away') or {}).get('name'),
            (fxt.get('fixture') or {}).get('date'), (fxt.get('fixture') or {}).get('status', {}).get('short')))
    try:
        d = api('/fixtures/lineups?fixture=%d' % fid)
    except Exception as e:
        print('🔴[三态] lineups 请求失败: %s' % str(e)[:60]); return
    resp = d.get('response') or []
    if not resp:
        print('⚪[三态] 阵容未公布（赛前约60分钟才有·或该场不含阵容数据）→ 本次不标注')
        return
    for side in resp:
        tm = (side.get('team') or {}).get('name')
        fm = side.get('formation')
        xi = side.get('startXI') or []
        names = []
        for p in xi:
            pl = p.get('player') or {}
            pos = '(%s)' % pl.get('pos') if pl.get('pos') else ''
            names.append('%s%s' % (pl.get('name'), pos))
        coach = (side.get('coach') or {}).get('name')
        print('【%s】阵型 %s ｜ 教练 %s' % (tm, fm, coach))
        print('   首发(%d): %s' % (len(names), ', '.join(names)))
    print('\n🔴消费纪律: 阵容=观察项（仅 Step0 基本面留痕 + Step7 比分参考）·不改任何分值/判定·无法回测仅三态标注')


if __name__ == '__main__':
    main()
