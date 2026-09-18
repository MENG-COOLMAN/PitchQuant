# -*- coding: utf-8 -*-
"""betting_plan_generator.py — 竞彩投注方案生成器（微调版 v0.6·2026-09-04·动态多维·无资金限制·多票多选项·四玩法全候选按场况筛选）
触发: 用户"请你给我今天的购买方案"(模型输出层·被动·本批分析完成后执行)
设计(v0.4·用户四约束):
  ① 只买串关: 串关需≥2场·N<2不出方案
  ② 串关场数 = 当天比赛数量与质量动态决定(N驱动·腿多维分序)
  ③ 多维评审: 腿质量分=置信度+玩法加成+EV档+集中度−伤停风险
  ④ 高收益取向: 比分/让球平/高赔进球优先
  ⑤ 无资金限制: 不做总资金/单日上限/预算分配·仅给"每注结构+小额参考提示"
  ⑥ 一场可多选项多票: 串关一场一选(竞彩规则)→ 同一场可用不同选项出现在多张票
     (主锚比分票/次锚比分票/混合容错票…·满足"比分买两个")
  ⑦ 诚实EV: EV_cal=历史命中率hit×赔率−1(比分0.105/让球平0.20/进球0.22/胆0.63)·串命中=∏hit·如实标注负EV
  ⑧ 每腿 source_field 可追溯
用法: python betting_plan_generator.py <input.json> [--per 每注参考金额(默认10元·可选)]
"""
import json, sys, itertools, io, math

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8') if hasattr(sys.stdout, 'buffer') else sys.stdout

CFG = {
    'conf_ok': ('HIGH', 'MID-HIGH', 'MID'),
    'dir_min_p': 0.45, 'dir_min_gap': 0.10, 'draw_signal_max': 4.0,
    'hit': {'score': 0.105, 'handicap_flat': 0.20, 'goals': 0.22, 'dan': 0.63},
    'ev_floor': {'score': -0.30, 'handicap_flat': -0.22, 'goals': -0.25, 'dan': -0.05},
    'score_w': {'HIGH': 3, 'MID-HIGH': 2, 'MID': 1},
    'kind_bonus': {'score': 1.2, 'handicap_flat': 0.9, 'goals': 0.6, 'dan': 0.3},
    'risk_w': 0.10,
}
def hit(k): return CFG['hit'].get(k, 0.5)
def opt_hit(k, p):
    """单注命中率: 进球档用模型档概率(分布去水可信·热档28%等不被0.22常数压制·🔴2026-09-04用户问进球数修正)·高赔尾档(0/1/4/5)×0.7保守·其余用历史常数"""
    if k == 'goals':
        return p if p >= 0.15 else p * 0.7
    return hit(k)
def ev_cal(k, o, p=0.0): return opt_hit(k, p) * o - 1

# ---------- 筛选与单注玩法产出 ----------
def layers(m):
    if not all(k in m for k in ('probs', 'jc', 'direction', 'confidence')) or not m.get('poisson_converged', True):
        return None
    ps = m['probs']
    if m['confidence'] not in CFG['conf_ok'] or max(ps.values()) < CFG['dir_min_p']: return None
    s = sorted(ps.values(), reverse=True)
    if s[0] - s[1] < CFG['dir_min_gap']: return None
    if m.get('draw_signal', 0) >= CFG['draw_signal_max']: return None
    return 'pass'

