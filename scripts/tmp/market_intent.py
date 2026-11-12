# -*- coding: utf-8 -*-
"""
market_intent.py — V3.5.81 P12 赔率升降意图 → 方向精确判定（落地版·P12.1 修订）
====================================================================
定位：方向层「机构意图」单一封装。读取已存在的多时点快照（snapshot_save），
不新采数据、不改 P8/P10/P11 任何既有产物。

三个核心判断：
  ① ml_vert_analyze   机构欧赔三向(主/平/客)时序【联动结构】
                         - 剥离共同漂移（识别「降返还率」，杜绝三项齐降误报方向）
                         - 去水概率相对漂移 → 剪刀差/防平/真看好/平局信号/客胜镜像
                         - ≥3 时点分段(早0.1/中0.3/临0.6，权重待回测)；不足→首末两点三态
  ② eu_ah_cross       机构欧赔结构 × 亚盘时序【横向背离】
                         - 升盘(真实门槛调整) ≠ 只升水(高水诱)；升盘+升水=盘升水阻交闸门裁决
  ③ fundamental_gate + intent_fusion  基本面【真伪闸门】
                         - 真信号(信息驱动·足额) / 中性(降档) / 强诱盘(国米型·扩覆盖) / 矛盾(并列)
纪律：默认只调置信度/扩覆盖，不硬反转硬核方向；仅「真信号+亚盘强确认+临场」给 +1 档建议。
开关：data/tmp/p12_config.json 的 p12_market_intent = auto/off/on

🔴P12.1 修订（2026-10-26）：
  R2  快照<2 时点双兜底 —— end_ml（--eu 临场欧赔）构造临时点喂 ml_vert_analyze；
      handi/home_water 构造亚盘字符串喂 dual_channel（C1 散户热捧兜底）。
      注意 vertical_for.end_ah 需 _ah_full 的 list（非字符串），正式块 L1926 单时点本就不传
      → 这里同样不传；单时点 ah_vert 三态（cross_conf=0），强诱盘靠 C1 散户热捧成立。
  AD  保留 `engage`/`mode` 字段（on=True）→ direction_full 内「真信号 +1 档」仅在 on 生效；
      强诱盘/矛盾属防守动作不受限。
"""
import json
import os

try:
    import snapshot_save as SS
except Exception:  # 允许评审助手目录以 PYTHONPATH 方式运行
    SS = None

# ───────────────────────── 阈值（全部【待回测校准】） ─────────────────────────
P12_EPS_COMMON = 1.0     # 三向赔率% 两两差 < 此值且同向 → 降返还率(无方向)
P12_PP_STRONG = 2.0      # 去水概率相对漂移 ≥2pp = 强结构
P12_PP_WEAK = 1.0        # 1~2pp = 弱结构
P12_W_EARLY = 0.10
P12_W_MID = 0.30
P12_W_LATE = 0.60
P12_INJ_HEAVY = 4.0
P12_FAT_HEAVY = 2.0
P12_INTENT_GAP = 2.0

NAMES = ('H', 'D', 'A')


def load_config():
    """读取 p12_config.json；不存在/异常 → 默认 auto(先留痕)。"""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'p12_config.json')
    try:
        return json.load(open(p, encoding='utf-8')).get('p12_market_intent', 'auto')
    except Exception:
        return 'auto'


# ─────────────────────── ① 机构欧赔三向联动结构 ───────────────────────
def _parse_ml(s):
    try:
        o = [float(x) for x in str(s).split('/')]
        if len(o) < 3 or min(o) <= 1.0:
            return None, None
        inv = [1.0 / x for x in o]
        t = sum(inv)
        return o, [100 * x / t for x in inv]
    except Exception:
        return None, None


def _seg_of(points):
    """返回 (early, mid, late) 索引列表（按距开赛分钟）；无法解析 → 三个 None。"""
    import datetime as _dt

    def _m(p):
        try:
            ko = _dt.datetime.strptime(str(p.get('kickoff_bj'))[:16], '%Y-%m-%d %H:%M')
            ts = str(p.get('saved_at') or (p.get('extract') or {}).get('upd') or '')[:16]
            return (ko - _dt.datetime.strptime(ts, '%Y-%m-%d %H:%M')).total_seconds() / 60.0
        except Exception:
            return None
    mins = [_m(p) for p in points]
    if any(m is None for m in mins):
        return None, None, None
    early = [i for i, m in enumerate(mins) if m > 2880]
    mid = [i for i, m in enumerate(mins) if 90 < m <= 2880]
    late = [i for i, m in enumerate(mins) if m <= 90]
    return early, mid, late


