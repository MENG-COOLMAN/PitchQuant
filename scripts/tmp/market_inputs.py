# -*- coding: utf-8 -*-
"""统一市场数据入口 · market_inputs（V3.5.79 · 2026-10-17）

════════════════════════════════════════════════════════════════════
🔴 为什么需要这个模块（根因：同一类遗漏已发生 5 次）
────────────────────────────────────────────────────────────────────
历史事故（均为「数据源单点依赖 + 静默降级」）:
  2026-09-28  早盘快照有产出无消费端          → 数据链断裂
  2026-09-29  快照队名跨语言不匹配            → 恒降级(三态)
  2026-10-11  大小球 Layer3 8象限恒不可达     → 只传5参·quadrant 恒 neutral
  2026-10-17  N23 波胆/BTTS/让球水只认快照     → 三场全空转
  2026-10-17  多档 Totals 只认快照            → 真盘口线(3球)未参与·量级偏高 0.2-0.3 球

结构性根因（三条）:
  ① **取数分散**: calc_all 有 4 个独立段，各自实现一遍「参数→文件→快照→实时」降级链
     → 每个段都可能漏一环，且补丁只修被问到的那一处
  ② **静默降级**: 取不到就退回等效值（O2.5 反推 λ / None），不报错不醒目
  ③ **无端到端断言**: check_sync 只查「代码里有这字符串」，不查「跑一场真实比赛字段非空」

🔴 本模块 = 单一数据入口，统一降级链与来源标记
   降级链: 显式 overrides → 本地文件 → prestep 快照 → **实时 1xbet** → 三态(None + src)
   所有消费方（N21/N23/Step6.5/双通道）**只从这里取市场数据**，
   禁止在 calc_all 内再直接调 prestep_fetch / snapshot_inputs 取市场量。

用法:
    import market_inputs as MI
    mi = MI.resolve(home="埃弗顿", away="切尔西", event_id="72221318")
    mi["eq"]          # 均衡档 {'hdp':0.25,'home':1.79,'away':1.98} 或 None
    mi["cs"]          # {'1-1':6.5, '1-2':8.5, ...}（已剔除占位档）
    mi["btts"]        # {'yes':1.54,'no':2.349}
    mi["totals"]      # [{'hdp':2.5,'over':1.753,'under':2.248}, ...]
    mi["src"]         # {'eq':'实时1xbet(72221318)', 'cs':'实时1xbet(...)', ...}
    print(MI.report(mi))   # 数据链体检表
"""
import os
import io
import json
import time
import sys
import json

_TMP = os.path.dirname(os.path.abspath(__file__))
if _TMP not in sys.path:
    sys.path.insert(0, _TMP)

_CACHE = {}          # event_id -> raw（进程内缓存，一次分析只拉一次）
_LAST_SRC = {}       # 供诊断


# ────────────────────────────── 基础工具 ──────────────────────────────
def _f(x):
    """安全转 float"""
    try:
        v = float(x)
        return v
    except Exception:
        return None


def _api_key():
    k = os.environ.get("ODDS_API_KEY")
    if k:
        return k
    try:
        import prestep_fetch as _pf
        return getattr(_pf, "KEY", None)
    except Exception:
        return None


def _http_get(url):
    """优先复用 prestep_fetch.get（🔴2026-10-31 代理优先 + 直连回退4s + 重试）"""
    try:
        import prestep_fetch as _pf
        return _pf.get(url)
    except Exception:
        import urllib.request, os as _os
        _px = _os.environ.get('HTTPS_PROXY') or 'http://127.0.0.1:7897'
        _last = None
        for _ph, _to in ((_px, 20), (None, 4)):   # 🔴2026-10-31 代理优先 → 直连回退4s
            try:
                _op = (urllib.request.build_opener(urllib.request.ProxyHandler({})) if _ph is None
                       else urllib.request.build_opener(urllib.request.ProxyHandler({'http': _ph, 'https': _ph})))
                with _op.open(url, timeout=_to) as r:
                    return json.loads(r.read().decode("utf-8"))
            except Exception as _e:
                _last = _e
        raise _last


