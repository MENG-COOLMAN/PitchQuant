# -*- coding: utf-8 -*-
"""Playwright 抓 fenxi.zgzcw.com 欧赔(bjop)+亚盘(ypdb)+大小球(dxdb)·V2通用版
用法: python pw_odds_v2.py <MID> [额外MID...]
输出: data/tmp/zgzcw_{MID}_pw.json -> {europe:[], asia:[], dxdb:[]}
"""
import io, sys, json, re, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from playwright.sync_api import sync_playwright

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0'
# 页面: 名称 -> 路径
PAGES = [('europe', 'bjop'), ('asia', 'ypdb'), ('dxdb', 'dxdb')]

def parse_tables(html):
    """解析表格为行列表"""
    out = []
    for tb in re.findall(r'<table[^>]*>(.*?)</table>', html, re.S):
        for r in re.findall(r'<tr[^>]*>(.*?)</tr>', tb, re.S):
            cells = [c.strip() for c in re.sub(r'<[^>]+>', '|', r).split('|') if c.strip()]
            if cells:
                out.append(cells)
    return out

def is_waf(body):
    return any(k in body for k in ['人机验证', 'Access Verification', '过于频繁', 'Please Enable JavaScript', '访问过于频繁'])

def fetch_mid(p, mid, page):
    results = {}
    for name, path in PAGES:
        try:
            page.goto(f'http://fenxi.zgzcw.com/{mid}/{path}', timeout=30000, wait_until='domcontentloaded')
            page.wait_for_timeout(5000)
            body = page.inner_text('body')
            if is_waf(body):
                print(f'[{mid}] ✗ {name}: WAF拦截')
                results[name] = {'waf': True}
                continue
            html = page.content()
            rows = parse_tables(html)
            inst = [r for r in rows if len(r) >= 7 and r[0].isdigit()]
            print(f'[{mid}] ✓ {name}: 表格{len(rows)}行·机构{len(inst)}行')
            results[name] = inst
        except Exception as e:
            print(f'[{mid}] ✗ {name}: ERR {e}')
            results[name] = {'error': str(e)}
        page.wait_for_timeout(1500)
    return results

def main():
    mids = sys.argv[1:] or ['4608845']
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA)
        page = ctx.new_page()
        for mid in mids:
            print(f'=== MID {mid} ===')
            results = fetch_mid(p, mid, page)
            out = f'data/tmp/zgzcw_{mid}_pw.json'
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=1)
            print(f'保存 → {out}')
            # 样例输出
            for name in ['europe', 'asia', 'dxdb']:
                v = results.get(name)
                if v and not isinstance(v, dict):
                    print(f'  {name}样例:', v[1] if len(v) > 1 else v[0])
            page.wait_for_timeout(8000)  # 冷却防WAF
        browser.close()

if __name__ == '__main__':
    main()
