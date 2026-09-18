# -*- coding: utf-8 -*-
"""calc_v3572.py — V3.5.72 R1-R18 确定性判定引擎（2026-08-24）
今日全部量化规则固化为可执行判定：输入比赛参数 → 查5表(odds/league/team/water/score) + R1-R18阈值判定
→ 输出每条 触发/不触发(原因)/无数据(原因) + 数值证据。模型只判断非确定性部分(伤停豁免机理/红牌预判)。

用法: python calc_v3572.py --div I1 --home Torino --away Milan --oh 4.10 --od 3.32 --oa 1.71 --o25 2.06 --u25 1.77 [--handi 0.5 --water 1.90 --form5_h 8 --inj 5]
"""
import json, os, argparse, sys
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')  # 🔴2026-09-04链路优化: 默认GBK控制台防UnicodeEncodeError崩溃/乱码
except Exception:
    pass


BASE = os.path.dirname(os.path.abspath(__file__))
def load(n):
    p = os.path.join(BASE, n)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}

LEAGUE = load('league_table.json')
TEAM = load('team_profiles.json')
WATER = load('water_table.json')
ODDS = load('odds_table.json')
LG_CODE = {'E0':'英超','SP1':'西甲','D1':'德甲','I1':'意甲','F1':'法甲','EC':'欧战/资格赛'}

# 🔴联赛归一化（2026-09-15 审计 P1 修复）—— 原 R 判定全依赖 a.div 精确匹配代码，
# 传 epl/laliga/中文名 等写法时 R1(超深盘档)/R4(意甲升权)/R10(欧战降档)/R16-R18(机制层) 全部静默失效。
_LG_TO_CODE = {
    '英超': 'E0', '西甲': 'SP1', '意甲': 'I1', '德甲': 'D1', '法甲': 'F1',
    'E0': 'E0', 'SP1': 'SP1', 'I1': 'I1', 'D1': 'D1', 'F1': 'F1',
    'epl': 'E0', 'premier': 'E0', 'premierleague': 'E0',
    'laliga': 'SP1', 'liga': 'SP1',
    'seriea': 'I1',
    'bundesliga': 'D1', 'bundes': 'D1',
    'ligue1': 'F1',
    '欧冠': 'EC', '欧联': 'EC', '欧协联': 'EC', '欧战': 'EC',
    'ec': 'EC', 'ucl': 'EC', 'uel': 'EC', 'uecl': 'EC', 'champions': 'EC',
}


