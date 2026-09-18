# -*- coding: utf-8 -*-
"""europe_group_stage.py — 欧战单循环小组赛分析模块（V3.5.74·2026-09-07）
精算师视角逆向推演：
  - 积分形势→战意等级→轮换概率
  - 欧冠新赛制(瑞士轮36队)排名规则
  - 庄家利用战意差设置诱阻盘的识别
  - 小组赛vs淘汰赛校准矩阵(基于1174场控制变量分析)
  - 末轮大球规律(2026年1月末轮18场61球场均3.4)

用法: python europe_group_stage.py --home_points 9 --away_points 3 --matchday 6 --league 欧冠 --home_odds 1.3
"""
import sys, json, argparse
sys.stdout.reconfigure(encoding='utf-8')

# ═══════════════════════════════════════════════════════════════
# 1. 战意等级评估（基于积分形势+轮次）
# ═══════════════════════════════════════════════════════════════
def assess_motivation(points, matchday, total_matchdays=6, is_home=True):
    """评估球队战意等级
    points: 当前积分
    matchday: 当前轮次(1-6)
    total_matchdays: 总轮次(小组赛6轮/瑞士轮8轮)
    返回: (战意等级, 说明, 轮换概率)
    """
    rounds_left = total_matchdays - matchday
    max_possible = points + rounds_left * 3
    # 已出线/已锁定头名
    if points >= 13 and rounds_left <= 2:
        return ('LOW', '已锁定出线/头名，大概率轮换', 0.75)
    if points >= 10 and rounds_left <= 1:
        return ('LOW', '末轮已出线，轮换概率高', 0.70)
    # 已出局
    if max_possible < 6 and rounds_left <= 2:
        return ('LOW', '已出局，无欲无求', 0.50)
    # 争出线关键战
    if 6 <= points <= 9 and rounds_left <= 2:
        return ('HIGH', '争出线关键战，全主力', 0.05)
    # 争头名
    if points >= 9 and rounds_left <= 2:
        return ('HIGH', '争头名/排名，全主力', 0.10)
    # 正常状态
    if rounds_left >= 3:
        return ('NORMAL', '小组赛中期，正常轮换', 0.20)
    # 末轮中游
    return ('MEDIUM', '末轮中游，轻度轮换', 0.35)

# ═══════════════════════════════════════════════════════════════
# 2. 欧战校准矩阵（基于1174场控制变量分析·精算师逆向）
# ═══════════════════════════════════════════════════════════════
EUROPE_CALIBRATION_MATRIX = {
    # 赔率档: (主胜校准pp, 平局校准pp, 进球校准, 说明)
    '0-1.5(大热)':   {'hw_adj': +1.4, 'draw_adj': -2.1, 'goal_adj': +0.09, 'note': '欧战强队略稳，平局少'},
    '1.5-1.8(热门)': {'hw_adj': +5.4, 'draw_adj': -4.5, 'goal_adj': +0.04, 'note': '欧战主场优势最大档！'},
    '1.8-2.2(略热)': {'hw_adj': +4.5, 'draw_adj': -5.8, 'goal_adj': -0.10, 'note': '欧战分胜负多，进球略少'},
    '2.2-2.8(均衡)': {'hw_adj': +1.4, 'draw_adj': +0.3, 'goal_adj': +0.00, 'note': '无显著差异'},
    '2.8-3.5(略冷)': {'hw_adj': -7.2, 'draw_adj': +7.5, 'goal_adj': +0.03, 'note': '欧战冷门少，弱队守平多！'},
    '3.5-4.5(冷门)': {'hw_adj': -5.3, 'draw_adj': +4.4, 'goal_adj': +0.00, 'note': '欧战弱队主场守平多'},
    '4.5+(大冷)':    {'hw_adj': -2.6, 'draw_adj': +0.0, 'goal_adj': -0.07, 'note': '差异缩小'},
}

