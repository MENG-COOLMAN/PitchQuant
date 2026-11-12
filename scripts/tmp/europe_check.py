# -*- coding: utf-8 -*-
"""欧战六项核查表（rule51-70）·脚本化（2026-11-03 用户「今天要分析欧冠·检查能否完全跑通」）

背景（实跑实抓）：欧冠场跑 pipeline 时，`C10 Step3 场景44/45/46(+欧战六项核查表)` 只是
**必核清单里的一行文字**，脚本层**零输出** → 全靠模型手工调 SL-europe-db。
一旦模型漏掉，欧冠分析就缺「44A/44B/44C + 定价偏差 + 亚盘铁则」六项 → 不算跑通。

本脚本把**可判定部分**结构化输出（每条附数值 + 触发/不触发），
模型只需在此基础上补「本场特有理据」，不再可能静默漏项。

用法：
  python data/tmp/europe_check.py --league 欧冠 --round main --oh 3.385 --od 4.005 --oa 2.126 --handi 0.25
  python data/tmp/europe_check.py --league 欧冠 --round ko --first-leg "2:1" --first-home 主 ...
参数：
  --round  main(联赛阶段/正赛) | ko(淘汰赛) | qual(资格赛) | qual_playoff(附加赛)
  --handi  亚盘让球（负数=主队让球；正数=主队受让）
  --first-leg/--first-home  次回合用（44A/44B）
"""
import argparse
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
_D = os.path.dirname(os.path.abspath(__file__))


def _load_calib():
    try:
        return json.load(io.open(os.path.join(_D, 'ucl_calibration.json'), encoding='utf-8'))
    except Exception:
        return {}


def devig3(oh, od, oa):
    """欧盘三向等比例去水 → (pH, pD, pA) 百分数"""
    try:
        inv = [1.0 / float(oh), 1.0 / float(od), 1.0 / float(oa)]
    except (TypeError, ValueError, ZeroDivisionError):
        return None, None, None
    s = sum(inv)
    if s <= 0:
        return None, None, None
    return inv[0] / s * 100, inv[1] / s * 100, inv[2] / s * 100


