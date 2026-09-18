# -*- coding: utf-8 -*-
"""_plan3_wide.py — 放宽版参考方案(case185+187+188·用户授权 dec-bf9e92ea1f6400a3·非标准门槛·诚实标注)"""
import json, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import betting_plan_generator as G

data = json.load(open(os.path.join(HERE, '_bet_plan_input2.json'), encoding='utf-8'))
matches = [m for m in data['matches'] if str(m['id']) in ('185', '187', '188')]
print('=' * 72)
print('放宽版参考方案（用户授权·非标准门槛·如实标注负EV体系）')
print('=' * 72)
entries = []
for m in matches:
    ops = G.single_options(m, include_second=True)
    for o in ops:
        G.leg_score(m, o)
    ops.sort(key=lambda x: -x['score'])
    entries.append((m, ops))
    print(f"\n{m['id']} {m['home']} vs {m['away']} [{m['direction']} {m['confidence']}]")
    if not ops:
        print('   (无达标候选·EV过滤)')
    for o in ops:
        ev = G.ev_cal(o['kind'], o['odds'], o.get('p', 0))
        print(f"   {o['label']} @{o['odds']} | 评分 {o['score']} | EV {ev:+.3f} | 来源 {o['from']}")

def show(name, note, legs):
    legs = [(m, o) for m, o in legs if o]
    if len(legs) < 2:
        print(f"\n【{name}】腿数不足({len(legs)})→ 不成串")
        return
    legs2 = [(m, {'o': o, 'label': o['label']}) for m, o in legs]
    t = G.make_ticket(legs2, name, note)
    print(f"\n【{name}】{note}")
    for m, o in legs:
        print(f"   {m['id']}  {m['home']}vs{m['away']}:  {o['label']} @{o['odds']}")
    print(f"   → 合计赔率 {t['odds']:.1f}倍 | 命中率 {t['hit']*100:.3f}% | 校准EV {t['ev']*100:+.1f}%")

def best_score(m, ops):
    so = next((x for x in ops if x['kind'] == 'score' and x.get('tag') == '主锚'), None)
    return so if so else (ops[0] if ops else None)

# 票1 · 3串4 容错（混合主串：每场最佳·主锚优先）
show('票1 · 3串4容错(混合主串)', '4注=3×2串1+1×3串1 · 错1场仍中2串1',
     [(m, best_score(m, ops)) for m, ops in entries])
# 票2 · 3串1 比分直串（各场最佳比分·主锚/次锚）
sc_legs = []
for m, ops in entries:
    so = next((x for x in ops if x['kind'] == 'score'), None)
    sc_legs.append((m, so))
show('票2 · 3串1比分直串', '高赔单票·全中才中', sc_legs)
# 票3 · 3串1 进球数串
gl = []
for m, ops in entries:
    go = next((x for x in ops if x['kind'] == 'goals'), None)
    gl.append((m, go))
show('票3 · 3串1进球数串', '各场热档进球', gl)
print('\n每注参考: 10元(自行定·无资金限制·小额) | 竞彩返奖70-73%·长期EV负·不追亏不倍投')
