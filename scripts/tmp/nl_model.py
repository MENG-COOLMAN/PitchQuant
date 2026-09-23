# -*- coding: utf-8 -*-
"""欧国联/国家队子模型 —— V3.5.75 (P0-3)
N1 赛事识别 | N2 主场参数 | N3 客热门平局泄漏 | N4 主客进球不对称
N5 公平赔率 edge | N6 战意分级 | N7 资金盘口径
铁律: 只调置信度·永不反转 L2 硬核方向·最多 ±1 档·未回测只提示
数据: nl_data/nl_with_elo.csv (658场) + fair_model.json (P0-2 已时间分割验证)
"""
import csv, io, json, math, os, sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
D = os.path.dirname(os.path.abspath(__file__))
NL_CSV = os.path.join(D, 'nl_data', 'nl_with_elo.csv')
FAIR = os.path.join(D, 'nl_data', 'fair_model.json')

# ---------- N1 赛事识别 ----------
NL_ALIASES = ('nations league', 'uefa nations league', '欧国联', '欧洲国家联赛')
NON_SENIOR = ('women', 'womens', 'u23', 'u21', 'u20', 'u19', 'u18', 'u17', '女足', '青年')


def is_nations_league(league_id=None, league_name=''):
    nm = (league_name or '').lower()
    # 🔴2026-09-23 稳健性: league_name 传纯数字(如 '5') 视为 league_id
    if league_id is None and nm.strip().isdigit():
        league_id = int(nm.strip())
    bad = [k for k in NON_SENIOR if k in nm]
    if bad:
        return False, '非成年队（含 %s）→ 不激活' % bad[0]
    if league_id is not None and int(league_id) == 5:
        return True, 'league_id=5 (UEFA Nations League)'
    if any(k in nm for k in NL_ALIASES):
        return True, 'league_name 含 Nations League'
    if 'friendly' in nm or 'friendlies' in nm or '友谊' in nm:
        return None, '国家队友谊赛（走友谊赛口径·非 NL）'
    return False, '非欧国联'


_BANDS = [('<-300', -99999, -300), ('-300~-200', -300, -200), ('-200~-100', -200, -100),
          ('-100~-50', -100, -50), ('-50~50', -50, 50), ('50~100', 50, 100),
          ('100~200', 100, 200), ('200~300', 200, 300), ('>300', 300, 99999)]
_CACHE = {}


def load_table():
    if _CACHE:
        return _CACHE
    # (1) local raw dataset present -> compute bands on the fly (development / backtest use)
    if os.path.exists(NL_CSV):
        rows = []
        for r in csv.DictReader(io.open(NL_CSV, encoding='utf-8')):
            try:
                hs, as_ = int(r['hs']), int(r['sa'])
                rows.append((float(r['elo_diff']), hs, as_, 'H' if hs > as_ else ('D' if hs == as_ else 'A')))
            except Exception:
                continue
        for lab, lo, hi in _BANDS:
            g = [x for x in rows if lo <= x[0] < hi]
            if not g:
                continue
            n = len(g)
            _CACHE[lab] = {'n': n,
                           'H': sum(1 for x in g if x[3] == 'H') / n,
                           'D': sum(1 for x in g if x[3] == 'D') / n,
                           'A': sum(1 for x in g if x[3] == 'A') / n,
                           'goals': sum(x[1] + x[2] for x in g) / n,
                           'o25': sum(1 for x in g if x[1] + x[2] >= 3) / n,
                           'btts': sum(1 for x in g if x[1] > 0 and x[2] > 0) / n}
        return _CACHE
    # (2) no raw dataset -> load pre-computed aggregate table (aggregates only, no raw match data)
    _bands_path = os.path.join(D, 'nl_data', 'nl_bands.json')
    try:
        doc = json.load(io.open(_bands_path, encoding='utf-8'))
        _CACHE.update(doc.get('bands', {}))
    except Exception:
        pass
    return _CACHE


# ---------- 队名 → 当前 Elo（读 elo_current.json·自动查询·防 存在不等于活跃·2026-09-23 P1 修复） ----------
ELO_JSON = os.path.join(D, 'nl_data', 'elo_current.json')
_ELO = {}


