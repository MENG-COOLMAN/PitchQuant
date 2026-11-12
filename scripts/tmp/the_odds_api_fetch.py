# -*- coding: utf-8 -*-
"""the-odds-api 欧亚盘多机构拉取（2026-09-27 · 用户选定数据源）

🔴 能力实测（2026-09-27）:
  ✅ current : 当前多机构赔率 —— h2h + spreads(亚盘·可多档) + totals(大小球) · 免费可用
  ❌ history : 历史逐时点快照 —— 免费计划返回 401 HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN（需付费）
  ⚠️ range   : 多时点遍历构造「逐T」 —— 同样需付费计划

免费额度: 500 次/月（响应头 x-requests-remaining 可查）

用法:
  python data/tmp/the_odds_api_fetch.py current [--sport soccer_uefa_nations_league] [--case 206] [--regions eu,uk]
  python data/tmp/the_odds_api_fetch.py history --date 2026-09-26T15:00:00Z [--sport X]
  python data/tmp/the_odds_api_fetch.py range --from 2026-09-26T12:00:00Z --to 2026-09-26T16:00:00Z --step 60
  python data/tmp/the_odds_api_fetch.py quota          # 只看剩余额度

输出（current）:
  data/tmp/snapshots/<case|sport>.json —— 与 odds_snapshot.py 同结构（snapshots[] 追加一个时点）
  · 每个时点: {t, source:"the-odds-api", n_books, events:[{home,away,commence,h2h:[...],spreads:[...],totals:[...]}]}
"""
import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP_DIR = os.path.join(HERE, 'snapshots')
BASE = 'https://api.the-odds-api.com/v4'
DEFAULT_SPORT = 'soccer_uefa_nations_league'

# 🔴2026-10-27 P0 修复（case287 实抓）: 原只有 DEFAULT_SPORT 且默认=欧国联 →
#   做意甲/英超等场次时**若不显式传 --sport 就会拉到欧国联 8 场**，表现为
#   「books 中未找到本场 → 误判『the-odds-api 未覆盖该联赛』」。
#   实测: `current`（默认）→ 8 场欧国联；`current --sport soccer_italy_serie_a` → **20 场意甲 · 41 家机构**。
#   修法: ① 加 --league 中文映射（自动转 sport key）② 未显式指定时**打印醒目提示**（不再静默用欧国联）
SPORT_MAP = {
    '意甲': 'soccer_italy_serie_a', 'seriea': 'soccer_italy_serie_a',
    '英超': 'soccer_epl', 'epl': 'soccer_epl',
    '西甲': 'soccer_spain_la_liga', 'laliga': 'soccer_spain_la_liga',
    '德甲': 'soccer_germany_bundesliga', 'bundesliga': 'soccer_germany_bundesliga',
    '法甲': 'soccer_france_ligue_one', 'ligue1': 'soccer_france_ligue_one',
    '欧冠': 'soccer_uefa_champs_league', 'ucl': 'soccer_uefa_champs_league',
    '欧联': 'soccer_uefa_europa_league', 'uel': 'soccer_uefa_europa_league',
    '欧国联': 'soccer_uefa_nations_league', 'nl': 'soccer_uefa_nations_league',
    '巴甲': 'soccer_brazil_campeonato', '中超': 'soccer_china_superleague',
    # 🔴2026-10-30 实测补（/v4/sports 列表核实 active=True）：瑞典超/芬超/丹超/挪超/日职/韩K
    '瑞典超': 'soccer_sweden_allsvenskan', 'allsvenskan': 'soccer_sweden_allsvenskan',
    '芬超': 'soccer_finland_veikkausliiga', 'veikkausliiga': 'soccer_finland_veikkausliiga',
    '丹超': 'soccer_denmark_superliga', '挪超': 'soccer_norway_eliteserien',
    '日职': 'soccer_japan_j_league', '韩K': 'soccer_korea_kleague1',
}


