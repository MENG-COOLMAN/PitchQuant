# -*- coding: utf-8 -*-
"""OCR 结果 → 标准竞彩 txt（供 txt_normalize / calc_all / pipeline 直接消费）

输入: glm-ocr 的 markdown（通常含 HTML table）
输出: 标准竞彩模板 txt

🔴 2026-11-01 三次实测修出来的真问题（真实竞彩赔率变化页）:
  ① 赔率带涨跌箭头（1.82↓ / 3.50↑）→ 必须剥离，否则 _nums/PAIR 匹配不到
  ② 比分表是「标签行 / 数值行」交替（标签与赔率不在同一 cell）→ 必须按行收集再 zip
  ③ 比分跨时点（每时点 6 行：主胜表头+数据 / 平表头+数据 / 负表头+数据）→ 按时点分组
  ④ 各玩法时点数不同（胜平负 6 / 总进球 4 / 比分 2）→ 每节独立时点，不强行对齐

用法:
  python data/tmp/ocr2std.py --md <xxx.ocr.md> [--league 意甲] [--time "..."]
"""
import argparse
import io
import json
import os
import re
import sys
from datetime import datetime
from html.parser import HTMLParser

sys.stdout.reconfigure(encoding='utf-8')

TIME_RE = re.compile(r'(\d{4}-\d{2}-\d{2}\s+)?\d{1,2}:\d{2}(:\d{2})?')
NUM = re.compile(r'^\d+\.?\d*$')
SCORE_LAB = re.compile(r'^\d+:\d+$|^[胜负平]其它$')
ARROW = re.compile(r'[↑↓▲▼]')


# ───────────────────── HTML 表格 → 行 ─────────────────────
class _Grid(HTMLParser):
    """🔴 colspan 不展开（展开会让同一赔率重复 cs 次）；'<br>' 转空格；'↑↓' 剥离"""

    def __init__(self):
        super().__init__()
        self.rows, self.cur, self.buf = [], None, None
        self.rs = self.cs = 1

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == 'tr':
            self.cur = []
        elif tag in ('td', 'th'):
            self.buf = []
            try:
                self.rs = int(d.get('rowspan') or 1)
                self.cs = int(d.get('colspan') or 1)
            except ValueError:
                self.rs = self.cs = 1
        elif tag == 'br' and self.buf is not None:
            self.buf.append(' ')

    def handle_data(self, data):
        if self.buf is not None:
            self.buf.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cur is not None and self.buf is not None:
            txt = ARROW.sub('', ''.join(self.buf))
            self.cur.append((re.sub(r'\s+', ' ', txt).strip(), self.rs, self.cs))
            self.buf = None
        elif tag == 'tr' and self.cur is not None:
            self.rows.append(self.cur)
            self.cur = None


def build_rows(md):
    g = _Grid()
    g.feed(md)
    return g.rows


def _infer_mode(mode, rows, title=''):
    """表头/标题兜底推断玩法（P40·2026-11-02）
    mode 已由标题命中 → 原样返回；否则按**首行表头内容**推断，防「标题格式变了整段丢失」。
    """
    if mode:
        return mode
    head = ''
    for r in (rows or [])[:3]:
        head += ' ' + ' '.join((c[0] or '') for c in r)
    head = re.sub(r'\s+', ' ', head)
    if ('胜其它' in head) or ('平其它' in head) or ('负其它' in head) \
            or len(re.findall(r'\d+\s*:\s*\d+', head)) >= 5:
        return '比分'
    if '胜胜' in head or '平平' in head:
        return '半全场'
    if ('0球' in head) or ('7+球' in head) or ('7+' in head and '球' in head):
        return '总进球'
    if '让球' in (title or '') or '让球' in head:
        return '让球'
    if ('胜' in head) and ('平' in head) and ('负' in head):
        return '胜平负'
    return None