def fetch_raw(event_id):
    """🔴 实时 1xbet 全市场（单一 API 调用 · 进程内缓存）

    返回 raw dict 或 None（失败）
    """
    if not event_id:
        return None
    eid = str(event_id)
    if eid in _CACHE:
        return _CACHE[eid]
    key = _api_key()
    if not key:
        _CACHE[eid] = None
        return None
    url = ("https://api.odds-api.io/v3/odds?apiKey=%s&eventId=%s&bookmakers=1xbet"
           % (key, eid))
    try:
        raw = _http_get(url)
    except Exception:
        raw = None
    _CACHE[eid] = raw
    return raw


def parse_markets(raw):
    """raw(1xbet) → 结构化市场量

    返回 dict:
      ml      {'home','draw','away'}
      spread  [{'hdp','home','away'}]        全档（原序）
      totals  [{'hdp','over','under'}]       全档（升序）
      cs      {'1-0':11.0, ...}              🔴已剔除占位档(1<odds<100)
      btts    {'yes','no'}
      htft    {'胜胜':4.6, ...}               有则解析，无则 {}
    """
    out = {"ml": {}, "spread": [], "totals": [], "cs": {}, "btts": {}, "htft": {}}
    if not isinstance(raw, dict):
        return out
    bms = ((raw.get("bookmakers") or {}).get("1xbet")) or []
    for mk in bms:
        name = str((mk or {}).get("name") or "")
        odds = (mk or {}).get("odds") or []
        if name == "ML" and odds:
            o = odds[0] or {}
            for k in ("home", "draw", "away"):
                v = _f(o.get(k))
                if v is not None:
                    out["ml"][k] = v
        elif name == "Spread":
            for o in odds:
                h, a = _f((o or {}).get("home")), _f((o or {}).get("away"))
                hp = _f((o or {}).get("hdp"))
                if h is None or a is None or hp is None:
                    continue
                out["spread"].append({"hdp": hp, "home": h, "away": a})
        elif name == "Totals":
            for o in odds:
                ov, un = _f((o or {}).get("over")), _f((o or {}).get("under"))
                hp = _f((o or {}).get("hdp"))
                if ov is None or un is None or hp is None:
                    continue
                out["totals"].append({"hdp": hp, "over": ov, "under": un})
            out["totals"].sort(key=lambda r: r["hdp"])
        elif name == "Correct Score":
            for o in odds:
                lab = str((o or {}).get("label") or "").strip()
                v = _f((o or {}).get("odds"))
                # 🔴占位档剔除：1xbet CS 约 120 档，约 100 档赔率=100 为占位
                if lab and v is not None and 1 < v < 100:
                    out["cs"][lab] = v
        elif name == "Both Teams To Score" and odds:
            o = odds[0] or {}
            y, n = _f(o.get("yes")), _f(o.get("no"))
            if y is not None:
                out["btts"]["yes"] = y
            if n is not None:
                out["btts"]["no"] = n
        elif name in ("HT-FT", "Half Time / Full Time", "HTFT"):
            for o in odds:
                o = o or {}
                for k, v in o.items():
                    fv = _f(v)
                    if fv is not None:
                        out["htft"][str(k)] = fv
        # 🔴2026-11-01 Team Total（R11 零封直盘：TT under 0.5 = 该队被零封）
        elif name in ("Team Total Home", "Team Total Away", "Team Total"):
            _side = "h" if name.endswith("Home") else ("a" if name.endswith("Away") else "h")
            out.setdefault("tt_h", {})
            out.setdefault("tt_a", {})
            for o in odds:
                o = o or {}
                _ln = _f(o.get("hdp"))
                _ov, _un = _f(o.get("over")), _f(o.get("under"))
                if _ln is not None and _ov and _un:
                    out["tt_" + _side][_ln] = (_ov, _un)
    return out


