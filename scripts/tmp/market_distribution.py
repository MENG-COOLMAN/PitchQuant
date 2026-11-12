# -*- coding: utf-8 -*-
"""市场三源比分分布矩阵（P10·V3.5.81）—— 纯市场驱动 · 全档盘口反推 · 非泊松

================================================================================
用户逻辑链（严格对应·全程不用泊松决定比分形状）
  源1 大小球【半档全档】(O0.5/O1.5/.../O5.5) 去水 → 生存函数 → 相邻差分
      + 竞彩总进球 8 档（0/1/2/3/4/5/6/7+ 直接给分布）
      ⇒ P(T=k)  总进球边缘（进几个球）
  源2 让球【全档】(hdp 0.25 步进·正确处理 quarter 拆盘 / 整数 push) + 1x2 去水三向
      ⇒ NNLS 解公平结算线性方程组 → P(M=m)  净胜边缘（赢/输几个）
  源3 主队/客队 Team Total【全档】半档差分
      ⇒ P(H=k) 行边缘 / P(A=k) 列边缘（只进先验·不硬迭代·见 §4.5 注释）
  源4 波胆 CS 全表去水 ⇒ 联合先验形状（携带 H 与 A 的相关性·泊松独立性给不了）
  融合 IPF（沿 h+a 总进球对角线 / h-a 净胜对角线迭代缩放）
      ⇒ P(H,A)：每个比分天然同时满足总进球边缘与净胜边缘
        → 机制上根除「比分锚定 vs 期望总进球 vs 让球净胜」三者打架

================================================================================
定位与铁律
  · 纯函数·无副作用·只读传入的全档数据；不 import / 不修改 joint_solver、snapshot_save
  · 三源齐全（决策门·方案 §5.5）→ ok=True → joint_solver 以市场矩阵为主排序基线（E0）
  · 任一源不足 → ok=False → 调用方回退现有 P5/泊松链路，**三态标注原因·禁臆造**
  · CS 只取形状：CS 去水期望系统性偏高 +0.23~0.34 球（V3.5.80 实测）→ 绝不用 CS 定期望
  · 深档假档过滤：NNLS 权重对「非均衡 / 高抽水」档降权（case229/234 教训）
  · 全部阈值【待回测校准】（Matches.csv 无全档多档字段 → 无法时间分割回测·仅实盘累积）

用法
  from market_distribution import infer_from_parts, fmt_line
  mm = infer_from_parts(ou_full=..., ah_full=..., cs_full=..., tt_full=...,
                        oh=3.49, od=3.735, oa=2.167, jc_goal8=[...])
  mm['ok'] / mm['matrix']['top'] / fmt_line(mm)

  从 raw 快照（独立调试）：
  from market_distribution import infer_market_matrix
  mm = infer_market_matrix(raw_1xbet, jc_goal8=None)
"""

import math
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ============================================================================
# 0. 阈值常量（🔴全部【待回测校准】·方案 §八.8 方法论铁律）
# ============================================================================

P10_KL_TOL = 0.15          # OU 差分 vs 竞彩8档 KL 自洽门（>0.15 → 欧亚盘为准·竞彩仅标注）
P10_OU_JC_W = (0.7, 0.3)   # 自洽时融合权重（竞彩仅降噪·与 P9 竞彩噪音隔离认知一致）
P10_EDGE_TOL = 0.08        # 净胜分布边缘 vs 1x2 容忍（>0.08 标「可能含假档/低分辨率」）
P10_CS_MIN = 15            # 决策门：CS 有效档 ≥15（决定相关性形状是否可信）
P10_OU_MIN = 3             # 决策门：OU 半档线 ≥3（建议 ≥4）
P10_AH_MIN = 4             # 决策门：AH 有效档 ≥4
P10_1X2_W = 4.0            # NNLS 中 1x2 三向硬约束权重
P10_IPF_ITERS = 3000       # IPF 迭代轮数（原型实测 2000 轮即稳）
P10_SOFT = 0.0             # 软边缘系数（0=硬约束；边缘不相容时调用方可用 0.6~0.8 折中）
P10_N = 7                  # 矩阵维度（0..6 球/队）·8+ 球不入矩阵（截断·见 notes）
P10_SQUEEZE_RATIO = 5.0    # 尾桶挤压判据: 矩阵概率 > 5× 波胆去水概率 → 判「边缘伪影」
                           #   （case278 实抓 3:4 矩阵 8.2% vs 波胆 ~1.5% = 5.5× → 挤压）
                           #   🔴待回测校准


# ============================================================================
# 1. 基础去水
# ============================================================================

def _devig_2way(o_over, o_under):
    """二向比例去水 → (p_over, p_under)；缺值返回 (None, None)"""
    if not o_over or not o_under or o_over <= 1 or o_under <= 1:
        return None, None
    io, iu = 1.0 / float(o_over), 1.0 / float(o_under)
    s = io + iu
    if s <= 0:
        return None, None
    return io / s, iu / s


def _devig_3way(oh, od, oa):
    """1x2 三向比例去水 → (pH, pD, pA)"""
    if not (oh and od and oa) or min(oh, od, oa) <= 1:
        return None, None, None
    ih, id_, ia = 1.0 / float(oh), 1.0 / float(od), 1.0 / float(oa)
    s = ih + id_ + ia
    return ih / s, id_ / s, ia / s


def _is_half(line):
    """是否半档线（x.5）—— 用 2*line 判奇偶（禁 round()：Python 银行家舍入 round(1.5)=2 会漏档）"""
    try:
        q = 2.0 * float(line)
    except (TypeError, ValueError):
        return False
    if abs(q - round(q)) > 1e-9:
        return False
    return int(round(q)) % 2 == 1


# ============================================================================
# 2. 源1：大小球半档差分 → 总进球分布 P(T=k)
# ============================================================================

def total_goals_distribution(ou_full, jc_goal8=None, max_k=7):
    """OU 半档去水 = 生存函数 S(k)=P(T≥k) → 相邻差分 PMF（恒等变换·不依赖进球过程假设）

    P(T=0)=1−S(1) ｜ P(T=k)=S(k)−S(k+1) ｜ 尾桶 P(T≥K)=S(K) 并入 min(K,max_k) 桶

    返回 {p[0..max_k], exp, ou_lines_used, jc_p, kl, origin, health, notes}
    """
    notes = []
    ou_full = ou_full or {}
    half_lines = sorted([ln for ln in ou_full.keys() if _is_half(ln) and float(ln) >= 0])
    surv = {}
    for ln in half_lines:
        try:
            over, under = ou_full[ln]
        except (TypeError, ValueError):
            continue
        p_over, _pu = _devig_2way(over, under)
        if p_over is None:
            continue
        k_total = int(math.floor(float(ln))) + 1        # 0.5→1, 1.5→2, ...
        surv[k_total] = p_over

    p = None
    if len(surv) >= 2:
        ks = sorted(surv.keys())
        pmf = {0: max(0.0, 1.0 - surv[ks[0]])}
        for i, k in enumerate(ks):
            if i == 0:
                continue
            pmf[k - 1] = max(0.0, surv[ks[i - 1]] - surv[k])
        # 尾桶：P(T≥ks[-1]) → 并入 min(ks[-1], max_k) 桶（语义「该档及以上」·见 notes）
        pmf[ks[-1]] = max(0.0, surv[ks[-1]])
        p = [0.0] * (max_k + 1)
        for kk, v in pmf.items():
            p[min(int(kk), max_k)] += v
        tot = sum(p)
        if tot > 0:
            p = [x / tot for x in p]
        if ks[-1] < max_k + 1:
            notes.append("尾桶=P(T≥%d 球) 并入第 %d 桶（O%d.5 以上无更细线）"
                         % (ks[-1], min(ks[-1], max_k), ks[-1] - 1))

    # 竞彩总进球 8 档（第二源·仅降噪/校验）
    jc_p = None
    if jc_goal8 and len(jc_goal8) == 8 and all(x and float(x) > 1 for x in jc_goal8):
        inv = [1.0 / float(x) for x in jc_goal8]
        s = sum(inv)
        if s > 0:
            _p = [x / s for x in inv]
            jc_p = _p[:max_k] + [sum(_p[max_k:])]        # 7+ 档并入最高桶
            _sj = sum(jc_p) or 1.0
            jc_p = [x / _sj for x in jc_p]

    kl = None
    if p is not None and jc_p is not None:
        kl = round(sum(ai * math.log((ai + 1e-9) / (bi + 1e-9))
                       for ai, bi in zip(p, jc_p)), 4)
        if kl > P10_KL_TOL:
            notes.append("⚠️OU差分 vs 竞彩8档 KL=%.3f 分歧 → 以欧亚盘为准·竞彩仅标注"
                         "（竞彩噪音隔离 P9）" % kl)
        else:
            _w = P10_OU_JC_W
            p = [_w[0] * a + _w[1] * b for a, b in zip(p, jc_p)]
            notes.append("✅OU差分 vs 竞彩8档 KL=%.3f 自洽 → 双源加权(%.1f/%.1f)"
                         % (kl, _w[0], _w[1]))

    if p is not None:
        origin = "OU半档差分(%d线)" % len(surv) + ("+竞彩8档" if jc_p is not None else "")
        health = "ok" if len(surv) >= 4 else "weak"
        if len(surv) < 4:
            notes.append("⚠️仅 %d 条半档线 → 总进球分布分辨率弱" % len(surv))
    elif jc_p is not None:
        p, origin, health = jc_p, "竞彩8档(无OU全档)", "weak"
        notes.append("⚠️无 OU 半档全档 → 仅用竞彩8档（单源）")
    else:
        return {"p": None, "exp": None, "ou_lines_used": len(surv), "jc_p": None, "kl": None,
                "origin": "无源", "health": "none",
                "notes": ["⚪OU 全档 / 竞彩8档均缺失 → 三态回退 λ+泊松"]}

    exp = sum(i * p[i] for i in range(len(p)))
    return {"p": [round(x, 4) for x in p], "exp": round(exp, 3),
            "ou_lines_used": len(surv),
            "jc_p": ([round(x, 4) for x in jc_p] if jc_p else None),
            "kl": kl, "origin": origin, "health": health, "notes": notes}


# ============================================================================
# 3. 源2：让球全档 + 1x2 → 净胜球分布 P(M=m)（NNLS）
# ============================================================================

def _settle_frac(m, line):
    """主队让球 line（负=主让）在真实净胜 m=H−A 下的 (win_frac, push_frac)

    半档 x.5：二元全赢/全输 ｜ 整数 x：赢/走水(push)/输 ｜ quarter x.25/x.75：拆相邻两盘各半注
    """
    def _one(x):
        z = m + x
        if z > 0:
            return 1.0, 0.0
        if z == 0:
            return 0.0, 1.0
        return 0.0, 0.0

    q = float(line) * 4.0
    if abs(q - round(q)) < 1e-9 and int(round(q)) % 2 == 1:      # quarter 盘
        w1, p1 = _one(float(line) - 0.25)
        w2, p2 = _one(float(line) + 0.25)
        return 0.5 * (w1 + w2), 0.5 * (p1 + p2)
    return _one(float(line))


def goal_margin_distribution(ah_full, ph, pd, pa, max_m=4):
    """让球全档 → 每条线一个公平结算线性方程 → NNLS 解 P(净胜=m)

    Σ_m p_m ·( wℓ·win_frac(m,ℓ) + push_frac(m,ℓ) ) = 1
    + 1x2 三向硬约束（权重 P10_1X2_W）+ 非负；权重按「均衡度」分档（深档假档降权）
    返回 {p:{m:p}, p_list, ms, exp, lines, edge_err, health, notes}
    """
    ms = list(range(-max_m, max_m + 1))
    ah_full = list(ah_full or [])
    if not ah_full or ph is None:
        return {"p": None, "p_list": None, "ms": ms, "exp": None, "lines": len(ah_full),
                "edge_err": None, "health": "none",
                "notes": ["⚪让球全档缺失 / 1x2 缺失 → 回退静态 margin_candidates"]}

    rows, b, w = [], [], []
    for item in ah_full:
        try:
            line, wh, wa = float(item[0]), float(item[1]), float(item[2])
        except (TypeError, IndexError, ValueError):
            continue
        if wh <= 1 or wa <= 1:
            continue
        coef = []
        for m in ms:
            wf, pf = _settle_frac(m, line)
            coef.append(wh * wf + pf)
        rows.append(coef)
        b.append(1.0)
        d = abs(wh - wa)                                  # 越接近均衡（≈1.9/1.9）权重越高
        w.append(1.0 if d <= 0.25 else (0.5 if d <= 0.6 else 0.15))

    n_lines = len(rows)
    # 1x2 三向硬约束
    rows.append([1.0 if m > 0 else 0.0 for m in ms]); b.append(ph); w.append(P10_1X2_W)
    rows.append([1.0 if m == 0 else 0.0 for m in ms]); b.append(pd); w.append(P10_1X2_W)
    rows.append([1.0 if m < 0 else 0.0 for m in ms]); b.append(pa); w.append(P10_1X2_W)

    if n_lines < 2:
        return {"p": None, "p_list": None, "ms": ms, "exp": None, "lines": n_lines,
                "edge_err": None, "health": "none",
                "notes": ["⚪让球有效档仅 %d 条（<2）→ 回退静态 margin_candidates" % n_lines]}

    try:
        import numpy as np
    except Exception as _en:
        return {"p": None, "p_list": None, "ms": ms, "exp": None, "lines": n_lines,
                "edge_err": None, "health": "none",
                "notes": ["⚪numpy 不可用(%s) → 回退静态 margin_candidates" % type(_en).__name__]}

    A = np.array(rows, dtype=float)
    y = np.array(b, dtype=float)
    W = np.diag(np.sqrt(np.array(w, dtype=float)))
    try:
        from scipy.optimize import nnls
        x, _rn = nnls(W @ A, W @ y)
    except Exception:
        x = np.linalg.lstsq(W @ A, W @ y, rcond=None)[0]
        x = np.clip(x, 0, None)
    s = float(x.sum())
    if s <= 0:
        return {"p": None, "p_list": None, "ms": ms, "exp": None, "lines": n_lines,
                "edge_err": None, "health": "none",
                "notes": ["⚪NNLS 解全 0 → 回退静态 margin_candidates"]}
    x = x / s

    p = {m: float(x[i]) for i, m in enumerate(ms)}
    ch = sum(v for m, v in p.items() if m > 0)
    cd = p.get(0, 0.0)
    ca = sum(v for m, v in p.items() if m < 0)
    exp = sum(m * v for m, v in p.items())
    err = max(abs(ch - ph), abs(cd - pd), abs(ca - pa))
    notes = []
    if err > P10_EDGE_TOL:
        notes.append("⚠️净胜分布边缘 vs 1x2 偏差 %.1fpp → 让球档可能含假档/低分辨率" % (100 * err))
    health = "ok" if (n_lines >= P10_AH_MIN and err <= P10_EDGE_TOL) else "weak"
    return {"p": p, "p_list": [round(p[m], 4) for m in ms], "ms": ms,
            "exp": round(exp, 3), "lines": n_lines,
            "edge_err": round(float(err), 4), "health": health, "notes": notes}


# ============================================================================
# 4. 源3：Team Total 主/客 → 行/列边缘（只进先验·不硬迭代）
# ============================================================================