def _norm(x):
    return ''.join(c for c in (x or '').lower() if c.isalnum())


# ---------- 国家队中文名 → 英文名映射（欧国联主要参赛队·2026-09-23 P1 修复·防中文 txt 匹配失败） ----------
TEAM_CN = {
    '荷兰': 'Netherlands', '德国': 'Germany', '法国': 'France', '意大利': 'Italy', '西班牙': 'Spain',
    '英格兰': 'England', '葡萄牙': 'Portugal', '比利时': 'Belgium', '克罗地亚': 'Croatia', '丹麦': 'Denmark',
    '奥地利': 'Austria', '瑞士': 'Switzerland', '波兰': 'Poland', '乌克兰': 'Ukraine', '瑞典': 'Sweden',
    '挪威': 'Norway', '塞尔维亚': 'Serbia', '希腊': 'Greece', '土耳其': 'Turkey', '匈牙利': 'Hungary',
    '捷克': 'Czech Republic', '捷克共和国': 'Czech Republic', '斯洛伐克': 'Slovakia', '斯洛文尼亚': 'Slovenia',
    '苏格兰': 'Scotland', '威尔士': 'Wales', '爱尔兰': 'Ireland', '爱尔兰共和国': 'Ireland',
    '北爱尔兰': 'Northern Ireland', '冰岛': 'Iceland', '芬兰': 'Finland', '罗马尼亚': 'Romania',
    '保加利亚': 'Bulgaria', '阿尔巴尼亚': 'Albania', '波黑': 'Bosnia and Herzegovina',
    '波斯尼亚和黑塞哥维那': 'Bosnia and Herzegovina', '黑山': 'Montenegro', '北马其顿': 'North Macedonia',
    '马其顿': 'North Macedonia', '格鲁吉亚': 'Georgia', '亚美尼亚': 'Armenia', '阿塞拜疆': 'Azerbaijan',
    '哈萨克斯坦': 'Kazakhstan', '以色列': 'Israel', '俄罗斯': 'Russia', '白俄罗斯': 'Belarus',
    '立陶宛': 'Lithuania', '拉脱维亚': 'Latvia', '爱沙尼亚': 'Estonia', '摩尔多瓦': 'Moldova',
    '卢森堡': 'Luxembourg', '安道尔': 'Andorra', '马耳他': 'Malta', '塞浦路斯': 'Cyprus',
    '圣马力诺': 'San Marino', '直布罗陀': 'Gibraltar', '列支敦士登': 'Liechtenstein',
    '法罗群岛': 'Faroe Islands', '科索沃': 'Kosovo',
}


def team_elo(name, fuzzy_cut=0.82):
    '''队名 → 当前 Elo（精确→归一→模糊三级·未命中返回 None）'''
    if not _ELO:
        try:
            _ELO.update(json.load(io.open(ELO_JSON, encoding='utf-8')))
        except Exception:
            return None
    if not name:
        return None
    if name in _ELO:
        return _ELO[name]
    # 中文名 → 英文名（2026-09-23 P1）
    _en = TEAM_CN.get(name)
    if _en and _en in _ELO:
        return _ELO[_en]
    key = _norm(name)
    idx = {_norm(k): v for k, v in _ELO.items()}
    if key in idx:
        return idx[key]
    import difflib
    hit = difflib.get_close_matches(key, list(idx.keys()), n=1, cutoff=fuzzy_cut)
    return idx[hit[0]] if hit else None


def band_of(elo_diff):
    for lab, lo, hi in _BANDS:
        if lo <= elo_diff < hi:
            return lab
    return '>300'


HOME_ELO = 60.7


def home_note():
    return ('保留主场 Elo 加成 ≈%.1f（国际赛事常规 60-65）。NL 主胜率 43.0%% 偏低'
            '源于中档对阵平局多 + 客队热门赢不下来，**非无主场**（修正参考方案 B）' % HOME_ELO)


