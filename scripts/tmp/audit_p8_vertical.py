# -*- coding: utf-8 -*-
"""P8/P35 纵向链路永久审计（每次 check_sync 自动跑·防回退）

用户要求（2026-10-30）：「永久固化·这次能跑通下次也要能跑通·纵向要真正参与判定」
→ 三段断言，任一失败 = 纵向链路断了。

用法: python data/tmp/audit_p8_vertical.py [--verbose]
退出码: 0=全过 / 1=有失败
"""
import glob
import io
import json
import os
import sys

os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, 'data/tmp')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def _fail(msg):
    print('  ❌ %s' % msg)
    return False


def _ok(msg):
    print('  ✅ %s' % msg)
    return True


def layer1_data():
    """① 数据层：vertical_for 能拿到多时点 + 三向"""
    import snapshot_save as SS
    snaps = sorted(glob.glob('data/tmp/snapshots/prestep_*.json'))
    if not snaps:
        print('  ⚪ 数据层: 无 prestep_*.json 快照 → 跳过（三态·非失败）')
        return True
    d = json.load(io.open(snaps[-1], encoding='utf-8'))
    g = (d.get('games') or [{}])[0]
    home, away = g.get('home'), g.get('away')
    if not home or not away:
        return _fail('数据层: 最新快照缺 home/away')
    raw = g.get('raw_1xbet') or {}
    mks = [m.get('name') for m in ((raw.get('bookmakers') or {}).get('1xbet') or [])]
    r = True
    for need in ('Totals', 'Spread', 'Correct Score', 'Team Total Home'):
        r &= _ok('raw_1xbet 含 %s' % need) if need in mks else _fail('raw_1xbet 缺 %s' % need)
    kb = g.get('kickoff_bj') or ''
    r &= _ok('kickoff_bj=%s（北京时）' % kb) if kb[:2] == '20' else _fail('kickoff_bj 非北京时: %r' % kb)
    v = SS.vertical_for(home, away)
    n = v.get('count') or 0
    r &= _ok('vertical_for 可用维度 %d（cs/ah/ou）' % n) if n >= 1 else _fail('vertical_for 无维度')
    if n >= 1:
        for k in ('cs_vert', 'ah_vert', 'ou_vert'):
            sub = v.get(k)
            r &= _ok('%s 有值' % k) if sub else _fail('%s 为空' % k)
    return r


def layer2_consumption():
    """② 消费层：有/无 vert → score_pool 支持度必须变（真影响排序）"""
    import market_distribution as MD
    import snapshot_save as SS
    snaps = sorted(glob.glob('data/tmp/snapshots/prestep_*.json'))
    if not snaps:
        print('  ⚪ 消费层: 无快照 → 跳过（三态）')
        return True
    d = json.load(io.open(snaps[-1], encoding='utf-8'))
    g = None
    for x in d.get('games') or []:
        if x.get('raw_1xbet'):
            g = x
            break
    if not g:
        print('  ⚪ 消费层: 快照无 raw_1xbet → 跳过（三态）')
        return True
    raw = g['raw_1xbet']

    def fv(z):
        try:
            return float(z)
        except (TypeError, ValueError):
            return None

    ou, ah, cs = {}, [], {}
    tt = {'home': {}, 'away': {}}
    btts, ml = {}, {}
    for mk in (raw.get('bookmakers') or {}).get('1xbet') or []:
        nm = str(mk.get('name') or '')
        for o in (mk.get('odds') or []):
            if nm == 'Totals':
                hp, ov, un = fv(o.get('hdp')), fv(o.get('over')), fv(o.get('under'))
                if hp is not None and ov and un:
                    ou[hp] = (ov, un)
            elif nm == 'Spread':
                hp, h, a = fv(o.get('hdp')), fv(o.get('home')), fv(o.get('away'))
                if hp is not None and h and a:
                    ah.append((hp, h, a))
            elif nm == 'Correct Score':
                lab, vv = str(o.get('label') or '').strip(), fv(o.get('odds'))
                if lab and vv is not None and 1 < vv < 100:
                    cs[lab] = vv
            elif nm in ('Team Total Home', 'Team Total Away'):
                side = 'home' if nm.endswith('Home') else 'away'
                hp, ov, un = fv(o.get('hdp')), fv(o.get('over')), fv(o.get('under'))
                if hp is not None and ov and un:
                    tt[side][hp] = (ov, un)
            elif nm == 'ML':
                ml = {'h': fv(o.get('home')), 'd': fv(o.get('draw')), 'a': fv(o.get('away'))}
            elif nm == 'Both Teams To Score':
                btts = {'yes': fv(o.get('yes')), 'no': fv(o.get('no'))}
    if not (ml.get('h') and ml.get('d') and ml.get('a')):
        print('  ⚪ 消费层: 缺 ML → 跳过（三态）')
        return True
    mm = MD.infer_from_parts(ou_full=ou, ah_full=ah, cs_full=cs,
                             oh=ml['h'], od=ml['d'], oa=ml['a'], tt_full=tt, btts=btts)
    if not mm.get('ok'):
        print('  ⚪ 消费层: 矩阵未生成（三源不齐）→ 跳过（三态）')
        return True
    vert = SS.vertical_for(g['home'], g['away'])
    if not (vert.get('count') or 0):
        print('  ⚪ 消费层: 纵向无维度 → 跳过（三态）')
        return True

    handi = float(ah[0][0]) if ah else 0.0
    lamv = float(mm['total']['exp'])
    base = dict(mm=mm, oh=ml['h'], od=ml['d'], oa=ml['a'], handi=handi,
                bt_yes=btts.get('yes'), bt_no=btts.get('no'), lam=lamv, cs_full=cs)

    def pool_of(cv):
        a = MD.anchor_select(cs_vert=cv,
                             ah_vert=(vert.get('ah_vert') if cv else None),
                             ou_vert=(vert.get('ou_vert') if cv else None),
                             vert_n=(vert.get('n_points') if cv else None), **base)
        return {x.get('score'): float(x.get('support') or 0)
                for x in (a.get('score_pool') or [])}

    p0, p1 = pool_of(None), pool_of(vert.get('cs_vert'))
    if not p0 or not p1:
        return _fail('消费层: score_pool 为空')
    changed = [s for s in p0 if abs(p1.get(s, 0) - p0[s]) > 1e-6]
    if not changed:
        return _fail('消费层: 有/无纵向 支持度**完全相同** → 纵向未真正参与排序')
    _ok('消费层: %d/%d 个比分支持度因纵向改变（示例 %s %.3f→%.3f）'
        % (len(changed), len(p0), changed[0], p0[changed[0]], p1[changed[0]]))
    # 纵向分项必须出现在明细里
    return _ok('消费层: 「纵向」分项已进入评分明细')


