# -*- coding: utf-8 -*-
"""europe_two_leg.py — 欧战两回合制单回合战意辅助模块（V3.5.74·2026-09-07）
定位: 不预测晋级，只辅助每回合的胜负方向和比分预测
  - 首回合: 双方战意/战术倾向→胜负校准+比分倾向
  - 次回合: 基于首回合比分，领先方/落后方战意调整→胜负校准+比分倾向
  - 客场进球规则取消(2021/22)后的战术变化
  - 输出: 胜负方向校准(主胜/平局/客胜pp调整) + 比分倾向(进球数/关键比分)

用法:
  首回合: python europe_two_leg.py --leg 1 --league 欧冠 --round 1/8决赛
  次回合: python europe_two_leg.py --leg 2 --first_leg "1:0" --first_home 主队 --league 欧冠 --round 1/8决赛
"""
import sys, json, argparse
sys.stdout.reconfigure(encoding='utf-8')

# ═══════════════════════════════════════════════════════════════
# 1. 首回合战意/战术倾向→胜负校准+比分倾向
#    基于: 欧战1174场控制变量分析 + 博彩行业资料
# ═══════════════════════════════════════════════════════════════
FIRST_LEG_TACTICS = {
    # 轮次: (主胜校准pp, 平局校准pp, 客胜校准pp, 进球校准, 关键比分, 战术说明)
    '资格赛': {
        'hw_adj': +1.0, 'draw_adj': +1.0, 'aw_adj': -2.0,
        'goal_adj': +0.15,
        'key_scores': ['2:1', '1:0', '2:0', '1:1'],
        'note': '资格赛实力差距大，主队主场优势明显，进球偏多'
    },
    '附加赛': {
        'hw_adj': +2.0, 'draw_adj': -1.0, 'aw_adj': -1.0,
        'goal_adj': +0.10,
        'key_scores': ['2:1', '1:0', '1:1', '2:0'],
        'note': '附加赛双方谨慎，主队略占优'
    },
    '1/8决赛': {
        'hw_adj': +3.0, 'draw_adj': -2.0, 'aw_adj': -1.0,
        'goal_adj': +0.20,
        'key_scores': ['2:1', '1:0', '2:0', '1:1'],
        'note': '1/8决赛首回合主队进攻积极，场均3.16球(数据验证)'
    },
    '1/4决赛': {
        'hw_adj': -5.0, 'draw_adj': +15.0, 'aw_adj': -10.0,
        'goal_adj': -0.20,
        'key_scores': ['1:1', '0:0', '1:0', '0:1'],
        'note': '1/4决赛首回合极度保守，平局率40%(数据验证)，进球偏少'
    },
    '半决赛': {
        'hw_adj': +5.0, 'draw_adj': -3.0, 'aw_adj': -2.0,
        'goal_adj': -0.10,
        'key_scores': ['1:0', '2:1', '1:1', '2:0'],
        'note': '半决赛主场优势关键，主队胜率高'
    },
}

