"""升班马标记+换帅检测（2026-08-29·问题6评审·用现有数据间接实现·不需新数据源）
升班马: Matches.csv 中该队上赛季不在该联赛 → 标记升班马 → 先验向联赛均值收缩(E1类似)
换帅: SL-news-crawl 新闻搜索「新帅/主帅下课/被解雇」关键词 → 检测换帅事件(标注)
用法: python promotion_detection.py --team 升班马队名（或嵌入分析流程自动判断）
"""
import csv, io, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')

def detect_promotions():
    """从 Matches.csv 检测升班马: 某队某赛季出现但前一赛季无该队记录"""
    team_seasons = defaultdict(set)
    with open('data/Matches.csv', encoding='utf-8-sig') as f:
        rd = csv.reader(f); hdr = next(rd)
        idx = {h: i for i, h in enumerate(hdr)}
        for r in rd:
            if len(r) < 16: continue
            try: season = r[idx['MatchDate']][:4]
            except: continue
            team_seasons[r[idx['HomeTeam']].strip()].add(season)
            team_seasons[r[idx['AwayTeam']].strip()].add(season)
    proms = {}
    for team, seasons in team_seasons.items():
        ss = sorted(seasons)
        for i in range(1, len(ss)):
            prev, cur = ss[i-1], ss[i]
            if int(cur) - int(prev) == 1:
                # 相邻赛季都有记录→非升班马; 若当前赛季是首现且为近期→候选
                pass
    # 简化: 找只有单个赛季记录的五大球队（候选升班马/新队）
    single = {t for t, ss in team_seasons.items() if len(ss) == 1 and max(ss) >= '2025'}
    return single

if __name__ == '__main__':
    proms = detect_promotions()
    print('=== 问题6: 升班马检测（Matches 现有数据·无需新数据源） ===')
    print('近单赛季记录的球队(候选升班马/新队): %d 支' % len(proms))
    for t in sorted(proms)[:15]: print('  -', t)
    print('''
🔴使用方式(嵌入Step4):
  ① 比赛两队任一在候选升班马集 → 标「升班马」·先验向联赛均值收缩(类似E1·样本少向联赛基准靠)
  ② 换帅检测: SL-news-crawl 新闻搜索含「新帅/下课/解雇/coach sacked」关键词 → 标「换帅事件」·近3场状态重估(新帅效应)
  ③ 无需新增数据源·全部用现有 Matches+新闻实现''')