# 小组赛额外校准（基于小组赛vs淘汰赛控制变量分析）
GROUP_STAGE_EXTRA = {
    '1.5-1.8(热门)': {'hw_adj': +4.1, 'goal_adj': +0.17, 'note': '小组赛强队更稳'},
    '1.8-2.2(略热)': {'hw_adj': -1.3, 'goal_adj': -0.49, 'note': '小组赛进球显著少！'},
    '2.2-2.8(均衡)': {'hw_adj': +2.6, 'goal_adj': -0.42, 'note': '小组赛进球显著少！'},
    '2.8-3.5(略冷)': {'hw_adj': +10.7, 'goal_adj': +0.10, 'note': '小组赛冷门多(轮换/战意差)！'},
}

# 赛事校准系数（三层架构第2层·基于1174场控制变量分析）
LEAGUE_CALIBRATION = {
    '欧冠': {'hw_adj': +3.0, 'draw_adj': -1.0, 'goal_adj': +0.10,
             'note': '欧冠强队更稳，1.5-1.8档主胜比欧协联高12.6pp'},
    '欧联': {'hw_adj': 0.0, 'draw_adj': 0.0, 'goal_adj': 0.0,
             'note': '基准赛事'},
    '欧协联': {'hw_adj': -2.0, 'draw_adj': +1.0, 'goal_adj': -0.05,
               'note': '欧协联冷门更多，弱队主场守平多'},
}

# ═══════════════════════════════════════════════════════════════
# 3. 庄家诱阻盘识别（小组赛场景）
# ═══════════════════════════════════════════════════════════════
def detect_trap(home_odds, away_odds, handi, home_motivation, away_motivation, home_water=None):
    """识别庄家利用战意差设置的诱阻盘"""
    traps = []
    # 诱盘1: 强队战意LOW但深盘高水
    if home_motivation == 'LOW' and home_odds < 1.5 and handi and ('球半' in handi or '两球' in handi):
        traps.append({'type': '诱上盘', 'severity': 'HIGH',
            'reason': '强队已出线战意低，但深盘利用名气诱上，实际轮换后赢球不赢盘',
            'action': '避上盘，考虑下盘/小球'})
    # 诱盘2: 弱队战意HIGH但赔率被高估
    if away_motivation == 'HIGH' and away_odds > 3.0 and home_odds < 2.0:
        traps.append({'type': '诱主胜', 'severity': 'MEDIUM',
            'reason': '客队争出线战意高，但赔率被低估，主队可能留力',
            'action': '防客胜/平局'})
    # 诱盘3: 末轮双方战意都LOW→大球
    if home_motivation == 'LOW' and away_motivation == 'LOW':
        traps.append({'type': '诱小球', 'severity': 'MEDIUM',
            'reason': '双方无欲无求，替补上场放开踢，实际大球概率高(末轮场均3.4球)',
            'action': '考虑大球'})
    # 诱盘4: 深盘+超低水
    if home_odds < 1.4 and home_water and home_water < 0.8:
        traps.append({'type': '深盘超低水诱盘', 'severity': 'HIGH',
            'reason': '深盘让1.5球+超低水0.8以下=高危诱盘，强队轮换3人以上直接下盘',
            'action': '观察临场阵容，轮换≥3人则下盘/小球'})
    # 阻盘: 强队战意HIGH但盘口偏浅
    if home_motivation == 'HIGH' and home_odds < 1.8 and handi and ('平/半' in handi or '半球' in handi):
        traps.append({'type': '阻上盘', 'severity': 'MEDIUM',
            'reason': '强队战意高但盘口偏浅，庄家阻上，实际强队赢面大',
            'action': '可考虑上盘'})
    return traps

