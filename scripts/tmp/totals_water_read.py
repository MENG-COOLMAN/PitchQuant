# -*- coding: utf-8 -*-
"""SL-totals-water-read —— 大小球盘口水位精读（2026-10-11·按用户升级方案完整接入）

🔴 定位与边界:
  · 本模块 = Step6/Step7 的【量级标签 + 置信度】辅助源，**不反转 L2 硬核方向**
  · 🔴 **未回测声明**: 盘口线锚定 / 盘口移动(8象限) / 水位动态时间加权 —— Matches.csv(148,395场) 无对应字段
    (无大小球盘口线 / 无初盘-临场双时点 / 无大小球水位时序) → **无法历史回测**
  · 已回测部分（2026-10-11·148,395场·时间分割 80/20·train 118,716 / test 29,680）:
      ① 泊松反推 λ vs 实测均球 偏差 ≤0.11 球（train/test 一致）→ ✅ 成立
      ② 碾压局陷阱(Layer4) → ⚠️ **回测反证**（深盘强主实际 3.23~3.41 球·over 63~67% ≫ 基准 2.62/48.6%；
         「大球隐含≤50%」与「>50%」两组几乎无差 3.23 vs 3.25）→ **按用户 2026-10-11 指令「严格按方案执行」启用**·
         回测反证已留痕（docs/方案评审_大小球盘口水位精读_20261011.md）→ 待样本积累后复核
      ③ 跨机构 over 分歧 → ❌ 不达门禁（控制 over 赔率后 ≤1.4pp）→ 不接入
  · λ_line 可由 **1xbet Totals 多档**(0.5~6.5) 插值求「均衡线」实现（无需新数据源）

🔴 数据来源（2026-10-11 审计补·治「存在≠活跃」）:
  · Layer1 多档 Totals 三级来源: `--totals-multi` → `data/tmp/_totals_multi.json` → **本场快照 raw_1xbet 自动提取**
  · Layer3 初盘/临场: `--line-open/--line-close/--water-open/--water-close` → **本场快照多时点自动提取**
  · 时间权重: `--mins-to-ko` → `--kickoff` 计算 → **快照 kickoff_bj 自动计算**
  （快照 = `data/tmp/snapshots/*.json`，由 snapshot_save.py 采集·T-0 早盘 … 临场）

用法:
  python data/tmp/totals_water_read.py --o25 1.712 --u25 2.32 [--line 2.75 --line-open 2.5 --water-open 1.05 --water-close 1.02] [--home-odds 2.722 --handi 0]
  python data/tmp/totals_water_read.py --home 阿拉维斯 --away 马德里竞技 --o25 1.97 --u25 1.97   # 自动读本场快照
  代码: from totals_water_read import water_read, snapshot_inputs
"""
import sys, math, json, argparse, os

sys.stdout.reconfigure(encoding='utf-8')

# 🔴2026-10-11 用户指令「严格按升级方案执行」→ Layer4 启用；独立回测反证记录见 docs/方案评审_大小球盘口水位精读_20261011.md
TRAP_ENABLED = True
UNBACKTESTED = True    # Layer1/3/水位动态时间加权 无字段可回测 → 输出标注

BINS = [(1.8, '极小球'), (2.2, '小球'), (2.5, '中小'), (2.8, '中性'),
        (3.1, '中大'), (3.4, '大球'), (3.8, '很大'), (4.2, '超大'), (99, '极超')]


def devig(o, u):
    """大小球两向赔率 → 去水真概率 p_over_fair"""
    po, pu = 1.0 / float(o), 1.0 / float(u)
    return po / (po + pu)


def lam_from_p(p):
    """over2.5 概率 → 泊松反解期望总进球 λ（解 1-e^-λ(1+λ+λ²/2)=p）"""
    lo, hi = 0.05, 9.0
    for _ in range(80):
        m = (lo + hi) / 2
        q = 1 - math.exp(-m) * (1 + m + m * m / 2)
        if q < p:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2


