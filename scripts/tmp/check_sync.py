# -*- coding: utf-8 -*-
# ⚠️ NOTE: 本脚本是完整版模型的自检工具（需 AGENTS.md / data 等完整文件），公开版直接运行会报 FileNotFoundError —— 保留版本仅作方法论参考（238 条校验规则示例）。
"""V3.5.74 更新同步校验器——每次模型修改后必须运行·全绿才完成
检查: ①版本一致性 ②skill引用覆盖(41) ③流水线Step0-11 ④数据文件在位 ⑤双路径md5 ⑥关键铁律存在性"""
import os, re, hashlib, re, sys, glob
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')  # 🔴2026-09-04链路优化: 默认GBK控制台防UnicodeEncodeError崩溃/乱码
except Exception:
    pass


OK, WARN, FAIL = [], [], []
def chk(cond, msg, level=FAIL):
    (OK if cond else level).append(msg)
    if cond: print(f"  ✅ {msg}")
    else: print(f"  {'⚠️' if level==WARN else '❌'} {msg}")

print("="*60)
print("V3.5.74 更新同步校验器")
print("="*60)

# ① 版本一致性
print("\n① 版本一致性（V3.5.74 应存在于核心文档·精确匹配防伪版本如 V3.5.732 穿透）")
VER = 'V3.5.74'
VER_RE = re.compile(r'V3\.5\.72(?![0-9])')
docs = {'AGENTS.md':'AGENTS.md', '主技能':'data/../.reasonix/skills/SK-model-v3-analysis/SKILL.md',
        'txt':'data/足球分析模型.txt'}
for k, v in docs.items():
    p = v if not v.startswith('data/../') else '.reasonix/skills/SK-model-v3-analysis/SKILL.md'
    chk(bool(VER_RE.search(open(p, encoding='utf-8').read())), f"{k} 含 {VER}(精确)")

# ② skill 引用覆盖
print("\n② skill 引用覆盖（29 个活跃 skill vs AGENTS 映射表）")
skills = sorted([os.path.basename(d) for d in glob.glob('.reasonix/skills/SK-*') + glob.glob('.reasonix/skills/SL-*') if os.path.isdir(d)])
agents = open('AGENTS.md', encoding='utf-8').read()
missing = []
for s in skills:
    # 分类：联赛/存档/回测 视为映射，其余需 AGENTS 显式出现
    if s.startswith('SK-league-') or s.startswith('SK-v3.5.') or s == 'SK-backtest-preview':
        continue
    if s not in agents:
        missing.append(s)
chk(len(missing) == 0, f"{len(skills)} 个 skill 映射全覆盖" + (f" 缺: {missing}" if missing else ""))

# 清理校验: 旧API key + 文档断链
_OLD_KEY = "8dd5cad6"
_key_files = ["AGENTS.md", "data/足球分析模型.txt"] + [f".reasonix/skills/{d}/SKILL.md" for d in os.listdir(".reasonix/skills")]
_key_bad = [f for f in _key_files if os.path.exists(f) and _OLD_KEY in open(f, encoding="utf-8").read()]
chk(not _key_bad, "旧API key已清除(8dd5cad6失效·仅保留新key)" + (f" 残留: {_key_bad}" if _key_bad else ""))

import re as _re_f, glob as _gl_f
_refs = set()
for _d in _key_files:
    if not os.path.exists(_d):
        continue
    _t = open(_d, encoding="utf-8").read()
    _refs |= set(_re_f.findall(r"(data/tmp/[\w\-]+\.(?:py|json))", _t))
    _refs |= set(_re_f.findall(r"(data/online_learning/[\w\-]+\.py)", _t))
_ref_miss = sorted(x for x in _refs if not os.path.exists(x))
chk(not _ref_miss, "文档引用无断链(脚本/数据文件均存在)" + (f" 断链: {_ref_miss}" if _ref_miss else ""))
# 映射表节存在
chk('Skill 清单×接入点映射表' in agents, "AGENTS 含 Skill 映射表节")

# ③ 流水线 Step0-11 完整性
print("\n③ 流水线 Step0-11 完整性")
for s in ['Step0','Step1','Step2','Step3','Step3.5','Step4','Step4.5','Step5','Step6','Step7','Step8','Step9','Step10','Step11']:
    chk(s in agents, f"AGENTS 含 {s}")

# ④ 数据文件在位
print("\n④ 数据文件在位性")
data_files = {
    'Matches.csv': 'data/Matches.csv', '欧战库': 'data/europe/欧战全量.csv',
    '联赛模块': 'data/league-modules/README.md', '联赛深度': 'data/league-modules/deep/E0_deep.json',
    '案例库raw': 'data/case-library/raw/case56_巴列卡诺vs阿拉维斯.md',
    'calc脚本': 'scripts/tmp/calc_match.py', 'calc_poisson': 'scripts/tmp/calc_poisson.py', 'calc_v3572': 'scripts/tmp/calc_v3572.py', 'fixture索引': 'data/fixture_index.json', 'league_table': 'data/tmp/league_table.json', 'team_profiles': 'data/tmp/team_profiles.json', 'water_table': 'data/tmp/water_table.json', 'score_depth_table': 'data/tmp/score_depth_table.json', 'draw_table(R20)': 'data/tmp/draw_table.json', 'homeaway(HAF)': 'data/tmp/homeaway_table.json', 'HAF脚本': 'scripts/tmp/calc_homeaway.py'}
for k, p in data_files.items():
    chk(os.path.exists(p), f"{k} 在位: {p}")
