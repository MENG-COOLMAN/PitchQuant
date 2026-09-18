# -*- coding: utf-8 -*-
"""txt 特征提取器（2026-09-11·机器学习数据接入核心）
从竞彩 txt 自动提取在线学习所需 features（无需手工传参）+ 扩展特征（半全场/比分/场均进失）
支持格式: 【胜平负固定奖金】/【让球胜平负固定奖金 让球+1】/【总进球固定奖金】/【半全场】/【比分】
"""
import os, re, sys, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C

LEAGUE_ALIAS = {'英超': 'E0', '西甲': 'SP1', '意甲': 'I1', '德甲': 'D1', '法甲': 'F1',
                '欧冠': '欧冠', '欧联': '欧联', '欧协联': '欧协联', '日职': '日职', '英冠': '英冠'}


def _seg(text, name):
    """取【name...】段落内容（到下一个【 为止）"""
    m = re.search(r'【%s[^】]*】\s*\n' % re.escape(name), text)
    if not m:
        return None
    rest = text[m.end():]
    nxt = rest.find('【')
    return rest[:nxt] if nxt > 0 else rest


def _last_row(seg):
    """段内最后一个数据行（发布时间,...）"""
    if not seg:
        return None
    rows = [l for l in seg.split('\n') if re.match(r'^\d{4}-\d{2}-\d{2}', l.strip())]
    return rows[-1] if rows else None


def _nums(line):
    """取数值：先剥掉时间戳前缀（2026-09-09 12:00:00），避免日期数字污染赔率"""
    if not line:
        return []
    line = re.sub(r'^\s*\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\s*,?', '', line)
    return [float(x) for x in re.findall(r'\d+\.?\d*', line)]


def _parse_teams(head):
    """解析主客队名（同 data_bridge.extract_teams 规则·本地实现防循环导入）

    🔴2026-09-16 修复(P0): 调用方原只传 txt **第 1 行** → 两行式 txt
      (行1「赛事：西甲 周二008」/ 行2「对阵：A(主) VS B(客)」) 队名恒 None
      → 「近期攻防回退(优化1·recent_form)」等依赖队名的逻辑静默失效。
      现由调用方传入前 5 行文本块；本函数兼容全角/半角括号。
    """
    m = re.search(r'([^：:\s]+)\s*[（(]主[）)]\s*(?:VS|vs|对)\s*([^(\s（]+)', head)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m2 = re.search(r'([^\s：:]+)\s*VS\s*([^\s(（]+)', head)
    if m2:
        return m2.group(1).strip(), m2.group(2).strip()
    return None, None


