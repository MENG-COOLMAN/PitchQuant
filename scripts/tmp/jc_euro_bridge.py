# -*- coding: utf-8 -*-
"""jc_euro_bridge.py — 🔴V3.5.80 P9 竞彩→欧亚盘分层填充（数据桥）

2026-10-20 用户指令「竞彩是噪音? 用欧亚盘填充运算·模型结构不变」。
设计：竞彩 txt = **结构壳**（spf/rq/zjq/bqc/bf 各段逐T）·欧亚盘 = **内容源**（机构意图）
     → 按段分层填充。**模型结构不变·下游消费端零改动**。

铁律（贯穿）：
  ① 竞彩**不删除** —— 两个物理不可替代资产：逐T 高密度时序（V1/D1/双通道 C1）+ 中国彩民情绪池（Q1/Q2/Q4）
  ② bqc 半全场 / 逐T / 公众情绪 → **保留竞彩**（欧亚快照无 HT-FT 市场·仅 2-4 时点）
  ③ 竞彩作为概率源须过 `retail_correction`（散户偏差校正·仅 src='竞彩' 生效）
  ④ 只换解析源·不改判定结构·全部幅度【待回测校准】·禁单场固化

分段源映射：
  spf 胜平负 ← 机构共识层 merge_devig → --eu → 竞彩(校正)
  rq  让球   ← 欧亚 Spread 均衡档 → --handi → 竞彩(保留)
  zjq 总进球 ← --o25/--u25 → 竞彩(保留)
  bf  比分盘 ← 欧亚 Correct Score 全表 → 竞彩(保留·E7 权重 0.12)
  bqc 半全场 ← **恒竞彩**（不可替）
  逐T/公众  ← **恒竞彩**（不可替）
"""
import os

# ── 散户偏差校正（竞彩噪音隔离核心）──
RETAIL_TOP_PENALTY = 0.02      # 热捧方向 −2.0pp（跟风噪音·待回测校准）
RETAIL_OTHER_BONUS = 0.01      # 其余方向 +1.0pp（含平局系统性低估）


def retail_correction(prob, src, note_list=None):
    """🔴P9 竞彩散户偏差校正（Retail Emotion 通道·§2.2）

    依据: 竞彩=中国彩民跟风池（限注·非市场化·抽水 12.8%）→ 最高隐含方向含跟风噪音·
          平局系统性偏低（彩民偏好分胜负）。
    输入 prob={方向: 去水概率}·输出校正后（重归一）。欧亚源原样返回。
    """
    if src != "竞彩" or not prob:
        return prob
    p = dict(prob)
    if len(p) < 2:
        return prob
    top_k = max(p, key=lambda k: p[k])
    p[top_k] -= RETAIL_TOP_PENALTY
    for k in p:
        if k != top_k:
            p[k] += RETAIL_OTHER_BONUS
    tot = sum(p.values())
    if tot > 0:
        p = {k: v / tot for k, v in p.items()}
    if note_list is not None:
        _CN = {1: "主胜", 0: "平局", 2: "客胜", "胜": "主胜", "平": "平局", "负": "客胜"}
        note_list.append("🔴P9散户校正: 竞彩热捧「%s」−%.1fpp·其余+%.1fpp（跟风噪音隔离·待回测校准）"
                         % (_CN.get(top_k, top_k),
                            RETAIL_TOP_PENALTY * 100, RETAIL_OTHER_BONUS * 100))
    return p


def _top3_cs(cs_full):
    """波胆 Top3（比分字符串·按赔率升序=概率降序）"""
    if not cs_full:
        return []
    return [str(k).replace("-", ":") for k, _ in sorted(cs_full.items(), key=lambda x: x[1])[:3]]


