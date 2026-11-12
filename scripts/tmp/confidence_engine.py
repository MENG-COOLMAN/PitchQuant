# -*- coding: utf-8 -*-
"""confidence_engine.py — 🔴V3.5.80 置信度层判定器（脚本化·替代手算）

背景（2026-10-20·用户「还有需要封装的部分请封装，避免每次手算带来的误差」）：
「置信度层」一直是**LLM 手算**——基础层按概率查表、再逐个叠加 Q2 诱盘/Elo 背离/弱共识/
资金盘 spread 等升降档信号。实际执行中同一场不同批次常给出不同档位（人工合成无留痕），
且与 `conf_calib.py` 的 strict 口径校准脱节（MID-LOW 实测 strict 仅 39.3%）。

本模块把「合成规则」固化为纯函数：**只输出层位建议 + 逐项依据**，
🔴铁律：只调置信度·**永不反转方向**·不排除候选；最终判定权仍在模型（本函数给建议与依据）。

层位映射（AGENTS 置信度概率映射·**strict 口径**）:
  p_max ≥ 70% → HIGH ｜ 55-70% → MID ｜ 45-55% → MID-LOW ｜ <45% → LOW
升降档信号（每项 −/+1 档·合计夹逼在 ±1 档·与「只调置信度」铁律一致）:
  Q2 诱盘（公众热捧但欧亚不跟进）           → −1
  低赔—ELO 背离（|ELO差|≥30 且低赔≠ELO强方） → −1
  弱共识 skew<150%（市场首选≈随机）          → −1
  资金盘 spread<2% 且热门<1.50               → +1
  资金盘 spread<2%（全样本）                 → +0.5
单押准入（AGENTS 2026-09-27 回测铁律）: **skew≥200% 且 最低赔率<1.30** 同时满足才可单押，
否则必须 2 向覆盖（默认「最低赔率+次低赔率」）。

用法:
    python data/tmp/confidence_engine.py --p-max 40.7 --skew 135.7 --fav-odd 2.447 \
        [--q2] [--elo-div] [--spread 4.05]
    from confidence_engine import assess
    r = assess(p_max=40.7, skew=135.7, fav_odd=2.447, q2=True)
"""
import sys

LEVELS = ["LOW", "MID-LOW", "MID", "MID-HIGH", "HIGH"]

# 基础层阈值（strict 口径·AGENTS 置信度概率映射）
T_HIGH = 70.0
T_MID = 55.0
T_MIDLOW = 45.0


def base_level(p_max):
    """按市场最高隐含概率（去水·%）定基础层"""
    try:
        p = float(p_max)
    except (TypeError, ValueError):
        return None
    if p >= T_HIGH:
        return "HIGH"
    if p >= T_MID:
        return "MID"
    if p >= T_MIDLOW:
        return "MID-LOW"
    return "LOW"


def _shift(level, steps):
    """层位平移 steps 档（夹在边界内）"""
    if level not in LEVELS:
        return level
    i = LEVELS.index(level) + int(steps)
    return LEVELS[max(0, min(len(LEVELS) - 1, i))]


def single_allowed(skew, fav_odd):
    """单押准入（回测 227,495 场: 单押全体 50.08%≈抛硬币 → 双条件门禁）"""
    s = None
    try:
        s = float(skew)
    except (TypeError, ValueError):
        pass
    if s is not None and s < 100:          # 传入的是比例（如 1.357）→ 统一换算成百分数
        s = s * 100.0
    f = None
    try:
        f = float(fav_odd)
    except (TypeError, ValueError):
        pass
    if s is None or f is None:
        return {"ok": False, "why": "缺 skew 或最低赔率 → 不可单押（须 2 向覆盖）"}
    ok = (s >= 200.0) and (f < 1.30)
    if ok:
        return {"ok": True, "why": "skew %.0f%%≥200%% 且最低赔 %.2f<1.30 → 可单押" % (s, f)}
    return {"ok": False,
            "why": "不满足单押准入（skew %.0f%%%s · 最低赔 %.2f%s）→ 必须 2 向覆盖"
                   % (s, "≥200%" if s >= 200 else "<200%", f, "<1.30" if f < 1.30 else "≥1.30")}


_LVL5 = ['LOW', 'MID-LOW', 'MID', 'MID-HIGH', 'HIGH']


def _cap_level(cur, cap):
    """把 cur 夹到**不高于** cap（档位序 LOW < MID-LOW < MID < MID-HIGH < HIGH）"""
    try:
        return _LVL5[min(_LVL5.index(cur), _LVL5.index(cap))]
    except (ValueError, TypeError):
        return cur


