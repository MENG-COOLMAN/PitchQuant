# -*- coding: utf-8 -*-
"""Playwright 验证：访问欧冠 cup/46 过 WAF"""
import io, sys, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1366, 'height': 900},
        )
        page = await ctx.new_page()
        try:
            await page.goto('http://saishi.zgzcw.com/soccer/cup/46', timeout=30000, wait_until='domcontentloaded')
            # 等待 JS 执行 + WAF 验证（最多15秒）
            await page.wait_for_timeout(8000)
            title = await page.title()
            body = await page.inner_text('body')
            print(f"标题: {title}")
            print(f"页面长度: {len(body)}")
            print(f"含Please Enable: {'Please Enable JavaScript' in body}")
            print(f"正文前500: {body[:500]}")
            await page.screenshot(path='data/tmp/cl46_shot.png')
            print("截图已保存 data/tmp/cl46_shot.png")
        except Exception as e:
            print(f"访问失败: {e}")
        await browser.close()

asyncio.run(main())
