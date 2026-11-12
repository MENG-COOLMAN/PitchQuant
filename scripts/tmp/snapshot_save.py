# -*- coding: utf-8 -*-
"""赔率快照保存（T-0 早盘时点·🔴支持多时点累积·供完整分析做赔率变动对比）

用法:
  python data/tmp/snapshot_save.py --leagues 欧国联 --bj 22:00-06:00 --tag nl   # 抓取并存一份快照
  python data/tmp/snapshot_save.py --leagues 英超,西甲,欧冠 --bj 22:00-06:00 --tag eu5   # 🔴五大联赛+欧战
  python data/tmp/snapshot_save.py --list                                        # 列出全部快照
  python data/tmp/snapshot_save.py --diff "Belgium vs France"                    # 🔴该场跨快照赔率时序(变动)
落盘:
  data/tmp/snapshots/<tag>_<YYYYMMDD_HHMMSS>.json   原始全市场（脚本消费）
  data/tmp/snapshots/<tag>_<YYYYMMDD_HHMMSS>.md     人读盘口表（分析引用）

🔴 数据隔离（2026-09-28 固化）:
  - 文件名**秒级时间戳** → 多次调取**各自成文件·只增不改·绝不覆盖**（可无限累积成时序）
  - 分析时**按 event_id / 队名精确匹配本场**·🔴**禁跨场复用**（防场次错配污染）
  - 同场多份 → 按 saved_at 排序 · 最早=早盘(T-0) · 最新=临场(T-n)
🔴 定位: 预分析与完整分析之间的「时间锚」。完整分析(Step0-11) 读入 →
  与竞彩 txt(赛前)/终赔 对比 → 支撑 V1 双源变动 / V2 诱阻盘 / V6 盘口联动 / P1-3 Steam / P2-1 CLV。
"""
import argparse, datetime as dt, glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_retry import fetch_json

KEY = '<REDACTED_HEX>'
LG = {
    # 🔴2026-09-29 接口-1 修复（《双通道问题汇总》P1-1/接口-1）:
    #   并入 五大联赛 + 欧联 + 欧冠（slug 与 prestep_fetch.LG 同源）→
    #   ⑤.5 双通道的机构通道不再只在欧国联可用 · 主战场(五大联赛+欧战)同样可拉快照。
    '英超': ['england-premier-league'],
    '西甲': ['spain-laliga'],
    '德甲': ['germany-bundesliga'],
    '意甲': ['italy-serie-a'],
    '法甲': ['france-ligue-1'],
    '欧联': ['international-clubs-uefa-europa-league'],
    '欧冠': ['international-clubs-uefa-champions-league'],
    '英联赛杯': ['england-efl-cup'],   # 🔴2026-10-28 实测确认（卡拉宝杯/EFL Cup）
    '亚冠精英': ['international-clubs-afc-champions-league-elite-east-region'],
    '芬超': ['finland-veikkausliiga-championship-round'],
    '瑞典超': ['sweden-allsvenskan'],
    '亚冠二级': ['international-clubs-afc-champions-league-two-group-e'],   # 🔴2026-10-29 实测（申花 vs 町田 20:15·Odds-API 标 Group E）   # 🔴2026-10-29 /leagues 实测确认
    '欧国联': ['international-uefa-nations-league-league-%s-gr-%d' % (g, i) for g in 'abcd' for i in range(1, 5)],
}
SNAP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'snapshots')
BJ_OFFSET = 8


def bj_window(lo, hi):
    """「今晚」窗口（北京时）。

    🔴2026-10-25 修（与 prestep_fetch.window_from_bj 统一口径·实测缺陷）:
      原实现 `if now.hour < 6: d0 -= 1天`（凌晨跑默认"归前一晚"）→ 在 05:03 指定
      `--bj 19:00-04:00`（=今日 19:00 → 次日 04:00）时被错判成**昨天** 19:00 → 今天 04:00
      → 窗口内 0 场 → 快照不落盘；而 prestep_fetch 同参数正确拉到 21 场（两脚本口径分裂）。
      新口径: 起始日=**今天**；`hi <= lo` → 结束顺延次日（跨夜）；
              仅当**整个窗口已过去**（now > 结束时刻）才回退一天（如次日 07:00 跑"昨晚 19-04"）。
    """
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(hours=BJ_OFFSET)
    d0 = now.replace(hour=int(lo[:2]), minute=int(lo[3:]), second=0, microsecond=0)
    span_min = ((int(hi[:2]) * 60 + int(hi[3:])) - (int(lo[:2]) * 60 + int(lo[3:]))) % 1440
    if span_min == 0:
        span_min = 480                      # 同刻起止 → 兜底 8h（保持原行为）
    d1 = d0 + dt.timedelta(minutes=span_min)
    if now > d1:                            # 窗口已整体过去 → 回退一天
        d0 -= dt.timedelta(days=1)
        d1 -= dt.timedelta(days=1)
    return d0.strftime('%Y-%m-%d %H:%M'), d1.strftime('%Y-%m-%d %H:%M')


def _extract(raw):
    """从 1xbet 原始市场提取关键盘口"""
    out = dict(ml='-', ah='-', o25='-', o35='-', btts='-', cs='-', upd='-')
    if not isinstance(raw, dict):
        return out
    bk = (raw.get('bookmakers') or {}).get('1xbet') or []

    def find(name):
        for m in bk:
            if (m.get('name') or '').lower() == name.lower():
                return m
        return None

    m = find('ML')
    if m and m.get('odds'):
        o = m['odds'][0]
        out['ml'] = '%s/%s/%s' % (o.get('home'), o.get('draw'), o.get('away'))
        out['upd'] = (m.get('updatedAt') or '')[:16].replace('T', ' ')
    s = find('Spread')
    if s and s.get('odds'):
        # 🔴2026-09-29 case218/220 修复: 原固定取「hdp≈−1.0」档 → 受让场/深盘场**取错档**
        #   （如苏格兰受让1球却读「让-1 主10.0」·西班牙让2球却读「让-1 主1.27」）
        #   → 改为取【均衡线档】= 主客赔率最接近的档（去水后水位≈1.85-1.95 对等）
        def _gap(x):
            try:
                return abs(float(x.get('home') or 99) - float(x.get('away') or 99))
            except Exception:
                return 99.0
        best = min(s['odds'], key=_gap)
        # 🔴2026-10-09（case229 教训·克制修复）: 若「最接近档」仍严重偏斜（|主−客|>0.9）→ 说明**无接近均衡的档**
        #   （实测朗斯场缺 −0.75~+0.75 区间·最接近档 −1 为 3.64/1.25·差 2.39）→ 必须**标注**，
        #   否则下游会把深档当「让球盘」读（case229 由此误得 handi=-1.0 → 候选池错成主胜谱系）。
        #   ※ 标注为**尾部附加文字**·`_ah_hdp` 用正则取值·不受影响。
        _warn = ' ⚠️均衡线缺失' if _gap(best) > 0.9 else ''
        out['ah'] = '让%+.2f 主%s/客%s%s' % (best.get('hdp', 0), best.get('home'),
                                           best.get('away'), _warn)
    tt = find('Totals')
    if tt and tt.get('odds'):
        for x in tt['odds']:
            if abs((x.get('hdp') or 0) - 2.5) < 0.01:
                out['o25'] = 'O%s/U%s' % (x.get('over'), x.get('under'))
            if abs((x.get('hdp') or 0) - 3.5) < 0.01:
                out['o35'] = 'O%s/U%s' % (x.get('over'), x.get('under'))
    b = find('Both Teams To Score')
    if b and b.get('odds'):
        out['btts'] = '是%s/否%s' % (b['odds'][0].get('yes'), b['odds'][0].get('no'))
    c = find('Correct Score')
    if c and c.get('odds'):
        lo = min(c['odds'], key=lambda x: float(x.get('odds') or 99))
        out['cs'] = '%s=%s' % (lo.get('label'), lo.get('odds'))
    return out


def _load_all():
    out = []
    for f in sorted(glob.glob(os.path.join(SNAP_DIR, '*.json'))):
        try:
            d = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        if 'games' not in d:
            continue
        # 🔴2026-09-29 防污染（实测: 多机构补全快照被 find_for 混入 1xbet 时序链 → ml='-' 破坏 delta_for）
        #   补全快照（the-odds-api 多机构）不入 1xbet 时序链·仅供存档/人工参考
        if d.get('snapshot_type') == 'multi_agency':
            continue
        d['_file'] = os.path.basename(f)
        out.append(d)
    out.sort(key=lambda x: x.get('saved_at', ''))
    return out


