# -*- coding: utf-8 -*-
"""quadrant_v2.py — (D,M,T) 联合象限（V3.5.77·方案 §5）

现 V6 四象限：quadrant_probs(handi, o25) = **亚盘档 × 大小球档**（2D·Matches 148,129 场统计）
V2 升级：**(D, M, T) 三维联合象限** —— 由 joint_solver 的交集池**实时聚合**（无需额外统计表），
         并与 V6 2D 象限做一致性对照。

用途：Step7 输出「四要素联合分布」+ 与 V6 交叉验证（方向/净胜/量级三边际）。

用法：
    python data/tmp/quadrant_v2.py --eu 2.865,3.43,2.667 --handi 0 --o25 2.248
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def quadrant_v2(oh, od, oa, handi=None, o25=None, u25=None, ou_line=None,
                lam_h=None, lam_a=None, league=None):
    """返回 {(D,M,T): prob} 联合象限 + 三边际 + V6 2D 对照"""
    try:
        from joint_solver import joint_anchor
    except Exception as e:
        return {"ok": False, "reason": "joint_solver 导入失败: %s" % str(e)[:60]}
    r = joint_anchor(oh, od, oa, handi, o25, u25, ou_line, lam_h, lam_a, league)
    if not r.get("ok"):
        return {"ok": False, "reason": r.get("reason")}
    cell, md, mm, mt = {}, {}, {}, {}
    for x in r.get("pool", []):
        k = (x["d"], x["m"], x["t"])
        cell[k] = round(cell.get(k, 0.0) + x["p_pct"], 2)
        md[x["d"]] = round(md.get(x["d"], 0.0) + x["p_pct"], 2)
        mm[x["m"]] = round(mm.get(x["m"], 0.0) + x["p_pct"], 2)
        mt[x["t"]] = round(mt.get(x["t"], 0.0) + x["p_pct"], 2)
    v6 = None
    try:
        from calc_v3572 import quadrant_hint
        v6 = quadrant_hint(handi=handi, o25=o25, u25=u25)
    except Exception:
        pass
    return {"ok": True, "cell": cell, "marg_d": md, "marg_m": mm, "marg_t": mt,
            "v6_2d": v6,
            "joint": {"anchor_1st": r["anchor_1st"], "anchor_2nd": r["anchor_2nd"],
                      "consistency": r["consistency"], "trust": r["trust"],
                      "lock": r["lock"], "parallel_dirs": r.get("parallel_dirs")}}


def fmt(r):
    if not r.get("ok"):
        return "❌ quadrant_v2 不可用: %s" % r.get("reason")
    L = ["【(D,M,T) 联合象限·方案 §5】"]
    for k in sorted(r["cell"], key=lambda z: -r["cell"][z])[:10]:
        L.append("   D=%s M=%+d T=%d球 → %.2f%%" % (k[0], k[1], k[2], r["cell"][k]))
    L.append("   边际 D: %s" % r["marg_d"])
    L.append("   边际 M(净胜): %s" % r["marg_m"])
    L.append("   边际 T(总进球): %s" % r["marg_t"])
    L.append("   V6 2D 对照(亚盘×大小球): %s" % r.get("v6_2d"))
    j = r["joint"]
    L.append("   主锚/次锚: %s / %s · 一致度 %s · 可信度 %s · 并列方向 %s"
             % (j["anchor_1st"], j["anchor_2nd"], j["consistency"], j["trust"], j.get("parallel_dirs")))
    return "\n".join(L)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="(D,M,T) 联合象限 V2")
    ap.add_argument("--eu", required=True, help="欧赔 主,平,客")
    ap.add_argument("--handi", type=float, default=None)
    ap.add_argument("--o25", type=float, default=None)
    ap.add_argument("--u25", type=float, default=None)
    ap.add_argument("--line", type=float, default=None)
    ap.add_argument("--lam-h", type=float, default=None)
    ap.add_argument("--lam-a", type=float, default=None)
    ap.add_argument("--league", default=None)
    a = ap.parse_args()
    oh, od, oa = [float(x) for x in a.eu.split(",")]
    print(fmt(quadrant_v2(oh, od, oa, a.handi, a.o25, a.u25, a.line, a.lam_h, a.lam_a, a.league)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
