# -*- coding: utf-8 -*-
"""在线学习配置（V1.0·2026-09-11）
🔴诚实修正(相对方案)：
  1) 静态大样本表(23万场)不被单场污染 —— 增量表独立累积·n>=MERGE_N 才参与·n<50 向静态表收缩
  2) 在线模型权重封顶(方向0.15/比分0.10) —— 仅作第6/7源·不覆盖硬核L2判定(判定权在旧模型)
  3) 单场学习效果有限 —— 期望提升需 A/B 验证(>=50场)·方案中的曲线为待验证目标
"""
import os
BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, 'state')

# 在线模型
LEARNING_RATE_DIR = 0.05      # 方向分类器学习率
LEARNING_RATE_GOALS = 0.03    # 进球回归学习率
FEATURE_KEYS = [
    # A. 赔率基础（11）
    'home_odds', 'draw_odds', 'away_odds', 'handicap', 'o25_odds',
    'league_id', 'is_top5', 'is_europe', 'elo_diff', 'handicap_layer',
    # B. 盘口衍生（10·半全场/比分盘/总进球分布·零成本）
    'bqc_half_home_prob', 'bqc_half_draw_prob', 'bqc_half_away_prob', 'bqc_half_goal_rate',
    'cs_low_score_prob', 'cs_high_score_prob', 'cs_home_clean_sheet', 'cs_away_clean_sheet',
    'goals_mode', 'goals_std',
    # C. 球队基本面（8）
    'home_avg_goals', 'away_avg_goals', 'home_avg_conceded', 'away_avg_conceded',
    'home_attack_strength', 'away_defense_vuln', 'xg_for_avg', 'xg_against_avg',
    # D. 外部模型（3）
    'api_home_p', 'api_draw_p', 'api_away_p',
    # E. 历史交锋（3）
    'h2h_n_matches', 'h2h_home_win_rate', 'h2h_avg_goals',
]  # 共 34 个数值特征（方案标 35·league 为字符串不计入）

# 特征增强后实测裁决（方案000055·两次验证）:
# ① 纯赔率特征(8): 样本外 42.23% (vs 基准 48.70%·-6.5pp)
# ② +非赔率基本面特征(共26): 样本外 47.10% (+4.87pp → 差距缩至 -1.6pp) · 方案方向成立
# ③ 🔴融合验证(6000场样本外): 热门基准 48.75% / 在线ML 47.40% / **融合(0.90+0.10)=49.43%**
# 配对 融合赢208 vs 基准赢167 → z=2.12 (p<0.05 显著) → **启用**
# → ENABLE_ONLINE_FUSION=True·权重 0.10（保守·仅第6源·不覆盖硬核判定）
# ⚠️ 依据=Matches 可得非赔率特征(Form/射门/角球/红黄牌/HT)·方案 B/C/D 类(半全场盘/比分盘/xG/api概率)
# 历史不可得 → prediction_log 已自动存档每场 35 特征·积累样本后需复核；若 20 场实测偏差>10pp 则回退
ENABLE_ONLINE_FUSION = True
W_DIR_COLD, W_DIR_GROW, W_DIR_MATURE = 0.0, 0.10, 0.10
W_GOALS_COLD, W_GOALS_GROW, W_GOALS_MATURE = 0.0, 0.0, 0.0
N_COLD, N_MATURE = 50, 200

# L2 增量表公平验证(60000场·时间分割): 冻结表 vs 在线增量表
# 比分Top1 12.89% vs 13.23%(+0.34pp)·Top2 24.70% vs 24.94%(+0.24pp)·配对 z=1.59 (p>0.05)
# → 判定: 短期无显著增益·**不接入预测**·价值仅在跨赛季长周期数据更新
# 贝叶斯层（防污染）
MERGE_N = 50          # 增量样本达到才与静态表合并
SHRINK_N = 50         # 小于此向静态/全局收缩
DECAY = 0.995         # 联赛校准滑动衰减
WINDOW = 200          # 联赛校准窗口

# 误差规则层
MIN_RULE_N = 30       # 生成修正规则的最小样本
DIR_ERR_THRESHOLD = 0.40
O25_ERR_THRESHOLD = 0.45

# CBR
CBR_MIN_CASES = 10
CBR_COLD, CBR_NORMAL = 0.05, 0.10

# 漂移
ADWIN_DELTA = 0.005
ROLLBACK_DIR_DROP = 0.02   # 方向命中率下降超过则回滚
ROLLBACK_SCORE_DROP = 0.03
VALIDATION_N = 20

LEAGUE_ID = {'E0': 0, 'SP1': 1, 'I1': 2, 'D1': 3, 'F1': 4, '欧冠': 5, '欧联': 6, '欧协联': 7,
             '英超': 0, '西甲': 1, '意甲': 2, '德甲': 3, '法甲': 4}
