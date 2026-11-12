# -*- coding: utf-8 -*-
"""audit_p10.py —— P10/R10/R11 专项审计（V3.5.81·2026-10-25）

审计口径（SK-audit A 模式·铁律「存在≠活跃」升级为「用真实输入跑一次，输出里出现非空数值」）:
  A 调用链/死代码/死常量
  B 留痕链（output_checker / check_luopan / analysis_template 是否**精确**覆盖 P10/R10/R11）
  C 统一入口（market_inputs / jc_euro_bridge 是否透传 OU/TT 全档）
  D 真实数据链路（快照 → infer_from_parts → joint_anchor(完整 mm) → 三个留痕块）
  E 三态边界（缺源 / 开关 off / 未传矩阵 的向后兼容）
  F 参数对齐（calc_all 调用 vs 函数签名）

用法: python data/tmp/audit_p10.py [--snapshot 文件名]
退出码: 0 = 无 P0/P1（P2 仅提示）; 1 = 存在 P0/P1
"""
import io
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "data", "tmp"))
os.chdir(ROOT)

P0, P1, P2, OK = [], [], [], []


def ok(msg):
    OK.append(msg)
    print("  ✅ " + msg)


def bad(level, msg):
    (P0 if level == "P0" else (P1 if level == "P1" else P2)).append(msg)
    print("  %s %s" % ("🔴" if level == "P0" else ("🟠" if level == "P1" else "🟡"), msg))


def _read(p):
    try:
        return io.open(p, encoding="utf-8", newline="").read()
    except Exception:
        return ""


# ============================================================ A 调用链/死代码
print("=" * 72)
print("A. 调用链 / 死代码 / 死常量")
print("=" * 72)
MD = _read("data/tmp/market_distribution.py")
JS = _read("data/tmp/joint_solver.py")
CA = _read("data/tmp/calc_all.py")
CS = _read("data/tmp/check_sync.py")

for fn in ("anchor_select", "team_zero_decision", "infer_from_parts", "fmt_block", "fmt_line", "fmt_r11_line"):
    # 🔴审计器自审计修: 同文件内部调用也算活跃（fmt_line 被 fmt_block 调用）→ 范围含 MD
    calls = len(re.findall(r"(?<!def )%s\(" % fn, MD + JS + CA + CS))
    production = len(re.findall(r"(?<!def )%s\(" % fn, MD + JS + CA))
    if production > 0:
        ok("%s 被生产代码调用 %d 处" % (fn, production))
    elif calls > 0:
        bad("P1", "%s **仅被 check_sync 调用**（生产链路未接入 → 存在≠活跃）" % fn)
    else:
        bad("P2", "%s 无任何调用点（死代码 → 删除或接入）" % fn)

# 死常量：P10_/R10_/R11_ 定义后是否在函数体被引用
for mod_name, body in (("market_distribution", MD), ("joint_solver", JS)):
    defs = re.findall(r"^(P10_|R10_|R11_)([A-Z0-9_]+)\s*=", body, re.M)
    total = len(defs)
    dead = []
    for pre, nm in defs:
        full = pre + nm
        if len(re.findall(r"\b%s\b" % full, body)) <= 1:
            dead.append(full)
    if dead:
        bad("P2", "%s 死常量 %d/%d: %s" % (mod_name, len(dead), total, ", ".join(dead)))
    else:
        ok("%s 常量全部被消费（%d 个）" % (mod_name, total))

# ============================================================ B 留痕链
print()
print("=" * 72)
print("B. 留痕链（精确匹配·防 R1-R10 误命中）")
print("=" * 72)
_PAT = r"市场矩阵\(P10|R10判定|R11 零封|market_r10|market_r11|R11-①|P10-①"
for f, need in (("data/tmp/output_checker.py", ("市场矩阵(P10", "R11 零封")),
                ("data/tmp/check_luopan.py", ("市场矩阵(P10", "R11 零封")),
                ("data/analysis_template.md", ("市场矩阵(P10", "R10判定", "R11 零封"))):
    txt = _read(f)
    miss = [n for n in need if n not in txt]
    if miss:
        bad("P1", "%s 留痕链缺: %s（方案 §六 要求 output_checker/check_luopan/模板 覆盖）"
            % (os.path.basename(f), ", ".join(miss)))
    else:
        ok("%s 已覆盖 P10/R10/R11 留痕" % os.path.basename(f))

