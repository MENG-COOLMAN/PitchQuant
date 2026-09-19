# -*- coding: utf-8 -*-
"""learn.py —— 赛后学习统一入口（轻封装·2026-09-11）
把「赛果 → 复盘学习 + 数据接入 + 在线学习 + 报告」收口为模块内单入口。

用法:
  # 单场（推荐 --txt 自动接入 8 源特征）
  python scripts/online_learning/learn.py --case 158 --real 1:1 --txt data/tmp/fen158.txt \
      --league 欧冠 --pred "客胜+平" --pred-dir 2 --anchor "1:1|1:2" --center 2.5
  # 仅日志回溯（calc_all 分析时已存特征）
  python scripts/online_learning/learn.py --case 158 --real 1:1 --from-log fen158
  # 汇总 / 状态
  python scripts/online_learning/learn.py --status
"""
import os, sys, io, subprocess, argparse, json
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.dirname(HERE)
ROOT = os.path.dirname(DATA)
sys.path.insert(0, HERE)
ENV = dict(os.environ, PYTHONIOENCODING='utf-8')


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', env=ENV)
    return r.stdout or ''


def _features_from_txt(txt_path, league=None, net=True):
    """data_bridge 统一接入（8 源）·失败回退 txt_features"""
    try:
        import data_bridge as DB
        r = DB.collect(txt_path, league, net)
        f = r.get('features') or {}
        st = r.get('status') or {}
        diag = {'complete': bool(f.get('home_odds') and f.get('draw_odds') and f.get('away_odds')),
                'missing': [k for k in ('home_odds', 'draw_odds', 'away_odds') if not f.get(k)],
                'sources_ok': [k for k, v in st.items() if v['status'] == 'ok'],
                'sources_missing': ['%s(%s)' % (k, v['note'][:20]) for k, v in st.items() if v['status'] in ('missing', 'error')],
                'completeness': r.get('completeness'), 'rich': r.get('sources')}
        return f, diag
    except Exception as e:
        import txt_features
        f, d = txt_features.extract(txt_path)
        d = dict(d or {}); d['bridge_error'] = str(e)[:100]
        return f, d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case'); ap.add_argument('--real'); ap.add_argument('--league', default='?')
    ap.add_argument('--txt', help='竞彩txt路径(推荐·自动接入8源特征)')
    ap.add_argument('--from-log', help='从预测日志回溯特征(prediction_log 文件名)')
    ap.add_argument('--oh', type=float); ap.add_argument('--od', type=float); ap.add_argument('--oa', type=float)
    ap.add_argument('--handi', type=float, default=0); ap.add_argument('--o25', type=float, default=1.9)
    ap.add_argument('--pred', default=''); ap.add_argument('--pred-dir', type=int, default=1)
    ap.add_argument('--anchor', default=''); ap.add_argument('--center', type=float, default=0)
    ap.add_argument('--no-net', action='store_true'); ap.add_argument('--status', action='store_true')
    a = ap.parse_args()
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    if a.status:
        print('── 复盘学习台账（self_iterate）──')
        print(run([sys.executable, os.path.join(DATA, 'tmp', 'self_iterate.py'), 'status']))
        print('── 在线学习系统状态 ──')
        print(run([sys.executable, os.path.join(HERE, 'learn_result.py'), '--status']))
        return
    if not (a.case and a.real):
        print(__doc__); return

    print('=' * 68)
    print('🧠 赛果自动学习: case%s %s' % (a.case, a.real))
    print('=' * 68)

    out1 = run([sys.executable, os.path.join(DATA, 'tmp', 'self_iterate.py'), 'learn',
                '--case', str(a.case), '--real', a.real, '--pred', a.pred,
                '--anchor', a.anchor, '--center', str(a.center),
                '--handi', str(a.handi), '--o25', str(a.o25 or 1.9)])
    for ln in out1.split('\n'):
        if ln.startswith(('===', '方向:', '归因:', '⚡', '   →', '→')):
            print(ln)

    feat = None
    if a.txt:
        feat, diag = _features_from_txt(a.txt, a.league, net=not a.no_net)
        if diag.get('sources_ok') is not None:
            _ok = ','.join(diag.get('sources_ok') or []) or '-'
            _miss = '; '.join((diag.get('sources_missing') or [])[:4]) or '-'
            print('🔗 数据接入: %s | OK: %s | 缺: %s' % (diag.get('completeness'), _ok, _miss))
        if feat and diag.get('complete'):
            print('📄 特征来源: txt自动提取(%s) → 主%.2f/平%.2f/客%.2f 让球%+g 联赛%s O25等效%.3f' % (
                a.txt, feat['home_odds'], feat['draw_odds'], feat['away_odds'],
                feat['handicap'], feat['league'], feat['o25_odds']))
    if feat is None and a.from_log:
        lp = os.path.join(HERE, 'prediction_log', '%s.json' % a.from_log)
        if os.path.exists(lp):
            j = json.load(open(lp, encoding='utf-8'))
            feat = j.get('features'); print('📄 特征来源: 预测日志回溯(%s)' % os.path.basename(lp))
    if feat is None and a.oh and a.od and a.oa:
        _lg = a.league or '?'
        feat = {'home_odds': a.oh, 'draw_odds': a.od, 'away_odds': a.oa, 'handicap': a.handi,
                'o25_odds': a.o25 or 1.9, 'league': _lg, 'league_id': 9,
                'is_top5': 1 if _lg in ('E0', 'SP1', 'I1', 'D1', 'F1', '英超', '西甲', '意甲', '德甲', '法甲') else 0,
                'is_europe': 1 if _lg in ('欧冠', '欧联', '欧协联', 'ec', 'ucl', 'uel', 'uecl') else 0,
                'elo_diff': 0, 'handicap_layer': 0}
        print('📄 特征来源: 显式参数')
    if feat:
        for k in ('home_odds', 'draw_odds', 'away_odds'):
            if not feat.get(k):
                print('⚠️ 特征字段缺失(%s) → 在线学习层跳过' % k); feat = None; break
    # 🔴融合监测记录（2026-09-11·须在【学习前】·防训练污染）
    try:
        if feat:
            import river_models as _RM
            import subprocess as _sp
            _m = _RM.load_models()
            _pv = _RM.predict(_m, feat)
            _dp = _pv.get('direction_probs') or {}
            _oh = float(feat.get('home_odds') or 0); _od = float(feat.get('draw_odds') or 0); _oa = float(feat.get('away_odds') or 0)
            if _dp and _oh > 1 and _od > 1 and _oa > 1:
                _inv = {1: 1/_oh, 0: 1/_od, 2: 1/_oa}; _t = sum(_inv.values())
                _mk = {k: v/_t for k, v in _inv.items()}
                import json as _js
                _gp = os.path.join(HERE, 'state', 'gate.json')
                _g = _js.load(open(_gp, encoding='utf-8')).get('L1_online_ml', {}) if os.path.exists(_gp) else {}
                _w = float(_g.get('weight', 0.10)) if _g.get('enabled', True) else 0.0
                if _g.get('status') == 'degraded':
                    _w = 0.0
                _fu = {k: _mk[k]*(1-_w) + _dp.get(k, 0)*_w for k in (0, 1, 2)}
                _fm = max(_fu, key=_fu.get); _mm = max(_mk, key=_mk.get)
                _h, _a2 = [int(x) for x in str(a.real).replace('：', ':').split(':')]
                _actual = 1 if _h > _a2 else (2 if _a2 > _h else 0)
                _sp.run([sys.executable, os.path.join(HERE, 'gate.py'), '--log', '--case', str(a.case),
                         '--pred-fused', str(_fm), '--pred-base', str(_mm), '--actual', str(_actual)],
                        capture_output=True, env=ENV)
                print('📊 融合监测已记录: 融合=%s 基准=%s 实际=%s' % (_fm, _mm, _actual))
    except Exception as _ge:
        print('⚠️ 融合监测记录失败:', str(_ge)[:60])

    if feat:
        # 🔴2026-09-12 修复: 直接调用 learning_loop 传**完整特征 dict**
        #   原实现走 subprocess+--oh/--od/--oa 命令行传参 → make_features 只造 A 类 11 特征
        #   → B/C/D/E 类 24 个特征全部丢失（case_library 24 个 null 的根因）
        try:
            import learning_loop as _LL
            _pred = {'direction': a.pred_dir, 'total': a.center,
                     'top2': [s for s in (a.anchor or '').split('|') if s]}
            _rep = _LL.learn_from_result(str(a.case), a.real, feat, _pred)
            _LL.print_report(_rep)
            _n_full = len([v for v in feat.values() if v is not None])
            print('📊 完整特征传入: %d 个非空字段（含 B/C/D/E 类）' % _n_full)
        except Exception as _le2:
            print('⚠️ learning_loop 直接调用失败·回退 CLI:', str(_le2)[:80])
            print(run([sys.executable, os.path.join(HERE, 'learn_result.py'),
                       '--case', str(a.case), '--real', a.real, '--league', str(feat.get('league') or a.league),
                       '--home-odds', str(feat['home_odds']), '--draw-odds', str(feat['draw_odds']),
                       '--away-odds', str(feat['away_odds']), '--handi', str(feat.get('handicap', 0)),
                       '--o25', str(feat.get('o25_odds', 1.9)), '--pred-dir', str(a.pred_dir),
                       '--pred-total', str(a.center), '--pred-top2', a.anchor]))
    else:
        print('⚠️ 无 txt/日志/赔率 → 在线学习层跳过（仅完成复盘学习）')



if __name__ == '__main__':
    main()
