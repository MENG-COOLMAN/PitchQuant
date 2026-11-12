# -*- coding: utf-8 -*-
"""机构数据统一层（2026-09-27 · 用户指令「跨市场分歧 + 多元合并去水 双用途分配」）

🔴 定位: 同一批机构原始赔率 → 输出两个**不同维度**的产物，互不冲突：
  ① **多元合并去水**（聚合）: 每家各自去水 → 按「抽水率倒数」加权 → 单一最优概率 p̂(H/D/A)
     → 消费于 Step5 方向 / 凯利 / 泊松 λ（概率基准）
  ② **跨市场分歧**（离散）: (Max − Median)/Median per outcome → spread% + 等级
     → **只调置信度（±1 档）**，永不反转方向（P0-1 规则·已回测）

🔴 数据源分工（宽窄互补）:
  · 广度（分歧度量）→ the-odds-api（21 家·家数最多）  ★主
  · 合并池（去水）  → the-odds-api（21-32 家）合并去重
  · 锐度锚          → Pinnacle / 1xbet（若在池中·可选加权·⚠️启发式未回测）
  · 兜底            → 竞彩 txt 去水（独立源）

🔴 输入格式（**三种全兼容**·`unwrap_books` 统一解包·2026-09-27 审计修复）:
  A. 裸 list         : [{"bookmaker": "Pinnacle", "h": 1.85, "d": 3.6, "a": 4.2}, ...]
  B. 包装 dict        : {"status":"ok","fixture":"...","home":"X","away":"Y","books":[...]}
  C. the-odds-api 快照: {"snapshots":[{...,"events":[{...,"markets":{"h2h":[...]}}]}]}

🔴 场次错配防护（2026-09-27 审计 P0 修复·实测 case103 读到 fixture 1528863 他场数据）:
  fundflow_books.json 是**全局单文件** → 上场数据残留会污染下场。
  `match_check(obj, argv)` 用 txt 的「主队:X,客队:Y」与 books 的 home/away 比对：
    ok           → 匹配·正常消费
    mismatch     → 🔴 **阻断**（不输出概率·提示重跑）
    unverifiable → 无队名信息（裸 list/旧文件）→ 显示来源并标「⚠️ 未校验」

用法:
  python data/tmp/market_consensus.py --books data/tmp/fundflow_books.json --txt <本场.txt>
  python data/tmp/market_consensus.py --the-odds-json data/tmp/snapshots/x.json --home X --away Y
"""
import argparse
import io
import json
import os
import re
import statistics
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# 锐度名单（⚠️启发式·未回测 → 默认 OFF，仅 --sharp-weighted 时启用）
SHARP_BOOKS = {'pinnacle', 'betfair', 'betfair_ex_eu', 'matchbook', 'smarkets', '1xbet', 'bet365'}


def implied(odds):
    return 1.0 / float(odds)


def devig_book(b):
    """单家去水 → (pH, pD, pA, margin)"""
    ih, id_, ia = implied(b['h']), implied(b['d']), implied(b['a'])
    s = ih + id_ + ia
    return ih / s, id_ / s, ia / s, (s - 1.0)


def unwrap_books(obj):
    """🔴 统一解包（2026-09-27 审计修复·治 P0: 包 dict 直喂致 string indices 崩溃）

    支持 裸 list / fetch_books 包装 dict / the-odds-api 快照；无法识别 → []
    """
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        if isinstance(obj.get('books'), list):
            return obj['books']
        snaps = obj.get('snapshots')
        if isinstance(snaps, list) and snaps:
            for e in ((snaps[-1] or {}).get('events') or []):
                mk = (e.get('markets') or {}).get('h2h') or []
                if mk:
                    out = []
                    for entry in mk:
                        oc = {o.get('name'): o.get('price') for o in (entry.get('outcomes') or [])}
                        out.append({'bookmaker': entry.get('book'), 'h': oc.get(e.get('home')),
                                    'd': oc.get('Draw'), 'a': oc.get(e.get('away'))})
                    return out
    return []


def source_info(obj):
    """包装 dict 的来源元信息（含队名·用于场次错配校验）"""
    if isinstance(obj, dict):
        return {'fixture': obj.get('fixture'), 'home': obj.get('home'), 'away': obj.get('away'),
                'declared': obj.get('n_books'), 'key_source': obj.get('key_source'),
                'status': obj.get('status')}
    return {}