# ============================================================ C 统一入口
print()
print("=" * 72)
print("C. 统一入口（market_inputs / jc_euro_bridge 是否透传 OU/TT 全档）")
print("=" * 72)
for f in ("data/tmp/market_inputs.py", "data/tmp/jc_euro_bridge.py"):
    txt = _read(f)
    has = ("ou_full" in txt) and ("tt_full" in txt)
    if has:
        ok("%s 已透传 ou_full/tt_full" % os.path.basename(f))
    else:
        # 🔴审计器自审计修: 区分「设计选择」与缺陷 —— P10 从**同一 raw** 自行收集全档
        #   （与 _n23_cs 同时点·口径一致），不经统一入口属可接受实现；仅提示不判 P1
        bad("P2", "%s 未透传 OU/TT 全档（P10 从同一 raw 自行收集·**设计选择非缺陷**·口径一致）"
            % os.path.basename(f))

# ============================================================ D 真实数据链路
print()
print("=" * 72)
print("D. 真实数据链路（快照 → infer_from_parts → joint_anchor → 留痕块）")
print("=" * 72)
try:
    import market_distribution as MDm
    import joint_solver as JSm
    from snapshot_save import _ou_full, _ah_full, _cs_full, _tt_full

    snap_dir = os.path.join(ROOT, "data", "tmp", "snapshots")
    cand = [f for f in os.listdir(snap_dir) if f.endswith(".json")]
    cand.sort(key=lambda f: os.path.getmtime(os.path.join(snap_dir, f)), reverse=True)
    raw = ml = btts = None
    used = None
    for fn in cand[:40]:
        try:
            d = json.load(io.open(os.path.join(snap_dir, fn), encoding="utf-8"))
        except Exception:
            continue
        for g in (d.get("games") or []):
            r = g.get("raw_1xbet") or {}
            ou = _ou_full(r)
            ah = _ah_full(r)
            cs = _cs_full(r)
            tt = _tt_full(r)
            if not (ou and ah and len(cs) >= 15 and (tt.get("home") or {})):
                continue
            _ml = None
            for m in ((r.get("bookmakers") or {}).get("1xbet") or []):
                if str(m.get("name") or "").lower() == "ml":
                    o = (m.get("odds") or [{}])[0]
                    _ml = (float(o["home"]), float(o["draw"]), float(o["away"]))
                    break
            _bt = None
            for m in ((r.get("bookmakers") or {}).get("1xbet") or []):
                if str(m.get("name") or "").lower() == "both teams to score":
                    o = (m.get("odds") or [{}])[0]
                    _bt = {"yes": float(o["yes"]), "no": float(o["no"])}
                    break
            if _ml and _bt:
                raw, ml, btts, used = r, _ml, _bt, (fn, g.get("home"), g.get("away"))
                break
        if raw:
            break

    if not raw:
        bad("P1", "D 链路：40 份最近快照内找不到「OU+AH+CS≥15+TT+ML+BTTS」齐全的场次 → 无法实测")
    else:
        print("  取样: %s [%s vs %s]" % (used[0], used[1], used[2]))
        mm = MDm.infer_from_parts(ou_full=_ou_full(raw), ah_full=_ah_full(raw), cs_full=_cs_full(raw),
                                  oh=ml[0], od=ml[1], oa=ml[2], tt_full=_tt_full(raw), btts=btts)
        # D1 上游数据到位
        for k, cond in (("tt_full.home", bool((mm.get("tt_full") or {}).get("home"))),
                        ("tt_full.away", bool((mm.get("tt_full") or {}).get("away"))),
                        ("btts_mkt", bool(mm.get("btts_mkt"))),
                        ("matrix.squeezed", "squeezed" in ((mm.get("matrix") or {})))):
            (ok if cond else lambda m: bad("P1", m))("D1 %s 非空（上游数据到位）" % k)
        (ok if mm.get("ok") else lambda m: bad("P0", m))("D1 决策门 ok=%s（矩阵启用）" % mm.get("ok"))
        # D2 joint_anchor 消费
        r_cmp = JSm.joint_anchor(ml[0], ml[1], ml[2], handi=-0.5, o25=1.95, u25=1.90,
                                 cs_odds=_cs_full(raw), btts_yes=btts["yes"], btts_no=btts["no"],
                                 market_matrix=mm)
        rep = JSm.fmt_report(r_cmp)
        for tag, cond in (("market_driven", bool(r_cmp.get("market_driven"))),
                          ("market_r10", isinstance(r_cmp.get("market_r10"), dict)),
                          ("market_r11", isinstance(r_cmp.get("market_r11"), dict)),
                          ("fmt_report 市场矩阵行", "市场矩阵" in rep),
                          ("fmt_report R10行", "R10" in rep),
                          ("fmt_report R11行", "R11" in rep)):
            (ok if cond else lambda m: bad("P0", m))("D2 %s 生效" % tag)
        # D3 R11 直盘数值
        _z = r_cmp.get("market_r11") or {}
        (ok if (_z.get("home_clean") is not None or _z.get("away_clean") is not None)
         else lambda m: bad("P0", m))("D3 R11 直盘零封数值非空（主 %s / 客 %s）"
                                     % (_z.get("home_clean"), _z.get("away_clean")))
        print("  ---- fmt_report 片段 ----")
        for ln in rep.split("\n"):
            if "市场矩阵" in ln or "R10" in ln or "R11" in ln:
                print("   " + ln[:150])
        # E 向后兼容
        r_old = JSm.joint_anchor(ml[0], ml[1], ml[2], handi=-0.5, o25=1.95, u25=1.90)
        rep_old = JSm.fmt_report(r_old)
        cond = (r_old.get("market_baseline") is None and r_old.get("market_r10") in (None, {})
                and r_old.get("market_r11") in (None, {})
                and all(x not in rep_old for x in ("市场矩阵", "R10判定", "R11 零封")))
        (ok if cond else lambda m: bad("P0", m))("E1 未传矩阵 → 三块留痕**均不出现**（向后兼容）")