def bridge_sections(txt_path, eu=None, handi=None, o25=None, u25=None,
                    books=None, snapshot=None, cs_full=None, ah_full=None):
    """🔴P9 数据桥主入口：竞彩结构壳 + 欧亚内容源 → 填充后 sections

    返回 {'sections': {段: [(ts, odds)]}, 'src_map': {段: 源标注}, 'notes': [三态]}
    🔴 sections 与 calc_match.parse_txt 同构（下游零改动）
    """
    import calc_match as _cm
    raw = ""
    try:
        raw = open(txt_path, encoding="utf-8").read()
    except Exception:
        pass
    secs = {}
    try:
        secs = _cm.parse_txt(raw) or {}
    except Exception:
        secs = {}
    out = {"sections": {}, "src_map": {}, "notes": []}
    # 🔴只复制**段结构**（list/tuple 的 [(ts, odds)]）·忽略 parse_txt 里的标量键
    #   （原实现 `list(v)` 对 float 键 → 'float' object is not iterable·实跑抓）
    for _k, _v in (secs or {}).items():
        if isinstance(_v, (list, tuple)):
            out["sections"][_k] = [tuple(x) if isinstance(x, (list, tuple)) and len(x) == 2 else x
                                   for x in _v]
        else:
            out["sections"][_k] = _v      # 标量原样保留（不迭代）

    # ── spf ──
    _f = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    if not eu:
        try:
            from snapshot_save import find_for as _ff
            if snapshot is None and txt_path:
                _teams = _cm.txt_teams([txt_path]) if hasattr(_cm, "txt_teams") else (None, None)
                if _teams and _teams[0] and _teams[1]:
                    snapshot = _ff(_teams[0], _teams[1])
        except Exception:
            pass
    if books and books.get("pH") and books.get("pD") and books.get("pA"):
        _o = {"胜": round(1 / float(books["pH"]), 3),
              "平": round(1 / float(books["pD"]), 3),
              "负": round(1 / float(books["pA"]), 3)}
        _ts = secs["spf"][-1][0] if secs.get("spf") else "机构共识层"
        out["sections"]["spf"] = [(_ts, _o)]
        out["src_map"]["spf"] = "欧亚merge_devig(多机构去水)"
        out["notes"].append("🟢P9 spf: 机构共识层填充(%s 家)" % books.get("n_books", "?"))
    elif eu:
        try:
            _e3 = [float(x) for x in str(eu).split(",")]
        except Exception:
            _e3 = []
        if len(_e3) == 3 and all(x > 1 for x in _e3):
            _ts = secs["spf"][-1][0] if secs.get("spf") else "正式执行--eu"
            _o3 = {"胜": _e3[0], "平": _e3[1], "负": _e3[2]}
            # 🔴2026-10-20 二轮深检修(P1-3): 原 `out["sections"]["spf"] = [(ts,_o3)]` = **单点整体替换**
            #   → calc_match 的 D1背离 / 低赔变动重排 / 逐T形态 全部「时点不足(<3)」三态（实跑复现）。
            #   → 改「**末点覆盖·保留逐T历史**」: 时点数不变·末点=欧亚正式执行价（D1 首末变动更真实）。
            _hist = list(secs.get("spf") or [])
            if _hist:
                _hist[-1] = (_ts, _o3)
                out["sections"]["spf"] = _hist
                out["src_map"]["spf"] = "欧亚--eu(末点覆盖·逐T历史保留 %d 时点)" % len(_hist)
                out["notes"].append("🟢P9 spf: --eu 覆盖末时点（保留竞彩逐T %d 时点·D1/形态学可算）"
                                    % len(_hist))
            else:
                out["sections"]["spf"] = [(_ts, _o3)]
                out["src_map"]["spf"] = "欧亚--eu(无竞彩逐T·单点)"
                out["notes"].append("🟢P9 spf: --eu 填充(原 txt 无 spf 段)")
    else:
        # 快照 ML 兜底
        _ml = None
        try:
            # 🔴2026-10-20 修(P1 口径·同源): 原取 first(最早时点) → 改 last(最接近赛前)·缺则回退 first
            if snapshot and (snapshot.get("last") or snapshot.get("first")):
                _pt = snapshot.get("last") or snapshot.get("first") or {}
                _ml = (_pt.get("extract") or {}).get("ml")
        except Exception:
            _ml = None
        if _ml and len(_ml) == 3:
            _ts = secs["spf"][-1][0] if secs.get("spf") else "快照ML"
            out["sections"]["spf"] = [(_ts, {"胜": _ml[0], "平": _ml[1], "负": _ml[2]})]
            out["src_map"]["spf"] = "欧亚快照ML"
            out["notes"].append("🟢P9 spf: 快照 ML 填充(首时点)")
        else:
            out["src_map"]["spf"] = "竞彩(保留·需散户校正)"
            out["notes"].append("⚪P9 spf: 无欧亚源 → 竞彩保留(散户校正·抽水约 12.8%)")

    # ── rq ──
    if ah_full:
        _hint = ah_net_hint(ah_full)
        _a0 = _pick_balanced_ah(ah_full)      # 🔴均衡线（|主−客|≤0.25）·禁深档冒充
        if not _a0:
            out["src_map"]["rq"] = "竞彩(保留·欧亚均衡线缺失)"
            out["notes"].append("⚪P9 rq: 欧亚 Spread %d 档中无均衡档(|主−客|>0.25) → **不采用**·竞彩保留"
                                % len(ah_full))
            ah_full_rq = None
        else:
            ah_full_rq = ah_full
        _wh, _wa = (_a0[1], _a0[2]) if _a0 else (0, 0)
        if _wh > 1 and _wa > 1:
            # 🔴2026-10-20 二轮深检修(P1-2): 原写入 `{"胜":.., "平":None, "负":..}` →
            #   任何 dejuice 直接 `TypeError: /: 'int' and 'NoneType'`（实跑复现）。
            #   🔴Spread 本就没有平赔 → **整段不写入 sections['rq']**（保留竞彩原文·零脏数据），
            #   欧亚让球口径由 src_map/notes + calc_all 的 --handi / 净胜档 独立承载。
            out["src_map"]["rq"] = ("欧亚快照Spread(均衡档 hdp=%+.2f·净胜%s·**仅方向/净胜用·不覆盖rq段**)"
                                    % (_a0[0], (_hint or {}).get("net_hint")))
            out["notes"].append("🟢P9 rq: 欧亚让球均衡档(hdp=%+.2f·主水%.2f/客水%.2f) 用于方向/净胜档判定·"
                                "**不写入 rq 段**（Spread 无平赔·防 None 污染下游）"
                                % (_a0[0], _wh, _wa))
    elif handi is not None:
        out["src_map"]["rq"] = "欧亚--handi(下游方向判定使用·竞彩rq仅参考)"
        out["notes"].append("🟢P9 rq: --handi %s 填充" % handi)
    else:
        out["src_map"]["rq"] = "竞彩(保留)"
        out["notes"].append("⚪P9 rq: 无欧亚让球源 → 竞彩保留(口径可能与真实盘偏离)")

    # ── zjq ──
    if o25 and u25:
        try:
            _o, _u = float(o25), float(u25)
            _po = (1 / _o) / (1 / _o + 1 / _u)
            _ts = secs["zjq"][-1][0] if secs.get("zjq") else "正式执行--o25/--u25"
            out["sections"]["zjq"] = [(_ts, {"o25": _o, "u25": _u, "p_over": round(_po, 4)})]
            out["src_map"]["zjq"] = "欧亚--o25/--u25"
            out["notes"].append("🟢P9 zjq: 欧亚大小球填充(O2.5 去水 %.1f%%)" % (_po * 100))
        except Exception:
            out["src_map"]["zjq"] = "竞彩(保留)"
    elif o25:
        out["src_map"]["zjq"] = "欧亚--o25(单侧)"
        out["notes"].append("🟡P9 zjq: 仅 --o25 单侧(未传 --u25)·大小球约束为单侧")
    else:
        out["src_map"]["zjq"] = "竞彩(保留)"
        out["notes"].append("⚪P9 zjq: 无欧亚大小球源 → 竞彩 zjq 保留(常缺段)")

    # ── bf ──
    if cs_full:
        _ts = secs["bf"][-1][0] if secs.get("bf") else "快照Correct Score"
        # 🔴2026-10-20 二轮深检修(P0-1): 原直接透传 `_cs_full` 的连字符键（'0-1'），
        #   而 calc_match 消费端用 `k.count(':')==1` / `k in ('0:0','1:1','2:2')` 判据
        #   → 22 档全被过滤 → **BTTS 0.0% / CS 侧 0.0%**（实跑铁证）。
        #   → bridge 出口统一归一为 ':'（calc_match 口径）·calc_match 端亦加兼容（双保险）
        _bf_norm = {str(k).replace("-", ":").replace("/", ":"): v
                    for k, v in dict(cs_full).items()}
        out["sections"]["bf"] = [(_ts, _bf_norm)]
        out["src_map"]["bf"] = "欧亚快照Correct Score(%d档·键归一':')" % len(_bf_norm)
        out["notes"].append("🟢P9 bf: 欧亚波胆全表填充(%d档·占位100已剔除·Top3=%s)"
                            % (len(cs_full), "/".join(_top3_cs(cs_full))))
    else:
        out["src_map"]["bf"] = "竞彩(保留)"
        out["notes"].append("⚪P9 bf: 无欧亚波胆源 → 竞彩 bf 保留(E7 权重 0.12·低噪音权重)")

    # ── bqc / 逐T / 公众情绪：物理不可替·保留竞彩 ──
    out["src_map"]["bqc"] = "竞彩(保留·欧亚快照无 HT/FT 市场)"
    out["notes"].append("🔴P9 bqc: 欧亚快照未拉 HT/FT 市场 → **必须保留竞彩**(E9/P7 依赖·不可替)")
    out["src_map"]["逐T"] = "竞彩(保留·V1/D1/双通道C1 依赖·物理不可替)"
    out["notes"].append("🔴P9 逐T/公众情绪: 竞彩保留(欧亚快照仅 2-4 时点·无中国彩民池)")
    return out


