# -*- coding: utf-8 -*-
"""Bzzoiro Sports Data · 结构化伤停源（源B8·2026-10-09 接入·用户决策①）

🔴 定位: api-football 停用后，伤停曾降级为「Bing/Google News **文本标题**」→ 铁则32 的位置级
   影响分只能靠 LLM 猜。Bzzoiro 提供**结构化**伤停（位置+状态+伤情+预计回归）→ 恢复确定性计算。

用法:
  python data/tmp/bzzoiro_fetch.py --event 213710              # 按赛事取两队伤停（推荐）
  python data/tmp/bzzoiro_fetch.py --teams "SC Freiburg,FC Schalke 04" [--league 5]
  python data/tmp/bzzoiro_fetch.py --status                    # 连通性 + coverage + 五大联赛 id

输出: ①人读清单 ②🔴 injury_impact.py 可消费的「位置,重要性」条目（保守=未知 / 主力假设）
🔴 位置精度局限: Bzzoiro 仅 G/D/M/F 四级 → 映射为 门将/中后卫/后腰/前锋（比新闻文本强·低于 7 类细粒度）
🔴 重要性未知: squad 无主力/替补字段 → 默认按「未知」(×1.0) 保守计算，并同时给出「主力」(×1.5) 备选
"""
import sys, os, json, argparse, time, urllib.request, unicodedata

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE = 'https://sports.bzzoiro.com/api/v2/'
PROXY = 'http://127.0.0.1:7897'
HERE = os.path.dirname(os.path.abspath(__file__))
FIVE = ('Premier League', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1')
POSMAP = {'G': '门将', 'D': '中后卫', 'M': '后腰', 'F': '前锋'}


def _deacc(t):
    """🔴去重音归一化（2026-10-09·Málaga vs Malaga 匹配修复）"""
    return ''.join(c for c in unicodedata.normalize('NFKD', str(t))
                   if not unicodedata.combining(c)).lower().strip()


def key():
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
    raise RuntimeError('🔴 未找到 Bzzoiro key：请设环境变量 BZZOIRO_KEY 或在 data/tmp/api_keys.json 写 {"bzzoiro": "..."}')


def get(path, timeout=25):
    """双通道（代理优先——实测该域代理通道稳定）。返回 (status, text)"""
    u = BASE + path
    h = {'Authorization': 'Token ' + key(), 'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
    last = None
    for _ph in (PROXY, None):
        try:
            op = (urllib.request.build_opener(urllib.request.ProxyHandler({})) if _ph is None
                  else urllib.request.build_opener(urllib.request.ProxyHandler({'https': _ph, 'http': _ph})))
            with op.open(urllib.request.Request(u, headers=h), timeout=timeout) as r:
                return r.status, r.read().decode('utf-8', errors='replace')
        except urllib.error.HTTPError as e:
            try:
                return e.code, e.read().decode('utf-8', errors='replace')[:200]
            except Exception:
                return e.code, ''
        except Exception as e:
            last = e
    return None, str(last)[:90]


def getj(p):
    st, b = get(p)
    try:
        return st, json.loads(b)
    except Exception:
        return st, None


# 🔴2026-11-01 新增：联赛覆盖白名单（实证 50 个联赛·**无任何亚洲联赛**）
#   用途：区分「源不覆盖」（合规三态）vs「覆盖但未定位」（需查）
COVERED_LEAGUES = {
    '英超', 'Premier League', '西甲', 'La Liga', '德甲', 'Bundesliga',
    '意甲', 'Serie A', '法甲', 'Ligue 1', 'Ligue 2', 'Ligue 3',
    '欧冠', 'Champions League', '欧联', 'Europa League', '欧协联', 'Conference League',
    '欧国联', 'UEFA Nations League', '欧超杯', 'UEFA Super Cup',
    '英冠', 'Championship', '英甲', 'League One', '英乙', 'League Two',
    '英联赛杯', 'Carabao Cup', '足总杯', 'FA Cup',
    '德乙', '2. Bundesliga', '德国杯', 'DFB Pokal', '意大利杯', 'Coppa Italia',
    '法国杯', 'Coupe de France', '巴西甲', 'Brasileirão Serie A',
    '巴西乙', 'Brasileirão Serie B', '巴西杯', 'Copa do Brasil',
    '中超', 'Chinese Super League', '澳超', 'A-League Men',
    '葡超', 'Parva Liga', '希腊超', 'Stoiximan Super League',
    '丹麦超', 'Danish Superliga', '捷克甲', 'Czech First League',
    '奥甲', 'Austrian Bundesliga', '比甲', 'Pro League',
    '荷甲', 'Suomen Cup', '芬超', 'Veikkausliiga', '阿甲', 'Liga Profesional de Fútbol',
    '哥甲', 'Categoría Primera A', '哥杯', 'Copa Colombia',
    '比乙', 'Challenger Pro League', '安哥拉', 'Girabola', '英议联', 'National League',
    '世预赛', 'World Cup Qualification', '世界杯', 'World Cup 2026',
    '友谊赛', 'International Friendly Games', '亚洲杯', 'AFC Asian Cup',
    '非洲杯', 'Africa Cup of Nations', '非洲冠军联赛', 'CAF Champions League',
}

# 明确**不覆盖**（实证不在 50 个联赛里）
UNCOVERED_HINT = {
    '日职', '日职联', 'J1', 'J2', 'J-League', 'JLeague',
    '韩职', '韩职联', 'K League', 'KLeague', 'K1',
    '日乙', '韩乙', '亚冠', 'AFC Champions League',
}


def league_covered(league):
    """→ (是否覆盖, 说明)

    实测依据（2026-11-01）：Bzzoiro `/api/v2/leagues/` 共 **50 个联赛**，
    亚洲**仅有** 中超 / 澳超 / 亚洲杯 / 世预赛-AFC —— **无日职、无韩职**。
    """
    if not league:
        return None, '未传联赛 → 无法判定覆盖'
    lg = str(league).strip()
    for k in UNCOVERED_HINT:
        if k.lower() in lg.lower():
            return False, ('🔴 源不覆盖：Bzzoiro 50 个联赛**无 %s**'
                           '（仅中超/澳超/亚洲杯/世预赛AFC）→ 三态合规' % lg)
    for k in COVERED_LEAGUES:
        if k.lower() in lg.lower() or lg.lower() in k.lower():
            return True, '✅ 源覆盖：%s 在 Bzzoiro 联赛表内' % lg
    return None, '⚪ 未知联赛「%s」→ 建议查 /leagues/ 确认' % lg


# 🔴V3.5.91 新增（2026-11-03 case320 实证）: **索引覆盖**（≠ 联赛覆盖）
#   两个概念必须分开:
#     ① COVERED_LEAGUES —— Bzzoiro `/api/v2/leagues/` 有该联赛 → 可查 squad/赛事数据
#     ② INDEX_COVERED   —— `--teams` 定位依赖 v1 events 索引，而 locate_event 只扫五大
#   → 欧冠/欧联/欧协联/欧国联 属「①覆盖 ②不覆盖」→ 传 --teams 必定位失败，
#     且要扫完五大才失败（实测等满 240s 超时）→ 应在入口直接三态
INDEX_COVERED = {
    '英超', 'Premier League', '西甲', 'La Liga', '德甲', 'Bundesliga',
    '意甲', 'Serie A', '法甲', 'Ligue 1',
    # 🔴2026-11-09 欧国联完善：**UEFA Nations League 在 v1 events 索引内（league id = 64）**
    #   实测依据（当晚全量翻页）：id=64「UEFA Nations League」99 场 / id=65「CONCACAF Nations League」77 场
    #   且 `bsd_layer.locate_event` 的 lids 已加 64 → 实测定位 4/4：
    #     Italy vs France 212689 / Türkiye vs Belgium 212687 / Spain vs England 212720 / Czechia vs Spain 212690
    #   → 原白名单无欧国联 → pipeline Stage2 直接判「索引不覆盖」→ 伤停恒三态（
    #     与 AGENTS「Bzzoiro 覆盖欧国联」矛盾，且 locate_event 明明能定位）
    #   ⚠️ 欧战（欧冠/欧联/欧协联）的 Bzzoiro league id **尚未实测** → 暂不加（保持三态·宁缺勿猜）
    '欧国联', 'Nations League', 'UEFA Nations League', 'nations',
}


def index_covered(league):
    """→ (是否可定位, 说明)  —— 仅五大联赛在 v1 events 索引内"""
    if not league:
        return None, '未传联赛 → 无法判定索引覆盖'
    lg = str(league).strip()
    for k in INDEX_COVERED:
        if k.lower() in lg.lower() or lg.lower() in k.lower():
            return True, '✅ events 索引覆盖：%s' % lg
    return False, ('⚪ 索引不覆盖：「%s」不在 v1 events 索引（仅五大联赛）'
                   '→ 传 --teams 必定位失败 → 直接三态·省 240s 超时'
                   '（若已知 event_id 请用 --event）' % lg)


def five_ids():
    st, j = getj('leagues/?limit=200')
    rows = (j.get('results') if isinstance(j, dict) else j) or []
    return {str(x.get('name')): x.get('id') for x in rows if str(x.get('name')) in FIVE}


def squad(team_id):
    # 🔴2026-10-30 加 squad 结果缓存（2h）—— 原实现每次调用都实拉 API：
    #   `bzzoiro_fetch --teams "A,B"` 需 2 次 squad 请求 ×25s timeout → 实测**总耗时 >2 分钟**
    #   → pipeline 超时 → 被当三态 → **又一次静默遗漏**（用户最后通牒指出的正是这类）
    #   缓存键 = team_id；TTL 2h（伤停名单日内变化小，2h 足够新鲜）
    _SC = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_bzz_squad_cache.json')
    _ttl = 2 * 3600
    _now = time.time()
    _cache = {}
    if os.path.exists(_SC):
        try:
            _cache = json.load(open(_SC, encoding='utf-8'))
        except Exception:
            _cache = {}
    ck = str(team_id)
    e = _cache.get(ck) or {}
    if e.get('ts') and (_now - e['ts']) < _ttl and e.get('players') is not None:
        print('  [cache] squad %s 命中缓存（%d 人·%.0f 分钟前）'
              % (team_id, len(e['players']), (_now - e['ts']) / 60))
        return e['players']
    st, j = getj('teams/%s/squad/' % team_id)
    if isinstance(j, dict):
        players = j.get('players') or []
    else:
        players = j if isinstance(j, list) else []
    if players:          # 只在成功时写缓存（失败不缓存·避免固化错误）
        _cache[ck] = {'ts': _now, 'players': players}
        try:
            json.dump(_cache, open(_SC, 'w', encoding='utf-8'), ensure_ascii=False)
        except Exception:
            pass
    return players


def out_players(team_id, tname, players, show_all=False, side='home'):
    bad = [p for p in players
           if str(p.get('availability')).lower() not in ('available', 'none', '')]
    print('\n  \U0001f3f3 %s (team_id=%s) 名单 %d 人 · 缺阵/存疑 %d 人' % (tname, team_id, len(players), len(bad)))
    if not bad:
        print('     ✅ 全部 available（或该队近期无赛事未刷新）')
    for p in bad:
        pos_raw = str(p.get('position') or '').upper()
        cn = POSMAP.get(pos_raw, '未知')
        print('     %-26s %-4s→%-4s %-10s %-24s 回归 %s' % (
            str(p.get('name'))[:26], pos_raw, cn, p.get('availability'),
            str(p.get('injury_type') or '-')[:24], p.get('injury_expected_return') or '-'))
    if show_all:
        for p in players:
            print('     %-26s %-4s #%s %s' % (str(p.get('name'))[:26], p.get('position'),
                                              p.get('jersey_number'), p.get('availability')))
    return [POSMAP.get(str(p.get('position') or '').upper(), '未知') for p in bad]


def impact(items, mult):
    return ['%s,%s' % (pos, mult) for pos in items]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--event', help='赛事 id（自动取主客两队）')
    ap.add_argument('--teams', help='队名（逗号分隔）')
    ap.add_argument('--league', help='联赛 id（--teams 时用于建队名索引·默认扫五大）')
    ap.add_argument('--status', action='store_true', help='连通性 + coverage + 五大联赛 id')
    ap.add_argument('--all', action='store_true', help='列出全名单')
    a = ap.parse_args()

    if a.status or not (a.event or a.teams):
        st, b = get('coverage/', timeout=20)
        print('Bzzoiro 连通性: HTTP %s' % st)
        if st == 200:
            j = json.loads(b)
            fb = [x for x in (j.get('sports') or []) if x.get('sport') == 'football']
            if fb:
                f = fb[0]
                print('  football: %s | 未来7天 %s 场 | 未来30天 %s 场 | 已定价 %s' % (
                    f.get('status'), f.get('events_next_7d'), f.get('events_next_30d'), f.get('priced_next_7d')))
        fi = five_ids()
        print('  五大联赛 id:', fi or '\U0001f534 未取到')
        print('  位置映射: G→门将 / D→中后卫 / M→后腰 / F→前锋（Bzzoiro 仅 4 级）')
        return

    # 决定要查的 team_id
    pairs = []
    if a.event:
        st, j = getj('events/%s/' % a.event)
        if isinstance(j, dict):
            pairs = [(j.get('home_team_id'), j.get('home_team') or str(j.get('home_team_id'))),
                     (j.get('away_team_id'), j.get('away_team') or str(j.get('away_team_id')))]
        else:
            print('\U0001f534 取赛事失败 HTTP=%s' % st); return
    else:
        want = [x.strip() for x in a.teams.split(',') if x.strip()]
        lg_ids = [a.league] if a.league else list(five_ids().values())
        # 🔴2026-10-28 P20 修复（卡顿+失效根因·用户报「每场分析经常卡顿」实测）:
        #   原代码 date_from/date_to **硬编码 2026-10-01 ~ 2026-10-20** →
        #   ① 随时间推移窗口越滑越远（罗马场 10-28 已在窗口外）→ 扫完 5 大联赛仍索引不到 → **定位失败**
        #   ② 每次调用全量扫 5 联赛 × 分页 = **实测 32.5 秒**，且失败时白跑
        #   现改：ⓐ 日期窗口动态（默认 today−45d ~ today+45d，可用 --from/--to 覆盖）
        #          ⓑ 联赛 events 索引 **本地缓存 6 小时**（同一批分析只扫一次）
        import datetime as _dt2
        _d0 = getattr(a, 'date_from', None) or (_dt2.date.today() - _dt2.timedelta(days=45)).isoformat()
        _d1 = getattr(a, 'date_to', None) or (_dt2.date.today() + _dt2.timedelta(days=45)).isoformat()
        _CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_bzz_idx_cache.json')
        _idx_cache = {}
        try:
            if os.path.exists(_CACHE):
                _idx_cache = json.load(open(_CACHE, encoding='utf-8'))
        except Exception:
            _idx_cache = {}
        idx = {}
        _now = time.time()
        for lid in lg_ids:
            _ck = '%s|%s|%s' % (lid, _d0, _d1)
            _ce = _idx_cache.get(_ck)
            if _ce and (_now - _ce.get('ts', 0) < 6 * 3600):
                for _nm, _v in _ce.get('items', {}).items():
                    idx[_nm] = tuple(_v)
                print('  [cache] league %s 索引命中缓存（%d 队）' % (lid, len(_ce.get('items') or {})))
                continue
            st, j = getj('events/?league=%s&date_from=%s&date_to=%s' % (lid, _d0, _d1))
            _items = {}
            for x in ((j.get('results') if isinstance(j, dict) else j) or []):
                for k in ('home_team_id', 'away_team_id'):
                    nm = x.get('home_team') if k == 'home_team_id' else x.get('away_team')
                    if x.get(k) and nm:
                        idx[_deacc(nm)] = (x.get(k), nm)
                        _items[_deacc(nm)] = [x.get(k), nm]
            _idx_cache[_ck] = {'ts': _now, 'items': _items}
        try:
            json.dump(_idx_cache, open(_CACHE, 'w', encoding='utf-8'), ensure_ascii=False)
        except Exception:
            pass
        for _wi, w in enumerate(want):
            hit = idx.get(_deacc(w))
            if not hit:
                # 🔴2026-10-27 修（罗马/卡利亚里 实抓）: 原写 [(v, k) for k, v in idx.items() ...]
                #   → 元素为 ((id, 原名), 队名) → hit[0] 变成**元组** → squad(tid) 内
                #   'teams/%s/squad/' % (id, 原名) → TypeError: not all arguments converted
                #   ⇒ 模糊命中的场次伤停整层崩掉（精确命中不崩→隐蔽）。改为直接取 v。
                cand = [v for k, v in idx.items() if _deacc(w) in k or k in _deacc(w)]
                hit = cand[0] if cand else None
            if hit:
                pairs.append((hit[0], hit[1], 'home' if _wi == 0 else 'away'))
            else:
                print('  ⚠️ 未定位到队名:', w, '→ 该侧伤停=三态（🔴禁把另一队当归此侧·防主客算反）')
        if not pairs:
            print('\U0001f534 未定位到任何队（可改用 --event 直接定位）'); return

    print('=' * 74)
    print('\U0001f534 Bzzoiro 结构化伤停（源B8·替代 api-football injuries）')
    print('=' * 74)
    side_pos = {'home': [], 'away': []}   # 🔴2026-10-09 修正: 按主/客分组(原混在一起 → 影响分算错)
    ok_n = 0
    for _i, _item in enumerate(pairs):
        tid, tname = _item[0], _item[1]
        if not tid:
            continue
        pl = squad(tid)
        if pl:
            ok_n += 1
        # 🔴2026-10-25 修（case279 实证）: 原按 pairs 命中下标定侧 → 主队未定位时客队被当主队
        _side = (_item[2] if len(_item) > 2 else ('home' if _i == 0 else 'away'))
        side_pos[_side] += out_players(tid, tname, pl, a.all, side=_side)
    allpos = side_pos['home'] + side_pos['away']
    print('\n' + '-' * 74)
    if ok_n == 0:
        print('\U0001f534 两队名单均未取到 → 三态标注「伤停维度不可用（Bzzoiro 无返回）」')
        return
    if not allpos:
        print('✅ 两队均无缺阵记录（或未刷新）→ 影响分 0')
        return
    # 🔴2026-10-09 修正（审计发现）: injury_impact.py 的真实接口是 --home/--away（**分号分隔**多条），
    #   原示例用位置参数 → 照抄必失败（argparse: unrecognized arguments）
    print('🔴 injury_impact.py 条目（🔴正确接口 = --home/--away·分号分隔·按主客分组）:')
    _hi = ';'.join(impact(side_pos['home'], '未知'))
    _ai = ';'.join(impact(side_pos['away'], '未知'))
    _hm = ';'.join(impact(side_pos['home'], '主力'))
    _am = ';'.join(impact(side_pos['away'], '主力'))
    print('   保守（重要性未知 ×1.0·默认采用）:')
    print('     python data/tmp/injury_impact.py --home "%s" --away "%s"' % (_hi, _ai))
    print('   备选（视为主力 ×1.5）:')
    print('     python data/tmp/injury_impact.py --home "%s" --away "%s"' % (_hm, _am))
    print('   （--home/--away 内多条用分号分隔·`--home_attack/--away_attack` 标注攻击线伤停）')
    print('   ⚠️ 重要性需结合号码/新闻判断后选定；铁则32 触发线 = 影响分 ≥4.0')


if __name__ == '__main__':
    main()