def _structure_once(p0, p1):
    o0, pr0 = _parse_ml(p0['extract']['ml'])
    o1, pr1 = _parse_ml(p1['extract']['ml'])
    if not o0 or not o1:
        return None
    chg = [round(100 * (o1[k] - o0[k]) / o0[k], 2) for k in range(3)]
    dpp = [round(pr1[k] - pr0[k], 3) for k in range(3)]
    common_chg = round(sum(chg) / 3.0, 2)
    spread_chg = round(max(chg) - min(chg), 2)
    common_pp = round(sum(dpp) / 3.0, 3)
    rel = [round(dpp[k] - common_pp, 3) for k in range(3)]
    rH, rD, rA = rel
    same_sign = all(c >= 0 for c in chg) or all(c <= 0 for c in chg)
    if same_sign and spread_chg < P12_EPS_COMMON:
        return {'pattern': '降返还率/整体漂移(无方向)', 'rel': rel, 'chg': chg,
                'common_bias': common_chg, 'intent': {'H': 0, 'D': 0, 'A': 0}, 'strength': '无'}
    pattern = '单项异动无配合(弱/无结构)'
    intent = None
    if rH >= P12_PP_WEAK:
        if rD <= -P12_PP_WEAK:
            pattern, intent = '剪刀差诱平(主胜概率升+平赔被抬高→强主胜)', {'H': 1, 'D': -1, 'A': -1 if rA <= 0 else 0}
        elif rD >= P12_PP_WEAK and rA <= 0:
            pattern, intent = '主胜+防平(主队不败·主胜信心打折)', {'H': 1, 'D': 1, 'A': -1}
        elif rA <= -P12_PP_WEAK:
            pattern, intent = '主胜结构性真看好(压主胜+抬客胜)', {'H': 1, 'D': 0, 'A': -1}
        elif rD >= P12_PP_WEAK:
            pattern, intent = '主胜+防平(平局同步设防)', {'H': 1, 'D': 1, 'A': 0}
        else:
            pattern = '弱主胜结构(主胜概率升但平/客配合不足)'
    if rA >= P12_PP_WEAK:
        if rD <= -P12_PP_WEAK:
            pattern, intent = '剪刀差诱平(客胜概率升+平赔被抬高→强客胜)', {'H': -1 if rH <= 0 else 0, 'D': -1, 'A': 1}
        elif rD >= P12_PP_WEAK and rH <= 0:
            pattern, intent = '客胜+防平(客队不败)', {'H': -1, 'D': 1, 'A': 1}
        elif rH <= -P12_PP_WEAK:
            pattern, intent = '客胜结构性真看好(压客胜+抬主胜)', {'H': -1, 'D': 0, 'A': 1}
        elif rD >= P12_PP_WEAK:
            pattern, intent = '客胜+防平(平局同步设防)', {'H': 0, 'D': 1, 'A': 1}
        elif intent is None:
            pattern = '弱客胜结构(客胜概率升但平/主配合不足)'
    if intent is None and rD >= P12_PP_WEAK and rH <= 0 and rA <= 0:
        pattern, intent = '平局信号(单压平局·主客概率同降)', {'H': -1, 'D': 1, 'A': -1}
    m = max(abs(rH), abs(rD), abs(rA))
    strength = '强' if m >= P12_PP_STRONG else ('弱' if m >= P12_PP_WEAK else '无')
    if intent is None:
        intent = {k: round(max(-1.0, min(1.0, rel[i] / P12_PP_STRONG)), 3) for i, k in enumerate(NAMES)}
    return {'pattern': pattern, 'rel': rel, 'chg': chg, 'common_bias': common_chg,
            'intent': intent, 'strength': strength}