def norm_div(x):
    """联赛归一化 → 内部代码 E0/SP1/I1/D1/F1/EC（2026-09-15审计修复·大小写与分隔符不敏感）"""
    if not x:
        return x
    s = str(x).strip()
    return _LG_TO_CODE.get(s) or _LG_TO_CODE.get(s.lower().replace(' ', '').replace('-', ''), s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--div', required=True, help='联赛代码 E0/SP1/D1/I1/F1/EC')
    ap.add_argument('--full', action='store_true', help='方向判定脚本化(P0-2): 输出方向概率+置信度+并列')
    ap.add_argument('--draw_score', type=float, default=0, help='修正53分组总分')
    ap.add_argument('--inj_h', type=float, default=0, help='主队伤停影响分')
    ap.add_argument('--inj_a', type=float, default=0, help='客队伤停影响分')
    ap.add_argument('--margin', type=int, help='比分深度查表: 净胜球(正=主胜)')
    ap.add_argument('--over25', type=float, help='比分深度查表: Over25赔率')
    ap.add_argument('--league_lookup', help='比分深度查表: 联赛代码(微调)')
    ap.add_argument('--home'); ap.add_argument('--away')
    ap.add_argument('--oh', type=float); ap.add_argument('--od', type=float); ap.add_argument('--oa', type=float)
    ap.add_argument('--o25', type=float); ap.add_argument('--u25', type=float)
    ap.add_argument('--handi', type=float, help='亚盘盘口(负=主让)'); ap.add_argument('--water', type=float, help='主水位(1.8-2.1体系)')
    ap.add_argument('--form5_h', type=int, help='主队近5场积分'); ap.add_argument('--inj', type=int, help='客队伤停人数')
    ap.add_argument('--cs_draw', type=float, help='欧盘13家CS最低平局比分赔率(如0:0/1:1)')
    a = ap.parse_args()
    a.div = norm_div(a.div)  # 🔴2026-09-15审计修复: 归一化→下游 R1/R4/R10/R16-R18 不再因写法差异静默失效
    if a.full and a.oh and a.od and a.oa:
        r = direction_full(a.oh, a.od, a.oa, a.o25, a.div, a.draw_score, a.inj_h, a.inj_a)
        print('🔴方向判定脚本化(P0-2·LLM仅确认): 主%.1f%% 平%.1f%% 客%.1f%% | 主方向=%s 置信度=%s 平局信号=%s 并列=%s' % (
            r['主胜'], r['平局'], r['客胜'], r['主方向'], r['置信度'], r['平局信号'], r['并列建议']))
        return
    if a.margin is not None and a.over25:
        r = score_depth_lookup(a.margin, a.over25, a.league_lookup)
        if r:
            print(f"🔴比分深度查表(v2.0·score_depth_table.json): 档位{r['bucket']}({r['bin']}) 主锚={r['anchor']}({r['anchor_pct']}%) 次锚={r['second']}({r['second_pct']}%) 第三={r['third']}({r['third_pct']}%) n={r['n']}{('·' + r['league_adjustment']) if r['league_adjustment'] else ''}")
        else:
            print('比分深度查表: 无数据')
        return
    out = []
    def emit(r, verdict, note, val=''):
        out.append(f'  R{r} [{verdict}] {note}' + (f' ({val})' if val else ''))
    div_name = LG_CODE.get(a.div, a.div)
    print(f'═══ V3.5.72 R1-R18 判定引擎 ═══ 联赛:{div_name} {a.home} vs {a.away}')
    # ── R1 HIGH分联赛 + R7 中深盘 + R10 欧战（Step1 置信度）──
    min_oh = a.oh if a.oh else 99; min_oa = a.oa if a.oa else 99
    deep_h = min_oh < 1.30; deep_a = min_oa < 1.30
    if deep_h or deep_a:
        if a.div in LG_CODE and a.div != 'EC':
            emit(1, '触发', '超深盘<1.30 五大联赛 → HIGH', f'主{min_oh}/客{min_oa}')
        else:
            emit(1, '触发', '超深盘<1.30 资格赛/小联赛 → 最高MID+平局升权(R1·平局爆冷37.5%)', f'主{min_oh}/客{min_oa}')
    else:
        emit(1, '不触发', '无超深盘(<1.30)')
    # 🔴R7/R8 欧盘口径(Matches.csv回测·正确单一来源·竞彩抽水12.8%会使档位偏移)
    for side, o in [('主', min_oh), ('客', min_oa)]:
        if o and 1.80 <= o < 2.10:
            emit(7, f'触发({side}胜1.80-2.10·欧盘口径)', '中深盘→强制MID-LOW(命中49.1%≈随机·需额外信号才MID)', str(o))
        elif o and 1.50 <= o < 1.80:
            emit(7, f'触发({side}胜1.50-1.80·欧盘口径)', '中深盘→最高MID(58.3%·非深盘不得HIGH)', str(o))
    if a.div == 'EC' and (deep_h or (a.oh and 1.3 <= a.oh < 1.8)):
        emit(10, '触发', '欧战深盘主胜→最高MID(EC 60.7%全类最低·vs英超65.7)', f'主赔{a.oh}')
    else:
        emit(10, '不触发', '非欧战深盘主胜场景')
    # ── R4 意甲客胜 + R5 弱旅主场 + R11 防平（Step4 先验）──
    if a.div == 'I1' and a.oa and 1.50 <= a.oa < 1.80:
        emit(4, '触发', '意甲客胜1.5-1.8→升权(62.6%五大最高·D1降级前必查)', str(a.oa))
    else:
        emit(4, '不触发', '非意甲客胜中深盘')
    if a.form5_h is not None and a.form5_h <= 5 and a.oh and a.oh < 2.0:
        emit(5, '触发', '弱旅主场(Form5≤5+主赔<2.0)→主胜60%不降不反向', f'Form5={a.form5_h} 主赔{a.oh}')
    else:
        emit(5, '不触发', '非弱旅主场条件')
    if a.oh and 1.80 <= a.oh < 2.10:
        emit(11, '触发', '主胜1.8-2.1防平优先(平28.4%>客22.5%·客冷门时平28.6%vs客18.8%·并列优先反向)', str(a.oh))
    else:
        emit(11, '不触发', '非主胜1.8-2.1档')
    # ── R2 伤停豁免 + R8 平局并列阈值（Step5 顺序）──
    if a.inj and a.inj >= 3 and a.oh and a.oa and a.oa < a.oh:
        emit(2, '触发', '客队伤停≥3+客胜升赔→真实防御·豁免D1背离降级(case69米兰5缺)', f'伤停{a.inj}')
    else:
        emit(2, '不触发', '无客队伤停≥3或非客胜场景')
    p_draw = (1/a.od) / (1/a.oh + 1/a.od + 1/a.oa) if a.od and a.oh and a.oa else 0
    if p_draw >= 0.28:
        emit(8, '触发', f'平局并列阈值P_平局≥28%满足({p_draw*100:.0f}%)·并列可触发但不得覆盖大样本主方向(客胜50.2%vs平27%·n=8703)')
    else:
        emit(8, '不触发', f'P_平局={p_draw*100:.0f}%<28%·并列不满足阈值(防过度平局化·case53/69/72)')
    # ── R12-R15 五大联赛档位（Step4.5 league_table）──
    lt = LEAGUE.get(f'{div_name}({a.div})') if div_name in '英超西甲德甲意甲法甲' else None
    if lt and a.oh:
        for tag, lo, hi in [('<1.3', 0, 1.3), ('1.3-1.5', 1.3, 1.5), ('1.5-1.8', 1.5, 1.8), ('1.8-2.1', 1.8, 2.1)]:
            if lo <= a.oh < hi:
                h = lt['主胜档→H/D/A'].get(tag)
                if h: emit(12, '查表', f'{div_name}主胜档{tag}→H{h[0]}%/D{h[1]}%/A{h[2]}%', f'league_table')
    # ── R13 球队特异性（Step4.5 team_profiles）──
    for t, side in [(a.home, '主'), (a.away, '客')]:
        if t and t in TEAM:
            p = TEAM[t]; tags = []
            if p['主客差'] >= 20: tags.append(f'主场龙+{p["主客差"]}pp')
            if p['主客差'] <= -12: tags.append(f'客场龙{p["主客差"]}pp')
            if p['平局'] >= 33: tags.append(f'平局王{p["平局"]}%')
            if p['大球率'] >= 65: tags.append(f'大球王{p["大球率"]}%')
            if p['大球率'] <= 35: tags.append(f'小球王{p["大球率"]}%')
            if p['赢1球'] >= 70: tags.append(f'赢1球{p["赢1球"]}%')
            if p['大胜3+'] >= 40: tags.append(f'大胜{p["大胜3+"]}%')
            if p['主胜'] >= 70: tags.append(f'主强{p["主胜"]}%')
            if p['主胜'] <= 30: tags.append(f'弱主{p["主胜"]}%')
            if tags: emit(13, '触发', f'{t}({side}): ' + '·'.join(tags), 'team_profiles')
        elif t:
            emit(13, '无数据', f'{t} 不在110队档案(升班马/新队·档案失效标注)', 'team_profiles')
    # ── R16-R18 机制层（红牌/零封/强度）──
    if a.div in ('SP1', 'I1'):
        emit(16, '触发', '西甲/意甲红牌率23%→深盘让球(≥1)易被打断→降权(case66马竞红牌2:2)', '红牌率23.3/22.7%')
    elif a.div in ('E0', 'D1', 'F1'):
        emit(16, '触发', f'红牌率{ {"E0":14.8,"D1":16.6,"F1":20.0}[a.div] }%→红牌打断风险低', 'R16')
    if a.div == 'F1':
        emit(17, '触发', '法甲零封率51%最高→主锚1:0/2:0权重升', '零封率51%')
    elif a.div == 'D1':
        emit(17, '触发', '德甲零封率44%最低→主锚≥3球(2:1/3:1)权重升', '零封率44%')
    else:
        emit(17, '不触发', '零封率中性(47-49%)')
    if a.div == 'D1':
        emit(18, '触发', '德甲对攻开放(射门25.2+犯规29.3+零封44%)→大球机制', '大球王基线56.7%')
    elif a.div == 'F1':
        emit(18, '触发', '法甲防守密(射门20+零封51%+黄牌3.0)→小球机制', '小球王基线45.2%')
    else:
        emit(18, '不触发', '强度中性')
    # ── 水位意图 + 欧亚背离（Step2）──
    if a.water and a.handi and -0.8 <= a.handi <= -0.45:
        wt = WATER.get('water_intent', {}).get('主让0.5-0.75', {})
        for k, v in wt.items():
            if '低水' in k and a.water < 1.85: emit('水位', '触发', f'主让0.5-0.75低水→主胜{v}%(防御·升档)', f'water_table 水{a.water}')
            if '高水' in k and a.water > 2.05: emit('水位', '触发', f'主让0.5-0.75高水→主胜{v}%(诱盘嫌疑·降级3-10pp)', f'water_table 水{a.water}')
    else:
        emit('水位', '不触发', '无亚盘水位数据或盘口不在0.5-0.75(量化需水位数据)')
    # ── R6/R9/score_table（Step6/7 联动提示）──
    if a.cs_draw and a.cs_draw < 4.5:
        emit(6, '触发', f'欧盘CS最低平局比分{a.cs_draw}<4.5→平局信号S8+1(case68 0:0 4.17被忽略教训)', str(a.cs_draw))
    if a.o25 and a.o25 < 1.7:
        emit(9, '触发', '大球强(O25<1.7)→主锚总进球≥3硬约束(大球率66%+)', str(a.o25))
    # ── 🔴净胜双出口硬约束（Step7·2026-08-27固化·case84/87/88执行不足教训·2026-08-28修正: 次锚覆盖净3+档·具体比分按大球深度精准判定非固定3:0/4:0）──
    if a.oh and a.oh < 1.5:
        if a.o25 and a.o25 < 1.7:
            emit('净胜双出口', '🔴数据驱动', f'深盘主{a.oh}<1.5+大球强(O25<1.7)→净3+=39%·🔴2026-08-29修正: 按档位数据覆盖(主胜3档次锚=4:1自然覆盖·主胜2球第三候选4:2=10.5%不强制升次锚·3:1=36.2%更高·主胜4+次锚5:0/5:1)·调score_depth_lookup查表+calc_poisson融合·废除一刀切强制·禁只锚净1/2', f'oh={a.oh} o25={a.o25}')
        else:
            emit('净胜双出口', '⚠️提示', f'深盘主{a.oh}<1.5·该档主净3+率应查r19_conditional_scores.json·主净3+≥20%→次锚覆盖净3+档(具体比分按大球深度选)', f'oh={a.oh}')
    elif a.oh and 1.8 <= a.oh < 2.1:
        emit('净胜双出口', '⚠️提示', f'主胜{a.oh}在1.8-2.1档·净3+=20%恰阈值·查r19表·主净3+≥20%→次锚考虑覆盖净3+档', f'oh={a.oh}')
    print('\n'.join(out))
    print('── 提示: calc_poisson.py 数值主模型须同步调用(主锚Top1/次锚Top2) + R3净胜出口 + score_depth_table查表+泊松融合(tie-break) ──')


# ── 🔴比分深度查表（2026-08-29·score_depth_table.json v2.0·23万场·九档位×5档Over25·替代粗糙score_table）──
def score_depth_lookup(margin, over25, league=None, odd_draw=None, win_odd=None, table_path=None):
    if odd_draw is None: odd_draw = 3.3   # 🔴容错(2026-08-29): D0档缺odd_draw→默认3.3·防KeyError
    """输入净胜球(正=主胜负=客胜,0=平)+Over25赔率+联赛代码 → 主锚/次锚/第三+条件概率
    联赛微调(德甲H1大球升权/法甲小球维持/欧冠3:2升权等)仅在 anchor-second 差<5pp 时生效"""
    import os, json
    path = table_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'score_depth_table.json')
    tbl = json.load(open(path, encoding='utf-8'))
    def bucket(m):
        if m >= 4: return 'H4+'
        if m == 3: return 'H3'
        if m == 2: return 'H2'
        if m == 1: return 'H1'
        if m == 0: return 'D0'
        if m == -1: return 'A1'
        if m == -2: return 'A2'
        if m == -3: return 'A3'
        return 'A4+'
    def sbin(ov):
        for k, v in tbl['over25_bins'].items():
            if v['min'] <= ov < v['max']: return k
        return 'S5'
    b, s = bucket(margin), sbin(over25)
    if b == 'D0' and odd_draw:
        db = 'DL' if odd_draw < 3.0 else ('DM' if odd_draw < 3.5 else 'DH')
        cell = tbl['buckets']['D0']['draw_bins'].get(db, {}).get(s)
        res_base = {'bucket': b, 'bin': s, 'draw_bin': db}
    else:
        w = 'W1' if (win_odd or 2.0) < 1.5 else ('W2' if (win_odd or 2.0) < 2.0 else 'W3')
        cell = tbl['buckets'][b]['win_bins'].get(w, {}).get(s)
        res_base = {'bucket': b, 'bin': s, 'win_bin': w}
    if not cell or not cell.get('n'):
        # fallback(D1·win_bin缺失时): 用 W2(中盘)同档格·再无可返回 None
        if b != 'D0':
            cell = tbl['buckets'][b]['win_bins'].get('W2', {}).get(s)
            if cell: res_base = {**res_base, 'win_bin': 'W2', 'fallback': 'win_bin缺失用W2'}
        if not cell or not cell.get('n'): return None
    res = {**res_base, 'anchor': cell['anchor'], 'anchor_pct': cell['anchor_pct'],
           'second': cell['second'], 'second_pct': cell['second_pct'],
           'third': cell['third'], 'third_pct': cell['third_pct'], 'n': cell['n'], 'league_adjustment': None}
    # F3(2026-08-29): 4+档泊松精细排序标记——主锚=查表anchor(4:0/0:4)·次锚/第三由泊松Top3排除主锚后选(4+档比分分散·查表仅定主锚·n样本有限)
    if b in ('H4+', 'A4+'):
        res['f3_poisson'] = True
        res['f3_note'] = '4+档: 主锚=查表' + str(cell['anchor']) + '·次锚/候选由calc_poisson Top3排除主锚后排序'
    # 联赛微调(报告第四节·仅差<5pp生效)
    if league and abs(cell['anchor_pct'] - cell['second_pct']) < 5:
        if league == 'D1' and b == 'H1' and s in ('S2','S3') and cell['anchor'] == '1:0':
            res['anchor'], res['second'], res['league_adjustment'] = '2:1', '1:0', '德甲主胜1球大球升权'
        elif league == 'F1' and b == 'H1' and s == 'S2' and cell['anchor'] == '1:0':
            res['league_adjustment'] = '法甲主胜1球维持1:0(小球属性·不切换)'
        elif league == 'EC' and b == 'H1' and s in ('S1','S2') and '3:2' == cell['third']:
            res['third'], res['league_adjustment'] = cell['third'], '欧冠主胜1球3:2升权'
        elif league == 'I1' and b == 'D0' and s in ('S3','S4') and cell['second'] == '0:0':
            res['league_adjustment'] = '意甲平局0:0略降权'
    return res