def resolve_sport(a):
    """--league 中文优先 → --sport 显式 → 默认（并醒目提示）"""
    lg = (getattr(a, 'league', None) or '').strip()
    if lg:
        k = SPORT_MAP.get(lg) or SPORT_MAP.get(lg.lower().replace(' ', ''))
        if k:
            print('  [sport] --league %s → %s' % (lg, k))
            return k
        print('  ⚠️ --league=%s 无内置映射 → 沿用 --sport=%s' % (lg, a.sport))
    if a.sport == DEFAULT_SPORT:
        print('  🔴 未指定 --sport/--league → 默认 **%s**（欧国联）'
              ' ｜ 五大联赛请传 `--league 意甲` 或 `--sport soccer_italy_serie_a`' % DEFAULT_SPORT)
    return a.sport


# ══════════════════════════════════════════════════════════════════════
# 🔴key 池轮转（2026-10-31 用户指令「一个用完就换另一个·没用完就不换」）
#   原实现单 key → 配额用尽即全站三态（跨机构分歧 P0-1 直接瘫痪）
#   机制: 池顺序取第一个**未标记用尽**的 key；只有真收到配额错误才标记+切换；
#         成功即记 remaining 并**继续用同一个**（不轮询/不主动探测·省额度）；
#         30 天自动恢复（额度按月重置）；功能类错误（historical 需付费）不换 key。
# ══════════════════════════════════════════════════════════════════════
STATE_P = os.path.join(HERE, 'the_odds_api_key_state.json')
RESET_DAYS = 30
QUOTA_MARKS = ('OUT_OF_USAGE_CREDITS', 'OUT_OF_QUOTA', 'Usage quota has been reached',
               'quota has been reached', 'exceeded your quota', 'monthly quota')
# 🔴这些是**功能限制**不是配额 → 换 key 无用，禁标记用尽（否则误拉黑好 key）
NOT_QUOTA_MARKS = ('HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN',)
# 🔴key 本身无效（配置输错）→ **必须切下一个**（否则一个错 key 卡死整条链·实测 2026-10-31）
INVALID_KEY_MARKS = ('INVALID_KEY', 'API key is not valid', 'MISSING_KEY',
                     'apiKey is required', 'invalid api key')


def mask_key(k):
    k = str(k or '')
    return (k[:6] + '…' + k[-4:]) if len(k) > 12 else (k[:3] + '…')


def _key_state():
    """读状态文件·顺带把已到重置期的「用尽」自动恢复为可用

    🔴2026-11-07 修（用户指出「k1 应该是恢复了」·实测成立）：
      额度是**按自然月重置**（月初 1 号归零），不是「耗尽后满 30 天」。
      原判据 `(now - t0).days >= 30` → 10-31 耗尽的 K1 被锁到 11-30，
      但实测 11-07 已 `used=0 / remaining=500`（**满血**）→ **白等 29 天**。
      新判据：**跨月即恢复**（year,month 与耗尽时不同）**或** 仍满 30 天 → 任一满足即可用。
      两种都保留：跨月覆盖「月初重置」，30 天兜底防「接口改成真·30 天」。
    """
    try:
        d = json.load(io.open(STATE_P, encoding='utf-8')) or {}
    except Exception:
        d = {}
    import datetime as dt
    now = dt.datetime.now()
    for k, v in list(d.items()):
        if not isinstance(v, dict) or v.get('state') != 'exhausted':
            continue
        try:
            t0 = dt.datetime.strptime(v.get('exhausted_at', ''), '%Y-%m-%dT%H:%M')
            crossed_month = (now.year, now.month) != (t0.year, t0.month)
            if crossed_month or (now - t0).days >= RESET_DAYS:
                v['state'] = 'ready'
                v['note'] = ('已跨月(%s→%s) → 按月度重置视为可用' % (t0.strftime('%Y-%m'), now.strftime('%Y-%m'))
                             if crossed_month else '已过 %d 天 → 视为可用' % RESET_DAYS)
        except Exception:
            pass
    return d


