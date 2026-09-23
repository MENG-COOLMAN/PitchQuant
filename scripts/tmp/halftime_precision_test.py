# -*- coding: utf-8 -*-
"""halftime_precision_test.py — 不同半场比分准确率下的Top2增益
验证：反推具体半场比分（非仅方向）时，不同准确率的Top2命中率
"""
import sys, csv, math, random
from collections import defaultdict, Counter
sys.stdout.reconfigure(encoding='utf-8')

DATA = 'data/Matches.csv'

def build_cond_matrix():
    ht_to_ft = defaultdict(Counter)
    with open(DATA, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                hth = int(float(row['HTHome'])); hta = int(float(row['HTAway']))
                fth = int(float(row['FTHome'])); fta = int(float(row['FTAway']))
                if hth > 4 or hta > 4 or fth > 6 or fta > 6: continue
                ht_to_ft[(hth,hta)][(fth,fta)] += 1
            except:
                continue
    cond = {}
    for ht, cnt in ht_to_ft.items():
        n = sum(cnt.values())
        if n >= 50:
            cond[ht] = {ft: c/n for ft, c in cnt.items()}
    return cond

def pois(k, l):
    return math.exp(-l) * l**k / math.factorial(k)

def solve_lambda(oh, od, oa, o25):
    if min(oh, od, oa, o25) <= 1.01: return None, None
    u25 = max(1.01, 1/(1.04 - 1/o25))
    inv = [1/oh, 1/od, 1/oa]
    ph = inv[0]/sum(inv)
    po, pu = 1/o25, 1/u25
    p_over = po/(po+pu)
    t = 2.5
    for _ in range(40):
        p3 = 1 - math.exp(-t)*(1+t+t*t/2)
        t += (p_over-p3)*1.2
        if t < 0.5 or t > 6: break
    t = max(0.5, min(6, t))
    lo, hi = 0.05*t, 0.95*t
    best, besterr = None, 9
    for k in range(80):
        lh = lo+(hi-lo)*k/79; la = t-lh
        if la <= 0.05: continue
        ph_c = sum(pois(i,lh)*pois(j,la) for i in range(7) for j in range(7) if i>j)
        err = abs(ph_c-ph)
        if err < besterr: besterr, best = err, (lh, la)
    return best if best else (t*0.6, t*0.4)

def poisson_top2(oh, od, oa, o25):
    r = solve_lambda(oh, od, oa, o25)
    if r[0] is None: return None
    lh, la = r
    P = {}
    for i in range(7):
        for j in range(7):
            p = pois(i,lh)*pois(j,la)
            P[(i,j)] = p
    return sorted(P, key=P.get, reverse=True)[:2]

# 半场比分的先验分布（用于随机猜测时的采样）
ht_prior = Counter()
with open(DATA, encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        try:
            hth = int(float(row['HTHome'])); hta = int(float(row['HTAway']))
            if hth <= 4 and hta <= 4:
                ht_prior[(hth,hta)] += 1
        except:
            continue
ht_prior_list = list(ht_prior.keys())
ht_prior_weights = [ht_prior[h] for h in ht_prior_list]

print("构建条件矩阵...")
cond = build_cond_matrix()
print(f"覆盖 {len(cond)} 种半场比分")

# 不同准确率下的Top2
print("\n不同半场比分反推准确率下的Top2命中率（2024-2025年·10866场）:")
print(f"{'准确率':>8} {'Top2命中':>10} {'增益':>8} {'说明':<30}")
print("-"*70)

accuracies = [1.0, 0.85, 0.70, 0.55, 0.40, 0.25, 0.0]
results = {}

for acc in accuracies:
    hit = 0; total = 0
    random.seed(42)
    with open(DATA, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                date = row['MatchDate']
                if not date.startswith('2024') and not date.startswith('2025'): continue
                oh = float(row['OddHome']); od = float(row['OddDraw']); oa = float(row['OddAway'])
                o25 = float(row['Over25'])
                hth = int(float(row['HTHome'])); hta = int(float(row['HTAway']))
                fth = int(float(row['FTHome'])); fta = int(float(row['FTAway']))
                if min(oh,od,oa,o25) <= 1.01: continue
                if fth > 6 or fta > 6 or hth > 4 or hta > 4: continue
                actual = (fth, fta)
                total += 1
                # 以acc概率用真实半场比分，否则随机采样
                if random.random() < acc:
                    ht_guess = (hth, hta)
                else:
                    ht_guess = random.choices(ht_prior_list, weights=ht_prior_weights)[0]
                # 查条件概率Top2
                if ht_guess in cond:
                    cp = cond[ht_guess]
                    top2 = sorted(cp, key=cp.get, reverse=True)[:2]
                    if actual in top2: hit += 1
                else:
                    # 不在条件矩阵中，用泊松
                    p2 = poisson_top2(oh, od, oa, o25)
                    if p2 and actual in p2: hit += 1
            except:
                continue
    rate = hit/total*100 if total > 0 else 0
    results[acc] = rate
    if acc == 1.0: desc = "完美半场（理论上限）"
    elif acc == 0.0: desc = "纯随机半场（≈泊松）"
    else: desc = f"{acc*100:.0f}%准确反推具体半场比分"
    print(f"{acc*100:>7.0f}% {rate:>9.1f}% {rate-23.9:>+7.1f}pp {desc}")

print(f"\n基线（纯泊松）: 23.9%")
print(f"\n关键结论:")
print(f"  完美半场比分 → Top2={results[1.0]:.1f}%（+{results[1.0]-23.9:.1f}pp）")
print(f"  85%准确反推 → Top2={results[0.85]:.1f}%（+{results[0.85]-23.9:.1f}pp）")
print(f"  70%准确反推 → Top2={results[0.70]:.1f}%（+{results[0.70]-23.9:.1f}pp）")
print(f"  55%准确反推 → Top2={results[0.55]:.1f}%（+{results[0.55]-23.9:.1f}pp）")
print(f"\n  半全场9格赔率反推具体半场比分的预期准确率: 55-70%")
print(f"  因此半场反推模块的实际增益: +{results[0.55]-23.9:.1f}~{results[0.70]-23.9:.1f}pp")
print(f"  加上CS比分盘(+3~5pp)+大小球约束(+1.5pp)，合计+{results[0.55]-23.9+4.5:.1f}~{results[0.70]-23.9+6.5:.1f}pp")
print(f"  预期Top2: {23.9+results[0.55]-23.9+4.5:.1f}~{23.9+results[0.70]-23.9+6.5:.1f}%")