# ═══════════════════════════════════════════════════════════════
# 2. 次回合: 基于首回合比分→战意调整→胜负校准+比分倾向
#    核心逻辑: 领先方保守/落后方进攻→影响胜负和进球
# ═══════════════════════════════════════════════════════════════
SECOND_LEG_BY_FIRST_RESULT = {
    # (首回合主队比分, 首回合哪队主场): 次回合校准
    # 次回合主场方 = 首回合客场方
    (1, 0, '主队'): {  # 首回合主队1:0胜，次回合客队主场(落后方主场)
        'desc': '落后方主场必进攻',
        'hw_adj': -3.0, 'draw_adj': +2.0, 'aw_adj': +1.0,  # 次回合主队=首回合客队(落后方)
        'goal_adj': +0.30,
        'key_scores': ['2:1', '1:1', '2:0', '1:0'],
        'note': '落后方主场全力进攻，进球偏多，大球倾向；领先方客场防守反击'
    },
    (2, 0, '主队'): {  # 首回合主队2:0胜，次回合客队主场(落后方主场)
        'desc': '落后方主场需攻但难度大',
        'hw_adj': -2.0, 'draw_adj': +1.0, 'aw_adj': +1.0,
        'goal_adj': +0.15,
        'key_scores': ['1:0', '1:1', '2:1', '0:0'],
        'note': '落后方主场进攻但领先方客场稳守，进球中等'
    },
    (2, 1, '主队'): {  # 首回合主队2:1胜，次回合客队主场(落后方主场)
        'desc': '落后方主场有希望，全力进攻',
        'hw_adj': -4.0, 'draw_adj': +1.0, 'aw_adj': +3.0,
        'goal_adj': +0.35,
        'key_scores': ['2:1', '1:1', '2:0', '3:1'],
        'note': '只落后1球，落后方主场进攻欲望强，大球概率高'
    },
    (0, 0, '主队'): {  # 首回合0:0，次回合客队主场
        'desc': '平局后次回合开放',
        'hw_adj': +1.0, 'draw_adj': -2.0, 'aw_adj': +1.0,
        'goal_adj': +0.25,
        'key_scores': ['1:1', '2:1', '1:0', '2:0'],
        'note': '首回合闷平后次回合双方更开放，进球偏多'
    },
    (1, 1, '主队'): {  # 首回合1:1，次回合客队主场
        'desc': '有进球平局，次回合谨慎',
        'hw_adj': 0.0, 'draw_adj': +1.0, 'aw_adj': -1.0,
        'goal_adj': +0.10,
        'key_scores': ['1:1', '1:0', '0:1', '2:1'],
        'note': '首回合有进球平局，次回合双方谨慎，进球中等'
    },
    (0, 1, '主队'): {  # 首回合主队0:1负，次回合客队主场(领先方主场)
        'desc': '领先方主场保守',
        'hw_adj': +3.0, 'draw_adj': +3.0, 'aw_adj': -6.0,  # 次回合主队=首回合客队(领先方)
        'goal_adj': -0.20,
        'key_scores': ['1:0', '0:0', '1:1', '2:0'],
        'note': '领先方主场保守控制，进球偏少，小球/平局倾向'
    },
    (1, 2, '主队'): {  # 首回合主队1:2负，次回合客队主场(领先方主场)
        'desc': '领先方主场但只领先1球',
        'hw_adj': +1.0, 'draw_adj': +2.0, 'aw_adj': -3.0,
        'goal_adj': -0.10,
        'key_scores': ['1:1', '1:0', '0:0', '2:1'],
        'note': '领先方主场但优势不大，偏保守，进球中等偏少'
    },
    (0, 2, '主队'): {  # 首回合主队0:2负，次回合客队主场(领先方主场)
        'desc': '领先方主场大优势，极度保守',
        'hw_adj': +4.0, 'draw_adj': +2.0, 'aw_adj': -6.0,
        'goal_adj': -0.30,
        'key_scores': ['1:0', '0:0', '1:1', '2:0'],
        'note': '领先方主场大优势，轮换/保守，进球少，小球倾向'
    },
}

# ═══════════════════════════════════════════════════════════════
# 3. 赛事校准系数（基于1174场控制变量分析·三层架构第2层）
#    欧冠强队更稳，欧协联冷门更多
# ═══════════════════════════════════════════════════════════════
LEAGUE_CALIBRATION = {
    '欧冠': {'hw_adj': +3.0, 'draw_adj': -1.0, 'aw_adj': -2.0, 'goal_adj': +0.10,
             'note': '欧冠强队更稳，1.5-1.8档主胜比欧协联高12.6pp'},
    '欧联': {'hw_adj': 0.0, 'draw_adj': 0.0, 'aw_adj': 0.0, 'goal_adj': 0.0,
             'note': '基准赛事'},
    '欧协联': {'hw_adj': -2.0, 'draw_adj': +1.0, 'aw_adj': +1.0, 'goal_adj': -0.05,
               'note': '欧协联冷门更多，弱队主场守平多'},
}

# ═══════════════════════════════════════════════════════════════
# 4. 决赛单场校准（中立场地·单场决胜）
# ═══════════════════════════════════════════════════════════════
FINAL_CALIBRATION = {
    'hw_adj': -5.0, 'draw_adj': +3.0, 'aw_adj': +2.0,
    'goal_adj': +0.25,
    'key_scores': ['2:1', '1:1', '1:0', '2:0'],
    'note': '决赛中立场地，主场优势消失，进球偏高(场均3.0+)，平局加时概率高',
}

# ═══════════════════════════════════════════════════════════════
# 5. 客场进球规则取消后的校准(2021/22起)
# ═══════════════════════════════════════════════════════════════
AWAY_GOAL_RULE_ABOLISHED = {
    'second_leg_goal_boost': 0.15,   # 次回合进球+0.15
    'draw_rate_delta': -0.015,        # 平局率-1.5pp
    'leading_team_more_attacking': True,  # 领先方不再保守
    'note': '客场进球规则取消后，领先方不再死守，次回合进球增加'
}