def _state_save(d):
    try:
        io.open(STATE_P, 'w', encoding='utf-8').write(
            json.dumps(d, ensure_ascii=False, indent=1))
    except Exception as e:
        print('  ⚠️ key 状态写入失败: %s' % e)


def load_keys():
    """返回 [(序号, key, 状态dict)]·池顺序·去重保序
    来源: env THE_ODDS_API_KEY（优先·K1）→ api_keys.json 的 the_odds_api_pool
          （无 pool 时兼容旧单值 the_odds_api）
    """
    pool = []
    env = (os.environ.get('THE_ODDS_API_KEY') or '').strip()
    if env:
        pool.append(env)
    try:
        cfg = json.load(io.open(os.path.join(HERE, 'api_keys.json'), encoding='utf-8')) or {}
    except Exception:
        cfg = {}
    got = cfg.get('the_odds_api_pool')
    if isinstance(got, list):
        pool += [str(x).strip() for x in got if str(x).strip()]
    elif (cfg.get('the_odds_api') or '').strip():
        pool.append(cfg['the_odds_api'].strip())
    seen, uniq = set(), []
    for k in pool:
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    st = _key_state()
    return [(i + 1, k, st.get(k, {})) for i, k in enumerate(uniq)]


def load_key():
    """兼容旧接口：返回**第一个可用** key（全部用尽则返回第一个·由调用方处理错误）"""
    ks = load_keys()
    if not ks:
        return ''
    for _i, k, st in ks:
        if st.get('state') != 'exhausted':
            return k
    return ks[0][1]


def _is_quota_err(code, body):
    b = (body or '')
    if any(x in b for x in NOT_QUOTA_MARKS):
        return False                      # 功能限制·换 key 无用
    if any(x.lower() in b.lower() for x in QUOTA_MARKS):
        return True
    return code == 429


def _is_invalid_key(body):
    """key 无效（输错/被删）—— 与「配额用尽」不同：**不自动恢复·需人工改配置**"""
    b = (body or '').lower()
    return any(x.lower() in b for x in INVALID_KEY_MARKS)


def mark_invalid(k, body=''):
    d = _key_state()
    d[k] = {'state': 'invalid', 'marked_at': __import__('datetime').datetime.now()
            .strftime('%Y-%m-%dT%H:%M'), 'reason': (body or '')[:120]}
    _state_save(d)
    print('  🔴 key %s **无效（INVALID_KEY）** → 已跳过（不自动恢复·请检查 api_keys.json 是否输错）'
          % mask_key(k))


def mark_exhausted(k, body='', remaining=None):
    d = _key_state()
    import datetime as dt
    d[k] = {'state': 'exhausted',
            'exhausted_at': dt.datetime.now().strftime('%Y-%m-%dT%H:%M'),
            'remaining': remaining,
            'reason': (body or '')[:120]}
    _state_save(d)
    print('  🔴 key %s 额度用尽 → 已标记（%d 天后自动恢复）' % (mask_key(k), RESET_DAYS))


def note_remaining(k, remaining):
    """成功调用 → 记录剩余额度（供 quota 命令查看·不主动探测省请求）"""
    if remaining in (None, ''):
        return
    d = _key_state()
    cur = d.get(k) if isinstance(d.get(k), dict) else {}
    cur.update({'state': 'ready', 'remaining': remaining})
    d[k] = cur
    _state_save(d)