def ml_vert_analyze(points):
    """机构欧赔三向时序联动结构；主体用全场首末，≥3 点叠加分段临场确认/反转。"""
    valid = [p for p in points if str((p.get('extract') or {}).get('ml')) not in ('-', '', 'None')]
    if len(valid) < 2:
        return {'ok': False, 'pattern': '时点不足(<2)·三态', 'intent': {'H': 0, 'D': 0, 'A': 0}}
    st = _structure_once(valid[0], valid[-1])
    if not st:
        return {'ok': False, 'pattern': 'ML 解析失败·三态', 'intent': {'H': 0, 'D': 0, 'A': 0}}
    seg_label, note, intent = '首末两点', '', st['intent']
    early, mid, late = _seg_of(valid)
    if early is not None and len(valid) >= 3:
        acc = {'H': 0.0, 'D': 0.0, 'A': 0.0}
        wsum = 0.0
        for idxs, w in ((early, P12_W_EARLY), (mid, P12_W_MID), (late, P12_W_LATE)):
            seg = None
            if len(idxs) >= 2:
                seg = _structure_once(valid[idxs[0]], valid[idxs[-1]])
            elif len(idxs) == 1 and idxs == late:
                prev = max(i for i in range(len(valid)) if i < idxs[0])
                seg = _structure_once(valid[prev], valid[idxs[0]])
            if seg:
                for k in NAMES:
                    acc[k] += w * seg['intent'][k]
                wsum += w
        seg_label = '分段(早%.1f/中%.1f/临%.1f)%s' % (P12_W_EARLY, P12_W_MID, P12_W_LATE,
                                                     '·无临场点' if not late else '')
        if wsum > 0:
            seg_intent = {k: acc[k] / wsum for k in NAMES}
            ff = max(NAMES, key=lambda k: intent[k])
            sf = max(NAMES, key=lambda k: seg_intent[k])
            if ff == sf and intent[ff] > 0 and seg_intent[sf] > 0:
                note = '临场确认(全场与分段同向·增强)'
                intent = {k: round(max(-1, min(1, st['intent'][k] * 1.1 + 0.3 * seg_intent[k])), 3)
                          for k in NAMES}
            elif seg_intent[sf] > 0.5 and intent[ff] < 0.5:
                note = '⚠️临场反转(以临场为主·降权)'
                intent = {k: round(0.7 * seg_intent[k], 3) for k in NAMES}
            else:
                note = '分段方向不一致(维持全场首末·谨慎)'
                intent = {k: round(0.7 * st['intent'][k], 3) for k in NAMES}
    return {'ok': True, 'pattern': st['pattern'], 'rel': st['rel'], 'chg': st['chg'],
            'common_bias': st['common_bias'], 'intent': {k: round(intent[k], 3) for k in NAMES},
            'strength': st['strength'], 'segment': seg_label, 'note': note}


# ─────────────────────── ② 欧赔 × 亚盘横向背离 ───────────────────────
def _ah_home_move(ah_vert):
    """主队视角盘口/水位移动：lm_home≤-0.25 主队升盘；wm_home<0 主队降水。"""
    line0, line1 = ah_vert.get('line0'), ah_vert.get('line1')
    w0, w1 = ah_vert.get('w0'), ah_vert.get('w1')
    recv = '受让' in str(ah_vert.get('up_side', ''))
    if line0 is None or line1 is None:
        return None, None
    lm_fav = (line1 - line0) * (-1.0 if recv else 1.0)
    lm_home = lm_fav * (-1.0 if recv else 1.0)
    wm_fav = (w1 - w0) if (w0 is not None and w1 is not None) else 0.0
    wm_home = wm_fav * (-1.0 if recv else 1.0)
    return round(lm_home, 3), round(wm_home, 3)


def eu_ah_cross(ml_vert, ah_vert):
    if not ml_vert or not ml_vert.get('ok') or not ah_vert:
        return {'cross': '三态(缺欧赔结构或亚盘时序)', 'conf': 0}
    it = ml_vert['intent']
    fav = max(NAMES, key=lambda k: it[k])
    if it[fav] < 0.5 or ml_vert.get('strength') == '无':
        return {'cross': '欧赔无明确方向结构', 'conf': 0}
    if fav == 'D':
        lm, _ = _ah_home_move(ah_vert)
        if lm is not None and lm >= 0.25:
            return {'cross': '强确认(欧赔压平局+亚盘让球变浅)', 'conf': 1, 'fav': 'D'}
        return {'cross': '弱(平局无亚盘强支撑)', 'conf': 0.3, 'fav': 'D'}
    s = 1.0 if fav == 'H' else -1.0
    lm, wm = _ah_home_move(ah_vert)
    if lm is None:
        return {'cross': '亚盘盘口不可解析·三态', 'conf': 0}
    line_align = (s * lm) <= -0.25
    water_align = (s * wm) <= -0.03
    line_against = (s * lm) >= 0.25
    water_against = (s * wm) >= 0.03
    name = '主胜' if fav == 'H' else '客胜'
    if line_align and water_align:
        return {'cross': '强确认(欧赔结构性看%s+亚盘升盘降水)' % name, 'conf': 1, 'fav': fav}
    if line_align and water_against:
        return {'cross': '盘升水阻(欧赔看%s+亚盘升盘但高水·门槛升盘口同向·待基本面裁决)' % name, 'conf': 0.3, 'fav': fav}
    if (not line_align and not line_against) and water_against:
        return {'cross': '🔴真诱上(欧赔示好%s但亚盘不升盘只升水·高水诱)' % name, 'conf': -1, 'fav': fav}
    if line_against:
        return {'cross': '🔴明确背离(欧赔看%s但亚盘降盘·看弱)' % name, 'conf': -1, 'fav': fav}
    if line_align:
        return {'cross': '弱确认(欧赔看%s+亚盘升盘·水位中性)' % name, 'conf': 0.5, 'fav': fav}
    return {'cross': '中性(盘水均无明确配合)', 'conf': 0, 'fav': fav}