def fair_line(totals_rows):
    """🔴Layer1 盘口线锚定：由多档 Totals 插值求「均衡线」(p_over≈50% 的中位数线·方案 §2.1/2.2)

    totals_rows: [{'hdp': 2.5, 'over': 1.712, 'under': 2.32}, ...]
    返回 (line, p_over_fair)；未跨越 50% 时用最接近档 p 反推等效线（= 该档报价隐含 λ）
    """
    pts = []
    for r in totals_rows or []:
        try:
            h = float(r.get('hdp'))
            p = devig(r.get('over'), r.get('under'))
            pts.append((h, p))
        except Exception:
            continue
    if not pts:
        return None, None
    pts.sort()
    for (h1, p1), (h2, p2) in zip(pts, pts[1:]):
        if (p1 - 0.5) * (p2 - 0.5) <= 0 and p1 != p2:
            line = h1 + (0.5 - p1) * (h2 - h1) / (p2 - p1)
            return round(line, 3), 0.5
    h, p = min(pts, key=lambda x: abs(x[1] - 0.5))
    return round(lam_from_p(p), 3), round(p, 4)


def move_quadrant(line_open, line_close, water_open, water_close):
    """🔴Layer3 盘口移动 8 象限（方案 §4.1·需初盘/临场·未回测）→ (λ修正, 象限)"""
    if line_open is None or line_close is None:
        return 0.0, 'neutral', None
    dline = float(line_close) - float(line_open)
    dwater = (float(water_close) - float(water_open)) if (water_open is not None and water_close is not None) else 0.0
    # 🔴P51(2026-10-31 用户指令「查专业机构怎么读欧亚盘·搬进模型」):
    #   亚盘结构与美式 spread 相反: **美式调盘口保等赔 · 亚盘保持盘口调水位**
    #   → 口径: 升盘(线↑)=抬门槛(偏大球) · 降水(over水位↓)=压价(偏大球)
    #     「升盘 + 降水」= 真看大球（最强） ｜「升盘 + 升水」= 盘升水阻（假动作·仅微正）
    #     「降盘 + 降水」= 真看小球（最强） ｜「降盘 + 升水」= 盘降水诱（假动作·微正=反向）
    #   🔴原实现 Q1(+0.30 升盘+升水) / Q2(+0.05 升盘+降水) 与本口径**方向相反** → 已修
    if dline >= 0.5 and abs(dwater) <= 0.05:      return 0.40, 'Q7(大幅升盘·水不动)', (dline, dwater)
    if dline <= -0.5 and abs(dwater) <= 0.05:     return -0.40, 'Q8(大幅降盘·水不动)', (dline, dwater)
    if dline > 0 and dwater < -0.05:              return 0.35, 'Q2(升盘+降水·真看大球)', (dline, dwater)
    if dline > 0:                                 return -0.10, 'Q1(升盘+升水·盘升水阻)', (dline, dwater)
    if dline < 0 and dwater <= 0:                 return -0.35, 'Q4(降盘+降水·真看小球)', (dline, dwater)
    if dline < 0:                                 return 0.10, 'Q3(降盘+升水·盘降水诱)', (dline, dwater)
    if dline == 0 and dwater < -0.10:             return 0.15, 'Q5(线不动+降水·纯资金看大)', (dline, dwater)
    if dline == 0 and dwater > 0.10:              return -0.15, 'Q6(线不动+升水·纯资金看小)', (dline, dwater)
    if dline == 0 and abs(dwater) <= 0.10 and (water_open is not None):
        return 0.0, 'FREEZE(线水双不动·line freeze 庄家自信)', (dline, dwater)
    return 0.0, 'neutral', (dline, dwater)


def time_weight(minutes_to_ko):
    """🔴临场时间窗口加权（方案 §4.2）: >24h→0.3 / 24h~1h→0.5 / ≤1h→1.0（未回测）"""
    if minutes_to_ko is None:
        return 1.0, '未知'
    m = float(minutes_to_ko)
    # 🔴2026-10-11 审计补: 负数 = 比赛已开始（历史场次复跑 / 快照时点已过）
    #   原实现落入下一条 `m <= 60` → 误给最高权重 1.0 且标签写成「T-1h内(终盘确认)」= 语义错误
    #   → 降为 0.5（时点已过·时效降级）并显式标注
    if m < 0:      return 0.5, '⚠️已开赛(时点已过·时效降级)'
    if m <= 60:    return 1.0, 'T-1h内(终盘确认)'
    if m <= 1440:  return 0.5, 'T-24h~T-1h(资金入场)'
    return 0.3, 'T-24h前(早盘信息)'