def _match(g, key):
    k = key.lower().replace('vs', ' ').split()
    h = (g.get('home') or '').lower()
    a = (g.get('away') or '').lower()
    return all(w in h or w in a for w in k) if k else False


# 🔴2026-09-29 修复(P0·数据链断裂): 快照存**英文**队名，而竞彩 txt 是**中文**队名 →
#   原 _match 纯英文子串匹配 → 中文输入恒不命中 → calc_all N21 恒报「无本场快照匹配」。
#   实测: 09-28 三场(Belgium/France 等 N21 均未命中) → 快照**未真正进入决策链**。
#   修法: 国家队中文→英文表（nl_team_cn_en.json）+ 🔴俱乐部中文→英文表（data_bridge.TEAM_ALIASES）。
_NL_CN2EN = None
_EXTRA_MAP = None
_CLUB_ALIAS = None


def _nl_map():
    """国家队中文名 → 英文（懒加载 data/tmp/nl_team_cn_en.json）"""
    global _NL_CN2EN
    if _NL_CN2EN is None:
        try:
            _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nl_team_cn_en.json')
            _NL_CN2EN = json.load(open(_p, encoding='utf-8')).get('teams', {}) or {}
        except Exception:
            _NL_CN2EN = {}
    return _NL_CN2EN


def _club_map():
    """🔴2026-09-29 接口-2 修复（《双通道问题汇总》接口-2）:
    俱乐部中文名 → 英文（懒加载 data/online_learning/data_bridge.TEAM_ALIASES·191 条）。
    此前 cn2en 只查国家队表 → 五大联赛/欧冠中文队名恒不命中 → 快照匹配失效。"""
    global _CLUB_ALIAS
    if _CLUB_ALIAS is None:
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            '..', 'online_learning'))
            import data_bridge as _db
            _CLUB_ALIAS = getattr(_db, 'TEAM_ALIASES', {}) or {}
        except Exception:
            _CLUB_ALIAS = {}
    return _CLUB_ALIAS


def _first(v):
    """别名表值 → 英文字符串（🔴2026-10-09 根治: 取**最长**候选）
    原取 v[0] → 「多特蒙德」返回 'BVB'(缩写·快照里是 'Borussia Dortmund') → 恒不命中"""
    if isinstance(v, (list, tuple)) and v:
        cands = [x for x in v if isinstance(x, str) and x.strip()]
        return max(cands, key=len) if cands else None
    return v if isinstance(v, str) else None


def _extra_map():
    """🔴2026-10-09 根治: 补充别名表（data/tmp/cn2en_extra.json）
    补 TEAM_ALIASES / nl_team_cn_en 未覆盖者（如「云达不来梅」）"""
    global _EXTRA_MAP
    if _EXTRA_MAP is None:
        try:
            _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cn2en_extra.json')
            _j = json.load(open(_p, encoding='utf-8'))
            _EXTRA_MAP = {k: v for k, v in _j.items() if not k.startswith('_')}
        except Exception:
            _EXTRA_MAP = {}
    return _EXTRA_MAP


def _shrink_fallback(name, table, take):
    """🔴简称回退（2026-09-29 case219 修复）: 竞彩常用简称（如「斯洛文尼」漏「亚」）恒不命中全称表
    → 若 name 是某键的**唯一**子串，回退命中；不唯一则放弃（防「刚果」等多候选误配）"""
    if not name:
        return None
    cands = [k for k in table if k and k != name and name in k]
    if len(cands) == 1:
        return take(table[cands[0]])
    return None


def _ensure_tmp_path():
    """确保 data/tmp 在 sys.path（cn2en_online 同目录·防 ImportError）"""
    _d = os.path.dirname(os.path.abspath(__file__))
    if _d not in sys.path:
        sys.path.insert(0, _d)


def cn2en_list(name):
    """中文队名 → **全部**英文候选（🔴2026-10-09 根治·供跨源逐个匹配）
    优先级: 补充表 → 俱乐部精确 → 国家队精确 → 子串匹配（**长键优先**·防短名吃掉长名）
    🔴「西班牙人→Spain」根因: 原实现先查国家队表且用 `cn in name` → 「西班牙人」⊃「西班牙」→ 误配"""
    if not name:
        return []
    out = []

    def _push(v):
        if isinstance(v, (list, tuple)):
            out.extend([x for x in v if isinstance(x, str) and x.strip()])
        elif isinstance(v, str) and v.strip():
            out.append(v)
    tables = [_extra_map(), _club_map(), _nl_map()]
    for tbl in tables:                      # ① 精确（补充表 → 俱乐部 → 国家队）
        if name in tbl:
            _push(tbl[name])
    if not out:                             # ② 子串（长键优先·同表内）
        for tbl in tables:
            for k in sorted([k for k in tbl if k and k != name and k in name], key=len, reverse=True):
                _push(tbl[k])
    if not out:                             # ③ 简称回退（唯一子串）
        for tbl in tables:
            hit = _shrink_fallback(name, tbl, lambda v: v)
            if hit:
                _push(hit)
                break
    if not out:
        # 🔴🔴2026-10-31 用户指令·**联网兜底**（严禁本地查不到就 missing）:
        #   「如果能正常获取到英文名映射就继续，如果不能则上网查询，然后继续，
        #     严禁存在查不到简称就 missing 的情况」
        #   实现: cn2en_online（中文维基 langlinks·批量 titles → 后缀批 → 搜索兜底）
        #   命中即**回写 cn2en_extra**（自我进化）→ 下次本地直接命中·不再联网
        #   负缓存 7 天（防每场重复联网）·总预算 12s·超时则如实返回空
        try:
            _ensure_tmp_path()          # 🔴确保 data/tmp 在 sys.path（否则 ImportError 静默吞掉）
            import cn2en_online as _onl
            for _e in ((_onl.lookup([name]) or {}).get(name) or []):
                _push(_e)
        except Exception:
            pass
    seen, res = set(), []
    for x in out:
        if x and x not in seen:
            seen.add(x); res.append(x)
    return res


def cn2en(name):
    """中文队名 → 单个英文名（向后兼容·取 cn2en_list 首个）
    🔴2026-10-09 根治: 原实现「先国家队表 + 子串匹配」→ 俱乐部被国家队名吃掉（西班牙人→Spain）"""
    lst = cn2en_list(name)
    return lst[0] if lst else (name or '')
    c = _club_map()
    if name in c:
        return _first(c[name]) or name
    for cn, en in c.items():
        if cn and cn in name:
            return _first(en) or name
    hit = _shrink_fallback(name, c, lambda v: _first(v))
    if hit:
        return hit
    return name