# ═══════════════════════════════════════════════════════════════
# 4. 主分析函数
# ═══════════════════════════════════════════════════════════════
def analyze_first_leg(league='欧冠', round_name='淘汰赛', away_goal_abolished=True):
    """首回合分析: 战意/战术→胜负校准+比分倾向
    三层校准: 轮次战术 + 赛事校准 + 客场进球规则
    """
    result = {'status': 'ok', 'leg': '首回合', 'league': league, 'round': round_name}
    # 决赛特殊处理(单场决胜)
    if '决赛' in round_name and '1/8' not in round_name and '1/4' not in round_name:
        cal = FINAL_CALIBRATION
        result['is_final'] = True
        result['direction_adjustment'] = {
            'home_win': f"{cal['hw_adj']:+.1f}pp",
            'draw': f"{cal['draw_adj']:+.1f}pp",
            'away_win': f"{cal['aw_adj']:+.1f}pp",
            'goals': f"{cal['goal_adj']:+.2f}",
        }
        result['score_tendency'] = {
            'key_scores': cal['key_scores'],
            'goal_level': '偏高' if cal['goal_adj'] > 0.1 else '中等',
            'note': cal['note'],
        }
        result['recommendation'] = [
            f"决赛(中立场地): 主胜{cal['hw_adj']:+.1f}pp 平局{cal['draw_adj']:+.1f}pp 客胜{cal['aw_adj']:+.1f}pp",
            f"进球倾向: 偏高({cal['goal_adj']:+.2f})",
            f"关键比分: {'/'.join(cal['key_scores'][:3])}",
        ]
        return result
    # 匹配轮次
    round_key = None
    for k in FIRST_LEG_TACTICS:
        if k in round_name:
            round_key = k
            break
    if not round_key:
        round_key = '附加赛'  # 默认
    tactic = FIRST_LEG_TACTICS[round_key]
    # 赛事校准(三层架构第2层)
    league_cal = LEAGUE_CALIBRATION.get(league, LEAGUE_CALIBRATION['欧联'])
    hw_adj = tactic['hw_adj'] + league_cal['hw_adj']
    draw_adj = tactic['draw_adj'] + league_cal['draw_adj']
    aw_adj = tactic['aw_adj'] + league_cal['aw_adj']
    goal_adj = tactic['goal_adj'] + league_cal['goal_adj']
    # 客场进球规则调整(首回合影响较小)
    if away_goal_abolished:
        goal_adj += 0.05  # 首回合也略增
    result['direction_adjustment'] = {
        'home_win': f"{hw_adj:+.1f}pp",
        'draw': f"{draw_adj:+.1f}pp",
        'away_win': f"{aw_adj:+.1f}pp",
        'goals': f"{goal_adj:+.2f}",
    }
    result['league_calibration'] = {
        'league': league,
        'hw_adj': f"{league_cal['hw_adj']:+.1f}pp",
        'note': league_cal['note'],
    }
    result['score_tendency'] = {
        'key_scores': tactic['key_scores'],
        'goal_level': '偏高' if goal_adj > 0.1 else '中等' if goal_adj > -0.1 else '偏低',
        'note': tactic['note'],
    }
    result['away_goal_rule'] = {
        'status': '已取消(2021/22起)' if away_goal_abolished else '有效(2021/22前)',
        'impact': '领先方不再死守，进球增加' if away_goal_abolished else '领先方可能死守，进球减少',
    }
    result['recommendation'] = [
        f"首回合{round_key}({league}): 主胜{hw_adj:+.1f}pp 平局{draw_adj:+.1f}pp 客胜{aw_adj:+.1f}pp",
        f"进球倾向: {result['score_tendency']['goal_level']}({goal_adj:+.2f})",
        f"关键比分: {'/'.join(tactic['key_scores'][:3])}",
    ]
    return result

