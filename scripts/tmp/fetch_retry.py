"""数据拉取重试封装（2026-08-29·解决 Odds-API SSL 偶发失败/代理不稳）
用法:
  from fetch_retry import fetch_json
  d = fetch_json("https://api.odds-api.io/v3/odds?apiKey=...&eventId=...")
自动: 3次重试·代理127.0.0.1:7897·超时25s·失败返回None(不崩)
"""
import json, subprocess, sys, time
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')  # 🔴2026-09-04链路优化: 默认GBK控制台防UnicodeEncodeError崩溃/乱码
except Exception:
    pass


PROXY = "http://127.0.0.1:7897"
RETRIES = 3
TIMEOUT = 25

def fetch_json(url, use_proxy=True, retries=RETRIES, timeout=TIMEOUT):
    """带重试的 URL→json 拉取（curl·代理容错）·失败返回 None"""
    for i in range(retries):
        try:
            cmd = ['curl', '-s', '--max-time', str(timeout)]
            if use_proxy:
                cmd += ['-x', PROXY]
            cmd += [url]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
            if r.returncode == 0 and r.stdout.strip():
                try:
                    return json.loads(r.stdout)
                except json.JSONDecodeError:
                    pass  # 重试
            if i < retries - 1:
                time.sleep(2 * (i + 1))
        except Exception:
            time.sleep(2 * (i + 1))
    return None

def fetch_text(url, use_proxy=True, retries=RETRIES, timeout=20):
    """带重试的 URL→文本（新闻/预览·不要求 json）·失败返回 None"""
    for i in range(retries):
        try:
            cmd = ['curl', '-s', '--max-time', str(timeout)]
            if use_proxy:
                cmd += ['-x', PROXY]
            cmd += [url]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout
            if i < retries - 1:
                time.sleep(2 * (i + 1))
        except Exception:
            time.sleep(2 * (i + 1))
    return None

if __name__ == '__main__':
    # 自测
    sys.path.insert(0, '.')
    d = fetch_json("https://api.odds-api.io/")  # 根路径404·应返回None(连接通)
    print('fetch_json 根路径(404预期None):', d)
    print('重试封装就绪（3次·代理·SSL容错）')