# ─────────────────────────────────────────────────────────────
# 🔴2026-10-11 审计补（用户「严格检查新部分是否完全接入」）:
#   Layer1 多档 / Layer3 初盘-临场线水位 / 时间权重 原在 calc_all 路径**恒为 None**（接口缺参）
#   → 8 象限恒 neutral = 典型「存在≠活跃」→ 补自动数据源（快照 raw_1xbet·模型已有采集链路）
# ─────────────────────────────────────────────────────────────
def totals_from_raw(raw):
    """1xbet 原始响应 → Totals 全档 [{'hdp','over','under'}]

    兼容两种 bookmakers 结构: dict{'1xbet': [markets]} / list[{'name':'1xbet',...}]
    """
    mk = []
    bms = (raw or {}).get('bookmakers')
    if isinstance(bms, dict):
        mk = bms.get('1xbet') or []
    elif isinstance(bms, list):
        for b in bms:
            if str((b or {}).get('name', '')).lower() == '1xbet':
                mk = b.get('markets') or b.get('odds') or []
    rows = []
    for m in mk or []:
        if isinstance(m, dict) and str(m.get('name', '')).lower() == 'totals':
            for o in (m.get('odds') or []):
                try:
                    rows.append({'hdp': float(o.get('hdp')),
                                 'over': float(o.get('over')),
                                 'under': float(o.get('under'))})
                except Exception:
                    continue
    return rows


def _water_at(rows, line):
    """取最接近 line 档的 over 水位"""
    best = None
    for r in rows or []:
        try:
            d = abs(float(r['hdp']) - float(line))
        except Exception:
            continue
        if best is None or d < best[0]:
            best = (d, float(r['over']))
    return best[1] if best else None


def snapshot_inputs(home, away):
    """🔴本场快照（多时点）→ Layer1 多档 + Layer3 初盘/临场 + 距开赛分钟（自动·无需手工填）

    返回 {points_n, totals_rows, line_open, line_close, water_open, water_close, mins_to_ko, note}
    无快照 / 无 Totals / 单时点 → 相应字段 None + note 说明（三态·禁臆造）
    """
    out = {'points_n': 0, 'totals_rows': None, 'line_open': None, 'line_close': None,
           'water_open': None, 'water_close': None, 'mins_to_ko': None, 'note': None}
    if not home or not away:
        out['note'] = '未提供队名 → 快照自动提取不触发'
        return out
    try:
        from snapshot_save import find_for, SNAP_DIR
        r = find_for(home, away)
    except Exception as e:
        out['note'] = '快照模块不可用(%s)' % str(e)[:40]
        return out
    pts = r.get('points') or []
    out['points_n'] = len(pts)
    if not pts:
        out['note'] = '无本场快照(T-0 缺失)'
        return out
    seq = []   # [(line, water, rows)]
    for p in pts:
        try:
            d = json.load(open(os.path.join(SNAP_DIR, p['file']), encoding='utf-8'))
        except Exception:
            continue
        g = None
        # 🔴2026-10-15 修复 P0（多场快照恒取首场·静默失败）：
        #   原条件 `_g.event_id == p.event_id or str(_g.home) == str(p.get('home', _g.home))`
        #   —— p 是 find_for 的 point，**无 `home` 键** → `.get('home', 默认)` 的默认值取自 _g 自身
        #   → **自比恒真** → 任何多场快照都命中**第一场**（欧冠 9 场 → 其余 8 场错用首场的
        #     λ_line/初盘线/临场线/水位·且无任何告警）。
        #   修：① event_id 归一为 str 比较 ② 队名回退**仅当 p 真含非空 home** ③ 未命中写三态 note。
        for _g in (d.get('games') or []):
            _hit = False
            _gid, _pid = _g.get('event_id'), p.get('event_id')
            if _gid is not None and _pid is not None:
                _hit = str(_gid).strip() == str(_pid).strip()
            if not _hit and p.get('home'):
                _hit = (str(_g.get('home') or '').strip().lower()
                        == str(p.get('home')).strip().lower())
            if _hit:
                g = _g
                break
        if g is None:
            out['note'] = ('⚠️快照匹配失败: event_id=%s 未在 %s 的 %d 场中命中（不臆造·三态）'
                           % (p.get('event_id'), p.get('file'), len(d.get('games') or [])))
            continue
        rows = totals_from_raw(g.get('raw_1xbet'))
        if not rows:
            continue
        ln, _p50 = fair_line(rows)
        seq.append((ln, _water_at(rows, ln), rows))
    if not seq:
        out['note'] = '快照 %d 时点但均无 Totals 多档 → 多档插值不触发' % len(pts)
        return out
    out['totals_rows'] = seq[-1][2]
    out['line_close'], out['water_close'] = seq[-1][0], seq[-1][1]
    out['line_open'], out['water_open'] = seq[0][0], seq[0][1]
    if len(seq) < 2:
        out['line_open'] = out['water_open'] = None
        out['note'] = '仅 1 时点 → 8象限不触发(需初盘+临场·三态)'
    else:
        out['note'] = '快照 %d 时点 → Layer3 用首点(初盘)/末点(临场)' % len(seq)
    # 距开赛分钟（末时点 kickoff_bj − now）
    try:
        import datetime as _d
        ko = (pts[-1].get('kickoff_bj') or '').strip()
        if ko:
            out['mins_to_ko'] = round((_d.datetime.strptime(ko[:16], '%Y-%m-%d %H:%M')
                                       - _d.datetime.now()).total_seconds() / 60.0, 1)
    except Exception:
        pass
    return out


