# -*- coding: utf-8 -*-
"""联赛赛季漂移校准（V3.5.80·2026-10-20·用户指令「意甲新赛季大球居多·平局很少」）

背景
----
`data/tmp/league_table.json` / `SK-league-*` 的 R 规则是**全历史**（意甲 8893 场）蒸馏的：
R1 平局王 27.1% / R2 均势必平 32.6% / R3 中盘平局 33.5% / R4 浅盘平局 32.1% /
R8 平赔档 33.9% / R9 半场平→全场平 38.0% / R20 平局全升权 —— 六条同向叠加，
**默认把平局顶到方向首位**。

实测（2026-10-20·案例库本季意甲 n=36）：
  平局 **4/36 = 11.1%**（vs 历史 27.1% → −16.0pp·二项 z≈−2.15·p≈0.016 单侧显著）
  场均 **2.94 球** · O2.5 **61.1%**（vs 50.2% → +10.9pp·z≈1.31 未显著）
  平局列首 9 场只兑现 1 场（11%）vs 非平局列首 27 场兑现 17 场（63%）→ **差 52pp**
→ 先验从「微弱正偏」变成「系统性误导」。

本脚本（机制通用·意甲先行）
--------------------------
任意联赛 → 从 `实战案例.csv` 算**当季实测** → 与 `league_table.json` 历史基准对比 →
输出「覆盖建议」（平局基准 / 大球基准 / 分档按因子缩放）。
启用门禁：当季 **n ≥ 20** 且 **|偏差| ≥ 8pp** → 启用；20 > n ≥ 10 → 仅提示；
n < 10 → 不启用（沿用历史基准）。🔴 分档样本必然不足（一季每档 2-5 场）→
**只按总体因子缩放 · 不重新拟合分档**，并显式标注。

用法
----
    python data/tmp/league_season_calib.py --league 意甲 [--since 2026-08-01] [--json out.json]
    python data/tmp/league_season_calib.py --all          # 五大联赛逐个体检（不启用只报告）

消费
----
`calc_all.py` 识别联赛后自动调用 `calibrate()` 并打印「🔴赛季漂移校准」块；
`SK-league-seriea` 已按本闸口实收值重写 R1/R3/R4/R7/R8/R9/R20（2026/27 覆盖块）。
"""
import argparse
import csv
import io
import json
import os
import sys
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(BASE, "..", "case-library", "实战案例.csv")
TABLE = os.path.join(BASE, "league_table.json")

# 中文联赛名 → league_table.json 键
LMAP = {
    "英超": "英超(E0)", "西甲": "西甲(SP1)", "德甲": "德甲(D1)",
    "意甲": "意甲(I1)", "法甲": "法甲(F1)",
}
# 启用门禁
MIN_N = 20          # 当季样本下限（启用覆盖）
HINT_N = 10         # 仅提示下限
MIN_DELTA_PP = 8.0  # |偏差| 阈值（pp）

DEFAULT_SINCE = "2026-08-01"


def _history(league):
    """读 league_table.json 该联赛历史基准 → dict（缺则 None）"""
    key = LMAP.get(league)
    if not key:
        return None
    try:
        d = json.load(open(TABLE, encoding="utf-8"))
    except Exception:
        return None
    blk = d.get(key)
    if not blk:
        return None
    return {
        "key": key,
        "draw": blk.get("平局率"),
        "over": blk.get("大球率"),
        "hda": blk.get("主胜档→H/D/A") or {},
        "top5": blk.get("比分Top5") or [],
    }


