# -*- coding: utf-8 -*-
"""BSD (Bzzoiro Sports Data) 增强层 · 按《BSD 数据源接入方案 2026-10-09》实现

🔴 分阶段纪律（方案§七）: 本脚本**默认「只记录不判定」**（第一阶段·并行观察）
   → 输出「BSD 字段 + 判定建议（观察）」并排落盘·**不参与 Step5/6/7 判定**
   → 第二阶段起（过 season_holdout 门禁后）才用 `--apply` 把 P0 结果接入判定。

端点（🔴 v1 才全字段·v2 缺 unavailable_players/form/referee/coach）:
  GET /api/events/{id}/                  → unavailable_players / home_form / away_form /
                                           head_to_head / home_coach / away_coach / referee /
                                           travel_distance_km / temperature_c / is_local_derby
  GET /api/odds/compare/?event={id}      → 14 家赔率 + movement(SHORTENING/DRIFTING)

用法:
  python data/tmp/bsd_layer.py --event 213710                 # 记录模式（默认·只打印不判定）
  python data/tmp/bsd_layer.py --event 213710 --apply         # 输出判定值（第二/三/四阶段）
  python data/tmp/bsd_layer.py --event 213710 --json out.json # 并排落盘

🔴 铁律: ①BSD 是**增强层**·挂了模型必须能独立跑（异常→全字段降级不报错）
        ②`ai_preview` **永不读取**（LLM 生成·幻觉风险·方案§二/§八）
        ③伤停分/ movement 只调置信度/大小球·**永不反转 L2 硬核方向**
        ④本地缓存 1 小时（方案§八）
"""
import sys, os, json, time, argparse, urllib.request, datetime as _dtm
import unicodedata

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

V1 = 'https://sports.bzzoiro.com/api/'
V2 = 'https://sports.bzzoiro.com/api/v2/'
PROXY = 'http://127.0.0.1:7897'
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '_bsd_cache.json')
POSMAP = {'G': '门将', 'D': '中后卫', 'M': '后腰', 'F': '前锋'}


def _key():
    k = (os.environ.get('BZZOIRO_KEY') or '').strip()
    if k:
        return k
    for p in (os.path.join(HERE, 'api_keys.json'), os.path.join(HERE, '..', 'api_keys.json')):
        try:
            j = json.load(open(p, encoding='utf-8'))
            if j.get('bzzoiro'):
                return str(j['bzzoiro']).strip()
        except Exception:
            continue
    raise RuntimeError('🔴 未找到 Bzzoiro key（env BZZOIRO_KEY / data/tmp/api_keys.json 的 bzzoiro）')