def find_for(home, away, limit=None):
    """🔴按队名匹配本场快照（供 calc_all / 完整分析消费·数据链闭环）
    返回 {count, first, last, points}；count=0 表示无早盘时点(T-0 缺失)
    🔴2026-09-29: 入参支持**中文**队名（逐名转英文后匹配·修跨语言不命中 P0）
    🔴联赛无关: 五大联赛/欧冠/欧国联 数据到位即自动接入"""
    ds = _load_all()
    hits = []
    # 🔴2026-10-09 根治: 多候选逐个试（cn2en_list → 任一候选命中即算）
    _hl = cn2en_list(home) or [home]
    _al = cn2en_list(away) or [away]
    _pairs = [('%s %s' % (h, a)) for h in _hl for a in _al]
    for d in ds:
        for g in d.get('games', []):
            if any(_match(g, _p) for _p in _pairs):
                _ex = _extract(g.get('raw_1xbet'))
                # 🔴2026-10-26 修 #2: 结构化快照（如 prestep_ps4_*.json·无 raw_1xbet）
                #   原实现直接 _extract(None) → ml/ah 全 '-' → delta_for 拿不到 → 双通道/时序恒三态
                if str(_ex.get('ml') or '-') == '-' and isinstance(g.get('ml'), dict):
                    _f = g['ml'].get('fair') or []
                    if len(_f) >= 3:
                        _ex['ml'] = '/'.join('%.3f' % float(x) for x in _f[:3])
                    _ah = g.get('ah') or {}
                    if _ah.get('handi') is not None:
                        _ex['ah'] = '让%+.2f 主%.3f/客%.3f' % (
                            float(_ah['handi']), float(_ah.get('home_water') or 0),
                            float(_ah.get('away_water') or 0))
                    _tt = g.get('totals') or {}
                    if _tt.get('over') is not None:
                        _ex['o25'] = '%.3f' % float(_tt['over'])
                        if _tt.get('under') is not None:
                            _ex['u25'] = '%.3f' % float(_tt['under'])
                    _ex['_src'] = 'structured'
                # 🔴2026-10-27 P0 修复（时序链断裂·实抓于意甲三场 PreStep）:
                #   旧快照由 `prestep_fetch.py --save` 写入 → games 只有 `kickoff_utc`、**无 `kickoff_bj`**；
                #   而下方「跨场防护」按 `kickoff_bj` 聚类（`hits = [h for h if kickoff_bj == max]`）
                #   → 缺字段者被全部剔除 → **三时点退化为单时点**（P12 双通道 / N21 全跨度序列 /
                #   P5 波胆纵向 全部退回三态，且无任何告警）。
                #   实测: 意甲 萨索洛/罗马/都灵 三份快照(06:06 / 08:33 / 18:06) → 修复前 count=1。
                #   修法: kickoff_bj 缺失时用 `kickoff_utc + 8h` 兜底为北京时间（保留跨场防护强度）。
                _kb = g.get('kickoff_bj')
                if not _kb and g.get('kickoff_utc'):
                    try:
                        _dtk = dt.datetime.fromisoformat(str(g['kickoff_utc']).replace('Z', '+00:00'))
                        if _dtk.tzinfo is not None:
                            _dtk = _dtk.astimezone(dt.timezone.utc).replace(tzinfo=None)
                        _kb = (_dtk + dt.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M')
                    except Exception:
                        _kb = None
                hits.append({'saved_at': d.get('saved_at'), 'file': d['_file'],
                             'kickoff_bj': _kb, 'event_id': g.get('event_id'),
                             'extract': _ex})
    # 🔴2026-10-24 P0 跨场防护（用户质疑「与之前的能否形成数据链」实抓）:
    #   根因: 原实现纯按队名匹配·无日期约束 → 10-24「马竞vs拉科」串到 10-10 同名场次
    #         （eventId 72478606 vs 实际 72478650·相隔14天）→ ML 变动 -70.6%/+55.4%/+411.6% 全假
    #   修法: 按 kickoff_bj 聚类·只保留**最晚一场**（要分析的就是最近这场）·防跨日期串场
        _kos = [h.get('kickoff_bj') for h in hits if h.get('kickoff_bj')]
        if _kos:
            _target = max(_kos)
            _n_before = len(hits)
            hits = [h for h in hits if h.get('kickoff_bj') == _target]
            if len(hits) != _n_before:
                pass  # 已剔除跨日期同名场次（保留最晚 kickoff 组）
    if limit:
        hits = hits[-limit:]
    return {'count': len(hits), 'first': hits[0] if hits else None,
            'last': hits[-1] if hits else None, 'points': hits}


def _imp(o):
    """三个赔率 → 去水隐含概率(%)"""
    try:
        a, b, c = [1.0 / float(x) for x in o]
    except Exception:
        return None
    s = a + b + c
    return (100 * a / s, 100 * b / s, 100 * c / s)


def _ah_hdp(s):
    """亚盘串 → (盘口, 主水, 客水)｜🔴2026-10-26 多格式兼容

    支持:
      ① 让-1.5 主1.950/客2.000        （原格式）
      ② -1.50 主1.950/客2.000         （无「让」字·实盘快照格式·此前恒 None → 双通道三态）
      ③ 主让1.5 水1.95/2.00 · 客让0.5 水1.9/2.0
      ④ -1.5@1.95/2.0 · -1.5 1.95/2.0 （宽松）
    全角负号/破折号统一归一。
    """
    t = str(s or '').replace('−', '-').replace('–', '-').replace('－', '-').replace('—', '-')
    if not t or t == '-':
        return None
    pats = [
        r'让\s*([+-]?\d+\.?\d*)\s*主\s*([\d.]+)\s*/\s*客\s*([\d.]+)',   # ①
        r'([+-]\d+\.?\d*)\s*主\s*([\d.]+)\s*/\s*客\s*([\d.]+)',           # ②
        r'主让\s*(\d+\.?\d*)[^\d]{0,4}([\d.]+)\s*/\s*([\d.]+)',            # ③主让
        r'客让\s*(\d+\.?\d*)[^\d]{0,4}([\d.]+)\s*/\s*([\d.]+)',            # ③客让
        r'([+-]?\d+\.?\d*)\s*[@水]?\s*([\d.]+)\s*/\s*([\d.]+)',            # ④
    ]
    m = re.search(pats[0], t) or re.search(pats[1], t)
    if m:
        return float(m.group(1)), float(m.group(2)), float(m.group(3))
    m = re.search(pats[2], t)
    if m:
        return -float(m.group(1)), float(m.group(2)), float(m.group(3))
    m = re.search(pats[3], t)
    if m:
        return float(m.group(1)), float(m.group(2)), float(m.group(3))
    m = re.search(pats[4], t)
    if m:
        try:
            hdp, hw, aw = float(m.group(1)), float(m.group(2)), float(m.group(3))
            if 1.0 < hw < 4.0 and 1.0 < aw < 4.0 and abs(hdp) <= 5:
                return hdp, hw, aw
        except ValueError:
            pass
    return None


def delta_for(home, away, end_ml=None, end_ah=None, end_o25=None, end_label=None):
    """🔴跨快照算「变动」→ 供 V1/V2/V6/P1-3 判定消费（非仅展示）
    🔴2026-09-29 增强（用户指令「把 prestep 快照 与 正式执行时的赔率 串联成完整欧亚盘时间序列」）:
       end_ml/end_ah/end_o25 = 「正式执行时点」（calc_all 的 --eu/--handi/--o25）→ 作为序列**末点**
       未给 → 退回「快照末点」（原行为·兼容）
    返回 {count, ml_pp, ml_chg_pct, ah, o25_imp, signal[], span, series[], end_label}"""
    from snapshot_save import find_for as _ff
    r = _ff(home, away)
    out = {'count': r['count'], 'ml_pp': None, 'ml_chg_pct': None, 'ah': None, 'o25_imp': None,
           'signal': [], 'span': None, 'series': [], 'end_label': None}
    # 🔴2026-09-29 P2-4 修复（《全量审计报告·V3.5.76 复检》）:
    #   ① 初始 dict 补 'ml_chg_pct': None —— 原实现无此键，而 docstring 声明含它 →
    #      消费端 calc_all `if _dl['ml_chg_pct']` 在无快照时抛 KeyError（被外层 except 吞成「异常」）
    #   ② 无 prestep 快照但给了「正式执行时点」→ 仍输出该单点序列（count=1），
    #      原实现直接 return → 有 --eu 也报「共 0 时点」（丢掉正式执行时点）
    if r['count'] < 1:
        if end_ml:
            out['end_label'] = end_label or '正式执行'
            out['series'] = [{'at': out['end_label'], 'ml': end_ml, 'ah': end_ah or '-',
                              'o25': end_o25 or '-', 'src': '正式分析(--eu/--handi/--o25)'}]
            out['count'] = 1
            out['span'] = '%s（无 prestep 快照·仅正式执行时点）' % out['end_label']
        return out
    fe = r['first']['extract']
    # 🔴序列（完整时点链：全部 prestep 快照）
    out['series'] = [{'at': p['saved_at'], 'ml': p['extract']['ml'], 'ah': p['extract']['ah'],
                      'o25': p['extract']['o25'], 'src': p['file']} for p in r['points']]
    # 🔴末点: 优先「正式执行时点」·否则取快照末点
    if end_ml:
        le = {'ml': end_ml, 'ah': end_ah or '-', 'o25': end_o25 or '-'}
        _ls = end_label or '正式执行'
        out['end_label'] = _ls
        out['series'].append({'at': _ls, 'ml': le['ml'], 'ah': le['ah'], 'o25': le['o25'],
                              'src': '正式分析(--eu/--handi/--o25)'})
    else:
        if r['count'] < 2:
            return out
        le = r['last']['extract']
        _ls = r['last']['saved_at']
    out['span'] = '%s → %s' % (r['first']['saved_at'], _ls)
    out['count'] = len(out['series'])
    # ── ML 去水隐含概率变动(pp) ──
    i0, i1 = _imp(fe['ml'].split('/')), _imp(le['ml'].split('/'))
    if i0 and i1:
        d = [round(i1[k] - i0[k], 1) for k in range(3)]
        out['ml_pp'] = d
        # 🔴口径对齐 AGENTS D1/D2: **赔率变动%**（升赔≥2T累计>3%）·非隐含pp（2026-09-28 修正）
        try:
            _o0 = [float(x) for x in fe['ml'].split('/')]
            _o1 = [float(x) for x in le['ml'].split('/')]
            _ch = [round(100 * (_o1[k] - _o0[k]) / _o0[k], 1) for k in range(3)]
            out['ml_chg_pct'] = _ch
            if _ch[0] >= 3.0:
                out['signal'].append('🔴D1 背离嫌疑: 主胜赔率 %+.1f%%（早盘→最新·阈值+3%%）→ 降档/不排除' % _ch[0])
            elif _ch[0] <= -3.0:
                out['signal'].append('🟢主胜降赔 %+.1f%%（资金流入·主方向升权线索）' % _ch[0])
            if _ch[2] <= -3.0:
                out['signal'].append('🔴客胜降赔 %+.1f%%（客队被看好·V1 双源变动）' % _ch[2])
            elif _ch[2] >= 3.0:
                out['signal'].append('🟡客胜升赔 %+.1f%%（客队被看淡·修正53 S2 参考）' % _ch[2])
            if abs(_ch[1]) >= 3.0:
                out['signal'].append('🟡平局赔率 %+.1f%%（平赔异动·修正53 组A 参考）' % _ch[1])
        except Exception:
            pass
        out['ml_pp'] = d
    # ── 亚盘盘口/水位变动 → V2 诱阻 / V6 联动 ──
    a0, a1 = _ah_hdp(fe['ah']), _ah_hdp(le['ah'])
    if a0 and a1:
        out['ah'] = {'hdp': '%.2f → %.2f' % (a0[0], a1[0]), 'hw': '%.3f → %.3f' % (a0[1], a1[1])}
        if a1[0] != a0[0]:
            out['signal'].append('🔴盘口移动: 让%.2f → 让%.2f（%s）'
                                 % (a0[0], a1[0], '加深=阻/诱上风险' if a1[0] < a0[0] else '退盘=诱阻关注'))
        if abs(a1[1] - a0[1]) >= 0.15:
            out['signal'].append('🟡主水变动 %.3f → %.3f（水位剪刀差·V2 四步第②步）' % (a0[1], a1[1]))
    # ── O2.5 隐含变动 → Step6 大球方向 ──
    try:
        o0 = 1.0 / float(fe['o25'].split('/')[0].lstrip('O'))
        o1 = 1.0 / float(le['o25'].split('/')[0].lstrip('O'))
        out['o25_imp'] = round(100 * (o1 - o0), 1)
        if abs(out['o25_imp']) >= 3.0:
            out['signal'].append('%s大球隐含 %+.1fpp（Step6 量级参考）'
                                 % ('🟢' if out['o25_imp'] > 0 else '🔵', out['o25_imp']))
    except Exception:
        pass
    return out


def dual_channel(jc_1x2=None, jc_handi=None, ah_from=None, ah_to=None, window_min=None):
    """🔴双通道四象限判定（V3.5.76·2026-09-29 用户方案《竞彩×欧亚盘双通道动态判定机制》）
    公众通道 = 竞彩逐T（jc_1x2=[(t,(H,D,A)),...]·抽水 12.8%·散户情绪代理）
    机构通道 = 欧亚盘时序（ah_from/ah_to="让±X 主Y/客Z" 早盘→临场·抽水 6.9%·机构意图）

    window_min（🔴2026-09-29 P1-3 修复: 此前文档称已支持但函数无此参数 → 文档-代码不一致）:
      距开赛分钟数 → 窗口分级，写入返回的 window 字段
        >48h(2880min) → 「⚠️烟雾弹 → 机构通道降级弱参考」（早期盘口失真）
        ≤90min        → 「✅临场 → 信息密度最高」
        90-2880       → 「常规窗口」｜None → 「未知·不降级」

    🔴铁律: 只调置信度 ≤±1 档·永不反转 L2 硬核方向·未回测项标「⏳待回测·仅参考」
    🔴follow 口径唯一性（P2-2）: 本函数 C2.follow 为**唯一 follow 判定口径**；
       fundflow_analyzer.rlm_detect(ah_from, ah_to) 转为其**佐证/独立观测**（不同阈值·不互替）
    返回 {C1,C2,C3,quadrant(Q号,名,动作,依据),window,notes[]}｜无竞彩 → C1=None 三态
    """
    res = {'C1': None, 'C2': None, 'C3': None, 'quadrant': None, 'window': None, 'notes': []}
    # 🔴P1-3: 窗口分级（>48h 烟雾弹降级 · ≤90min 临场最强）
    if window_min is not None:
        try:
            _w = float(window_min)
            if _w > 2880:
                res['window'] = {'min': _w, 'grade': '⚠️早盘>48h · 烟雾弹 → 机构通道降级为弱参考'}
            elif _w <= 90:
                res['window'] = {'min': _w, 'grade': '✅临场≤90min → 信息密度最高'}
            else:
                res['window'] = {'min': _w, 'grade': '常规窗口（90min-48h）'}
        except Exception:
            res['window'] = None
    if not jc_1x2 or len(jc_1x2) < 2:
        res['notes'].append('⚪双通道: 未传竞彩逐T → 公众通道不可判(三态)')
        return res
    try:
        v0, v1 = jc_1x2[0][1], jc_1x2[-1][1]
        if len(v0) < 3 or len(v1) < 3:
            res['notes'].append('⚪双通道: 竞彩赔率列不完整')
            return res
    except Exception:
        res['notes'].append('⚪双通道: 竞彩逐T 格式异常')
        return res
    fi = min(range(3), key=lambda i: v0[i])           # 初盘最低赔 = 公众热门
    fav = ('H', 'D', 'A')[fi]
    c1 = round(100 * (v1[fi] - v0[fi]) / v0[fi], 2)   # C1 公众热门方向降赔%(负=降赔)
    res['C1'] = {'fav': fav, 'pct': c1}
    a0, a1 = _ah_hdp(ah_from), _ah_hdp(ah_to)
    if not (a0 and a1):
        res['notes'].append('⚪双通道: 欧亚盘口不可解析（缺早盘/临场亚盘）→ 机构通道不可判(三态)')
        return res
    hdp_chg = round(a1[0] - a0[0], 2)
    hw_chg = round(a1[1] - a0[1], 3)
    if fav == 'H':                                     # 热门=主 → 盘口加深(更负) 或 主水降
        follow = (hdp_chg < -0.01) or (hw_chg <= -0.03)
    elif fav == 'A':                                   # 热门=客 → 盘口变浅(更正) 或 客水降(≈主水升)
        follow = (hdp_chg > 0.01) or (hw_chg >= 0.03)
    else:                                              # 热门=平 → 盘口不动即跟进
        follow = abs(hdp_chg) < 0.01 and abs(hw_chg) < 0.03
    res['C2'] = {'hdp_chg': hdp_chg, 'hw_chg': hw_chg, 'follow': follow}
    res['C3'] = {'water_dir': ('降=防御' if hw_chg <= -0.01 else ('升=诱' if hw_chg >= 0.01 else '平')),
                 'hdp_moved': abs(hdp_chg) >= 0.01}
    # ── 四象限（优先级 Q2 > Q1 > Q4 > Q3·诱盘警报最优先）──
    if c1 <= -2.0 and follow is False:
        res['quadrant'] = ('Q2', '诱盘警报', '公众热捧但欧亚不跟进 → 热门方向降1档 + 强制并列次方向（D1 纪律联动）',
                           '⚠️ 竞彩降赔≠方向（4场样本命中25%）·本象限依据充分')
    elif c1 <= -2.0 and follow is True:
        res['quadrant'] = ('Q1', '共识确认', '公众+机构同向 → 置信度 +0.5 档（spread<2% 且热门<1.50 可 +1 档）',
                           '✅ P0-1 已回测（spread<2% +8.7/+17.6pp）')
    elif c1 >= 2.0 and follow is True:
        res['quadrant'] = ('Q4', '阻盘信号', '欧亚看好但拉高赔率阻买 → 按欧亚方向 +0.5 档·标注「阻盘·非诱」',
                           '⏳待回测·仅参考（行业共识）')
    elif -2.0 < c1 < 2.0 and abs(hdp_chg) >= 0.01:
        # 🔴P2-1 修复(2026-09-29): 收紧为 -2.0 < c1 < 2.0 ——
        #   公众「主动看衰」(c1>=2.0) ≠ 「公众未察觉的冷门」，此前 c1>=2.0 被误标 Q3
        res['quadrant'] = ('Q3', '冷门前兆', '仅欧亚独自动·公众未察觉 → 提示关注（不直接调档·等 Steam 确认）',
                           '⏳待回测·仅参考（中文欧亚盘圈方法）')
    elif c1 >= 2.0 and follow is False:
        # 🔴P2-1 修复: 公众主动看衰 + 机构未跟 → 共识看衰（非冷门前兆·不调档）
        res['notes'].append('⚪双通道: 公众主动看衰(%+.2f%%) + 机构未跟进 → 共识看衰·不调档（非冷门前兆）' % c1)
    if res['quadrant']:
        q = res['quadrant']
        res['notes'].append('🟣双通道四象限 %s %s: %s' % (q[0], q[1], q[2]))
        res['notes'].append('   └ %s' % q[3])
    else:
        res['notes'].append('⚪双通道四象限: 未触发（C1 %+.2f%% · 欧亚跟进=%s）' % (c1, follow))
    return res


def list_snapshots():
    """列出已有快照（🔴含时点顺序·供安全选取·防跨场复用）"""
    ds = _load_all()
    if not ds:
        print('（无快照）')
        return
    for d in ds:
        w = d.get('window_bj', ['?', '?'])
        print('%s  存于 %s  窗口 %s → %s  (%d 场)' % (
            d['_file'], d.get('saved_at', '?'), w[0], w[1], len(d.get('games', []))))
        for g in d.get('games', []):
            print('     %s  %-22s vs %-22s  eventId=%s' % (
                (g.get('kickoff_bj') or '')[-5:], g.get('home'), g.get('away'), g.get('event_id')))


def diff(key):
    """🔴某场跨快照的赔率时序（多时点 → 变动）"""
    ds = _load_all()
    hits = []
    for d in ds:
        for g in d.get('games', []):
            if _match(g, key):
                hits.append((d.get('saved_at', '?'), d['_file'], g))
    if not hits:
        print('未找到该场（检查队名·用 --list 查看已有场次）')
        return
    print('=== %s 的赔率时序（%d 个时点）===' % (key, len(hits)))
    print('| 抓取时刻 | 文件 | ML 主/平/客 | 亚盘 | O2.5 | 市场更新 |')
    print('|:--|:--|:--|:--|:--|:--|')
    for t, f, g in hits:
        s = _extract(g.get('raw_1xbet'))
        print('| %s | %s | %s | %s | %s | %s |' % (t, f, s['ml'], s['ah'], s['o25'], s['upd']))
    if len(hits) >= 2:
        a, b = _extract(hits[0][2].get('raw_1xbet')), _extract(hits[-1][2].get('raw_1xbet'))
        print()
        print('🔴 变动（最早 → 最新）:')
        for lbl, k in (('ML', 'ml'), ('亚盘', 'ah'), ('O2.5', 'o25')):
            if a[k] != b[k]:
                print('   %-5s %s → %s' % (lbl, a[k], b[k]))
            else:
                print('   %-5s %s（未变）' % (lbl, a[k]))
        print('   ⏱ 时间跨度: %s → %s' % (hits[0][0], hits[-1][0]))
        # 🔴2026-09-28: 接入 delta_for → 直接输出判定信号（用户指令「模型判定依据模块输出」·非仅展示）
        _d = delta_for(key.split(' vs ')[0], key.split(' vs ')[-1]) if ' vs ' in key else None
        if _d and _d.get('signal'):
            print()
            print('🔴 判定信号（模块输出 → V1 双源变动 / V2 诱阻盘 / V6 盘口联动 / Step6 量级）:')
            for s in _d['signal']:
                print('   %s' % s)
        elif _d:
            print()
            print('⚪ 变动未触发阈值（赔率 <3% / 盘口未动 / 水位 <0.15 / 隐含 <3pp）')
    else:
        print()
        print('ℹ️ 仅 1 个时点 → 再抓一次即可形成变动对比（V1/V2/V6/P1-3 需要 ≥2 时点）')


API_ERRS = []   # 🔴2026-10-09: 收集 API 错误(限流等)·供 main 显式提示


def collect(leagues, lo, hi, t0, t1):
    rows, misses = [], []
    for lg in leagues.split(','):
        for slug in LG.get(lg.strip(), []):
            u = 'https://api.odds-api.io/v3/events?apiKey=%s&sport=football&league=%s&status=pending' % (KEY, slug)
            d = fetch_json(u)
            # 🔴2026-10-09 修复: 原实现把限流/错误响应(如 {"error": "exceeded rate limit"})
            #   当作「成功但 0 场」→ 静默失败 → 误判「窗口内确实无赛事」(与 09-29 同型缺陷)
            if not d or (isinstance(d, dict) and d.get('error')):
                misses.append(slug)
                if isinstance(d, dict) and d.get('error'):
                    _e = str(d['error'])[:90]
                    if _e not in API_ERRS:
                        API_ERRS.append(_e)
                continue
            evs = d.get('events') if isinstance(d, dict) else d
            for e in (evs or []):
                ts = (e.get('date') or '')[:16].replace('T', ' ')
                if not ts:
                    continue
                try:
                    utc = dt.datetime.strptime(ts, '%Y-%m-%d %H:%M')
                except Exception:
                    continue
                bj = (utc + dt.timedelta(hours=BJ_OFFSET)).strftime('%Y-%m-%d %H:%M')
                if not (t0 <= bj <= t1):
                    continue
                rows.append({'league': lg, 'slug': slug, 'event_id': e.get('id'),
                             'home': e.get('home'), 'away': e.get('away'), 'kickoff_bj': bj})
    return rows, misses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--leagues', default='英超,西甲,德甲,意甲,法甲,欧联,欧冠')  # 🔴2026-10-09 域分离: 原默认'欧国联'为双通道早期残留 → 主战场(五大+欧战)应为默认
    ap.add_argument('--bj', default='22:00-06:00')
    ap.add_argument('--tag', default='nl')
    ap.add_argument('--list', action='store_true', help='列出已有快照及场次（不拉取）')
    ap.add_argument('--diff', help='显示某场跨快照的赔率时序（如 "Belgium vs France"）')
    a = ap.parse_args()
    if a.list:
        list_snapshots()
        return
    if a.diff:
        diff(a.diff)
        return
    lo, hi = a.bj.split('-')
    t0, t1 = bj_window(lo, hi)
    print('窗口(北京): %s → %s' % (t0, t1))
    rows, misses = collect(a.leagues, lo, hi, t0, t1)
    if API_ERRS:
        print('🔴 [API 错误] 非「无赛事」·而是接口报错 → 快照**未采集**·请稍后重试:')
        for _e in API_ERRS[:3]:
            print('     -', _e)
    print('窗口内 %d 场 ｜ slug 拉取失败 %d 个%s' % (
        len(rows), len(misses), ('（可能漏场: %s）' % ','.join(misses[:4])) if misses else ''))
    # 🔴2026-09-29 空快照拦截（实测: Odds-API 配额耗尽时 events 返回 0 场 → 原实现仍落盘空 JSON·污染时序）
    if not rows:
        print('⚪ [三态] 窗口内 0 场 → **不落盘**（避免空快照污染时序）')
        print('   可能原因: Odds-API 配额/限流 · 窗口内确实无赛事 · slug 全失败 %d 个' % len(misses))
        return
    for r in rows:
        u = 'https://api.odds-api.io/v3/odds?apiKey=%s&eventId=%s&bookmakers=1xbet' % (KEY, r['event_id'])
        r['raw_1xbet'] = fetch_json(u)
    # 🔴2026-09-29 三态标注修复（实测 18:40 快照 6/10 场 bookmakers 为空却静默落盘·违反三态纪律）:
    #   逐场标记 fetch_ok（ML 可解析 = 有效）→ 落盘 JSON 带该字段 + MD/终端显式告警
    #   实测根因: Odds-API 免费档**配额/限流**（批量拉取时前几场成功、后续为空；间隔重试仍空）
    _fail = []
    for r in rows:
        _ok = (_extract(r.get('raw_1xbet'))['ml'] not in ('-', '', None))
        r['fetch_ok'] = bool(_ok)
        if not _ok:
            _fail.append('%s vs %s' % (r['home'], r['away']))
    if _fail:
        print('🔴 [三态·数据缺口] 赔率拉取失败 %d/%d 场（fetch_ok=false·ML 不可解析）：' % (len(_fail), len(rows)))
        print('   可能原因: Odds-API 配额/限流 或 该场暂未上架 → 本快照这些场**不可用于变动对比**')
        for _f in _fail[:8]:
            print('     · %s' % _f)
    ts = dt.datetime.now().strftime('%Y%m%d_%H%M%S')   # 🔴秒级: 同分钟多次调用亦不覆盖
    os.makedirs(SNAP_DIR, exist_ok=True)
    jp = os.path.join(SNAP_DIR, '%s_%s.json' % (a.tag, ts))
    json.dump({'saved_at': dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'window_bj': [t0, t1],
               'source': 'Odds-API v3 (1xbet 全市场)',
               'fetch_fail_n': len(_fail), 'fetch_fail': _fail, 'games': rows},
              open(jp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('✅ JSON 落盘:', jp)
    md = ['# 赔率快照 %s（%s → %s·北京）' % (ts, t0, t1), '',
          '> 🔴 用途: 完整分析(Step0-11)时读入 → 与竞彩 txt/终赔对比 → 支撑 V1 双源变动 / V2 诱阻盘 / V6 盘口联动 / P1-3 Steam',
          '> 🔴 数据隔离: 秒级命名·只增不改·按 event_id/队名匹配本场·禁跨场复用',
          ('> 🔴 **本快照拉取失败 %d/%d 场**（fetch_ok=false·ML 不可解析）→ 这些场**不可用于变动对比**·原因多为 Odds-API 配额/限流' % (len(_fail), len(rows))) if _fail else '> ✅ 本快照全部场次拉取成功', '',
          '| 开赛 | 场次 | ML 主/平/客 | 亚盘(让球·主水/客水) | O2.5 | O3.5 | BTTS | CS最低 | 市场更新 | eventId |',
          '|:--|:--|:--|:--|:--|:--|:--|:--|:--|:--|']
    for r in rows:
        s = _extract(r.get('raw_1xbet'))
        _tag = '' if r.get('fetch_ok') else '⚠️'
        md.append('| %s | %s%s vs %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            r['kickoff_bj'][-5:], _tag, r['home'], r['away'], s['ml'], s['ah'], s['o25'], s['o35'],
            s['btts'], s['cs'], s['upd'], r['event_id']))
    md += ['', '> 口径: ML=1xbet 胜平负 · 亚盘=Spread(近 -1 档·主/客水) · O2.5/O3.5=Totals · BTTS · CS最低=Correct Score 最低赔率比分',
           '> ⚠️ 前缀=该场赔率拉取失败（fetch_ok=false·不可用于变动对比）']
    mp = os.path.join(SNAP_DIR, '%s_%s.md' % (a.tag, ts))
    open(mp, 'w', encoding='utf-8').write(chr(10).join(md) + chr(10))
    print('✅ MD 落盘:', mp)
    for r in rows:
        print('   %s %-22s vs %-22s  eventId=%s%s' % (
            r['kickoff_bj'][-5:], r['home'], r['away'], r['event_id'],
            '' if r.get('fetch_ok') else '   ⚠️拉取失败(fetch_ok=false)'))


if __name__ == '__main__':
    main()


# ================= V3.5.80 P8 纵向消费（2026-10-20 用户方案·prestep 快照驱动） =================
# 缺口：快照每份含波胆/让球/大小球全表，但只消费横向（当期值）·纵向（初盘→临场）0 消费 = 存在≠活跃
# 铁律：只供信号（权重/置信度）·不排除候选·全部阈值【待回测校准】
# 阈值与 joint_solver.P8_* 同值（此处独立定义·避免循环 import）
_P8_CS_CHG_MOVE = 0.05        # 波胆赔率变化显著阈值(5%)·|chg|<5% 视为持平
_P8_CS_CHG_STRONG = 0.15      # 波胆赔率强烈变化阈值(15%)
_P8_AH_LINE_MOVE = 0.25       # 盘口移动显著阈值(一格 0.25)
_P8_AH_WATER_MOVE = 0.03      # 水位方向阈值(判方向)·0.15 仍为剪刀差阈值
_P8_OU_OVER_MOVE = 0.05       # 大球水位变化显著阈值
_P8_OU_LINE_MOVE = 0.25       # 大小球盘线移动显著阈值


def _raw_of(file, event_id=None):
    """🔴P8: 按快照文件名读回 raw_1xbet（🔴按 event_id 精确匹配·防多场快照取错场）"""
    p = file if os.path.isabs(str(file)) else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "snapshots", os.path.basename(str(file)))
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}
    games = d.get("games") or []
    if event_id is not None:
        for g in games:
            if str(g.get("event_id")) == str(event_id) and g.get("raw_1xbet"):
                return g["raw_1xbet"]
    # 无 event_id（或未命中）→ 仅当全场只有 1 个含 raw 的 game 才回退（防跨场污染）
    cand = [g for g in games if g.get("raw_1xbet")]
    if len(cand) == 1:
        return cand[0]["raw_1xbet"]
    return {}