def team_goal_distribution(tt_dict, max_k=7):
    """单队 Team Total 半档差分 → P(该队进 k 球)；不足 3 条 → None"""
    tt_dict = tt_dict or {}
    half = sorted([ln for ln in tt_dict.keys() if _is_half(ln)])
    surv = {}
    for ln in half:
        try:
            over, under = tt_dict[ln]
        except (TypeError, ValueError):
            continue
        p_over, _pu = _devig_2way(over, under)
        if p_over is None:
            continue
        surv[int(math.floor(float(ln))) + 1] = p_over
    if len(surv) < 3:
        return None
    ks = sorted(surv.keys())
    p = [0.0] * (max_k + 1)
    p[0] = max(0.0, 1.0 - surv[ks[0]])
    for i, k in enumerate(ks):
        if i == 0:
            continue
        p[min(k - 1, max_k)] += max(0.0, surv[ks[i - 1]] - surv[k])
    p[max_k] += max(0.0, surv[ks[-1]])
    s = sum(p)
    return [round(v / s, 4) for v in p] if s > 0 else None


# 🔴P40 DEPRECATED（2026-10-30 批次5）: 全库零调用。内部辅助·重构遗留
#   → 保留备查·不接入
def _tt_parse(raw):
    """raw 1xbet → {"home": {line:(over,under)}, "away": {...}}（Team Total 主/客各 10 档）"""
    out = {"home": {}, "away": {}}
    if not isinstance(raw, dict):
        return out
    for m in ((raw.get("bookmakers") or {}).get("1xbet") or []):
        nm = str(m.get("name") or "").strip().lower()
        if nm not in ("team total home", "team total away"):
            continue
        key = "home" if nm.endswith("home") else "away"
        for o in (m.get("odds") or []):
            try:
                out[key][float(o.get("hdp"))] = (float(o.get("over")), float(o.get("under")))
            except (TypeError, ValueError):
                continue
    return out


# ============================================================================
# 5. 源4 + 融合：CS 联合先验 → IPF 投影到 T/M 边缘 → 比分矩阵
# ============================================================================

def _cs_prior(cs_full, n=7):
    """波胆去水联合先验（占位档 1<v<100 剔除·键归一 'H-A'/'H:A'/'H/A'）"""
    Q = {}
    if not cs_full:
        return Q
    inv = {}
    for k, v in cs_full.items():
        try:
            s = str(k).strip().replace(":", "-").replace("/", "-")
            h, a = int(s.split("-")[0]), int(s.split("-")[1])
            fv = float(v)
        except (TypeError, ValueError, IndexError):
            continue
        if 0 <= h < n and 0 <= a < n and 1 < fv < 100:
            inv[(h, a)] = 1.0 / fv
    tot = sum(inv.values())
    if tot > 0:
        Q = {k: v / tot for k, v in inv.items()}
    return Q


def market_score_matrix(cs_full, pT, pM, pH_row=None, pA_row=None, n=7,
                        iters=P10_IPF_ITERS, soft=P10_SOFT):
    """IPF：以 CS 为形状先验，沿 h+a（总进球）与 h-a（净胜）两组对角线迭代缩放

    只硬约束 T 与 M 两组边缘（用户三源逻辑的两条主轴）；
    Team Total 行/列边缘**只进先验、不硬迭代**——H+A 卷积隐含 T，若再硬约束会与 OU 的 T
    过约束、把矩阵挤变形（原型实测会把 E[M] 拉偏）。
    ```
    """
    try:
        import numpy as np
    except Exception as _en:
        return {"matrix": None, "top": [], "cs_coverage": 0, "expT": None, "expM": None,
                "health": "none", "notes": ["⚪numpy 不可用(%s)" % type(_en).__name__]}

    cs = _cs_prior(cs_full, n)
    cs_cov = len(cs)

    # ---- 先验 Q：优先 Team Total 独立乘积 → 否则按 T 边缘在总进球对角线内均匀铺 ----
    Q = np.full((n, n), 1e-6)
    if pH_row is not None and pA_row is not None:
        for h in range(n):
            for a in range(n):
                Q[h, a] = max(1e-9, float(pH_row[h]) * float(pA_row[a]))
    elif pT is not None:
        for t in range(len(pT)):
            cells = [(h, a) for h in range(n) for a in range(n) if h + a == t]
            if cells and pT[t] > 0:
                for (h, a) in cells:
                    Q[h, a] = max(1e-9, pT[t] / len(cells))
    else:
        Q[:, :] = 1.0
    for (h, a), v in cs.items():
        Q[h, a] = max(Q[h, a], v)                 # CS 覆盖档：市场联合定价覆盖弱先验
    Q = Q / Q.sum()
    P = Q.copy()

    def _scale(cells, target):
        cur = sum(P[h, a] for h, a in cells)
        if cur <= 0:
            return
        factor = (target / cur) ** soft if soft and soft > 0 else target / cur
        for h, a in cells:
            P[h, a] *= factor

    # 🔴P10-fix(2026-10-25·check_sync P10-② 实抓): 预计算对角线格表 + 对「边缘不允许」的对角线
    #   **显式清零** —— 否则 t≥len(pT) / |m|>max(M) 的格无任何约束，会被另一侧缩放反复放大，
    #   导致矩阵 E[T] 系统性偏离 OU 边缘（合成场实测偏差 0.86 球）。
    _cells_t, _cells_m = {}, {}
    for _h in range(n):
        for _a in range(n):
            _cells_t.setdefault(_h + _a, []).append((_h, _a))
            _cells_m.setdefault(_h - _a, []).append((_h, _a))

    def _zero(cells):
        for _h, _a in cells:
            P[_h, _a] = 0.0

    _t_max = (len(pT) - 1) if pT is not None else -1
    _m_ok = set(pM.keys()) if pM is not None else set()

    for _ in range(int(iters)):
        if pT is not None:
            for _t in range(0, 2 * n - 1):
                _cells = _cells_t.get(_t) or []
                if not _cells:
                    continue
                _tv = pT[_t] if _t <= _t_max else 0.0
                if _tv <= 0:
                    _zero(_cells)
                else:
                    _scale(_cells, _tv)
        if pM is not None:
            for _m in range(-(n - 1), n):
                _cells = _cells_m.get(_m) or []
                if not _cells:
                    continue
                if _m not in _m_ok or pM.get(_m, 0.0) <= 0:
                    _zero(_cells)
                else:
                    _scale(_cells, pM[_m])
        _s = P.sum()
        if _s > 0:
            P = P / _s

    matrix = {(h, a): float(P[h, a]) for h in range(n) for a in range(n)}
    top = sorted(matrix.items(), key=lambda kv: -kv[1])[:10]
    top_fmt = []
    for (h, a), pv in top:
        cs_odd = None
        for _k in ("%d-%d" % (h, a), "%d:%d" % (h, a)):
            if isinstance(cs_full, dict) and cs_full.get(_k):
                cs_odd = cs_full.get(_k)
                break
        top_fmt.append(("%d:%d" % (h, a), round(pv * 100, 2), cs_odd))

    expT = sum((h + a) * P[h, a] for h in range(n) for a in range(n))
    expM = sum((h - a) * P[h, a] for h in range(n) for a in range(n))
    # 🔴P10-fix3(2026-10-25·case278 实抓): **尾桶挤压格检测**
    #   「P(T≥max_k)」与某净胜档在 n×n 矩阵内常只有**唯一交叉格**（如 7+球 × 客胜1球 → 3:4），
    #   IPF 为同时满足两条边缘会把它放大到远超波胆定价 → 属**边缘伪影**，禁单独作锚依据。
    #   判据: 矩阵概率 ≥0.05 且（波胆无该格 或 矩阵概率 > 5×CS 去水概率）【阈值待回测校准】
    _cs_p = _cs_prior(cs_full, n)
    squeezed = []
    for (h_, a_), pv_ in matrix.items():
        if pv_ < 0.05:
            continue
        _cp = _cs_p.get((h_, a_))
        if _cp is None:
            squeezed.append("%d:%d(无波胆定价·矩阵%.1f%%)" % (h_, a_, pv_ * 100))
        elif pv_ > P10_SQUEEZE_RATIO * _cp:
            squeezed.append("%d:%d(矩阵%.1f%% > %.1f×波胆%.1f%%)"
                            % (h_, a_, pv_ * 100, P10_SQUEEZE_RATIO, _cp * 100))
    health = "ok" if (cs_cov >= P10_CS_MIN and pT is not None and pM is not None) else (
        "weak" if (pT is not None or pM is not None) else "none")
    return {"matrix": matrix, "top": top_fmt, "cs_coverage": cs_cov,
            "expT": round(float(expT), 3), "expM": round(float(expM), 3),
            "health": health,
            "notes": ["CS 覆盖 %d 档（决定相关性形状·门槛 %d）" % (cs_cov, P10_CS_MIN),
                      "TeamTotal 行/列边缘：%s" % ("有（仅先验）" if (pH_row and pA_row) else "无"),
                      "矩阵截断 0-%d 球/队 → 总进球>%d / 净胜>%d 的对角线**显式清零**"
                      "（T/M 边缘不允许·保边缘精确）" % (n - 1, len(pT) - 1, max(pM.keys()) if pM else 0),
                      ("⚠️尾桶挤压格(矩阵>%.0f×波胆或无波胆定价·**禁单独作锚**): %s"
                       % (P10_SQUEEZE_RATIO, "·".join(squeezed))) if squeezed else "尾桶挤压格: 无"],
            "squeezed": squeezed}


# ============================================================================
# 6. 决策门（方案 §5.5·三源齐全才启用）
# ============================================================================

def decision_gate(tot, mar, cs_full, n_half, n_ah, cs_cov=None):
    """三源齐全才启用：OU 半档≥3 / AH 有效≥4 且 edge_err≤0.08 / CS 有效档≥15"""
    reasons = []
    if n_half < P10_OU_MIN:
        reasons.append("OU 半档仅 %d 条(<%d)" % (n_half, P10_OU_MIN))
    if n_ah < P10_AH_MIN:
        reasons.append("AH 有效档仅 %d 条(<%d)" % (n_ah, P10_AH_MIN))
    _err = (mar or {}).get("edge_err")
    if _err is not None and _err > P10_EDGE_TOL:
        reasons.append("AH vs 1x2 边缘偏差 %.3f(>%.2f)" % (_err, P10_EDGE_TOL))
    if (tot or {}).get("p") is None:
        reasons.append("总进球分布反推失败")
    if (mar or {}).get("p") is None:
        reasons.append("净胜分布反推失败")
    _cs = cs_cov if cs_cov is not None else len(_cs_prior(cs_full))
    if _cs < P10_CS_MIN:
        reasons.append("CS 有效档 %d(<%d)" % (_cs, P10_CS_MIN))
    return {"pass": len(reasons) == 0, "reasons": reasons,
            "n_half": n_half, "n_ah": n_ah, "cs_cov": _cs}


# ============================================================================
# 7. 统一入口
# ============================================================================

def infer_from_parts(ou_full=None, ah_full=None, cs_full=None, oh=None, od=None, oa=None,
                     tt_full=None, jc_goal8=None, n=P10_N, iters=P10_IPF_ITERS, soft=P10_SOFT,
                     btts=None):
    """由**已解析的全档数据**直接算市场矩阵（calc_all 主路径·避免重复解析 raw）

    返回:
      {"ok": bool, "matrix": {matrix:{...}, top, expT, expM, cs_coverage, health, notes},
       "total": {...}, "margin": {...}, "team": {...}, "gate": {...}, "notes": [...]}
      ok=True  ← 决策门通过且矩阵 health=ok → 可作主排序基线
      ok=False ← 三源不足 → 调用方回退 P5/泊松（notes 给三态原因）
    """
    notes = []
    ou_full = ou_full or {}
    ah_full = list(ah_full or [])
    cs_full = dict(cs_full or {})
    tt_full = tt_full or {"home": {}, "away": {}}

    n_half = len([ln for ln in ou_full.keys() if _is_half(ln) and float(ln) >= 0])
    n_ah = len([1 for it in ah_full
                if len(it) >= 3 and float(it[1]) > 1 and float(it[2]) > 1]) if ah_full else 0

    if not (ou_full and ah_full and cs_full and oh and od and oa):
        miss = []
        if not ou_full:
            miss.append("OU全档")
        if not ah_full:
            miss.append("AH全档")
        if not cs_full:
            miss.append("波胆CS")
        if not (oh and od and oa):
            miss.append("ML1x2")
        notes.append("⚪三源不齐（缺 %s）→ 回退 P5/泊松链路" % "/".join(miss))
        return {"ok": False, "matrix": None, "total": None, "margin": None, "team": None,
                "gate": {"pass": False, "reasons": notes}, "notes": notes}

    ph, pd, pa = _devig_3way(oh, od, oa)
    if ph is None:
        return {"ok": False, "matrix": None, "total": None, "margin": None, "team": None,
                "gate": {"pass": False, "reasons": ["ML 赔率异常"]},
                "notes": ["⚪ML 赔率异常 → 回退 P5/泊松链路"]}

    tot = total_goals_distribution(ou_full, jc_goal8, max_k=n)
    mar = goal_margin_distribution(ah_full, ph, pd, pa)
    pH_row = team_goal_distribution(tt_full.get("home") or {}, max_k=n)
    pA_row = team_goal_distribution(tt_full.get("away") or {}, max_k=n)
    gate = decision_gate(tot, mar, cs_full, n_half, n_ah)

    if tot.get("p") is None or mar.get("p") is None:
        return {"ok": False, "matrix": None, "total": tot, "margin": mar,
                "team": {"home": pH_row, "away": pA_row}, "gate": gate,
                "notes": gate.get("reasons") or ["⚪边缘分布反推失败 → 回退 P5/泊松链路"]}

    mat = market_score_matrix(cs_full, tot["p"], mar["p"], pH_row, pA_row,
                              n=n, iters=iters, soft=soft)
    ok = bool(gate.get("pass") and mat.get("health") == "ok")
    notes = list(tot.get("notes") or []) + list(mar.get("notes") or []) + list(mat.get("notes") or [])
    if not ok:
        notes.append("⚪决策门未通过（%s）→ 仅展示·不参与选锚"
                     % ("；".join(gate.get("reasons") or ["矩阵 health=%s" % mat.get("health")])))
    return {"ok": ok, "matrix": mat, "total": tot, "margin": mar,
            "team": {"home": pH_row, "away": pA_row},
            "x12": {"pH": round(ph, 4), "pD": round(pd, 4), "pA": round(pa, 4)},
            # 🔴P10-FINAL R11: 原始 TT 全档 + BTTS 赔率（R11 直盘需要·仅行边缘不够定位 0.5 档去水口径）
            "tt_full": tt_full, "btts_mkt": btts,
            "gate": gate, "notes": notes}


def infer_market_matrix(raw, jc_goal8=None, n=P10_N):
    """从一份 1xbet raw 快照 → 市场矩阵（独立调试/审计用）

    依赖 snapshot_save 的只读解析器（_ou_full/_ah_full/_cs_full/_tt_full），不改其任何状态。
    """
    try:
        import os as _os
        _d = _os.path.dirname(_os.path.abspath(__file__))
        if _d not in sys.path:
            sys.path.insert(0, _d)
        from snapshot_save import _ou_full, _ah_full, _cs_full, _tt_full
    except Exception as _e:
        return {"ok": False, "matrix": None,
                "notes": ["⚪snapshot_save 解析器不可用(%s)" % type(_e).__name__]}

    ou = _ou_full(raw) or {}
    ah = _ah_full(raw) or []
    cs = _cs_full(raw) or {}
    tt = _tt_full(raw) or {"home": {}, "away": {}}

    oh = od = oa = None
    for m in ((raw or {}).get("bookmakers") or {}).get("1xbet") or []:
        if str(m.get("name") or "").strip().lower() == "ml":
            o = (m.get("odds") or [{}])[0]
            try:
                oh, od, oa = float(o["home"]), float(o["draw"]), float(o["away"])
            except (KeyError, TypeError, ValueError):
                oh = od = oa = None
            break

    return infer_from_parts(ou_full=ou, ah_full=ah, cs_full=cs, oh=oh, od=od, oa=oa,
                            tt_full=tt, jc_goal8=jc_goal8, n=n)