def print_all_exhausted(tried, where=''):
    """🔴全池耗尽的**统一告知**（用户指令 2026-10-31：两个都没了要告诉我）。

    必须满足: ① 一眼看出「是 key 用完了，不是源坏了」 ② 给出**可操作**解法
              ③ 说明影响面（哪些层走三态、哪些不受影响）
    """
    ks = load_keys()
    names = ' / '.join('K%d %s' % (i, mask_key(k)) for i, k, _st in ks) or '（池为空）'
    _n_invalid = sum(1 for _i, _k, _s in ks if _s.get('state') == 'invalid')
    _n_exhaust = sum(1 for _i, _k, _s in ks if _s.get('state') == 'exhausted')
    if _n_invalid and not _n_exhaust:
        _title = ('🔴🔴 the-odds-api **全部 %d 个 key 都无效（INVALID_KEY）** → 请检查 key 是否输错'
                  % len(ks))
    elif _n_invalid and _n_exhaust:
        _title = ('🔴🔴 the-odds-api **key 池已不可用**（%d 个无效 / %d 个额度用尽）'
                  % (_n_invalid, _n_exhaust))
    else:
        _title = '🔴🔴 the-odds-api **全部 %d 个 key 额度都用完了** → 需要你补 key' % len(ks)
    print('')
    print('=' * 76)
    print(_title)
    print('   池内: %s' % names)
    if tried:
        print('   本次: %s' % ' ｜ '.join(tried))
    print('   解法① 补 key（推荐·立即生效）:')
    print('        往 `data/tmp/api_keys.json` 的 **the_odds_api_pool** 追加一个 key 字符串')
    print('        （数组形式·自动轮转·**不用改代码**）')
    print('   解法② 等重置: 额度按月重置·已用尽的 key **30 天后自动恢复**（无需手动清状态）')
    print('   影响面: 跨机构分歧 P0-1 / 亚盘多档 spreads / BTTS 走**三态**；')
    print('           其余分析（calc_all 主体 / 方向 / 锚 / 大小球）**不受影响·不阻断流程**')
    if where:
        print('   触发点: %s' % where)
    print('=' * 76)
    print('')


def fetch_rotated(build_url, quiet=False):
    """按池顺序逐个 key 请求；额度用尽 → 标记 + 切下一个。

    返回 (data, headers, key_used, tried)
      · 全池用尽 → data = {'_all_exhausted': True, '_tried': [...]}
      · 非配额错误（如 historical 需付费）→ 原样返回（**不换 key**）
    """
    pool = load_keys()
    if not pool:
        return {'_no_key': True}, {}, None, []
    tried = []
    for idx, k, st in pool:
        if st.get('state') == 'exhausted':
            tried.append('K%d(%s)已用尽@%s' % (idx, mask_key(k),
                                              (st.get('exhausted_at') or '')[:10]))
            continue
        if st.get('state') == 'invalid':
            tried.append('K%d(%s)key无效' % (idx, mask_key(k)))
            continue
        d, h = fetch(build_url(k))
        if isinstance(d, dict) and d.get('_http_error'):
            code, body = d['_http_error'], d.get('_body', '')
            # 🔴key 无效 → 标记 + 切下一个（防守：一个错 key 不能卡死整条链）
            if _is_invalid_key(body):
                mark_invalid(k, body)
                tried.append('K%d(%s)key 无效→切下一个' % (idx, mask_key(k)))
                continue
            if _is_quota_err(code, body):
                mark_exhausted(k, body, h.get('x-requests-remaining'))
                tried.append('K%d(%s)额度用尽→切下一个' % (idx, mask_key(k)))
                continue
            return d, h, k, tried          # 非配额错：换 key 无用，直接返回
        note_remaining(k, h.get('x-requests-remaining'))
        if tried and not quiet:
            print('  🔄 key 轮转: %s → 本次用 K%d(%s)'
                  % (' ｜ '.join(tried), idx, mask_key(k)))
        return d, h, k, tried
    return {'_all_exhausted': True, '_tried': tried}, {}, None, tried


def fetch(url):
    """直连优先 → 代理回退（真直连须空 ProxyHandler）"""
    last = None
    for opener in (urllib.request.build_opener(urllib.request.ProxyHandler({})),
                   urllib.request.build_opener(urllib.request.ProxyHandler(
                       {'http': 'http://127.0.0.1:7897', 'https': 'http://127.0.0.1:7897'}))):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with opener.open(req, timeout=35) as r:
                hdr = {k.lower(): v for k, v in r.getheaders()}
                return json.loads(r.read().decode('utf-8')), hdr
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', 'replace')
            return {'_http_error': e.code, '_body': body}, {}
        except Exception as e:
            last = e
    raise last