# ═══════════════════════════════════════════════════════════════
# 4. 欧冠新赛制(瑞士轮)排名规则
# ═══════════════════════════════════════════════════════════════
SWISS_LEAGUE_RULES = {
    'format': '36队单循环，每队8场',
    'qualification': {
        '前8名': '直接晋级16强',
        '9-24名': '打附加赛(2回合)争夺8个16强名额',
        '25-36名': '淘汰',
    },
    'ranking_criteria': ['积分', '净胜球', '总进球', '客场进球', '欧战积分'],
    'key_implications': [
        '末轮净胜球/总进球关键→需要刷进球的球队大球概率高',
        '9-24名附加赛多踢2场→体能消耗翻倍，豪门可能争取前8避附加赛',
        '没有"死亡之组"，强弱混搭，冷门概率比旧赛制高',
    ],
    'final_round_goals': '2026年1月末轮18场61球，场均3.4球(数据验证)',
}

# ═══════════════════════════════════════════════════════════════
# 5. 主分析函数
# ═══════════════════════════════════════════════════════════════
def analyze_group_stage(home_points, away_points, matchday, league='欧冠',
                        home_odds=None, away_odds=None, handi=None, home_water=None,
                        total_matchdays=None, is_swiss_league=None):
    """小组赛分析主入口"""
    result = {'status': 'ok', 'league': league, 'matchday': matchday}
    # 自动判断赛制
    if is_swiss_league is None:
        is_swiss_league = (league == '欧冠' and matchday > 6) or (total_matchdays and total_matchdays > 6)
    if total_matchdays is None:
        total_matchdays = 8 if is_swiss_league else 6
    result['format'] = '瑞士轮(36队8场)' if is_swiss_league else '小组赛(6场)'
    result['total_matchdays'] = total_matchdays
    # 战意评估
    hm, hm_note, hm_rot = assess_motivation(home_points, matchday, total_matchdays, True)
    am, am_note, am_rot = assess_motivation(away_points, matchday, total_matchdays, False)
    result['home_motivation'] = {'level': hm, 'note': hm_note, 'rotation_prob': f'{hm_rot*100:.0f}%'}
    result['away_motivation'] = {'level': am, 'note': am_note, 'rotation_prob': f'{am_rot*100:.0f}%'}
    # 战意差
    mot_diff = {'HIGH': 2, 'MEDIUM': 1, 'NORMAL': 0, 'LOW': -2}
    diff = mot_diff.get(hm, 0) - mot_diff.get(am, 0)
    if diff >= 3:
        result['motivation_gap'] = {'level': 'BIG', 'desc': '主队战意远强于客队', 'impact': '主胜概率+5~8pp，进球可能偏少(客队保守)'}
    elif diff <= -3:
        result['motivation_gap'] = {'level': 'BIG', 'desc': '客队战意远强于主队', 'impact': '客胜/平局概率+5~8pp，客队进攻积极'}
    elif diff >= 1:
        result['motivation_gap'] = {'level': 'SMALL', 'desc': '主队战意略强', 'impact': '主胜概率+2~3pp'}
    elif diff <= -1:
        result['motivation_gap'] = {'level': 'SMALL', 'desc': '客队战意略强', 'impact': '客队方向+2~3pp'}
    else:
        result['motivation_gap'] = {'level': 'NONE', 'desc': '双方战意相当', 'impact': '按正常实力分析'}
    # 校准矩阵
    if home_odds:
        h = float(home_odds)
        if h < 1.5: bucket = '0-1.5(大热)'
        elif h < 1.8: bucket = '1.5-1.8(热门)'
        elif h < 2.2: bucket = '1.8-2.2(略热)'
        elif h < 2.8: bucket = '2.2-2.8(均衡)'
        elif h < 3.5: bucket = '2.8-3.5(略冷)'
        elif h < 4.5: bucket = '3.5-4.5(冷门)'
        else: bucket = '4.5+(大冷)'
        cal = EUROPE_CALIBRATION_MATRIX.get(bucket, {})
        result['europe_calibration'] = {
            'odds_bucket': bucket,
            'home_win_adjust': f"{cal.get('hw_adj', 0):+.1f}pp",
            'draw_adjust': f"{cal.get('draw_adj', 0):+.1f}pp",
            'goal_adjust': f"{cal.get('goal_adj', 0):+.2f}",
            'note': cal.get('note', ''),
        }
        # 小组赛额外校准
        extra = GROUP_STAGE_EXTRA.get(bucket, {})
        if extra:
            result['group_stage_extra'] = {
                'home_win_extra': f"{extra.get('hw_adj', 0):+.1f}pp",
                'goal_extra': f"{extra.get('goal_adj', 0):+.2f}",
                'note': extra.get('note', ''),
            }
        # 赛事校准(三层架构第2层)
        league_cal = LEAGUE_CALIBRATION.get(league, LEAGUE_CALIBRATION['欧联'])
        result['league_calibration'] = {
            'league': league,
            'home_win_adjust': f"{league_cal['hw_adj']:+.1f}pp",
            'draw_adjust': f"{league_cal['draw_adj']:+.1f}pp",
            'goal_adjust': f"{league_cal['goal_adj']:+.2f}",
            'note': league_cal['note'],
        }
    # 庄家诱阻盘识别
    if home_odds and away_odds:
        traps = detect_trap(float(home_odds), float(away_odds), handi, hm, am, home_water)
        result['trap_detection'] = traps if traps else [{'type': '无明显诱阻盘', 'severity': 'NONE', 'reason': '盘口与战意匹配'}]
    # 末轮特殊规则
    if matchday == total_matchdays:
        result['final_round'] = {
            'is_final_round': True,
            'goal_pattern': '末轮场均3.4球(2026年1月数据验证)，无欲无求场次大球概率高',
            'rotation_risk': '已出线球队轮换概率70%+，深盘强队赢球不赢盘风险高',
            'swiss_league_ranking': '净胜球/总进球排名关键，需刷进球的球队大球' if is_swiss_league else '头名/出线关键战全主力',
        }
    # 综合建议
    result['recommendation'] = _generate_recommendation(result)
    return result