def build_sections(md):
    """🔴 按 markdown 标题切分玩法 —— 真实竞彩截图里玩法名在 `## 胜平负固定奖金` 标题中，
    不在表格 cell 里（只找 cell 会全部 mode=None → 0/5 全空，2026-11-01 实测踩坑）。
    返回 [(mode_hint, rows), ...]；无标题时回退整篇（兼容单表 + cell 标签的老格式）。
    """
    # 🔴2026-11-02 P40：glm-ocr 对部分图输出 **HTML 居中标题**（`<div align="center">比分固定奖金</div>`）
    #   而非 markdown `## 比分固定奖金` → 原正则只认 `^#{1,3}` → 直接回退 mode=None
    #   → 比分段被当普通玩法 → scores 恒空（拉科场实测：3 时点 × 31 档全丢）
    md = re.sub(r'(?is)<div[^>]*>\s*([^<>]{1,40}?)\s*</div>',
                lambda m: '\n## ' + re.sub(r'<[^>]+>', '', m.group(1)).strip() + '\n', md)

    parts = re.split(r'(?m)^#{1,3}\s*(.+?)\s*$', md)
    if len(parts) < 3:
        return [(_infer_mode(None, build_rows(md)), build_rows(md))]
    secs = []
    for i in range(1, len(parts) - 1, 2):
        title, body = parts[i], parts[i + 1]
        mode = None
        # 🔴 长词优先：「让球胜平负」「半全场胜平负」都含「胜平负」，若把「胜平负」放前面
        #    会被抢先匹配 → 让球/半全场两节全被当成胜平负（2026-11-01 实测：spf 12 让球 0）
        for k in ('让球', '半全场', '总进球', '比分', '胜平负'):
            if k in title:
                mode = k
                break
        rows = build_rows(body)
        if rows:
            secs.append((_infer_mode(mode, rows, title), rows))
    return secs or [(_infer_mode(None, build_rows(md)), build_rows(md))]


def _nums(cells):
    """同行赔率。兼容 '0 15.00' / '胜胜 2.10'；拒绝时间戳"""
    out = []
    for c in cells:
        c = ARROW.sub('', (c or '')).strip()
        if not c or TIME_RE.fullmatch(c):
            continue
        if NUM.match(c):
            out.append(float(c))
            continue
        if TIME_RE.search(c) and len(c) <= 24 and not re.search(r'\s\d+\.\d+$', c):
            continue
        m = re.search(r'(?<![\d.])(\d+\.?\d*)$', c)
        if m and NUM.match(m.group(1)):
            out.append(float(m.group(1)))
    return out


PAIR = re.compile(r'^(\d+:\d+|[^\s:]{1,5})\s+([\d.]+)$')


def _pairs(cells):
    out = []
    for c in cells:
        m = PAIR.match(ARROW.sub('', (c or '')).strip())
        if m:
            try:
                out.append((m.group(1), float(m.group(2))))
            except ValueError:
                pass
    return out


def _time_of(cell):
    c = (cell or '').strip()
    m = TIME_RE.search(c)
    return c if (m and len(c) <= 24) else ''