def txt_teams(argv):
    """从命令行 txt 提取本场队名（兼容多格式·🔴2026-09-27 补格式B·case209 实证只认 A 会退化）"""
    for a in argv or []:
        if not str(a).lower().endswith('.txt') or not os.path.exists(a):
            continue
        try:
            s = io.open(a, encoding='utf-8', errors='replace').read()[:4000]
        except Exception:
            continue
        # 格式A: 「主队:塞尔塔,客队:毕尔巴鄂」
        m = re.search(r'主队[:：]\s*(.+?)\s*[,，;；]\s*客队[:：]\s*(.+?)(?:\r?\n|$)', s)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        # 🔴格式B: 「赛事：周六016 欧国联 英格兰(主) VS 西班牙(客)」（case209 实测格式）
        # 🔴2026-11-01 修：原 `[^\s:：()（）,，]+` **排除空格** → 英文队名
        #   `Machida Zelvia` / `V-Varen Nagasaki` 恒失配 → 队名为空 → P10/P8/纵向/R11 连锁失效
        #   （case308/309 实证：三源不齐 + 纵向不启用 + R11 无输出）
        # 🔴2026-11-01 加 【】\n 边界：否则「【赛事】英超 曼城」整串被当队名
        m2 = re.search(r'([^\[\]【】:：()（）,，\n]{2,60}?)\s*[(（]主[)）]\s*'
                       r'(?:VS|vs|Vs|vS|对阵)\s*'
                       r'([^\[\]【】:：()（）,，\n]{2,60}?)\s*[(（]客[)）]', s)
        if m2:
            _h, _a = m2.group(1).strip(), m2.group(2).strip()
            # 去掉可能的联赛前缀（「日职 联 Machida Zelvia」→「Machida Zelvia」）
            _LG_WORDS = ('英超', '西甲', '德甲', '意甲', '法甲', '日职联', '日职 联',
                         '韩职联', '欧联', '欧冠', '英联赛杯', '亚冠精英', '欧国联',
                         '日职', '韩职', '英冠', '苏超', '荷甲', '葡超', '土超',
                         '巴甲', '阿甲', '美职', '日乙', '韩K2')
            for _w in _LG_WORDS:
                if _h.startswith(_w):
                    _h = _h[len(_w):].strip()
                    break
                if _a.startswith(_w):
                    _a = _a[len(_w):].strip()
                    break
            # 兜底：若仍含「X 联 / X 超」等 2-3 字 + 空格 的联赛残留，取最后一个空格后的部分
            #   （仅当剩余部分仍含空格且前缀是 2-3 个中文字时触发）
            for _k in ('_h', '_a'):
                _v = locals()[_k]
                _mm = re.match(r'^([\u4e00-\u9fa5]{1,3})\s+(.+)$', _v or '')
                if _mm and len(_mm.group(2)) >= 3:
                    if _k == '_h':
                        _h = _mm.group(2).strip()
                    else:
                        _a = _mm.group(2).strip()
            if _h and _a:
                return _h, _a
    return None, None


# 🔴 国家队中英映射（2026-09-27 补·局部表·仅服务「场次错配校验」）
#   根因（实测）: data_bridge.normalize_name 用 `[^a-z0-9]` 剔除中文 → 中文名归一为空串；
#     且 TEAM_ALIASES(191 队) / team_name_mapping_2025-26.json 均**无国家队** → 中英永不互认。
#   🔴 不改 data_bridge（被 haf/clubelo/h2h/euro_odds 等源共用）→ 局部表零污染。
NATION_ALIASES = {
    '英格兰': ['england'], '西班牙': ['spain'], '法国': ['france'], '德国': ['germany'],
    '意大利': ['italy'], '葡萄牙': ['portugal'], '荷兰': ['netherlands', 'holland'],
    '比利时': ['belgium'], '克罗地亚': ['croatia'], '瑞士': ['switzerland'],
    '丹麦': ['denmark'], '奥地利': ['austria'], '波兰': ['poland'], '匈牙利': ['hungary'],
    '捷克': ['czechia', 'czech republic'], '苏格兰': ['scotland'], '威尔士': ['wales'],
    '爱尔兰': ['ireland', 'republic of ireland'], '北爱尔兰': ['northern ireland'],
    '挪威': ['norway'], '瑞典': ['sweden'], '芬兰': ['finland'], '冰岛': ['iceland'],
    '乌克兰': ['ukraine'], '土耳其': ['turkey'], '希腊': ['greece'], '塞尔维亚': ['serbia'],
    '斯洛伐克': ['slovakia'], '斯洛文尼亚': ['slovenia'], '罗马尼亚': ['romania'],
    '保加利亚': ['bulgaria'], '卢森堡': ['luxembourg'], '以色列': ['israel'],
    '阿尔巴尼亚': ['albania'], '格鲁吉亚': ['georgia'], '波黑': ['bosnia', 'bosnia and herzegovina'],
    '爱沙尼亚': ['estonia'], '拉脱维亚': ['latvia'], '立陶宛': ['lithuania'],
    '北马其顿': ['north macedonia', 'macedonia'], '白俄罗斯': ['belarus'], '俄罗斯': ['russia'],
    '亚美尼亚': ['armenia'], '哈萨克斯坦': ['kazakhstan'], '黑山': ['montenegro'],
    '摩尔多瓦': ['moldova'], '阿塞拜疆': ['azerbaijan'], '塞浦路斯': ['cyprus'],
    '马耳他': ['malta'], '安道尔': ['andorra'], '法罗群岛': ['faroe islands'],
    '圣马力诺': ['san marino'], '直布罗陀': ['gibraltar'], '列支敦士登': ['liechtenstein'],
    '科索沃': ['kosovo'], '摩洛哥': ['morocco'], '突尼斯': ['tunisia'], '埃及': ['egypt'],
    '阿尔及利亚': ['algeria'], '尼日利亚': ['nigeria'], '美国': ['usa', 'united states'],
    '墨西哥': ['mexico'], '日本': ['japan'], '韩国': ['south korea', 'korea republic'],
    '澳大利亚': ['australia'], '巴西': ['brazil'], '阿根廷': ['argentina'],
    '乌拉圭': ['uruguay'], '哥伦比亚': ['colombia'], '智利': ['chile'], '秘鲁': ['peru'],
    '厄瓜多尔': ['ecuador'], '巴拉圭': ['paraguay'], '加拿大': ['canada'],
}


