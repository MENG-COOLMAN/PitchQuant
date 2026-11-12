# -*- coding: utf-8 -*-
"""eval_baseline.py — 评估层基线体检（2026-09-30·双轨方案 v2 任务 0/1）

## 为什么需要它（评论者第 2 条建议 + 2026-09-30 实测）

模型长期对外报「方向 55-58%」，但**从不附同场基线**。评论者指出：
  · 三向足球市场里「选热门」本身就有 ~50%
  · 所以必须对比【去水市场热门】而非 50%/33%
  · 更强的是【log loss vs 去水收盘概率】

2026-09-30 用本脚本同场实测（prediction_log ∩ 案例库·n=34）发现：
  · 模型 any 47.1%  ==  市场单押热门 47.1%（**+0.0pp·零增量**）
  · 模型 strict 41.2%  <  市场单押热门 47.1%（**−5.9pp**）
  · 市场「最低+次低」两向覆盖 76.5% ≫ 模型 any 47.1%（**−29.4pp**）
  → 与 22.7 万场全样本基线（单押 50.07% / 两向覆盖 77.63%）互相印证

## 用法
  python data/tmp/eval_baseline.py                 # 同场对比（默认）
  python data/tmp/eval_baseline.py --all           # 全样本市场基线（Matches.csv）
  python data/tmp/eval_baseline.py --trial-log     # 输出实验台账行（配置哈希+指标）

## 输出四基线（缺一不可）
  ① 模型 strict（仅主方向）
  ② 模型 any（含并列/次方向）
  ③ 市场单押热门（同场·去水前后同序）
  ④ 市场最低+次低 两向覆盖（同场）
  + log loss 对比（需案例库概率列·未补时三态标注）
  + 配对 McNabemar 检验 + 95% CI

## 铁律
  · 🔴 同场对比优先（只在模型与市场**分歧**的场次上信息量最大）
  · 🔴 任何对外宣称方向准确率时，必须同页给出 ③④ 两行
  · 🔴 日志非 git 仓库 → 配置哈希 = md5(依赖 json 内容 + 脚本版本号)
"""
import os, sys, json, glob, re, csv, io, math, hashlib, argparse, datetime

_TMP = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_TMP))
VERSION = 'V3.5.76+eval1.0'


def _dirs(s):
    s = s or ''
    out = set()
    if '主胜' in s: out.add('H')
    if '客胜' in s: out.add('A')
    if '平局' in s or '平' in s: out.add('D')
    return out


def _first(s):
    m = re.search(r'(主胜|客胜|平局|平)', s or '')
    return {'主胜': 'H', '客胜': 'A', '平局': 'D', '平': 'D'}.get(m.group(1)) if m else None


def _real(sc):
    m = re.match(r'\s*(\d+)\s*[:\-]\s*(\d+)', sc or '')
    if not m: return None
    fh, fa = int(m.group(1)), int(m.group(2))
    return 'H' if fh > fa else ('D' if fh == fa else 'A')


def load_log():
    """prediction_log → {case_id: (oh, od, oa)}（含赔率的场次）"""
    out = {}
    for p in glob.glob(os.path.join(_ROOT, 'data/online_learning/prediction_log/*.json')):
        b = os.path.basename(p)[:-5]
        m = re.search(r'(\d+)$', b)
        if not m: continue
        try:
            j = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue
        f = j.get('features') or {}
        ho, do, ao = f.get('home_odds'), f.get('draw_odds'), f.get('away_odds')
        if None in (ho, do, ao): continue
        out[m.group(1)] = (float(ho), float(do), float(ao))
    return out


def load_cases():
    p = os.path.join(_ROOT, 'data/case-library/实战案例.csv')
    rows = list(csv.reader(io.StringIO(io.open(p, encoding='utf-8-sig').read())))
    hdr = rows[0]
    ix = {k: hdr.index(k) for k in ('预测方向', '真实比分') if k in hdr}
    return {r[0].strip(): r for r in rows[1:] if r and r[0].strip().isdigit()}, ix


def mcnemar(a, b):
    """配对 2x2（仅比较两法在同一样本上的命中差异）→ (chi2, p)"""
    if a + b == 0: return 0.0, 1.0
    chi = (abs(a - b) - 1) ** 2 / (a + b)
    return chi, math.erfc(math.sqrt(max(chi, 0) / 2))


def wilson(k, n):
    """命中率的 95% CI（Wilson·小样本更稳）"""
    if n == 0: return (0, 0)
    z = 1.96
    ph = k / n
    d = 1 + z * z / n
    c = ph + z * z / (2 * n)
    r = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def same_match():
    log = load_log()
    cases, ix = load_cases()      # 🔴修复（2026-09-30 实跑）：load_cases 返回 (cases_dict, ix_dict)，
    ixd, ixr = ix['预测方向'], ix['真实比分']   #   原写法 `(ixd, ixr) = load_cases()[1]` 把 dict 当 tuple 解包 → 索引报错
    inter = sorted(set(log) & set(cases), key=lambda x: int(x))
    rec = []
    for c in inter:
        ho, do, ao = log[c]
        real = _real(cases[c][ixr])
        if real is None: continue
        pairs = sorted([(ho, 'H'), (do, 'D'), (ao, 'A')])
        rec.append(dict(case=c, ml='%.2f/%.2f/%.2f' % (ho, do, ao),
                        fav=pairs[0][1], sec=pairs[1][1], real=real,
                        fdir=_first(cases[c][ixd]), adirs=_dirs(cases[c][ixd])))
    return rec


