# -*- coding: utf-8 -*-
"""修正50+庄家盈亏矩阵·案例库小样本验证
验证假设: 竞彩比分盘降赔>3%(资金流入)=庄家暴露→该比分更可能打出；升赔=诱盘→更不可能
数据: case21-35 raw 比分盘（竞彩口径·已知边界：非欧盘CS全量120比分）
用法: python data/scripts/backtest/backtest_profit_matrix_case.py
"""
import sys, re, glob, os
sys.stdout.reconfigure(encoding="utf-8")

RAW = "data/case-library/raw"
# case33-35 赛果来自用户提供(2026-08-16复盘)
KNOWN = {"case30_阿森纳vs曼城": "3:0", "case31_葡国民vs埃斯托里": "2:0", "case32_卡尔马vs哈马比": "0:4",
         "case33_阿贾克斯vs海伦芬": "2:2", "case34_伯恩利vs西汉姆联": "2:2", "case35_桑坦德vs比利亚雷": "2:2"}

def parse_score_line(line):
    """解析 '1:1=6.25（锁死最低）| 2:1=7.50→7.25↓' → [(score, o0, o1, dir), ...]"""
    out = []
    for seg in line.split("|"):
        seg = seg.strip()
        m = re.match(r"(\d+:\d+)\s*=\s*([\d.]+)(?:→([\d.]+))?([↓↑])?", seg)
        if m:
            sc, o0, o1, d = m.group(1), float(m.group(2)), None, m.group(4)
            if m.group(3):
                o1 = float(m.group(3))
            out.append((sc, o0, o1, d))
    return out

def extract_score_line(txt):
    """两种格式: ①### 比分 独立标题 ②'## 一、竞彩数据'内 '- 比分:' 行"""
    m = re.search(r"### 比分\n[-*]\s*(.+?)(?:\n\n|\n-)", txt, re.S)
    if m:
        return m.group(1)
    m = re.search(r"[-*]\s*比分[:：]\s*(.+?)(?:\n|$)", txt)
    if m:
        return m.group(1)
    return None

def get_result(path, case_id):
    """提取赛果: 优先 raw 内 '## 五、赛果' 下第一行; 否则用 KNOWN"""
    if case_id in KNOWN:
        return KNOWN[case_id]
    try:
        txt = open(path, encoding="utf-8", errors="ignore").read()
        m = re.search(r"## 五、赛果.*?\n([\d]+:[\d]+)", txt, re.S)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None

files = sorted(glob.glob(os.path.join(RAW, "case*.md")))
rows = []
for p in files:
    case_id = os.path.basename(p)[:-3]
    if int(re.match(r"case(\d+)", case_id).group(1)) < 21:
        continue  # 只验 case21-35（有比分盘变动）
    txt = open(p, encoding="utf-8", errors="ignore").read()
    line = extract_score_line(txt)
    if not line:
        continue
    scores = parse_score_line(line)
    if not scores:
        continue
    result = get_result(p, case_id)
    if not result:
        print(f"  [跳过] {case_id}: 无赛果")
        continue
    rows.append((case_id, scores, result))

print(f"有效样本: {len(rows)} 场\n")
print(f"{'场次':<28} {'降赔比分(资金流入)':<28} {'升赔比分(诱盘)':<24} {'实际':<6} 降赔命中?")
tot_down = [0,0]; tot_up = [0,0]; tot_min = [0,0]; hit_any_down = 0
for case_id, scores, result in rows:
    downs = [s for s, o0, o1, d in scores if d == "↓" or (o1 is not None and o1 < o0)]
    ups = [s for s, o0, o1, d in scores if d == "↑" or (o1 is not None and o1 > o0)]
    mins = [s for s, o0, o1, d in scores if o0 == min(x[1] for x in scores)]
    hit_d = result in downs
    if downs:
        tot_down[1] += 1; tot_down[0] += 1 if hit_d else 0
        hit_any_down += 1 if hit_d else 0
    if ups:
        tot_up[1] += 1; tot_up[0] += 1 if result in ups else 0
    if mins:
        tot_min[1] += 1; tot_min[0] += 1 if result in mins else 0
    print(f"{case_id:<28} {str(downs):<28} {str(ups):<24} {result:<6} {'✅' if hit_d else '❌'}")

print("\n" + "="*60)
print("【验证结果】")
def rp(h, t):
    return f"{h}/{t} = {h/t*100:.0f}%" if t else "N/A"
print(f"降赔比分(资金流入) 命中实际赛果: {rp(tot_down[0], tot_down[1])}   <- 庄家暴露假设")
print(f"升赔比分(诱盘)     命中实际赛果: {rp(tot_up[0], tot_up[1])}   <- 诱盘假设(应低)")
print(f"最低赔比分          命中实际赛果: {rp(tot_min[0], tot_min[1])}   <- 对照组")
if tot_down[1] and tot_up[1]:
    d = tot_down[0]/tot_down[1]*100 - tot_up[0]/tot_up[1]*100
    print(f"降赔vs升赔分离度: {d:+.1f}pp")
print("\n注: 竞彩比分盘口径(抽水12.8%)·仅5-8个主要比分·非欧盘CS全量→结论标注待验证,不能改模型")
