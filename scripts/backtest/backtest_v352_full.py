# -*- coding: utf-8 -*-
"""V3.5.52 全模块回测脚本 —— 覆盖赔率/抽水/方向/大小球/让球/硬核层/修正45A/47/50/41
用法: python data/scripts/backtest/backtest_v352_full.py > data/backtest_v352_report.txt 2>&1
"""
import csv, sys, statistics
from collections import Counter

# Windows 控制台/重定向默认 GBK，强制 UTF-8 输出（支持 ✅/🔴 等字符）
sys.stdout.reconfigure(encoding="utf-8")

PATH = "data/Matches.csv"

def fnum(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default

# 模块统计容器
stats = {
    "rows": 0, "valid": 0,
    "overround_all": [], "overround_bins": Counter(),
    "favorite": {"deep": [0,0], "mid": [0,0], "mild": [0,0], "high": [0,0]},  # [命中, 总]
    "skew": {"extreme": [0,0], "mild": [0,0], "none": [0,0]},
    "ou": {"over": [0,0], "under": [0,0], "over_strong": [0,0]},
    "handi": {},  # HandiSize -> [命中,总]
    "fix47": {"strong_over_3plus": [0,0]},
    "fix50": {"deep": [0,0], "mid": [0,0], "shallow": [0,0]},  # 净胜>=2球
    "elo41": {"agree": [0,0], "disagree": [0,0]},
    "fix45a": {"ht_home": [0,0], "ht_away": [0,0]},
    "calib": {},  # 去抽水概率分箱 -> [命中,总]
}

def safe_add(d, k, hit):
    v = d.setdefault(k, [0,0])
    v[0] += hit
    v[1] += 1

with open(PATH, encoding="utf-8", errors="ignore") as f:
    r = csv.DictReader(f)
    for row in r:
        stats["rows"] += 1
        oh, od, oa = fnum(row.get("OddHome")), fnum(row.get("OddDraw")), fnum(row.get("OddAway"))
        res = (row.get("FTResult") or "").strip()
        fth, fta = fnum(row.get("FTHome")), fnum(row.get("FTAway"))
        if not (oh and od and oa and res and fth is not None):
            continue
        stats["valid"] += 1

        # ===== 抽水模块 =====
        orr = 1.0/oh + 1.0/od + 1.0/oa - 1.0
        stats["overround_all"].append(orr)
        if orr < 0.03: bin_ = "0-3%"
        elif orr < 0.05: bin_ = "3-5%"
        elif orr < 0.08: bin_ = "5-8%"
        elif orr < 0.12: bin_ = "8-12%"
        else: bin_ = "12%+"
        stats["overround_bins"][bin_] += 1

        # ===== 方向判定(热门分层) =====
        p_h, p_d, p_a = 1/oh, 1/od, 1/oa
        s = p_h + p_d + p_a
        fav_odd = min(oh, oa)
        fav_side = "H" if oh <= oa else "A"
        hit_fav = 1 if res == fav_side else 0
        if fav_odd < 1.30: stats["favorite"]["deep"][0] += hit_fav; stats["favorite"]["deep"][1] += 1
        elif fav_odd < 1.70: stats["favorite"]["mid"][0] += hit_fav; stats["favorite"]["mid"][1] += 1
        elif fav_odd < 2.50: stats["favorite"]["mild"][0] += hit_fav; stats["favorite"]["mild"][1] += 1
        else: stats["favorite"]["high"][0] += hit_fav; stats["favorite"]["high"][1] += 1

        # ===== skew 共识分层(修正32) =====
        ph, pa = p_h/s, p_a/s
        if ph > pa: fav_p, cold_p = ph, pa
        else: fav_p, cold_p = pa, ph
        skew = (fav_p - cold_p) / cold_p * 100 if cold_p > 0 else 999
        if skew > 200: k = "extreme"
        elif skew > 100: k = "mild"
        else: k = "none"
        stats["skew"][k][0] += hit_fav; stats["skew"][k][1] += 1

        # ===== 去抽水概率校准 =====
        fav_p_true = fav_p  # 去抽水后热门隐含概率
        b = int(fav_p_true * 10) / 10  # 0.1 分箱
        safe_add(stats["calib"], b, hit_fav)

        # ===== 大小球(O/U) =====
        ou_o, ou_u = fnum(row.get("Over25")), fnum(row.get("Under25"))
        if ou_o and ou_u:
            tot = fth + fta
            over_hit = 1 if tot >= 3 else 0
            under_hit = 1 if tot <= 2 else 0
            if ou_o < ou_u:
                stats["ou"]["over"][0] += over_hit; stats["ou"]["over"][1] += 1
                if ou_o < 1.70:
                    stats["ou"]["over_strong"][0] += over_hit; stats["ou"]["over_strong"][1] += 1
                    stats["fix47"]["strong_over_3plus"][0] += over_hit; stats["fix47"]["strong_over_3plus"][1] += 1
            else:
                stats["ou"]["under"][0] += under_hit; stats["ou"]["under"][1] += 1

        # ===== 让球(HandiSize) =====
        hs = fnum(row.get("HandiSize"))
        hh, ha = fnum(row.get("HandiHome")), fnum(row.get("HandiAway"))
        if hs is not None:
            # 主队让球 hs>0: 主胜且净胜>|hs| 命中让胜
            if hs > 0:
                gd = fth - fta
                handi_hit = 1 if (gd + hs) > 0 else 0
            elif hs < 0:
                gd = fth - fta
                handi_hit = 1 if (gd + hs) > 0 else 0
            else:
                handi_hit = 1 if res != "D" else 0
            b2 = abs(hs)
            key = "0.25" if b2 <= 0.25 else ("0.5" if b2 <= 0.5 else ("0.75" if b2 <= 0.75 else ("1.0" if b2 <= 1.0 else "1.25+")))
            safe_add(stats["handi"], key, handi_hit)

        # ===== 修正50 三盘口仓位一致性 -> 净胜>=2球 =====
        fav_net2 = 0
        if fav_side == "H": fav_net2 = 1 if (fth - fta) >= 2 else 0
        else: fav_net2 = 1 if (fta - fth) >= 2 else 0
        over_p = None
        if ou_o and ou_u:
            over_p = (1/ou_o) / (1/ou_o + 1/ou_u)
        abs_hs = abs(hs) if hs is not None else 0
        if fav_odd < 1.70 and over_p is not None and over_p >= 0.5 and abs_hs >= 1.0:
            stats["fix50"]["deep"][0] += fav_net2; stats["fix50"]["deep"][1] += 1
        elif fav_odd < 1.70 and over_p is not None and over_p >= 0.5 and abs_hs < 1.0:
            stats["fix50"]["mid"][0] += fav_net2; stats["fix50"]["mid"][1] += 1
        elif fav_odd < 1.70 and over_p is not None and over_p < 0.5 and abs_hs < 1.0:
            stats["fix50"]["shallow"][0] += fav_net2; stats["fix50"]["shallow"][1] += 1

        # ===== 修正41 ELO =====
        eh, ea = fnum(row.get("HomeElo")), fnum(row.get("AwayElo"))
        if eh is not None and ea is not None and eh != ea:
            elo_side = "H" if eh > ea else "A"
            if elo_side == fav_side:
                stats["elo41"]["agree"][0] += hit_fav; stats["elo41"]["agree"][1] += 1
            else:
                stats["elo41"]["disagree"][0] += hit_fav; stats["elo41"]["disagree"][1] += 1

        # ===== 修正45A 半场传导 =====
        htr = (row.get("HTResult") or "").strip()
        if htr == "H":
            stats["fix45a"]["ht_home"][0] += 1 if res == "H" else 0
            stats["fix45a"]["ht_home"][1] += 1
        elif htr == "A":
            stats["fix45a"]["ht_away"][0] += 1 if res == "A" else 0
            stats["fix45a"]["ht_away"][1] += 1

# ================= 输出报告 =================
def pct(h, t):
    return f"{h/t*100:.1f}%" if t else "N/A"

def diff_mark(h, t, baseline, tol=2.0):
    if not t: return ""
    v = h/t*100
    d = v - baseline
    return f"  {'✅' if abs(d) <= tol else '🔴需修改'} 偏差{d:+.1f}pp (固化{baseline:.1f}%)"

print("="*72)
print("V3.5.52 全模块回测报告 (Matches.csv)")
print(f"总行数: {stats['rows']} | 有效行: {stats['valid']} | 缺失跳过: {stats['rows']-stats['valid']}")
print("="*72)

print("\n【模块1·抽水 overround】")
if stats["overround_all"]:
    med = statistics.median(stats["overround_all"])
    mean = statistics.mean(stats["overround_all"])
    print(f"  中位数: {med*100:.2f}% | 均值: {mean*100:.2f}%")
    print(f"  分布: {dict(stats['overround_bins'])}")
    high = sum(v for k, v in stats["overround_bins"].items() if "8-12" in k or "12%" in k)
    print(f"  高抽水(>8%)场次占比: {high/len(stats['overround_all'])*100:.1f}%")

print("\n【模块2·方向判定 热门分层命中率】")
for k, name, base in [("deep","深盘热门<1.30",82.4), ("mid","中热门1.30-1.70",None), ("mild","温和热门1.70-2.50",None), ("high","高赔≥2.50",None)]:
    h, t = stats["favorite"][k]
    d = diff_mark(h, t, base) if base else ""
    print(f"  {name}: {pct(h,t)} (n={t}){d}")

print("\n【模块2b·skew共识分层(修正32)】")
for k, name, base in [("extreme","极端共识>200%",67.5), ("mild","温和100-200%",53.3), ("none","无共识<100%",41.7)]:
    h, t = stats["skew"][k]
    print(f"  {name}: {pct(h,t)} (n={t}){diff_mark(h,t,base)}")

print("\n【模块2c·去抽水概率校准(热门隐含概率分箱→实际命中)】")
print("  概率箱   命中率     n")
for b in sorted(stats["calib"], reverse=True):
    h, t = stats["calib"][b]
    print(f"  {b:.1f}-{b+0.1:.1f}  {pct(h,t):>7s}  {t}")

print("\n【模块3·大小球 O/U】")
for k, name in [("over","Over25 方向"), ("under","Under25 方向"), ("over_strong","强Over(O2.5<1.70)")]:
    h, t = stats["ou"][k]
    print(f"  {name}: {pct(h,t)} (n={t})")

print("\n【模块4·让球 HandiSize 分层】")
for k in sorted(stats["handi"]):
    h, t = stats["handi"][k]
    print(f"  让球|{k}|: {pct(h,t)} (n={t})")

print("\n【模块5·修正47 强Over→≥3球率】")
h, t = stats["fix47"]["strong_over_3plus"]
print(f"  O2.5<1.70 场次实际≥3球率: {pct(h,t)} (n={t})")

print("\n【模块6·修正50 三盘口仓位一致性→净胜≥2球率】")
for k, name, base in [("deep","深盘(热门+大球+深让)",47.9), ("mid","中盘(热门+大球+浅让)",34.6), ("shallow","浅盘(热门≥1.70+小球+浅让)",30.4)]:
    h, t = stats["fix50"][k]
    print(f"  {name}: {pct(h,t)} (n={t}){diff_mark(h,t,base)}")

print("\n【模块7·修正41 ELO一致性】")
for k, name, base in [("agree","ELO与赔率一致",54.4), ("disagree","ELO与赔率背离",41.5)]:
    h, t = stats["elo41"][k]
    print(f"  {name}: {pct(h,t)} (n={t}){diff_mark(h,t,base)}")
if stats["elo41"]["agree"][1] and stats["elo41"]["disagree"][1]:
    sep = stats["elo41"]["agree"][0]/stats["elo41"]["agree"][1]*100 - stats["elo41"]["disagree"][0]/stats["elo41"]["disagree"][1]*100
    print(f"  分离度: {sep:.1f}pp")

print("\n【模块8·修正45A 半场传导】")
for k, name, base in [("ht_home","半场主胜→全场主胜率",78.6), ("ht_away","半场客胜→全场客胜率",68.1)]:
    h, t = stats["fix45a"][k]
    print(f"  {name}: {pct(h,t)} (n={t}){diff_mark(h,t,base)}")

print("\n" + "="*72)
print("🔴需修改判定: |偏差|>2pp 标记需修改；偏差≤2pp 固化值成立")
print("注: 固化值来自22.7万场回测，本脚本同源数据，偏差应≈0；如有偏差需检查脚本口径")
print("="*72)