def _pick_balanced_ah(rows):
    """🔴均衡线档：|主水−客水| ≤ 0.25（取最接近 0 的盘口）；无 → None（三态·禁深档冒充）"""
    if not rows:
        return None
    bal = [r for r in rows if r[1] > 1 and r[2] > 1 and abs(r[1] - r[2]) <= 0.25]
    if not bal:
        return None
    return min(bal, key=lambda r: abs(r[0]))


def ah_net_hint(ah_full, handi=None):
    """🔴P9: 欧亚让球全档 → 净胜档提示（均衡线优先·无均衡档 → None·禁深档冒充）"""
    if not ah_full:
        return None
    a = _pick_balanced_ah(ah_full)
    if not a:
        return None
    h = a[0]
    if h < -1.75:
        net = "H3+"
    elif h < -1.0:
        net = "H2"
    elif h < -0.35:
        net = "H1"
    elif h <= 0.35:
        net = "D0"
    elif h <= 1.0:
        net = "A1"
    elif h <= 1.75:
        net = "A2"
    else:
        net = "A3+"
    return {"hdp": h, "net_hint": net,
            "note": "欧亚让球均衡档 hdp=%+.2f → 净胜档 %s（P9 数据桥）" % (h, net)}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("retail_correction 自检:")
    _p = {"主": 0.50, "平": 0.27, "客": 0.23}
    print("  竞彩 →", {k: round(v, 4) for k, v in retail_correction(_p, "竞彩").items()})
    print("  欧亚 →", retail_correction(_p, "欧亚"))
