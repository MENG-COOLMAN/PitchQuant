# -*- coding: utf-8 -*-
"""PreStep1（英锦赛 EFL Trophy）: 窗口赛事 + 1xbet 赔率（ML/亚盘/O25/主水）"""
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from prestep_fetch import KEY, get, parse_odds, window_from_bj  # noqa: E402

SLUGS = (['england-efl-trophy']
         + ['england-efl-trophy-northern-group-%s' % c for c in 'abcdefgh']
         + ['england-efl-trophy-southern-group-%s' % c for c in 'abcdefgh'])


def main():
    bj = sys.argv[1] if len(sys.argv) > 1 else '22:00-06:00'
    u0, u1, label = window_from_bj(bj)
    print('窗口: 北京 %s（UTC %s → %s）' % (label, u0, u1))
    seen = {}
    for sl in SLUGS:
        try:
            evs = get('https://api.odds-api.io/v3/events?apiKey=%s&sport=football&league=%s&status=pending' % (KEY, sl))
        except Exception as e:
            print('  ⚠️ %s 拉取失败: %s' % (sl, str(e)[:60]))
            continue
        for e in (evs or []):
            d = (e.get('date') or '')
            if u0 <= d[:16] <= u1:
                seen[e.get('id')] = {'slug': sl, 'id': e.get('id'), 'home': e.get('home'),
                                     'away': e.get('away'), 'date': d}
    print('窗口内英锦赛赛事: %d 场\n' % len(seen))

    rows = []
    for r in seen.values():
        try:
            oh, od, oa, handi, o25, hw = parse_odds(r['id'])
            r.update({'oh': oh, 'od': od, 'oa': oa, 'handi': handi, 'o25': o25, 'home_water': hw})
        except Exception as e:
            r['err'] = str(e)[:60]
        rows.append(r)

    print('%-12s %-34s %-7s %-7s %-7s %-8s %-7s %-7s' % ('北京', '赛事', '主', '平', '客', '让球', 'O25', '主水'))
    for r in sorted(rows, key=lambda x: x.get('date') or ''):
        try:
            t = dt.datetime.strptime((r.get('date') or '')[:16], '%Y-%m-%dT%H:%M') + dt.timedelta(hours=8)
            bjt = t.strftime('%m-%d %H:%M')
        except Exception:
            bjt = '?'
        print('%-12s %-34s %-7s %-7s %-7s %-8s %-7s %-7s' % (
            bjt, ('%s vs %s' % (r.get('home'), r.get('away')))[:32],
            r.get('oh') or '-', r.get('od') or '-', r.get('oa') or '-',
            r.get('handi') if r.get('handi') is not None else '-',
            r.get('o25') or '-', r.get('home_water') or '-'))
        if r.get('err'):
            print('    ⚠️ 赔率异常: %s' % r['err'])

    p = os.path.join(HERE, 'prestep_efl.json')
    json.dump(rows, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n已保存: data/tmp/prestep_efl.json（%d 场）' % len(rows))


if __name__ == '__main__':
    main()