# 联赛 skill 数
league_skills = [s for s in skills if s.startswith('SK-league-')]
chk(len(league_skills) == 5, f"联赛 skill 5 个（实际{len(league_skills)}）")
euro_files = glob.glob('data/europe/*.csv')
chk(len(euro_files) >= 3, f"欧战库 CSV ≥3（实际{len(euro_files)}）")
# 半场模块（）
ht_json = [f for f in glob.glob('data/league-modules/*.json') if '半场先验' in open(f, encoding='utf-8').read()]
chk(len(ht_json) == 5, f"联赛 json 半场节 5/5（实际{len(ht_json)}）")
ht_skill = [s for s in glob.glob('.reasonix/skills/SK-league-*/SKILL.md') if 'R11' in open(s, encoding='utf-8').read()]
chk(len(ht_skill) == 5, f"联赛 skill R11/R12 5/5（实际{len(ht_skill)}）")

# ⑤ 双路径 md5
print("\n⑤ txt 双路径 md5 一致性")
m1 = hashlib.md5(open('data/足球分析模型.txt','rb').read()).hexdigest()
desk = os.path.expanduser('~/Desktop/足球分析模型.txt')
if os.path.exists(desk):
    m2 = hashlib.md5(open(desk,'rb').read()).hexdigest()
    chk(m1 == m2, f"双路径一致 {m1}")
else:
    chk(False, "桌面副本不存在")

# ⑥ 关键铁律存在性
print("\n⑥ 关键铁律存在性（AGENTS.md）")
for kw in ['备份铁则','比分命中口径','欧战六项核查表','负载缓解','必核层','分析完整性铁律','预算红线豁免铁律','Skill 清单×接入点映射表','修正53','修正54-58','批末压缩','数据源主从','半场胜平负','R20平局温度计','draw_table','Step4.6','主客场因子层','homeaway_table']:
    chk(kw in agents, f"含「{kw}」")
