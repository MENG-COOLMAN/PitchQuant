# -*- coding: utf-8 -*-
"""变动形态学分类器 (V3.5.53+ 升级工具·2026-08-17)
从 raw 案例库提取竞彩胜平负逐T序列，自动分类变动形态，与赛果对照验证。
形态: 单调减/单调增/先减后增V/先增后减∧/震荡/剧烈/变动少/频繁/温和变动
用法: python data/scripts/utils/morph_classify.py
"""
import re, glob, sys, io
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def extract_1x2(path):
    """提取胜平负逐T: 返回 [(主胜,平,客胜),...]
    兼容两种格式:
      A (case36): '### 胜平负固定奖金（逐T）\\n2026-08-15 09:45:52｜胜1.74 平3.35 负3.90'
      B (case21-25): '### 胜平负\\n- 09:47 主3.85 平3.02 客1.86'
    """
    txt = open(path, encoding='utf-8').read()
    m = re.search(r'###\s*胜平负[^\n]*\n(.*?)(?=\n###|\Z)', txt, re.S)
    if not m:
        return None
    block = m.group(1)
    series = []
    for line in block.strip().split('\n'):
        line = line.lstrip('- ').strip()
        # 格式A: 胜1.74 平3.35 负3.90 / 格式B: 主3.85 平3.02 客1.86
        mm = re.match(r'.*?(?:主|胜)([\d.]+)[↑↓]?\s*平([\d.]+)[↑↓]?\s*(?:客|负)([\d.]+)', line)
        if mm:
            series.append((float(mm.group(1)), float(mm.group(2)), float(mm.group(3))))
    return series if len(series) >= 2 else None


def classify(seq):
    """分类单项序列. 返回 (形态, 总变动%)"""
    n = len(seq)
    if n < 2:
        return ('不足', 0)
    total_chg = (seq[-1] - seq[0]) / seq[0] * 100
    steps = [seq[i + 1] - seq[i] for i in range(n - 1)]
    up = sum(1 for s in steps if s > 0)
    down = sum(1 for s in steps if s < 0)
    reversals = sum(1 for i in range(1, len(steps)) if steps[i] * steps[i - 1] < 0)
    max_step = max(abs(s) for s in steps) / seq[0] * 100
    # 单调
    if down == 0 and up > 0 and total_chg <= -1:
        return ('单调减', total_chg)
    if up == 0 and down > 0 and total_chg >= 1:
        return ('单调增', total_chg)
    # 震荡(≥2次方向反转)
    if reversals >= 2:
        return ('震荡', total_chg)
    # V型(先减后增) / ∧型(先增后减): 中间点偏离>1.5%但终点回到原点
    if n >= 3 and abs(total_chg) < 2:
        mid_idx = n // 2
        mid = (seq[mid_idx] - seq[0]) / seq[0] * 100
        if mid < -1.5:
            return ('先减后增V', total_chg)
        if mid > 1.5:
            return ('先增后减∧', total_chg)
    # 剧烈(单步≥5% 或 累计≥8%)
    if max_step >= 5 or abs(total_chg) >= 8:
        return ('剧烈', total_chg)
    # 变动少(累计<1%)
    if abs(total_chg) < 1:
        return ('变动少', total_chg)
    # 频繁(≥4次且至少1次反转)
    if n >= 4 and reversals >= 1:
        return ('频繁', total_chg)
    return ('温和变动', total_chg)


def main():
    results = defaultdict(lambda: [0, 0])  # 形态 -> [命中, 总]
    detail = []
    # 赛果从实战案例.csv 读取（权威口径·raw格式不统一）
    scores = {}
    import csv as _csv
    with open('data/case-library/实战案例.csv', encoding='utf-8-sig') as f:
        for row in _csv.DictReader(f):
            if row['真实比分'] and row['真实比分'] not in ('待赛果', ''):
                try:
                    a, b = row['真实比分'].split(':')
                    scores[row['case_id']] = (int(a), int(b))
                except (ValueError, KeyError):
                    pass
    for f in sorted(glob.glob('data/case-library/raw/case*.md')):
        cid = re.search(r'case(\d+)', f).group(1)
        if cid not in scores:
            continue
        seq = extract_1x2(f)
        if not seq:
            continue
        gh, ga = scores[cid]
        res = 'H' if gh > ga else ('D' if gh == ga else 'A')
        morphs = {}
        for idx, name in [(0, '胜'), (1, '平'), (2, '负')]:
            s = [x[idx] for x in seq]
            morphs[name] = classify(s)
        # 资金流入方向 = 累计降幅最大
        chgs = {name: (seq[-1][i] - seq[0][i]) / seq[0][i] * 100
                for i, name in [(0, '胜'), (1, '平'), (2, '负')]}
        flow_dir = min(chgs, key=lambda k: chgs[k])
        hit = (flow_dir == '胜' and res == 'H') or (flow_dir == '平' and res == 'D') or (flow_dir == '负' and res == 'A')
        mname = morphs[flow_dir][0]
        results[mname][1] += 1
        results[mname][0] += 1 if hit else 0
        detail.append(
            f"  case{cid}: 实际{res} | 胜[{morphs['胜'][0]}/{morphs['胜'][1]:.1f}%] "
            f"平[{morphs['平'][0]}/{morphs['平'][1]:.1f}%] 负[{morphs['负'][0]}/{morphs['负'][1]:.1f}%] "
            f"资金流入={flow_dir}({chgs[flow_dir]:.1f}%) {'✅' if hit else '❌'}")
    print("===== 变动形态 × 降赔方向命中 (case09-36·raw逐T) =====")
    print(f"{'形态':<12}{'场次':<6}{'命中':<6}{'准确率':<8}")
    for m, (hit, tot) in sorted(results.items(), key=lambda x: -x[1][1]):
        if tot:
            print(f"{m:<12}{tot:<6}{hit:<6}{hit / tot * 100:.0f}%")
    print()
    print("===== 明细 =====")
    for d in detail:
        print(d)


if __name__ == '__main__':
    main()