# ============================================================================
# 8. 三态留痕（方案附录 B 模板）
# ============================================================================

def fmt_line(mm):
    """一行式留痕（calc_all / 审计消费）——三态：启用 / 弱启用 / 回退"""
    if not isinstance(mm, dict):
        return "⚪市场矩阵(P10)：未计算（无全档数据入口）"
    gate = mm.get("gate") or {}
    if mm.get("ok") and (mm.get("matrix") or {}).get("health") == "ok":
        t, m, mat = mm.get("total") or {}, mm.get("margin") or {}, mm["matrix"]
        pt = t.get("p") or []
        _ptag = " ".join("%d球%.0f%%" % (i, v * 100) for i, v in enumerate(pt) if v >= 0.05)
        _mtag = " ".join("%s %.0f%%" % (("平" if k == 0 else ("主%d" % k if k > 0 else "客%d" % -k)), v * 100)
                         for k, v in sorted((m.get("p") or {}).items(), key=lambda kv: -kv[1])[:4]
                         if v >= 0.03)
        _top = "·".join("%s(%.1f%%)" % (s, p) for s, p, _c in (mat.get("top") or [])[:4])
        _dT = (mat["expT"] - t["exp"]) if (mat.get("expT") is not None and t.get("exp") is not None) else None
        _dM = (mat["expM"] - m["exp"]) if (mat.get("expM") is not None and m.get("exp") is not None) else None
        return ("🔴市场矩阵(P10)：CS覆盖%d档/OU %d半档/AH %d档 | 总进球 %s(期望%.2f) | "
                "净胜 %s(期望%+.2f) | Top4 %s | 主排序=市场矩阵 | 边缘自洽ΔT=%s ΔM=%s"
                % (mat.get("cs_coverage", 0), t.get("ou_lines_used", 0), m.get("lines", 0),
                   _ptag or "-", t.get("exp", 0), _mtag or "-", m.get("exp", 0), _top,
                   ("%+.2f" % _dT) if _dT is not None else "-",
                   ("%+.2f" % _dM) if _dM is not None else "-"))
    if mm.get("matrix"):
        return ("🟡市场矩阵弱(CS %s档·health=%s)：仅展示不选锚 → 比分仍走 P5/泊松链路"
                "（%s）" % ((mm["matrix"] or {}).get("cs_coverage"),
                            (mm["matrix"] or {}).get("health"),
                            "；".join((gate.get("reasons") or [])[:3]) or "-"))
    return ("⚪市场矩阵未启用 → 回退 P5/泊松链路，三态原因：%s"
            % ("；".join((gate.get("reasons") or mm.get("notes") or [])[:4]) or "无全档数据"))


def fmt_block(mm):
    """多行块（供 calc_all 详细留痕）"""
    lines = [fmt_line(mm)]
    if isinstance(mm, dict) and mm.get("total") and mm["total"].get("p"):
        t = mm["total"]
        lines.append("    总进球分布(%s·KL=%s)：%s"
                     % (t.get("origin"), t.get("kl"),
                        " ".join("%d球%.1f%%" % (i, v * 100) for i, v in enumerate(t["p"]))))
    if isinstance(mm, dict) and mm.get("margin") and mm["margin"].get("p"):
        m = mm["margin"]
        _s = " ".join("%s %.1f%%" % (("平" if k == 0 else ("主%d" % k if k > 0 else "客%d" % -k)), v * 100)
                      for k, v in sorted(m["p"].items(), key=lambda kv: -kv[1])[:5] if v >= 0.02)
        lines.append("    净胜分布(%d档·边缘偏差%.3f)：%s" % (m.get("lines", 0), m.get("edge_err") or 0, _s))
    if isinstance(mm, dict) and (mm.get("matrix") or {}).get("top"):
        lines.append("    比分矩阵 Top6：%s"
                     % " · ".join("%s %.1f%%%s" % (s, p, ("(CS%s)" % c) if c else "")
                                  for s, p, c in mm["matrix"]["top"][:6]))
        lines.append("    🔴每个比分同时满足总进球边缘与净胜边缘（IPF 不动点）→ 锚与期望/让球天然不冲突")
        _sq = (mm.get("matrix") or {}).get("squeezed") or []
        if _sq:
            lines.append("    ⚠️尾桶挤压格（矩阵概率远超波胆定价·边缘强制分配·**禁单独作锚**）: %s"
                         % "·".join(_sq[:4]))
    for _n in (mm.get("notes") or [])[:6]:
        if str(_n).startswith("⚠️尾桶挤压格"):
            continue                      # 已由上方专行展示（防重复）
        lines.append("    " + _n)
    return "\n".join(lines)


# ============================================================================
# 5.5 判定标准层（方案 §4.7·R10-1~R10-9）—— 模型拿到矩阵后「怎么定锚」
# ============================================================================
# 🔴全部阈值【待回测校准】·禁单场固化（方向类≥10 场·比分/量级类≥20~30 场且 p<0.05）
# 🔴铁律: ① 输出是分布不是单点（宽池）② 只调权重·不排除候选·不反转 L2 方向
#        ③ 锚必须落在交集池内（受让禁主胜锚 / M·T 域约束·防死锚）
R10_DOUBLE_MAIN_PP = 0.015     # R10-1 双主锚: Top1−Top2 < 1.5pp
R10_WIDE_TOP1 = 0.08           # R10-1 宽池: Top1 < 8%
R10_ZERO_P = 0.30              # R10-3 零封谱系阈值
R10_BTTS_YES_HI = 0.62         # R10-3 BTTS yes ≥62% → 双方进球谱系优先
R10_BTTS_YES_LO = 0.42         # R10-3 BTTS yes ≤42% → 零封谱系强化
R10_BIG4_MID = 0.18            # R10-4 P(T≥4) ≥18% → 主锚候选须含 3+ 球
R10_BIG4_EXTREME = 0.35        # R10-4 P(T≥4) ≥35% → 极端大球宽池 1~6 球
R10_DEEP_HANDI = 1.5           # R10-6 深盘 |handi| ≥1.5
R10_DEEP_LAM = 3.4             # R10-6 极端 λ ≥3.4
R10_CONC_HI = (0.15, 0.35)     # R10-7 高集中（Top1, 前3）
R10_CONC_LO = (0.08, 0.25)     # R10-7 离散下限
R10_DIR_DOM = 0.45             # R10-8 1x2 主导方向阈值
R10_CS_MULT = {"drop_strong": 1.12, "drop_mild": 1.06,
               "rise_mild": 0.96, "rise_strong": 0.90}   # R10-5 波胆纵向乘子
R10_AH_SHIFT_MAX = 0.30        # R10-5 让球升降盘：同向净胜档最大加权
R10_AH_STEP = 0.05             # R10-5 每档 shift 加权步长


def _score_dir(s):
    h, a = [int(x) for x in str(s).split(":")]
    return "主胜" if h > a else ("平局" if h == a else "客胜")


# 🔴P25(2026-10-28 用户指正): 信号约束权重（概率有低分偏置·禁作排序主键）
P25_SIG_W = 1.0        # 约束惩罚权重（pen 单位 = 球）
P25_SIG_MERGE = 1      # 惩罚归并精度（round 到 0.1 → 同档内按概率/波胆排）


def tri_source_move(ah_vert=None, ou_vert=None, cs_vert=None):
    """🔴P51(2026-10-31): **三源移动相关性**（专业机构口径·检索所得）

    行业事实:
      · 开盘→收盘路径携带的信息多于任何单点（OddsFlow）
      · AH 动了而 1X2 不动 = 背离信息；三源同向 = 行业同步调整（synchronized move）
      · 亚盘结构 = 保持盘口调水位 → 水位单向移动本身即资金流
    返回 (判定标签, 置信度档位调整, 说明)
    """
    def _sgn(d, key='shift'):
        try:
            if isinstance(d, dict):
                v = d.get(key)
                if v is None:
                    v = d.get('conf_step') or d.get('dir')
                if isinstance(v, str):
                    return 1 if v in ('drop_strong', 'drop_mild', 'up', 'rise') else -1
                return (float(v) > 0) - (float(v) < 0)
        except Exception:
            pass
        return 0
    _a, _o = _sgn(ah_vert), _sgn(ou_vert)
    _c = 0
    if isinstance(cs_vert, dict) and cs_vert:
        _ds = [1 if (v or {}).get('dir') in ('drop_strong', 'drop_mild') else -1
               for v in cs_vert.values() if isinstance(v, dict)]
        _c = (sum(_ds) > 0) - (sum(_ds) < 0) if _ds else 0
    _acts = [x for x in (_a, _o, _c) if x != 0]
    if not _acts:
        return 'FREEZE/未动', 0.0, 'AH/OU/CS 三源均无移动 → line freeze（庄家自信·按开盘值判）'
    if _a and _o and _a == _o:
        return '三源共振', +0.5, ('AH 与 OU 同向（%s）→ 行业同步调整·置信度 +0.5 档'
                                  % ('看大/主' if _a > 0 else '看小/客'))
    if _a and _o and _a != _o:
        return '三源分裂', -0.5, 'AH 与 OU 反向 → 市场分裂·置信度 −0.5 档·锚取宽池'
    if _a and not _o:
        return '净胜结构变', 0.0, 'AH 移动而 OU 未动 → 净胜档跟随让球·总进球不跟（让球主导）'
    if _o and not _a:
        return '纯进球预期变', 0.0, 'OU 移动而 AH 未动 → 量级跟随大小球·净胜不跟'
    return '单源移动', 0.0, '仅波胆纵向移动 → 仅调候选权重·不改量级'


