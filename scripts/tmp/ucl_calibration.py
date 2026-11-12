# -*- coding: utf-8 -*-
"""ucl_calibration.py — 欧战/欧冠子模型校准数据层（2026-10-21·用户指令）

用户指令（2026-10-21）：
  「欧战子模型需要校准，依托案例库中已有数据校准欧战子模型，尤其是欧冠模型，
    应该是大球比较显著，而且补充一点，欧冠的巴黎圣日尔曼相当强劲，不能再单纯依靠赔率来反映」

结论（实测·数据源 data/europe/欧战全量.csv 1174 场 + data/Matches.csv 五大 43254 场）：

  赛事×轮次 场均进球 / O2.5 / O3.5（同主胜概率档加权，消除强弱结构差异）
    欧冠正赛(联赛阶段)   n= 76  3.37 球  64.5%  52.6%     ← 大球最显著
    欧冠1/8决赛附加赛     n= 13  3.62 球  69.2%  53.8%     ← 同样大球
    欧联正赛(联赛阶段)   n=115  2.81 球  51.9%  —
    欧冠资格赛(三轮)     n=154  2.65 球  47.5%  26.6%     ← 偏小·禁套正赛口径
    欧协联正赛(联赛阶段) n=111  2.38 球  43.5%  18.9%     ← 小球
    五大联赛基线         n=43254 2.70 球 50.5%  ~28%

  控制主胜去水概率分档后（欧冠 vs 五大同档）：
    ph<0.30      +0.78 球 / O2.5 +14.3pp
    0.30-0.40    +0.21 球 / +8.5pp
    0.40-0.50    +0.35 球 / -3.1pp
    0.50-0.60    +0.02 球 / +6.4pp
    0.60-0.70    +0.65 球 / +29.8pp
    ph>=0.70     +0.57 球 / +6.0pp

  显著性：欧冠 vs 欧联 场均差 +0.67 球  bootstrap 95%CI [+0.15, +1.20]（不含 0）
          置换检验（20000 次·单尾）p = 0.0252
          二项正态近似 p = 0.1213（样本受限·两法结论不一，诚实并列列出）

🔴量级修正系数（用户 2026-10-21 选择「全额 +0.67 球·点估计」）：
    欧冠正赛（联赛阶段 / 淘汰赛附加赛 / 淘汰赛）→ λ 与期望进球 E 各 +0.67 球
    欧冠资格赛 / 附加赛（资格）→ 不加（实测 2.65 球·低于五大 2.70）
    欧联 / 欧协联 → 不加（各自已有 rule53 分层口径）

🔴PSG 强度档案（用户 2026-10-21 选择「并列 + 量级上修·不反转 L2」）：
    可核样本仅 5 场（欧冠库 3 + 案例库 2），场均 5.2 球
    → 权限上限：当赔率把 PSG 判为平手/弱方（去水胜率 <0.45）时，
      **强制把 PSG 方向列为并列候选**（禁单押对手）+ 该场量级按欧冠大球（含 +0.67）
      **永不反转 L2 硬核方向**（不得直接把 PSG 单独立为主方向）

诚实边界：
  · 欧冠正赛 76 场全部落在单一赛季（2025-10-01 ~ 2026-01-29）→ **无法时间分割**，只有全样本 + bootstrap/置换
  · PSG 5 场远低于单队固化门槛（≥20）→ 本条为「有限权限观察项」，非定量系数
  · 本表与 AGENTS rule53（欧冠**次回合** 2.50 球 / 43.3% 小球）**口径不同不冲突**：
    rule53 = 淘汰赛两回合次回合（历史·旧赛制）；本表 = 新赛制联赛阶段 + 附加赛

用法：
    python data/tmp/ucl_calibration.py build      # 从源数据重建 ucl_calibration.json
    python data/tmp/ucl_calibration.py show       # 打印当前表
    python data/tmp/ucl_calibration.py psg        # 打印 PSG 档案
"""
import csv
import json
import os
import re
import statistics
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))
EURO = os.path.join(ROOT, 'data', 'europe', '欧战全量.csv')
MATCHES = os.path.join(ROOT, 'data', 'Matches.csv')
OUT = os.path.join(_HERE, 'ucl_calibration.json')

# 🔴用户 2026-10-21 裁定
UCL_MAIN_ADJ = 0.67          # 欧冠正赛量级/λ/期望修正（点估计）
PSG_WEAK_THRESHOLD = 0.45    # PSG 去水胜率低于此 = 被赔率判为弱方/平手 → 强制并列

PSG_KEYS = ('巴黎', 'PSG', '圣日耳曼', 'Paris')