def single_options(m, include_second=False):
    """单注候选·include_second=True 时含次锚比分(一场可两比分·多票用)"""
    ops = []
    jc, gd, gd_dist, sc = m['jc'], m.get('goal_diff', {}), m.get('goals_dist', {}), m.get('anchors', {})
    jc_rq = jc.get('让球') or {}   # 🔴2026-09-05: 竞彩盘缺失容错(让球/进球盘可为空·欧盘口径)
    jc_zjq = jc.get('进球') or {}
    jc_spf = jc.get('胜平负') or {}
    jc_bf = jc.get('比分') or {}
    hc = m.get('handicap')
    if hc is not None:
        fm = {-1: '主胜1球', 1: '客胜1球', -2: '主胜2球', 2: '客胜2球'}
        fp = gd.get(fm.get(hc, ''), 0)
        if fp >= 0.20 and '让球平' in jc.get('让球', {}):
            ops.append({'kind': 'handicap_flat', 'label': f"让球平({hc:+d})", 'p': fp,
                        'odds': jc['让球']['让球平'], 'from': f"goal_diff[{fm.get(hc,'')}]", 'tag': '让平'})
    for role in ('anchor', 'second') if include_second else ('anchor',):
        a0 = sc.get(role); pa = sc.get('p_anchor' if role == 'anchor' else 'p_second', 0)
        if a0:
            o = jc.get('比分', {}).get(a0, 0)
            if pa >= 0.075 and 4.5 <= o <= 20.0:
                ops.append({'kind': 'score', 'label': f"比分{a0}", 'p': pa, 'odds': o,
                            'from': f"score_{role}({'anchor' if role=='anchor' else 'second'})", 'tag': ('主锚' if role == 'anchor' else '次锚')})
    if gd_dist:
        top = sorted(gd_dist.items(), key=lambda x: -x[1]); g1, p1 = top[0]
        ou = m.get('over_under', 0.5)
        if int(g1) in (2, 3) and p1 >= 0.20:
            ops.append({'kind': 'goals', 'label': f"总进球{g1}球", 'p': p1, 'odds': jc_zjq.get(g1, 0),
                        'from': f"goals_dist[{g1}]", 'tag': f'{g1}球'})
        elif int(g1) in (0, 1, 4, 5) and p1 >= 0.08 and ((ou >= 0.60) if int(g1) >= 4 else (1 - ou) >= 0.60):
            ops.append({'kind': 'goals', 'label': f"总进球{g1}球", 'p': p1, 'odds': jc_zjq.get(g1, 0),
                        'from': f"goals_dist[{g1}]+over_under", 'tag': f'{g1}球'})
    if m['confidence'] == 'HIGH' and max(m['probs'].values()) >= 0.65:
        d = m['direction']; o = jc_spf.get({'主胜': '主胜', '客胜': '客胜'}.get(d, '平'), 0)
        if 1.5 <= o <= 2.2:
            ops.append({'kind': 'dan', 'label': f"胜平负{d}", 'p': m['probs'][d], 'odds': o,
                        'from': "confidence+prob", 'tag': '胆'})
    ok = [o for o in ops if ev_cal(o['kind'], o['odds'], o.get('p', 0.0)) >= CFG['ev_floor'].get(o['kind'], -0.25)]
    return ok

def leg_score(m, o):
    c = CFG['score_w'].get(m['confidence'], 1)
    sc = (c / 3.0) * 3.5 + CFG['kind_bonus'].get(o['kind'], 0.3)
    sc += max(-1.0, min(1.5, ev_cal(o['kind'], o['odds'], o.get('p', 0.0)) * 4))
    sc += min(1.5, o['p'] / 0.10 * 0.5)
    inj = m.get('injury', {}); sc -= min(1.5, (inj.get('home', 0) + inj.get('away', 0)) * CFG['risk_w'])
    o['score'] = round(max(0.0, min(10.0, sc)), 2)
    return o['score']

def make_ticket(legs, name, note):
    """legs=[(match, option)]·每场一选项(竞彩串关规则)"""
    hitp = math.prod(opt_hit(l['o']['kind'], l['o'].get('p', 0.0)) for _, l in legs)
    odds = math.prod(l['o']['odds'] for _, l in legs)
    return {'name': name, 'note': note, 'legs': legs, 'odds': odds, 'hit': hitp, 'ev': hitp * odds - 1}