def pick_equal_line(spread, tol=0.25):
    """🔴 均衡档：|主−客| 最小且 ≤tol（≈1.9/1.9）

    铁律（case229/234）：禁把深档当让球盘解读 → 无均衡档返回 None（P1 不采用·三态）
    """
    best, n = None, 0
    for o in spread or []:
        h, a = _f(o.get("home")), _f(o.get("away"))
        if h is None or a is None:
            continue
        n += 1
        d = abs(h - a)
        if best is None or d < best[0]:
            best = (d, o)
    if best is None:
        return None, 0
    if best[0] <= tol:
        return {"hdp": _f(best[1].get("hdp")), "home": _f(best[1].get("home")),
                "away": _f(best[1].get("away"))}, n
    return None, n


def _read_snap(p, eid):
    """读单个快照文件并按 event_id 取本场 → (markets, src, eid) 或 (None, {}, eid)"""
    try:
        sd = json.load(open(p, encoding="utf-8"))
    except Exception:
        return None, {}, eid
    for g in (sd.get("games") or []):
        if eid is None or str(g.get("event_id")) == str(eid):
            raw = {"bookmakers": {"1xbet": ((g.get("raw_1xbet") or {}).get("bookmakers") or {}).get("1xbet") or []}}
            return (parse_markets(raw),
                    {"_src": "prestep快照(%s)" % os.path.basename(p)},
                    g.get("event_id") or eid)
    return None, {}, eid


def _locate_event(home=None, away=None, league=None):
    """🔴2026-11-01 按队名查 Odds-API → (eventId, slug)

    🔴 根因（用户「Odds-API 是正常的·问题出在你」·核实成立）：
       原 `eid = str(event_id or snap_eid or "")` **只认** ①--event ②快照 event_id
       → 中文队名 + 无快照 = eid 恒空 → 不拉实时 1xbet → P10「三源不齐」
       → 被误写成「源不可用」。实测 Odds-API 正常（5000 场 / 科莫场 71945370）。

    🔴 实现要点（两次踩坑后收敛·用户「别把简单的事做复杂」）：
       ① **不带 league 一次返回 5000 场**（带 league 必须全 slug·传 `seriea` 会 404）
       ② **用 `cn2en_list` 精确子串匹配**，不用 `data_bridge.match_team` ——
          后者模糊匹配把「科莫」配到 `spain-segunda-federacion-women`（女足）过
       ③ 排除女足/青年/预备队（AGENTS 铁则：NL/U21 等须排除）
    """
    try:
        import prestep_fetch as _PF
    except Exception:
        return None, None

    def _cands(name):
        """名 → 全部候选（原文 + cn2en_list 英文），小写"""
        out = []
        if not name:
            return out
        out.append(str(name).strip().lower())
        try:
            from snapshot_save import cn2en_list
            for x in (cn2en_list(str(name)) or []):
                if x and str(x).strip().lower() not in out:
                    out.append(str(x).strip().lower())
        except Exception:
            pass
        return out

    _BAD = ('women', 'womens', "women's", 'u17', 'u19', 'u20', 'u21', 'u23',
            'reserve', 'youth', 'academy', 'feminine', 'femenina')

    def _hit(name, full):
        """候选名是否命中 full（子串双向·长度≥3 防假阳）"""
        if not full:
            return False
        _f = str(full).lower()
        for c in _cands(name):
            if len(c) >= 3 and (c in _f or _f in c):
                return True
        return False

    # 🔴2026-11-01 缓存（用户问「配额不会很快用完吧」→ 实测：100 请求/小时·
    #   5000 场只扣 1 次，但一次 calc_all 会调本函数 **2 次**（resolve + _oe9 段）
    #   → 加 10 分钟 TTL 缓存，2 次变 1 次；同批多场共用同一份 events）
    _CACHE = os.path.join('data', 'tmp', '_events_cache.json')
    _TTL = 600          # 10 分钟（events 时段内变化慢·够用）
    _now = time.time()
    _d = None
    try:
        if os.path.exists(_CACHE):
            _c = json.load(io.open(_CACHE, encoding='utf-8'))
            if (_now - float(_c.get('ts') or 0)) < _TTL and _c.get('events'):
                _d = _c['events']
    except Exception:
        _d = None
    if _d is None:
        try:
            _d = _PF.get('https://api.odds-api.io/v3/events?apiKey=%s'
                         '&sport=football&status=pending' % _PF.KEY)
            try:
                _keep = [{k: e.get(k) for k in ('id', 'home', 'away', 'league', 'date')}
                         for e in (_d or [])]
                io.open(_CACHE, 'w', encoding='utf-8').write(
                    json.dumps({'ts': _now, 'n': len(_keep), 'events': _keep},
                               ensure_ascii=False))
            except Exception:
                pass
        except Exception:
            return None, None

    for _e in (_d or []):
        try:
            _h, _a = str(_e.get('home') or ''), str(_e.get('away') or '')
            if not _h or not _a:
                continue
            _lg = (_e.get('league') or {}).get('slug') if isinstance(_e.get('league'), dict) else ''
            _probe = ('%s %s %s' % (_h, _a, _lg or '')).lower()
            if any(b in _probe for b in _BAD):     # 排除女足/青年
                continue
            if _hit(home, _h) and _hit(away, _a):
                return str(_e.get('id')), _lg
        except Exception:
            continue
    return None, None