def _norm_key(s):
    """轻量归一（英文小写去标点·中文剔空后由 _nation_canonical 走原名分支）"""
    return re.sub(r'[^a-z0-9]+', ' ', str(s).lower()).strip()


_NATION_INDEX = {}
for _cn, _ens in NATION_ALIASES.items():
    _NATION_INDEX[_cn] = _cn
    for _e in _ens:
        _k = _norm_key(_e)
        if _k and _k not in _NATION_INDEX:
            _NATION_INDEX[_k] = _cn


def _nation_canonical(name):
    """中文/英文国家队名 → 规范中文名（未登记 → None）"""
    s = str(name).strip()
    if not s:
        return None
    if s in NATION_ALIASES:
        return s
    return _NATION_INDEX.get(_norm_key(s))


def _hit(x, y):
    """队名同一性判定（子串 → 国家队中英映射 → data_bridge 别名归一）

    🔴2026-09-27 修复 P0: 原实现 `if _db.match_team(x,[y])` —— match_team 返回 **(候选, 置信度) 元组**，
      恒非空 → 恒真 → **场次错配防护完全失效**（实测 case103 真错配被放行）。改为解包 + 置信度阈值。
    """
    x, y = str(x).strip(), str(y).strip()
    if not x or not y:
        return False
    # 1. 同语言子串互含
    if x in y or y in x:
        return True
    # 2. 国家队中英互认（局部表·根治 normalize_name 剔中文致中英永不互认）
    nx, ny = _nation_canonical(x), _nation_canonical(y)
    if nx and ny and nx == ny:
        return True
    # 3. 复用 data_bridge 别名表（俱乐部中英·🔴解包元组 + 置信度阈值 ≥0.8）
    #    只信 精确(1.0)/别名索引(0.95)/包含(0.8)；前缀4字符(0.65)过松不采用
    try:
        _olp = os.path.join(os.path.dirname(HERE), 'online_learning')
        if os.path.isdir(_olp) and _olp not in sys.path:
            sys.path.insert(0, _olp)
        import data_bridge as _db
        for a, b in ((x, y), (y, x)):
            cand, conf = _db.match_team(a, [b])
            if cand and conf >= 0.8:
                return True
            kws = _db.cn_to_en_keywords(a)      # 中文名 → 归一化英文关键词
            nb = _db.normalize_name(b)
            if nb and kws and any(k == nb or (len(k) >= 4 and (k in nb or nb in k)) for k in kws):
                return True
    except Exception:
        pass
    # 4. 🔴2026-10-30 补：cn2en_extra 表（**非五大球队唯一来源**·与 snapshot_save.cn2en_list 同源）
    #    实证 case294: books=('Hammarby IF','IK Sirius') vs txt=('哈马比','天狼星')
    #    → 中文名不在 data_bridge.TEAM_ALIASES（只有五大+欧战）→ 第3步恒 False → **误判场次错配**
    #    → 39 家机构被整层拒绝消费。这里补读 extra 表 + 去重音子串匹配。
    try:
        _ex = json.load(io.open(os.path.join(HERE, 'cn2en_extra.json'), encoding='utf-8'))
    except Exception:
        _ex = {}
    if _ex:
        import unicodedata

        def _da(s):
            return ''.join(c for c in unicodedata.normalize('NFKD', str(s))
                           if not unicodedata.combining(c)).lower().strip()

        for a, b in ((x, y), (y, x)):
            for cand in (_ex.get(a) or []):
                ca, cb = _da(cand), _da(b)
                if ca and cb and (ca in cb or cb in ca):
                    return True
    return False