# ── 🔴M1 贝叶斯融合（2026-08-29·查表^α × 泊松^β·替代启发式阈值·α=样本量·β=收敛性）──
def fusion_score_depth(lookup_res, poisson_dist, alpha_max=1.0, beta=1.0):
    """贝叶斯融合: 后验 ∝ 查表概率^α × 泊松概率^β·归一化·输出融合Top3
    lookup_res: score_depth_lookup 输出(anchor/second/third+pct·收缩后)
    poisson_dist: calc_poisson score_dist 输出 [(score, p)]
    α = min(样本量/1000, alpha_max)·样本量大查表权重高·β=收敛性(converged=1)
    """
    if not lookup_res: return None
    n_cell = lookup_res.get('n', 500)
    alpha = min(n_cell / 1000.0, alpha_max)
    table_p = {}
    for k in ('anchor', 'second', 'third'):
        v = lookup_res.get(k)
        p = lookup_res.get(k + '_pct')
        if v and p is not None: table_p[v] = p / 100.0
    pois_p = {f'{k[0]}:{k[1]}': p for k, p in poisson_dist[:8]}
    cands = set(table_p) | set(pois_p)
    post = {}
    for sc in cands:
        tp = table_p.get(sc, 0.001) ** alpha
        pp = pois_p.get(sc, 0.001) ** beta
        post[sc] = tp * pp
    tot = sum(post.values())
    ranked = sorted(post.items(), key=lambda x: -x[1])[:3]
    return [{'score': s, 'post_pct': round(p/tot*100, 1)} for s, p in ranked]

# ── 🔴E4 跨档候选池扩展（2026-08-29·方向置信度低时跨档覆盖·防净胜档误判全失效）──
ADJ = {
    'H4+': [('H3', '3:0')], 'H3': [('H2', '2:0'), ('H4+', '4:0')],
    'H2': [('H1', '1:0'), ('H3', '3:0')], 'H1': [('D0', '1:1'), ('H2', '2:0')],
    'D0': [('H1', '1:0'), ('A1', '0:1')], 'A1': [('D0', '1:1'), ('A2', '0:2')],
    'A2': [('A1', '0:1'), ('A3', '0:3')], 'A3': [('A2', '0:2'), ('A4+', '0:4')],
    'A4+': [('A3', '0:3')],
}
def expand_candidates(bucket, confidence, core_cands):
    """E4: 方向置信度 HIGH=核心3候选·MID=+相邻档各1·MID-LOW/LOW=+相邻档各2(跨档)
    返回扩展候选池(标注来源)"""
    pool = list(core_cands)
    if confidence in ('HIGH', None): return pool
    adj = ADJ.get(bucket, [])
    if confidence == 'MID':
        for b2, sc in adj: pool.append({'score': sc, 'src': '相邻档'})
    elif confidence in ('MID-LOW', 'LOW'):
        for b2, sc in adj:
            pool.append({'score': sc, 'src': '相邻档'})
            for b3, sc3 in ADJ.get(b2, []): pool.append({'score': sc3, 'src': '跨2档'})
    return pool

# ── 🔴F1 红牌率融入（2026-08-29·联赛红牌率>20%+深盘+大球强→次锚向高比分偏移一档）──
RED_RATE = {'西甲': 29.0, '意甲': 27.0, '法甲': 23.8, '德甲': 17.3, '英超': 14.8}  # 张/100场·league_red_rate.json
def _weight_adjust(candidates, high_bias, strength):
    """方向性权重调整(2026-08-29修正·禁机械固定偏移): 按候选总进球加权重排——
    high_bias=True 高比分候选权重升(总进球≥3×1.2·≤1×0.85)·False 低比分权重升·具体比分由原候选池决定·非固定替换"""
    def goals(sc):
        try:
            h, a = sc.split(':')
            return int(h) + int(a)
        except: return 2
    out = []
    for c in candidates:
        g = goals(c.get('score', '1:1'))
        if high_bias:
            w = 1.2 if g >= 3 else (0.85 if g <= 1 else 1.0)
        else:
            w = 1.2 if g <= 1 else (0.85 if g >= 3 else 1.0)
        out.append({**c, 'weight': round(w * strength, 2)})
    out.sort(key=lambda x: -x.get('weight', 1))
    return out