def six_checks(league='欧冠', rnd='main', oh=None, od=None, oa=None, handi=None,
               first_leg=None, first_home=None):
    """返回六项判定 [(序号, 项名, 判定文本, 触发bool)]"""
    out = []
    calib = _load_calib()
    ph, pd, pa = devig3(oh, od, oa)
    tbl = (calib.get('table') or {}).get(league) or {}
    lv = (calib.get('apply') or {}).get(rnd, 0.0)

    # ① rule51/52（44A/44B 两回合结构）
    if rnd == 'ko' and first_leg:
        try:
            fh, fa = [int(x) for x in str(first_leg).split(':')[:2]]
        except ValueError:
            fh = fa = None
        if fh is not None:
            txt = ('首回合 %s（%s主场）→ 44A 净胜差 %+d 球 → 次回合'
                   % (first_leg, first_home or '?', fh - fa))
            if abs(fh - fa) >= 2:
                txt += ' 领先方控场 → 按 44A 偏小球（-0.2~0.3 球）·落后方主场全力 → 大球侧'
            else:
                txt += ' 差距 ≤1 球 → 双方均有机会 → 44B 主客结构优先（次回合主队略升权）'
            out.append(('①', 'rule51/52 两回合(44A/44B)', txt, True))
        else:
            out.append(('①', 'rule51/52 两回合(44A/44B)', '首回合比分解析失败（三态）', False))
    else:
        out.append(('①', 'rule51/52 两回合(44A/44B)',
                    '**非次回合**（%s·不适用）' % ('正赛/单回合' if rnd != 'ko' else '未提供首回合比分'),
                    False))

    # ② rule53（44C 赛事分层基准）
    band = tbl.get(rnd) or {}
    if band:
        out.append(('②', 'rule53 赛事分层(44C)',
                    '%s·%s：n=%d · 均球 %.2f · O2.5 %.1f%% · O3.5 %.1f%%（五大基线 2.69/50.4%%）'
                    % (league, band.get('label', rnd), band.get('n', 0), band.get('mean_goals', 0),
                       band.get('o25', 0), band.get('o35', 0) or 0), True))
    else:
        out.append(('②', 'rule53 赛事分层(44C)', '校准表无该轮次样本（三态）', False))

    # ③ rule54/55（资格赛低比分）
    if rnd in ('qual', 'qual_playoff'):
        q = tbl.get('qual') or {}
        out.append(('③', 'rule54/55 资格赛低比分',
                    '资格赛/附加赛：均球 %.2f · O2.5 %.1f%%（%s）'
                    % (q.get('mean_goals', 2.65), q.get('o25', 47.5),
                       '低于五大基线 → 禁套正赛大球口径' if (q.get('mean_goals') or 0) < 2.69 else ''),
                    True))
    else:
        out.append(('③', 'rule54/55 资格赛低比分', '**非资格赛**（不适用）', False))

    # ④ rule56-58（定价偏差）
    if ph is not None:
        t56 = 30 <= ph <= 65
        t57 = 30 <= pd <= 35
        t58 = pa > 55
        out.append(('④', 'rule56-58 定价偏差',
                    '主胜隐含 **%.1f%%**（30-65%%→%s）｜ 平局 **%.1f%%**（30-35%%→%s）｜ '
                    '客胜 **%.1f%%**（>55%%→%s）'
                    % (ph, '升权 +3.8~4.9pp' if t56 else '不触发',
                       pd, '强平局' if t57 else '不触发',
                       pa, '降级' if t58 else '不触发'),
                    bool(t56 or t57 or t58)))
    else:
        out.append(('④', 'rule56-58 定价偏差', '缺欧盘 ML（三态）', False))

    # ⑤ rule59/60（精算仓位 + 比分深度）
    if band:
        _bm = band.get('mean_goals') or 0
        _side = ('大球侧·4 球档优先' if _bm >= 3.0
                 else ('中性·3 球档' if _bm >= 2.7 else '小球侧·≤2 球档'))
        out.append(('⑤', 'rule59/60 精算仓位+比分深度',
                    '按 ② 的本轮次基准：均球 %.2f · O2.5 %.1f%% → **%s**（禁套其它轮次口径）'
                    % (_bm, band.get('o25', 0), _side), True))
    else:
        out.append(('⑤', 'rule59/60 精算仓位+比分深度', '缺赛事基准（三态）', False))

    # ⑥ rule61-66（亚盘铁则）
    if handi is not None:
        try:
            h = float(handi)
        except (TypeError, ValueError):
            h = None
    else:
        h = None
    if h is not None:
        seg = []
        if h <= -1.75:
            seg.append('rule61 主让≥1.75 → 历史主胜 91%%（🔴欧战次回合 73.3%% **降级**）**触发**')
        elif h <= -1.5:
            seg.append('rule62 主让≥1.5 → 主胜 80%%（欧战 69-73%%）**触发**%s'
                       % ('·主赔<1.6 满足' if (oh or 99) < 1.6 else '·主赔≥1.6 条件不全'))
        elif h >= 0.05:
            seg.append('rule63 主队受让 %.2f → 客胜 54%%（🔴欧战 61-62%% **升级**）**触发**' % h)
        else:
            seg.append('rule61-63 不触发（让球 %.2f 未达阈值）' % h)
        if ph is not None:
            gap = abs(ph - pa)
            if 5 <= gap <= 10:
                seg.append('rule64 主客隐含差 %.1fpp ∈ 5-10 → 平局 34%%（欧战平手盘 32.9%%）**触发**' % gap)
            elif h > -0.05 and h < 0.05:
                seg.append('rule64 平手盘 → 平局 30.2%%（n=96）**并列候选**')
            else:
                seg.append('rule64 主客隐含差 %.1fpp → 平局按欧战基准 22.8%%（不额外升权）' % gap)
        if rnd == 'ko':
            seg.append('rule65-70 次回合专项：水位低水 60.5%% vs 高水 45%%／欧亚同深 76.1%%／'
                       '半场平 47.8%%／主让 1 球防平 29.9%%（按实际水位取）')
        out.append(('⑥', 'rule61-66 亚盘铁则', ' ｜ '.join(seg), True))
    else:
        out.append(('⑥', 'rule61-66 亚盘铁则', '缺亚盘让球（三态）', False))

    return out, {'ph': ph, 'pd': pd, 'pa': pa, 'n24': lv, 'band': band}


def report(league='欧冠', rnd='main', **kw):
    items, meta = six_checks(league=league, rnd=rnd, **kw)
    lines = ['🔴欧战六项核查表(rule51-70·脚本化·%s·轮次=%s)' % (league, rnd)]
    hit = sum(1 for x in items if x[3])
    for no, name, txt, trg in items:
        lines.append('  %s %-24s %s%s' % (no, name, txt, '' if trg else ' ⚪'))
    lines.append('  —— 触发 %d/6 项（⚪ = 不适用/三态·须在 raw 说明）' % hit)
    if meta.get('n24'):
        lines.append('  N24 校准: %s 轮次 +%.2f 球（λ 与期望 E 同步上修·资格赛不加）'
                     % (rnd, meta['n24']))
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--league', default='欧冠')
    ap.add_argument('--round', default='main', choices=['main', 'ko', 'qual', 'qual_playoff'])
    ap.add_argument('--oh', type=float)
    ap.add_argument('--od', type=float)
    ap.add_argument('--oa', type=float)
    ap.add_argument('--handi', type=float)
    ap.add_argument('--first-leg')
    ap.add_argument('--first-home')
    a = ap.parse_args()
    for ln in report(league=a.league, rnd=a.round, oh=a.oh, od=a.od, oa=a.oa,
                     handi=a.handi, first_leg=a.first_leg, first_home=a.first_home):
        print(ln)


if __name__ == '__main__':
    main()
