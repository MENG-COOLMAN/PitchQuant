# -*- coding: utf-8 -*-
"""handicap_dynamic_magnitude.py — 让球分层动态比分量级模型 V2.0 (2026-09-10·按用户方案落地)
架构: 先验(9层让球分层·非锚定) → 8因子动态调整 → 贝叶斯融合 → 动态候选池(禁机械锚)
🔴历史数据=先验基准仅起点·🔴每场按因子现场动态调整·🔴候选池从后验分布生成·硬约束仅边界
🔴诚实标注(评审2026-09-10): 9层先验时间分割回测量级MAE改善仅0.021球/+1.3pp(不显著)·模块价值=因子解释性与深盘聚焦
  非独立增益承诺·方案预期收益表(+33/42/17%)无回测·仅参考不作承诺·实际增益以P2回测为准
F1用goal_bin校准分布(148397场实际·2026-09-15全量重建)非O25市场隐含(2026-09-09隐含直读坑修复)
用法: python handicap_dynamic_magnitude.py --handi -2 --league 德甲 --o25 1.65 --eu 1.5,4.5,6.0 --elo 150 [--inj_h 3 --inj_a 1 --cs "..."] [--tg "0=20,1=8,2=4.5,..."]
输出: 先验+因子贡献+后验(量级中心/5层概率/置信)+动态候选池(权重)
"""
import sys, json, os, math, re, statistics
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRIOR = json.load(open(os.path.join(BASE, 'data', 'tmp', 'handicap_prior_table.json'), encoding='utf-8'))

def get_prior(layer):
    """Step1: 让球分层基准先验"""
    p = PRIOR.get(layer)
    if not p: return None
    return {'magnitude_center': p['magnitude_center'], 'goal_layer_probs': p['goal_layer_probs'],
            'net_goal_dist': p.get('net_goal_dist', {}), 'confidence': p['confidence'], 'n': p['n']}

def layer_key(handi):
    if handi is None: return None
    if handi <= -2.5: return '主让3(超深)'
    if handi <= -1.75: return '主让2(深盘)'
    if handi <= -1.25: return '主让1.5'
    if handi <= -0.75: return '主让1(中深)'
    if handi <= -0.25: return '主让0.5(浅)'
    if handi < 0.25: return '均势(平手)'
    if handi < 0.75: return '受让0.5(浅)'
    if handi < 1.25: return '受让1(中深)'
    if handi < 1.75: return '受让1.5'
    if handi < 2.5: return '受让2(深盘)'
    return '受让3(超深)'

# ═══ F1: O2.5偏离度(用goal_bin校准分布·非隐含) ═══
def factor_o25(o25, layer):
    if not o25: return None
    try:
        import calc_v3572 as c3
        gb = c3.goal_bin_probs(float(o25))
    except Exception:
        return None
    if not gb: return None
    cal_big = gb['prob_3'] + gb['prob_4']  # 校准后总3+球概率(148397场实际·2026-09-15重建)
    prior_big = 1 - PRIOR[layer]['goal_layer_probs']['0-1球'] - PRIOR[layer]['goal_layer_probs']['2球']
    dev = cal_big - prior_big
    return {'name': 'F1_O25校准偏离', 'magnitude_adjust': round(dev * 3.0, 3), 'confidence': 0.8,
            'detail': 'O25校准3+球%.0f%% vs 分层基准%.0f%%' % (cal_big * 100, prior_big * 100)}

# ═══ F2: 欧亚一致性(方向层已有·量级微调) ═══
def factor_euro_asia(oh, od, oa, handi):
    if not (oh and handi is not None): return None
    hp = (1 / oh) / (1 / oh + 1 / od + 1 / oa)
    implied = -(hp - 0.5) * 4.0
    if implied > -handi + 0.4: adj = -0.2  # 欧赔隐含让浅于亚盘? 按主让负: 隐含更浅=诱
    elif implied < -handi - 0.4: adj = 0.2
    else: adj = 0.0
    return {'name': 'F2_欧亚一致性', 'magnitude_adjust': round(adj, 3), 'confidence': 0.6,
            'detail': '隐含让%.1f vs 实际%.1f' % (implied, -handi)}

# ═══ F3: ELO匹配度(保留·标注共线风险·评审ELO已证伪于O25分层) ═══
def factor_elo(elo_diff, layer):
    if elo_diff is None: return None
    base = PRIOR[layer].get('base_elo_diff') or 0
    dev = elo_diff - base
    adj = 0.15 if dev > 40 else (-0.15 if dev < -40 else 0.0)
    return {'name': 'F3_ELO匹配', 'magnitude_adjust': round(adj, 3), 'confidence': 0.4,
            'detail': 'ELO差%d vs 档基准%d(⚠共线·弱参考)' % (elo_diff, base)}

