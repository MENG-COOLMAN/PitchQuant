# -*- coding: utf-8 -*-
"""prestep_fetch.py —— PreStep 赛事拉取+赔率解析（2026-09-12·脚本化·反复使用）
拉 pending 赛事 → 按时间窗口过滤 → 取 1xbet 赔率(均衡线+2.5线/插值) → 调 prestep_dual 双向评级

🔴2026-09-20 接入 V3 新信号数据源:
  · 主水: Spread 均衡线的 home 值（零成本·同一响应内提取）
  · ELO差: clubelo 缓存（data/tmp/clubelo_*.json·由 fetch_clubelo.py 生成）→ 队名模糊匹配 → 主-客差
  · 两者缺失 → 传空 → prestep_dual 自动降级（信号不触发·不臆造）

用法:
  python data/tmp/prestep_fetch.py --from 2026-09-12T15:00 --to 2026-09-12T19:00   # UTC 窗口
  python data/tmp/prestep_fetch.py --bj "23:00-03:00"                               # 北京窗口(今日23点→次日3点)
  python data/tmp/prestep_fetch.py --bj "22:00-06:00" --leagues 西甲,欧联            # 只筛指定联赛
"""
import json, sys, io, os, re, glob, argparse, subprocess, urllib.request, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding='utf-8')
KEY = '<REDACTED_HEX>'
PROXY = 'http://127.0.0.1:7897'
# 🔴2026-09-23: PreStep 适用域 = 五大联赛 + 欧战 + 欧国联(NL)
#   🔴欧国联确实已收录（2026-09-23 实测 16 slug·League A-D × Gr.1-4·勿信旧「未收录」结论）
#   NL 场判定仍以 SK-league-nations(R1-R10·658 场专属库) 为准·本清单仅用于拉取赛程
LG = {'england-premier-league': '英超', 'spain-laliga': '西甲', 'germany-bundesliga': '德甲',
      'italy-serie-a': '意甲', 'france-ligue-1': '法甲',
      'international-clubs-uefa-europa-league': '欧联',
      'international-clubs-uefa-champions-league': '欧冠',
      'england-efl-cup': '英联赛杯',   # 🔴2026-10-28 实测确认（卡拉宝杯/EFL Cup·857 联赛表中 eventsCount 6）
      # 🔴2026-11-01 日职联/韩职联（用户指令·**超域**：PreStep 阈值源自五大联赛 22.7 万场
      #   → 这两个联赛的分值仅参考·须标「超域·仅参考」）
      #   实测 /leagues：J1=73场 · K1 拆 championship(16)+relegation(12) 两组（赛季末分组）
      'japan-jleague': '日职联',
      # 🔴2026-11-11 新增日联赛杯（用户指令「获取今天日联赛杯 J.League Cup / YBC Levain Cup 的快照并打分」）
      #   Odds-API `/leagues` 实测：`japan-j-league-cup` = "Japan - J. League Cup"·eventsCount **8**（在册）
      #   → 同样属**超域**（PreStep 阈值源自五大 22.7 万场）·分值仅参考·须标「超域·仅参考」
      #   🔴 the-odds-api `/v4/sports` 79 个 key 中**无任何日本赛事** → 跨机构分歧层不可用（三态）
      'japan-j-league-cup': '日联赛杯',
      'republic-of-korea-k-league-1-championship-round': '韩职联',
      'republic-of-korea-k-league-1-relegation-round': '韩职联',
    'international-clubs-afc-champions-league-elite-east-region': '亚冠精英','finland-veikkausliiga-championship-round': '芬超','sweden-allsvenskan': '瑞典超', 'international-clubs-afc-champions-league-two-group-e': '亚冠二级',   # 🔴2026-10-29 /leagues 实测
    # 🔴2026-11-09 欧国联完善 P0-3（用户「马上欧国联开始了」）：
    #   Odds-API `/leagues` 实测（eventsCount 佐证）UEFA Nations League **只收录 14 个 slug**：
    #     A 联赛 1-4 组（各 4 场）/ B 联赛 1-4 组（各 4 场）/ C 联赛 1-4 组（各 4 场）/ **D 联赛仅 1-2 组**（各 2 场）
    #   原表列了 16 个（含 d-gr-3 / d-gr-4）→ 两个 404 → 每次 prestep 都误报
    #   「三态·失败 / 漏场风险」噪音（用户会以为赛程不全）。**这两个组本就不存在**，删掉即消噪。
    #   ⚠️ 若 UEFA 未来把 D 联赛扩到 4 组 → 需回来补（届时 /leagues 会出现新 slug）。
    'international-uefa-nations-league-league-a-gr-1': '欧国联',
    'international-uefa-nations-league-league-a-gr-2': '欧国联',
    'international-uefa-nations-league-league-a-gr-3': '欧国联',
    'international-uefa-nations-league-league-a-gr-4': '欧国联',
    'international-uefa-nations-league-league-b-gr-1': '欧国联',
    'international-uefa-nations-league-league-b-gr-2': '欧国联',
    'international-uefa-nations-league-league-b-gr-3': '欧国联',
    'international-uefa-nations-league-league-b-gr-4': '欧国联',
    'international-uefa-nations-league-league-c-gr-1': '欧国联',
    'international-uefa-nations-league-league-c-gr-2': '欧国联',
    'international-uefa-nations-league-league-c-gr-3': '欧国联',
    'international-uefa-nations-league-league-c-gr-4': '欧国联',
    'international-uefa-nations-league-league-d-gr-1': '欧国联',
    'international-uefa-nations-league-league-d-gr-2': '欧国联',
}
# 🔴2026-10-09 域分离（用户质疑: 执行「五大联赛」prestep 不该连带拉 16 个 NL slug）:
#   PreStep 适用域 = 五大联赛 + 欧战（阈值源自 Matches.csv 22.7 万场）;
#   欧国联属**另一模块**(SK-league-nations·nl_model.py·不打 PreStep 分) → **须显式 --leagues 欧国联**。
#   分离前: 未传 --leagues 即全拉 23 slug → 配额浪费(16 次) + 输出混入 NL 404 噪音。
DOMAIN_5 = ['英超', '西甲', '德甲', '意甲', '法甲', '欧联', '欧冠']

