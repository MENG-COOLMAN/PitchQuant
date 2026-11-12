# -*- coding: utf-8 -*-
"""time_guard —— 模型时间模块（V3.5.86 · 2026-11-01 · 用户指令「模型的时间会漂移」）

设计原则（调研结论·georgedouzas/sports-betting 踩过同样的坑）:
  ① **绝对时刻一律 UTC 存储**，只在展示层转北京 —— 禁止裸 datetime 混用
  ② **单一时间入口** —— 全仓 `now_bj()/now_utc()`，禁再散落 `datetime.now()`
  ③ **数据新鲜度统一分级** —— 快照/盘口/ELO/赛季表各有阈值，每次分析开头打印体检表
  ④ **业务语义封装** —— 比赛状态、跨日窗口、时序跨度
  ⑤ 零第三方依赖（标准库 `zoneinfo`）—— 我们只涉及 UTC+8 与 UTC，中国无夏令时

为什么不用 whenever/pendulum：DST-safe 能力对本场景用不上（无夏令时），
却要多一层依赖；调研结论「没有单一主导的 Python freshness 库」→ 自建更合适。

用法:
  from time_guard import now_bj, freshness, match_state, parse_window, context
  python data/tmp/time_guard.py              # 打印当前时间上下文
  python data/tmp/time_guard.py --sweep      # 数据新鲜度体检表
  python data/tmp/time_guard.py --kickoff "2026-11-01 04:00"   # 含比赛状态
  python data/tmp/time_guard.py --verify     # 联网校验系统时钟偏差
"""
import io
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    BJ = ZoneInfo('Asia/Shanghai')          # 🔴用 IANA 时区，不硬编码 +8
except Exception:                            # pragma: no cover
    BJ = timezone(timedelta(hours=8))

UTC = timezone.utc
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


# ══════════════ L1 时间源（唯一入口）══════════════
def now_bj():
    """当前北京时间（aware datetime）"""
    return datetime.now(BJ)


def now_utc():
    """当前 UTC（aware datetime）"""
    return datetime.now(UTC)


def today_bj():
    """今天（北京日期）"""
    return now_bj().date()


def fmt_bj(t=None, with_tz=False):
    """格式化北京时间 → 'YYYY-MM-DD HH:MM[:SS]'"""
    t = t or now_bj()
    if isinstance(t, str):
        return t
    if t.tzinfo is None:
        t = t.replace(tzinfo=BJ)
    s = t.astimezone(BJ).strftime('%Y-%m-%d %H:%M:%S')
    return s + ' (北京)' if with_tz else s


def to_bj(t):
    """任意 aware/naive → 北京 aware"""
    if isinstance(t, str):
        t = parse_dt(t)
    if t is None:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=BJ)
    return t.astimezone(BJ)


def to_utc(t):
    if isinstance(t, str):
        t = parse_dt(t)
    if t is None:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=BJ)      # 🔴约定：naive 一律视为北京
    return t.astimezone(UTC)


def parse_dt(s):
    """尽力解析多种时间串 → aware datetime（naive 视为北京）"""
    if not s:
        return None
    s = str(s).strip().replace('Z', '+00:00')
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M', '%Y-%m-%d', '%m-%d %H:%M'):
        try:
            t = datetime.strptime(s[:len(datetime.now().strftime(fmt))], fmt)
            if fmt == '%m-%d %H:%M':
                t = t.replace(year=now_bj().year)
            return t.replace(tzinfo=BJ) if t.tzinfo is None else t
        except Exception:
            continue
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


# ══════════════ L2 数据新鲜度 ══════════════
# (fresh_h, ok_h, stale_h) —— 超过 stale_h 即 expired
KINDS = {
    'snapshot': (2, 6, 24),        # 赔率快照（临场 2h 内最佳）
    'odds':     (6, 12, 48),       # 盘口文件
    'elo':      (72, 168, 336),    # ELO 缓存（3d/7d/14d）
    'table':    (24 * 30, 24 * 90, 24 * 180),   # 赛季表/基准（30d/90d/180d）
    'cache':    (6, 24, 168),      # 通用缓存
    'case':     (24 * 365, 24 * 730, 24 * 1095),  # 案例库
}

KEY_FILES = [
    ('data/tmp/snapshots', 'snapshot', 'dir'),
    ('data/tmp/prestep_window.json', 'snapshot', 'file'),
    ('data/tmp/clubelo_*.json', 'elo', 'glob'),   # 实际按日期命名 clubelo_YYYYMMDD.json
    ('data/tmp/homeaway_table.json', 'table', 'file'),
    ('data/tmp/odds_table.json', 'table', 'file'),
    ('data/tmp/score_depth_table.json', 'table', 'file'),
    ('data/tmp/goal_bins_table.json', 'table', 'file'),
    ('data/tmp/team_attack_defense.json', 'table', 'file'),
    ('data/case-library/实战案例.csv', 'case', 'file'),
]