def _get(url, timeout=25):
    h = {'Authorization': 'Token ' + _key(), 'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
    for _ph in (PROXY, None):
        try:
            op = (urllib.request.build_opener(urllib.request.ProxyHandler({})) if _ph is None
                  else urllib.request.build_opener(urllib.request.ProxyHandler({'https': _ph, 'http': _ph})))
            with op.open(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                return r.status, json.loads(r.read().decode('utf-8', errors='replace'))
        except Exception:
            continue
    return None, None


def _cache_get(k):
    try:
        c = json.load(open(CACHE, encoding='utf-8'))
        v = c.get(k)
        if v and time.time() - v.get('_ts', 0) < 3600:
            return v.get('data')
    except Exception:
        pass
    return None


def _cache_put(k, data):
    try:
        c = {}
        if os.path.exists(CACHE):
            c = json.load(open(CACHE, encoding='utf-8'))
        c[k] = {'_ts': time.time(), 'data': data}
        json.dump(c, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False)
    except Exception:
        pass


def fetch_event(eid):
    k = 'ev:%s' % eid
    c = _cache_get(k)
    if c is not None:
        return c
    st, j = _get(V1 + 'events/%s/' % eid)
    if j is None:
        return None
    j.pop('ai_preview', None)          # 🔴 方案§二/§八: 永不读取
    _cache_put(k, j)
    return j


def fetch_compare(eid):
    k = 'cmp:%s' % eid
    c = _cache_get(k)
    if c is not None:
        return c
    st, j = _get(V1 + 'odds/compare/?event=%s' % eid)
    _cache_put(k, j)
    return j


# ---------------- 方案 §3.1 伤停因子 ----------------
def injury_score(players, event_date=None):
    """按 expected_return 距比赛日天数差加权（方案§3.1）
       d>14 → 0.0 / 3≤d≤14 → 0.5 / d<3 → 1.0 / null → 0.5 ; doubtful ×0.5
    """
    import datetime as _dt
    base = None
    if event_date:
        try:
            base = _dt.datetime.strptime(str(event_date)[:10], '%Y-%m-%d')
        except Exception:
            base = None
    tot = 0.0
    det = []
    for p in (players or []):
        w = 0.5
        er = p.get('expected_return')
        d = None
        if er and base:
            try:
                d = (_dt.datetime.strptime(str(er)[:10], '%Y-%m-%d') - base).days
                w = 0.0 if d > 14 else (0.5 if d >= 3 else 1.0)
            except Exception:
                w = 0.5
        if str(p.get('status') or '').lower() == 'doubtful':
            w *= 0.5
        tot += w
        det.append({'name': p.get('name'), 'status': p.get('status'), 'reason': p.get('reason'),
                    'expected_return': er, 'days': d, 'weight': round(w, 2)})
    return round(tot, 2), det


def injury_verdict(sh, sa):
    """方案§3.1 触发阈值"""
    if sh >= 2.5 and sa <= 1.0:
        return '主队伤停显著 → 主胜置信 -1 档'
    if sh <= 1.0 and sa >= 2.5:
        return '客队伤停显著 → 客队方向/大球下调'
    if sh >= 2.5 and sa >= 2.5:
        return '双方均重灾 → 大小球偏向小球'
    return '不触发（无显著伤停）'


# ---------------- 方案 §3.2 movement ----------------
# 🔴2026-11-02 P39 修（case318 实证·用户裁定「现在修」）：
#   原实现**对每个方向独立判 Q1/Q2** → 语义颠倒：「某方向 DRIFTING」= 该方向赔率上升=**被卖**，
#   不等于「该方向被诱」。Q2 诱盘的定义 = **热门方被机构升水**（不跟进公众买热门）。
#   本场实证：Everton(客) DRIFT=9/13 被判「Q2 诱盘确认」→ 实际是「客队被卖 + 主队被买」= Q1 主队共识
#   （同批 竞彩主 −6.7% / 1xbet 主 −3.2% / 亚盘 14-15 档降主水 → 三源同向）。
#   修法：① 先用 best_odds 最小定热门方 ② 逐方向标注角色（热门方/对手方）③ 只有热门方 DRIFTING 才算 Q2
LAST_OVERALL = {'code': '-', 'text': 'movement 不可用'}


def movement_verdict(cmp_j):
    """对 1x2 三方向统计 SHORTENING/DRIFTING → **先定热门方**，再判 Q1/Q2（P39·2026-11-02）"""
    global LAST_OVERALL
    mk = ((cmp_j or {}).get('markets') or {}).get('1x2') or {}
    rows = {}
    for dname, dv in (mk.items() if isinstance(mk, dict) else []):
        if not isinstance(dv, dict):
            continue
        bks = dv.get('bookmakers') or {}
        mvs = [v.get('movement') for v in bks.values() if isinstance(v, dict)]
        n_sh = sum(1 for x in mvs if x == 'SHORTENING')
        n_dr = sum(1 for x in mvs if x == 'DRIFTING')
        rows[dname] = {'n_books': len(bks), 'short': n_sh, 'drift': n_dr,
                       'n_total': n_sh + n_dr, 'best_odds': dv.get('best_odds')}

    # ① 热门方 = best_odds 最小（赔率最低＝概率最高）；缺失则 None（三态）
    _ok = [(dn, float(r['best_odds'])) for dn, r in rows.items()
           if isinstance(r.get('best_odds'), (int, float)) and float(r['best_odds']) > 0]
    fav = min(_ok, key=lambda x: x[1])[0] if _ok else None

    # ② 逐方向 verdict（措辞带角色·根治「对手方 DRIFT 被读成 Q2」）
    out = {}
    for dn, r in rows.items():
        is_fav = (dn == fav)
        role = '热门方' if is_fav else '对手方'
        n_tot, n_sh, n_dr = r['n_total'], r['short'], r['drift']
        if n_tot < 3:
            v = '%s n_total<3 → 信号无效（三态）' % role
        elif n_sh >= 2 * n_tot / 3:
            v = ('%s SHORTENING ≥2/3（机构同向降赔·被买）→ **Q1 真共识 +0.5~1档**' % role) if is_fav \
                else ('%s SHORTENING ≥2/3（对手被买）→ 对热门方**反向旁证**（非 Q1）' % role)
        elif n_dr >= 2 * n_tot / 3:
            v = ('%s DRIFTING ≥2/3（机构给**热门**升水·不跟进公众）→ **Q2 诱盘确认**' % role) if is_fav \
                else ('%s DRIFTING ≥2/3（对手被卖）→ **支持热门方（Q1 旁证·非 Q2）**' % role)
        else:
            v = '%s 无 2/3 多数（混乱）→ 不触发' % role
        r['role'] = role
        r['verdict'] = v
        out[dn] = r

    # ③ 全局判定（唯一权威·下游只认这条，防「逐行 Q2」误读）
    fr = out.get(fav) or {}
    if fav and fr.get('n_total', 0) >= 3:
        if fr['short'] >= 2 * fr['n_total'] / 3:
            LAST_OVERALL = {'code': 'Q1', 'fav': fav,
                            'text': '热门方 %s SHORTENING → **Q1 真共识**（机构同向降热门赔率）' % fav}
        elif fr['drift'] >= 2 * fr['n_total'] / 3:
            LAST_OVERALL = {'code': 'Q2', 'fav': fav,
                            'text': '热门方 %s DRIFTING → **Q2 诱盘确认**（机构给热门升水·不跟进公众）' % fav}
        else:
            LAST_OVERALL = {'code': '-', 'fav': fav,
                            'text': '热门方 %s 无 2/3 多数 → 不触发（看方向一致度）' % fav}
    elif fav:
        LAST_OVERALL = {'code': '-', 'fav': fav,
                        'text': '热门方 %s 样本 n_total<3 → 三态（不触发）' % fav}
    else:
        LAST_OVERALL = {'code': '-', 'text': '1x2 无 best_odds → 热门方无法定位（三态）'}
    return out

    return out


# ---------------- 方案 §4 P1 ----------------
def xg_factor(hf, af):
    try:
        xh, xa = float(hf.get('avg_xg')), float(af.get('avg_xg'))
    except Exception:
        return None
    d = round(xh - xa, 2)
    tot = round(xh + xa, 2)
    if d > 0.8:
        v = '主队进攻显著强 → 主胜加权'
    elif d < -0.8:
        v = '客队进攻显著强'
    else:
        v = '均势（-0.3~0.3）' if -0.3 <= d <= 0.3 else '轻度倾向'
    tl = '大球倾向（>3.0）' if tot > 3.0 else ('小球倾向（<2.2）' if tot < 2.2 else '中性')
    return {'xg_diff': d, 'expected_total_goals': tot, 'verdict': v, 'total_verdict': tl}


def referee_factor(ref):
    try:
        g = int(ref.get('career_games') or 0)
        rc = int(ref.get('career_red_cards') or ref.get('redCards') or 0)
        yc = int(ref.get('career_yellow_cards') or ref.get('yellowCards') or 0)
    except Exception:
        return None
    if g < 50:
        return {'career_games': g, 'verdict': '样本不足（<50场）→ 不使用'}
    rr = round(rc / g, 4)
    yp = round(yc / g, 2)
    v = ('严哨（红牌率>0.10）→ 红牌概率上调·大球/客队可能受益' if rr > 0.10
         else ('松哨（<0.05）→ 比赛流畅·伤停影响放大' if rr < 0.05 else '中性'))
    return {'career_games': g, 'red_rate': rr, 'yellow_per_game': yp, 'verdict': v}


# ---------------- 方案 §5 P2 ----------------
def coach_factor(hc, ac):
    def hp(c):
        try:
            return float(c.get('pressing_intensity') or 0) > 0.6 or str(c.get('defensive_line')) == 'high'
        except Exception:
            return False
    ph, pa = hp(hc or {}), hp(ac or {})
    if ph and pa:
        v = '双方高压 → 比赛开放·大球 +0.5 档'
    elif str((hc or {}).get('defensive_line')) == 'low' or str((ac or {}).get('defensive_line')) == 'low':
        v = '任一方低位防线 → 收缩·小球倾向'
    else:
        v = '不触发'
    return {'home_press': ph, 'away_press': pa, 'verdict': v}


def travel_factor(km):
    if km is None:
        return {'km': None, 'verdict': '无数据'}
    try:
        k = float(km)
    except Exception:
        return {'km': km, 'verdict': '无数据'}
    v = ('正常' if k < 200 else '轻度疲劳（不调整）' if k < 500
         else '客队体能 -0.5 档' if k < 1000 else '客队体能 -1 档（跨区/跨国）')
    return {'km': k, 'verdict': v}


def v2_positions(team_id):
    """v2 squad 补位置（v1 unavailable_players 无 position）"""
    st, j = _get(V2 + 'teams/%s/squad/' % team_id)
    out = {}
    for p in ((j or {}).get('players') or []):
        out[str(p.get('name') or '').lower()] = p.get('position')
    return out


_CITY_EN_LOCAL = {
    # 🔴2026-10-16 审计补(P1-6): 德/意/西/葡城市名的**英译 ↔ 本地语**归一
    #   根因: 1xbet 用英译（1. FC Cologne）· BSD/Bzzoiro 用本地语（1. FC Köln）
    #   → _deacc 只处理重音(Köln→Koln) → 英译名恒不命中 → case244 BSD 未定位(⚪)
    #   原理: 匹配前**两边都归一** → 即使 BSD 一侧用英译也仍一致（milan/milano 同变）
    'cologne': 'koln', 'munich': 'munchen', 'nuremberg': 'nurnberg',
    'hanover': 'hannover', 'naples': 'napoli', 'rome': 'roma',
    'turin': 'torino', 'genoa': 'genova', 'florence': 'firenze',
    'seville': 'sevilla', 'lisbon': 'lisboa', 'copenhagen': 'kobenhavn',
    'milan': 'milano', 'vienna': 'wien', 'brussels': 'bruxelles',
    'basel': 'basel', 'prague': 'praha', 'warsaw': 'warszawa',
}


def _deacc(t):
    """🔴去重音归一化（2026-10-09·用户指出「BSD 一定可用·是方式有问题」实证）:
    Bzzoiro 队名带重音（Málaga CF / Atlético / Alavés），txt 为无重音写法 → 原 `in` 匹配恒 False
    → locate_event 定位失败（case228 误判「非五大联赛」·实为 La Liga 正赛）。
    🔴2026-10-16 审计补(P1-6): 追加**英译城市名→本地语**归一（Cologne↔Köln 等），
    仅在去重音之后按整词替换，避免误伤（如 "Cologne" 不会误匹配其他词）。"""
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(t))
                if not unicodedata.combining(c)).lower().strip()
    for _en, _lc in _CITY_EN_LOCAL.items():
        if _en in s:
            s = ' '.join(_lc if w.strip('.,') == _en else w for w in s.split())
    return s


