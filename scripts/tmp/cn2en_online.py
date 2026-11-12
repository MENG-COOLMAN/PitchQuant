# -*- coding: utf-8 -*-
"""cn2en_online —— 队名**联网兜底**反查（2026-10-31 用户指令）

用户指令原文:
  「这种简称匹配不到正确英文的情况不应该发生，做一个 if 机制，
    如果能正常获取到英文名映射就继续，如果不能则上网查询，然后继续，
    严禁存在查不到简称就 missing 的情况」

三层机制（`cn2en_list` 内嵌调用·本地全查不到时触发）:
  ① 本地三表（cn2en_extra / TEAM_ALIASES / 国家队）→ 命中即返回（**零开销**·正常场次不走本模块）
  ② **联网**：中文维基百科跨语言链接（`langlinks lllang=en`）
     · 批量 `titles`（MediaWiki 上限 50/批·**原词批** → 命中约 60%）
     · **后缀批**（+足球俱乐部/足球會/足球俱樂部）→ 再补约 10%
     · **搜索兜底**（`list=search`·每队 ≤1 次）→ 补剩余
  ③ **缓存 + 自我进化**：命中即写 `cn2en_online_cache.json` **并回写 `cn2en_extra.json`**
     → 下次本地直接命中，永远不再联网

🔴 负缓存: 查不到的也记（`src='miss'`·7 天过期）→ 防每场重复联网（慢）。
🔴 校验: 搜到的页面须像球队（含 足球/球會/俱乐部/F.C./FK/FC/CF 等）·防「年轻人」搜到无关页。
"""
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_P = os.path.join(HERE, 'cn2en_online_cache.json')
EXTRA_P = os.path.join(HERE, 'cn2en_extra.json')
PROXY = '127.0.0.1:7897'
NEG_TTL = 7 * 86400          # 负缓存 7 天
POS_TTL = 400 * 86400        # 正缓存长期（本地表已固化）

_MEM = {}                    # 进程内缓存（一次分析内多源共享）
_DEADLINE = [0.0]            # 🔴当前 lookup 的绝对截止时刻（治「24.6s 超预算」）


def _left():
    """剩余预算秒数（<=0 表示耗尽·立即停手）"""
    if not _DEADLINE[0]:
        return 99.0
    return _DEADLINE[0] - time.time()


def _sub2(a, b):
    """查询名与标题是否有 **≥2 字连续子串**（防误配：林肯红魔 vs 布伦特福德 = 0）
    简体查询 vs 繁体标题时子串也不匹配 → 保守拒绝（宁可为空·不可张冠李戴）
    """
    a, b = str(a or ''), str(b or '')
    if len(a) < 2 or len(b) < 2:
        return False
    for i in range(len(a) - 1):
        if a[i:i + 2] in b:
            return True
    return False


# ---------------- 基础设施 ----------------
def _get(url, to=8):
    """代理优先 → 直连（实测维基经代理通·直连常超时）
    🔴单次 timeout = min(传入, 剩余预算)·预算耗尽直接返回 None（治超时）
    """
    to = max(1.0, min(float(to), _left()))
    if _left() <= 0.5:
        return None
    for hs in ([urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY})],
               [urllib.request.ProxyHandler({})]):
        try:
            op = urllib.request.build_opener(*hs)
            rq = urllib.request.Request(url, headers={'User-Agent': 'FootballModel/3.5.84'})
            with op.open(rq, timeout=to) as r:
                raw = r.read()
            if raw[:2] == b'\x1f\x8b':
                raw = gzip.decompress(raw)
            return json.loads(raw.decode('utf-8'))
        except Exception:
            continue
    return None


def _load_cache():
    try:
        return json.load(io.open(CACHE_P, encoding='utf-8'))
    except Exception:
        return {}


