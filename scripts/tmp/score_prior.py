# -*- coding: utf-8 -*-
"""score_prior.py — 比分先验 / 口径仲裁 / 作用域开关（P0+P1+P2 结构修订·2026-09-29）

## 背景（用户审计提问「是否系统性结构问题」→ 查实三条结构性病）

① 口径无仲裁：同一场「期望总进球」有 5 个值（市场/查表/泊松/半场推断/子模型）而无权威源
   → 217/218/219 用市场口径、220 用 NL 口径；217/219 内部大小球用 NL、期望用市场（同场自相矛盾）

② 规则全局化 vs 事实场景化：anchor_market_check ④「主锚总进球 ≥ 期望−1.0」是全局一刀切约束
   在强小球场排除全部 1 球比分 → 系统性把主锚钉在 1:1（次优）
   而真实数据是【分盘口分大小球】的：
     主让1球+小球 1:0=15.8% vs 1:1=12.2%（n=3687·split_ok=True）
     主让1球+中档 1:0=12.8% vs 1:1=10.9%（n=14225·split_ok=True）
   同型已发作 19 次（R1-R19 全是「全局规则在某档位失效→打补丁」）

③ 约束靠事后校验而非事前接口：「超域」边界是 12 行文字清单（19 raw 提到 / 仅 2 脚本提到）
   → 同一天同联赛同批次出现 220 判折价、217/218/219 未判

## 本模块（单一入口·只提供判定素材·不覆盖 L2 硬核方向）

  handi_prior_table(handi, o25)      → P0 查 data/tmp/handi_score_table.json 本场格
  authority_resolve(metric, values)  → P1 按 canonical_sources.json 仲裁口径
  scope_check(scope, item)           → P2 按 scope_registry.json 判 use/ref/block

用法:
  from score_prior import handi_prior_table, authority_resolve, scope_check
"""
import os, json

_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE = {}


def _load(name):
    if name in _CACHE:
        return _CACHE[name]
    fp = os.path.join(_DIR, name)
    try:
        _CACHE[name] = json.load(open(fp, encoding='utf-8'))
    except Exception:
        _CACHE[name] = None
    return _CACHE[name]


# ── 分档 ──────────────────────────────────────────────────────
def _hbin(x):
    """亚盘盘口（主让为负）→ 档名（与 build 脚本一致）"""
    if x is None:
        return None
    if x <= -1.75: return '-2'
    if x <= -1.25: return '-1.5'
    if x <= -0.75: return '-1'
    if x <= -0.25: return '-0.5'
    if x <   0.25: return '0'
    if x <   0.75: return '+0.5'
    if x <   1.25: return '+1'
    return '+1.5'


def _obin(o):
    """O2.5 赔率 → big/mid/small"""
    if o is None:
        return None
    return 'big' if o < 1.70 else ('mid' if o <= 2.10 else 'small')


# ── P0：比分先验表 ────────────────────────────────────────────
def handi_prior_table(handi, o25, min_n=40):
    """盘口 × 大小球 → 本场比分先验（P0·替代全局下界约束）

    返回 dict:
      ok        : 本格是否可用于调序（split_ok 且 n≥min_n）
      cell      : 格键（如 '-1|small'）
      n         : 样本量
      split_ok  : 时间分割 train/test 首选是否一致
      top       : [[比分, 百分比], ...] 该格实测 Top
      boost     : {比分: 相对权重}（ok 时给出·供调序用·不排除任何候选）
      reason    : 三态说明

    🔴 铁律: 仅 ok=True 才参与调序；ok=False 时返回原始 top 但标『不调序』
    🔴 本函数只提供【排序素材】·不排除候选·不反转方向（L2 硬核优先）
    """
    res = {'ok': False, 'cell': None, 'n': 0, 'split_ok': False,
           'top': [], 'boost': {}, 'reason': ''}
    t = _load('handi_score_table.json')
    if not t:
        res['reason'] = '无 handi_score_table.json（三态·不调序）'
        return res
    hb, ob = _hbin(handi), _obin(o25)
    if hb is None or ob is None:
        res['reason'] = '盘口/大小球缺失 → 不调序'
        return res
    key = '%s|%s' % (hb, ob)
    c = (t.get('cells') or {}).get(key)
    if not c or not c.get('n'):
        res['cell'] = key
        res['reason'] = '该格无样本 → 不调序'
        return res
    res['cell'], res['n'] = key, c['n']
    res['top'] = c.get('top', [])
    res['split_ok'] = bool(c.get('split_ok'))
    if c['n'] < min_n:
        res['reason'] = '样本不足(n=%d<%d) → 不调序' % (c['n'], min_n)
        return res
    if not c.get('split_ok'):
        res['reason'] = ('时间分割不稳定(train=%s/test=%s) → 不调序（仅作参考）'
                         % (c.get('top1_train'), c.get('top1_test')))
        return res
    res['ok'] = True
    res['reason'] = '查表命中 %s(n=%d·split_ok=True) → 以该格实测分布调序' % (key, c['n'])
    mx = max((v for _, v in c.get('top', [])), default=1) or 1
    res['boost'] = {k: round(v / mx, 3) for k, v in c.get('top', [])}
    return res


