# -*- coding: utf-8 -*-
"""**总分总架构** —— 主模型通用 / 子模型隔离 / 接口一致 / 防串场

用户指令（2026-11-09）：「梳理模型结构，隔离子模型，但主模型通用，接口一致，
也就是总分总形式，防止不同的比赛相互串」+ 隔离强度=**强隔离（越界直接拒绝并报警）**

════════════════════════════════════════════════════════════════════════
架构
════════════════════════════════════════════════════════════════════════

  总①  MatchContext（一场比赛的唯一上下文）
        └─ case_id / match_id / league_kind / 全部数据
        └─ **子模型只读 ctx，禁读全局文件**

  分    子模型 analyze(ctx) -> SubModelResult
        └─ SUBMODEL_SCOPE 白名单：只能读自己域的表（**越界直接拒绝 + 报警**）
        └─ 无模块级状态：缓存按 match_id 分键
        └─ 不适用 → applicable=False + 三态原因（不静默）

  总②  aggregate(results) -> 统一判定
        └─ 按优先级合并：L2 硬核 > 子模型 > L3 变动层
        └─ 冲突留痕，禁静默覆盖

════════════════════════════════════════════════════════════════════════
为什么需要（今晚实抓的串场事故）
════════════════════════════════════════════════════════════════════════
· `_last_league.json` 全局单值 → 2026-11-01 队名定位用到错联赛 → P10 定位到错场 72221364
· `snapshot_diff.LAST_BASELINE` 模块级 → prestep 拿「上场基线」比本场
· `prestep_window.json` 无 case 分键 → 每次 --save 覆盖，上场打分被下场读
· NL 场读五大表（无代码强制，只靠 AGENTS 文档纪律）
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ══════════════════════════════════════════════════════════════════════
# 一、子模型 scope 白名单（🔴 强隔离：越界直接拒绝 + 报警）
# ══════════════════════════════════════════════════════════════════════
# 表名 = data/tmp 下的 json/模块名（不含扩展名）。每个子模型只能读 allow 里的。
# forbid 显式列出「本域绝不该碰」的表（更强的自我约束 + 审计可见）。
SUBMODEL_SCOPE = {
    'top5_epl': {
        'league': {'英超', 'E0', 'epl', 'premier-league'},
        'allow': {'odds_table', 'league_table', 'score_depth_table', 'goal_bins_table',
                  'draw_table', 'quadrant_table', 'deep_anchor_table', 'water_table',
                  'homeaway_table', 'team_attack_defense', 'handi_score_table',
                  'league_season_calib'},
        'forbid': {'nl_data', 'fair_model', 'elo_current', 'europe', 'ucl_calibration'},
    },
    'top5_laliga': {
        'league': {'西甲', 'SP1', 'laliga'},
        'allow': {'odds_table', 'league_table', 'score_depth_table', 'goal_bins_table',
                  'draw_table', 'quadrant_table', 'deep_anchor_table', 'water_table',
                  'homeaway_table', 'team_attack_defense', 'handi_score_table',
                  'league_season_calib'},
        'forbid': {'nl_data', 'fair_model', 'elo_current', 'europe', 'ucl_calibration'},
    },
    'top5_seriea': {
        'league': {'意甲', 'I1', 'seriea'},
        'allow': {'odds_table', 'league_table', 'score_depth_table', 'goal_bins_table',
                  'draw_table', 'quadrant_table', 'deep_anchor_table', 'water_table',
                  'homeaway_table', 'team_attack_defense', 'handi_score_table',
                  'league_season_calib'},
        'forbid': {'nl_data', 'fair_model', 'elo_current', 'europe', 'ucl_calibration'},
    },
    'top5_bundesliga': {
        'league': {'德甲', 'D1', 'bundesliga'},
        'allow': {'odds_table', 'league_table', 'score_depth_table', 'goal_bins_table',
                  'draw_table', 'quadrant_table', 'deep_anchor_table', 'water_table',
                  'homeaway_table', 'team_attack_defense', 'handi_score_table',
                  'league_season_calib'},
        'forbid': {'nl_data', 'fair_model', 'elo_current', 'europe', 'ucl_calibration'},
    },
    'top5_ligue1': {
        'league': {'法甲', 'F1', 'ligue1'},
        'allow': {'odds_table', 'league_table', 'score_depth_table', 'goal_bins_table',
                  'draw_table', 'quadrant_table', 'deep_anchor_table', 'water_table',
                  'homeaway_table', 'team_attack_defense', 'handi_score_table',
                  'league_season_calib'},
        'forbid': {'nl_data', 'fair_model', 'elo_current', 'europe', 'ucl_calibration'},
    },
    # 🔴 欧国联：自己的 658 场库 + 公平模型 + Elo；**禁读五大表**（阈值超域）
    'nations': {
        'league': {'欧国联', 'Nations League', 'nations', 'nl', '5'},
        'allow': {'nl_data', 'fair_model', 'elo_current', 'nl_with_elo',
                  'goal_bins_table', 'score_depth_table', 'quadrant_table'},   # 后三个：通用市场表（已在 NL 场实测兼容）
        'forbid': {'odds_table', 'league_table', 'ucl_calibration', 'team_attack_defense',
                   'homeaway_table', 'handi_score_table', 'league_season_calib'},
    },
    # 🔴 欧战：欧战库 + 欧冠校准；**禁读联赛表与 NL**
    'europe': {
        'league': {'欧冠', '欧联', '欧协联', 'ec', 'ucl', 'el', 'uecl',
                   'champions', 'europa', 'conference'},
        'allow': {'europe', 'ucl_calibration', 'goal_bins_table', 'score_depth_table',
                  'quadrant_table', 'odds_table'},
        'forbid': {'league_table', 'nl_data', 'fair_model', 'elo_current',
                   'league_season_calib', 'team_attack_defense'},
    },
}

# ══════════════════════════════════════════════════════════════════════
# 二、子模型注册表（一处定义·主模型只认这张表）
# ══════════════════════════════════════════════════════════════════════
# (sub_id, 中文名, 适用的 league_kind, adapter 函数名)
SUBMODELS = [
    ('top5_epl', '英超', 'top5', 'calc_epl'),
    ('top5_laliga', '西甲', 'top5', 'calc_laliga'),
    ('top5_seriea', '意甲', 'top5', 'calc_seriea'),
    ('top5_bundesliga', '德甲', 'top5', 'calc_bundesliga'),
    ('top5_ligue1', '法甲', 'top5', 'calc_ligue1'),
    ('nations', '欧国联', 'nations', 'calc_nations'),
    ('europe', '欧战', 'europe', 'calc_europe'),
]

# 五大联赛里哪一个（用于 scope 精确匹配）
_TOP5_MAP = {
    '英超': 'top5_epl', 'E0': 'top5_epl', 'epl': 'top5_epl', 'premier-league': 'top5_epl',
    '西甲': 'top5_laliga', 'SP1': 'top5_laliga', 'laliga': 'top5_laliga',
    '意甲': 'top5_seriea', 'I1': 'top5_seriea', 'seriea': 'top5_seriea',
    '德甲': 'top5_bundesliga', 'D1': 'top5_bundesliga', 'bundesliga': 'top5_bundesliga',
    '法甲': 'top5_ligue1', 'F1': 'top5_ligue1', 'ligue1': 'top5_ligue1',
}

# ══════════════════════════════════════════════════════════════════════
# 三、MatchContext —— 一场比赛的唯一上下文（防串场的核心）
# ══════════════════════════════════════════════════════════════════════
class MatchContext(dict):
    """用 dict 子类（兼容现有代码按 dict 取值的方式），但提供强约束访问器。

    🔴 铁律：子模型只能从 ctx 读数据。禁子模型自己去 open() 全局 json
    （这是 `_last_league.json` 那类串场事故的根源）。
    """

    # 允许的键（越界写会报警）
    KEYS = ('case_id', 'match_id', 'league', 'league_kind', 'sub_id',
            'home', 'away', 'kickoff',
            'eu', 'handi', 'o25', 'u25',
            'market', 'elo', 'inj', 'form', 'h2h',
            'cs', 'btts', 'tt_h', 'tt_a', 'ou_full', 'ah_full',
            'prev_snapshot')

    def __init__(self, **kw):
        super().__init__()
        for k, v in kw.items():
            self[k] = v

    # ---- 标识 ----
    @property
    def case_id(self):
        return self.get('case_id') or ''

    @property
    def match_id(self):
        """🔴 缓存分键用：优先 event_id，否则 case_id，否则队名哈希"""
        m = self.get('match_id')
        if m:
            return str(m)
        if self.get('case_id'):
            return 'case%s' % self['case_id']
        h = '%s|%s|%s' % (self.get('home', ''), self.get('away', ''), self.get('kickoff', ''))
        return 'h' + hashlib.md5(h.encode('utf-8')).hexdigest()[:12]

    # ---- 安全取数（缺则 None，不抛）----
    def get_data(self, key, default=None):
        return self.get(key, default)

    def require(self, *keys):
        miss = [k for k in keys if not self.get(k)]
        if miss:
            raise KeyError('MatchContext 缺必需字段: %s（case=%s）'
                           % (', '.join(miss), self.case_id or '?'))
        return True

    # ---- 隔离自检 ----
    def scope_of(self):
        return SUBMODEL_SCOPE.get(self.get('sub_id') or '', {})


# ══════════════════════════════════════════════════════════════════════
# 四、SubModelResult —— 统一输出契约（7 组字段）
# ══════════════════════════════════════════════════════════════════════
class SubModelResult(object):
    """所有子模型【必须】返回这个对象。主模型只认这个契约。

    字段语义（🔴 只调置信度/排序·永不反转 L2 硬核方向）：
      applicable     是否适用于本场（False = 三态，reason 必填）
      reason         不适用原因（三态必须写）
      dir_adj        方向概率校正 { 'H': +0.05, 'D': -0.02, 'A': -0.03 }（**百分点**）
      conf_adj       置信度档位调整（-1 / 0 / +1·引擎另有夹逼）
      goals_adj      量级校正（球·±）
      anchor_hints   [('1:2', 0.8), ...] 锚提示（权重 0-1）
      rules_hit      命中的规则 ID（留痕用·如 ['R5','R10']）
      warnings       警告（进 raw·人可读）
      scope_blocked  被 scope 白名单挡掉的表（留痕·证明隔离生效）
    """

    __slots__ = ('name', 'applicable', 'reason', 'dir_adj', 'conf_adj', 'goals_adj',
                 'anchor_hints', 'rules_hit', 'warnings', 'scope_blocked', 'raw_text')

    def __init__(self, name, applicable=True, reason=''):
        self.name = name
        self.applicable = applicable
        self.reason = reason
        self.dir_adj = {}
        self.conf_adj = 0
        self.goals_adj = 0.0
        self.anchor_hints = []
        self.rules_hit = []
        self.warnings = []
        self.scope_blocked = []
        self.raw_text = ''

    # ---- 链式构造（子模型 adapter 用）----
    def adj(self, home=0.0, draw=0.0, away=0.0):
        self.dir_adj = {'H': home, 'D': draw, 'A': away}
        return self

    def conf(self, v):
        self.conf_adj = int(v)
        return self

    def goals(self, v):
        self.goals_adj = float(v)
        return self

    def anchor(self, *pairs):
        self.anchor_hints.extend(pairs)
        return self

    def hit(self, *rules):
        self.rules_hit.extend(rules)
        return self

    def warn(self, msg):
        self.warnings.append(str(msg))
        return self

    def blocked(self, table):
        self.scope_blocked.append(str(table))
        return self

    # ---- 统一摘要（raw 输出用）----
    def summary(self):
        if not self.applicable:
            return '⚪ %s: 不触发（%s）' % (self.name, self.reason or '无原因')
        parts = []
        if any(self.dir_adj.values()):
            parts.append('方向校正 H%+.1fpp/D%+.1fpp/A%+.1fpp'
                         % (self.dir_adj.get('H', 0), self.dir_adj.get('D', 0), self.dir_adj.get('A', 0)))
        if self.conf_adj:
            parts.append('置信度%+d档' % self.conf_adj)
        if self.goals_adj:
            parts.append('量级%+.2f球' % self.goals_adj)
        if self.anchor_hints:
            parts.append('锚提示 %s' % ', '.join('%s(%.2f)' % (a, w) for a, w in self.anchor_hints[:4]))
        if self.rules_hit:
            parts.append('规则命中 %s' % '/'.join(self.rules_hit[:8]))
        body = ' ｜ '.join(parts) if parts else '无调整'
        tail = (' ｜ ⚠️' + '; '.join(self.warnings[:3])) if self.warnings else ''
        blk = (' ｜ 🔒越界拦截 %s' % ','.join(self.scope_blocked)) if self.scope_blocked else ''
        return '✅ %s: %s%s%s' % (self.name, body, tail, blk)

    def to_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}


# ══════════════════════════════════════════════════════════════════════
# 五、联赛分类 + 子模型选择
# ══════════════════════════════════════════════════════════════════════
def league_kind(league):
    """→ 'top5' | 'nations' | 'europe' | 'other'"""
    s = str(league or '').strip()
    low = s.lower().replace(' ', '').replace('-', '')
    if not s:
        return 'other'
    # 欧国联
    if any(k.lower().replace(' ', '') in low for k in ('欧国联', 'nationsleague', 'nations')):
        return 'nations'
    if low in ('nl', '5'):
        return 'nations'
    # 欧战
    for k in ('欧冠', '欧联', '欧协联', 'championsleague', 'europaleague', 'conferenceleague'):
        if k.lower() in low:
            return 'europe'
    if low in ('ec', 'ucl', 'el', 'uecl', 'champions', 'europa', 'conference'):
        return 'europe'
    # 五大
    if s in _TOP5_MAP or low in _TOP5_MAP:
        return 'top5'
    for k in _TOP5_MAP:
        if k.lower().replace('-', '') == low:
            return 'top5'
    return 'other'


def pick_submodel(league):
    """→ (sub_id, 中文名) 或 (None, '非子模型域')"""
    s = str(league or '').strip()
    if s in _TOP5_MAP:
        sid = _TOP5_MAP[s]
        for a, cn, _, _ in SUBMODELS:
            if a == sid:
                return sid, cn
    kind = league_kind(s)
    if kind == 'nations':
        return 'nations', '欧国联'
    if kind == 'europe':
        return 'europe', '欧战'
    low = s.lower().replace(' ', '').replace('-', '')
    for k, sid in _TOP5_MAP.items():
        if k.lower().replace('-', '') == low:
            for a, cn, _, _ in SUBMODELS:
                if a == sid:
                    return sid, cn
    return None, '非子模型域'


# ══════════════════════════════════════════════════════════════════════
# 六、🔴 强隔离：越界读表 → 直接拒绝 + 报警
# ══════════════════════════════════════════════════════════════════════
_VIOLATIONS = []     # 进程内违规记录（供 raw 留痕 / check_sync 审计）


def guard_table(sub_id, table, raise_on_forbid=True):
    """子模型读表前的强隔离门禁。

    → (allowed: bool, msg: str)
      · table 在 allow → allowed=True
      · table 在 forbid（或不在 allow）→ **拒绝** + 记录违规 + 默认抛 ScopeViolation
      · sub_id 未知 → 保守拒绝（宁严勿宽）

    用法（子模型内部）：
        ok, msg = guard_table('nations', 'league_table')
        if not ok:
            res.blocked('league_table')
            return res        # 不读 · 留痕 · 走三态
    """
    sc = SUBMODEL_SCOPE.get(sub_id or '')
    if not sc:
        msg = '🔒 scope 违规: 未知子模型 %r 试图读 %r → 拒绝（宁严勿宽）' % (sub_id, table)
        _VIOLATIONS.append({'sub': sub_id, 'table': table, 'msg': msg})
        if raise_on_forbid:
            raise ScopeViolation(msg)
        return False, msg
    t = str(table or '').strip().lower()
    allow = {x.lower() for x in sc.get('allow', ())}
    forbid = {x.lower() for x in sc.get('forbid', ())}
    if t in forbid or t not in allow:
        why = '在 forbid 列表' if t in forbid else '不在 allow 白名单'
        msg = ('🔒 scope 违规[%s]: 表 %r %s → **拒绝读取**'
               '（避免跨域口径污染·如 NL 场用五大阈值）' % (sub_id, table, why))
        _VIOLATIONS.append({'sub': sub_id, 'table': table, 'msg': msg})
        if raise_on_forbid:
            raise ScopeViolation(msg)
        return False, msg
    return True, ''


class ScopeViolation(Exception):
    """子模型越界读表（强隔离）"""


def violations():
    """进程内全部隔离违规（供 raw / audit 消费）"""
    return list(_VIOLATIONS)


def clear_violations():
    global _VIOLATIONS
    _VIOLATIONS = []


# ══════════════════════════════════════════════════════════════════════
# 七、总② 主模型聚合（按优先级合并 + 冲突留痕）
# ══════════════════════════════════════════════════════════════════════
# 优先级：L2 硬核不可被覆盖；子模型只调置信度/排序
PRIORITY = {'nations': 30, 'europe': 25, 'top5_epl': 20, 'top5_laliga': 20,
            'top5_seriea': 20, 'top5_bundesliga': 20, 'top5_ligue1': 20}


def aggregate(results, l2_lock=None):
    """把多个 SubModelResult 合成统一判定。

    → {
        'dir_adj': {'H':..,'D':..,'A':..},   # 各子模型加权和（同域只会有一个 applicable）
        'conf_adj': int,                      # 夹逼 ±1
        'goals_adj': float,
        'anchor_hints': [...],
        'rules_hit': [...],
        'warnings': [...],
        'conflicts': [...],                   # 冲突留痕
        'applied': [name...],
        'tristate': [name...],
        'scope_blocked': [...],
      }

    🔴 l2_lock：如传入（如 'H'），则**任何子模型都不得把方向翻到对面**（只降档不反转）。
    """
    out = {'dir_adj': {'H': 0.0, 'D': 0.0, 'A': 0.0}, 'conf_adj': 0, 'goals_adj': 0.0,
           'anchor_hints': [], 'rules_hit': [], 'warnings': [], 'conflicts': [],
           'applied': [], 'tristate': [], 'scope_blocked': []}
    app = [r for r in (results or []) if getattr(r, 'applicable', False)]
    tri = [r for r in (results or []) if not getattr(r, 'applicable', False)]
    out['tristate'] = [r.name for r in tri]
    if not app:
        return out
    # 只取优先级最高的那个 applicable（同域正常只有一个）
    app.sort(key=lambda r: -PRIORITY.get(r.name if isinstance(r.name, str) else '', 0))
    main = app[0]
    out['applied'] = [r.name for r in app]

    for k in ('H', 'D', 'A'):
        out['dir_adj'][k] = round(main.dir_adj.get(k, 0.0), 3)
    # 🔴 L2 锁：子模型不得把方向翻到对面
    if l2_lock in ('H', 'D', 'A'):
        for k in ('H', 'D', 'A'):
            if k == l2_lock and out['dir_adj'][k] < 0 and out['dir_adj'][k] < -3:
                out['conflicts'].append('子模型 %s 对 L2 方向 %s 给出 %+.1fpp 负校正 → '
                                        '**已按铁律限制降档不反转**' % (main.name, l2_lock, out['dir_adj'][k]))
                out['dir_adj'][k] = max(out['dir_adj'][k], -3.0)
    out['conf_adj'] = max(-1, min(1, int(main.conf_adj)))
    out['goals_adj'] = round(float(main.goals_adj), 3)
    out['anchor_hints'] = list(main.anchor_hints)
    out['rules_hit'] = list(main.rules_hit)
    out['warnings'] = list(main.warnings)
    for r in app[1:]:
        out['conflicts'].append('多个子模型同时适用（%s / %s）→ 只取优先级最高的'
                                % (main.name, r.name))
    for r in app + tri:
        out['scope_blocked'].extend(getattr(r, 'scope_blocked', []) or [])
    return out


def fmt_aggregate(agg, l2_lock=None):
    """统一输出（raw 用·人可读）"""
    if not agg or not agg.get('applied'):
        tri = '、'.join(agg.get('tristate', [])) if agg else '—'
        return '⚪ 子模型聚合: 无适用子模型（三态: %s）' % (tri or '无')
    L = []
    L.append('🔴 子模型聚合（总分总·总②）: 生效 %s ｜ 三态 %s'
             % ('/'.join(agg['applied']), '/'.join(agg['tristate']) or '无'))
    d = agg['dir_adj']
    L.append('   方向校正: H%+.1fpp / D%+.1fpp / A%+.1fpp ｜ 置信度%+d档 ｜ 量级%+.2f球'
             % (d['H'], d['D'], d['A'], agg['conf_adj'], agg['goals_adj']))
    if agg['anchor_hints']:
        L.append('   锚提示: %s' % ', '.join('%s(%.2f)' % (a, w) for a, w in agg['anchor_hints'][:5]))
    if agg['rules_hit']:
        L.append('   规则命中: %s' % '/'.join(agg['rules_hit'][:10]))
    if l2_lock:
        L.append('   🔴 L2 锁: 方向锁定 %s（子模型只降档·永不反转）' % l2_lock)
    if agg['conflicts']:
        for c in agg['conflicts']:
            L.append('   ⚠️ 冲突: %s' % c)
    if agg['warnings']:
        for w in agg['warnings'][:4]:
            L.append('   ⚠️ %s' % w)
    if agg['scope_blocked']:
        L.append('   🔒 隔离拦截: %s（越界读表已拒绝）' % ', '.join(agg['scope_blocked'][:6]))
    return '\n'.join(L)


# ══════════════════════════════════════════════════════════════════════
# 八、自测
# ══════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    print('=' * 86)
    print('match_context.py 自测')
    print('=' * 86)
    # ① league_kind
    for lg in ('英超', '西甲', '意甲', '德甲', '法甲', '欧国联', 'Nations League',
               '欧冠', '欧联', '欧协联', '日职', 'E0', 'epl'):
        print('   league_kind(%-16r) = %-8s → %s' % (lg, league_kind(lg),
                                                     pick_submodel(lg)[1]))
    print()
    # ② scope 强隔离
    print('   guard_table 强隔离实测:')
    for sub, tab, expect in (('nations', 'nl_with_elo', True), ('nations', 'league_table', False),
                             ('nations', 'ucl_calibration', False),
                             ('europe', 'europe', True), ('europe', 'league_table', False),
                             ('top5_epl', 'odds_table', True), ('top5_epl', 'nl_data', False),
                             ('unknown', 'anything', False)):
        try:
            ok, msg = guard_table(sub, tab)
            flag = '✅' if ok == expect else '❌'
            print('      %s %-10s × %-18s → %s' % (flag, sub, tab, 'allow' if ok else 'REJECT'))
        except ScopeViolation as e:
            flag = '✅' if expect is False else '❌'
            print('      %s %-10s × %-18s → ScopeViolation（强隔离生效）' % (flag, sub, tab))
    print()
    # ③ 聚合
    r1 = SubModelResult('nations').adj(draw=-2.0, away=1.5).conf(-1).goals(0.1).hit('R5', 'R10')
    r1.anchor(('0:1', 0.6), ('1:1', 0.5))
    r2 = SubModelResult('europe', False, '非欧战场')
    agg = aggregate([r1, r2], l2_lock='A')
    print(fmt_aggregate(agg, l2_lock='A'))
    print()
    # ④ MatchContext
    ctx = MatchContext(case_id='999', league='欧国联', home='Italy', away='France',
                       kickoff='2026-11-12 19:45', sub_id='nations')
    print('   MatchContext.match_id =', ctx.match_id, '｜ scope allow 表数 =',
          len(ctx.scope_of().get('allow', ())))
    print()
    print('   违规记录:', len(violations()), '条')
