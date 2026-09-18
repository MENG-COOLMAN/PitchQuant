# -*- coding: utf-8 -*-
"""zgzcw 综合抓取 v4：最少请求 + 先试现cookie + 退避重试
用法: python zgzcw_crawl.py <matchId> [输出json路径]
"""
import io, sys, re, json, subprocess, os, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0'
CJ = 'data/tmp/zgzcw_cookies.txt'
os.makedirs('data/tmp', exist_ok=True)

def curl(url, referer=None):
    cmd = ['curl', '-s', '-L', '--max-time', '20', '-b', CJ, '-c', CJ,
           url, '-H', f'User-Agent: {UA}']
    if referer: cmd += ['-H', f'Referer: {referer}']
    return subprocess.run(cmd, capture_output=True, timeout=30).stdout.decode('utf-8', errors='replace')

def ok(t, ok_kw=None):
    return 'Please Enable JavaScript' not in t and len(t) > 10000 and (ok_kw is None or ok_kw in t)

def fetch_ok(url, referer=None, ok_kw=None, retries=4):
    """先确保有效会话（bjzs>20KB）→ 抓详情 → 失败退避重试"""
    for i in range(retries):
        # 确保会话有效（bjzs 有时返回 7.7KB 壳页·需验证）
        sess_ok = False
        for _ in range(3):
            t = curl('https://plzx.zgzcw.com/bjzs')
            if len(t) > 20000:
                sess_ok = True
                break
        if not sess_ok:
            time.sleep(2 + i)
            continue
        t = curl(url, referer)
        if ok(t, ok_kw):
            return t
        time.sleep(2 + i)  # 退避·防 WAF 高频封禁
    return ''

def parse_jsonodds(t):
    m = re.search(r"var JsonOdds\s*=\s*'([^']*)';", t, re.S)
    if not m: return None
    raw = m.group(1)
    try:
        return json.loads(raw)
    except Exception:
        pass
    for k in ['MODIFY_DATE', 'GUEST', 'HOST', 'HANDICAP']:
        raw = raw.replace(k, f'"{k}"')
    raw = re.sub(r'=\s*([^,}]+)', r': "\1"', raw)
    return json.loads(raw)

def table_rows(t):
    out = []
    for tb in re.findall(r'<table[^>]*>(.*?)</table>', t, re.S):
        for r in re.findall(r'<tr[^>]*>(.*?)</tr>', tb, re.S):
            cells = [c.strip() for c in re.sub(r'<[^>]+>', '|', r).split('|') if c.strip()]
            if cells: out.append(cells)
    return out

def main(match_id):
    res = {'match_id': match_id}
    t = fetch_ok(f'http://fenxi.zgzcw.com/{match_id}/bjop', ok_kw='<table')
    rows = table_rows(t)
    res['europe'] = [r for r in rows if len(r) >= 7 and r[0].isdigit()]
    t = fetch_ok(f'http://fenxi.zgzcw.com/{match_id}/ypdb', ok_kw='<table')
    rows = table_rows(t)
    res['asia'] = [r for r in rows if len(r) >= 7 and r[0].isdigit()]
    t = fetch_ok(f'http://fenxi.zgzcw.com/{match_id}/bsls', ok_kw='<table')
    rows = table_rows(t)
    res['history'] = [r for r in rows if len(r) >= 7]
    jc = None
    for i in range(4):
        t = curl('https://plzx.zgzcw.com/bjzs')
        jc = parse_jsonodds(t)
        if jc: break
        time.sleep(2 + i)
    res['jc_flow'] = jc
    return res

if __name__ == '__main__':
    mid = sys.argv[1] if len(sys.argv) > 1 else '4608845'
    out = sys.argv[2] if len(sys.argv) > 2 else f'data/tmp/zgzcw_{mid}.json'
    r = main(mid)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    print(f"✅ 抓取完成 → {out}")
    print(f"  竞彩逐T: {len(r['jc_flow']) if r['jc_flow'] else 0}场")
    print(f"  欧赔机构: {len(r['europe'])}家")
    print(f"  亚盘机构: {len(r['asia'])}家")
    print(f"  历史记录: {len(r['history'])}行")