def anchor_select(mm, oh=None, od=None, oa=None, handi=None, bt_yes=None, bt_no=None,
                  cs_vert=None, ah_vert=None, ou_vert=None, vert_n=None,
                  tad_h=None, tad_a=None, lam=None, cs_full=None, pool=None, n=None,
                  zero_direct=None,
                  t_band=None,               # 🔴V3.5.87 量级档（magnitude_band 输出·方法二）
                  def_dual=None,             # 🔴2026-11-03 O-BIG-1 双方防线双伤 → 宽池扩 6 球
                  dir_first=None,            # 🔴2026-11-03 O-ANCHOR-1 方向首选 → 主锚方向纯
                  # 🔴V3.5.91（2026-11-03 case320 实证）: 真实盘口均衡线（多档 Totals 插值）
                  #   禁再用 _E25 代替 —— N24 校准会把 E[T] 抬高 +0.67 而盘口不动
                  line_eq=None,
                  # 🔴V3.5.92: 纵向**统一标准结构**（snapshot_save._vert_std 产出）
                  #   有则优先消费（结构一致·无需按维度写 if-else）；无则回退旧三键
                  vert_std=None):
    """R10 判定层：市场矩阵 → 主锚/次锚/可信度/规则留痕（方案 §4.7）

    🔴与原型（market_distribution_prototype.anchor_select）的差异（4 处缺陷已修）:
      ⓐ R10-5 cs_vert 真正做乘子（原型是 `pass` 占位）
      ⓑ R10-9 改读 `cs_full`（原型读 `matrix["covered"]` 而该键从不输出 → 规则永不生效）
      ⓒ R10-7 集中度三档重写（原型含无意义语句）
      ⓓ 锚**限定在交集池内**（原型无池约束 → 受让场会锚主胜比分 = 违反铁律）

    返回 {anchor_1st, anchor_2nd, trust, double, wide, pool_top,
          notes, zero_notes, big_notes, masked}
    """
    notes, zero_notes, big_notes = [], [], []
    mm = mm or {}
    mat_sum = mm.get("matrix") or {}
    raw_m = (mat_sum.get("matrix") or {}) if isinstance(mat_sum, dict) else {}
    mat = {"%d:%d" % (h, a): float(p) for (h, a), p in raw_m.items()}
    if not mat:
        return {"anchor_1st": None, "anchor_2nd": None, "trust": "不可信", "double": False,
                "wide": True, "pool_top": [], "notes": ["R10 跳过: 市场矩阵为空"],
                "zero_notes": [], "big_notes": [], "masked": []}

    n = int(n or (max(int(s.split(":")[0]) for s in mat) + 1))
    _zd_final = zero_direct if isinstance(zero_direct, dict) else None
    pT = (mm.get("total") or {}).get("p")
    # 🔴V3.5.88(2026-11-03 分布驱动): 矩阵不可用（无 OU 全档/矩阵弱）时，
    #   回退用 magnitude_band 的分布（查表 148,397 场或泊松）
    #   —— 否则 pT 为空 → 「量级」分项只剩「距均衡线」→ 退回点估计
    if not pT and isinstance(t_band, dict) and t_band.get('pT'):
        pT = list(t_band['pT'])
    pM = (mm.get("margin") or {}).get("p")
    pool_set = set(pool) if pool else None

    # ---- R10-5 纵向异动乘子（只调权重·不改矩阵本体·不排除候选） ----
    mult = {s: 1.0 for s in mat}
    if isinstance(cs_vert, dict):
        hit = 0
        for s, cv in cs_vert.items():
            key = str(s).replace("-", ":")
            d = (cv or {}).get("dir")
            m = R10_CS_MULT.get(d, 1.0)
            if key in mult and m != 1.0:
                mult[key] *= m
                hit += 1
        if hit:
            notes.append("R10-5 波胆纵向 %d 档乘子（降水×1.12/1.06·升水×0.96/0.90·只调权重不排除）" % hit)
    if isinstance(ah_vert, dict) and int(ah_vert.get("shift") or 0) != 0:
        _sh = int(ah_vert.get("shift") or 0)
        _w = min(R10_AH_SHIFT_MAX, abs(_sh) * R10_AH_STEP)
        for s in mult:
            d = _score_dir(s)
            if (_sh > 0 and d == "主胜") or (_sh < 0 and d == "客胜"):
                mult[s] *= (1.0 + _w)
        notes.append("R10-5 让球升降盘[%s] shift=%+d → 同向净胜档 +%.0f%%（≤30%%·不硬移档）"
                     % (ah_vert.get("combo"), _sh, _w * 100))

    adj = {s: mat[s] * mult[s] for s in mat}
    masked = []
    if pool_set:
        cand = {s: p for s, p in adj.items() if s in pool_set}
        if cand:
            dropped = [s for s in adj if s not in pool_set and adj[s] >= 0.03]
            adj = cand
            if dropped:
                masked = sorted(dropped, key=lambda x: -mat[x])[:4]
        else:
            notes.append("R10 池过滤后为空 → 回退全矩阵（标注·非死锚）")
    # 🔴P25(2026-10-28 用户指正): 排序主键 = **市场信号约束**（非概率·概率天然低分偏置）
    #   ① 期望进球 E（由总进球分布 pT 加权）② 大小球方向（P(over2.5)）
    #   ③ 让球深度（让 1.5+ 须净胜≥2 · 让 0.75+ 须净胜≥1）
    #   同档内再按矩阵概率排序 → 满足「信号定方向·波胆/概率在档内挑最认的」
    _E25 = None
    _pov25 = None
    # ① 期望进球：优先 lam（Step6.5 五源 λ_final = 权威期望）→ total.exp → pT 加权
    try:
        if lam is not None:
            _E25 = float(lam)
    except Exception:
        _E25 = None
    if _E25 is None:
        try:
            _ex = (mm.get("total") or {}).get("exp")
            if _ex is not None:
                _E25 = float(_ex)
        except Exception:
            pass
    # ② over2.5：兼容 pT 为 list（下标=进球数）或 dict
    try:
        _sum_all = _sum_o = 0.0
        if isinstance(pT, dict) and pT:
            for _k, _v in pT.items():
                _sum_all += float(_v)
                if float(_k) > 2.5:
                    _sum_o += float(_v)
        elif isinstance(pT, (list, tuple)) and pT:
            _sum_all = sum(float(_v) for _v in pT)
            _sum_o = sum(float(_v) for _i, _v in enumerate(pT) if _i > 2.5)
        if _sum_all > 0:
            _pov25 = _sum_o / _sum_all
    except Exception:
        _pov25 = None
    # ③ 大/小球侧：over2.5 优先，缺失时用 lam 阈值兜底
    if _pov25 is not None:
        _big25 = _pov25 >= 0.53
        _small25 = _pov25 <= 0.47
    elif _E25 is not None:
        _big25 = _E25 >= 2.70
        _small25 = _E25 <= 2.30
    else:
        _big25 = _small25 = False
    # 🔴P47(2026-10-31 用户指正「1.378的大2.5+让1.5 却推荐1:2·应该在数据层面做文章」):
    #   从本场档分布推「市场均衡线」= P(T≥k) 首次 ≤50% 的 k−0.5
    #   等价于大小球 over/under 赔率相等处（本场 = 3.5，与 1xbet 全档插值 3.43 差 0.07）
    #   → 供「量级」分项与次锚上沿跨度使用（此前只用 O2.5 单档 → 大球强度信息丢失）
    # 🔴P51-fix(泛化修正): 均衡线优先 λ（_E25=市场期望≈1xbet 全档插值均衡线）+ 2.0~4.2 守卫
    #   PMF 反推仅回退（逐档验算：1.20-1.30 档反推 4.50 而实际均球 3.23 → 会抬到 5 球）
    _line_eq = None
    # 🔴V3.5.91 修（2026-11-03 case320 实证·P52 同场两分级的根因）:
    #   原实现直接拿 _E25（期望总进球）当均衡线，理由是「无校准时两者近似」。
    #   但 N24 欧冠校准把 λ 上修 +0.67 → _E25=4.02，而**盘口均衡线仍是 3.15**（机构没动盘）
    #   → level_from_line(4.02) 判 L5，而 calc_all 用 3.15 判 L3 → **同场两个分级**
    #   → 宽池必含 / 次锚跨度 / 量级分项全部按错档执行。
    #   现: ①优先显式传入的**真实均衡线** ②无才回退 _E25 ③再无走 PMF 反推
    try:
        if line_eq is not None and 2.0 <= float(line_eq) <= 4.2:
            _line_eq = round(float(line_eq), 2)
    except (TypeError, ValueError):
        _line_eq = None
    if _line_eq is None:
        try:
            if _E25 is not None and 2.0 <= float(_E25) <= 4.2:
                _line_eq = round(float(_E25), 2)
        except (TypeError, ValueError):
            _line_eq = None
    if _line_eq is None:
        try:
            if isinstance(pT, (list, tuple)) and pT and sum(pT) > 0:
                _sumT = sum(pT)
                _cumT = 0.0
                for _k7 in range(1, len(pT)):
                    _cumT += pT[_k7 - 1]
                    if _cumT / _sumT >= 0.5:
                        _c7 = _k7 - 0.5
                        if 2.0 <= _c7 <= 4.2:
                            _line_eq = _c7
                        break
        except Exception:
            _line_eq = None

    # 🔴P52-fix(2026-10-31 端到端审计): 六级分级**单一口径**（唯一源 = big_pool_policy）
    #   断链实证: 修复前本文件 grep `big_pool|classify|LEVELS|required` = **全空**
    #   → P52「超大球 L5/L4」只在 calc_all 打印，对锚/宽池/支持度**零影响**
    #   现三处真消费: ①量级分项 ②宽池必含(4/5/6/7) ③次锚跨度
    _P52_LV, _P52_REQ, _P52_SPAN = 'L0', [], 0
    try:
        import big_pool_policy as _BPP52
        _P52_LV = _BPP52.level_from_line(_line_eq, None)
            # 🔴2026-11-03 O-BIG-1: 双方防线双伤 → L3 宽池扩 6 球 / L2 补 5 球
        _P52_REQ = _BPP52.required_bins(_P52_LV, def_dual=bool(def_dual))
    except Exception:
        _P52_LV, _P52_REQ = 'L0', []
    # 🔴V3.5.88(2026-11-03 分布驱动·用户裁定方案 A): 尾部档并入宽池必含
    #   判据从「距中心几球」改为「**本场分布 P(k) ≥ 5%**」—— 市场自己说这个档不罕见，就该进池
    #   实证 317: P(≥4球)=36.4%，旧机制把 5/6/7 球按「距中心」压到 0.10 → 真实打出 2:4(6球)
    #   **只扩入不删除**（不占锚位 → 零代价·R-POOL-BIG 铁律）
    _tail_req = []
    try:
        if isinstance(t_band, dict):
            _tail_req = [int(k) for k in (t_band.get('tail_bins') or []) if 1 <= int(k) <= 7]
    except Exception:
        _tail_req = []
    # 🔴V3.5.88 灰度/AB 开关: MD_NO_TAIL=1 → 关闭尾部档并入（回滚 + 消融验证用）
    try:
        import os as _os88
        if _os88.environ.get('MD_NO_TAIL') == '1':
            _tail_req = []
    except Exception:
        pass
    if _tail_req:
        _P52_REQ = sorted(set(list(_P52_REQ) + _tail_req))

    # 🔴R11 零封/双方进球直盘（P26 L3 输入·直盘优先于矩阵后验）
    _zd = _zd_final if isinstance(_zd_final, dict) else {}
    _hclean = _zd.get("home_clean")
    _aclean = _zd.get("away_clean")
    _btts_p = _zd.get("btts")
    _spec = _zd.get("spectrum_code")
    _rh = _zd.get("rho")
    # BTTS 缺直盘时用矩阵后验兜底（三态留痕在 anchor_select 外层）

    # 🔴P29(2026-10-28 用户指令「不依赖概率」): 池内选择只用**市场原始报价**
    #   波胆排名 = CS 赔率升序（赔率越低=市场越看好）——这是市场直接定价，非概率计算
    _cs_rank29 = {}
    try:
        _csv29 = {}
        for _k29, _o29 in (cs_full or {}).items():
            try:
                _f29 = float(_o29)
            except (TypeError, ValueError):
                continue
            if 1 < _f29 < 100:                 # 剔除占位档
                _csv29[str(_k29).replace("-", ":")] = _f29
        for _r29, (_kk29, _oo29) in enumerate(sorted(_csv29.items(), key=lambda z: z[1]), 1):
            _cs_rank29[_kk29] = _r29
    except Exception:
        _cs_rank29 = {}

    # 🔴P28(2026-10-28 用户裁定「摆脱机械锚定·可以设比分池但不能机械锚定某一个」):
    #   罚分制(违反阈值即出局) → 评分制(每个比分算「市场信号支持度」，连续分·不淘汰)
    #   输出 = 比分池 + 每个比分逐项信号依据；主锚=池内支持度第一(排序结果·非承诺)

    def _signal_support(_s):

        """市场信号支持度（0~1 各分项 → 加权总分）· 不淘汰任何候选

        返回 (总分, {分项: (得分, 说明)})
        分项全部来自市场读数：期望进球 / 大小球方向 / 让球深度 / 零封-双方进球谱系 / 矩阵概率
        """
        try:
            _h, _a = [int(_x) for _x in str(_s).split(":")]
        except Exception:

            return 0.0, {}
        _t, _m = _h + _a, _h - _a
        _d = {}
        # ⑥ 🔴P35 纵向变动（时间维度·初盘→临场·与截面三源信息不重叠）
        #   注: cs_vert/ah_vert/ou_vert 早已由 joint_solver 传入 anchor_select，
        #   但 _signal_support 此前**从未消费**（P28/P29 评分池重写时遗漏）→ 纵向零影响
        # 🔴V3.5.92（用户指令「固定标准数据结构·方便获取也方便消费」）:
        #   **优先读 std 统一层**（signal/detail 结构固定），无则回退旧三键 —— 行为不变。
        #   · ah / ou 是**全局单值** → 读 std.signal.{ah,ou}.v
        #   · cs 是**逐比分** → 仍需读 std.detail.cs[str(s)]（signal.cs 为全局聚合，不能替代单比分）
        #   🔴 视角铁律: std 的 v 已折算成主队视角（受让场在 snapshot_save 已翻转）
        #      → 此处**禁止再按 handi 正负二次翻转**（会翻两次 = 反）。
        _vs, _vnote = 0.5, "无纵向数据"
        _sg, _dt = {}, {}
        if isinstance(vert_std, dict):
            _sg = vert_std.get("signal") or {}
            _dt = vert_std.get("detail") or {}
        _csd = (_dt.get("cs") if _dt else None) or cs_vert
        _ahd = (_dt.get("ah") if _dt else None) or ah_vert
        _oud = (_dt.get("ou") if _dt else None) or ou_vert
        _cv1 = None
        if isinstance(_csd, dict) and _csd:
            _cv1 = _csd.get(str(_s))
            if _cv1 is None:
                _cv1 = _csd.get(str(_s).replace(":", "-"))
        if isinstance(_cv1, dict):
            _dr = _cv1.get("dir")
            _vs = {"drop_strong": 1.0, "drop_mild": 0.75,
                   "rise_mild": 0.25, "rise_strong": 0.0}.get(_dr, 0.5)
            _vnote = "波胆%s(%+.1f%%)" % (_dr, (_cv1.get("chg") or 0) * 100)
            if int(vert_n or 0) >= 3:
                _vs = min(1.0, max(0.0, 0.5 + (_vs - 0.5) * 1.3))
                _vnote += "·%d时点" % int(vert_n)
        # 让球：优先 std.signal.ah.v（统一口径）→ 回退旧 shift
        _sh = int((_sg.get("ah") or {}).get("v") or 0) if _sg else 0
        if not _sh:
            _sh = int((_ahd or {}).get("shift") or 0) if isinstance(_ahd, dict) else 0
        if _sh:
            _same = ((_m > 0 and _sh > 0) or (_m < 0 and _sh < 0)
                     or (_m == 0 and _sh == 0))
            _vs = min(1.0, _vs + 0.10) if _same else max(0.0, _vs - 0.10)
            _vnote += "·让球%s(%s)" % ((_ahd or {}).get("combo"), "同向" if _same else "反向")
        # 大小球：优先 std.signal.ou.v → 回退旧 conf_step
        _st = int((_sg.get("ou") or {}).get("v") or 0) if _sg else 0
        if not _st:
            _st = int((_oud or {}).get("conf_step") or 0) if isinstance(_oud, dict) else 0
        if _st:
            _ok_ou = (_st > 0 and _t >= 3) or (_st < 0 and _t <= 2)
            _vs = min(1.0, _vs + 0.08) if _ok_ou else max(0.0, _vs - 0.06)
            _vnote += "·大小球%+d档" % _st
        # std 汇总（几源同向）——仅留痕·不加权（避免重复计价 ah/cs 已被各自计入）
        if _sg and (_sg.get("agree") or {}).get("n_agree"):
            _vnote += "·" + str((_sg["agree"]).get("label"))
        _d["纵向"] = (round(_vs, 3), _vnote)

        # (7) 2026-10-30 批次2 修复: N27 球队攻防档案（原 D5 死代码·全库零调用）
        #   双向预期（禁混合主客）: 主=(主.gf+客.ga)/2 · 客=(客.gf+主.ga)/2
        _ad_s, _ad_note = 0.5, "无攻防档案"
        try:
            if (isinstance(tad_h, dict) and isinstance(tad_a, dict)
                    and tad_h.get("gf") is not None and tad_a.get("ga") is not None):
                _eh = (float(tad_h.get("gf")) + float(tad_a.get("ga"))) / 2.0
                _ea = (float(tad_a.get("gf")) + float(tad_h.get("ga"))) / 2.0
                _dev = abs(_h - _eh) + abs(_a - _ea)
                _ad_s = max(0.0, 1.0 - _dev / 2.5)
                _ad_note = "预期%.1f:%.1f·实际%d:%d·偏离%.2f" % (_eh, _ea, _h, _a, _dev)
        except (TypeError, ValueError):
            pass
        _d["攻防"] = (round(_ad_s, 3), _ad_note)

        # ① 期望进球匹配（越接近越高·连续·非阈值）
        if _E25 is not None:
            _dev = abs(_t - _E25)
            _d["期望"] = (max(0.0, 1.0 - _dev / 2.0), "%d球·偏离%+.2f" % (_t, _t - _E25))
        else:
            _d["期望"] = (0.5, "无期望源")
        # ② 量级（🔴P47 2026-10-31 连续化）
        #   旧实现: 大球侧 t≥3 一律 1.0、小球侧 t≤2 一律 1.0 → **1.378 与 1.80 的盘完全同分**
        #     → 大球强度在评分层零信息（case300 实证: 3 球与 5 球同分 → 锚永远偏小）
        #   新实现: 档相对密度(40%) + 均衡线单侧容忍(60%)——**下侧严、上侧宽 1 球**
        #     低于均衡线每 1 球罚 /1.5；高出均衡线 1 球以内不罚（大球盘的上沿本就该宽）
        _lv_ok = False
        if _line_eq is not None:
            try:
                _pk7 = max(pT) if isinstance(pT, (list, tuple)) and len(pT) else None
                _dens = (pT[_t] / _pk7) if (_pk7 and 0 <= _t < len(pT)) else None
                # 🔴P51-fix: **对称**偏离（原「下侧严·上侧宽 1 球」= 照单场加的偏置）
                _near = max(0.0, 1.0 - abs(_t - _line_eq) / 2.0)
                _lv = (0.5 * _dens + 0.5 * _near) if _dens is not None else _near
                _d["量级"] = (round(min(1.0, max(0.0, _lv)), 3),
                              "均衡线%.2f·%d球·密度%s·贴合%.2f"
                              % (_line_eq, _t,
                                 ("%.0f%%" % (100 * _dens)) if _dens is not None else "-", _near))
                _lv_ok = True
            except Exception:
                _lv_ok = False
        if not _lv_ok:
            if _big25:
                _d["量级"] = (1.0 if _t >= 3 else 0.25, "大球侧·%d球(无均衡线回退)" % _t)
            elif _small25:
                _d["量级"] = (1.0 if _t <= 2 else 0.25, "小球侧·%d球(无均衡线回退)" % _t)
            else:
                _d["量级"] = (0.7, "中性·%d球(无均衡线回退)" % _t)
        # 🔴P52-fix: 分级叠加（只抬不压·超大球 L5/L4 顶格·数据: L5 均球4.02/L4 3.55/L3 3.21）
        try:
            _lv_floor = {'L5': 0.97, 'L4': 0.90, 'L3': 0.82}.get(_P52_LV)
            if _lv_floor is not None and _d["量级"][0] < _lv_floor:
                _d["量级"] = (_lv_floor, _d["量级"][1] + "·%s(%s)抬至%.2f" % (_P52_LV, _P52_REQ, _lv_floor))
        except Exception:
            pass
        # ③ 让球深度（满足穿盘=满 · 越接近越加分·不淘汰）
        try:
            if handi is not None:
                _hh = abs(float(handi))
                _need = 2 if _hh >= 1.5 else (1 if _hh >= 0.75 else 0)
                _gap = max(0, _need - abs(_m))
                _d["让球"] = (max(0.0, 1.0 - _gap * 0.5),
                              "让%.2f·净胜%+d%s" % (float(handi), _m, "·穿盘" if _gap == 0 else "·差%d球" % _gap))
            else:
                _d["让球"] = (0.7, "无让球源")
        except Exception:
            _d["让球"] = (0.7, "让球解析失败")
        # ④ 零封 / 双方进球谱系（连续·按直盘概率加权·不硬性禁止）
        _sup4, _note4 = 0.7, "中性"
        try:
            _bp = float(_btts_p) if _btts_p is not None else None
            _both = (_h > 0 and _a > 0)
            if _bp is not None:
                if _bp >= 0.60:                       # 双方进球为主
                    _sup4 = 1.0 if _both else 0.15
                    _note4 = "BTTS%.0f%%·%s" % (_bp * 100, "双方进球" if _both else "含零封")
                elif _bp <= 0.42:                     # 零封为主
                    _sup4 = 1.0 if not _both else 0.35
                    _note4 = "BTTS%.0f%%·%s" % (_bp * 100, "零封型" if not _both else "双方进球")
                else:
                    _note4 = "BTTS%.0f%%·中性" % (_bp * 100)
            # 单方强零封：按概率连续加权（不淘汰）
            for _cl, _side in ((_aclean, "away"), (_hclean, "home")):
                if _cl is None:
                    continue
                _cp = float(_cl)
                if _side == "away" and _a == 0:
                    _sup4 = min(1.0, _sup4 + _cp * 0.5)
                    _note4 += "·客零封%.0f%%" % (_cp * 100)
                elif _side == "home" and _h == 0:
                    _sup4 = min(1.0, _sup4 + _cp * 0.5)
                    _note4 += "·主零封%.0f%%" % (_cp * 100)
                elif _cp >= 0.40:
                    _sup4 = max(0.0, _sup4 - _cp * 0.5)
                    _note4 += "·%s被零封%.0f%%" % ("客" if _side == "away" else "主", _cp * 100)
            _d["零封/双方进球"] = (_sup4, _note4)
        except Exception:
            _d["零封/双方进球"] = (0.7, "直盘缺失")
        # ⓪ 🔴P46(2026-10-30 用户指令「以市场信号为准」): 矩阵概率入排序
        #   P10 三源(OU×AH×CS) IPF 融合矩阵 = **市场赔率反推的分布**（非泊松统计概率）
        #   此前 _signal_support 注释声称含「矩阵概率」但权重表**根本没这一项**
        #   → 矩阵算出却零影响（四场实证：矩阵 Top1 与锚全不一致）→ 本项补上
        _mm_s, _mm_note = 0.5, "无矩阵"
        try:
            if isinstance(mm, dict):
                # 🔴实测结构(mm['matrix'] 是嵌套 dict):
                #   {'matrix': {(h,a): p}, 'top': [('2:0', 12.71, 8.5), ...],
                #    'cs_coverage': 24, 'expT': 3.31, 'expM': 1.454}
                # 首版取 mm.get('matrix') 拿到的正是外层 → _pw 恒 None（假接入）→ 已修
                _outer = mm.get("matrix") or {}
                _grid = (_outer.get("matrix") if isinstance(_outer, dict) else None) or {}
                _top = (_outer.get("top") if isinstance(_outer, dict) else None) or []
                _pw, _pk = None, None
                if _top:
                    _pk = float(_top[0][1]) / 100.0     # 本场最高比分概率
                    for _it in _top:
                        if str(_it[0]) == str(_s):
                            _pw = float(_it[1]) / 100.0
                            break
                if _pw is None and isinstance(_grid, dict):
                    try:
                        _hh, _aa = [int(x) for x in str(_s).split(":")]
                        _pw = _grid.get((_hh, _aa))
                    except (TypeError, ValueError):
                        _pw = None
                    if _pk is None:
                        _vals = [float(v) for v in _grid.values() if isinstance(v, (int, float))]
                        _pk = max(_vals) if _vals else None
                if _pw is not None and _pk:
                    _mm_s = min(1.0, float(_pw) / max(float(_pk), 1e-9))
                    _mm_note = "矩阵%.1f%%(峰值比%.0f%%)" % (100 * float(_pw), 100 * _mm_s)
        except Exception:
            pass
        _d["矩阵"] = (round(_mm_s, 3), _mm_note)

        # ⑤ 波胆市场排名（CS 赔率升序=市场直接定价·**非概率**·P29 取代矩阵概率）
        _rk29 = _cs_rank29.get(_s)
        if _rk29:
            _d["波胆排名"] = (max(0.0, 1.0 - (_rk29 - 1) * 0.12), "市场第%d低赔" % _rk29)
        else:
            _d["波胆排名"] = (0.25, "波胆未定价")
        # 加权总分（只用市场原始读数·零概率项）
        # 🔴P35: 5 → 6 项（新增「纵向」0.12·其余等比缩至 0.88）
        _W = {"矩阵": 0.30, "波胆排名": 0.24, "期望": 0.15, "量级": 0.11,
            "让球": 0.08, "零封/双方进球": 0.06, "纵向": 0.04, "攻防": 0.02}
        _tot = sum(_W.get(k, 0) * v[0] for k, v in _d.items())

        return _tot, _d

    def _pen25(_s):
        """（P26 罚分·保留兼容旧调用·P28 起排序改用 _signal_support）
        """
        try:
            _h, _a = [int(_x) for _x in str(_s).split(":")]
        except Exception:
            return 0.0
        _t, _m = _h + _a, _h - _a
        _p = 0.0
        # ── L1 让球穿盘（最硬·不可让） ──
        try:
            if handi is not None:
                _hh = abs(float(handi))
                if _hh >= 1.5 and abs(_m) < 2:
                    _p += 3.0
                elif _hh >= 0.75 and abs(_m) < 1:
                    _p += 2.0
        except Exception:
            pass
        # ── L2 大小球方向（硬） ──
        if _big25 and _t < 3:
            _p += 2.0
        if _small25 and _t > 2:
            _p += 2.0
        # ── L3 零封 / 双方进球谱系（R11 直盘·用户补充重点） ──
        _zero_allowed = False        # 本场是否「零封合理」（供 L4 放宽）
        try:
            if _btts_p is not None:
                _bp = float(_btts_p)
                if _bp >= 0.60:      # 双方进球为主 → 任一队 0 球重罚
                    if _h == 0 or _a == 0:
                        _p += 2.5
                elif _bp <= 0.42:    # 零封为主 → 双方进球比分降权
                    _zero_allowed = True
                    if _h > 0 and _a > 0:
                        _p += 1.5
            # 单方强零封谱系（R11-4：≥40% 强 / 30-40% 弱）
            for _cl, _side in ((_aclean, "away"), (_hclean, "home")):
                if _cl is None:
                    continue
                _cp = float(_cl)
                if _cp >= 0.40:
                    _zero_allowed = True
                    if _side == "away" and _a > 0:
                        _p += 1.5     # 客队被零封强 → 客进球比分降权
                    if _side == "home" and _h > 0:
                        _p += 1.5
                elif _cp >= 0.30:
                    _zero_allowed = True
                    if _side == "away" and _a > 0:
                        _p += 0.75
                    if _side == "home" and _h > 0:
                        _p += 0.75
        except Exception:
            pass
        # ── L4 期望进球（正经约束·允许偏移量由**市场信号强度**决定·上限 1.5） ──
        #   🔴P26-c(2026-10-28 用户澄清): 期望不是最低优先级；只有「信号 vs 期望略微冲突」时
        #   才以信号为准 —— 信号越明确，允许偏离期望越多（0.5 → 1.5 球），偏移再大照样扣分。
        try:
            if _E25 is not None:
                _strength = 0
                # ① 让球穿盘条件本身满足（L1 未罚）
                try:
                    if handi is not None:
                        _hh2 = abs(float(handi))
                        if _hh2 >= 1.5 and abs(_m) >= 2:
                            _strength += 1
                        elif _hh2 >= 0.75 and abs(_m) >= 1:
                            _strength += 1
                        elif _hh2 < 0.75:
                            _strength += 1          # 浅盘无穿盘要求 → 不构成冲突
                except Exception:
                    pass
                # ② 大小球方向明确
                if _pov25 is not None and (_pov25 >= 0.58 or _pov25 <= 0.42):
                    _strength += 1
                # ③ BTTS 明确
                if _btts_p is not None:
                    try:
                        if float(_btts_p) >= 0.60 or float(_btts_p) <= 0.42:
                            _strength += 1
                    except Exception:
                        pass
                # ④ 强零封谱系
                for _cl2 in (_aclean, _hclean):
                    if _cl2 is not None:
                        try:
                            if float(_cl2) >= 0.40:
                                _strength += 1
                                break
                        except Exception:
                            pass
                _allow = 0.5 + 0.25 * _strength
                if _zero_allowed:
                    _allow += 0.25
                _allow = min(_allow, 1.5)
                _d = abs(_t - _E25)
                if _d > _allow:
                    _p += (_d - _allow) * 2.0
        except Exception:
            pass
        return _p

        def _tof(_s):        # 总进球（排序辅助）·P40 嵌套辅助（保留原结构）
            try:
                _x = [int(_z) for _z in str(_s).split(":")]
                return _x[0] + _x[1]
            except Exception:
                return 0

    # 🔴P28: 评分制排序 —— 每个比分算「市场信号支持度」，保留全部候选（不淘汰）
    # 🔴V3.5.87 量级档前置（用户 2026-11-02 指令「先定量级再选比分」）
    #   根因（315 场实证）：主锚总球 σ=0.77 vs 真实 σ=1.71 → 真实 4+ 球 44.4% 而主锚只 2.0%
    #     → 真实 3+ 球场次里 49.2% 主锚 ≤2 球 = **锚注定出局**
    #   修法：`t_band`（magnitude_band 五源融合：P10 E[T] + P52 六档 + O2.5 + λ + 盘口线）
    #     给每个比分乘**档权重**（档内 1.0 / 档外 1 球 0.55 / 2 球 0.25 / ≥3 球 0.10）
    #   🔴**只降权不排除**（用户明确「方法一不用·禁止限制量级上下限」→ 档外强信号仍可进池）
    _bw_hit = {}
    _scored_raw = []
    for _s, _p in adj.items():
        _sup, _det = _signal_support(_s)
        if t_band:
            try:
                from magnitude_band import band_weight as _bwt
                _bw = float(_bwt(_s, t_band))
            except Exception:
                _bw = 1.0
            if _bw != 1.0:
                _bw_hit[_bw] = _bw_hit.get(_bw, 0) + 1
            _sup = _sup * _bw
            if isinstance(_det, dict):
                _det = dict(_det)
                _det['量级档'] = (round(_bw, 2), {'w': round(_bw, 2)})
        _scored_raw.append((_sup, _s, _p, _det))
    if t_band:
        notes.append('🔴V3.5.87 量级档前置: 中心 %s 球（优先 %s-%s）｜%s｜档外降权 %s'
                     % (t_band.get('T_star'), t_band.get('T_lo'), t_band.get('T_hi'),
                        t_band.get('band'),
                        ('/'.join('%d档×%.2f' % (k, v) for k, v in sorted(_bw_hit.items()))
                         if _bw_hit else '全部档内')))
    # 🔴P29: tie-break 也不用概率 → 波胆市场排名靠前优先，再退字典序
    _scored_raw.sort(key=lambda z: (-z[0], _cs_rank29.get(z[1], 999), z[1]))
    # 比分池（Top8·附逐项依据）
    score_pool = [{"score": z[1], "support": round(z[0], 3),
                   "cs_rank": _cs_rank29.get(z[1]), "why": z[3]} for z in _scored_raw[:8]]
    _sup_txt = " · ".join("%s %.2f" % (z[1], z[0]) for z in _scored_raw[:5])
    # 🔴P52-fix②: 宽池必含档（L5→4/5/6/7 · L4→4/5/6 · L3→4/5 · L2→4）
    #   只**扩入不删除**（宽池不占锚位 → 零代价·契合用户「宽池可放宽·锚位要谨慎」）
    notes.append("🔴P52 超大球分级: %s（均衡线%s·宽池必含%s球）"
                 % (_P52_LV, ("%.2f" % _line_eq) if _line_eq is not None else "-",
                    ("/" .join(str(b) for b in _P52_REQ)) or "无"))
    _p52_added = []
    # 🔴2026-11-03 用户指令「宽池里的比分也得符合市场信号，而不是硬锚」
    #   原实现（下方 next(...)）**只按总进球数取该档第一个** → 完全绕过 方向/净胜/受让/支持度，
    #   实测 317 场补入 2:4（净胜 −2·该场受让 0.25 + 市场净胜期望 −0.02）= 硬塞。
    #   现改为「**逐候选过市场信号门槛**·全被拒则该档空缺并留痕」，口径与 P28「池内按市场信号挑·非按档塞」一致。
    _mkt_dir, _mkt_p, _mkt_m = None, 0.0, None
    try:
        _o_ = [float(x) for x in (oh, od, oa)]
        if all(v > 1.0 for v in _o_):
            _inv = [1.0 / v for v in _o_]
            _sm = sum(_inv)
            _ph, _pd, _pa = [x / _sm for x in _inv]
            _mkt_p, _mkt_dir = max((_ph, '主胜'), (_pd, '平局'), (_pa, '客胜'))
    except (TypeError, ValueError):
        pass
    try:                                   # 市场净胜期望（矩阵 margin 边缘·键带符号）
        _pm = (mm.get('margin') or {}).get('p') or {}
        if isinstance(_pm, dict) and _pm:
            _den = sum(float(v) for v in _pm.values()) or 1.0
            _mkt_m = sum(int(k) * float(v) for k, v in _pm.items()) / _den
        elif isinstance(_pm, list) and _pm:
            _off = len(_pm) // 2
            _mkt_m = sum((i - _off) * float(v) for i, v in enumerate(_pm))
    except (TypeError, ValueError, IndexError):
        _mkt_m = None

    def _wl_gate(_s, _sup):
        """宽池补入 · 市场信号门槛 → (ok, 原因)"""
        try:
            _dd = _score_dir(_s)
            _h, _a = [int(x) for x in str(_s).split(":")]
            _mg = _h - _a
        except (ValueError, TypeError):
            return False, '比分解析失败'
        # ① 受让场禁主胜比分（P17/case210 铁律·原补入路径完全没检查）
        if handi is not None:
            try:
                if float(handi) > 0.05 and _dd == '主胜':
                    return False, '受让场禁主胜比分'
            except (TypeError, ValueError):
                pass
        # ② 方向：市场方向明确(≥45%) → 只允许「市场方向 或 平局」（禁反向硬塞）
        if _mkt_dir and _mkt_p >= 0.45 and _dd not in (_mkt_dir, '平局'):
            return False, '方向%s≠市场%s(%.0f%%)' % (_dd, _mkt_dir, _mkt_p * 100)
        # ③ 净胜：偏离市场净胜期望 >2 球 → 拒（宽池可放宽·但不能脱离市场）
        if _mkt_m is not None and abs(_mg - _mkt_m) > 2.0:
            return False, '净胜%+d偏市场%+.1f球' % (_mg, _mkt_m)
        # ④ 波胆市场定价：**有定价但排名很后（>12）** → 市场明确不看好 → 拒
        #   （未定价不拒·沿用 P28「未定价给基线 0.25」口径）
        try:
            _rk = _cs_rank29.get(_s)
            if _rk is not None and int(_rk) > 12:
                return False, '波胆第%d(市场不看好)' % int(_rk)
        except (TypeError, ValueError):
            pass
        # 🔴2026-11-03 审计实抓: _cs_rank29 只收录**低赔档**，高价比分查不到排名
        #   → 3:3(60倍) 被判「未定价」混进宽池 → 改用**原始波胆赔率**兜底（≥30 倍 = 市场明显不看好）
        try:
            _o_s = (cs_full or {}).get(_s)
            if _o_s is not None and float(_o_s) >= 30.0:
                return False, '波胆%.0f倍(市场不看好)' % float(_o_s)
        except (TypeError, ValueError):
            pass
        # ⑤ 支持度地板：该比分与市场信号全面冲突（相对峰值 30%）→ 不进池稀释
        _peak = _scored_raw[0][0] if _scored_raw else 1.0
        _floor = max(0.08, 0.30 * _peak)
        if _sup < _floor:
            return False, '支持度%.2f<地板%.2f' % (_sup, _floor)
        return True, 'ok'

    if _P52_REQ:
        try:
            _in_pool = set(str(x["score"]) for x in score_pool)
            _p52_rej = []
            for _bin in _P52_REQ:
                if any(sum(int(q) for q in s.split(":")) == _bin for s in _in_pool):
                    continue
                # 该档**全部候选按支持度降序**逐个过门槛（不是取第一个）
                _cands = [z for z in _scored_raw
                          if sum(int(q) for q in str(z[1]).split(":")) == _bin]
                _picked, _why_rej = None, []
                # 🔴2026-11-03 结构性修复：`_scored_raw` 只扫交集池（L833 `adj = cand`）
                #   → 交集池里没有的档，宽池**永远补不进去**（真实 calc_all 零留痕，此前是假效果）
                #   现改：池内无该档 → 从**典型谱系 TYPICAL** 生成候选，**仍逐条过市场信号门槛**
                #   （即「补量级覆盖」≠「脱离市场硬塞」——用户 2026-11-03 明确要求）
                if not _cands:
                    try:
                        from big_pool_policy import TYPICAL as _TYP
                        for _ts in (_TYP.get(_bin) or []):
                            try:
                                _sup_t, _det_t = _signal_support(_ts)
                            except Exception:
                                continue
                            _ok_t, _rs_t = _wl_gate(_ts, _sup_t)
                            if _ok_t:
                                _cands.append((_sup_t, _ts, None, _det_t))
                            else:
                                _why_rej.append('%s←%s' % (_ts, _rs_t))
                        _cands.sort(key=lambda z: -z[0])
                    except Exception:
                        pass
                for _z in _cands:
                    _ok, _rs = _wl_gate(_z[1], _z[0])
                    if _ok:
                        _picked = _z
                        break
                    _why_rej.append('%s←%s' % (_z[1], _rs))
                if _picked is None:
                    if _why_rej:
                        _p52_rej.append('%d球档空(%s)' % (_bin, '；'.join(_why_rej[:2])))
                    continue
                _w52 = dict(_picked[3]) if isinstance(_picked[3], dict) else {}
                _w52["宽池补入"] = (1.0, "%s 必含 %d 球·过市场信号门槛（不占锚位%s）"
                                    % (_P52_LV, _bin,
                                       "·交集池外典型谱系" if _picked[2] is None else ""))
                score_pool.append({"score": _picked[1], "support": round(_picked[0], 3),
                                   "cs_rank": _cs_rank29.get(_picked[1]), "why": _w52})
                _in_pool.add(str(_picked[1]))
                # 🔴2026-11-03: 留痕必须带**市场信号依据**（方向/净胜/支持度/波胆排名），
                #   否则只写「(N球)」= 看不出凭什么补它 → 用户质疑「硬锚」成立
                try:
                    _ph2, _pa2 = [int(x) for x in str(_picked[1]).split(":")]
                    _mg2 = _ph2 - _pa2
                except (ValueError, TypeError):
                    _mg2 = 0
                _rk2 = _cs_rank29.get(_picked[1])
                _p52_added.append("%s(%d球·%s·净%+d·支%.2f·%s%s)" % (
                    _picked[1], _bin, _score_dir(_picked[1]), _mg2, _picked[0],
                    ('波胆第%d' % _rk2) if _rk2 else '波胆未定价',
                    '·池外谱系' if _picked[2] is None else ''))
            if _p52_added:
                notes.append("🔴P52 宽池补入(过市场信号门槛): %s（%s 必含 %s·只扩入不删除·不占锚位）"
                             % ("/".join(_p52_added), _P52_LV, _P52_REQ))
                notes.append("    门槛口径: 受让场禁主胜 / 市场方向≥45%%时禁反向(允许平局) / "
                             "净胜偏离市场期望>2球拒 / 波胆排名>12拒 / 支持度<峰值30%%拒"
                             " ｜ 本场市场方向: %s(%.0f%%)%s"
                             % (_mkt_dir or '三态', (_mkt_p or 0) * 100,
                                '' if (_mkt_p or 0) >= 0.45
                                else '·均势(方向门槛放宽·双向+平局皆可)'))
            if _p52_rej:
                notes.append("🔴P52 宽池**拒收**(不符合市场信号·不硬塞): %s"
                             % " ｜ ".join(_p52_rej))
        except Exception as _e52b:
            notes.append("⚪P52 宽池补入三态: %s" % _e52b)
    # 🔴P51(2026-10-31): 三源移动相关性（AH/OU/CS）→ 置信度与宽池
    try:
        _tsm_lab, _tsm_adj, _tsm_note = tri_source_move(ah_vert, ou_vert, cs_vert)
        notes.append("🔴P51 三源移动相关性: %s（置信度%+.1f 档）｜ %s"
                     % (_tsm_lab, _tsm_adj, _tsm_note))
    except Exception:
        _tsm_lab, _tsm_adj = "三态", 0.0
    if _tsm_adj <= -0.5:
        wide = True          # 🔴P51-fix 真正消费：三源分裂 → 宽池（此前只 print）
    notes.append("🔴P28 信号支持度评分池(前5): %s ｜ 期望%.2f ｜ %s ｜ 主锚=池内第一(排序结果·非唯一结论)"
                 % (_sup_txt,
                    _E25 if _E25 is not None else 0,
                    ("大球侧" if _big25 else ("小球侧" if _small25 else "中性"))))
    # 兼容下游：top 以支持度分排序后的 (比分, 伪概率) 供旧逻辑消费
    top = [(z[1], z[0]) for z in _scored_raw]
    if _E25 is not None:
        _pen_top = _pen25(top[0][0])
        notes.append("🔴P25 信号约束排序: 期望 %.2f 球 · P(over2.5)=%s · %s ｜ Top1 %s 约束分 %.2f（同档内按矩阵概率/波胆）"
                     % (_E25,
                        ("%.1f%%" % (_pov25 * 100)) if _pov25 is not None else "n/a",
                        ("大球侧" if _big25 else ("小球侧" if _small25 else "中性")),
                        top[0][0], _pen_top))
    if not top:
        return {"anchor_1st": None, "anchor_2nd": None, "trust": "不可信", "double": False,
                "wide": True, "pool_top": [], "notes": notes + ["R10: 无候选"],
                "zero_notes": zero_notes, "big_notes": big_notes, "masked": masked}

    # ---- R10-1 主锚选取（分布·非死锚） ----
    p1 = top[0][1]
    p2 = top[1][1] if len(top) > 1 else 0.0
    # 🔴P46b(2026-10-30 用户指令「以市场信号为准·不硬参考最低赔率和平手盘规矩」):
    #   主锚 = **市场信号支持度第 1**（矩阵 0.30 + 波胆 0.24 主导）
    #   原 top[0][0] 会被后续 P25 约束分 / R12 次锚选择覆盖 → 出现
    #   「P28 池显示 0:2 最高但主锚给 1:2」的自相矛盾（case300 实证）
    # 🔴P46c: 支持度第1**必须限定在传入交集池内**（否则选到池外 → joint_solver 回退
    #   成 _pair_cover_select 的结果 → 出现「anchor_select 给 0:4 但最终锚 1:2」的分裂·case300 实证）
    _pset46 = set(str(x) for x in (pool or []))
    _by_sup = sorted([z for z in _scored_raw if (not _pset46 or str(z[1]) in _pset46)],
                     key=lambda z: (-z[0], _cs_rank29.get(z[1], 999), z[1]))
    if not _by_sup:
        _by_sup = sorted(_scored_raw, key=lambda z: (-z[0], _cs_rank29.get(z[1], 999), z[1]))
    anchor_1st = _by_sup[0][1] if _by_sup else top[0][0]
    # 🔴2026-11-03 O-ANCHOR-1（case319 拉科 2:1 实证·用户裁定「两个都修」）：
    #   **方向首选为主胜/客胜时，主锚不得落在平局谱系**（反之亦然）
    #   原实现纯按支持度取第一 → 首选主胜却锚 1:1（平局）→ 两锚各差一球
    #   → 从支持度序列里取**同方向最高分**作主锚；同方向一个都没有才保持原锚并留痕
    if dir_first in ('主胜', '客胜', '平局') and _by_sup:
        _d1 = _score_dir(anchor_1st)
        if _d1 != dir_first:
            _same = [z for z in _by_sup if _score_dir(z[1]) == dir_first]
            if _same:
                notes.append("O-ANCHOR-1 主锚方向纯: 支持度第一 %s(%s) 与方向首选[%s]不符 → 改取同方向最高 %s"
                             % (anchor_1st, _d1, dir_first, _same[0][1]))
                anchor_1st = _same[0][1]
            else:
                notes.append("O-ANCHOR-1 主锚方向纯: 池内无[%s]谱系候选 → 保持 %s(%s)（须在 raw 说明）"
                             % (dir_first, anchor_1st, _d1))
    anchor_2nd = top[1][0] if len(top) > 1 else None
    double = abs(p1 - p2) < R10_DOUBLE_MAIN_PP
    wide = p1 < R10_WIDE_TOP1
    if double:
        notes.append("R10-1 双主锚（Top1−Top2=%.1fpp<1.5pp·并列不硬拆）" % (100 * abs(p1 - p2)))
    if wide:
        notes.append("R10-1 Top1=%.1f%%<8%% → 宽池低置信（输出 Top4~6·不承诺单锚）" % (100 * p1))

    # ---- R10-2 次锚 = 市场边缘覆盖（T*±1 ∩ M*±1） ----
    t_star = max(range(len(pT)), key=lambda t: pT[t]) if pT else None
    m_star = max(pM, key=lambda m: pM[m]) if pM else None

    # 🔴P10-FINAL R11-6: 四维交集（T 主峰±1 ∩ M 主峰±1 ∩ 主队单队谱系±1 ∩ 客队单队谱系±1）
    #   交集为空 → 先放宽 ±1.5；仍空 → 退回 R10-2 的 ①② 两维（防死锁/防死锚）
    _hs = (_zd_final or {}).get("h_star")
    _as = (_zd_final or {}).get("a_star")

    def _ok4(s, tol=1):
        h, a = [int(x) for x in s.split(":")]
        if t_star is not None and abs((h + a) - t_star) > tol:
            return False
        if m_star is not None and abs((h - a) - m_star) > tol:
            return False
        if _hs is not None and abs(h - _hs) > tol:
            return False
        if _as is not None and abs(a - _as) > tol:
            return False
        return True

    def _ok(s):
        h, a = [int(x) for x in s.split(":")]
        r = True
        if t_star is not None:
            r = r and abs((h + a) - t_star) <= 1
        if m_star is not None:
            r = r and abs((h - a) - m_star) <= 1
        if _hs is not None or _as is not None:
            r = r and _ok4(s, 1)
        return r

    if anchor_2nd and (not _ok(anchor_2nd) or anchor_2nd == anchor_1st):
        c2 = [s for s, _ in top if _ok(s) and s != anchor_1st]
        if c2:
            anchor_2nd = c2[0]
            notes.append("R10-2 次锚改取市场边缘交集（T*%s±1 ∩ M*%s±1）" % (t_star, m_star))
        else:
            anchor_2nd = None
            notes.append("R10-2 无次锚满足边缘交集 → 次锚置空（宽池）")
    # 🔴P47(2026-10-31 用户指正): 次锚须与主锚形成「量级上沿跨度」
    #   数据驱动·**不硬限主锚**（用户: 主锚不许设限定）:
    #     次锚总进球 ≥ max(主锚+1, round(均衡线))
    #   目的: 主锚保命中(低位)，次锚覆盖市场指向的上沿（"开 3.43 至少该想到 4/5 球"）
    if _line_eq is not None and _line_eq >= 2.6 and anchor_1st:
        try:
            _a1t = sum(int(x) for x in str(anchor_1st).split(":"))
            # 🔴P52-fix③: 跨度改由 **big_pool_policy.span_requirement 单一源**（消除双副本）
            #   旧实现硬编码 `max(a1+1, round(line))` → 改分级对锚零影响（实测确认）
            #   L5 → max(a1+2, round(line)+1) ｜ L4 → max(a1+1, round(line)) ｜ L3 → max(a1+1, round(line)−1)
            try:
                import big_pool_policy as _BPP52s
                _need2 = _BPP52s.span_requirement(_line_eq, _P52_LV, _a1t)
                _P52_SPAN = _need2
            except Exception:
                _need2 = max(_a1t + 1, int(round(_line_eq)))
            if not _need2:
                _need2 = max(_a1t + 1, int(round(_line_eq)))
            _a2t = sum(int(x) for x in str(anchor_2nd).split(":")) if anchor_2nd else None
            if (_a2t is None) or (_a2t < _need2):
                _cand7 = [z for z in _scored_raw
                          if ((not _pset46) or str(z[1]) in _pset46)
                          and sum(int(x) for x in str(z[1]).split(":")) >= _need2]
                if _cand7:
                    _old2 = anchor_2nd
                    anchor_2nd = _cand7[0][1]
                    notes.append("🔴P52 次锚跨度(%s): %s → %s（均衡线%.2f·须≥%d球·主锚%d球·支持度%.3f）"
                                 % (_P52_LV, _old2 or "空", anchor_2nd, _line_eq, _need2, _a1t, _cand7[0][0]))
                else:
                    notes.append("🔴P52 次锚跨度(%s): 池内无 ≥%d 球候选 → 次锚保持 %s（宽池补足·非死锚）"
                                 % (_P52_LV, _need2, anchor_2nd))
        except Exception:
            pass
    if not _ok(anchor_1st):
        notes.append("R10-2 ⚠️主锚不在 T*%s±1 ∩ M*%s±1 内 → 弱对齐（仅标注·不硬改）"
                     % (t_star, m_star))

    # ---- R10-3 零封判定（🔴P10-FINAL: 直盘权威 → 本规则**降级为回退路径**） ----
    #   方案 §6.3 接线1: TT under0.5 + BTTS 直盘可用 → 一律走 R11-1/R11-4；本规则不产谱系（仅留痕对比）
    #   原因: 矩阵后验（波胆反推）是截断分布，会把零封概率压扁 ≈1.9-2.0 倍（阿森纳场 48%→7.7%）
    p_a_zero = sum(mat.get("%d:0" % h, 0.0) for h in range(n))     # 客队零封 → 主队零封谱系
    p_h_zero = sum(mat.get("0:%d" % a, 0.0) for a in range(n))     # 主队零封 → 客队零封谱系
    bt_p = None
    if bt_yes and bt_no and 1 < float(bt_yes) < 100 and 1 < float(bt_no) < 100:
        bt_p, _ = _devig_2way(float(bt_yes), float(bt_no))
    _zd_ok = bool(isinstance(_zd_final, dict) and _zd_final.get("health") in ("ok", "weak")
                  and (_zd_final.get("home_clean") is not None
                       or _zd_final.get("away_clean") is not None))
    if _zd_ok:
        zero_notes.append(
            "R10-3 ⚪已降级（R11 直盘权威接管）: 主被零封 %s / 客被零封 %s / BTTS %s ｜ 矩阵后验参考 主%.0f%%/客%.0f%%（截断压扁·不作判定）"
            % (("%.0f%%" % (100 * _zd_final["home_clean"])) if _zd_final.get("home_clean") is not None else "缺",
               ("%.0f%%" % (100 * _zd_final["away_clean"])) if _zd_final.get("away_clean") is not None else "缺",
               ("%.0f%%" % (100 * _zd_final["btts"])) if _zd_final.get("btts") is not None else "缺",
               100 * p_a_zero, 100 * p_h_zero))
    else:
        zero_notes.append("R10-3 ⚠️直盘缺失 → 走**矩阵后验回退路径**（截断分布会把零封压扁≈2 倍·仅回退用）")
        if p_a_zero >= R10_ZERO_P:
            zero_notes.append("R10-3 客队零封 %.0f%%≥30%% → 主队零封谱系优先（2:0/1:0/3:0 升权·2:1 降权）"
                              % (100 * p_a_zero))
        if p_h_zero >= R10_ZERO_P:
            zero_notes.append("R10-3 主队零封 %.0f%%≥30%% → 客队零封谱系优先（0:2/0:1/0:3）"
                              % (100 * p_h_zero))
        if bt_p is not None:
            if bt_p >= R10_BTTS_YES_HI:
                zero_notes.append("R10-3 BTTS yes %.0f%%≥62%% → 双方进球谱系优先（零封若在 Top5 保留兜底）"
                                  % (100 * bt_p))
            elif bt_p <= R10_BTTS_YES_LO:
                zero_notes.append("R10-3 BTTS yes %.0f%%≤42%% → 零封谱系强化" % (100 * bt_p))
        if not (p_a_zero >= R10_ZERO_P or p_h_zero >= R10_ZERO_P):
            zero_notes.append("R10-3 零封 %.0f%%/%.0f%% 均在 15-30%% 中性带 → 按矩阵原序（防过度修正）"
                              % (100 * p_a_zero, 100 * p_h_zero))

    # ---- R10-4 大球锚定（治「不敢锚大球」） ----
    p_t4 = sum(pT[4:]) if (pT and len(pT) > 4) else 0.0
    if p_t4 >= R10_BIG4_EXTREME:
        big_notes.append("R10-4 P(T≥4)=%.0f%%≥35%% 极端大球 → 宽池 1~6 球·主锚大球谱系·可信度降级"
                         % (100 * p_t4))
    elif p_t4 >= R10_BIG4_MID:
        big_notes.append("R10-4 P(T≥4)=%.0f%%≥18%% → 主锚候选须含 3+ 球（4:1/3:2/4:0/3:1）·次锚低分兜底"
                         % (100 * p_t4))
    # 🔴R10-4 上调前置条件（方案原文）: Top1 低总分 **且 T 边缘主峰在大球档(t*≥3)**
    #   缺此条件 → 只要 P(T≥4)≥18% 就把 2:0/1:1 硬换成 3+ 球 = 过度修正（合成用例实测）
    if p_t4 >= R10_BIG4_MID and (t_star is not None and t_star >= 3):
        _h1, _a1 = [int(x) for x in anchor_1st.split(":")]
        if (_h1 + _a1) <= 2:
            _cands = [s for s, _ in top
                      if sum(int(x) for x in s.split(":")) >= max(3, (t_star or 3))]
            if _cands:
                _old = anchor_1st
                anchor_1st = _cands[0]
                if anchor_2nd == anchor_1st:
                    anchor_2nd = next((s for s, _ in top if s != anchor_1st), None)
                big_notes.append("R10-4 主锚 %s(总分%d) 与 P(T≥4)=%.0f%% 冲突 → 以 T 边缘为准上调为 %s"
                                 % (_old, _h1 + _a1, 100 * p_t4, anchor_1st))

    # 🔴V3.5.90 O-TAIL 厚尾覆盖（评审修复·观察期标注级·2026-11-03）
    #   厚尾场锚必须覆盖尾部档：t_band.tail.flag ∈ {厚尾, 强厚尾} 时，
    #   主锚**或**次锚必须有一个落在 ≥5 球谱系（4:1/4:2/3:2/5:1/2:4/3:3…）
    #   —— 真实打出 5-6 球时双锚是「命中」而非「预测错」（概率声明式输出）
    #   原理：波胆尾部定价 + 全档 P(≥5) + 让球净胜交叉（三线在 magnitude_band.tail_signal 合成）
    # 🔴V3.5.90 观察期: 与 joint_solver._TAIL_ACT 联动——False 时只打印标注不改锚
    try:
        _tail_act = False
        try:
            from joint_solver import _TAIL_ACT
            _tail_act = _TAIL_ACT
        except Exception:
            _tail_act = False
        _tail_sig = (t_band or {}).get('tail') or {}
        _tail_flag = _tail_sig.get('flag')
        if _tail_flag in ('厚尾', '强厚尾') and anchor_1st:
            _a1t5 = sum(int(x) for x in anchor_1st.split(":"))
            _a2t5 = sum(int(x) for x in anchor_2nd.split(":")) if anchor_2nd else 0
            if _a1t5 >= 5 or _a2t5 >= 5:
                big_notes.append("O-TAIL 厚尾(%s) 锚已覆盖 ≥5球谱系: 主%s球/次%s球"
                                 % (_tail_flag, _a1t5, _a2t5))
            elif _tail_act:
                # 从高分序列取 ≥5 球谱系最高支持度者 → 覆盖次锚（主锚保命中·次锚保尾部）
                _tail_cands = [z for z in _by_sup
                               if (not _pset46 or str(z[1]) in _pset46)
                               and sum(int(x) for x in str(z[1]).split(":")) >= 5
                               and str(z[1]) != anchor_1st]
                if not _tail_cands:
                    _tail_cands = [z for z in top
                                   if sum(int(x) for x in str(z[1]).split(":")) >= 5
                                   and str(z[1]) != anchor_1st]
                if _tail_cands:
                    _old2 = anchor_2nd
                    anchor_2nd = _tail_cands[0][1]
                    big_notes.append("O-TAIL 厚尾(%s·P≥5=%.0f%%) 次锚 %s 未覆盖尾部 → 改取 %s（≥5球谱系·主锚保命中）"
                                     % (_tail_flag,
                                        (_tail_sig.get('p5_ge') or 0) * 100,
                                        _old2, anchor_2nd))
                else:
                    big_notes.append("O-TAIL 厚尾(%s) 但交集池无 ≥5球谱系 → 保持双锚（宽池兜底·留痕）"
                                     % _tail_flag)
            else:
                big_notes.append("O-TAIL 厚尾标注(V3.5.90观察期): %s 锚未覆盖 ≥5球谱系"
                                 "（主%s球/次%s球·_TAIL_ACT=False 不动作·观察 ≥20 场）"
                                 % (_tail_flag, _a1t5, _a2t5))
    except Exception as _eTAIL:
        big_notes.append("O-TAIL 厚尾覆盖三态: %s" % type(_eTAIL).__name__)

    # ---- R10-6 深盘 / 极端场（承接锚可信度分级） ----
    deep = handi is not None and abs(float(handi)) >= R10_DEEP_HANDI
    extrem = lam is not None and float(lam) >= R10_DEEP_LAM
    trust = "可信"
    if deep or extrem:
        trust = "不可信"
        notes.append("R10-6 %s → 宽池 Top5~8·主锚降级"
                     % ("深盘 |handi|≥1.5" if deep else "极端大球 λ≥3.4"))
        if deep and p_t4 >= R10_BIG4_MID:
            _has3 = any((int(s.split(":")[0]) - int(s.split(":")[1])) >= 3 for s, _ in top[:5])
            if not _has3:
                notes.append("R10-6 深盘+大球强 → Top5 须注入净胜≥3 出口（3:0/4:0/4:1）")

    # ---- R10-7 一致性分级（分布离散度量化·替代「只数仲裁次数」） ----
    top3 = sum(p for _, p in top[:3])
    if p1 >= R10_CONC_HI[0] and top3 >= R10_CONC_HI[1]:
        _conc = "高集中"
    elif p1 < R10_CONC_LO[0] or top3 < R10_CONC_LO[1]:
        _conc = "离散"
    else:
        _conc = "中"
    if _conc == "高集中":
        trust = "可信" if trust == "可信" else trust
    elif _conc == "离散":
        trust = "不可信"
        notes.append("R10-7 分布离散（Top1=%.1f%% 前3=%.0f%%）→ 宽池" % (100 * p1, 100 * top3))
    else:
        if trust == "可信":
            trust = "弱"
        notes.append("R10-7 中集中（Top1=%.1f%% 前3=%.0f%%）→ 可信度弱" % (100 * p1, 100 * top3))
    # 🔴P51-fix(2026-10-31 用户指正「光说没用·要用到模型」): 三源移动相关性进入 trust
    #   三源分裂 −0.5 档 → trust 降一档；三源共振 +0.5 档 → 弱→可信（上限「可信」）
    try:
        if _tsm_adj <= -0.5:
            _tp = trust
            trust = {"可信": "弱", "弱": "不可信"}.get(trust, "不可信")
            notes.append("🔴P51 三源分裂 → trust %s→%s（宽池·只调置信度不反转方向）" % (_tp, trust))
        elif _tsm_adj >= 0.5 and trust == "弱":
            trust = "可信"
            notes.append("🔴P51 三源共振 → trust 弱→可信（行业同步调整）")
    except Exception:
        pass

    # ---- R10-8 方向一致性（锚方向须 ∈ 1x2 主导方向或含兜底） ----
    if oh and od and oa:
        ph, pd, pa = _devig_3way(oh, od, oa)
        if ph is not None:
            dom = max((("主胜", ph), ("平局", pd), ("客胜", pa)), key=lambda t: t[1])
            d1 = _score_dir(anchor_1st)
            if dom[1] >= R10_DIR_DOM and d1 != dom[0]:
                _c8 = [s for s, _ in top if _score_dir(s) == dom[0] and _ok(s)]
                if not _c8:
                    _c8 = [s for s, _ in top if _score_dir(s) == dom[0]]
                if _c8:
                    _old = anchor_1st
                    anchor_1st = _c8[0]
                    if anchor_2nd == anchor_1st:
                        anchor_2nd = next((s for s, _ in top if s != anchor_1st), None)
                    notes.append("R10-8 方向修正（1x2 主导 %s %.0f%%：%s → %s·平局兜底保留）"
                                 % (dom[0], 100 * dom[1], _old, anchor_1st))

    # ---- R10-9 低波胆覆盖降档（🔴读 cs_full·非 matrix["covered"]） ----
    cs_map = {}
    if isinstance(cs_full, dict):
        for k, v in cs_full.items():
            try:
                if 1 < float(v) < 100:
                    cs_map[str(k).replace("-", ":")] = float(v)
            except (TypeError, ValueError):
                continue
    unpriced = [s for s in (anchor_1st, anchor_2nd) if s and cs_map and s not in cs_map]
    if unpriced:
        notes.append("R10-9 %s 波胆未定价 → 置信降一档" % "/".join(unpriced))
        if trust == "可信":
            trust = "弱"

    pool_top = ["%s:%.1f%%" % (s, 100 * p) for s, p in top[:6]]
    # 🔴P28: 比分池 + 主锚支持度明细（主锚=池内第一·非唯一结论）
    _a1_sup = next((x for x in score_pool if x["score"] == anchor_1st), None)
    return {"score_pool": score_pool, "anchor_1st_support": _a1_sup,
            "anchor_1st": anchor_1st, "anchor_2nd": anchor_2nd, "trust": trust,
            "double": double, "wide": wide, "pool_top": pool_top,
            "zero_notes": zero_notes, "big_notes": big_notes,
            "masked": masked, "notes": notes}