# 🔴直连优先（实测 Odds-API 可直连·无需 VPN）→ 代理回退
# 🔴2026-09-23 修复: 无参 build_opener() 会继承 Windows 系统代理(127.0.0.1:7897)
#   → 名为"直连"实走代理 → 代理失效时双通道全灭。必须显式禁用代理才是真直连。
_op_direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_op_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY}))

# 🔴2026-10-31 通道顺序修订: **代理优先(25s) → 直连回退(4s 快速失败)**
#   实测: 直连 api.odds-api.io **SSL 握手超时 26.3s** / 代理 127.0.0.1:7897 **1.2s**
#   原「直连优先」→ 每请求白等 26s（单场 parse_odds 54.6s·12 场 prestep ≈6 分钟）
#   🔴真直连约束不变: 回退通道必须显式 ProxyHandler({})（禁无参 build_opener）
_CHANNELS = ((_op_proxy, 25), (_op_direct, 4))


def get(u, tries=2):
    last = None
    for op, _to in _CHANNELS:   # 🔴2026-10-31 代理优先 → 直连回退(4s)
        for _ in range(tries):
            try:
                with op.open(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=_to) as r:
                    raw = r.read()
                    if raw[:2] == b'\x1f\x8b':
                        import gzip
                        raw = gzip.decompress(raw)
                    return json.loads(raw.decode('utf-8', errors='replace'))
            except Exception as e:
                last = e
    raise last


def window_from_bj(bj):
    import datetime as dt
    m = re.match(r'(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})', bj)
    if not m:
        raise SystemExit('--bj 格式应为 HH:MM-HH:MM')
    now = dt.datetime.now()
    h0, m0, h1, m1 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    w0 = now.replace(hour=h0, minute=m0, second=0, microsecond=0)
    w1 = now.replace(hour=h1, minute=m1, second=0, microsecond=0)
    if w1 <= w0:
        w1 += dt.timedelta(days=1)
    u0 = (w0 - dt.timedelta(hours=8)).strftime('%Y-%m-%dT%H:%M')
    u1 = (w1 - dt.timedelta(hours=8)).strftime('%Y-%m-%dT%H:%M')
    return u0, u1, ('%s → %s' % (w0.strftime('%m-%d %H:%M'), w1.strftime('%m-%d %H:%M')))


