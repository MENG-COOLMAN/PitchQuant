# -*- coding: utf-8 -*-
"""Understat xG 获取（V3.5.68·2026-08-22·页面改版后数据端点 getLeagueData）
定位: 🔴基本面/观察项——预测以赔率水位+基本面为准·xG属基本面·辅助验证不主导
用法: python understat_xg.py <EPL|La_liga|Bundesliga|Serie_A|Ligue_1> [season]
输出: 已赛比赛 日期/主队/比分/客队/xG主-xG客
"""
import requests, json, sys, os, time

# 🔴GBK 控制台防护(2026-09-15·防 emoji/中文在 GBK 控制台崩溃)
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

PROXY = {'http':'http://127.0.0.1:7897','https':'http://127.0.0.1:7897'}
H = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
     'X-Requested-With':'XMLHttpRequest','Referer':'https://understat.com/league/'}

def get_league_xg(league='EPL', season=2026, cache=True):
    cache_file = f'data/tmp/xg_{league}_{season}.json'
    if cache and os.path.exists(cache_file):
        return json.load(open(cache_file, encoding='utf-8'))
    url = f'https://understat.com/getLeagueData/{league}/{season}'
    for attempt in range(3):  # 重试(代理SSL抖动容错)
        try:
            d = json.loads(requests.get(url, proxies=PROXY, timeout=30, headers=H, verify=False).text)
            break
        except Exception as e:
            if attempt == 2: raise
            time.sleep(2)
    if cache:
        json.dump(d, open(cache_file, 'w', encoding='utf-8'))
        time.sleep(1)  # 低频率·防封
    return d

def show(league, season):
    d = get_league_xg(league, season)
    dates = d.get('dates', [])
    played = [m for m in dates if m.get('goals') and m['goals'].get('h') is not None]
    print(f"{league} {season}-{season+1}: 总{len(dates)}场·已赛{len(played)}场 (xG源: understat.com·基本面观察项)")
    for m in played[-5:]:
        h = m['h']['title'] if isinstance(m['h'], dict) else m['h']
        a = m['a']['title'] if isinstance(m['a'], dict) else m['a']
        xg_h = float(m['xG']['h']) if m.get('xG') and m['xG'].get('h') else None
        xg_a = float(m['xG']['a']) if m.get('xG') and m['xG'].get('a') else None
        print(f"  {m.get('datetime','')[:10]} {h} {m['goals']['h']}-{m['goals']['a']} {a} | xG {xg_h}-{xg_a} | id:{m['id']}")

if __name__ == '__main__':
    league = sys.argv[1] if len(sys.argv) > 1 else 'EPL'
    season = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
    show(league, season)

def team_avg_xg(league, season, n=3):
    """赛前可用: 每队近N场已赛平均xG/xGA（仅用已赛比赛·本场xG仅赛后验证·防数据泄露）"""
    d = get_league_xg(league, season)
    from collections import defaultdict
    agg = defaultdict(lambda: {'xg':[], 'xga':[]})
    for m in d.get('dates', []):
        if not (m.get('xG') and m['xG'].get('h')): continue
        h = m['h']['title'] if isinstance(m['h'], dict) else m['h']
        a = m['a']['title'] if isinstance(m['a'], dict) else m['a']
        agg[h]['xg'].append(float(m['xG']['h'])); agg[h]['xga'].append(float(m['xG']['a']))
        agg[a]['xg'].append(float(m['xG']['a'])); agg[a]['xga'].append(float(m['xG']['h']))
    out = {}
    for team, v in agg.items():
        if v['xg']:
            out[team] = {'avg_xg': round(sum(v['xg'][-n:])/len(v['xg'][-n:]),2),
                         'avg_xga': round(sum(v['xga'][-n:])/len(v['xga'][-n:]),2),
                         'n': len(v['xg'])}
    return out

def export_csv(league, season, path=None):
    """完整赛季导出CSV(merge键=datetime+h+a·可merge竞彩/欧盘)·方案3全量380场xG"""
    import csv as _csv
    d = get_league_xg(league, season)
    dates = d.get('dates', [])
    played = [m for m in dates if m.get('xG') and m['xG'].get('h')]
    path = path or f'data/tmp/xg_{league}_{season}_matches.csv'
    with open(path, 'w', encoding='utf-8-sig', newline='') as fp:
        w = _csv.writer(fp)
        w.writerow(['datetime','home','away','h_goals','a_goals','h_xg','a_xg'])
        for m in played:
            h = m['h']['title'] if isinstance(m['h'], dict) else m['h']
            a = m['a']['title'] if isinstance(m['a'], dict) else m['a']
            w.writerow([m.get('datetime','')[:10], h, a, m['goals']['h'], m['goals']['a'],
                        float(m['xG']['h']), float(m['xG']['a'])])
    print(f"已导出 {len(played)}场 → {path}")
    return path

def lambda_scale(avg_xg_h, avg_xg_a, o25_odds, season_total_avg=2.7):
    """🔴λ缩放观察项(用户实操要点·不主导预测·V3.5.67泊松=观察项):
    历史xG作λ0 → 用大小球赔率反推总进球期望缩放λ绝对值·保持净胜差(2-1/3-2深度区分)"""
    ih, ia = 1/o25_odds, 1/(o25_odds*1.9)  # O2.5 vs U2.5 近似
    s = ih + ia
    over_p = ih/s
    total_exp = 2.5 if over_p < 0.5 else 2.5 + (over_p-0.5)*4  # 大球越强总进球期望越高
    base = avg_xg_h + avg_xg_a
    scale = total_exp / base if base > 0 else 1.0
    lam_h, lam_a = avg_xg_h*scale, avg_xg_a*scale
    return {'lam_h': round(lam_h,2), 'lam_a': round(lam_a,2), '净胜差': round(lam_h-lam_a,2),
            '总进球期望': round(lam_h+lam_a,2), '说明': '观察项·λ初始值·预测以赔率水位+基本面为准'}