# ============================================================================
# 5.6 单队进球 / 零封判定器（方案 §6·R11-0~R11-9）—— 回答「双方会不会进球」
# ============================================================================
# 🔴数据源（快照里全都有·此前未消费）: TeamTotal 主/客各 10 档（0.5 档 under = 该队被零封的**直盘**）
#   + BTTS（yes/no 直盘） + 波胆 0 行/0 列（交叉验证·截断校正）
# 🔴核心价值: 直盘是机构为「零封/双方进球」单独开的盘，权威度高于任何反推——
#   矩阵后验（波胆反推）是截断分布，会把零封概率压扁 ≈1.9-2.0 倍（"2:0 老判成 2:1"的根因之一）。
# 🔴全部阈值【待回测校准】·禁单场固化。
R11_STRONG_CLEAN = 0.40        # R11-4 强谱系：任一队被零封 ≥40%
R11_WEAK_CLEAN = 0.30          # R11-4 弱谱系：30~40%
R11_BTTS_HI = 0.60             # 双方进球为主（BTTS yes ≥60%）
R11_BTTS_LO = 0.42             # 零封为主（BTTS yes ≤42%）
R11_RHO = 0.03                 # R11-3 相关性显著阈：|rho| ≥ 3pp
R11_CS_DIVERGE = 0.10          # R11-7 波胆 vs 直盘分歧阈（10pp）