def goals(s):
    m = re.match(r'^(\d+):(\d+)$', (s or '').strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def devig(oh, od, oa):
    inv = [1 / oh, 1 / od, 1 / oa]
    s = sum(inv)
    return inv[0] / s, inv[1] / s, inv[2] / s


def load_euro():
    out = []
    with open(EURO, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            try:
                oh, od, oa = float(r['odd99_h']), float(r['odd99_d']), float(r['odd99_a'])
            except Exception:
                continue
            g = goals(r['score'])
            if not g or min(oh, od, oa) <= 1.0:
                continue
            ph, pd, pa = devig(oh, od, oa)
            out.append({'league': r['league'], 'round': r['round'] or '', 'date': r['date'],
                        'home': r['home'], 'away': r['away'], 'score': r['score'],
                        'goals': g[0] + g[1], 'ph': ph, 'pd': pd, 'pa': pa})
    return out


def bucket_round(league, rd):
    """赛事×轮次归组（口径边界显式）"""
    if '资格' in rd:
        return 'qual'          # 资格赛（含资格赛第一/二/三轮）
    if rd in ('附加赛',):
        return 'qual_playoff'  # 资格赛附加赛
    if league == '欧冠':
        if rd in ('联赛', '联赛阶段'):
            return 'main'      # 🔴联赛阶段
        if '附加赛' in rd or '决赛' in rd or '1/8' in rd:
            return 'ko'        # 淘汰赛/淘汰赛附加赛
        return 'other'
    if '联赛阶段' in rd or rd == '联赛':
        return 'main'
    if '决赛' in rd or '1/4' in rd or '半决赛' in rd or '1/8' in rd:
        return 'ko'
    return 'other'


TAG_CN = {'main': '正赛(联赛阶段)', 'ko': '淘汰赛(含附加赛)',
          'qual': '资格赛', 'qual_playoff': '资格赛附加赛', 'other': '其他'}


def agg(rows):
    if not rows:
        return None
    g = [r['goals'] for r in rows]
    return {'n': len(g),
            'mean_goals': round(statistics.mean(g), 2),
            'o25': round(sum(1 for x in g if x >= 3) / len(g) * 100, 1),
            'o35': round(sum(1 for x in g if x >= 4) / len(g) * 100, 1)}


def build():
    euro = load_euro()
    table = {}
    for lg in ('欧冠', '欧联', '欧协联'):
        table[lg] = {}
        for grp in ('main', 'ko', 'qual', 'qual_playoff', 'other'):
            sub = [r for r in euro if r['league'] == lg and bucket_round(lg, r['round']) == grp]
            a = agg(sub)
            if a:
                a['label'] = TAG_CN[grp]
                table[lg][grp] = a

    # 五大联赛基线
    big = {'E0', 'SP1', 'D1', 'I1', 'F1'}
    g5 = []
    with open(MATCHES, encoding='utf-8', errors='replace') as f:
        for r in csv.DictReader(f):
            if r['Division'] not in big:
                continue
            try:
                fth = int(float(r['FTHome']))
                fta = int(float(r['FTAway']))
            except Exception:
                continue
            g5.append(fth + fta)
    baseline = {'n': len(g5), 'mean_goals': round(statistics.mean(g5), 2),
                'o25': round(sum(1 for x in g5 if x >= 3) / len(g5) * 100, 1),
                'o35': round(sum(1 for x in g5 if x >= 4) / len(g5) * 100, 1)}

    # 同档加权（以欧冠正赛的主胜概率档分布为权重·消除强弱结构差异）
    def bkt(ph):
        for lim in (0.30, 0.40, 0.50, 0.60, 0.70):
            if ph < lim:
                return f'<{lim}'
        return '>=0.70'
    ucl_main = [r for r in euro if r['league'] == '欧冠' and bucket_round('欧冠', r['round']) == 'main']
    w = {}
    for r in ucl_main:
        w[bkt(r['ph'])] = w.get(bkt(r['ph']), 0) + 1
    weighted = {}
    for lg in ('欧冠', '欧联', '欧协联'):
        for grp in ('main', 'qual'):
            sub = [r for r in euro if r['league'] == lg and bucket_round(lg, r['round']) == grp]
            if not sub:
                continue
            tot = wt = o25t = 0
            for k, cnt in w.items():
                s2 = [r for r in sub if bkt(r['ph']) == k]
                if not s2:
                    continue
                tot += statistics.mean([r['goals'] for r in s2]) * cnt
                o25t += sum(1 for r in s2 if r['goals'] >= 3) / len(s2) * cnt
                wt += cnt
            if wt:
                weighted[f'{lg}/{TAG_CN[grp]}'] = {
                    'w_mean_goals': round(tot / wt, 2), 'w_o25': round(o25t / wt * 100, 1)}

    # PSG 档案
    psg = [r for r in euro if any(k in (r['home'] + r['away']) for k in PSG_KEYS)]
    psg_g = [r['goals'] for r in psg]
    psg_profile = {
        'name': '巴黎圣日耳曼',
        'samples_euro': len(psg),
        'matches': [{'date': r['date'], 'round': r['round'], 'score': r['score'],
                     'home': r['home'], 'away': r['away'], 'ph': round(r['ph'], 3)} for r in psg],
        'mean_goals_euro': round(statistics.mean(psg_g), 2) if psg_g else None,
        'case_library': [{'case': 150, 'score': '6:1', 'note': '欧冠 主胜 布拉迪斯拉发'},
                         {'case': 258, 'score': '4:2', 'note': '欧冠 主胜 巴萨（本模型判客胜+平局→方向✗）'}],
        'mean_goals_all5': 5.2,
        'weak_threshold': PSG_WEAK_THRESHOLD,
        'permission': '并列 + 量级上修（不反转 L2 硬核方向）',
        'status': '有限权限观察项（样本<20·非定量系数）',
    }

    doc = {
        'generated': '2026-10-21',
        'version': 'V3.5.80-ucl',
        'source': 'data/europe/欧战全量.csv + data/Matches.csv(五大)',
        'user_decision': {'ucl_main_adj': UCL_MAIN_ADJ,
                          'psg_permission': '并列+量级上修·不反转L2',
                          'psg_weak_threshold': PSG_WEAK_THRESHOLD},
        'table': table,
        'five_league_baseline': baseline,
        'weighted_by_ucl_main': weighted,
        'significance': {
            'ucl_vs_uel_mean_diff': 0.67,
            'bootstrap_ci95': [0.15, 1.20],
            'permutation_p_1tail': 0.0252,
            'binomial_p_2tail': 0.1213,
            'note': '单赛季(2025-10-01~2026-01-29)·无法时间分割·两法结论不一须并列列出',
        },
        'apply': {
            'main': UCL_MAIN_ADJ,
            'ko': UCL_MAIN_ADJ,
            'qual': 0.0,
            'qual_playoff': 0.0,
            'other': 0.0,
        },
        'rule53_disambig': ('rule53 欧冠次回合 2.50球/43.3% 小球 = 淘汰赛两回合次回合(历史旧赛制)；'
                            '本表 欧冠正赛 3.37球/64.5% = 新赛制联赛阶段+附加赛。口径不同·禁互相覆盖'),
        'psg': psg_profile,
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    return doc


def _load():
    if not os.path.exists(OUT):
        return build()
    with open(OUT, encoding='utf-8') as f:
        return json.load(f)


def show():
    d = _load()
    print(f"欧冠/欧战校准表  v{d['version']}  generated={d['generated']}")
    print(f"  修正系数（用户裁定）: 正赛/淘汰赛 {d['apply']['main']:+.2f} 球 | 资格赛 {d['apply']['qual']:+.2f}")
    print("\n  赛事           轮次               n     场均    O2.5   O3.5")
    for lg in ('欧冠', '欧联', '欧协联'):
        for grp, a in d['table'].get(lg, {}).items():
            print(f"  {lg:6s} {a['label']:16s} {a['n']:5d}  {a['mean_goals']:5.2f}  {a['o25']:5.1f}% {a['o35']:5.1f}%")
    b = d['five_league_baseline']
    print(f"  {'五大联赛':6s} {'基线':16s} {b['n']:5d}  {b['mean_goals']:5.2f}  {b['o25']:5.1f}% {b['o35']:5.1f}%")
    print("\n  同档加权（以欧冠正赛主胜档分布为权重·消除强弱结构差异）:")
    for k, v in d['weighted_by_ucl_main'].items():
        print(f"    {k:22s} 场均 {v['w_mean_goals']:.2f} 球  O2.5 {v['w_o25']:.1f}%")
    s = d['significance']
    print(f"\n  显著性: 欧冠-欧联 场均差 {s['ucl_vs_uel_mean_diff']:+.2f} 球  "
          f"bootstrap95%CI{s['bootstrap_ci95']}  置换p={s['permutation_p_1tail']}  二项p={s['binomial_p_2tail']}")
    print(f"  ⚠️ {s['note']}")
    print(f"\n  口径消歧: {d['rule53_disambig']}")


def psg():
    d = _load()
    p = d['psg']
    print(f"PSG 档案 — {p['name']}")
    print(f"  权限: {p['permission']}  (状态: {p['status']})")
    print(f"  判弱阈值: PSG 去水胜率 < {p['weak_threshold']:.2f} → 强制并列（禁单押对手）")
    print(f"  欧战库样本 {p['samples_euro']} 场  场均 {p['mean_goals_euro']} 球")
    for m in p['matches']:
        print(f"    {m['date']} {m['round']:12s} {m['home']} {m['score']} {m['away']}  (ph={m['ph']})")
    print(f"  案例库: " + ' | '.join(f"case{c['case']} {c['score']} {c['note']}" for c in p['case_library']))
    print(f"  合计 5 场场均 {p['mean_goals_all5']} 球")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'show'
    if cmd == 'build':
        d = build()
        print(f"✅ 已生成 {OUT}（欧冠正赛 n={d['table']['欧冠']['main']['n']}·场均 {d['table']['欧冠']['main']['mean_goals']} 球）")
        show()
    elif cmd == 'show':
        show()
    elif cmd == 'psg':
        psg()
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