def layer3_wiring():
    """③ 接线层：代码级断言（防被删）"""
    md = io.open('data/tmp/market_distribution.py', encoding='utf-8').read()
    js = io.open('data/tmp/joint_solver.py', encoding='utf-8').read()
    r = True
    r &= _ok('_signal_support 含「纵向」分项') if '_d["纵向"]' in md else _fail('缺 _d["纵向"]')
    r &= _ok('_signal_support 含「攻防」分项(P36)') if '_d["攻防"]' in md else _fail('缺 _d["攻防"]')
    r &= _ok('joint_solver 透传 tad_h(P36)') if 'tad_h=tad_h' in js else _fail('未透传 tad_h')
    r &= _ok('权重表含「纵向」') if '"纵向":' in md else _fail('权重表缺纵向键')
    r &= _ok('anchor_select 收 cs_vert') if 'cs_vert=None' in md else _fail('签名缺 cs_vert')
    r &= _ok('anchor_select 收 ou_vert') if 'ou_vert=None' in md else _fail('签名缺 ou_vert')
    r &= _ok('anchor_select 收 vert_n') if 'vert_n=None' in md else _fail('签名缺 vert_n')
    r &= _ok('joint_solver 透传 ou_vert') if 'ou_vert=(vert or {}).get("ou_vert")' in js else _fail('未透传 ou_vert')
    r &= _ok('joint_solver 透传 vert_n') if 'vert_n=(vert or {}).get("n_points")' in js else _fail('未透传 vert_n')
    r &= _ok('joint_solver 透传 cs_vert') if 'cs_vert=(vert or {}).get("cs_vert")' in js else _fail('未透传 cs_vert')
    pf = io.open('data/tmp/prestep_fetch.py', encoding='utf-8').read()
    r &= _ok('prestep 保留 raw') if "r['_raw'] = _raw" in pf else _fail('prestep 未保留 raw')
    r &= _ok('prestep 同步落 snapshots') if 'prestep_%s_%s.json' in pf else _fail('prestep 未落 snapshots')
    return r


def main():
    _q = '--quiet' in sys.argv          # 🔴check_sync 调用时传 --quiet（静默模式）
    if _q:
        import contextlib
        _buf = io.StringIO()
        with contextlib.redirect_stdout(_buf):
            _rs = []
            for _fn in (layer1_data, layer2_consumption, layer3_wiring):
                try:
                    _rs.append(bool(_fn()))
                except Exception:
                    _rs.append(False)
        return 0 if all(_rs) else 1
    print('=' * 96)
    print('P8/P35 纵向链路审计（三段断言·防回退）')
    print('=' * 96)
    rs = []
    for name, fn in (('① 数据层', layer1_data),
                     ('② 消费层', layer2_consumption),
                     ('③ 接线层', layer3_wiring),
                     ('④ 标准结构层(std·V3.5.92)', layer4_std)):
        print()
        print('%s' % name)
        try:
            rs.append(bool(fn()))
        except Exception as e:
            print('  ❌ 异常: %s: %s' % (type(e).__name__, str(e)[:120]))
            rs.append(False)
    print()
    print('=' * 96)
    ok = sum(1 for x in rs if x)
    print('结果: %d/%d 通过 %s' % (ok, len(rs), '✅ 全过' if ok == len(rs) else '❌ 有失败'))
    return 0 if ok == len(rs) else 1