def normalize(events):
    """按场次整理: 每场 → {home, away, commence, markets:{h2h:[...], spreads:[...], totals:[...]}}"""
    out = []
    for e in events or []:
        row = {'home': e.get('home_team'), 'away': e.get('away_team'),
               'commence': e.get('commence_time'), 'id': e.get('id'), 'markets': {}}
        for b in (e.get('bookmakers') or []):
            for m in (b.get('markets') or []):
                row['markets'].setdefault(m.get('key'), []).append(
                    {'book': b.get('key'), 'last_update': m.get('last_update'),
                     'outcomes': m.get('outcomes')})
        out.append(row)
    return out


def save_snapshot(tag, t, rows, n_books, extra=None):
    os.makedirs(SNAP_DIR, exist_ok=True)
    p = os.path.join(SNAP_DIR, '%s.json' % tag)
    d = {'case_id': tag, 'snapshots': []}
    if os.path.exists(p):
        try:
            with io.open(p, encoding='utf-8') as f:
                d = json.load(f)
        except Exception:
            pass
    rec = {'t': t, 'source': 'the-odds-api', 'n_books': n_books, 'events': rows}
    if extra:
        rec.update(extra)
    d.setdefault('snapshots', []).append(rec)
    with io.open(p, 'w', encoding='utf-8') as f:
        f.write(json.dumps(d, ensure_ascii=False, indent=1))
    return p, len(d['snapshots'])


def cmd_current(a):
    a.sport = resolve_sport(a)
    d, h, key, _tried = fetch_rotated(
        lambda k: ('%s/sports/%s/odds/?apiKey=%s&regions=%s&markets=h2h,spreads,totals&oddsFormat=decimal'
                   % (BASE, a.sport, k, a.regions)))
    if isinstance(d, dict) and d.get('_all_exhausted'):
        print_all_exhausted(d.get('_tried') or [], 'current')
        return
    if isinstance(d, dict) and d.get('_no_key'):
        print('❌ 缺 key（env THE_ODDS_API_KEY 或 api_keys.json 的 the_odds_api_pool）')
        return
    if isinstance(d, dict) and d.get('_http_error'):
        print('❌ HTTP%s | %s' % (d['_http_error'], d['_body'][:200]))
        return
    rows = normalize(d)
    nb = max([len(e.get('bookmakers') or []) for e in d] or [0])
    mk = sorted({k for r in rows for k in r['markets']})
    print('✅ current: %d 场 | 最多 %d 家机构 | markets=%s | 额度剩余 %s'
          % (len(rows), nb, mk, h.get('x-requests-remaining')))
    for r in rows[:6]:
        sp = (r['markets'].get('spreads') or [{}])[0].get('outcomes')
        print('   %-34s 亚盘 %s' % ('%s vs %s' % (r['home'], r['away']), sp))
    tag = a.case or a.sport
    import datetime as dt
    t = a.t or dt.datetime.now().strftime('%Y-%m-%d %H:%M')
    p, n = save_snapshot(tag, t, rows, nb, extra={'sport': a.sport, 'markets': mk,
                                                  'quota_remaining': h.get('x-requests-remaining')})
    print('   已落盘 %s（第 %d 个时点）' % (p, n))
    if n < 2:
        print('   ⚠️ 时序需 ≥2 个时点 → 多次运行本命令即可累积（免费计划可行）')