# ---------- N3 客队热门平局泄漏（实测 n=658） ----------
def draw_leak(elo_diff):
    if -200 <= elo_diff < -50:
        return {'level': '中浅客热门', 'n': 197, 'away': .35, 'draw': .31, 'not_away': .65,
                'alert': '🔴 强警报：禁把客胜当稳胆 · 平局按 27-31% 评估 · 串关降 1 档',
                'top_cs': '1:1 (14.2%) / 0:0 (11.2%) / 主队爆冷 1:0 (10.7%)'}
    if -300 <= elo_diff < -200:
        return {'level': '中深客热门', 'n': 86, 'away': .55, 'draw': .27, 'not_away': .45,
                'alert': '⚠️ 中警报：平局 27% 高于市场常给值', 'top_cs': '—'}
    if elo_diff < -300:
        return {'level': '超深客热门', 'n': 67, 'away': .63, 'draw': .28, 'not_away': .37,
                'alert': '⚠️ 平局仍 28% 非零 · 保留 0:0/1:1 出口', 'top_cs': '0:2 / 1:1 / 0:1'}
    return None


# ---------- N4 主客进球不对称（实测·修正参考方案 A 的拟合值混用） ----------
def goal_asymmetry(elo_diff, n_min=20):
    t = load_table()
    lab = band_of(elo_diff)
    b = t.get(lab)
    if not b:
        return None
    warn = '' if b['n'] >= n_min else '⚠️ 样本薄(n=%d<20)·仅参考' % b['n']
    side = '主队热门' if elo_diff > 50 else ('客队热门' if elo_diff < -50 else '均势')
    return {'band': lab, 'n': b['n'], 'side': side, 'goals': round(b['goals'], 2),
            'o25': round(b['o25'] * 100, 1), 'btts': round(b['btts'] * 100, 1), 'warn': warn}


# ---------- N5 公平赔率 edge（P0-2 已验证：方向 53.8% vs 基准 40.9% / ≥0.60 档 78.6%） ----------
_FAIR = {}


def fair_params():
    if not _FAIR:
        try:
            _FAIR.update(json.load(io.open(FAIR, encoding='utf-8'))['params'])
        except Exception:
            _FAIR.update({'base': .800, 'sh': .00050, 'sa': .00172, 'adv': HOME_ELO})
    return _FAIR


def _pmf(k, l):
    return math.exp(-l) * l ** k / math.factorial(k)


def fair_probs(elo_h, elo_a, maxg=9):
    p = fair_params()
    d = (elo_h + p['adv']) - elo_a
    lh = math.exp(p['base'] + p['sh'] * d)
    la = math.exp(p['base'] + p['sa'] * (-d))
    H = Dd = A = 0.0
    for i in range(maxg):
        for j in range(maxg):
            q = _pmf(i, lh) * _pmf(j, la)
            if i > j: H += q
            elif i == j: Dd += q
            else: A += q
    t = H + Dd + A
    return H / t, Dd / t, A / t, lh, la


def edge_report(elo_h, elo_a, mkt_h=None, mkt_d=None, mkt_a=None):
    fh, fd, fa, lh, la = fair_probs(elo_h, elo_a)
    best = max(fh, fd, fa)
    tier = ('≥0.60 高质量(实测 78.6%·可进串关)' if best >= .6 else
            ('0.50-0.60 中等(实测 51.5%)' if best >= .5 else '0.40-0.50 低(实测 36.8%·🔴不进串关)'))
    out = {'fair': {'H': round(fh, 4), 'D': round(fd, 4), 'A': round(fa, 4)},
           'lambda': {'home': round(lh, 2), 'away': round(la, 2)}, 'best': round(best, 4), 'tier': tier}
    if None not in (mkt_h, mkt_d, mkt_a):
        inv = 1 / mkt_h + 1 / mkt_d + 1 / mkt_a
        mh, md, ma = (1 / mkt_h) / inv, (1 / mkt_d) / inv, (1 / mkt_a) / inv
        out['market'] = {'H': round(mh, 4), 'D': round(md, 4), 'A': round(ma, 4),
                         'margin': round((inv - 1) * 100, 2)}
        out['edge_pp'] = {'H': round((fh - mh) * 100, 2), 'D': round((fd - md) * 100, 2),
                          'A': round((fa - ma) * 100, 2)}
        mx = max(out['edge_pp'].values())
        k = max(out['edge_pp'], key=out['edge_pp'].get)
        out['verdict'] = ('✅ 有 edge(%s %+.2fpp)' % (k, mx) if mx > 0 and best >= .6 else
                          ('⚠️ 置信 <0.60 → 不下注' if best < .6 else '⚪ 无正 edge'))
    return out


