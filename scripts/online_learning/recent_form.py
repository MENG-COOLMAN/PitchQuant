# -*- coding: utf-8 -*-
"""近期攻防回退模块（2026-09-16·优化1）
背景: footballcharts.com 域名死亡后，竞彩 txt 缺「场均进 X vs Y | 场均失 Z vs W」行时，
      home/away_avg_goals、home/away_avg_conceded、home_attack_strength、away_defense_vuln
      6 个特征恒 0。
方案: 从本地 Matches.csv（23 万场·FTHome/FTAway 全场比分）按队取近 N 场实战均值回退填充。
纪律: 仅在 txt 未提供该行时填充（不覆盖 txt 真值）·非五大联赛不填充（不臆造）
      ·命中失败保持 0（三态标注由上层 missing 处理）·少于 3 场不算均值。
"""
import os, sys, csv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_MATCHES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Matches.csv')
_CACHE = {}            # {division: [(date, home, away, fth, fta) 按日期升序]}
_LOADED = set()

# 联赛中文 → Matches.csv Division（与 txt_features.LEAGUE_ALIAS 一致）
DIV_MAP = {'英超': 'E0', '西甲': 'SP1', '意甲': 'I1', '德甲': 'D1', '法甲': 'F1'}


def _norm(s):
    """队名归一：小写 + 去非字母数字（与 data_bridge.normalize_name 同规则·本地实现防循环导入）"""
    return ''.join(c for c in (s or '').lower() if c.isalnum())


_CAND_CACHE = {}


def _cand_norms(team_cn):
    """中文队名 → 归一化英文候选集（复用 data_bridge 70+ 别名库·懒加载防循环导入）"""
    if team_cn not in _CAND_CACHE:
        cands = {_norm(team_cn)}
        try:
            from data_bridge import cn_to_en_keywords
            # 二次 _norm: data_bridge.normalize_name 不去空格('real madrid')·
            # 而 Matches.csv 侧匹配用本模块 _norm('realmadrid')·必须归一到同一标度
            cands |= {_norm(c) for c in cn_to_en_keywords(team_cn) if c}
        except Exception:
            pass
        _CAND_CACHE[team_cn] = {c for c in cands if c}
    return _CAND_CACHE[team_cn]


def _load_division(division):
    """按需加载某 Division 全部历史行（进程内缓存·按日期升序）"""
    if division in _LOADED:
        return _CACHE.get(division, [])
    rows = []
    if os.path.exists(_MATCHES_PATH):
        try:
            with open(_MATCHES_PATH, encoding='utf-8-sig', newline='') as f:
                for r in csv.DictReader(f):
                    if r.get('Division') != division:
                        continue
                    try:
                        rows.append((r.get('MatchDate') or '', r.get('HomeTeam') or '',
                                     r.get('AwayTeam') or '', float(r.get('FTHome') or 0),
                                     float(r.get('FTAway') or 0)))
                    except (ValueError, TypeError):
                        continue
            rows.sort(key=lambda x: x[0])
        except Exception:
            rows = []
    _LOADED.add(division)
    _CACHE[division] = rows
    return rows


def team_recent_form(team_cn, division, n=6):
    """单队近期攻防: {'avg_scored','avg_conceded','n','team_en'} · 失败返回 None"""
    rows = _load_division(division)
    if not rows:
        return None
    cands = _cand_norms(team_cn)
    if not cands:
        return None
    # 精确匹配: 逐场判定该队在主/客哪一侧
    per_team = []          # (date, is_home, gf, ga)
    for d, h, a, fth, fta in rows:
        nh, na = _norm(h), _norm(a)
        if nh in cands:
            per_team.append((d, True, fth, fta))
        elif na in cands:
            per_team.append((d, False, fth, fta))
    hit = None
    if len(per_team) < max(3, n // 2):
        # 模糊回退: 对历史唯一队名做 包含/前缀5 匹配锁定一支队
        names = set()
        for d, h, a, fth, fta in rows:
            names.add(h); names.add(a)
        for nm in names:
            nn = _norm(nm)
            if any(c and len(c) >= 4 and (c in nn or nn in c or (len(c) >= 5 and c[:5] == nn[:5]))
                   for c in cands):
                hit = nn
                break
        if not hit:
            return None
        per_team = [(d, _norm(h) == hit, fth, fta)
                    for d, h, a, fth, fta in rows if _norm(h) == hit or _norm(a) == hit]
    if len(per_team) < 3:
        return None
    per_team.sort(key=lambda x: x[0])
    recent = per_team[-n:]
    k = len(recent)
    gf = sum(r[2] for r in recent)
    ga = sum(r[3] for r in recent)
    return {'avg_scored': round(gf / k, 3), 'avg_conceded': round(ga / k, 3),
            'n': k, 'team_en': hit or team_cn, 'last_date': recent[-1][0]}


def fill_recent_form(features, home_cn, away_cn, league_cn, n=6, detail=None):
    """txt 缺场均进失时回退填充 6 特征 · 返回实填 key 列表
    detail 传 dict 时写入 recent_form_meta（含数据截止日期·供上层标注新鲜度）"""
    division = DIV_MAP.get(league_cn)
    if not division or not home_cn or not away_cn:
        return []
    filled = []
    fh = features.get('home_avg_goals') or 0
    fa = features.get('away_avg_goals') or 0
    if not fh or not fa:
        sh = team_recent_form(home_cn, division, n) if not fh else None
        sa = team_recent_form(away_cn, division, n) if not fa else None
        if sh:
            features['home_avg_goals'] = sh['avg_scored']
            features['home_avg_conceded'] = sh['avg_conceded']
            features['home_attack_strength'] = round(sh['avg_scored'] / 1.35, 3)
            filled += ['home_avg_goals', 'home_avg_conceded', 'home_attack_strength']
        if sa:
            features['away_avg_goals'] = sa['avg_scored']
            features['away_avg_conceded'] = sa['avg_conceded']
            features['away_defense_vuln'] = round(sa['avg_conceded'] / 1.35, 3)
            filled += ['away_avg_goals', 'away_avg_conceded', 'away_defense_vuln']
        if detail is not None and filled:
            last = max(x['last_date'] for x in (sh, sa) if x)
            detail['recent_form_meta'] = {'source': 'Matches.csv', 'n': n,
                                          'data_last_date': last or '?'}
    return filled
