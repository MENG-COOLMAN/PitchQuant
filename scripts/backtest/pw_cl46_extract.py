# -*- coding: utf-8 -*-
"""Playwright 抓欧冠：提取比赛列表+matchId+赛季切换"""
import io, sys, asyncio, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0')
        page = await ctx.new_page()
        await page.goto('http://saishi.zgzcw.com/soccer/cup/46', timeout=30000, wait_until='domcontentloaded')
        await page.wait_for_timeout(8000)

        # 1. 赛季选择选项
        seasons = await page.eval_on_selector_all('select option, .season a, [class*="season"] a', 'els => els.map(e => e.textContent.trim() + "|" + (e.value||e.href||""))')
        print("=== 赛季选项 ===")
        for s in seasons[:20]: print("  ", s[:80])

        # 2. 比赛行（含链接）
        print("\n=== 比赛行 ===")
        rows = await page.eval_on_selector_all('tr', 'els => els.map(e => { const a=[...e.querySelectorAll("a")].map(x=>x.href+"|"+x.textContent.trim()); const t=e.textContent.replace(/\\s+/g," ").trim(); return t+" :: "+a.join(" ; "); })')
        for r in rows[:25]:
            if 'fenxi' in r or ':' in r:
                print("  ", r[:150])

        # 3. 提取 fenxi matchId
        links = await page.eval_on_selector_all('a', 'els => els.map(e => e.href).filter(h => h && h.includes("fenxi.zgzcw.com"))')
        mids = sorted(set(re.search(r'/(\d+)/', h).group(1) for h in links if re.search(r'/(\d+)/', h)))
        print(f"\n=== fenxi matchId: {len(mids)} 个 ===")
        print(mids[:30])
        await browser.close()

asyncio.run(main())