def adjust_by_red(league_cn, win_odd, over25, candidates):
    """F1: 红牌率≥20+深盘(<1.8)+大球强(<1.8)→高比分候选加权·重排(方向性·禁机械1:0→2:1)"""
    rate = RED_RATE.get(league_cn, 0)
    if rate >= 20 and win_odd and win_odd < 1.8 and over25 and over25 < 1.8:
        return _weight_adjust(candidates, True, 1.3), True
    return candidates, False

# ── 🔴D5 球队攻防分层 + D4 半场先验（2026-08-29·融合层调整·不扩表）──
import os as _os, json as _json
_TEAM_AD = None
def _load_team_ad():
    global _TEAM_AD
    if _TEAM_AD is None:
        p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'team_attack_defense.json')
        _TEAM_AD = _json.load(open(p, encoding='utf-8'))
    return _TEAM_AD
def adjust_by_team_half(team_h, team_a, half_draw_prob, candidates):
    """D5/D4(2026-08-29修正·禁机械偏移): 方向性权重调整+重排——
    D5: 预期总进球>3.0→高比分候选加权·D4: 半场平≥45%→低比分候选加权·具体比分由原候选池+权重决定"""
    ad = _load_team_ad()
    th = ad.get(team_h, {}); ta = ad.get(team_a, {})
    changes = []
    if th and ta:
        exp = (th.get('gf',1.5) + ta.get('ga',1.2) + ta.get('gf',1.2) + th.get('ga',1.0)) / 2
        if exp > 3.0:
            candidates = _weight_adjust(candidates, True, 1.2)
            changes.append('D5: 预期总进球%.1f>3.0 高比分候选加权' % exp)
    if half_draw_prob is not None and half_draw_prob >= 0.45:
        candidates = _weight_adjust(candidates, False, 1.3)
        changes.append('D4: 半场平%d%%>=45 低比分候选加权' % (half_draw_prob*100))
    return candidates, changes