def extract(txt_path):
    """返回 (features, detail) · 提取失败字段为 None/0（不臆造）"""
    try:
        s = open(txt_path, encoding='utf-8').read()
    except Exception as e:
        return None, {'error': 'txt 读取失败: %s' % e}
    detail = {}
    # 联赛
    league = '?'
    head = s.split('\n')[0]
    # 🔴2026-09-16 修复(P0): 前 5 行文本块 —— 两行式 txt 的联赛/队名可能落在第 2 行
    head_block = '\n'.join(s.split('\n')[:5])
    detail['league_raw'] = head[:60]
    for kw in ('欧冠', '欧联', '欧协联', '英超', '西甲', '意甲', '德甲', '法甲', '英冠', '日职'):
        if kw in head_block:
            league = kw
            break

    # 胜平负末盘
    oh = od = oa = None
    row = _last_row(_seg(s, '胜平负固定奖金'))
    if row:
        v = _nums(row)
        if len(v) >= 3:
            oh, od, oa = v[0], v[1], v[2]
    detail['ml_last'] = (oh, od, oa)

    # 让球（标题里的 让球+N / 让球-N）
    handi = 0.0
    mh = re.search(r'【让球胜平负固定奖金[^】]*让球([+-]?\d+(?:\.\d+)?)', s)
    if mh:
        handi = float(mh.group(1))
    detail['handi'] = handi

    # 总进球 → O25 等效赔率（反推：去水归一 → P(3+) → 等效赔率 1/P）
    o25 = 1.9
    row = _last_row(_seg(s, '总进球固定奖金'))
    if row:
        v = _nums(row)
        if len(v) >= 8:
            odds = v[0:8]           # 0,1,2,3,4,5,6,7+ 球
            inv = [(i, 1 / o) for i, o in enumerate(odds) if o > 1]
            tot = sum(x[1] for x in inv)
            if tot > 0:
                p_over = sum(x[1] for x in inv if x[0] >= 3) / tot   # 3+ 球 = 大球 2.5
                o25 = round(1 / p_over, 3) if p_over > 0 else 1.9
                detail['p_over25'] = round(p_over, 4)
                detail['goals_dist'] = {i: round(v / tot, 4) for i, v in inv}
    detail['o25_equiv'] = o25

    # 半全场末盘（9 值）
    bq = {}
    keys = ['胜胜', '胜平', '胜负', '平胜', '平平', '平负', '负胜', '负平', '负负']
    row = _last_row(_seg(s, '半全场胜平负固定奖金'))
    if row:
        v = _nums(row)
        if len(v) >= 9:
            bq = {keys[i]: v[i] for i in range(9)}
    if not bq:
        for k in keys:
            mm = re.search(r'%s=([\d.]+)' % k, s)
            if mm:
                bq[k] = float(mm.group(1))
    detail['bqc_last'] = bq

    # 比分末盘（1:0=... 格式）
    cs = {}
    for mm in re.finditer(r'(\d+:\d+)=([\d.]+)', s):
        cs[mm.group(1)] = float(mm.group(2))
    detail['cs_last'] = cs

    # 特征分析（场均进/失）
    stats = {}
    ms = re.search(r'场均进\s*([\d.]+)\s*vs\s*([\d.]+)\s*\|\s*场均失\s*([\d.]+)\s*vs\s*([\d.]+)', s)
    if ms:
        stats = {'home_avg_goals': float(ms.group(1)), 'away_avg_goals': float(ms.group(2)),
                 'home_avg_conceded': float(ms.group(3)), 'away_avg_conceded': float(ms.group(4))}
    detail['team_stats'] = stats

    features = {
        # A. 赔率基础（原有 11）
        'home_odds': oh, 'draw_odds': od, 'away_odds': oa,
        'handicap': handi, 'o25_odds': o25,
        'league': league, 'league_id': C.LEAGUE_ID.get(league, 9),
        'is_top5': 1 if league in ('E0', 'SP1', 'I1', 'D1', 'F1', '英超', '西甲', '意甲', '德甲', '法甲') else 0,
        'is_europe': 1 if league in ('欧冠', '欧联', '欧协联') else 0,
        'elo_diff': 0, 'handicap_layer': _layer(handi),
        # B. 半全场/比分盘/总进球衍生（2026-09-11 增强·零成本·原丢弃在 detail）
        'bqc_half_home_prob': _bqc_half_prob(bq, 'home'),
        'bqc_half_draw_prob': _bqc_half_prob(bq, 'draw'),
        'bqc_half_away_prob': _bqc_half_prob(bq, 'away'),
        'bqc_half_goal_rate': _bqc_half_goal_rate(bq),
        'cs_low_score_prob': _cs_score_prob(cs, 'low'),
        'cs_high_score_prob': _cs_score_prob(cs, 'high'),
        'cs_home_clean_sheet': _cs_clean_sheet(cs, 'home'),
        'cs_away_clean_sheet': _cs_clean_sheet(cs, 'away'),
        'goals_mode': _goals_mode(detail.get('goals_dist', {})),
        'goals_std': _goals_std(detail.get('goals_dist', {})),
        # C1. 场均进失（txt 特征分析行）
        'home_avg_goals': stats.get('home_avg_goals', 0),
        'away_avg_goals': stats.get('away_avg_goals', 0),
        'home_avg_conceded': stats.get('home_avg_conceded', 0),
        'away_avg_conceded': stats.get('away_avg_conceded', 0),
        # C2. 攻防强度（联赛基准 1.35 球）
        'home_attack_strength': round(stats.get('home_avg_goals', 0) / 1.35, 3) if stats.get('home_avg_goals') else 0,
        'away_defense_vuln': round(stats.get('away_avg_conceded', 0) / 1.35, 3) if stats.get('away_avg_conceded') else 0,
    }
    # C3. 近期攻防回退（2026-09-16·优化1·Matches.csv 近 N 场实战均值）
    #     txt 缺「场均进/失」行时回退填充 6 特征·来源标注进 detail（三态: txt/matches_csv/none）
    team_stats_source = 'txt' if stats else 'none'
    if not stats:
        home, away = _parse_teams(head_block)
        try:
            import recent_form as _rf
            if _rf.fill_recent_form(features, home, away, league, detail=detail):
                team_stats_source = 'matches_csv'
        except Exception:
            pass
    detail['team_stats_source'] = team_stats_source
    ok = all([oh, od, oa])
    return features, {'detail': detail, 'complete': ok,
                      'missing': [k for k in ('home_odds', 'draw_odds', 'away_odds') if not features.get(k)]}