def _cs_key(k):
    """🔴比分键归一为 'H-A'（🔴与 joint_solver._cs_market_probs 同口径·2026-10-20 审计修复）

    历史断点: P8 原实现输出 'H:A' 而 `_cs_market_probs` 用 `k.split("-")` → 直接
    `ValueError: invalid literal for int()`（传 cs_odds 即崩·审计实跑抓到）。
    → 全链统一 '-' 口径；vertical_for 内部再转 ':' 供 cs_vert（pool 比分用 ':'）。
    """
    return str(k or "").strip().replace(":", "-").replace("/", "-")


def _cs_full(raw):
    """🔴P8: 波胆全表（剔除占位档 1<v<100·key 归一为 'H-A'·与 joint_solver 同口径）"""
    out = {}
    if not isinstance(raw, dict):
        return out
    for m in ((raw.get("bookmakers") or {}).get("1xbet") or []):
        if str(m.get("name") or "").lower() != "correct score":
            continue
        for o in (m.get("odds") or []):
            try:
                v = float(o.get("odds"))
                k = str(o.get("label") or "").strip()
            except Exception:
                continue
            if k and 1 < v < 100:
                out[_cs_key(k)] = v
        break
    return out


def _ah_full(raw):
    """🔴P8: 让球全档 [(hdp, home, away)]·按 hdp 升序"""
    out = []
    if not isinstance(raw, dict):
        return out
    for m in ((raw.get("bookmakers") or {}).get("1xbet") or []):
        if str(m.get("name") or "").lower() != "spread":
            continue
        for o in (m.get("odds") or []):
            try:
                out.append((float(o.get("hdp")), float(o.get("home")), float(o.get("away"))))
            except Exception:
                continue
        break
    return sorted(out, key=lambda x: x[0])