# ── 🔴P0-2 方向判定脚本化（2026-08-29·问题1评审·最大剩余风险·LLM仅确认）──
def direction_full(oh, od, oa, over25=None, league_div=None, draw_group_score=0.0, inj_score_h=0, inj_score_a=0, handi=None, home_water=None, official_dc=None):
    """🔴V3.5.73方向判定升级(2026-09-02·用户反馈机械依赖低赔): 赔率档基础 × 亚盘盘口深度校正 × 水位意图 → 综合方向
    数据: Matches 95144场——同低赔主胜1.3-1.8·浅让0.5-0.75实际主胜56.4%(诱主·欧亚背离)vs深让1.5+74.5%(真实)·差18pp
    逻辑: 欧盘低赔但亚盘浅让=庄家不敢开深·主队被高估(诱盘陷阱)·方向降权; 深让=真实·升权"""
    """方向判定脚本化: 输出方向概率(主/平/客)+置信度档+并列建议
    输入: 欧盘1x2 + 可选(Over25/联赛/修正53分组分/伤停影响分)
    逻辑: ①赔率档→实际H/D/A(odds_table·rule56/57) ②去水校准 ③修正53平局加权 ④伤停微调
    输出: 主/平/客概率·主方向·置信度档·平局并列建议——LLM仅确认禁反转(除非L2硬证据+标注)
    """
    import math
    # ① 去水+校准
    inv = [1/oh, 1/od, 1/oa]
    s = sum(inv)
    ph, pd, pa = [x/s for x in inv]
    try:
        calib = _json.load(open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'prob_calibration.json'), encoding='utf-8'))
        for k, v in calib.items():
            lo, hi = float(k.split('-')[0]), float(k.split('-')[1])
            if lo <= ph < hi: ph += v['bias_pp']/100; break
    except: pass
    # ② 修正53 平局加权（分组分≥2.5并列·≥4唯一）
    draw_adj = 0
    draw_signal = 'none'
    if draw_group_score >= 4 and pd >= 0.25:
        draw_adj = 0.08; draw_signal = 'sole'
    elif draw_group_score >= 2.5:
        draw_adj = 0.05; draw_signal = 'parallel'
    elif draw_group_score >= 1.5:
        draw_adj = 0.02; draw_signal = 'weak_parallel'
    pd = min(pd + draw_adj, 0.5)
    tot = ph + pd + pa
    ph, pd, pa = ph/tot, pd/tot, pa/tot
    # ③ 伤停微调（影响分≥4.0: 该队方向降档）
    if inj_score_h >= 4.0: ph = max(ph - 0.04, 0.05); pa = min(pa + 0.03, 0.6)
    if inj_score_a >= 4.0: pa = max(pa - 0.04, 0.05); ph = min(ph + 0.03, 0.7)
    tot = ph + pd + pa; ph, pd, pa = ph/tot, pd/tot, pa/tot
    # ④ 置信度档（strict口径: 主方向概率）
    main_p = max(ph, pd, pa)
    main_dir = '主胜' if ph == main_p else ('平局' if pd == main_p else '客胜')
    if main_p >= 0.62: conf = 'HIGH'
    elif main_p >= 0.52: conf = 'MID'
    elif main_p >= 0.45: conf = 'MID-LOW'
    else: conf = 'LOW'
    # 🔴欧亚盘口深度校正(2026-09-02·95144场: 低赔1.3-1.8×浅让56.4% vs 深让74.5%·差18pp)
    trap = []
    if handi is not None and 1.3 <= oh < 1.8 and main_dir == '主胜':
        if -0.85 <= handi <= -0.45:  # 低赔但浅让0.5-0.75
            conf = 'MID-LOW' if conf == 'HIGH' else ('LOW' if conf == 'MID' else conf)  # 降级
            trap.append(('欧亚背离: 主胜%.2f但仅让%.2f(浅·56.4%%实主<65%%基准)→诱主嫌疑·主胜降权') % (oh, -handi))
        elif handi <= -1.45:  # 深让1.5+真实
            trap.append(('欧亚一致: 主胜%.2f+深让%.2f(74.5%%实主)→真实·主胜可信') % (oh, -handi))
    if home_water and main_dir == '主胜' and home_water > 2.05:
        trap.append(('高水主让(%.2f): 诱主迹象·庄家收割主队筹码(低水56.1 vs 高水46.3·水位量化)') % home_water)
    # 🔴③.5 三层校准(V3.5.74·P0修复·2026-09-07·读 league-modules/league_calibration.json·数值微调不改main_dir/conf·不反转)
    #   联赛校准(5大联赛·主胜/平局校准pp级·校准=微调) + 欧战赛事校准(欧冠+3/欧联0/欧协联-2) + 欧战赔率档矩阵(7档·仅欧战)
    try:
        import os as _osl, json as _jsonl
        _lcf = _osl.path.join(_osl.path.dirname(_osl.path.dirname(_osl.path.abspath(__file__))), 'league-modules', 'league_calibration.json')
        if _osl.path.exists(_lcf):
            _lc = _jsonl.load(open(_lcf, encoding='utf-8'))['calibration']
            _is_eu = league_div in ('欧冠', '欧联', '欧协联', 'ec', 'ucl', 'uel', 'uecl')
            _nm = {'E0': '英超', 'SP1': '西甲', 'I1': '意甲', 'D1': '德甲', 'F1': '法甲',
                   '英超': '英超', '西甲': '西甲', '意甲': '意甲', '德甲': '德甲', '法甲': '法甲',
                   '欧冠': '欧冠', '欧联': '欧联', '欧协联': '欧协联'}
            _cn = _nm.get(league_div, '')
            if _cn in _lc:
                _c = _lc[_cn]
                if not _is_eu:  # 联赛层: 主胜校准/平局校准(比例→pp×100)
                    ph += (_c.get('主胜校准', 0) or 0) * 100 / 100
                    pd += (_c.get('平局校准', 0) or 0) * 100 / 100
                else:  # 欧战赛事层: hw_adj/draw_adj(pp)
                    ph += _c.get('hw_adj', 0) / 100
                    pd += _c.get('draw_adj', 0) / 100
            # 欧战赔率档矩阵(第3层·ph阈值档·方案1174场)
            if _is_eu:
                if main_p >= 0.55: ph += 0.014; pd -= 0.021
                elif main_p >= 0.45: ph += 0.054; pd -= 0.045
                elif main_p >= 0.35: ph += 0.045; pd -= 0.058
                elif main_p >= 0.25: ph += 0.014; pd += 0.003
                elif main_p >= 0.18: ph -= 0.072; pd += 0.075
                elif main_p >= 0.12: ph -= 0.053; pd += 0.044
                else: ph -= 0.026
            _tot3 = ph + pd + pa; ph, pd, pa = ph / _tot3, pd / _tot3, pa / _tot3
    except Exception:
        pass  # 校准失败不阻断
    # 并列建议
    second_p = sorted([ph, pd, pa])[1]
    parallel = 'yes' if (second_p - (main_p - 0.15)) > 0 and draw_signal in ('parallel','sole') else 'no'
    # 🔴执行提示(2026-08-30案例库102场首析机制化·不改变判定·仅把已固化规则执行提示确定性输出)
    hints = []
    if main_dir == '主胜' and (oh < 1.5 or (over25 and over25 < 1.7)):
        hints.append('H3+出口: 候选池需含3:0/4:0类(净胜双出口·2026-08-27固化·案例库H3+锚定仅6%执行不足)')
    if main_dir == '客胜' and 3.0 <= od <= 3.5:
        # 🔴O2回退(2026-09-02自查): 客胜实平23.7% < R8并列阈值28%·parallel保持'no'·仅提示防平·禁机械并列
        hints.append('客胜防平: 平赔3.0-3.5+客胜→平局参考(实平23.7%·未达R8 28%阈值·仅提示不并列·禁机械)')
    # 🔴LOW档修正方向(2026-09-02·用户要求提高三档准确率·案例库LOW 19场实主32%非主68%):
    #   LOW档(中盘+浅让诱主)判主基本必错→输出「修正方向: 防主胜」供LLM综合(档级校准·19场聚合+Matches浅让57%降级+用户授权·非单场机械反转)
    fix_dir = None
    if conf == 'LOW' and main_dir == '主胜' and handi is not None and -0.85 <= handi <= -0.45:
        fix_dir = '防主胜·倾向平/客(诱主LOW档·实主32%非主68%·反向参考)'
    # 🔴中盘细分(2026-09-02·用户要求提高MID/MID-LOW档·Matches 28327场):
    #   1.8-2.1模糊区主胜48%仍首选(禁反转)·细分价值=并列/防客提升any口径
    if main_dir == '主胜' and 1.8 <= oh < 2.1:
        if od < 3.2:
            hints.append(('中盘细分: 平赔%.2f<3.2→平局32%%(28327场·主48%%仍首选)·建议平局并列(any口径·R8 32%%>=28%%达标)') % od)
            if parallel == 'no':
                parallel = 'yes'  # 平32%>=R8阈值·并列合法
        if oa < 3.5:
            hints.append(('中盘细分: 客赔%.2f<3.5→客队强(客27%%·主降46%%)·防主·客胜次选') % oa)
    # 🔴O9小概率管理(2026-09-05·用户方法论·默认正常事件·猫腻微小冲突组合≥2才降档)
    #   超深盘爆冷为小概率(基础<1.2档12.2%·1.35-1.5档31.7%)·不因历史爆冷常态防御·仅盘面猫腻触发提示
    M = []
    if inj_score_h >= 15 and main_dir == '主胜':
        M.append('M1主队伤停≥15仍热门(盘面未降档·逆基本面·case129型)')
    if inj_score_a >= 15 and main_dir == '客胜':
        M.append('M1客队伤停≥15仍热门(盘面未降档·逆基本面·case129型皇马7缺)')
    if handi is not None:
        if main_dir == '主胜' and ph >= 0.70 and -1.0 < handi < 0:
            M.append('M2欧深亚浅(主隐%.0f%%但仅让%.2f·庄家不真信深盘)' % (ph*100, abs(handi)))
        if main_dir == '客胜' and pa >= 0.65 and 0 < handi < 1.0:
            M.append('M2欧深亚浅(客隐%.0f%%但客仅让%.2f·诱盘嫌疑)' % (pa*100, handi))
    if official_dc is not None and official_dc >= 45 and main_dir in ('主胜', '客胜'):
        M.append('M3官方背离(官方看冷双机会%d%%·市场资金反向·case128型)' % int(official_dc))
    if len(M) >= 2:
        sp_note = '🔴猫腻组合%d项→降档1级+并列提示: %s' % (len(M), '; '.join(M))
    elif len(M) == 1:
        sp_note = '⚠️猫腻观察(单信号·默认正常不降档·LLM综合M4诱阻/盘面判断): ' + M[0]
    else:
        sp_note = '正常(无盘面猫腻·默认按档位正常事件判定·爆冷为小概率不常态防御·M4诱阻见分类段·M5净胜需泊松)'
    # 🔴D规则(2026-09-07·V3.5.74数据驱动·Matches 22.75万实测复现·方案actuary分析验证):
    #   D1两端校准(实测: 超冷ph<0.2实际+3.9pp·大热0.7-0.8 +3.7pp·超深0.85+ -1.3pp)
    if ph < 0.20: ph += 0.030
    elif 0.70 <= ph < 0.85: ph += 0.030
    elif ph >= 0.85: ph -= 0.010
    _tot = ph + pd + pa; ph, pd, pa = ph/_tot, pd/_tot, pa/_tot
    #   D3赔率组合(实测: 主2.0×平2.5→平39.6%≈主40.9%平局追平·主2.5×平3.0→三方37.4/31.4/31.2均衡)
    if 1.9 <= oh <= 2.1 and 2.4 <= od <= 2.6:
        parallel = 'yes'; hints.append('D3赔率组合(主%.1f×平%.1f): 实测平39.6%%≈主40.9%%→平局并列(2026-09-07数据·n728)' % (oh, od))
    elif 2.4 <= oh <= 2.6 and 2.9 <= od <= 3.1:
        hints.append('D3赔率组合(主%.1f×平%.1f): 实测三方均衡37.4/31.4/31.2→主/平/客三方覆盖(n26086)' % (oh, od))
    #   D5亚盘深浅(实测: 深盘让2+净胜2+合计72%%大胜可信·浅盘让0.25-0.5赢盘45.5%%防下/防平)
    if handi is not None:
        if handi <= -2.0 and main_dir == '主胜':
            hints.append('D5深盘(让%.2f): 实测净胜2+概率72%%→净胜双出口/大胜可信' % abs(handi))
        elif -0.5 < handi < 0 and main_dir == '主胜':
            hints.append('D5浅盘(让%.2f): 实测赢盘45.5%%(防下盘)·平局风险升(净胜+0.4≈盘口)' % abs(handi))
    #   D6平手/客浅高水(实测: 赢盘率43.3%%<45%%→诱上·主胜降权)
    if handi is not None and -0.3 <= handi <= 0.3 and home_water and home_water > 1.0 and main_dir == '主胜':
        hints.append('D6平手/客浅高水(%.2f): 实测赢盘率43.3%%→诱上嫌疑·主胜降权考虑' % home_water)
        if conf == 'HIGH': conf = 'MID-HIGH'
    # 🔴P0-2置信度标签(2026-09-06·V3.5.74): LOW诱主修正=反向高命中·区分原始档
    conf_label = 'LOW-反向高命中(诱主修正·实非主68%)' if (conf == 'LOW' and fix_dir) else conf
    # 🔴P1-1 MID-LOW专项(2026-09-06·V3.5.74·保守提示级·禁自动降档/强制并列——方向判定权归LLM):
    #   MID-LOW 52.9%最弱档·模糊区默认并列参考+欧亚背离提示(仅hint·不改conf/parallel)
    if conf == 'MID-LOW':
        if handi is not None and main_dir == '主胜' and abs(ph - (0.56 if abs(handi) >= 0.5 else 0.48)) > 0.05:
            hints.append('MID-LOW欧亚背离提示: 主隐%.0f%% vs 亚盘让%.2f档期望——背离超5pp·考虑降档LOW或并列(诱盘嫌疑·LLM定)' % (ph*100, abs(handi)))
        if draw_group_score >= 1.0:
            hints.append('MID-LOW平局加权: 平局分组%.1f分→弱并列参考(此档平局率偏高·LLM综合)' % draw_group_score)
        if '并列' not in str(hints):
            hints.append('MID-LOW模糊区: 默认并列参考(不单选·此档单选命中52.9%·LLM定并列与否)')
    return {'主胜': round(ph*100, 1), '平局': round(pd*100, 1), '客胜': round(pa*100, 1),
            '主方向': main_dir, '置信度': conf, '置信度标签': conf_label, '平局信号': draw_signal, '并列建议': parallel,
            '诱盘信号': trap, '执行提示': hints, '修正方向': fix_dir, '小概率管理': sp_note,
            '依据': 'odds_table档位校准+修正53分组分%.1f+伤停影响分H%d/A%d' % (draw_group_score, inj_score_h, inj_score_a)}