def freshness(target, kind='cache', ref=None):
    """数据年龄 + 分级
    返回 {path, mtime_bj, age_h, level(fresh/ok/stale/expired/missing), note}
    """
    ref = ref or now_bj()
    p = target if os.path.isabs(target) else os.path.join(ROOT, target)
    if '*' in target:                      # 🔴glob 前缀（如 clubelo_*.json）·须在 exists 之前判定
        import glob as _g
        fs = _g.glob(p)
        if not fs:
            return {'path': target, 'mtime_bj': None, 'age_h': None,
                    'level': 'missing', 'note': 'glob 无匹配文件'}
        mt = max(os.path.getmtime(f) for f in fs)
        t = datetime.fromtimestamp(mt, BJ)
        age_h = (ref - t).total_seconds() / 3600.0
        f_h, o_h, s_h = KINDS.get(kind, KINDS['cache'])
        lv = ('fresh' if age_h <= f_h else 'ok' if age_h <= o_h
              else 'stale' if age_h <= s_h else 'expired')
        return {'path': target, 'mtime_bj': fmt_bj(t), 'age_h': round(age_h, 1),
                'level': lv, 'note': ''}
    if not os.path.exists(p):
        return {'path': target, 'mtime_bj': None, 'age_h': None,
                'level': 'missing', 'note': '文件/目录不存在'}
    if os.path.isdir(p):
        fs = [os.path.join(p, f) for f in os.listdir(p) if f.endswith('.json')]
        if not fs:
            return {'path': target, 'mtime_bj': None, 'age_h': None,
                    'level': 'missing', 'note': '目录内无 json'}
        mt = max(os.path.getmtime(f) for f in fs)
    else:
        mt = os.path.getmtime(p)
    t = datetime.fromtimestamp(mt, BJ)
    age_h = (ref - t).total_seconds() / 3600.0
    f_h, o_h, s_h = KINDS.get(kind, KINDS['cache'])
    if age_h <= f_h:
        lv = 'fresh'
    elif age_h <= o_h:
        lv = 'ok'
    elif age_h <= s_h:
        lv = 'stale'
    else:
        lv = 'expired'
    return {'path': target, 'mtime_bj': fmt_bj(t), 'age_h': round(age_h, 1),
            'level': lv, 'note': ''}


ICON = {'fresh': '🟢', 'ok': '🟡', 'stale': '🟠', 'expired': '🔴', 'missing': '⚪'}


def sweep(verbose=True):
    """数据新鲜度体检表"""
    rows = []
    for target, kind, _ in KEY_FILES:
        r = freshness(target, kind)
        r['kind'] = kind
        rows.append(r)
    if verbose:
        print('🔴 数据新鲜度体检（阈值: snapshot 2/6/24h · elo 3/7/14d · table 30/90/180d）')
        for r in rows:
            name = os.path.basename(r['path'].rstrip('/')) or r['path']
            age = ('%.1fh' % r['age_h']) if r['age_h'] is not None else '—'
            print('  %s %-28s %-9s 年龄 %-8s %s' %
                  (ICON.get(r['level'], '⚪'), name[:28], r['level'], age, r['note']))
        bad = [r for r in rows if r['level'] in ('stale', 'expired')]
        if bad:
            print('  ⚠️ %d 项过期/陈旧 → 判定前须刷新或三态标注' % len(bad))
        else:
            print('  ✅ 无过期项')
    return rows


# ══════════════ L3 业务语义 ══════════════
def match_state(kickoff, duration_min=120):
    """比赛状态（按开赛时间 + 常规时长 120min 粗判）
    返回 {state, minutes, note}  state ∈ 未开赛/进行中/已结束/未知
    """
    k = parse_dt(kickoff)
    if not k:
        return {'state': '未知', 'minutes': None, 'note': '开赛时间不可解析'}
    delta = (now_bj() - k).total_seconds() / 60.0
    if delta < -1:
        return {'state': '未开赛', 'minutes': round(-delta), 'note': '距开赛 %.0f 分钟' % (-delta)}
    if delta <= duration_min:
        return {'state': '进行中', 'minutes': round(delta), 'note': '已开赛 %.0f 分钟' % delta}
    return {'state': '已结束', 'minutes': round(delta), 'note': '已开赛 %.0f 分钟（常规时长已过）' % delta}


_WIN = re.compile(r'(\d{1,2})[:：](\d{2})\s*[-~到至]\s*(\d{1,2})[:：](\d{2})')
# 🔴中文口语窗口（2026-11-01 补）: 今晚23点到凌晨4点 / 20点到4点 / 晚上8点到凌晨4点
_CN_WIN = re.compile(r'(?:今晚|今天晚上|夜里|晚上)?\s*(\d{1,2})\s*[点时]?\s*(?:半)?'
                     r'\s*(?:到|至|~|-)\s*(?:凌晨|次日|明天|明早)?\s*(\d{1,2})\s*[点时]?')