def _ou_full(raw):
    """🔴P8: 大小球全档 {line: (over, under)}"""
    out = {}
    if not isinstance(raw, dict):
        return out
    for m in ((raw.get("bookmakers") or {}).get("1xbet") or []):
        if str(m.get("name") or "").lower() != "totals":
            continue
        for o in (m.get("odds") or []):
            try:
                out[float(o.get("hdp"))] = (float(o.get("over")), float(o.get("under")))
            except Exception:
                continue
        break
    return out


def _tt_full(raw):
    """🔴P10(2026-10-25): Team Total 主/客全档 → {"home": {line:(over,under)}, "away": {...}}

    P10 市场矩阵的**形状先验**来源（P(H=k)/P(A=k) 行列边缘·只进先验·不进 IPF 硬迭代）。
    与 _ou_full 同款循环骨架·只改 market name；不改动任何既有解析器。
    """
    out = {"home": {}, "away": {}}
    if not isinstance(raw, dict):
        return out
    for m in ((raw.get("bookmakers") or {}).get("1xbet") or []):
        nm = str(m.get("name") or "").strip().lower()
        if nm not in ("team total home", "team total away"):
            continue
        key = "home" if nm.endswith("home") else "away"
        for o in (m.get("odds") or []):
            try:
                out[key][float(o.get("hdp"))] = (float(o.get("over")), float(o.get("under")))
            except (TypeError, ValueError):
                continue
    return out


