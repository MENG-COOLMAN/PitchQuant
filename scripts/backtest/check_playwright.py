# -*- coding: utf-8 -*-
"""检测 playwright 可用性 + 试 fenxi 列表变体"""
import io, sys, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# playwright 检测
try:
    import playwright
    print("python playwright: 可用")
except ImportError:
    print("python playwright: 不可用（需 pip install playwright）")

# npm playwright
r = subprocess.run(['npm', 'ls', 'playwright'], capture_output=True, text=True, cwd='.')
print("npm playwright:", '可用' if 'playwright@' in r.stdout else '未安装')

# fenxi 变体
import time
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0'
CJ = 'data/tmp/saishi_jar.txt'
for path in ['bfyc', 'matchlist']:
    url = f'https://fenxi.zgzcw.com/{path}'
    out = subprocess.run(['curl', '-s', '-L', '--max-time', '20', '-b', CJ, '-c', CJ, url,
                          '-H', f'User-Agent: {UA}'], capture_output=True, timeout=30)
    t = out.stdout.decode('utf-8', errors='replace')
    print(f"{path}: {len(t)}B · Please={'Please Enable' in t}")
    time.sleep(2)
