"""赛果自动获取（2026-08-29评审固化·P2-4·辅助通道·不替代用户告知）
用法: python fetch_results.py --date 2026-08-28 --league 西甲
输出: 五大联赛该日已赛场次+比分·供与案例库待赛果场次匹配
🔴复盘模式铁律: 用户告知真实赛果为主通道·本脚本仅可选验证/辅助(Odds-API赛果通道同)
"""
import argparse, io, sys, json, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
AF_KEY = os.environ.get('API_FOOTBALL_KEY', '')
LEAGUE_ID = {39:'英超',140:'西甲',78:'德甲',135:'意甲',61:'法甲'}  # api-football 标准id
if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', required=True)
    ap.add_argument('--league', default=None)
    a = ap.parse_args()
    req = urllib.request.Request(f'https://v3.football.api-sports.io/fixtures?date={a.date}', headers={'x-apisports-key': AF_KEY})
    d = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    print(f'🔴赛果自动获取(P2-4·辅助通道·{a.date}):')
    n = 0
    for f in d.get('response', []):
        lg = LEAGUE_ID.get(f['league']['id'], '')
        if not lg: continue
        if a.league and lg != a.league: continue
        if f['fixture']['status']['short'] != 'FT': continue
        h = f['teams']['home']['name']; aw = f['teams']['away']['name']
        gh = f['score']['fulltime']['home']; ga = f['score']['fulltime']['away']
        if gh is None: continue
        print(f'  {lg}: {h} {gh}:{ga} {aw} (fixture {f["fixture"]["id"]})')
        n += 1
    print(f'  共 {n} 场·🔴仅供辅助验证·复盘以用户告知为准')