def parse_odds(md):
    o = {'match': None, 'league': None, 'handi_line': None,
         'spf': [], 'handi': [], 'bqc': [], 'goals': [], 'score': [],
         '_score_groups': []}

    t = re.sub(r'<[^>]+>', ' ', md)
    NM = r'[\u4e00-\u9fa5A-Za-z0-9·\.\-]{2,20}'
    for pat in (r'(' + NM + r')\s*[（(]\s*主\s*[)）]\s*V\.?S\.?\s*(' + NM + r')\s*[（(]\s*客\s*[)）]',
                r'(' + NM + r')\s+VS\s+(' + NM + r')',
                r'(' + NM + r')\s+vs\.?\s+(' + NM + r')'):
        m = re.search(pat, t, re.I)
        if m:
            o['match'] = (m.group(1).strip(), m.group(2).strip())
            break

    for mode_hint, rows in build_sections(md):
        mode = mode_hint
        for row in rows:
            if not row:
                continue
            cells = [c[0] for c in row]
            label = ARROW.sub('', (cells[0] or '')).strip()

            if label in ('胜平负', '让球', '比分', '总进球', '半全场'):
                mode = label
                data = cells[1:]
            else:
                data = cells

            joined = ' '.join(cells)
            # 🔴 让球值提取必须放在「表头跳过」之前 —— 「让球-1彩果:」恰好就在表头行里，
            #    若先 continue 会永久丢失让球盘口（2026-11-01 实测：让球 -1 变成 +0）
            mh = re.search(r'让球胜平负\s*[（(]\s*主队\s*([+-]?\d+(?:\.\d+)?)\s*[)）]', joined)
            if mh:
                o['handi_line'] = float(mh.group(1))
            mh2 = re.search(r'让球胜平负\s*[（(]\s*客队\s*([+-]?\d+(?:\.\d+)?)\s*[)）]', joined)
            if mh2:
                o['handi_line'] = -float(mh2.group(1))
            mh3 = re.search(r'让球\s*([+-]?\d+(?:\.\d+)?)\s*彩果', joined)
            if mh3 and o['handi_line'] is None:
                o['handi_line'] = float(mh3.group(1))

            # 🔴 表头行：比分表的表头「就是」标签行（发布时间|1:0|2:0|…|胜其它），
            #    必须收集标签，否则丢 13 个主胜标签（2026-11-01 实测 lab=10 val=23）
            if '发布时间' in joined:
                if mode == '比分':
                    labs = [x for x in data if SCORE_LAB.match(ARROW.sub('', x).strip())]
                    if labs:
                        if not o['_score_groups'] or o['_score_groups'][-1]['lab']:
                            o['_score_groups'].append({'t': '', 'lab': [], 'val': []})
                        o['_score_groups'][-1]['lab'].extend(labs)
                continue

            ts = _time_of(label) or (_time_of(data[0]) if data else '')
            if ts and data and _time_of(data[0]) == ts:
                data = data[1:]

            # ── 比分：标签行 / 数值行 交替，按时点分组 ──
            if mode == '比分':
                labs = [x for x in data if SCORE_LAB.match(ARROW.sub('', x).strip())]
                vals = _nums(data)
                if ts:
                    # 表头刚建的组还没填时间 → 用本行时间填充（不新开组）
                    if (o['_score_groups'] and not o['_score_groups'][-1]['t']
                            and o['_score_groups'][-1]['lab']):
                        o['_score_groups'][-1]['t'] = ts
                    else:
                        o['_score_groups'].append({'t': ts, 'lab': [], 'val': []})
                elif not o['_score_groups']:
                    o['_score_groups'].append({'t': '', 'lab': [], 'val': []})
                g = o['_score_groups'][-1]
                if labs:
                    g['lab'].extend(labs)
                elif vals:
                    g['val'].extend(vals)
                continue

            is_header = any(x in data for x in ('主胜', '平', '客胜',
                                                '胜胜', '胜平', '胜负', '平胜', '平平'))
            vals = _nums(data)
            if not vals or is_header:
                continue

            if mode == '胜平负' and len(vals) >= 3:
                o['spf'].append({'t': ts, 'h': vals[0], 'd': vals[1], 'a': vals[2]})
            elif mode == '让球' and len(vals) >= 3:
                o['handi'].append({'t': ts, 'h': vals[0], 'd': vals[1], 'a': vals[2]})
            elif mode == '半全场':
                o['bqc'].append({'t': ts, 'v': vals[:9]})
            elif mode == '总进球':
                o['goals'].append({'t': ts, 'v': vals[:8]})

    # 比分分组 → (label, odds) 列表（取标签与数值的较小长度对齐）
    for g in o['_score_groups']:
        n = min(len(g['lab']), len(g['val']))
        for i in range(n):
            o['score'].append({'t': g['t'], 'lab': g['lab'][i], 'odds': g['val'][i]})
    return o


def _f(v):
    return ('%g' % v) if v is not None else ''


def _clean_form(v):
    """🔴 特征分析去斜杠：OCR 出「2胜/5平/3负」，而 calc_match.parse_features 的正则是
    「数字+胜+数字+平+数字+负」这种紧凑格式 —— **不含斜杠**，原样输出会解析失败（2026-11-01 实测）"""
    return re.sub(r'\s*/\s*', '', str(v or '')).strip()


def _tm(v):
    """🔴 时间戳补空格：比分表时间常被 OCR 粘成「2026-10-3009:35:15」（2026-11-01 实测）"""
    s = str(v or '').strip()
    return re.sub(r'^(\d{4}-\d{2}-\d{2})(\d{2}:)', r'\1 \2', s)