def cmd_history(a):
    a.sport = resolve_sport(a)
    d, h, key, _tried = fetch_rotated(
        lambda k: ('%s/historical/sports/%s/odds?apiKey=%s&regions=eu&markets=h2h,spreads,totals&oddsFormat=decimal&date=%s'
                   % (BASE, a.sport, k, a.date)))
    if isinstance(d, dict) and d.get('_all_exhausted'):
        print_all_exhausted(d.get('_tried') or [], 'history')
        return
    if isinstance(d, dict) and d.get('_http_error'):
        code = d['_http_error']
        body = d['_body']
        if 'HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN' in body:
            print('🔴 历史逐时点需付费计划（免费额度不含 historical）')
            print('   → 免费替代: 多次运行 `current` 自行累积时序（每次 +1 时点）')
        else:
            print('❌ HTTP%s | %s' % (code, body[:200]))
        return
    ts = d.get('timestamp')
    arr = d.get('data') if isinstance(d, dict) else d
    print('✅ history @ %s → %d 场 | prev=%s next=%s | 额度 %s'
          % (ts, len(arr or []), d.get('previous_timestamp'), d.get('next_timestamp'),
             h.get('x-requests-remaining')))
    for r in normalize(arr)[:6]:
        print('   %s vs %s' % (r['home'], r['away']))


def cmd_range(a):
    a.sport = resolve_sport(a)
    import datetime as dt
    t0 = dt.datetime.strptime(a.f, '%Y-%m-%dT%H:%M:%SZ')
    t1 = dt.datetime.strptime(a.t, '%Y-%m-%dT%H:%M:%SZ')
    n = 0
    cur = t0
    while cur <= t1:
        d, h, _k, _tr = fetch_rotated(
            lambda k, _c=cur: ('%s/historical/sports/%s/odds?apiKey=%s&regions=eu&markets=h2h,spreads,totals&oddsFormat=decimal&date=%s'
                               % (BASE, a.sport, k, _c.strftime('%Y-%m-%dT%H:%M:%SZ'))), quiet=True)
        if isinstance(d, dict) and d.get('_all_exhausted'):
            # 🔴2026-10-31: 原实现没判 → 每时点都失败但仍继续循环（静默刷屏·浪费）
            print_all_exhausted(d.get('_tried') or [], 'range（已中断遍历·第 %d 个时点）' % (n + 1))
            return
        if isinstance(d, dict) and d.get('_http_error'):
            if 'HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN' in d.get('_body', ''):
                print('🔴 range 需付费计划（historical）→ 请改用多次 `current` 累积')
            else:
                print('❌ HTTP%s' % d['_http_error'])
            return
        n += 1
        print('   %s → %d 场（额度 %s）' % (cur.strftime('%m-%d %H:%M'), len(d.get('data') or []),
                                        h.get('x-requests-remaining')))
        cur += dt.timedelta(minutes=a.step)
    print('✅ 遍历 %d 个时点完成' % n)