def _from_event_id(eid, limit=14):
    """🔴2026-10-20 修复: **仅传 event_id 时**的快照通道

    根因: `_from_snapshot` 只按队名匹配 → calc_all 段④(N23) 调 `resolve(event_id=...)`
    不带队名 → 快照恒失配 → 波胆/让球水位全部为空 → P5 退化为 S3(泊松兜底 ×0.0)
    → 次锚偏离期望(ex. 254 次锚 2:0 偏离 1.42) → 锚-期望 ok=False。
    修复: 按 event_id 扫 snapshots 目录(按调取时刻倒序·取最接近赛前=最新那份)。
    """
    if not eid:
        return None, {}, eid
    snapdir = os.path.join(_TMP, "snapshots")
    try:
        files = [os.path.join(snapdir, x) for x in os.listdir(snapdir) if x.endswith(".json")]
        files.sort(key=lambda q: os.path.getmtime(q), reverse=True)
    except Exception:
        return None, {}, eid
    for p in files[:limit]:
        mk, src, got = _read_snap(p, eid)
        if mk:
            return mk, src, got
    return None, {}, eid


def _from_snapshot(home, away, event_id=None):
    """prestep 快照回读 raw_1xbet → (markets, src_dict, event_id)

    ① 队名通道（优先·可跨语言匹配）
    ② 缺队名/队名未命中 → event_id 通道（2026-10-20 补·治 N23「只传 event_id」断点）
    """
    eid0 = str(event_id or "")
    if home and away:
        try:
            from snapshot_save import find_for as _ff
            r = _ff(home, away) or {}
        except Exception:
            r = {}
        if r.get("count"):
            # 🔴2026-10-20 修(P1 口径): 原取 first(最早时点) → 与 line 210 设计意图
            #   「取最接近赛前=最新那份」相悖 → 临场分析反用 3h 前盘口
            #   (实测 利物浦-比利亚雷亚尔: 首点 hdp=-1.0/ML1.555 vs 末点 hdp=-1.25/ML1.524)
            #   → 改取 last(末点)·末点市场不全时回退 first(三态不静默)
            last = r.get("last") or {}
            first = r.get("first") or {}
            pick = last if last.get("file") else first
            f = pick.get("file")
            eid = pick.get("event_id")
            if f:
                p = str(f) if os.path.isabs(str(f)) else os.path.join(_TMP, "snapshots", os.path.basename(str(f)))
                if os.path.exists(p):
                    mk, src, got = _read_snap(p, eid)
                    if mk:
                        return mk, src, got
    if eid0:
        return _from_event_id(eid0)
    return None, {}, (eid0 or None)


