# -*- coding: utf-8 -*-
"""Step0-11 × 审计器覆盖矩阵 —— 找「哪一步没有审计」
   判据来源：各 audit*.py 的实际检查项（读源码提取 + 人工归类）
"""
import io
import os
import re
import sys

WS = r"<HOME>\AppData\Roaming\reasonix\global-workspace"
os.chdir(WS)
sys.stdout.reconfigure(encoding='utf-8')

# ── Step0-11 全步骤（按 AGENTS 流水线）──
STEPS = [
    ('S0-a', 'txt 归一化', ['audit_steps:S01']),
    ('S0-b', '伤停 Bzzoiro', ['audit_steps:S02', 'audit_sensitivity:E_inj']),
    ('S0-c', '市场三源 P10(CS/OU/AH)', ['audit_steps:S03', 'audit_p10', 'audit_chain:CS/OU/AH→P10']),
    ('S0-d', '跨机构共识 the-odds-api', ['audit_steps:S04']),
    ('S0-e', 'ELO clubelo', ['audit_steps:S05']),
    ('S0-f', 'H2H 双源', ['audit_steps:S06']),
    ('S0-g', '赔率档查表', ['audit_steps:S07']),
    ('S0-h', 'goal_bins 总进球档', ['audit_steps:S08']),
    ('S1', '硬核层 12 项', ['audit_chain:欧盘→去水→方向', 'output_checker 硬核']),
    ('S2', '变动层 V1-V6', ['audit_flow:V1~V6 边', 'audit_chain:让球→净胜档']),
    ('S2-R20', '平局温度计 S9-S12', ['audit_steps:S09']),
    ('S2-V6', '四象限', ['audit_steps:S10']),
    ('S3', '场景 44/45/46（欧战）', ['audit_judgment:S3']),
    ('S3.5', '情境 F1-F7', ['audit_judgment:S3.5']),
    ('S4', '推论层 26 项', ['audit_judgment:S4']),
    ('S4.5', '联赛子模型 SK-league-*', ['audit_judgment:S4.5']),
    ('S4.6', 'HAF 主客场', ['audit_judgment:S4.6']),
    ('S4.8', 'NL 子模型', ['audit_steps:S20']),
    ('S5', '方向判定（D1-D4+修正53）', ['audit_sensitivity:C_draw', 'audit_flow:并列']),
    ('S5-cov', '方向覆盖 ≤2 向 + 下限', ['check_luopan:P30', 'signal_landing']),
    ('S6', '大球深度 O2.5→量级', ['audit_steps:S08/S13', 'audit_chain:O2.5→λ→量级']),
    ('S6.5', '大小球水位精读 λ_final', ['audit_sensitivity:B_o25', 'audit_chain:λ']),
    ('S6.5-inj', '伤停→λ', ['audit_sensitivity:E_inj']),
    ('S7.5', '半场精细反推', ['audit_judgment:S7.5']),
    ('S7', '比分谱系（锚定）', ['audit_steps:S14/S15/S16', 'audit_chain:全链→锚→校验']),
    ('S7-P17', 'P17 穿盘', ['audit_steps:S16']),
    ('S7-R11', 'R11 零封/BTTS', ['audit_p10:R11']),
    ('S8', '总进球+交叉验证', ['audit_steps:S12']),
    ('S9', '自检表 22 项', ['audit_judgment:S9']),
    ('S9-P30', '信号落地核查', ['audit_steps:S18', 'signal_landing', 'check_luopan:P30']),
    ('S10', '落盘 raw+CSV', ['check_luopan', 'output_checker']),
    ('S10.5', '赛后学习（赛后场景·分析时不审）', ['⚪N/A']),
    ('S11', '批末压缩/投注（批末场景·分析时不审）', ['⚪N/A']),
    ('S-P33', '步骤审计硬门禁', ['audit_steps(S00-S20)']),
    ('S-consume', '消费审计', ['audit_consumption']),
    ('S-contract', '接口契约', ['audit_contracts']),
    ('S-flow', '步骤间传导', ['audit_flow']),
    ('S-align', '口径一致性', ['audit_alignment']),
]

covered = [s for s in STEPS if s[2] and s[2] != ['⚪N/A']]
blind = [s for s in STEPS if not s[2]]
na = [s for s in STEPS if s[2] == ['⚪N/A']]

print("=" * 100)
print("Step0-11 × 审计器覆盖矩阵")
print("=" * 100)
print("  %-10s %-30s %s" % ('Step', '内容', '审计器'))
print("-" * 100)
for k, name, aud in STEPS:
    tag = '  '.join(aud) if aud else '🔴 🔴 无审计'
    print("  %-10s %-30s %s" % (k, name, tag))

print("\n" + "=" * 100)
print("汇总: 总 %d 步 ｜ 有审计 %d ｜ 🔴 盲区 %d ｜ ⚪赛后场景 %d"
      % (len(STEPS), len(covered), len(blind), len(na)))
print("=" * 100)
if blind:
    print("\n🔴 无审计覆盖的步骤（= 我反复遗漏的根源）：")
    for k, name, _ in blind:
        print("   %-10s %s" % (k, name))
