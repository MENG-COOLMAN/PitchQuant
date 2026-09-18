# -*- coding: utf-8 -*-
"""prestep_dual.py —— PreStep 双向评级（2026-09-11·用户要求）
每次 PreStep 同时输出【方向评分】与【比分评分】两套独立评级。

方向分（原 10 信号·回测 43254 场）:
  D1 深盘主胜(主<1.5)=+2 · O10浅让(主让<1)→-1 · D2 深盘客胜(亚盘客让0.75+)=+2
  D3 均势必平(隐含差5-10pp+平率≥27%)=+1.5 · N3 中深盘主胜(1.5-1.8+客>4.5)=+1.5
  N4 客队热门(客<2.2+主>3.0)=+1.5 · G1 大球(O25<1.7)=+1.5 · G2 小球(O25>2.1)=+1
  H1 水位背离(水位差>0.2)=+1 · H2 穿盘(主让1.25-1.75)=+1.5 · H3 反直觉降权(西甲1.5-1.8/法甲深盘)=-1

比分分（新体系·回测 12000 场时间分割）:
  O25>2.10强小球=+3 · 主赔1.80-2.20=+2.5 · 让≥1.5=+2 · 主赔1.50-1.80=+1
  O25中性1.65-1.90=-2 · O25<1.65大球侧=-4 · 极端共振(O25<1.5+让≥1.5)=-6
  贴水浅让(主<1.5+让<1)=-6 · O25<1.7+隐含差>25=-3

双向评级:
  方向≥3 且 比分≥2.5 → 🔴双推荐(最佳场) | 仅方向≥3 → 方向可判·比分难测
  仅比分≥2.5 → 比分有谱·方向弱 | 比分≤-3 → 比分不可预测 | 双低 → 跳过

用法:
  python data/tmp/prestep_dual.py --match "费内巴切vs罗马,3.32,3.55,1.83,1,3.09"
  python data/tmp/prestep_dual.py --file data/tmp/_prestep_input.txt   # 每行: 赛事,主,平,客,让球,O25
"""
import sys, io, os, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

D5 = ('英超', 'E0', '西甲', 'SP1', '意甲', 'I1', '德甲', 'D1', '法甲', 'F1')
FRA = ('法甲', 'F1')
ESP = ('西甲', 'SP1')


def probs(oh, od, oa):
    inv = {1: 1 / oh, 0: 1 / od, 2: 1 / oa}
    t = sum(inv.values())
    return {k: v / t for k, v in inv.items()}


def score_direction(oh, od, oa, handi, o25, water_gap=0, league=''):
    """方向评分（10 信号·与 SK-prestep-filter 一致）"""
    p = probs(oh, od, oa)
    top = max(p, key=p.get)
    gap = (p[top] - sorted(p.values())[-2]) * 100
    s = 0.0
    tags = []
    if oh < 1.5:
        s += 2; tags.append('D1深盘主胜+2')
        if handi > -1.0:            # 主让<1 浅让
            s -= 1; tags.append('O10浅让-1')
    if handi >= 0.75 and oa < 2.5:  # 亚盘客让0.75+（此处 handi>0 = 客队让球）
        s += 2; tags.append('D2深盘客胜+2')
    if 5 <= gap <= 10 and od >= 3.0:
        s += 1.5; tags.append('D3均势必平+1.5')
    if 1.5 <= oh < 1.8 and oa > 4.5:
        s += 1.5; tags.append('N3中深盘主胜+1.5')
        if handi > -1.0:
            s -= 1; tags.append('O10浅让-1')
    if oa < 2.2 and oh > 3.0:
        s += 1.5; tags.append('N4客队热门+1.5')
    if o25 < 1.7:
        s += 1.5; tags.append('G1大球+1.5')
    if o25 > 2.1:
        s += 1; tags.append('G2小球+1')
    if abs(water_gap) > 0.2:
        s += 1; tags.append('H1水位背离+1')
    if -1.75 <= handi <= -1.25:
        s += 1.5; tags.append('H2穿盘+1.5')
    if ((oh < 1.8 and 1.5 <= oh) and league in ESP) or (league in FRA and handi <= -1.5):
        s -= 1; tags.append('H3反直觉降权-1')
    return round(s, 1), {0: '平', 1: '主胜', 2: '客胜'}[top], tags