# ═══ F4: 联赛风格(实测深盘量级差·德甲/西甲高·意甲低) ═══
LEAGUE_DEEP = {'德甲': 3.56, '西甲': 3.34, '法甲': 3.20, '英超': 3.11, '意甲': 2.92,
               'D1': 3.56, 'SP1': 3.34, 'F1': 3.20, 'E0': 3.11, 'I1': 2.92}
LEAGUE_CN_MAP = {'E0': '英超', 'SP1': '西甲', 'I1': '意甲', 'D1': '德甲', 'F1': '法甲'}
def factor_league(league, layer):
    if not league: return None
    league = LEAGUE_CN_MAP.get(league, league)  # E0等代码→中文(fx02·2026-09-10)
    if '主让2' not in layer and '主让3' not in layer: return None
    base = PRIOR[layer]['magnitude_center'] if layer in PRIOR else 3.3
    lm = LEAGUE_DEEP.get(league)
    if not lm: return None
    return {'name': 'F4_联赛风格', 'magnitude_adjust': round(lm - base, 3), 'confidence': 0.7,
            'detail': '%s深盘量级%.2f vs 分层基准%.2f' % (league, lm, base)}

# ═══ F5: 伤停影响(输入injury_impact影响分0-10·攻线/防线方向) ═══
def factor_injury(inj_h, inj_a, layer):
    if inj_h is None and inj_a is None: return None
    h, a = inj_h or 0, inj_a or 0
    if '主让' in layer:
        adj = -h * 0.05 + a * 0.03   # 主队攻线缺降总进球·客队防线弱升
    elif '受让' in layer:
        adj = h * 0.03 - a * 0.05
    else:
        adj = (h + a) * 0.02
    return {'name': 'F5_伤停影响', 'magnitude_adjust': round(adj, 3), 'confidence': 0.4,
            'detail': '主伤%.0f客伤%.0f' % (h, a)}

# ═══ F6: 半场推断(复用live extract_ht_goals_layer) ═══
def factor_halftime(bqc, prior_mag):
    if not bqc: return None
    try:
        sys.path.insert(0, os.path.join(BASE, 'data', 'tmp'))
        from live_score_engine import extract_ht_goals_layer
        r = extract_ht_goals_layer(bqc)
    except Exception:
        return None
    if not r: return None
    dev = r['mean_ft'] - prior_mag
    return {'name': 'F6_半场推断', 'magnitude_adjust': round(dev * 0.5, 3), 'confidence': r['confidence'],
            'detail': '半场推断期望%.2f vs 分层基准%.2f' % (r['mean_ft'], prior_mag)}

# ═══ F7: 比分盘低比分占比(⚠手写映射·数据待核·观察级) ═══
LOW_SCORES = ['0:0', '1:0', '0:1', '1:1']
def factor_cs_low(cs_str):
    if not cs_str: return None
    odds = dict(re.findall(r'(\d+:\d+)=([\d.]+)', cs_str))
    if len(odds) < 10: return None
    inv = {k: 1 / float(v) for k, v in odds.items() if float(v) > 1}
    tot = sum(inv.values())
    if tot <= 0: return None
    low = sum(inv.get(s, 0) for s in LOW_SCORES) / tot
    adj = (0.25 - low) * 2.0  # 低比分占比高于基准(0.25)降量级
    return {'name': 'F7_比分盘低比分', 'magnitude_adjust': round(adj, 3), 'confidence': 0.4,
            'detail': '低比分占比%.0f%%(⚠映射待数据核·观察级)' % (low * 100)}

# ═══ F8: 总进球盘(竞彩8档反推期望·与goal_odds同源) ═══
def factor_total_goals(tg_str, prior_mag):
    if not tg_str: return None
    vals = {}
    for m in re.finditer(r'(?:^|,)(\d+)=([\d.]+)', tg_str):
        k = int(m.group(1))
        if 0 <= k <= 7: vals[k] = float(m.group(2))
    if len(vals) < 5: return None
    inv = {k: 1 / v for k, v in vals.items()}
    tot = sum(inv.values())
    exp = sum(k * v / tot for k, v in inv.items())
    return {'name': 'F8_总进球盘', 'magnitude_adjust': round((exp - prior_mag) * 0.6, 3), 'confidence': 0.7,
            'detail': '总进球盘期望%.2f vs 分层基准%.2f' % (exp, prior_mag)}