def cmd_books(a):
    # 🔴2026-10-30：books 可能需回调 cmd_current → 补齐其所需属性（regions/t）
    for _k, _v in (('regions', 'eu,uk'), ('t', None)):
        if not hasattr(a, _k):
            setattr(a, _k, _v)
    """把 the-odds-api 快照的某场 h2h 转成 books.json（喂 market_consensus / P0-1 跨机构分歧）"""
    a.sport = resolve_sport(a)
    tag = a.case or a.sport
    p = os.path.join(SNAP_DIR, '%s.json' % tag)
    if not os.path.exists(p):
        # 🔴2026-10-30 修 P0：无快照时**自动拉取**（原直接 return → 上层只能记三态）
        print('   ⚠️ 无快照 %s → **自动拉取 current**（--league %s）' % (os.path.basename(p), a.league or a.sport))
        try:
            cmd_current(a)
        except SystemExit:
            pass
        except Exception as _ex:
            print('   ⚠️ 自动拉取失败: %s' % str(_ex)[:80])
        if not os.path.exists(p):
            print('   ❌ 自动拉取后仍无快照 → 三态（须在 raw 写明本次已尝试自动拉取）')
            return
    d = json.load(io.open(p, encoding='utf-8'))
    snaps = d.get('snapshots') or []
    evs = (snaps[-1].get('events') or []) if snaps else []
    books, found = [], None
    for e in evs:
        if a.home and a.home.lower() not in (e.get('home') or '').lower():
            continue
        if a.away and a.away.lower() not in (e.get('away') or '').lower():
            continue
        found = e
        for entry in (e.get('markets', {}).get('h2h') or []):
            oc = {o['name']: o['price'] for o in entry.get('outcomes', [])}
            books.append({'bookmaker': entry.get('book'), 'h': oc.get(e['home']),
                          'd': oc.get('Draw'), 'a': oc.get(e['away'])})
        break
    if not found:
        # 🔴2026-10-30 修 P0（用户最后通牒后实测抓出）：books 依赖**上次 current 的快照** →
        #   快照是别的联赛/别的日 → 恒「未找到」→ 上层只会记「三态」= 又一次静默遗漏。
        #   修法：快照不含本场时 **自动先跑一次 current 刷新**，再重试匹配；
        #         仍找不到才报三态，并区分「免费档未覆盖」vs「队名不匹配」。
        print('   ⚠️ 快照未含本场 → **自动刷新 current**（--league %s）后重试' % (a.league or a.sport))
        try:
            rc0 = cmd_current(a)      # 复用 current 逻辑刷新 %s.json
        except SystemExit:
            pass
        except Exception as _ex:
            print('   ⚠️ 自动刷新失败: %s' % str(_ex)[:80])
        try:
            d = json.load(io.open(p, encoding='utf-8'))
            snaps = d.get('snapshots') or []
            evs = (snaps[-1].get('events') or []) if snaps else []
            for e in evs:
                if a.home and a.home.lower() not in (e.get('home') or '').lower():
                    continue
                if a.away and a.away.lower() not in (e.get('away') or '').lower():
                    continue
                found = e
                books = []
                for entry in (e.get('markets', {}).get('h2h') or []):
                    oc = {o['name']: o['price'] for o in entry.get('outcomes', [])}
                    books.append({'bookmaker': entry.get('book'), 'h': oc.get(e['home']),
                                  'd': oc.get('Draw'), 'a': oc.get(e['away'])})
                break
        except Exception:
            pass
    if not found:
        # 🔴P41（2026-10-30 全流程验证抓出）: 拉取失败时**旧文件会残留** →
        #   下场分析时 calc_all 读到上一场的 books（场次错配防护虽拦得住·但噪音大且易误判）
        #   → 失败即**删除旧文件**（宁可无数据三态·不留污染）
        _old_out = a.out or os.path.join(HERE, 'fundflow_books.json')
        try:
            if os.path.exists(_old_out):
                os.remove(_old_out)
                print('   🔴P41 已清理旧 books 文件（防跨场污染）: %s' % os.path.basename(_old_out))
        except Exception:
            pass
        print('❌ 自动刷新后仍未找到 %s vs %s（共 %d 场）' % (a.home, a.away, len(evs)))
        print('   → current 只含 **pending（未开赛）** 场次；本场可能已开赛/已结束'
              '（换 `--event` 或直接读该场历史快照）· 非配额问题')
        print('   🔴 定性: ①若队名差异大 → 用 the-odds-api 官方队名重试 '
              '②否则为「免费档未覆盖」（非漏执行）→ 三态须写明本次已自动刷新+仍缺')
    out = a.out or os.path.join(HERE, 'fundflow_books.json')
    # 🔴2026-09-27 审计P0: 写包装 dict（含 fixture/home/away）→ market_consensus.match_check 可做场次错配校验
    obj = {'status': 'ok', 'fixture': found.get('id'), 'home': found.get('home'), 'away': found.get('away'),
           'n_books': len(books), 'key_source': 'the-odds-api', 'books': books}
    io.open(out, 'w', encoding='utf-8').write(json.dumps(obj, ensure_ascii=False, indent=1))
    print('✅ %s vs %s → %d 家机构 → %s' % (found.get('home'), found.get('away'), len(books), out))
    print('   下一步: python data/tmp/market_consensus.py --books "%s"' % out)