# ───────────── 🔴 标准 txt 槽位清单（与 txt_normalize 的 11 个节对齐）─────────────
# 2026-11-01 用户指正：「先定义模型需要的格式，再把 OCR 结果往里填」——
#   不是 OCR 有什么就拼什么（那样会漏字段而无人察觉）。
#   txt_normalize 认的节: 赛事/时间/特征/胜平负/让球/半全场/总进球/比分
#   calc_match.parse_features 消费【特征分析】→ 修正53 平局信号 S4/S6 唯一数据源
STD_SLOTS = [
    ('赛事行', 'required'),      # 【赛事】<联赛> <主>(主) VS <客>(客)
    ('场次编号', 'nice'),        # 周六026 英超 主(主) VS 客(客)
    ('比赛时间', 'required'),    # 比赛时间：YYYY-MM-DD HH:MM <轮次>
    ('特征分析', 'required'),    # 6 行（近10场交锋/同主客交锋/近10场战况/同主客战况/场均进/失）
    ('胜平负', 'required'),
    ('让球', 'nice'),
    ('半全场', 'nice'),
    ('总进球', 'nice'),
    ('比分', 'nice'),
]

FEAT_ROWS = [
    ('近10场交锋', 'h2h_10'),
    ('同主客交锋', 'h2h_ha'),
    ('近10场战况', 'form_10'),
    ('同主客战况', 'form_ha'),
    ('场均进球', 'gf', '个'),
    ('场均失球', 'ga', '个'),
]