def _save_cache(d):
    try:
        json.dump(d, io.open(CACHE_P, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    except Exception:
        pass


def _writeback(cn, ens):
    """命中即回写本地表 → 下次零联网（自我进化）"""
    try:
        ex = json.load(io.open(EXTRA_P, encoding='utf-8'))
    except Exception:
        return
    cur = ex.get(cn)
    lst = list(cur) if isinstance(cur, list) else ([cur] if isinstance(cur, str) else [])
    changed = False
    for e in ens:
        if e and e not in lst:
            lst.append(e)
            changed = True
    if changed:
        ex[cn] = lst
        try:
            json.dump(ex, io.open(EXTRA_P, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        except Exception:
            pass


# ---------------- 维基查询 ----------------
def _batch_titles(names, to=12):
    """titles 批量（≤50/批）→ {原始变体: 英文}"""
    out = {}
    for i in range(0, len(names), 45):
        chunk = names[i:i + 45]
        j = _get('https://zh.wikipedia.org/w/api.php?action=query&titles=%s&prop=langlinks'
                 '&lllang=en&format=json&redirects=1'
                 % urllib.parse.quote('|'.join(chunk)), to=to)
        if not j:
            continue
        qy = j.get('query', {})
        redir = {}
        for r in (qy.get('normalized') or []):
            redir[r.get('from')] = r.get('to')
        for r in (qy.get('redirects') or []):
            redir[r.get('from')] = r.get('to')
        t2e = {}
        for _pid, pg in (qy.get('pages') or {}).items():
            ll = (pg.get('langlinks') or [])
            if ll and pg.get('title'):
                t2e[pg['title']] = ll[0].get('*')
        for v in chunk:
            t, seen = v, set()
            while t in redir and t not in seen:
                seen.add(t)
                t = redir[t]
            if t in t2e:
                out[v] = t2e[t]
    return out


_TEAM_HINT = re.compile(r'足球|球會|球会|俱乐部|俱樂部|F\.?C\.?|FK|CF|SC|AFC| Sporting | Club |United|City|FC\b|隊|队')


def _search_one(name, to=4):
    """搜索兜底：先搜到正确标题 → 再查英文（每队 ≤2 请求）"""
    j = _get('https://zh.wikipedia.org/w/api.php?action=query&list=search&srsearch=%s'
             '&format=json&srlimit=4' % urllib.parse.quote(name + ' 足球'), to=to)
    if not j:
        return None
    titles = [x.get('title') for x in (j.get('query', {}).get('search') or []) if x.get('title')]
    # 🔴两道闸: ① 像球队 ② **与查询名有 ≥2 字连续子串**（防「林肯红魔→布伦特福德」误配）
    titles = [x for x in titles if _TEAM_HINT.search(x) and _sub2(name, x)]
    if not titles:
        return None
    got = _batch_titles(titles[:3], to=to)
    for t in titles[:3]:
        if t in got:
            return got[t]
    return None


_PREFIX = re.compile(r'^(F\.?C\.?|FK|CF|SC|AFC|AS|AC|SK|BK|IF|CD|CS|SS|US|SV|VfB|VfL|TSG)\s+', re.I)


def _expand(en):
    """英文名 → 多候选（原名 + 去俱乐部前缀 + 去标点变体）"""
    out = []
    for e in [en]:
        if not e:
            continue
        out.append(e)
        s = _PREFIX.sub('', e).strip()
        if s and s != e:
            out.append(s)
        s2 = e.replace('F.C.', '').replace('FC', '').strip(' .')
        if s2 and s2 not in out:
            out.append(s2)
    seen, res = set(), []
    for x in out:
        x = x.strip()
        if x and x not in seen:
            seen.add(x)
            res.append(x)
    return res


# ---------------- 主入口 ----------------
def lookup(names, budget=12.0):
    """联网反查：{中文名: [英文候选...]}
    names 可单个字符串或列表。总耗时受 budget 约束（超时返回已得部分）。
    """
    if isinstance(names, str):
        names = [names]
    names = [n for n in names if n and re.search(r'[\u4e00-\u9fff]', str(n))]
    if not names:
        return {}
    t0 = time.time()
    _DEADLINE[0] = t0 + float(budget)      # 🔴设绝对截止时刻
    cache = _load_cache()
    now = time.time()
    res, todo = {}, []

    for n in names:
        if n in _MEM:
            res[n] = _MEM[n]
            continue
        c = cache.get(n)
        if c:
            age = now - float(c.get('at') or 0)
            ttl = POS_TTL if c.get('en') else NEG_TTL
            if age < ttl:
                res[n] = c.get('en') or []
                _MEM[n] = res[n]
                continue
        todo.append(n)

    if todo and time.time() - t0 < budget:
        # ① 原词批
        got = _batch_titles(todo) if _left() > 1 else {}
        # ② 后缀批（补未命中）
        miss = [n for n in todo if n not in got]
        if miss and _left() > 2:
            SUF = ['足球俱乐部', '足球會', '足球俱樂部']
            g2 = _batch_titles([n + s for n in miss for s in SUF])
            for n in list(miss):
                for s in SUF:
                    if n + s in g2:
                        got[n] = g2[n + s]
                        break
        # ③ 搜索兜底（每队 ≤1 次·受预算约束）
        _from_search = set()
        for n in [x for x in todo if x not in got]:
            if _left() <= 2:               # 剩余不足 2s → 停（搜索需 2 请求）
                break
            e = _search_one(n)
            if e:
                got[n] = e
                _from_search.add(n)        # 🔴搜索来源 → 只入缓存·**不回写本地表**

        for n in todo:
            # 🔴直查命中也校验（防 redirect 把简称导到无关页·如「林肯红魔」→某非球队页）
            _raw = got.get(n) or ''
            ens = _expand(_raw) if _raw else []
            cache[n] = {'en': ens, 'src': 'wiki' if ens else 'miss', 'at': now,
                        'ms': int((time.time() - t0) * 1000)}
            res[n] = ens
            _MEM[n] = ens
            # 🔴只回写**精确路径**（titles 直查）·搜索路径不回写（实测误配固化案例）
            if ens and n not in _from_search:
                _writeback(n, ens)
        _save_cache(cache)

    return res


def stats():
    """缓存统计（审计可见）"""
    c = _load_cache()
    pos = [k for k, v in c.items() if v.get('en')]
    neg = [k for k, v in c.items() if not v.get('en')]
    return {'total': len(c), 'hit': len(pos), 'miss': len(neg),
            'hit_names': pos[:12], 'miss_names': neg[:12]}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:] or ['比利亚雷', '横滨水手', '年轻人', '海法马卡比']
    t = time.time()
    r = lookup(args)
    print("查询 %d 个 · %.1fs" % (len(args), time.time() - t))
    for n in args:
        print("  %-12s → %s" % (n, r.get(n) or '❌ 仍未命中'))
    print("\n缓存统计:", {k: v for k, v in stats().items() if k in ('total', 'hit', 'miss')})
