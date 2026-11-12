# -*- coding: utf-8 -*-
"""量级确定层 magnitude_band.py（V3.5.88 · 2026-11-03 · **分布驱动重写**）

## 为什么重写（2026-11-03 用户质疑「量级把控还是差点意思・是市场不准还是机制有问题」）

诊断三段（`data/tmp/magnitude_diag.py` 可复现）:

**① 市场没错**（案例库 50 场有完整分布）
    市场期望偏差均值 **+0.002 球**（无偏）｜MAE 0.824 ｜ 逐场比我的锚更准 14:11
    🔴 但市场期望的**跨场 σ 只有 0.331、≥4 球占比 0%** → 均值这个坐标天生表达不出「这球多」

**② 旧机制有 3 个系统性问题**
    a. **伪多源**：五源两两相关 **r=0.97~0.99**（λ vs O2.5 反推 0.9936 / 线 vs O2.5 0.9864）
       → 「五路投票」= 同一个数被平均 5 次，信息量零增加
    b. **均值 + 固定 ±1 带宽 → 结构性削掉尾部**
       317 场 O2.5=1.563 → 表实测 P(≥4球)=**36.4%**（4球17%/5球10%/6球5%）
       旧机制 `band_weight` 按「距中心」阶梯降权 **1.0 / 0.55 / 0.25 / 0.10**
       → 5/6/7 球被压到 0.10 倍 = **结构性出局**（真实 2:4 = 6 球）
    c. **E → 众数层二次离散**：分布众数是「4+球」，台账却记「预测层 2 球」

**③ 不可约部分（诚实边界）**：单场 σ≈1.06 → 即使期望完美也有 26% 场次偏 ≥1 球

## 本版改法（用户 2026-11-03 裁定 dec-9e0e0b6dcc2535e8 = **方案 A 分布驱动**）

| 项 | 旧（点+固定带宽） | 新（分布驱动） |
|:--|:--|:--|
| 形状 | 五源加权平均 → 一个点 | 取**最可靠的一条分布** pT[0..7]（矩阵 > 查表 > 泊松） |
| 中心 | `T_star = round(加权均值)` | `T_star` = **分布众数**（仅留痕·不再是硬中心） |
| 区间 | 固定 `±1` 球 | **分位数自适应**：T_lo/T_hi = P20~P80 ｜ wide = P5~P95 |
| 档外权重 | 阶梯 1.0/0.55/0.25/0.10 | **密度比** `w = 0.35 + 0.65 × pT[t]/max(pT)`（不排除·但不虚高） |
| 尾部 | 无 | `tail_bins` = P(k) ≥ **5%** → **必进宽池**（不占锚位） |

**为什么不加权平均分布**：五源 r>0.97 → 混合分布 ≈ 任一单源，只会把方差再压一次（数学必然）。
选「最可靠的单条分布」+ 用其它源做**校验**（三源偏差 >0.35 球 → 标注冲突），信息不被平均抹平。

## 分布来源（按可靠性降序·缺则降级）

| # | 源 | 条件 | 说明 |
|:-:|:--|:--|:--|
| ① | P10 矩阵 `mm['total']['p']` | 有 OU 全档 | IPF 后逐球分布·最权威 |
| ② | `goal_bins_table` 按 O2.5 档 | 有 O2.5 | **148,397 场实测**（只有 4 档 → 泊松比例拆 0-1 与 4+ 内部） |
| ③ | 泊松 λ | 只有 λ | 兜底 |

## 用法

    from magnitude_band import magnitude_band, band_weight
    bd = magnitude_band(mm=mm, p52='L3', o25=1.563, lam=3.5)
    bd['pT']         # [p0..p7] 逐球分布
    bd['tail_bins']  # [2,3,4,5,6] → 宽池必含档
    bd['T_lo'], bd['T_hi']  # 分位数区间（自适应）
    w = band_weight('2:4', bd)   # 密度比（6 球档 ≈ 0.5 左右·不再被压到 0.10）
"""
import os
import sys
import math

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

_D = os.path.dirname(os.path.abspath(__file__))
if _D not in sys.path:
    sys.path.insert(0, _D)

# ── 源权重（**仅用于校验与留痕**·不再用于加权平均定中心）──
W = {'E_T': 0.35, 'P52': 0.25, 'O25': 0.20, 'LAM': 0.15, 'LINE': 0.05}