def assess(p_max=None, skew=None, fav_odd=None, q2=False, elo_div=False,
           spread=None, fatigue_fav=None, intent_fav=None, completeness=None,
           inj_fav=None):        # 🔴2026-11-01 热门方伤停影响分（原 assess 无此参数 → 12.9 分完全不降档）
    """置信度层建议（含逐项依据）

    参数
      p_max   市场最高隐含概率（去水·%）
      skew    市场最高/次高隐含比（百分比或比例均可）
      fav_odd 最低赔率（热门赔率）
      q2      Q2 诱盘警报是否触发（公众热捧但欧亚不跟进）
      elo_div 低赔—ELO 背离是否触发
      spread  跨机构分歧（热门侧 %·P0-1）
      fatigue_fav  🔴S03.5 热门侧疲劳分（fatigue_intent.fatigue·≥2 降1档·λ-0.2）
      intent_fav   🔴S03.5 热门侧战意分（fatigue_intent.intent·≥2 升1档 / ≤-1 降1档）
    返回 {base, level, steps, reasons[], single{ok,why}, note}
    """
    base = base_level(p_max)
    if base is None:
        return {"base": None, "level": None, "steps": 0, "reasons": [],
                "single": {"ok": False, "why": "缺 p_max → 无法定层"},
                "note": "⚪缺市场最高隐含概率 → 信度层不可判（三态）"}
    reasons = []
    steps = 0

    # ── 降档信号 ──
    if q2:
        steps -= 1
        reasons.append("Q2 诱盘警报(公众热捧·欧亚不跟进) → −1")
    if elo_div:
        steps -= 1
        reasons.append("低赔—ELO 背离(|ELO差|≥30 且低赔≠ELO强方) → −1")
    _sk = None
    try:
        _sk = float(skew)
        # 🔴2026-10-30 批次4 修（A/B 实测抓出边界 bug）: 原判据 `_sk < 100` 会把
        #   **百分数 95**（95%<100）误判为比值 → ×100 = 9500% → 永远"强共识"（该降档的不降）。
        #   比值实际范围 1~5、百分数 30~500 → 用 10 作清晰分界。
        if _sk <= 10:
            _sk *= 100.0
    except (TypeError, ValueError):
        pass
    if _sk is not None and _sk < 150:
        steps -= 1
        reasons.append("弱共识 skew %.0f%%<150%%(市场首选≈随机) → −1" % _sk)
    # ── 升档信号 ──
    _sp = None
    _fo = None
    try:
        _sp = float(spread)
    except (TypeError, ValueError):
        pass
    try:
        _fo = float(fav_odd)
    except (TypeError, ValueError):
        pass
    if _sp is not None and _sp < 2.0:
        if _fo is not None and _fo < 1.50:
            steps += 1
            reasons.append("资金盘 spread %.2f%%<2%% 且热门 %.2f<1.50 → +1（回测 80.0/81.5%%）" % (_sp, _fo))
        else:
            steps += 0.5
            reasons.append("资金盘 spread %.2f%%<2%% → +0.5（回测 52.7/62.6%%）" % _sp)

    # ── 🔴S03.5 情境因子（疲劳/战意·2026-10-31 批次3 接入）──
    #   审计实证: fatigue_intent 算出的「疲劳≥2 降1档 / 战意差≥2 升1档」**只 print** →
    #   从未进入置信度（print-only 断链）。现接入，受下方 ±1 档夹逼约束。
    try:
        _ffv = float(fatigue_fav)
    except (TypeError, ValueError):
        _ffv = None
    if _ffv is not None and _ffv >= 2.0:
        steps -= 1
        reasons.append('情境S03.5 热门侧疲劳 %.1f≥2 → −1（Step3.5 疲劳惩罚·λ-0.2）' % _ffv)
    try:
        _ifv = float(intent_fav)
    except (TypeError, ValueError):
        _ifv = None
    if _ifv is not None:
        if _ifv <= -1.0:
            steps -= 1
            reasons.append('情境S03.5 热门侧战意 %+.1f≤-1（中游无欲/杯赛轮换）→ −1' % _ifv)
        elif _ifv >= 2.0:
            steps += 1
            reasons.append('情境S03.5 热门侧战意 %+.1f≥2（争冠/保级）→ +1' % _ifv)

    # 🔴2026-11-01 伤停 → 置信度（原 assess 无 inj 参数 → 伤停 12.9 分只改概率·置信度纹丝不动）
    #   依据: 铁则32（≥4.0 重度 → 降档）+ M1（≥15 且仍为热门 = 逆基本面 → 硬降 1 档）
    try:
        _ijv = float(inj_fav)
    except (TypeError, ValueError):
        _ijv = None
    if _ijv is not None and _ijv > 0:
        if _ijv >= 15.0:
            steps -= 1
            reasons.append('🔴伤停 M1 热门侧 %.1f≥15 且仍为热门（逆基本面）→ −1 档（硬动作）' % _ijv)
        elif _ijv >= 4.0:
            steps -= 0.5
            reasons.append('伤停 铁则32 热门侧 %.1f≥4.0（重度）→ −0.5 档' % _ijv)
        elif _ijv >= 2.0:
            steps -= 0.25
            reasons.append('伤停 热门侧 %.1f（轻度 2-4）→ −0.25 档' % _ijv)

    # 合计夹逼 ±1 档（只调置信度铁律）
    steps = max(-1, min(1, steps)) if steps != 0 else 0
    # 半档（+0.5）用四舍五入到整数档处理：>0 → +1
    _st = 1 if steps >= 0.5 else (-1 if steps <= -0.5 else 0)
    level = _shift(base, _st)
    if _st != steps:
        reasons.append("合计夹逼在 ±1 档（只调置信度·不反转方向）")

    # 🔴🔴2026-10-31 复盘固化（case301 实抓·用户追问「还会不会再犯」）
    #   case301 数据源仅 **3/8**（euro_odds 队名解析失败 / h2h / xg / 伤停 全缺）
    #   却因 skew367%+D1 给了 **HIGH** → 高置信建立在残缺数据上，
    #   违背既有「数据缺失须降级/三态标注」原则（当时**零防线**）。
    #   封顶规则（⚠️阈值经验值·**未回测**）：≤3 源 → MID-LOW ｜ 4 源 → MID ｜ ≥5 源不封顶
