# -*- coding: utf-8 -*-
"""P52 端到端链路审计（2026-10-31·用户要求「挨着挨着审计·有没有数据链断裂」）

审计实证的 3 处断链（修复前）:
  ① calc_all 的 report/anchor_requirement/span_requirement 只喂 print → 零传导
  ② market_distribution 全文件 grep `big_pool|classify|LEVELS|required` = 全空 → 分级未进锚定模块
  ③ anchor_select 次锚跨度硬编码 `max(a1+1, round(line))` = 与 span_requirement 双副本

三段断言（仿 audit_p8_vertical·可挂 check_sync）:
  ① 数据层：level_from_line / required_bins / span_requirement 输出正确
  ② 消费层：A/B 实测 —— 超大球(L4/L5) vs 大球(L3/L2) 的 池/次锚/量级分 必须不同
  ③ 接线层：market_distribution 真引用 big_pool_policy（禁回退 print-only）
"""
import sys
import os

WS = r"<HOME>\AppData\Roaming\reasonix\global-workspace"
os.chdir(WS)
sys.path.insert(0, os.path.join(WS, "data", "tmp"))
sys.stdout.reconfigure(encoding='utf-8')

FAIL = []


def chk(cond, msg):
    print(("  ✅ " if cond else "  ❌ ") + msg)
    if not cond:
        FAIL.append(msg)


def _tot(s):
    try:
        return sum(int(x) for x in str(s).split(":")[:2])
    except Exception:
        return 0


print("【① 数据层】big_pool_policy 分级函数")
import big_pool_policy as B

for line, exp in ((3.95, 'L5'), (3.55, 'L4'), (3.20, 'L3'), (2.75, 'L2'), (2.40, 'L0')):
    got = B.level_from_line(line, None)
    chk(got == exp, "level_from_line(线%.2f) = %s（期望 %s）" % (line, got, exp))
chk(B.required_bins('L5') == [4, 5, 6, 7], "required_bins(L5) = %s" % B.required_bins('L5'))
chk(B.required_bins('L4') == [4, 5, 6], "required_bins(L4) = %s" % B.required_bins('L4'))
chk(B.span_requirement(3.95, 'L5', 2) == 5, "span(L5·线3.95·主锚2球) = %d（期望 5）" % B.span_requirement(3.95, 'L5', 2))
chk(B.span_requirement(3.55, 'L4', 2) == 4, "span(L4·线3.55·主锚2球) = %d（期望 4）" % B.span_requirement(3.55, 'L4', 2))
chk(B.span_requirement(3.20, 'L3', 2) == 3, "span(L3·线3.20·主锚2球) = %d（期望 3）" % B.span_requirement(3.20, 'L3', 2))
chk(B.span_requirement(2.75, 'L2', 2) == 0, "span(L2) = 0（不限）")

print("\n【③ 接线层】market_distribution / calc_all 真引用（禁 print-only）")
_src = open("data/tmp/market_distribution.py", encoding="utf-8").read()
chk("big_pool_policy" in _src, "market_distribution 引用 big_pool_policy")
chk("level_from_line" in _src, "market_distribution 调 level_from_line（单一口径）")
chk("required_bins" in _src, "market_distribution 调 required_bins（宽池必含）")
chk("_BPP52s.span_requirement" in _src, "anchor_select 次锚跨度走 span_requirement（消除双副本）")
chk("_P52_REQ" in _src, "宽池必含 _P52_REQ 已接线")
chk("_lv_floor" in _src, "量级分项分级叠加已接线")
# 🔴2026-11-03 用户指令「宽池里的比分也得符合市场信号，而不是硬锚」：
#   补入现在必须过市场信号门槛 → 该档候选全不合格时**应明确拒收**（禁硬塞）。
#   判据从「必须有补入」改为「补入 或 拒收 二者其一留痕」，并额外要求门槛存在。
chk(("宽池补入" in _src and "市场信号" in _src) or "宽池**拒收**" in _src,
    "宽池补入/拒收有留痕（带市场信号门槛·禁按档硬塞）")
