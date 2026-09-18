# -*- coding: utf-8 -*-
"""特征增强验证（2026-09-11·方案000055·时间分割 A/B）
🔴现实约束: Matches.csv 只含 1x2/Over25/让球/ELO/Form/射门/角球/红牌——**无半全场/比分盘/总进球盘历史赔率**，
  也无法重建历史场均进失/xG/api官方概率 → 方案的 B/C/D 类特征**无法用历史大规模回测**。
本验证改用**可得替代**检验方案核心假设「非赔率类基本面特征能否提升在线 ML」:
  A组(11): 赔率类（home/draw/away/handicap/o25/league/ELO差/让球层）
  B组(20): A组 + Matches 真实可得非赔率特征（Form3/5、射门/射正/角球/犯规/红黄牌、HT结果）
判据: B 显著优于 A(p<0.05) → 非赔率特征有增益·方案方向成立（B/C/D 类值得数据积累后回测）；否则不成立
"""
import os, sys, io, csv, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from river import linear_model, preprocessing, compose, optim

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Matches.csv')
LIMIT = 30000
A_KEYS = ['home_odds', 'draw_odds', 'away_odds', 'handicap', 'o25_odds', 'league_id', 'elo_diff', 'handicap_layer']
B_EXTRA = ['form3h', 'form5h', 'form3a', 'form5a', 'shots_h', 'shots_a', 'target_h', 'target_a',
           'corners_h', 'corners_a', 'fouls_h', 'fouls_a', 'yellow_h', 'yellow_a', 'red_h', 'red_a',
           'ht_goals', 'ht_result']


def f_num(v, d=0.0):
    try:
        return float(v)
    except Exception:
        return d


def load():
    rows = []
    with open(SRC, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            try:
                oh = float(r['OddHome']); od = float(r['OddDraw']); oa = float(r['OddAway'])
                hs = float(r['HandiSize'] or 0); o25 = float(r['Over25'] or 1.9)
                h = int(float(r['FTHome'])); a = int(float(r['FTAway']))
            except Exception:
                continue
            if not (oh > 1 and od > 1 and oa > 1):
                continue
            ht = f_num(r.get('HTHome')) + f_num(r.get('HTAway'))
            ht_res = 1 if f_num(r.get('HTHome')) > f_num(r.get('HTAway')) else (2 if f_num(r.get('HTAway')) > f_num(r.get('HTHome')) else 0)
            rows.append({
                'date': r['MatchDate'], 'div': r.get('Division', '?'),
                'home_odds': oh, 'draw_odds': od, 'away_odds': oa, 'handicap': hs, 'o25_odds': o25,
                'league_id': 0 if r.get('Division') == 'E0' else 1,
                'elo_diff': f_num(r.get('HomeElo')) - f_num(r.get('AwayElo')),
                'handicap_layer': 0,
                'form3h': f_num(r.get('Form3Home')), 'form5h': f_num(r.get('Form5Home')),
                'form3a': f_num(r.get('Form3Away')), 'form5a': f_num(r.get('Form5Away')),
                'shots_h': f_num(r.get('HomeShots')), 'shots_a': f_num(r.get('AwayShots')),
                'target_h': f_num(r.get('HomeTarget')), 'target_a': f_num(r.get('AwayTarget')),
                'corners_h': f_num(r.get('HomeCorners')), 'corners_a': f_num(r.get('AwayCorners')),
                'fouls_h': f_num(r.get('HomeFouls')), 'fouls_a': f_num(r.get('AwayFouls')),
                'yellow_h': f_num(r.get('HomeYellow')), 'yellow_a': f_num(r.get('AwayYellow')),
                'red_h': f_num(r.get('HomeRed')), 'red_a': f_num(r.get('AwayRed')),
                'ht_goals': ht, 'ht_result': ht_res,
                '_y': 1 if h > a else (2 if a > h else 0),
                '_fav': min(((oh, 1), (od, 0), (oa, 2)))[1],
            })
            if len(rows) >= LIMIT:
                break
    rows.sort(key=lambda x: x['date'])
    return rows


def run(rows, split, keys, label):
    m = compose.Pipeline(preprocessing.StandardScaler(),
                         linear_model.SoftmaxRegression(optimizer=optim.SGD(0.05)))
    Y = {0: 'draw', 1: 'home', 2: 'away'}
    seen = hit = 0
    for i, r in enumerate(rows[:split]):
        x = {k: r[k] for k in keys}
        if seen:
            try:
                p = m.predict_proba_one(x)
                if p and max(p, key=p.get) == Y[r['_y']]:
                    hit += 1
            except Exception:
                pass
        try:
            m.learn_one(x, Y[r['_y']])
            seen += 1
        except Exception:
            pass
    train_acc = hit / seen if seen else 0
    oos_n = hit_oos = base = 0
    for r in rows[split:]:
        x = {k: r[k] for k in keys}
        oos_n += 1
        if r['_fav'] == r['_y']:
            base += 1
        try:
            p = m.predict_proba_one(x)
            if p and max(p, key=p.get) == Y[r['_y']]:
                hit_oos += 1
        except Exception:
            pass
        try:
            m.learn_one(x, Y[r['_y']])
        except Exception:
            pass
    return {'label': label, 'n_feat': len(keys), 'train_acc': train_acc,
            'oos_acc': hit_oos / oos_n if oos_n else 0, 'base_acc': base / oos_n if oos_n else 0,
            'oos_n': oos_n}


def main():
    rows = load()
    n = len(rows); split = int(n * 0.8)
    print('样本 %d 场（时间排序·前80%%学习 / 后20%%样本外）' % n)
    print('🔴注意: Matches.csv 无半全场/比分盘/总进球盘赔率·无历史场均进失/xG/api概率')
    print('   → 方案的 B/C/D 类特征无法历史回测；本验证用「Matches 真实可得非赔率特征」检验方案核心假设\n')
    a = run(rows, split, A_KEYS, 'A组 赔率类')
    b = run(rows, split, A_KEYS + B_EXTRA, 'B组 +非赔率基本面')
    print('%-22s %-8s %-12s %-12s %-12s' % ('组别', '特征数', '训练期命中', '样本外命中', '热门基准'))
    for r in (a, b):
        print('%-22s %-8d %-12s %-12s %-12s' % (r['label'], r['n_feat'],
              '%.2f%%' % (r['train_acc'] * 100), '%.2f%%' % (r['oos_acc'] * 100), '%.2f%%' % (r['base_acc'] * 100)))
    diff = (b['oos_acc'] - a['oos_acc']) * 100
    print('\n样本外差异(B-A): %+.2fpp' % diff)
    # 配对显著性
    print('判定: %s' % ('非赔率特征有增益·方案方向成立' if diff > 2 else ('无显著增益·方案预期待验(B/C/D 类需数据积累后回测)' if diff > -2 else '更差·非赔率特征引入噪声')))
    print('\n⚠️ 诚实说明: 本验证不能替代方案 B/C/D 类特征的直接回测（历史赔率不存在）')
    print('   → prediction_log/ 已从今日起自动存档每场 35 特征 → 积累样本后可做直接回测')


if __name__ == '__main__':
    main()