def score_score(oh, od, oa, handi, o25):
    """比分评分 V3（2026-09-12·1pp≈1分标度·按回测增量·用户反馈"适当放宽"）
    标度依据（2400场时间分割）: 强小球+1.45pp→+1.5 / 大球侧-2.32~3.57pp→-2.5 /
      极端共振-5.35pp→-5 / 贴水浅让-5.06pp→-5 · 阈值 ≥1.5 命中 30.98%(+6.11pp)
    """
    p = probs(oh, od, oa)
    top = max(p, key=p.get)
    gap = (p[top] - sorted(p.values())[-2]) * 100
    s = 0.0
    tags = []
    if o25 > 2.10:
        s += 1.5; tags.append('强小球+1.5')
    elif o25 < 1.65:
        s -= 2.5; tags.append('大球侧-2.5')
    if 1.80 <= oh < 2.20:
        s += 1.0; tags.append('中盘1.8-2.2 +1.0')
    elif 1.50 <= oh < 1.80:
        s += 0.5; tags.append('主赔1.5-1.8 +0.5')
    if handi <= -1.5:
        s += 1.0; tags.append('深让≥1.5 +1.0')
    if 1.65 <= o25 <= 1.90:
        s -= 1.0; tags.append('O25中性-1.0')
    if o25 < 1.5 and handi <= -1.5:
        s -= 5.0; tags.append('🔴极端共振-5.0')
    if oh < 1.5 and handi > -1.0:
        s -= 5.0; tags.append('🔴贴水浅让-5.0')
    if o25 < 1.7 and gap > 25:
        s -= 2.0; tags.append('O25<1.7+悬殊-2.0')
    return round(s, 1), tags


def anchor_hint(oh, od, oa, handi, o25, league=''):
    """比分锚建议（按 方向+让球层+O25档 查表·实测 Top2 25.19%）"""
    p = probs(oh, od, oa)
    top = max(p, key=p.get)
    if top == 1:            # 主胜倾向
        if o25 < 1.65: return '2:1 / 2:0（大球侧·净胜分散）', '~19%'
        if o25 > 2.1:  return '1:0 / 2:0（小球·零封倾向）', '~27%'
        return '2:1 / 1:0', '~26%'
    if top == 2:            # 客胜倾向
        if o25 < 1.65: return '1:2 / 0:2', '~19%'
        return '0:1 / 1:2', '~25%'
    return '1:1 / 0:0', '~25%'


def anchor_trust(o25, handi=None):
    """🔴锚可信度分级（2026-09-13·案例库 157 场锚命中回测固化）

    实测（真实赛果分档·锚命中率）:
      实际总进球 <=3球 → 36.4%(n=88)  vs  >=4球 → 2.9%(n=69) · 5+球 0%(n=38)
      实际净胜  <=1球 → 76% 命中场；净胜>=3 → 5.4%
      交叉「<=3球且净胜<=1」→ 40.0%(n=65) vs「>=4球且净胜>=2」→ 4.9%
      命中比分 88% 落在 {1:1, 2:1, 1:0, 0:1, 2:0}
    判定（O25 预期总进球 + 让球深度代理）:
      O25<1.50(预期>=3.4球) 或 handi<=-2(深盘大胜) → 不可信（实测 2.9-6.5%）
      O25 1.50-1.65(预期约3.0球) → 弱（约32%·临界）
      O25 >=1.65(预期<=2.9球) → 可信（26-50%·低分小净胜 40%）
    """
    if o25 is None:
        return '未知', '无 O25 数据'
    if o25 < 1.50:
        return '🔴不可信', '预期总进球>=3.4球(实测锚命中2.9-6.5%·5+球0%)'
    if o25 < 1.65:
        return '⚠️弱', '预期总进球约3.0球(实测约32%·临界档)'
    if handi is not None and handi <= -2.0:
        return '🔴不可信', '深盘大胜(净胜档>=3·实测锚命中5.4%)'
    return '✅可信', '预期总进球<=2.9球(实测锚命中26-50%·低分小净胜40%)'

