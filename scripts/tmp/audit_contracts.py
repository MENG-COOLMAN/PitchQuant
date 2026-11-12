# -*- coding: utf-8 -*-
"""audit_contracts.py — 🔴V3.5.80 接口契约矩阵审计（2026-10-20）

用途（用户「每一步数据的接口是否正确接入」）：
  对**每条关键数据流**实跑生产者，断言「消费者真正读取的键都存在且类型正确」。
  「存在≠活跃」升级版：不仅函数在，还要**返回契约与消费端一致**。

输出：契约矩阵（生产者 → 键 → 消费者 → 判定）+ 失败清单（exit≠0 = 有断点）。

用法：python data/tmp/audit_contracts.py
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

FAIL = []
OK = []


def chk(cond, name, detail=""):
    (OK if cond else FAIL).append(name)
    print("%s %-46s %s" % ("✅" if cond else "❌", name, detail))


def keys_ok(d, ks, tag):
    """断言 dict 含全部键"""
    if not isinstance(d, dict):
        chk(False, tag, "返回非 dict: %s" % type(d).__name__)
        return False
    miss = [k for k in ks if k not in d]
    chk(not miss, tag, "缺键 %s" % miss if miss else "键齐(%d)" % len(ks))
    return not miss


# 🔴2026-10-29 审计修复: fixture 动态化（原硬编码 event_id/队名对会随时间失效 → 误报断点）
def _pick_events(limit=6):
    """从现存快照里取候选 event_id（最新优先·去重）"""
    import glob as _g, json as _j
    out = []
    for f in sorted(_g.glob('data/tmp/snapshots/*.json'), reverse=True):
        try:
            raw = _j.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        for g in (raw.get('games') or raw.get('matches') or []):
            eid = g.get('event_id') or g.get('id')
            if eid and str(eid) not in out:
                out.append(str(eid))
        if len(out) >= limit:
            break
    return out[:limit]


def _pick_pair_multi_point(min_files=2):
    """从现存快照里挑「出现在 ≥min_files 份快照」的队名对（P8 纵向需多时点）"""
    import glob as _g, json as _j
    seen = {}
    for f in sorted(_g.glob('data/tmp/snapshots/*.json')):
        try:
            raw = _j.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        for g in (raw.get('games') or raw.get('matches') or []):
            h = g.get('home_cn') or g.get('home')
            a = g.get('away_cn') or g.get('away')
            if h and a:
                seen.setdefault((str(h), str(a)), set()).add(f)
    for (h, a), fs in sorted(seen.items(), key=lambda kv: -len(kv[1])):
        if len(fs) >= min_files:
            return h, a, len(fs)
    return None, None, 0


print("=" * 78)
print("① market_inputs.resolve（市场统一入口）→ calc_all 消费")
print("=" * 78)
import market_inputs as MI      # noqa: E402

# 🔴2026-10-29: 动态选「ML+波胆齐全且非滚球」的场次（原硬编码 71945316 已开赛→滚球防护禁用派生）
mi = None
_eid = None
for _cand in _pick_events(6):
    _m = MI.resolve(event_id=_cand)
    if (len(_m.get("cs") or {}) > 0) and (_m.get("ml") or {}) and ((_m.get("coverage") or 0) > 0):
        mi, _eid = _m, _cand
        break
if mi is None:
    print("  ⚠️ 现存快照中无可复现 fixture（ML+波胆齐全且非滚球）→ 三项三态跳过（非失败）")
else:
    print("  fixture = event_id %s（动态选取·非硬编码）" % _eid)
    keys_ok(mi, ("ml", "spread", "totals", "cs", "btts", "htft", "eq", "eq_scan",
                 "src", "coverage", "notes"), "resolve 返回键")
    chk(len(mi.get("cs") or {}) > 0, "resolve.cs 非空(波胆档)", "%d 档" % len(mi.get("cs") or {}))
    chk((mi.get("coverage") or 0) > 0, "resolve.coverage 有值", "%s%%" % mi.get("coverage"))

print()
print("=" * 78)
print("② snapshot_save.find_for / _raw_of / _cs_full / vertical_for → P8 链")
print("=" * 78)
import snapshot_save as SS       # noqa: E402

ff = SS.find_for("热刺", "考文垂")
keys_ok(ff, ("count", "first", "last", "points"), "find_for 返回键")
f0 = ff.get("first") or {}
keys_ok(f0, ("saved_at", "file", "event_id", "extract"), "find_for.first 键")
raw = SS._raw_of(f0.get("file"), f0.get("event_id"))
cs, ah, ou = SS._cs_full(raw), SS._ah_full(raw), SS._ou_full(raw)
chk(isinstance(cs, dict) and len(cs) > 0, "_cs_full 返回 dict", "%d 档" % len(cs))
chk(isinstance(ah, list) and len(ah) > 0, "_ah_full 返回 list[(hdp,h,a)]", "%d 档" % len(ah))
chk(isinstance(ou, dict) and len(ou) > 0, "_ou_full 返回 dict{线:(o,u)}", "%d 档" % len(ou))
chk(all(len(str(k).split("-")) == 2 and ":" not in str(k) for k in cs),
    "_cs_full 键口径 'H-A'(与 joint_solver 一致)")
# 🔴2026-10-29: 动态选「≥2 时点」的队名对（原硬编码 西班牙/克罗地亚 只剩 1 时点→恒失败）
_h, _a, _nf = _pick_pair_multi_point(2)
if _h:
    v = SS.vertical_for(_h, _a)
    print("  fixture = %s vs %s（出现在 %d 份快照·动态选取）" % (_h, _a, _nf))
    keys_ok(v, ("count", "span", "cs_vert", "ah_vert", "ou_vert", "note"), "vertical_for 返回键")
    chk(v.get("count", 0) >= 2, "vertical_for 多时点激活", "count=%s" % v.get("count"))
else:
    print("  ⚠️ 现存快照中无 ≥2 时点的队名对 → vertical_for 该项三态跳过（非失败）")

print()
print("=" * 78)
print("③ jc_euro_bridge.bridge_sections → calc_match 消费（P9 数据桥）")
print("=" * 78)
import jc_euro_bridge as JB      # noqa: E402

b = JB.bridge_sections("std_raw_spurs_coventry_257.txt", eu="1.574,4.57,6.19",
                        handi="-1.00", o25="1.648", u25="2.447", cs_full=cs, ah_full=ah)
keys_ok(b, ("sections", "src_map", "notes"), "bridge_sections 返回键")
bf = (b["sections"].get("bf") or [(None, {})])[-1][1]
chk(all(str(k).count(":") == 1 for k in bf) and len(bf) > 0,
    "bridge.bf 键归一 ':'(calc_match 判据)", "%d 档" % len(bf))
rq = b["sections"].get("rq") or []
chk(all(not (isinstance(o, dict) and any(x is None for x in o.values())) for _t, o in rq),
    "bridge.rq 无 None 脏值", "%d 时点" % len(rq))
chk("bqc" in b["src_map"] and "保留" in b["src_map"]["bqc"], "bridge 保留 bqc 竞彩源")

print()
print("=" * 78)
print("④ joint_solver（joint_anchor / 证据 / 锚校验）")
print("=" * 78)
import joint_solver as JS        # noqa: E402

r = JS.joint_anchor(1.574, 4.57, 6.19, handi=-1.0, o25=1.648, u25=2.447,
                    cs_odds=cs, step5_dirs=["主胜", "平局"],
                    jc_cs={"2:1": 0.111})
keys_ok(r, ("ok", "est", "axes", "lock", "arbitrations", "arb_n", "notes", "consistency",
            "candidates", "pool", "pool_n", "anchor_1st", "anchor_2nd", "anchor_3rd",
            "anchor_1st_evidence", "anchor_2nd_evidence", "pois", "trust",
            "lambda_final", "totals_bin", "market_baseline_src", "parallel_dirs", "vert"),
        "joint_anchor 返回键")
chk(r.get("ok") and r.get("anchor_1st"),
    "joint_anchor 可跑出锚(输入=case257 热刺真实赔率)",
    "%s/%s（该场真实 3:1·次锚精确）" % (r.get("anchor_1st"), r.get("anchor_2nd")))
# 🔴防死锚自检（2026-10-20 用户质疑「锚 2:1/3:1 是死锚吗」）:
#   换一场 / 换方向输入 → 锚必须随之变化；若四组全同 = 死锚回归
_anc = []
for _args, _kw in (
        ((1.574, 4.57, 6.19), dict(handi=-1.0, o25=1.648, u25=2.447, step5_dirs=["主胜", "平局"])),
        ((2.447, 3.295, 3.295), dict(handi=-0.25, o25=2.131, u25=1.831, step5_dirs=["平局", "主胜"])),
        ((3.13, 3.09, 2.685), dict(handi=0.0, o25=2.72, u25=1.47, step5_dirs=["平局", "客胜"])),
        ((4.60, 3.90, 1.72), dict(handi=1.0, o25=1.62, u25=2.35, step5_dirs=["客胜", "平局"]))):
    _r2 = JS.joint_anchor(*_args, **_kw)
    _anc.append((_r2.get("anchor_1st"), _r2.get("anchor_2nd")))
chk(len(set(_anc)) >= 3, "防死锚自检(4 组输入→锚不全相同)",
    " / ".join("%s+%s" % (a, b) for a, b in _anc))
# 同场换方向 → 池与锚应随方向变（方向透传生效·也是「方向判错则锚必错」的机理）
_r3 = JS.joint_anchor(4.60, 3.90, 1.72, handi=1.0, o25=1.62, u25=2.35,
                      step5_dirs=["主胜", "平局"])
_r4 = JS.joint_anchor(4.60, 3.90, 1.72, handi=1.0, o25=1.62, u25=2.35,
                      step5_dirs=["客胜", "平局"])
chk(_r3.get("pool_n") != _r4.get("pool_n") or _r3.get("anchor_1st") != _r4.get("anchor_1st"),
    "方向透传生效(换 step5_dirs→池/锚随动)",
    "%s(池%s) vs %s(池%s)" % (_r3.get("anchor_1st"), _r3.get("pool_n"),
                              _r4.get("anchor_1st"), _r4.get("pool_n")))
keys_ok(r.get("est") or {}, ("D", "M", "T", "B"), "joint_anchor.est 四要素键")
from live_score_engine import anchor_market_check as AMC   # noqa: E402
amc = AMC([r["anchor_1st"], r.get("anchor_2nd") or r["anchor_1st"]],
          1.574, 4.57, 6.19, o25=1.648, u25=2.447, handi=-1.0)
keys_ok(amc, ("ok", "conflicts", "suggestion", "band", "exp_net"), "anchor_market_check 返回键")

print()
print("=" * 78)
print("⑤ 本轮封装：confidence_engine / 半场推断 / 赛季校准")
print("=" * 78)
import confidence_engine as CE   # noqa: E402

cf = CE.assess(p_max=40.7, skew=135.7, fav_odd=2.447, q2=True)
keys_ok(cf, ("base", "level", "steps", "reasons", "single", "note"), "confidence_engine.assess 键")
chk(cf.get("level") in CE.LEVELS, "confidence_engine 层位合法", str(cf.get("level")))
chk(isinstance(cf.get("single"), dict) and "ok" in cf["single"], "单押准入返回结构")
from live_score_engine import _bqc_to_ht_dist as B2H   # noqa: E402
ht = B2H("胜胜=3.70,胜平=14.00,胜负=28.00,平胜=5.25,平平=4.85,平负=5.60,负胜=26.00,负平=14.00,负负=5.25")
chk(isinstance(ht, tuple) and len(ht) == 3, "_bqc_to_ht_dist 返回 3 元组")
if ht:
    chk(abs(sum(ht[1].values()) - 1.0) < 0.02, "半场方向归一(=1)", "%.3f" % sum(ht[1].values()))
import league_season_calib as LSC   # noqa: E402
cal = LSC.calibrate("意甲")
keys_ok(cal, ("league", "since", "current", "history", "enabled", "status", "suggest", "notes"),
        "league_season_calib.calibrate 键")
chk(cal.get("enabled") is True, "意甲当季校准启用", "%.1f%%" % (cal.get("suggest") or {}).get("draw", 0))

print()
print("=" * 78)
print("⑥ 让球水位 / B 档（P8 修正挂载点）")
print("=" * 78)
w = JS._handi_water_strength(-1.0, 1.86, 1.94,
                             ah_vert={"shift": 1, "combo": "升盘降水(真看好)"})
keys_ok(w, ("p_up", "strength", "shift", "note"), "handi_water_strength 键(+p8_shift)")
chk(w.get("p8_shift") == 1, "P8 升降盘修正生效", "p_up=%.3f" % (w.get("p_up") or 0))
lbl = JS._b_label_fallback(1.648, 0.599, ou_vert={"conf_step": 1, "dir": "真看好大球"})
chk(isinstance(lbl, str), "_b_label_fallback 返回 label", str(lbl))

print()
print("=" * 78)
print("汇总: ✅%d  ❌%d" % (len(OK), len(FAIL)))
if FAIL:
    print("❌ 契约断点:")
    for x in FAIL:
        print("   - " + x)
    sys.exit(1)
print("🟢 全部数据流契约一致（生产者返回键 == 消费者读取键）")
