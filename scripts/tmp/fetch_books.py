#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_books.py — 打通断链①: api-football 13 家逐家赔率 → fundflow_books.json

用途: calc_all.py 的 P0-1 跨机构 spread 需要【逐家】赔率（真·跨机构）。
      本脚本调 api-football /odds?fixture=<ID>，把每家 bookmaker 的 **Match Winner**
      赔率转成 [{"bookmaker":name,"h":..,"d":..,"a":..}] 落到 data/tmp/fundflow_books.json。

用法:
    python data/tmp/fetch_books.py --fixture 1550132
    python data/tmp/fetch_books.py --fixture 1550132 --out data/tmp/fundflow_books.json

key 来源（优先级）: 环境变量 API_FOOTBALL_KEY → reasonix.toml 的 env → api_football_mcp.ENV_KEY
三态: ok(写入) / no_key(无 key) / error(网络或空数据) —— 均写出三态 JSON 并 **exit 0**（非异常）。
"""
import argparse
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import json
import os
import re
import sys
import urllib.request

BASE = "https://v3.football.api-sports.io"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # W
DEFAULT_OUT = os.path.join(HERE, 'fundflow_books.json')


def _key_from_toml():
    for cand in (os.path.join(ROOT, 'reasonix.toml'), os.path.join(ROOT, '.reasonix', 'reasonix.toml')):
        try:
            with open(cand, encoding='utf-8') as f:
                text = f.read()
            m = re.search(r'API_FOOTBALL_KEY\s*=\s*"([^"]+)"', text)
            if m:
                return m.group(1).strip()
        except Exception:
            continue
    return ''


def resolve_key():
    k = os.environ.get('API_FOOTBALL_KEY', '').strip()
    if k:
        return k, 'env'
    k = _key_from_toml()
    if k:
        return k, 'reasonix.toml'
    try:
        sys.path.insert(0, HERE)
        import api_football_mcp as _m
        k = (getattr(_m, 'ENV_KEY', '') or '').strip()
        if k:
            return k, 'api_football_mcp'
    except Exception:
        pass
    return '', 'none'


def parse_books(payload):
    """从 /odds 响应提取逐家 Match Winner → [{bookmaker,h,d,a}]"""
    books = []
    resp = payload.get('response') or []
    for r in resp:
        for b in (r.get('bookmakers') or []):
            name = b.get('name')
            h = d = a = None
            for bet in (b.get('bets') or []):
                if (bet.get('name') or '').strip().lower() in ('match winner', '1x2', 'winner'):
                    for v in (bet.get('values') or []):
                        val = (v.get('value') or '').strip().lower()
                        try:
                            odd = float(v.get('odd'))
                        except (TypeError, ValueError):
                            continue
                        if val in ('home', '1'):
                            h = odd
                        elif val in ('draw', 'x'):
                            d = odd
                        elif val in ('away', '2'):
                            a = odd
            if h is not None and d is not None and a is not None:
                books.append({'bookmaker': name, 'h': h, 'd': d, 'a': a})
    return books


def write_out(out_path, obj):
    # 🔴2026-09-21 修复: 仅 status=='ok' 才落盘 —— 原实现 error/no_key 也写 →
    #   会污染生产 data/tmp/fundflow_books.json（实测留下 292B 的 status=error 文件，
    #   即使 load_books 会返回 None，仍属脏写；且 check_luopan 留痕会被误导）
    if obj.get('status') != 'ok':
        return False
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f'⚠️ 写文件失败 {out_path}: {e}')
        return False


def main():
    ap = argparse.ArgumentParser(description='api-football 逐家赔率 → fundflow_books.json')
    ap.add_argument('--fixture', required=True, help='api-football fixture id（由 fixtures?date 定位）')
    ap.add_argument('--out', default=DEFAULT_OUT, help='输出路径（默认 data/tmp/fundflow_books.json）')
    args = ap.parse_args()

    key, src = resolve_key()
    if not key:
        obj = {'status': 'no_key', 'fixture': args.fixture, 'books': [],
               'note': '无 API_FOOTBALL_KEY（环境变量/reasonix.toml/mcp 均无）→ 待补 key',
               'hint': 'export API_FOOTBALL_KEY=xxx 或写 reasonix.toml env'}
        write_out(args.out, obj)
        print(json.dumps(obj, ensure_ascii=False, indent=2))
        print(f'📄 未落盘(仅打印·status!=ok 不写文件): {args.out}（key 来源=none）')
        return 0

    url = f"{BASE}/odds?fixture={args.fixture}"
    try:
        req = urllib.request.Request(url, headers={'x-apisports-key': key, 'Accept': 'application/json'})
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read().decode('utf-8'))
    except Exception as e:
        obj = {'status': 'error', 'fixture': args.fixture, 'books': [],
               'note': f'请求失败: {str(e)[:200]}', 'key_source': src}
        write_out(args.out, obj)
        print(json.dumps(obj, ensure_ascii=False, indent=2))
        print(f'📄 未落盘(仅打印·status!=ok 不写文件): {args.out}（status=error）')
        return 0

    errs = payload.get('errors') or {}
    if errs:
        obj = {'status': 'error', 'fixture': args.fixture, 'books': [], 'errors': errs,
               'note': 'api-football 返回 errors', 'key_source': src}
        write_out(args.out, obj)
        print(json.dumps(obj, ensure_ascii=False, indent=2))
        print(f'📄 未落盘(仅打印·status!=ok 不写文件): {args.out}（status=error）')
        return 0

    books = parse_books(payload)
    if not books:
        obj = {'status': 'error', 'fixture': args.fixture, 'books': [],
               'note': '响应无 Match Winner 逐家赔率（fixture 未开赔或字段缺失）', 'key_source': src}
        write_out(args.out, obj)
        print(json.dumps(obj, ensure_ascii=False, indent=2))
        print(f'📄 未落盘(仅打印·status!=ok 不写文件): {args.out}（status=error·无逐家数据）')
        return 0

    obj = {'status': 'ok', 'fixture': args.fixture, 'n_books': len(books),
           'key_source': src, 'books': books}
    write_out(args.out, obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f'✅ 已写 {len(books)} 家 → {args.out}（key 来源={src}）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