chk("_wl_gate" in _src, "宽池补入过市场信号门槛（方向/净胜/受让/波胆/支持度）")
_ca = open("data/tmp/calc_all.py", encoding="utf-8").read()
chk("_bp_pol.get('level')" in _ca, "calc_all 分级输出在")

print("\n【② 消费层】A/B 实测：不同分级 → 池/次锚/量级分 是否变")
import market_distribution as M


def _mk_mm():
    """真实结构: mm['matrix']['matrix']={(h,a):p}（元组键）+ total.p[list] + margin.p[dict]"""
    n = 7
    mat = {}
    for h in range(n):
        for a in range(n):
            t = h + a
            w = {0: .01, 1: .04, 2: .12, 3: .26, 4: .28, 5: .18, 6: .11}.get(t, 0.0)
            w *= (1.25 if h > a else (1.0 if h == a else 0.8))
            mat[(h, a)] = w
    for k, v in {(1, 0): .60, (1, 1): .55, (0, 0): .40, (2, 0): .35, (0, 1): .30}.items():
        mat[k] *= (1 + v)      # 还原「概率天然低分」的病态分布
    s = sum(mat.values())
    mat = {k: v / s for k, v in mat.items()}
    pT = [0.0] * 8
    pM = {}
    for (h, a), v in mat.items():
        pT[min(7, h + a)] += v
        pM[h - a] = pM.get(h - a, 0.0) + v
    return {"matrix": {"matrix": mat,
                       "top": ["%d:%d" % k for k, _ in sorted(mat.items(), key=lambda kv: -kv[1])[:6]],
                       "expT": sum((h + a) * v for (h, a), v in mat.items()),
                       "expM": sum((h - a) * v for (h, a), v in mat.items())},
            "total": {"p": pT}, "margin": {"p": pM}, "health": "ok"}


mm = _mk_mm()
_mat = mm["matrix"]["matrix"]
pool = ["%d:%d" % k for k, v in sorted(_mat.items(), key=lambda kv: -kv[1])[:12]]
pool += ["3:0", "4:0", "3:2", "4:1", "5:2", "6:0"]

# 场景照 (oh, od, oa, handi, lam)：lam 决定 _E25 → _line_eq → 层级
CASES = [("L5 极超大球", 1.45, 5.20, 9.00, -2.0, 4.10),
         ("L4 超大球", 1.80, 3.90, 4.20, -1.5, 3.55),
         ("L3 大球很强", 1.95, 3.50, 3.80, -1.0, 3.20),
         ("L2 大球", 2.10, 3.30, 3.30, -0.5, 2.75),
         ("L0 非大球", 2.40, 3.20, 2.90, 0.0, 2.35)]
res = {}
for name, oh, od, oa, hd, lm in CASES:
    r = M.anchor_select(mm, oh=oh, od=od, oa=oa, handi=hd,
                        bt_yes=1.85, bt_no=1.95, lam=lm, pool=pool)
    a1, a2 = r.get("anchor_1st"), r.get("anchor_2nd")
    sp = r.get("score_pool") or []
    _p52 = [n for n in (r.get("notes") or []) if "P52" in n]
    _lv = ""
    for n in _p52:
        if "P52 超大球分级" in n:
            for tag in ("L5", "L4", "L3", "L2", "L1", "L0"):
                if "分级: %s" % tag in n:
                    _lv = tag
                    break
            break
    res[name] = dict(a1=a1, a2=a2, pool=[x["score"] for x in sp],
                     lv=_lv, p52=_p52)
    print("\n  【%s】主锚=%s 次锚=%s（%d球）｜判级=%s" % (name, a1, a2, _tot(a2), _lv or "未留痕"))
    print("     池(%d个): %s" % (len(sp), " ".join("%s/%.2f" % (x["score"], x["support"]) for x in sp[:10])))
    for n in _p52:
        print("     · " + n[:150])