def parse_window(spec, base_date=None):
    """解析窗口 'HH:MM-HH:MM'（支持 20:00-04:00 跨日 / 「今晚20点到4点」）
    返回 {start_bj, end_bj, start_utc, end_utc, cross_day, note}
    """
    raw = str(spec or '')
    m = _WIN.search(raw)
    if m:
        h1, m1, h2, m2 = (int(x) for x in m.groups())
    else:
        # 🔴中文口语窗口（2026-11-01 补）: 「今晚23点到凌晨4点」/「20点到4点」/「晚上8点到凌晨4点」
        mc = _CN_WIN.search(raw)
        if not mc:
            return {'ok': False, 'note': '窗口格式不可解析: %r' % spec}
        h1, h2 = int(mc.group(1)), int(mc.group(2))
        m1 = m2 = 0
    base = base_date or now_bj().date()
    if isinstance(base, str):
        base = parse_dt(base).date()
    s = datetime.combine(base, datetime.min.time()).replace(hour=h1, minute=m1, tzinfo=BJ)
    e = datetime.combine(base, datetime.min.time()).replace(hour=h2, minute=m2, tzinfo=BJ)
    cross = e <= s
    if cross:
        e += timedelta(days=1)
    return {'ok': True, 'start_bj': fmt_bj(s), 'end_bj': fmt_bj(e),
            'start_utc': to_utc(s).strftime('%Y-%m-%dT%H:%M'),
            'end_utc': to_utc(e).strftime('%Y-%m-%dT%H:%M'),
            'cross_day': cross,
            'note': '跨日窗口（次日 %02d:%02d 结束）' % (h2, m2) if cross else '同日窗口'}


def time_span(points):
    """时序跨度（输入时间串列表或 'a → b'）"""
    ts = [parse_dt(x) for x in (points or []) if parse_dt(x)]
    if len(ts) < 2:
        return {'n': len(ts), 'span_h': None, 'note': '时点不足 2 个'}
    ts.sort()
    span = (ts[-1] - ts[0]).total_seconds() / 3600.0
    return {'n': len(ts), 'span_h': round(span, 2),
            'first': fmt_bj(ts[0]), 'last': fmt_bj(ts[-1]),
            'note': '%d 时点 · 跨度 %.2f 小时' % (len(ts), span)}


# ══════════════ 汇总 ══════════════
def context(kickoff=None, sweep_data=False):
    """一次拿全时间上下文（pipeline Stage0 用）"""
    bj, utc = now_bj(), now_utc()
    ctx = {'now_bj': fmt_bj(bj), 'now_utc': utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
           'tz': str(BJ), 'weekday': ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][bj.weekday()]}
    if kickoff:
        st = match_state(kickoff)
        ctx['kickoff_bj'] = fmt_bj(parse_dt(kickoff)) if parse_dt(kickoff) else str(kickoff)
        ctx.update({'match_state': st['state'], 'match_note': st['note']})
    if sweep_data:
        ctx['data'] = sweep(verbose=False)
    return ctx


def print_context(kickoff=None, sweep_data=True):
    ctx = context(kickoff, sweep_data)
    print('=' * 88)
    print('🕐 时间上下文（time_guard）')
    print('=' * 88)
    print('  当前时间: %s %s  |  UTC: %s  |  时区: %s'
          % (ctx['now_bj'], ctx['weekday'], ctx['now_utc'], ctx['tz']))
    if kickoff:
        print('  比赛状态: %s（%s）' % (ctx.get('match_state'), ctx.get('match_note')))
        print('  开球时间: %s' % ctx.get('kickoff_bj'))
    if sweep_data:
        print()
        sweep(verbose=True)
    print('=' * 88)


def verify_clock(timeout=6):
    """联网校验系统时钟（对比 HTTP Date header）· 偏差 >5min 告警"""
    import urllib.request
    for url in ('https://www.baidu.com', 'https://api.odds-api.io/v3/events?sport=football'):
        try:
            op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with op.open(req, timeout=timeout) as r:
                hdr = r.headers.get('Date')
            if not hdr:
                continue
            net = datetime.strptime(hdr, '%a, %d %b %Y %H:%M:%S %Z').replace(tzinfo=UTC)
            skew = (now_utc() - net).total_seconds()
            return {'ok': abs(skew) <= 300, 'skew_sec': round(skew, 1),
                    'note': '系统时钟偏差 %.1f 秒（%s）' % (skew, '正常' if abs(skew) <= 300 else '⚠️超过5分钟')}
        except Exception:
            continue
    return {'ok': None, 'skew_sec': None, 'note': '联网校验失败（网络不可用·跳过）'}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:]
    if '--sweep' in args:
        sweep(verbose=True)
        return
    if '--verify' in args:
        r = verify_clock()
        print('🕐 时钟校验: %s' % r['note'])
        return
    kick = None
    for i, a in enumerate(args):
        if a == '--kickoff' and i + 1 < len(args):
            kick = args[i + 1]
    if '--window' in args:
        i = args.index('--window')
        spec = args[i + 1] if i + 1 < len(args) else ''
        w = parse_window(spec)
        print('窗口解析 %r →' % spec)
        for k, v in w.items():
            print('  %-10s %s' % (k, v))
        return
    print_context(kick, sweep_data=True)


if __name__ == '__main__':
    main()