# ── P1：口径仲裁 ──────────────────────────────────────────────
def authority_resolve(metric, values, scope=None):
    """按 canonical_sources.json 仲裁同一量的多源取值（P1）

    metric : 'expect_total' | 'over_under' | 'direction' | 'net_band' | 'score_prior'
    values : {'market': 2.24, 'table': 2.34, ...}（键名自由·与 candidates 对齐即可）
    scope  : 命中的子模型作用域（'nl'/'europe'/'league5'/None）→ 若该 scope 覆盖此量则切权威源

    返回 dict(authority, value, candidates, conflicts[], ok, msg)
    🔴 冲突不改变判定权·仅留痕（市场源优先铁律）
    """
    res = {'metric': metric, 'authority': None, 'value': None,
           'candidates': dict(values or {}), 'conflicts': [], 'ok': True, 'msg': ''}
    cfg = _load('canonical_sources.json')
    if not cfg:
        res['ok'] = False
        res['msg'] = '无 canonical_sources.json → 不仲裁（三态）'
        return res
    m = (cfg.get('metrics') or {}).get(metric)
    if not m:
        res['ok'] = False
        res['msg'] = '未知量 %s（未登记）→ 不仲裁' % metric
        return res
    auth = m.get('authority')
    if scope:
        sc = scope_check(scope, metric)
        if sc in ('use',) and m.get('submodel'):
            auth = m['submodel'].split('（')[0].split('(')[0].strip()
            res['msg'] = '作用域 %s 覆盖该量 → 权威源切换为 %s' % (scope, auth)
    res['authority'] = auth
    # 取值：先按精确键，再按前缀模糊
    if values:
        for k, v in values.items():
            if k == auth or (auth and k.startswith(auth.split('(')[0].strip())):
                if res['value'] is None:
                    res['value'] = v
        if res['value'] is None and auth in values:
            res['value'] = values[auth]
    if res['value'] is None and values:
        res['ok'] = False
        res['msg'] = (res['msg'] + ' ｜ ' if res['msg'] else '') + \
                     '权威源 %s 无取值（给出来源: %s）' % (auth, ','.join(values))
        return res
    tol = m.get('tol') or 0
    if tol and isinstance(res['value'], (int, float)):
        for k, v in (values or {}).items():
            if isinstance(v, (int, float)) and abs(v - res['value']) > tol:
                res['conflicts'].append('%s=%s 偏离权威 %s=%s 超容差 %s' % (k, v, auth, res['value'], tol))
    if not res['msg']:
        res['msg'] = '以 %s 为准（%s）' % (auth, m.get('on_conflict') or '')
    return res


# ── P2：作用域开关 ────────────────────────────────────────────
def scope_check(scope, item):
    """作用域开关（P2）→ 'use' | 'ref' | 'block' | 'unknown'

    scope : 'nl' | 'europe' | 'league5' | None
    item  : 量名/模块名（如 'step6_tiers'、'score_depth_table'、'prior(R2)'）

    匹配规则: 先精确，再『前缀/子串』（item 出现在声明项中，或声明项出现在 item 中）
    """
    reg = _load('scope_registry.json')
    if not reg or not scope:
        return 'unknown'
    sc = (reg.get('scopes') or {}).get(scope)
    if not sc:
        return 'unknown'
    for lvl in ('block', 'use', 'ref'):
        for decl in sc.get(lvl, []) or []:
            d = str(decl).split('(')[0].split('（')[0].strip()
            if not d:
                continue
            if d == item or d in item or item in d:
                return lvl
    return (reg.get('defaults') or {}).get('unknown', 'ref')


def scope_for_league(league_id=None, league_name=None):
    """按赛事识别作用域（与 SK 触发口径一致·仅识别不判定）"""
    reg = _load('scope_registry.json')
    if not reg:
        return None
    nm = league_name or ''
    for sid, sc in (reg.get('scopes') or {}).items():
        mt = sc.get('match') or {}
        if league_id is not None and league_id in (mt.get('league_id') or []):
            return sid
        # 🔴2026-10-20 试跑修(P1·存在≠活跃): 原实现**漏读 `keys` 字段**——
        #   league5 的匹配口径写在 `keys`（英超/西甲/德甲/意甲/法甲 + E0/SP1/D1/I1/F1），
        #   而本函数只查 name_contains/league_name_contains → 五大联赛恒「未识别」
        #   → 作用域开关在主战场从未生效（全部落「默认 ref 保守」）。
        _kws = ((mt.get('name_contains') or []) + (mt.get('league_name_contains') or [])
                + (mt.get('keys') or []))
        for kw in _kws:
            if not kw:
                continue
            if kw == nm or kw in nm:
                return sid
    return None


# ── CLI（自检/冒烟） ──────────────────────────────────────────
if __name__ == '__main__':
    import sys
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    print('== P0 比分先验表（三场实测复现）==')
    for hd, o25, tag in [(-1.0, 2.315, '217/219 主让1球+小球'),
                         (1.0, 2.17, '218 受让1球+小球'),
                         (-2.0, 1.43, '220 主让2球+大球')]:
        r = handi_prior_table(hd, o25)
        print(' %-22s cell=%-9s n=%-6d ok=%-5s split_ok=%-5s top=%s | %s'
              % (tag, r['cell'], r['n'], r['ok'], r['split_ok'],
                 ' '.join('%s=%.1f%%' % (k, v) for k, v in r['top'][:4]), r['reason']))
    print()
    print('== P1 口径仲裁（217 期望总进球·五源）==')
    r = authority_resolve('expect_total',
                          {'market': 2.24, 'table': 2.34, 'poisson': 2.32, 'ht': 2.66, 'submodel': 2.93})
    print(' authority=%s value=%s ok=%s conflicts=%s' % (r['authority'], r['value'], r['ok'], r['conflicts']))
    print()
    print('== P2 作用域开关 ==')
    for item in ['step6_tiers', 'score_depth_table', 'prior(R2)', 'fair_edge(R10)', 'five_league_skew_threshold', 'handi_score_table']:
        print('  nl × %-28s → %s' % (item, scope_check('nl', item)))
    print(' scope_for_league(5)=%s  scope_for_league(None,"意甲")=?' % scope_for_league(5))