# ---------- N6 战意分级 ----------
def motivation(matchday, can_promote=None, can_relegate=None, is_derby=False, is_dead=False):
    if matchday <= 2:
        return {'label': 'MOT_NORMAL' if is_dead else 'MOT_HIGH', 'md': matchday,
                'note': 'MD1-2 所有队战意均高（积分清零·无人出局）→ 🔴 禁用死球淡化'}
    if matchday <= 4:
        if can_promote or can_relegate:
            return {'label': 'MOT_LOW' if is_dead else 'MOT_HIGH', 'md': matchday,
                    'note': 'MD3-4 按实时积分判定·警惕 MOT_MIXED'}
        return {'label': 'MOT_NORMAL', 'md': matchday, 'note': 'MD3-4 中期·结果不改变短期处境'}
    if is_dead:
        return {'label': 'MOT_LOW', 'md': matchday, 'note': 'MD5-6 死球·市场常已提前定价（陷阱）'}
    if is_derby:
        return {'label': 'MOT_HIGH', 'md': matchday, 'note': '德比·战意加成'}
    return {'label': 'MOT_HIGH' if (can_promote or can_relegate) else 'MOT_NORMAL', 'md': matchday,
            'note': 'MD5-6 升级/保级/死球集中·战意权重最大'}


# ---------- N7 资金盘口径 ----------
def spread_note(n_books, fav_spread=None):
    if fav_spread is None:
        return 'N7 资金盘: spread=N/A（无 Max/单源）·按 NL 纪律仅标注'
    band = ('CONSENSUS' if fav_spread < 2 else ('NORMAL' if fav_spread < 5 else
            ('DIVERGED' if fav_spread < 10 else 'CHAOS')))
    return ('N7 资金盘: n_books=%d · 热门侧 spread=%.1f%% → %s ⚠️ NL 机构池更小(9-13家)·'
            '阈值须按机构数标准化·**待 NL 样本重标·当前仅标注不降档**' % (n_books, fav_spread, band))


