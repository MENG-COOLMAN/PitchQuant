# -*- coding: utf-8 -*-
"""竞彩赔率截图 → 结构化文本（智谱 GLM-OCR + 可选 GLM-4.6V 结构化）

设计原则（对齐 AGENTS）：
  ① 视觉/计算全在代码层，模型只消费加工好的文本（同 time_guard 架构思想）
  ② 双引擎分级：glm-ocr 走 OCR 资源包（便宜·版面准确）；glm-4.6v 扣现金（结构化语义）
  ③ 恒有落盘产物（txt + json），失败即三态，不臆造
  ④ 直连不走系统代理（AGENTS「真直连铁律」）

用法:
  python data/tmp/img2txt.py --img <图片路径> [--engine ocr|vision|both] [--out <目录>]
  python data/tmp/img2txt.py --dir <图片目录> [--engine ocr]      # 批量

输出（默认 data/tmp/ocr_out/）:
  <stem>.ocr.md     glm-ocr 版面文本（markdown，含 bbox 占位）
  <stem>.ocr.json   layout_details 逐框（label/content/bbox_2d）+ usage
  <stem>.vision.txt glm-4.6v 结构化赔率（仅 vision/both）
  <stem>.meta.json  引擎/耗时/token/三态

退出码: 0=成功 1=部分成功(有降级) 2=全部失败
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

# 🔴🔴 2026-11-02 修「识图 15 分钟不返回」：
#   原实现 = **强制直连单通道** `build_opener(ProxyHandler({}))`。
#   实测 open.bigmodel.cn：**直连 TCP 握手 24.06s / TLS 24.09s** vs **代理 TLS 0.06s**（慢约 400 倍）
#   → 每张 OCR 白等握手 ⇒ 单张 3 分 22 秒、赛事页 glm-4.6v 15 分钟不返回。
#   🔴 与 2026-10-31「Odds-API 直连优先 → 改代理优先，prestep 6 分钟→31 秒」是**同一坑重犯**。
#   正确口径（抄 prestep_fetch `_CHANNELS`）：**代理优先(25s) → 直连回退(4s 快速失败)**。
#   🔴 AGENTS「真直连铁律」本意 = **回退通道**必须显式 `ProxyHandler({})`（禁无参 opener 继承系统代理），
#      不是「只能直连」—— 主通道应代理优先。
PROXY = os.environ.get('IMG2TXT_PROXY') or 'http://127.0.0.1:7897'
_op_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY}))
_op_direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
# (opener, 单次尝试超时秒) —— 代理优先，直连快速失败兜底
_CHANNELS = ((_op_proxy, 25), (_op_direct, 4))
LAST_CHANNEL = {'name': None}          # 便于诊断：本次请求实际走哪条通道
API = 'https://open.bigmodel.cn/api/paas/v4/'
IMG_EXT = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')


def load_key():
    """key 优先级：环境变量 > api_keys.json['zhipu']"""
    for env in ('ZHIPU_API_KEY', 'GLM_API_KEY'):
        if os.environ.get(env):
            return os.environ[env].strip(), 'env:' + env
    p = os.path.join(HERE, 'api_keys.json')
    if os.path.exists(p):
        d = json.load(open(p, encoding='utf-8'))
        if d.get('zhipu'):
            return str(d['zhipu']).strip(), 'api_keys.json'
    return None, None


def _post(path, body, key, timeout=180, deadline=None):
    """双通道 POST：**代理优先(25s) → 直连回退(4s)**

    timeout  = 单次尝试超时
    deadline = 绝对截止时刻（time.time() 基准）；与 timeout 取小。
      🔴 urllib 的 timeout 只是**单次 socket 读超时**，服务端慢速持续返回时可远超该值
         （实测赛事页 glm-4.6v 卡 15 分钟）→ 必须另有**总时限**才能真正止损。
    HTTP 错误（4xx/5xx）属服务端明确响应 → 不切通道、直接返回。
    """
    data = json.dumps(body).encode('utf-8')
    last = (-1, 'no-channel')
    for op, ch_to in _CHANNELS:
        _to = ch_to if not timeout else min(ch_to, timeout)
        if deadline is not None:
            left = deadline - time.time()
            if left <= 0.5:
                return -1, 'deadline exceeded(%.1fs 剩余)' % max(0.0, left)
            _to = min(_to, max(0.5, left))
        req = urllib.request.Request(
            API + path,
            data=data,
            headers={'Authorization': 'Bearer ' + key,
                     'Content-Type': 'application/json'},
            method='POST')
        try:
            with op.open(req, timeout=_to) as r:
                LAST_CHANNEL['name'] = 'proxy' if op is _op_proxy else 'direct'
                return r.status, json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8', 'replace')[:600]
        except Exception as e:
            last = (-1, '%s: %s' % (type(e).__name__, str(e)[:200]))
            continue
    return last


def _data_uri(path):
    ext = os.path.splitext(path)[1].lower()
    mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.webp': 'image/webp', '.bmp': 'image/bmp'}.get(ext, 'image/png')
    with open(path, 'rb') as f:
        return 'data:%s;base64,%s' % (mime, base64.b64encode(f.read()).decode())


# ─────────────────────── 引擎 A：glm-ocr 版面识别（走 OCR 资源包）───────────────────────
def ocr_layout(img, key, timeout=180, deadline=None):
    t0 = time.time()
    st, r = _post('layout_parsing', {'model': 'glm-ocr', 'file': _data_uri(img)},
                  key, timeout, deadline)
    dt = round(time.time() - t0, 2)
    if st != 200:
        return {'ok': False, 'err': 'HTTP %s: %s' % (st, str(r)[:300]), 'sec': dt}
    md = r.get('md_results') or ''
    if isinstance(md, list):
        md = '\n'.join(str(x) for x in md)
    boxes = []
    for page in (r.get('layout_details') or []):
        for b in page:
            boxes.append({'label': b.get('label'), 'content': b.get('content'),
                          'bbox': b.get('bbox_2d')})
    return {'ok': True, 'md': md, 'boxes': boxes, 'usage': r.get('usage'),
            'pages': (r.get('data_info') or {}).get('num_pages'), 'sec': dt}


# ────────────── 引擎 B：glm-4.6v 结构化赔率（扣现金·只提取不脑补）──────────────
PROMPT = """你是竞彩赔率截图提取器。严格只提取图中可见内容，禁止编造、禁止推测缺失值。