def water_read(o25=None, u25=None, line=None, totals_rows=None,
               line_open=None, line_close=None, water_open=None, water_close=None,
               home_win_odds=None, handicap=None, minutes_to_ko=None,
               lambda_market=None, lambda_table=None, lambda_pois=None):
    out = {'unbacktested': UNBACKTESTED, 'trap_enabled': TRAP_ENABLED, 'notes': []}
    # ── 2. 静态水位先算 p_over_fair（Layer1 等效线回退需用）──
    lam_water = lam_pois = None
    p = None
    if o25 and u25:
        p = devig(o25, u25)
        out['p_over_fair'] = round(p, 4)
        lam_pois = lam_from_p(p)
    # ── 1. 盘口线主锚（Layer1）: 多档 Totals 插值均衡线 → 否则 O2.5 反推等效线（方案 §八 容错）──
    if line is None:
        # 🔴2026-10-11 审计修复(P0·口径混淆): λ_line 必须是「λ」而非「均衡线数值」——
        #   原实现取 fair_line() 的均衡线(≈2.5 的盘口值·且跨越 50% 时 p 人为设 0.5)
        #   → lam_from_p(0.5) 恒定 → **四场 λ_line 全等 2.51·该源(融合权重 0.30)退化为常数失效**；
        #   而真正的本场去水概率只写在 elif 分支(几乎走不到)。
        #   修正: 优先用本场 O2.5 去水 p 反推 λ（Layer1「盘口线锚定」的本意）；
        #   多档 Totals 均衡线仅作 notes 参考（盘口值·非 λ）。
        if p is not None:
            line = round(lam_from_p(p), 3)
            out['notes'].append('λ_line 由本场 O2.5 去水 p=%.4f 反推 %.2f（Layer1 盘口线锚定）' % (p, line))
            _fl, _p50 = fair_line(totals_rows)
            if _fl is not None:
                out['notes'].append('参考: 多档 Totals 插值均衡线 %.2f（盘口值·非 λ·不作 λ_line）' % _fl)
        else:
            line, _p50 = fair_line(totals_rows)
            if line is not None:
                out['notes'].append('无 O2.5 输入 → 退用多档 Totals 均衡线 %.2f（仅参考·非常规路径）' % line)
    out['lambda_line'] = round(line, 3) if line is not None else None
    if p is not None:
        base_line = line if line is not None else lam_from_p(p)
        lam_water = base_line + (p - 0.50) * 1.5
        out['lambda_water'] = round(lam_water, 3)
        out['lambda_pois'] = round(lam_pois, 3)
    if lambda_pois is not None:
        out['lambda_pois'] = round(float(lambda_pois), 3)
        lam_pois = float(lambda_pois)
    # ── 3. 多源加权融合（方案 §6: market .30 / line .30 / water .20 / pois .10 / table .10·缺失按可用归一）──
    srcs = {}
    if lambda_market is not None: srcs['market'] = (float(lambda_market), 0.30)
    # 🔴P51(2026-10-31 用户指令「尤其要获取真实的欧亚盘开盘数·不要所有比赛都以大2.5判断」):
    #   line 源**优先多档 Totals 插值均衡线**（机构直接定价·本场 3.42）
    #   O2.5 单档反推（本场 3.55）降为交叉验证 → 修掉「只用 O2.5 单档」这一残留
    _line_src = None
    try:
        _n_rows = len([r for r in (totals_rows or []) if r.get('hdp') is not None])
        if _n_rows >= 4:
            _fl, _ = fair_line(totals_rows)
            if _fl is not None and 1.5 < float(_fl) < 6.5:
                _line_src = float(_fl)
                out['line_fair'] = round(_line_src, 3)
                out['notes'].append(
                    'P51 盘口线取**均衡线 %.2f**（%d 档插值·机构直接定价）｜O2.5 反推 %.2f 仅交叉验证'
                    % (_line_src, _n_rows, float(line) if line is not None else 0))
    except Exception:
        _line_src = None
    if _line_src is None and line is not None:
        _line_src = float(line)
    if _line_src is not None:
        srcs['line'] = (_line_src, 0.30)
        out['lambda_line'] = round(float(_line_src), 3)   # 🔴P51: 展示同步（否则审计看到 3.55 而实际用 3.42）
    if lam_water is not None:     srcs['water'] = (lam_water, 0.20)
    if lam_pois is not None:      srcs['pois'] = (lam_pois, 0.10)
    if lambda_table is not None:  srcs['table'] = (float(lambda_table), 0.10)
    # 🔴第 6 源 handi（2026-10-12 用户指令「不回测直接加入」）——
    #   数据: Matches 148,127 场实测「让球档 → 实际均球」，取下与市场期望的【修正量】(train)
    #   诚实边界: 时间分割回测显示修正量仅 ±0.05 球·MAE 改善 0.0016（≈0）→ **权重压至 0.05**（最小源）
    #   · 未回测直接接入（用户指令）· ⏳待前瞻验证 · 只调量级标签/置信度·永不反转 L2 方向
    if handicap is not None:
        _h = abs(float(handicap))
        _fix = (-0.046 if _h < 0.001 else
                -0.036 if _h < 0.5 else
                -0.011 if _h < 1.0 else
                0.025 if _h < 1.5 else
                0.029 if _h < 2.0 else 0.050)
        _hbase = (float(lambda_market) if lambda_market is not None
                  else (lam_from_p(p) if p is not None else None))
        if _hbase is not None:
            srcs['handi'] = (_hbase + _fix, 0.05)
            out['lambda_handi'] = round(_hbase + _fix, 3)
            out['handi_fix'] = round(_fix, 4)
            out['notes'].append('第6源 handi(让球档修正量 %+.3f 球·Matches 148,127场·未回测直接接入·权重0.05)' % _fix)
    tw = sum(w for _, w in srcs.values())
    lam_base = sum(v * w for v, w in srcs.values()) / tw if tw else None
    out['lambda_base'] = round(lam_base, 3) if lam_base else None
    out['sources'] = sorted(srcs)
    # ── 4. 盘口移动 8 象限（Layer3·临场加权）──
    lam_move, quad, mv = move_quadrant(line_open, line_close, water_open, water_close)
    w, wlab = time_weight(minutes_to_ko)
    out['lambda_move'] = round(lam_move * w, 3)
    out['quadrant'] = quad
    out['time_window'] = wlab
    out['mins_to_ko'] = minutes_to_ko
    if mv:
        out['notes'].append('8象限(未回测): 线移动 %+.2f · 水位移动 %+.3f → %s · 时间权重 %.1f' % (mv[0], mv[1], quad, w))
    # ── 5. 碾压局陷阱（Layer4·方案 P0·按用户指令启用·回测反证已留痕）──
    trap_adj = 0.0
    if TRAP_ENABLED and home_win_odds is not None and handicap is not None and line is not None:
        if float(home_win_odds) <= 1.40 and float(handicap) <= -1.5 and float(line) <= 2.5:
            if water_close is not None and float(water_close) > 1.95:
                trap_adj = -0.40
            elif water_close is not None and float(water_close) < 1.85:
                trap_adj = 0.0
            else:
                trap_adj = -0.20
            out['notes'].append('碾压局陷阱触发 λ%+.2f（⚠️2026-10-11 回测反证·按指令启用·待复核）' % trap_adj)
    out['trap_adj'] = trap_adj
    # ── 6. λ_final + 九档量级（方案 §四）──
    lam_final = (lam_base or 0) + lam_move * w + trap_adj
    out['lambda_final'] = round(lam_final, 3) if lam_base else None
    out['totals_bin'] = next(b for t, b in BINS if lam_final < t) if lam_base else None
    # ── 7. 置信度（源间离散·方案 §6 step8）──
    vals = [v for v, _ in srcs.values()]
    if len(vals) >= 2:
        spread = max(vals) - min(vals)
        out['src_spread'] = round(spread, 3)
        out['confidence'] = 'HIGH' if spread < 0.25 else ('MID' if spread < 0.45 else 'LOW')
    else:
        out['confidence'] = 'LOW'
        out['notes'].append('单源 → 置信度降档（方案 §八 容错）')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--o25'); ap.add_argument('--u25')
    ap.add_argument('--line'); ap.add_argument('--line-open'); ap.add_argument('--line-close')
    ap.add_argument('--water-open'); ap.add_argument('--water-close')
    ap.add_argument('--home-odds'); ap.add_argument('--handi'); ap.add_argument('--mins-to-ko')
    ap.add_argument('--totals-json', help='多档 Totals JSON 文件或字符串')
    ap.add_argument('--home', help='主队（中文/英文·用来自动读本场快照）')
    ap.add_argument('--away', help='客队')
    ap.add_argument('--auto-snapshot', action='store_true', help='强制从快照自动提取（默认 --home/--away 给了就自动）')
    a = ap.parse_args()
    tr = None
    if a.totals_json:
        try:
            tr = json.load(open(a.totals_json, encoding='utf-8')) if os.path.exists(a.totals_json) else json.loads(a.totals_json)
        except Exception as e:
            print('⚠️ totals-json 解析失败: %s' % e)
    f = lambda x: float(x) if x else None
    lo, lc, wo, wc, mk, sn = f(a.line_open), f(a.line_close), f(a.water_open), f(a.water_close), f(a.mins_to_ko), {}
    if a.home and a.away:
        sn = snapshot_inputs(a.home, a.away)
        print('🔎 快照自动提取: %s（%d 时点）' % (sn.get('note'), sn.get('points_n') or 0))
        if tr is None:
            tr = sn.get('totals_rows')
        lo = lo if lo is not None else sn.get('line_open')
        lc = lc if lc is not None else sn.get('line_close')
        wo = wo if wo is not None else sn.get('water_open')
        wc = wc if wc is not None else sn.get('water_close')
        mk = mk if mk is not None else sn.get('mins_to_ko')
    r = water_read(o25=a.o25, u25=a.u25, line=f(a.line), totals_rows=tr,
                   line_open=lo, line_close=lc, water_open=wo, water_close=wc,
                   home_win_odds=f(a.home_odds), handicap=f(a.handi), minutes_to_ko=mk)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    print('🔴 未回测项(盘口线/盘口移动/水位动态)仅作参考·只调量级标签与置信度·永不反转 L2 方向')


if __name__ == '__main__':
    main()