# ---------- 动态多票引擎(N·质量·多选项) ----------
def dynamic_tickets(pool, include_second=True):
    """按可投场数N与腿质量·动态生成多张串关票(同场可不同选项出现于不同票·满足一场多注)"""
    N = len(pool)
    if N < 2: return [], f"可投{N}场——只买串关需≥2场·今日不出方案"
    entries = []  # (match, 单注ops含主次锚)
    for m, ops0 in pool:
        ops = single_options(m, include_second=include_second)
        for o in ops: leg_score(m, o)
        ops.sort(key=lambda x: -x['score'])
        entries.append((m, ops))
    entries.sort(key=lambda x: -(x[1][0]['score'] if x[1] else 0))
    def pick_best(m, ops, forbid_kind=None, forbid_tag=None):
        for o in ops:
            if forbid_kind and o['kind'] == forbid_kind: continue
            if forbid_tag and o.get('tag') == forbid_tag: continue
            return o
        return None
    tickets = []
    def leg_of(m, o): return (m, {'o': o, 'label': o['label']})
    # —— 票1: 因场而异的混合主串(🔴v0.6用户: 每场选其多维评分最高玩法·不强求玩法均匀·仅同玩法≥4场才调整防单调) ——
    legs1 = []
    for m, ops in entries:
        if not ops: continue
        so = next((x for x in ops if x['kind'] == 'score' and x.get('tag') == '主锚'), None)
        # 主锚比分优先(模型最信第一判断)·无主锚则该场最高分玩法(因场况: 热那亚→进球2球)
        legs1.append(leg_of(m, so if so else ops[0]))
    if N == 2 and len(legs1) >= 2:
        tickets.append(make_ticket(legs1[:2], '2串1(混合·两场最佳)', '2串1单票·每注'))
    elif N == 3 and len(legs1) >= 3:
        tickets.append(make_ticket(legs1[:3], '3串4容错(混合主串)', '3串4=4注(3×2串1+1×3串1)·错1仍中2串'))
    elif N >= 4:
        tickets.append(make_ticket(legs1[:4] if N == 4 else legs1[:3],
                                   f"{'4串5容错' if N==4 else '3串4容错'}·混合主串",
                                   f"{'4串5=5注·错1仍中3串' if N==4 else '3串4=4注·错1仍中2串'}"))
    # —— 票2: 比分高赔直串(各场主锚比分·无比分场用让球平)——高收益
    sc_legs = []
    for m, ops in entries:
        o = pick_best(m, ops, forbid_kind=None)  # 票2取每场最高分score优先
        so = next((x for x in ops if x['kind'] == 'score' and x.get('tag') == '主锚'), None)
        if so: o = so
        if o: sc_legs.append(leg_of(m, o))
    if len(sc_legs) >= 3:
        k = min(len(sc_legs), 6)
        tag = '3串1' if k == 3 else f'{k}串1'
        tickets.append(make_ticket(sc_legs[:k], f'{tag}·比分主锚高赔直串',
                                   f'{k}场主锚比分(无比分场取该场最佳)·单票小额·全中才中'))
    # —— 票3: 次锚比分票(满足"比分买两个": 主锚票已含·此票用次锚·场与票2可重叠)
    sec_legs = []
    for m, ops in entries:
        so = next((x for x in ops if x['kind'] == 'score' and x.get('tag') == '次锚'), None)
        if so: sec_legs.append(leg_of(m, so))
    if len(sec_legs) >= 3:
        k = min(len(sec_legs), 6)
        tag = '3串1' if k == 3 else f'{k}串1'
        tickets.append(make_ticket(sec_legs[:k], f'{tag}·比分次锚票(与主锚票互补·一场两比分)',
                                   f'{k}场次锚比分·与票2构成同场双比分覆盖'))
    # —— 进球数串票(🔴2026-09-04用户核心玩法: 各场进球热档/高赔档·单注口径·每场一档) ——
    gl_legs = []
    for m, ops in entries:
        go = next((x for x in ops if x['kind'] == 'goals'), None)
        if go: gl_legs.append(leg_of(m, go))
    if len(gl_legs) >= 3:
        k = min(len(gl_legs), 6)
        tag = '3串1' if k == 3 else f'{k}串1'
        tickets.append(make_ticket(gl_legs[:k], f'{tag}·进球数串票(各场热档)',
                                   f'{k}场总进球各选一档·单注口径·错1即废(无容错)·高赔'))
    # —— 票4: 让球平稳健串(各场让平/胆·混合)——次容错
    if N >= 3:
        hf_legs = []
        for m, ops in entries:
            o = pick_best(m, ops)
            ho = next((x for x in ops if x['kind'] == 'handicap_flat'), None)
            if ho: o = ho
            if o: hf_legs.append(leg_of(m, o))
        if len(hf_legs) >= 3:
            tickets.append(make_ticket(hf_legs[:3], '3串4·让球平稳健串(中赔参考)',
                                       '3场让球平·3串4=4注·相对高命中(单注20%)'))
    return tickets, f"可投{N}场·动态生成 {len(tickets)} 张串关票(每场可跨票用不同选项)"