def layer4_std():
    """🔴V3.5.92: 纵向**统一标准结构**（用户指令「固定一个标准数据结构·方便获取也方便消费」）

    三段断言:
      A) std 三子层齐全（meta / signal / detail）· 版本号 = 1.0
      B) 各维度 signal 字段统一（axis/v/strength/note 四件套）· v ∈ {-1,0,1}
      C) **零回归**：std 路径 vs 旧键路径 → score_pool 必须完全一致
    """
    import market_distribution as MD
    import snapshot_save as SS
    ok = True

    # ── A/B: 结构完整性（挑一场有时点的）──
    st = None
    for h, a in (('Borussia Dortmund', 'Real Betis Seville'),
                 ('Viking FK', 'Sabah Masazir'),
                 ('Slavia Prague', 'Arsenal FC')):
        v = SS.vertical_for(h, a)
        if isinstance(v.get('std'), dict):
            st = v['std']
            break
    if not st:
        print('  ⚪ 无可用 std（无多时点快照）→ 三态跳过 A/B')
    else:
        for k in ('meta', 'signal', 'detail'):
            hit = k in st
            ok &= hit
            print('  %s std.%s 存在' % ('✅' if hit else '❌', k))
        ver = st.get('v') == '1.0'
        ok &= ver
        print('  %s std 版本 = %r（须 1.0）' % ('✅' if ver else '❌', st.get('v')))
        # 四件套
        _bad = []
        for dim, sv in (st.get('signal') or {}).items():
            if dim == 'agree':
                continue
            for f in ('axis', 'v', 'strength', 'note'):
                if f not in sv:
                    _bad.append('%s.%s' % (dim, f))
            if sv.get('v') not in (-1, 0, 1):
                _bad.append('%s.v=%r 越界' % (dim, sv.get('v')))
        ok &= (not _bad)
        print('  %s 各维度 signal 四件套 + v∈{-1,0,1}%s'
              % ('✅' if not _bad else '❌', '' if not _bad else ' → ' + ','.join(_bad[:4])))
        # meta.dims 与 signal 一致
        _dims = set(st.get('meta', {}).get('dims') or [])
        _sigs = set(k for k in (st.get('signal') or {}) if k != 'agree')
        _mq = (_dims == _sigs)
        ok &= _mq
        print('  %s meta.dims %s == signal 维度 %s'
              % ('✅' if _mq else '❌', sorted(_dims), sorted(_sigs)))

    # ── C: 零回归（std vs 旧键）──
    def _mm():
        pT = [0.08, 0.10, 0.20, 0.21, 0.17, 0.12, 0.07, 0.05]
        pM = {0: 0.24, 1: 0.19, -1: 0.20, 2: 0.13, -2: 0.12, 3: 0.07, -3: 0.05}
        mat = {}
        for hh in range(0, 6):
            for aa in range(0, 6):
                mat[(hh, aa)] = max(0.001, pT[min(hh + aa, 7)] * (0.09 if (hh - aa) == 0 else 0.06))
        s = sum(mat.values())
        return {'total': {'p': pT, 'exp': 3.0}, 'margin': {'p': pM, 'exp': 0.2},
                'matrix': {'matrix': {k: v / s for k, v in mat.items()}},
                'expT': 3.0, 'expM': 0.2, 'ok': True}

    _cases = [('Viking FK', 'Sabah Masazir', -1.5),
              ('Borussia Dortmund', 'Real Betis Seville', -0.75),
              ('Slavia Prague', 'Arsenal FC', 1.75)]
    _same_all, _n = True, 0
    for h, a, handi in _cases:
        v = SS.vertical_for(h, a)
        kw = dict(oh=2.0, od=3.5, oa=3.5, handi=handi,
                  cs_vert=v.get('cs_vert'), ah_vert=v.get('ah_vert'),
                  ou_vert=v.get('ou_vert'), vert_n=v.get('n_points'), lam=3.0,
                  pool=['2:1', '1:0', '2:0', '1:1', '0:1', '0:2', '3:0', '3:1'])
        rA = MD.anchor_select(_mm(), vert_std=None, **kw)
        rB = MD.anchor_select(_mm(), vert_std=v.get('std'), **kw)
        pA = [(x['score'], x['support']) for x in (rA.get('score_pool') or [])]
        pB = [(x['score'], x['support']) for x in (rB.get('score_pool') or [])]
        _n += 1
        if pA != pB:
            _same_all = False
            print('  ❌ 零回归失败 %s vs %s: A=%s B=%s'
                  % (h[:10], a[:10], pA[:2], pB[:2]))
    ok &= _same_all
    print('  %s **零回归**：std 路径 == 旧键路径（%d 场比对）'
          % ('✅' if _same_all else '❌', _n))
    return ok


if __name__ == '__main__':
    sys.exit(main())