def parse_odds(ev_id):
    """取 1xbet 赔率: ML / 均衡线 Spread(含主水) / 2.5线(或插值) Totals"""
    d = get('https://api.odds-api.io/v3/odds?apiKey=%s&eventId=%s&bookmakers=1xbet' % (KEY, ev_id))
    mkts = (d.get('bookmakers') or {}).get('1xbet') or []
    ml = spr = tot = None
    for m in mkts:
        nm = m.get('name')
        if nm == 'ML': ml = m.get('odds') or []
        elif nm == 'Spread': spr = m.get('odds') or []
        elif nm == 'Totals': tot = m.get('odds') or []
    oh = od = oa = handi = o25 = home_water = None
    if ml:
        try:
            oh = float(ml[0].get('home') or 0) or None
            od = float(ml[0].get('draw') or 0) or None
            oa = float(ml[0].get('away') or 0) or None
        except Exception:
            pass
    if spr:
        try:
            best = min(spr, key=lambda x: abs(float(x.get('home') or 99) - float(x.get('away') or 99)))
            handi = float(best.get('hdp') or 0)
            # 🔴2026-09-20 新增: 主队一侧水位（亚盘主水位·供 W1 主水诱主信号）
            home_water = float(best.get('home') or 0) or None
        except Exception:
            handi = None
    if tot:
        try:
            lines = sorted([(float(x.get('hdp') or 0), float(x.get('over') or 0)) for x in tot if x.get('over')], key=lambda t: t[0])
            ex = [l for l in lines if abs(l[0] - 2.5) < 0.01]
            if ex:
                o25 = ex[0][1]
            else:
                lo = [l for l in lines if l[0] <= 2.5]; hi = [l for l in lines if l[0] >= 2.5]
                if lo and hi and hi[0][0] > lo[-1][0]:
                    a, b = lo[-1], hi[0]
                    o25 = round(a[1] + (b[1] - a[1]) * ((2.5 - a[0]) / (b[0] - a[0])), 3)
                elif lines:
                    o25 = lines[0][1]
        except Exception:
            o25 = None
    # 🔴2026-10-30 P34: 保留 1xbet 全响应（原只提 ML/Spread/Totals 三字段 → raw 全丢
    #   → P10 三源(OU/AH/CS 全档) / P8 纵向序列 / BTTS 在 prestep 阶段全部拿不到数据）
    return oh, od, oa, handi, o25, home_water, d


def _norm(s):
    return re.sub(r'[^a-z]', '', (s or '').lower())


# 🔴2026-09-20: 复用 data_bridge 的队名匹配（别名表 164中文名/395别名 + NFKD + 包含 + 前缀4）
_BRIDGE_MATCH = None
_BRIDGE_NORM = None
try:
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'online_learning'))
    from data_bridge import match_team as _BRIDGE_MATCH, normalize_name as _BRIDGE_NORM
    print('[队名匹配] 已接入 data_bridge（别名+模糊匹配）')
except Exception as _e:
    print('[队名匹配] data_bridge 不可用 → 回退本地简化匹配: %s' % str(_e)[:50])


def load_elo():
    """读 clubelo 缓存 → {归一化队名: elo}（多别名）。无缓存 → 空 dict（信号降级）"""
    fs = sorted(glob.glob(os.path.join(HERE, 'clubelo_*.json')))
    m = {}
    if not fs:
        return m, None
    try:
        d = json.load(open(fs[-1], encoding='utf-8'))
    except Exception:
        return m, None
    for lg, info in (d.get('leagues') or {}).items():
        for t in (info.get('teams') or []):
            elo = t.get('elo')
            if not elo:
                continue
            if t.get('name'):
                m[t['name']] = elo          # 🔴保留原始名（供 data_bridge.match_team 别名/模糊匹配）
    return m, d.get('date')