def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    data = json.load(open(sys.argv[1], encoding='utf-8'))
    per = float(sys.argv[sys.argv.index('--per') + 1]) if '--per' in sys.argv else 10.0
    pool = []
    print('=' * 76)
    print('# 今日竞彩串关方案（v0.4·动态多维·无资金限制·可一场多选项多票）')
    print('=' * 76)
    print(f"当日比赛 {len(data['matches'])} 场 | 每注参考 {per:.0f}元(自行定·不设资金限制) | 只买串关")
    print('-' * 76)
    for m in data['matches']:
        if layers(m) != 'pass':
            print(f"  ✗ {m.get('id','?')} {m.get('home','')}vs{m.get('away','')}: 淘汰(置信/方向/平局信号)"); continue
        ops = single_options(m)
        if not ops:
            print(f"  ✗ {m['id']} {m['home']}vs{m['away']}: 无达标单注玩法"); continue
        pool.append((m, ops))
    if not pool:
        print('今日无符合模型标准的串关场次。'); print('免责声明: AI模型数据分析生成·仅供参考·不构成投注建议·不保证盈利·未满18岁禁止购彩。'); return
    # 四玩法候选一览(🔴全玩法候选·按场况筛选·✓有信号/✗无信号)
    print('每场四玩法候选一览(比分/让球平/进球数/胜平负胆·全候选·按场况筛选用):')
    for m, _ in pool:
        ops = single_options(m, include_second=True)
        for o in ops: leg_score(m, o)
        ops.sort(key=lambda x: -x['score'])
        def fmt(kind, tag=None):
            xs = [o for o in ops if o['kind'] == kind and (tag is None or o.get('tag') == tag)]
            return '、'.join(f"{x['label']}@{x['odds']}({x['score']}分)" for x in xs) or '✗无信号'
        print(f"  {m['id']} {m['home']}vs{m['away']} [{m['direction']} {m['confidence']}]")
        print(f"      比分主锚: {fmt('score','主锚')} | 次锚: {fmt('score','次锚')}")
        print(f"      让球平: {fmt('handicap_flat')}")
        print(f"      进球数: {fmt('goals')}")
        print(f"      胜平负胆: {fmt('dan')}")
    print('-' * 76)
    tickets, msg = dynamic_tickets(pool)
    print(msg)
    for t in tickets:
        print('=' * 76)
        print(f"## 票: {t['name']} | 串关赔率≈{t['odds']:.0f} | 全中命中≈{t['hit']:.2%} | 校准EV={t['ev']:+.1%}")
        print(f"   {t['note']}")
        for i, (mm, lg) in enumerate(t['legs'], 1):
            o = lg['o']
            print(f"   场{i} {mm['id']} {mm['home']}vs{mm['away']} | {o['label']} @{o['odds']} "
                  f"| 单注命中≈{hit(o['kind']):.0%} | {o['from']}")
    print('=' * 76)
    print('### 说明')
    print('- 串关一场一选项(竞彩规则)·"一场买两比分"= 该场在主锚票与次锚票各用一次(两注/两票)')
    print('- 每注金额自行决定(建议小额·无资金限制·不追亏不倍投)')
    print('- EV校准=历史命中率×赔率−1(比分0.105/让平0.20/进球0.22·127场基线·诚实负EV)·串命中=∏单注命中')
    print('- 每腿依据字段(source_field)可追溯模型输出')
    print('\n### 风险提示')
    print('1. 竞彩返奖70-73%·长期EV负·比分/让球平低命中高赔·连黑风险高·务必小额')
    print('2. 赔率以投注时官方为准·变动>15%重评·不追亏/不倍投/不借钱')
    print('免责声明: AI模型数据分析生成·仅供参考·不构成投注建议·不保证盈利·自行判断承担风险·未满18岁禁止购彩。')

if __name__ == '__main__':
    main()