def _pmf_from_tt(tt_dict, max_k=7):
    """单队 Team Total 半档差分 → PMF（R11-5·形状参考）"""
    tt_dict = tt_dict or {}
    half = sorted([ln for ln in tt_dict.keys() if _is_half(ln)])
    surv = {}
    for ln in half:
        try:
            over, under = tt_dict[ln]
        except (TypeError, ValueError):
            continue
        p_over, _pu = _devig_2way(over, under)
        if p_over is not None:
            surv[int(math.floor(float(ln))) + 1] = p_over
    if len(surv) < 2:
        return None
    ks = sorted(surv.keys())
    p = [0.0] * (max_k + 1)
    p[0] = max(0.0, 1.0 - surv[ks[0]])
    for i, k in enumerate(ks):
        if i == 0:
            continue
        p[min(k - 1, max_k)] += max(0.0, surv[ks[i - 1]] - surv[k])
    p[max_k] += max(0.0, surv[ks[-1]])
    s = sum(p)
    return [round(v / s, 4) for v in p] if s > 0 else None


# ══════════════ R12 次锚终选器（P11·2026-10-26·用户指令「两锚任一命中·机制保证分散」）══════════════
# 🔴 为什么需要 R12（实测断点·已逐行核实）:
#    `joint_solver._pair_cover_select` 在 L988 先算出多样性双锚，但随后
#      · L1042-1045  `if _R1: a1=_R1; if _R2: a2=_R2`      → **R10 无条件覆盖**
#      · L1090-1094  `if _cand11 and a2 not in _cand11: a2=_cand11[0]` → **R11 硬替换**
#    → 矩阵启用（主流路径）时 pair_cover **只留痕、不决定最终双锚**（存在≠活跃）
#    → 且其概率源是波胆去水 cs_probs（零封被截断压扁约 1.9-2.0 倍），非矩阵后验
# 🔴 R12 定位: **R10 只定主锚 a1（不动）；R12 用矩阵后验在交集池内定次锚 a2**
#    多样性奖励**数据驱动**（接 1x2 方向分散度 + R11 直盘谱系），非固定常数 → 防过拟合
# 🔴 全部系数【待回测校准】·灰度开关 `p10_config.json: r12_pair_cover`（off/auto/on）
R12_W_DIR = 0.020         # 跨方向奖励上限（方向分散时拉满）
R12_W_SPEC = 0.014        # 跨谱系奖励（零封 ↔ BTTS）
R12_W_MARGIN = 0.009      # 同方向·净胜档分离（赢1球 vs 赢2球）
R12_W_BAG = 0.008         # 总进球袋分离（≤1/2/3/≥4）
R12_PEN_EQUIV = 0.030     # 同方向且同净胜档（近等价比分）强惩罚
R12_FLOOR_RATIO = 0.35    # 次锚质量地板 = max(0.05, ratio × P(a1))
R12_FLOOR_ABS = 0.05
R12_DIR_CLEAR = 0.55      # 主导方向 ≥55% = 方向明确（不鼓励跨方向）
R12_DIR_SPLIT = 0.42      # 主导方向 <42% = 方向分散（跨方向拉满）