# ═══ Step3: 贝叶斯融合(先验+因子加权·先验置信收缩) ═══
def bayesian_fusion(prior, factors):
    fs = [x for x in factors if x]
    if not fs: return dict(prior, confidence=prior['confidence'])
    tw = sum(x['confidence'] for x in fs)
    adj = sum(x['magnitude_adjust'] * x['confidence'] for x in fs) / tw if tw > 0 else 0
    shrink = 1 - prior['confidence'] * 0.5
    post_mag = prior['magnitude_center'] + adj * shrink
    # 因子一致性
    std = statistics.pstdev([x['magnitude_adjust'] for x in fs]) if len(fs) > 1 else 0
    consist = max(0.0, 1 - std / 1.2)
    conf = round(min(1.0, prior['confidence'] * 0.5 + consist * 0.3 + min(tw / 5, 1.0) * 0.3), 3)
    return {'magnitude_center': round(post_mag, 2), 'confidence': conf,
            'factor_contrib': {x['name']: x['magnitude_adjust'] for x in fs},
            'prior_center': prior['magnitude_center'], 'net_adjust': round(adj * shrink, 3)}

# ═══ Step4: 动态候选池(从后验分布·禁机械锚) ═══
SCORE_GRID = {0: [(0, 0)], 1: [(1, 0), (0, 1)], 2: [(2, 0), (1, 1), (0, 2)], 3: [(3, 0), (2, 1), (1, 2), (0, 3)],
              4: [(4, 0), (3, 1), (2, 2), (1, 3), (0, 4)],
              5: [(5, 0), (4, 1), (3, 2), (2, 3), (1, 4), (0, 5)]}
def dynamic_candidates(post_mag, direction, layer, top_n=5):
    cands = []
    for tg, scores in SCORE_GRID.items():
        w = math.exp(-0.5 * ((tg - post_mag) / 1.2) ** 2)  # 高斯权重(中心±)
        for (h, a) in scores:
            if direction == '主胜' and h <= a: continue
            if direction == '客胜' and a <= h: continue
            if direction == '平局' and h != a: continue
            cands.append((f'{h}:{a}', w))
    cands.sort(key=lambda x: -x[1])
    scores = [sc for sc, _ in cands]
    # 硬约束边界(仅补足·非替换·fx03·): 超深含4+球·主让2含净2
    def _add(tg, h, a):
        if (h, a) not in [(int(x.split(':')[0]), int(x.split(':')[1])) for x in scores]:
            cands.append((f'{h}:{a}', max(0.2, math.exp(-0.5 * ((tg - post_mag) / 1.2) ** 2) * 0.8)))
    if ('主让3' in layer or '受让3' in layer) and not any(int(x.split(':')[0]) + int(x.split(':')[1]) >= 4 for x in scores):
        _add(4, 4, 0)
    if '主让2' in layer and not any(int(x.split(':')[0]) - int(x.split(':')[1]) >= 2 for x in scores):
        _add(2, 2, 0)
    cands.sort(key=lambda x: -x[1])
    cands = cands[:top_n]
    tot = sum(w for _, w in cands)
    return [{'score': sc, 'weight': round(w / tot, 3)} for sc, w in cands]

def analyze(handi, league=None, o25=None, oh=None, od=None, oa=None, elo=None,
            inj_h=None, inj_a=None, bqc=None, cs=None, tg=None, direction='主胜'):
    layer = layer_key(handi)
    prior = get_prior(layer)
    if not prior:
        return {'status': 'no_prior', 'layer': layer}
    fs = [factor_o25(o25, layer), factor_euro_asia(oh, od, oa, handi), factor_elo(elo, layer),
          factor_league(league, layer), factor_injury(inj_h, inj_a, layer), factor_halftime(bqc, prior['magnitude_center']),
          factor_cs_low(cs), factor_total_goals(tg, prior['magnitude_center'])]
    post = bayesian_fusion(prior, fs)
    cands = dynamic_candidates(post['magnitude_center'], direction, layer)
    return {'status': 'ok', 'layer': layer, 'prior': prior['magnitude_center'], 'prior_conf': prior['confidence'],
            'posterior': post, 'candidates': cands,
            'factors': [{'name': x['name'], 'adjust': x['magnitude_adjust'], 'conf': x['confidence'], 'detail': x['detail']} for x in fs if x]}

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--handi', type=float, required=True)
    ap.add_argument('--league', default=None); ap.add_argument('--o25', type=float, default=None)
    ap.add_argument('--eu', default=None); ap.add_argument('--elo', type=float, default=None)
    ap.add_argument('--inj_h', type=float, default=None); ap.add_argument('--inj_a', type=float, default=None)
    ap.add_argument('--bqc', default=None); ap.add_argument('--cs', default=None); ap.add_argument('--tg', default=None)
    ap.add_argument('--direction', default='主胜')
    a = ap.parse_args()
    eu = a.eu.split(',') if a.eu else None
    r = analyze(a.handi, a.league, a.o25, *(map(float, eu) if eu else (None, None, None)),
                a.elo, a.inj_h, a.inj_a, a.bqc, a.cs, a.tg, a.direction)
    print(json.dumps(r, ensure_ascii=False, indent=2))
