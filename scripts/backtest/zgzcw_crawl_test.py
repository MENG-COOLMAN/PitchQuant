# -*- coding: utf-8 -*-
"""zgzcw 综合抓取验证：一场比赛完整数据（竞彩逐T+欧赔+亚盘+历史）→ 结构化输出"""
import io, sys, re, json, subprocess, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0'
CJ = 'data/tmp/cookies2.txt'
os.makedirs('data/tmp', exist_ok=True)

def fetch(url, referer=None, cookie_jar=CJ):
    cmd = ['curl', '-s', '-L', '--max-time', '20', '-b', cookie_jar, '-c', cookie_jar,
           url, '-H', f'User-Agent: {UA}']
    if referer: cmd += ['-H', f'Referer: {referer}']
    out = subprocess.run(cmd, capture_output=True, timeout=30)
    return out.stdout.decode('utf-8', errors='replace')

# 1. 建立会话（bjzs 种 cookie）
fetch('https://plzx.zgzcw.com/bjzs')
print("✅ 会话建立")

match_id = '4608845'  # 奈梅亨vs博德闪耀
result = {'match_id': match_id, 'team': '奈梅亨vs博德闪耀', 'league': '欧冠'}

# 2. 竞彩逐T（从 bjzs 页面 JsonOdds 提取——需对应场次）
t = fetch('https://plzx.zgzcw.com/bjzs', referer='https://plzx.zgzcw.com/')
m = re.search(r'var JsonOdds\s*=\s*(\'.*?\');', t, re.S)
if m:
    data = json.loads(m.group(1)[1:-1])
    result['jc_flow'] = {'matches': len(data), 'points_per_match': len(data[0]) if data else 0,
                         'sample_latest': data[0][-1] if data else None}

# 3. 百家欧赔 bjop
t = fetch(f'http://fenxi.zgzcw.com/{match_id}/bjop', referer='https://plzx.zgzcw.com/bjzs')
tables = re.findall(r'<table[^>]*>(.*?)</table>', t, re.S)
companies = []
for tb in tables:
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tb, re.S)
    for r in rows[1:]:
        cells = [c.strip() for c in re.sub(r'<[^>]+>', '|', r).split('|') if c.strip()]
        if len(cells) >= 7 and cells[0].isdigit():
            companies.append({'name': cells[1], 'init': cells[2:5], 'latest': cells[5:8]})
result['europe'] = {'companies': len(companies), 'top10': companies[:10]}

# 4. 亚盘 ypdb
t = fetch(f'http://fenxi.zgzcw.com/{match_id}/ypdb', referer=f'http://fenxi.zgzcw.com/{match_id}/bjop')
tables = re.findall(r'<table[^>]*>(.*?)</table>', t, re.S)
asia = []
for tb in tables:
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tb, re.S)
    for r in rows[1:]:
        cells = [c.strip() for c in re.sub(r'<[^>]+>', '|', r).split('|') if c.strip()]
        if len(cells) >= 7 and cells[0].isdigit():
            asia.append({'name': cells[1], 'init_water': cells[2], 'init_handi': cells[3],
                         'init_away': cells[4], 'latest_water': cells[5], 'latest_handi': cells[6]})
result['asia'] = {'companies': len(asia), 'top8': asia[:8]}

# 5. 历史 bsls（两队近期）
t = fetch(f'http://fenxi.zgzcw.com/{match_id}/bsls', referer=f'http://fenxi.zgzcw.com/{match_id}/ypdb')
tables = re.findall(r'<table[^>]*>(.*?)</table>', t, re.S)
history = []
for tb in tables:
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tb, re.S)
    if len(rows) > 20:  # 大表=历史战绩
        for r in rows[1:6]:
            cells = [c.strip() for c in re.sub(r'<[^>]+>', '|', r).split('|') if c.strip()]
            if len(cells) >= 7:
                history.append({'league': cells[0], 'date': cells[2], 'match': cells[3:6], 'odds': cells[6:9]})
result['history'] = {'records': len(history), 'sample': history[:4]}

# 输出
print(json.dumps(result, ensure_ascii=False, indent=1)[:2500])
