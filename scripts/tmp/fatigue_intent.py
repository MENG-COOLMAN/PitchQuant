"""疲劳+战意量化（2026-08-29评审固化·P1-3·Step3.5情境因子新增·L3级）
用法: python fatigue_intent.py --home_games_7d 2 --away_games_7d 1 --home_games_14d 4 --away_games_14d 3 --travel_km 1200 --home_rank 3 --away_rank 15
输出: fatigue_score(主/客) + intent_score(主/客) + 调整建议(置信度档/λ)
数据来源: api-football standings(排名)+fixtures(赛程密度)+欧战旅行距离
"""
import argparse, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def fatigue(games_7d, games_14d, travel_km):
    f = 0
    if games_7d >= 3: f += 2
    elif games_7d == 2: f += 1
    if games_14d >= 5: f += 1.5
    elif games_14d == 4: f += 1
    elif games_14d == 3: f += 0.5
    if travel_km > 1500: f += 1
    elif travel_km > 500: f += 0.5
    return f

def intent(rank, cup_rotation=False, derby=False, n=20):
    s = 0
    if rank <= 4 or (rank - 4) <= 3: s += 1          # 争冠/欧战资格
    if rank >= n-2 or (rank - (n-2)) <= 3: s += 1    # 保级
    if 8 <= rank <= 15: s -= 1                       # 中游无欲无求
    if cup_rotation: s -= 1                          # 杯赛轮换
    if derby: s += 0.5                                # 德比/复仇
    return s

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    for t in ('home', 'away'):
        ap.add_argument(f'--{t}_games_7d', type=int, default=1)
        ap.add_argument(f'--{t}_games_14d', type=int, default=2)
        ap.add_argument(f'--{t}_rank', type=int, default=10)
        ap.add_argument(f'--{t}_travel_km', type=int, default=0)
    ap.add_argument('--home_cup_rotation', action='store_true'); ap.add_argument('--away_cup_rotation', action='store_true')
    ap.add_argument('--home_derby', action='store_true'); ap.add_argument('--away_derby', action='store_true')
    a = ap.parse_args()
    hf = fatigue(a.home_games_7d, a.home_games_14d, a.home_travel_km)
    af = fatigue(a.away_games_7d, a.away_games_14d, a.away_travel_km)
    hi = intent(a.home_rank, a.home_cup_rotation, a.home_derby)
    ai = intent(a.away_rank, a.away_cup_rotation, a.away_derby)
    print('🔴疲劳+战意量化(P1-3·2026-08-29评审固化·L3级):')
    print(f'  疲劳分: 主{hf:.1f} 客{af:.1f} (近7天1场=0/2场=1/3场=2·近14天≤2=0/3=0.5/4=1/≥5=1.5·旅行>1500km=1/>500km=0.5·≥2降1档+λ-0.2)')
    print(f'  战意分: 主{hi:+.1f} 客{ai:+.1f} (争冠/欧战+1·保级+1·中游-1·杯赛轮换-1·德比+0.5)')
    diff = hi - ai
    if diff >= 2: print(f'  🔴战意差{diff:+.1f}≥2 → 主队方向升1档')
    elif diff <= -2: print(f'  🔴战意差{diff:+.1f}≤-2 → 客队方向升1档')
    else: print(f'  战意差{diff:+.1f}·中性·不调整')
    if hf >= 2: print(f'  🔴主队疲劳{hf:.1f}≥2 → 主队置信度降1档·λ-0.2')
    if af >= 2: print(f'  🔴客队疲劳{af:.1f}≥2 → 客队置信度降1档·λ-0.2')