# ── P52 六档 → 档中心均球（L4/L5 为 148,397 场实测值）──
P52_CENTER = {'L0': 2.35, 'L1': 2.90, 'L2': 3.20, 'L3': 3.40, 'L4': 3.55, 'L5': 4.02}

# ── 尾部进池阈值（P(k) ≥ 该值 → 宽池必含·不占锚位）──
TAIL_P = 0.05

# ── 档外权重下限（最稀档也不低于此·**不排除**）──
W_FLOOR = 0.35

_BINS = None


def _load_bins():
    global _BINS
    if _BINS is not None:
        return _BINS
    try:
        import json, io as _io
        _BINS = json.load(_io.open(os.path.join(_D, 'goal_bins_table.json'), encoding='utf-8'))
    except Exception:
        _BINS = {}
    return _BINS


def _o25_band(o25):
    try:
        v = float(o25)
    except Exception:
        return None
    for lo, hi in ((1.00, 1.30), (1.30, 1.50), (1.50, 1.70), (1.70, 1.90),
                   (1.90, 2.10), (2.10, 2.30), (2.30, 2.60)):
        if lo <= v < hi:
            return '%.2f-%.2f' % (lo, hi)
    if v >= 2.60:
        return '2.60-99.00'
    return '1.00-1.30'


def _o25_expect(o25):
    """O2.5 → 期望总球（复用 live_score_engine·由 148,397 场实测档分布反推）"""
    try:
        from live_score_engine import _o25_expect as _oe
        return float(_oe(o25))
    except Exception:
        try:
            v = float(o25)
        except Exception:
            return None
        return 3.05 if v < 1.75 else (2.70 if v < 2.05 else 2.28)


def _poisson_p(k, lam):
    try:
        lam = float(lam)
        if lam <= 0:
            return 0.0
        return math.exp(-lam) * lam ** k / math.factorial(k)
    except Exception:
        return 0.0


def _norm(p):
    s = sum(p)
    if s <= 0:
        return None
    return [x / s for x in p]


# ══════════ 三条分布源 ══════════

def pts_from_matrix(mm):
    """① P10 矩阵 → 逐球分布（IPF 后·最权威）"""
    p = ((mm or {}).get('total') or {}).get('p')
    if not p:
        return None
    try:
        v = [float(x) for x in p][:8]
        while len(v) < 8:
            v.append(0.0)
        return _norm(v)
    except Exception:
        return None


def pts_from_bins(o25, lam=None):
    """② goal_bins_table（148,397 场实测·仅 4 档）→ 逐球分布

    拆分规则（可审计）：
      · 0-1 球档：按泊松 P(0):P(1) 比例拆
      · 4+ 球档：按泊松 P(4):P(5):P(6):P(7+) 比例拆
    泊松 λ 取：传入 λ → 否则 O2.5 反推期望。
    """
    r = _load_bins().get(_o25_band(o25))
    if not r:
        return None
    try:
        g = [float(r.get(k, 0)) for k in ('g01', 'g2', 'g3', 'g4')]
    except Exception:
        return None
    s = sum(g)
    if s <= 0:
        return None
    g01, g2, g3, g4 = [x / s for x in g]

    L = None
    try:
        L = float(lam) if lam else None
    except Exception:
        L = None
    if not L or L <= 0:
        L = _o25_expect(o25) or 2.70

    p0 = _poisson_p(0, L)
    p1 = _poisson_p(1, L)
    p01_sum = p0 + p1
    f0 = (p0 / p01_sum) if p01_sum > 0 else 0.42

    tail = [_poisson_p(k, L) for k in (4, 5, 6, 7)]
    tail_sum = sum(tail) or 1.0
    t4, t5, t6, t7 = [x / tail_sum for x in tail]

    return _norm([g01 * f0, g01 * (1 - f0), g2, g3, g4 * t4, g4 * t5, g4 * t6, g4 * t7])


def pts_from_poisson(lam):
    """③ 泊松兜底"""
    try:
        L = float(lam)
        if L <= 0:
            return None
    except Exception:
        return None
    return _norm([_poisson_p(k, L) for k in range(8)])


# ══════════ 分位数 ══════════

def quantile(pT, q):
    """离散分布分位数（返回进球数 k·P(T ≤ k) 首次 ≥ q）"""
    acc = 0.0
    for k, p in enumerate(pT):
        acc += p
        if acc >= q - 1e-9:
            return k
    return len(pT) - 1