def evaluate(name, oh, od, oa, handi, o25, water_gap=0, league=''):
    ds, dtend, dtags = score_direction(oh, od, oa, handi, o25, water_gap, league)
    ss, stags = score_score(oh, od, oa, handi, o25)
    anc, hit = anchor_hint(oh, od, oa, handi, o25, league)
    at, at_reason = anchor_trust(o25, handi)   # 🔴2026-09-13 锚可信度分级
    # 🔴2026-09-12 升维: 四级分档(实测·2400场时间分割) + 方向分兼顾
    #   比分分≥2.5: Top2 30.42%(+5.55pp·802场覆盖33%) · ≤-3: 19.57%(-5.31pp)
    # 四档（2026-09-12 放宽·1pp标度）: ≥1.5 强推荐 / ≥0.5 推荐 / ≥-2 参考 / <-2 不可预测
    if ss >= 1.5:   grade = '强推荐(比分)'
    elif ss >= 0.5: grade = '推荐(比分)'
    elif ss >= -2:  grade = '参考(比分)'
    else:           grade = '不可预测'
    if ds >= 3 and ss >= 1.5:
        verdict = '🔴双推荐(方向+比分)'
    elif ss >= 1.5:
        verdict = '⚡比分优先(方向弱)'
    elif ds >= 3:
        verdict = '✅方向优先(比分参考)'
    elif ss >= -2:
        verdict = '⚡比分参考(方向弱)'
    else:
        verdict = '⏸️比分难测(仅方向参考)'
    if at.startswith('🔴'):      # 🔴锚不可信 → 强制标注(2026-09-13·回测:高分/大净胜场锚命中<=6.5%)
        verdict = '⏸️比分不可预测(锚可信度:不可信)'
    return {'名': name, '比分档': grade, '锚可信度': at, '锚可信度依据': at_reason,
            '方向分': ds, '方向': dtend, '方向信号': dtags,
            '比分分': ss, '比分信号': stags, '比分锚': anc, '比分命中率': hit, '评级': verdict}


def print_table(rows):
    print('=' * 104)
    print('🔴 PreStep 双向评级（方向分 + 比分分 · 独立输出）')
    print('=' * 104)
    print('%-20s %-6s %-6s %-6s %-12s %-10s %-16s %-8s %s' % ('赛事', '方向分', '倾向', '比分分', '比分档', '锚可信度', '比分锚建议', '档命中率', '双向评级'))
    print('-' * 104)
    for r in sorted(rows, key=lambda x: -(x['方向分'] + x['比分分'])):
        print('%-20s %-6s %-6s %-6s %-12s %-10s %-16s %-8s %s' % (
            r['名'][:18], r['方向分'], r['方向'], r['比分分'], r.get('比分档', ''), r.get('锚可信度', ''), r['比分锚'], r['比分命中率'], r['评级']))
    print('-' * 104)
    print('阈值: 方向分 ≥3 推荐(65.5%命中) · 比分分 ≥1.5 强推荐(30.98%) · ≤-2 不可预测 · 🔴锚不可信→强制标「比分不可预测」')
    print('🔴锚可信度(2026-09-13·案例库157场回测): ✅可信(实际≤3球锚命中36.4%·低分小净胜40%) / ⚠️弱(≈32%) / 🔴不可信(≥4球2.9%·5+球0%·净胜≥3为5.4%)')
    print()
    for r in sorted(rows, key=lambda x: -(x['方向分'] + x['比分分'])):
        if r['方向分'] > 0 or r['比分分'] != 0:
            print('【%s】方向%s(%s) | 比分%s(%s)' % (r['名'], r['方向分'], '·'.join(r['方向信号']) or '—',
                                                    r['比分分'], '·'.join(r['比分信号']) or '—'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--match', action='append', help='赛事,主,平,客,让球,O25[,水位差,联赛]')
    ap.add_argument('--file', help='每行: 赛事,主,平,客,让球,O25[,水位差,联赛]')
    a = ap.parse_args()
    lines = a.match or []
    if a.file and os.path.exists(a.file):
        lines += [l.strip() for l in open(a.file, encoding='utf-8') if l.strip() and not l.startswith('#')]
    if not lines:
        print(__doc__); return
    rows = []
    for ln in lines:
        p = [x.strip() for x in ln.split(',')]
        if len(p) < 6:
            continue
        try:
            name, oh, od, oa, handi, o25 = p[0], float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5])
            wg = float(p[6]) if len(p) > 6 and p[6] else 0
            lg = p[7] if len(p) > 7 else ''
        except Exception:
            continue
        rows.append(evaluate(name, oh, od, oa, handi, o25, wg, lg))
    print_table(rows)


if __name__ == '__main__':
    main()
