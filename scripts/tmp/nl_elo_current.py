# -*- coding: utf-8 -*-
"""从 intl_results.csv 计算当前 Elo（P1-3 数据管线·供 nl_model.py 输入）
算法: 时间序更新·K=20·主场等效 Elo=60.7(与公平模型一致)·期望=1/(1+10^(-d/400))
"""
import csv, io, sys, os, math, json
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
D = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(D, 'nl_data', 'intl_results.csv')
OUT = os.path.join(D, 'nl_data', 'elo_current.json')
HOME_ADV = 60.7
K = 20.0


def compute(min_year=2010):
    rows = []
    for r in csv.DictReader(io.open(SRC, encoding='utf-8')):
        d = r.get('date') or ''
        if d[:4].isdigit() and int(d[:4]) >= min_year:
            try:
                rows.append((d, r['home_team'], r['away_team'], int(r['home_score']), int(r['away_score'])))
            except Exception:
                continue
    rows.sort(key=lambda x: x[0])
    elo = {}
    for d, h, a, hs, as_ in rows:
        eh, ea = elo.get(h, 1500.0), elo.get(a, 1500.0)
        exp_h = 1.0 / (1.0 + 10 ** (-((eh + HOME_ADV) - ea) / 400.0))
        act_h = 1.0 if hs > as_ else (0.5 if hs == as_ else 0.0)
        # 净胜球加权（FIFA 风格·防大比分过度）
        g = abs(hs - as_)
        gmul = 1.0 if g <= 1 else (1.5 if g == 2 else (1.75 if g == 3 else 1.75 + (g - 3) / 8.0))
        ch = K * gmul * (act_h - exp_h)
        elo[h] = eh + ch
        elo[a] = ea - ch
    return elo, len(rows)


def main():
    elo, n = compute()
    json.dump(elo, io.open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print('数据源 intl_results.csv · 参算 %d 场（2010 年至今）· 覆盖 %d 队' % (n, len(elo)))
    print('已保存 %s' % OUT)
    md1 = [('Netherlands', 'Germany'), ('Serbia', 'Greece'), ('Norway', 'Denmark'), ('Andorra', 'Malta')]
    print('\n═══ 欧国联 Matchday 1 当前 Elo（主队-客队差）═══')
    for h, a in md1:
        eh, ea = elo.get(h), elo.get(a)
        if eh is None or ea is None:
            print('  %-12s vs %-10s ⚠️ 缺失(%s)' % (h, a, '主' if eh is None else '客')); continue
        print('  %-12s %.0f  vs  %-10s %.0f  → Elo差 %+.0f' % (h, eh, a, ea, eh - ea))


if __name__ == '__main__':
    main()