# ─────────────────────── ③ 基本面真伪闸门 + 融合 ───────────────────────
def fundamental_gate(ml_vert, cross, fund=None, dual=None):
    fund = fund or {}
    if not ml_vert or not ml_vert.get('ok') or ml_vert.get('strength') == '无':
        return {'gate': '三态(无欧赔结构)', 'fund_dir': 0, 'weight': 0.5}
    fav = max(NAMES, key=lambda k: ml_vert['intent'][k])
    h_inj = float(fund.get('home_inj') or 0)
    a_inj = float(fund.get('away_inj') or 0)
    h_fat = float(fund.get('home_fatigue') or 0)
    a_fat = float(fund.get('away_fatigue') or 0)
    h_int = float(fund.get('home_intent') or 0)
    a_int = float(fund.get('away_intent') or 0)
    h_rot = 1 if fund.get('home_rotation') else 0
    a_rot = 1 if fund.get('away_rotation') else 0
    score = ((h_inj - a_inj) * -0.35 + (a_fat - h_fat) * 0.5
             + (h_int - a_int) * 0.5 + (a_rot - h_rot) * 0.8)
    fund_dir = 1 if score >= 1.0 else (-1 if score <= -1.0 else 0)
    c1 = (dual or {}).get('C1')
    pub_fav = c1.get('fav') if c1 else None
    pub_heat = bool(c1 and c1.get('pct') is not None and c1['pct'] <= -2.0)
    fav_team = {'H': 1, 'A': -1, 'D': 0}.get(fav, 0)
    cross_conf = cross.get('conf', 0)
    if fav == 'D':
        return {'gate': '中性(平局·基本面不背书)', 'fund_dir': fund_dir, 'weight': 0.5, 'fav': fav}
    if fund_dir == 0:
        return {'gate': '中性(基本面无明显利好/利空·降一档)', 'fund_dir': 0, 'weight': 0.5, 'fav': fav}
    if fund_dir == fav_team:
        if cross_conf == 1 and str(ml_vert.get('segment', '')).startswith('分段'):
            return {'gate': '真信号(四重确认·信息驱动)', 'fund_dir': fund_dir, 'weight': 1.0, 'fav': fav}
        return {'gate': '真信号(基本面同向)', 'fund_dir': fund_dir, 'weight': 0.85, 'fav': fav}
    if pub_heat and pub_fav == fav and cross_conf <= 0:
        return {'gate': '🔴强诱盘(基本面反向+散户热捧+亚盘不确认·国米型)', 'fund_dir': fund_dir,
                'weight': -1.0, 'fav': fav}
    return {'gate': '矛盾待查(基本面反向·机构仍示好·强制并列)', 'fund_dir': fund_dir, 'weight': 0.25, 'fav': fav}