# ────────────────────────────── 统一入口 ──────────────────────────────
def resolve(home=None, away=None, event_id=None, overrides=None, league=None):
    """🔴 统一市场数据入口

    降级链: overrides（显式传参） → prestep快照 → 实时 1xbet → 三态(None)
    每个字段独立标记来源，便于审计「这个数到底是哪来的」。

    overrides 支持: ml / spread / totals / cs / btts / eq
    """
    ov = overrides or {}
    mi = {"ml": {}, "spread": [], "totals": [], "cs": {}, "btts": {}, "htft": {},
          # 🔴2026-11-01 补 Team Total（R11 零封判定需要·原入口没有 → R11「被零封 缺」）
          "tt_h": {}, "tt_a": {},
          "eq": None, "eq_scan": 0, "src": {}, "coverage": 0, "notes": []}

    # ① prestep 快照（有时点基线价值）
    # 🔴2026-10-20: 传 event_id → 无队名/队名未命中时仍可按 event_id 命中（N23 只传 event_id）
    snap, ssrc, snap_eid = _from_snapshot(home, away, event_id)
    if snap:
        for k in ("ml", "spread", "totals", "cs", "btts", "htft"):
            if snap.get(k):
                mi[k] = snap[k]
                mi["src"][k] = ssrc.get("_src")
    eid = str(event_id or snap_eid or "")
    # 🔴2026-11-01 补「按队名查 events」降级（原缺这条 → 中文队名+无快照=恒三态）
    _loc_src = None
    if not eid and (home or away):
        # 🔴2026-11-01 用**调用方传入的联赛**过滤（原读不存在的 _last_league.json → None
        #   → 扫全部 7 slug → 英超先匹配上「科莫」→ 定位到错场 eventId=72221364）
        eid, _slug = _locate_event(home, away, league)
        if eid:
            _loc_src = '按队名定位(%s)' % (_slug or '?')
            mi["notes"].append("🔴按队名定位到 eventId=%s（slug=%s）—— "
                               "原实现无此降级路径 → 中文队名恒三态" % (eid, _slug or '?'))

    # ② 实时 1xbet 补齐（快照缺的字段）+ 均衡档
    raw = fetch_raw(eid) if eid else None
    live = parse_markets(raw) if raw else None
    lsrc = ("实时1xbet(%s)" % eid) if live else None
    if live:
        for k in ("ml", "spread", "totals", "cs", "btts", "htft", "tt_h", "tt_a"):
            if not mi.get(k) and live.get(k):
                mi[k] = live[k]
                mi["src"][k] = lsrc

    # ③ 显式 overrides（最高优先）
    for k in ("ml", "spread", "totals", "cs", "btts"):
        if ov.get(k):
            mi[k] = ov[k]
            mi["src"][k] = "显式传参"

    # ④ 均衡档（Spread 全档 → |主−客|≤0.25）
    if ov.get("eq"):
        mi["eq"] = ov["eq"]
        mi["src"]["eq"] = "显式传参"
    elif mi.get("spread"):
        eq, n = pick_equal_line(mi["spread"])
        mi["eq"], mi["eq_scan"] = eq, n
        if eq:
            mi["src"]["eq"] = mi["src"].get("spread") or "spread全档扫描"
        else:
            mi["notes"].append("⚪无均衡档(扫%d档·Δ>0.25)→P1不采用" % n)

    # ⑤ 派生：O2.5 / U2.5（取最接近 2.5 的档 · 无则用均衡档邻近）
    t = mi.get("totals") or []

    # ⑤.5 🔴滚球盘/已开赛检测（2026-10-17 审计加固·治 A2④「异常不静默」）
    # 赛前盘特征: ML 存在 且 Totals 多档(≥3)
    # 滚球盘特征: ML 缺失 + Totals 极少档 + 赔率极端（如滚球 2.5 线 大8.50/小1.07）
    # 反例（真实抓到）: event 72221318 已开赛 → ML=None, Totals 仅1档(2.5: 8.50/1.07)
    #                   旧实现把它当赛前盘 → 派生 O2.5=8.50（隐含大球 11.8%）→ 污染 λ
    _ml_ok = bool(mi.get("ml"))
    _extreme = False
    if t and len(t) <= 2:
        for _r in t:
            _o, _u = _r.get("over"), _r.get("under")
            try:
                if _o and _u and (max(float(_o), float(_u)) / max(min(float(_o), float(_u)), 0.01)) > 4.0:
                    _extreme = True
            except (TypeError, ValueError):
                pass
    mi["rolling_suspect"] = bool((not _ml_ok) and (len(t) < 3 or _extreme))
    if mi["rolling_suspect"]:
        mi["notes"].append(
            "🔴疑似滚球盘/已开赛（ML 缺失 + Totals 仅 %d 档%s）→ 派生 O2.5 不可信·仅赛前场次可用"
            % (len(t), "·赔率极端" if _extreme else ""))
        mi["src"]["o25"] = "🔴滚球疑似·已禁用"

    if t and not mi.get("rolling_suspect"):
        near = min(t, key=lambda r: abs(r["hdp"] - 2.5))
        if abs(near["hdp"] - 2.5) <= 0.25:
            mi["o25"], mi["u25"] = near["over"], near["under"]
            mi["src"]["o25"] = mi["src"].get("totals")
    # ⑥ 派生：handi（均衡档优先·否则主客赔率最接近档）
    if mi.get("eq"):
        mi["handi"] = mi["eq"]["hdp"]
        mi["ah_wh"], mi["ah_wa"] = mi["eq"]["home"], mi["eq"]["away"]
        mi["src"]["handi"] = mi["src"].get("eq")

    # ⑦ 覆盖度（6 个关键市场）
    keys = ("ml", "spread", "totals", "cs", "btts")
    got = sum(1 for k in keys if mi.get(k))
    mi["coverage"] = int(round(got * 100.0 / len(keys)))
    mi["event_id"] = eid or None
    mi["snapshot_count"] = (snap_eid is not None and bool(snap))
    return mi