print("\n  ── A/B 判定 ──")
chk(all(v["lv"] for v in res.values()), "全部场景均有 P52 判级留痕（分级真进模块）")
chk(res["L5 极超大球"]["lv"] == 'L5', "L5 场景判级 = L5（实际 %s）" % res["L5 极超大球"]["lv"])
chk(res["L4 超大球"]["lv"] == 'L4', "L4 场景判级 = L4（实际 %s）" % res["L4 超大球"]["lv"])
chk(res["L0 非大球"]["lv"] in ('L0', ''), "L0 场景不误判为超大球（实际 %s）" % res["L0 非大球"]["lv"])
chk(_tot(res["L5 极超大球"]["a2"]) >= 5,
    "L5 次锚 ≥5 球（span=max(主锚+2,线+1)）：%s 共%d球" % (res["L5 极超大球"]["a2"], _tot(res["L5 极超大球"]["a2"])))
chk(_tot(res["L4 超大球"]["a2"]) >= 4,
    "L4 次锚 ≥4 球：%s 共%d球" % (res["L4 超大球"]["a2"], _tot(res["L4 超大球"]["a2"])))
chk(_tot(res["L5 极超大球"]["a2"]) > _tot(res["L3 大球很强"]["a2"]),
    "L5 次锚球数 > L3（超大球与大球拉开差距）：%d vs %d"
    % (_tot(res["L5 极超大球"]["a2"]), _tot(res["L3 大球很强"]["a2"])))
_p5 = res["L5 极超大球"]["pool"]
# 🔴2026-11-03: 宽池补入现在必须过市场信号门槛（用户指令「宽池也得符合市场信号·不硬锚」）
#   → 6 球档候选全不合格时应**明确拒收**而非硬塞 → 判据改为「含 ≥6 球 或 已留痕拒收」
_n5 = " ".join(res["L5 极超大球"].get("p52") or [])
chk(any(_tot(s) >= 6 for s in _p5) or ("拒收" in _n5),
    "L5 宽池含 ≥6 球候选 或 该档明确拒收：%s｜%s"
    % ([s for s in _p5 if _tot(s) >= 6],
       [x for x in (res["L5 极超大球"].get("p52") or []) if "拒收" in x][:1]))
_p4 = res["L4 超大球"]["pool"]
_n4 = " ".join(res["L4 超大球"].get("p52") or [])
chk(any(_tot(s) >= 6 for s in _p4) or ("拒收" in _n4),
    "L4 宽池含 ≥6 球候选 或 该档明确拒收：%s｜%s"
    % ([s for s in _p4 if _tot(s) >= 6],
       [x for x in (res["L4 超大球"].get("p52") or []) if "拒收" in x][:1]))
chk(len(_p4) > 8, "L4 宽池发生补入（>8 → 补入生效）：%d 个" % len(_p4))
chk(res["L5 极超大球"]["pool"] != res["L0 非大球"]["pool"],
    "L5 与 L0 宽池不同（分级差异化成立）")

print("\n【④ 矩阵弱兜底】joint_solver 在 _r10 为空时须自动纠偏（否则 P52 全链失效）")
_js = open("data/tmp/joint_solver.py", encoding="utf-8").read()
chk("P52 矩阵弱兜底判级" in _js, "joint_solver 含 P52 矩阵弱兜底判级")
chk("P52 锚量级纠偏" in _js, "joint_solver 含主锚量级纠偏（大球强须≥3球·同方向）")
chk("if not _r10:" in _js, "兜底条件是矩阵未生效（_r10 为空）")
chk("_sg52(x[\"score\"]) == _sd1" in _js, "纠偏限同方向（净胜符号一致·禁反转 L2）")
_ca2 = open("data/tmp/calc_all.py", encoding="utf-8").read()
chk("P52 超大球分级" in _ca2, "calc_all 输出 P52 分级行（含已接入标注）")

print("\n" + "=" * 72)
if FAIL:
    print("❌ 未通过 %d 项:" % len(FAIL))
    for f in FAIL:
        print("   - " + f)
    sys.exit(1)
print("✅ P52 端到端链路审计 %d 项全部通过" % (len([1])))