def _generate_recommendation(result):
    recs = []
    hm = result['home_motivation']['level']
    am = result['away_motivation']['level']
    # 战意建议
    if hm == 'LOW' and am == 'LOW':
        recs.append('双方无欲无求→大球倾向，替补放开踢')
    elif hm == 'LOW':
        recs.append('主队已出线轮换→防冷，深盘避上')
    elif am == 'LOW':
        recs.append('客队已出局→主队赢面大，但客队可能摆大巴小球')
    elif hm == 'HIGH' and am == 'HIGH':
        recs.append('双方关键战→全主力，按实力分析')
    # 诱盘建议
    for t in result.get('trap_detection', []):
        if t['severity'] == 'HIGH':
            recs.append(f"⚠️{t['type']}: {t['action']}")
    # 校准建议
    cal = result.get('europe_calibration', {})
    if cal:
        recs.append(f"欧战校准: 主胜{cal.get('home_win_adjust','')} 平局{cal.get('draw_adjust','')} 进球{cal.get('goal_adjust','')}")
    extra = result.get('group_stage_extra', {})
    if extra:
        recs.append(f"小组赛额外: 主胜{extra.get('home_win_extra','')} 进球{extra.get('goal_extra','')}")
    return recs

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='欧战小组赛分析')
    ap.add_argument('--home_points', type=int, required=True, help='主队当前积分')
    ap.add_argument('--away_points', type=int, required=True, help='客队当前积分')
    ap.add_argument('--matchday', type=int, required=True, help='当前轮次')
    ap.add_argument('--league', type=str, default='欧冠')
    ap.add_argument('--home_odds', type=str, default=None)
    ap.add_argument('--away_odds', type=str, default=None)
    ap.add_argument('--handi', type=str, default=None)
    ap.add_argument('--home_water', type=float, default=None)
    ap.add_argument('--total_matchdays', type=int, default=None)
    a = ap.parse_args()
    r = analyze_group_stage(a.home_points, a.away_points, a.matchday, a.league,
                            a.home_odds, a.away_odds, a.handi, a.home_water, a.total_matchdays)
    print(json.dumps(r, ensure_ascii=False, indent=2))