def intent_fusion(ml_vert, ah_vert=None, ou_vert=None, fund=None, dual=None, spread=None):
    cross = eu_ah_cross(ml_vert, ah_vert)
    gate = fundamental_gate(ml_vert, cross, fund=fund, dual=dual)
    it = (ml_vert or {}).get('intent', {'H': 0, 'D': 0, 'A': 0})
    w = gate.get('weight', 0.5)
    if spread is not None:
        if spread < 2.0:
            w *= 1.2
        elif spread > 4.0:
            w *= 0.7
    w = max(-1.0, min(1.0, w))
    shift = {k: round(it[k] * w, 3) for k in NAMES}
    if gate['gate'].startswith('🔴') and gate.get('fav'):
        shift[gate['fav']] = round(-abs(it[gate['fav']]) * 0.5, 3)
    g = gate['gate']
    if g.startswith('真信号') and cross.get('conf') == 1:
        action = '方向 +1 档建议(四重确认·LLM 终裁)'
    elif g.startswith('🔴'):
        action = '被诱方向降档 + 强制次方向并列/出口(不自动反转)'
    elif g.startswith('矛盾'):
        action = '强制并列、不跟单(机构分歧)'
    elif g.startswith('中性'):
        action = '仅调置信度 ±0.5 档 / 提示'
    else:
        action = '三态·不动作'
    ev = ['欧赔三向: %s（%s·%s）%s' % (ml_vert.get('pattern'), ml_vert.get('strength'),
                                       ml_vert.get('segment'),
                                       ('｜' + ml_vert.get('note')) if ml_vert.get('note') else ''),
          '欧亚横向: %s' % cross.get('cross'),
          '真伪闸门: %s' % g,
          '方向意图: 主%+.2f 平%+.2f 客%+.2f' % (shift['H'], shift['D'], shift['A'])]
    return {'shift': shift, 'gate': g, 'cross': cross.get('cross'), 'cross_conf': cross.get('conf'),
            'fav': gate.get('fav') or cross.get('fav'),
            'action': action, 'evidence': ev, 'confidence': abs(w), 'ml_vert': ml_vert,
            'ah_vert': ah_vert, 'dual': dual}


# ─────────────────────── 高层封装（calc_all 一次调用） ───────────────────────
def build_market_intent(home, away, txt_path=None, jc_series=None, fund=None,
                        kickoff=None, event_id=None, spread=None,
                        handi=None, home_water=None, end_ml=None):
    """calc_all 单一入口：从快照 + 竞彩 txt + 基本面，产出完整 P12 意图。
    任何一部分缺失都三态降级，绝不抛断主流程。

    🔴P12.1 正式执行时点双兜底（快照<2 时点时）：
      end_ml=(oh,od,oa)   → 构造临时欧赔临场点喂 ml_vert_analyze（让欧赔三向可算）
      handi/home_water    → 构造亚盘字符串喂 dual_channel（C1/C2 兜底，口径同 calc_all L1114-1118）
    注意：vertical_for.end_ah 需 _ah_full 的 list（非字符串），calc_all 正式块 L1926 单时点本就
          不传 end_ah → 这里同样不传；单时点 ah_vert 三态（cross_conf=0），强诱盘靠 C1 散户热捧成立。
    """
    if SS is None:
        return {'ok': False, 'reason': 'snapshot_save 不可用·三态'}
    try:
        sf = SS.find_for(home, away)
        points = sf.get('points') or []
        # 🔴P12.1 正式执行亚盘字符串（dual_channel 兜底用）
        end_ah = None
        if handi is not None and home_water is not None:
            try:
                end_ah = '让%+.2f 主%s/客0' % (float(handi), home_water)
            except Exception:
                end_ah = None
        # 🔴P12.1 单时点快照 + 临场欧赔 → 构造临时临场点
        pts = list(points)
        if len(pts) == 1 and end_ml is not None:
            try:
                pts.append({'saved_at': '正式执行',
                            'kickoff_bj': pts[-1].get('kickoff_bj'),
                            'extract': {'ml': '%.2f/%.2f/%.2f' % tuple(float(x) for x in end_ml)}})
            except Exception:
                pts = list(points)
        mv = ml_vert_analyze(pts)
        ah_vert = None
        try:
            # 🔴P12 口径：只传快照（不传 end_ah 字符串）；单时点 ah_vert 三态，亚盘横向由 dual 兜底
            vf = SS.vertical_for(home, away, event_id=event_id)
            ah_vert = vf.get('ah_vert')
        except Exception:
            ah_vert = None
        dual = None
        try:
            jc = jc_series
            if jc is None and txt_path and os.path.exists(txt_path):
                import calc_match as _cm
                _pd = _cm.parse_txt(open(txt_path, encoding='utf-8').read())
                jc = [(t, (v.get('胜'), v.get('平'), v.get('负'))) for t, v in (_pd.get('spf') or [])
                      if v.get('胜') and v.get('平') and v.get('负')]
            ah0 = points[0]['extract']['ah'] if points else None
            ah1 = points[-1]['extract']['ah'] if len(points) >= 2 else None
            if ah1 is None and end_ah is not None:
                ah1 = end_ah   # 🔴P12.1 快照<2 点用正式执行盘口兜底（dual_channel 接受字符串）
            wmin = None
            if kickoff:
                import datetime as _dt
                wmin = (_dt.datetime.strptime(str(kickoff)[:16], '%Y-%m-%d %H:%M')
                        - _dt.datetime.now()).total_seconds() / 60.0
            if jc and len(jc) >= 2:
                dual = SS.dual_channel(jc, None, ah0, ah1, wmin)
        except Exception:
            dual = None
        fu = intent_fusion(mv, ah_vert=ah_vert, fund=fund, dual=dual, spread=spread)
        fu['ok'] = True
        fu['count'] = sf.get('count')
        fu['points_used'] = len(pts)
        # 🔴适配：engage/mode → direction_full 内「真信号 +1 档」仅在 on 时生效
        fu['mode'] = load_config()
        fu['engage'] = (fu['mode'] == 'on')
        return fu
    except Exception as e:
        return {'ok': False, 'reason': 'P12 意图计算异常: %s·三态' % type(e).__name__}