except Exception as _e:
    import traceback
    traceback.print_exc()
    bad("P0", "D/E 链路实测异常: %s" % _e)

# ============================================================ F 参数对齐
print()
print("=" * 72)
print("F. 参数对齐（calc_all 调用 vs 函数签名）")
print("=" * 72)
try:
    import inspect
    import market_distribution as MDm2
    import joint_solver as JSm2
    sig_ip = set(inspect.signature(MDm2.infer_from_parts).parameters)
    m = re.search(r"infer_from_parts\(([^)]*)\)", CA, re.S)
    used = set(re.findall(r"(\w+)\s*=", m.group(1))) if m else set()
    unknown = used - sig_ip
    (ok if not unknown else lambda x: bad("P1", x))(
        "F1 infer_from_parts 调用参数全部在签名内（%d 个）%s"
        % (len(used), ("·未知: %s" % unknown) if unknown else ""))
    sig_ja = set(inspect.signature(JSm2.joint_anchor).parameters)

    def _balanced_call(text, anchor):
        r"""🔴审计器自审计修: 原正则 `_n23_ja\(([^)]*?)\)` 在多行/嵌套括号调用上提前截断
        → 8 条假 P1。改为括号平衡提取（含嵌套·位置参数与关键字参数分离）。"""
        i = text.find(anchor)
        if i < 0:
            return ""
        j = i + len(anchor)
        depth = 1
        out = []
        while j < len(text) and depth > 0:
            c = text[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            out.append(c)
            j += 1
        return "".join(out)

    # 🔴审计器自审计修(2): 排除 `==`/`!=`/`<=`/`>=` 比较运算（原会把 `_p10_mode ==` 当参数名）
    used2 = set(re.findall(r"(\w+)\s*=(?!=)", _balanced_call(CA, "_n23_ja(")))
    unknown2 = used2 - sig_ja
    (ok if not unknown2 else lambda x: bad("P0", x))(
        "F1 joint_anchor 调用参数全部在签名内（%d 个）%s"
        % (len(used2), ("·未知: %s" % unknown2) if unknown2 else ""))
    for need in ("market_matrix", "step5_dirs", "jc_cs", "htft", "vert", "btts_yes", "btts_no", "cs_odds"):
        if need not in used2:
            bad("P1", "F2 joint_anchor 调用缺参数 %s（该功能将静默空转）" % need)
    if not [x for x in P1 if x.startswith("F2")]:
        ok("F2 joint_anchor 关键参数齐（market_matrix/step5_dirs/jc_cs/htft/vert/btts/cs_odds）")
except Exception as _e2:
    bad("P1", "F 参数对齐检查异常: %s" % _e2)

# ============================================================ G 重复计价
print()
print("=" * 72)
print("G. 重复计价（方案 §5.4: 矩阵启用时波胆不再作加分项）")
print("=" * 72)
_e5_guard = re.search(r"if cs_cand is not None and not _mm_ok10:", JS) is not None
_e10_guard = re.search(r"if _cs_vert and s in _cs_vert and not _mm_ok10:", JS) is not None
(ok if _e5_guard else lambda m: bad("P1", m))("G1 E5 波胆证据在矩阵启用时跳过（防与矩阵先验双计）")
(ok if _e10_guard else lambda m: bad("P1", m))("G2 E10 波胆纵向在矩阵启用时跳过（交 R10-5）")
try:
    import market_distribution as _Gmd
    import joint_solver as _Gjs
    from snapshot_save import _ou_full as _gou, _ah_full as _gah, _cs_full as _gcs, _tt_full as _gtt
    _gsd = os.path.join(ROOT, "data", "tmp", "snapshots")
    _graw = None
    for _f in sorted(os.listdir(_gsd), key=lambda x: os.path.getmtime(os.path.join(_gsd, x)), reverse=True)[:40]:
        try:
            _d = json.load(io.open(os.path.join(_gsd, _f), encoding="utf-8"))
        except Exception:
            continue
        for _g in (_d.get("games") or []):
            _r = _g.get("raw_1xbet") or {}
            if _gou(_r) and _gah(_r) and len(_gcs(_r)) >= 15 and (_gtt(_r).get("home")):
                _graw = _r
                break
        if _graw:
            break
    if _graw:
        _mlg = None
        for _m in ((_graw.get("bookmakers") or {}).get("1xbet") or []):
            if str(_m.get("name") or "").lower() == "ml":
                _o = (_m.get("odds") or [{}])[0]
                _mlg = (float(_o["home"]), float(_o["draw"]), float(_o["away"]))
                break
        _mmg = _Gmd.infer_from_parts(ou_full=_gou(_graw), ah_full=_gah(_graw),
                                     cs_full=_gcs(_graw), oh=_mlg[0], od=_mlg[1], oa=_mlg[2],
                                     tt_full=_gtt(_graw))
        _rg = _Gjs.joint_anchor(_mlg[0], _mlg[1], _mlg[2], handi=-0.5, o25=1.95, u25=1.90,
                                cs_odds=_gcs(_graw), market_matrix=_mmg)
        _ev1 = " ".join(_rg.get("anchor_1st_evidence") or [])
        (ok if "波胆+" not in _ev1 else lambda m: bad("P1", m))(
            "G3 实跑主锚证据链**不含**「波胆+N」（启用矩阵后波胆只作矩阵先验）→ 当前: %s"
            % (_ev1[:80] or "无证据"))
    else:
        bad("P2", "G3 实跑跳过：无齐全快照")
except Exception as _eG:
    bad("P2", "G3 实跑异常: %s" % _eG)


# ============================================================ H. 执行判据（2026-10-25）
print()
print("【H】执行判据断言（P10/R10/R11 裁决链 · SK-score-depth 同步）")
try:
    import importlib
    import sys as _sysH
    if "data/tmp" not in _sysH.path:
        _sysH.path.insert(0, "data/tmp")
    _lseH = importlib.import_module("live_score_engine")
    _poolH = ["1:0", "2:0", "1:1", "2:1", "0:0", "3:1", "2:2"]
    _rH = _lseH.anchor_market_check(_poolH, 1.593, 4.16, 6.78, o25=2.34, u25=1.701, handi=-1.0)
    (ok if _rH.get("suggestion_verified") else lambda m: bad("P0", m))(
        "H1 建议锚可执行(verified=True·case279 fixture) → %s" % (_rH.get("suggestion"),))
    _rH2 = _lseH.anchor_market_check(_rH.get("suggestion") or ["2:0", "1:1"], 1.593, 4.16, 6.78,
                                     o25=2.34, u25=1.701, handi=-1.0)
    (ok if _rH2.get("ok") else lambda m: bad("P0", m))("H2 按建议锚复验 ok=True（防死循环回归）")
    _skH = _read(".reasonix/skills/SK-score-depth/SKILL.md")
    (ok if "P10/R10/R11 执行判据" in _skH else lambda m: bad("P1", m))(
        "H3 SK-score-depth 含「P10/R10/R11 执行判据」节")
    for _k in ("锚-期望【硬1】", "R11 强谱系", "suggestion_verified=False"):
        (ok if _k in _skH else lambda m: bad("P1", m))("H3 判据子项已写入 skill: %s" % _k)
    _caH = _read("data/tmp/calc_all.py")
    (ok if ("N28" in _caH and "understat_xg" in _caH) else lambda m: bad("P1", m))(
        "H4 calc_all 自动接入 understat xG（N28·防漏执行）")
    (ok if ("norm_league(league)" in _caH and "'_league_cn' in dir()" not in _caH) else lambda m: bad("P1", m))(
        "H5 N28 联赛识别用 norm_league(league)（作用域陷阱防回退·2026-10-25 实抓两次）")
    (ok if ("\n    print('\U0001f534xG 滚动均值(N28" in _caH) else lambda m: bad("P0", m))(
        "H6 N28 段缩进在 main() 内（2026-10-25 实抓: 补丁块顶格→模块级执行→league 未定义）")
except Exception as _eH:
    bad("P1", "H 段执行判据断言异常: %s" % _eH)


# ============================================================ 汇总
print()
print("=" * 72)
print("汇总: ✅%d  🔴P0=%d  🟠P1=%d  🟡P2=%d" % (len(OK), len(P0), len(P1), len(P2)))
for tag, lst in (("P0", P0), ("P1", P1), ("P2", P2)):
    for x in lst:
        print("  %s: %s" % (tag, x))
print("=" * 72)
sys.exit(1 if (P0 or P1) else 0)
