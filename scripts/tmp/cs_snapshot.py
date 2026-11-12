# -*- coding: utf-8 -*-
"""比分盘（Correct Score）快照提取 —— PreStep 配套工具（2026-10-12）

用法:
  python data/tmp/cs_snapshot.py                     # 取最新 prestep_*.json 快照
  python data/tmp/cs_snapshot.py --file <快照.json>
  python data/tmp/cs_snapshot.py --top 20 --save     # 落盘 MD 到 snapshots/

输出（每场）:
  ① 比分盘 Top-N（赔率 + 去水概率 P_i）
  ② 方向聚合（主胜/平/客胜）—— 与 ML 去水对照（一致性自检）
  ③ 期望总进球 / 期望净胜（供 Step7 比分量级与锚定参考）

🔴 口径要点（2026-10-12 实测修正·P0）:
  1xbet 的 CS 固定返回 120 档，其中大量档位赔率 = **100（占位/未提供标记）**
  （如 0-10=100 / 9-9=100），**必须排除**——否则 Σ(1/odds) 虚高至 2.3
  （抽水 130%）、期望总进球失真（6.7 球）。排除后 Σ(1/odds)≈1.2-1.33（抽水 20-33%）合理。
  🔴 判据: `odds >= 100` → 占位（`--cap` 可调）。
  去水 = (1/odds) / Σ(1/odds)（仅对有效档·与 calc_match/cs_deep_analyzer 同口径）
"""
import argparse
import glob
import json
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "snapshots")
CS_NAME = "Correct Score"
DEFAULT_CAP = 100.0


def pick_snapshot(explicit=None):
    if explicit:
        return explicit
    cands = [p for p in glob.glob(os.path.join(SNAP, "prestep_*.json"))
             if os.path.basename(p).startswith("prestep_")]
    if not cands:
        return None
    return max(cands, key=os.path.getmtime)


def load_cs(game):
    """返回 (rows, updated_at)；rows = [{'label':.., 'odds':..}, ...]"""
    raw = game.get("raw_1xbet") or {}
    for _bk, arr in (raw.get("bookmakers") or {}).items():
        if not isinstance(arr, list):
            continue
        for m in arr:
            if isinstance(m, dict) and m.get("name") == CS_NAME:
                return m.get("odds") or [], m.get("updatedAt")
    return [], None


def parse_label(lb):
    """'1-0' / '1:0' → (1, 0)；'Other'/'AOS' → None"""
    s = str(lb).strip().replace(":", "-")
    if "-" in s:
        a, b = s.split("-", 1)
        a, b = a.strip(), b.strip()
        if a.isdigit() and b.isdigit():
            return int(a), int(b)
    return None


def split_rows(rows, cap=DEFAULT_CAP):
    """拆分有效档 / 占位档（odds >= cap 视为 1xbet 未提供）"""
    valid, capped = [], []
    for r in rows:
        try:
            od = float(r.get("odds"))
        except Exception:
            continue
        (capped if od >= cap else valid).append((r.get("label"), od))
    return valid, capped


def devig(valid):
    """等比例去水：返回 [(label, odds, p)], Σ(1/o), 抽水%"""
    inv = [1.0 / od for _lb, od in valid if od > 0]
    s = sum(inv)
    probs = [x / s if s > 0 else 0.0 for x in inv]
    vig = (s - 1) * 100 if s > 0 else 0.0
    return [(valid[i][0], valid[i][1], probs[i]) for i in range(len(valid))], s, vig


def ml_devig(game):
    """从 raw_1xbet ML 取去水概率（对照用）"""
    raw = game.get("raw_1xbet") or {}
    for _bk, arr in (raw.get("bookmakers") or {}).items():
        if not isinstance(arr, list):
            continue
        for m in arr:
            if isinstance(m, dict) and m.get("name") == "ML":
                o = m.get("odds")
                if isinstance(o, list) and o:
                    o = o[0]
                if isinstance(o, dict):
                    try:
                        vals = [1.0 / float(o[k]) for k in ("home", "draw", "away")]
                    except Exception:
                        return None
                    s = sum(vals)
                    return [v / s * 100 for v in vals]
    return None