# ─────────────────────── 合成 fixture 单元测试（check_sync 依据） ───────────────────────
def _mk_pts(o0, o1):
    return [{'saved_at': '2026-10-20 18:00', 'kickoff_bj': '2026-10-20 22:00',
             'extract': {'ml': '%.2f/%.2f/%.2f' % o0}},
            {'saved_at': '2026-10-20 21:00', 'kickoff_bj': '2026-10-20 22:00',
             'extract': {'ml': '%.2f/%.2f/%.2f' % o1}}]


def unit_tests():
    n = 0

    def check(name, cond, extra=''):
        nonlocal n
        assert cond, '❌ %s %s' % (name, extra)
        n += 1
        print('  ✅ %s %s' % (name, extra))

    mv = ml_vert_analyze(_mk_pts((2.00, 3.40, 3.80), (1.94, 3.30, 3.68)))
    check('降返还率不误报', mv['pattern'].startswith('降返还率') and mv['intent'] == {'H': 0, 'D': 0, 'A': 0}, mv['pattern'])
    mv = ml_vert_analyze(_mk_pts((2.00, 3.40, 3.80), (1.82, 3.78, 4.05)))
    check('剪刀差强主胜', mv['pattern'].startswith('剪刀差') and mv['intent']['H'] == 1, mv['pattern'])
    mv = ml_vert_analyze(_mk_pts((2.00, 3.60, 3.50), (1.85, 3.30, 4.10)))
    check('主胜+防平', mv['pattern'].startswith('主胜+防平') and mv['intent']['H'] == 1 and mv['intent']['D'] == 1, mv['pattern'])
    mv = ml_vert_analyze(_mk_pts((1.40, 4.80, 7.00), (1.32, 5.30, 7.60)))
    fu = intent_fusion(mv, ah_vert={'line0': -1.5, 'line1': -1.5, 'w0': 1.85, 'w1': 1.98,
                                   'combo': '盘稳·主水升', 'shift': -1, 'up_side': '主队(主让场)'},
                       fund={'home_inj': 6.0, 'away_inj': 0, 'home_rotation': True},
                       dual={'C1': {'fav': 'H', 'pct': -4.0}})
    check('国米型强诱盘', fu['gate'].startswith('🔴强诱盘') and fu['cross'].startswith('🔴真诱上'), fu['gate'])
    mv = ml_vert_analyze(_mk_pts((2.00, 3.40, 3.80), (1.82, 3.78, 4.05)))
    fu = intent_fusion(mv, ah_vert={'line0': -1.0, 'line1': -1.25, 'w0': 1.90, 'w1': 1.78,
                                   'combo': '升盘降水(真看好)', 'shift': 1, 'up_side': '主队(主让场)'},
                       fund={'home_inj': 0, 'away_inj': 6.0})
    check('真信号(基本面同向)', fu['gate'].startswith('真信号') and fu['cross'].startswith('强确认'), fu['gate'])
    cross = eu_ah_cross(mv, {'line0': -1.0, 'line1': -1.25, 'w0': 1.806, 'w1': 1.924,
                             'combo': '升盘升水', 'shift': -1, 'up_side': '主队(主让场)'})
    check('升盘升水=盘升水阻', cross['cross'].startswith('盘升水阻') and cross['conf'] == 0.3, cross['cross'])
    print('  P12 单元测试全部通过：%d/%d' % (n, 6))


if __name__ == '__main__':
    unit_tests()