def fix_tail_monotonic(pT, o25=None, lam=None, tail_from=3):
    """🔴2026-11-03 用户裁定 dec-376e7267d95be6e2（方案 A）：
    **矩阵尾部非单调 → 从拐点起整段回退查表**

    背景（317 萨索洛 2:4 = 6 球实证）:
      · 市场（查表 148,397 场）对 1.50-1.70 档 6 球定价 **6.4%**，历史实际 **5.3%** → 市场准、甚至高估
      · 但矩阵分布给 [.. 6球 **3%** 7球 **9%**] —— **形状不可能**（泊松尾部必须单调递减）
        → 6 球 3% < 5% 阈值 → **6 球档被排除出宽池**（本该覆盖）
      · 根因：CS 波胆「胜其它」合并档，7+ 被并成一格 → 7 球虚高、6 球被压

    规则：从 `tail_from`（默认 3）起检查 P(k) ≥ P(k+1)；首次违反处记为拐点 bad
          → **bad 及其后全部改用查表分布**（前段保持矩阵），再归一
    返回 (pT_new, note)；无违反 → (pT, None)
    """
    try:
        if not pT or len(pT) < 8:
            return pT, None
        bad = None
        for k in range(int(tail_from), len(pT) - 1):
            if float(pT[k]) < float(pT[k + 1]) - 1e-9:
                bad = k
                break
        if bad is None:
            return pT, None
        alt = pts_from_bins(o25, lam)
        if not alt or len(alt) < 8:
            return pT, '尾部非单调(P(%d)<P(%d))·查表不可用→保留原分布' % (bad, bad + 1)
        out = [float(x) for x in pT[:bad]] + [float(x) for x in alt[bad:]]
        s = sum(out)
        if s <= 0:
            return pT, None
        out = [x / s for x in out]
        return out, ('尾部非单调 P(%d)=%.1f%%<P(%d)=%.1f%%（CS「胜其它」合并污染）'
                     '→ %d 球起回退查表尾部（%s）'
                     % (bad, pT[bad] * 100, bad + 1, pT[bad + 1] * 100, bad,
                        '/'.join('%.1f%%' % (x * 100) for x in out[bad:])))
    except Exception:
        return pT, None


def tail_bins(pT, thr=TAIL_P):
    """P(k) ≥ thr 的档（宽池必含·不占锚位）"""
    return [k for k, p in enumerate(pT) if p >= thr - 1e-9]


# ══════════ 主入口 ══════════