先输出【OCR原文】：把图中所有文字按版面顺序原样抄录（数字、小数点、±号、队名一字不改）。
再输出【结构化JSON】：按玩法归类。同一个玩法可能有多个时间点，全部列出。

JSON 结构（字段缺失就留空数组，不要编造）：
{
 "match": {"home":"主队","away":"客队","league":"联赛","kickoff":"开赛时间","code":"场次编号"},
 "spf":   [{"t":"发布时间或空","h":赔率,"d":赔率,"a":赔率}],
 "handi": {"line":让球值数字或null,"rows":[{"t":"","h":,"d":,"a":}]},
 "bqc":   [{"t":"","ww":,"wd":,"wl":,"dw":,"dd":,"dl":,"lw":,"ld":,"ll":}],
 "goals": [{"t":"","g0":,"g1":,"g2":,"g3":,"g4":,"g5":,"g6":,"g7":}],
 "score": [{"score":"1:0","odds":赔率}],
 "uncertain": ["凡是看不清/存疑的字段名或数值，列在这里"]
}

规则：赔率一律浮点两位小数；看不清的赔率放 uncertain 而不要瞎填；让球值带符号（主队让球为负数）。"""


# ────────────── 赛事页专用 prompt（2026-11-01 按「模型需要的槽」反推字段）──────────────
# 🔴 字段不是「OCR 有什么写什么」，而是**先看模型要什么**：
#    · 赛事行 → txt_normalize 必填节「赛事」
#    · 场次编号 → 基准 txt 第二行（周六026）
#    · 比赛时间 → txt_normalize 节「时间」
#    · 特征分析 → txt_normalize 节「特征」→ calc_match.parse_features 消费
#      → 修正53 平局信号 S4(主队近10平率/客队客场平率) + S6(交锋平数) **唯一数据源**
PROMPT_EVENT = """你在提取一场足球比赛的赛事信息页。严格只提取图中可见内容，看不清就留空字符串，禁止编造。

