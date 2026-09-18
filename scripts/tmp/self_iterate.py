# -*- coding: utf-8 -*-
"""
self_iterate.py —— 赛后自我迭代学习引擎（V3.5.74·2026-09-10 固化）

目的: 每次得到赛果后，把「复盘」升级为「可累积、可验证、可固化的学习」——
      禁止单场直接改规则（防过拟合），学习必须走：偏差定量 → 归因 → 观察池累积 →
      门槛判定（方向类≥10 同向 / 比分·量级类≥20） → 批量回测验证(p<0.05·时间分割) → 才可固化。

用法:
  # 1) 单场学习录入（复盘后必跑）
  python data/tmp/self_iterate.py learn --case 158 --real 1:1 --pred "客胜+平(并列)" \
      --anchor "1:1|1:2" --center 2.5 --handi -1 --o25 3.09

  # 2) 观察池汇总 + 门槛判定（每批复盘后跑）
  python data/tmp/self_iterate.py status

  # 3) 归因类型汇总（哪些偏差模式在累积）
  python data/tmp/self_iterate.py patterns
"""
import sys, os, csv, io, re

# 🔴GBK 控制台防护(2026-09-15·复盘时实测崩溃: ✅/❌ emoji 无法编码·漏补 reconfigure)
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(BASE, '..', 'case-library', '学习台账.csv')
HEADER = ['日期', '场次', '真实比分', '预测方向', '方向', '主锚|次锚', '锚命中',
          '预测进球中心', '实际总进球', '量级偏差', '净胜偏差档', '归因类型', '归因说明', '状态']

# 归因类型 → 门槛（达到即建议批量回测验证）
THRESHOLD = {
    '超深屠杀锚量级': 20, '均势对攻量级': 20, '净胜穿透': 20, '大球低估': 20,
    '方向误判': 10, '平局漏判': 10, '诱盘方向': 10,
}


def _load():
    if not os.path.exists(LEDGER):
        return []
    with open(LEDGER, encoding='utf-8-sig', newline='') as f:
        r = list(csv.reader(f))
    return r[1:] if r else []


def _save(rows):
    with open(LEDGER, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)


def _attr(real_goals, center, net_real, net_anchors, dir_ok, draw_real):
    """归因规则(经验映射·可扩展): 返回 [(类型,说明)]·多项可并存"""
    tags = []
    if not dir_ok and draw_real:
        tags.append(('平局漏判', '真实平局·预测方向未含平'))
    elif not dir_ok:
        tags.append(('方向误判', '方向与真实相反/未含'))
    # 锚净胜低估(屠杀型锚保守·关键学习信号)
    if net_anchors and net_real > max(net_anchors):
        dev_net = net_real - max(net_anchors)
        t = '超深屠杀锚量级' if (center >= 3.5 or net_real >= 4) else '锚净低估'
        tags.append((t, '真实净%d > 锚净%d·低估%d档' % (net_real, max(net_anchors), dev_net)))
    # 进球量级
    if real_goals - center >= 2:
        tags.append(('大球低估', '实际进球 %d vs 预测中心 %.1f·低估 %.1f 球' % (real_goals, center, real_goals - center)))
    elif center - real_goals >= 2:
        tags.append(('小球高估', '实际进球 %d vs 预测中心 %.1f·高估 %.1f 球' % (real_goals, center, center - real_goals)))
    # 净胜穿透(即使进球量级不显著)
    if net_anchors and net_real - max(net_anchors) >= 2:
        if '锚净低估' not in [t for t, _ in tags] and '超深屠杀锚量级' not in [t for t, _ in tags]:
            tags.append(('净胜穿透', '真实净%d 穿透锚净%d·超2档' % (net_real, max(net_anchors))))
    if not tags:
        tags.append(('命中', '方向+量级+锚净均合理'))
    return tags