def _pick_ah(rows):
    """🔴P8: 选**均衡线档**（|主水−客水| ≤ 0.25·主客最接近且≈1.9/1.9）

    🔴铁律（case229/234 教训·2026-10-09 固化）: 亚盘判定必须用均衡线——
    「最接近 0 的负档」常是庄家用来摆设的深档（实测 热刺场 −0.25 档 1.33/3.08
    = 抽水 60% 的假档）→ 拿它判「升盘/降水」必错。
    无均衡档 → **返回 None（三态·不采用）**，禁深档冒充。
    """
    if not rows:
        return None

    # 🔴V3.5.92-fix3（2026-11-04 case323/324 实证）: 均衡档判据 ← **去水后 p_home 偏离 0.5**
    #   旧判据 `abs(主-客) <= 0.25` 把**抽水率混进均衡度**:
    #     case323 +0.25 档 2.159/1.811 → 抽水仅 1.5%（最健康）· p偏离 0.044 · Δ赔率 0.35 → **被误拒**
    #     case321 +1.00 档 2.035/1.806 → 抽水 4.5% · p偏离 0.030 · Δ赔率 0.23 → 通过
    #   逻辑反直觉: **抽水越低 → 主客赔率差越大**（更接近真实 2.0/2.0）→ 越容易误拒
    #   → 后果: 判「无均衡档」→ P1 让球水位 / V3 水位 / rule61-64 / P8 升降盘 全部失效
    #   现判据: 去水后主队隐含概率偏离 0.5 超 0.08 才算不均衡（与抽水率无关·0.08 ≈ 让球 ≤1/4 档）
    def _dev(r):
        try:
            _ih, _ia = 1.0 / r[1], 1.0 / r[2]
            return abs(_ih / (_ih + _ia) - 0.5)
        except Exception:
            return 9.0

    bal = [r for r in rows if r[1] > 1 and r[2] > 1 and _dev(r) <= 0.08]
    if not bal:
        return None
    # 🔴2026-10-20 三点实跑修: 原按 |hdp| 最小选档 → 初/末盘可能选到**不同 hdp 档**
    #   （萨巴赫初 +1.50 主2.051/客1.895，末盘 +1.75 主1.780/客1.969 才是均衡点，
    #    但 +1.50 档末盘也勉强 |Δ|≤0.25 → 被选中 → 误判「盘稳」）
    #   → 改按**主客赔率最接近**（市场均衡点）选档，并列再按 |hdp|。
    # 选「去水后最接近 0.5」的档（并列再按 |hdp| 小者）
    return min(bal, key=lambda r: (round(_dev(r), 4), abs(r[0])))


