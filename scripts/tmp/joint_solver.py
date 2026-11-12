# -*- coding: utf-8 -*-
"""joint_solver.py — 四要素深度融合锚定（V3.5.77·2026-10-13 用户方案）

🔴 严格按《四要素深度融合锚定机制升级方案 V3.5.77》实现（用户指令：按方案修改·不需回测）。

核心思想（方案 §1.2 / §2.1）：把「四要素独立产出 + 事后一致性检查」改为
   「统一坐标系 + 约束传播 + 交集生成」—— 冲突在**生成阶段**消解，不靠事后补救。

四要素 = 同一场比赛的四个投影（B 由 T 派生，实际 3 个自由维度·方案 §2.1）：
    比分 s=(h,a) → D 方向=sign(h−a) · M 净胜=|h−a| · T 总进球=h+a · B 大小球=方向投影(T)

融合链路（方案 §2.2·单向传导·禁回跳）：
    7.0 四要素并行估值（只读·互不写·方案 §3 Step7.0）
    7.1 坐标系转换      （方案 §3 Step7.1）
    7.2 约束传播        （方案 §3 Step7.2·按市场硬度锁定）
    7.3 冲突仲裁        （方案 §3 Step7.3·6 规则矩阵·🔴规则3/4 于 2026-10-13 用户裁决「真正生效」）
    7.4 自洽比分池生成  （方案 §3 Step7.4·交集 + 泊松排序 + 查表集成）

市场硬度降序（方案 §7.3 优先级总规则）：
    O2.5 赔率（市场大小球） > 亚盘盘口（净胜） > 期望进球五源 > 泊松/查表

🔴 口径单一权威（2026-10-13 接入审计修·防「同场两个期望总进球」）：
    T 的源值**优先由外部注入**（`src_lam`）——来源 = 管道 Step6.5 大小球水位精读
    （`totals_water_read.water_read` 的 λ_market/λ_line/λ_pois/λ_table/λ_water +
     λ_handi 让球深度源）→ joint_solver **只按方案 §4.1 权重合成**，不重复造源头。
    无注入 → 内部回退自算（**三态标注 origin**·禁静默）。

🔴 2026-10-13 P1 修复（用户审计发现·两条均为「实现未落地设计」）：
    P1-1 **受让场谱系被误杀**：原实现把 D 切成单值「平局」→ M 中的客胜净胜档（-1）被浪费
         → 交集池只剩 1:1、次锚=None，**未复现 case210「平局/客胜谱系」铁律**；
         且 D 被改写后 **T 域未同步重算**。
         → 改为 **`lock["D_set"]` 多值谱系**（受让×主胜 → [平局, 客胜]·**方向保留**）
           + 规则1（禁主胜锚）**前移到 7.2 约束传播**（因其必须参与 T 域推导）
           + T 域按 D_set 推：含平局 → t_lo=0（保留 0:0 出口）
    P1-2 **规则6 污染一致度**：规则6（查表 vs 市场·**设计即仅提示**）必触发且计入 arb_n
         → 任何正常场 consistency 恒为 MID，**HIGH 档成为死档**。
         → 规则6 移入独立 `notes`（**不计入一致度**）· consistency 只数「✅生效类」仲裁

接口（方案 §5）：
    joint_anchor(oh, od, oa, handi, o25, u25, ou_line, lam_h, lam_a, league, src_lam) -> dict
    返回 {ok, est, axes, lock(D/D_set/M/T), arbitrations(生效类), notes(仅提示),
          candidates, pool, anchor_1st/2nd/3rd, consistency, trust, parallel_dirs}
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    from calc_v3572 import direction_full, margin_candidates, goal_bin_probs, score_depth_lookup
except Exception as _e:                                    # pragma: no cover
    direction_full = margin_candidates = goal_bin_probs = score_depth_lookup = None
    _IMP_ERR = str(_e)
else:
    _IMP_ERR = None

try:
    from live_score_engine import _o25_expect, expect_table
except Exception:                                          # pragma: no cover
    _o25_expect = expect_table = None

# 方案 §4.1：四要素→五源融合权重（market/line/pois/table/water）
W_SRC = {"market": 0.40, "line": 0.35, "pois": 0.05, "table": 0.10, "water": 0.10}
# 🔴2026-10-20 用户指令「严格按市场信号·不依赖泊松·泊松约束了上限」→
#   pois 0.20→0.05（最小源·仅在有盘口移动时作辅助）·market 0.30→0.40 / line 0.30→0.35 升权
# 🔴五源注入键（外部 src_lam 允许的键·方案 §4.1）
SRC_KEYS = ("market", "line", "pois", "table", "water")


def _f(x):
    try:
        return float(x)
    except Exception:
        return None


def _devig_over(o25, u25):
    """方案 §4.2：O2.5 去水真概率 p_over_fair"""
    a, b = _f(o25), _f(u25)
    if not a or not b:
        return None
    ia, ib = 1.0 / a, 1.0 / b
    return ia / (ia + ib)


# 🔴P40 DEPRECATED（2026-10-30 批次5）: 全库零调用。被 _b_label_fallback（三级降级）取代
#   → 保留备查·不接入
def b_label_of(p_over_fair):
    """方案 §4.2 大小球五档"""
    if p_over_fair is None:
        return None
    if p_over_fair > 0.62:
        return "大球强"
    if p_over_fair > 0.55:
        return "大球"
    if p_over_fair > 0.45:
        return "中性"
    if p_over_fair > 0.38:
        return "小球"
    return "小球强"


B_T_MAP = {"大球强": ("3", "4"), "大球": ("2", "3"), "中性": ("2", "3", "4"),
           "小球": ("1", "2"), "小球强": ("1", "2")}      # 方案 §4.2 派生关系


# ==================== 大球识别与锚定（V3.5.78·2026-10-14 用户方案·盘口线驱动） ====================

# 极端大球档（欧亚盘盘口线→λ 判档·goal_bins_table 148,397 场实测支撑）
#   λ≥3.4 → 4+ 球是主模态(g4=45.8-59.2%) → 主锚大球谱系 + 次锚低分兜底
EXTREME_OVER_LAM = 3.4          # O2.5≈1.50 边界（1.30-1.50 档 g4=45.8%）
STRONG_OVER_LAM = 3.0           # 大球强边界
BIG_OVER_LAM = 2.7              # 大球边界


# ============ 市场信号主导排序（V3.5.79 P5·2026-10-17 用户方案·封装式补丁包） ============
# 决策依据：35 份真实快照实证 64% 场次波胆 Top1 ≠ 泊松 Top1（市场想说 1:1·泊松默认 2:1）；
#   泊松基线权重（0.22-0.36）是波胆证据（≤0.20）的 1.5-1.8 倍 → 市场信号被压制。
# 原则：「一切以市场信号为准」——波胆排名主导（排名对 FLB 数值偏差不敏感）·让球水位次之·泊松兜底。
# 🔴 全部权重标【待回测校准】·禁单场固化（方案 §5.3）。
P5_BS_RANK_TOP = 0.30           # 波胆排名基线 Top1 权重（待回测校准）
P5_BS_RANK_STEP = 0.03          # 每降 1 名线性衰减（待回测校准）
P5_POIS_WEIGHT = 0.0            # 🔴2026-10-20 用户指令「不要依赖泊松」→ 泊松完全退出【排序】
                                #   （实测 0.5→0.0 四场锚零变化 = 市场主导基線已饱和·P5 已生效）
                                #   泊松仍保留：候选池生成(_build_pool) / λ 反推 / BTTS 校准
P5_CS_MIN_BINS = 10             # S1 触发门槛：波胆档数 ≥10（方案 §六）
P5_WATER_STRONG_NET = 0.15      # S2: 上盘覆盖≥55% 且 |净胜|≥2（机构真看好→净胜2+档升权·待回测）
P5_WATER_STRONG = 0.10          # S2: 上盘覆盖≥55% 且 |净胜|<2
P5_WATER_MID = 0.05             # S2: 45%≤上盘覆盖<55%
P5_WATER_WEAK_LOW = 0.10        # S2: 上盘覆盖<45% 且 净胜≤0（弱让→平局/受让档升权）
P5_WATER_WEAK_HIGH = 0.02       # S2: 上盘覆盖<45% 且 净胜>0
P5_E5_CS = (0.30, 0.15, 0.05)   # E5 波胆证据加分（S1 时·与排名基线双通道强化市场·待回测）
P5_E5_CS_OFF = (0.20, 0.12, 0.05)   # E5（S2/S3 时·无波胆不虚增）
P5_E1_TABLE = (0.20, 0.10, 0.05)    # E1 查表升权（148,397 场历史分布=市场统计·待回测）
P5_E6_WATER = 0.08              # E6 让球水位共振（新增·与 P5-2 呼应·待回测）
P5_E8_EXPECT = (0.10, 0.10, -0.30, -0.30)   # E8 市场期望匹配（🔴2026-10-20 P6-c 语义修正）
                                #   |总进球−市场期望| ≤0.5 / ≤1.0 / ≤1.5 / >1.5 → +0.10/+0.10/−0.30/−0.30
                                #   🔴容差内**同等加分**（不因偏离更小而过度加权·把排序权让回波胆/竞彩市场共识）
                                #   🔴容差外**重罚剔除锚位**（锚-期望强制铁律：主锚 ≤1.0 / 至少一锚 ∈[E−1,E+1]）
                                #   期望源=O2.5 市场价反推(_o25_expect)·纯市场信息（非泊松）·待回测校准
P5_E9_HT = (0.08, -0.04)        # E9 半场方向一致性（🔴2026-10-20 新增·待回测校准）
                                #   半场方向概率与候选比分形态一致 +0.08 / 明显不一致 -0.04
P5_E7_JC = (0.12, 0.06, 0.03)   # E7 竞彩比分盘证据（🔴2026-10-20 用户点名「竞彩」·P5 未含）

# ============ 纵向消费升级（V3.5.80 P8·2026-10-20 用户方案·prestep 快照驱动） ============
# ① 波胆赔率初盘→临场变化 = 大资金对具体比分的定向表态（E10）
# ② 让球升降盘组合 = 机构意图方向（升盘降水真看好 / 升盘升水造热 / 降盘升水看弱）
# ③ 大球水位变化 = 生水诱大 vs 真看好判别（B 档 ±1 级）
# 🔴 铁律：只调权重/置信度·永不反转方向·不排除候选（防死锚）·全部【待回测校准】
P8_CS_DROP_STRONG = 0.12         # E10 波胆显著降水(赔率降≥15%) +0.12
P8_CS_DROP_MILD = 0.06           # E10 波胆温和降水(5%~15%) +0.06
P8_CS_RISE_MILD = -0.04          # E10 波胆温和升水(-15%~-5%) -0.04
P8_CS_RISE_STRONG = -0.08        # E10 波胆显著升水(≤-15%) -0.08

# ======== 市场三源比分分布矩阵（V3.5.81 P10·2026-10-25 用户方案《P10 补丁包》） ========
# 逻辑: 大小球全档(进几个球)·让球全档(赢几个球)·波胆(怎么进) → 全档去水反推边缘 →
#       IPF 投影成联合比分矩阵 → 每个比分天然同时满足总进球边缘与净胜边缘（不再由泊松定形状）。
# 排序: 🔴P23(2026-10-28 用户指令) 矩阵概率 ×3.0 主导·其余证据 ×0.15 仅 tie-break·E8 期望匹配全额不缩放·泊松仅回填。
# 🔴 全部权重【待回测校准】（Matches.csv 无全档多档字段 → 无法时间分割回测·仅实盘累积）
P10_MM_BASE = 3.0               # 🔴P23(2026-10-28 用户指令「市场信号主导」) 1.0→3.0：矩阵跨度 0.15→0.45 压过证据
_P10_MM_BASE_MARK = 1           # E0 市场矩阵基线权重（矩阵概率原尺度 0.02-0.16）
P10_EV_SCALE = 0.15             # 🔴P23(2026-10-28) 0.5→0.15：其余证据仅 tie-break（E8 期望不缩放·见下）
_P10_EV_SCALE_OLD_MARK = 1      # 证据加分整体减半（方案 §5.4「避免重复计价」）
P25_SIGNAL_W = 3.0            # 🔴P25(2026-10-28 用户指正) 信号约束权重：期望偏离 1 球 = 3.0 分（压过所有证据）
P25_P_TIE = 0.1                # 🔴P25 矩阵概率仅作 tie-break（概率有「低分偏置」禁作主键）
P24_M_RATIO = 0.6               # 🔴P24 M 域放宽阈值 = 现有 M 档最高市场净胜概率 × 0.6
P24_M_MAX = 2                   # 🔴P24 最多扩入净胜档数（防池爆炸）
P10_POIS_FILL = 0.15            # 泊松仅作「矩阵缺失档」回填（方案 §5.4）
# 🔴2026-10-20 二轮深检修(P2-3): 原 14 个常量中 10 个是**死常量**（仅定义·从不消费）——
#   阈值判定实际全在 snapshot_save（`_P8_*` 前缀）完成并输出 dir/shift/conf_step **语义值**，
#   joint_solver 只消费语义值 → 已删除 8 个死常量（CHG_MOVE/CHG_STRONG/AH_LINE_MOVE/AH_WATER_MOVE/
#   OU_OVER_DROP/OU_OVER_RISE/OU_LINE_MOVE/OU_CONF_STEP）·**阈值单一源 = snapshot_save._P8_***
#   保留项均为本模块真正消费的「加分幅度 / 水位偏移」：
P8_AH_UP_STRONG = 0.05           # 升降盘：真看好(升盘降水) p_up 偏移 +0.05
P8_AH_UP_WEAK = -0.05            # 升降盘：造热/看弱(升盘升水/降盘升水) p_up 偏移 -0.05
                                #   权重低于 E5 波胆（0.30）因竞彩抽水 12.8% > 欧盘 6.9% · 待回测

# 🔴V3.5.90 厚尾观察期开关（2026-11-03 评审修复·用户实测 9 场）
#   评审结论: 判据已收敛为 premium≥2.0 单条（magnitude_band.tail_signal），但 premium
#   能否分离 5-6 球场次仅 case155 单场验证 → 按项目铁律「观察项 ≥20 场才改规则」，
#   O-TAIL 三处防线进入**标注级观察期**：默认只打印提示、不强制改锚。
#   观察期满（≥20 场）且 premium 分离有效 → 置 True 恢复动作。
_TAIL_ACT = False


def _b_label_raw(o25, p_over_fair=None):
    """🔴V3.5.78: B 档三级降级——u25 缺失时用 O2.5 单边反推 λ 判档（治「B=None→T 域无人抬」）

    复用 totals_water_read.lam_from_p（泊松反解 over2.5 概率→期望总进球 λ）。
    欧亚盘 O2.5 赔率本身就是市场强度声明（goal_bins 148,397 场分箱实测）·无需 u25 也可判档。
    返回 label（'极端大球'/'大球强'/'大球'/'中性'/'小球'/'小球强'·无 o25 时 None）
    """
    if p_over_fair is not None:          # 一级：已有去水真概率（u25 在场·现状）
        if p_over_fair > 0.62:
            return "大球强"
        if p_over_fair > 0.55:
            return "大球"
        if p_over_fair > 0.45:
            return "中性"
        if p_over_fair > 0.38:
            return "小球"
        return "小球强"
    o = _f(o25)
    if o is None or o <= 0:
        return None
    # 二级：O2.5 单边反推 λ（泊松反解·复用 totals_water_read.lam_from_p）
    try:
        from totals_water_read import lam_from_p as _lfp
        lam_est = _lfp(1.0 / o)          # 单边隐含 over 概率→λ（无 u25 时近似）
    except Exception:
        lam_est = None
    if lam_est is None:
        # 三级兜底：O2.5 赔率直接映射（goal_bins 实测档位）
        if o <= 1.50:
            return "极端大球"
        if o < 1.70:
            return "大球强"
        if o < 1.90:
            return "大球"
        if o <= 2.10:
            return "中性"
        return "小球强"
    if lam_est >= EXTREME_OVER_LAM:
        return "极端大球"
    if lam_est >= STRONG_OVER_LAM:
        return "大球强"
    if lam_est >= BIG_OVER_LAM:
        return "大球"
    if lam_est >= 2.3:
        return "中性"
    if lam_est >= 2.0:
        return "小球"
    return "小球强"


def _label_shift(label, ou_vert):
    """🔴P8: 大球水位方向 → B 档 ±1 级（只调置信档·不反转方向·不跨极端）"""
    if not label or not ou_vert:
        return label
    try:
        step = int(ou_vert.get("conf_step") or 0)
    except Exception:
        step = 0
    if not step:
        return label
    ladder = ["小球强", "小球", "中性", "大球", "大球强", "极端大球"]
    if label not in ladder:
        return label
    i = ladder.index(label) + step
    return ladder[max(0, min(len(ladder) - 1, i))]


def _b_label_fallback(o25, p_over_fair=None, ou_vert=None):
    """🔴V3.5.78 B 档三级降级 + 🔴V3.5.80 P8 大球水位方向修正

    label = _b_label_raw(...)（原三级逻辑·零改动）
          → P8: ou_vert.conf_step ±1 档位 ladder 微调（生水诱大↓ / 真看好大球↑）
    🔴铁律: 只调置信档·不反转方向·待回测校准
    """
    return _label_shift(_b_label_raw(o25, p_over_fair), ou_vert)


def _apply_totals_driven_domain(lock, lam_final, totals_bin, notes):
    """🔴V3.5.78: 盘口线驱动 T 域上探——根治「极端大球 4+ 谱系被净胜公式排除」

    现有公式 t_hi=min(6, max|m|+2) 用「净胜+2」锁死总进球上界，无视欧亚盘盘口线已给出的 λ
    （复盘② 国米 O2.5=1.33 → water_read λ_final=4.27 却 T 域(1,4)·4+ 谱系全被排除）。
    本函数**只在大球场抬上界**·非大球场返回原 lock（完全兼容现有路径）。

    🔴🔴 严禁死锚（2026-10-14 用户指令·V2 修订）:
       **只抬上界(t_hi)·绝不抬下界(t_lo)** —— 低分谱系必须保留在候选池！
       (极端档 g01=7.8-13.4%≠0·复盘④ 真实 1:0 恰为低分·抬下界排除低分=死锚)

    数据依据（goal_bins_table.json·148,397 场实测）:
      O2.5 1.00-1.30 → 4+球 59.2% / 0-1球 7.8%  (极端档主模态=大球·但低分非零)
      O2.5 1.30-1.50 → 4+球 45.8% / 0-1球 13.4%
      O2.5 1.50-1.70 → 4+球 36.4% / 0-1球 18.8%
    """
    # 🔴V3.5.78→V3.5.79(P0-1): 盘口线驱动 T 域上探——**连续 λ 映射·无硬断档**
    if lam_final is not None:
        # 🔴V3.5.79 P0-1: 连续映射——任何 λ≥2.6 都上探（去掉 3.4 硬阈值·3.0-3.3 大球强档也响应）
        lam = float(lam_final)
        t_lo, t_hi = lock["T"]
        if lam >= 2.6:
            new_hi = max(t_hi, min(6, int(round(lam + 1.5))))
            if new_hi > t_hi:
                lock["T"] = (t_lo, new_hi)
                notes.append("🔴盘口线驱动(V3.5.79 P0-1): λ_final=%.2f → 候选空间上界 %d（原%d·连续λ映射·下界不动[%d]）"
                             % (lam, new_hi, t_hi, t_lo))
            else:
                # 🔴2026-11-01: 上界已达标（M 域扩展后 max|m|+2 已够）→ **仍留痕**
                #   原实现只在「真上探」时写 note → 达标即静默 → 审计看不到 = 判未执行
                notes.append("✅盘口线驱动(V3.5.79 P0-1): λ_final=%.2f → 候选空间上界 %d 已满足"
                             "（原%d·M域/净胜公式已覆盖·无需上探·下界不动[%d]）"
                             % (lam, new_hi, t_hi, t_lo))
            return lock, True
        return lock, False
    # 无 λ_final → 用 totals_bin 兜底（V3.5.78 原逻辑·兼容）
    if totals_bin in ("大球", "很大", "超大", "极超"):
        t_lo, t_hi = lock["T"]
        if t_hi < 5:
            lock["T"] = (t_lo, 5)
            notes.append("🔴盘口线驱动(V3.5.78): totals_bin=%s → 候选空间上界至 5（下界不动·严禁死锚）" % totals_bin)
        return lock, True
    return lock, False


# ==================== Step 7.0 四要素并行估值（方案 §3·只估值不修正） ====================
def _est_direction(oh, od, oa, o25, league):
    out = {"dir": None, "pH": None, "pD": None, "pA": None, "conf": None, "skew": None,
           "src": "direction_full"}
    if direction_full is None:
        out["src"] = "缺 direction_full"
        return out
    r = None
    used = None
    for kw in ({"over25": o25, "league_div": league}, {"over25": o25}, {}):
        try:
            r = direction_full(oh, od, oa, **kw)
            used = ",".join(sorted(kw)) or "无附加参数"
            break
        except Exception:
            continue
    if not isinstance(r, dict):
        out["src"] = "direction_full 返回非 dict"
        return out
    out["src"] = "direction_full(%s)" % used
    ph = _f(r.get("主胜") or r.get("pH") or r.get("home"))
    pd = _f(r.get("平局") or r.get("pD") or r.get("draw"))
    pa = _f(r.get("客胜") or r.get("pA") or r.get("away"))
    out.update(pH=ph, pD=pd, pA=pa)
    for k in ("main", "main_dir", "dir", "direction"):
        if r.get(k):
            out["dir"] = str(r[k]).replace("主队", "主胜").replace("客队", "客胜")
            break
    if out["dir"] is None and None not in (ph, pd, pa):
        out["dir"] = max((("主胜", ph), ("平局", pd), ("客胜", pa)), key=lambda t: t[1])[0]
    for k in ("conf", "confidence", "confidence_layer"):
        if r.get(k):
            out["conf"] = str(r[k])
            break
    if None not in (ph, pd, pa):
        srt = sorted([ph, pd, pa], reverse=True)
        out["skew"] = round(srt[0] / srt[1], 3) if srt[1] > 0 else 9.9
    # 🔴2026-10-21 P0-3 修复: 额外输出 skew_raw = **纯去水**口径
    #   根因: out["skew"] 用 direction_full 的**校准后**概率（含 prob_calibration + 欧战三层校准）
    #   而 AGENTS「弱共识 skew<150%」/「单押须 skew≥200%」阈值来自 227,495 场**纯去水**回测
    #   → 用校准后 skew 比纯去水阈值 = 口径错配（case260: 纯去水 159% 高共识 / 校准后 124% 弱共识 → 结论相反）
    try:
        _iv = [1.0 / float(oh), 1.0 / float(od), 1.0 / float(oa)]
        _sv = sum(_iv)
        _pv = [x / _sv for x in _iv]
        _srt0 = sorted(_pv, reverse=True)
        out["skew_raw"] = round(_srt0[0] / _srt0[1], 3) if _srt0[1] > 0 else 9.9
    except Exception:
        out["skew_raw"] = None
    return out


def _handi_water_strength(handi, wh, wa, lam=None, ah_vert=None):
    """🔴V3.5.79 P1 + 🔴V3.5.80 P8: 欧亚盘让球赔率 → 上盘覆盖概率 → 净胜档强度

    P8: 消费 vertical_for 的 ah_vert（升盘降水=真看好 → p_up +0.05 ·
        升盘升水/降盘升水=造热/看弱 → p_up −0.05）→ 重算强度并在原 shift 上叠加
    🔴铁律: 只调强度/置信·不硬改 M 集合（防死锚）·无 ah_vert 时行为与原实现完全一致

    原理（行业通识·已搜索核验）:
      欧式让球赔率(主wh/客wa) 去水后 P(上盘覆盖盘口) = 机构对净胜量级的实时定价
      升盘降水=机构真看好 → 净胜档上移 · 降盘升水=诱导/风险 → 净胜档下移
    返回: {p_up, strength, shift, note}
    """
    if not (wh and wa and wh > 1 and wa > 1):
        # 🔴2026-10-20 审计修复(P1·存在≠活跃): 无当期水位时原实现直接 return None
        #   → P8 纵向 ah_vert **恒不生效**（calc_all 多数场只有 --home_water 无 --ah_wh/--ah_wa）
        #   修法: **不编造水位**（禁臆造），改用 ah_vert.shift 直接给「净胜档位移提示」
        if ah_vert and int(ah_vert.get("shift") or 0):
            _s8o = int(ah_vert.get("shift"))
            return {"p_up": None, "strength": ("强" if _s8o > 0 else "弱"),
                    "shift": _s8o, "p8_shift": _s8o, "p8_only": True,
                    "note": "🔴让球升降盘(P8·无当期水位·仅纵向): %s → 净胜档%s"
                            % (ah_vert.get("combo"), "上移" if _s8o > 0 else "下移")}
        return None                                     # 缺水位且无纵向信号→不介入
    ih, ia = 1.0 / wh, 1.0 / wa
    p_up = ih / (ih + ia)
    # 强度分级（阈值待回测校准·禁单场固化）
    # 🔴P8: 升降盘组合修正（先改 p_up·再重算强度·最后在原 shift 上叠加·夹在 ±1）
    _s8, _combo = 0, None
    if ah_vert:
        _s8 = int(ah_vert.get("shift") or 0)
        _combo = ah_vert.get("combo")
        if _s8:
            # 🔴P2-3 修正: 用对称的 WEAK 常量（原写 -P8_AH_UP_STRONG → 改 A 不改 B 会静默失效）
            p_up = min(0.95, max(0.05, p_up + (P8_AH_UP_STRONG if _s8 > 0 else P8_AH_UP_WEAK)))
    if p_up >= 0.55:
        strength, shift = "强", +1
    elif p_up >= 0.45:
        strength, shift = "中", 0
    else:
        strength, shift = "弱", -1
    if _s8:
        shift = max(-1, min(+1, shift + _s8))
    note = "🔴让球水位(P1): 上盘覆盖%.1f%%(%s)·净胜档%s%s" % (
        p_up * 100, strength, "上移" if shift > 0 else ("下移" if shift < 0 else "保持"),
        ("·P8升降盘[%s]" % _combo) if _combo else "")
    return {"p_up": round(p_up, 3), "strength": strength, "shift": shift,
            "p8_shift": _s8, "note": note}


def _est_margin(handi, lam, wh=None, wa=None, ah_vert=None):
    """方案 §4.3：M 主档∪相邻档；λ 过滤 + 🔴P1 让球水位档位移 + 🔴P8 升降盘修正"""
    try:
        M = list(margin_candidates(handi))
    except Exception:
        M = [0]
    # 🔴2026-11-01 M 域按量级扩展（用户质疑「让1.5为什么不能是 4:1/4:0·你就这么死板吗」）:
    #   原实现把让球档**硬映射**成净胜档（让1.5 → 净胜[1,2]），池里**永远不会有 4:0/4:1/5:1**。
    #   P43 只放宽了**校验层**（market_net_band ±1.5），**池生成层从未放宽** = 只校验不生成。
    #   λ 越大净胜分布越宽（极端大球场 4:0/4:1/5:1 都是真实高频比分）→ 按 λ 追加更大净胜档。
    #   🔴只**追加**不改变原顺序 → main（M[0]）不变，主档不动（防死锚）。
    if lam is not None and M:
        try:
            _lm = float(lam)
            _mx = max(M)
            _ext = []
            if _lm >= 4.0:
                _ext = [_mx + 1, _mx + 2, _mx + 3]
            elif _lm >= 3.4:
                _ext = [_mx + 1, _mx + 2]
            elif _lm >= 3.0:
                _ext = [_mx + 1]
            _add = [x for x in _ext if x not in M]
            if _add:
                M = M + _add
        except Exception:
            pass
    main = M[0] if M else 0
    low = []
    if lam is not None:
        low = [m for m in M if abs(m) > lam + 1]
    out = {"all": M, "main": main, "adj": M[1:], "low_possibility": low}
    # 🔴V3.5.79 P1: 让球水位精调（盘口线粗域 + 水位细调·只提示不移除）
    wm = _handi_water_strength(handi, wh, wa, lam, ah_vert=ah_vert)   # 🔴P8
    if wm:
        out["water"] = wm
        # 强度位移：强→主档邻域扩入·弱→低档权重升（仅在 M 集合内平移·不删除原档·防死锚）
        out["shifted"] = wm["shift"] != 0
    return out


def _est_lambda(o25, u25, ou_line, lam_h, lam_a, src_lam=None):
    """方案 §4.1 五源融合：λ_market / λ_line / λ_pois / λ_table / λ_water

    🔴 口径单一权威（2026-10-13 接入审计修）：
      ① **优先** 消费外部注入 `src_lam`（来源 = 管道 Step6.5 大小球水位精读·同一场同一口径）
         → 消除「同场两个期望总进球」的口径分裂（本文件不重复造源头）
      ② 注入不足（<3 源）→ 内部回退自算补齐（**origin 三态标注**）
    返回 (lam, {源:值}, bad_src, origin)
    """
    src, origin = {}, None
    if isinstance(src_lam, dict):
        for k in SRC_KEYS:
            v = _f(src_lam.get(k))
            if v is not None:
                src[k] = v
        if src:
            origin = "Step6.5五源注入(%d源)" % len(src)
    if len(src) < 3:
        fb = {}
        if _o25_expect is not None and o25 is not None:
            try:
                fb["market"] = _o25_expect(o25)
            except Exception:
                pass
        if expect_table is not None and o25 is not None:
            try:
                fb["table"] = expect_table(o25)
            except Exception:
                pass
        if lam_h is not None and lam_a is not None:
            try:
                fb["pois"] = float(lam_h) + float(lam_a)
            except Exception:
                pass
        if ou_line is not None:
            try:
                fb["line"] = float(ou_line)
            except Exception:
                pass
        added = [k for k, v in fb.items() if v is not None and k not in src]
        for k, v in fb.items():
            if v is not None and k not in src:
                src[k] = v
        if added:
            origin = (origin + " + 回退补源%s" % added) if origin else "内部回退自算(%s·无注入)" % added
        elif not origin:
            origin = "内部回退自算(无注入·源不足)"
    if not src:
        return None, {}, None, "无源(缺赔率/期望)⚠️"
    ws = {k: W_SRC.get(k, 0.10) for k in src}
    lam = sum(src[k] * ws[k] for k in src) / sum(ws.values())
    # 方案 §4.1 一致性：任一源偏离均值 >0.45 → 该源降权
    bad = [k for k, v in src.items() if abs(v - lam) > 0.45]
    if bad and len(src) > 2:
        ws2 = {k: (ws[k] * 0.5 if k in bad else ws[k]) for k in src}
        lam = sum(src[k] * ws2[k] for k in src) / sum(ws2.values())
    return round(lam, 3), {k: round(v, 3) for k, v in src.items()}, (bad or None), origin


def _est_goalbin(o25):
    if goal_bin_probs is None or o25 is None:
        return None
    try:
        return goal_bin_probs(o25)
    except Exception:
        return None


# ==================== Step 7.1 坐标系转换（方案 §3） ====================
def _t_axis(lam):
    if lam is None:
        return None
    if lam < 1.8:
        return "1"
    if lam < 2.4:
        return "2"
    if lam < 3.2:
        return "3"
    return "4"


def _to_axes(est):
    return {"D": est["D"].get("dir"),
            "M": est["M"].get("all") or [0],
            "T": _t_axis(est["T"].get("lambda")),
            "B": est["B"].get("label")}


def _m_expand_shallow(handi, M, lam_final):
    """🔴V3.5.79 P3: 浅盘主胜 M 扩入净胜2（2:0/3:1 入池·治结构性出局）

    根因: 让-0.25~-0.75 主胜场 M=[-1,0,1] 不含净胜2 → 2:0 永远无法成为候选
    （浅盘主胜恰是 2:0 最高发场景·与 2:1 同量级）
    规则: 浅盘主让(handi∈[-0.75,0))·M含1不含2 → 扩入 +2 档（只扩入不删除）
    """
    if (handi is not None and -0.75 <= handi < 0
            and 2 not in M and 1 in M):
        _M2 = sorted(set(list(M) + [2]))
        # 🔴2026-10-21 判据A（case261 复盘）: 浅盘+大球强(λ≥3.4) → 再扩净胜3
        #   根因: 原实现浅盘仅扩到净胜2 → 真实净胜3（4:1/3:0）**永在池外**
        #   case261 实测: 让-0.25 + O2.5 1.49 + λ 3.87 → M=[-1,0,1,2]（无净胜3）
        #                 → 主锟 2:2（净0）落空·真实 4:1（净+3） → 扩入后 4:1 可入池
        #   铁律: **只扩入不删除**（小分谱系保留·防死锧）
        if lam_final is not None and float(lam_final) >= 3.4 and 3 not in _M2:
            _M2 = sorted(set(list(_M2) + [3]))
        return _M2, True
    return M, False


# ==================== Step 7.2 约束传播（方案 §3·按市场硬度锁定） ====================
def _propagate(axes, est, handi, lambda_final=None, totals_bin=None, p_notes=None,
               step5_dirs=None, t_band=None):
    """🔴 规则1（禁主胜锚·受让场）**动作在此执行**——因其必须参与 T 域推导
    （原实现在 7.3 才改 D 单值 → T 域不随动 + 客胜谱系被浪费 · 2026-10-13 P1-1 修）
    🔴V3.5.90 O-TAIL 标注级观察期: 厚尾场（t_band.tail.flag ∈ {厚尾,强厚尾}）T 域上界放宽到 ≥5/6
    —— 否则交集池 T 域被净胜封顶在 3-4 → 5球谱系进不了池 → 厚尾锚永远无法覆盖（结构性伪消费）
    ⚠️ 观察期 `_TAIL_ACT=False`：仅打印标注建议·不实际放宽（_TAIL_ACT=True 时恢复动作）"""
    logs = []
    # ① D 锁定（方案 §7.2①：LOW 且亚盘反向 → 低置信方向让位于亚盘）
    d_lock = axes["D"]
    # 🔴2026-10-20 P6: Step5 最终方向（含平局并列）透传 → 平局谱系入池
    #   根因: P5 方案 §四 明确「不动 D×M×T 约束传播」→ 下方 d_set=[d_lock] 为单值
    #         → 平局谱系（1:1/0:0）被整段排除出池（255/256 池仅 2 个成员·实测）
    #         → 只能在结算层「手动把 1:1 塞回」= 手工补丁（违反自动化）
    _st5 = None
    if step5_dirs:
        _st5 = [d for d in step5_dirs if d in ("主胜", "平局", "客胜")]
        if _st5:
            if _st5[0] != d_lock:
                logs.append("🔴Step5方向透传: %s（脚本原 D=%s）→ D_lock=%s·D_set 多值" 
                            % ("+".join(_st5), d_lock, _st5[0]))
            d_lock = _st5[0]
    conf_u = str(est["D"].get("conf") or "").upper()
    # 🔴2026-11-03 端到端实测加固：handi 若为 **字符串**（calc_all 曾以 `'%g'` 传出）
    #   → `handi < -0.05` 抛 TypeError → **整个 N23 崩溃**（锚定层/量级分布/宽池全不消费）
    #   实测: case317 复跑报 `'<' not supported between 'str' and 'float'`（L578）
    #   → 此处做 float 容错（调用方已修为 float·本处为第二道防线）
    if handi is not None:
        try:
            handi = float(handi)
        except (TypeError, ValueError):
            logs.append("⚪ handi 无法转 float（%r）→ 亚盘方向锁定跳过" % (handi,))
            handi = None
    ah_dir = None
    if handi is not None:
        ah_dir = "主胜" if handi < -0.05 else ("客胜" if handi > 0.05 else "平局")
    if conf_u == "LOW" and ah_dir and ah_dir != d_lock:
        logs.append("②D×亚盘(方案§7.2①): LOW 档方向(%s)让位于亚盘(%s) → D_lock=%s" % (d_lock, ah_dir, ah_dir))
        d_lock = ah_dir
    # ② M 锁定 + 受让场谱系（方案 §7.2②·case210「受让场禁主胜锚」）
    d_set = list(_st5) if _st5 else [d_lock]                  # 🔴锚侧候选方向集合（可多值谱系）
    m_lock = list(axes["M"])
    if handi is not None and handi > 0:                       # 受让场：禁主胜锚
        drop = [m for m in m_lock if m > 0]
        m_lock = [m for m in m_lock if m <= 0] or [0]
        if d_lock == "主胜":
            d_set = (["平局", "客胜"] if not _st5
                     else ([d for d in _st5 if d != "主胜"] or ["平局", "客胜"]))
            # 🔴P1-1: 谱系多值（非单值「平局」）· step5 透传时剔除主胜方向保留其余
            logs.append("①D×M(规则1✅生效·方案§7.2②): 受让场(handi=%.2f) 且 D=主胜 → **禁主胜锚**·"
                        "锚侧谱系 D_set=%s（方向保留）· 剔除主胜净胜档%s → M_lock=%s"
                        % (handi, d_set, drop or [], m_lock))
        elif d_lock == "平局":
            d_set = ["平局"]
            if drop:
                logs.append("①D×M(规则1✅生效·方案§7.2②): 受让场(handi=%.2f) → 剔除主胜净胜档%s → M_lock=%s"
                            % (handi, drop, m_lock))
        else:                                                 # D=客胜（受让场本命谱系）
            if drop:
                logs.append("①D×M(规则1✅生效·方案§7.2②): 受让场(handi=%.2f) → 剔除主胜净胜档%s → M_lock=%s"
                            % (handi, drop, m_lock))
    if d_lock == "平局" and "平局" not in d_set:
        d_set = ["平局"]
        m_lock = [0]
    # 🔴2026-10-20 P6: 平局谱系入池 → M 必须含净胜 0 档（否则 1:1/0:0 仍被 _build_pool 排除）
    if "平局" in d_set and 0 not in m_lock:
        m_lock = sorted(set(list(m_lock) + [0]))
        logs.append("🔴平局谱系(P6): D_set 含平局 → M_lock 补净胜0档 → %s（1:1/0:0 入池）" % m_lock)
    # 🔴V3.5.79 P4-1: 无亚盘空锚修复——M=[0](纯平局档) + 主胜/客胜方向 → 补方向净胜档
    #   （无亚盘时 margin_candidates 返回 [0]·主胜×M[0] 交集为空 = 结构性缺陷·9.8% 场次）
    if handi is None and list(m_lock) == [0] and d_lock in ("主胜", "客胜"):
        _add_m = 1 if d_lock == "主胜" else -1
        m_lock = sorted(set(list(m_lock) + [_add_m]))
        logs.append("🔴无亚盘兜底(P4-1): handi=None → M=[0] 补净胜%+d档 → M=%s（治空锚）"
                    % (_add_m, m_lock))
    # 🔴V3.5.79 P3-2: 浅盘主胜 M 扩入净胜2（2:0 结构性出局修复）
    _m2, _m2_ch = _m_expand_shallow(handi, m_lock, lambda_final)
    if _m2_ch:
        logs.append("🔴浅盘M×零封(P3): 让%+.2f 主胜 → M 档 %s→%s（2:0/3:1入池）"
                    % (handi, m_lock, _m2))
        m_lock = _m2
    # ③ T 域（方案 §7.2③：由 (D_set, M_lock) 推出的可行总进球集合）
    #    🔴P1-1 修: 由 D_set 推（含平局 → t_lo=0·保留 0:0 出口）；上界仍按净胜档推
    t_lo, t_hi = 0, 6
    absm = [abs(m) for m in m_lock if m != 0] or [0]
    if "平局" not in d_set:
        t_lo = max(t_lo, min(absm))                           # 总进球 ≥ 最小非零净胜
    t_hi = min(t_hi, max(absm) + 2)                           # 净胜 m → t ≤ m+2
    # 🔴V3.5.78: 盘口线驱动上探（大球场抬上界·非大球场零影响）
    #   🔴2026-10-14 修复 D1: 原 `p_notes or []` → 主入口传的 _w_notes=[] 是 falsy →
    #   造临时列表 → notes.append 后丢弃（盘口线留痕全丢）→ 改为**保持引用**
    if p_notes is None:
        p_notes = []
    lock_t = {"T": (t_lo, t_hi)}
    lock_t, _driven = _apply_totals_driven_domain(lock_t, lambda_final, totals_bin, p_notes)
    if _driven:
        t_lo, t_hi = lock_t["T"]
    # ④ B×T 校验（方案 §7.2④）
    bl = axes["B"]
    if bl == "大球强" and t_hi <= 1:
        t_lo, t_hi = 2, max(t_hi, 3)
        logs.append("④T×B: B=大球强 但 T 域≤1 → 以 O2.5 市场为准·T 域=[%d,%d]" % (t_lo, t_hi))
    if bl == "小球强" and t_lo >= 3:
        t_lo, t_hi = 0, 2
        logs.append("④T×B: B=小球强 但 T 域≥3 → 以 O2.5 市场为准·T 域=[%d,%d]" % (t_lo, t_hi))
    # 🔴V3.5.79 P0-3: M 档随 λ 扩展（浅盘大球场·净胜2谱系入池）
    #   浅盘-0.75 大球场 λ=3.8 → M=[-1,0,1] 恒定·2:0/3:1 永远无法成为候选（实证断档）
    #   规则: λ≥3.4 且 M 无非零>1 档 → 扩入 ±1 档（只扩入·不删除·防死锚）
    if lambda_final is not None and float(lambda_final) >= 3.4:
        _absm = [abs(m) for m in m_lock if m != 0]
        if not _absm or max(_absm) < 2:
            _expand = set(m_lock)
            for _m in list(m_lock):
                if _m > 0 and _m + 1 <= 3:
                    _expand.add(_m + 1)
                elif _m < 0 and _m - 1 >= -3:
                    _expand.add(_m - 1)
                elif _m == 0:
                    _expand.add(1)
            _newm = sorted(_expand)
            if _newm != sorted(set(m_lock)):
                logs.append("🔴M×λ(P0-3): λ_final=%.2f≥3.4 → M 档扩展 %s→%s（净胜2谱系入池·只扩入不删除）"
                            % (float(lambda_final), sorted(set(m_lock)), _newm))
                m_lock = _newm
    return {"D": d_lock, "D_set": d_set, "M": sorted(set(m_lock)), "T": (t_lo, t_hi)}, logs


# ==================== Step 7.3 冲突仲裁矩阵（方案 §7.3·6 规则） ====================
def _arbitrate(lock, est, axes, o25, u25, handi, t_band=None):
    """6 规则矩阵。

    🔴 2026-10-13 修（用户审计）：
      · 规则1（禁主胜锚）**动作前置到 7.2 `_propagate`**（须参与 T 域推导）→ 此处仅由 7.2 留痕
      · 规则3/4 于 2026-10-13 按用户裁决【真正生效】（原只打日志未赋值 = 内部不一致）
      · 规则6（查表 vs 市场·**设计即仅提示**）→ 移入 `notes`·**不计入一致度**（原必触发致 HIGH 死档）

    🔴V3.5.90 O-TAIL 最后防线（置于全部规则之后·观察期标注级）：厚尾场（t_band.tail.flag ∈ {厚尾,强厚尾}）
      → T 上界放宽到 ≥5/6 —— 必须放在规则4/5（T×B 压缩）**之后**执行，
        否则「规则4 小球强压 T≤2」会把厚尾 T 域又压回去 = 厚尾信号被后续规则伪消费
      → 保证交集池能装下 5-6 球谱系 → anchor_select O-TAIL 次锚覆盖不被 joint_solver 丢弃
      ⚠️ 观察期 `_TAIL_ACT=False`：仅打印「O-TAIL T域标注(V3.5.90观察期)」·不实际放宽
        （评审 P1-2 标注级 ≥20 场·`_TAIL_ACT=True` 后自动恢复动作）

    返回 (lock, logs(✅生效类·计入一致度), notes(仅提示·不计入))
    """
    logs, notes = [], []
    lam = est["T"].get("lambda")
    b = axes["B"]
    d_set = lock.get("D_set") or [lock.get("D")]
    # 规则1 D×M：受让场禁主胜锚 —— 动作已在 7.2（见 _propagate 日志）；此处仅做一致性复核（防孤儿）
    if handi is not None and handi > 0 and lock.get("D") == "主胜" and "主胜" in d_set:
        lock["D_set"] = ["平局", "客胜"]
        lock["M"] = sorted({m for m in lock["M"] if m <= 0} | {0})
        logs.append("①D×M(规则1✅生效·复核补正): 受让场且 D 仍含主胜 → 强制 D_set=%s（方向保留）" % lock["D_set"])
    # 规则2 D×T：纯主胜且 λ<1.2 → 🔴V3.5.79 P4-3 改「主档1收敛+0:0出口保留」（原收敛唯一1:0=死锚）
    if lock.get("D_set") == ["主胜"] and lam is not None and lam < 1.2:
        lock["M"] = sorted(set([1] + [m for m in lock["M"] if m == 0]))   # 1为主·保留0(0:0出口)
        t_lo2, t_hi2 = lock["T"]
        lock["T"] = (min(t_lo2, 1), min(t_hi2, 2))                        # 上界≤2·保留1:0/2:0
        logs.append("②D×T(规则2✅生效·P4-3防死锚): 主胜且 λ=%.2f<1.2 → M=%s（1为主·0保留）·"
                    "T 域=[%d,%d]（1:0/0:0/2:0 共存·禁唯一1:0）" % (lam, lock["M"], lock["T"][0], lock["T"][1]))
    # 规则3 M×T：净胜 m=2 但 λ≈2.0 → 🔴V3.5.79 P4-2 改「主档收敛+相邻保留」（原收敛唯一2:0=死锚）
    if 2 in lock["M"] and lam is not None and abs(lam - 2.0) <= 0.25:
        _m3 = [2] + [m for m in lock["M"] if m != 2 and abs(m) <= 2]   # 主档2保留·相邻≤2保留
        lock["M"] = sorted(set(_m3)) if _m3 else [2]
        t_lo3, t_hi3 = lock["T"]
        lock["T"] = (t_lo3, max(t_hi3, 3))                              # T 不收敛·保留 2:0/3:1 共存
        logs.append("③M×T(规则3✅生效·P4-2防死锚): 净胜 m=2 且 λ=%.2f≈2.0 → M=%s（主档2+相邻保留）·"
                    "T 域=[%d,%d]（2:0/3:1 共存·禁唯一解）" % (lam, lock["M"], lock["T"][0], lock["T"][1]))
    # 规则4 T×B：λ 判'3' 但 O2.5 判小球强 → 以 O2.5 为准·λ 降档（🔴生效·用户裁决 2026-10-13）
    if axes["T"] == "3" and b == "小球强":
        _lam_cap = 2.4
        _old = lam
        est["T"]["lambda"] = min(float(lam) if lam is not None else _lam_cap, _lam_cap)
        t_lo4, t_hi4 = lock["T"]
        lock["T"] = (t_lo4, min(t_hi4, 2))
        logs.append("④T×B(规则4✅生效): λ=%.2f 判档'3' 但 O2.5 判小球强 → 以市场为准·"
                    "λ 夹至 %.2f(≤2.4·T 轴降为'2')·T 域收紧为 [%d,%d]"
                    % (_old if _old is not None else -1, est["T"]["lambda"],
                       lock["T"][0], lock["T"][1]))
    # 规则5 M×B：净胜 m=3+ 但小球强 → 净胜收敛（3:0 类唯一候选）
    if b == "小球强" and max([abs(m) for m in lock["M"]] or [0]) >= 3:
        lock["M"] = sorted({m for m in lock["M"] if abs(m) <= 2} or {1})
        logs.append("⑤M×B(规则5✅生效): 净胜档≥3 且 小球强 → 净胜收敛为 %s（3:0 类唯一候选）" % lock["M"])
    # 规则6 查表 vs 市场（仅提示·不计一致度）
    gb = est["B"].get("bin")
    if gb:
        notes.append("⑥查表vs市场(规则6·**设计即仅提示·不计入一致度**): goal_bins 档=%s 仅作素材·"
                     "以市场五源融合 λ=%s 为准" % (gb, lam))
    # 🔴V3.5.89 O-TAIL 厚尾 T 域最后防线（置于全部规则之后·用户 2026-11-03「期望3球·真实5-6球怎么办」）
    #   —— 对抗规则4/5（T×B 小球强压缩 T≤2）等所有先行规则对 T 域的收敛。
    #      厚尾场锚必须覆盖尾部档 → 交集池必须能装下 5-6 球谱系，
    #      否则 anchor_select 的 O-TAIL 次锚覆盖在 joint_solver「不在交集池」被静默丢弃
    #      = 打印了厚尾、锚没动（结构性伪消费·端到端审计实抓）
    try:
        _tail_flagA = (t_band or {}).get('tail', {}).get('flag') if isinstance(t_band, dict) else None
        if _tail_flagA in ('厚尾', '强厚尾'):
            _tl_hiA = 6 if _tail_flagA == '强厚尾' else 5
            _tloA, _thiA = lock["T"]
            if _thiA < _tl_hiA:
                if _TAIL_ACT:
                    lock["T"] = (_tloA, _tl_hiA)
                    logs.append("🔴O-TAIL T域最后防线: %s(%s) → T 上界 %d→%d（规则4/5 压缩后回放宽·厚尾场锚必须覆盖尾部档）"
                                % (_tail_flagA,
                                   ('P≥5=%.0f%%' % (t_band.get('tail', {}).get('p5_ge', 0) * 100))
                                   if t_band.get('tail', {}).get('p5_ge') is not None else '',
                                   _thiA, _tl_hiA))
                else:
                    logs.append("🔴O-TAIL T域标注(V3.5.90观察期): %s → 建议 T 上界 ≥%d（当前 %d·_TAIL_ACT=False 不动作）"
                                % (_tail_flagA, _tl_hiA, _thiA))
    except Exception as _eOTAILA:
        notes.append("⚪O-TAIL T域防线三态: %s" % type(_eOTAILA).__name__)
    return lock, logs, notes


# ==================== Step 7.4 自洽比分池生成（方案 §3·交集 + 泊松排序 + 查表集成） ====================
def _pois_pmf(lam, k):
    import math
    if lam is None or lam <= 0:
        lam = 2.6
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def _apply_btts_zero(lh, la, btts_yes=None, btts_no=None, cap=0.4):
    """🔴V3.5.79 P3: BTTS 市场定价 → λa 双向校准（治 2:0 被误判 2:1）

    原理（解析解·已实测 case194/219）:
      泊松BTTS = (1-exp(-λh))·(1-exp(-λa)) 应与市场 BTTS yes 去水概率一致
      → λa = -ln(1 - p_yes/(1-exp(-λh)))
      · 零封倾向(BTTS no 高·yes 低) → λa 压低 → 2:0 反超 2:1
      · 双方进球倾向(BTTS yes 高)   → λa 抬升 → 2:1 合理优先（双向校准·不硬压）

    防死锚:
      ① 只动 λa·绝不动 λh（净胜方向保留·不逆市场）
      ② 修正量封顶 ±0.4（防单源过度修正）
      ③ 缺 BTTS 零影响·无解析解(市场BTTS超λh单边极限)零影响
      ④ 与大小球/让球约束正交——只影响同净胜档内 0球 vs 1球 排序
    返回 (新la, 修正量, note)
    """
    if not (btts_yes and btts_no):
        return la, 0.0, None
    try:
        iy, inn = 1.0 / float(btts_yes), 1.0 / float(btts_no)
        p_yes = iy / (iy + inn)                     # BTTS yes 去水概率
        p_no = inn / (iy + inn)                     # BTTS no = 零封概率
    except Exception:
        return la, 0.0, None
    if not (0.02 < p_yes < 0.98):
        return la, 0.0, None
    import math
    ph = 1 - math.exp(-lh)
    if ph <= 0 or p_yes >= ph:                      # 无解 → 不修正
        return la, 0.0, None
    target = -math.log(1 - p_yes / ph)              # 解析解: 泊松BTTS=市场BTTS
    delta = max(-cap, min(cap, target - la))
    if abs(delta) < 0.05:
        return la, 0.0, None
    la_new = round(max(0.1, la + delta), 3)
    note = "🔴零封修正(P3): BTTS no=%.0f%% → λa %.2f→%.2f(Δ%+.2f)" % (
        p_no * 100, la, la_new, delta)
    return la_new, round(delta, 3), note


def _solve_lams(oh, od, oa, lam_total):
    """λh/λa 分配（方案 §7.4：泊松排序取五源融合 λ）"""
    a, b, c = _f(oh), _f(od), _f(oa)
    lam_total = lam_total or 2.6
    if not (a and b and c):
        return lam_total * 0.56, lam_total * 0.44, None
    ia, ib, ic = 1.0 / a, 1.0 / b, 1.0 / c
    s = ia + ib + ic
    ph, pd, pa = ia / s, ib / s, ic / s
    net = (ph - pa) * 2.2
    return (max(0.15, (lam_total + net) / 2.0), max(0.15, (lam_total - net) / 2.0),
            {"pH": round(ph * 100, 1), "pD": round(pd * 100, 1), "pA": round(pa * 100, 1)})


def _table_in_pool(pool_scores, lock, o25, league):
    """方案 §7.4 查表集成：score_depth_lookup 只在此交集内取 anchor/second/third
       一致 → 采信；不一致 → 以交集为准（市场硬度更高）"""
    hits, conflicts = [], []
    for m in (lock["M"] or [0]):
        try:
            lb = score_depth_lookup(m, o25, league=league) if score_depth_lookup is not None else None
        except Exception:
            lb = None
        if not isinstance(lb, dict):
            continue
        for key in ("anchor", "second", "third"):
            s = lb.get(key)
            if not s:
                continue
            s = str(s).replace("-", ":")
            if s in pool_scores:
                hits.append(s)
            else:
                conflicts.append(s)
    return hits, conflicts


def _pair_cover_select(ranked, po, lock=None, cs_probs=None, topk=12, meta_out=None):
    """🔴2026-10-25 机制化「双锚联合覆盖」（用户指令：**两个比分中一个准确即可**·非仅口径断言）

    原机制缺陷: a1=ranked[0], a2=ranked[1]（单锚证据排序取前二）→ **两锚常挤在同一角落**
      · case279: 主锚 2:0 / 次锚 2:1 = 都是「主胜+零封型」→ 实际 4:0 双锚全失
      · case281: 主锚 2:1 / 次锚 1:0（覆盖 26.6%）→ 而 1:1+1:0 覆盖 31.5%（同样含 1:0 但更宽）

    新机制: 在 ranked 前 topk 内**枚举所有对**，最大化
        cover = P(A) + P(B) + 多样性奖励
    多样性奖励（防同角落）:
        方向不同(D 不同)                 +0.015
        |净胜| 不同                      +0.008
        总进球袋不同(≤1 / 2 / 3 / ≥4)      +0.008
        同方向且同净胜档(近等价比分)        −0.030
    约束不变（硬约束在调用方 anchor_market_check / R10 交集后执行）:
        返回 (主锚, 次锚, meta)  —— 主锚 = 对中概率高者（主/次【同级】·仅输出排序）
    """
    import math
    lh = float(po.get("lam_h") or 2.0)
    la = float(po.get("lam_a") or 2.0)

    def _pmf(h, a):
        return (math.exp(-lh) * (lh ** h) / math.factorial(h)) * \
               (math.exp(-la) * (la ** a) / math.factorial(a))

    def _p(sc):
        try:
            if cs_probs and sc in cs_probs:
                return float(cs_probs[sc])
            h, a = map(int, str(sc).split(":"))
            return _pmf(h, a)
        except Exception:
            return 0.0

    def _bag(t):
        return 0 if t <= 1 else (1 if t == 2 else (2 if t == 3 else 3))

    # 🔴2026-10-25: R10-4 硬约束 —— P(T≥4) ≥18% 时双锚**须含 3+ 球**
    #   否则"覆盖最大化"会把 3 球锚挤掉（回放实测: case280 会从 2:1 换到 1:0）
    #   口径: 用同一 λh+λa 的泊松尾概率（与 N23/goal_bins 同源·不引入新参数）
    _lam_t = lh + la
    _p_lt4 = sum(math.exp(-_lam_t) * (_lam_t ** _k) / math.factorial(_k) for _k in range(4))
    need_big3 = (1.0 - _p_lt4) >= 0.18

    seq = [s for s, _ev in (ranked or [])][:max(topk, 2)]
    if len(seq) < 2:
        return (seq[0] if seq else None, None, {"pair": seq, "pair_cover": None})

    best = None
    for i in range(len(seq)):
        for j in range(i + 1, len(seq)):
            A, B = seq[i], seq[j]
            try:
                ha, aa = map(int, A.split(":"))
                hb, ab = map(int, B.split(":"))
            except Exception:
                continue
            na, nb = ha - aa, hb - ab
            ta, tb = ha + aa, hb + ab
            da = "主胜" if na > 0 else ("平局" if na == 0 else "客胜")
            db = "主胜" if nb > 0 else ("平局" if nb == 0 else "客胜")
            bon = 0.0
            if da != db:
                bon += 0.015
            if abs(na) != abs(nb):
                bon += 0.008
            if _bag(ta) != _bag(tb):
                bon += 0.008
            if da == db and na == nb:
                bon -= 0.030
            # 🔴2026-10-25 权衡（回放实证）: R10-4「须含 3+ 球」**降为加分项**（+0.010）而非硬约束。
            #   硬约束会把命中的低分锚挤掉（case281: 1:1+1:0 命中 1:0 → 被强换成 1:1+2:1 未中）。
            #   用户目标=「两个比分中一个准确即可」→ **覆盖最大化为主**·3+ 球锚为次（大球场自然胜出）
            if need_big3 and max(ta, tb) >= 3:
                bon += 0.010
            cov = _p(A) + _p(B) + bon
            if best is None or cov > best[0]:
                best = (cov, A, B, bon, _p(A) + _p(B))

    if not best:
        return (seq[0], seq[1], {"pair": [seq[0], seq[1]], "pair_cover": None})

    cov, A, B, bon, raw = best
    if _p(B) > _p(A):                     # 主锚 = 对中概率高者
        A, B = B, A
    meta = {"pair": [A, B], "pair_cover": round(cov, 4), "need_big3": need_big3,
            "pair_raw": round(raw, 4), "pair_bonus": round(bon, 4),
            "pair_p": [round(_p(A), 4), round(_p(B), 4)]}
    if meta_out is not None:
        meta_out.update(meta)
    return (A, B, meta)


def _build_pool(lock, est, oh, od, oa, o25=None, league=None, max_goal=6,
                lam_pois=None, btts_yes=None, btts_no=None):
    """🔴P1-1 修: 按 `D_set`（多值谱系）过滤·非单值 D（受让场「平局/客胜谱系」方生效）
    🔴V3.5.79 P0-2: 泊松 λ 口径统一 + P3: BTTS 零封双向校准"""
    lam_total = lam_pois if lam_pois is not None else est["T"].get("lambda")
    lam_total = float(lam_total) if lam_total is not None else 2.6
    lh, la, dv = _solve_lams(oh, od, oa, lam_total)
    # 🔴V3.5.79 P3-1: BTTS 双向校准（零封→压λa·双方进球→抬λa）
    la, _bt_delta, _bt_note = _apply_btts_zero(lh, la, btts_yes, btts_no)
    t_lo, t_hi = lock["T"]
    d_set = lock.get("D_set") or [lock.get("D")]
    pool = []
    for h in range(max_goal + 1):
        for a in range(max_goal + 1):
            d = "主胜" if h > a else ("平局" if h == a else "客胜")
            m = h - a
            if d not in d_set:
                continue
            if d == "平局":
                if 0 not in lock["M"]:
                    continue
            else:
                if m not in lock["M"]:
                    continue
            t = h + a
            if not (t_lo <= t <= t_hi):
                continue
            p = _pois_pmf(lh, h) * _pois_pmf(la, a)
            pool.append({"score": "%d:%d" % (h, a), "h": h, "a": a, "d": d,
                         "m": m, "t": t, "p": p})
    pool.sort(key=lambda x: -x["p"])
    tot = sum(x["p"] for x in pool) or 1.0
    for x in pool:
        x["p_pct"] = round(x["p"] / tot * 100, 2)
    hits, conflicts = _table_in_pool({x["score"] for x in pool}, lock, o25, league)
    return pool, {"lam_h": round(lh, 3), "lam_a": round(la, 3), "devig": dv,
                  "table_hits": hits, "table_conflicts": conflicts,
                  "btts_zero": _bt_note}                    # 🔴V3.5.79 P3 留痕


# ==================== 主入口（方案 §5 接口） ====================
def joint_anchor(oh, od, oa, handi=None, o25=None, u25=None, ou_line=None,
                 lam_h=None, lam_a=None, league=None, src_lam=None,
                 lambda_final=None, totals_bin=None,
                 ah_wh=None, ah_wa=None,                       # 🔴V3.5.79 P1: 让球双水位
                 cs_odds=None,                                  # 🔴V3.5.79 P2: 波胆赔率表
                 btts_yes=None, btts_no=None,                   # 🔴V3.5.79 P3: BTTS 市场定价
                 step5_dirs=None,                               # 🔴2026-10-20 P6: Step5 方向（含平局并列）
                 jc_cs=None,                                    # 🔴2026-10-20 P6: 竞彩比分盘去水 P_i
                 htft=None,                                    # 🔴2026-10-20 P7: 半全场 9 格
                 vert=None,                                   # 🔴2026-10-20 P8: 纵向信号
                 tad_h=None, tad_a=None,                       # 🔴批次2: N27 攻防档案
                 t_band=None,                                  # 🔴V3.5.87 量级档（方法二）
                 def_dual=None,                                # 🔴2026-11-03 O-BIG-1 双方防线双伤
                 market_matrix=None,
  second_min_goals=None,                      # 🔴2026-11-01 R-ANCHOR-BIG: 次锚最小总进球（大球场次上探·原只打印不动作）
  first_min_goals=None,
  line_eq=None):                              # 🔴V3.5.91: 真实盘口均衡线（P52 分级用·禁拿 E[T] 顶替）                      # 🔴2026-11-01 P52 主锚最低球数（六级分级驱动·原只约束次锚）
    if _IMP_ERR:
        return {"ok": False, "reason": "依赖导入失败: %s" % _IMP_ERR}
    est = {"D": {}, "M": {}, "T": {}, "B": {}}
    # —— Step 7.0 并行估值 ——
    est["D"] = _est_direction(oh, od, oa, o25, league)
    p_over = _devig_over(o25, u25)
    lam, srcs, bad, lam_origin = _est_lambda(o25, u25, ou_line, lam_h, lam_a, src_lam)
    est["T"] = {"lambda": lam, "src": srcs, "bad_src": bad, "origin": lam_origin}
    # 🔴2026-10-17 口径统一(P0): Step6.5 λ_final（含盘口移动 λ_move）为唯一权威 λ
    #   原: T 的 λ 走五源加权(line/pois/water 均未含盘口移动) → 与 Step6.5 形成 0.30 球口径分裂
    #       实测 case248/249: N23 2.905 vs Step6.5 2.608（差 0.297·超 0.20 门禁）
    if lambda_final is not None:
        try:
            _lf = float(lambda_final)
            _lo = lam
            if _lo is None or abs(_lf - float(_lo)) > 0.02:
                est['T']['lambda'] = _lf
                est['T']['lam_final_override'] = {'from': _lo, 'to': _lf}
                lam = _lf
                est['T']['origin'] = ((str(lam_origin or '') + '+Step6.5 λ_final 权威').strip('+'))
        except Exception:
            pass
    est["M"] = _est_margin(handi, lam, ah_wh, ah_wa,
                            ah_vert=(vert or {}).get("ah_vert"))   # 🔴P1 + 🔴P8 升降盘
    gb = _est_goalbin(o25)
    est["B"] = {"label": _b_label_fallback(o25, p_over,
                                           ou_vert=(vert or {}).get("ou_vert")),  # 🔴V3.5.78 + 🔴P8
                "p_over_fair": (round(p_over, 4) if p_over else None),
                "bin": (gb or {}).get("band") if isinstance(gb, dict) else None, "goalbin": gb}
    if est["D"].get("dir") is None and lam is None:
        return {"ok": False, "reason": "四要素估值全空（缺赔率/期望源）", "est": est}
    # —— Step 7.1 坐标转换 ——
    axes = _to_axes(est)
    # —— Step 7.2 约束传播（含规则1·受让场谱系） ——
    _w_notes = []                                            # 🔴V3.5.78: 盘口线驱动留痕（仅提示·不计入一致度）
    lock, w_logs = _propagate(axes, est, handi, lambda_final, totals_bin, _w_notes,
                              step5_dirs=step5_dirs, t_band=t_band)   # 🔴V3.5.89 O-TAIL T域放宽
    # —— Step 7.3 冲突仲裁（生效类 logs / 仅提示 notes） ——
    lock, a_logs, a_notes = _arbitrate(lock, est, axes, o25, u25, handi,
                                       t_band=t_band)   # 🔴V3.5.89 O-TAIL T域最后防线
    if _w_notes:                                             # 🔴V3.5.78: 合并盘口线留痕（仅提示）
        a_notes = list(a_notes or []) + _w_notes
    _wm = est["M"].get("water")                              # 🔴V3.5.79 P1: 让球水位留痕（仅提示·不计一致度）
    if _wm:
        a_notes = list(a_notes or []) + [_wm["note"]]
    # —— Step 7.4 交集池 + 泊松排序 ——
    # 🔴V3.5.79 P2: 波胆解析 + 深盘 M 档扩入（防边缘错位·国米2-0教训）
    _cs = _cs_market_probs(cs_odds) if cs_odds else None
    if _cs and handi is not None and abs(handi) >= 1.5:
        _top1_m = int(_cs["top5"][0][0].split('-')[0]) - int(_cs["top5"][0][0].split('-')[1])
        if _top1_m not in lock["M"]:
            lock["M"] = sorted(list(lock["M"]) + [_top1_m])   # 只扩入·不删除·防死锚
    # 🔴P24(2026-10-28 用户指令「市场信号主导·结合期望进球」): M 域按市场净胜分布放宽
    #   原理: 固定「主档±1」挡掉市场认为概率同样高的档（289 客胜净2 19.0% ≈ 净1 21.2% → 0:2 进不了池）
    #   纪律: 阈值=现有档最高概率×P24_M_RATIO ｜ 方向符号过滤（不破 Step5 方向）｜ 只扩入不删除 ｜ 上限 P24_M_MAX
    if market_matrix:
        try:
            _mp24 = (market_matrix.get("margin") or {}).get("p") or {}
            _mp24 = {int(_k): float(_v) for _k, _v in _mp24.items() if _v}
            if _mp24:
                _ds24 = lock.get("D_set") or [lock.get("D")]
                _sgn24 = set()
                for _d24 in _ds24:
                    _s24 = str(_d24)
                    if "主" in _s24:
                        _sgn24.add(1)
                    elif "客" in _s24:
                        _sgn24.add(-1)
                    elif "平" in _s24:
                        _sgn24.add(0)
                # 🔴P24-fix: 基准只取「同方向符号」档（平局档不抬阈值·287 教训：M[-1,0] 平局27%最高→阈值16.2%差点挡掉客2 15%）
                _same24 = [_m for _m in lock["M"]
                           if ((_m > 0 and 1 in _sgn24) or (_m < 0 and -1 in _sgn24)
                               or (_m == 0 and 0 in _sgn24))]
                _base24 = _same24 or list(lock["M"])
                _pcur24 = max([_mp24.get(_m, 0.0) for _m in _base24] or [0.0])
                _thr24 = _pcur24 * P24_M_RATIO
                _cand24 = [(_p, _m) for _m, _p in _mp24.items()
                           if _p >= _thr24 and _p > 0 and _m not in lock["M"]
                           and ((_m > 0 and 1 in _sgn24) or (_m < 0 and -1 in _sgn24)
                                or (_m == 0 and 0 in _sgn24))]
                _cand24.sort(reverse=True)
                _add24 = sorted({_m for _p, _m in _cand24[:P24_M_MAX]})
                if _add24:
                    _mold24 = list(lock["M"])
                    _merged24 = set(lock["M"]) | set(_add24)
                    # 🔴P27(2026-10-28 机械锚定自查): **同号段补齐中间档**（防谱系断裂）
                    #   罗马场教训: 净4(19.5%)入域但净3(11.3%)被阈值挡 → M=[1,2,4] 跳过3
                    #   → 3:0 被池排除 → 被迫锚 4:0（偏离期望 1.0 而非 0）
                    _fill24 = set()
                    for _sg in (1, -1):
                        _seg = sorted([_m for _m in _merged24 if _m * _sg > 0])
                        if len(_seg) >= 2:
                            _lo = min(abs(_m) for _m in _seg)
                            _hi = max(abs(_m) for _m in _seg)
                            for _k in range(_lo, _hi + 1):
                                _fill24.add(_k * _sg)
                    _newfill = sorted(_fill24 - _merged24)
                    lock["M"] = sorted(_merged24 | _fill24)
                    if _newfill:
                        a_notes = list(a_notes or []) + [
                            "P27 谱系连续性补齐: 新增 %s（原 %s → %s·防跳过中间档致锚极端）"
                            % (_newfill, sorted(_merged24), lock["M"])]
                    a_notes = list(a_notes or []) + [
                        "P24 M 域按市场净胜分布放宽: %s → %s（新增 %s·阈值 %.1f%%=现档最高×%.1f·方向[%s]过滤·只扩入不删除）"
                        % (_mold24, lock["M"], _add24, _thr24 * 100, P24_M_RATIO,
                           "/".join(str(_x) for _x in _ds24))]
        except Exception as _e24:
            a_notes = list(a_notes or []) + ["P24 M 域放宽异常(已跳过·不影响主流程): %s" % str(_e24)[:60]]
    _cs_cand = _cs_select(_cs, lock["M"], lock["T"]) if _cs else None
    pool, po = _build_pool(lock, est, oh, od, oa, o25=o25, league=league,
                           lam_pois=lambda_final,                      # 🔴P0-2: λ 口径统一
                           btts_yes=btts_yes, btts_no=btts_no)         # 🔴P3: BTTS 校准
    # 🔴V3.5.78 防死锚: 证据加权排序选锚（替代纯泊松 Top1/Top2·方案 P6）
    _bmeta = {}                                              # 🔴P5: 市场基线留痕容器
    # 🔴P39（2026-10-30 批次5）: **F1 红牌率接入**（原 `adjust_by_red` 全库零调用=死代码）
    #   条件: 联赛红牌率≥20（西甲23.2/意甲22.7/法甲20.0）+ 主胜赔<1.8 + O2.5<1.8
    #   动作: 高比分候选（总进球≥3）权重×1.2·低比分（≤1）×0.85·重排（方向性·禁机械1:0→2:1）
    _f1_red39 = False
    try:
        from calc_v3572 import adjust_by_red as _abr39
        _rk39, _f1_red39 = _abr39(league, oh, o25, ranked)
        if _f1_red39:
            ranked = _rk39
            a_notes = list(a_notes or []) + [
                "🔴F1 红牌率触发（%s 红牌率>=20 + 主赔<1.8 + O2.5<1.8）→ 高比分候选×1.2 / 低比分×0.85" % league]
        else:
            # 🔴P39-fix: 未触发也须留痕（防「未列出=未执行」）
            _why39 = ("联赛红牌率 %.1f" % (__import__("calc_v3572").RED_RATE.get(league, 0)) if True else "")
            _r39 = __import__("calc_v3572").RED_RATE.get(league, 0)
            _p39 = []
            if _r39 < 20: _p39.append("红牌率%.1f<20" % _r39)
            if oh and float(oh) >= 1.8: _p39.append("主赔%.2f>=1.8非深盘" % float(oh))
            if o25 and float(o25) >= 1.8: _p39.append("O2.5 %.2f>=1.8非大球强" % float(o25))
            a_notes = list(a_notes or []) + [
                "⚪F1 红牌率未触发（联赛红牌率 %.1f）：%s" % (_r39, " / ".join(_p39) or "条件未详")]
    except Exception:
        _f1_red39 = False
    ranked = _evidence_rank(pool, lock, est, o25, league, lambda_final,
                            cs_cand=_cs_cand, cs=_cs, meta_out=_bmeta,                        # 🔴P2: 波胆精选证据
                            jc_cs=jc_cs,                                                    # 🔴P6: 竞彩CS证据
                            htft=htft,                                                     # 🔴P7: 半全场证据
                            vert=vert,                                                     # 🔴P8: 纵向证据
                            market_matrix=market_matrix,                                   # 🔴P10: E0 市场矩阵
                            handi=handi)                                                   # 🔴P25: 让球深度信号
    # 🔴2026-10-25 双锚覆盖（P11 修正：**仅作「矩阵未启用」兜底**）
    #   矩阵启用时最终双锚由 R10(主锚)+R12(次锚) 决定；此处结果只作 _pcmeta 对照留痕
    _pcmeta = {}
    _a1_pc, _a2_pc, _pcmeta = _pair_cover_select(
        ranked, po, lock, cs_probs=(_cs or {}).get("probs"), meta_out=_pcmeta)
    a1, a2 = _a1_pc, _a2_pc
    a3 = next((_s for _s, _e in (ranked or []) if _s not in (a1, a2)), None)
    # 🔴P11 灰度开关提前读取（决定 R10-2 / R11 的旧次锚逻辑是否生效）
    #   off  = 完全旧行为（R10-2 邻域次锚 + R11 硬替换）
    #   auto = 旧行为 + R12 只留痕（默认·回测达标前）
    #   on   = R12 接管次锚（R10-2 / R11 不再覆盖）
    _r12m = "auto"
    try:
        import json as _j12m
        import os as _o12m
        _p12m = _o12m.path.join(_o12m.path.dirname(_o12m.path.abspath(__file__)), "p10_config.json")
        if _o12m.path.exists(_p12m):
            _r12m = str((_j12m.load(io.open(_p12m, encoding="utf-8")).get("r12_pair_cover")) or "auto").lower()
    except Exception:
        _r12m = "auto"
    if _pcmeta.get("pair_cover") is not None:
        a_notes = list(a_notes or []) + [
            "双锚覆盖: %s + %s ｜ 联合 %.1f%%（纯概率 %.1f%% + 多样性 %.1f%%）"
            % (_pcmeta["pair"][0], _pcmeta["pair"][1],
               _pcmeta["pair_cover"] * 100, _pcmeta["pair_raw"] * 100,
               _pcmeta["pair_bonus"] * 100)]
    ev_map = dict(ranked)
    # 🔴P10-R10 判定标准层（方案 §4.7/§5.6·2026-10-25 补强）
    #   拿到市场分布后按 R10-1~R10-9 定主锚/次锚/可信度 → **与交集池求交**（受让禁主胜锚·M/T 域·防死锚）
    _r10 = None
    _r10_trust = None
    _mmF = _bmeta.get("market_matrix_full")
    # 🔴P10-FINAL R11: 单队进球/零封（直盘 TT 0.5 + BTTS）—— **先算**（R10-3 需据此降级·§6.3 接线1）
    _r11 = None
    if _mmF:
        try:
            import market_distribution as _mdR11m
            _r11 = _mdR11m.team_zero_decision(
                tt_full=(_mmF or {}).get("tt_full"),
                btts=({"yes": btts_yes, "no": btts_no} if (btts_yes and btts_no) else None),
                cs_full=cs_odds,
                tt_h_row=((_mmF.get("team") or {}).get("home")),
                tt_a_row=((_mmF.get("team") or {}).get("away")),
                handi=handi)
        except Exception as _eR11:
            import traceback as _tbR11
            _lnR11 = _tbR11.extract_tb(_eR11.__traceback__)[-1]
            a_notes = list(a_notes or []) + [
                "R11 判定异常(%s: %s @%s:%d) → 零封回退矩阵后验"
                % (type(_eR11).__name__, _eR11,
                   __import__("os").path.basename(_lnR11.filename), _lnR11.lineno)]
            _r11 = None
    if _mmF:
        try:
            import market_distribution as _mdR10m
            _r10 = _mdR10m.anchor_select(
                _mmF, oh=oh, od=od, oa=oa, handi=handi,
                bt_yes=btts_yes, bt_no=btts_no,
                cs_vert=(vert or {}).get("cs_vert"),
                ah_vert=(vert or {}).get("ah_vert"),
                ou_vert=(vert or {}).get("ou_vert"),          # 🔴P35: 大小球纵向
                vert_n=(vert or {}).get("n_points"),          # 🔴P35: 时点数（≥3 加权）
                tad_h=tad_h, tad_a=tad_a,                    # 🔴批次2: N27 攻防双向档案
                lam=(lambda_final if lambda_final is not None else est["T"].get("lambda")),
                cs_full=cs_odds, pool=[x["score"] for x in pool],
                zero_direct=_r11,          # 🔴P10-FINAL: R11 直盘 → R10-3 降级 + 四维交集
                t_band=t_band,             # 🔴V3.5.87 量级档前置（先定量级再选比分）
                def_dual=def_dual,         # 🔴2026-11-03 O-BIG-1 宽池扩档
                line_eq=line_eq,           # 🔴V3.5.91 真实均衡线（P52 分级·治 E[T] 顶替）
                vert_std=((vert or {}).get("std")),  # 🔴V3.5.92 纵向统一标准结构
                dir_first=((step5_dirs or [None])[0]))  # 🔴2026-11-03 O-ANCHOR-1 方向首选
            _pset = {x["score"] for x in pool}
            _R1, _R2 = _r10.get("anchor_1st"), _r10.get("anchor_2nd")
            # 🔴V3.5.89 O-TAIL 伪消费防线: 厚尾场 R2 若不在交集池（M/T 域硬约束排除），
            #   将 O-TAIL 已改的尾部谱系次锚**补入交集池**（只补入·不删除·防死锚）
            #   —— 否则 L1192「_R2 not in _pset → 回退 pool 第一个」会静默丢掉厚尾覆盖
            #      = 打印了厚尾、次锚被换回低分（结构性伪消费·端到端审计实抓）
            try:
                _tail9 = (t_band or {}).get('tail', {}).get('flag') if isinstance(t_band, dict) else None
                if (_tail9 in ('厚尾', '强厚尾') and _R2 and _R2 not in _pset
                        and sum(int(x) for x in _R2.split(":")) >= 5):
                    pool.append({"score": _R2,
                                 "h": int(_R2.split(":")[0]), "a": int(_R2.split(":")[1]),
                                 "d": "主胜" if int(_R2.split(":")[0]) > int(_R2.split(":")[1])
                                 else ("平局" if int(_R2.split(":")[0]) == int(_R2.split(":")[1]) else "客胜"),
                                 "m": int(_R2.split(":")[0]) - int(_R2.split(":")[1]),
                                 "t": int(_R2.split(":")[0]) + int(_R2.split(":")[1]), "p": 0.0})
                    _pset.add(_R2)
                    a_notes = list(a_notes or []) + [
                        "🔴O-TAIL 尾锚补池: %s（厚尾场 M/T 域外·补入交集池·只补入不删除）" % _R2]
            except Exception as _eOTAIL:
                a_notes = list(a_notes or []) + ["⚪O-TAIL 补池三态: %s" % type(_eOTAIL).__name__]
            if _R1 and _R1 not in _pset:
                a_notes = list(a_notes or []) + [
                    "R10 主锚 %s 不在交集池 → 回退矩阵排序（受让禁主胜锚/域约束·防死锚）" % _R1]
                _R1 = None
            if _R2 and (_R2 not in _pset or _R2 == _R1):
                _R2 = next((x["score"] for x in pool if x["score"] != _R1), None)
            if _R1:
                a1 = _R1
                # 🔴P11(2026-10-26): **R10 只定主锚** —— 删除「if _R2: a2 = _R2」
                #   原 R10-2 次锚 = T*±1∩M*±1 四维交集次高分 = 又挤回主锚同角落（双锚高相关）
                #   → 次锚改由 R12（矩阵后验 + 数据驱动分散）决定；_R2 仅作参考留痕
                _r10_anchor2_ref = _R2
                if _r12m != "on" and _R2:
                    a2 = _R2          # 🔴off/auto = 旧行为（R10-2 邻域次锚）
                elif a2 == a1:
                    a2 = next((x["score"] for x in pool if x["score"] != a1), None)
                _r10_trust = _r10.get("trust")
                _r10n = list(_r10.get("notes") or [])
                a_notes = list(a_notes or []) + [
                    "R10判定层: 主锚 %s / 次锚 %s · 可信度 %s%s · %s"
                    % (a1, a2, _r10_trust,
                       ("·双主锚" if _r10.get("double") else "") + ("·宽池" if _r10.get("wide") else ""),
                       " ".join(_r10n[:2]))]
                # 🔴2026-11-03 端到端审计实抓（第 3 层伪消费）：原只取 notes[:2]，
                #   而 anchor_select 的 notes 顺序里 **P52 分级/宽池补入/门槛口径/拒收** 都在第 3 条之后
                #   → 全被截掉 → 用户只看到「补入 2:4(6球)」看不到依据，我也看不到拒收理由。
                #   现全量追加（带缩进·可审计），让「宽池为什么是这些比分」在 calc_all/raw 里可见。
                for _n10 in _r10n:
                    if any(_k10 in _n10 for _k10 in ('P52', '宽池', '门槛口径')):
                        a_notes = list(a_notes or []) + ["  " + _n10]
                # 🔴P28(2026-10-28 用户裁定「摆脱机械锚定·可设比分池但不能机械锚定某一个」):
                #   输出比分池 + 每个比分的市场信号依据；主锚=池内支持度第一(非唯一结论)
                _pool28 = _r10.get("score_pool") or []
                if _pool28:
                    a_notes = list(a_notes or []) + [
                        "🔴P28 比分池(按市场信号支持度·共%d个·主锚仅指池内第一·非唯一结论)" % len(_pool28)]
                    for _i28, _x28 in enumerate(_pool28[:6]):
                        # 🔴P46(2026-10-30): 「矩阵」「波胆排名」= 市场直接读数·**前置显示**
                        #   原 [:120] 截断会把二者切掉 → 审计看不到 = 判未执行
                        _wd28 = _x28.get("why") or {}
                        _first28 = [_k for _k in ("矩阵", "波胆排名") if _k in _wd28]
                        _rest28 = [_k for _k in _wd28 if _k not in _first28]
                        _why28 = " · ".join("%s:%s" % (_k28, _wd28[_k28][1])
                                            for _k28 in (_first28 + _rest28))
                        a_notes = list(a_notes or []) + [
                            "   %d) %-5s 支持度%.3f ｜ %s" % (_i28 + 1, _x28["score"],
                                                             _x28.get("support", 0), _why28[:210])]
                    if len(_pool28) > 6:
                        a_notes = list(a_notes or []) + [
                            "   ...池内另有 %s（未淘汰·仅支持度靠后，请结合基本面判断）"
                            % "/".join(x["score"] for x in _pool28[6:])]
                for _z in (_r10.get("zero_notes") or [])[:2]:
                    a_notes = list(a_notes or []) + ["  " + _z]
                for _b in (_r10.get("big_notes") or [])[:2]:
                    a_notes = list(a_notes or []) + ["  " + _b]
                if _r10.get("masked"):
                    a_notes = list(a_notes or []) + [
                        "R10 池外高分被屏蔽（矩阵高但域不允许）: %s" % "/".join(_r10["masked"])]
            else:
                a_notes = list(a_notes or []) + ["R10: 无可用池内锚 → 保留矩阵排序结果"]
        except Exception as _eR:
            import traceback as _tbR
            _lnR = _tbR.extract_tb(_eR.__traceback__)[-1]
            a_notes = list(a_notes or []) + [
                "R10 判定层异常(%s: %s @%s:%d) → 保留矩阵排序结果"
                % (type(_eR).__name__, _eR,
                   __import__("os").path.basename(_lnR.filename), _lnR.lineno)]
            _r10 = None
    # 🔴P10-FINAL R11 谱系对齐（只调**次锚/候选池**·不推翻 R10 主锚方向·防死锚·§6.3 接线3）
    if isinstance(_r11, dict) and _r11.get("health") in ("ok", "weak") and a1:
        try:
            _sc = _r11.get("spectrum_code")
            _dir1 = ("主胜" if int(a1.split(":")[0]) > int(a1.split(":")[1])
                     else ("平局" if int(a1.split(":")[0]) == int(a1.split(":")[1]) else "客胜"))
            _cand11 = []
            if _sc in ("strong_away_clean", "weak_away_clean"):
                _cand11 = [x["score"] for x in pool if x["score"].split(":")[1] == "0"]
                if _dir1 == "客胜":
                    _cand11 = []                  # 主锚客胜 + 主队零封谱系 → 不对齐（避免方向矛盾）
            elif _sc in ("strong_home_clean", "weak_home_clean"):
                _cand11 = [x["score"] for x in pool if x["score"].split(":")[0] == "0"]
                if _dir1 == "主胜":
                    _cand11 = []
            elif _sc == "btts":
                _cand11 = [x["score"] for x in pool
                           if x["score"].split(":")[0] != "0" and x["score"].split(":")[1] != "0"]
            _cand11 = [s for s in _cand11 if s != a1]
            # 🔴P11(2026-10-26): **删除 R11 硬替换 a2**（原 `a2 = _cand11[0]` 不看概率/覆盖增益）
            #   谱系信息改为传给 R12（r11 参数），由 R12 用矩阵后验 + 自适应奖励裁决
            _r11_cand_ref = _cand11[:5]
            # 🔴V3.5.89 O-TAIL 豁免（用户 2026-11-03「新升级一定不要伪消费」）:
            #   R11 谱系对齐在 anchor_select O-TAIL **之后**执行 → 会把厚尾场已覆盖的
            #   ≥5球次锚（如 2:3）硬替换成零封谱系低分（如 0:1）= 打印了厚尾、次锚被换回
            #   → 厚尾场 O-TAIL 优先级 > R11（厚尾覆盖=用户硬要求·R11 零封=软提示）
            _tail_exempt11 = False
            try:
                _tf11 = (t_band or {}).get('tail', {}).get('flag') if isinstance(t_band, dict) else None
                if (_tf11 in ('厚尾', '强厚尾') and a2 and
                        sum(int(x) for x in a2.split(":")) >= 5):
                    _tail_exempt11 = True
            except Exception:
                _tail_exempt11 = False
            if _cand11 and a2 not in _cand11 and _r12m != "on" and not _tail_exempt11:
                a_notes = list(a_notes or []) + [
                    "R11 谱系对齐次锚: %s → %s（谱系=%s·**主锚方向不变**·防死锚·off/auto 旧行为）"
                    % (a2, _cand11[0], _r11.get("spectrum"))]
                a2 = _cand11[0]
            elif _cand11 and _tail_exempt11:
                a_notes = list(a_notes or []) + [
                    "R11 谱系对齐 **O-TAIL 豁免**: 次锚 %s(≥5球·厚尾覆盖) 不被 %s 替换"
                    % (a2, _cand11[0])]
            elif _cand11:
                a_notes = list(a_notes or []) + [
                    "R11 谱系候选(供 R12·on 模式不硬替换): %s（谱系=%s）"
                    % ("/".join(_cand11[:4]), _r11.get("spectrum"))]
            _f11 = lambda v: ("%.0f%%" % (100 * v)) if v is not None else "缺"
            a_notes = list(a_notes or []) + [
                "R11 零封(直盘·%s): 主被零封 %s / 客被零封 %s / BTTS %s / rho %s → %s"
                % (_r11.get("source") or "-", _f11(_r11.get("home_clean")),
                   _f11(_r11.get("away_clean")), _f11(_r11.get("btts")),
                   ("%+.1fpp" % (100 * _r11["rho"])) if _r11.get("rho") is not None else "缺",
                   _r11.get("spectrum"))]
        except Exception as _eA11:
            a_notes = list(a_notes or []) + ["R11 谱系对齐异常(%s)" % type(_eA11).__name__]
    # 🔴P11·R12 次锚终选（2026-10-26·用户指令「两锚任一命中·机制保证分散」）
    #   R10 定主锚 a1（不动）→ R12 用**矩阵后验**在交集池内定 a2（数据驱动分散·质量地板）
    #   开关 p10_config.json: r12_pair_cover = on(接管) / auto(仅留痕) / off(旧行为)
    _r12 = None
    if _mmF and a1:
        try:
            if _r12m != "off":
                import market_distribution as _mdR12
                _r12 = _mdR12.r12_second_anchor(
                    _mmF, a1, r11=_r11, pool=[x["score"] for x in pool])
                if _r12.get("a2"):
                    if _r12m == "on":
                        a2 = _r12["a2"]
                    a_notes = list(a_notes or []) + [
                        "R12 双锚终选(%s): %s + %s ｜ **联合覆盖 %.1f%%**（p1 %.1f%%+p2 %.1f%%）"
                        "· 模式=%s · qdir=%s · w_dir=%s/w_spec=%s"
                        % (_r12m, a1, _r12["a2"], 100 * _r12["joint"], 100 * _r12["p1"],
                           100 * _r12["p2"], _r12["mode"], _r12.get("qdir"),
                           _r12.get("w_dir"), _r12.get("w_spec"))]
                else:
                    a_notes = list(a_notes or []) + [
                        "R12(%s): 无合格次锚（全部低于质量地板）→ 宽池 a2=%s" % (_r12m, a2)]
        except Exception as _e12:
            a_notes = list(a_notes or []) + [
                "R12 异常(%s: %s) → 回退 R10/R11 次锚 %s" % (type(_e12).__name__, _e12, a2)]
            _r12 = None
    _bn = po.get("btts_zero")                                 # 🔴V3.5.79 P3: 零封修正留痕
    if _bn:
        a_notes = list(a_notes or []) + [_bn]
    arb = w_logs + a_logs                                     # 🔴一致度只数「✅生效类」
    notes = a_notes                                           # 🔴仅提示（规则6）·不计入
    n_arb = len(arb)
    # 一致度 = 生效类仲裁次数（方案 §7.4：0→HIGH / 1→MID / ≥2→LOW）
    consistency = "HIGH" if n_arb == 0 else ("MID" if n_arb == 1 else "LOW")
    # 锚可信度（方案 §7.4 复用 anchor_trust 口径）
    #   🔴2026-10-14 修复 D2: 极端性判定应以 Step6.5 λ_final 为准（口径单一权威）·
    #   原只读 est["T"]["lambda"]（内部自算）→ 与 Step6.5 冲突时误判
    trust = "可信"
    lam_eff = lambda_final if lambda_final is not None else est["T"].get("lambda")
    if lam_eff is not None and lam_eff >= 3.4:
        trust = "不可信"
    elif lam_eff is not None and lam_eff >= 2.9:
        trust = "弱"
    if a1 and max(abs(x["m"]) for x in pool[:2]) >= 3:
        trust = "不可信"
    if len(pool) > 8 and trust == "可信":
        trust = "弱"
    # 🔴P10-R10: 可信度取**更严档**（R10-7 集中度 / R10-6 深盘 / R10-9 低覆盖 vs 既有 λ/净胜/池）
    if _r10_trust in ("可信", "弱", "不可信"):
        _TORD = {"可信": 2, "弱": 1, "不可信": 0}
        if _TORD.get(_r10_trust, 2) < _TORD.get(trust, 2):
            trust = _r10_trust
    # 模型铁律标注（不参与池生成·仅供 LLM 并列使用·覆盖最多两向 2026-10-29）
    ph, pd, pa = est["D"].get("pH"), est["D"].get("pD"), est["D"].get("pA")
    parallel_dirs = []
    if None not in (ph, pd, pa):
        srt = sorted((("主胜", ph), ("平局", pd), ("客胜", pa)), key=lambda t: -t[1])
        skew = srt[0][1] / srt[1][1] if srt[1][1] else 9.9
        if skew < 1.50:
            parallel_dirs = [d for d, _ in srt]
        elif skew < 2.00:
            parallel_dirs = [srt[0][0], "平局"]
    # 🔴P25-b(2026-10-28 用户指正): **次锚同样受信号约束**
    #   用户要求「期望进球搭配欧亚盘让球大小球综合判定」→ 次锚不得取 1 球低分出口
    #   （实测 287/289 次锚 0:1=1 球·偏离期望 -1.9 球·违背大球侧）
    if a2 and pool:
        try:
            _E25b = (lambda_final if lambda_final is not None else est["T"].get("lambda"))

            def _penb(_s):
                try:
                    _h2, _a2x = [int(_x) for _x in str(_s).split(":")]
                except Exception:
                    return 99.0
                return _signal_penalty({"t": _h2 + _a2x, "m": _h2 - _a2x},
                                       _E25b, lock, est, handi)

            _pa2 = _penb(a2)
            if _pa2 > 1.0:
                _alts = sorted((_penb(x["score"]), -float(x.get("p_pct") or 0), x["score"])
                               for x in pool if x["score"] != a1)
                if _alts and _alts[0][0] < _pa2 - 0.3:
                    _prev2 = a2
                    a2 = _alts[0][2]
                    notes.append(
                        "🔴P25 次锚信号约束校正: %s(约束分%.2f) → %s(%.2f)"
                        "（禁低分出口·期望%.2f球·同档按矩阵概率）"
                        % (_prev2, _pa2, a2, _alts[0][0], _E25b or 0))
        except Exception as _e25b:
            notes.append("P25 次锚校正异常(已跳过): %s" % str(_e25b)[:60])
    # 🔴P27-b(2026-10-28 机械锚定自查): 候选去重 —— 第三候选不得等于主锚/次锚
    #   罗马场实测「第三 3:0」与主锚重复（排序表三档只出两个不同比分）
    try:
        if a3 in (a1, a2):
            a3 = next((x["score"] for x in pool
                       if x["score"] not in (a1, a2)), None)
            notes.append("P27-b 第三候选去重 → %s（原与主/次锚重复）" % a3)
    except Exception:
        pass
    # 🔴P52-fix2(2026-10-31 端到端审计): 矩阵弱/未启用 → anchor_select 不跑 →
    #   P52 分级三级消费（量级/宽池/次锚跨度）**全部失效** → N23 退回纯泊松。
    #   实证(勒阿弗尔vsPSG·O2.5=1.378=L4): edge_err 0.242>0.08 判弱 → 主锚 2:0(2球)
    #   → 与「大球强主锚须≥3球」矛盾（N07b 复校验 ❌·原本靠人手工替换=执行不足）
    #   兜底: P52 分级只需 O2.5/λ（**不依赖矩阵**）→ 同方向内做量级纠偏
    #   铁律: 只调**量级**·**永不反转 L2 方向**（净胜符号必须一致）·完整留痕
    if not _r10:
        try:
            import big_pool_policy as _BPP52j

            def _tot52(_s):
                try:
                    return sum(int(x) for x in str(_s).split(":")[:2])
                except (TypeError, ValueError):
                    return 0

            def _sg52(_s):
                try:
                    _h52, _a52 = (int(x) for x in str(_s).split(":")[:2])
                    return (_h52 > _a52) - (_h52 < _a52)
                except Exception:
                    return None

            def _nm52(_s):      # 🔴净胜绝对值（排序用·防取 4:0 这类极值）
                try:
                    _h52, _a52 = (int(x) for x in str(_s).split(":")[:2])
                    return abs(_h52 - _a52)
                except Exception:
                    return 99

            _lam52 = lambda_final if lambda_final is not None else est["T"].get("lambda")
            _lv52 = _BPP52j.level_from_line(_lam52, o25)
            _need_a1 = {'L5': 3, 'L4': 3, 'L3': 3}.get(_lv52, 0)
            _need_a2 = _BPP52j.span_requirement(_lam52, _lv52, _tot52(a1))
            notes.append("🔴P52 矩阵弱兜底判级: %s（λ%s·O2.5=%s）→ 主锚须≥%d球·次锚须≥%d球"
                         % (_lv52, ("%.2f" % _lam52) if _lam52 else "-", o25 or "-",
                            _need_a1, _need_a2))
            # ① 主锚量级（同方向内改选·禁反转方向）
            if _need_a1 and a1 and _tot52(a1) < _need_a1:
                _sd1 = _sg52(a1)
                _c52 = [x["score"] for x in pool
                        if _tot52(x["score"]) >= _need_a1 and _sg52(x["score"]) == _sd1]
                # 🔴2026-10-31: 同达标时**净胜绝对值小者优先**（原直接取 _c52[0] →
                #   实测取到 4:0·净胜+4 超市场档 H2[+0,+3] → N07b ❌ → pipeline 缺块）
                _c52.sort(key=lambda s: (_nm52(s), _tot52(s)))
                if _c52:
                    notes.append("🔴P52 锚量级纠偏: 主锚 %s(%d球) → %s(%d球)"
                                 "（%s 大球强须≥%d球·同方向·锚-市场一致性铁律自动执行）"
                                 % (a1, _tot52(a1), _c52[0], _tot52(_c52[0]), _lv52, _need_a1))
                    a1 = _c52[0]
                else:
                    notes.append("🔴P52 锚量级: 池内无同方向 ≥%d 球候选 → 主锚保持 %s(宽池补足)"
                                 % (_need_a1, a1))
            # ② 次锚跨度（同方向优先·跨方向允许但需 ≥跨度 球）
            if _need_a2 and a2 and _tot52(a2) < _need_a2:
                _c52b = [x["score"] for x in pool
                         if _tot52(x["score"]) >= _need_a2 and x["score"] != a1]
                _c52b.sort(key=lambda s: (0 if _sg52(s) == _sg52(a1) else 1, _tot52(s)))
                if _c52b:
                    notes.append("🔴P52 次锚跨度(%s): %s(%d球) → %s(%d球)（须≥%d球·跨度式·主锚不动）"
                                 % (_lv52, a2, _tot52(a2), _c52b[0], _tot52(_c52b[0]), _need_a2))
                    a2 = _c52b[0]
        except Exception as _e52j:
            notes.append("⚪P52 矩阵弱兜底异常: %s" % str(_e52j)[:80])
    # 🔴2026-10-31 批次6 修复（步骤间传导审计实抓「修一处漏一处」）:
    #   P27-b 去重在 P52 纠偏**之前**执行 → 纠偏改了 a1/a2 后 a3 可能重新撞上。
    #   实证: 勒阿弗尔vsPSG 去重时 a1=2:0 → a3=2:1 正确；P52 把 a1 改成 2:1
    #   → 输出「主锚 2:1 / 次锚 3:1 / 第三 2:1」= 第三候选=主锚（去重白做）。
    #   修: return 前做**终态去重**（先 a2 后 a3·顺序稳定）
    try:
        if a2 == a1:
            _fx2 = next((x["score"] for x in pool if x["score"] != a1), None)
            if _fx2:
                notes.append("🔴终态去重: 次锚 %s = 主锚 → %s" % (a2, _fx2))
                a2 = _fx2
        if a3 in (a1, a2):
            _fx3 = next((x["score"] for x in pool if x["score"] not in (a1, a2)), None)
            if _fx3:
                notes.append("🔴终态去重: 第三 %s ∈ {主锚,次锚} → %s（P52 纠偏后重校验）"
                             % (a3, _fx3))
                a3 = _fx3
            else:
                notes.append("🔴终态去重: 第三候选无可用项(池内均为锚) → 置空（原 %s）" % a3)
                a3 = None
    except Exception as _efin:
        notes.append("⚪终态去重异常: %s" % str(_efin)[:60])

    # 🔴2026-11-01 修 R-ANCHOR-BIG 断链（用户「修」·真断链）:
    #   原缺陷 = calc_all 的 big_pool_policy.anchor_requirement 算出「次锚须 ≥ N 球」，
    #   但**只 print 不消费** → joint_solver 从不改锚（「只报警不动作」型·同 AGENTS P18 一类）。
    #   修法 = 池内找「总进球 ≥ N 且不在主锚位」的最高分候选替换次锚；找不到 → 三态保留原锚。
    if second_min_goals and a2 is not None:
        def _totv(_s):
            """比分 → 总进球。🔴锚是字符串 '3:1' 不是元组（2026-11-01 实测：a2[0]+a2[1] → '3'+':' TypeError）"""
            if isinstance(_s, (tuple, list)):
                return int(_s[0]) + int(_s[1])
            _ps = str(_s).replace('：', ':').split(':')
            return (int(_ps[0]) + int(_ps[1])) if len(_ps) == 2 else 0
        try:
            _t2 = _totv(a2)
            if _t2 < second_min_goals:
                # 🔴2026-11-01 修「约束打架」：选次锚时必须**同时赢盘**，
                #   否则后面 P17 会把它推翻（实测：3:1→3:2 上探后 P17 判 3:2 输盘 → 换 2:0 两球，R-ANCHOR 要求又失效）
                def _nv(_s):
                    _p = str(_s).replace('：', ':').split(':')
                    return (int(_p[0]) - int(_p[1])) if len(_p) == 2 else 0
                _hd_r = float(handi) if handi is not None else 0.0
                _nn_r = int(abs(_hd_r) + 0.999) if _hd_r else 0

                def _wp(_s):
                    if abs(_hd_r) < 0.5:
                        return True
                    _n = _nv(_s)
                    if _hd_r < 0:
                        return (_n >= _nn_r) if _n > 0 else (_n <= -1)
                    return (_n <= -_nn_r) if _n < 0 else (_n >= 1)

                _cands = [x["score"] for x in pool
                          if _totv(x["score"]) >= second_min_goals
                          and x["score"] != a1
                          and _wp(x["score"])]
                if _cands:
                    _new2 = _cands[0]
                    notes.append(
                        "🔴R-ANCHOR-BIG 次锚上探: %s(%d球) → %s(%d球)"
                        "（明确大球场次·要求 ≥%d 球·用户指令「明确大球场必须改锚定」）"
                        % (a2, _t2, _new2, _totv(_new2), second_min_goals))
                    a2 = _new2
                    if a3 in (a1, a2):
                        _fx3b = next((x["score"] for x in pool
                                      if x["score"] not in (a1, a2)), None)
                        notes.append("   第三候选顺延 → %s" % (_fx3b,))
                        a3 = _fx3b
                else:
                    notes.append(
                        "⚪R-ANCHOR-BIG: 池内无「总进球≥%d 且赢盘」的候选 → 原次锚 %s 保留（宽池受限·三态）"
                        % (second_min_goals, a2))
            else:
                notes.append("✅R-ANCHOR-BIG: 次锚 %s 已满足 ≥%d 球"
                             % (a2, second_min_goals))
        except Exception as _earb:
            notes.append("⚪R-ANCHOR-BIG 异常: %s" % str(_earb)[:60])

    # 🔴2026-11-01 P17 穿盘铁律真正落地（用户质疑「3:2？让球盘让一球」·机制缺陷）:
    #   原缺陷 = 让球只在 _signal_support 里**扣分**（P28「不淘汰任何候选」），不是硬约束
    #   → 主让 -1.5 的场次锚出 2:1 / 3:2（净胜都只有 1）= **两个锚都输盘**，锚无意义。
    #   修法 = 锚位（主锚/次锚）必须赢盘：主让场主胜锚净胜 ≥ ceil(|handi|)；
    #          不满足 → 池内换「赢盘且分数最高」的候选（池子本身不变·保留 P28 不淘汰精神）。
    if (handi is not None) or first_min_goals:
        try:
            import math as _mth2
            _hd = float(handi) if handi is not None else 0.0
            if abs(_hd) >= 0.5 or first_min_goals:
                _need_net = int(_mth2.ceil(abs(_hd)))

                def _netv2(_s):
                    _ps = str(_s).replace('：', ':').split(':')
                    return (int(_ps[0]) - int(_ps[1])) if len(_ps) == 2 else 0

                def _totv3(_s):
                    _ps = str(_s).replace('：', ':').split(':')
                    return (int(_ps[0]) + int(_ps[1])) if len(_ps) == 2 else 0

                def _win_plate(_sc):
                    """该比分在让球盘上是否赢盘"""
                    _n = _netv2(_sc)
                    if _hd < 0:            # 主队让球 → 主队须净胜 ≥ need；客队受让任何负净胜都赢
                        return (_n >= _need_net) if _n > 0 else (_n <= -1)
                    return (_n <= -_need_net) if _n < 0 else (_n >= 1)

                def _legal(_sc, _is_first):
                    """🔴锚合法性 = 分级主锚下限（P52）+ 穿盘（P17）同时满足"""
                    if _is_first and first_min_goals and _totv3(_sc) < first_min_goals:
                        return False
                    if abs(_hd) >= 0.5 and not _win_plate(_sc):
                        return False
                    return True

                for _tag in ('主锚', '次锚'):
                    _cur = a1 if _tag == '主锚' else a2
                    _isf = (_tag == '主锚')
                    if _cur is None or _legal(_cur, _isf):
                        continue
                    _alt = [x["score"] for x in pool
                            if _legal(x["score"], _isf)
                            and x["score"] != a1
                            and (a2 is None or x["score"] != a2 or _isf)]
                    if _alt:
                        _pick = _alt[0]
                        notes.append(
                            "🔴P17 穿盘铁律: %s %s(净胜%+d) 在让%.2f 盘上**输盘** → %s(净胜%+d)"
                            "（主锚必须落在不输盘一侧·用户质疑「让一球还给净胜1的锚」）"
                            % (_tag, _cur, _netv2(_cur), _hd, _pick, _netv2(_pick)))
                        if _tag == '主锚':
                            a1 = _pick
                            # 主锚换掉后次锚可能失效（撞主锚/不再合法）→ 重选，且仍须满足次锚下限
                            if a2 in (None, a1) or not _legal(a2, False):
                                _a2c = [x["score"] for x in pool
                                        if x["score"] != a1
                                        and _legal(x["score"], False)
                                        and (not second_min_goals
                                             or _totv3(x["score"]) >= second_min_goals)]
                                if _a2c:
                                    notes.append("   次锚重选 → %s（满足分级+穿盘）" % (_a2c[0],))
                                    a2 = _a2c[0]
                        else:
                            a2 = _pick
                    else:
                        notes.append(
                            "⚪P17 穿盘: %s %s(净胜%+d) 输盘，但池内无其他赢盘候选 → 保留（宽池受限·三态）"
                            % (_tag, _cur, _netv2(_cur)))
                if a3 in (a1, a2):
                    a3 = next((x["score"] for x in pool
                               if x["score"] not in (a1, a2)), None)
        except Exception as _ep17:
            notes.append("⚪P17 穿盘校验异常: %s" % str(_ep17)[:60])

    # 🔴2026-11-01 终态去重（P52/P17/R-ANCHOR-BIG 都是**后置校正**）:
    #   实测踩坑: R-ANCHOR 保留次锚 3:1 → P17 把主锚也换成 3:1 → 主锚=次锚（重复）
    #   必须在 return 前再查一次；找不到合法次锚则置空（宽池），禁重复主锚。
    try:
        _hd_f = float(handi) if handi is not None else 0.0
        _nn_f = int(abs(_hd_f) + 0.999) if _hd_f else 0

        def _tot_f(_s):
            _p = str(_s).replace('：', ':').split(':')
            return (int(_p[0]) + int(_p[1])) if len(_p) == 2 else 0

        def _net_f(_s):
            _p = str(_s).replace('：', ':').split(':')
            return (int(_p[0]) - int(_p[1])) if len(_p) == 2 else 0

        def _ok_f(_s):
            """🔴终态合法性 = 分级主锚/次锚下限（P52）+ 赢盘（P17）"""
            if not _s:
                return False
            if _hd_f and abs(_hd_f) >= 0.5:
                _n = _net_f(_s)
                if _hd_f < 0:
                    if _n > 0:
                        if _n < _nn_f:
                            return False
                    elif _n > -1:
                        return False
                else:
                    if _n < 0:
                        if _n > -_nn_f:
                            return False
                    elif _n < 1:
                        return False
            return True

        # 主锚不合法（极端情况：池内全输盘）→ 三态保留原锚并告警
        if a1 is not None and not _ok_f(a1):
            notes.append("⚠️终态: 主锚 %s 仍不满足「分级+穿盘」（池内无合法候选·宽池受限·三态）" % a1)

        # 次锚：必须合法且 ≠ 主锚；找不到就置空（禁给输盘锚）
        _ok2 = [x["score"] for x in pool if x["score"] != a1 and _ok_f(x["score"])
                and (not second_min_goals or _tot_f(x["score"]) >= second_min_goals)]
        if a2 is None or a2 == a1 or not _ok_f(a2):
            if _ok2:
                notes.append("🔴终态: 次锚 %s → %s（满足分级+穿盘+≥%s球）"
                             % (a2, _ok2[0], second_min_goals or '-'))
                a2 = _ok2[0]
            else:
                # 放宽「次锚下限」再试（分级是 nice-to-have·穿盘是硬）
                _ok2b = [x["score"] for x in pool if x["score"] != a1 and _ok_f(x["score"])]
                if _ok2b:
                    notes.append("🔴终态: 次锚 %s → %s（满足穿盘·但未达 ≥%s 球下限·三态）"
                                 % (a2, _ok2b[0], second_min_goals or '-'))
                    a2 = _ok2b[0]
                else:
                    notes.append("🔴终态: 池内无「赢盘」的次锚候选 → **次锚置空**"
                                 "（宁缺勿给输盘锚·用户质疑「让一球还给净胜1的锚」）")
                    a2 = None
        if a3 is not None and a3 in (a1, a2):
            _alt3 = next((x["score"] for x in pool if x["score"] not in (a1, a2)), None)
            notes.append("🔴终态去重(P17 后): 第三 %s 撞锚 → %s" % (a3, _alt3))
            a3 = _alt3
    except Exception as _edp:
        notes.append("⚪终态去重(P17 后)异常: %s" % str(_edp)[:60])

    # 🔴V3.5.89 O-TAIL 终态覆盖（用户 2026-11-03「新升级一定要结构清晰不要模模糊糊·伪消费禁止」）
    #   —— 最后一道防线·兜住前面全部 a2 覆盖点（R11/R12/P52/终态去重…）。
    #      厚尾场（t_band.tail.flag ∈ {厚尾,强厚尾}）且双锚均 <5 球时，
    #      从交集池强制取「≥5球 + 赢盘 + 合法」的最高支持度比分作次锚。
    #      （主锚保命中·次锚保尾部 = 用户批准的「厚尾场锚必须覆盖尾部档」落地）
    try:
        _tf_fin = (t_band or {}).get('tail', {}).get('flag') if isinstance(t_band, dict) else None
        if _tf_fin in ('厚尾', '强厚尾') and a1:
            _a1t_fin = sum(int(x) for x in a1.split(":"))
            _a2t_fin = sum(int(x) for x in a2.split(":")) if a2 else 0
            if _a2t_fin < 5:
                if _TAIL_ACT:
                    if a2:
                        _tail_ok = [x["score"] for x in pool
                                    if x["score"] != a1
                                    and (int(x["score"].split(":")[0]) + int(x["score"].split(":")[1])) >= 5
                                    and (not _hd_f or abs(_hd_f) < 0.5
                                         or _net_f(x["score"]) * (-1 if _hd_f < 0 else 1) > 0)]
                        if _tail_ok:
                            _old2_fin = a2
                            a2 = _tail_ok[0]
                            notes.append("🔴O-TAIL 终态覆盖: 厚尾(%s) 双锚均 <5球(%d/%d) → 次锚 %s → %s"
                                         "（交集池强制取 ≥5球尾锚·主锚保命中·次锚保尾部）"
                                         % (_tf_fin, _a1t_fin, _a2t_fin, _old2_fin, a2))
                        else:
                            notes.append("⚪O-TAIL 终态: 厚尾(%s) 但交集池无合法 ≥5球候选 → 保持 %s（宽池受限·三态）"
                                         % (_tf_fin, a2))
                    else:
                        notes.append("⚪O-TAIL 终态: 厚尾(%s) 但次锚为空 → 宽池受限（交集池 %d 个候选）"
                                     % (_tf_fin, len(pool)))
                else:
                    notes.append("🔴O-TAIL 终态标注(V3.5.90观察期): 厚尾(%s) 主锚%d球/次锚%s → "
                                 "建议次锚覆盖 ≥5球谱系（_TAIL_ACT=False 不动作·观察 ≥20 场后复核 premium）"
                                 % (_tf_fin, _a1t_fin, ('%d球' % _a2t_fin) if a2 else '空'))
    except Exception as _eTAIL_fin:
        notes.append("⚪O-TAIL 终态三态: %s" % type(_eTAIL_fin).__name__)

    return {"ok": True, "est": est, "axes": axes, "lock": lock,
            "arbitrations": arb, "arb_n": n_arb, "notes": notes,
            "consistency": consistency,
            "candidates": [x["score"] for x in pool], "pool": pool, "pool_n": len(pool),
            "anchor_1st": a1, "anchor_2nd": a2, "anchor_3rd": a3,
        "pair_cover": (_r12 if _r12 else _pcmeta), "r12": _r12,
            "anchor_1st_evidence": ev_map.get(a1, []), "anchor_2nd_evidence": ev_map.get(a2, []),
            "pois": po, "trust": trust, "empty": (len(pool) == 0),
            "lambda_final": lambda_final, "totals_bin": totals_bin,
            "vert": vert,                                  # 🔴P8: 纵向信号回传（供 fmt_report 留痕）
            "market_baseline_src": _bmeta.get("market_baseline_src"),
            "market_baseline_note": _bmeta.get("market_baseline_note"),
            # 🔴P10: 市场矩阵留痕（None=未传入·旧行为；dict=已传入·含 health/覆盖/边缘）
            "market_driven": _bmeta.get("market_driven"),
            "market_baseline": _bmeta.get("market_matrix"),
            "market_r10": _r10,                            # 🔴P10-R10 判定层留痕
            "market_r11": _r11,                            # 🔴P10-FINAL R11 零封/双方进球留痕
            "parallel_dirs": parallel_dirs}


def _ht_split(htft_raw):
    """🔴2026-10-20 P7: 半全场 9 格 → 半场三元去水概率
    输入: {"胜胜":1.88, "平胜":4.05, ...}（或 "胜胜=1.88,平胜=4.05" 字符串）
    返回: {"H":..,"D":..,"A":..} 或 None（不足 6 格/异常 → 三态降级）
    """
    if isinstance(htft_raw, str):
        _d = {}
        for _tok in htft_raw.replace("，", ",").split(","):
            if "=" in _tok:
                _k, _v = _tok.split("=", 1)
                _d[_k.strip()] = _v
        htft_raw = _d
    if not isinstance(htft_raw, dict) or len(htft_raw) < 6:
        return None
    inv = {}
    for k, v in htft_raw.items():
        _v = _f(v)
        if _v is not None and 1.0 < _v < 200.0:
            inv[str(k).strip()] = 1.0 / _v
    tot = sum(inv.values())
    if tot <= 0:
        return None
    p = {k: v / tot for k, v in inv.items()}
    out = {"H": 0.0, "D": 0.0, "A": 0.0}
    for k, v in p.items():
        if k.startswith("胜"):
            out["H"] += v
        elif k.startswith("平"):
            out["D"] += v
        elif k.startswith("负"):
            out["A"] += v
    if sum(out.values()) <= 0:
        return None
    return {k: round(v, 4) for k, v in out.items()}


def _cs_market_probs(cs_odds_raw):
    """🔴V3.5.79 P2: 波胆赔率表 → 去水精确比分概率分布
    输入: {'0-1':10.0, '1-0':7.5, ...} (1xbet Correct Score 全表)
    返回: {probs, exp_goals, exp_margin, top5}"""
    if not isinstance(cs_odds_raw, dict) or len(cs_odds_raw) < 10:
        return None                                      # 波胆不足→不介入（向后兼容）
    inv = {k: 1.0 / v for k, v in cs_odds_raw.items()
           if v and _f(v) is not None and 1 < float(v) < 100}   # 🔴占位档(赔率=100)必须剔除
    tot = sum(inv.values())
    if tot <= 0:
        return None
    probs = {k: v / tot for k, v in inv.items()}
    # 🔴2026-10-20 审计修复: 键分隔符兼容 '-' ':' '/'（P8 `_cs_full` 曾输出 ':' → ValueError）
    def _pk(_k):
        _s = str(_k).replace(":", "-").replace("/", "-")
        _a, _b = _s.split("-")[0], _s.split("-")[1]
        return int(_a), int(_b)
    exp_goals = sum((_pk(k)[0] + _pk(k)[1]) * p for k, p in probs.items())
    # 🔴2026-11-03 V3.5.89 端到端审计实抓: 原 `int(k.split('-')[0])` 对冒号格式键崩溃
    #   （'1:0'.split('-') → ['1:0'] → int('1:0') ValueError）
    #   L1782 已做分隔符兼容修复·此处漏改 → 竞彩冒号格式 cs 全崩 → 改用 _pk(k) 统一口径
    exp_margin = sum((_pk(k)[0] - _pk(k)[1]) * p for k, p in probs.items())
    top5 = sorted(probs.items(), key=lambda x: -x[1])[:5]
    return {"probs": probs, "exp_goals": exp_goals, "exp_margin": exp_margin, "top5": top5}


def _cs_select(cs, M, t_range):
    """🔴V3.5.79 P2: 波胆分布 × 净胜档(M) × 总进球域(T) 交集筛选
    只取满足二维约束的波胆比分 → 实时市场精选（候选池校准）
    🔴沙盒修复: key 统一冒号格式(1:0)·与交集池一致(否则波胆证据永不命中)"""
    if not cs:
        return None
    lo, hi = t_range
    cand = {}
    for k, p in cs["probs"].items():
        try:
            h, a = int(k.split("-")[0]), int(k.split("-")[1])
        except Exception:
            continue
        if (h - a) in M and lo <= h + a <= hi:
            cand['%d:%d' % (h, a)] = p
    return sorted(cand.items(), key=lambda x: -x[1]) if cand else None


def _cs_rank_map(cs):
    """🔴V3.5.79 P5-1: 波胆全表 → {比分: 排名(1-based)}（按去水概率降序）

    用**排名**而非概率值做基线：规避波胆 FLB 数值偏差（Reade&Singleton 2020·
    冷门比分概率被系统性高估·但排名不受影响——1:1 仍是第 1 名·4:4 仍是第 N 名）。
    """
    probs = (cs or {}).get("probs") or {}
    order = sorted(probs.items(), key=lambda x: -x[1])
    return {k.replace("-", ":"): i + 1 for i, (k, _p) in enumerate(order)}


def _market_baseline(pool, cs, est, lock):
    """🔴V3.5.79 P5 三态市场排序基线（原则「一切以市场信号为准」）

    S1 波胆完整(≥10档) → p_bs = 0.30 − 0.03×(rank−1)（排名线性衰减·Top1=0.30·第11名起=0）
    S2 波胆缺失·有让球水位 → p_bs = 上盘覆盖概率 × 净胜档系数（复用 P1 `_handi_water_strength`）
    S3 双缺 → 返回 None（排序回退泊松基线 ×P5_POIS_WEIGHT·与改前一致·向后兼容）

    🔴防死锚（方案 §三）: 波胆 Top1 全在交集池外（与 M 净胜档硬冲突）→ **不硬搬**·
       标记「市场分歧」并回退 S3 泊松基线（排序不空·绝不把池外波胆比分强行入池）。

    返回 (bs_map | None, src, note)
    """
    scores = [x["score"] for x in pool]
    probs = (cs or {}).get("probs") or {}
    # 🔴P5 空池保护（2026-10-17 接入审计实抓修）: 交集池为空时既非「波胆冲突」也非「双缺」——
    #   须直接回退泊松基线；否则会误报「🔴市场分歧」/ 返回 src=S2 但 bs_map 为空（留痕与行为不一致）
    if not scores:
        return None, "S3", "交集池为空 → 市场基线不适用(回退泊松基线)"
    # —— S1 波胆排名基线（最高优先） ——
    if len(probs) >= P5_CS_MIN_BINS:
        rmap = _cs_rank_map(cs)
        _top1 = sorted(probs.items(), key=lambda x: -x[1])[0][0].replace("-", ":")
        hits = [s for s in scores if s in rmap]
        if hits:
            bs = {}
            for s in scores:
                r = rmap.get(s)
                bs[s] = max(0.0, P5_BS_RANK_TOP - P5_BS_RANK_STEP * (r - 1)) if r else 0.0
            return bs, "S1", ("波胆排名基线(池内命中 %d/%d·波胆Top1=%s 排名%s)"
                              % (len(hits), len(scores), _top1, rmap.get(_top1)))
        return None, "S3", ("🔴市场分歧(波胆Top1=%s 全在交集池外·与净胜档硬冲突) → "
                            "不硬搬·回退泊松基线（防死锚）" % _top1)
    # —— S2 让球水位基线（波胆缺失·有 P1 水位） ——
    wm = (est.get("M") or {}).get("water") or {}
    p_up = wm.get("p_up")
    if p_up is not None:
        bs = {}
        for x in pool:
            _m = abs(int(x["m"]))
            if p_up >= 0.55:
                v = P5_WATER_STRONG_NET if _m >= 2 else P5_WATER_STRONG
            elif p_up >= 0.45:
                v = P5_WATER_MID
            else:
                v = P5_WATER_WEAK_LOW if x["m"] <= 0 else P5_WATER_WEAK_HIGH
            bs[x["score"]] = v
        return bs, "S2", ("让球水位基线(上盘覆盖%.1f%%·强度%s·波胆档%d<10→降级)"
                          % (p_up * 100, wm.get("strength"), len(probs)))
    # —— S3 泊松兜底（双缺·向后兼容） ——
    return None, "S3", ("双缺(无波胆/无让球水位) → 泊松兜底(基线×%.1f)"
                        % P5_POIS_WEIGHT)


def _signal_penalty(x, E_mkt=None, lock=None, est=None, handi=None):
    """🔴P25 市场信号约束惩罚（0 = 完全满足信号读数·越大越差）

    用户指令（2026-10-28）：「不依靠市场概率，而是市场信号——期望进球搭配欧亚盘让球
    大小球以及波胆综合判定」。比分概率天然低分偏置，故**概率不作排序主键**。

    四项信号约束（全部来自市场读数，非概率）：
      ① 期望进球 E（大小球全档 → λ）· 每偏离 1 球 = 1.0 分，超 1 球额外加罚
      ② 大小球方向（大球侧须 ≥3 球 · 小球侧须 ≤2 球）
      ③ 让球深度（让 1.5+ 须净胜 ≥2 · 让 0.75+ 须净胜 ≥1）
      ④ 净胜域（M 域外重罚·双保险）
    返回 float（越小越好）。
    """
    try:
        t = float(x.get("t") or 0)
        m = int(x.get("m") or 0)
    except Exception:
        return 0.0
    pen = 0.0
    # ① 期望进球
    try:
        if E_mkt is not None:
            dT = abs(t - float(E_mkt))
            pen += dT
            if dT > 1.0:
                pen += (dT - 1.0) * 0.5
    except Exception:
        pass
    # ② 大小球方向
    lab = str(((est or {}).get("B") or {}).get("label") or "")
    if "大球" in lab and t < 3:
        pen += 1.2
    if "小球" in lab and t > 2:
        pen += 1.2
    # ③ 让球深度（深盘须穿盘）
    try:
        if handi is not None:
            h = abs(float(handi))
            if h >= 1.5 and abs(m) < 2:
                pen += 1.5
            elif h >= 0.75 and abs(m) < 1:
                pen += 1.0
    except Exception:
        pass
    # ④ 净胜域
    try:
        if lock and lock.get("M") is not None and m not in lock["M"]:
            pen += 1.0
    except Exception:
        pass
    return pen


def _evidence_rank(pool, lock, est, o25, league, lam_final=None, cs_cand=None,
                   cs=None, meta_out=None, jc_cs=None, htft=None,
                   vert=None,                      # 🔴P8 纵向信号（vertical_for 产出）
                   market_matrix=None,             # 🔴P10 市场矩阵（E0·三源齐全时主导排序）
                   handi=None):                    # 🔴P25 让球深度（信号约束用）
    """🔴V3.5.78 防死锚 + 🔴V3.5.79 P5 市场信号主导排序

    第一铁律不变（严禁死锚·必须根据数据分析）: T域上探只打开候选空间·
    **主锚必须由当场数据链共振裁决**——非纯泊松Top1·非机械4+球。

    🔴P5 排序公式（2026-10-17 用户方案「一切以市场信号为准」·35 份真实快照实证）:
        score = 市场基线 p_bs（三态·见 _market_baseline）
              + 泊松基线 ×0.5（降权·原 ×1.0·仍参与排序·保留「最可能比分」信息）
              + 证据加分
        S3（双缺）时 p_bs 不合入 → 与改前完全一致（×0.5 是唯一差异）
        🔴 所有新增权重均【待回测校准】·禁单场固化

    证据源（全部当场数据·可复现·非虚构）:
      E1 查表命中: score_depth_lookup(m,o25).anchor/second/third ∈ 交集池 → +0.20/+0.10/+0.05
                   (score_depth_table 148,397 场历史分布·同属市场统计·P5 升权)
      E2 goal_bins top: goal_bin_probs(o25).top 前2 ∈ 交集池 → +0.10/+0.05
                   (goal_bins_table 148,397场实测·极端档 top 含 3:0/4:0/4:1)
      E3 盘口线共振: λ_final≥3.4 **且** 该比分总进球≥4 → +0.05
                   (仅当去水 p_over_fair≥0.62 时生效·防单源高λ死锚大球)
      E4 大球反向校验: λ_final≥3.4 但该比分总进球≤1 → −0.10
                   (低分谱系保留候选·但主锚让位——极端档 g01=7.8-13.4%≠0·复盘④教训)
      E5 波胆市场: S1 时 +0.30/+0.15/+0.05（与排名基线双通道强化市场）·S2/S3 时 +0.20/+0.12/+0.05
      E6 让球水位共振（P5 新增）: 上盘覆盖≥55% 且 |净胜|≥2 → +0.08（与 P5-2 呼应）
      E10 波胆纵向（P8 新增）: 波胆赔率初盘→临场 显著降水(≥15%) +0.12 / 温和降水 +0.06 /
                   温和升水 −0.04 / 显著升水 −0.08（大资金对具体比分的定向表态·与 E5 横向双通道）
                   🔴只调权重·不排除候选（防死锚）·【待回测校准】

    返回 [(score, evidence_desc)]·evidence_desc 列明命中证据（供留痕·治「审计看不到=判未执行」）
    meta_out(dict·可选): 回填 market_baseline_src / market_baseline_note
    """
    # 🔴P10: 市场三源矩阵（E0·三源齐全→主导排序；不健康→完全走旧链路）
    # 🔴P10-R10 补强: 兼容两种入参 —— ①matrix 摘要（含 health/matrix）②**完整 mm**（含 ok/matrix/total/margin）
    _mm_raw10 = market_matrix if isinstance(market_matrix, dict) else None
    if (_mm_raw10 and isinstance(_mm_raw10.get("matrix"), dict)
            and isinstance((_mm_raw10.get("matrix") or {}).get("matrix"), dict)):
        _mm10 = _mm_raw10.get("matrix")
        if meta_out is not None:
            meta_out["market_matrix_full"] = _mm_raw10
    else:
        _mm10 = _mm_raw10
    _mm_ok10 = bool(_mm10 and _mm10.get("health") == "ok" and _mm10.get("matrix"))
    _mm_probs10 = (_mm10.get("matrix") or {}) if _mm_ok10 else {}
    # 🔴P10-fix3: 尾桶挤压格（矩阵概率远超波胆定价 = 边缘强制分配）
    #   → **不给 E0 矩阵基线**（防伪影被推上锚位）；仍留在候选池，可经证据/泊松回填入选（防死锚）
    _mm_sq10 = set()
    if _mm_ok10:
        for _s10 in (_mm10.get("squeezed") or []):
            try:
                _mm_sq10.add(str(_s10).split("(")[0].strip().replace("-", ":"))
            except Exception:
                pass
    if meta_out is not None:
        meta_out["market_driven"] = _mm_ok10
        meta_out["market_matrix"] = _mm10
    # 🔴P5: 市场排序基线（三态·市场主导排序的核心）
    bs_map, bs_src, bs_note = _market_baseline(pool, cs, est, lock)
    if meta_out is not None:
        meta_out["market_baseline_src"] = bs_src
        meta_out["market_baseline_note"] = bs_note
    # 预取证据源（查表·按 M 档逐档）
    try:
        lb_map = {}
        _e1 = P5_E1_TABLE                              # 🔴P5: E1 查表升权 0.20/0.10/0.05
        for m in (lock["M"] or [0]):
            try:
                lb = score_depth_lookup(m, o25, league=league)
            except Exception:
                lb = None
            if isinstance(lb, dict):
                for k, v in (("anchor", _e1[0]), ("second", _e1[1]), ("third", _e1[2])):
                    s = lb.get(k)
                    if s:
                        lb_map[str(s).replace("-", ":")] = max(lb_map.get(str(s).replace("-", ":"), 0), v)
    except Exception:
        lb_map = {}
    # 预取 goal_bins top
    try:
        gb = goal_bin_probs(o25) if o25 is not None else None
        gb_top = {}
        if isinstance(gb, dict) and gb.get("top"):
            for i, (s, _p) in enumerate(gb["top"][:2]):
                gb_top[str(s).replace("-", ":")] = 0.10 if i == 0 else 0.05
    except Exception:
        gb_top = {}
    p_over = (est["B"] or {}).get("p_over_fair")
    # 🔴2026-10-20 P7 E9: 半场三元去水（半全场 9 格）
    _ht_p = _ht_split(htft) if htft is not None else None
    # 🔴2026-10-20 P6-b E8: 市场期望（O2.5 市场价反推·纯市场信号）
    _E_mkt = None
    try:
        if o25 is not None and _o25_expect is not None:
            _E_mkt = float(_o25_expect(o25))
    except Exception:
        _E_mkt = None
    if _E_mkt is None and lam_final is not None:
        _E_mkt = float(lam_final)
    extreme = lam_final is not None and float(lam_final) >= EXTREME_OVER_LAM
    strong_over = p_over is not None and float(p_over) >= 0.62
    _wm = (est.get("M") or {}).get("water") or {}      # 🔴P5: E6 让球水位共振输入
    _p_up = _wm.get("p_up")
    _cs_vert = (vert or {}).get("cs_vert") or {}       # 🔴P8: E10 波胆纵向输入

    ranked = []
    for x in pool:
        s = x["score"]
        t = x["t"]
        ev = []
        w = 0.0
        _w8 = 0.0        # 🔴P23: E8 期望匹配额（不参与 EV_SCALE 缩放）
        if s in lb_map:
            w += lb_map[s]
            ev.append("查表+%.2f" % lb_map[s])
        if s in gb_top:
            w += gb_top[s]
            ev.append("goal_bins+%.2f" % gb_top[s])
        if extreme and strong_over and t >= 4:
            w += 0.05
            ev.append("盘口线共振+0.05")
        if extreme and t <= 1:
            w -= 0.10
            ev.append("低分让位-0.10")
        # 🔴V3.5.79 P2: E5 波胆市场证据（实时·最高权重·优先于静态查表）
        #   🔴P5: S1 时与排名基线双通道强化（0.30/0.15/0.05）·S2/S3 不虚增（0.20/0.12/0.05）
        #   🔴P10 审计修(2026-10-25): **矩阵启用时跳过 E5** —— CS 已作为矩阵形状先验进 E0，
        #     再加 E5 = 同一波胆信号计两次（方案 §5.4「E5 仅在市场矩阵未启用时保留旧作用」）
        if cs_cand is not None and not _mm_ok10:
            _pm = dict(cs_cand).get(s)
            if _pm is not None:
                _e5 = P5_E5_CS if bs_src == "S1" else P5_E5_CS_OFF
                if _pm >= 0.05:
                    w += _e5[0]; ev.append("波胆+%.2f(%.1f%%)" % (_e5[0], _pm * 100))
                elif _pm >= 0.03:
                    w += _e5[1]; ev.append("波胆+%.2f(%.1f%%)" % (_e5[1], _pm * 100))
                else:
                    w += _e5[2]; ev.append("波胆+%.2f(%.1f%%)" % (_e5[2], _pm * 100))
        # 🔴P5 新增 E6: 让球水位共振（机构真看好→净胜2+档加分·与 S2 基线呼应）
        if _p_up is not None and _p_up >= 0.55 and abs(int(x["m"])) >= 2:
            w += P5_E6_WATER
            ev.append("水位共振+%.2f" % P5_E6_WATER)
        # 🔴2026-10-20 P7 E9: 半场方向一致性（半全场 9 格去水 → 半场主/平/客）
        if _ht_p is not None:
            _hp = _ht_p.get("H") if x["h"] > x["a"] else (
                  _ht_p.get("D") if x["h"] == x["a"] else _ht_p.get("A"))
            if _hp is not None:
                _hi = 0.45 if x["h"] >= x["a"] else 0.35
                _lo = 0.30 if x["h"] >= x["a"] else 0.20
                if _hp >= _hi:
                    w += P5_E9_HT[0]
                    ev.append("半场方向%.0f%%+%.2f" % (_hp * 100, P5_E9_HT[0]))
                elif _hp < _lo:
                    w += P5_E9_HT[1]
                    ev.append("半场方向弱%.0f%%%.2f" % (_hp * 100, P5_E9_HT[1]))
        # 🔴2026-10-20 P6-b E8: 市场期望匹配（期望=O2.5 反推·锚与市场期望自洽）
        if _E_mkt is not None:
            _off = abs(t - _E_mkt)
            _w8 = (P5_E8_EXPECT[0] if _off <= 0.5 else
                   P5_E8_EXPECT[1] if _off <= 1.0 else
                   P5_E8_EXPECT[2] if _off <= 1.5 else P5_E8_EXPECT[3])
            w += _w8
            ev.append("期望%s%.2f(偏离%.2f·E=%.2f)"
                      % ("匹配+" if _w8 > 0 else "越界", _w8, _off, _E_mkt))
        # 🔴2026-10-20 P6 E7: 竞彩比分盘证据（用户点名「竞彩」·P5 未含）
        if jc_cs:
            _jv = jc_cs.get(s)
            if _jv is not None:
                _e7 = P5_E7_JC
                # 🔴P9 竞彩噪音隔离: 与欧亚波胆 Top3 **一致** → 全权重（双通道共识）；
                #   背离 → ×0.5（竞彩跟风/散户噪音·防把欧亚波胆 Top 挤掉）
                _diverge = False
                if cs_cand:
                    try:
                        _eu_top3 = {str(_k).replace("-", ":")
                                    for _k in sorted(cs_cand, key=lambda x: -cs_cand[x])[:3]}
                        _diverge = s not in _eu_top3
                    except Exception:
                        _diverge = False
                _e7u = tuple(v * 0.5 for v in _e7) if _diverge else _e7
                _tag9 = "·P9背离欧亚Top3·降权" if _diverge else "·与欧亚一致"
                if _jv >= 0.08:
                    w += _e7u[0]; ev.append("竞彩CS+%.2f(%.1f%%)%s" % (_e7u[0], _jv * 100, _tag9))
                elif _jv >= 0.05:
                    w += _e7u[1]; ev.append("竞彩CS+%.2f(%.1f%%)%s" % (_e7u[1], _jv * 100, _tag9))
                elif _jv >= 0.03:
                    w += _e7u[2]; ev.append("竞彩CS+%.2f(%.1f%%)%s" % (_e7u[2], _jv * 100, _tag9))
        # 🔴P8 E10: 波胆纵向变化（初盘→临场·大资金定向表态）
        #   🔴2026-10-30 P35 修（用户指令「纵向要真正起作用」·A/B 实测抓出**两个真 bug**）：
        #   bug① 原条件 `and not _mm_ok10` → **P10 矩阵可用时 E10 被完全跳过**
        #        （今日两场矩阵都 ok=True → 纵向零影响·A/B 输出完全相同）
        #   bug② `cs_vert` 的键是**字符串** '0:1'，而此处 `s` 是**元组** (0,1)
        #        → `s in _cs_vert` **恒 False** → E10 从未命中过（比 bug① 更根本）
        #   🔴机理: 矩阵=**截面**（同一时点 OU/AH/CS 三源）· E10=**时间维度**（初盘→临场变动）
        #        → 信息不重叠，"防双计"假设不成立 → 矩阵可用时**减半**而非跳过
        #   修法: 键归一化（元组→'h:a'）+ 矩阵减半 + 多时点加权（≥3 时点 ×1.2）
        _sk10 = '%d:%d' % (s[0], s[1]) if isinstance(s, (tuple, list)) else str(s)
        _cv10 = None
        if _cs_vert:
            _cv10 = _cs_vert.get(_sk10)
            if _cv10 is None:
                try:
                    _cv10 = _cs_vert.get(s)
                except TypeError:
                    _cv10 = None
        if _cv10 is not None:
            _d10 = _cv10.get("dir")
            _w10 = (P8_CS_DROP_STRONG if _d10 == "drop_strong" else
                    P8_CS_DROP_MILD if _d10 == "drop_mild" else
                    P8_CS_RISE_MILD if _d10 == "rise_mild" else
                    P8_CS_RISE_STRONG if _d10 == "rise_strong" else 0.0)
            if _w10:
                _np10 = int((vert or {}).get("n_points") or 0)
                _k10 = 1.2 if _np10 >= 3 else 1.0
                if _mm_ok10:
                    _k10 *= 0.5
                _w10 = _w10 * _k10
                w += _w10
                ev.append("波胆纵向%+.2f(%s·chg%+.1f%%%s)"
                          % (_w10, _d10, (_cv10.get("chg") or 0) * 100,
                             ("·%d时点" % _np10) if _np10 >= 2 else ""))
        # 🔴P10 E0 市场矩阵基线（三源齐全·决策门通过）: 🔴P23 矩阵×3.0 主导 · 其余证据×0.15 tie-break · E8 全额
        if _mm_ok10:
            _mp10 = float(_mm_probs10.get((x["h"], x["a"]), 0.0))
            if s in _mm_sq10:
                # 🔴P10-fix3: 尾桶挤压格 → E0 基线置 0（仍保留候选·仅不让伪影主导锚位）
                ev.append("市场矩阵挤压格(E0 不加分·边缘伪影)")
                _mp10 = 0.0
            # 🔴P25(2026-10-28 用户指正): 信号约束主导（概率有低分偏置·降为 tie-break）
            _pen25 = _signal_penalty(x, _E_mkt, lock, est, handi)
            _score = (-P25_SIGNAL_W * _pen25                            # 期望/大小球/让球/净胜域 硬约束
                      + (w - _w8)                                      # 波胆·让球水位等证据（同约束内区分）
                      + _w8                                            # E8 期望匹配
                      + P25_P_TIE * _mp10)                             # 矩阵概率仅 tie-break
            ev.insert(0, "信号约束-%.2f" % (P25_SIGNAL_W * _pen25))
            if _mp10 > 0:
                ev.append("市场矩阵+%.2f(E0·%.1f%%·含T/M边缘)" % (P10_MM_BASE * _mp10, _mp10 * 100))
            ranked.append((_score, s, ev))
            continue
        # 🔴P5 排序公式: 市场基线（三态） + 泊松基线×权重（2026-10-20: 权重=0 → 泊松退出排序） + 证据加分
        _score = P5_POIS_WEIGHT * (x["p_pct"] / 100.0)
        if bs_map:
            _b = bs_map.get(s, 0.0)
            if _b > 0:
                _score += _b
                ev.append("市场基线+%.2f(%s)" % (_b, bs_src))
        ranked.append((_score + P10_EV_SCALE * (w - _w8) + _w8, s, ev))   # 🔴P23 同口径
    ranked.sort(key=lambda z: -z[0])
    return [(s, ev) for _, s, ev in ranked]


def fmt_report(r):
    if not r.get("ok"):
        return "❌ joint_solver 不可用: %s" % r.get("reason")
    e, lk = r["est"], r["lock"]
    L = []
    L.append("【7.0 四要素并行估值】")
    L.append("  D 方向: %s (pH %s/pD %s/pA %s · skew %s · conf %s)"
             % (e["D"].get("dir"), e["D"].get("pH"), e["D"].get("pD"), e["D"].get("pA"),
                e["D"].get("skew"), e["D"].get("conf")))
    L.append("  M 净胜档: 主档 %s ∪ 相邻 %s → %s%s" % (e["M"].get("main"), e["M"].get("adj"), e["M"].get("all"),
                                                   ("·低可能性%s" % e["M"]["low_possibility"]) if e["M"].get("low_possibility") else ""))
    _nsrc = len(e["T"].get("src") or {})
    _src_tag = "✅五源齐" if _nsrc >= 5 else ("⚠️仅%d源" % _nsrc)
    L.append("  T 期望 λ: %s (源 %s · 口径=%s · %s%s)"
             % (e["T"].get("lambda"), e["T"].get("src"), e["T"].get("origin"), _src_tag,
                ("·异常源%s" % e["T"]["bad_src"]) if e["T"].get("bad_src") else ""))
    L.append("  B 大小球: %s (over去水 %s · goal_bins档 %s)" % (e["B"].get("label"), e["B"].get("p_over_fair"), e["B"].get("bin")))
    _ds = lk.get("D_set") or [lk.get("D")]
    _ds_tag = ("%s（🔴锚谱系·方向保留）" % _ds) if len(_ds) > 1 else str(lk.get("D"))
    L.append("【7.1→7.2 坐标与约束传播】 D_lock=%s · M_lock=%s · T∈[%d,%d]"
             % (_ds_tag, lk["M"], lk["T"][0], lk["T"][1]))
    if r["arbitrations"]:
        L.append("【7.3 仲裁命中 %d 条（✅生效类·计入一致度）】" % r["arb_n"])
        for a in r["arbitrations"]:
            L.append("  · " + a)
    else:
        L.append("【7.3 仲裁】 无生效类仲裁（四要素天然自洽）")
    for _nt in (r.get("notes") or []):
        L.append("  · " + _nt)
    L.append("【7.4 交集池 %d 个】 主锚 %s / 次锚 %s / 第三 %s" % (r["pool_n"], r["anchor_1st"], r["anchor_2nd"], r["anchor_3rd"]))
    # 🔴P11·R12 双锚联合覆盖留痕（2026-10-26·用户指令「两锚任一命中·机制保证分散」）
    _r12f = r.get("r12") or {}
    if _r12f.get("a2"):
        L.append("    🔴双锚联合覆盖(R12): %.1f%%（p1 %.1f%% + p2 %.1f%%）· 模式=%s · qdir=%s"
                 % (100 * (_r12f.get("joint") or 0), 100 * (_r12f.get("p1") or 0),
                    100 * (_r12f.get("p2") or 0), _r12f.get("mode"), _r12f.get("qdir")))
    elif _r12f:
        L.append("    ⚪R12: %s → 宽池（不硬凑次锚）" % (_r12f.get("mode") or "-"))
    else:
        L.append("    ⚪R12 不触发（矩阵未启用 或 p10_config.r12_pair_cover=off）")
    # 🔴V3.5.79 P5: 市场排序基线来源留痕（三态 S1/S2/S3·治「审计看不到=判未执行」）
    _bm = r.get("market_baseline_src")
    if _bm:
        L.append("  🔴市场排序基线(P5·市场主导): %s ← %s ｜ 泊松基线降权 ×%.1f"
                 % (_bm, r.get("market_baseline_note") or "-", P5_POIS_WEIGHT))
    # 🔴V3.5.81 P10: 市场三源比分矩阵留痕（治「审计看不到=判未执行」·未传入时**不输出**=旧行为一致）
    _mmx = r.get("market_baseline")
    if _mmx:
        _top10 = "·".join("%s(%.1f%%)" % (s, p) for s, p, _c in (_mmx.get("top") or [])[:4])
        L.append("  🔴市场矩阵(P10·E0): health=%s · CS覆盖%s档 · 矩阵E[T]=%s E[M]=%s · Top %s ｜ %s"
                 % (_mmx.get("health"), _mmx.get("cs_coverage"),
                    _mmx.get("expT"), _mmx.get("expM"), _top10 or "-",
                    ("主排序=市场矩阵×%.1f(证据仅×%.2f·E8期望全额·泊松回填)" % (P10_MM_BASE, P10_EV_SCALE) if r.get("market_driven")
                     else "未启用(health≠ok) → 走 P5/泊松链路")))
    # 🔴V3.5.81 P10-R10 判定标准层留痕（未启用矩阵时**不输出**=旧行为一致）
    _r10x = r.get("market_r10")
    if _r10x:
        L.append("  🔴R10判定层: 主锚 %s / 次锚 %s · 可信度 %s%s ｜ %s"
                 % (_r10x.get("anchor_1st"), _r10x.get("anchor_2nd"), _r10x.get("trust"),
                    ("·双主锚" if _r10x.get("double") else "") + ("·宽池" if _r10x.get("wide") else ""),
                    " ".join((_r10x.get("notes") or [])[:2]) or "-"))
        for _zz in (_r10x.get("zero_notes") or [])[:2]:
            L.append("    " + _zz)
        for _bb in (_r10x.get("big_notes") or [])[:2]:
            L.append("    " + _bb)
    # 🔴P10-FINAL R11 零封/双方进球留痕（未启用矩阵时不输出 = 旧行为一致）
    _r11x = r.get("market_r11")
    if isinstance(_r11x, dict):
        # 🔴2026-10-25 审计修(死代码): 改用 market_distribution.fmt_r11_line 单一实现（原此处内联复制）
        try:
            import market_distribution as _mdF11
            L.append("  " + _mdF11.fmt_r11_line(_r11x))
        except Exception:
            _f = lambda v: ("%.0f%%" % (100 * v)) if v is not None else "缺"
            L.append("  🔴R11 零封(直盘·%s): 主被零封 %s / 客被零封 %s / BTTS %s / rho %s → %s"
                     % (_r11x.get("source") or "-", _f(_r11x.get("home_clean")),
                        _f(_r11x.get("away_clean")), _f(_r11x.get("btts")),
                        ("%+.1fpp" % (100 * _r11x["rho"])) if _r11x.get("rho") is not None else "缺",
                        _r11x.get("spectrum")))
        for _n11 in (_r11x.get("notes") or [])[-2:]:
            L.append("    " + _n11)
    # 🔴V3.5.80 P8 纵向信号留痕（治「审计看不到=判未执行」）
    _vt = r.get("vert") or {}
    if _vt.get("cs_vert"):
        _top = sorted(_vt["cs_vert"].items(), key=lambda x: -x[1].get("chg", 0))[:3]
        L.append("  🔴P8波胆纵向: %s ← （初盘→临场赔率降=被看好·跨度 %s）"
                 % (", ".join("%s(%+.0f%%)" % (k, v["chg"] * 100) for k, v in _top),
                    _vt.get("span") or "-"))
    if _vt.get("ah_vert"):
        _a = _vt["ah_vert"]
        L.append("  🔴P8让球升降: %s (line %+.2f→%+.2f · 主水 %.2f→%.2f · 净胜档%+d)"
                 % (_a.get("combo"), _a.get("line0") or 0, _a.get("line1") or 0,
                    _a.get("w0") or 0, _a.get("w1") or 0, int(_a.get("shift") or 0)))
    if _vt.get("ou_vert"):
        _o = _vt["ou_vert"]
        L.append("  🔴P8大小球水位: %s (线 %.2f→%.2f · 大球水 %.2f→%.2f · 置信%+d 档)"
                 % (_o.get("dir"), _o.get("line0") or 0, _o.get("line1") or 0,
                    _o.get("over0") or 0, _o.get("over1") or 0, int(_o.get("conf_step") or 0)))
    # 🔴方案 §5: (D,M,T) 联合象限边际（由交集池实时聚合 · 零额外成本 · quadrant_v2 同源口径）
    _md, _mm, _mt = {}, {}, {}
    for _x in r["pool"]:
        _md[_x["d"]] = round(_md.get(_x["d"], 0.0) + _x["p_pct"], 2)
        _mm[_x["m"]] = round(_mm.get(_x["m"], 0.0) + _x["p_pct"], 2)
        _mt[_x["t"]] = round(_mt.get(_x["t"], 0.0) + _x["p_pct"], 2)
    if _md:
        L.append("  (D,M,T) 联合象限边际: D=%s ｜ M(净胜)=%s ｜ T(总进球)=%s" % (_md, _mm, _mt))
    for x in r["pool"][:8]:
        L.append("    %s  %s 净%+d %d球  %.2f%%" % (x["score"], x["d"], x["m"], x["t"], x["p_pct"]))
    if r["pois"].get("table_hits") or r["pois"].get("table_conflicts"):
        L.append("  查表集成: 交集内命中 %s / 让位市场(交集外) %s" % (r["pois"].get("table_hits"), r["pois"].get("table_conflicts")))
    L.append("  一致度 %s（✅生效类仲裁 %d 次·规则6 仅提示不计入）· 锚可信度 %s%s"
             % (r["consistency"], r["arb_n"], r["trust"],
                ("·并列方向%s(模型铁律标注·不参与池生成)" % r["parallel_dirs"]) if r.get("parallel_dirs") else ""))
    if _nsrc < 3:
        L.append("  ⚠️ 口径告警: T 源不足 3（实际 %d）→ 期望进球可信度降级（缺 Step6.5 五源注入）" % _nsrc)
    # 🔴V3.5.78: 极端大球档方差预警（goal_bins 实测: 极端档 g01 7.8-13.4% ≠ 0·低分不罕见）
    #   🔴2026-10-14 修复 D2: 优先读 Step6.5 λ_final（口径单一权威）·回退内部自算
    _lamf = r.get("lambda_final")
    if _lamf is None:
        _lamf = (r.get("est", {}).get("T") or {}).get("lambda")
    if _lamf is not None and float(_lamf) >= EXTREME_OVER_LAM:
        L.append("  ⚠️ 极端大球场(λ=%.2f≥%.1f): 量级方差极大·真实总进球 1-6 球均可能"
                 "（goal_bins 实测 0-1球≈8-13%% / 4+球≈46-59%%）→ 主锚大球谱系 + 次锚低分兜底·禁单锚"
                 % (float(_lamf), EXTREME_OVER_LAM))
    # 🔴V3.5.78: 主锚证据链留痕（P6 防死锚·治「审计看不到=判未执行」）
    _ev1 = r.get("anchor_1st_evidence") or []
    _ev2 = r.get("anchor_2nd_evidence") or []
    if _ev1 or _ev2:
        L.append("  🔴选锚证据链(V3.5.78·防死锚): 主锚 %s ← %s ｜ 次锚 %s ← %s"
                 % (r.get("anchor_1st"), (_ev1 or ["无证据·仅泊松"]), r.get("anchor_2nd"), (_ev2 or ["无证据·仅泊松"])))
    return "\n".join(L)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="四要素深度融合锚定（joint_solver·方案 V3.5.77）")
    ap.add_argument("--eu", required=True, help="欧赔 主,平,客")
    ap.add_argument("--handi", type=float, default=None)
    ap.add_argument("--o25", type=float, default=None)
    ap.add_argument("--u25", type=float, default=None)
    ap.add_argument("--line", type=float, default=None, help="亚盘大小球均衡线(λ_line 源)")
    ap.add_argument("--lam-h", type=float, default=None)
    ap.add_argument("--lam-a", type=float, default=None)
    ap.add_argument("--league", default=None)
    ap.add_argument("--src", default=None,
                    help="五源注入 JSON/键值串: market=3.10,line=2.75,pois=2.57,table=3.16,water=2.9")
    a = ap.parse_args()
    oh, od, oa = [float(x) for x in a.eu.split(",")]
    src_lam = None
    if a.src:
        src_lam = {}
        for kv in a.src.split(","):
            if "=" in kv:
                k, v = kv.split("=", 1)
                try:
                    src_lam[k.strip()] = float(v)
                except Exception:
                    pass
    r = joint_anchor(oh, od, oa, a.handi, a.o25, a.u25, a.line, a.lam_h, a.lam_a, a.league, src_lam)
    print("=" * 78)
    print(fmt_report(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