def magnitude_band(mm=None, p52=None, o25=None, u25=None, lam=None,
                   line=None, handi=None, cs_full=None):
    """分布驱动定量级档

    返回（🔴 保留旧键 T_star / T_lo / T_hi / band / confidence / src / n_src / spread / notes 以兼容下游）：
      pT        : [p0..p7] 逐球分布（归一）
      pT_src    : '矩阵' / '查表' / '泊松' / None
      p25/p50/p75/p90 : 分位数（球）
      T_lo/T_hi : P20~P80 区间（自适应·替代固定 ±1）
      wide_lo/wide_hi : P5~P95 区间（90% 覆盖·留痕用）
      tail_bins : P(k)≥5% 的档（宽池必含）
      T_star    : 分布**众数**（仅留痕·不再是硬中心）
      T_cont    : 分布均值（留痕·与市场期望对照）
      tail      : 🔴V3.5.90 厚尾判据收敛（唯一判据 premium≥2.0·cs_tail_ratio/p5_ge/p6_ge/margin 留痕）
      notes     : 留痕
    """
    notes, src = [], {}

    # ── ① 取最可靠的一条分布 ──
    pT, pT_src = None, None
    pT = pts_from_matrix(mm)
    if pT:
        pT_src = '矩阵'
    if not pT:
        pT = pts_from_bins(o25, lam)
        if pT:
            pT_src = '查表'
    if not pT:
        pT = pts_from_poisson(lam if lam else _o25_expect(o25))
        if pT:
            pT_src = '泊松'

    # 🔴2026-11-03 用户裁定（方案 A）：矩阵尾部非单调 → 回退查表尾部
    #   实证 317: 矩阵 6球3% < 7球9%（不可能）→ 6 球被 5% 阈值排除，而市场定价 6.4%
    if pT:
        pT, _tail_note = fix_tail_monotonic(pT, o25, lam, tail_from=3)
        if _tail_note:
            notes.append('🔴' + _tail_note)
            if pT_src == '矩阵':
                pT_src = '矩阵+查表尾部'

    # ── ② 各源点值（**仅校验/留痕·不参与定中心**）──
    et = None
    try:
        et = float((mm or {}).get('expT'))
    except Exception:
        et = None
    if et is None:
        p = ((mm or {}).get('total') or {}).get('p')
        if p:
            try:
                et = sum(i * float(x) for i, x in enumerate(p))
            except Exception:
                et = None
    if et is not None and 0.5 <= et <= 7:
        src['E_T'] = round(et, 3)
    eo = _o25_expect(o25) if o25 is not None else None
    if eo is not None and 0.5 <= eo <= 7:
        src['O25_exp'] = round(eo, 3)
    try:
        lv = float(lam)
        if 0.5 <= lv <= 8:
            src['LAM'] = round(lv, 3)
    except Exception:
        pass
    if p52 in P52_CENTER:
        src['P52'] = p52
    try:
        ln = float(line)
        if 1.0 <= ln <= 6:
            src['LINE'] = round(ln, 3)
    except Exception:
        pass
    if o25 is not None and u25 is not None:
        try:
            _o, _u = float(o25), float(u25)
            notes.append('O2.5 去水 p_over=%.3f'
                         % ((1.0 / _o) / ((1.0 / _o) + (1.0 / _u))))
        except Exception:
            pass

    if not pT:
        return {'T_star': None, 'T_lo': None, 'T_hi': None, 'band': '未知',
                'pT': None, 'pT_src': None, 'tail_bins': [],
                'src': src, 'confidence': 'LOW', 'n_src': 0,
                'notes': ['三条分布源全缺 → 无法定量级（三态）']}

    # ── ③ 统计量 ──
    t_cont = sum(k * p for k, p in enumerate(pT))          # 分布均值
    t_mode = max(range(8), key=lambda k: (pT[k], -k))       # 众数（并列取小球·保守）
    p25, p50, p75, p90 = [quantile(pT, q) for q in (0.25, 0.50, 0.75, 0.90)]
    p20, p80 = quantile(pT, 0.20), quantile(pT, 0.80)
    p05, p95 = quantile(pT, 0.05), quantile(pT, 0.95)
    tails = tail_bins(pT)

    # 极差（源间离散·仅留痕与置信度）
    pts_vals = [v for k, v in src.items() if k in ('E_T', 'O25_exp', 'LAM', 'LINE')]
    _spread = (max(pts_vals) - min(pts_vals)) if len(pts_vals) >= 2 else 0.0
    _n = len(pts_vals)
    if _n >= 3 and _spread > 0.35:
        notes.append('🔴源间分歧 %.2f 球（>0.35·市场三源不自洽·以分布为准并在 raw 说明）' % _spread)

    # 置信度（按分布集中度·不再是「源多就高」）
    top_p = max(pT)
    if top_p >= 0.26 and p50 == t_mode:
        conf = 'HIGH'
    elif top_p >= 0.20:
        conf = 'MID'
    else:
        conf = 'LOW'
    notes.append('分布源=%s ｜ 峰值 %.1f%% ｜ P(≥4球) %.1f%% ｜ 尾部档 %s ｜ 源 %d 个(离散%.2f)'
                 % (pT_src, top_p * 100, sum(pT[4:]) * 100,
                    ('/'.join(str(k) for k in tails)) or '无', _n, _spread))

    return {
        # 分布驱动（新·主）
        'pT': [round(x, 4) for x in pT],
        'pT_src': pT_src,
        'p25': p25, 'p50': p50, 'p75': p75, 'p90': p90,
        'T_lo': p20, 'T_hi': p80,                 # 🔴自适应区间（替代固定 ±1）
        'wide_lo': p05, 'wide_hi': p95,
        'tail_bins': tails,
        'P_ge4': round(sum(pT[4:]), 4),
        # 🔴V3.5.90 厚尾判据收敛（premium 单条·cs_tail_ratio/p5_ge/p6_ge/margin 留痕）
        'tail': tail_signal(mm=mm, cs_full=cs_full, pT=pT,
                            margin=(mm or {}).get('margin') if isinstance(mm, dict) else None),
        # 兼容旧键
        'T_star': t_mode,
        'T_cont': round(t_cont, 3),
        'band': '%d球档(%d-%d)' % (t_mode, p20, p80),
        'src': src, 'n_src': _n,
        'spread': round(_spread, 2),
        'confidence': conf,
        'notes': notes,
        'weights': dict(W),
    }