def _pick_ou(d):
    """🔴P8: 选 2.5 档·无则最接近 2.5"""
    if not d:
        return None
    if 2.5 in d:
        return 2.5
    return min(d.keys(), key=lambda k: abs(k - 2.5))


def _vert_std(out, home=None, away=None):
    """🔴V3.5.92 PIECE-1: 纵向**统一标准结构**（std 层）

    背景（2026-11-04 用户指令「固定一个标准的数据结构·方便获取也方便消费」）:
      三个维度原本结构迥异 ——
        cs_vert = {比分: {chg, dir}}                        按比分索引
        ah_vert = {line0,line1,w0,w1,combo,shift,up_side}   扁平
        ou_vert = {line0,line1,over0,over1,dir,conf_step}   扁平
      → 消费端每个维度各写一套 if-else（易错·难扩展·审计难核对）

    本标准层把**方向语义**统一成 4 个字段（明细仍留 detail 供追溯）:
        axis     'net'(净胜轴) | 'total'(总进球轴) | 'both'(比分=两轴联合)
        v        -1 / 0 / +1   —— 相对 axis 的方向
        strength 'none' | 'mild' | 'strong'
        note     人读说明

    🔴 铁律 1（视角）: 所有 v 均已折算成**主队视角**（受让场 ah_vert.shift 已翻转·
       见本文件 vertical_for 内 `if _recv: shift = -shift`）→ **消费端禁止再按 handi 正负二次翻转**。
    🔴 铁律 2（轴不同不投票）: ah/cs 属净胜轴，ou 属总进球轴 → 汇总同向只统计前两者，
       禁把「看大球」和「看主胜」当同一件事。
    """
    std = {
        'v': '1.0',
        'meta': {'home': home, 'away': away,
                 'n_points': int(out.get('n_points') or 0),
                 'span': out.get('span'),
                 'dims': [], 'n_dims': 0},
        'signal': {},
        'detail': {},
    }

    # ── ah（净胜轴）──
    ah = out.get('ah_vert')
    if isinstance(ah, dict):
        _sh = int(ah.get('shift') or 0)
        std['signal']['ah'] = {
            'axis': 'net', 'v': _sh,
            'strength': 'strong' if abs(_sh) >= 1 else ('mild' if _sh else 'none'),
            'note': str(ah.get('combo') or ''),
        }
        std['detail']['ah'] = dict(ah)
        std['meta']['dims'].append('ah')

    # ── ou（总进球轴）──
    ou = out.get('ou_vert')
    if isinstance(ou, dict):
        _st = int(ou.get('conf_step') or 0)
        std['signal']['ou'] = {
            'axis': 'total', 'v': _st,
            'strength': 'strong' if abs(_st) >= 1 else 'none',
            'note': str(ou.get('dir') or ''),
        }
        std['detail']['ou'] = dict(ou)
        std['meta']['dims'].append('ou')

    # ── cs（联合轴·按比分方向加权聚合为「净胜方向」）──
    cv = out.get('cs_vert')
    if isinstance(cv, dict) and cv:
        _W = {'drop_strong': 2, 'drop_mild': 1, 'rise_mild': -1, 'rise_strong': -2}
        _sc, _n_drop, _n_rise = 0.0, 0, 0
        _td, _tr = [], []
        for _s, _x in cv.items():
            if not isinstance(_x, dict):
                continue
            try:
                _h, _a = [int(_t) for _t in str(_s).split(':')]
            except Exception:
                continue
            _sign = 1 if _h > _a else (-1 if _h < _a else 0)   # 主胜+/平0/客胜-
            _w = _W.get(_x.get('dir'), 0)                     # 降赔+/升赔-
            if _w > 0:
                _n_drop += 1
                _td.append((abs(_x.get('chg') or 0), _s))
            elif _w < 0:
                _n_rise += 1
                _tr.append((abs(_x.get('chg') or 0), _s))
            _sc += _sign * _w
        _den = max(1.0, float(_n_drop + _n_rise))
        _bias = max(-1.0, min(1.0, _sc / (_den * 2.0)))
        _v = 1 if _bias >= 0.15 else (-1 if _bias <= -0.15 else 0)
        _td.sort(reverse=True)
        _tr.sort(reverse=True)
        std['signal']['cs'] = {
            'axis': 'both', 'v': _v,
            'strength': ('strong' if abs(_bias) >= 0.5
                         else ('mild' if abs(_bias) >= 0.15 else 'none')),
            # 🔴表述要点（防误读）: 档数多少 ≠ 方向 —— 客胜比分「升赔」同样利好主队，
            #   故 note 同时给「档数」与「方向」并说明净偏，避免「升 10 降 7 却说偏主队」的困惑
            'note': ('降%d/升%d → 净偏%s（按比分方向加权·客胜比分升赔亦利好主队）'
                     % (_n_drop, _n_rise,
                        '主队' if _v > 0 else ('客队' if _v < 0 else '中性'))),
            'bias': round(_bias, 3), 'n_drop': _n_drop, 'n_rise': _n_rise,
            'top_drop': [s for _, s in _td[:3]], 'top_rise': [s for _, s in _tr[:3]],
        }
        std['detail']['cs'] = dict(cv)
        std['meta']['dims'].append('cs')

    std['meta']['n_dims'] = len(std['meta']['dims'])

    # ── 汇总：净胜轴几源同向（🔴只统计 ah+cs·ou 轴不同不投票） ──
    _d = {k: std['signal'][k].get('v') for k in ('ah', 'cs') if k in std['signal']}
    _nz = [v for v in _d.values() if v]
    if len(_nz) >= 2 and all(v == _nz[0] for v in _nz):
        std['signal']['agree'] = {'n_agree': len(_nz), 'dir': _nz[0],
                                  'label': '%d 源同向（%s）' % (len(_nz), '+'.join(_d))}
    else:
        std['signal']['agree'] = {
            'n_agree': 0, 'dir': 0,
            'label': ('净胜轴无源（ah/cs 均缺）' if not _nz
                      else ('净胜轴单源（无法交叉验证）' if len(_nz) < 2
                            else '净胜轴两源分歧'))}
    return std