if __name__ == "__main__":
    main()

# ── 🔴净胜档多档候选（2026-08-29深入评估优化·替代泊松Top1单档·2万场+26.4pp）──
MARGIN_CAND = {
    'H4+': [4, 3], 'H3': [3, 2], 'H2': [2, 1], 'H1': [1, 2, 0],
    'D0': [0, 1, -1], 'A1': [-1, 0], 'A2': [-2, -1], 'A3': [-3, -2], 'A4+': [-4, -3],
}
def margin_candidates(handi):
    """亚盘盘口→净胜档多档候选(主档+相邻档·E4跨档思想·替代泊松Top1单档)
    依据: Matches 2万场评估——泊松Top1单档21.1% vs 亚盘多档47.4%(+26.4pp·81%押1:1失效)
    输入: handi=亚盘盘口(负=主让·如-1.0)
    返回: [净胜档列表·如[-1,0]客胜1球+平局]"""
    if handi is None: return [0]  # 无亚盘→平局档保守
    if handi <= -2.0: return MARGIN_CAND['H4+']
    if handi <= -1.6: return MARGIN_CAND['H3']
    if handi <= -1.2: return MARGIN_CAND['H2']
    if handi <= -0.85: return MARGIN_CAND['H1']
    if handi <= -0.45: return MARGIN_CAND['D0']  # 主让0.5-0.75→平局候选
    if handi <= -0.05: return MARGIN_CAND['D0']  # 主让0.25/0.1→浅让平局候选(2026-08-29修复: 原误判A1)
    if handi < 0.45: return MARGIN_CAND['D0']    # 客让0.1-0.4→浅让平局候选
    # 🔴2026-09-15审计P0修复: 受让盘分支缺失——原 handi>=0.45 一律返回 A1(客胜1球+平)，
    # 致受让1.5/2/2.5等深盘净胜档严重低估(实测 Elche vs 皇马 受让2.0 误判净[-1,0]·实应客胜3-4球)
    if handi >= 2.0: return MARGIN_CAND['A4+']   # 受让2+ → 客胜3-4球(镜像 让2+ = H4+)
    if handi >= 1.6: return MARGIN_CAND['A3']    # 受让1.75 → 客胜2-3球(镜像 H3)
    if handi >= 1.2: return MARGIN_CAND['A2']    # 受让1.25-1.5 → 客胜1-2球(镜像 H2)
    if handi >= 0.85: return MARGIN_CAND['A1']   # 受让1.0 → 客胜1球+平(镜像 H1)
    return MARGIN_CAND['D0']                     # 受让0.5-0.75 → 平局候选

# ── 🔴O1比分量级硬约束（2026-09-02批量回测固化·118场: 方向✅比分❌48场中50%净胜≥3·真实净3+仅6.9%锚定）──
def score_pool_with_big(po, oh, o25, top=4):
    """深盘主胜+大球强 → 候选池必含净3+比分（O1固化·替代仅执行提示）
    依据: 批量回测118场——净胜双出口规则已固化但执行不足·方向✅比分❌50%错因净≥3·
         深盘(<1.6)+大球强(O2.5<1.8)场景下真实净3+概率高(R19: 悬殊>50pp净3 28%)
    输入: po=score_dist排序列表·oh=主胜赔率·o25=Over25赔率·top=候选数
    返回: 调整后候选池(含净3+·按泊松概率排序·不改变概率只注入出口)"""
    if oh >= 1.6 or (o25 and o25 >= 1.8): return po[:top]
    pool = list(po[:top])
    has_big = any(k[0]-k[1] >= 3 for k, p in pool)
    if has_big: return pool
    # 注入最高概率净3+比分(3:0/4:0/4:1/5:0·不改变原概率·排在候选池第3位之后)
    big3 = [k for k, p in po if k[0]-k[1] >= 3]
    if big3:
        inject = big3[0]
        # 🔴注入第3参考位·不进主锚次锚(防机械锚定·尊重概率排序·不提升命中口径·仅执行提示数据化)
    pool = pool[:2] + [inject] + [k for k in pool[2:] if k != inject][:top-3]
    return pool[:top]

# ── 🔴总进球档查表（V3.5.74·2026-09-15升级·148397场·goal_bins_table.json·O2.5→总进球档+净3+概率+典型比分）──
_GOAL_BINS = None
def goal_bin_probs(o25):
    """O2.5赔率→总进球档概率(0-1/2/3/4+球)+净胜3+概率+典型比分Top4·数据驱动查表(替代主观λ判断)
    依据: Matches 148,397场分箱(2026-09-15全量重建·旧表80000场子集·数字差异≤1.3pp)——
          O2.5=1.00-1.30→4+球59.2%/净3+46.0%·1.30-1.50→45.8%/29.7%·1.50-1.70→36.4%/20.3%·
          1.90-2.10→25.5%/12.0%·2.30-2.60→17.8%/8.2%·2.60+→13.2%/7.4%
    典型比分: 每档 top4(2:0/3:0 大胜型 vs 1:1/1:0 小球型)——供 Step7 候选池分配(数据驱动非机械注入)
    用法: Step6大球深度/Step7比分量级→查此表定档位分布→候选池按档位概率+典型比分分配
    返回: dict(prob_01, prob_2, prob_3, prob_4, net3, top, band)·无表→None(标注无数据)"""
    global _GOAL_BINS
    if _GOAL_BINS is None:
        import os, json as _json
        fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'goal_bins_table.json')
        try: _GOAL_BINS = _json.load(open(fp, encoding='utf-8'))
        except: _GOAL_BINS = {}
    if not _GOAL_BINS or o25 is None: return None
    best = None
    for band, v in _GOAL_BINS.items():
        lo, hi = map(float, band.split('-'))
        if lo <= o25 < hi: best = v; break
    if best is None:  # 超表边界(2026-09-09批检修复: 归最近档防静默None·2026-09-15末档改开区间后仅极值触发)
        _bands = sorted(_GOAL_BINS.items(), key=lambda x: float(x[0].split('-')[0]))
        if _bands:
            if o25 >= float(_bands[-1][0].split('-')[1]):
                best, band = _bands[-1][1], _bands[-1][0]
            elif o25 < float(_bands[0][0].split('-')[0]):
                best, band = _bands[0][1], _bands[0][0]
            else:
                return None
        else:
            return None
    return {'prob_01': best['g01']/100, 'prob_2': best['g2']/100, 'prob_3': best['g3']/100,
            'prob_4': best['g4']/100, 'net3': best['net3']/100,
            'top': best.get('top') or [], 'n': best.get('n'), 'band': band}



# ── 🔴盘口诱阻识别模块（2026-09-02·诱阻识别文档落地·核心三函数）──
# 原则: 先分类(正常/模糊/庄家主导·70%正常不硬套) → 庄家主导才7维意图分析
# 铁律: 只调置信度1档·永不反转L2方向·无数据指标标0不算分(防假精度)