def locate_event(home, away, league_id=None, days_back=7, days_fwd=14):
    """按队名在 v1 events 索引中定位 event_id（🔴2026-10-09 加·供 calc_all 自动接入）
    → 先查 --league 指定联赛；否则扫五大联赛 id（1/3/5/4/6）"""
    import datetime as _dt
    _now = _dtm.datetime.now(_dtm.timezone.utc).replace(tzinfo=None)
    f0 = (_now - _dtm.timedelta(days=days_back)).strftime('%Y-%m-%d')
    f1 = (_now + _dtm.timedelta(days=days_fwd)).strftime('%Y-%m-%d')
    lids = [league_id] if league_id else [1, 3, 5, 4, 6]
    # 🔴2026-11-09 欧国联完善 P1-6（用户「马上欧国联开始了」）：
    #   实测 Bzzoiro `/api/events/` 的 league 对象 → **UEFA Nations League id = 64**
    #   （全量翻页佐证：id=64 「UEFA Nations League」99 场 / id=65 CONCACAF Nations League 77 场）。
    #   原 lids 只扫五大联赛 → **欧国联场恒「未定位」→ Form5（points_last_n）三态、M1 伤停无数据**。
    #   实测 id=64 的 event 有 home_form/away_form（如 Vietnam vs Chinese Taipei：13/5 与 6/5）。
    #   → 默认加入 64。⚠️ CONCACAF Nations League(65) 属北美赛事，不进默认（需要时传 --league 65）。
    if not league_id:
        lids = [1, 3, 5, 4, 6, 64]
    # 🔴2026-10-09 根治（用户指令「根治」）: 中文→英文**多候选**
    #   原直接用中文 lower() 去匹配英文 events → 恒 False → 三场全部「数据缺口降级」
    try:
        _sd2 = os.path.dirname(os.path.abspath(__file__))
        if _sd2 not in sys.path:
            sys.path.insert(0, _sd2)
        from snapshot_save import cn2en_list as _cnl2
    except Exception:
        def _cnl2(x):
            return [x]
    hn = [str(x).lower() for x in (_cnl2(home) or [home]) if x]
    an = [str(x).lower() for x in (_cnl2(away) or [away]) if x]

    def _anyM(cands, target):
        return any(_m(c, target) for c in cands)

    def _m(a, b):
        # 🔴2026-10-09 修复: 去重音后再判（原直接 in → Málaga vs Malaga 恒 False）
        _a, _b = _deacc(a), _deacc(b)
        if not (_a and _b):
            return False
        if _a in _b or _b in _a:
            return True
        # 逐词回退: 「espanyol barcelona」↔「espanyol」这类一方带后缀的情况
        _wa = [w for w in _a.split() if len(w) >= 4]
        _wb = [w for w in _b.split() if len(w) >= 4]
        return bool(_wa and _wb and (set(_wa) & set(_wb)))

    for lid in lids:
        st, j = _get(V1 + 'events/?league=%s&date_from=%s&date_to=%s&status=notstarted' % (lid, f0, f1))
        rows = (j.get('results') if isinstance(j, dict) else j) or []
        for x in rows:
            h, aw = str(x.get('home_team') or ''), str(x.get('away_team') or '')
            if (_anyM(hn, h.lower()) and _anyM(an, aw.lower())) or \
               (_anyM(an, h.lower()) and _anyM(hn, aw.lower())):
                return x.get('id'), h, aw, x.get('event_date')
    return None, None, None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--event', help='BSD event id')
    ap.add_argument('--teams', help='队名「主,客」→ 自动定位 event（供 calc_all 接入）')
    ap.add_argument('--league', help='联赛 id（配合 --teams·可选）')
    ap.add_argument('--apply', action='store_true', help='输出判定值（默认记录模式）')
    ap.add_argument('--json', help='并排落盘路径')
    a = ap.parse_args()

    if not a.event and a.teams:
        _p = [x.strip() for x in a.teams.split(',') if x.strip()]
        if len(_p) >= 2:
            _eid, _h, _aw, _d = locate_event(_p[0], _p[1], a.league)
            if _eid:
                a.event = str(_eid)
                print('\U0001f535 BSD 定位: %s vs %s → event %s (%s)' % (_h, _aw, _eid, str(_d)[:16]))
            else:
                print('\U0001f534 BSD 未定位到「%s vs %s」（不在 v1 赛事索引/非五大联赛）→ 三态降级' % (_p[0], _p[1]))
                return
    if not a.event:
        print('\U0001f534 需 --event <id> 或 --teams "主,客"')
        return

    ev = fetch_event(a.event)
    if not ev:
        print('🔴 BSD 不可用（降级：跳过 BSD 因子·模型独立跑通）')
        return
    cmpj = fetch_compare(a.event)
    ed = ev.get('event_date')
    up = ev.get('unavailable_players') or {}
    sh, dh = injury_score(up.get('home'), ed)
    sa, da = injury_score(up.get('away'), ed)

    print('=' * 78)
    print('\U0001f535 BSD 增强层（Bzzoiro）· %s vs %s · %s' % (
        ev.get('home_team'), ev.get('away_team'), str(ed)[:16]))
    print('   模式: %s' % ('\U0001f534 --apply（判定值·第二/三/四阶段）' if a.apply else '\U0001f4dd 记录模式（第一阶段·只记录不判定）'))
    print('=' * 78)

    # P0-a 伤停
    print('\n\U0001f534 P0-a 伤停因子（方案§3.1）')
    print('   主队 unavailable %d 人 · 加权分 %.2f' % (len(up.get('home') or []), sh))
    for d in dh:
        print('      %-24s %-9s %-24s 回归 %-12s d=%-5s w=%s' % (
            d['name'], d['status'], str(d['reason'])[:24], str(d['expected_return']),
            d['days'], d['weight']))
    print('   客队 unavailable %d 人 · 加权分 %.2f' % (len(up.get('away') or []), sa))
    for d in da:
        print('      %-24s %-9s %-24s 回归 %-12s d=%-5s w=%s' % (
            d['name'], d['status'], str(d['reason'])[:24], str(d['expected_return']),
            d['days'], d['weight']))
    print('   \u27a1\ufe0f 判定建议: %s' % injury_verdict(sh, sa))

    # P0-b movement
    print('\n\U0001f534 P0-b 多博彩 movement 资金流向（方案§3.2）· %s 家' % (
        (cmpj or {}).get('bookmakers_count')))
    mv = movement_verdict(cmpj) or {}
    if not mv:
        print('   （odds/compare 无 1x2 数据 → 三态标注「movement 不可用」）')
    for dn, d in mv.items():
        print('   %-18s 家=%-3d SHORT=%-2d DRIFT=%-2d n_tot=%-2d best=%-7s %s' % (
            dn, d['n_books'], d['short'], d['drift'], d['n_total'], d['best_odds'], d['verdict']))
    if mv:
        print('   \u27a1\ufe0f movement 全局判定: %s' % LAST_OVERALL.get('text'))

    # P1
    print('\n\U0001f7e1 P1 xG 攻防（方案§4.1）')
    xf = xg_factor(ev.get('home_form') or {}, ev.get('away_form') or {})
    print('   %s' % (json.dumps(xf, ensure_ascii=False) if xf else '无数据（降级）'))
    print('\U0001f7e1 P1 裁判严厉度（方案§4.2）')
    rf = referee_factor(ev.get('referee') or {})
    print('   %s' % (json.dumps(rf, ensure_ascii=False) if rf else '无数据（降级）'))
    print('\U0001f7e1 P1 H2H 先验（方案§4.3）')
    h2h = ev.get('head_to_head') or {}
    n = h2h.get('total_matches')
    if n and n >= 10:
        print('   %d 场 · 主胜率 %.2f · 客胜率 %.2f · 场均 %.2f → %s' % (
            n, h2h.get('home_win_rate') or 0, h2h.get('away_win_rate') or 0,
            h2h.get('avg_total_goals') or 0,
            ('主场心理优势' if (h2h.get('home_win_rate') or 0) > 0.5 else '无明显主场优势')
            + ('·交锋历来开放(>3.0)' if (h2h.get('avg_total_goals') or 0) > 3.0 else '')))
    else:
        print('   total_matches=%s <10 → 样本不足·仅参考' % n)

    # P2
    print('\n\U0001f7e2 P2 教练风格（方案§5.1）')
    print('   %s' % json.dumps(coach_factor(ev.get('home_coach'), ev.get('away_coach')), ensure_ascii=False))
    print('\U0001f7e2 P2 旅行距离（方案§5.2）')
    print('   %s' % json.dumps(travel_factor(ev.get('travel_distance_km')), ensure_ascii=False))
    print('\U0001f7e2 P2 其他: 温度 %s · 德比 %s · 天气码 %s' % (
        ev.get('temperature_c'), ev.get('is_local_derby'), ev.get('weather_code')))
    print('   \u26d4 ai_preview: 已按方案§二/§八**剔除未读**')

    rec = {'event_id': a.event, 'home': ev.get('home_team'), 'away': ev.get('away_team'),
           'event_date': ed, 'mode': 'apply' if a.apply else 'record',
           'injury': {'home_score': sh, 'away_score': sa, 'home_detail': dh, 'away_detail': da,
                      'verdict': injury_verdict(sh, sa)},
           'movement': mv, 'xg': xf, 'referee': rf,
           'h2h': {'total_matches': n, 'home_win_rate': h2h.get('home_win_rate'),
                   'away_win_rate': h2h.get('away_win_rate'), 'avg_total_goals': h2h.get('avg_total_goals')},
           'coach': coach_factor(ev.get('home_coach'), ev.get('away_coach')),
           'travel': travel_factor(ev.get('travel_distance_km')),
           'odds_inline': {'h': ev.get('odds_home'), 'd': ev.get('odds_draw'), 'a': ev.get('odds_away'),
                           'o25': ev.get('odds_over_25'), 'u25': ev.get('odds_under_25')}}
    if a.json:
        json.dump(rec, open(a.json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('\n[落盘] %s' % a.json)
    if not a.apply:
        print('\n\U0001f4dd 记录模式：以上**仅供并排对照**·不进入 Step5/6/7 判定（方案§七 第一阶段）')


if __name__ == '__main__':
    main()
