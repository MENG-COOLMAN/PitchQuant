# -*- coding: utf-8 -*-
"""批量抓欧冠 bsls 历史（低频·WAF友好）→ 欧战历史数据库验证"""
import io, sys, re, subprocess, time, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0'
CJ = 'data/tmp/eu_jar.txt'
os.makedirs('data/tmp', exist_ok=True)

def curl(url, referer=None):
    cmd = ['curl', '-s', '-L', '--max-time', '20', '-b', CJ, '-c', CJ, url, '-H', f'User-Agent: {UA}']
    if referer: cmd += ['-H', f'Referer: {referer}']
    return subprocess.run(cmd, capture_output=True, timeout=30).stdout.decode('utf-8', errors='replace')

def fetch_bsls(mid):
    for i in range(3):
        curl('https://plzx.zgzcw.com/bjzs')
        t = curl(f'http://fenxi.zgzcw.com/{mid}/bsls', referer='https://plzx.zgzcw.com/bjzs')
        if 'Please Enable JavaScript' not in t and len(t) > 100000:
            return t
        time.sleep(3 + i)
    return ''

def parse_history(t):
    rows = []
    for tb in re.findall(r'<table[^>]*>(.*?)</table>', t, re.S):
        trs = re.findall(r'<tr[^>]*>(.*?)</tr>', tb, re.S)
        if len(trs) < 10: continue
        for r in trs[1:]:
            cells = [c.strip() for c in re.sub(r'<[^>]+>', '|', r).split('|') if c.strip()]
            if len(cells) >= 11:
                rows.append(cells)
    return rows

targets = {
    '4608831': '凯尔特人vs林茨',
    '4608838': '布拉迪斯拉发vs采列',
}
for mid, label in targets.items():
    t = fetch_bsls(mid)
    if not t:
        print(f"{mid} {label}: 抓取失败（WAF）")
        continue
    hist = parse_history(t)
    with open(f'data/tmp/eu_bsls_{mid}.html', 'w', encoding='utf-8') as f:
        f.write(t)
    print(f"{mid} {label}: OK {len(hist)} 行历史")
    for r in hist[:3]:
        print("   ", ' | '.join(r[:11])[:100])
    time.sleep(4)