FORM_CACHE = os.path.join(HERE, '_form_cache.json')
FORM_UNAVAILABLE = None   # 🔴2026-10-29 用户决策: 改源 Bzzoiro v1 home_form/away_form → Form5 恢复（原 api-football 2026-10-06 停用）
FORM_SOURCE = 'Bzzoiro v1 home_form/away_form.points_last_n ÷ matches_played（场均积分 0-3 · 2026-10-29 换源·口径变更待前瞻复核）'
TEAM_IDX = {}   # 🔴2026-10-09 修复: api-football 停用后 build_team_index 从不赋值(_afb 已删→异常被吞)→L298 NameError



# 🔴P40 DEPRECATED（2026-10-30 批次5）: 全库零调用。旧版索引构建·同上
#   → 保留备查·不接入
def build_team_index(dates):
    """🔴从当日 fixtures 建立 归一化队名→team_id 索引
    （比 /teams?search 可靠——实测 search 端点对俱乐部名返回空·2026-09-20）"""
    global TEAM_IDX
    # 🔴2026-10-09: api-football 已停用（_afb 已删）→ 本函数无数据源 → 直接三态返回
    #   （原实现仍调 _afb() → NameError 被 except 吞 → TEAM_IDX 从不赋值 → 调用处崩）
    if FORM_UNAVAILABLE:
        return TEAM_IDX
    for d in dates:
        try:
            for f in (_afb('/fixtures?date=%s' % d).get('response') or []):
                for side in ('home', 'away'):
                    t = (f.get('teams') or {}).get(side) or {}
                    if t.get('id') and t.get('name'):
                        TEAM_IDX[_norm(t['name'])] = t['id']
                        # 🔴去常见后缀（提高与 Odds-API 名匹配率·实测 Sunderland AFC/Getafe CF 失配）
                        nm = re.sub(r'\b(afc|cf|cfc|fc|sc|ac|ss|as|sv|calcio|1907|1899|29)\b', '', t['name'], flags=re.I)
                        nm = re.sub(r'\s+', ' ', nm).strip()
                        if nm and _norm(nm):
                            TEAM_IDX.setdefault(_norm(nm), t['id'])
        except Exception:
            pass
    return TEAM_IDX


# 🔴P40 DEPRECATED（2026-10-30 批次5）: 全库零调用。旧版球队索引·被 Bzzoiro 队名匹配取代
#   → 保留备查·不接入
def _lookup_team(t):
    """索引查询: 精确 → 含子串（≥4字符）回退"""
    n = _norm(t)
    if n in TEAM_IDX:
        return TEAM_IDX[n]
    cands = [(k, v) for k, v in TEAM_IDX.items() if len(k) >= 4 and (k in n or n in k)]
    return cands[0][1] if cands else None


def load_form(teams, rows=None):
    """🔴V3.2 Form5（近期状态）—— 🔴2026-10-29 换源: Bzzoiro v1 home_form/away_form

    历史: 原源 api-football fixtures?team&last=5（2026-10-06 停用→曾置 FORM_UNAVAILABLE 恒三态）
    现在: Bzzoiro v1 `home_form.points_last_n / matches_played` = **场均积分（0-3）**
    ⚠️ 口径变更: 原 api-football 算法未留存 → 本实现为场均积分差；F1 阈值(≥1.0)沿用
       → **未回测·待前瞻 ≥20 场复核**（用户 2026-10-29 决策 dec-ada50f0a7961c711）
    🔴 定位范围: bsd_layer.locate_event 默认扫五大联赛 → 杯赛/欧战/小联赛**定位不到 → 该队 None（三态）**
    返回 {队名: 场均积分}
    """
    out = {}
    if not rows:
        return out
    try:
        import bsd_layer as _B
    except Exception as e:
        print('⚠️ Form5: bsd_layer 导入失败 → 三态 (%s)' % str(e)[:60])
        return out
    for r in rows:
        h, a = r.get('home'), r.get('away')
        if not h or not a:
            continue
        if (h in out) and (a in out):
            continue
        eid = r.get('bsd_event')
        if not eid:
            try:
                # 🔴 loc 返回 4 元组 (event_id, home, away, event_date) → 取 [0]
                _loc = _B.locate_event(h, a)
                eid = (_loc[0] if isinstance(_loc, (tuple, list)) else _loc)
            except Exception:
                eid = None
        if not eid:
            continue                      # 定位失败 → 该场两队均 None
        try:
            ev = _B.fetch_event(eid) or {}
        except Exception:
            continue
        _raw = {}
        for side, name in (('home_form', h), ('away_form', a)):
            f = ev.get(side) or {}
            n_pl = f.get('matches_played') or 5
            pts = f.get('points_last_n')
            if pts is not None:
                out[name] = round(float(pts) / float(n_pl), 2)
            _raw[name] = {k: f.get(k) for k in
                          ('form_string', 'wins', 'draws', 'losses', 'points_last_n', 'matches_played')}
        r['form_raw'] = _raw
    return out


