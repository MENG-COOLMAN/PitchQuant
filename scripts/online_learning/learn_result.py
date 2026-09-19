# -*- coding: utf-8 -*-
"""赛果自动学习入口（用户给比分即触发·一条命令）
用法:
  # 单场（显式特征）
  python scripts/online_learning/learn_result.py --case 158 --real 1:1 --league 欧冠 \
      --home-odds 3.32 --draw-odds 3.55 --away-odds 1.83 --handi 1 --o25 3.09 \
      --pred-dir 2 --pred-total 2.5 --pred-top2 "1:1|1:2"

  # 批量回填（用实战案例.csv 已复盘场次顺序学习·模拟学习曲线）
  python scripts/online_learning/learn_result.py --backfill
  python scripts/online_learning/learn_result.py --status
"""
import os, sys, io, csv, json, argparse, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 🔴stdout 包装移至 __main__（被 import 时不得重复包装·防 I/O closed 错误）
import config as C
import persistence as P
import river_models as RM
import bayes_updater as BU
import error_miner as EM
import learning_loop as LL

CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'case-library', '实战案例.csv')


def _layer_from_handi(handi):
    """让球 → 9层编码（与 handicap_dynamic_magnitude 对齐）"""
    try:
        v = float(handi)
    except Exception:
        return 0
    if v <= -2.5: return 1
    if v <= -1.75: return 2
    if v <= -1.25: return 3
    if v <= -0.75: return 4
    if v <= -0.25: return 5
    if v < 0.25: return 6
    if v < 0.75: return 7
    if v < 1.25: return 8
    if v < 1.75: return 9
    if v < 2.5: return 10
    return 11


def make_features(league, oh, od, oa, handi, o25, elo=0):
    return {'home_odds': oh, 'draw_odds': od, 'away_odds': oa,
            'handicap': handi, 'o25_odds': o25,
            'league': league, 'league_id': C.LEAGUE_ID.get(league, 9),
            'is_top5': 1 if league in ('E0', 'SP1', 'I1', 'D1', 'F1', '英超', '西甲', '意甲', '德甲', '法甲') else 0,
            'is_europe': 1 if league in ('欧冠', '欧联', '欧协联') else 0,
            'elo_diff': elo, 'handicap_layer': _layer_from_handi(handi)}


def cmd_single(args):
    f = make_features(args.league, args.home_odds, args.draw_odds, args.away_odds,
                      args.handi, args.o25, args.elo or 0)
    top2 = [s for s in (args.pred_top2 or '').split('|') if s]
    predicted = {'direction': args.pred_dir, 'total': args.pred_total, 'top2': top2}
    r = LL.learn_from_result(args.case or 'manual', args.real, f, predicted)
    LL.print_report(r)
    return r


def _parse_csv():
    """读实战案例.csv → 已复盘场次(有真实比分)列表·保持文件顺序"""
    if not os.path.exists(CSV):
        return []
    with open(CSV, encoding='utf-8-sig', newline='') as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        real = (r.get('真实比分') or '').strip()
        if not real or ':' not in real:
            continue
        out.append(r)
    return out


def cmd_backfill(args):
    """用历史案例顺序回填学习（模拟"逐场进化"）·并给出学习前后对比"""
    rows = _parse_csv()
    if not rows:
        print('无已复盘案例'); return
    n_ok = 0
    log = []
    for r in rows:
        try:
            oh = float(r.get('主胜赔率') or r.get('home_odds') or 0) or None
            od = float(r.get('平局赔率') or 0) or None
            oa = float(r.get('客胜赔率') or 0) or None
            o25 = float(r.get('O25') or 0) or 1.9
            handi = float(r.get('让球') or 0)
        except Exception:
            oh = od = oa = None
        if not (oh and od and oa):
            continue
        league = r.get('联赛') or '?'
        # 🔴2026-09-12 修复: 优先用 raw 提取的完整特征（A+B 类）·退化到显式赔率 11 特征
        f = None
        try:
            import importlib.util as _iu
            _rp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tmp', 'raw_features.py')
            if os.path.exists(_rp):
                _spec = _iu.spec_from_file_location('raw_features', _rp)
                _rf = _iu.module_from_spec(_spec); _spec.loader.exec_module(_rf)
                _raws = __import__('glob').glob(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'case-library', 'raw', 'case%s*.md' % (r.get('case_id') or '').lstrip('case').lstrip('0')))
                if _raws:
                    _fd = _rf.extract_from_raw(_raws[0])
                    if _fd and len([v for v in _fd.values() if v is not None]) >= 12:
                        f = _fd
        except Exception:
            f = None
        if f is None:
            f = make_features(league, oh, od, oa, handi, o25)
        predicted = {'direction': None, 'total': None, 'top2': []}
        rep = LL.learn_from_result(r.get('case_id') or r.get('编号') or '?', r['真实比分'], f, predicted)
        log.append(rep)
        n_ok += 1
    print('=' * 68)
    print('📚 批量回填完成: %d 场（顺序学习·模拟逐场进化）' % n_ok)
    st = RM.status()
    print('  L1 在线: 方向n=%s 进球n=%s | 权重 方向=%s 进球=%s' % (
        st['n_direction'], st['n_goals'], st['weight_dir'], st['weight_goals']))
    print('  L2 增量: %s' % json.dumps(BU.status()['handicap'], ensure_ascii=False))
    print('  L3 规则: %d 条 | L4 案例: %d 场' % (
        len(P.load_json('rules/correction_rules.json', []) or []), EM.total_cases()))
    print('  ⚠️ CSV 无赛前赔率/让球列的场次被跳过（回填仅覆盖含特征列的部分）')
    print('=' * 68)
    return log


def cmd_status(args):
    st = RM.status()
    print('=== 在线学习状态 ===')
    print('L1 River: %s' % json.dumps(st, ensure_ascii=False))
    print('L2 增量表: %s' % json.dumps(BU.status(), ensure_ascii=False)[:400])
    print('L2 可合并: %s' % json.dumps(BU.propose_merge(), ensure_ascii=False)[:300])
    print('L3 规则: %d 条' % len(P.load_json('rules/correction_rules.json', []) or []))
    print('L4 案例: %d 场' % EM.total_cases())
    print('日志: %d 条' % len(P.read_log()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case'); ap.add_argument('--real')
    ap.add_argument('--league', default='?')
    ap.add_argument('--home-odds', type=float); ap.add_argument('--draw-odds', type=float)
    ap.add_argument('--away-odds', type=float); ap.add_argument('--handi', type=float, default=0)
    ap.add_argument('--o25', type=float, default=1.9); ap.add_argument('--elo', type=float, default=0)
    ap.add_argument('--pred-dir', type=int); ap.add_argument('--pred-total', type=float)
    ap.add_argument('--pred-top2', default='')
    ap.add_argument('--backfill', action='store_true')
    ap.add_argument('--status', action='store_true')
    a = ap.parse_args()
    LL.gitignore_state()
    if a.status: cmd_status(a)
    elif a.backfill: cmd_backfill(a)
    elif a.real: cmd_single(a)
    else: print(__doc__)


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    main()