def cmd_learn(args):
    g = lambda k, d=None: args[args.index(k) + 1] if k in args else d
    cid = g('--case'); real = g('--real'); pred = g('--pred', '')
    anchor = g('--anchor', ''); center = float(g('--center', 0) or 0)
    handi = float(g('--handi', 0) or 0); o25 = g('--o25', 0)
    try:
        h, a = [int(x) for x in real.split(':')]
    except Exception:
        print('真实比分格式错误'); return
    rg = h + a; net_real = h - a
    anchors = [s for s in anchor.split('|') if s]
    hit = real in anchors
    neth = [int(x.split(':')[0]) - int(x.split(':')[1]) for x in anchors if ':' in x]
    # 方向判定(宽松 any: 预测含真实结果)
    real_dir = '主胜' if h > a else ('客胜' if a > h else '平')
    dir_ok = real_dir in pred or (real_dir == '平' and '平' in pred)
    dev = round(rg - center, 1)
    net_dev = ('真实净%d vs 锚净%s' % (net_real, neth)) if neth else ''
    tags = _attr(rg, center, net_real, neth, dir_ok, real_dir == '平')
    rows = _load()
    # 🔴去重 + 真实日期（2026-09-15 修复）: 原实现无去重且日期硬编码 '2026-09-10' →
    #    重复调用(learn.py 内部调 + 手动调)致台账虚增(实测 46 行→去重后仅 26 场·case179 重复6次)
    #    → 门槛判定被污染(方向误判 count 11 虚高·实际仅 8·未达门槛10)
    import datetime as _dt
    _today = _dt.date.today().isoformat()
    for t, why in tags:
        _new = [_today, cid, real, pred, '✅' if dir_ok else '❌', anchor,
                '✅' if hit else '❌', center, rg, dev, net_dev, t, why, '观察']
        rows = [r for r in rows
                if not (len(r) > 11 and r[1].strip() == str(cid) and r[11].strip() == t)]
        rows.append(_new)
    _save(rows)
    rules = _bump(rows)
    print('=== case%s 学习录入 ===' % cid)
    print('方向: %s (真实 %s) | 锚命中: %s | 量级偏差: %+.1f 球(中心%.1f→实际%d)' % (
        '✅' if dir_ok else '❌', real_dir, '✅' if hit else '❌', dev, center, rg))
    print('归因: %s' % '; '.join('%s(%s)' % t for t in tags))
    if hit and dir_ok:
        print('→ 命中·纳入正样本累积（同类命中率定期复核）')
    else:
        st = cmd_status([])
        print('→ 已入观察池·同类累积见下（未达门槛禁止改规则·学习≠批量更新）')
    upd = [t for t, e in rules.items() if e.get('_auto') and e.get('count', 0) >= 2]
    if upd:
        print('⚡ 学习成果自动更新(提示级·防同一失误复发): %s' % ' | '.join(upd))
        print('   → calc_all 每场将自动输出该提示（不改变任何计算/判定·仅提示）')


def cmd_status(args):
    rows = _load()
    if not rows:
        print('学习台账为空'); return
    from collections import Counter
    cnt = Counter(r[11] for r in rows if len(r) > 11)
    print('=== 学习台账状态（%d 条）===' % len(rows))
    print('%-16s %5s %5s %s' % ('归因类型', '累积', '门槛', '状态'))
    for t, n in cnt.most_common():
        th = THRESHOLD.get(t, 20)
        st = '🔴达标·建议批量回测验证' if n >= th and t != '命中' else '观察中'
        print('%-16s %5d %5d  %s' % (t, n, th, st))
    print('→ 达标类型方可进入批量回测（时间分割·p<0.05）→ 验证通过才固化进规则')
    rules = _load_rules()
    if rules:
        print('=== learned_rules.json（学习成果库）===')
        for t, e in rules.items():
            print('  %-16s count=%-3s status=%s' % (t, e.get('count'), e.get('status')))


def cmd_patterns(args):
    rows = _load()
    from collections import defaultdict
    agg = defaultdict(list)
    for r in rows:
        if len(r) > 12 and r[11] != '命中':
            agg[r[11]].append('%s:%s(偏差%s)' % (r[1], r[2], r[9]))
    print('=== 偏差模式明细 ===')
    for t, items in agg.items():
        print('[%s] n=%d' % (t, len(items)))
        for it in items[-8:]:
            print('   ', it)