def report(rec, silent=False):
    n = len(rec)
    if n == 0:
        print('⚠️ 无可用同场样本（需 prediction_log 含赔率 ∩ 案例库）')
        return None
    st = sum(1 for r in rec if r['fdir'] == r['real'])
    an = sum(1 for r in rec if r['real'] in r['adirs'])
    md = sum(1 for r in rec if r['fav'] == r['real'])
    md2 = sum(1 for r in rec if r['real'] in (r['fav'], r['sec']))
    dis = [r for r in rec if r['real'] not in r['adirs'] and r['real'] not in (r['fav'], r['sec'])]
    out = dict(n=n, strict=st, any=an, mkt_single=md, mkt_cover=md2,
               strict_pct=100 * st / n, any_pct=100 * an / n,
               mkt_single_pct=100 * md / n, mkt_cover_pct=100 * md2 / n)
    if silent:
        return out
    print('=' * 66)
    print('📊 基线体检（同场对比·n=%d）' % n)
    print('=' * 66)
    print(' %-26s %-9s %-8s %s' % ('指标', '命中', '率', '95% CI（Wilson）'))
    for lbl, k in [('① 模型 strict（主方向）', st), ('② 模型 any（含并列/次方向）', an),
                   ('③ 市场单押热门（同场基线）', md), ('④ 市场最低+次低 两向覆盖', md2)]:
        lo, hi = wilson(k, n)
        print(' %-26s %-9s %-8s [%.1f%%, %.1f%%]' % (lbl, '%d/%d' % (k, n), '%.1f%%' % (100 * k / n), 100 * lo, 100 * hi))
    print('-' * 66)
    print(' 🔴 模型 any − 市场两向覆盖 = %+.1fpp' % (100 * (an - md2) / n))
    print(' 🔴 模型 any − 市场单押热门 = %+.1fpp' % (100 * (an - md) / n))
    print('    模型 strict − 市场单押热门 = %+.1fpp' % (100 * (st - md) / n))
    chi, p = mcnemar(an, md2)
    print('    配对 McNemar（any vs 两向覆盖）: χ²=%.2f p=%.4f %s' % (chi, p, '显著' if p < 0.05 else '不显著'))
    print('    ⚠️ 两法均未覆盖的场次 = %d（模型与市场都没料到）' % len(dis))
    print()
    print(' ⚪ log loss 对比: 未计算 —— 案例库缺「模型三向概率列」(pH/pD/pA)')
    print('    前置任务: case_write 增列 + 历史回填（方案 v2 任务 4）')
    return out


def all_sample():
    """全样本市场基线（Matches.csv）"""
    p = os.path.join(_ROOT, 'data/Matches.csv')
    def f(x):
        try: return float(x)
        except Exception: return None
    n = s1 = s2 = 0
    with io.open(p, encoding='utf-8', errors='replace') as fp:
        for d in csv.DictReader(fp):
            o, dr, a = f(d['OddHome']), f(d['OddDraw']), f(d['OddAway'])
            fh, fa = f(d['FTHome']), f(d['FTAway'])
            if None in (o, dr, a, fh, fa): continue
            real = 'H' if fh > fa else ('D' if fh == fa else 'A')
            pr = sorted([(o, 'H'), (dr, 'D'), (a, 'A')])
            n += 1
            s1 += (pr[0][1] == real)
            s2 += (real in (pr[0][1], pr[1][1]))
    lo1, hi1 = wilson(s1, n); lo2, hi2 = wilson(s2, n)
    print('📊 全样本市场基线（Matches.csv·n=%d）' % n)
    print('  ① 单押最低赔率      = %.2f%%  [%.2f%%, %.2f%%]' % (100 * s1 / n, 100 * lo1, 100 * hi1))
    print('  ② 最低+次低 两向覆盖 = %.2f%%  [%.2f%%, %.2f%%]' % (100 * s2 / n, 100 * lo2, 100 * hi2))
    print('  🔴 结论：任何方向命中率宣称都应与 ② 对比（而非 50%/33%）')
    return dict(n=n, single=100 * s1 / n, cover=100 * s2 / n)


def config_hash():
    """配置哈希（非 git 仓库 → 依赖 json 内容 + 版本号）"""
    h = hashlib.md5()
    deps = ['data/tmp/calc_v3572.py', 'data/tmp/live_score_engine.py', 'data/tmp/goal_bins_table.json',
            'data/tmp/handi_score_table.json', 'data/tmp/odds_table.json']
    for d in deps:
        fp = os.path.join(_ROOT, d)
        if os.path.exists(fp):
            h.update(open(fp, 'rb').read())
    h.update(VERSION.encode())
    return h.hexdigest()[:12]


if __name__ == '__main__':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    ap = argparse.ArgumentParser(description='评估层基线体检（同场对比 + 配对检验）')
    ap.add_argument('--all', action='store_true', help='全样本市场基线（Matches.csv）')
    ap.add_argument('--trial-log', action='store_true', help='输出实验台账行（供 rule_registry.experiments）')
    a = ap.parse_args()
    if a.all:
        all_sample()
    else:
        r = report(same_match())
        if r and a.trial_log:
            line = dict(date=datetime.datetime.now().strftime('%Y-%m-%d'),
                        rule_id='EVAL-BASELINE-1', variant=config_hash(),
                        sample='prediction_log∩case-library', n=r['n'],
                        model_any_pp=round(r['any_pct'], 1),
                        mkt_cover_pp=round(r['mkt_cover_pct'], 1),
                        delta_pp=round(r['any_pct'] - r['mkt_cover_pct'], 1),
                        adopted=False, held_out_status='N/A(工具·非规则变体)')
            print('\n[trial] ' + json.dumps(line, ensure_ascii=False))