def match_elo(m, team):
    """🔴2026-09-20: 优先 data_bridge.match_team（别名+NFKD+包含+前缀4）→ 回退本地简化匹配"""
    if not m or not team:
        return None
    if _BRIDGE_MATCH:
        try:
            c, conf = _BRIDGE_MATCH(team, list(m.keys()))
            if c and conf >= 0.6:
                return m[c]
        except Exception:
            pass
    n = _norm(team)
    for k, v in m.items():
        if _norm(k) == n:
            return v
    cands = [(k, v) for k, v in m.items() if len(_norm(k)) >= 4 and (_norm(k) in n or n in _norm(k))]
    return max(cands, key=lambda kv: len(_norm(kv[0])))[1] if cands else None


# 🔴2026-09-24(实操复盘 P2-2): NL 场 clubelo 无国家队档案 → 载入 nl_data/elo_current.json(313 队) 供 NL 场 ELO 使用
try:
    _NLP = os.path.join(HERE, 'nl_data', 'elo_current.json')
    NL_ELO = json.load(open(_NLP, encoding='utf-8')) if os.path.exists(_NLP) else {}
except Exception:
    NL_ELO = {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='f'); ap.add_argument('--to', dest='t')
    ap.add_argument('--bj', help='北京窗口 HH:MM-HH:MM（如 23:00-03:00）')
    ap.add_argument('--leagues', help='筛选联赛(逗号分隔)。🔴默认=五大联赛+欧战·欧国联须显式传「欧国联」')
    ap.add_argument('--save', action='store_true')
    a = ap.parse_args()
    if a.bj:
        u0, u1, label = window_from_bj(a.bj)
    elif a.f and a.t:
        u0, u1, label = a.f, a.t, '%s → %s (UTC)' % (a.f, a.t)
    else:
        print(__doc__); return
    print('窗口: 北京 %s（UTC %s → %s）\n' % (label, u0, u1))
    elo_map, elo_date = load_elo()
    print('clubelo ELO 缓存: %s（队数 %d）' % (elo_date or '无', len(elo_map)))
    rows = []
    fail_slugs = []
    only = [s.strip() for s in (a.leagues or '').split(',') if s.strip()] or DOMAIN_5
    print('📌 域: %s%s\n' % ('、'.join(only),
          '（🔴 PreStep 仅适用五大联赛+欧战·欧国联请走 SK-league-nations）' if '欧国联' not in only else '（欧国联属超域·分值不参与判定）'))
    for slug, cn in LG.items():
        if only and cn not in only:
            continue
        evs = None
        for _t in range(2):
            try:
                evs = get('https://api.odds-api.io/v3/events?apiKey=%s&sport=football&league=%s&status=pending' % (KEY, slug))
                break
            except Exception as e:
                _m = str(e)[:60]
                if '429' in _m and _t == 0:
                    __import__('time').sleep(6); continue
                fail_slugs.append((slug, _m))
                print('  ⚠️ [三态·失败] %s / %s: %s' % (cn, slug, _m)); break
        if evs is None:
            continue
        for e in (evs or []):
            d = (e.get('date') or '')
            if u0 <= d[:16] <= u1:
                rows.append({'cn': cn, 'id': e['id'], 'home': e['home'], 'away': e['away'], 'date': d})
    print('窗口内赛事: %d 场' % len(rows))
    if fail_slugs:
        # 🔴2026-10-09: 429(限流) 与 slug 404 分列 —— 原实现一律报「漏场风险」→ 限流时误指「赛程不完整」
        _api = [(x, y) for (x, y) in fail_slugs
                if '429' in y or 'rate limit' in y.lower() or 'exceeded' in y.lower()]
        _real = [(x, y) for (x, y) in fail_slugs if (x, y) not in _api]
        if _api:
            print('🔴 [API 限流] %d/%d 个 slug 报 429（**非「无赛事」**）→ 本窗口赛程**未采集**·配额恢复后重跑'
                  % (len(_api), len(fail_slugs)))
            print('     原始信息: %s' % _api[0][1])
        if _real:
            print('🔴 [三态·漏场风险] slug 拉取失败 %d 个 → 本窗口赛程**可能不完整**·请复核:' % len(_real))
            for _s, _m in _real:
                print('     %s  (%s)' % (_s, _m))
    for r in rows:
        try:
            oh, od, oa, handi, o25, hw, _raw = parse_odds(r['id'])
            r.update({'oh': oh, 'od': od, 'oa': oa, 'handi': handi, 'o25': o25, 'home_water': hw})
            r['_raw'] = _raw   # 🔴P34 全响应留驻（落 snapshots·不写 prestep_window.json）
        except Exception as e:
            r['err'] = str(e)[:50]
        # 🔴2026-09-20: ELO 差（clubelo · 缺失则 None → 信号降级）
        # 🔴2026-09-24(P2-2): NL 场 clubelo 无国家队 → 并入 nl_data/elo_current.json 后再匹配
        _em = elo_map if (r.get('cn') != '欧国联' or not NL_ELO) else dict(elo_map, **NL_ELO)
        eh, ea = match_elo(_em, r['home']), match_elo(_em, r['away'])
        r['elo_diff'] = round(eh - ea, 1) if (eh is not None and ea is not None) else None
    # 🔴V3.2: Form5（原 api-football 近期战绩·🔴2026-10-06 该源已停用 → ⚪ 三态不触发）
    form_map = {}
    # 🔴2026-10-09 修复: 源已停用 → 直接三态跳过（原实现仍调 build_team_index→_afb 已删→异常被吞→NameError）
    if FORM_UNAVAILABLE:
        print('⚪[三态] Form5 不可用（%s）→ F1/F2 信号本次不触发' % FORM_UNAVAILABLE)
    else:
        try:
            need = []
            for r in rows:
                for t in (r['home'], r['away']):
                    if t not in need:
                        need.append(t)
            form_map = load_form(need, rows)
            got = sum(1 for v in form_map.values() if v is not None)
            print('Form5 数据源: %s ｜ %d/%d 队命中' % (FORM_SOURCE, got, len(need)))
            if got < len(need):
                print('  ⚪[三态] 未命中队（bsd_layer.locate_event 默认仅五大联赛 → 杯赛/欧战/小联赛不支持）')
        except Exception as e:
            print('⚠️ Form5 降级: %s' % str(e)[:60])
    for r in rows:
        fh, fa = form_map.get(r['home']), form_map.get(r['away'])
        r['form_diff'] = round(fh - fa, 2) if (fh is not None and fa is not None) else None
    print('%-6s %-6s %-32s %-6s %-6s %-6s %-7s %-7s %-8s %-7s %-8s' % ('北京', '联赛', '赛事', '主', '平', '客', '让球', 'O25', 'ELO差', '主水', 'Form差'))
    for r in sorted(rows, key=lambda x: x['date']):
        bj = str(int(r['date'][11:13]) + 8).zfill(2) + r['date'][13:16]
        if int(bj[:2]) >= 24:
            bj = str(int(bj[:2]) - 24).zfill(2) + bj[2:]
        print('%-6s %-6s %-32s %-6s %-6s %-6s %-7s %-7s %-8s %-7s %-8s' % (
            bj, r['cn'], ('%s vs %s' % (r['home'], r['away']))[:30], r.get('oh'), r.get('od'), r.get('oa'),
            r.get('handi'), r.get('o25'), r.get('elo_diff') if r.get('elo_diff') is not None else '-',
            r.get('home_water') if r.get('home_water') is not None else '-',
            r.get('form_diff') if r.get('form_diff') is not None else '-'))
    # 🔴2026-09-24(P1-1): 分数留痕 —— 写入 方向分/比分分/评级（此前 window json 只存原始赔率·事后无法审计）
    try:
        sys.path.insert(0, HERE)
        import prestep_dual as _pd
        for r in rows:
            if r.get('oh') and r.get('o25'):
                _ev = _pd.evaluate('%s %s vs %s' % (r['cn'], r['home'], r['away']),
                                   r['oh'], r.get('od'), r.get('oa'), r.get('handi') or 0, r['o25'],
                                   0, r['cn'], r.get('elo_diff'), r.get('home_water'), r.get('form_diff'))
                r['dir_score'], r['score_score'], r['tag'] = _ev.get('方向分'), _ev.get('比分分'), _ev.get('评级')
    except Exception as e:
        print('⚠️ 分数留痕降级: %s' % str(e)[:60])
    if a.save:
        # 🔴2026-11-02 全档时点 diff（用户裁定 dec-89ecf96e243c7665）
        #   改前：时点对比只看 snapshot_save._extract 单截面（均衡档亚盘 + O2.5 + 波胆1-1）
        #        → 实测 T0 06:53 vs T1 18:05 五场全部漏报「无变动」（实际 5/5 全动）
        #   改后：按市场名逐档对比 raw 全量 → 打印「全档时点变动」块 + 写 mkt_move 进 window json
        #   🔴 铁律：本块只标注·不改方向分/比分分
        _diff_rows = None
        try:
            sys.path.insert(0, HERE)
            import snapshot_diff as _sdf
            _diff_rows = _sdf.diff_against_prev(rows, HERE)
            for _r in rows:
                _mv = (_diff_rows or {}).get((_r.get('home'), _r.get('away')))
                if _mv:
                    _sg = _mv.get('_signals') or {}
                    _r['mkt_move'] = {
                        'tags': _sg.get('tags') or [],
                        'summary': _sg.get('summary'),
                        'core_moved': _sg.get('core_moved'),
                        'ml': _sg.get('ml'),
                        'spread': _sg.get('spread'),
                        'totals': _sg.get('totals'),
                        'chg_by_market': {k: v.get('changed') for k, v in _mv.items() if k != '_signals'},
                    }
            if _diff_rows:
                # 🔴 时点标签必须写实际时间（审计要能对上快照文件）
                #   2026-11-02：基线可能来自**回溯**（相邻时点无变动时会往前找有变动的时点）
                _bl = getattr(_sdf, 'LAST_BASELINE', {}) or {}
                _base_at = _bl.get('saved_at') or '上一时点'
                if _bl.get('lookback_used', 1) > 1:
                    _base_at += '（相邻 %d 个时点无变动·已回溯到此基线）' % (_bl.get('lookback_used') - 1)
                _now_at = '本时点 %s' % __import__('datetime').datetime.now().strftime('%H:%M:%S')
                print(_sdf.fmt_batch(_diff_rows, _base_at, _now_at))
            else:
                print('\n⚪ 全档时点 diff：无上一时点基线（首次采集）→ 仅本时点')
        except Exception as _e:
            print('⚠️ 全档时点 diff 降级(三态·非「无变动」): %s' % str(_e)[:70])
        p = os.path.join(HERE, 'prestep_window.json')
        _rows_out = [{k: v for k, v in r.items() if k != '_raw'} for r in rows]
        json.dump(_rows_out, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('\n已保存: data/tmp/prestep_window.json')
        # 🔴2026-10-30 P34（治「prestep 存了但没进模型」）：同步落 snapshot_save 兼容快照。
        #   原只写 prestep_window.json → 仅本脚本读 → find_for/delta_for/vertical_for 匹配不到
        #   （实测 vertical_for count=0 / delta_for 仅 1 时点）→ P8/P12/N21/P10 全断。
        try:
            def _bj(_s):
                # P34: UTC ISO → 北京时间 'YYYY-MM-DD HH:MM'
                #   find_for 跨场防护按 kickoff_bj 聚类；若填 UTC 会与 snapshot_save 的北京时
                #   分属两组 → 新快照被剔除 → 时序恒 1 点（P8/P12/N21 全退三态）
                try:
                    _d = __import__('datetime').datetime.fromisoformat(
                        str(_s).replace('Z', '+00:00'))
                    if _d.tzinfo is not None:
                        _d = _d.astimezone(
                            __import__('datetime').timezone.utc).replace(tzinfo=None)
                    return (_d + __import__('datetime').timedelta(hours=8)).strftime(
                        '%Y-%m-%d %H:%M')
                except Exception:
                    return str(_s)
            _sd = os.path.join(HERE, 'snapshots')
            os.makedirs(_sd, exist_ok=True)
            _now = __import__('datetime').datetime.now()
            _fn = 'prestep_%s_%s.json' % (_now.strftime('%Y%m%d'), _now.strftime('%H%M%S'))
            # 🔴V3.5.93 写入端 schema 防线（2026-11-06 用户指令「避免格式问题导致的识别错误」）
            #   实测: 53 份历史快照 = 8 种字段结构; 读取层 _extract 兼容 6 种(51/53=96.2%),
            #         仅 F3(b7)/F4(ps4) 各 1 份读不到 → 根因=落盘时无契约(不是读取层不够聪明)。
            #   做法: ①必填字段非空校验 ②只写白名单键(禁多余键混入) → 永不再产生第 9 种格式。
            #   缺必填 → 该场剔除并告警; 全部剔除 → raise 拒绝落盘(由外层 except 记三态)。
            _REQ = ('home', 'away', 'kickoff_bj', 'raw_1xbet')
            _OPT = ('event_id', 'kickoff_utc')
            _games, _drop = [], []
            for r in rows:
                _g = {'home': r.get('home'), 'away': r.get('away'),
                      'event_id': r.get('id'), 'kickoff_utc': r.get('date'),
                      'kickoff_bj': _bj(r.get('date')), 'raw_1xbet': r.get('_raw') or {}}
                _miss = [k for k in _REQ if not _g.get(k)]
                if _miss:
                    _drop.append('%s vs %s(缺 %s)' % (r.get('home'), r.get('away'), '/'.join(_miss)))
                    continue
                _games.append({k: _g[k] for k in _REQ + _OPT})  # 🔴白名单·禁多余键
            if _drop:
                print('🔴 schema 剔除 %d 场（缺必填·不写快照）: %s' % (len(_drop), '; '.join(_drop[:4])))
            if not _games:
                raise RuntimeError('schema 校验后 0 场合格（必填=%s）→ 拒绝写快照' % '/'.join(_REQ))
            json.dump({'saved_at': _now.strftime('%Y-%m-%d %H:%M:%S'),
                       'window_bj': (getattr(a, 'bj', '') or '').replace('-', ' '),
                       'src': 'prestep_fetch P34', 'schema': 'v2', 'games': _games},
                      open(os.path.join(_sd, _fn), 'w', encoding='utf-8'), ensure_ascii=False)
            print('📸 同步落快照(供 P8/P12/N21/P10): snapshots/%s（%d 场·schema v2）' % (_fn, len(_games)))
        except Exception as _e:
            print('⚠️ 快照同步落盘失败(三态): %s' % str(_e)[:70])
    args = []
    for r in rows:
        if r.get('oh') and r.get('o25'):
            args += ['--match', '%s %s vs %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s' % (
                r['cn'], r['home'], r['away'], r['oh'], r['od'], r['oa'],
                r.get('handi') or 0, r['o25'], 0, r['cn'],
                r.get('elo_diff') if r.get('elo_diff') is not None else '',
                r.get('home_water') if r.get('home_water') is not None else '',
                r.get('form_diff') if r.get('form_diff') is not None else '')]
    if args:
        print()
        subprocess.run([sys.executable, os.path.join(HERE, 'prestep_dual.py')] + args,
                       encoding='utf-8', errors='replace',
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))


if __name__ == '__main__':
    main()
