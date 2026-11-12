# -*- coding: utf-8 -*-
"""🔴 一条命令：竞彩赔率截图（可多张）→ 标准竞彩 txt（直接喂 calc_all / pipeline）

    python data/tmp/image2txt.py 图1.png 图2.png 图3.png [--league 英超] [--teams "主,客"]

🔴 设计思路（2026-11-01 用户指正后改为「先定槽、再填空」）：
  不是「OCR 输出什么就拼什么」，而是**先按模型需要的标准 txt 模板列出所有槽**，
  再拿 OCR 结果逐槽填 —— 填不上就明确标「（三态：原因）」，绝不悄悄丢字段。
  槽清单见 ocr2std.STD_SLOTS（与 txt_normalize 的 11 个节对齐）。

自动分流:
  · 赔率表（规整 HTML table）→ glm-ocr（走 OCR 资源包·不扣现金·0.8-2s）
  · 赛事信息页（图形+条形图）→ glm-ocr 只出 36 tokens → **自动回退 glm-4.6v**
    （PROMPT_EVENT 按槽位反推：队名/联赛/场次编号/开赛时间/特征分析 6 行）
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import img2txt as I2T
import ocr2std as O2S


def _vision_parse(text):
    """从 glm-4.6v 输出提取 match + features（结构化 JSON 优先，正则兜底）"""
    m = re.search(r'\{[\s\S]*\}', text)
    d = None
    if m:
        try:
            d = json.loads(m.group(0))
        except Exception:
            d = None
    out = {}
    if d:
        mt = d.get('match') or {}
        if mt.get('home') and mt.get('away'):
            out['match'] = (mt['home'], mt['away'])
        for k in ('league', 'kickoff', 'code', 'round'):
            if mt.get(k):
                out[k] = mt[k]
        ft = d.get('features') or {}
        if ft:
            out['features'] = ft
    if not out.get('match'):
        mm = re.search(r'(\S{2,12})\s*\n\s*VS\s*\n\s*(\S{2,12})', text)
        if mm:
            out['match'] = (mm.group(1), mm.group(2))
    return out


def _vmatch_empty(vt):
    """🔴V3.5.91 新增（2026-11-03 case320 实证）: glm-4.6v 返回空壳判定

    根因: glm-4.6v 的 PROMPT_EVENT 是**赛事页专用**（提取 match/features），
    对「赔率表格图」完全无效 → 返回 match/features 全空壳（393B）
    而旧实现只看 size>20 → 空壳被当有效缓存复用 → 比分永远 0 条。
    """
    if not vt or len(vt.strip()) < 10:
        return True
    try:
        s = vt[vt.find('{'):vt.rfind('}') + 1]
        import json as _j
        d = _j.loads(s)
    except Exception:
        return False  # 非 JSON（可能是纯文本赛事页·正常）→ 不判空

    def _empty(o):
        if isinstance(o, dict):
            return all(_empty(v) for v in o.values())
        if isinstance(o, list):
            return all(_empty(v) for v in o)
        return not str(o if o is not None else '').strip()

    m = d.get('match') or {}
    f = d.get('features') or {}
    return _empty(m) and _empty(f)


def _is_table_img(img):
    """宽表特征：宽高比 > 1.6 且宽 > 800px → 赔率表格图（应走 glm-ocr，禁转 vision）"""
    try:
        import struct
        with open(img, 'rb') as fh:
            head = fh.read(33)
        if head[:8] != b'\x89PNG\r\n\x1a\n':
            return False
        w, h = struct.unpack('>II', head[16:24])
        return w > 800 and (w / max(h, 1)) > 1.6
    except Exception:
        return False


def ocr_one(img, key, outdir, force=False, deadline=None):
    """→ (markdown, extra)。extra = 赛事页 glm-4.6v 兜底提取的 match/features"""
    stem = os.path.splitext(os.path.basename(img))[0]
    base = os.path.join(ROOT, outdir)
    os.makedirs(base, exist_ok=True)
    md_p = os.path.join(base, stem + '.ocr.md')
    meta_p = os.path.join(base, stem + '.ocr.json')
    vp = os.path.join(base, stem + '.vision.txt')

    def _toks():
        try:
            return (json.load(open(meta_p, encoding='utf-8')).get('usage') or {}).get('total_tokens', 0)
        except Exception:
            return 0

    if os.path.exists(md_p) and not force and os.path.getsize(md_p) > 20:
        md, toks = open(md_p, encoding='utf-8').read(), _toks()
        print('   ↩️ 复用 glm-ocr: %s tokens' % toks)
    else:
        # 🔴V3.5.91 修（2026-11-03 实证·识图根因）: 原 timeout=15 硬编码
        #   比分表 120 档 × 3 时点，15 秒做不完 → glm-ocr 必超时
        #   → 转 glm-4.6v（不认表格）→ 空壳 → 比分 0 条
        #   实测同一张图 --force 重跑即可成功（15s 是边界）→ 按文件大小给足时间
        try:
            _sz = os.path.getsize(img)
        except Exception:
            _sz = 0
        _to = 90 if _sz > 200_000 else (60 if _sz > 80_000 else 40)
        r = I2T.ocr_layout(img, key, timeout=_to, deadline=deadline)
        # 🔴V3.5.91 修（A2）: 表格图 glm-ocr 失败 → **重试一次更长 timeout**
        #   禁转 glm-4.6v（那是赛事页专用·不认表格 → 空壳）
        if not r['ok'] and _is_table_img(img):
            print('   🔁 表格图 glm-ocr 失败 → 重试（timeout %ds → 150s·禁转 vision）' % _to)
            r = I2T.ocr_layout(img, key, timeout=150, deadline=deadline)
        if not r['ok']:
            print('   ❌ glm-ocr 失败: %s' % str(r.get('err'))[:140])
            # 🔴2026-11-02 修：失败时**回退读旧缓存**。
            #   实测 --force 时第 3 张 glm-ocr 超时 → 原实现 md='' → 该张「胜平负 5 时点」
            #   全部丢失（而旧缓存本来是好的）→ force 重跑比不跑更差。
            if os.path.exists(md_p) and os.path.getsize(md_p) > 20:
                md, toks = open(md_p, encoding='utf-8').read(), _toks()
                print('   ↩️ 回退复用旧 OCR 缓存（%s tokens）' % toks)
            else:
                md, toks = '', 0
        else:
            md, toks = r['md'], (r.get('usage') or {}).get('total_tokens', 0)
            open(md_p, 'w', encoding='utf-8').write(md)
            json.dump({'boxes': r['boxes'], 'usage': r.get('usage'), 'pages': r.get('pages')},
                      open(meta_p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            print('   ✅ glm-ocr %.1fs · %s tokens · %d 框' % (r['sec'], toks, len(r['boxes'])))

    # 质量判断：有表格且 tokens 够 → 赔率表，走 glm-ocr 结果即可
    if '<table' in (md or '') and toks >= 200:
        return md, {}

    # 否则视为「赛事信息/非表格页」→ glm-4.6v 兜底（用按槽位定制的 PROMPT_EVENT）
    # 🔴 复用前必须检查**非空** —— 曾出现 0 字节 vision.txt 被复用 → 队名/特征分析全丢
    #    （2026-11-01 实测：科莫场被识别成「主队 VS 客队」·缺失槽=赛事行）
    _vt_cached = None
    if os.path.exists(vp) and os.path.getsize(vp) > 20 and not force:
        _vtmp = open(vp, encoding='utf-8').read()
        # 🔴V3.5.91 修（A4）: 复用前校验**内容**（不只看字节数）→ 空壳视为无缓存
        if _vmatch_empty(_vtmp):
            print('   🔴 旧 glm-4.6v 缓存是空壳（match/features 全空）→ 视为无缓存·重识别')
        else:
            _vt_cached = _vtmp
            print('   ↩️ 复用 glm-4.6v 结果（%d 字）' % len(_vtmp))
    if _vt_cached is not None:
        vt = _vt_cached
    else:
        print('   ⚠️ glm-ocr 信息量过低（%s tokens·无表格）→ 回退 glm-4.6v' % toks)
        v = I2T.vision_extract(img, key, prompt=I2T.PROMPT_EVENT, deadline=deadline)
        if not v['ok']:
            print('   ❌ glm-4.6v 失败: %s' % str(v.get('err'))[:120])
            return md, {}
        vt = v['text']
        # 🔴V3.5.91 修（A3·2026-11-03 实证）: 空壳不落盘
        #   原实现无条件写 vp → 393B 空壳（match/features 全空）被 size>20 判为有效
        #   → 下次复用 → 该图信息永久丢失（case320 比分 0 条的直接原因）
        if _vmatch_empty(vt):
            print('   🔴 glm-4.6v 返回空壳（match/features 全空）→ 不写缓存（防污染后续复用）')
            if _is_table_img(img):
                print('   🔴 且该图是表格图 → glm-4.6v 本就不适用（应走 glm-ocr）')
        else:
            open(vp, 'w', encoding='utf-8').write(vt)
            print('   ✅ glm-4.6v %.1fs · %s tokens'
                  % (v['sec'], (v.get('usage') or {}).get('total_tokens', '?')))
    return (md or '') + '\n\n<!-- ==== glm-4.6v 兜底 ==== -->\n' + vt, _vision_parse(vt)


def merge(od_list, extras):
    """多图合并：同玩法取时点最多者；赛事信息取任一有值的"""
    out = {'match': None, 'league': None, 'kickoff': None, 'code': None, 'round': None,
           'features': None, 'handi_line': None,
           'spf': [], 'handi': [], 'bqc': [], 'goals': [], 'score': []}
    for o in list(od_list) + list(extras):
        if not o:
            continue
        for k in ('match', 'league', 'kickoff', 'code', 'round', 'features'):
            if not out[k] and o.get(k):
                out[k] = o[k]
        if out['handi_line'] is None and o.get('handi_line') is not None:
            out['handi_line'] = o['handi_line']
        for k in ('spf', 'handi', 'bqc', 'goals', 'score'):
            if len(o.get(k) or []) > len(out[k]):
                out[k] = o[k]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('imgs', nargs='*')
    ap.add_argument('--dir')
    ap.add_argument('--league', default=None)
    ap.add_argument('--teams', default=None)
    ap.add_argument('--kickoff', default=None)
    ap.add_argument('--out', default='data/tmp/ocr_out')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--deadline', type=float, default=300,
                    help='整批 OCR 总时限秒（默认 300）—— 防单张卡死拖垮整批')
    a = ap.parse_args()

    imgs = list(a.imgs)
    if a.dir:
        for f in sorted(os.listdir(a.dir)):
            if f.lower().endswith(I2T.IMG_EXT):
                imgs.append(os.path.join(a.dir, f))
    if not imgs:
        ap.print_help()
        return 2

    key, src = I2T.load_key()
    if not key:
        print('❌ 无智谱 key')
        return 2
    print('🔑 %s ｜ %d 张图 ｜ 总时限 %.0fs（代理优先→直连回退）\n'
          % (src, len(imgs), a.deadline))
    T_DEADLINE = time.time() + a.deadline

    # 🔴2026-11-01 修（用户问「为什么识图会混淆·需不需要每场隔离」→ 必须隔离）：
    #   根因（实跑复现）：`merge()` 赛事信息取**第一个有值的**、赔率取**时点最多的**
    #     → 7 张图（埃尔切3 + 毕尔巴鄂4）一起喂时：
    #        赛事行 = 埃尔切（第 1 个）  比分数据 = 毕尔巴鄂（93 条 > 31 条）
    #     → 生成的「埃尔切 txt」里其实是毕尔巴鄂的比分 = **跨场污染**
    #   修法：按 `extra['match']`（主客队）**分组**，每组独立 merge → 独立输出
    odds_list, extras = [], []
    _groups = {}          # {(主,客): {'odds': [], 'extras': [], 'imgs': []}}
    _nomatch = []         # 无赛事信息的图（赔率页）→ 归属**当前组**
    _cur = None           # 当前组 key（图片按上传顺序，赔率页紧跟其赛事页）
    for i, im in enumerate(imgs, 1):
        print('[%d/%d] %s' % (i, len(imgs), os.path.basename(im)))
        _t_img = time.time()
        md, extra = ocr_one(im, key, a.out, a.force, deadline=T_DEADLINE)
        print('   ⏱ 本张 %.1fs ｜ 通道=%s ｜ 剩余 %.0fs'
              % (time.time() - _t_img, I2T.LAST_CHANNEL.get('name'),
                 max(0.0, T_DEADLINE - time.time())))
        if not md:
            continue
        o = O2S.parse_odds(md)
        got = [k for k in ('spf', 'handi', 'bqc', 'goals', 'score') if o.get(k)]
        if got:
            print('   → 玩法: %s ｜ 胜平负 %d 时点 ｜ 比分 %d 条'
                  % (','.join(got), len(o['spf']), len(o['score'])))
        # ── 定组 ──
        _mk = None
        if extra and extra.get('match'):
            _mk = tuple(extra['match'])
            _cur = _mk
        elif _cur:
            _mk = _cur          # 赔率页 → 归当前组
        _g = _groups.setdefault(_mk, {'odds': [], 'extras': [], 'imgs': []})
        _g['imgs'].append(os.path.basename(im))
        if got:
            _g['odds'].append(o)
        if extra:
            if extra.get('match'):
                print('   🎯 %s VS %s%s'
                      % (extra['match'][0], extra['match'][1],
                         ' ｜ %s' % extra['kickoff'] if extra.get('kickoff') else ''))
            if extra.get('features'):
                print('   📊 特征分析: %d 项' % len(extra['features']))
            _g['extras'].append(extra)
        odds_list.append(o) if got else None
        if extra:
            extras.append(extra)

    # ── 多场检测（🔴隔离核心）──
    _real = [k for k in _groups if k]
    # 🔴🔴2026-11-02 修「赔率全丢」：截图顺序常是「赔率页在前、赛事页在后」，
    #   中间/开头的赔率页没有赛事信息 → 归到 _groups[None]；而下面的输出循环
    #   只遍历 `_real`（有赛事信息的组）→ **赔率页被整组丢弃** → 生成的 txt 里
    #   五个玩法全标「截图未含」（实测本批：胜平负 5 时点/比分 124 条全丢）。
    # 修法：全批只有 **1 场**时，把 None 组并入该场（单一赛事不可能跨场污染）；
    #       有 ≥2 场时不并（无法确定归属）→ 保留原有「拒绝输出」门禁。
    _orphan = _groups.get(None)
    if len(_real) == 1 and _orphan:
        _t = _groups[_real[0]]
        _t['odds'] = _orphan['odds'] + _t['odds']
        _t['extras'] = _orphan['extras'] + _t['extras']
        _t['imgs'] = _orphan['imgs'] + _t['imgs']
        print('   🔗 赔率页无赛事信息（%d 张）→ 全批仅 1 场，已并入【%s VS %s】'
              % (len(_orphan['imgs']), _real[0][0], _real[0][1]))
    elif _orphan and len(_real) > 1:
        print('   ⚠️ 有 %d 张赔率页无法归属（本批多场）→ 不并入，请按场分批'
              % len(_orphan['imgs']))
    if len(_real) > 1:
        print('\n' + '=' * 78)
        print('🔴🔴 检测到 **%d 场不同赛事** 混在同一批图里 → 已自动按场隔离' % len(_real))
        for _k in _real:
            print('   【%s VS %s】%d 张图' % (_k[0], _k[1], len(_groups[_k]['imgs'])))
        print('   ⚠️ 若不隔离会怎样（已实测）：赛事行取第 1 场、赔率取时点最多的那场'
              ' → 生成「A 场 txt」里混着 B 场数据')
        print('=' * 78)

    # ── 按组独立输出 ──
    _outputs = []
    for _k in (_real if _real else [None]):
        _g = _groups.get(_k) or {'odds': [], 'extras': [], 'imgs': []}
        _o = merge(_g['odds'], _g['extras'])
        if _k:
            _o['match'] = _k
        _outputs.append((_k, _o, _g['imgs']))

    # 兼容原逻辑：单场时直接走下面；多场时循环输出
    # ── 🔴多场门禁（2026-11-01 · 用户问「为什么混淆·需不需要每场隔离」→ 必须）──
    #   原行为：7 张图（2 场）全喂 merge → 赛事行取第 1 场、赔率取时点最多的那场
    #          → 「A 场 txt」里混着 B 场比分 = **跨场污染**
    #          实证：埃尔切 txt 混进毕尔巴鄂 93 条比分（埃尔切只有 31 条）
    #   🔴为何不能靠「顺序」推断归属：截图顺序是「赔率页在前、赛事页在后」
    #      → 实测埃尔切 4 张 vs 毕尔巴鄂 1 张（错），因为中间 3 张赔率页无法归属
    #   → **正确做法：多场 → 直接拒绝输出（rc=2），强制按批分开跑**
    _multi = [x for x in _outputs if x[0]]
    if len(_multi) > 1:
        print('\n' + '🔴' * 40)
        print('🔴 **拒绝处理**：本批含 %d 场不同赛事 —— 混在一起会跨场污染' % len(_multi))
        for _i, (_k, _oo, _ii) in enumerate(_multi, 1):
            print('   %d) 【%s VS %s】（该组识别到 %d 张图）' % (_i, _k[0], _k[1], len(_ii)))
        print()
        print('   🔴 实测过的污染方式：赛事行取第 1 场 · 赔率取「时点最多的那场」')
        print('      → 生成「A 场 txt」里其实是 B 场的比分（今晚埃尔切被毕尔巴鄂污染）')
        print()
        print('   ✅ 正确做法（一场一批）：')
        print('      python data/tmp/latest_images.py --list          # 看有哪几批')
        print('      python data/tmp/latest_images.py --n 2           # 取最近 2 批（各自独立）')
        print('      python data/tmp/image2txt.py <某一批的图> ...     # 一次只跑一批')
        print('🔴' * 40)
        return 2      # 非零退出 → pipeline / 脚本链上游能感知

    o = _multi[0][1] if _multi else _outputs[0][1]
    _used_imgs = _multi[0][2] if _multi else [os.path.basename(x) for x in imgs]
    if a.teams and ',' in a.teams:
        o['match'] = tuple(x.strip() for x in a.teams.split(',', 1))
    if a.league:
        o['league'] = a.league
    if a.kickoff:
        o['kickoff'] = a.kickoff

    print('\n=== 槽位填充情况 ===')
    # 🔴 2026-11-01 用户指正「你的时间模块又没生效」：识别出开赛时间后必须**立即**判状态。
    #    否则会出现「19:30 开赛、20:15 才分析」却毫无提示的情况（第二次同类漏接）。
    ko = o.get('kickoff')
    if ko:
        try:
            import time_guard as _TG
            _st = _TG.match_state(ko)
            _s = _st.get('state')
            if _s == '已结束':
                print('  🔴🔴 比赛状态: %s —— 赛前盘已不可得（1xbet 只剩滚球·会被防护拦截）' % _st.get('note'))
                print('     ⚠️ 此时只能做「事后复盘」；方向/锚分析已失去时效意义')
            elif _s == '进行中':
                print('  🔴🔴 比赛状态: %s —— **已过赛前窗口**' % _st.get('note'))
                print('     ⚠️ 赛前分析已失效；欧盘赛前盘拉不到（滚球防护）·只能作过程观察')
            else:
                print('  ✅ 比赛状态: %s' % _st.get('note'))
        except Exception as _e:
            print('  ⚪ 时间判定不可用（三态）: %s' % str(_e)[:60])

    txt, fill = O2S.to_std_txt(o, time.strftime('%Y-%m-%d %H:%M:%S'))
    for slot, state, detail in fill:
        mark = {'ok': '✅', 'tri': '⚪', 'miss': '🔴'}.get(state, '?')
        print('  %s %-14s %s' % (mark, slot, detail))

    # 🔴2026-11-01 文件名改用「**队名 + 日期**」（原用 imgs[0] 时间戳）：
    #   时间戳命名有两个问题：①同一批图跑不同场会**互相覆盖**（埃尔切 txt 被毕尔巴鄂覆盖过）
    #                        ②看不出是哪场，审计时必须打开文件才知道
    _m = o.get('match') or ()
    if len(_m) >= 2:
        _safe = lambda s: re.sub(r'[\\/:*?"<>|\s]+', '', str(s))[:18]
        stem = '%s_vs_%s_%s' % (_safe(_m[0]), _safe(_m[1]),
                                time.strftime('%Y%m%d_%H%M'))
    else:
        stem = os.path.splitext(os.path.basename(_used_imgs[0]))[0].rsplit('-', 1)[0] + '_merged'
    out_p = os.path.join(ROOT, a.out, stem + '.std.txt')
    open(out_p, 'w', encoding='utf-8').write(txt)
    # 🔴 落 meta.json —— pipeline 直接吃图片时用它回填 teams/league/kickoff
    meta_p = os.path.join(ROOT, a.out, stem + '.meta.json')
    json.dump({'match': o.get('match'), 'league': o.get('league'),
               'kickoff': o.get('kickoff'), 'code': o.get('code'),
               'round': o.get('round'), 'features': o.get('features'),
               'handi_line': o.get('handi_line'),
               'fill': [{'slot': s, 'state': st, 'detail': d} for s, st, d in fill],
               'src_imgs': list(_used_imgs)},
              open(meta_p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n标准 txt: %s' % os.path.relpath(out_p, ROOT))

    print('\n=== txt_normalize 校验 ===')
    p = subprocess.run([sys.executable, os.path.join(HERE, 'txt_normalize.py'), out_p],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    o2 = (p.stdout or '') + (p.stderr or '')
    for line in o2.splitlines():
        if any(x in line for x in ('✅', '❌', '⚠️')):
            print('  ' + line.strip())
    ok = '❌' not in o2
    miss = [s for s, st, _ in fill if st == 'miss']
    if miss:
        print('\n🔴 缺失槽（模型需要但没填上）: %s' % ', '.join(miss))
    print('\n' + '=' * 60)
    if ok:
        print('✅ 可直接喂模型：')
        print('   python data/tmp/calc_all.py %s %s --net --eu 主,平,客 --handi X --o25 X'
              % (os.path.relpath(out_p, ROOT), a.league or 'seriea'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