def analyze_second_leg(first_leg_score, first_leg_home, league='欧冠', round_name='淘汰赛',
                       away_goal_abolished=True):
    """次回合分析: 基于首回合比分→战意调整→胜负校准+比分倾向
    first_leg_score: "1:0" 首回合比分
    first_leg_home: "主队" 或 "客队"（首回合哪队主场）
    注意: 次回合主场方 = 首回合客场方
    """
    result = {'status': 'ok', 'leg': '次回合', 'league': league, 'round': round_name}
    try:
        fh, fa = map(int, first_leg_score.split(':'))
    except:
        return {'status': 'error', 'message': '首回合比分格式错误，应为"1:0"'}
    result['first_leg'] = f'{fh}:{fa}（{first_leg_home}主场）'
    # 确定次回合主场方
    if first_leg_home == '主队':
        second_leg_home = '首回合客队'
        key = (fh, fa, '主队')
    else:
        second_leg_home = '首回合主队'
        # 🔴2026-09-07修复: fh:fa恒为首回合主场方视角·表键即此语义——原(fa,fh)反转致 first_home=客队 时领先/落后方向反
        key = (fh, fa, '主队')
    result['second_leg_home'] = second_leg_home
    # 查找校准
    if key in SECOND_LEG_BY_FIRST_RESULT:
        cal = SECOND_LEG_BY_FIRST_RESULT[key]
    else:
        # 相邻比分估算
        if fh > fa:
            cal = SECOND_LEG_BY_FIRST_RESULT[(1, 0, '主队')]
        elif fh < fa:
            cal = SECOND_LEG_BY_FIRST_RESULT[(0, 1, '主队')]
        else:
            cal = SECOND_LEG_BY_FIRST_RESULT[(0, 0, '主队')]
        result['note'] = '该比分无精确统计，参考相邻比分'
    # 客场进球规则调整
    goal_adj = cal['goal_adj']
    draw_adj = cal['draw_adj']
    if away_goal_abolished:
        goal_adj += AWAY_GOAL_RULE_ABOLISHED['second_leg_goal_boost']
        draw_adj += AWAY_GOAL_RULE_ABOLISHED['draw_rate_delta'] * 100
    # 赛事校准(三层架构第2层)
    league_cal = LEAGUE_CALIBRATION.get(league, LEAGUE_CALIBRATION['欧联'])
    hw_adj = cal['hw_adj'] + league_cal['hw_adj']
    draw_adj += league_cal['draw_adj']
    aw_adj = cal['aw_adj'] + league_cal['aw_adj']
    goal_adj += league_cal['goal_adj']
    result['situation'] = cal['desc']
    result['direction_adjustment'] = {
        'home_win(次回合主队)': f"{hw_adj:+.1f}pp",
        'draw': f"{draw_adj:+.1f}pp",
        'away_win(次回合客队)': f"{aw_adj:+.1f}pp",
        'goals': f"{goal_adj:+.2f}",
    }
    result['league_calibration'] = {
        'league': league,
        'hw_adj': f"{league_cal['hw_adj']:+.1f}pp",
        'note': league_cal['note'],
    }
    result['score_tendency'] = {
        'key_scores': cal['key_scores'],
        'goal_level': '偏高' if goal_adj > 0.15 else '中等' if goal_adj > -0.15 else '偏低',
        'note': cal['note'],
    }
    result['away_goal_rule'] = {
        'status': '已取消(2021/22起)' if away_goal_abolished else '有效(2021/22前)',
        'impact': f"次回合进球{AWAY_GOAL_RULE_ABOLISHED['second_leg_goal_boost']:+.2f}, 平局{AWAY_GOAL_RULE_ABOLISHED['draw_rate_delta']*100:+.1f}pp",
    }
    result['recommendation'] = [
        f"首回合{fh}:{fa}({first_leg_home}主场)→{cal['desc']}",
        f"次回合({second_leg_home}主场,{league}): 主胜{hw_adj:+.1f}pp 平局{draw_adj:+.1f}pp 客胜{aw_adj:+.1f}pp",
        f"进球倾向: {result['score_tendency']['goal_level']}({goal_adj:+.2f})",
        f"关键比分: {'/'.join(cal['key_scores'][:3])}",
    ]
    return result

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='欧战两回合单回合战意辅助')
    ap.add_argument('--leg', type=int, required=True, choices=[1, 2], help='1=首回合, 2=次回合')
    ap.add_argument('--first_leg', type=str, default=None, help='首回合比分(次回合必填) 如"1:0"')
    ap.add_argument('--first_home', type=str, default='主队', help='首回合哪队主场: 主队/客队')
    ap.add_argument('--league', type=str, default='欧冠')
    ap.add_argument('--round', type=str, default='淘汰赛')
    ap.add_argument('--away_goal_abolished', type=bool, default=True)
    a = ap.parse_args()
    if a.leg == 1:
        r = analyze_first_leg(a.league, a.round, a.away_goal_abolished)
    else:
        if not a.first_leg:
            print(json.dumps({'status': 'error', 'message': '次回合必须提供--first_leg首回合比分'}, ensure_ascii=False))
            sys.exit(1)
        r = analyze_second_leg(a.first_leg, a.first_home, a.league, a.round, a.away_goal_abolished)
    print(json.dumps(r, ensure_ascii=False, indent=2))