def _dewater_odds(odds_dict):
    """去水归一：赔率→概率"""
    inv = {k: 1.0 / v for k, v in odds_dict.items() if v and v > 1}
    tot = sum(inv.values())
    return {k: v / tot for k, v in inv.items()} if tot > 0 else {}


def _bqc_half_prob(bq, side):
    """半场主/平/客概率（半全场 9 赔率去水归一·2026-09-11 增强）"""
    if not bq:
        return 0.0
    p = _dewater_odds(bq)
    if side == 'home':
        return round(sum(p.get(k, 0) for k in ('胜胜', '胜平', '胜负')), 4)
    if side == 'draw':
        return round(sum(p.get(k, 0) for k in ('平胜', '平平', '平负')), 4)
    return round(sum(p.get(k, 0) for k in ('负胜', '负平', '负负')), 4)


def _bqc_half_goal_rate(bq):
    """半场有球率 = 1 - 半场平局概率"""
    if not bq:
        return 0.5
    return round(1.0 - _bqc_half_prob(bq, 'draw'), 4)


def _cs_score_prob(cs, kind):
    """比分盘低/高比分概率（33 比分去水归一·2026-09-11 增强）"""
    if not cs:
        return 0.0
    p = _dewater_odds(cs)
    if kind == 'low':
        return round(sum(p.get(k, 0) for k in ('0:0', '1:0', '0:1', '1:1')), 4)
    high = 0.0
    for k, v in p.items():
        try:
            h, a = map(int, k.split(':'))
            if h + a >= 4:
                high += v
        except Exception:
            pass
    return round(high, 4)


def _cs_clean_sheet(cs, side):
    """主/客零封概率（比分盘去水归一·2026-09-11 增强）"""
    if not cs:
        return 0.0
    p = _dewater_odds(cs)
    total = 0.0
    for k, v in p.items():
        try:
            h, a = map(int, k.split(':'))
            if side == 'home' and a == 0:
                total += v
            if side == 'away' and h == 0:
                total += v
        except Exception:
            pass
    return round(total, 4)


def _goals_mode(goals_dist):
    """最可能进球档（总进球分布）"""
    if not goals_dist:
        return 2
    try:
        return int(max(goals_dist.items(), key=lambda x: x[1])[0])
    except Exception:
        return 2


def _goals_std(goals_dist):
    """进球数标准差（不确定性）·🔴修正方案: 按概率和归一（防未归一 dict 失真）"""
    if not goals_dist:
        return 1.5
    try:
        tot = sum(goals_dist.values()) or 1.0
        mean = sum(int(k) * v for k, v in goals_dist.items()) / tot
        var = sum((int(k) - mean) ** 2 * v for k, v in goals_dist.items()) / tot
        return round(var ** 0.5, 3)
    except Exception:
        return 1.5


def _layer(handi):
    try:
        v = float(handi)
    except Exception:
        return 0
    if v <= -2.5: return 1
    if v <= -1.75: return 2
    if v <= -1.25: return 3
    if v <= -0.75: return 4
    if v <= -0.25: return 5
    if v < 0.25: return 6
    if v < 0.75: return 7
    if v < 1.25: return 8
    if v < 1.75: return 9
    if v < 2.5: return 10
    return 11


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    # 🔴stdout 包装移至 __main__（被 import 时不得重复包装·防 I/O closed 错误）
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(0)
    f, d = extract(sys.argv[1])
    import json
    print('features:', json.dumps(f, ensure_ascii=False))
    print('complete:', d.get('complete'), '| missing:', d.get('missing'))
    det = d.get('detail', {})
    print('让球:', det.get('handi'), '| O25等效:', det.get('o25_equiv'),
          '| P(>2.5):', det.get('p_over25'))
    print('半全场:', det.get('bqc_last'))
    print('场均进失:', det.get('team_stats'))
