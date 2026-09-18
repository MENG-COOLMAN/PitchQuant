# -*- coding: utf-8 -*-
"""calc_homeaway.py — HAF 主客场因子层·数据层（V3.5.73·2026-08-25·用户指令）
每队×场地子集统计（近5年·五大联赛）+ 主客场增益/衰减系数 → data/tmp/homeaway_table.json
🔴硬性约束: 只用对应场地子集·不混主场/客场·样本不足(n<15)标注风险·不合并取平均
用法: python calc_homeaway.py [--team 队名] [--league E0] [--ha 主队,客队]（对抗耦合输出）
"""
import csv, json, io, sys, argparse
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

DIV5 = {'E0':'英超','SP1':'西甲','D1':'德甲','I1':'意甲','F1':'法甲'}
# 联赛主客场基准（近5年实测·HAF设计文档第六节）
LEAGUE_BASE = {
    '英超': {'主场胜率': 43.6, '客场胜率': 33.5, '主队均球': 1.56, '客队均球': 1.33},
    '西甲': {'主场胜率': 44.4, '客场胜率': 28.6, '主队均球': 1.43, '客队均球': 1.11},
    '德甲': {'主场胜率': 43.0, '客场胜率': 31.9, '主队均球': 1.73, '客队均球': 1.41},
    '意甲': {'主场胜率': 41.0, '客场胜率': 32.4, '主队均球': 1.49, '客队均球': 1.29},
    '法甲': {'主场胜率': 41.7, '客场胜率': 33.5, '主队均球': 1.50, '客队均球': 1.30},
}

# 1) 收集近5年五大联赛场次
matches = []
with open('data/Matches.csv', encoding='utf-8') as f:
    rd = csv.reader(f); hdr = next(rd)
    idx = {k: hdr.index(k) for k in ['Division','MatchDate','HomeTeam','AwayTeam','FTResult','FTHome','FTAway','HomeShots','AwayShots','HomeTarget','AwayTarget','HomeCorners','AwayCorners']}
    for r in rd:
        if len(r) < len(hdr): continue
        div = r[idx['Division']]
        if div not in DIV5 or r[idx['MatchDate']][:4] < '2020': continue
        d = {'lg': DIV5[div], 'ht': r[idx['HomeTeam']], 'at': r[idx['AwayTeam']], 'res': r[idx['FTResult']]}
        try:
            d['fh'] = float(r[idx['FTHome']]); d['fa'] = float(r[idx['FTAway']])
            d['hshots'] = float(r[idx['HomeShots']]) if r[idx['HomeShots']].strip() else None
            d['ashots'] = float(r[idx['AwayShots']]) if r[idx['AwayShots']].strip() else None
            d['htarget'] = float(r[idx['HomeTarget']]) if r[idx['HomeTarget']].strip() else None
            d['atarget'] = float(r[idx['AwayTarget']]) if r[idx['AwayTarget']].strip() else None
            d['hcorn'] = float(r[idx['HomeCorners']]) if r[idx['HomeCorners']].strip() else None
            d['acorn'] = float(r[idx['AwayCorners']]) if r[idx['AwayCorners']].strip() else None
        except:
            continue
        matches.append(d)

# 2) 每队×场地聚合
def newstat(): return defaultdict(lambda: [0,0,0,0,0,0,0,0,0])  # 胜/平/负/总/进球/失球/射门/射正/角球
home = defaultdict(newstat); away = defaultdict(newstat)
for m in matches:
    h = home[m['ht']][m['lg']]; a = away[m['at']][m['lg']]
    for s in (h, a):
        s[3] += 1  # 总
    if m['res']=='H': h[0]+=1; a[2]+=1
    elif m['res']=='A': a[0]+=1; h[2]+=1
    else: h[1]+=1; a[1]+=1
    h[4]+=m['fh']; h[5]+=m['fa']; a[4]+=m['fa']; a[5]+=m['fh']
    for s, sh, ta, co in ((h, m['hshots'], m['htarget'], m['hcorn']), (a, m['ashots'], m['atarget'], m['acorn'])):
        if sh: s[6]+=sh
        if ta: s[7]+=ta
        if co: s[8]+=co

def stat_to_dict(s, base_win, base_goals):
    n = s[3]
    if n == 0: return None
    win = s[0]/n*100; draw = s[1]/n*100
    g_avg = s[4]/n; ga_avg = s[5]/n
    shots = s[6]/n if s[6] else None; target = s[7]/n if s[7] else None
    corn = s[8]/n if s[8] else None
    conv = (s[4]/s[6]*100) if s[6] else None  # 攻防转化率=进球/射门
    return {
        'n': n, '胜率%': round(win,1), '平率%': round(draw,1), '负率%': round(100-win-draw,1),
        '场均进球': round(g_avg,2), '场均失球': round(ga_avg,2), '场均净胜': round(g_avg-ga_avg,2),
        '场均射门': round(shots,1) if shots else None, '场均射正': round(target,1) if target else None,
        '场均角球': round(corn,1) if corn else None, '攻防转化率%': round(conv,1) if conv else None,
        '胜率增益pp': round(win - base_win,1), '进球增益': round(g_avg - base_goals,2),
    }

out = {'_meta': {'来源': 'Matches.csv 五大联赛近5年(2020+)·2026-08-25·HAF数据层', '联赛基准': LEAGUE_BASE, '样本不足阈值': 15},
       '_teams': {}}
