"""数据源健康监控（2026-08-29评审固化·P1-6·每场分析前运行·6源检测+降级建议）
用法: python source_health_check.py [--proxy 127.0.0.1:7897]
输出: 数据源健康表(可用/降级/不可用+响应时间) + 降级链建议
"""
import argparse, io, sys, time, urllib.request, json, socket
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

ODDS_KEY = os.environ.get('ODDS_API_KEY', '')
AF_KEY = os.environ.get('API_FOOTBALL_KEY', '')

def probe(name, url, timeout=12, proxy=None, headers=None):
    """🔴2026-09-13 修正: 直连优先 + 代理回退（双通道）
    原实现按 use_proxy 单通道探测 → Odds-API/Bing News 被强制走代理而误报"不可用"
    （实测: Odds-API 直连可用·Bing RSS 代理可用）→ 现双通道任一成功即算可用"""
    last = None
    for px in (None, proxy):
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers=headers or {'User-Agent': 'Mozilla/5.0'})
            if px:
                req.set_proxy(px, 'http')
            with urllib.request.urlopen(req, timeout=timeout) as r:
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
    print('🔴数据源健康检查(P1-6·2026-08-29评审固化):')
    print(f'  代理: {a.proxy} | 时间: {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
    checks = [
        ('源B1 Odds-API', f'https://api.odds-api.io/v3/events?apiKey={ODDS_KEY}&sport=football&league=england-premier-league&status=pending', True),
        ('源B3 api-football', 'https://v3.football.api-sports.io/status', False, {'x-apisports-key': AF_KEY}),
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
    print('  降级链: Odds-API不可用→api-football 13家补·api-football不可用→zgzcw·新闻不可用→api-football injuries·footballcharts已废弃→xG/校准用 understat_xg.py + SK-xg-depth 补·VPN断开→api-football/clubelo直连')
    if avail <= 3:
        print('  ⚠️ 警告: 连续多源不可用·建议检查网络/VPN/API key')