def to_std_txt(o, ts, league=None):
    """→ (txt, fill)  fill = [(槽名, 'ok'|'tri'|'miss', 说明)]

    🔴 返回填充状态，让调用方能明确报「模型需要但没填上」的槽（用户要求「填空」而非「拼凑」）
    """
    fill = []
    home, away = (o.get('match') or (None, None))
    lg = league or o.get('league')
    ko = o.get('kickoff')

    if home and away:
        fill.append(('赛事行', 'ok', '%s VS %s' % (home, away)))
    else:
        fill.append(('赛事行', 'miss', '队名缺失（赛事页未识别且未传 --teams）'))
        home, away = ('主队', '客队')
    if not lg:
        fill.append(('联赛', 'tri', '未识别 → 写「未知联赛」（赛事行仍可用）'))
    lg = lg or '未知联赛'

    L = ['【赛事】%s %s(主) VS %s(客)' % (lg, home, away)]
    code = o.get('code')
    if code:
        L.append('%s %s %s(主) VS %s(客)' % (code, lg, home, away))
        fill.append(('场次编号', 'ok', code))
    else:
        fill.append(('场次编号', 'tri', '截图未含（不影响分析）'))

    if ko:
        L.append('比赛时间：%s%s' % (ko, ' ' + o['round'] if o.get('round') else ''))
        fill.append(('比赛时间', 'ok', ko))
    else:
        L.append('比赛时间：（截图缺·三态）')
        fill.append(('比赛时间', 'tri', '截图未含 → 影响时效判断'))
    L.append('')

    # ── 特征分析（calc_match.parse_features 消费·修正53 S4/S6 数据源）──
    ft = o.get('features') or {}
    got_rows = []
    for row in FEAT_ROWS:
        name, key = row[0], row[1]
        unit = row[2] if len(row) > 2 else ''
        v = ft.get(key) or {}
        hv, av = v.get('home'), v.get('away')
        if hv and av:
            # 🔴 单位必须拼上（基准 txt 是「维拉2.4个」·「个」是口径的一部分）
            got_rows.append('%s：%s%s%s | %s%s%s'
                            % (name, home, _clean_form(hv), unit,
                               away, _clean_form(av), unit))
    if got_rows:
        if code:
            L.append('【特征分析】')
        else:
            L.append('【特征分析】')
        L.extend(got_rows)
        fill.append(('特征分析', 'ok', '%d/6 行' % len(got_rows)))
    else:
        L.append('【特征分析】')
        L.append('（三态：截图未含特征分析 → 修正53 S4/S6 平局信号不可用）')
        fill.append(('特征分析', 'tri', '缺失 → S4 平率/S6 交锋平数 不可用'))
    L.append('')

    def blk(title, head, rows3, slot):
        L.append('【%s】' % title)
        if not rows3:
            L.append('（三态：截图未含%s）' % title)
            fill.append((slot, 'tri', '截图未含'))
        else:
            L.append('发布时间,' + head)
            for r in rows3:
                L.append('%s,%s,%s,%s' % (_tm(r.get('t') or ts), _f(r['h']), _f(r['d']), _f(r['a'])))
            fill.append((slot, 'ok', '%d 时点' % len(rows3)))
        L.append('')

    blk('胜平负固定奖金', '胜,平,负', o.get('spf') or [], '胜平负')
    hl = o.get('handi_line')
    blk('让球胜平负固定奖金｜让球%+g' % (hl if hl is not None else 0), '胜,平,负',
        o.get('handi') or [], '让球')

    def multi(title, head, items, ncol, slot):
        L.append('【%s】' % title)
        rows = [it for it in (items or []) if len(it.get('v') or []) >= ncol]
        if not rows:
            L.append('（三态：截图未含%s）' % title)
            fill.append((slot, 'tri', '截图未含'))
        else:
            L.append('发布时间,' + head)
            for it in rows:
                L.append('%s,%s' % (_tm(it.get('t') or ts),
                                    ','.join(_f(v) for v in it['v'][:ncol])))
            fill.append((slot, 'ok', '%d 时点' % len(rows)))
        L.append('')

    multi('半全场胜平负固定奖金', '胜胜,胜平,胜负,平胜,平平,平负,负胜,负平,负负',
          o.get('bqc'), 9, '半全场')
    multi('总进球固定奖金', '0球,1球,2球,3球,4球,5球,6球,7+球', o.get('goals'), 8, '总进球')

    L.append('【比分固定奖金】')
    sc = o.get('score') or []
    if sc:
        labs = []
        for x in sc:
            if x['lab'] not in labs:
                labs.append(x['lab'])
        L.append('发布时间,' + ','.join(labs))
        tps = []
        for x in sc:
            if x['t'] not in tps:
                tps.append(x['t'])
        for tp in tps:
            row = {x['lab']: x['odds'] for x in sc if x['t'] == tp}
            L.append('%s,%s' % (_tm(tp or ts), ','.join(_f(row.get(l)) for l in labs)))
        fill.append(('比分', 'ok', '%d 时点 × %d 档' % (len(tps), len(labs))))
    else:
        L.append('（三态：截图未含比分）')
        fill.append(('比分', 'tri', '截图未含'))
    return '\n'.join(L) + '\n', fill


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--md', required=True)
    ap.add_argument('--out')
    ap.add_argument('--time')
    ap.add_argument('--league')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    md = io.open(a.md, encoding='utf-8').read()
    ts = a.time or datetime.fromtimestamp(os.path.getmtime(a.md)).strftime('%Y-%m-%d %H:%M:%S')
    o = parse_odds(md)
    txt, fill = to_std_txt(o, ts, league=a.league)
    out = a.out or os.path.splitext(a.md)[0].replace('.ocr', '') + '.std.txt'
    io.open(out, 'w', encoding='utf-8').write(txt)

    n = lambda k: len(o.get(k) or [])
    got = [k for k in ('spf', 'handi', 'bqc', 'goals', 'score') if o.get(k)]
    print('玩法 %d/5: %s' % (len(got), ','.join(got) or '无'))
    print('比赛: %s | 让球: %s' % (' VS '.join(o['match']) if o.get('match') else '❌未识别',
                                  o.get('handi_line') if o.get('handi_line') is not None else '?'))
    print('时点: 胜平负 %d | 让球 %d | 半全场 %d | 总进球 %d | 比分 %d 条'
          % (n('spf'), n('handi'), n('bqc'), n('goals'), n('score')))
    print('输出: %s' % out)
    if n('spf') >= 2:
        print('✅ 多时点 → V1 变动/D1 背离/形态学 可用')
    else:
        print('⚠️ 单时点 → V1/D1/形态学 不可用（须三态标注）')
    if a.json:
        print(json.dumps({'spf': o['spf'][:3], 'n_spf': n('spf'),
                          'handi': o['handi'][:2], 'handi_line': o['handi_line'],
                          'goals': n('goals'), 'bqc': n('bqc'),
                          'score_n': n('score'),
                          'score_head': o['score'][:4]}, ensure_ascii=False, indent=1))
    return 0 if len(got) >= 3 else 1


if __name__ == '__main__':
    sys.exit(main())
