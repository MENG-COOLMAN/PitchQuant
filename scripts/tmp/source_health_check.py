"""数据源健康监控（2026-08-29评审固化·P1-6·每场分析前运行·5源检测+降级建议）
用法: python source_health_check.py [--proxy 127.0.0.1:7897]
输出: 数据源健康表(可用/降级/不可用+响应时间) + 降级链建议

🔴2026-10-06 变更（用户决策「api-football 已停用·用现有数据源替代·从数据链完全剔除」）:
   - 移除「源B3 api-football」探测项与 AF_KEY（6 源 → 5 源活跃源）
   - 替代映射: 赔率→the-odds-api(源B7·21-32家) / 伤停→Bing News(唯一源) /
              赛事定位→Odds-API events(eventId) / H2H→fixture_cache+Matches.csv /
              官方概率·Form5·lineups → ⚪ 无替代(三态标注)
"""
import argparse, io, os, sys, time, urllib.request, json, socket
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

ODDS_KEY = '<REDACTED_HEX>'
try:
    _TOK = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api_keys.json'), encoding='utf-8')).get('the_odds_api', '')
except Exception:
    _TOK = ''


def probe(name, url, timeout=12, proxy=None, headers=None):
    """🔴2026-10-31 修订: 代理优先 + 直连回退（双通道·直连 SSL 超时26.3s/代理1.2s）
    原实现按 use_proxy 单通道探测 → Odds-API/Bing News 被强制走代理而误报"不可用"
    （实测: Odds-API 直连可用·Bing RSS 代理可用）→ 现双通道任一成功即算可用"""
    # 🔴2026-09-23 修复: 原用无参 urllib.request.urlopen() → 继承 Windows 系统代理(7897)
    #   → 名为"直连"实走代理 → 代理失效时双通道全灭、误报"源不可用"。
    #   必须用显式 opener（ProxyHandler({}) = 真直连）
    last = None
    for px, _to in ((proxy, timeout), (None, 4)):   # 🔴2026-10-31 代理优先 → 直连回退4s
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers=headers or {'User-Agent': 'Mozilla/5.0'})
            op = (urllib.request.build_opener(urllib.request.ProxyHandler({})) if not px
                  else urllib.request.build_opener(urllib.request.ProxyHandler({'http': 'http://' + str(px).replace('http://', ''), 'https': 'http://' + str(px).replace('http://', '')})))
            with op.open(req, timeout=_to) as r:
                data = r.read()[:200]
                ms = (time.time()-t0)*1000
                ok = getattr(r, 'status', 200) == 200 and len(data) > 0
                return ('✅可用' if ok else '⚠️降级'), ms, 'via %s' % ('proxy' if px else 'direct')
        except Exception as e:
            last = ((time.time()-t0)*1000, str(e)[:60])
    return '❌不可用', last[0], last[1]


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--proxy', default='127.0.0.1:7897')
    a = ap.parse_args()
    print('🔴数据源健康检查(P1-6·2026-08-29评审固化·2026-10-06 剔除 api-football):')
    print(f'  代理: {a.proxy} | 时间: {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
    checks = [
        ('源B1 Odds-API', f'https://api.odds-api.io/v3/events?apiKey={ODDS_KEY}&sport=football&league=england-premier-league&status=pending', True),
        ('源B7 the-odds-api', 'https://api.the-odds-api.com/v4/sports/?apiKey=' + _TOK, False),
        ('源B2 zgzcw', 'https://live.zgzcw.com/', True),
        ('源B5 footballcharts', 'https://footballcharts.com/', False),  # ⛔2026-09-15: 域名已永久失效·见下方 DEPRECATED
        ('源B6 clubelo', 'http://clubelo.com/', False),
        ('新闻伤停 Bing News', 'https://www.bing.com/news/search?q=football&format=RSS', True),
    ]
    # ⛔已知永久废弃源（域名失效·降级链已覆盖·不计入可用源分母·避免常态化 ❌ 噪音）
    DEPRECATED = {'源B5 footballcharts'}
    results = []
    for item in checks:
        name, url, use_proxy = item[0], item[1], item[2]
        headers = item[3] if len(item) > 3 else None
        if name in DEPRECATED:
            results.append((name, '⛔已废弃', 0.0))
            print(f'  {name}: ⛔已废弃(域名失效·降级链覆盖·非本机问题)')
            continue
        st, ms, err = probe(name, url, proxy=a.proxy if use_proxy else None, headers=headers)
        results.append((name, st, ms))
        print(f'  {name}: {st} ({ms:.0f}ms){("·" + err) if err else ""}')
    active = [(n, s) for n, s, _ in results if n not in DEPRECATED]
    avail = sum(1 for _, s in active if s.startswith('✅'))
    print(f'\n  可用源: {avail}/{len(active)} 活跃源 (另有 {len(DEPRECATED)} 个已废弃源已剔除)')
    print('  降级链(2026-10-06 更新·已剔除 api-football): Odds-API不可用→zgzcw(源B2)补·'
          '赔率广度→the-odds-api(源B7·21-32家)·伤停→Bing News(唯一源)·'
          'H2H→fixture_cache+Matches.csv·footballcharts已废弃→understat_xg+SK-xg-depth补·'
          '官方概率/Form5/lineups→⚪无替代(三态标注)')
    if avail <= 2:
        print('  ⚠️ 警告: 连续多源不可用·建议检查网络/VPN/API key')