#   🔴按**绝对源数**（不按比例）→ 分母变化（8→7·排除已停用 api_football）不影响本逻辑
    if completeness not in (None, ''):
        try:
            _cn = int(str(completeness).split('/')[0])
            _cap = 'MID-LOW' if _cn <= 3 else ('MID' if _cn <= 4 else None)
            if _cap:
                _lv2 = _cap_level(level, _cap)
                if _lv2 != level:
                    reasons.append(
                        "🔴数据完整度 %s → **置信封顶 %s**（原 %s·case301 教训·阈值待回测）"
                        % (completeness, _cap, level))
                else:
                    # 🔴留痕铁律：机制跑了但没改变结论也必须写（否则审计判「未执行」）
                    reasons.append(
                        "数据完整度 %s → 封顶上限 %s（当前 %s 已 ≤ 上限·无需再压）"
                        % (completeness, _cap, level))
                level = _lv2
            else:
                reasons.append("数据完整度 %s（≥5/8）→ 不封顶" % completeness)
        except (ValueError, TypeError, AttributeError):
            pass

    return {
        "base": base, "level": level, "steps": _st,
        "reasons": reasons,
        "single": single_allowed(skew, fav_odd),
        "note": "🔴脚本建议层=%s（基础 %s %+d 档）·最终判定权在模型·可用但需留痕依据"
                % (level, base, _st),
    }


def fmt(r):
    L = ["🔴置信度层建议(脚本·confidence_engine·只调置信度·不反转方向)"]
    if not r.get("level"):
        L.append("   " + r.get("note", "三态"))
        return "\n".join(L)
    L.append("   基础层 %s（p_max 映射）→ 调整后 **%s**（%+d 档）"
             % (r["base"], r["level"], r["steps"]))
    for x in r["reasons"]:
        L.append("     · " + x)
    if not r["reasons"]:
        L.append("     · 无升降档信号触发（维持基础层）")
    L.append("   单押准入: %s" % r["single"]["why"])
    return "\n".join(L)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    a = sys.argv
    def _g(k, cast=float):
        if k in a and a.index(k) + 1 < len(a):
            try:
                return cast(a[a.index(k) + 1])
            except Exception:
                return None
        return None
    r = assess(p_max=_g("--p-max"), skew=_g("--skew"), fav_odd=_g("--fav-odd"),
               q2=("--q2" in a), elo_div=("--elo-div" in a), spread=_g("--spread"))
    print(fmt(r))


if __name__ == "__main__":
    main()