def season_stats(league, since=DEFAULT_SINCE):
    """案例库当季实测（真实比分口径）"""
    n = h = dr = a = 0
    goals = 0
    tot = Counter()
    scores = Counter()
    btts = 0
    listed = []
    with io.open(CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if (r.get("联赛") or "").strip() != league:
                continue
            date = (r.get("日期") or "").strip()
            if date < since:
                continue
            rb = (r.get("真实比分") or "").strip()
            if ":" not in rb:
                continue
            try:
                x, y = [int(v) for v in rb.split(":")[:2]]
            except ValueError:
                continue
            n += 1
            goals += x + y
            tot[x + y] += 1
            scores["%d:%d" % (x, y)] += 1
            if x > 0 and y > 0:
                btts += 1
            if x > y:
                h += 1
            elif x == y:
                dr += 1
            else:
                a += 1
            listed.append(r.get("case_id"))
    if not n:
        return None
    o25 = sum(v for k, v in tot.items() if k >= 3)
    o35 = sum(v for k, v in tot.items() if k >= 4)
    return {
        "n": n, "home": 100.0 * h / n, "draw": 100.0 * dr / n, "away": 100.0 * a / n,
        "avg_goals": goals / float(n), "over25": 100.0 * o25 / n, "over35": 100.0 * o35 / n,
        "btts": 100.0 * btts / n,
        "score_top": scores.most_common(6),
        "draw_scores": sum(v for k, v in scores.items() if k.split(":")[0] == k.split(":")[1]),
        "cases": listed,
    }


def calibrate(league, since=DEFAULT_SINCE):
    """核心：当季实测 vs 历史基准 → 覆盖建议（含启用门禁与三态）"""
    cur = season_stats(league, since)
    his = _history(league)
    out = {"league": league, "since": since, "current": cur, "history": his,
           "enabled": False, "status": "", "suggest": {}, "notes": []}
    if cur is None:
        out["status"] = "⚪ 当季无已复盘场次（不可校准·沿用历史基准）"
        return out
    if his is None:
        out["status"] = "⚪ 该联赛无历史基准表（仅输出当季实测·不改判定）"
        return out
    d_draw = cur["draw"] - (his["draw"] or 0)
    d_over = cur["over25"] - (his["over"] or 0)
    out["delta_draw"] = d_draw
    out["delta_over"] = d_over
    if cur["n"] < HINT_N:
        out["status"] = "⚪ 当季样本 %d 场 < %d → 样本不足·沿用历史基准" % (cur["n"], HINT_N)
        return out
    if cur["n"] < MIN_N:
        out["status"] = ("⚠️ 当季样本 %d 场（%d~%d）→ 仅提示: 平局 %+.1fpp / 大球 %+.1fpp·不改判定"
                         % (cur["n"], HINT_N, MIN_N - 1, d_draw, d_over))
        return out
    if abs(d_draw) < MIN_DELTA_PP and abs(d_over) < MIN_DELTA_PP:
        out["status"] = ("⚪ 当季 n=%d 与历史基准偏差均 < %.0fpp（平局 %+.1f / 大球 %+.1f）→ 无需校准"
                         % (cur["n"], MIN_DELTA_PP, d_draw, d_over))
        return out
    # 🔴 启用：总体值直接取当季实测；分档按因子缩放（不重拟合）
    kd = cur["draw"] / his["draw"] if his["draw"] else None
    ko = cur["over25"] / his["over"] if his["over"] else None
    out["enabled"] = True
    out["status"] = ("🔴 启用当季校准: n=%d · 平局 %.1f%%（历史 %.1f%%·%+.1fpp）· 大球 %.1f%%（历史 %.1f%%·%+.1fpp）"
                     % (cur["n"], cur["draw"], his["draw"], d_draw,
                        cur["over25"], his["over"], d_over))
    out["factors"] = {"draw": kd, "over": ko}
    sug = {"draw": round(cur["draw"], 1), "over25": round(cur["over25"], 1),
           "avg_goals": round(cur["avg_goals"], 2), "over35": round(cur["over35"], 1),
           "btts": round(cur["btts"], 1),
           "home": round(cur["home"], 1), "away": round(cur["away"], 1)}
    # 分档 H/D/A 缩放（仅平局列 + 大球率；H/A 按剩余比例归一）
    scaled = {}
    for band, vals in (his["hda"] or {}).items():
        if not isinstance(vals, (list, tuple)) or len(vals) != 3:
            continue
        hh, dd, aa = [float(v) for v in vals]
        dd2 = dd * kd if kd is not None else dd
        rest = max(0.0, 100.0 - dd2)
        s = (hh + aa) or 1.0
        scaled[band] = [round(hh / s * rest, 1), round(dd2, 1), round(aa / s * rest, 1)]
    sug["hda_scaled"] = scaled
    out["suggest"] = sug
    out["notes"].append("分档样本必然不足（一季每档 2-5 场）→ **只按总体因子缩放·未重新拟合**")
    out["notes"].append("平局因子 k=%.2f · 大球因子 k=%.2f" % (kd or 0, ko or 0))
    return out


def fmt(res):
    L = []
    c = res.get("current")
    L.append("🔴 赛季漂移校准（league_season_calib·%s 起·门禁 n≥%d & |Δ|≥%.0fpp）"
             % (res["since"], MIN_N, MIN_DELTA_PP))
    if c:
        L.append("   当季实测: n=%d · 主 %.1f%% / 平 %.1f%% / 客 %.1f%% · 场均 %.2f 球 · O2.5 %.1f%% · O3.5 %.1f%% · BTTS %.0f%%"
                 % (c["n"], c["home"], c["draw"], c["away"], c["avg_goals"],
                    c["over25"], c["over35"], c["btts"]))
        L.append("   比分Top: " + ", ".join("%s %d" % (k, v) for k, v in c["score_top"]))
    L.append("   " + res["status"])
    if res.get("enabled"):
        s = res["suggest"]
        L.append("   → 覆盖建议: 平局基准 **%.1f%%** · 大球基准 **%.1f%%** · 场均 %.2f · BTTS %.0f%%"
                 % (s["draw"], s["over25"], s["avg_goals"], s["btts"]))
        L.append("   → 分档按因子缩放（示例 2.1-2.5档: %s → %s）"
                 % (",".join(str(x) for x in (res["history"]["hda"].get("2.1-2.5") or [])),
                    ",".join(str(x) for x in (s["hda_scaled"].get("2.1-2.5") or []))))
        for n in res.get("notes") or []:
            L.append("   ⚠️ " + n)
    return "\n".join(L)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--league", default="意甲")
    ap.add_argument("--since", default=DEFAULT_SINCE)
    ap.add_argument("--json", default=None)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    if a.all:
        for lg in LMAP:
            print(fmt(calibrate(lg, a.since)))
            print("")
        return
    res = calibrate(a.league, a.since)
    print(fmt(res))
    if a.json:
        with io.open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        print("   [json] " + a.json)


if __name__ == "__main__":
    main()
