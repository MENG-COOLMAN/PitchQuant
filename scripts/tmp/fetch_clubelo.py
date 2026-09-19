# -*- coding: utf-8 -*-
"""
ClubElo 抓取v3(最终): 五大联赛当前 ELO（2026-27·每日更新·免费）
来源: http://clubelo.com/  HTML表格解析（每国家一 table·Level1节）
输出: data/tmp/clubelo_<date>.json
用法: PYTHONIOENCODING=utf-8 python scripts/tmp/fetch_clubelo.py
"""
import re, json, os, datetime, urllib.request
import sys

# GBK console guard (2026-09-15)
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


FEDS = {'England': '英超', 'Spain': '西甲', 'Germany': '德甲', 'Italy': '意甲', 'France': '法甲'}

def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')

ROW = re.compile(r'<small>\s*(\d+)\s*</small>.*?<span class="NonAst">([A-Z0-9]+)</span><span class="Ast">([^<]+)</span></a></td><td class="r">(-?\d+)</td>')
LVL = re.compile(r'<i>\s*Level (\d) \((\d+) teams\)</i></td><td><i>⌀(\d+)</i>')

def parse_block(block):
    """解析一个国家块: 返回 {level: [(rank,tlc,name,elo)]}"""
    levels = {}
    cur = None
    for lvl_m in LVL.finditer(block):
        cur = int(lvl_m.group(1))
        levels[cur] = []
        # 该 level 行: 从 lvl_m.end() 到下一个 Level 标记
        nxt = LVL.search(block, lvl_m.end())
        seg_end = nxt.start() if nxt else len(block)
        seg = block[lvl_m.end():seg_end]
        for r, t, n, e in ROW.findall(seg):
            levels[cur].append({'rank': int(r), 'tlc': t, 'name': n.strip(), 'elo': int(e)})
    return levels

def main():
    html = fetch('http://clubelo.com/')
    dm = re.search(r'Page created on ([\d-]+ [\d:]+)', html)
    page_date = dm.group(1) if dm else 'unknown'
    print(f"抓取 {len(html)} bytes | 页面日期: {page_date}")

    out = {}
    total = 0
    for m in re.finditer(r'<a href="([A-Z]{3})">([^<]+)</a></div><div class="accordion-content"><table class="ast">(.*?)(?=</table>)', html, re.S):
        code, country, block = m.group(1), m.group(2), m.group(3)
        if country not in FEDS:
            continue
        levels = parse_block(block)
        l1 = levels.get(1, [])
        out[FEDS[country]] = {'fed_code': code, 'level1_n': len(l1), 'teams': l1}
        total += len(l1)
        avg = sum(t['elo'] for t in l1) / len(l1) if l1 else 0
        print(f"  {FEDS[country]}({code}): Level1 {len(l1)} 队·均值⌀{avg:.0f} | " + ' '.join(f"{t['name']}={t['elo']}" for t in l1[:4]) + ('...' if len(l1) > 4 else ''))

    print(f"五大联赛 Level1 合计: {total} 队")
    p = f"data/tmp/clubelo_{datetime.date.today().strftime('%Y%m%d')}.json"
    json.dump({'date': page_date, 'leagues': out}, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"已保存: {p}")

if __name__ == '__main__':
    main()