def main():
    ap = argparse.ArgumentParser(description="比分盘（Correct Score）快照提取")
    ap.add_argument("--file", default=None, help="指定快照 json（默认取最新）")
    ap.add_argument("--top", type=int, default=15, help="每场展示 Top-N 比分（默认 15）")
    ap.add_argument("--cap", type=float, default=DEFAULT_CAP,
                    help="占位赔率阈值（>= cap 视为未提供·默认 100）")
    ap.add_argument("--save", action="store_true", help="落盘 MD 到 data/tmp/snapshots/")
    a = ap.parse_args()

    f = pick_snapshot(a.file)
    if not f or not os.path.exists(f):
        print("❌ 未找到快照（data/tmp/snapshots/prestep_*.json）")
        return 1

    d = json.load(open(f, encoding="utf-8"))
    games = d.get("games") or []
    print("=" * 96)
    print("🔴 比分盘快照（Correct Score）· %s" % os.path.basename(f))
    print("   存入时刻: %s ｜ 窗口: %s ｜ 场次: %d" % (d.get("saved_at"), d.get("window_bj"), len(games)))
    print("=" * 96)

    lines = ["# 🔴 比分盘快照（Correct Score）· %s" % os.path.basename(f), "",
             "- 存入时刻: %s" % d.get("saved_at"),
             "- 窗口: %s" % d.get("window_bj"),
             "- 场次: %d ｜ 来源: %s" % (len(games), d.get("source")),
             "- 🔴 占位档过滤: `odds >= %.0f` 视为未提供（1xbet CS 固定 120 档·含大量占位）" % a.cap,
             "- 口径: 去水 P_i = (1/odds)/Σ(1/odds)（仅有效档）", ""]

    for g in games:
        rows, upd = load_cs(g)
        head = "%s ｜ %s vs %s ｜ eventId=%s" % (g.get("kickoff_bj"), g.get("home"), g.get("away"), g.get("event_id"))
        print("\n" + "-" * 96)
        print("【%s】" % head)
        lines += ["## %s" % head, ""]

        if not rows:
            print("   ⚪ 无比分盘数据（CS 缺失）")
            lines += ["⚪ 无比分盘数据（CS 缺失）", ""]
            continue

        valid, capped = split_rows(rows, a.cap)
        if not valid:
            print("   ⚪ 无有效档（全部被判定为占位·cap=%.0f）" % a.cap)
            lines += ["⚪ 无有效档（全部占位）", ""]
            continue

        scored, invsum, vig = devig(valid)
        print("   档数: %d（有效 %d ｜ 占位≥%.0f %d） ｜ 抽水: %.2f%% ｜ updatedAt: %s"
              % (len(rows), len(valid), a.cap, len(capped), vig, upd))

        h = dr = aw = 0.0
        eg = enet = 0.0
        for lab, od, p in scored:
            sc = parse_label(lab)
            if sc is None:
                continue
            x, y = sc
            if x > y:
                h += p
            elif x == y:
                dr += p
            else:
                aw += p
            eg += p * (x + y)
            enet += p * (x - y)

        topn = sorted(scored, key=lambda t: -t[2])[: a.top]
        print("   方向聚合(去水): 主胜 %.1f%% ｜ 平 %.1f%% ｜ 客胜 %.1f%%" % (h * 100, dr * 100, aw * 100))
        print("   🔴 CS 谱系期望: %.2f 球（**截断分布·非真实期望**·禁当期望用）｜ 期望净胜: %+.2f 球" % (eg, enet))
        print("      ⚠️ 真实期望请取 _o25_expect(O2.5)（市场）/ expect_table（查表）/ 泊松 λ 和 —— 三源联动·偏差≤0.20")
        print("      ⚠️ CS 只可用于【比分谱系相对排序】——高比分档缺失致期望系统性偏高约 +0.25 球（4 场实测）")
        mlp = ml_devig(g)
        if mlp:
            print("   ML 去水对照:      主胜 %.1f%% ｜ 平 %.1f%% ｜ 客胜 %.1f%% ｜ 偏差 %+.1f/%+.1f/%+.1f pp"
                  % (mlp[0], mlp[1], mlp[2], (h * 100 - mlp[0]), (dr * 100 - mlp[1]), (aw * 100 - mlp[2])))
        print("   Top%d 比分:" % a.top)
        for i in range(0, len(topn), 5):
            print("     " + " ｜ ".join("%s=%.2f(%.2f%%)" % (t[0], t[1], t[2] * 100) for t in topn[i:i + 5]))
        if mlp:
            print("   🔴 注: CS 方向聚合与 ML 存在结构性偏差（平局偏低 ≈5-7pp）——CS 有效档仅覆盖主流比分，"
                  "高比分平局（3-3/4-4）落占位档被截断 → CS 方向仅作【比分谱系】参考，方向判定仍以 ML 为准")

        lines += [
            "- 档数: %d（有效 %d ｜ 占位 %d） ｜ 抽水: %.2f%% ｜ updatedAt: %s"
            % (len(rows), len(valid), len(capped), vig, upd),
            "- 方向聚合(去水): 主胜 **%.1f%%** ｜ 平 **%.1f%%** ｜ 客胜 **%.1f%%**" % (h * 100, dr * 100, aw * 100),
            "- 期望总进球: **%.2f 球** ｜ 期望净胜: **%+.2f 球**" % (eg, enet),
        ]
        if mlp:
            lines.append("- ML 去水对照: 主胜 %.1f%% ｜ 平 %.1f%% ｜ 客胜 %.1f%% ｜ 偏差 %+.1f/%+.1f/%+.1f pp"
                         % (mlp[0], mlp[1], mlp[2], (h * 100 - mlp[0]), (dr * 100 - mlp[1]), (aw * 100 - mlp[2])))
        lines += ["", "| 排名 | 比分 | 赔率 | 去水 P_i |", "|:-:|:-:|--:|--:|"]
        for i, (lab, od, p) in enumerate(topn, 1):
            lines.append("| %d | %s | %.2f | %.2f%% |" % (i, lab, od, p * 100))
        lines.append("")

    if a.save:
        out = os.path.join(SNAP, "cs_%s.md" % datetime.now().strftime("%Y%m%d_%H%M%S"))
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        print("\n✅ MD 落盘: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