def _rules_path():
    return os.path.join(BASE, 'learned_rules.json')


def _load_rules():
    p = _rules_path()
    if os.path.exists(p):
        try:
            import json
            return json.load(open(p, encoding='utf-8'))
        except Exception:
            pass
    return {}


def _save_rules(d):
    import json
    json.dump(d, open(_rules_path(), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


# 自动生成执行提示模板(复发≥2即时升级·防同一失误犯第二遍)
RULE_TEMPLATES = {
    '超深屠杀锚量级': '超深屠杀型(主胜隐含>88%+让≥2): 历史n=2109 净3+43.2%/净4+24.9%/净0-1 29%(时间分割516场一致) → 主锚净3·次锚须含净4-5+出口(4:1/5:0)·并保留净1停止分支(1:0/2:1)',
    '锚净低估': '锚净胜低于真实(复发): 检查该让球层是否系统性偏保守 → 次锚上移一档净胜',
    '大球低估': '实际进球显著高于预测中心(复发): 检查 O25 校准与对攻/伤停极端场次分层 → 量级中心上移',
    '小球高估': '实际进球低于预测中心(复发): 检查小球校准 → 中心下移',
    '平局漏判': '真实平局而方向未含平(复发): 校验修正53并列判定门槛与CS最低定价 → 平局并列前置',
    '方向误判': '方向与真实相反(复发): 归因该场盘口/水位/诱盘信号 → 检查诱阻识别覆盖',
    '净胜穿透': '净胜穿透锚上档(复发): 次锚上移·检查让球层锚表保守度',
}


def _bump(rows):
    """按类型累积+复发检测→自动升级 learned_rules.json"""
    from collections import Counter, defaultdict
    rules = _load_rules()
    cnt = Counter(r[11] for r in rows if len(r) > 11)
    for t, n in cnt.items():
        if t == '命中':
            continue
        e = rules.get(t, {'count': 0, 'status': '观察', 'evidence': []})
        e['count'] = n
        e['last_seen'] = max((r[0] for r in rows if len(r) > 11 and r[11] == t), default='')
        if n >= 2 and e['status'] == '观察':
            e['status'] = '提示'
            e['rule'] = RULE_TEMPLATES.get(t, '%s: 同类偏差复发 %d 次·执行时须显式核对该层' % (t, n))
            e['_auto'] = '复发≥2自动升级(防同一失误重复)'
        if n >= THRESHOLD.get(t, 20) and e['status'] == '提示':
            e['status'] = '待回测验证'
        rules[t] = e
    _save_rules(rules)
    return rules


def cmd_verify(args):
    """回测验证通过 → 固化规则(时间分割+p<0.05 依据由调用者提供)"""
    g = lambda k, d=None: args[args.index(k) + 1] if k in args else d
    t = g('--type'); ev = g('--evidence', '')
    n = g('--n', ''); p = g('--p', '')
    rules = _load_rules()
    e = rules.get(t, {'count': 0, 'status': '观察', 'evidence': []})
    e['evidence'] = (e.get('evidence') or []) + ['%s | n=%s p=%s' % (ev, n, p)]
    e['status'] = '已固化'
    e['verified'] = '回测验证(时间分割)'
    rules[t] = e
    _save_rules(rules)
    print('✅ 已固化规则: %s | 依据: %s (n=%s p=%s)' % (t, ev, n, p))
    print('→ calc_all 每场将自动输出该提示；规则文本: %s' % e.get('rule', '')[:80])


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == 'learn': cmd_learn(sys.argv[2:])
    elif cmd == 'status': 
        try: cmd_status(sys.argv[2:])
        except SystemExit: pass
    elif cmd == 'patterns': cmd_patterns(sys.argv[2:])
    elif cmd == 'verify': cmd_verify(sys.argv[2:])
    else: print(__doc__)


if __name__ == '__main__':
    main()