def true_handicap_calculator(elo_diff=None, home_adv=0.0, inj_h=0, inj_a=0, form_h=0, form_a=0):
    # 🔴2026-09-07实测降权: 控制赔率后ELO残差对结果影响<1.4pp(无预测力·方案发现3复现)·本函数输出=参考信息·不参与方向/诱盘判定(诱盘判定须用离散度/水位/资金动态)
    """真实实力盘计算(文档5.4.1·线性近似): ELO差100≈0.25球 + 主客场0.25 + 伤停±0.1/缺
    输入: elo_diff=主队ELO-客队ELO(正=主强)·inj_h/a=伤停影响分(0-5)·form差
    返回: 真实实力盘(正=主让·负=主受让) + 置信度·无ELO→None"""
    if elo_diff is None:
        return None, 0.3  # 无ELO→低置信近似
    h = elo_diff / 400.0 + home_adv + (inj_a - inj_h) * 0.1
    conf = min(0.5 + abs(elo_diff) / 400.0, 0.9)
    return h, conf

def match_classifier(oh, od, oa, handi=None, true_handi=None, water=None, kelly=None, multi_std=None):
    """比赛分类器(文档6.2·8项异常指标·每项1分):
    可得指标: 盘口背离|盘口-真实实力盘|>0.25球 · 水位异常(热方>0.95或<0.75) · 欧亚背离(欧赔主胜隐含 vs 亚盘盘口隐含差>5%)
            凯利异常(>1.0或<0.85) · 多源std>3%
    不可得(无初盘/临场变动): 盘口变动/水位变动 → 标"无数据"不算分
    返回: match_type(normal/ambiguous/bookmaker_driven) + total_score + 各指标得分"""
    import math
    scores = {}
    details = []
    # ① 欧亚背离: 欧赔主胜隐含 vs 亚盘盘口映射(盘口→主胜概率近似: 0.5球55%/0.75球60%/1球65%/1.5球75%)
    if handi is not None and oh:
        inv = 1/oh + 1/od + 1/oa
        ep = 1/(oh*inv)
        ah = {0.25: 0.48, 0.5: 0.56, 0.75: 0.61, 1.0: 0.66, 1.25: 0.70, 1.5: 0.75, 1.75: 0.80, 2.0: 0.85}.get(abs(handi), 0.55)
        if handi < 0: ah = 1 - ah  # 主受让
        dev = abs(ep - ah)
        scores['euro_asia'] = 1 if dev > 0.05 else 0
        if dev > 0.05: details.append('欧亚背离%.0f%%(欧赔主%.0f%% vs 亚盘主%.0f%%)' % (dev*100, ep*100, ah*100))
    # ② 盘口背离(真实实力盘)
    if handi is not None and true_handi is not None:
        d = abs(handi - true_handi)
        scores['handi_dev'] = 1 if d > 0.25 else 0
        if d > 0.25: details.append('盘口背离%.2f球(实盘%.2f vs 真实%.2f)' % (d, handi, true_handi))
    # ③ 水位异常(单时点·降级: 无初盘对比)
    if water is not None:
        scores['water'] = 1 if (water > 0.95 or water < 0.75) else 0
        if water > 0.95: details.append('高水%.2f(热门方>0.95·诱盘信号)' % water)
        elif water < 0.75: details.append('低水%.2f(<0.75·阻盘/真实看好)' % water)
    # ④ 凯利异常
    if kelly is not None:
        k = max(kelly.values()) if isinstance(kelly, dict) else kelly
        scores['kelly'] = 1 if (k > 1.0 or k < 0.85) else 0
        if k > 1.0: details.append('凯利%.2f>1.0(庄家赔付风险·该方向可能不打出)' % k)
    # ⑤ 多源std(双源降级·仅标)
    if multi_std is not None:
        scores['multi'] = 1 if multi_std > 0.03 else 0
    total = sum(scores.values())
    if total >= 3:
        mt = 'bookmaker_driven'; conf = min(total/5.0, 1.0)
    elif total >= 1:
        mt = 'ambiguous'; conf = total/3.0
    else:
        mt = 'normal'; conf = 0.0
    return {'match_type': mt, 'confidence': round(conf, 2), 'total_score': total,
            'anomaly_scores': scores, 'anomaly_details': details,
            '无数据指标': ['盘口变动(需初盘+临场)', '水位变动(需初盘+临场)']}

def handicap_intent_analyzer(cf, direction, trap_signals, fundamental_dir=None, o25=None, draw_odd=None, totals_line=None):
    """庄家意图分析器(文档6.3·诱阻识别):
    输入: cf=classifier输出·direction=方向判定(含诱盘信号)·trap_signals=欧亚/水位信号·fundamental_dir=基本面方向
    逻辑: 庄家主导时·诱盘信号反向=真实方向·阻盘信号同向=真实方向·至少证据同向才输出
    返回: intent_type + true_direction + confidence + votes"""
    if cf['match_type'] != 'bookmaker_driven':
        return None  # 正常/模糊不分析意图(70%正常不硬套)
    votes = []
    # trap_signals 是 direction_full 的诱盘信号列表(欧亚背离/高水)
    for s in (trap_signals or []):
        if '欧亚背离' in s or '高水' in s or '诱主' in s:
            votes.append(('诱上', '主胜降权·防冷'))
        if '诱客' in s:
            votes.append(('诱下', '客胜降权'))
    if fundamental_dir:
        votes.append(('基本面', fundamental_dir))
    # 投票统计: 至少2条证据同向(数据可得受限·降级为2·文档3维·实际数据2-3源)
    # 降级门槛: classifier总分>=3(庄家主导确证) + 至少1条方向性诱盘信号 → 输出意图
    # (文档理想3维·实际免费数据1-2源·降级为 classifier总分3 + 信号1条)
    # 🔴9类意图扩展(2026-09-02文档3.1/3.2补全): 诱平(平赔<3.0超买)·诱大球(大小球高开大球低水)/诱小球(低开小球低水)·阻大球(大球高水升)/阻小球
    if o25 is not None:
        if o25 < 1.5: votes.append(('诱大球', '大球低水强·诱大球→真实小球倾向(防守场)'))
        elif o25 > 2.2 and draw_odd and draw_odd < 3.0: votes.append(('诱小球', '小球高水+平赔低·诱小球'))
    if draw_odd is not None and draw_odd < 2.9:
        votes.append(('诱平', '平赔%.2f超买·诱平→真实分胜负' % draw_odd))
    if len(votes) >= 1 and cf['total_score'] >= 3:
        # 意图优先级: 诱平(强超买)>诱上/诱下(欧亚)>大小球(辅助)
        if any(v[0] == '诱平' for v in votes) and draw_odd and draw_odd < 2.8:
            intent = '诱平'; true_dir = '真实分胜负(主或客)·防平局陷阱'
        elif any(v[0] == '诱大球' for v in votes):
            intent = '诱大球'; true_dir = '真实小球倾向(大球低水吸引·防守场)'
        elif any(v[0] == '诱小球' for v in votes):
            intent = '诱小球'; true_dir = '真实大球倾向(小球被低开)'
        elif any(v[0] == '诱上' for v in votes):
            intent = '诱上'; true_dir = '防主胜(主队难赢盘·倾向平/客/输盘)'
        elif any(v[0] == '诱下' for v in votes):
            intent = '诱下'; true_dir = '主胜可信(赢盘)'
        else: intent = 'balanced'; true_dir = direction
        return {'intent_type': intent, 'true_direction': true_dir, 'confidence': round(min(len(votes)/3.0, 0.7), 2),
                'dimension_votes': dict(votes), 'vote_count': len(votes), 'reasoning': '庄家主导(总分%d)+诱盘信号%d条→意图%s' % (cf['total_score'], len(votes), intent)}
    return {'intent_type': 'balanced', 'true_direction': direction, 'confidence': 0.0, 'dimension_votes': dict(votes), 'vote_count': len(votes),
            'reasoning': '非庄家主导或诱盘信号不足·不调整'}

# ── 🔴诱阻识别辅助模块补全（2026-09-02·文档P1/P2缺失补齐·维度1-7独立函数）──
# 全部无数据降级返回None·禁假精度