# ---------- 主入口 ----------
def analyze(league_id=None, league_name='', elo_h=None, elo_a=None, matchday=1,
            mkt=None, n_books=0, fav_spread=None, home_team=None, away_team=None):
    # 2026-09-23 P1 修复: 未传 Elo 时按队名自动查 elo_current.json（防 存在不等于活跃 降级）
    _elo_src = '传入'
    if elo_h is None and home_team:
        elo_h = team_elo(home_team); _elo_src = '自动查询'
    if elo_a is None and away_team:
        elo_a = team_elo(away_team)
    if elo_h is None or elo_a is None:
        _elo_src = '未取得(标注)'
    ok, why = is_nations_league(league_id, league_name)
    L = ['══════ 欧国联子模型 V3.5.75 ══════']
    L.append('N1 赛事识别: %s（%s）' % ('✅ 激活' if ok else ('⚪ 不确定' if ok is None else '❌ 不激活'), why))
    if not ok:
        return '\n'.join(L)
    t = load_table()
    tot = sum(v['n'] for v in t.values())
    L.append('R2 先验(n=%d): 主 %.1f%% / 平 %.1f%% / 客 %.1f%%' % (
        tot, sum(v['H'] * v['n'] for v in t.values()) / tot * 100,
        sum(v['D'] * v['n'] for v in t.values()) / tot * 100,
        sum(v['A'] * v['n'] for v in t.values()) / tot * 100))
    L.append('R3 场均 %.2f 球 · O2.5 %.1f%% · BTTS %.1f%%（🔴 禁用友谊赛/世界杯口径）' % (
        sum(v['goals'] * v['n'] for v in t.values()) / tot,
        sum(v['o25'] * v['n'] for v in t.values()) / tot * 100,
        sum(v['btts'] * v['n'] for v in t.values()) / tot * 100))
    L.append('')
    if elo_h is not None and elo_a is not None:
        d = elo_h - elo_a
        L.append('Elo差(主-客) = %+.0f → 档位 %s (Elo来源: %s)' % (d, band_of(d), _elo_src))
        b = t.get(band_of(d))
        if b:
            L.append('R4 档位实测(9档口径·n=%d): 主 %.0f%% / 平 %.0f%% / 客 %.0f%% · 场均 %.2f · O2.5 %.0f%% · BTTS %.0f%%' % (
                b['n'], b['H'] * 100, b['D'] * 100, b['A'] * 100, b['goals'], b['o25'] * 100, b['btts'] * 100))
        dl = draw_leak(d)
        if dl:
            L.append('R5 %s(客热门3档口径·与R4九档不同·n=%d): 实际客胜 %.0f%% · 平 %.0f%% · 客队未胜 %.0f%%' % (
                dl['level'], dl['n'], dl['away'] * 100, dl['draw'] * 100, dl['not_away'] * 100))
            L.append('    %s' % dl['alert'])
            L.append('    该档常见比分: %s' % dl['top_cs'])
        ga = goal_asymmetry(d)
        if ga:
            L.append('R6 主客进球不对称(与R4同档·结论侧): %s → %s | 实测总 %.2f·O2.5 %.1f%%·BTTS %.1f%% %s' % (
                ga['side'], ('主热门偏大球(零封大胜谱)' if ga['side'] == '主队热门' else
                              ('客热门偏小球(窄胜谱·防0:0/1:1)' if ga['side'] == '客队热门' else '均势→中性(不偏大不偏小)')),
                ga['goals'], ga['o25'], ga['btts'], ga['warn']))
        L.append('R7 均势判定: %s' % (
            '✅ 中性（实测 45%·🔴 修正参考方案"均势小球"结论）' if -50 <= d < 50 else '不适用（非均势档）'))
        L.append('R8 %s' % home_note())
        fe = edge_report(elo_h, elo_a, *(mkt or (None, None, None)))
        L.append('R10 公平模型: 公平 %.1f/%.1f/%.1f · λ %.2f/%.2f · 最高 %.1f%% → %s' % (
            fe['fair']['H'] * 100, fe['fair']['D'] * 100, fe['fair']['A'] * 100,
            fe['lambda']['home'], fe['lambda']['away'], fe['best'] * 100, fe['tier']))
        if 'edge_pp' in fe:
            L.append('    市场去水 %.1f/%.1f/%.1f（抽水 %.1f%%）→ edge H%+.2f / D%+.2f / A%+.2f pp → %s' % (
                fe['market']['H'] * 100, fe['market']['D'] * 100, fe['market']['A'] * 100,
                fe['market']['margin'], fe['edge_pp']['H'], fe['edge_pp']['D'], fe['edge_pp']['A'],
                fe.get('verdict', '')))
    if elo_h is None or elo_a is None:
        L.append('⚪ R4-R7/R10 档位类规则不输出: Elo 未取得（中文队名未在 TEAM_CN 映射 / '
                 '队名未收录于 elo_current.json）→ 三态标注（非静默跳过）')
        L.append('    → 修复: 补 TEAM_CN 映射 或 更新 Elo（python data/tmp/nl_elo_current.py）')
    m = motivation(matchday)
    L.append('R9 战意: %s（%s）' % (m['label'], m['note']))
    L.append(spread_note(n_books, fav_spread))
    L.append('')
    L.append('🔴 铁律: 只调置信度 · 永不反转 L2 硬核方向 · 最多 ±1 档 · 未回测项仅提示')
    return '\n'.join(L)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--league-id', type=int)
    ap.add_argument('--league-name', default='UEFA Nations League')
    ap.add_argument('--elo-h', type=float)
    ap.add_argument('--elo-a', type=float)
    ap.add_argument('--md', type=int, default=1)
    ap.add_argument('--o-h', type=float)
    ap.add_argument('--o-d', type=float)
    ap.add_argument('--o-a', type=float)
    ap.add_argument('--n-books', type=int, default=0)
    ap.add_argument('--spread', type=float)
    ap.add_argument('--home-team', help='主队名(自动查 Elo)')
    ap.add_argument('--away-team', help='客队名(自动查 Elo)')
    a = ap.parse_args()
    print(analyze(a.league_id, a.league_name, a.elo_h, a.elo_a, a.md,
                  (a.o_h, a.o_d, a.o_a), a.n_books, a.spread,
                  a.home_team, a.away_team))
