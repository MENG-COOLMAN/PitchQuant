# -*- coding: utf-8 -*-
"""raw_features.py —— 从 case-library/raw 文档提取特征（2026-09-12·用户评审长期建议）
raw 结构: 「一、竞彩数据」含 ### 胜平负 / ### 让球-N / ### 半全场 / ### 总进球 / ### 比分
  → 提取末行（临场）赔率 → 补全 A 类(ML/让球/O25) + B 类(半场概率/比分盘/进球分布)
  C/D/E 类(HAF/xG/api/H2H)历史不可得 → None（如实标注·不臆造）

用法:
  python scripts/tmp/raw_features.py --case case100          # 单场提取预览
  python scripts/tmp/raw_features.py --fill-all               # 批量补全案例库
"""
import os, re, sys, io, json, glob, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(DATA, 'online_learning'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import config as C
import txt_features as TF


def _last_row(block):
    """取块内最后一个数据行（| ... | 形式）"""
    rows = [l for l in block.split('\n') if l.strip().startswith('|') and '时间' not in l and '---' not in l]
    return rows[-1] if rows else None


def _nums(line):
    if not line:
        return []
    return [float(x) for x in re.findall(r'\d+\.?\d*', line.replace('↑', '').replace('↓', '').replace('锁死', ''))]


def _block(text, name):
    """取 ### name 到下一个 ###/## 的块"""
    m = re.search(r'###\s*%s[^\n]*\n(.*?)(?=\n###|\n##|\Z)' % re.escape(name), text, re.S)
    return m.group(1) if m else None


def _section(text, name):
    """取 ## name 到下一个 ## 的整节（raw 用 ## 一、竞彩全文 / ## 二、欧盘 等）"""
    m = re.search(r'##\s*[一二三四五六七八九十][、.]?\s*%s(.*?)(?=\n##\s|\Z)' % re.escape(name), text, re.S)
    return m.group(1) if m else None


def _triples(block):
    """块内所有 x.xx y.yy z.zz 三元组（赔率序列）"""
    out = []
    for m in re.finditer(r'(\d\.\d{2})\s*[|/\s,，]\s*(\d\.\d{2})\s*[|/\s,，]\s*(\d\.\d{2})', block or ''):
        try:
            out.append((float(m.group(1)), float(m.group(2)), float(m.group(3))))
        except Exception:
            pass
    return out


def _extract_ml(text):
    """ML 赔率: 优先「二、欧盘」节（Bet365/x1bet 行）·退化到「一、竞彩」三元组"""
    sec2 = _section(text, '欧盘')
    if sec2:
        for ln in sec2.split('\n'):
            if re.search(r'胜平负|1x2|ML|主.*平.*客', ln):
                t = _triples(ln)
                if t:
                    return t[0]
    sec1 = _section(text, '竞彩')
    if sec1:
        # 胜平负表：含"胜平负"行后的第一个数据行
        lines = sec1.split('\n')
        for i, ln in enumerate(lines):
            if '胜平负' in ln:
                for j in range(i + 1, min(i + 6, len(lines))):
                    t = _triples(lines[j])
                    if t:
                        return t[-1]
        t = _triples(sec1)
        if t:
            return t[-1]
    t = _triples(text)
    return t[0] if t else (None, None, None)


def _extract_team_stats(text):
    """从「四、基本面」提取场均进/失（启发式）"""
    sec = _section(text, '基本面') or ''
    m = re.search(r'场均进\s*([\d.]+)\s*(?:vs|VS|/)\s*([\d.]+)\s*[|·]?\s*场均失\s*([\d.]+)\s*(?:vs|VS|/)\s*([\d.]+)', sec)
    if m:
        return {'home_avg_goals': float(m.group(1)), 'away_avg_goals': float(m.group(2)),
                'home_avg_conceded': float(m.group(3)), 'away_avg_conceded': float(m.group(4))}
    m2 = re.search(r'场均进\s*([\d.]+)[^\d]+([\d.]+)[^\d]+场均失\s*([\d.]+)[^\d]+([\d.]+)', sec)
    if m2:
        return {'home_avg_goals': float(m2.group(1)), 'away_avg_goals': float(m2.group(2)),
                'home_avg_conceded': float(m2.group(3)), 'away_avg_conceded': float(m2.group(4))}
    return {}


def extract_from_raw(raw_path):
    """从 raw md 提取 A+B 类特征（2026-09-12 增强版·兼容 raw 多变格式）"""
    try:
        s = open(raw_path, encoding='utf-8').read()
    except Exception:
        return None
    head = s.split('\n')[0]
    league = '?'
    for kw in ('欧冠', '欧联', '欧协联', '英超', '西甲', '意甲', '德甲', '法甲', '英冠', '日职'):
        if kw in head:
            league = kw
            break
    oh, od, oa = _extract_ml(s)
    handi = 0.0
    mh = re.search(r'让球\s*([+-]?\d+(?:\.\d+)?)', s)
    if mh:
        handi = float(mh.group(1))
    keys = ['胜胜', '胜平', '胜负', '平胜', '平平', '平负', '负胜', '负平', '负负']
    bq = {}
    # 半全场: 标签式(胜胜3.80) 或 逗号9值 或 | 分隔
    for k in keys:
        mm = re.search(r'%s\s*=?\s*([\d.]+)' % k, s)
        if mm:
            bq[k] = float(mm.group(1))
    if len(bq) < 9:
        for ln in s.split('\n'):
            if '半全场' in ln or ('胜胜' in ln and '平平' in ln):
                v = _nums(ln)
                if len(v) >= 9:
                    bq = {keys[i]: v[i] for i in range(9)}
                    break
    goals = {}
    for ln in s.split('\n'):
        if '总进球' in ln or ('0球' in ln and '2球' in ln):
            v = _nums(ln)
            v = [x for x in v if 1.01 <= x <= 60]
            if len(v) >= 6:
                goals = {i: v[i] for i in range(min(8, len(v)))}
                break
    cs = {}
    for m in re.finditer(r'(\d+:\d+)\s*=\s*([\d.]+)', s):
        try:
            cs[m.group(1)] = float(m.group(2))
        except Exception:
            pass
    if not cs:   # 表格式: | 1:0 | 5.50 |
        for m in re.finditer(r'\|\s*(\d+:\d+)\s*\|\s*([\d.]+)\s*\|', s):
            try:
                cs[m.group(1)] = float(m.group(2))
            except Exception:
                pass
    o25 = 1.9
    if goals:
        inv = [(i, 1 / o) for i, o in goals.items() if o > 1]
        tot = sum(x[1] for x in inv)
        if tot > 0:
            p_over = sum(x[1] for x in inv if x[0] >= 3) / tot
            if p_over > 0:
                o25 = round(1 / p_over, 3)
    stats = _extract_team_stats(s)
    f = {k: None for k in C.FEATURE_KEYS}
    f.update({
        'home_odds': oh, 'draw_odds': od, 'away_odds': oa,
        'handicap': handi, 'o25_odds': o25,
        'league': league, 'league_id': C.LEAGUE_ID.get(league, 9),
        'is_top5': 1 if league in ('E0', 'SP1', 'I1', 'D1', 'F1', '英超', '西甲', '意甲', '德甲', '法甲') else 0,
        'is_europe': 1 if league in ('欧冠', '欧联', '欧协联') else 0,
        'handicap_layer': TF._layer(handi),
    })
    if stats:
        f.update(stats)
        if stats.get('home_avg_goals'):
            f['home_attack_strength'] = round(stats['home_avg_goals'] / 1.35, 3)
        if stats.get('away_avg_conceded'):
            f['away_defense_vuln'] = round(stats['away_avg_conceded'] / 1.35, 3)
    if bq:
        f['bqc_half_home_prob'] = TF._bqc_half_prob(bq, 'home')
        f['bqc_half_draw_prob'] = TF._bqc_half_prob(bq, 'draw')
        f['bqc_half_away_prob'] = TF._bqc_half_prob(bq, 'away')
        f['bqc_half_goal_rate'] = TF._bqc_half_goal_rate(bq)
    if cs:
        f['cs_low_score_prob'] = TF._cs_score_prob(cs, 'low')
        f['cs_high_score_prob'] = TF._cs_score_prob(cs, 'high')
        f['cs_home_clean_sheet'] = TF._cs_clean_sheet(cs, 'home')
        f['cs_away_clean_sheet'] = TF._cs_clean_sheet(cs, 'away')
    if goals:
        inv = {i: 1 / o for i, o in goals.items() if o > 1}
        tot = sum(inv.values()) or 1
        gd = {i: v / tot for i, v in inv.items()}
        f['goals_mode'] = TF._goals_mode(gd)
        f['goals_std'] = TF._goals_std(gd)
    return f


def _case_no(cid):
    m = re.search(r'(\d+)', str(cid))
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case'); ap.add_argument('--fill-all', action='store_true', dest='fill')
    a = ap.parse_args()
    raws = glob.glob(os.path.join(DATA, 'case-library', 'raw', '*.md'))
    if a.case:
        no = _case_no(a.case)
        for r in raws:
            if _case_no(os.path.basename(r)) == no:
                f = extract_from_raw(r)
                n = len([v for v in (f or {}).values() if v is not None])
                print('case%s: %d 个非空字段' % (no, n))
                print(json.dumps({k: v for k, v in f.items() if v is not None}, ensure_ascii=False, indent=1)[:900])
                return
        print('未找到 case%s 的 raw' % no)
        return
    if a.fill:
        cp = os.path.join(DATA, 'online_learning', 'state', 'cases', 'case_library.json')
        cases = json.load(open(cp, encoding='utf-8'))
        raw_map = {}
        for r in raws:
            no = _case_no(os.path.basename(r))
            if no:
                raw_map[no] = r
        filled = skipped = 0
        for c in cases:
            cid = str(c.get('case_id') or '')
            no = _case_no(cid)
            feats = c.get('features') or {}
            has_full = len([v for v in feats.values() if v is not None]) > 15
            if has_full or not no or no not in raw_map:
                skipped += 1
                continue
            fd = extract_from_raw(raw_map[no])
            if not fd:
                skipped += 1
                continue
            n = len([v for v in fd.values() if v is not None])
            if n >= 12:
                if not c.get('features'):
                    c['features'] = {}
                c['features'].update({k: v for k, v in fd.items() if v is not None})
                c['_feature_source'] = 'raw提取(%d字段·A+B类·C/D/E历史不可得)' % n
                filled += 1
        json.dump(cases, open(cp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('特征补全: %d 个案例已补（跳过 %d）' % (filled, skipped))
        # 统计
        stats = {'完整(>15)': 0, '部分(12-15)': 0, '空(<12)': 0}
        for c in cases:
            n = len([v for v in (c.get('features') or {}).values() if v is not None])
            stats['完整(>15)' if n > 15 else ('部分(12-15)' if n >= 12 else '空(<12)')] += 1
        print('案例库特征分布:', stats)
        return
    print(__doc__)


if __name__ == '__main__':
    main()
