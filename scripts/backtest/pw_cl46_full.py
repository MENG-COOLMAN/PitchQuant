# -*- coding: utf-8 -*-
"""Playwright 完整管线 v2：欧冠90场 → bsls(21列) → 欧战历史数据库
用法: python pw_cl46_full.py [开始索引] [结束索引]
"""
import io, sys, asyncio, re, json, time, csv, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from playwright.async_api import async_playwright

OUT_CSV = 'data/zgzcw_eu_history_full.csv'
HEADER = ['source_mid','source_time','source_match','league','round','date','home','score','away','ht',
          'odd99_h','odd99_d','odd99_a','odd_ao_h','odd_ao_d','odd_ao_a',
          'handi_h','handi_hc','handi_a','panlu']

def load_done():
    if os.path.exists(OUT_CSV):
        with open(OUT_CSV, encoding='utf-8-sig') as f:
            return set(r['source_mid'] for r in csv.DictReader(f))
    return set()

def parse_bsls(html, mid, mtime, mname):
    """21列表头版解析：联赛 轮次 时间 主 比分 客 半场 [99家终赔3] [澳3] ... [亚盘3] 盘路"""
    recs = []
    for tb in re.findall(r'<table[^>]*>(.*?)</table>', html, re.S):
        trs = re.findall(r'<tr[^>]*>(.*?)</tr>', tb, re.S)
        if len(trs) < 10: continue
        for r in trs[1:]:
            cells = [c.strip() for c in re.sub(r'<[^>]+>', '|', r).split('|')]
            cells = [c for c in cells if c != '']  # 过滤空但保序
            # 基础 12+ 列: 联赛 轮次 时间 主 比分 客 半场 欧赔3 亚盘3
            if len(cells) >= 12 and ':' in (cells[4] if len(cells) > 4 else ''):
                recs.append({
                    'source_mid': mid, 'source_time': mtime, 'source_match': mname,
                    'league': cells[0], 'round': cells[1], 'date': cells[2],
                    'home': cells[3], 'score': cells[4], 'away': cells[5], 'ht': cells[6],
                    'odd99_h': cells[7], 'odd99_d': cells[8], 'odd99_a': cells[9],
                    'odd_ao_h': cells[10] if len(cells) > 10 else '',
                    'odd_ao_d': cells[11] if len(cells) > 11 else '',
                    'odd_ao_a': cells[12] if len(cells) > 12 else '',
                    'handi_h': cells[13] if len(cells) > 13 else '',
                    'handi_hc': cells[14] if len(cells) > 14 else '',
                    'handi_a': cells[15] if len(cells) > 15 else '',
                    'panlu': cells[16] if len(cells) > 16 else '',
                })
    return recs

async def main(start_idx, end_idx):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0')
        page = await ctx.new_page()
        await page.goto('http://saishi.zgzcw.com/soccer/cup/46', timeout=30000, wait_until='domcontentloaded')
        await page.wait_for_timeout(8000)
        rows = await page.eval_on_selector_all('tr', '''els => els.map(e => {
            const tds=[...e.querySelectorAll('td')].map(t=>t.textContent.replace(/\\s+/g,' ').trim());
            const fenxi=[...e.querySelectorAll('a')].map(a=>a.href).find(h=>h&&h.includes('fenxi.zgzcw.com'));
            return {tds, fenxi};
        })''')
        matches = []
        for r in rows:
            if r['fenxi'] and len(r['tds']) >= 6:
                mid = re.search(r'/(\d+)/', r['fenxi']).group(1)
                matches.append({'mid': mid, 'time': r['tds'][0], 'home': r['tds'][1],
                                'score': r['tds'][2], 'away': r['tds'][3]})
        print(f"欧冠赛程: {len(matches)} 场")
        done = load_done()
        slice_ = matches[start_idx:min(end_idx, len(matches))]
        print(f"本批 {start_idx}-{min(end_idx,len(matches))}: {len(slice_)} 场 · 库中已完成 {len(done)}")
        new_recs = []
        for i, m in enumerate(slice_):
            if m['mid'] in done:
                continue
            # WAF 冷却重试
            for attempt in range(3):
                try:
                    await page.goto(f'http://fenxi.zgzcw.com/{m["mid"]}/bsls', timeout=25000, wait_until='domcontentloaded')
                    await page.wait_for_timeout(4000)
                    body = await page.inner_text('body')
                    if '人机验证' in body or 'Access Verification' in body or '过于频繁' in body:
                        print(f"  [{start_idx+i}] {m['mid']} WAF验证·冷却60s·重试{attempt+1}")
                        await browser.close()
                        await asyncio.sleep(60)
                        browser = await p.chromium.launch(headless=True)
                        ctx = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0')
                        page = await ctx.new_page()
                        await page.goto('http://saishi.zgzcw.com/soccer/cup/46', timeout=30000, wait_until='domcontentloaded')
                        await page.wait_for_timeout(5000)
                        continue
                    html = await page.content()
                    recs = parse_bsls(html, m['mid'], m['time'], f"{m['home']} vs {m['away']}")
                    new_recs.extend(recs)
                    print(f"  [{start_idx+i}/{len(matches)}] {m['mid']} {m['home']}vs{m['away']}: {len(recs)} 条")
                    break
                except Exception as e:
                    print(f"  [{start_idx+i}] {m['mid']} ERR {e}")
                    await asyncio.sleep(10)
            await asyncio.sleep(8)  # 降频·防 WAF 限流
        if new_recs:
            is_new = not os.path.exists(OUT_CSV) or os.path.getsize(OUT_CSV) == 0
            with open(OUT_CSV, 'a', encoding='utf-8-sig', newline='') as f:
                w = csv.DictWriter(f, fieldnames=HEADER)
                if is_new: w.writeheader()
                w.writerows(new_recs)
        print(f"✅ 本批新增 {len(new_recs)} 条 → 累计 {len(done)+len(new_recs)}")
        await browser.close()

if __name__ == '__main__':
    s = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    e = int(sys.argv[2]) if len(sys.argv) > 2 else 999
    asyncio.run(main(s, e))