def band_weight(score, band):
    """比分 → 量级权重（**分布密度比**·不排除）

    🔴V3.5.88（2026-11-03 用户裁定方案 A）：
      旧实现 = 距中心阶梯 1.0 / 0.55 / 0.25 / 0.10
        → 317 场 P(≥4球)=36.4%，而 5/6/7 球被压到 **0.10** = 结构性出局（真实 2:4）
      新实现 = `W_FLOOR + (1-W_FLOOR) × pT[t] / max(pT)`
        → 完全跟随市场分布密度（同档位不再按「距中心几球」粗暴分档）
        → 317 场：4球(17%)≈0.88 · 5球(10%)≈0.66 · 6球(5%)≈0.48（原全 0.10）
      仍**不排除**（最低 W_FLOOR=0.35），遵守「禁硬上下限」铁律。
    """
    if not band or not band.get('pT'):
        return 1.0
    try:
        h, a = [int(x) for x in str(score).replace('-', ':').split(':')]
        t = h + a
    except Exception:
        return 1.0
    pT = band['pT']
    if not isinstance(pT, (list, tuple)) or not pT:
        return 1.0
    # 🔴V3.5.88 消融开关: MB_OLD_BAND=1 → 退回旧「距中心阶梯」1.0/0.55/0.25/0.10
    try:
        import os as _os89
        if _os89.environ.get('MB_OLD_BAND') == '1':
            return {0: 1.00, 1: 0.55, 2: 0.25}.get(abs(t - int(band.get('T_star') or 0)), 0.10)
    except Exception:
        pass
    if t >= len(pT):
        return W_FLOOR
    peak = max(pT) or 1e-9
    dens = pT[t] / peak
    return round(W_FLOOR + (1.0 - W_FLOOR) * dens, 3)