def vertical_for(home, away, end_cs=None, end_ah=None, end_ou=None, end_label=None,
                 event_id=None):
    """🔴V3.5.80 P8: 纵向信号（初盘→临场·快照驱动）

    返回 {count, n_points, span, cs_vert, ah_vert, ou_vert, note, **std**}
      **std**（🔴V3.5.92 新增·统一标准结构·消费端优先读这个）:
        std.meta   = {home, away, n_points, span, dims[], n_dims}
        std.signal = {ah:{axis,v,strength,note}, ou:{...}, cs:{...}, agree:{n_agree,dir,label}}
        std.detail = {ah:{原始}, ou:{原始}, cs:{原始}}   ← 追溯用
      —— 旧键（cs_vert/ah_vert/ou_vert）**全部保留**，作为兼容层
      cs_vert: {比分: {chg(正=赔率降=被看好), dir}}
      ah_vert: {line0,line1,w0,w1,combo,shift,up_side}
      ou_vert: {line0,line1,over0,over1,dir,conf_step}
    🔴单时点 → count=0（三态）·按 event_id 精确回读·禁跨场复用
    """
    out = {"count": 0, "n_points": 0, "span": None, "cs_vert": None, "ah_vert": None,
           "ou_vert": None, "note": []}
    try:
        r = find_for(home, away)
    except Exception as e:
        out["note"].append("⚪P8纵向: 快照查询异常(%s)" % type(e).__name__)
        return out
    if not r.get("count"):
        out["note"].append("⚪P8纵向: 无本场快照 → 不启用(三态)")
        return out
    # 🔴event_id 精确过滤（禁跨场复用·同队名可能有多场·如欧国联双循环）
    if event_id is not None:
        _pts = [p for p in (r.get("points") or [])
                if str(p.get("event_id")) == str(event_id)]
        if not _pts:
            out["note"].append("⚪P8纵向: 本场 event_id=%s 在快照中无时点 → 三态" % event_id)
            return out
        r = {"count": len(_pts), "first": _pts[0], "last": _pts[-1], "points": _pts}
    f0 = r["first"]
    # 🔴2026-10-27 语义固化（防误读）: `count` 是**可用维度数**（cs/ah/ou 各 +1·下方 `out["count"] += 1`），
    #   **不是时点数**；时点数（快照份数）由本字段 `n_points` 表示。
    #   原同名不同义已致一次误读（看到 count=3 以为是丢了时点，实际是三维各 1）。
    out["n_points"] = int(r.get("count") or 0)
    _fraw = _raw_of(f0.get("file"), f0.get("event_id"))
    if end_cs or end_ah or end_ou:
        le = {"cs": end_cs, "ah": end_ah, "ou": end_ou}
        _ls = end_label or "正式执行"
    else:
        if r["count"] < 2:
            out["note"].append("⚪P8纵向: 仅 1 时点 → 无变动可算(三态)")
            return out
        fz = r["last"]
        _lraw = _raw_of(fz.get("file"), fz.get("event_id"))
        le = {"cs": _cs_full(_lraw), "ah": _ah_full(_lraw), "ou": _ou_full(_lraw)}
        _ls = fz.get("saved_at")
    _fcs = _cs_full(_fraw)
    out["span"] = "%s → %s" % (f0.get("saved_at"), _ls)
    # ── cs_vert ──（🔴两端键归一为 '-' 再比·输出 ': ' 供 pool 口径）
    if _fcs and isinstance(le.get("cs"), dict) and le["cs"]:
        _endcs = {_cs_key(k): v for k, v in le["cs"].items()}
        cv = {}
        for k, v0 in _fcs.items():
            v1 = _endcs.get(k)
            if not v1 or v0 <= 0:
                continue
            chg = (v0 - v1) / v0
            if chg >= _P8_CS_CHG_STRONG:
                d = "drop_strong"
            elif chg >= _P8_CS_CHG_MOVE:
                d = "drop_mild"
            elif chg <= -_P8_CS_CHG_STRONG:
                d = "rise_strong"
            elif chg <= -_P8_CS_CHG_MOVE:
                d = "rise_mild"
            else:
                d = "flat"
            cv[k.replace("-", ":")] = {"chg": round(chg, 3), "dir": d}
        if cv:
            out["cs_vert"] = cv
            out["count"] += 1
    # ── ah_vert ──
    _fa = _ah_full(_fraw)
    _la = le.get("ah") if isinstance(le.get("ah"), list) else None
    if _fa and _la:
        a0, a1 = _pick_ah(_fa), _pick_ah(_la)
        if a0 and a1:
            # 🔴2026-10-20 三点实跑修(受让场语义): 主队受让(handi>0)时「上盘」= 客队(让球方)
            #   ① 上盘水位应取 **away**（原取 home → 方向错）
            #   ② line 变大 = 受让加深 = 客队让球更深 = **升盘(客队方向)**（原按 line>0 判「降盘」）
            #   ③ 判完再把 shift **转回主队净胜视角**（joint_solver 的 M 是主队净胜）
            _recv = (a0[0] > 0)                      # 初盘主队受让
            lm = (a1[0] - a0[0]) * (-1 if _recv else 1)   # 让球方视角：负 = 加深(升盘)
            _w0u = a0[2] if _recv else a0[1]         # 上盘水位（让球方赔率）
            _w1u = a1[2] if _recv else a1[1]
            wm = _w1u - _w0u                         # 上盘水位变化（负 = 降水）
            combo, shift = "盘稳水稳", 0
            if abs(lm) >= _P8_AH_LINE_MOVE and abs(wm) >= _P8_AH_WATER_MOVE:
                if lm < 0 and wm < 0:
                    combo, shift = "升盘降水(真看好)", +1
                elif lm < 0 and wm > 0:
                    combo, shift = "升盘升水(造热/阻上)", -1
                elif lm > 0 and wm > 0:
                    combo, shift = "降盘升水(看弱/走次盘)", -1
                else:
                    combo, shift = "降盘降水(压赔付)", 0
            elif abs(wm) >= _P8_AH_WATER_MOVE:
                combo, shift = (("盘稳·主水降(上盘被看好)", +1) if wm < 0
                                else ("盘稳·主水升(上盘信心降)", -1))
            if _recv:                                # 转回主队净胜视角
                shift = -shift
            out["ah_vert"] = {"line0": a0[0], "line1": a1[0],
                              "w0": round(_w0u, 3), "w1": round(_w1u, 3),
                              "combo": combo, "shift": shift,
                              "up_side": ("客队(受让场)" if _recv else "主队(主让场)")}
            out["count"] += 1
    # ── ou_vert ──
    _fo = _ou_full(_fraw)
    _lo = le.get("ou") if isinstance(le.get("ou"), dict) else None
    if _fo and _lo:
        k0, k1 = _pick_ou(_fo), _pick_ou(_lo)
        if k0 is not None and k1 is not None:
            o0, o1 = _fo[k0][0], _lo[k1][0]
            lm, om = k1 - k0, o1 - o0
            if om <= -_P8_OU_OVER_MOVE:
                d, conf = (("升盘+大球降水(强大球)" if lm >= _P8_OU_LINE_MOVE else "真看好大球(大球降水)"), +1)
            elif om >= _P8_OU_OVER_MOVE:
                d, conf = (("降盘+大球升水(强小球)" if lm <= -_P8_OU_LINE_MOVE else "生水诱大(大球升水·八成是坑)"), -1)
            else:
                d, conf = "盘稳水稳", 0
            out["ou_vert"] = {"line0": k0, "line1": k1, "over0": o0, "over1": o1,
                              "dir": d, "conf_step": conf}
            out["count"] += 1
    # 🔴V3.5.92 PIECE-1: 生成**统一标准结构**（零回归·旧键全保留）
    try:
        out["std"] = _vert_std(out, home, away)
    except Exception as _e_std:
        out["std"] = None
        out["note"].append("⚪P8纵向 std 构造失败(%s) → 消费端回退旧键"
                           % type(_e_std).__name__)
    if out["count"] == 0:
        out["note"].append("⚪P8纵向: 快照存在但波胆/让球/大小球关键市场缺失 → 三态")
    else:
        out["note"].append("🟢P8纵向: %d 维可用·%d 时点·跨度 %s"
                       % (out["count"], out.get("n_points") or 0, out["span"]))
    return out