def _r12_spec(h, a):
    """比分谱系标签：zero_home(客队0球=主队零封) / zero_away(主队0球) / zero00 / btts"""
    if a == 0 and h > 0:
        return "zero_home"
    if h == 0 and a > 0:
        return "zero_away"
    if h == 0 and a == 0:
        return "zero00"
    return "btts"


def _r12_bag(t):
    return 0 if t <= 1 else (1 if t == 2 else (2 if t == 3 else 3))


def _r12_dir(h, a):
    return "主胜" if h > a else ("平局" if h == a else "客胜")


def r12_second_anchor(mm, a1, x12=None, r11=None, pool=None):
    """固定主锚 a1，在池内枚举次锚 → 最大化【联合覆盖 = P(a1)+P(a2) + 自适应多样性奖励】。

    返回 dict:
      a2        次锚（None = 无合格候选 → 宽池·不硬凑）
      joint     纯概率联合覆盖 P(a1)+P(a2)（核心置信度·不含奖励）
      score     决策分（含奖励·仅用于选择）
      mode      覆盖模式（邻域 / 跨方向 / 跨谱系 / 跨量级，可多选）
      qdir      1x2 主导方向概率（方向分散度代理）
      w_dir/w_spec  本次自适应权重（留痕·可审计）
      candidates Top3 候选[(比分, 决策分, 纯概率, 标签)]
    """
    raw_m = (((mm or {}).get("matrix") or {}).get("matrix")) or {}
    Pm = {"%d:%d" % (h, a): float(p) for (h, a), p in raw_m.items()}
    if not Pm or not a1 or a1 not in Pm:
        return {"a2": None, "mode": "无矩阵/无主锚", "candidates": [], "joint": None}

    # ① x12：矩阵边缘求和（infer_from_parts 不产出 → 自洽推导）
    if not x12:
        ph = pd_ = pa = 0.0
        for k, v in Pm.items():
            h, a = map(int, k.split(":"))
            if h > a:
                ph += v
            elif h == a:
                pd_ += v
            else:
                pa += v
        _tt = (ph + pd_ + pa) or 1.0
        x12 = {"pH": ph / _tt, "pD": pd_ / _tt, "pA": pa / _tt}   # 🔴归一（构造/非IPF矩阵也安全）

    h1, g1 = map(int, a1.split(":"))
    d1, m1, t1, sp1 = _r12_dir(h1, g1), h1 - g1, h1 + g1, _r12_spec(h1, g1)
    p1 = Pm.get(a1, 0.0)

    # ② 方向互补系数（数据驱动·非固定）
    probs = [q for q in (x12.get("pH"), x12.get("pD"), x12.get("pA")) if q is not None]
    qdir = max(probs) if probs else None
    if qdir is None:
        w_dir = R12_W_DIR * 0.5
    elif qdir >= R12_DIR_CLEAR:
        w_dir = 0.0                                     # 方向明确 → 不鼓励跨方向
    elif qdir <= R12_DIR_SPLIT:
        w_dir = R12_W_DIR                               # 方向分散 → 跨方向拉满
    else:
        w_dir = R12_W_DIR * (R12_DIR_CLEAR - qdir) / (R12_DIR_CLEAR - R12_DIR_SPLIT)

    # ③ 谱系互补系数（R11 直盘驱动）
    r11 = r11 or {}
    sc = r11.get("spectrum_code") or "indep"
    btts_v = r11.get("btts")
    hc, ac = r11.get("home_clean"), r11.get("away_clean")
    dual = (btts_v is not None and btts_v >= 0.55 and
            ((hc is not None and hc >= 0.30) or (ac is not None and ac >= 0.30)))
    spec_strong = sc in ("strong_home_clean", "strong_away_clean", "btts")
    w_spec = R12_W_SPEC if (spec_strong or dual) else R12_W_SPEC * 0.5

    seq = [x for x in (pool or sorted(Pm, key=lambda k: -Pm[k])) if x != a1 and x in Pm]
    floor = max(R12_FLOOR_ABS, R12_FLOOR_RATIO * p1)

    rows = []
    for sc2 in seq:
        h, a = map(int, sc2.split(":"))
        base = Pm.get(sc2, 0.0)
        d2, m2, t2, sp2 = _r12_dir(h, a), h - a, h + a, _r12_spec(h, a)
        bon = 0.0
        tags = []
        if d2 != d1:
            bon += w_dir
            if w_dir > 0:
                tags.append("跨方向")
        else:
            if m2 != m1:
                bon += R12_W_MARGIN
                tags.append("跨净胜")
        if sp2 != sp1 and ("zero" in sp1) != ("zero" in sp2):
            bon += w_spec
            tags.append("跨谱系")
        if _r12_bag(t2) != _r12_bag(t1):
            bon += R12_W_BAG
            tags.append("跨量级")
        if d2 == d1 and m2 == m1:
            bon -= R12_PEN_EQUIV                     # 近等价（同方向同净胜档）
        rows.append((base + bon, sc2, base, bon, tags))

    rows.sort(key=lambda r: -r[0])
    elig = [r for r in rows if r[2] >= floor]
    cands = [(r[1], round(r[0], 4), round(r[2], 4), r[4]) for r in rows[:3]]
    if not elig:
        return {"a2": None, "mode": "无合格次锚(全低于质量地板)→宽池", "joint": round(p1, 4),
                "p1": round(p1, 4), "qdir": round(qdir, 3) if qdir else None,
                "w_dir": round(w_dir, 4), "w_spec": round(w_spec, 4), "candidates": cands}

    _, a2, p2, bon, tags = elig[0]
    return {"a2": a2, "joint": round(p1 + p2, 4), "p1": round(p1, 4), "p2": round(p2, 4),
            "score": round(p1 + p2 + bon, 4), "bonus": round(bon, 4),
            "mode": "/".join(tags) if tags else "邻域(同方向同谱系)",
            "qdir": round(qdir, 3) if qdir else None,
            "w_dir": round(w_dir, 4), "w_spec": round(w_spec, 4), "candidates": cands}