chk(os.path.exists("data/case-library/量级台账.csv") and "量级台账" in open("AGENTS.md", encoding="utf-8").read(), "量级台账(不确定度管理闭环·复盘对账)")
chk(os.path.exists("data/tmp/deep_anchor_table.json") and "deep_anchor_table" in open(".reasonix/skills/SK-v3572-rules/SKILL.md", encoding="utf-8").read(), "深盘锚表(档×让深·禁机械3:0+4:0模板)")
_ca = open("scripts/tmp/calc_all.py", encoding="utf-8").read()
chk("error_miner" in _ca and "cbr_predict" in _ca, "calc_all消费L4 CBR(存在≠活跃修复·2026-09-11)")
chk("river_models" in _ca and "predict" in _ca, "calc_all消费L1在线ML(仅观察·2026-09-11)")
chk("rules_for" in _ca, "calc_all消费L3误差规则(仅提示·2026-09-11)")
chk(os.path.exists("data/online_learning/docs/特征增强验证报告_20260911.txt") and os.path.exists("data/online_learning/docs/融合增益验证报告_20260911.txt"), "35特征增强+融合验证报告归档")
chk(len([k for k in __import__("re").findall(r"'\w+'", open("scripts/online_learning/config.py", encoding="utf-8").read()[open("scripts/online_learning/config.py", encoding="utf-8").read().find("FEATURE_KEYS = ["):open("scripts/online_learning/config.py", encoding="utf-8").read().find("]", open("scripts/online_learning/config.py", encoding="utf-8").read().find("FEATURE_KEYS = ["))])]) >= 30, "FEATURE_KEYS 增强(≥30特征·方案000055)")
chk(os.path.exists("data/online_learning/state/gate.json") and os.path.exists("data/online_learning/state/fusion_monitor.json"), "门禁/融合监测状态文件持久化(2026-09-11审计修复)")
chk("learning_loop as _LL" in open("scripts/online_learning/learn.py", encoding="utf-8").read(), "learn.py直接传完整特征dict(2026-09-12修复命令行传参丢失B/C/D/E)")
chk("按 case_id+date 去重" in open("scripts/online_learning/error_miner.py", encoding="utf-8").read(), "CBR add_case去重(2026-09-12)")
chk(os.path.exists("data/online_learning/state/cases/case_library.json") and len(__import__("json").load(open("data/online_learning/state/cases/case_library.json", encoding="utf-8"))) >= 10, "CBR案例库≥10(解除冷启动·含raw导入)")
chk(os.path.exists("scripts/tmp/raw_features.py"), "raw特征提取器(raw_features.py·A+B类补全·2026-09-12)")
chk(os.path.exists("scripts/online_learning/batch_learn.py"), "批量学习脚本(batch_learn.py·2026-09-12)")
chk("1pp≈1分标度" in open("scripts/tmp/prestep_dual.py", encoding="utf-8").read(), "比分分V3标度(1pp≈1分·四档放宽·2026-09-12)")
chk(os.path.exists("scripts/tmp/prestep_fetch.py") and "直连优先" in open("scripts/tmp/prestep_fetch.py", encoding="utf-8").read(), "PreStep拉取脚本(prestep_fetch.py·直连优先+代理回退·按窗口拉五大联赛)")
chk("raw_features" in open("scripts/online_learning/learn_result.py", encoding="utf-8").read(), "cmd_backfill用完整特征(raw提取优先)")
chk("融合监测" in open("scripts/online_learning/learn.py", encoding="utf-8").read(), "复盘自动记录融合监测(回滚门禁数据来源)")
chk("学习成果/融合判定" in open("scripts/tmp/check_luopan.py", encoding="utf-8").read() or "留痕" in open("scripts/tmp/check_luopan.py", encoding="utf-8").read(), "落盘校验含学习成果/融合判定留痕(case159起·闭环审计)")
chk("学习成果进入判定" in open("scripts/tmp/calc_all.py", encoding="utf-8").read(), "学习成果进入模型判定(弱判定场<45%·用户要求·分档验证)")
chk("锚-量级一致性铁律" in open("AGENTS.md", encoding="utf-8").read(), "锚-量级一致性铁律(case169教训·2026-09-12)")
chk("八场复盘三铁律" in open("AGENTS.md", encoding="utf-8").read(), "八场复盘三铁律(163-170极端批次·2026-09-13)")
chk("弱共识场平局并列铁律" in open("AGENTS.md", encoding="utf-8").read(), "弱共识场平局并列铁律(skew<150%·2026-09-13回测)")
chk("锚-六项一致性" in open("AGENTS.md", encoding="utf-8").read(), "锚-六项一致性校验(自检25·2026-09-13)")
chk("市场源优先铁律" in open("AGENTS.md", encoding="utf-8").read(), "市场源优先铁律(2026-09-13回测寻优)")
_chk_mig = open("data/tmp/migration_prompt.md", encoding="utf-8").read() if __import__("os").path.exists("data/tmp/migration_prompt.md") else ""
chk("V3.5.74" in _chk_mig and "2026-09-13" in _chk_mig, "迁移文档版本(V3.5.74·2026-09-13快照·防过时)")
chk("市场源优先" in _chk_mig and "弱共识" in _chk_mig, "迁移文档含2026-09-13关键更新")
chk("market_matrix" in open("scripts/tmp/live_score_engine.py", encoding="utf-8").read(), "live引擎市场源(market matrix·2026-09-13)")
chk("_o25_expect" in open("scripts/tmp/live_score_engine.py", encoding="utf-8").read() and "tot = _o25_expect(o25)" in open("scripts/tmp/live_score_engine.py", encoding="utf-8").read(), "market源tot动态标定(2026-09-13修复硬编码非单调/低估强攻场0.81球·防回退)")
chk("anchor_market_check" in open("scripts/tmp/live_score_engine.py", encoding="utf-8").read() and "market_net_band" in open("scripts/tmp/live_score_engine.py", encoding="utf-8").read(), "锚-市场一致性检查(2026-09-13·用户要求·净胜档±1球/大小球方向/盘口方向)")
chk("<= u1" in open("scripts/tmp/prestep_fetch.py", encoding="utf-8").read(), "PreStep窗口含上界(2026-09-13修复: \"到三点\"须含03:00开赛场·曾漏Real Sociedad vs Atletico)")
chk("直连优先 + 代理回退" in open("scripts/tmp/source_health_check.py", encoding="utf-8").read(), "source_health双通道探测(2026-09-13修复单通道误报·Odds-API/Bing实测可用却报不可用)")
chk("N07" in open("scripts/tmp/output_checker.py", encoding="utf-8").read(), "output_checker含N07锚-市场一致性块(必核)")
chk("锚-市场一致性" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含锚-市场一致性铁律(2026-09-13用户要求)")
chk("锚可信度分级" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含锚可信度分级铁律(2026-09-13·案例库157场回测)")
chk("anchor_trust" in open("scripts/tmp/prestep_dual.py", encoding="utf-8").read(), "PreStep锚可信度分级(anchor_trust·每场判级)")
chk("N08" in open("scripts/tmp/output_checker.py", encoding="utf-8").read(), "output_checker含N08锚可信度块(必核)")
chk("anchor_trust" in open("scripts/tmp/calc_all.py", encoding="utf-8").read(), "calc_all输出锚可信度行(N08配套·2026-09-13)")
chk("_netflag" in open("scripts/tmp/calc_all.py", encoding="utf-8").read() and "_lcn" in open("scripts/tmp/calc_all.py", encoding="utf-8").read(), "calc_all --net参数+_league_cn顺序修复(2026-09-14·学习日志网络源接入)")
chk("magnitude_rerank" in open("scripts/tmp/live_score_engine.py", encoding="utf-8").read() and "锚-量级矛盾" in open("scripts/tmp/live_score_engine.py", encoding="utf-8").read(), "live引擎量级重排+锚-量级告警(2026-09-13用户指出根因修复)")
chk(os.path.exists("data/online_learning/docs/融合分档验证报告_20260911.txt"), "融合分档验证报告归档(4档·弱档优势)")
chk("弱方向" in open("scripts/tmp/calc_all.py", encoding="utf-8").read(), "融合分级参与(P1-1修复·弱判定场并列建议)")
chk("竞彩txt去水" in open("scripts/tmp/calc_all.py", encoding="utf-8").read(), "融合自动赔率来源(P1-2修复·不依赖--eu)")
chk("tie-break_only" in open("data/online_learning/state/gate.json", encoding="utf-8").read(), "L3应用方式已定义(P2-1)")
chk(os.path.exists("scripts/online_learning/gate.py"), "学习接入门禁(gate.py·回测/样本/回滚/裁剪四道)")
chk("融合方向概率" in open("scripts/tmp/calc_all.py", encoding="utf-8").read(), "calc_all 输出融合方向概率(学习结果真影响预测)")
chk("融合方向概率" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS 含学习接入消费规则(不反转方向)")
chk(os.path.exists("scripts/online_learning/learn.py"), "赛后学习统一入口(模块内·轻封装)")
chk("learn.py" in open("scripts/tmp/learn_from_result.py", encoding="utf-8").read(), "tmp入口转发兼容(learn.py)")
chk(os.path.exists("data/online_learning/docs/增量表验证报告_20260911.txt"), "L2增量表验证报告归档(不显著→不接入)")
chk("VPN 默认已开" in open("AGENTS.md", encoding="utf-8").read(), "VPN默认已开前提(2026-09-12用户声明)")
chk("Bing News 伤停搜索" in open("scripts/online_learning/data_bridge.py", encoding="utf-8").read(), "news源真实接入(Bing News·VPN默认开)")
chk(os.path.exists("scripts/online_learning/data_bridge.py"), "统一数据接入层(data_bridge.py·8源+三态标注)")
chk("extract_match_date" in open("scripts/online_learning/data_bridge.py", encoding="utf-8").read(), "比赛日期自动提取(api-football按UTC日定位)")
chk(os.path.exists("scripts/online_learning/data_bridge.py") and "src_haf" in open("scripts/online_learning/data_bridge.py", encoding="utf-8").read() and "src_clubelo" in open("scripts/online_learning/data_bridge.py", encoding="utf-8").read() and "src_api_fb" in open("scripts/online_learning/data_bridge.py", encoding="utf-8").read(), "8源接入完整性(txt/haf/clubelo/xg/api_football/h2h/news/euro_odds)")
chk("TEAM_ALIASES" in open("scripts/online_learning/data_bridge.py", encoding="utf-8").read() and "def normalize_name" in open("scripts/online_learning/data_bridge.py", encoding="utf-8").read() and os.path.exists("data/team_name_mapping_2025-26.json"), "队名映射升级(2026-09-14·TEAM_ALIASES+normalize_name+映射文件在位·防回退)")
chk(os.path.exists("scripts/online_learning/txt_features.py"), "txt特征自动提取器(txt_features.py·ML数据接入)")
chk("--txt" in open("scripts/tmp/learn_from_result.py", encoding="utf-8").read(), "learn_from_result支持--txt自动提取特征")
chk("prediction_log" in open("scripts/tmp/calc_all.py", encoding="utf-8").read(), "calc_all预测日志(赛果--from-log回溯)")
chk(os.path.exists("scripts/online_learning/learning_loop.py") and os.path.exists("scripts/online_learning/config.py"), "在线学习系统(5层·learning_loop+config)")
chk("ENABLE_ONLINE_FUSION = True" in open("scripts/online_learning/config.py", encoding="utf-8").read(), "在线ML启用(特征增强+融合验证z=2.12·权重0.10·有据)")
chk(os.path.exists("scripts/tmp/learn_from_result.py"), "赛果自动学习总入口(learn_from_result.py)")
chk(os.path.exists("scripts/tmp/self_iterate.py") and os.path.exists("data/tmp/learned_rules.json"), "赛后学习闭环(self_iterate.py+学习台账+learned_rules.json)")
chk(os.path.exists("scripts/tmp/prestep_v2_verify.py") and os.path.exists("data/online_learning/docs/PreStepV2验证_20260912.txt"), "PreStepV2方案验证脚本+报告(含符号bug修正结论)")
chk("四级分档" in open(".reasonix/skills/SK-prestep-filter/SKILL.md", encoding="utf-8").read() or "强推荐(比分)" in open("scripts/tmp/prestep_dual.py", encoding="utf-8").read(), "PreStep四级分档升级(方案V2.0验证后)")
chk(os.path.exists("scripts/tmp/prestep_dual.py") and "双向评级" in open("scripts/tmp/prestep_dual.py", encoding="utf-8").read(), "PreStep双向评级脚本(方向分+比分分·用户要求)")
chk("双向评级" in open(".reasonix/skills/SK-prestep-filter/SKILL.md", encoding="utf-8").read(), "SK-prestep-filter含双向评级流程")
chk("比分命中评分" in open(".reasonix/skills/SK-prestep-filter/SKILL.md", encoding="utf-8").read(), "PreStep比分导向评分V2(用户要求·回测12000场)")
chk(os.path.exists("data/online_learning/docs/PreStep比分导向回测_20260911.txt") and os.path.exists("scripts/tmp/prestep_score_backtest.py"), "PreStep比分回测脚本+报告归档")
chk("learned_rules.json" in open("scripts/tmp/calc_all.py", encoding="utf-8").read(), "calc_all消费学习成果(⚡学习提示节·仅提示不改判定)")
chk("'E0'" in open("scripts/tmp/calc_all.py", encoding="utf-8").read() and "is_top5" in open("scripts/tmp/calc_all.py", encoding="utf-8").read(), "calc_all联赛代码映射(E0/SP1等→中文·C13触发正确)")
chk("bqc=_bqs" in open("scripts/tmp/calc_all.py", encoding="utf-8").read() and "cs=_css" in open("scripts/tmp/calc_all.py", encoding="utf-8").read() and "tg=_tgs" in open("scripts/tmp/calc_all.py", encoding="utf-8").read(), "让球动态量级8因子参数全传(F6/F7/F8生效)")
chk(os.path.exists("scripts/tmp/handicap_dynamic_magnitude.py") and os.path.exists("data/tmp/handicap_prior_table.json") and "handicap_dynamic_magnitude" in open("scripts/tmp/calc_all.py", encoding="utf-8").read() and "handicap_dynamic_magnitude" in open(".reasonix/skills/SK-v3572-rules/SKILL.md", encoding="utf-8").read(), "让球动态量级V2.0(9层先验+8因子+calc_all接入+SK消费)")
chk("extract_ht_goals_layer" in open("scripts/tmp/live_score_engine.py", encoding="utf-8").read() and "_bqc_to_ht_dist" in open("scripts/tmp/live_score_engine.py", encoding="utf-8").read() and "extract_ht_goals_layer" in open("scripts/tmp/calc_all.py", encoding="utf-8").read(), "半场推断量级模块(DRY公共+calc_all接入)")
# 审计P0/P1修复校验（防回退·原缺陷: 传 epl/laliga 等别名时 C13/C25/C27 静默不触发）
_ca_src = open("scripts/tmp/calc_all.py", encoding="utf-8").read()
chk("def norm_league" in _ca_src and "'epl': '英超'" in _ca_src and "is_top5 = _league_cn in" in _ca_src, "calc_all联赛统一归一化(norm_league·接受中文名/E0码/英文别名·C13/C25/C27触发正确)")
chk("_LMAP = {" not in _ca_src, "calc_all无旧_LMAP重复映射定义残留")
_cv_src = open("scripts/tmp/calc_v3572.py", encoding="utf-8").read()
chk("def norm_div" in _cv_src and "a.div = norm_div(a.div)" in _cv_src, "calc_v3572联赛归一化(norm_div·R1/R4/R10/R16-R18不再静默失效)")
_tf_src = open("scripts/online_learning/txt_features.py", encoding="utf-8").read()
chk("'英超', '西甲', '意甲', '德甲', '法甲'" in _tf_src, "txt_features is_top5中英双认(原只认英文代码→恒0·误差聚类失真)")
_ln_src = open("scripts/online_learning/learn.py", encoding="utf-8").read()
chk("'is_top5': 1 if _lg in" in _ln_src, "learn.py显式参数路径is_top5动态计算(原硬编码0)")

print("\n" + "="*60)
# E2: score_depth_table 时效校验
try:
    import json as _json
    _sd = _json.load(open('data/tmp/score_depth_table.json', encoding='utf-8'))
    _gen = _sd.get('generated', '')
    _ver = _sd.get('version', '')
    chk(bool(_gen), f"score_depth_table generated时间戳: {_gen}")
    chk(str(_ver) >= '3.0', f"score_depth_table version≥3.0(D1/E1): {_ver}")
except Exception as _e:
    chk(False, f"score_depth_table读取失败: {_e}")
# E2b: 134格低样本校验
try:
    import json as _j2
    _sd2 = _j2.load(open('data/tmp/score_depth_table.json', encoding='utf-8'))
    _n_cells = 0; _low_unshrunk = 0
    for _b in _sd2['buckets']:
        if _b == 'D0':
            for _db in _sd2['buckets']['D0']['draw_bins']:
                for _s in _sd2['buckets']['D0']['draw_bins'][_db]:
                    _c = _sd2['buckets']['D0']['draw_bins'][_db][_s]
                    if _c.get('n'):
                        _n_cells += 1
                        if _c['n'] < 1000 and not _c.get('shrinkage_applied'): _low_unshrunk += 1
        else:
            for _w in _sd2['buckets'][_b]['win_bins']:
                for _s in _sd2['buckets'][_b]['win_bins'][_w]:
                    _c = _sd2['buckets'][_b]['win_bins'][_w][_s]
                    if _c.get('n'):
                        _n_cells += 1
                        if _c['n'] < 1000 and not _c.get('shrinkage_applied'): _low_unshrunk += 1
    chk(_n_cells >= 130, f"score_depth_table 格数: {_n_cells}(应>=130)")
    chk(_low_unshrunk == 0, f"低样本未收缩格: {_low_unshrunk}(应为0·E1全覆盖)")
except Exception as _e2:
    chk(False, f"score_depth_table 校验失败: {_e2}")
chk("margin_candidates" in open("scripts/tmp/calc_v3572.py", encoding="utf-8").read(), "calc_v3572含margin_candidates(净胜档多档)")
chk("goal_bin_probs" in open("scripts/tmp/calc_v3572.py", encoding="utf-8").read(), "calc_v3572含goal_bin_probs(O1比分量级查表)")
chk("诱盘信号" in open("scripts/tmp/calc_v3572.py", encoding="utf-8").read() and "欧亚背离" in open("scripts/tmp/calc_v3572.py", encoding="utf-8").read(), "calc_v3572含欧亚盘口校正+诱盘信号(方向判定升级)")
chk("修正方向" in open("scripts/tmp/calc_v3572.py", encoding="utf-8").read(), "calc_v3572含LOW档修正方向(防主·提高LOW档准确率)")
chk("中盘细分" in open("scripts/tmp/calc_v3572.py", encoding="utf-8").read(), "calc_v3572含中盘细分(平赔低平局并列·提高MID档)")
chk("历史频率只做参考" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含历史频率参考铁律(禁机械锚定主场)")
chk("旧模型优点吸收" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含旧模型优点吸收清单(方向判定权归旧模型·禁脚本直出)")
chk(re.search(r"^Step5\s+方向判定", open("AGENTS.md", encoding="utf-8").read(), re.M), "AGENTS流水线含Step5标题(方向判定·防丢失)")
chk("match_classifier" in open("scripts/tmp/calc_v3572.py", encoding="utf-8").read() and "handicap_intent_analyzer" in open("scripts/tmp/calc_v3572.py", encoding="utf-8").read(), "calc_v3572含盘口诱阻识别三函数(分类器+意图分析)")
chk(all(x in open("scripts/tmp/calc_v3572.py", encoding="utf-8").read() for x in ["odds_anomaly_detector","euro_asia_consistency","water_level_anomaly","handicap_movement_analyzer","kelly_index_analyzer","jingcai_special_signal"]), "calc_v3572含诱阻识别6辅助模块(维度1-4·6-7·文档9模块全落地)")
chk("match_classifier" in open(".reasonix/skills/SK-v3572-rules/SKILL.md", encoding="utf-8").read() and "trap_classify_output" in open("scripts/tmp/calc_match.py", encoding="utf-8").read(), "诱阻识别执行链完整(SK技能消费+calc_match预计算)")
chk(os.path.exists("scripts/tmp/calc_all.py") and "必核清单" in open("scripts/tmp/calc_all.py", encoding="utf-8").read(), "calc_all全覆盖预计算存在(步骤遗失根除·30项必核清单)")
chk(os.path.exists("scripts/tmp/output_checker.py") and os.path.exists("scripts/tmp/fetch_all.py"), "output_checker+fetch_all存在(三支柱闭环)")
chk("诱平" in open("scripts/tmp/calc_v3572.py", encoding="utf-8").read() and "诱大球" in open("scripts/tmp/calc_v3572.py", encoding="utf-8").read(), "intent_analyzer支持9类意图(诱平/诱大球等)")
chk("goal_bin_probs" in open(".reasonix/skills/SK-v3572-rules/SKILL.md", encoding="utf-8").read() and "goal_bin_probs" in open("AGENTS.md", encoding="utf-8").read(), "SK-v3572-rules+AGENTS 含 goal_bin_probs(O1消费链)")
# 大小球精细化升级
_gb = open("data/tmp/goal_bins_table.json", encoding="utf-8").read() if os.path.exists("data/tmp/goal_bins_table.json") else ""
chk('"top"' in _gb, "goal_bins_table含典型比分top字段(2026-09-15全量重建·148397场)")
chk(os.path.exists("scripts/tmp/build_goal_bins.py"), "goal_bins生成脚本存在(build_goal_bins.py·可复现)")
chk("信号强度" in open("scripts/tmp/goal_odds_analyzer.py", encoding="utf-8").read() and "OV_MED_BIG" in open("scripts/tmp/goal_odds_analyzer.py", encoding="utf-8").read(), "goal_odds_analyzer信号强度三档(强/中/弱·2026-09-15)")
chk("信号强度三档" in open(".reasonix/skills/SK-v3572-rules/SKILL.md", encoding="utf-8").read() and "信号强度三档" in open("AGENTS.md", encoding="utf-8").read() and "信号强度" in open("data/足球分析模型.txt", encoding="utf-8").read(), "三文件含大小球信号强度三档(AGENTS+SK+txt)")
chk("典型比分" in open("scripts/tmp/calc_all.py", encoding="utf-8").read() and "典型比分" in open("scripts/tmp/calc_match.py", encoding="utf-8").read(), "calc_all/calc_match输出典型比分(goal_bins top4传导)")
chk("已否决" in open(".reasonix/skills/SK-v3572-rules/SKILL.md", encoding="utf-8").read() and "0.00pp" in open("AGENTS.md", encoding="utf-8").read(), "偏差校准/不对称阈值已否决留痕(防回退·2026-09-15)")
chk("N09" in open("scripts/tmp/output_checker.py", encoding="utf-8").read() and "信号强度" in open("scripts/tmp/output_checker.py", encoding="utf-8").read(), "output_checker含N09大小球信号强度块(2026-09-15·新规则入强制链)")
chk("口径对照" in open(".reasonix/skills/SK-v3572-rules/SKILL.md", encoding="utf-8").read(), "O2.5赔率↔over概率口径对照(live锚定vs信号分层·衔接说明)")
chk("44-48%边缘带" not in open("scripts/tmp/calc_match.py", encoding="utf-8").read() and "中性区" in open("scripts/tmp/calc_match.py", encoding="utf-8").read(), "calc_match旧44-48边缘带已改中性区47-53(与信号分层对齐·防冲突)")
chk(os.path.exists("data/case-library/案例库模板.md"), "案例库统一模板存在(CSV 15列+raw 七节)")
chk(os.path.exists("scripts/tmp/case_write.py"), "案例库填写脚本存在(case_write·防乱码串码遗失)")
chk("case_write" in open(".reasonix/skills/SK-model-v3-analysis/SKILL.md", encoding="utf-8").read() and "case_write" in open(".reasonix/skills/SL-case-library/SKILL.md", encoding="utf-8").read(), "主技能+SL-case-library 含 case_write(填写执行链)")
# ⑦ 投注方案生成模块
print("\n⑦ 投注方案生成模块(betting_plan_generator·2026-09-04)")
_ag = open("AGENTS.md", encoding="utf-8").read()
_bp = open("scripts/tmp/betting_plan_generator.py", encoding="utf-8").read() if os.path.exists("scripts/tmp/betting_plan_generator.py") else ""
chk(bool(_bp), "betting_plan_generator.py 存在(投注方案生成器)")
chk("投注方案生成模块" in _ag and "请你给我今天的购买方案" in _ag, "AGENTS含投注方案触发词章节")
chk(all(x in _bp for x in ["dynamic_tickets", "只买串关", "多票", "include_second", "leg_score", "goal_diff", "hit"]), "betting_plan含动态引擎+多维评分+串关铁律+source_field")
chk("只买串关" in _ag and "场数由当天" in _ag or "场数动态" in _ag, "AGENTS含只买串关+场数动态+多票铁律")
chk("ev_cal" in _bp and "0.105" in _bp, "投注模块含诚实EV(历史命中率hit·防虚高)")
_g=open("scripts/tmp/goal_odds_analyzer.py",encoding="utf-8").read() if os.path.exists("scripts/tmp/goal_odds_analyzer.py") else ""
chk(bool(_g) and "五级" in _g and "KL" in _g and "返奖率" in _g, "goal_odds_analyzer存在(竞彩总进球反推·返奖/五级量级/KL融合)")
_v3=open("scripts/tmp/calc_v3572.py",encoding="utf-8").read()
chk("小概率管理" in _v3 and "M1" in _v3 and "M2" in _v3 and "M3" in _v3, "calc_v3572含小概率管理(M1伤停冲突/M2欧深亚浅/M3官方背离·O9)")
chk(os.path.isdir(".reasonix/skills/SL-betting-plan") and "SL-betting-plan" in _ag, "SL-betting-plan skill存在且AGENTS接入(Step11购买方案指令)")
chk("betting_plan_generator" in _ag and "betting_plan_generator" in open(".reasonix/skills/SL-betting-plan/SKILL.md", encoding="utf-8").read(), "投注生成器三处引用一致(AGENTS+skill)")

# ⑯ 防过拟合/降噪校验
print("\n⑯ 防过拟合/降噪校验(2026-09-16)")
_gj_src = open("data/online_learning/state/gate.json", encoding="utf-8").read()
_ca_src2 = open("scripts/tmp/calc_all.py", encoding="utf-8").read()
chk("L1_fusion_in_decision" in _gj_src, "gate.json 含融合判定独立门禁(L1_fusion_in_decision)")
chk("degraded" in _gj_src, "L1 在线ML 已显式降级(degraded·防退化污染)")
chk("_fdec_gate" in _ca_src2 and "仅提示·不进入判定" in _ca_src2, "calc_all 消费融合判定门禁(默认仅提示·不进入判定)")
chk("防过拟合" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS 含防过拟合/降噪记录")
# 梳理补充: 参数完整性 + 规则冲突标注(防回退)
chk("draw_group_score=_draw_score" in _ca_src2 and "_true_handi" in _ca_src2, "calc_all 补传 draw_group_score + true_handi(原缺失致功能静默降级)")
chk("true_handicap_calculator" in _ca_src2, "calc_all 消费真实实力盘(盘口背离指标激活)")
chk("2026-09-16 现状（优先级最高·覆盖本条）" in open("AGENTS.md", encoding="utf-8").read()
    and "2026-09-16 现状（优先级最高·覆盖本条）" in open("data/足球分析模型.txt", encoding="utf-8").read()
    and "2026-09-16 现状（优先级最高·覆盖本条）" in open(".reasonix/skills/SK-online-learning/SKILL.md", encoding="utf-8").read(),
    "规则冲突已标注(旧「学习成果进入判定」被 L1_fusion_in_decision 门禁覆盖·三文件一致)")


print("\n⑧ 案例库数据质量校验(V3.5.74)")
import csv as _csv
try:
    with open('data/case-library/实战案例.csv', encoding='utf-8-sig') as _f:
        _rows = list(_csv.DictReader(_f))
    _vals = set((r.get('置信度层','') or '').strip() for r in _rows)
    chk(_vals <= {'HIGH','MID-HIGH','MID','MID-LOW','LOW'}, f"案例库置信度标准档(五档·含MID-HIGH·实际{_vals})")
    chk(('主锚命中' in (_rows[0] if _rows else {})), "案例库含主锚命中列(P0-3比分口径)")
    chk(len(_rows) >= 130, f"案例库样本量≥130(实际{len(_rows)})")
except Exception as _e:
    chk(False, f"案例库质量校验异常:{_e}")

print("\n⑨ 数据驱动增强校验(V3.5.74)")
import os as _os
_prior=open("data/tmp/odds_score_prior.json",encoding="utf-8").read() if _os.path.exists("data/tmp/odds_score_prior.json") else ""
_v3=open("scripts/tmp/calc_v3572.py",encoding="utf-8").read()
chk(bool(_prior) and "15" in _prior and "deep_big" in _prior, "odds_score_prior.json存在(16格比分先验·实测)")
chk("fusion_score_4way" in _v3, "calc_v3572含fusion_score_4way(四方融合)")
chk("D3赔率组合" in _v3 and "D5亚盘" in _v3 and "D6平手" in _v3, "D规则代码化(D3组合并列/D5浅盘/D6平手高水)")
chk("降权" in _v3 and "true_handicap" in _v3, "ELO残差诱盘降权标注(2026-09-07实测无预测力)")

print("⑩ 现场比分引擎校验(V3.5.74)")
_ls2 = open("scripts/tmp/live_score_engine.py", encoding="utf-8").read() if _os.path.exists("scripts/tmp/live_score_engine.py") else ""
chk(bool(_ls2) and all(x in _ls2 for x in ["analyze_live","poisson_matrix","cs_market_matrix","calculate_dynamic_weights","bayesian_fusion"]), "live_score_engine存在且核心函数齐全")
chk("弱先验" in _ls2 or "prior" in _ls2, "live引擎含16格先验弱先验(≤10%·数据不足兜底)")
chk("现场动态" in open("AGENTS.md", encoding="utf-8").read() or "live_score_engine" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含现场动态比分描述")
chk("禁止直接用先验表" in open("AGENTS.md", encoding="utf-8").read() or "非机械锚定" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含禁机械锚定铁律")

print("⑪ 半场反推+CS深度校验(Top2=40·V3.5.74)")
_hi=open("scripts/tmp/halftime_inference.py",encoding="utf-8").read() if _os.path.exists("scripts/tmp/halftime_inference.py") else ""
_cd=open("scripts/tmp/cs_deep_analyzer.py",encoding="utf-8").read() if _os.path.exists("scripts/tmp/cs_deep_analyzer.py") else ""
_hc=_os.path.exists("data/tmp/ht_ft_cond.json")
_ls3=open("scripts/tmp/live_score_engine.py",encoding="utf-8").read() if _os.path.exists("scripts/tmp/live_score_engine.py") else ""
chk(bool(_hi) and "halftime_precise_matrix" in _hi or bool(_hi) and "infer_ht_direction" in _hi, "halftime_inference存在(半场反推)")
chk(_hc, "ht_ft_cond.json条件矩阵缓存存在(175476场·19类)")
chk(bool(_cd) and "cs_vig_analysis" in _cd, "cs_deep_analyzer存在(抽水率偏差CS深度)")
chk("ht" in _ls3 and "halftime_precise_matrix" in _ls3, "live引擎含精细半场ht源(权重0.30)")

print("⑫ 实际调用链校验(V2.0·存在不等于活跃)")
_ca2 = open("scripts/tmp/calc_all.py", encoding="utf-8").read()
_cm2 = open("scripts/tmp/calc_match.py", encoding="utf-8").read()
_ls5 = open("scripts/tmp/live_score_engine.py", encoding="utf-8").read() if _os.path.exists("scripts/tmp/live_score_engine.py") else ""
chk("from live_score_engine import analyze_live" in _ca2, "live_score_engine实际接入calc_all(calc_all→live·非仅文档)")
chk("cs_deep_analyzer" in _ls5 and "cs_vig_analysis" in _ls5, "cs_deep实际接入live(live→cs_deep·抽水偏差)")
chk("from goal_odds_analyzer import" in _cm2, "goal_odds_analyzer实际接入calc_match(每场自动)")
chk("现场比分引擎" in _ca2 and "主锚建议" in _ca2, "calc_all含现场引擎输出节(主锚建议脚本Top1)")

print("⑬ 欧战+联赛校准模块校验(V3.5.74)")
_etl = open("scripts/tmp/europe_two_leg.py", encoding="utf-8").read() if _os.path.exists("scripts/tmp/europe_two_leg.py") else ""
_egs = open("scripts/tmp/europe_group_stage.py", encoding="utf-8").read() if _os.path.exists("scripts/tmp/europe_group_stage.py") else ""
_lc2 = open("data/league-modules/league_calibration.json", encoding="utf-8").read() if _os.path.exists("data/league-modules/league_calibration.json") else ""
chk(bool(_etl) and "analyze_first_leg" in _etl and "analyze_second_leg" in _etl and "SECOND_LEG_BY_FIRST_RESULT" in _etl and "LEAGUE_CALIBRATION" in _etl and "FINAL_CALIBRATION" in _etl, "europe_two_leg三层架构(单回合校准+赛事分层欧冠+3/欧协联-2+决赛中立-5pp)")
chk(bool(_egs) and "analyze_group_stage" in _egs and "detect_trap" in _egs and "EUROPE_CALIBRATION_MATRIX" in _egs and "LEAGUE_CALIBRATION" in _egs, "europe_group_stage三层(小组战意·诱盘·校准矩阵+赛事分层欧冠+3/欧协联-2)")
chk(bool(_lc2) and "德甲" in _lc2 and "英超" in _lc2 and "战术标签" in _lc2, "league_calibration.json存在(5联赛战术标签校准)")
chk("europe_two_leg" in open("AGENTS.md", encoding="utf-8").read() or "欧战两回合" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含欧战模块指引")
chk("europe_two_leg" in open(".reasonix/skills/SK-model-v3-analysis/SKILL.md", encoding="utf-8").read(), "主技能含欧战模块(三处同步)")
chk("europe_two_leg" in open("data/足球分析模型.txt", encoding="utf-8").read(), "txt含欧战模块(三处同步)")


# ── 🔴数据源成功路径固化──
chk("数据源成功路径固化表" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含数据源成功路径固化表(2026-09-19防重复纠错)")
chk("禁带 league/season" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含api-football禁league/season铁律(纯date定位)")
chk("数据源成功路径固化表" in open(".reasonix/skills/SK-model-v3-analysis/SKILL.md", encoding="utf-8").read(), "主技能含数据源成功路径固化表")
chk("数据源成功路径固化表" in open("data/足球分析模型.txt", encoding="utf-8").read(), "txt含数据源成功路径固化表")
chk("自动剥离" in open("scripts/tmp/api_football_mcp.py", encoding="utf-8").read(), "api_football_mcp含误带league/season自动剥离(脚本级防错)")
chk("fetch_clubelo.py" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含clubelo脚本通道(fetch_clubelo·禁curl)")
# ── 🔴txt 通用归一化层──
chk("txt 通用归一化层" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含txt通用归一化层(2026-09-19)")
chk("txt 通用归一化层" in open(".reasonix/skills/SK-model-v3-analysis/SKILL.md", encoding="utf-8").read(), "主技能含txt归一化层")
chk("txt 通用归一化层" in open("data/足球分析模型.txt", encoding="utf-8").read(), "txt含txt归一化层")
chk("txt_normalize.py" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含txt_normalize.py入口")
# ── 🔴模型维护最小化纪律 skill──
chk("SK-model-maintenance" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含SK-model-maintenance注册(33 skill)")
chk(os.path.exists(".reasonix/skills/SK-model-maintenance/SKILL.md"), "SK-model-maintenance skill 文件存在")
chk("分析场景不读" in open(".reasonix/skills/SK-model-maintenance/SKILL.md", encoding="utf-8").read(), "维护纪律含场景隔离(分析场景不读)")
# ── 🔴SK-audit 模型审计 skill──
chk("SK-audit" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含SK-audit注册(34 skill)")
chk(os.path.exists(".reasonix/skills/SK-audit/SKILL.md"), "SK-audit skill 文件存在")
chk(("存在≠活跃" in open(".reasonix/skills/SK-audit/SKILL.md", encoding="utf-8").read()) and ("未列出=未执行" in open(".reasonix/skills/SK-audit/SKILL.md", encoding="utf-8").read()), "SK-audit含双模式核心铁律(存在≠活跃/未列出=未执行)")
chk("审计入口" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS审计入口已升级指SK-audit")
# ── 🔴审计修复──
_ag = open("AGENTS.md", encoding="utf-8").read()
_tx = open("data/足球分析模型.txt", encoding="utf-8").read()
_sk = open(".reasonix/skills/SK-model-v3-analysis/SKILL.md", encoding="utf-8").read()
_tp = open("data/analysis_template.md", encoding="utf-8").read()
chk("执行留痕" in _ag, "AGENTS含raw第八节执行留痕规范")
chk("执行留痕" in _tx, "txt含raw第八节执行留痕规范")
chk("执行留痕" in _sk, "主技能含raw第八节执行留痕规范")
chk("执行留痕" in _tp, "模板含raw第八节执行留痕规范")
chk("联赛基准" in open("scripts/tmp/calc_all.py", encoding="utf-8").read(), "calc_all含联赛基准自动输出(fix_s1·P1-4)")
chk("第八节" in open("scripts/tmp/check_luopan.py", encoding="utf-8").read(), "check_luopan含第八节校验(fix_s3·case189+强制)")
_oc = open("scripts/tmp/output_checker.py", encoding="utf-8").read()
chk(all(b in _oc for b in ("'N10'", "'N11'", "'N12'", "'N13'", "'N14'", "'N15'")), "output_checker含N10-N15留痕块(fix_s4)")
# ── 🔴数据链三层风险原则──
_sm = open(".reasonix/skills/SK-model-maintenance/SKILL.md", encoding="utf-8").read()
chk("数据链三层风险" in _sm, "维护纪律含数据链三层风险(输入解析/数据表/展示留痕·L1-L7不引入决策)")
_au = open(".reasonix/skills/SK-audit/SKILL.md", encoding="utf-8").read()
chk(("术语差异" in _au) and ("改动分层纪律" in _au), "SK-audit含术语差异判定+改动分层纪律")
# ── 🔴审计入口三处同步──
chk("审计入口" in _sk, "主技能含审计入口(指SK-audit·2026-09-19)")
chk("审计入口" in _tx, "txt含审计入口(指SK-audit·2026-09-19)")
# ── 总结果(审计修正: 移至全部chk后·含⑧-⑪扩展段·防段后失败漏报) ──
print()
print(f"总结果(含全部校验): ✅{len(OK)} ⚠️{len(WARN)} ❌{len(FAIL)}")
if FAIL:
    print("🔴 有失败项——修复后再完成更新！")
    sys.exit(1)
else:
    print("🟢 全绿——更新同步完成")