def match_check(obj, argv=None):
    """🔴 场次错配校验（P0·全局单文件防护）→ {'verdict','books_teams','txt_teams'}"""
    info = source_info(obj)
    bh, ba = info.get('home'), info.get('away')
    th, ta = txt_teams(argv if argv is not None else sys.argv[1:])
    if not bh or not ba or str(bh) == 'None' or str(ba) == 'None':
        return {'verdict': 'unverifiable', 'books_teams': None, 'txt_teams': (th, ta),
                'reason': 'books 无队名信息（裸 list / 旧文件）'}
    if not th or not ta:
        return {'verdict': 'unverifiable', 'books_teams': (bh, ba), 'txt_teams': None,
                'reason': 'txt 未提取到队名'}
    ok = (_hit(bh, th) and _hit(ba, ta)) or (_hit(bh, ta) and _hit(ba, th))
    return {'verdict': 'ok' if ok else 'mismatch', 'books_teams': (bh, ba), 'txt_teams': (th, ta)}


def clean_books(books):
    """过滤无效/重复机构（同名取最新一条）；入参自动解包"""
    seen = {}
    for b in unwrap_books(books):
        if not isinstance(b, dict):
            continue
        try:
            h, d, a = float(b['h']), float(b['d']), float(b['a'])
        except (KeyError, TypeError, ValueError):
            continue
        if min(h, d, a) <= 1.01:
            continue
        name = str(b.get('bookmaker') or b.get('book') or 'unknown')
        seen[name] = {'bookmaker': name, 'h': h, 'd': d, 'a': a}
    return list(seen.values())


def merge_devig(books, sharp_weighted=False):
    """① 多元合并去水：抽水率倒数加权（抽水越低=越锐=越可信）"""
    books = unwrap_books(books)
    rows = [devig_book(b) for b in books]
    if not rows:
        return None
    weights = []
    for b, (ph, pd, pa, mg) in zip(books, rows):
        w = 1.0 / max(mg, 1e-4)                 # 抽水倒数
        if sharp_weighted and str(b.get('bookmaker', '')).lower() in SHARP_BOOKS:
            w *= 2.0                            # ⚠️启发式·未回测
        weights.append(w)
    tw = sum(weights)
    ph = sum(r[0] * w for r, w in zip(rows, weights)) / tw
    pd = sum(r[1] * w for r, w in zip(rows, weights)) / tw
    pa = sum(r[2] * w for r, w in zip(rows, weights)) / tw
    margins = [r[3] for r in rows]
    # 等权对照（防加权引入偏差）
    eh = sum(r[0] for r in rows) / len(rows)
    ed = sum(r[1] for r in rows) / len(rows)
    ea = sum(r[2] for r in rows) / len(rows)
    return {
        'n_books': len(rows),
        'pH': round(ph, 4), 'pD': round(pd, 4), 'pA': round(pa, 4),
        'p_equal': [round(eh, 4), round(ed, 4), round(ea, 4)],
        'margin_mean': round(sum(margins) / len(margins), 4),
        'margin_min': round(min(margins), 4), 'margin_max': round(max(margins), 4),
        'sharp_weighted': sharp_weighted,
        'favorite': ['H', 'D', 'A'][max(range(3), key=lambda i: (ph, pd, pa)[i])],
    }


def spread(books):
    """② 跨市场分歧：复用 bookmaker_spread 口径（(Max−Median)/Median）"""
    books = unwrap_books(books)
    try:
        import bookmaker_spread as bs
        return bs.calc_spread_from_books(books)
    except Exception:
        out = {}
        for oc, k in zip(('H', 'D', 'A'), ('h', 'd', 'a')):
            vals = sorted(float(b[k]) for b in books if b.get(k))
            if len(vals) < 3:
                out[oc] = {'status': 'insufficient', 'n': len(vals)}
                continue
            med = statistics.median(vals)
            out[oc] = {'n': len(vals), 'median': round(med, 3), 'spread_pct': round((vals[-1] - med) / med, 4)}
        return out