def team_zero_decision(tt_full=None, btts=None, cs_full=None,
                       tt_h_row=None, tt_a_row=None, handi=None):
    """R11 单队进球/零封判定（方案 §6）

    输入:
      tt_full : {"home": {line:(over,under)}, "away": {...}}  ← snapshot_save._tt_full（首选·直盘）
      btts    : {"yes": odds, "no": odds}                     ← BTTS 直盘
      cs_full : {"H-A": odds}                                 ← 波胆（交叉验证·不推翻直盘）
      tt_h_row/tt_a_row : P(主进k球) 列表（直盘缺失时的**回退**路径·p[0]=被零封）
      handi   : 让球（仅留痕）
    返回:
      {ok, source, health, home_clean, away_clean, btts, at_least_one_clean, indep, rho,
       spectrum, spectrum_code, pmf_h, pmf_a, h_star, a_star, cs_check, notes}
    """
    notes = []
    tt_full = tt_full or {}
    hh = tt_full.get("home") or {}
    aa = tt_full.get("away") or {}
    src = []

    def _tt_clean(d):
        """0.5 档二向去水 → (P(≥1), P(被零封))；无该档 → (None, None)"""
        try:
            over, under = d[0.5]
        except (KeyError, TypeError, ValueError):
            return None, None
        return _devig_2way(over, under)

    ph1, ph0 = _tt_clean(hh)
    pa1, pa0 = _tt_clean(aa)
    if ph0 is not None:
        src.append("直盘TT主")
    if pa0 is not None:
        src.append("直盘TT客")
    # 回退：单队行边缘 p[0] = P(进0球) = P(被零封)
    if ph0 is None and tt_h_row:
        try:
            ph0 = float(tt_h_row[0])
            ph1 = 1.0 - ph0
            src.append("行边缘主")
        except (IndexError, TypeError, ValueError):
            pass
    if pa0 is None and tt_a_row:
        try:
            pa0 = float(tt_a_row[0])
            pa1 = 1.0 - pa0
            src.append("行边缘客")
        except (IndexError, TypeError, ValueError):
            pass

    pbt = pnb = None
    if isinstance(btts, dict):
        by, bn = btts.get("yes"), btts.get("no")
        if by and bn and 1 < float(by) < 100 and 1 < float(bn) < 100:
            pbt, pnb = _devig_2way(float(by), float(bn))
            if pbt is not None:
                src.append("直盘BTTS")

    # R11-3 相关性信号 rho = P(BTTS) − P(主≥1)·P(客≥1)
    indep = (ph1 * pa1) if (ph1 is not None and pa1 is not None) else None
    rho = (pbt - indep) if (pbt is not None and indep is not None) else None

    # R11-5 单队 PMF（形状参考）+ 主峰
    pmf_h = _pmf_from_tt(hh)
    pmf_a = _pmf_from_tt(aa)
    h_star = max(range(len(pmf_h)), key=lambda i: pmf_h[i]) if pmf_h else None
    a_star = max(range(len(pmf_a)), key=lambda i: pmf_a[i]) if pmf_a else None

    # R11-4 谱系（优先级：强零封 > BTTS 绝对值 > 弱零封 > rho > 独立）
    spectrum, code = "独立（无谱系倾斜）", "indep"
    if pa0 is not None and pa0 >= R11_STRONG_CLEAN:
        code = "strong_away_clean"
        spectrum = "强谱系: 客被零封%.0f%% → 主队零封比分优先(2:0/1:0/3:0)" % (100 * pa0)
    elif ph0 is not None and ph0 >= R11_STRONG_CLEAN:
        code = "strong_home_clean"
        spectrum = "强谱系: 主被零封%.0f%% → 客队零封比分优先(0:2/0:1/0:3)" % (100 * ph0)
    elif pbt is not None and pbt >= R11_BTTS_HI:
        code = "btts"
        spectrum = "双方进球为主(BTTS %.0f%%) → 1:1/2:1/1:2/2:2 优先" % (100 * pbt)
        if (pa0 is not None and pa0 >= R11_WEAK_CLEAN) or (ph0 is not None and ph0 >= R11_WEAK_CLEAN):
            spectrum += "；零封弱谱系并存（2:0/3:0 作候选·不挤掉 BTTS 比分）"
    elif pbt is not None and pbt <= R11_BTTS_LO:
        code = "clean"
        spectrum = "零封为主(BTTS %.0f%%) → 零封比分优先" % (100 * pbt)
    elif pa0 is not None and pa0 >= R11_WEAK_CLEAN:
        code = "weak_away_clean"
        spectrum = "弱谱系: 客被零封%.0f%% → 零封比分进候选前列（不强制挤掉 BTTS 比分）" % (100 * pa0)
    elif ph0 is not None and ph0 >= R11_WEAK_CLEAN:
        code = "weak_home_clean"
        spectrum = "弱谱系: 主被零封%.0f%% → 客队零封比分进候选前列" % (100 * ph0)
    if code == "indep" and rho is not None:
        if rho >= R11_RHO:
            code = "counter"
            spectrum = "对攻正相关(rho=%+.1fpp) → 双方进球谱系强化" % (100 * rho)
        elif rho <= -R11_RHO:
            code = "edge"
            spectrum = "单边负相关(rho=%+.1fpp) → 零封谱系强化" % (100 * rho)

    # R11-7 波胆交叉验证（截断校正·只留痕不推翻）
    cs_check = None
    if isinstance(cs_full, dict) and cs_full:
        inv = {}
        for k, v in cs_full.items():
            try:
                s0 = str(k).replace(":", "-").replace("/", "-")
                h, a = int(s0.split("-")[0]), int(s0.split("-")[1])
                fv = float(v)
            except (TypeError, ValueError, IndexError):
                continue
            if 1 < fv < 100:
                inv[(h, a)] = 1.0 / fv
        tot = sum(inv.values())
        if tot > 0:
            c_h0 = sum(v for (h, a), v in inv.items() if h == 0) / tot
            c_a0 = sum(v for (h, a), v in inv.items() if a == 0) / tot
            k_h = (ph0 / c_h0) if (ph0 and c_h0 > 0) else None
            k_a = (pa0 / c_a0) if (pa0 and c_a0 > 0) else None
            diverge = False
            if ph0 is not None and abs(c_h0 - ph0) > R11_CS_DIVERGE:
                diverge = True
            if pa0 is not None and abs(c_a0 - pa0) > R11_CS_DIVERGE:
                diverge = True
            cs_check = {"h0": round(c_h0, 3), "a0": round(c_a0, 3),
                        "k_h": (round(k_h, 1) if k_h else None),
                        "k_a": (round(k_a, 1) if k_a else None),
                        "diverge": diverge}
            notes.append("R11-7 波胆0行/0列=%.0f%%/%.0f%%（截断校正 k≈%s/%s）→ %s"
                         % (100 * c_h0, 100 * c_a0,
                            ("%.1f" % k_h) if k_h else "缺", ("%.1f" % k_a) if k_a else "缺",
                            "⚠️与直盘分歧>10pp·以直盘为准" if diverge else "✅与直盘一致（以直盘为准）"))

    # 三态
    direct_n = sum(1 for s in src if s.startswith("直盘"))
    if direct_n == 0 and ph0 is None and pa0 is None:
        health = "none"
        notes.append("⚪R11 直盘与行边缘均缺失（TT 0.5 档无 / 行边缘无）→ 回退 R10-3 矩阵后验")
    elif direct_n >= 2:
        health = "ok"
    else:
        health = "weak"
        notes.append("⚠️R11 部分直盘缺失（来源=%s）→ 谱系可信度降级" % ("/".join(src) or "无"))

    if pnb is not None and ph0 is not None and pa0 is not None:
        notes.append("R11-2 自洽: 至少一方零封 %.0f%% ≈ 主被零封 %.0f%% + 客被零封 %.0f%% − 双零封"
                     % (100 * pnb, 100 * ph0, 100 * pa0))
    notes.append("R11-4 输入: 主被零封%s 客被零封%s BTTS=%s rho=%s → %s"
                 % ("%.0f%%" % (100 * ph0) if ph0 is not None else "缺",
                    "%.0f%%" % (100 * pa0) if pa0 is not None else "缺",
                    "%.0f%%" % (100 * pbt) if pbt is not None else "缺",
                    "%+.1fpp" % (100 * rho) if rho is not None else "缺", spectrum))

    return {"ok": health in ("ok", "weak"), "health": health, "source": "/".join(src) or "无",
            "home_clean": ph0, "away_clean": pa0, "btts": pbt,
            "at_least_one_clean": pnb, "indep": indep, "rho": rho,
            "spectrum": spectrum, "spectrum_code": code,
            "pmf_h": pmf_h, "pmf_a": pmf_a, "h_star": h_star, "a_star": a_star,
            "cs_check": cs_check, "handi": handi, "notes": notes}


def fmt_r11_line(z):
    """R11 一行式留痕（三态）"""
    if not isinstance(z, dict) or z.get("health") == "none":
        return "⚪R11 零封判定未启用（直盘缺失 → 回退 R10-3 矩阵后验）"
    _f = lambda v: ("%.0f%%" % (100 * v)) if v is not None else "缺"
    return ("🔴R11 零封(直盘·%s): 主被零封 %s / 客被零封 %s / BTTS %s / rho %s → %s"
            % (z.get("source") or "-", _f(z.get("home_clean")), _f(z.get("away_clean")),
               _f(z.get("btts")),
               ("%+.1fpp" % (100 * z["rho"])) if z.get("rho") is not None else "缺",
               z.get("spectrum")))


# ============================================================================
# 9. 自测（4 份真实快照·路径动态探测·无硬编码）
# ============================================================================

def _self_test():
    import os
    import json

    _snap = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")
    if not os.path.isdir(_snap):
        print("⚪未找到 snapshots 目录：%s" % _snap)
        return
    cands = sorted([f for f in os.listdir(_snap) if f.endswith(".json")], reverse=True)
    tested = 0
    for fn in cands:
        if tested >= 4:
            break
        fp = os.path.join(_snap, fn)
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        games = [g for g in (d.get("games") or []) if g.get("raw_1xbet")]
        if not games:
            continue
        g = games[0]
        mm = infer_market_matrix(g["raw_1xbet"])
        print("=" * 78)
        print("场: %s vs %s  [%s]" % (g.get("home", "?"), g.get("away", "?"), fn))
        print(fmt_block(mm))
        tested += 1
    print("=" * 78)
    print("自测完成，成功场次: %d" % tested)


if __name__ == "__main__":
    _self_test()