def tail_signal(mm=None, cs_full=None, pT=None, margin=None):
    """🔴V3.5.90 厚尾判据收敛（2026-11-03 评审修复·用户实测 9 场·四硬伤全修）

    ⚠️ V3.5.89 教训（全部实测·不是推测）：
      ① p5_ge≥0.15 分支 else 无条件判厚尾 → 9 场 8 场触发（89%）= 等价「是不是大球盘」零增量
      ② 折价比（波胆尾部/全档P≥5）当晚 min 0.99 / 中位 1.22 / max 1.46·0/9 ≥1.5 → 
         波胆尾部 ≈ 全档 P(≥5) × 1.2 是**结构性常数**（CS 表高比分档位数量多），不是信号
      ③ cs_tail_ratio 阈值与真厚尾**反向**（case155 尾部仅 14% < 普通大球场 21-45%）
      ④ case260 波胆 28% = 全档 28%（1.0× 零溢价）仍判强厚尾 → 次锚推 5 球（与 R-ANCHOR-BIG 叠加）

    数据读数（全部市场定价·零模型主观·仅作留痕）：
      ① cs_tail_ratio：cs_full 里 ≥5 球比分去水概率之和 ÷ 全表去水概率之和
         （P1-3 去水归一·Σ(1/f_i)/Σ(1/f_j) ≡ 归一后尾部占比·与 p5_ge 同口径·跨场可比）
      ② p5_ge / p6_ge：pT 全档差分 PMF 直接算 P(≥5)/P(≥6)
      ③ margin_m：净胜分布 E[M]

    判定（V3.5.90·唯一判据 = premium）：
      · premium = cs_tail_ratio / p5_ge（波胆相对溢价·结构性基线 ≈ 1.2）
      · flag = 强厚尾 if premium ≥ 3.0
            | 厚尾   if premium ≥ 2.0   （case155 2.1× 触发·今晚 0/9 触发）
            | 正常   otherwise          （无波胆数据 → premium=n/a → 正常·诚实降级）
      · cs_tail_ratio / p5_ge / p6_ge / margin_m 全部降为留痕（不参与判定）

    返回 dict（无 pT/cs → 三态）：
      {flag, p5_ge, p6_ge, cs_tail_ratio, tail_premium, margin_m, notes[]}
    """
    _n = []
    try:
        p5_ge = p6_ge = None
        if isinstance(pT, (list, tuple)) and len(pT) >= 7 and sum(pT) > 0:
            _s = sum(pT) or 1e-9
            p5_ge = sum(pT[5:]) / _s
            p6_ge = sum(pT[6:]) / _s

        cs_tail_ratio = None
        tail_premium = None
        if isinstance(cs_full, dict) and cs_full:
            _tail = _all = 0.0
            _n_cs = _n_tail = 0
            for _k, _v in cs_full.items():
                try:
                    _s0 = str(_k).strip().replace(":", "-").replace("/", "-")
                    _h0, _a0 = int(_s0.split("-")[0]), int(_s0.split("-")[1])
                    _f0 = float(_v)
                except (TypeError, ValueError, IndexError):
                    continue
                if not (1 < _f0 < 100):
                    continue
                _p0 = 1.0 / _f0          # 去水概率（1/odds·原始倒数和）
                _all += _p0
                _n_cs += 1
                if _h0 + _a0 >= 5:
                    _tail += _p0
                    _n_tail += 1
            # 🔴P1-3: 分母去水归一——_tail/_all ≡ Σ(1/f_i)/Σ(1/f_j) 即归一后尾部占比
            #   （与 p5_ge 同为「去水概率占比」口径·跨场可比；旧实现注释未写清口径）
            if _all > 0:
                cs_tail_ratio = _tail / _all
            # 🔴相对溢价：波胆尾部占比 / 全档 P(≥5)（唯一判据·V3.5.90）
            #   注意: 波胆尾部占比 ≈ 全档 P(≥5) × 1.2 是 CS 表高比分档位数量多导致的
            #   结构性常数（9 场实测 min 0.99/中位 1.22/max 1.46）→ 阈值 2.0 需显著超越基线
            if cs_tail_ratio is not None and p5_ge is not None and p5_ge > 0.01:
                tail_premium = cs_tail_ratio / p5_ge

        margin_m = None
        try:
            if isinstance(margin, dict) and margin.get("p"):
                _pm = margin["p"]
                if isinstance(_pm, dict) and _pm:
                    _den = sum(float(v) for v in _pm.values()) or 1e-9
                    margin_m = sum(int(k) * float(v) for k, v in _pm.items()) / _den
                elif isinstance(_pm, (list, tuple)) and _pm:
                    _off = len(_pm) // 2
                    margin_m = sum((i - _off) * float(v) for i, v in enumerate(_pm))
        except Exception:
            pass

        # ── 判定（V3.5.90 评审修复：只用 premium 一条·其余全降为留痕）──
        #   评审实证（2026-11-03 晚 9 场）: p5_ge≥0.15 / cs_tail_ratio≥0.30 都是
        #   「大球盘同义词」→ 89% 误触发；波胆尾部占比 ≈ 全档 P(≥5) × 1.2 是
        #   CS 表高比分档位数量多导致的结构性常数（9 场 min 0.99 / 中位 1.22 / max 1.46）
        #   → 只有 premium≥2.0 是真信号（case155 折价 2.1× 触发·普通大球场 0/9 触发）
        #   P0-1: p5_ge≥0.15 分支的 else 无条件判厚尾 → 删除
        #   P0-2: 判据只用 premium → cs_tail_ratio / p5_ge / p6_ge / |E[M]| 全降留痕
        #   P1-3: cs_tail_ratio 分母去水归一（1/odds 归一后再算占比·跨场可比）
        flag, _why = '正常', []
        if tail_premium is not None and tail_premium >= 2.0:
            flag = '强厚尾' if tail_premium >= 3.0 else '厚尾'
            _why = ['波胆溢价%.1f×（尾部%.0f%% vs 全档P≥5=%.0f%%）'
                    % (tail_premium, cs_tail_ratio * 100, p5_ge * 100)]
        _why = _why or ['全档P(≥5)=%s·波胆尾部=%s·溢价=%s·净胜=%s·P(≥6)=%s'
                        % (('%.0f%%' % (p5_ge * 100)) if p5_ge is not None else 'n/a',
                           ('%.0f%%' % (cs_tail_ratio * 100)) if cs_tail_ratio is not None else 'n/a',
                           ('%.1f×' % tail_premium) if tail_premium is not None else 'n/a',
                           ('%+.1f' % margin_m) if margin_m is not None else 'n/a',
                           ('%.0f%%' % (p6_ge * 100)) if p6_ge is not None else 'n/a')]
        _n.append('厚尾三线索: %s（%s）' % (flag, '·'.join(_why)))
        _n.append('🔴V3.5.90 观察期: 判据仅 premium≥2.0·其余线索留痕·标注级不动作')
        return {"flag": flag, "p5_ge": round(p5_ge, 4) if p5_ge is not None else None,
                "p6_ge": round(p6_ge, 4) if p6_ge is not None else None,
                "cs_tail_ratio": round(cs_tail_ratio, 4) if cs_tail_ratio is not None else None,
                "tail_premium": round(tail_premium, 3) if tail_premium is not None else None,
                "margin_m": round(margin_m, 3) if margin_m is not None else None,
                "notes": _n}
    except Exception as _e:
        return {"flag": '三态', "p5_ge": None, "p6_ge": None,
                "cs_tail_ratio": None, "tail_premium": None, "margin_m": None,
                "notes": ["厚尾三线索异常(%s)" % type(_e).__name__]}