all_teams = sorted(set([m['ht'] for m in matches] + [m['at'] for m in matches]))
for t in all_teams:
    entry = {}
    for lg, base in LEAGUE_BASE.items():
        hs, as_ = home[t].get(lg), away[t].get(lg)
        hd = stat_to_dict(hs, base['主场胜率'], base['主队均球']) if hs and hs[3] else None
        ad = stat_to_dict(as_, base['客场胜率'], base['客队均球']) if as_ and as_[3] else None
        if hd is None and ad is None: continue
        risk = []
        if hd and hd['n'] < 15: risk.append('主场样本不足')
        if ad and ad['n'] < 15: risk.append('客场样本不足')
        entry[lg] = {'主场': hd, '客场': ad, '样本风险': risk,
                     '主场龙系数': round(hd['胜率%']-ad['胜率%'],1) if hd and ad else None}
    if entry: out['_teams'][t] = entry

with open('data/tmp/homeaway_table.json','w',encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(f'homeaway_table.json 已生成: {len(out["_teams"])} 队')

# 3) 对抗耦合（可选·--ha 主队,客队）
def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('--team', help='查单队档案')
    ap.add_argument('--ha', help='对抗耦合: 主队,客队 (如 "Torino,Inter")')
    return ap.parse_args()
args = parse_args()

if args.team:
    t = out['_teams'].get(args.team)
    if t:
        for lg, v in t.items():
            print(f'\n{args.team} [{lg}] 主场龙系数={v["主场龙系数"]}pp 风险={v["样本风险"]}')
            print('  主场:', json.dumps(v['主场'], ensure_ascii=False))
            print('  客场:', json.dumps(v['客场'], ensure_ascii=False))
    else: print('未找到:', args.team)

if args.ha:
    hname, aname = [x.strip() for x in args.ha.split(',')]
    hlg = out['_teams'].get(hname, {}); alg = out['_teams'].get(aname, {})
    for lg in LEAGUE_BASE:
        hv = hlg.get(lg, {}).get('主场'); av = alg.get(lg, {}).get('客场')
        if hv and av:
            base = LEAGUE_BASE[lg]
            print(f'\n=== 对抗耦合 {hname}(主场) vs {aname}(客场) [{lg}] ===')
            print(f'主队主场: 胜率{hv["胜率%"]}% 场均进球{hv["场均进球"]} 失球{hv["场均失球"]} 胜率增益+{hv["胜率增益pp"]}pp 转化率{hv["攻防转化率%"]}%')
            print(f'客队客场: 胜率{av["胜率%"]}% 场均进球{av["场均进球"]} 失球{av["场均失球"]} 胜率增益{av["胜率增益pp"]}pp 转化率{av["攻防转化率%"]}%')
            # 对抗耦合 λ：三元融合（场地子集场均 + 基准-对手失球 + 基准）·clamp 0.85-1.15
            lh_raw = (hv['场均进球'] + (base['主队均球'] - av['场均失球']) + base['主队均球']) / 3
            la_raw = (av['场均进球'] + (base['客队均球'] - hv['场均失球']) + base['客队均球']) / 3
            # 失球修正系数（转化率对比·防极端）
            conv_h = hv['攻防转化率%'] or 9.0; conv_a = av['攻防转化率%'] or 9.0
            c_h = max(0.85, min(1.15, 1 + (conv_h - conv_a) / 100))
            c_a = max(0.85, min(1.15, 1 + (conv_a - conv_h) / 100))
            lh = round(lh_raw * c_h, 2); la = round(la_raw * c_a, 2)
            print(f'🔴对抗耦合 λh={lh} λa={la}（转化率修正 ×{c_h:.2f}/×{c_a:.2f}·clamp 0.85-1.15）')
            print(f'  主队主场贡献: 场均进球{hv["场均进球"]}+基准{base["主队均球"]}-客失球{av["场均失球"]} → λh={lh}')
            print(f'  客队客场贡献: 场均进球{av["场均进球"]}+基准{base["客队均球"]}-主失球{hv["场均失球"]} → λa={la}')
            # 泊松概率输出（复用 calc_poisson.probs）
            sys.path.insert(0, 'data/tmp')
            try:
                from calc_poisson import probs, pois
                ph, pd_, pa = probs(lh, la)
                p_over = 1 - sum(pois(i, lh) * pois(j, la) for i in range(3) for j in range(3 - i))
                p_over35 = 1 - sum(pois(i, lh) * pois(j, la) for i in range(4) for j in range(4 - i))
                # 亚盘 -0.5（主让半球）上盘率
                p_handi = ph + sum(pois(1, lh) * pois(0, la) * 0 + 0 for _ in [0])
                print(f'\n📊 泊松输出（HAF λ）:')
                print(f'  胜平负: 主{ph*100:.1f}% / 平{pd_*100:.1f}% / 客{pa*100:.1f}%')
                print(f'  大小球: O2.5={p_over*100:.1f}% / O3.5={p_over35*100:.1f}%')
                print(f'  亚盘主让0.5上盘率≈{ph*100:.1f}%（主胜即赢盘·平/客输盘）')
                print(f'  🔴主客场偏移: 主场增益+{hv["胜率增益pp"]}pp(基准{base["主场胜率"]}%)·客场衰减{av["胜率增益pp"]}pp(基准{base["客场胜率"]}%)·整体场地分离{base["主场胜率"]-base["客场胜率"]:+.1f}pp')
            except ImportError as e:
                print('泊松输出跳过:', e)
            break
    else:
        print('未找到共同联赛的主/客场档案')
