# -*- coding: utf-8 -*-
"""Playwright 完整管线测试：cup/46 赛程 → 逐场 bsls 历史（5场验证）"""
import io, sys, asyncio, re, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0')
        page = await ctx.new_page()

        # 1. 欧冠赛程
        await page.goto('http://saishi.zgzcw.com/soccer/cup/46', timeout=30000, wait_until='domcontentloaded')
        await page.wait_for_timeout(6000)
        rows = await page.eval_on_selector_all('tr', '''els => els.map(e => {
            const tds=[...e.querySelectorAll('td')].map(t=>t.textContent.replace(/\\s+/g,' ').trim());
            const links=[...e.querySelectorAll('a')].map(a=>a.href);
            const fenxi=links.find(h=>h&&h.includes('fenxi.zgzcw.com'));
            return {tds, fenxi};
        })''')
        matches = []
        for r in rows:
            if r['fenxi'] and len(r['tds']) >= 5 and ':' in r['tds'][3]:
                mid = re.search(r'/(\d+)/', r['fenxi']).group(1)
                matches.append({'mid': mid, 'time': r['tds'][0], 'home': r['tds'][1],
                                'score': r['tds'][3], 'away': r['tds'][4] if len(r['tds'])>4 else '',
                                'handi': r['tds'][6] if len(r['tds'])>6 else ''})
        print(f"欧冠赛程: {len(matches)} 场")
        for m in matches[:8]: print("  ", m)
        json.dump(matches, open('data/tmp/cl46_matches.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

        # 2. 前5场抓 bsls 历史
        results = {}
        for m in matches[:5]:
            try:
                await page.goto(f'http://fenxi.zgzcw.com/{m["mid"]}/bsls', timeout=25000, wait_until='domcontentloaded')
                await page.wait_for_timeout(4000)
                body = await page.inner_text('body')
                if 'Please Enable' in body:
                    results[m['mid']] = 'WAF BLOCK'
                    continue
                # 历史表行
                rows2 = await page.eval_on_selector_all('table tr', 'els => els.map(e => e.textContent.replace(/\\s+/g," ").trim())')
                hist = [r2 for r2 in rows2 if len(r2) > 30 and ':' in r2]
                results[m['mid']] = f'{len(hist)} 行'
                print(f"  {m['mid']} {m['home']}vs{m['away']}: {len(hist)} 行历史")
            except Exception as e:
                results[m['mid']] = f'ERR {e}'
            time.sleep(2)
        print("\n=== 5场测试结果 ===")
        for k, v in results.items(): print(f"  {k}: {v}")
        await browser.close()

asyncio.run(main())