def cmd_quota(a):
    """🔴2026-10-31: 显示 **key 池** 状态（不主动探测·省额度·--probe 才逐个实探）"""
    pool = load_keys()
    if not pool:
        print('❌ 缺 key（env THE_ODDS_API_KEY 或 api_keys.json 的 the_odds_api_pool）')
        return
    probe = bool(getattr(a, 'probe', False))
    print('🔑 key 池共 %d 个（顺序: 用完才换 · %d 天后自动恢复）' % (len(pool), RESET_DAYS))
    for idx, k, st in pool:
        state = st.get('state') or 'ready'
        icon = {'exhausted': '🔴', 'invalid': '❌'}.get(state, '🟢')
        line = '  %s K%d %-12s 剩余=%-6s' % (icon, idx, mask_key(k), st.get('remaining', '-'))
        if state == 'exhausted':
            line += ' 用尽于 %s' % (st.get('exhausted_at') or '?')
        elif state == 'invalid':
            line += ' **key 无效·请检查 api_keys.json 是否输错**（不会自动恢复）'

        if st.get('note'):
            line += ' (%s)' % st['note']
        print(line)
        # 🔴2026-11-07 修（K2 实抓「假耗尽」）：
        #   原 `and state != 'exhausted'` → **已标记 exhausted 的 key 永远不实探**
        #   → 就算额度已恢复（实测 K2 remaining=1 仍能出数）也永远发现不了 → 白锁。
        #   且 `/v4/sports/` 是**免费端点（不消耗额度）** → probe 可随时跑，不必吝啬。
        if probe:
            d, h = fetch('%s/sports/?apiKey=%s' % (BASE, k))
            if isinstance(d, dict) and d.get('_http_error'):
                print('      实探 → ❌ HTTP%s | %s' % (d['_http_error'], d.get('_body', '')[:110]))
            else:
                left = h.get('x-requests-remaining')
                print('      实探 → ✅ 剩余 %s | 已用 %s'
                      % (left, h.get('x-requests-used')))
                note_remaining(k, left)
                # 🔴 探到仍有额度 → 自动清除 exhausted 标记（治「假耗尽」）
                if state == 'exhausted':
                    try:
                        if left is not None and float(left) > 0:
                            _st = _key_state()
                            if k in _st:
                                _st[k]['state'] = 'ready'
                                _st[k]['note'] = '--probe 实探仍有 %s 次 → 自动恢复' % left
                                _state_save(_st)
                                print('      ➡️ **已自动恢复为可用**（原标 exhausted · 实探剩余 %s）' % left)
                    except Exception:
                        pass
    if not probe:
        print('  💡 加 --probe 逐个实探最新额度（`/v4/sports/` 为**免费端点·不消耗额度**）')


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd')
    p1 = sub.add_parser('current'); p1.add_argument('--sport', default=DEFAULT_SPORT)
    p1.add_argument('--league')   # 🔴2026-10-27: 中文联赛名 → sport key（防默认欧国联误用）
    p1.add_argument('--case'); p1.add_argument('--regions', default='eu,uk'); p1.add_argument('--t')
    p2 = sub.add_parser('history'); p2.add_argument('--sport', default=DEFAULT_SPORT)
    p2.add_argument('--league')
    p2.add_argument('--date', required=True)
    p3 = sub.add_parser('range'); p3.add_argument('--sport', default=DEFAULT_SPORT)
    p3.add_argument('--league')
    p3.add_argument('--from', dest='f', required=True); p3.add_argument('--to', dest='t', required=True)
    p3.add_argument('--step', type=int, default=60)
    p4 = sub.add_parser('books'); p4.add_argument('--sport', default=DEFAULT_SPORT)
    p4.add_argument('--league')
    p4.add_argument('--case'); p4.add_argument('--home'); p4.add_argument('--away'); p4.add_argument('--out')
    _pq = sub.add_parser('quota')
    _pq.add_argument('--probe', action='store_true',
                     help='逐个 key 实探最新额度（默认只读状态文件·不耗请求）')
    a = ap.parse_args()
    {'current': cmd_current, 'history': cmd_history, 'range': cmd_range,
     'books': cmd_books, 'quota': cmd_quota}.get(
        a.cmd, lambda x: ap.print_help())(a)


if __name__ == '__main__':
    main()