def from_snapshot(path, home=None, away=None):
    """从 the-odds-api 快照提取某场 books（h2h）"""
    d = json.load(io.open(path, encoding='utf-8'))
    snaps = d.get('snapshots') or []
    if not snaps:
        return []
    evs = snaps[-1].get('events') or []
    for e in evs:
        if home and e.get('home') != home:
            continue
        if away and e.get('away') != away:
            continue
        books = []
        for entry in (e.get('markets', {}).get('h2h') or []):
            oc = {o['name']: o['price'] for o in entry.get('outcomes', [])}
            books.append({'bookmaker': entry.get('book'), 'h': oc.get(e['home']), 'd': oc.get('Draw'), 'a': oc.get(e['away'])})
        return books
    return []


def report(books, title='', sharp_weighted=False):
    info = source_info(books)
    books = clean_books(books)
    if not books:
        print('  ⚠️ 无有效机构数据（格式无法识别或全部无效）')
        return
    md = merge_devig(books, sharp_weighted)
    sp = spread(books)
    print('【%s】机构 %d 家 · 平均抽水 %.2f%% · 锐度加权=%s'
          % (title, md['n_books'], md['margin_mean'] * 100, 'ON' if sharp_weighted else 'OFF'))
    if info.get('fixture') or info.get('home'):
        print('  ⚠️ 来源: fixture=%s %s vs %s（fundflow_books.json 为全局单文件·须确认与本场一致）'
              % (info.get('fixture'), info.get('home') or '?', info.get('away') or '?'))
    print('  ① 多元合并去水（→ 方向/凯利/泊松λ）:')
    print('     概率: 主 %.1f%% | 平 %.1f%% | 客 %.1f%%   （等权对照 主 %.1f/平 %.1f/客 %.1f）'
          % (md['pH'] * 100, md['pD'] * 100, md['pA'] * 100,
             md['p_equal'][0] * 100, md['p_equal'][1] * 100, md['p_equal'][2] * 100))
    print('     热门=%s · 抽水区间 %.2f%%~%.2f%%'
          % ({'H': '主胜', 'D': '平局', 'A': '客胜'}[md['favorite']], md['margin_min'] * 100, md['margin_max'] * 100))
    print('  ② 跨市场分歧（→ 仅调置信度±1档）:')
    for oc, label in (('H', '主'), ('D', '平'), ('A', '客')):
        r = sp.get(oc) or {}
        if r.get('status') == 'insufficient' or 'spread_pct' not in r:
            print('     %s: 机构不足(<3) → 不启用' % label)
        else:
            print('     %s: median %.3f · spread %.2f%% · 等级 %s'
                  % (label, r['median'], r['spread_pct'] * 100, r.get('consensus', '-')))
    # P0-1 消费建议
    spH = (sp.get('H') or {}).get('spread_pct')
    if spH is not None and md['favorite'] == 'H':
        if spH < 0.02 and min(float(b['h']) for b in books) < 1.50:
            print('  🔴 P0-1 建议: 热门侧 spread<2%% 且赔率<1.50 → **置信度 +1 档**（回测 80.0/81.45%）')
        elif spH < 0.02:
            print('  🟡 P0-1 建议: spread<2%% → 置信度 **+0.5 档**（回测 52.7/62.6%）')
        else:
            print('  ⚪ P0-1: spread≥2%% → 仅标注·**不降档**（回测不达 >3pp 门禁）')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--books')
    ap.add_argument('--the-odds-json', dest='snap')
    ap.add_argument('--home')
    ap.add_argument('--away')
    ap.add_argument('--txt', help='本场 txt（用于场次错配校验）')
    ap.add_argument('--sharp-weighted', action='store_true')
    ap.add_argument('--title', default='机构共识层')
    a = ap.parse_args()
    if a.books:
        obj = json.load(io.open(a.books, encoding='utf-8'))
        argv = [a.txt] if a.txt else []
        chk = match_check(obj, argv)
        if chk['verdict'] == 'mismatch':
            print('  🔴 场次错配 → 拒绝消费! books来源=%s vs txt本场=%s'
                  % (chk['books_teams'], chk['txt_teams']))
            print('     请重跑: python data/tmp/fetch_books.py --fixture <本场ID> --home X --away Y')
            return
        if chk['verdict'] == 'unverifiable':
            print('  ⚪ 场次校验: 无法校验（%s）' % chk.get('reason'))
        report(obj, a.title, a.sharp_weighted)
    elif a.snap:
        report(from_snapshot(a.snap, a.home, a.away), '%s %s vs %s' % (a.title, a.home or '', a.away or ''), a.sharp_weighted)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