def odds_anomaly_detector(odds_list, label_list=None):
    """维度1·多源赔率异常检测(文档4.1): 输入各源某方向赔率列表→异常源(与均值差>5%)
    免费数据1-2源·2源时仅标分歧·3源+才有异常判定"""
    if not odds_list or len(odds_list) < 3:
        return {'anomaly': '无数据(需3源+)' if len(odds_list) < 3 else 'ok', 'sources': len(odds_list)}
    mean = sum(odds_list)/len(odds_list)
    anomalies = []
    for i, o in enumerate(odds_list):
        if abs(o-mean)/mean > 0.05:
            anomalies.append({'源': label_list[i] if label_list else i, '赔率': o, '偏差': '%.1f%%' % (abs(o-mean)/mean*100)})
    return {'anomaly': anomalies if anomalies else '一致', 'mean': round(mean, 3), 'sources': len(odds_list)}

def euro_asia_consistency(oh, od, oa, handi):
    """维度2·欧亚一致性独立(文档4.2): 欧赔主胜隐含 vs 亚盘盘口隐含→背离值+方向
    背离>5%→以亚盘为准(亚盘更接近真实意图)·欧赔高=欧赔诱"""
    if not (oh and handi is not None): return None
    inv = 1/oh + 1/od + 1/oa
    ep = 1/(oh*inv)
    ah = {0.25: 0.48, 0.5: 0.56, 0.75: 0.61, 1.0: 0.66, 1.25: 0.70, 1.5: 0.75, 1.75: 0.80, 2.0: 0.85}.get(abs(handi), 0.55)
    if handi < 0: ah = 1 - ah
    dev = ep - ah
    if abs(dev) > 0.05:
        return {'背离': '欧赔高估%.0f%%(欧赔诱主·以亚盘为准)' % (dev*100) if dev > 0 else '亚盘高估%.0f%%(主队被低估)' % (-dev*100),
                '欧赔主胜隐含': round(ep, 3), '亚盘主胜隐含': round(ah, 3), '一致': False}
    return {'背离': '一致(差%.0f%%≤5%)' % (abs(dev)*100), '欧赔主胜隐含': round(ep, 3), '亚盘主胜隐含': round(ah, 3), '一致': True}

def water_level_anomaly(water_init, water_live, side='热门'):
    """维度3·水位异常检测(文档4.3·初盘+临场): 临场>0.95高水诱盘·<0.75低水阻盘·变动>+0.1升水诱盘/<-0.1降水真实
    无初盘→单时点降级(>0.95诱/<0.75阻·标降级)"""
    if water_live is None: return None
    if water_init is None:
        tag = '高水诱盘信号' if water_live > 0.95 else ('低水阻盘/真实看好' if water_live < 0.75 else '水位正常')
        return {'标签': tag + '(单时点·无初盘降级)', '临场水位': water_live}
    chg = water_live - water_init
    if water_live > 0.95 or chg > 0.1: tag = '高水/升水·诱盘信号(庄家不怕热门打出)'
    elif water_live < 0.75 or chg < -0.1: tag = '低水/降水·真实看好(庄家降赔付)'
    else: tag = '水位正常'
    return {'标签': tag, '初盘': water_init, '临场': water_live, '变动': round(chg, 2)}

def handicap_movement_analyzer(h_init, h_live, w_init=None, w_live=None):
    """维度4·盘口变动模式(文档4.4): 升盘>0.25·降盘>0.25·三段式(需初盘+临场)
    升盘+上盘低水=阻上(真实看好)·升盘+高水=诱下·降盘+高水=诱上·降盘+低水=阻下
    无初盘→None(降级)"""
    if h_init is None or h_live is None: return None
    chg = h_live - h_init
    if abs(chg) <= 0.25: return {'模式': '稳定盘(变动≤0.25·正常或意图不明显)', '变动': chg}
    if chg > 0.25:  # 升盘
        mode = '升盘+低水=阻上(吓退上盘·真实看好)' if (w_live and w_live < 0.9) else '升盘+高水=诱下(吸引下盘)'
    else:
        mode = '降盘+高水=诱上(上盘变便宜·诱主)' if (w_live and w_live > 0.9) else '降盘+低水=阻下'
    return {'模式': mode, '变动': '%.2f球(%s盘)' % (abs(chg), '升' if chg > 0 else '降'), '初盘': h_init, '临场': h_live}

def kelly_index_analyzer(kelly_dict):
    """维度6·凯利指数分析(文档4.6): >1.0赔付风险高(方向可能不打出)·<0.85庄家赚(可能打出)
    需投注比例·无则用赔率倒数归一近似·无数据→None"""
    if not kelly_dict: return None
    out = {}
    for k, v in kelly_dict.items():
        if v > 1.0: out[k] = {'凯利': round(v, 3), '标签': '赔付风险高·该方向可能不打出'}
        elif v < 0.85: out[k] = {'凯利': round(v, 3), '标签': '赔付风险低·该方向可能打出'}
        else: out[k] = {'凯利': round(v, 3), '标签': '正常区间'}
    return out

def jingcai_special_signal(jc_odds, intl_odds):
    """维度7·竞彩特殊信号(文档4.7): 竞彩某方向比国际低>5%=竞彩控制赔付=真实看好·以竞彩方向为准
    需竞彩txt vs 欧盘·无竞彩→None"""
    if not jc_odds or not intl_odds: return None
    signals = []
    for direction in ('主', '平', '客'):
        if direction in jc_odds and direction in intl_odds:
            jp = 1/jc_odds[direction]; ip = 1/intl_odds[direction]
            if jp > ip * 1.05:
                signals.append('%s方向竞彩低%.0f%%(竞彩控制赔付·真实看好%s)' % (direction, (jp/ip-1)*100, direction))
    return {'信号': signals or '竞彩与国际一致', '说明': '竞彩有信息优势·变动滞后但幅度大时信号强'}

def fusion_score_4way(odd_prior_top5=None, poisson_top=None, table_top3=None, cs_probs=None,
                       alpha_prior=0.30, alpha_poisson=0.25, alpha_table=0.20, alpha_cs=0.25):
    """四方融合比分参考(V3.5.74·2026-09-07): 赔率先验30%+泊松25%+查表20%+CS盘25%
    🔴已冗余标注(2026-09-07评审): 功能已被 live_score_engine.bayesian_fusion(现场多源·含半场反推/CS深度) 替代——live引擎已接入calc_all预测链·本函数保留仅作单场手动/研究参考·不参与主流程
    🔴主锚判定铁律: calc_poisson+查表+本场数据驱动·非机械锚定(O8)·16格先验表(odds_score_prior.json)仅区间校验/tie-break(概率差<2pp)·反概率依赖(V3.5.65)
    无CS→CS权重均分·返回Top5[{score,pct,src}]"""
    import math
    def _p(items):
        out={}
        for it in (items or []):
            if isinstance(it,(list,tuple)) and len(it)>=2 and isinstance(it[0],str): out[it[0]]=float(it[1])/100
            elif isinstance(it,dict): out[it.get('score','')]=float(it.get('pct',0))/100
        return out
    pp,po,pt,pc=_p(odd_prior_top5),_p(poisson_top),_p(table_top3),_p(cs_probs or {})
    if not pc:  # 无CS均分
        alpha_prior+=0.08; alpha_poisson+=0.07; alpha_table+=0.10; alpha_cs=0
    cands=set(pp)|set(po)|set(pt)|set(pc)
    post={}
    for sc in cands:
        if not sc: continue
        v=(max(pp.get(sc,1e-4),1e-6)**alpha_prior*max(po.get(sc,1e-4),1e-6)**alpha_poisson*
           max(pt.get(sc,1e-4),1e-6)**alpha_table*max(pc.get(sc,1e-4),1e-6)**alpha_cs)
        post[sc]=v
    tot=sum(post.values())
    top=sorted(post.items(),key=lambda x:-x[1])[:5]
    return [{'score':sc,'pct':round(v/tot*100,1),'src':[k for k,dd in (('先验',pp),('泊松',po),('查表',pt),('CS',pc)) if sc in dd]} for sc,v in top]