输出【结构化JSON】（字段值原样照抄，不要换算单位）：
{
 "match": {
   "home": "主队名", "away": "客队名", "league": "联赛名",
   "kickoff": "YYYY-MM-DD HH:MM", "code": "场次编号如 周六026",
   "round": "轮次如 第9轮或 Regular Season 第9轮"
 },
 "features": {
   "h2h_10":  {"home": "8胜0平2负", "away": "2胜0平8负"},
   "h2h_ha":  {"home": "7胜1平2负", "away": "2胜1平7负"},
   "form_10": {"home": "7胜1平2负", "away": "4胜2平4负"},
   "form_ha": {"home": "5胜1平4负", "away": "3胜4平3负"},
   "gf":      {"home": "2.4", "away": "1.2"},
   "ga":      {"home": "1.3", "away": "1.0"}
 },
 "uncertain": ["看不清的字段名"]
}
说明：h2h_10=近10场交锋 h2h_ha=同主客交锋 form_10=近10场战况 form_ha=同主客战况
     gf=场均进球 ga=场均失球；数值只写数字（2.4 不要写 2.4个）；缺失写 ""。"""


def vision_extract(img, key, timeout=90, prompt=None, deadline=None):
    # 🔴2026-11-02：单次上限由 180s 收到 90s —— 视觉页实测可卡 15 分钟，
    #   宁可 90s 三态降级（赛事行/特征缺失 → txt 里标「（三态）」），也不阻塞整批出 txt
    t0 = time.time()
    st, r = _post('chat/completions', {
        'model': 'glm-4.6v',
        'messages': [{'role': 'user', 'content': [
            {'type': 'image_url', 'image_url': {'url': _data_uri(img)}},
            {'type': 'text', 'text': prompt or PROMPT},
        ]}],
        'temperature': 0.1,
        'max_tokens': 4096,
    }, key, timeout, deadline)
    dt = round(time.time() - t0, 2)
    if st != 200:
        return {'ok': False, 'err': 'HTTP %s: %s' % (st, str(r)[:300]), 'sec': dt}
    txt = (r.get('choices') or [{}])[0].get('message', {}).get('content', '')
    return {'ok': True, 'text': txt, 'usage': r.get('usage'), 'sec': dt}


# ─────────────────────────────── 单图处理 ───────────────────────────────
def process(img, key, engine='both', outdir='data/tmp/ocr_out'):
    os.makedirs(os.path.join(ROOT, outdir), exist_ok=True) if not os.path.isabs(outdir) else os.makedirs(outdir, exist_ok=True)
    base = os.path.join(ROOT, outdir) if not os.path.isabs(outdir) else outdir
    stem = os.path.splitext(os.path.basename(img))[0]
    meta = {'img': img, 'stem': stem, 'engine': engine, 'ts': time.strftime('%Y-%m-%d %H:%M:%S')}
    ok_n = 0

    if engine in ('ocr', 'both'):
        r = ocr_layout(img, key)
        meta['ocr'] = {'ok': r['ok'], 'sec': r.get('sec'), 'usage': r.get('usage'),
                       'boxes': len(r.get('boxes') or []), 'err': r.get('err')}
        if r['ok']:
            ok_n += 1
            open(os.path.join(base, stem + '.ocr.md'), 'w', encoding='utf-8').write(r['md'])
            json.dump({'boxes': r['boxes'], 'usage': r.get('usage'), 'pages': r.get('pages')},
                      open(os.path.join(base, stem + '.ocr.json'), 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=1)
            print('  ✅ glm-ocr   %.1fs  %s tokens  %d 框  → %s.ocr.md'
                  % (r['sec'], (r.get('usage') or {}).get('total_tokens', '?'),
                     len(r['boxes']), stem))
        else:
            print('  ❌ glm-ocr   %s' % r['err'][:110])

    if engine in ('vision', 'both'):
        r = vision_extract(img, key)
        meta['vision'] = {'ok': r['ok'], 'sec': r.get('sec'), 'usage': r.get('usage'),
                          'err': r.get('err')}
        if r['ok']:
            ok_n += 1
            open(os.path.join(base, stem + '.vision.txt'), 'w', encoding='utf-8').write(r['text'])
            print('  ✅ glm-4.6v  %.1fs  %s tokens  %d 字  → %s.vision.txt'
                  % (r['sec'], (r.get('usage') or {}).get('total_tokens', '?'),
                     len(r['text']), stem))
        else:
            print('  ❌ glm-4.6v  %s' % r['err'][:110])

    meta['ok_count'] = ok_n
    json.dump(meta, open(os.path.join(base, stem + '.meta.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    return ok_n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--img', help='单张图片路径')
    ap.add_argument('--dir', help='批量：图片目录')
    ap.add_argument('--engine', default='both', choices=['ocr', 'vision', 'both'])
    ap.add_argument('--out', default='data/tmp/ocr_out')
    a = ap.parse_args()

    key, src = load_key()
    if not key:
        print('❌ 无智谱 key（env ZHIPU_API_KEY 或 data/tmp/api_keys.json["zhipu"]）')
        return 2
    print('🔑 key 来源: %s' % src)

    if a.img:
        imgs = [a.img]
    elif a.dir:
        imgs = sorted(os.path.join(a.dir, f) for f in os.listdir(a.dir)
                      if f.lower().endswith(IMG_EXT))
    else:
        ap.print_help()
        return 2

    print('📷 %d 张 · 引擎 %s · 输出 %s\n' % (len(imgs), a.engine, a.out))
    tot = 0
    for i, im in enumerate(imgs, 1):
        print('[%d/%d] %s' % (i, len(imgs), os.path.basename(im)))
        tot += process(im, key, a.engine, a.out)
    print('\n完成: 成功引擎调用 %d 次' % tot)
    return 0 if tot else 2


if __name__ == '__main__':
    sys.exit(main())