def report(mi):
    """数据链体检表（每场必打·缺项显式告警·禁静默）"""
    L = []
    def _v(k, label, val, unit=""):
        s = mi["src"].get(k) or "**缺失**"
        L.append("    %-8s %-22s %s  ← %s" % (label, (str(val) + unit) if val not in (None, "", {}, []) else "—", "", s))
    ml = mi.get("ml") or {}
    _v("ml", "ML 主/平/客", "%s/%s/%s" % (ml.get("home"), ml.get("draw"), ml.get("away")))
    eq = mi.get("eq") or {}
    _v("eq", "让球均衡档", ("hdp=%s %s/%s" % (eq.get("hdp"), eq.get("home"), eq.get("away"))) if eq else None)
    _v("totals", "大小球全档", "%d 档" % len(mi.get("totals") or []))
    _v("cs", "波胆(CS)", "%d 档" % len(mi.get("cs") or {}))
    bt = mi.get("btts") or {}
    _v("btts", "BTTS", ("yes %s / no %s" % (bt.get("yes"), bt.get("no"))) if bt else None)
    if mi.get("o25"):
        L.append("    %-8s %-22s %s" % ("派生", "O2.5/U2.5", "%s / %s" % (mi.get("o25"), mi.get("u25"))))
    if mi.get("handi") is not None:
        L.append("    %-8s %-22s %s" % ("派生", "handi(均衡线)", mi.get("handi")))
    L.append("    %-8s %-22s %d%%（event=%s）" % ("覆盖度", "5 关键市场", mi.get("coverage", 0), mi.get("event_id")))
    for n in (mi.get("notes") or []):
        L.append("    ⚠️ " + n)
    return "\n".join(L)


def csv_arg(cs, sep=","):
    """CS dict → CLI/下游字符串（冒号格式，供 live 引擎用）"""
    if not cs:
        return None
    parts = []
    for k, v in sorted(cs.items(), key=lambda kv: kv[1]):
        kk = str(k).replace("-", ":")
        parts.append("%s=%s" % (kk, v))
    return sep.join(parts)


if __name__ == "__main__":
    # 自检：python market_inputs.py <event_id> [home] [away]
    eid = sys.argv[1] if len(sys.argv) > 1 else None
    h = sys.argv[2] if len(sys.argv) > 2 else None
    a = sys.argv[3] if len(sys.argv) > 3 else None
    m = resolve(home=h, away=a, event_id=eid)
    print("=" * 66)
    print("market_inputs 数据链体检 · event=%s" % (eid or "—"))
    print("=" * 66)
    print(report(m))