def fmt(band):
    """一行留痕"""
    if not band or band.get('T_star') is None or not band.get('pT'):
        return '量级分布: ⚪ 无法确定（三态）'
    pT = band['pT']
    return ('量级分布(%s): 众数 %s球 ｜ 区间 %s-%s球(P20-P80) · 宽 %s-%s(P5-P95) ｜ '
            'P(≥4球) %.1f%% ｜ 尾部档 %s ｜ 峰值 %.1f%% ｜ 置信 %s'
            % (band.get('pT_src'), band['T_star'], band['T_lo'], band['T_hi'],
               band.get('wide_lo'), band.get('wide_hi'),
               band.get('P_ge4', 0) * 100,
               ('/'.join(str(k) for k in band.get('tail_bins') or [])) or '无',
               max(pT) * 100, band['confidence']))


def dist_line(band):
    """逐球分布一行（供 raw/calc_all 留痕）"""
    if not band or not band.get('pT'):
        return '  分布: ⚪ 三态'
    pT = band['pT']
    seg = ' '.join('%d球%.0f%%' % (k, p * 100) for k, p in enumerate(pT) if p >= 0.005)
    return '  分布: %s ｜ 均值 %.2f 球' % (seg, sum(k * p for k, p in enumerate(pT)))


# ══════════════ 自测 ══════════════
if __name__ == '__main__':
    print('=' * 88)
    print('量级分布驱动 自测（V3.5.88）')
    print('=' * 88)
    CASES = [
        ('317 萨索洛场（O2.5 1.563·λ3.505·真实 6 球 2:4）', dict(o25=1.563, lam=3.505, p52='L3')),
        ('318 纽卡场（O2.5 1.773·λ2.66·真实 1 球 0:1）', dict(o25=1.773, lam=2.66, p52='L2')),
        ('319 拉科场（O2.5 2.281·λ2.36·真实 3 球 2:1）', dict(o25=2.281, lam=2.36, p52='L0')),
        ('超大球场（O2.5 1.30·L5）', dict(o25=1.30, lam=4.0, p52='L5')),
        ('小球场（O2.5 2.571·λ2.445·L0）', dict(o25=2.571, lam=2.445, p52='L0')),
    ]
    for tag, kw in CASES:
        b = magnitude_band(**kw)
        print('\n  %s' % tag)
        print('    %s' % fmt(b))
        print(dist_line(b))
        _tl = b.get('tail') or {}
        print('    厚尾三线索(V3.5.90): %s ｜ 溢价=%s ｜ P(≥5)=%s P(≥6)=%s ｜ 波胆尾部=%s ｜ 净胜=%s(留痕)'
              % (_tl.get('flag'),
                 ('%.2f×' % _tl.get('tail_premium')) if _tl.get('tail_premium') is not None else 'n/a',
                 ('%.0f%%' % (_tl.get('p5_ge') * 100)) if _tl.get('p5_ge') is not None else 'n/a',
                 ('%.0f%%' % (_tl.get('p6_ge') * 100)) if _tl.get('p6_ge') is not None else 'n/a',
                 ('%.0f%%' % (_tl.get('cs_tail_ratio') * 100)) if _tl.get('cs_tail_ratio') is not None else 'n/a',
                 ('%+.1f' % _tl.get('margin_m')) if _tl.get('margin_m') is not None else 'n/a'))
        print('    权重: 1:1→%.2f  2:1→%.2f  3:1→%.2f  2:2→%.2f  1:4→%.2f  2:4→%.2f  3:3→%.2f'
              % tuple(band_weight(s, b) for s in ('1:1', '2:1', '3:1', '2:2', '1:4', '2:4', '3:3')))
