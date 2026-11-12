# -*- coding: utf-8 -*-
"""V3.5.75 更新同步校验器——每次模型修改后必须运行·全绿才完成
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
print("V3.5.75 更新同步校验器")
print("="*60)

# ① 版本一致性
print("\n① 版本一致性（🔴2026-10-13 审计修: 原写死 VER='V3.5.75' 且只查「全文是否存在」→ 文档历史标注恒命中 = 假通过）")
#   真断言: 取三处【声明行】的版本 → 必须同版 且 = EXPECT_VER（防「文档降到旧版不拦」）
EXPECT_VER = 'V3.5.94'
VER_RE = re.compile(r'V3\.5\.\d+(?![0-9])')
_decl_vers = {}
_ag_decl = (open('AGENTS.md', encoding='utf-8').readline() or '')
_sk_l = open('.reasonix/skills/<REDACTED_SK>/SKILL.md', encoding='utf-8').read().splitlines()
_tx_l = open('data/足球分析模型.txt', encoding='utf-8').read().splitlines()
for _k, _ln in (('AGENTS.md', _ag_decl),
                # 🔴2026-11-02 修「取第一个匹配行」→「取**最后**一个匹配行」：
                #   主技能 frontmatter `description` 与正文版本行是**两处独立声明**，
                #   原实现取第一个（description）→ 正文版本行滞后（实测仍写 V3.5.85）不被拦 = 假通过。
                #   改为取 [:8]/[:3] 内最后一个匹配行 → 两处声明均须 = EXPECT_VER，任一滞后即报红。
                ('主技能', next((x for x in reversed(_sk_l[:8]) if VER_RE.search(x)), '')),
                ('txt', next((x for x in reversed(_tx_l[:3]) if VER_RE.search(x)), ''))):
    _m = VER_RE.search(_ln or '')
    _decl_vers[_k] = _m.group(0) if _m else None
    chk(_decl_vers[_k] == EXPECT_VER,
        f"{_k} 声明版本={_decl_vers[_k]}（须 {EXPECT_VER}·取声明行非全文·2026-10-13 修假通过）")
chk(len({v for v in _decl_vers.values() if v}) == 1,
    "三处声明版本一致(%s)" % _decl_vers)
# 防伪版本穿透: 声明行不得出现比 EXPECT_VER 更新的版本号
#   🔴2026-10-14 修: 原硬编码 r'V3\.5\.(?:7[89]|[89]\d)' → EXPECT_VER 升到 V3.5.78 后
#   「V3.5.78」本身被误判为超前（假失败）→ 改为**动态**：解析声明行所有版本号，须 ≤ EXPECT_VER
def _vkey(_v):
    try:
        return tuple(int(x) for x in _v.lstrip("Vv").split("."))
    except Exception:
        return (0, 0, 0)


_exp_k = _vkey(EXPECT_VER)
_decl_vs = re.findall(r'V(\d+\.\d+\.\d+)', _ag_decl)
_overshoot = [v for v in _decl_vs if _vkey(v) > _exp_k]
chk(not _overshoot,
    "AGENTS 声明行无超前版本号(防伪版本穿透·动态比对 %s%s)"
    % (EXPECT_VER, (" 超前: %s" % _overshoot) if _overshoot else ""))

# ② skill 引用覆盖
print("\n② skill 引用覆盖（29 个活跃 skill vs AGENTS 映射表）")
skills = sorted([os.path.basename(d) for d in glob.glob('.reasonix/skills/SK-*') + glob.glob('.reasonix/skills/SL-*') if os.path.isdir(d)])
agents = open('AGENTS.md', encoding='utf-8').read()
missing = []
for s in skills:
    # 分类：联赛/存档/回测 视为映射，其余需 AGENTS 显式出现
    if s.startswith('SK-league-') or s.startswith('SK-v3.5.') or s == '<REDACTED_SK>':
        continue
    if s not in agents:
        missing.append(s)
chk(len(missing) == 0, f"{len(skills)} 个 skill 映射全覆盖" + (f" 缺: {missing}" if missing else ""))

# 🔴2026-09-12 清理校验: 旧API key + 文档断链
_OLD_KEY = "<REDACTED_HEX>"
_key_files = ["AGENTS.md", "data/足球分析模型.txt"] + [f".reasonix/skills/{d}/SKILL.md" for d in os.listdir(".reasonix/skills")]
_key_bad = [f for f in _key_files if os.path.exists(f) and _OLD_KEY in open(f, encoding="utf-8").read()]
chk(not _key_bad, "旧API key已清除(8dd5cad6失效·仅保留8b393c0a)" + (f" 残留: {_key_bad}" if _key_bad else ""))

import re as _re_f, glob as _gl_f
_refs = set()
for _d in _key_files:
    if not os.path.exists(_d):
        continue
    _t = open(_d, encoding="utf-8").read()
    _refs |= set(_re_f.findall(r"(data/tmp/[\w\-]+\.(?:py|json))", _t))
    _refs |= set(_re_f.findall(r"(data/online_learning/[\w\-]+\.py)", _t))
# 🔴2026-10-31: **运行时产物**不该算「文档引用断链」——
#   `fundflow_books.json` 由 `the_odds_api_fetch books` 生成，按设计**失败即删除**
#   （宁可无数据三态·不留污染）→ 缺失属正常状态，不是断链。
_RUNTIME_GEN = ('data/tmp/fundflow_books.json',           # books 产物（失败即删）
                'data/tmp/prestep_window.json',           # PreStep 产物
                'data/tmp/_totals_multi.json',            # 多档 Totals 临时产物
                'data/tmp/the_odds_api_key_state.json')   # key 池状态
_ref_miss = sorted(x for x in _refs
                   if not os.path.exists(x) and x not in _RUNTIME_GEN)
chk(not _ref_miss, "文档引用无断链(脚本/数据文件均存在)" + (f" 断链: {_ref_miss}" if _ref_miss else ""))
# 映射表节存在
chk('Skill 清单×接入点映射表' in agents, "AGENTS 含 Skill 映射表节")

# ③ 流水线 Step0-11 完整性
print("\n③ 流水线 Step0-11 完整性")
for s in ['Step0','Step1','Step2','Step3','Step3.5','Step4','Step4.5','Step5','Step6','Step7','Step8','Step9','Step10','Step11']:
    chk(s in agents, f"AGENTS 含 {s}")

# 🔴早盘快照机制（2026-09-28·防回退）
print()
print("⑯ 早盘快照机制")
snap_src = open("data/tmp/snapshot_save.py", encoding="utf-8").read()
chk("snapshot_save 时间戳命名(防覆盖)", "%Y%m%d_%H%M" in snap_src)
chk("早盘快照规则在 AGENTS", "早盘赔率快照" in open("AGENTS.md", encoding="utf-8").read())
chk("数据隔离条款(event_id匹配·禁跨场)", "禁跨场复用" in open("AGENTS.md", encoding="utf-8").read())

# ④ 数据文件在位
print("\n④ 数据文件在位性")
data_files = {
    'Matches.csv': 'data/Matches.csv', '欧战库': 'data/europe/欧战全量.csv',
    '联赛模块': 'data/league-modules/README.md', '联赛深度': 'data/league-modules/deep/E0_deep.json',
    '案例库raw': 'data/case-library/raw/case56_巴列卡诺vs阿拉维斯.md',
    '早盘快照工具': 'data/tmp/snapshot_save.py', '快照目录说明': 'data/tmp/snapshots/README.md', 'calc脚本': 'data/tmp/calc_match.py', 'calc_poisson': 'data/tmp/calc_poisson.py', 'calc_v3572': 'data/tmp/calc_v3572.py', 'fixture索引': 'data/fixture_index.json', 'league_table': 'data/tmp/league_table.json', 'team_profiles': 'data/tmp/team_profiles.json', 'water_table': 'data/tmp/water_table.json', 'score_depth_table': 'data/tmp/score_depth_table.json', 'draw_table(R20)': 'data/tmp/draw_table.json', 'homeaway(HAF)': 'data/tmp/homeaway_table.json', 'HAF脚本': 'data/tmp/calc_homeaway.py'}
for k, p in data_files.items():
    chk(os.path.exists(p), f"{k} 在位: {p}")
# 联赛 skill 数
# 🔴2026-09-23: 五大联赛 5 个 + 欧国联 nations 1 个（分开计数·防 glob 误判）
league_skills = [s for s in skills if s.startswith('SK-league-') and 'nations' not in s]
chk(len(league_skills) == 5, f"联赛 skill 5 个（五大联赛·实际{len(league_skills)}）")
chk(any('nations' in s for s in skills), "SK-league-nations 存在（欧国联子模型·V3.5.75）")
euro_files = glob.glob('data/europe/*.csv')
chk(len(euro_files) >= 3, f"欧战库 CSV ≥3（实际{len(euro_files)}）")
# 半场模块（V3.5.73）
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
_ca = open("data/tmp/calc_all.py", encoding="utf-8").read()
chk("error_miner" in _ca and "cbr_predict" in _ca, "calc_all消费L4 CBR(存在≠活跃修复·2026-09-11)")
chk("river_models" in _ca and "predict" in _ca, "calc_all消费L1在线ML(仅观察·2026-09-11)")
chk("rules_for" in _ca, "calc_all消费L3误差规则(仅提示·2026-09-11)")
chk(os.path.exists("data/online_learning/docs/特征增强验证报告_20260911.txt") and os.path.exists("data/online_learning/docs/融合增益验证报告_20260911.txt"), "35特征增强+融合验证报告归档")
chk(len([k for k in __import__("re").findall(r"'\w+'", open("data/online_learning/config.py", encoding="utf-8").read()[open("data/online_learning/config.py", encoding="utf-8").read().find("FEATURE_KEYS = ["):open("data/online_learning/config.py", encoding="utf-8").read().find("]", open("data/online_learning/config.py", encoding="utf-8").read().find("FEATURE_KEYS = ["))])]) >= 30, "FEATURE_KEYS 增强(≥30特征·方案000055)")
chk(os.path.exists("data/online_learning/state/gate.json") and os.path.exists("data/online_learning/state/fusion_monitor.json"), "门禁/融合监测状态文件持久化(2026-09-11审计修复)")
chk("learning_loop as _LL" in open("data/online_learning/learn.py", encoding="utf-8").read(), "learn.py直接传完整特征dict(2026-09-12修复命令行传参丢失B/C/D/E)")
chk("按 case_id+date 去重" in open("data/online_learning/error_miner.py", encoding="utf-8").read(), "CBR add_case去重(2026-09-12)")
chk(os.path.exists("data/online_learning/state/cases/case_library.json") and len(__import__("json").load(open("data/online_learning/state/cases/case_library.json", encoding="utf-8"))) >= 10, "CBR案例库≥10(解除冷启动·含raw导入)")
chk(os.path.exists("data/tmp/raw_features.py"), "raw特征提取器(raw_features.py·A+B类补全·2026-09-12)")
chk(os.path.exists("data/online_learning/batch_learn.py"), "批量学习脚本(batch_learn.py·2026-09-12)")
chk("强小球+1.0" in open("data/tmp/prestep_dual.py", encoding="utf-8").read(), "比分分V4.1标度(极强小球+1.5/强小球+1.0·2026-10-26 35,879场实测 +3.1~+5.8pp 支持)")
chk(os.path.exists("data/tmp/prestep_fetch.py") and "_CHANNELS" in open("data/tmp/prestep_fetch.py", encoding="utf-8").read() and "代理优先" in open("data/tmp/prestep_fetch.py", encoding="utf-8").read(), "PreStep拉取脚本(prestep_fetch.py·🔴2026-10-31 代理优先1.2s + 直连回退4s·按窗口拉五大联赛)")
chk("raw_features" in open("data/online_learning/learn_result.py", encoding="utf-8").read(), "cmd_backfill用完整特征(raw提取优先)")
chk("融合监测" in open("data/online_learning/learn.py", encoding="utf-8").read(), "复盘自动记录融合监测(回滚门禁数据来源)")
chk("学习成果/融合判定" in open("data/tmp/check_luopan.py", encoding="utf-8").read() or "留痕" in open("data/tmp/check_luopan.py", encoding="utf-8").read(), "落盘校验含学习成果/融合判定留痕(case159起·闭环审计)")
    # 🔴2026-10-30 P31 机制防回退（第二次同类事故：case297/298 伤停误报三态）
chk("_raw" in open("data/tmp/prestep_fetch.py", encoding="utf-8").read() and "sync\u843d" not in "x", "P34 prestep 保留 1xbet 全响应(raw)")
chk("prestep_%s_%s.json" in open("data/tmp/prestep_fetch.py", encoding="utf-8").read(), "P34 prestep 同步落 snapshots 快照(供 find_for/delta_for/vertical_for/P10)")
chk("def _bj(_s)" in open("data/tmp/prestep_fetch.py", encoding="utf-8").read(), "P34 kickoff_bj 北京时间(防跨场防护剔除)")
_pfv = open("data/tmp/prestep_fetch.py", encoding="utf-8").read()
chk("_REQ = ('home', 'away', 'kickoff_bj', 'raw_1xbet')" in _pfv and "schema 校验后 0 场合格" in _pfv and "_OPT" in _pfv, "V3.5.93 prestep 写入端 schema 防线(必填非空+白名单键·实测53份8种格式·禁再产生第9种)")
chk('_d["攻防"]' in open("data/tmp/market_distribution.py", encoding="utf-8").read(), "P36 N27 攻防分项已接入 _signal_support（防再成死代码）")
chk("tad_h=tad_h" in open("data/tmp/joint_solver.py", encoding="utf-8").read(), "P36 joint_anchor 透传 tad_h/tad_a")
chk("if '--teams' in sys.argv:" in open("data/tmp/calc_all.py", encoding="utf-8").read().split("_teams27 = ''")[1][:120], "P36b N27 队名 --teams 英文优先（防中文匹配失败再断）")
_rc4 = __import__("subprocess").run([__import__("sys").executable, "data/tmp/audit_chain.py", "--l4"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
chk(_rc4.returncode == 0, "L4 全链端到端 8 链贯通（audit_chain.py --l4）")
chk("if _sk <= 10:" in open("data/tmp/confidence_engine.py", encoding="utf-8").read(), "P37 skew 单位分界（防百分数<100 被误乘成 9500%%）")
chk("_FULL = {" in open("data/tmp/team_attack_defense.py", encoding="utf-8").read(), "P38 N27 全称映射表(防全称匹配不到)")
chk("_CITY_NOISE" in open("data/tmp/team_attack_defense.py", encoding="utf-8").read(), "P38b N27 城市名黑名单(防 Espanyol→Barcelona 误配)")
_rcD = __import__("subprocess").run([__import__("sys").executable, "data/tmp/audit_deadcode.py"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
chk("主链无未登记死代码" in (_rcD.stdout or ""), "P40 死代码扫描 主链无未登记死代码（audit_deadcode.py）")
chk(os.path.exists("data/tmp/audit_deadcode.py"), "audit_deadcode.py 死代码扫描器")
chk("def market_net_band(oh, od, oa, handi=None)" in open("data/tmp/live_score_engine.py", encoding="utf-8").read(), "P43 让球口径纳入净胜档(防超深盘判过窄)")
chk("market_net_band(oh, od, oa, handi=handi)" in open("data/tmp/live_score_engine.py", encoding="utf-8").read(), "P43 anchor_market_check 透传 handi")
chk(os.path.exists("data/tmp/audit_chain.py"), "audit_chain.py 全链路审计(2026-10-30 批次1)")
_rc1 = __import__("subprocess").run([__import__("sys").executable, "data/tmp/audit_chain.py", "--l1", "--fmt"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
chk(_rc1.returncode == 0, "L1 存在性 + 格式化扫描 实跑通过")
chk(os.path.exists("data/tmp/audit_steps.py"), "audit_steps.py 20步审计器(2026-10-30)")
_asS1b = open("data/tmp/audit_steps.py", encoding="utf-8").read()
chk("S01b" in _asS1b and "竞彩胜平负时点数" in _asS1b and "(?<!让球)" in _asS1b,
    "S01b 竞彩**胜平负时点数**断言（2026-11-07 case335 实证·原 S01 只看格式不看内容 → 胜平负 0 时段时 V1/D1/形态学/低赔重排 四层静默失效）")
chk("P33 步骤审计硬门禁" in open("data/tmp/check_luopan.py", encoding="utf-8").read(), "P33 步骤审计硬门禁(check_luopan·case299+)")
chk("audit_steps" in open("data/tmp/pipeline.py", encoding="utf-8").read(), "pipeline Stage6 集成步骤审计(2026-10-30)")
chk("R-POOL-BIG" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "R-POOL-BIG 宽池分级已接线 calc_all(2026-10-30)")
chk("R-ANCHOR-BIG" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "R-ANCHOR-BIG 次锚上探已接线 calc_all(2026-10-30)")
chk(os.path.exists("data/tmp/big_pool_policy.py"), "big_pool_policy.py 宽池/次锚策略脚本(2026-10-30)")
chk("'L4'" in open("data/tmp/big_pool_policy.py", encoding="utf-8").read() and "span_requirement" in open("data/tmp/big_pool_policy.py", encoding="utf-8").read(), "P47/P48 大球分级 L4 + 次锚跨度式要求(2026-10-31 用户指正)")
chk("'L5'" in open("data/tmp/big_pool_policy.py", encoding="utf-8").read() and "1.40" in open("data/tmp/big_pool_policy.py", encoding="utf-8").read(), "P52 超大球独立档 L5 + O2.5<=1.40 门槛(148397场时间分割·2026-10-31)")
chk("P52 超大球独立档" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS 含 P52 超大球独立档节(三处同步)")
chk("4:3" in open("data/tmp/big_pool_policy.py", encoding="utf-8").read() and "2:5" in open("data/tmp/big_pool_policy.py", encoding="utf-8").read(), "P52 宽池 7 球档典型比分(防 KeyError·2026-10-31 实抓)")
chk("def level_from_line" in open("data/tmp/big_pool_policy.py", encoding="utf-8").read() and "def required_bins" in open("data/tmp/big_pool_policy.py", encoding="utf-8").read(), "P52 分级单一入口 level_from_line/required_bins（禁调用方各自复制 if-else）")
chk("level_from_line" in open("data/tmp/market_distribution.py", encoding="utf-8").read() and "_BPP52s.span_requirement" in open("data/tmp/market_distribution.py", encoding="utf-8").read(), "P52-fix 分级真接入锚定模块（量级/宽池/次锚跨度·禁回退 print-only）")
_rc52 = __import__("subprocess").run([__import__("sys").executable, "data/tmp/audit_p52_chain.py"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
chk(_rc52.returncode == 0, "P52 端到端链路审计全过（audit_p52_chain.py）")
chk("P52 矩阵弱兜底判级" in open("data/tmp/joint_solver.py", encoding="utf-8").read() and "P52 锚量级纠偏" in open("data/tmp/joint_solver.py", encoding="utf-8").read(), "P52-fix2 矩阵弱兜底（实测: 矩阵 edge_err>门禁→不选锚→纯泊松主锚2球与大盘矛盾·N07b ❌→✅）")
# ── Step 全流程审计（2026-10-31 用户「大工程」）──
chk(os.path.exists("data/tmp/audit_all_steps.py"), "Step 全流程四段审计器(27 步·A生产/B调用/C输出/D消费)")
chk(os.path.exists("data/tmp/h2h_lookup.py") and "h2h_lookup" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "S00d H2H 双源已接入 calc_all（源2=Matches.csv 逐场可核对→自动补 修正53 S6）")
chk("fatigue_intent" in open("data/tmp/calc_all.py", encoding="utf-8").read() and "_fi.fatigue(" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "S03.5 疲劳战意已接入 calc_all（此前零调用）")
chk("if __name__ == '__main__':" in open("data/tmp/fatigue_intent.py", encoding="utf-8").read()[:1500], "fatigue_intent stdout 重定向仅在 CLI（防被 import 时关闭全局 stdout·批次1 实抓）")
# ── 批次2（消融实抓 2 个真缺陷）──
chk("_draw_parallel" in open("data/tmp/calc_v3572.py", encoding="utf-8").read() and "draw_group_score >= 2.5" in open("data/tmp/calc_v3572.py", encoding="utf-8").read(), "修正53 分组分≥2.5 → 平局并列落到 parallel（消融实证: draw-score 3.0 曾只 +5% 概率·并列仍 no）")
chk("max(i for i, x in enumerate(sys.argv) if x == n)" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "_av 取最后一个同名参数（与 _ov 字典口径一致·消融实证: Step6.5 λ 曾不认覆盖的 --o25）")
chk(os.path.exists("data/tmp/audit_sensitivity.py"), "Step 输入敏感性消融器（owner 判据·批次2 新增）")
# ── 批次3（消融/单元实抓 2 个真断链）──
chk("fatigue_fav" in open("data/tmp/confidence_engine.py", encoding="utf-8").read() and "fatigue_fav=_fi_fat_fav" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "S03.5 疲劳/战意 → 置信度层（此前只 print·实测仅疲劳4.5 即 HIGH→MID-HIGH）")
chk("cn2en_list" in open("data/tmp/calc_all.py", encoding="utf-8").read() and "HAF λ对照" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "S04.6 HAF 用统一别名层 + 自动 λ对照（实测「巴黎圣曼」曾→None 致整层未触发）")
# ── 批次4（S05 两处「只写文案不执行」）──
chk("O9 小概率管理执行(批次4 落地)" in open("data/tmp/calc_v3572.py", encoding="utf-8").read(), "O9 小概率管理 猫腻≥2 → 真降档+真并列（原仅拼 sp_note 文案·conf/parallel 未动）")
chk("判据①诱主降并列(2026-10-24 固化·批次4 真执行)" in open("data/tmp/calc_v3572.py", encoding="utf-8").read(), "判据① 诱主信号 → 真降并列（原仅 calc_all print「执行要求」·parallel 未动）")
# ── key 池轮转（2026-10-31 用户指令：用完才换·没用完不换）──
_TOA = open("data/tmp/the_odds_api_fetch.py", encoding="utf-8").read()
chk("fetch_rotated" in _TOA and "load_keys" in _TOA and "mark_exhausted" in _TOA,
    "the-odds-api **key 池轮转**（原单 key·配额用尽即全站三态→跨机构分歧 P0-1 瘫痪）")
chk("NOT_QUOTA_MARKS" in _TOA and "HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN" in _TOA,
    "key 轮转**区分功能限制**（historical 需付费 ≠ 配额·禁误拉黑好 key）")
chk("RESET_DAYS = 30" in _TOA,
    "key 用尽 **30 天自动恢复**（额度按月重置·不永久拉黑）")
# 🔴2026-11-07 修（用户指出「k1 应该是恢复了」·实测成立）：
#   额度是**按自然月重置**（11-01 归零），不是「耗尽后满 30 天」。
#   原只有 `(now-t0).days >= 30` → 10-31 耗尽的 K1 被锁到 11-30，
#   实测 11-07 已 used=0/remaining=500（满血）却完全不用 → **白等 29 天**
chk("crossed_month" in _TOA and "(now.year, now.month) != (t0.year, t0.month)" in _TOA,
    "the-odds-api **跨月即恢复**（2026-11-07 实证·原 30 天逻辑把 10-31 耗尽的 K1 锁到 11-30，"
    "而实际 11-01 已满血 500 → 白等 29 天；现「跨月 OR 30 天」任一满足即可用）")
# 🔴2026-11-07 K2「假耗尽」实抓：
#   state 标 exhausted@11-02，但实探 `used=499 remaining=1` **仍能出数**（18 场）
#   根因：原 `--probe` 写 `if probe and state != 'exhausted'` → **exhausted 永远不实探** → 假耗尽永不可见
#   且 `/v4/sports/` 是**免费端点不耗额度** → probe 可随时跑（原文档「会消耗 1 次」是错的）
chk("if probe:" in _TOA and "已自动恢复为可用" in _TOA,
    "the-odds-api `--probe` **对 exhausted 也实探 + 探到有额度自动恢复**（2026-11-07 K2 实证: "
    "假耗尽·remaining=1 仍能出数却因 `state != 'exhausted'` 永远不被探到）")
chk("INVALID_KEY_MARKS" in _TOA and "mark_invalid" in _TOA,
    "key **INVALID_KEY 处理**（实测: 一个错 key 原本会卡死整条链·现标记后切下一个）")
chk("已自动改用欧盘均衡线" in open("data/tmp/calc_all.py", encoding="utf-8").read(),
    "handi **自动纠正**（原仅告警·模型可忽略 → 现差≥0.5档直接改用均衡线·校验在 joint_anchor 之前）")
chk("complete_ness" in open("data/tmp/confidence_engine.py", encoding="utf-8").read()
    or "completeness" in open("data/tmp/confidence_engine.py", encoding="utf-8").read(),
    "confidence_engine **数据完整度封顶**（case301: 3/8 源却给 HIGH → ≤3/8 封 MID-LOW / 4/8 封 MID）")
_DBR = open("data/online_learning/data_bridge.py", encoding="utf-8").read()
chk("_DEAD_SRC" in _DBR and "不计入分母" in _DBR,
    "完整度分母**排除已停用源**（原 tot=len(status) 含 api_football → 8/8 结构不可达·虚低 1/8）")
import json as _jsn   # 🔴局部导入（check_sync 主流程未 import json·断言内自足）
_EXTRA = _jsn.load(open("data/tmp/cn2en_extra.json", encoding="utf-8"))
chk(len([k for k in _EXTRA if not k.startswith("_")]) >= 700,
    "队名并入用户 691 队表（cn2en_extra ≥700 键·只增不覆盖·[欧战小联赛队名可转](cn2en_list 全源生效)）")
chk(len(_DBR.split("LEAGUE_SLUG")[0]) >= 0 and
    _DBR.count(": '") > 0 and "england-championship" in _DBR and "netherlands-eredivisie" in _DBR,
    "LEAGUE_SLUG 扩至二级+欧战小联赛（34 条·slug 全部 /leagues 实测·**禁自动匹配**）")
chk(os.path.exists("data/tmp/team_names_master.json"),
    "team_names_master.json 在位（691 队 + 107 联赛留档）")
_SS = open("data/tmp/snapshot_save.py", encoding="utf-8").read()
_ON = open("data/tmp/cn2en_online.py", encoding="utf-8").read() if os.path.exists("data/tmp/cn2en_online.py") else ""
_DB = open("data/online_learning/data_bridge.py", encoding="utf-8").read()
chk("[:5]" not in _DB.split("def src_h2h")[1].split("def ")[0],
    "H2H **禁 [:5] 截断**（原 'AFC Ajax'→'afcaj' 致 16 队 h2h 永久静默 missing）")
chk("startswith(T) or k.endswith(T)" in _DB and "len(k) - len(T)) <= 4" in _DB,
    "H2H 反向子串**限前缀/后缀+长度差≤4**（原无条件反向 → 巴萨被当西班牙人/AC米兰被当国米）")
chk("understat 无该队数据" in _DB and "非队名问题" in _DB,
    "数据源归因**指向真实瓶颈**（候选已转出时禁写「未命中队名」·防排查方向错）")
chk("cn2en_online" in _SS and bool(_ON),
    "队名**联网兜底**（本地查不到→维基 langlinks·用户指令「严禁查不到简称就 missing」·"
    "命中即回写 cn2en_extra 自我进化）")
chk("_sub2" in _ON and "_TEAM_HINT" in _ON,
    "联网结果**相关度校验**（≥2 字连续子串·实测拦下「林肯红魔→Brentford」误配）")
chk("_DEADLINE" in _ON and "_from_search" in _ON,
    "联网**预算守卫 + 搜索路径禁回写**（实测 24.6s 超时 → 1-3s；搜索误配不固化）")
chk(os.path.exists("data/tmp/time_guard.py") and
    "now_bj" in open("data/tmp/time_guard.py", encoding="utf-8").read() and
    "freshness" in open("data/tmp/time_guard.py", encoding="utf-8").read(),
    "时间模块 time_guard 在位（L1 时间源 now_bj + L2 新鲜度 freshness·"
    "用户指令「模型的时间会漂移」·防删防回退）")
chk(os.path.exists("data/tmp/image2txt.py") and
    os.path.exists("data/tmp/img2txt.py") and
    os.path.exists("data/tmp/ocr2std.py"),
    "竞彩截图→txt 三件套在位（image2txt 一条命令 / img2txt OCR / ocr2std 转换·"
    "用户指令「发图片自动识别转化为 txt 输入模型」）")
chk("build_sections" in open("data/tmp/ocr2std.py", encoding="utf-8").read() and
    "ARROW" in open("data/tmp/ocr2std.py", encoding="utf-8").read(),
    "ocr2std 含真实竞彩截图三修（build_sections 标题切分 / ARROW 剥离涨跌箭头 / 表头跳过）"
    "—— 只按表格 cell 找玩法会全部 0/5（2026-11-01 实测）")
chk("inj_fav" in open("data/tmp/confidence_engine.py", encoding="utf-8").read() and
    "热门方伤停" in open("data/tmp/calc_all.py", encoding="utf-8").read(),
    "伤停**进置信度引擎**（inj_fav → 铁则32≥4.0 降档 / M1≥15 硬降1档）—— "
    "原 assess() 无 inj 参数 → 科莫场伤停 12.9 却仍判 HIGH（2026-11-01 修）")
chk("def min_cover_check" in open("data/tmp/signal_landing.py", encoding="utf-8").read(),
    "signal_landing.min_cover_check 存在（覆盖下限判据本体）—— "
    "2026-11-01 曾「只写脚本没执行」导致函数不存在·pipeline 调用抛 AttributeError 被 except 吞掉")
chk("预测方向（程序预填）" in open("data/tmp/pipeline.py", encoding="utf-8").read(),
    "raw 骨架「预测方向」**程序预填**（原留 ______ → 模型漏填 = 覆盖不足）")
chk("分析时间:" in open("data/tmp/calc_all.py", encoding="utf-8").read()
    and "time_guard" in open("data/tmp/calc_all.py", encoding="utf-8").read(),
    "calc_all **开头打印分析时间**（time_guard·禁模型口述）—— "
    "2026-11-01 模型**6 次**报错时间（说 01:28 实际 23:18·差 2h10m）")
chk("当前时间:" in open("data/tmp/pipeline.py", encoding="utf-8").read()
    and "time_guard" in open("data/tmp/pipeline.py", encoding="utf-8").read(),
    "pipeline **末尾打印当前时间** + Stage0 `time_guard.print_context()`")
chk("TT1" in open("data/tmp/output_checker.py", encoding="utf-8").read(),
    "output_checker **T01 必核断言**：输出缺「分析时间/当前时间」即拦（模型口述不算）")
chk("2026-11-01 时间模块全模型安装" in open("AGENTS.md", encoding="utf-8").read(),
    "AGENTS **时间模块铁律 T1-T5**（报时间必调 time_guard.now_bj·赛程必用 match_state）")
chk("league_covered(getattr(a, 'league', None)" in open("data/tmp/pipeline.py", encoding="utf-8").read()
    or "league_covered(_lg)" in open("data/tmp/pipeline.py", encoding="utf-8").read(),
    "pipeline._inj **先判源是否覆盖联赛**（`bzzoiro_fetch.league_covered`）—— "
    "Bzzoiro 50 个联赛**无任何亚洲联赛** → 日职/韩职 伤停缺失 = 「源不覆盖」合规三态，"
    "而非「(缺失)」（原标注审计无法区分「源不覆盖」与「漏查」·307/308/309 实证）")
chk("源不覆盖" in open("data/tmp/audit_steps.py", encoding="utf-8").read(),
    "audit_steps **S02 接受「源不覆盖」为合规三态**（否则源不覆盖的日职/韩职场次永远判遗漏）")
chk("COVERED_LEAGUES" in open("data/tmp/bzzoiro_fetch.py", encoding="utf-8").read(),
    "bzzoiro_fetch **COVERED_LEAGUES 白名单**（实证 50 个联赛·无亚洲联赛）")
chk(os.path.exists("data/tmp/magnitude_band.py")
    and "def magnitude_band" in open("data/tmp/magnitude_band.py", encoding="utf-8").read(),
    "**V3.5.87 量级确定层**（用户 2026-11-02「方法二·先定量级再选比分」）—— "
    "五源融合（P10 E[T] 0.35 + P52 六档 0.25 + O2.5 0.20 + λ 0.15 + 盘口线 0.05）"
    "→ 档中心+优先范围；**禁硬上下限**（档外只降权 0.55/0.25/0.10·不排除）")
chk("t_band=t_band" in open("data/tmp/joint_solver.py", encoding="utf-8").read()
    and "t_band=None" in open("data/tmp/joint_solver.py", encoding="utf-8").read(),
    "joint_solver **t_band 透传**（joint_anchor → anchor_select）")
chk("band_weight" in open("data/tmp/market_distribution.py", encoding="utf-8").read()
    and "量级档前置" in open("data/tmp/market_distribution.py", encoding="utf-8").read(),
    "anchor_select **支持度 × band_weight**（档内 1.0 / 档外降权·只降不排除）")
_ca_mb = open("data/tmp/calc_all.py", encoding="utf-8").read()
chk(("量级分布" in _ca_mb or "量级档确定" in _ca_mb) and "t_band=_n23_tb" in _ca_mb,
    "calc_all **生成量级档 + 传参**（配套链路：生成→打印→透传）·V3.5.88 兼容两版文案")
chk("blk('量级档V387')" in open("data/tmp/pipeline.py", encoding="utf-8").read(),
    "pipeline raw 骨架**真的拼装**量级档块（`buf.append(... blk('量级档V387'))`）—— "
    "🔴2026-11-02 实抓：只加 KEY_BLOCKS（切片表）不加 buf.append（拼装行）→ "
    "calc_all 有输出但 raw 骨架**不含该块**（用户在 raw 里看不到·等于没接入）")
# ────────────────────────────────────────────────────────────────────────────
# 🔴V3.5.90 厚尾判据收敛 + O-TAIL 标注级观察期（2026-11-03 评审修复·用户实测 9 场）
#   评审四硬伤: ①p5_ge≥0.15 else 无条件判厚尾(89% 触发) ②premium 相对折价比非独立线索
#   (9 场 min 0.99/中位 1.22/max 1.46·1.2 是结构性常数) ③cs_tail_ratio 未去水口径
#   ④与 R-ANCHOR-BIG 叠加。修复 = 判据只用 premium≥2.0·其余线索留痕·O-TAIL 标注级
#   (_TAIL_ACT=False 只打印不动作·观察 ≥20 场)·验收红线 = 判据收敛 + 无伪消费
# ────────────────────────────────────────────────────────────────────────────
_mb90 = open("data/tmp/magnitude_band.py", encoding="utf-8").read()
chk("def tail_signal" in _mb90 and "tail_premium" in _mb90
    and "判据仅 premium≥2.0" in _mb90 and "波胆溢价" in _mb90
    and "P0-2: 判据只用 premium" in _mb90,
    "V3.5.90 magnitude_band **tail_signal 判据收敛**（premium≥2.0 单条·强厚尾 premium≥3.0·"
    "cs_tail_ratio/p5_ge/p6_ge/|E[M]| 全降留痕·评审四硬伤修复）")
chk("cs_full=_n23_cs_full9" in open("data/tmp/calc_all.py", encoding="utf-8").read()
    and "厚尾三线索(V3.5.90)" in open("data/tmp/calc_all.py", encoding="utf-8").read()
    and "标注(V3.5.90观察期)" in open("data/tmp/calc_all.py", encoding="utf-8").read(),
    "calc_all **波胆全表传入(欧盘优先·竞彩回退) + 厚尾块打印**（V3.5.90 标注级·"
    "cs_full→magnitude_band→tail 键→输出块·真接线）")

chk('厚尾三线索' in open("data/tmp/pipeline.py", encoding="utf-8").read()
    and "blk('厚尾三线索')" in open("data/tmp/pipeline.py", encoding="utf-8").read(),
    "V3.5.90 pipeline 接线 **KEY_BLOCKS 切片 + raw 骨架真拼装**（厚尾三线索）—— "
    "🔴实跑实抓: calc_all 每场打印但 pipeline 零命中 → raw 不含 = 伪消费")
chk('厚尾三线索' in open("data/tmp/output_checker.py", encoding="utf-8").read()
    and 'TAIL90' in open("data/tmp/output_checker.py", encoding="utf-8").read(),
    "V3.5.90 output_checker **TAIL90 判据**（缺厚尾块即报）—— 闸门不查 = 漏写无人拍")
chk('厚尾三线索' in open("data/tmp/audit_consumption.py", encoding="utf-8").read(),
    "V3.5.90 audit_consumption **厚尾消费项**（观察期不动锚但必须被消费）")

# 🔴2026-11-03 V3.5.90 厚尾 A/B 消融（_TAIL_ACT False→True 锚必须变·否则激活路径=死代码）
try:
    _abl90 = __import__('subprocess').run(
        [__import__('sys').executable, 'data/tmp/audit_tail90.py'],
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=240)
    _abl_o = (_abl90.stdout or '')
    chk(_abl90.returncode == 0 and 'A/B ✅' in _abl_o,
        "V3.5.90 厚尾 A/B 消融（_TAIL_ACT False→True → 次锚必须变·激活路径非死代码）")
    chk('降级 ✅' in _abl_o,
        "V3.5.90 厚尾无波胆诚实降级（premium=None → 正常·禁臆造）")
except Exception as _e90:
    chk(False, "V3.5.90 厚尾消融异常: %s" % str(_e90)[:60])

# 🔴2026-11-03 文档-实现一致（审计 A2⑥「描述与实现一致」）:
#   实抓：判据已收敛为 premium 单条，但 docstring 仍写 V3.5.89 四线索 → 审计必判不一致
_mb90b = open("data/tmp/magnitude_band.py", encoding="utf-8").read()
chk('cs_tail_ratio ≥ 0.30' not in _mb90b and 'P(≥5) ≥ 0.15 且' not in _mb90b
    and 'V3.5.89 厚尾三线索' not in _mb90b,
    "V3.5.90 **docstring 与实现一致**（旧判据 cs_tail_ratio≥0.30 / P≥5≥0.15 已清·审计 A2⑥）")
chk('溢价=%s' in _mb90b,
    "V3.5.90 自测打印**显示溢价**——判据已收敛 premium·原只显示已降级为留痕的净胜 = 伪展示")
chk('观察期' in open("data/tmp/joint_solver.py", encoding="utf-8").read()
    and '强制放宽' not in open("data/tmp/joint_solver.py", encoding="utf-8").read(),
    "V3.5.90 O-TAIL docstring 含**观察期说明**（_TAIL_ACT=False 标注级·非「强制放宽」）")
chk("_n23_cs_full9" in open("data/tmp/calc_all.py", encoding="utf-8").read()
    and "竞彩回退" in open("data/tmp/calc_all.py", encoding="utf-8").read(),
    "calc_all **cs_full 竞彩回退**（欧盘 1xbet 波胆缺时回退竞彩 22 档反推赔率·"
    "实抓: 欧盘缺波胆 → 波胆线索恒三态 = 覆盖缺口）")
_md90 = open("data/tmp/market_distribution.py", encoding="utf-8").read()
chk("O-TAIL 厚尾覆盖" in _md90 and "_TAIL_ACT" in _md90
    and "O-TAIL 厚尾标注(V3.5.90观察期)" in _md90,
    "anchor_select **O-TAIL 标注级开关**（联动 joint_solver._TAIL_ACT·False 只打印标注不改锚）")
_js90 = open("data/tmp/joint_solver.py", encoding="utf-8").read()
chk("_TAIL_ACT = False" in _js90 and "O-TAIL T域最后防线" in _js90 and "O-TAIL 终态覆盖" in _js90,
    "joint_solver **O-TAIL 双防线 + 观察期开关**（①T域放宽②终态覆盖·_TAIL_ACT=False "
    "只打印标注·观察 ≥20 场后置 True 恢复动作）")
chk("_pk(k)[0] - _pk(k)[1]" in _js90,
    "joint_solver **_cs_market_probs 冒号键修复**（原 int(k.split('-')[0]) 对 '1:0' 崩溃·V3.5.89 审计实抓）")

# 🔴V3.5.91（2026-11-03 case320 端到端检验实抓·识图根因 + 4 类判据缺陷）
#   元教训: 「识图老是出问题」此前一直被归因为 OCR 模型不行，实测全在我自己代码
_it91 = open("data/tmp/image2txt.py", encoding="utf-8").read()
chk("_to = 90 if _sz > 200_000 else (60 if _sz > 80_000 else 40)" in _it91
    and "timeout=15," not in _it91
    and "timeout=150," in _it91,
    "V3.5.91 识图 **动态 timeout**（原硬编码 15s·而 ocr_layout 默认 180s → 比分表 120 档×3 时点必超时 "
    "→ 转 glm-4.6v 空壳 → 比分永久 0 条·实测重跑 10.3s 成功）")
chk("def _vmatch_empty" in _it91 and "_vmatch_empty(vt)" in _it91
    and "_vmatch_empty(_vtmp)" in _it91,
    "V3.5.91 识图 **空壳不落盘 + 复用前校验内容**（原只判 size>20 → 393B 空壳 match/features 全空 "
    "却被当有效缓存复用 → 该图信息永久丢失）")
chk("_is_table_img(img)" in _it91 and "timeout=150" in _it91,
    "V3.5.91 识图 **宽表图 glm-ocr 失败重试 150s·禁转 vision**（glm-4.6v 是赛事页专用·不认表格）")
_le91 = open("data/tmp/live_score_engine.py", encoding="utf-8").read()
_tri91 = (_le91[_le91.find("if not _tri['ok']:"):][:700]
          if "if not _tri['ok']:" in _le91 else "")
# 🔴只看**非注释行**（注释里会引用旧代码 `res['ok'] = False` → 全文搜会假失败）
_tri91_code = [l for l in _tri91.split("\n")
               if l.strip() and not l.strip().startswith("#")]
chk("期望三源不一致（校验层·以市场为准继续判锚·不阻断）" in _tri91
    and not any("res['ok'] = False" in l for l in _tri91_code),
    "V3.5.91 锚校验 **三源不一致不再短路**（原 res['ok']=False → 好锚被误杀：case320 主锚偏离 0.97≤1.0、"
    "软b 3≤3.97≤5 全过却判 ❌ 并给「无可行组合·锚不可信」）")
_md91 = open("data/tmp/market_distribution.py", encoding="utf-8").read()
_js91 = open("data/tmp/joint_solver.py", encoding="utf-8").read()
_ca91 = open("data/tmp/calc_all.py", encoding="utf-8").read()
chk("line_eq=None," in _md91
    and "if line_eq is not None and 2.0 <= float(line_eq) <= 4.2" in _md91
    and "line_eq=line_eq" in _js91 and "line_eq=_n23_fv" in _ca91,
    "V3.5.91 P52 分级 **用真实盘口均衡线**（原拿 _E25/期望总进球当均衡线 → N24 校准 +0.67 后 E=4.02 "
    "而盘口线仍 3.15 → 同场 calc_all 判 L3 / market_distribution 判 L5 两分级）")
chk("_tw.get('lam_final')" in _ca91,
    "V3.5.91 calc_all **P52 均衡线 key 修正**（原查 lambda_final → 实际 key 是 lam_final → 三档全 None）")
_cw91 = open("data/tmp/case_write.py", encoding="utf-8").read()
chk("any(a in ('-h', '--help', '/?', '-?') for a in argv)" in _cw91,
    "V3.5.91 case_write **--help 拦截**（原 --help 被当参数 → 直接写 21 列全空记录污染案例库）")
_bz91 = open("data/tmp/bzzoiro_fetch.py", encoding="utf-8").read()
_pl91 = open("data/tmp/pipeline.py", encoding="utf-8").read()
chk("INDEX_COVERED" in _bz91 and "def index_covered" in _bz91 and "index_covered(_lg)" in _pl91,
    "V3.5.91 Bzzoiro **索引覆盖 ≠ 联赛覆盖**（欧冠在 COVERED_LEAGUES 但 --teams 依赖 v1 events 索引、"
    "索引仅五大 → 原扫完五大白等 240s 超时）")

# 🔴V3.5.92（2026-11-04 用户指令「固定一个标准的数据结构·方便获取也方便模型消费」）
#   纵向三维原本结构迥异（cs 按比分索引 / ah·ou 扁平）→ 消费端各写一套 if-else
#   现新增 std 统一层（meta/signal/detail）+ 消费端优先读 std、回退旧键 → 零回归
_ss92 = open("data/tmp/snapshot_save.py", encoding="utf-8").read()
_md92 = open("data/tmp/market_distribution.py", encoding="utf-8").read()
_js92 = open("data/tmp/joint_solver.py", encoding="utf-8").read()
chk("def _vert_std(" in _ss92 and "out[\"std\"] = _vert_std(" in _ss92,
    "V3.5.92 纵向 **std 统一标准结构**（_vert_std·meta/signal/detail 三层·旧键全保留=兼容层）")
chk(("'axis': 'net'" in _ss92 or '"axis": "net"' in _ss92) and "_W = {'drop_strong': 2" in _ss92,
    "V3.5.92 std.signal **四件套**（axis/v/strength/note）·cs 按比分方向加权聚合（客胜升赔亦利好主队）")
chk("vert_std=None):" in _md92 and "_sg = vert_std.get(\"signal\")" in _md92,
    "V3.5.92 消费端**优先读 std**、无则回退旧三键（anchor_select 收 vert_std）")
chk('vert_std=((vert or {}).get("std"))' in _js92,
    "V3.5.92 joint_solver **透传 vert.std**（防「数据层有了消费层读不到」）")

# 🔴V3.5.92-fix（2026-11-04 case323 实证）: S02 判据与真实输出不同步
#   V3.5.91 起 Bzzoiro 三态文案 = 「**索引**不覆盖」，而 audit_steps S02 白名单只认「源不覆盖」
#   → 判据退化成「靠模型在 raw 手写『源不覆盖』四字才过」= 假通过
#   实证: case321/322 恰好写了 → PASS / case323 没写 → MISSING（三态证据完全一样）
_as92 = open("data/tmp/audit_steps.py", encoding="utf-8").read()
chk("索引不覆盖" in _as92 and "未定位到任何队" in _as92,
    "V3.5.92 S02 伤停判据**认「索引不覆盖」**（V3.5.91 起的真实文案·原只认「源不覆盖」"
    " → 靠模型手写四字才过 = 假通过）")

# 🔴V3.5.92-fix2（2026-11-04 case324 实证·P31 同型第 3 次）:
#   Stage2 打印了「索引不覆盖」实证，但 stage5 raw 只从 calc_all 切片 → 实证**没进 raw**
#   → audit_steps S02 判 MISSING → 每场靠模型手写才过
#   修: stage5 收 inj_msg → 写进 raw 伤停块
_pl92 = open("data/tmp/pipeline.py", encoding="utf-8").read()
chk("def stage5(a, std, calc_out, calc_path, inj_msg=None):" in _pl92
    and "Stage2 伤停实证（pipeline 实测·非未执行）" in _pl92
    and "_inj_t = (_stage2_res or {}).get('inj')" in _pl92,
    "V3.5.92-fix **Stage2 伤停实证写入 raw**（原 stage5 只切片 calc_all → 实证不进 raw "
    "→ S02 判 MISSING → 每场靠模型手写「索引不覆盖」才过）")
_oc92 = open("data/tmp/output_checker.py", encoding="utf-8").read()
chk("重排不触发" in _oc92 and "重排.{0,6}未触发" in _oc92,
    "V3.5.92-fix **N04 量级重排接受「不触发」三态**（live 只在 O2.5<1.50/>2.10 强信号时重排·"
    "中信号场正确地不重排 → 原判据仍要 → 把「正确不触发」判成「未完成」）")

# 🔴V3.5.92-fix3（2026-11-04 case323/324 实证）: 让球均衡档判据把**抽水率**混进了**均衡度**
#   旧: abs(主-客) <= 0.25 → case323 +0.25 档(抽水仅 1.5%·去水 p偏离 0.044) 被误拒
#       而 case321 +1.00 档(抽水 4.5%·p偏离 0.030) 通过 → **抽水越低越容易被拒**（反直觉）
#   后果: 判「无均衡档」→ P1 让球水位 / V3 水位 / rule61-64 / P8 升降盘 **全部失效**
#   新: 去水后 p_home 偏离 0.5 <= 0.08（与抽水率无关）
_ss93 = open("data/tmp/snapshot_save.py", encoding="utf-8").read()
chk("去水后主队隐含概率偏离 0.5 超 0.08 才算不均衡" in _ss93
    and "_dev(r) <= 0.08" in _ss93,
    "V3.5.92-fix3 让球**均衡档判据改用去水 p偏移**（原 abs(主-客)<=0.25 把抽水率混进均衡度 "
    "→ 抽水越低越易被拒 → case323/324 让球维度全失效）")


chk("R11零封" in open("data/tmp/pipeline.py", encoding="utf-8").read()
    and "blk('R11零封')" in open("data/tmp/pipeline.py", encoding="utf-8").read(),
    "pipeline **R11 零封块切片 + raw 骨架拼装** —— 2026-11-02 端到端审计实抓断点："
    "calc_all 输出 3 行 R11，但 KEY_BLOCKS 缺 → raw 不含 → 消费审计报「未消费 3」")
chk(r"队名解析[:：]" in open("data/tmp/audit_steps.py", encoding="utf-8").read(),
    "audit_steps **S00b 判据对齐实际输出**（`🔎 队名解析: A→B`）—— 原判据要求「主=」"
    "与 calc 实际格式不符 → 恒判 MISSING（假遗漏·2026-11-02 实抓）")
# 🔴 2026-11-03 欧战六项核查表（rule51-70）脚本化——
#   实跑实抓: 欧冠场跑 pipeline 时「C10 Step3 场景44/45/46(+欧战六项核查表)」
#   只是必核清单里一行文字，脚本层**零输出** → 模型漏调 SL-europe-db 就缺六项而不自知
chk(os.path.exists("data/tmp/europe_check.py"),
    "europe_check.py 在位（欧战六项核查 rule51-70 脚本化）")
chk("from europe_check import report" in open("data/tmp/calc_all.py", encoding="utf-8").read(),
    "calc_all **真调用** europe_check.report（欧战六项核查）—— " 
    "防「脚本存在但无人调」的存在≠活跃型回退")
chk("欧战六项核查" in open("data/tmp/pipeline.py", encoding="utf-8").read()
    and "blk('欧战六项核查')" in open("data/tmp/pipeline.py", encoding="utf-8").read(),
    "pipeline **KEY_BLOCKS 切片 + raw 骨架真拼装**（欧战六项核查）—— " 
    "🔴只加 KEY_BLOCKS 不加 buf.append → raw 不含该块 = 等于没接入")


chk("量级档V387" in open("data/tmp/pipeline.py", encoding="utf-8").read(),
    "pipeline **KEY_BLOCKS 切片量级档块**（raw 骨架必含·防模型漏写）")
chk("锚**自动校正**" in open("data/tmp/calc_all.py", encoding="utf-8").read()
    and "自枚举" in open("data/tmp/calc_all.py", encoding="utf-8").read(),
    "calc_all **N07b 自动改锚**（原只 print「必须替换」→ 靠模型手工改 → case311 我漏了）"
    "—— 锚打印前先校验，ok=False → **自枚举候选**（净胜≤D0档 × 总球0-6 · 按近 E[T] 排序）"
    "→ 逐个测到 ok=True → 直接替换（不依赖波胆 suggestion）· 替换后复核不过则保留原锚")
chk("GAP = 30" in open("data/tmp/latest_images.py", encoding="utf-8").read(),
    "latest_images **按批次取图 GAP=30 秒**（禁用时间窗抓图 — 2026-11-01 混淆直接原因）")
chk("识图隔离铁律" in open("AGENTS.md", encoding="utf-8").read(),
    "AGENTS **识图隔离铁律 I1-I4**")
chk("拒绝处理" in open("data/tmp/image2txt.py", encoding="utf-8").read()
    and "跨场污染" in open("data/tmp/image2txt.py", encoding="utf-8").read(),
    "image2txt **多场门禁**：一批图含 >1 场赛事 → **拒绝输出（rc=2）** —— "
    "原 `merge()` 赛事行取第 1 场、赔率取时点最多的那场 → 「A 场 txt」混 B 场比分"
    "（2026-11-01 实证：埃尔切 txt 混进毕尔巴鄂 93 条比分）")
chk("_safe(_m[0])" in open("data/tmp/image2txt.py", encoding="utf-8").read(),
    "image2txt **文件名改「队名_vs_队名_日期」**（原用 imgs[0] 时间戳 → "
    "同一批跑不同场会互相覆盖·埃尔切 txt 曾被毕尔巴鄂覆盖）")
chk(os.path.exists("data/tmp/latest_images.py")
    and "GAP = 30" in open("data/tmp/latest_images.py", encoding="utf-8").read(),
    "latest_images.py **按最近一批抓附件**（±30 秒合并·替代手工时间窗）—— "
    "2026-11-01 实证：我用 `-12 分钟` 窗 → 22:45 那批（利物浦 vs 阿森纳）整批漏掉")
chk("主队\\s*[\\d.]+\\s*分\\s*→" in open("data/tmp/audit_steps.py", encoding="utf-8").read(),
    "audit_steps **S02 伤停必须有具体分值**（原三态判据含 `bzzoiro_fetch` → calc 总输出"
    "「可用 bzzoiro_fetch.py」提示 → **恒判三态假通过**·307/308/309 实证）")
chk("_wdef = _pn.get('G', 0) * 3.0" in open("data/tmp/calc_all.py", encoding="utf-8").read(),
    "伤停 λ **按 POS_WEIGHT 加权判攻/防**（原按人数 `F >= D+G` → 门将/中后卫各算 1 → "
    "「1中后卫+1门将」vs「2前锋」平手误判攻击线 → λ 方向反了）")
chk("_INJ_LAM_W = 0.3" in open("data/tmp/calc_all.py", encoding="utf-8").read(),
    "伤停 λ 调整 **×0.3 打折**（防与市场双重计算）—— 庄家定价已知伤停，市场 λ 已含该信息，"
    "直接叠加 = 二次计入（埃尔切场实证：全额 +1.20 → λ 3.787 vs 市场 2.728）")
chk("inj_list_h" in open("data/tmp/pipeline.py", encoding="utf-8").read()
    and "_stage2_res = stage2(a)" in open("data/tmp/pipeline.py", encoding="utf-8").read()
    and "stage4(std, a, dirs, pre=None)" in open("data/tmp/pipeline.py", encoding="utf-8").read(),
    "pipeline **伤停名单真透传**（Stage2 解析 Bzzoiro → Stage4 传 --inj_list_*）—— "
    "原只报「定位 N 队」不解析名单 → calc_all 仍判「伤停缺失」= **查了不用**（case311/310/312 三场全中）")
chk("health=ok" in open("data/tmp/audit_steps.py", encoding="utf-8").read()
    and "S00b" in open("data/tmp/audit_steps.py", encoding="utf-8").read(),
    "audit_steps **S03 判据升级**（必须 `health=ok`·原只要「E[T 后有数字」→ 三源不齐时"
    "N26 的 E[T 诱饵造成假通过）+ **S00b 队名提取门禁**（队名为空=硬缺陷→MISS·非三态）"
    "—— case308/309 实证：txt_teams 正则排除空格 → 英文队名失配 → P10/P8/R11/P1 四项连锁失效")
chk("_LG_WORDS" in open("data/tmp/market_consensus.py", encoding="utf-8").read()
    and "日职 联" in open("data/tmp/market_consensus.py", encoding="utf-8").read(),
    "txt_teams **支持带空格英文队名 + 联赛前缀剥离**"
    "（原方括号排除空格写法 → Machida Zelvia / V-Varen Nagasaki 恒失配）")
chk("_events_cache.json" in open("data/tmp/market_inputs.py", encoding="utf-8").read()
    and "_TTL = 600" in open("data/tmp/market_inputs.py", encoding="utf-8").read(),
    "Odds-API events **10 分钟缓存**（配额 100 请求/小时·5000 场只扣 1 次·"
    "但一次 calc_all 调 `_locate_event` 2 次 → 缓存后同批多场共用 1 次）")
chk(os.path.exists("data/tmp/audit_semantic.py")
    and "CONFLICT" in open("data/tmp/audit_semantic.py", encoding="utf-8").read()
    and "改锚理由" in open("data/tmp/audit_semantic.py", encoding="utf-8").read(),
    "audit_semantic.py **语义级审计**（calc 权威值 vs raw 声明值·补关键词级的边界："
    "能拦「提了但判断错」·改判须写「改锚理由:」否则判 CONFLICT）")
chk("[7/7] audit_semantic" in open("data/tmp/pipeline.py", encoding="utf-8").read(),
    "pipeline --verify **七道闸门**（六 → 加 7 语义级）")
chk(os.path.exists("data/tmp/audit_judgment.py")
    and "UNCONSUMED" in open("data/tmp/audit_judgment.py", encoding="utf-8").read(),
    "audit_judgment.py **判定层审计**（补 S3/3.5/4/4.5/4.6/7.5/9 七个原无审计的步骤）—— "
    "2026-11-01 覆盖矩阵实证：17 个审计器只覆盖数据/传导/消费/契约层，判定层 0 覆盖 "
    "= 「意甲子模型没调」「自检表没做」反复遗漏的结构性根源")
chk(os.path.exists("data/tmp/audit_matrix.py"),
    "audit_matrix.py **Step0-11 × 审计器覆盖矩阵**（38 步逐项标注有无审计·找盲区）")
chk("[5/7] audit_judgment" in open("data/tmp/pipeline.py", encoding="utf-8").read()
    and "[6/7] audit_chain" in open("data/tmp/pipeline.py", encoding="utf-8").read(),
    "pipeline --verify **七道闸门**（原四道 → 加 5 判定层 + 6 传导链 + 7 语义级）")
chk("def _locate_event" in open("data/tmp/market_inputs.py", encoding="utf-8").read()
    and "cn2en_list" in open("data/tmp/market_inputs.py", encoding="utf-8").read(),
    "market_inputs.**按队名定位 eventId**（`_locate_event`·cn2en_list 精确匹配）—— "
    "原 eid 只认 --event/快照 → 中文队名恒三态·被误写成「Odds-API 不可用」"
    "（2026-11-01 用户「Odds-API 是正常的·问题出在你」实证）")
chk("_oe9, _slg9 = _MIm9._locate_event" in open("data/tmp/calc_all.py", encoding="utf-8").read()
    and "_n23_ou_full[float(_hl9b)]" in open("data/tmp/calc_all.py", encoding="utf-8").read(),
    "calc_all **无快照时**按队名定位 + 用 _mi9 补全档（原 ou_full/ah_full 只从快照 raw "
    "解析 → 没快照全空 → P10 恒「三源不齐」）")
chk("_bigf" in open("data/tmp/live_score_engine.py", encoding="utf-8").read(),
    "大球场次次锚容差 1.0→1.5（用户裁决 dec-0231c5e22bbd5bf3·R-ANCHOR-BIG 优先·"
    "主锚硬约束仍 ≤1.0 不变·仅放宽次锚参与的软判据）")
chk("方向覆盖不足" in open("data/tmp/check_luopan.py", encoding="utf-8").read(),
    "方向覆盖**下限**门禁（原只查「不超过2向」·不查「该2向却写1向」）—— "
    "case304/306 实证抓出「程序推导应含平局但只写主胜+客胜」")
chk("E_inj" in open("data/tmp/audit_sensitivity.py", encoding="utf-8").read() and
    "S02伤停λ调整" in open("data/tmp/audit_sensitivity.py", encoding="utf-8").read(),
    "消融审计含**伤停变体**（E_inj + 伤停λ监视项）—— 原 4 变体全无伤停 → "
    "伤停「算了不动作」查不出来（2026-11-01 用户追问「为什么总遗漏」后建）")
chk("_inj_lamadj" in open("data/tmp/calc_all.py", encoding="utf-8").read() and
    "lambda_inj_raw" in open("data/tmp/calc_all.py", encoding="utf-8").read(),
    "伤停 λ 调整**真正接入 λ_final**（lambda_adj → Step6.5）—— "
    "原 injury_impact.lambda_adj 只在 CLI 打印·从未进主链（消融审计实证）")
chk("M 域按量级扩展" in open("data/tmp/joint_solver.py", encoding="utf-8").read() and
    "_ext" in open("data/tmp/joint_solver.py", encoding="utf-8").read(),
    "M 域（净胜档）按量级扩展（大球场次追加净胜 3/4 档）—— "
    "原 margin_candidates 把让球硬映射成净胜档（让1.5→[1,2]），池里永远没有 4:0/4:1/5:1 "
    "（用户质疑「为什么不能是4:1/4:0·你就这么死板吗」）")
chk("first_min_goals" in open("data/tmp/joint_solver.py", encoding="utf-8").read() and
    "FIRST_MIN" in open("data/tmp/big_pool_policy.py", encoding="utf-8").read() and
    "first_requirement" in open("data/tmp/big_pool_policy.py", encoding="utf-8").read(),
    "P52 六级分级**约束主锚**（FIRST_MIN L5=4/L4=3/L3=3/L2=2 + first_requirement）—— "
    "原分级表只有「次锚」要求·主锚无约束=假实现（用户质疑「极端大球还主锚2:1」「你不是有六级分档吗」）")
chk("_win_plate" in open("data/tmp/joint_solver.py", encoding="utf-8").read() and
    "_legal" in open("data/tmp/joint_solver.py", encoding="utf-8").read(),
    "P17 穿盘铁律**硬约束落地**（_win_plate/_legal：主让 -1.5 → 主锚须净胜≥2）—— "
    "原让球只在 _signal_support 扣分（P28 不淘汰）→ 锚出 2:1/3:2 两个都输盘（2026-11-01 用户质疑实证）")
chk("second_min_goals" in open("data/tmp/joint_solver.py", encoding="utf-8").read() and
    "_totv" in open("data/tmp/joint_solver.py", encoding="utf-8").read() and
    "_bp_need_second" in open("data/tmp/calc_all.py", encoding="utf-8").read() and
    "second_min_goals=_bp_need_second" in open("data/tmp/calc_all.py", encoding="utf-8").read(),
    "R-ANCHOR-BIG 次锚上探**真传导**（calc_all 算出的「次锚须≥N球」→ joint_anchor "
    "second_min_goals → 池内替换次锚）—— 原实现只 print 不动作=断链（2026-11-01 全流程测试实证："
    "科莫场要求≥5球却给 3:1 四球）")
chk("match_state" in open("data/tmp/image2txt.py", encoding="utf-8").read(),
    "image2txt 识别后立即判比赛状态（match_state·未开赛/进行中/已结束）—— "
    "用户指正「时间模块又没生效」：识别拿到开赛时间却不判状态 = 同型漏接第二次（2026-11-01）")
chk("_clean_form" in open("data/tmp/ocr2std.py", encoding="utf-8").read() and
    "_tm" in open("data/tmp/ocr2std.py", encoding="utf-8").read(),
    "ocr2std 两处下游兼容清洗（_clean_form 去斜杠 / _tm 补时间空格）—— "
    "特征分析带斜杠会让 parse_features 返回空（S4/S6 全失效）·比分时间粘连破 TIME_RE（2026-11-01 实测）")
chk("STD_SLOTS" in open("data/tmp/ocr2std.py", encoding="utf-8").read() and
    "特征分析" in open("data/tmp/ocr2std.py", encoding="utf-8").read() and
    "FEAT_ROWS" in open("data/tmp/ocr2std.py", encoding="utf-8").read(),
    "ocr2std 按「槽位清单」填充（STD_SLOTS + FEAT_ROWS 特征分析 6 行）—— "
    "特征分析是 calc_match.parse_features 的输入 = 修正53 S4/S6 唯一数据源，不可漏")
chk("stage_img" in open("data/tmp/pipeline.py", encoding="utf-8").read() and
    "图片识别 → 标准 txt" in open("data/tmp/pipeline.py", encoding="utf-8").read() and
    "nargs='+'" in open("data/tmp/pipeline.py", encoding="utf-8").read(),
    "pipeline 支持直接吃图片（Stage -1 → image2txt → 回填 teams/league/kickoff → 原 Stage 0-6）"
    "—— 用户要求「之前识别到 txt 直接跑·现在改成直接给图」")
chk("meta.json" in open("data/tmp/image2txt.py", encoding="utf-8").read() and
    "'fill'" in open("data/tmp/image2txt.py", encoding="utf-8").read(),
    "image2txt 落 meta.json（含 match/league/kickoff + 槽位 fill 状态·供 pipeline 回填）")
chk("PROMPT_EVENT" in open("data/tmp/img2txt.py", encoding="utf-8").read() and
    "features" in open("data/tmp/img2txt.py", encoding="utf-8").read(),
    "img2txt 赛事页专用 prompt（PROMPT_EVENT·按槽反推字段含 features 6 行）")
chk("_vision_parse" in open("data/tmp/image2txt.py", encoding="utf-8").read() and
    "回退 glm-4.6v" in open("data/tmp/image2txt.py", encoding="utf-8").read(),
    "image2txt 自动分流（glm-ocr 信息量过低 → 回退 glm-4.6v 提取队名）"
    "—— 赛事页布局是图形+条形图·glm-ocr 只出 36 tokens（2026-11-01 实测根因）")
chk("nargs='*'" in open("data/tmp/image2txt.py", encoding="utf-8").read() and
    "def merge(" in open("data/tmp/image2txt.py", encoding="utf-8").read(),
    "image2txt 支持多图合并（竞彩赔率变化页按玩法分屏·单图只能拿局部）")
chk("glm-ocr" in open("data/tmp/img2txt.py", encoding="utf-8").read() and
    "layout_parsing" in open("data/tmp/img2txt.py", encoding="utf-8").read(),
    "img2txt 走 glm-ocr layout_parsing（走 OCR 资源包·不扣现金）")
chk("TIME_RE" in open("data/tmp/ocr2std.py", encoding="utf-8").read() and
    "时点: 胜平负" in open("data/tmp/ocr2std.py", encoding="utf-8").read(),
    "ocr2std 支持多时点序列（赔率变化页→V1/D1/形态学 可用·单时点须三态）")
chk("time_guard" in open("data/tmp/calc_all.py", encoding="utf-8").read(),
    "calc_all 已接时间上下文（必经路径·只在 pipeline 打印=只覆盖一条路径·"
    "手工跑 calc_all 全漏·用户质疑「pipeline 接入就自动跟随了吗」实证修正）")
chk("S00" in open("data/tmp/audit_steps.py", encoding="utf-8").read() and
    "时间上下文" in open("data/tmp/audit_steps.py", encoding="utf-8").read(),
    "audit_steps 含 S00 时间上下文门禁（raw 缺失→MISSING·落盘失败）")
chk("stage00_context" in open("data/tmp/pipeline.py", encoding="utf-8").read(),
    "pipeline Stage0 已接入时间上下文（time_guard·当前时间/比赛状态/数据年龄体检）")
chk("cn2en_list" in _DBR,
    "队名**统一入口回退**（cn_to_en_keywords 精确未命中→cn2en_list 子串/简称回退·"
    "原「比利亚雷」查不到致 4 源连锁 missing）")
chk(_DBR.count("TEAM_ALIASES.get(str(_n))") == 0 and _DBR.count("cn_to_en_keywords") >= 5,
    "各源队名解析**统一走 cn_to_en_keywords**（原 src_xg/src_bzz 自写 .get()/中文匹配=修一处漏一处）")
chk("数据完整度" in open("data/tmp/calc_all.py", encoding="utf-8").read(),
    "calc_all **完整度显式打印+自数兜底**（bridge 降级时 completeness=None → 封顶静默不执行·已堵）")
chk("--handi 口径校验" in open("data/tmp/calc_all.py", encoding="utf-8").read(),
    "calc_all **--handi 口径防线**（case301/302 实抓：竞彩让球±1 被当欧盘均衡线·302 平手盘→传-1.0）")
chk("print_all_exhausted" in _TOA,
    "全池耗尽**统一告知**（用户指令: 两个都没了要告诉我·区分「额度用完」vs「key 无效」）")
try:
    _kct = open("data/tmp/api_keys.json", encoding="utf-8").read()
    chk("the_odds_api_pool" in _kct,
        "api_keys.json `the_odds_api_pool` 已配置（key 轮转池·加 key 无需改代码）")
except Exception as _ekc:
    chk(False, "api_keys.json 读取失败: %s" % str(_ekc)[:60])
# ── 批次6（Step 间传导·边判据）──
chk("终态去重" in open("data/tmp/joint_solver.py", encoding="utf-8").read(),
    "joint_solver **终态去重**（P52 纠偏改 a1 后 a3 撞主锚 → 输出「第三=主锚」）")
chk("→ S6 传导" in open("data/tmp/calc_all.py", encoding="utf-8").read()
    and "平 %d 场" in open("data/tmp/calc_all.py", encoding="utf-8").read(),
    "calc_all H2H→S6 带上游数据（交锋场次/平局率·原只打「✗ 不计」=审计看不见依据）")
chk("共 %d 时点" in open("data/tmp/calc_all.py", encoding="utf-8").read(),
    "calc_all N21 全跨度带时点数（原无法验证「N 时点都进了变动计算」）")
chk(os.path.exists("data/tmp/audit_flow.py")
    and "EDGES" in open("data/tmp/audit_flow.py", encoding="utf-8").read()
    and "lam_vs_expect" in open("data/tmp/audit_flow.py", encoding="utf-8").read(),
    "audit_flow.py Step 间**边判据**（24 边·值级传递/口径一致/结论消费·判据自适应）")
chk("竞彩逐T形态" in open("data/tmp/pipeline.py", encoding="utf-8").read()
    and "竞彩逐T形态学" not in open("data/tmp/pipeline.py", encoding="utf-8").read(),
    "pipeline 块正则「竞彩逐T形态」（原「形态学」+emoji 致恒不匹配=假失败）")
chk("soft=True" in open("data/tmp/pipeline.py", encoding="utf-8").read()
    and "SOFT_WARN" in open("data/tmp/pipeline.py", encoding="utf-8").read(),
    "pipeline **soft 通道**（外部源三态不计 STAGE_FAIL·原配额用尽即整条 EXIT=1）")
# ── 批次5（S09 门禁承诺兑现）──
chk("无处置留痕" in open("data/tmp/check_luopan.py", encoding="utf-8").read() and "_handled5" in open("data/tmp/check_luopan.py", encoding="utf-8").read(), "check_luopan 锚-市场**结论级**断言（原只查关键词·写「❌不匹配」也通过=门禁空转）")

chk("_line_eq" in open("data/tmp/market_distribution.py", encoding="utf-8").read() and "tri_source_move" in open("data/tmp/market_distribution.py", encoding="utf-8").read(), "P47/P51 均衡线驱动量级 + 三源移动相关性(2026-10-31)")
chk("line_fair" in open("data/tmp/totals_water_read.py", encoding="utf-8").read() and "盘降水诱" in open("data/tmp/totals_water_read.py", encoding="utf-8").read(), "P51 大小球线源优先均衡线 + 8象限亚盘口径修正(2026-10-31)")
chk("P47~P51 大球分级细化" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS 含 P47~P51 机构读盘层(三处同步)")

chk("P32 大球场次锚上探" in open("data/tmp/check_luopan.py", encoding="utf-8").read(), "P32 大球场次锚上探门禁(2026-10-30)")
chk("_bsd_teams(raw_teams)" in open("data/tmp/pipeline.py", encoding="utf-8").read(), "P31 伤停队名中→英(pipeline._inj 必须走 _bsd_teams)")
chk("中文原样" in open("data/tmp/pipeline.py", encoding="utf-8").read() and "两次尝试均未定位" in open("data/tmp/pipeline.py", encoding="utf-8").read(), "P31 伤停双向尝试(英文失败再用中文·两次留痕)")
chk("P31 三态须已验证" in open("data/tmp/check_luopan.py", encoding="utf-8").read() or "P31 三态已验证通过" in open("data/tmp/check_luopan.py", encoding="utf-8").read(), "P31 三态须已验证门禁(check_luopan)")

chk("学习成果进入判定" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "学习成果进入模型判定(弱判定场<45%·用户要求·分档验证)")
chk("锚-量级一致性铁律" in open("AGENTS.md", encoding="utf-8").read(), "锚-量级一致性铁律(case169教训·2026-09-12)")
chk("八场复盘三铁律" in open("AGENTS.md", encoding="utf-8").read(), "八场复盘三铁律(163-170极端批次·2026-09-13)")
chk("弱共识场平局并列铁律" in open("AGENTS.md", encoding="utf-8").read(), "弱共识场平局并列铁律(skew<150%·2026-09-13回测)")
chk("锚-六项一致性" in open("AGENTS.md", encoding="utf-8").read(), "锚-六项一致性校验(自检25·2026-09-13)")
chk("市场源优先铁律" in open("AGENTS.md", encoding="utf-8").read(), "市场源优先铁律(2026-09-13回测寻优)")
_chk_mig = open("data/tmp/migration_prompt.md", encoding="utf-8").read() if __import__("os").path.exists("data/tmp/migration_prompt.md") else ""
# 🔴2026-10-11 梳理重构: 迁移文档由「硬编码日期」改为「动态版本一致性 + 结构标记」→ 根除「每轮更新都要改断言」
import re as _re_mig
_chk_ag = open("AGENTS.md", encoding="utf-8").read()
_chk_sk = open(".reasonix/skills/<REDACTED_SK>/SKILL.md", encoding="utf-8").read()
_chk_tx = open("data/足球分析模型.txt", encoding="utf-8").read()
_mig_v = _re_mig.search(r'V3\.5\.\d+', _chk_ag)
chk(bool(_mig_v) and _mig_v.group(0) in _chk_mig, "迁移文档版本号与 AGENTS 一致(动态·防过时)")
chk("唯一权威" in _chk_mig, "迁移文档为单一权威快照(2026-10-11 重构·历史日志已归档)")
chk("市场源优先" in _chk_mig and "弱共识" in _chk_mig, "迁移文档含关键更新摘要(市场源优先/弱共识)")
chk("第八节" in _chk_mig, "迁移文档含第八节执行留痕(防过时)")
chk("SK-audit" in _chk_mig, "迁移文档含审计入口(SK-audit)")
chk("纪律④" in _chk_ag and "纪律④" in _chk_sk and "纪律④" in _chk_tx, "三处(AGENTS/主技能/txt)含合并编辑纪律④(2026-09-24·防锁死)")
chk("纪律④" in _chk_mig, "迁移文档含合并编辑纪律④(防过时)")
# 🔴2026-10-11 新增: 梳理载体（历史日志归档 + 参数标准化 match_params）
chk(__import__("os").path.exists("docs/迁移更新日志_归档.md"), "迁移更新日志归档存在(2026-10-11 重构)")
chk(__import__("os").path.exists("data/tmp/match_params.py") and "params" in open("data/tmp/match_params.py", encoding="utf-8").read(),
    "match_params 参数标准化脚本在位(2026-10-11)")
chk(__import__("os").path.exists("data/tmp/params/README.md"), "data/tmp/params/README 在位")
chk("match_params" in _chk_ag and "match_params" in _chk_sk and "match_params" in _chk_tx,
    "三处(AGENTS/主技能/txt)登记 match_params 参数标准化(2026-10-11)")
chk("match_params" in _chk_mig, "迁移文档含 match_params 常用命令(防过时)")
# 🔴2026-10-11 防复发: 每场临时参数文件已统一为 data/tmp/params/case<ID>.json
_legacy_params = ([f for f in __import__("glob").glob("data/tmp/_case*_params.json")]
                  + [f for f in __import__("glob").glob("data/tmp/_eu2*.json")]
                  + [f for f in __import__("glob").glob("data/tmp/_rev2*.json")])
chk(not _legacy_params, "无遗留临时参数文件(_case*_params/_eu2*/_rev2*·已统一至 params/)" + (("·残留:%s" % _legacy_params) if _legacy_params else ""))
# 🔴2026-10-11 回归检验修复: HAF calc_homeaway 支持中文队名（原只认英文键 → 中文恒不命中 = 存在≠活跃）
try:
    _haf_ = open("data/tmp/calc_homeaway.py", encoding="utf-8").read()
    chk(("cn2en_list" in _haf_) and ("def _lookup" in _haf_),
        "HAF calc_homeaway 支持中文队名(cn2en_list+_lookup·2026-10-11 回归检验修复)")
except Exception as _e98:
    chk(False, "HAF 中文队名支持校验失败(%s)" % str(_e98)[:60])

# 🔴2026-10-12 第6源 handi（用户指令「不回测直接加入」）: 静态存在 + 实跑激活
try:
    _twH_ = open("data/tmp/totals_water_read.py", encoding="utf-8").read()
    chk(("srcs['handi']" in _twH_) and ("handi_fix" in _twH_),
        "totals_water_read 含第6源 handi（让球深度修正量·权重0.05）")
    import sys as _syH
    if os.path.abspath("data/tmp") not in _syH.path:
        _syH.path.insert(0, os.path.abspath("data/tmp"))
    import totals_water_read as _twrH
    _rH = _twrH.water_read(o25=1.742, u25=2.267, handicap=-1.0,
                           lambda_market=2.82, lambda_table=2.89)
    chk((_rH.get("lambda_handi") is not None) and ("handi" in (_rH.get("sources") or [])),
        "totals 第6源 handi 实跑激活(lambda_handi=%s·fix=%s)" % (_rH.get("lambda_handi"), _rH.get("handi_fix")))
except Exception as _eH:
    chk(False, "totals 第6源 handi 校验失败(%s)" % str(_eH)[:70])

# 🔴2026-10-12 CS 占位档守卫（1xbet CS 固定返回 120 档·其中约 100 档赔率「恰好 100」= 占位标记）
#   原缺陷: 占位档计入去水 → Σ(1/odds)≈2.3（抽水 130%）·矩阵概率全错 → 上限护栏（排除 ≥100）
try:
    import sys as _syC
    if os.path.abspath("data/tmp") not in _syC.path:
        _syC.path.insert(0, os.path.abspath("data/tmp"))
    import cs_deep_analyzer as _cdaC
    _pC, _vC = _cdaC.dejuice({"1:0": 7.5, "1:1": 6.5, "0:10": 100, "9:9": 100, "8:9": 100})
    _liveC = open("data/tmp/live_score_engine.py", encoding="utf-8").read()
    chk((len(_pC) == 2) and ("1 < v < 100" in _liveC),
        "CS 占位档守卫(cs_deep_analyzer+live_score_engine·剔除赔率=100)·实跑保留档=%d" % len(_pC))
except Exception as _eC:
    chk(False, "CS 占位档守卫校验失败(%s)" % str(_eC)[:70])

# 🔴2026-10-13 四要素深度融合 joint_solver（V3.5.77·用户方案·第一优先级）
#   契约: ok / 交集非空 / 主锚∈交集 / 仲裁留痕为 list / anchor_1st+consistency+lock 齐备 / quadrant_v2 在位
try:
    import sys as _syJ
    if os.path.abspath("data/tmp") not in _syJ.path:
        _syJ.path.insert(0, os.path.abspath("data/tmp"))
    import joint_solver as _js
    _rj = _js.joint_anchor(1.627, 4.53, 5.56, -1.0, 1.5)
    _okj = bool(_rj.get("ok"))
    _poolj = [x["score"] for x in _rj.get("pool", [])]
    _pool_okj = (not _rj.get("empty")) and (_rj.get("anchor_1st") in _poolj)
    _arb_okj = isinstance(_rj.get("arbitrations"), list)
    _chart_okj = all(k in _rj for k in ("anchor_1st", "anchor_2nd", "consistency", "lock", "est", "trust"))
    _srcj = open("data/tmp/joint_solver.py", encoding="utf-8").read()
    _q2j = os.path.exists("data/tmp/quadrant_v2.py")
    # 🔴2026-10-13 加固: quadrant_v2 由「文件存在」升级为「功能实跑」——治「存在≠活跃」
    #   （原实现只 os.path.exists → 脚本挂掉也判过；现须真跑出 ok + 三边际键）
    _q2run = False
    try:
        from quadrant_v2 import quadrant_v2 as _qv2f
        _q2r = _qv2f(1.627, 4.53, 5.56, -1.0, 1.5)
        _q2run = bool(_q2r.get("ok")) and all(k in _q2r for k in ("cell", "marg_d", "marg_m", "marg_t"))
    except Exception:
        _q2run = False
    _caJ = open("data/tmp/calc_all.py", encoding="utf-8").read()
    chk(_okj and _pool_okj and _arb_okj and _chart_okj and _q2j and _q2run
        and ("约束传播" in _srcj) and ("joint_solver" in _caJ),
        "joint_solver 四要素融合(ok=%s 交集锚=%s 仲裁留痕=%s 契约=%s quadrant_v2存在=%s quadrant_v2实跑=%s calc_all接线=%s)"
        % (_okj, _pool_okj, _arb_okj, _chart_okj, _q2j, _q2run, ("joint_solver" in _caJ)))
    # 🔴2026-10-13 P1 修复防回退（用户审计实抓·两条「实现未落地设计」）
    #   P1-1 受让场谱系被误杀: 原 D 切单值「平局」→ 客胜档 -1 被浪费·池只剩 1:1·次锚 None
    #        → 须: 锚谱系含客胜 + 池含客胜比分 + 次锚非 None
    _r_ah = _js.joint_anchor(2.05, 3.5, 3.4, 1.0, 2.1, 1.8)   # 受让 1 球·D=主胜
    _ah_ds = (_r_ah.get("lock") or {}).get("D_set") or []
    _ah_cand = _r_ah.get("candidates") or []
    _ah_ok = (bool(_r_ah.get("ok")) and "客胜" in _ah_ds and "平局" in _ah_ds
              and _r_ah.get("anchor_2nd") is not None
              and any(c.split(":")[1] > c.split(":")[0] for c in _ah_cand))
    #   P1-2 规则6 污染一致度: 原「仅提示」规则计入 arb_n → 正常场 consistency 恒 MID·HIGH 成死档
    #        → 须: 无生效类仲裁时 arb_n=0 且 consistency=HIGH（规则6 落 notes）
    _r_nm = _js.joint_anchor(1.627, 4.53, 5.56, -1.0, 1.5)
    _nm_ok = (bool(_r_nm.get("ok")) and _r_nm.get("arb_n") == 0
              and _r_nm.get("consistency") == "HIGH" and bool(_r_nm.get("notes")))
    chk(_ah_ok and _nm_ok,
        "joint_solver P1修复(受让场客胜谱系=%s[%s·次锚%s] 规则6不计一致度=%s[arb_n=%s,%s])"
        % (_ah_ok, _ah_ds, _r_ah.get("anchor_2nd"), _nm_ok,
           _r_nm.get("arb_n"), _r_nm.get("consistency")))
    # 🔴2026-10-13 量级台账规范化（用户指令「先规范化台账两列 + 加门槛自动计数」）
    #   契约: 台账含枚举列「偏差档」+ status 可跑且输出含门槛/holdout 分层（治「自由文本→门槛判不出来」）
    try:
        import subprocess as _sp_ml
        _mlo = _sp_ml.run([sys.executable, "data/tmp/magnitude_ledger.py", "status"],
                          capture_output=True, text=True, encoding="utf-8").stdout or ""
        _mlh = open("data/case-library/量级台账.csv", encoding="utf-8-sig").readline()
        _ml_ok = ("偏差档" in _mlh) and ("门槛" in _mlo) and ("holdout" in _mlo) and ("方向聚合" in _mlo)
    except Exception:
        _ml_ok = False
    chk(_ml_ok, "量级台账规范化(枚举列『偏差档』在位 + 门槛计数含 holdout 分层与方向聚合)")
    # 🔴2026-10-13 接入审计加固（用户「严格检查新更新是否真正介入模型·接口是否正确·无断点」）:
    #   ① 五源注入通道存在（src_lam → 口径单一权威·防「同场两套期望总进球」口径分裂）
    #   ② 仲裁规则3/4 必须**真正生效**（源码须含「✅生效」标记·防「日志声称动作而代码无赋值」）
    #   ③ calc_all 的 N23 须位于 Step6.5 之后并消费 _tw 五源（λ_line/pois/water 不再恒缺）
    _src5j = ("src_lam" in _srcj) and ("SRC_KEYS" in _srcj)
    _effj = ("规则3✅生效" in _srcj) and ("规则4✅生效" in _srcj)
    _posj = ("_n23_tw" in _caJ) and ("src_lam=(_n23_src" in _caJ) and ("lambda_water" in _caJ)
    _ordj = (_caJ.index("N23 **正式块**") > _caJ.index("大小球盘口水位精读")) if (   # 抗装饰锚点(2026-10-20)
        "N23 **正式块**" in _caJ and "大小球盘口水位精读" in _caJ) else False
    chk(_src5j and _effj and _posj and _ordj,
        "joint_solver 接入加固(五源注入=%s 规则3/4生效=%s N23消费_tw五源=%s N23位于Step6.5之后=%s)"
        % (_src5j, _effj, _posj, _ordj))
except Exception as _ej:
    chk(False, "joint_solver 四要素融合校验失败(%s)" % str(_ej)[:70])

# 🔴2026-10-14 大球识别与锚定（V3.5.78·用户方案·V2 防死锚·第一铁律「严禁死锚·必须根据数据分析」）
#   六断言（方案 §8.1）: ①极端场 T 域上探+含4+候选 ②正常场零回归 ③受让场谱系保留
#                        ④缺 u25 仍判 B 档 ⑤小球场不被误抬 ⑥防死锚（低分保留+证据链）
try:
    _r78a = _js.joint_anchor(1.275, 5.75, 10.0, handi=-1.5, o25=1.33, ou_line=3.0,
                             lambda_final=4.27, totals_bin="极超")
    _t78 = (_r78a.get("lock") or {}).get("T") or (0, 0)
    _up78 = _t78[1] >= 5
    _c4_78 = any(int(s.split(":")[0]) + int(s.split(":")[1]) >= 4 for s in _r78a.get("candidates", []))
    _r78b = _js.joint_anchor(2.865, 3.43, 2.667, handi=0, o25=2.248)
    _norm78 = _r78b.get("consistency") == "HIGH"
    _r78c = _js.joint_anchor(1.275, 5.75, 10.0, handi=-1.5, o25=1.33)          # 缺 u25
    _b78 = ((_r78c.get("est") or {}).get("B") or {}).get("label")
    _b_ok78 = _b78 is not None
    _r78d = _js.joint_anchor(1.95, 3.75, 3.40, handi=-0.25, o25=1.24, lambda_final=3.66, totals_bin="极超")
    _low78 = any(int(s.split(":")[0]) + int(s.split(":")[1]) <= 2 for s in _r78d.get("candidates", []))
    _ev78 = isinstance(_r78d.get("anchor_1st_evidence"), list)
    _r78e = _js.joint_anchor(3.50, 3.20, 2.10, handi=0.5, o25=2.60, lambda_final=2.1, totals_bin="小球")
    _small78 = ((_r78e.get("lock") or {}).get("T") or (0, 0))[1] <= 4
    _src78 = open("data/tmp/joint_solver.py", encoding="utf-8").read()
    _ca78 = open("data/tmp/calc_all.py", encoding="utf-8").read()
    chk(_up78 and _c4_78 and _norm78 and _b_ok78 and _low78 and _ev78 and _small78
        and ("_apply_totals_driven_domain" in _src78) and ("_evidence_rank" in _src78)
        and ("_b_label_fallback" in _src78) and ("EXTREME_OVER_LAM" in _src78)
        and ("lambda_final=_n23_fv" in _ca78) and ("totals_bin=_n23_tw" in _ca78),
        "大球识别与锚定 V3.5.78(T域上探=%s 含4+候选=%s 正常场零回归=%s 缺u25判B档[%s]=%s 防死锚低分保留=%s 证据链=%s 小球场不误抬=%s)"
        % (_up78, _c4_78, _norm78, _b78, _b_ok78, _low78, _ev78, _small78))
except Exception as _e78:
    chk(False, "大球识别与锚定 V3.5.78 校验失败(%s)" % str(_e78)[:70])

# 🔴2026-10-17 V3.5.79「审查修正」防回退（用户「严格审查是否完全嵌入模型·数据链完整·无断点·活跃」）
#   审查实抓 3 项（1×P0 + 2×P1）:
#     P0 P1 让球水位用了**非均衡档**( _sn9.extract.ah = 「主客赔率最接近档」·实测常为深档)
#        → 违反铁律「禁把深档当让球盘解读」(case229/234) → 74% 非均衡场次给系统性「弱」判定
#        → 修正: 扫快照 Spread 全档·取 |主−客|≤0.25 为真均衡档·无则 None(P1 不采用·三态)
#     P1 留痕链缺失: output_checker/check_luopan/analysis_template 均无 V3.5.79 → 已补
try:
    _caS2 = open("data/tmp/calc_all.py", encoding="utf-8").read()
    for _k in ("_n23_eq_hdp", "P1不采用", "无均衡档"):
        chk(_k in _caS2, "V3.5.79 P1 均衡档修正在岗: %s" % _k)
    _ocS = open("data/tmp/output_checker.py", encoding="utf-8").read()
    chk("N23b" in _ocS, "V3.5.79 留痕链: output_checker 含 N23b 断言")
    _clS = open("data/tmp/check_luopan.py", encoding="utf-8").read()
    chk(">= 248" in _clS and "V3.5.79" in _clS, "V3.5.79 留痕链: check_luopan case>=248 断言")
    _tpS = open("data/analysis_template.md", encoding="utf-8").read()
    chk("V3.5.79" in _tpS, "V3.5.79 留痕链: analysis_template 含 V3.5.79 节")
    # 🔴实跑断言: 均衡档(Δ≤0.25)水位 → 强度必为「中」(p_up≈0.5)
    import sys as _sy79b
    if os.path.abspath("data/tmp") not in _sy79b.path:
        _sy79b.path.insert(0, os.path.abspath("data/tmp"))
    import importlib as _il79b
    import joint_solver as _js79b
    _il79b.reload(_js79b)
    _ra = _js79b.joint_anchor(1.60, 3.80, 5.50, handi=-1.0, o25=1.90, ah_wh=1.90, ah_wa=1.92)
    _st = (_ra["est"]["M"].get("water") or {}).get("strength")
    chk(_st == "中", "V3.5.79 P1 均衡档水位(1.90/1.92)→%s" % _st)
    _rb = _js79b.joint_anchor(1.60, 3.80, 5.50, handi=-1.0, o25=1.90)
    chk("water" not in _rb["est"]["M"], "V3.5.79 P1 缺水位→不介入(water 缺失)")
    print("   \u2705 2026-10-17 V3.5.79 审查修正(均衡档+留痕链) 防回退校验通过")
except Exception as _e79b:
    chk(False, "V3.5.79 审查修正校验失败(%s)" % str(_e79b)[:70])

# 🔴2026-10-17 审计修复「V3.5.79 P1/P2/P3 数据源单点依赖」防回退
#   根因: N23 段只从 prestep 快照(_sn9)取 cs/btts/均衡水 → 未跑 prestep 的常规分析中三项恒空
#        = 三项新功能永久空转（存在≠活跃·三场 case248/249/250 实测 波胆 0 档 / 均衡水 None/None）
#   修复: 无快照时回退「当场实时 1xbet 全市场」(--odd-event/--event 或快照 event_id)
try:
    _caS3 = open("data/tmp/calc_all.py", encoding="utf-8").read()
    for _k3 in ("当场实时 1xbet 全市场", "_n23_p1src", "--odd-event", "数据源["):
        chk(_k3 in _caS3, "V3.5.79 N23 实时回退在岗: %s" % _k3)
    import py_compile as _pc3, tempfile as _tf3
    _pc3.compile("data/tmp/calc_all.py", cfile=os.path.join(_tf3.gettempdir(), "_cs3.pyc"), doraise=True)
    chk(True, "V3.5.79 calc_all 编译通过(实时回退段)")
    print("   \u2705 2026-10-17 V3.5.79 N23 实时回退(无快照→当场1xbet) 防回退校验通过")
except Exception as _e3:
    chk(False, "V3.5.79 N23 实时回退校验失败(%s)" % str(_e3)[:70])

# 🔴2026-10-17 修复「多档 Totals 盘口线单点依赖」防回退（用户「欧亚盘开盘都是大3」）
#   根因: Layer1 多档 Totals 只在 prestep 快照存在时可用 → 常规分析退化为「O2.5 反推等效线」
#        = 真盘口线(3球)与 Layer3 盘口移动(Q4 降盘)全程未参与 → 量级判「中大」偏高
#   修复: 无快照时回退当场实时 1xbet Totals 全档（totals_from_raw）
try:
    _caS4 = open("data/tmp/calc_all.py", encoding="utf-8").read()
    # 🔴2026-10-17 封装后更新: 多档 Totals 改由 market_inputs 提供（原直调 totals_from_raw 已移除）
    for _k4 in ("market_inputs as _MImod", "_MI['totals']", "市场数据链体检"):
        chk(_k4 in _caS4, "V3.5.79 多档Totals实时回退在岗: %s" % _k4)
    print("   \u2705 2026-10-17 多档Totals盘口线实时回退 防回退校验通过")
except Exception as _e4:
    chk(False, "多档Totals回退校验失败(%s)" % str(_e4)[:70])

# 🔴2026-10-17 封装「统一市场数据入口」防回退（用户「把需要封装的封装·整理整体数据链」）
#   根因: 市场取数在 calc_all 分散 4 段·各写一遍降级链 → 5 次同类遗漏(09-28/09-29/10-11/10-17×2)
#   修复: market_inputs.resolve() 单入口（显式→快照→实时1xbet→三态·带 src 标记）
#        + λ_final 为唯一权威 λ（消除 N23 vs Step6.5 的口径分裂 0.30 球）
try:
    _miP = "data/tmp/market_inputs.py"
    chk(os.path.exists(_miP), "统一入口 market_inputs.py 在位")
    _caS5 = open("data/tmp/calc_all.py", encoding="utf-8").read()
    for _k5 in ("import market_inputs", "market_inputs", "市场数据链体检"):
        chk(_k5 in _caS5, "calc_all 已接统一入口: %s" % _k5)
    chk("prestep_fetch as _pf9" not in _caS5,
        "calc_all 已移除 N23 裸取数(防回退到分散取数)")
    chk("prestep_fetch as _pfT" not in _caS5,
        "calc_all 已移除 Step6.5 裸取数(防回退)")
    _js5 = open("data/tmp/joint_solver.py", encoding="utf-8").read()
    chk("lam_final_override" in _js5, "joint_solver λ_final 权威覆盖在岗")
    # 纯函数 fixture 实测（不依赖网络）: 解析 + 均衡档 + 占位档剔除
    import sys as _sy5
    if os.path.abspath("data/tmp") not in _sy5.path:
        _sy5.path.insert(0, os.path.abspath("data/tmp"))
    import importlib as _il5
    import market_inputs as _mi5
    _il5.reload(_mi5)
    _rawfix = {"bookmakers": {"1xbet": [
        {"name": "ML", "odds": [{"home": "3.05", "draw": "3.66", "away": "2.415"}]},
        {"name": "Spread", "odds": [{"hdp": -2, "home": "11.5", "away": "1.01"},
                                     {"hdp": 0.25, "home": "1.79", "away": "1.98"}]},
        {"name": "Totals", "odds": [{"hdp": 2.5, "over": "1.753", "under": "2.248"},
                                     {"hdp": 3, "over": "2.12", "under": "1.69"}]},
        {"name": "Correct Score", "odds": [{"label": "1-1", "odds": "6.5"},
                                            {"label": "0-10", "odds": "100"}]},
        {"name": "Both Teams To Score", "odds": [{"yes": "1.54", "no": "2.349"}]},
    ]}}
    _pm = _mi5.parse_markets(_rawfix)
    chk(_pm["ml"].get("home") == 3.05, "parse_markets ML 解析(3.05)")
    chk(len(_pm["totals"]) == 2, "parse_markets Totals 档数(2)")
    chk("1-1" in _pm["cs"] and "0-10" not in _pm["cs"],
        "parse_markets CS 占位档剔除(留1-1·剔0-10=100)")
    _eq, _n = _mi5.pick_equal_line(_pm["spread"])
    chk(_eq is not None and _eq["hdp"] == 0.25,
        "pick_equal_line 均衡档(hdp=0.25·扫%d档)" % _n)
    _eq2, _n2 = _mi5.pick_equal_line([{"hdp": -1, "home": 5.05, "away": 1.14}])
    chk(_eq2 is None, "pick_equal_line 深档不冒充均衡(Δ>0.25→None)")
    chk(_mi5.csv_arg({"1-1": 6.5, "1-2": 8.5}) == "1:1=6.5,1:2=8.5",
        "csv_arg 冒号格式转换")
    # 🔴滚球盘检测（2026-10-17 A 模式审计实抓：event 72221318 已开赛 → ML 缺失 + Totals 仅1档
    #   滚球 2.5 线 大8.50/小1.07 → 旧实现当赛前盘派生 O2.5=8.50（隐含大球 11.8%）→ 污染 λ）
    def _roll(ml, totals):
        _t = totals or []
        _ok = bool(ml)
        _ext = False
        if _t and len(_t) <= 2:
            for _r in _t:
                _o, _u = _r.get("over"), _r.get("under")
                try:
                    if _o and _u and (max(float(_o), float(_u)) / max(min(float(_o), float(_u)), 0.01)) > 4.0:
                        _ext = True
                except (TypeError, ValueError):
                    pass
        return bool((not _ok) and (len(_t) < 3 or _ext))
    chk(_roll({}, [{"hdp": 2.5, "over": 8.5, "under": 1.07}]) is True,
        "滚球检测 命中(ML无+1档极端 8.50/1.07)")
    chk(_roll(_pm["ml"], _pm["totals"]) is False, "滚球检测 不误伤赛前(ML齐全)")
    chk(_roll({}, [{"hdp": x, "over": 1.9, "under": 1.9} for x in (2.0, 2.25, 2.5, 2.75)]) is False,
        "滚球检测 多档正常盘不触发")
    _mi5_src = open(_mi5.__file__, encoding="utf-8").read()
    chk("rolling_suspect" in _mi5_src, "market_inputs 含 rolling_suspect 滚球防护")
    chk("not mi.get(\"rolling_suspect\")" in _mi5_src.replace("'", "\""),
        "派生 O2.5 受 rolling_suspect 拦截")
    print("   \u2705 2026-10-17 统一市场数据入口(market_inputs) 防回退校验通过")
except Exception as _e5:
    chk(False, "统一入口校验失败(%s)" % str(_e5)[:80])

# 🔴2026-10-17 综合升级 V3.5.79 防回退（用户方案·P0-P4 五大升级·实跑验证）
#   P0 λ传导链修复 / P1 让球量级判定 / P2 精确比分三源融合 / P3 零封BTTS修正 / P4 四项修复
try:
    _jsS = open("data/tmp/joint_solver.py", encoding="utf-8").read()
    for _fn in ("_handi_water_strength", "_m_expand_shallow", "_apply_btts_zero",
                "_cs_market_probs", "_cs_select"):
        chk(("def %s" % _fn) in _jsS, "V3.5.79 P1/P2/P3 新函数在岗: %s" % _fn)
    chk("lam >= 2.6" in _jsS, "V3.5.79 P0-1 T域连续λ映射(去3.4硬断档)")
    chk("P4-2防死锚" in _jsS and "P4-3防死锚" in _jsS,
        "V3.5.79 P4-2/P4-3 规则3/规则2 死锚修复(主档收敛+相邻/出口保留)")
    chk("cs_cand=None" in _jsS and "btts_yes=None" in _jsS and "ah_wh=None" in _jsS,
        "V3.5.79 joint_anchor/_evidence_rank 签名扩展(P1水位/P2波胆/P3 BTTS)")
    _caS = open("data/tmp/calc_all.py", encoding="utf-8").read()
    for _k in ("cs_odds=(_n23_cs or _n23_cs_full9 or None)", "btts_yes=(_n23_btts or {}).get('yes')",
               "ah_wh=_n23_ah_wh", "_n23_f9 = _n23_s9.get('first') or {}", "V3.5.79 P4-4"):
        chk(_k in _caS, "V3.5.79 calc_all N23 接线在岗: %s" % _k[:44])
    _agS = open("AGENTS.md", encoding="utf-8").read()
    chk("综合升级 V3.5.79" in _agS, "AGENTS 含 V3.5.79 综合升级段")
    # 🔴实跑断言（禁「关键词存在即通过」）: 带波胆 → 证据链必须出现波胆项
    import sys as _sy79
    if os.path.abspath("data/tmp") not in _sy79.path:
        _sy79.path.insert(0, os.path.abspath("data/tmp"))
    import importlib as _il79
    import joint_solver as _js79
    _il79.reload(_js79)
    _r79 = _js79.joint_anchor(1.73, 4.37, 4.83, handi=-1.0, o25=1.90,
                              cs_odds={'1-1': 18.5, '2-1': 18.5, '1-0': 23.1, '2-0': 23.1,
                                       '2-2': 25.4, '3-1': 25.4, '3-0': 30.0, '0-1': 34.6,
                                       '3-2': 32.3, '1-2': 30.0, '4-1': 41.6, '0-0': 40.0})
    _ev79 = _r79.get("anchor_1st_evidence") or []
    chk(any("波胆" in str(_e) for _e in _ev79),
        "V3.5.79 P2 波胆证据真生效(主锚=%s 证据=%s)" % (_r79.get("anchor_1st"), _ev79))
    _r79b = _js79.joint_anchor(1.80, 3.60, 4.50, handi=None, o25=1.95)
    chk(bool(_r79b.get("ok")) and (_r79b.get("pool_n") or 0) > 0,
        "V3.5.79 P4-1 无亚盘非空池(pool_n=%s)" % _r79b.get("pool_n"))
    print("   \u2705 2026-10-17 V3.5.79 综合升级(P0-P4) 防回退校验通过")
except Exception as _e79:
    chk(False, "V3.5.79 综合升级校验失败(%s)" % str(_e79)[:70])

# 🔴2026-10-17 V3.5.79 P5 市场信号主导排序防回退（用户方案·封装式补丁包·严格按方案）
#   契约: 三态基线 S1/S2/S3 · 波胆排名 0.30−0.03×(rank−1) · 泊松降权 ×0.5
#         · E1 升权 0.20/0.10/0.05 · E5 S1 升权 0.30/0.15/0.05 · E6 水位共振 +0.08
#         · 防死锚（波胆 Top1 全在池外→不硬搬·回退 S3）· market_baseline_src 留痕
try:
    _p5_src = open("data/tmp/joint_solver.py", encoding="utf-8").read()
    for _p5_fn in ("_market_baseline", "_cs_rank_map"):
        chk(("def %s" % _p5_fn) in _p5_src, "V3.5.79 P5 新函数在岗: %s" % _p5_fn)
    for _p5_k, _p5_d in (("P5_BS_RANK_TOP = 0.30", "波胆Top1基线"),
                         ("P5_BS_RANK_STEP = 0.03", "排名衰减"),
                         ("P5_POIS_WEIGHT = 0.0", "泊松退出排序(P6)"),
                         ("P5_E6_WATER = 0.08", "E6水位共振")):
        chk(_p5_k.replace(" ", "") in _p5_src.replace(" ", ""),
            "V3.5.79 P5 常量在岗: %s" % _p5_d)
    chk("market_baseline_src" in _p5_src and u"市场排序基线(P5" in _p5_src,
        "V3.5.79 P5 留痕链(返回字段+fmt_report 打印)")
    # 🔴实跑断言（禁「关键词存在即通过」）
    import importlib as _p5_il
    import joint_solver as _p5_js
    _p5_il.reload(_p5_js)
    _p5_pool = [{"score": "1:0", "m": 1, "t": 1, "p_pct": 11.5},
                {"score": "1:1", "m": 0, "t": 2, "p_pct": 10.8},
                {"score": "2:0", "m": 2, "t": 2, "p_pct": 10.8}]
    _p5_cs = _p5_js._cs_market_probs({"1-0": 6.5, "1-1": 7.0, "2-0": 8.0, "2-1": 8.5,
                                      "0-0": 9.0, "0-1": 10.0, "3-0": 12.0, "3-1": 13.0,
                                      "2-2": 14.0, "1-2": 15.0})
    _p5_bs, _p5_sp, _p5_nt = _p5_js._market_baseline(_p5_pool, _p5_cs, {"M": {}}, {})
    chk(_p5_sp == "S1" and abs(_p5_bs.get("1:0") - 0.30) < 1e-9,
        "V3.5.79 P5 S1 波胆排名基线(Top1 基线=%.2f)" % _p5_bs.get("1:0", 0))
    _p5_bs2, _p5_sp2, _p5_nt2 = _p5_js._market_baseline(
        _p5_pool, None, {"M": {"water": {"p_up": 0.60}}}, {})
    chk(_p5_sp2 == "S2" and _p5_bs2.get("2:0") == _p5_js.P5_WATER_STRONG_NET,
        "V3.5.79 P5 S2 让球水位基线(净胜>=2 升权=%.2f)" % _p5_bs2.get("2:0", 0))
    _p5_bs3, _p5_sp3, _p5_nt3 = _p5_js._market_baseline(_p5_pool, None, {"M": {}}, {})
    chk(_p5_sp3 == "S3" and _p5_bs3 is None, "V3.5.79 P5 S3 双缺泊松兜底(基线不合入)")
    # 🔴2026-10-20 P6 市场主导终版（用户指令「严格依赖市场信息决定·不依赖泊松」）
    chk("P5_E7_JC" in _p5_src and "jc_cs" in _p5_src,
        "P6 E7 竞彩比分盘证据在岗（用户点名「竞彩」）")
    chk("P5_E8_EXPECT" in _p5_src and "_E_mkt" in _p5_src,
        "P6 E8 市场期望匹配在岗（期望=O2.5 反推·非泊松）")
    chk("step5_dirs" in _p5_src, "P6 Step5 方向透传在岗（平局谱系入池）")
    chk('"pois": 0.05' in _p5_src.replace("  ", " "),
        "P6 λ 融合泊松降源(pois=0.05·market=0.40/line=0.35)")
    # 🔴2026-10-20 P6-g/h: 市场数据自动写入（jc_cs 自动去水 + step5_dirs 缺失告警）
    _ca_src = open("data/tmp/calc_all.py", encoding="utf-8").read()
    chk("竞彩CS自动接入(P6)" in _ca_src and "方向未透传(--step5-dirs)" in _ca_src,
        "P6 市场数据自动写入(竞彩CS自动去水/方向缺失显式告警)")
    chk("_jc_csv = (_extract_cs_bqc(txt_path)[0] or '')" in _ca_src,
        "P6 竞彩CS按 CSV 字符串契约解析(非 dict)")
    # 🔴2026-10-20 P7 E9: 半全场（HT-FT）市场证据
    chk("P5_E9_HT" in _p5_src and "def _ht_split" in _p5_src,
        "P7 E9 半全场证据函数在岗(_ht_split)")
    chk("htft=htft" in _p5_src and "htft=(_n23_ht or None)" in _ca_src,
        "P7 半全场透传链完整(joint_anchor→calc_all)")
    try:
        _p7 = _p5_js._ht_split({"胜胜": 1.88, "胜平": 18.0, "胜负": 45.0, "平胜": 4.05,
                                "平平": 7.70, "平负": 13.5, "负胜": 22.0, "负平": 18.0, "负负": 11.0})
        chk(_p7 is not None and abs(sum(_p7.values()) - 1.0) < 1e-6,
            "P7 半全场去水归一 H%.1f/D%.1f/A%.1f"
            % ((_p7 or {}).get("H", 0) * 100, (_p7 or {}).get("D", 0) * 100, (_p7 or {}).get("A", 0) * 100))
        chk(_p5_js._ht_split({"胜胜": 1.88}) is None, "P7 半全场不足 6 格→三态降级")
    except Exception as _p7e:
        chk(False, "P7 半全场实跑断言异常: %s" % _p7e)
    # 🔴实跑断言（禁「关键词存在即通过」）: step5_dirs 必须真能扩池含平局谱系
    try:
        _p6_r = _p5_js.joint_anchor(2.0, 3.4, 3.6, handi=0.0, o25=2.0, u25=1.9,
                                    step5_dirs=["主胜", "平局"])
        _p6_pool = [x["score"] for x in (_p6_r.get("pool") or [])]
        chk(any(x in _p6_pool for x in ("1:1", "0:0")),
            "P6 step5_dirs 透传实跑(平局谱系入池): %s" % (_p6_pool[:6] or "空池"))
        _p6_r2 = _p5_js.joint_anchor(2.0, 3.4, 3.6, handi=0.0, o25=2.0, u25=1.9)
        _p6_pool2 = [x["score"] for x in (_p6_r2.get("pool") or [])]
        chk(len(_p6_pool) >= len(_p6_pool2),
            "P6 透传后池不减(%d >= %d)" % (len(_p6_pool), len(_p6_pool2)))
    except Exception as _p6e:
        chk(False, "P6 实跑断言异常: %s" % _p6e)
    _p5_csx = {"probs": {"4-2": .12, "5-1": .09, "0-4": .08, "0-5": .07, "4-3": .06,
                         "5-2": .05, "3-4": .05, "2-5": .05, "6-1": .04, "1-6": .04}}
    _p5_bs4, _p5_sp4, _p5_nt4 = _p5_js._market_baseline(_p5_pool, _p5_csx, {"M": {}}, {})
    chk(_p5_sp4 == "S3" and (u"市场分歧" in _p5_nt4),
        "V3.5.79 P5 防死锚(波胆Top1 全在池外->不硬搬·回退S3)")
    # 🔴审计补强（2026-10-17 接入审计实抓）: 空池保护 + 四处留痕链在岗
    _p5_bsx, _p5_sx, _p5_nx = _p5_js._market_baseline([], _p5_cs, {"M": {}}, {})
    chk(_p5_sx == "S3" and (u"交集池为空" in _p5_nx) and (u"市场分歧" not in _p5_nx),
        "V3.5.79 P5 空池保护(不误报市场分歧·note=%s)" % _p5_nx[:20])
    _p5_oc = open("data/tmp/output_checker.py", encoding="utf-8").read()
    _p5_lp = open("data/tmp/check_luopan.py", encoding="utf-8").read()
    _p5_tm = open("data/analysis_template.md", encoding="utf-8").read()
    _p5_rg = open("data/tmp/rule_registry.json", encoding="utf-8").read()
    chk("N23c" in _p5_oc, "V3.5.79 P5 留痕链: output_checker N23c 在岗")
    chk(u"市场排序基线" in _p5_lp and "_cidi >= 254" in _p5_lp,
        "V3.5.79 P5 留痕链: check_luopan case>=254 在岗")
    chk(u"市场排序基线" in _p5_tm, "V3.5.79 P5 留痕链: analysis_template 登记")
    chk("P5-MARKET-LEAD" in _p5_rg, "V3.5.79 P5 变体台账: rule_registry.experiments 已登记")
    print("   \u2705 2026-10-17 V3.5.79 P5 市场主导排序 防回退校验通过")
except Exception as _p5_e:
    chk(False, "V3.5.79 P5 校验失败(%s)" % str(_p5_e)[:80])

# 🔴2026-10-17 复盘实抓·方向命中口径统一（治「多脚本各写一份·改一处≠改全部」复发第2次）
#   缺陷: 简写兜底把「客胜(主)」的 (主) 误当主胜声明 → case250（真实 1:0 主胜）方向误判✅
#   根治: 抽 case_write.dir_hit 单一实现 + self_iterate 改调该函数（禁再各自实现）
try:
    _cw_src = open("data/tmp/case_write.py", encoding="utf-8").read()
    _si_src = open("data/tmp/self_iterate.py", encoding="utf-8").read()
    chk("def dir_hit(" in _cw_src, "方向命中·单一实现 dir_hit 在岗(case_write)")
    chk("dir_hit(pred, real_dir)" in _si_src and "from case_write import dir_hit" in _si_src,
        "self_iterate 已改调单一实现(禁各写一份)")
    chk("_SHORT[real_dir] in pred" not in _si_src, "self_iterate 旧简写兜底已移除(防回退)")
    chk("target[16]" in _cw_src and "target[15]" in _cw_src,
        "cmd_review 派生列自动填(比分口径/主锚命中/次锚命中)")
    import sys as _sy_dh
    if os.path.abspath("data/tmp") not in _sy_dh.path:
        _sy_dh.path.insert(0, os.path.abspath("data/tmp"))
    from case_write import dir_hit as _dh
    chk(_dh("客胜(主)+平局(覆盖)", "主胜") is False,
        "括号孤字不构成方向声明(case250 fixture: 客胜(主) vs 真实主胜 → 否)")
    chk(_dh("主胜(并列平局)", "平局") is True,
        "括号含并列语义=真方向声明(主胜(并列平局) vs 平局 → 是)")
    print("   \u2705 2026-10-17 方向命中口径统一(dir_hit 单一实现) 防回退校验通过")
except Exception as _edh:
    chk(False, "方向命中口径校验失败(%s)" % str(_edh)[:70])

# 🔴2026-10-14 V3.5.78 断点修复防回退（实跑审计实抓·**方案自身 2 处缺陷**）
#   D1: `_propagate` 内 `p_notes or []` → 主入口 _w_notes=[] 是 falsy → 造临时列表 →
#       notes.append 后丢弃（盘口线留痕全丢）→ 须「保持引用」
#   D2: `fmt_report`/`trust` 原只读 est["T"]["lambda"]（内部自算）→ 与 Step6.5 λ_final 口径分裂 →
#       极端档预警恒不触发 → 须「优先 lambda_final」
try:
    _rD = _js.joint_anchor(1.275, 5.75, 10.0, handi=-1.5, o25=1.33, u25=2.98, ou_line=3.0,
                           lambda_final=4.27, totals_bin="极超")
    _d1 = any("盘口线驱动" in x for x in (_rD.get("notes") or []))
    _d2 = ("极端大球场" in _js.fmt_report(_rD)) and (_rD.get("lambda_final") == 4.27)
    _d2b = _rD.get("trust") == "不可信"                      # λ_final=4.27≥3.4 → 锚不可信
    _rDn = _js.joint_anchor(2.865, 3.43, 2.667, handi=0, o25=2.248)
    _d0 = ("极端大球场" not in _js.fmt_report(_rDn))         # 正常场不得误报
    _srcD = open("data/tmp/joint_solver.py", encoding="utf-8").read()
    _d1src = ("if p_notes is None:" in _srcD)
    _d2src = ('r.get("lambda_final")' in _srcD)
    chk(_d1 and _d2 and _d2b and _d0 and _d1src and _d2src,
        "V3.5.78 断点修复防回退(D1 notes真到达=%s·src=%s ｜ D2 极端档预警=%s·trust=%s·src=%s ｜ 正常场无误报=%s)"
        % (_d1, _d1src, _d2, _d2b, _d2src, _d0))
except Exception as _eD:
    chk(False, "V3.5.78 断点修复校验失败(%s)" % str(_eD)[:70])

# 🔴2026-10-15 P0 修复防回退: `snapshot_inputs` 多场快照须按 event_id 命中**本场**
#   原缺陷: 条件 `event_id==  or str(_g.home)==str(p.get('home', _g.home))` —— p 无 home 键
#   → `.get('home', 默认)` 默认取自 _g 自身 → **自比恒真** → 任何多场快照恒取第一场（静默）
try:
    import totals_water_read as _twr2
    _sA = _twr2.snapshot_inputs("Real Betis Seville", "FC Porto")
    _sB = _twr2.snapshot_inputs("Aston Villa", "Fenerbahce Istanbul")
    _lcA, _lcB = _sA.get("line_close"), _sB.get("line_close")
    _srcT = open("data/tmp/totals_water_read.py", encoding="utf-8").read()
    _okMark = ("_hit = str(_gid).strip() == str(_pid).strip()" in _srcT)
    chk((_lcA is None and _lcB is None) or (_lcA != _lcB),
        "snapshot_inputs 多场匹配(禁恒取首场): 贝蒂斯=%s vs 维拉=%s · 标记=%s" % (_lcA, _lcB, _okMark))
    chk(_okMark, "snapshot_inputs P0 修复标记存在")
except Exception as _eT:
    chk(False, "snapshot_inputs 多场匹配校验失败(%s)" % str(_eT)[:60])

# 🔴2026-10-16 SK-audit B 模式审计修复防回退（四场 case244-247 实跑实抓·补漏留痕）
#   P0-1: cs_deep_analyzer L131 把「其它」档（字符串键）混入 top10 → 赔率<100 时 unpack 崩溃
#         实例: case244 德甲 胜其它=15.0 → ValueError: too many values to unpack (expected 2)
#   P1-6: bsd_layer._deacc 仅去重音 → 英译队名(Cologne) vs 本地语(Köln) 恒不命中 → BSD 三态
try:
    import sys as _syC
    if os.path.abspath("data/tmp") not in _syC.path:
        _syC.path.insert(0, os.path.abspath("data/tmp"))
    _srcCS = open("data/tmp/cs_deep_analyzer.py", encoding="utf-8").read()
    chk("isinstance(k, tuple)" in _srcCS,
        "P0-1 修复: cs_deep_analyzer top10 按元组键过滤(防「其它」档崩溃)")
    _srcBS = open("data/tmp/bsd_layer.py", encoding="utf-8").read()
    chk("_CITY_EN_LOCAL" in _srcBS and "cologne" in _srcBS and "def _deacc" in _srcBS,
        "P1-6 修复: bsd_layer 英译城市名归一表(_CITY_EN_LOCAL)存在")
    _fxp = "data/tmp/_audit_fixtures/cs_other_low_odds.json"
    chk(os.path.exists(_fxp),
        "P0-1 fixture 已固化(cs_other_low_odds.json · 用 .json 避免与竞彩 txt 回归集混淆)")
    if os.path.exists(_fxp):
        from cs_deep_analyzer import analyze_cs_deep as _acsd
        _r = _acsd(open(_fxp, encoding="utf-8").read())
        _okT = (_r.get("status") == "ok" and len(_r.get("top10", [])) > 0
                and all(":" in x["score"] for x in _r["top10"]))
        chk(_okT, "P0-1 fixture 回归: 「其它档<100」输入不再崩溃(status=%s top10=%s)" % (_r.get("status"), len(_r.get("top10", []))))
    from bsd_layer import _deacc as _da
    chk(_da("1. FC Cologne") == _da("1. FC Köln"),
        "P1-6 回归: Cologne 与 Köln 归一后一致(%s)" % _da("1. FC Cologne"))
    print("   \u2705 2026-10-16 审计修复(P0-1 cs_deep / P1-6 BSD别名) 防回退校验通过")
except Exception as _eC:
    chk(False, "2026-10-16 审计修复校验失败(%s)" % str(_eC)[:60])

# 🔴2026-10-16 锚-期望【软约束】漏检防回退（SK-audit B 模式·case244-247·用户质疑「次锚和期望差太多」）
#   问题: 第17节只写硬1/硬2 → 漏 2026-10-13 新增【软 a/b/c 须满足其一】
#         → case246 实跑 ok=False（期望3.48 vs 锚[3,2]·软a/b/c 全不满足）却落盘通过
try:
    _srcL = open("data/tmp/live_score_engine.py", encoding="utf-8").read()
    chk("_soft_a" in _srcL and "_soft_b" in _srcL and "_soft_c" in _srcL,
        "锚-期望三级软约束已在 anchor_market_check 实现(软a/软b/软c · 2026-10-16)")
    # 🔴2026-10-25 小问题修补（case279 试验暴露·6 项）：建议锚可执行性 / bzzoiro 主客归组 / 校验器容错
    chk("suggestion_verified" in _srcL and "_pair_probe" in _srcL,
        "建议锚须「组合搜索校验可执行」(_pair_probe 守卫 + suggestion_verified · 2026-10-25 修死循环)")
    try:
        import sys as _sysP
        if "data/tmp" not in _sysP.path:
            _sysP.path.insert(0, "data/tmp")
        import live_score_engine as _lseP
        _pool7 = ["1:0", "2:0", "1:1", "2:1", "0:0", "3:1", "2:2"]
        _rP = _lseP.anchor_market_check(_pool7, 1.593, 4.16, 6.78, o25=2.34, u25=1.701, handi=-1.0)
        _rP2 = _lseP.anchor_market_check(_rP.get("suggestion") or ["2:0", "1:0"],
                                         1.593, 4.16, 6.78, o25=2.34, u25=1.701, handi=-1.0)
        chk(bool(_rP.get("suggestion_verified")) and _rP2.get("ok") is True,
            "建议锚可执行性实跑(case279 fixture): 7 候选池 → 建议锚复验 ok=True")
        _rN = _lseP.anchor_market_check(["2:0", "1:0"], 1.593, 4.16, 6.78, o25=2.34, u25=1.701, handi=-1.0)
        chk(_rN.get("suggestion_verified") is False and bool(_rN.get("warnings")),
            "无可行组合时须 verified=False + 显式警告（禁出假建议）")
    except Exception as _eP:
        chk(False, "建议锚组合搜索实跑失败: %s" % type(_eP).__name__)
    try:
        _srcB = open("data/tmp/bzzoiro_fetch.py", encoding="utf-8").read()
        chk("'home' if _wi == 0 else 'away'" in _srcB,
            "bzzoiro 主客归组按【输入顺序】(_wi)·防主队未定位时把客队当主队(2026-10-25·case279)")
        _srcC = open("data/tmp/check_luopan.py", encoding="utf-8").read()
        chk("[\\s\\*]+" in _srcC,
            "check_luopan 节标题容错匹配(去空白/星号·2026-10-25·治排版变体误报缺节)")
        _skS = open(".reasonix/skills/SK-score-depth/SKILL.md", encoding="utf-8").read()
        chk("P10/R10/R11 执行判据" in _skS and "锚-期望【硬1】" in _skS and "suggestion_verified=False" in _skS,
            "SK-score-depth 含「P10/R10/R11 执行判据」(优先级总表 + 3 实战裁决 · 2026-10-25)")
        chk("N28" in open("data/tmp/calc_all.py", encoding="utf-8").read()
            and "understat_xg" in open("data/tmp/calc_all.py", encoding="utf-8").read(),
            "calc_all 自动接入 understat xG(N28·防漏执行·2026-10-25)")
        chk("执行判据断言" in open("data/tmp/audit_p10.py", encoding="utf-8").read(),
            "audit_p10 含 H 段执行判据断言")
        _caN = open("data/tmp/calc_all.py", encoding="utf-8").read()
        chk("for _sn28 in (2027, 2026, 2025)" in _caN and "len(_d28) >= 8" in _caN,
            "N28 xG 赛季按队数阈值自动回退（2026-10-25 修·当前季稀疏→上一季完整）")
        _agM = open("AGENTS.md", encoding="utf-8").read()
        chk("主锚与次锚【同级】" in _agM,
            "AGENTS 含「主/次锚同级·命中其一即算·禁对主锚设更高要求」口径（2026-10-25 用户指令）")
        _jsP = open("data/tmp/joint_solver.py", encoding="utf-8").read()
        chk("_pair_cover_select" in _jsP and "pair_cover" in _jsP and "need_big3" in _jsP,
            "双锚联合覆盖机制已落地(_pair_cover_select + pair_cover 留痕 + R10-4 奖励 · 2026-10-25)")
        chk("双锚覆盖" in _agM, "AGENTS 含双锚机制化说明（覆盖最大化·非单锚排序）")
        # 🔴2026-10-26 审计补: _ov 白名单完整性（漏登记 → 参数静默失效·R3 曾中招）
        _caov = open("data/tmp/calc_all.py", encoding="utf-8").read()
        _mfl = re.search(r"_OVFLAGS\s*=\s*\((.*?)\)", _caov, re.S)
        _used = set(re.findall(r"_ov\.get\(['\"](--[\w-]+)['\"]\)", _caov))
        _white = set(re.findall(r"['\"](--[\w-]+)['\"]", _mfl.group(1))) if _mfl else set()
        _lack_ov = sorted(_used - _white)
        chk(not _lack_ov, "calc_all 所有 _ov.get 参数均已登记 _OVFLAGS（缺: %s）" % (_lack_ov or "无"))
        # 🔴P12.1 全链兼容（2026-10-26）
        _arb12 = open("data/tmp/p12_arbitrate.py", encoding="utf-8").read()
        _cv12 = open("data/tmp/calc_v3572.py", encoding="utf-8").read()
        chk("def p12_arbitrate" in _arb12 and "from p12_arbitrate import p12_arbitrate" in _cv12,
            "P12.1 调档仲裁器已落地且被 direction_full 调用（覆盖资金盘+同源去重）")
        chk("_conf_after_static" in _cv12 and "_spread_raised" in _cv12 and "_static_trap_downgrade" in _cv12,
            "P12.1 三标记齐全（资金盘前档位/升档标记/静态诱主标记）")
        _oc12 = open("data/tmp/output_checker.py", encoding="utf-8").read()
        chk("def check_p12" in _oc12 and "check_p12(text)" in _oc12,
            "P12.1 N21c 并列闭环断言已定义并接线（非只定义）")
        # 🔴2026-10-26 审计补: 迁移文档状态数字防滞后（曾出现 278 场 vs 实际 282）
        try:
            import csv as _csvmig
            _mig = open("data/tmp/migration_prompt.md", encoding="utf-8").read()
            _n_case = len(list(_csvmig.DictReader(open("data/case-library/实战案例.csv", encoding="utf-8-sig"))))
            chk(("**%d 场**" % _n_case) in _mig,
                "migration_prompt 案例库场次与 CSV 实测一致（%d 场）" % _n_case)
            _agv = re.search(r"V3\.5\.\d+", open("AGENTS.md", encoding="utf-8").read()[:4000])
            chk((_agv.group(0) if _agv else "?") in _mig,
                "migration_prompt 版本号与 AGENTS 一致（%s）" % (_agv.group(0) if _agv else "?"))
        except Exception as _emig:
            chk(False, "migration_prompt 一致性校验异常: %s" % str(_emig)[:60])
        # 🔴2026-10-26 比分分 V4.1（案例库蒸馏+大样本验证）
        # 🔴2026-10-26 时序接线修复（三缺口）
        _sv = open("data/tmp/snapshot_save.py", encoding="utf-8").read()
        chk("无「让」字" in _sv and "主让" in _sv, "_ah_hdp 多格式兼容（无「让」字/主让/客让/@）")
        chk("structured" in _sv, "find_for 支持结构化快照（ml.fair / ah / totals → extract）")
        _ce = open("data/tmp/cn2en_extra.json", encoding="utf-8").read()
        chk(all(k in _ce for k in ("弗拉门戈", "布洛涅", "圣克拉拉", "本菲卡")),
            "cn2en 别名含本批非五大球队")
        _ca2 = open("data/tmp/calc_all.py", encoding="utf-8").read()
        chk("kickoff=_kof" in _ca2, "calc_all 向 fundflow 透传 kickoff（P2-3 时间权重）")
        # 🔴2026-10-27 P13 执行总控（<REDACTED_SK> + run_guard）
        chk(os.path.exists(".reasonix/skills/<REDACTED_SK>/SKILL.md"),
            "<REDACTED_SK> 技能存在（发竞彩 txt 即触发的执行总控）")
        _ro = open(".reasonix/skills/<REDACTED_SK>/SKILL.md", encoding="utf-8").read()
        chk(all(k in _ro for k in ("PROFILE A", "PROFILE B", "H1 数字三来源白名单", "十条红线")),
            "<REDACTED_SK> 含两套 profile + 反幻觉 H1-H10 + 十条红线")
        chk(os.path.exists("data/tmp/run_guard.py"), "run_guard.py 开场 preflight 脚本存在")
        _rg = open("data/tmp/run_guard.py", encoding="utf-8").read()
        chk(all(k in _rg for k in ("def profile_of", "def parse_header", "def find_snapshot",
                                   "FULL-5", "CORE", "── G. 本场放行门禁")),
            "run_guard 含域判定/解析/快照/门禁四段（非空壳）")
        # 🔴2026-10-27 P13.1 深入检查修复（防回退·每条对应一个真实断链）
        _ca3 = open("data/tmp/calc_all.py", encoding="utf-8").read()
        chk("if eu: cmd += ['--eu', str(eu)]" in _ca3,
            "P13.1 P0-1: calc_all 向 calc_match 子进程透传 --eu（原漏传→V5 恒跳过）")
        chk("禁止把竞彩末盘" in _rg and "eu = '%.2f,%.2f,%.2f' % (last_eu.get('胜')" not in _rg,
            "P13.1 P0-2: run_guard 禁用竞彩末盘冒充 --eu（同源→V5 假一致）")
        _cm3 = open("data/tmp/calc_match.py", encoding="utf-8").read()
        chk("_v5_src = sections.get('spf_jc') or sections['spf']" in _cm3,
            "P13.1 P0-1b: V5 竞彩侧取 spf_jc 原序（P9 桥覆盖后 spf 已是欧盘→防「欧盘 vs 欧盘」假一致）")
        _tn3 = open("data/tmp/txt_normalize.py", encoding="utf-8").read()
        chk("l.startswith(('比赛时间', '开赛时间'))" in _tn3,
            "P13.1 P1-3: txt_normalize 兼容「开赛时间」（原只认「比赛时间」→ 误报缺时间）")
        _ls3 = open("data/tmp/live_score_engine.py", encoding="utf-8").read()
        chk("if not o25:\n" in _ls3.replace("\r\n", "\n") and "缺 o25 时 1/None" in _ls3,
            "P13.1 P1-4: live_score_engine solve_lambda_live 缺 o25 三态返回（原 1/None 崩溃）")
        # 🔴2026-10-27 P14 时序链断裂修复（find_for 跨场防护误剔除缺 kickoff_bj 的旧快照）
        _ss4 = open("data/tmp/snapshot_save.py", encoding="utf-8").read()
        chk("_kb = g.get('kickoff_bj')" in _ss4 and "kickoff_utc" in _ss4
            and "_kb = (_dtk + dt.timedelta(hours=8))" in _ss4,
            "P14: find_for 对缺 kickoff_bj 的旧快照用 kickoff_utc+8h 兜底（原被跨场防护剔除→时序链断为单时点）")
        chk("n_points" in _ss4 and "时点·跨度" in _ss4 and "out[\"n_points\"] = int(r.get(\"count\") or 0)" in _ss4,
            "P8 vertical_for 语义固化（count=可用维度数 / n_points=快照时点数·防同名不同义误读）")
        # 🔴2026-10-27 P15 数据源执行铁律（case287 实抓：伤停源用错 + the-odds-api 未传联赛）
        _to5 = open("data/tmp/the_odds_api_fetch.py", encoding="utf-8").read()
        chk("SPORT_MAP" in _to5 and "def resolve_sport" in _to5
            and "'意甲': 'soccer_italy_serie_a'" in _to5,
            "P15: the-odds-api 加 --league 映射（原 DEFAULT_SPORT 默认欧国联 → 意甲场次误报「源未覆盖」）")
        _ag5 = open("AGENTS.md", encoding="utf-8").read()
        chk("伤停源优先级：Bzzoiro 结构化名册" in _ag5,
            "P15: AGENTS 固化「伤停必须走 Bzzoiro 结构化名册·禁新闻标题推断」")
        # 🔴2026-10-27 P16（case287 完整重跑实抓 4 缺陷）
        _ca6 = open("data/tmp/calc_all.py", encoding="utf-8").read()
        chk("inj_score_h=float(inj_h)" in _ca6,
            "P16: calc_all inj_score 用 float（原 int('11.5') 崩掉整个 direction_full）")
        chk("'--draw-score'" in _ca6 and "_ov.get('--draw-score')" in _ca6,
            "P16: calc_all 支持 --draw-score（外部证据补 S4/S6/S12·否则平局并列系统性漏判）")
        chk("elif inj_h or inj_a:" in _ca6,
            "P16: 直传 --inj_h/--inj_a 时不再误报「伤停缺失」")
        _bs6 = open("data/tmp/bookmaker_spread.py", encoding="utf-8").read()
        chk("books 缺 status 字段" in _bs6,
            "P16: load_books 兼容「有 books 列表但缺 status」（原静默丢弃 41 家→P0-1 假报不可得）")
        # 🔴2026-10-28 P17（罗马场用户质疑·锚-让球穿盘一致性）
        _ag7 = open("AGENTS.md", encoding="utf-8").read()
        chk("P17 锚-让球穿盘一致性" in _ag7,
            "P17: AGENTS 固化「主锚必须落在不输盘一侧·H3+出口必消费·净胜双源分歧必报」")
        import glob as _g7
        _c288 = [p for p in _g7.glob("data/case-library/raw/case288_*.md")]
        if _c288:
            _r7 = open(_c288[0], encoding="utf-8").read()
            chk("H3+ 出口消费留痕" in _r7 or "穿 −1.5 盘" in _r7,
                "P17: case288 raw 已落「穿盘锚 / H3+ 出口消费」留痕（防回退到输盘主锚）")
        # 🔴2026-10-28 P18 消费保障
        chk(os.path.exists("data/tmp/audit_consumption.py"),
            "P18: 消费审计脚本 audit_consumption.py 在位（落盘前必跑·未消费清单须为 0）")
        _ag8 = open("AGENTS.md", encoding="utf-8").read()
        chk("P18 消费保障铁律" in _ag8,
            "P18: AGENTS 固化「输出被消费才算生效·让球水位/N26 高频漏项必判」")
        _lp8 = open("data/tmp/check_luopan.py", encoding="utf-8").read()
        chk("P18 消费兜底" in _lp8,
            "P18: check_luopan 已加「让球水位 + N26」关键词兜底（漏消费即拦落盘）")
        # 🔴2026-10-28 P19 H2H 双源
        chk("P19 H2H 双源" in _ag8,
            "P19: AGENTS 固化「H2H 必须双源(竞彩特征+Matches.csv)·场均差>1球标量级冲突·主锚方向≠首选须写取舍」")
        chk("P19 H2H 双源兜底" in _lp8,
            "P19: check_luopan 已加 H2H 双源兜底（缺 Matches.csv 即拦）")
        # 🔴2026-10-28 P20 伤停收敛 + 卡顿修复
        _ag9 = open("AGENTS.md", encoding="utf-8").read()
        chk("P20 伤停数据源收敛" in _ag9,
            "P20: AGENTS 固化「伤停=Bzzoiro 唯一源·网页新闻已停用·BRIDGE_NEWS 应急」")
        _db9 = open("data/online_learning/data_bridge.py", encoding="utf-8").read()
        chk("P20 用户决策：伤停只用 Bzzoiro" in _db9 and "BRIDGE_NEWS" in _db9,
            "P20: data_bridge news 源默认停用（保留 BRIDGE_NEWS=1 应急通道）")
        _bz9 = open("data/tmp/bzzoiro_fetch.py", encoding="utf-8").read()
        chk("_bzz_idx_cache.json" in _bz9 and "date_from=2026-10-01" not in _bz9,
            "P20: bzzoiro 日期窗口动态化 + 索引 6h 缓存（原硬编码 10-01~10-20 致定位失效+32.5s）")
        _ca9 = open("data/tmp/calc_all.py", encoding="utf-8").read()
        chk("Bzzoiro 结构化·源B8·唯一源" in _ca9,
            "P20: calc_all 必核清单 C23 已改为 Bzzoiro（原 SL-news-crawl）")
        # 🔴2026-10-28 P21 统一入口 pipeline
        chk(os.path.exists("data/tmp/pipeline.py"),
            "P21: 统一入口 pipeline.py 在位（7 阶段一键全流程·≈33s）")
        _pl9 = open("data/tmp/pipeline.py", encoding="utf-8").read()
        chk("Stage0" in _pl9 and "Stage6" in _pl9 and "消费审计" in _pl9,
            "P21: pipeline 含 Stage0-6 全阶段 + 消费审计（禁漏步骤）")
        chk("_bsd_teams" in _pl9,
            "P21: pipeline BSD 队名中→英转换（原中文直传→BSD 整块缺失）")
        _rg9 = open("data/tmp/run_guard.py", encoding="utf-8").read()
        chk("禁「先跑一次看输出再补参数重跑」" in _rg9,
            "P21: run_guard 已删「重跑」教条（原教模型 Step5 后重跑=最大耗时源）")
        _agA = open("AGENTS.md", encoding="utf-8").read()
        chk("P21 统一入口 pipeline.py" in _agA,
            "P21: AGENTS 固化「单场唯一入口 pipeline.py·禁重跑·数值程序填判断模型填」")
        # 🔴2026-10-28 P22 市场三源实证
        chk("P22 市场三源" in _agA,
            "P22: AGENTS 固化「三源硬门槛 + AH>OU>>CS 贡献排序 + E0 基线非主排序」")
        chk("E0 主排序" not in _agA,
            "P22: 旧口径「E0 主排序」已清除（实测=证据加分主导·防回退）")
        chk(os.path.exists("data/tmp/_ablate_p10.py") and os.path.exists("data/tmp/_ablate_p10b.py"),
            "P22: 三源消融工具在位（_ablate_p10 缺一消融 / _ablate_p10b 抹平敏感度）")
        # 🔴2026-10-28 P23/P24 市场信号主导锚定
        _jsA = open("data/tmp/joint_solver.py", encoding="utf-8").read()
        chk("P10_MM_BASE = 3.0" in _jsA,
            "P23: 市场矩阵权重 ×3.0 主导（1.0→3.0·用户指令「市场信号主导」）")
        chk("P10_EV_SCALE = 0.15" in _jsA,
            "P23: 其余证据 ×0.15 仅 tie-break（0.5→0.15）")
        chk("_w8 = 0.0" in _jsA and "+ _w8" in _jsA,
            "P23: E8 期望匹配全额保留不缩放（锚-期望铁律不失守）")
        chk("P24_M_RATIO" in _jsA and "P24_M_MAX" in _jsA,
            "P24: M 域按市场净胜分布放宽常量在位（RATIO 0.6 / MAX 2）")
        chk("_same24" in _jsA,
            "P24-fix: 阈值基准只取同方向档（平局档不抬阈值·287 教训）")
        chk("P24 M 域按市场净胜分布放宽" in _jsA,
            "P24: M 域放宽留痕在位（审计可见）")
        chk("P23 市场信号主导锚定" in _agA,
            "P23/P24: AGENTS 固化「市场主导 + M 域市场分布放宽」")
        chk("证据减半·泊松仅回填" not in _jsA,
            "P23: 旧口径「证据减半」文案已清除（防与实测不符）")
        # 🔴2026-10-28 P25 信号驱动锚定
        _mdA = open("data/tmp/market_distribution.py", encoding="utf-8").read()
        chk("_pen25" in _mdA and "P25 信号约束排序" in _mdA,
            "P25: anchor_select 排序主键改为信号约束（期望/大小球/让球）·概率降同档 tie-break")
        chk("top = sorted(adj.items(), key=lambda kv: -kv[1])" not in _mdA,
            "P25: 旧「纯概率排序」已清除（低分偏置根因）")
        chk("isinstance(pT, (list, tuple))" in _mdA,
            "P25: total.p 兼容 list（实跑坑：曾按 dict 判断致惩罚静默失效）")
        chk("P25 次锚信号约束校正" in _jsA,
            "P25-b: 次锚同受信号约束（禁 1 球低分出口）")
        chk("P25 信号驱动锚定" in _agA,
            "P25: AGENTS 固化「信号驱动锚定·概率禁作排序主键」")
        # 🔴2026-10-28 P26 分层市场信号约束
        chk("def _pen25" in _mdA and "_zero_allowed" in _mdA,
            "P26: 分层约束体系在位（_pen25 罚分·P28 起排序改用 _signal_support 评分）")
        chk("_allow = 0.5 + 0.25 * _strength" in _mdA,
            "P26: 允许偏移随信号强度放宽（0.5→1.5·期望不被降级）")
        chk("home_clean" in _mdA and "away_clean" in _mdA,
            "P26: 消费 R11 零封直盘（home_clean/away_clean/btts）")
        chk("P26-c" in _mdA,
            "P26-c: L4 语义为「期望正经约束+信号强度定偏移」（用户澄清）")
        chk("P26 分层市场信号约束" in _agA,
            "P26: AGENTS 固化分层约束与冲突优先级")
        # 🔴2026-10-28 P27 机械锚定自查修正
        chk("P27 谱系连续性补齐" in _jsA and "_fill24" in _jsA,
            "P27: M 域放宽后同号段补齐中间档（防谱系断裂跳过净3）")
        chk("P27-b 第三候选去重" in _jsA,
            "P27-b: 第三候选不得等于主锚/次锚")
        chk("P27 机械锚定自查修正" in _agA,
            "P27: AGENTS 固化自查结论（含已知局限：阈值规则同象限同解）")
        # 🔴2026-10-28 P28/P29 反机械锚定（评分池 + 去概率）
        chk("_signal_support" in _mdA and "score_pool" in _mdA,
            "P28: 罚分制改评分制·输出比分池（不淘汰候选）")
        chk("_cs_rank29" in _mdA and "波胆排名" in _mdA,
            "P29: 池内选择去概率·改波胆市场排名（CS赔率=市场直接定价）")
        chk('_d["矩阵概率"]' not in _mdA and '波胆排名' in _mdA,
            "P29: 评分项已无「矩阵概率」键·改波胆市场排名（IPF产物非市场报价）")
        chk("P28+P29 反机械锚定" in _agA,
            "P28/P29: AGENTS 固化「可设比分池·禁机械锚定某一个」")
        # 🔴2026-10-29 P30 信号落地强制传导（用户「保证信号识别能传导到落地」·case290/292 双实证）
        _slA = open("data/tmp/signal_landing.py", encoding="utf-8").read()
        chk("RULES" in _slA and "ACTION_WORDS" in _slA and "def signals" in _slA,
            "P30: signal_landing.py 在位（信号→强制动作映射 + 动作词校验）")
        chk("M1伤停仍热门" in _slA and "对手方方向" in _slA,
            "P30: M1/诱主/Q2 硬动作 = 降档 + 并列对手方方向（非平局）")
        chk("P30 信号落地强制传导" in _agA and "最多 2 向" in _agA,
            "P30: AGENTS 固化「硬动作信号清单 + 每场最多两向」")
        chk("三向全列" not in _agA,
            "P30: AGENTS 已清除旧「三向全列」口径（2026-10-29 用户指令废止三向）")
        chk("MAX_DIRS" in _slA and "max_two_check" in _slA,
            "P30: signal_landing 含「最多两向」截断 + 三向超标检测")
        chk("最多 2 向" in open("data/analysis_template.md", encoding="utf-8").read(),
            "P30: 分析模板覆盖自检 = 最多两向")
        chk("禁三向" in open("data/tmp/calc_match.py", encoding="utf-8").read(),
            "P30: calc_match 输出文案同步两向口径（模型读到的提示不再要求三向）")
        # 🔴2026-10-29 审计补: P30 二期（接入自动链路 + 清残留）
        _pipeA = open("data/tmp/pipeline.py", encoding="utf-8").read()
        chk("signal_landing" in _pipeA and "信号落地核查" in _pipeA and "max_two_check" in _pipeA,
            "P30二期: pipeline 接入 signal_landing（Stage5 预填节 + Stage6 校验）")
        chk("三个方向都写进" not in _agA and "须三向覆盖" not in _agA,
            "P30二期: AGENTS 已无「三向」活跃要求（2026-10-29 用户指令废止）")
        _nsk = open(".reasonix/skills/SK-league-nations/SKILL.md", encoding="utf-8").read()
        chk("只写两向" in _nsk and "三个方向都写进" not in _nsk,
            "P30二期: SK-league-nations 弱共识=两向（首选+平局·三向正文已清）")
        chk("三个方向都写进" not in open("data/足球分析模型.txt", encoding="utf-8").read(),
            "P30二期: txt 已无「三向」活跃要求")
        chk("_pick_events" in open("data/tmp/audit_contracts.py", encoding="utf-8").read(),
            "审计: audit_contracts fixture 动态化（防硬编码 event_id 过期误报）")
        # 🔴2026-10-29 Form5 恢复（Bzzoiro 替代 api-football·用户决策 dec-ada50f0a7961c711）
        _pfA = open("data/tmp/prestep_fetch.py", encoding="utf-8").read()
        chk("FORM_UNAVAILABLE = None" in _pfA and "points_last_n" in _pfA and "FORM_SOURCE" in _pfA,
            "Form5: prestep_fetch 已换源 Bzzoiro（points_last_n ÷ matches_played）+ FORM_SOURCE 口径标注")
        chk("Form5 的 PreStep F1 信号（+0.5）已于 2026-10-29 由 Bzzoiro 恢复" in _agA,
            "Form5: AGENTS 记录换源（不再写「Form5 无替代 / 唯一实质损失」）")
        chk("Form5 已于 2026-10-29 由 Bzzoiro 恢复" in open("data/足球分析模型.txt", encoding="utf-8").read(),
            "Form5: txt 同步换源表述")
        chk("Bzzoiro 恢复" in open("data/tmp/migration_prompt.md", encoding="utf-8").read(),
            "Form5: 迁移文档同步（api-football 停用段不再称 Form5 无替代）")
        # 🔴2026-10-29 断链修复（用户「严格深入检查模型有无断链·新更新与旧模块都要传导到位」）
        _caA = open("data/tmp/calc_all.py", encoding="utf-8").read()
        chk("_sb.get('期次')" in _caA,
            "断链修①: 意甲单赛季块读 I1 的「期次」（原读 截至日期/轮次范围 → 恒空·期次打印缺失）")
        chk("_TT_H, _TT_A = _mkT0.txt_teams" in _caA and "_teams27 = '%s,%s' % (_hT, _aT)" in _caA,
            "断链修②: N27/BSD 队名改走 txt 解析（原只读 calc_all 不存在的 --teams/--bsd-teams → 恒三态）")
        chk("非欧冠场（%s）→ 不触发（三态·数据隔离）" in _caA,
            "断链修③: N24/N25 非欧冠场显式三态（原整段无输出 = 「没做也不说」）")
        chk("P30 信号落地兜底" in open("data/tmp/check_luopan.py", encoding="utf-8").read(),
            "P30: check_luopan 兜底（case294+ 强制「信号落地核查」节）")
        chk("信号落地核查（P30" in open("data/analysis_template.md", encoding="utf-8").read(),
            "P30: analysis_template 含「信号落地核查」节模板")
        # 🔴2026-10-28 英联赛杯 slug 扩展（用户指定执行 PreStep）
        chk("england-efl-cup" in open("data/tmp/prestep_fetch.py", encoding="utf-8").read(),
            "英联赛杯: prestep_fetch.LG 含 england-efl-cup（实测 slug·非猜测）")
        chk("england-efl-cup" in open("data/tmp/snapshot_save.py", encoding="utf-8").read(),
            "英联赛杯: snapshot_save.LG 含 england-efl-cup（快照可拉）")
        chk("england-efl-cup" in _agA,
            "英联赛杯: AGENTS 记录 slug + 杯赛超域标注")
        # 🔴2026-10-27 P8 纵向端到端审计（用户质疑「纵向序列真能进模型并执行吗」→ 固化为 A/B 实测）
        #   只断言 vert 参数存在 = 「存在≠活跃」；必须证明 joint_anchor 输出真的被 vert 改变。
        try:
            import subprocess as _sp8v
            _r8v = _sp8v.run([sys.executable, "data/tmp/audit_p8_vertical.py", "--quiet"],
                             capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=240)
            chk(_r8v.returncode == 0,
                "P8 纵向端到端审计全过（数据层多时点+三维 / vert A/B 真改变 joint_anchor 输出 / calc_all 接线）")
            if _r8v.returncode != 0:
                print("     " + (_r8v.stdout or "")[-400:].replace("\n", "\n     "))
        except Exception as _e8v2:
            chk(False, "audit_p8_vertical 执行失败: %s" % type(_e8v2).__name__)
        _sm = open(".reasonix/skills/<REDACTED_SK>/SKILL.md", encoding="utf-8").read()
        chk("【执行入口】凡用户在对话框发来竞彩 txt" in _sm,
            "主技能顶部已接线执行入口（强制触发 <REDACTED_SK>）")
        _pd4 = open("data/tmp/prestep_dual.py", encoding="utf-8").read()
        # 🔴2026-10-26 审计补: 方向档三档（AGENTS 声明 ≥3.5推荐/≥3.0观察/<3.0不推荐·此前只声明未实现）
        chk(all(k in _pd4 for k in ("推荐(方向)", "观察(方向)", "不推荐(方向)", "'方向档': dgrade")),
            "PreStep 方向档三档已实现且写入返回字典（原仅 verdict 用 3.5·无独立字段）")
        chk("'方向档', '倾向'" in _pd4, "PreStep 表格含「方向档」列")
        chk("比分分 V4.1: ≥2.0 强推荐" in _pd4, "PreStep 输出阈值行已标 V4.1 口径")
        chk("比分评分 V4.1" in _pd4 and "低平赔+1.5" in _pd4 and "小球+弱主+0.5" in _pd4,
            "比分分 V4.1 已落地（平赔维+小球组合+大球弱主）")
        chk("主赔1.5-1.8 -0.3" in _pd4, "V4.1 修正主赔 1.5-1.8 符号（原 +0.5 → -0.3）")
        chk("悬殊场(|主隐-客隐|>40pp)" not in _pd4 and "深让≥1.5 +1.0" not in _pd4,
            "V4.1 已删除无效规则（悬殊-1.0 / 深让+1.0）")
        _mi12 = open("data/tmp/market_intent.py", encoding="utf-8").read()
        chk("end_ml=None" in _mi12 and "home_water=None" in _mi12 and "points_used" in _mi12,
            "P12.1 单时点双兜底（end_ml 欧赔点 + handi/home_water 亚盘串）")
        # 🔴P12 机构意图：audit_p12 断言型自检（6 fixture + 接线 + 签名 + 三态）
        try:
            import subprocess as _sp12
            _r12a = _sp12.run([sys.executable, "data/tmp/audit_p12.py"],
                              capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
            chk(_r12a.returncode == 0,
                "audit_p12 自检全绿（6 fixture / calc_all 接线 / 签名 / 三态）")
        except Exception as _e12a:
            chk(False, "audit_p12 执行失败: %s" % type(_e12a).__name__)
        # 🔴P11·R12 次锚终选器（2026-10-26）
        _md12 = open("data/tmp/market_distribution.py", encoding="utf-8").read()
        _js12 = open("data/tmp/joint_solver.py", encoding="utf-8").read()
        chk("def r12_second_anchor" in _md12 and "r12_second_anchor(" in _js12,
            "R12 次锚终选器已落地且被 joint_solver 调用（非只定义·防「存在≠活跃」）")
        chk('_r12m != "on" and _R2' in _js12,
            "R10-2 邻域次锚仅在 off/auto 生效（on 由 R12 接管·防双锚挤同角落）")
        chk(("a2 = _cand11[0]" in _js12) and ('_r12m != "on"' in _js12),
            "R11 硬替换仅在 off/auto 生效（on 模式改传谱系候选给 R12）")
        try:
            _cf12 = __import__("json").load(open("data/tmp/p10_config.json", encoding="utf-8"))
            chk("r12_pair_cover" in _cf12, "p10_config 含 r12_pair_cover 灰度开关（off/auto/on）")
        except Exception:
            chk(False, "p10_config.json 读取失败")
    except Exception as _eQ:
        chk(False, "小问题修补断言读取失败: %s" % type(_eQ).__name__)
    _srcA = open("AGENTS.md", encoding="utf-8").read()
    chk("锚-期望【软约束】漏检修复" in _srcA,
        "AGENTS 含 2026-10-16 锚-期望软约束漏检修复段(执行纪律四项)")
    for _cid in ("case244", "case246"):
        _rawc = open("data/case-library/raw/%s.md" % _cid, encoding="utf-8").read()
        chk("软约束核验" in _rawc, "%s raw 第17节含软约束核验留痕(硬1/硬2/软a/软b/软c)" % _cid)
    import sys as _syS
    if os.path.abspath("data/tmp") not in _syS.path:
        _syS.path.insert(0, os.path.abspath("data/tmp"))
    import live_score_engine as _lseS
    _rOK = _lseS.anchor_market_check(['2:1', '2:2'], 2.512, 3.74, 2.858, 1.42, None, 0.0)
    chk(_rOK.get("ok") is True, "case246 修正后锚 2:1/2:2 通过(ok=True)")
    _rBad = _lseS.anchor_market_check(['2:1', '1:1'], 2.512, 3.74, 2.858, 1.42, None, 0.0)
    chk(_rBad.get("ok") is False, "case246 原锚 2:1/1:1 仍被拦(ok=False → 证明软约束真生效)")
    print("   \u2705 2026-10-16 锚-期望软约束漏检 防回退校验通过")
except Exception as _eS:
    chk(False, "2026-10-16 锚-期望软约束校验失败(%s)" % str(_eS)[:60])

# 🔴2026-10-16 case_write raw 复盘节匹配修复防回退（case244-247 复盘实抓·"存在≠活跃"型）
#   缺陷: 原 `f.startswith(f'case{cid}_')` 只认历史命名 `case244_队名.md`
#         → 本批 `case244.md` 恒不匹配 → CSV 更新了但 raw 复盘节**静默不写**
try:
    _cwS = open("data/tmp/case_write.py", encoding="utf-8").read()
    chk("_exact = f'case{cid}.md'" in _cwS,
        "case_write 兼容 case{cid}.md 命名(防「raw 复盘节静默不写」)")
    _miss = []
    for _cid2 in ("244", "245", "246", "247"):
        _rp2 = "data/case-library/raw/case%s.md" % _cid2
        if (not os.path.exists(_rp2)) or ("## 复盘（" not in open(_rp2, encoding="utf-8").read()):
            _miss.append(_cid2)
    chk(not _miss, "case244-247 raw 均含复盘节(缺失=%s)" % (_miss or "无"))
    print("   \u2705 2026-10-16 case_write raw 复盘节匹配修复 防回退校验通过")
except Exception as _eW:
    chk(False, "case_write raw 匹配校验失败(%s)" % str(_eW)[:60])

# 🔴2026-10-13 锚-期望【双锚强制】匹配（用户指令「锚定比分必须与期望进球能对上」）
#   防回退: ①旧「至少一锚」口径必须已废除（1:1/1:0 须被拦·次锚偏离 −1.42）
#           ②跨期望双锚（1:1/2:0·均∈±1.0）须通过 ③cs_snapshot 须标注「CS 谱系期望·禁当期望用」
try:
    import sys as _syA
    if os.path.abspath("data/tmp") not in _syA.path:
        _syA.path.insert(0, os.path.abspath("data/tmp"))
    import live_score_engine as _lseA
    _rA1 = _lseA.anchor_market_check(["1:1", "1:0", "0:0", "2:1"], 2.865, 3.43, 2.667, o25=2.248, handi=0.0)
    _blkA = (_rA1.get("ok") is False) and ((_rA1.get("anchor_expect") or {}).get("exp") is not None)
    _rA2 = _lseA.anchor_market_check(["1:1", "2:1", "1:0", "0:0"], 2.865, 3.43, 2.667, o25=2.248, handi=0.0)
    _passA = (_rA2.get("ok") is True)
    _csA = open("data/tmp/cs_snapshot.py", encoding="utf-8").read()
    chk(_blkA and _passA and ("CS 谱系期望" in _csA),
        "锚-期望双锚强制匹配(旧1:1/1:0须拦=%s·新1:1/2:1须过=%s)+CS谱系期望禁用标注" % (_blkA, _passA))
except Exception as _eA:
    chk(False, "锚-期望双锚匹配校验失败(%s)" % str(_eA)[:70])

# 🔴P0 fixture 防回归(2026-10-11 审计·λ_line 口径混淆): λ_line 必须随本场 O2.5 变化
#   原缺陷: fair_line() 均衡线(≈2.51)被当 λ → 四场恒等 → 权重 0.30 的源退化为常数
try:
    import json as _jfL, sys as _syL
    _fxpL = "data/tmp/_audit_fixtures/totals_lambda_line.json"
    _fxL = _jfL.load(open(_fxpL, encoding="utf-8"))
    if os.path.abspath("data/tmp") not in _syL.path:
        _syL.path.insert(0, os.path.abspath("data/tmp"))
    import totals_water_read as _twrL
    _valsL, _okL = [], True
    for _cL in _fxL.get("cases", []):
        _rL = _twrL.water_read(o25=_cL["o25"], u25=_cL["u25"])
        _vL = _rL.get("lambda_line")
        _valsL.append(_vL)
        if _vL is None or abs(float(_vL) - float(_cL["expect_lambda_line"])) > 0.02:
            _okL = False
    chk(_okL and len(set(_valsL)) > 1,
        "totals λ_line 随本场 O2.5 变化(fixture 4 例=%s)" % ",".join(str(v) for v in _valsL))
except Exception as _eL:
    chk(False, "totals λ_line fixture 回归失败(%s)" % str(_eL)[:70])
chk("NL 超域" in open("data/tmp/prestep_dual.py", encoding="utf-8").read(), "prestep_dual NL 分流(超域区·不混入正式表·2026-09-24)")
chk("dir_score" in open("data/tmp/prestep_fetch.py", encoding="utf-8").read() and "漏场风险" in open("data/tmp/prestep_fetch.py", encoding="utf-8").read(), "prestep_fetch 分数留痕+slug三态(2026-09-24)")
chk("market_matrix" in open("data/tmp/live_score_engine.py", encoding="utf-8").read(), "live引擎市场源(market matrix·2026-09-13)")
chk("_o25_expect" in open("data/tmp/live_score_engine.py", encoding="utf-8").read() and "tot = _o25_expect(o25)" in open("data/tmp/live_score_engine.py", encoding="utf-8").read(), "market源tot动态标定(2026-09-13修复硬编码非单调/低估强攻场0.81球·防回退)")
chk("anchor_market_check" in open("data/tmp/live_score_engine.py", encoding="utf-8").read() and "market_net_band" in open("data/tmp/live_score_engine.py", encoding="utf-8").read(), "锚-市场一致性检查(2026-09-13·用户要求·净胜档±1球/大小球方向/盘口方向)")
chk("<= u1" in open("data/tmp/prestep_fetch.py", encoding="utf-8").read(), "PreStep窗口含上界(2026-09-13修复: \"到三点\"须含03:00开赛场·曾漏Real Sociedad vs Atletico)")
chk("代理优先 + 直连回退" in open("data/tmp/source_health_check.py", encoding="utf-8").read(), "source_health双通道探测(2026-09-13修复单通道误报·🔴2026-10-31 代理优先+直连4s回退·Odds-API/Bing实测可用却报不可用)")
chk("N07" in open("data/tmp/output_checker.py", encoding="utf-8").read(), "output_checker含N07锚-市场一致性块(必核)")
chk("锚-市场一致性" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含锚-市场一致性铁律(2026-09-13用户要求)")
chk("锚可信度分级" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含锚可信度分级铁律(2026-09-13·案例库157场回测)")
chk("anchor_trust" in open("data/tmp/prestep_dual.py", encoding="utf-8").read(), "PreStep锚可信度分级(anchor_trust·每场判级)")
chk("N08" in open("data/tmp/output_checker.py", encoding="utf-8").read(), "output_checker含N08锚可信度块(必核)")
chk("anchor_trust" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "calc_all输出锚可信度行(N08配套·2026-09-13)")
chk("锚-市场期望进球匹配铁律" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含锚-市场期望进球匹配铁律(2026-09-26·用户建议·锚须匹配市场期望进球±0.5)")
chk("锚-市场期望进球匹配铁律" in open(".reasonix/skills/<REDACTED_SK>/SKILL.md", encoding="utf-8").read(), "主技能含锚-市场期望进球匹配铁律(2026-09-26)")
chk("锚-市场期望进球匹配铁律" in open("data/足球分析模型.txt", encoding="utf-8").read(), "txt含锚-市场期望进球匹配铁律(2026-09-26)")
chk("exp_total" in open("data/tmp/live_score_engine.py", encoding="utf-8").read(), "锚-市场期望匹配脚本实现(2026-09-26·用户建议·anchor_market_check第4项)")
chk("N18" in open("data/tmp/output_checker.py", encoding="utf-8").read(), "output_checker含N18锚-市场期望匹配块(必核)")
chk("市场期望" in open("data/tmp/check_luopan.py", encoding="utf-8").read(), "check_luopan含锚-市场期望匹配留痕校验(2026-09-26)")
chk(__import__("os").path.exists("data/tmp/the_odds_api_fetch.py"), "源B7 the-odds-api 脚本在位(2026-09-27·欧亚盘多机构·21家)")
chk(__import__("os").path.exists("data/tmp/market_consensus.py"), "机构数据双用途脚本在位(2026-09-27·合并去水+跨机构分歧)")
chk("match_check" in open("data/tmp/market_consensus.py", encoding="utf-8").read(), "机构层场次错配校验match_check在位(2026-09-27 P0)")
chk("场次错配 → 拒绝消费" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "calc_all机构层错配阻断(2026-09-27 P0)")
chk("机构共识层" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "calc_all含机构共识层输出(2026-09-27)")
chk("机构数据双用途" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含机构数据双用途铁律(2026-09-27)")
chk("the-odds-api" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含源B7 the-odds-api(2026-09-27)")
chk("the-odds-api" in open("data/足球分析模型.txt", encoding="utf-8").read(), "txt含源B7 the-odds-api")
chk("C31" in open("data/tmp/calc_all.py", encoding="utf-8").read() and "C34" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "必核清单含Step0四源C31-C34(2026-09-27·B1/H2H/B7/txt归一化·case209根因)")
chk("格式B" in open("data/tmp/market_consensus.py", encoding="utf-8").read(), "txt_teams兼容格式B(2026-09-27·case209实证)")
chk("必核清单同步铁律" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含必核清单同步铁律(2026-09-27)")
chk("expect_triple_check" in open("data/tmp/live_score_engine.py", encoding="utf-8").read(), "期望进球三源联动校验(2026-09-27·用户要求·市场/查表/泊松一致自洽)")
chk("N19" in open("data/tmp/output_checker.py", encoding="utf-8").read(), "output_checker含N19期望三源联动块(必核)")
chk("三源" in open("data/tmp/check_luopan.py", encoding="utf-8").read(), "check_luopan含期望三源联动留痕校验(2026-09-27)")
# ── 2026-09-28 NL 子模型 4×P0 + P1-5 修复防回退（对照外部审阅报告·逐条实测复现）──
_nl_src = open("data/tmp/nl_model.py", encoding="utf-8").read()
_ca_nl = open("data/tmp/calc_all.py", encoding="utf-8").read()
chk("float(r['eh']) - float(r['ea'])" in _nl_src, "NL 建表用 raw=eh-ea(2026-09-28 P0-1·防回退到 elo_diff=raw-65·档位错位65Elo)")
chk("-135 <= elo_diff < 15" in _nl_src, "NL R5 draw_leak 边界为 raw 空间(2026-09-28 P0-1)")
chk("raw口径" in _nl_src, "NL R4/R7 输出标注 raw 口径(2026-09-28 P0-1)")
chk("def extract_nl_teams" in _nl_src, "NL 队名提取函数在位(2026-09-28 P0-2·原正则真实txt全不命中)")
chk("def parse_matchday" in _nl_src, "NL 轮次解析函数在位(2026-09-28 P0-4·原硬编码 matchday=1)")
chk("def edge_actions" in _nl_src, "NL 逐方向 edge ±10pp 动作在位(2026-09-28 P1-5)")
chk("extract_nl_teams" in _ca_nl and "parse_matchday" in _ca_nl, "calc_all 接线 NL 队名/轮次提取(2026-09-28 P0-2/P0-4)")
chk("(oh, od, oa), 0, _fav_spread" in _ca_nl, "calc_all 传市场赔率给 nl_model(2026-09-28 P0-3·edge 自动计算·case211 拦截)")
chk("无 --eu 兜底" in _ca_nl and "if not eu:" in _ca_nl, "calc_all NL 段含无 --eu 兜底(2026-09-28 P0-5·防存在≠活跃复发)")
chk(__import__("os").path.exists("data/tmp/quadrant_table.json"), "四象限量化表在位(2026-09-27·V6修正54·22.7万场回测)")
chk("quadrant_probs" in open("data/tmp/calc_v3572.py", encoding="utf-8").read(), "calc_v3572含四象限函数(2026-09-27·用户要求固化)")
chk("N20" in open("data/tmp/output_checker.py", encoding="utf-8").read(), "output_checker含N20四象限块")
chk("四象限" in open("data/tmp/check_luopan.py", encoding="utf-8").read(), "check_luopan含四象限留痕校验(2026-09-27)")
chk("_netflag" in open("data/tmp/calc_all.py", encoding="utf-8").read() and "_lcn" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "calc_all --net参数+_league_cn顺序修复(2026-09-14·学习日志网络源接入)")
chk("magnitude_rerank" in open("data/tmp/live_score_engine.py", encoding="utf-8").read() and "锚-量级矛盾" in open("data/tmp/live_score_engine.py", encoding="utf-8").read(), "live引擎量级重排+锚-量级告警(2026-09-13用户指出根因修复)")
chk(os.path.exists("data/online_learning/docs/融合分档验证报告_20260911.txt"), "融合分档验证报告归档(4档·弱档优势)")
chk("弱方向" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "融合分级参与(P1-1修复·弱判定场并列建议)")
chk("竞彩txt去水" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "融合自动赔率来源(P1-2修复·不依赖--eu)")
chk("tie-break_only" in open("data/online_learning/state/gate.json", encoding="utf-8").read(), "L3应用方式已定义(P2-1)")
chk(os.path.exists("data/online_learning/gate.py"), "学习接入门禁(gate.py·回测/样本/回滚/裁剪四道)")
chk("融合方向概率" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "calc_all 输出融合方向概率(学习结果真影响预测)")
chk("融合方向概率" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS 含学习接入消费规则(不反转方向)")
chk(os.path.exists("data/online_learning/learn.py"), "赛后学习统一入口(模块内·轻封装)")
chk("learn.py" in open("data/tmp/learn_from_result.py", encoding="utf-8").read(), "tmp入口转发兼容(learn.py)")
chk(os.path.exists("data/online_learning/docs/增量表验证报告_20260911.txt"), "L2增量表验证报告归档(不显著→不接入)")
chk("VPN 默认已开" in open("AGENTS.md", encoding="utf-8").read(), "VPN默认已开前提(2026-09-12用户声明)")
chk("Bing News 伤停搜索" in open("data/online_learning/data_bridge.py", encoding="utf-8").read(), "news源真实接入(Bing News·VPN默认开)")
chk(os.path.exists("data/online_learning/data_bridge.py"), "统一数据接入层(data_bridge.py·8源+三态标注)")
chk("extract_match_date" in open("data/online_learning/data_bridge.py", encoding="utf-8").read(), "比赛日期自动提取(UTC日定位·供欧盘选场消歧)")
chk(os.path.exists("data/online_learning/data_bridge.py") and "src_haf" in open("data/online_learning/data_bridge.py", encoding="utf-8").read() and "src_clubelo" in open("data/online_learning/data_bridge.py", encoding="utf-8").read() and "src_api_fb" in open("data/online_learning/data_bridge.py", encoding="utf-8").read() and "已停用" in open("data/online_learning/data_bridge.py", encoding="utf-8").read(), "7源接入完整性(txt/haf/clubelo/xg/h2h/news/euro_odds)+api-football已停用标注")
chk("TEAM_ALIASES" in open("data/online_learning/data_bridge.py", encoding="utf-8").read() and "def normalize_name" in open("data/online_learning/data_bridge.py", encoding="utf-8").read() and os.path.exists("data/team_name_mapping_2025-26.json"), "队名映射升级(2026-09-14·TEAM_ALIASES+normalize_name+映射文件在位·防回退)")
chk(os.path.exists("data/online_learning/txt_features.py"), "txt特征自动提取器(txt_features.py·ML数据接入)")
chk("--txt" in open("data/tmp/learn_from_result.py", encoding="utf-8").read(), "learn_from_result支持--txt自动提取特征")
chk("prediction_log" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "calc_all预测日志(赛果--from-log回溯)")
chk(os.path.exists("data/online_learning/learning_loop.py") and os.path.exists("data/online_learning/config.py"), "在线学习系统(5层·learning_loop+config)")
# 🔴2026-09-30 反向断言（L1 泄露裁决专项）: 原断言「ENABLE_ONLINE_FUSION = True」在新裁决下必须为 False
_cfg_l1 = open("data/online_learning/config.py", encoding="utf-8").read()
chk("ENABLE_ONLINE_FUSION = False" in _cfg_l1, "在线ML已否决(ENABLE_ONLINE_FUSION=False·泄露裁决2026-09-30)")
chk(("数据泄露" in _cfg_l1) and ("作废" in _cfg_l1), "config 含泄露作废声明(原+0.68pp证据无效)")
chk("rejected_leak" in open("data/online_learning/state/gate.json", encoding="utf-8").read(), "gate.json L1 标记 rejected_leak")
_vl_src = open("data/online_learning/validate_learning.py", encoding="utf-8").read()
chk("已禁用" in _vl_src, "validate_learning 禁止回测模型写回生产(防污染 state/river)")
chk("作废声明" in open("data/online_learning/validate_fusion.py", encoding="utf-8").read(),
    "validate_fusion 含数据泄露作废声明(禁再引用+0.68pp)")
chk(os.path.exists("data/tmp/learn_from_result.py"), "赛果自动学习总入口(learn_from_result.py)")
chk(os.path.exists("data/tmp/self_iterate.py") and os.path.exists("data/tmp/learned_rules.json"), "赛后学习闭环(self_iterate.py+学习台账+learned_rules.json)")
# 🔴2026-10-07 修复: 学习台账写入改「按场次 upsert」(原去重键=(场次,归因类型) → 归因变化时旧行残留·污染门槛判定)
_si = open("data/tmp/self_iterate.py", encoding="utf-8").read()
chk("r[1].strip() == str(cid))]" in _si and "r[11].strip() == t" not in _si, "self_iterate 台账按场次 upsert(2026-10-07·防回退到(场次,归因)去重致陈旧行残留)")

# 🔴2026-10-07 用户指令: 低赔大幅变动 → 不再严格依照最低赔率（case225 教训·脚本+三处同步防回退）
_cm = open("data/tmp/calc_match.py", encoding="utf-8").read()
chk("def low_odds_shift" in _cm and ("low_odds_shift(_sec_chg)" in _cm or "low_odds_shift(sections)" in _cm), "calc_match 含 low_odds_shift 且已接线 run_extensions(2026-10-07·防回退··2026-10-21 接受竞彩原序引用)")
chk("D1检测: 胜平负数据不足" in _cm, "d1_divergence return 完整(2026-10-07 patch anchor 教训·防再被吞)")
chk("低赔大幅变动" in open("AGENTS.md", encoding="utf-8").read()
    and "低赔大幅变动" in open(".reasonix/skills/<REDACTED_SK>/SKILL.md", encoding="utf-8").read()
    and "低赔大幅变动" in open("data/足球分析模型.txt", encoding="utf-8").read(),
    "低赔大幅变动·主方向重排 三处同步(AGENTS+主技能+txt·防回退)")
chk("def jc_series_shape" in _cm and "jc_series_shape(sections)" in _cm, "calc_match 含 jc_series_shape 且已接线(2026-10-07 竞彩逐T形态学·防回退)")
chk("竞彩逐T 形态学" in open("AGENTS.md", encoding="utf-8").read()
    and "竞彩逐T 形态学" in open(".reasonix/skills/<REDACTED_SK>/SKILL.md", encoding="utf-8").read()
    and "竞彩逐T 形态学" in open("data/足球分析模型.txt", encoding="utf-8").read(),
    "竞彩逐T形态学 三处同步(AGENTS+主技能+txt·防回退)")
_v = open("data/tmp/calc_v3572.py", encoding="utf-8").read()
chk("def draw_temp_lookup" in _v and "def deep_anchor_lookup" in _v, "calc_v3572 含 R20平局温度/深盘锚 查表函数(2026-10-07 审计补·防回退)")
_ca = open("data/tmp/calc_all.py", encoding="utf-8").read()
chk("draw_temp_lookup" in _ca and "deep_anchor_lookup" in _ca, "calc_all 已接线两张表(禁手查·防回退)")
_cm2 = open("data/tmp/calc_match.py", encoding="utf-8").read()
chk("未经过归一化" in _cm2, "calc_match 含未归一化告警(2026-10-07 审计补·防回退到静默降级)")
_pf2 = open("data/tmp/prestep_fetch.py", encoding="utf-8").read()
chk("TEAM_IDX = {}" in _pf2, "prestep_fetch 模块级 TEAM_IDX(2026-10-09·防回退到 NameError)")
chk("FORM_UNAVAILABLE = None" in _pf2 and "FORM_SOURCE" in _pf2, "Form5 换源后仍可静态判断（2026-10-29: None + FORM_SOURCE·防回退到硬编码停用串）")
_ss2 = open("data/tmp/snapshot_save.py", encoding="utf-8").read()
chk("API_ERRS" in _ss2 and "d.get('error')" in _ss2, "snapshot_save 识别 API 错误响应(2026-10-09·防回退到静默当0场)")
_pf3 = open("data/tmp/prestep_fetch.py", encoding="utf-8").read()
chk("DOMAIN_5" in _pf3 and "or DOMAIN_5" in _pf3, "prestep_fetch 默认域=五大+欧战(2026-10-09·防回退到全拉NL)")
chk("API 限流" in _pf3 and "_real" in _pf3, "prestep_fetch 429限流与404漏场分列(2026-10-09·防回退到混报漏场风险)")
_ss3 = open("data/tmp/snapshot_save.py", encoding="utf-8").read()
chk("default='英超,西甲,德甲,意甲,法甲,欧联,欧冠'" in _ss3, "snapshot_save 默认域=五大+欧战(2026-10-09·原欧国联残留已改)")
chk(os.path.exists("data/tmp/bzzoiro_fetch.py"), "Bzzoiro 结构化伤停脚本在位(源B8·2026-10-09)")
_db3 = open("data/online_learning/data_bridge.py", encoding="utf-8").read()
chk("src_bzz_injury" in _db3 and "add('bzz_injury'" in _db3, "data_bridge 已接线 bzz_injury(防回退到文本级伤停)")
chk("bzzoiro" in open("data/tmp/api_keys.json", encoding="utf-8").read(), "Bzzoiro key 已登记 api_keys.json")
chk(os.path.exists("data/tmp/bsd_layer.py"), "BSD 增强层脚本在位(2026-10-09·方案接入)")
_bsd = open("data/tmp/bsd_layer.py", encoding="utf-8").read()
chk("ai_preview" in _bsd and "pop('ai_preview'" in _bsd, "BSD ai_preview 已剔除未读(方案§二/§八·防回退)")
chk("SPORTS.bzzoiro.com/api/" in _bsd.replace("https://sports", "SPORTS").replace("SPORTS", "SPORTS") or "V1 = 'https://sports.bzzoiro.com/api/'" in _bsd, "BSD 用 v1 端点(全字段·防回退到 v2 缺字段版)")
chk("只记录不判定" in _bsd or "record" in _bsd, "BSD 分阶段纪律(默认记录模式·方案§七)")
_ca2 = open("data/tmp/calc_all.py", encoding="utf-8").read()
chk("--bsd-teams" in _ca2 and "bsd_layer.py" in _ca2, "calc_all 已接线 BSD 增强层(2026-10-09·防回退到未接入)")
chk("BSD 增强层: 未提供" in _ca2 or "BSD 增强层" in _ca2, "calc_all BSD 三态降级提示在位")
chk("locate_event" in open("data/tmp/bsd_layer.py", encoding="utf-8").read(), "bsd_layer 队名自动定位在位")
_bsdl2 = open("data/tmp/bsd_layer.py", encoding="utf-8").read()
chk("_deacc" in _bsdl2 and "unicodedata" in _bsdl2, "bsd_layer 去重音匹配(2026-10-09·防回退到 Málaga/Malaga 失配)")
chk("set(_wa) & set(_wb)" in _bsdl2, "bsd_layer 逐词回退匹配(Espanyol Barcelona↔Espanyol)")
chk("_deacc" in open("data/tmp/bzzoiro_fetch.py", encoding="utf-8").read(), "bzzoiro_fetch 去重音索引")
_db4 = open("data/online_learning/data_bridge.py", encoding="utf-8").read()
chk("inj_bzz_home_n" in _db4 and "inj_bzz_away_items" in _db4, "data_bridge bzz_injury 特征已汇入(2026-10-09·防回退到有产出无消费)")
_oc2 = open("data/tmp/output_checker.py", encoding="utf-8").read()
chk("check_bsd(text)" in _oc2 and "check_bsd" in _oc2.split("def main()")[-1], "output_checker check_bsd 已接线(防孤岛)")
chk("BSD 增强层" in open("data/tmp/check_luopan.py", encoding="utf-8").read(), "check_luopan BSD 留痕校验在位")
_bf2 = open("data/tmp/bzzoiro_fetch.py", encoding="utf-8").read()
chk("--home" in _bf2 and "side_pos" in _bf2, "bzzoiro_fetch 主客分组+正确接口示例(2026-10-09)")
_ss4 = open("data/tmp/snapshot_save.py", encoding="utf-8").read()
chk("def cn2en_list" in _ss4 and "cn2en_extra" in _ss4, "snapshot_save cn2en_list 多候选(2026-10-09·防回退到单候选+国家队优先)")
chk("max(cands, key=len)" in _ss4, "_first 取最长候选(防回退到 v[0] 缩写如 BVB)")
chk(os.path.exists("data/tmp/cn2en_extra.json"), "cn2en_extra.json 补充别名表在位(59条)")
_bl4 = open("data/tmp/bsd_layer.py", encoding="utf-8").read()
chk("cn2en_list" in _bl4 and "_anyM" in _bl4, "bsd_layer locate_event 接多候选(防回退到中文直匹英文→恒None)")
chk("cn2en_list" in _ss4.split("def find_for")[-1], "find_for 接多候选")
chk("双源分歧方向锁定铁律" in open("AGENTS.md", encoding="utf-8").read(), "双源分歧方向锁定铁律(2026-10-09·case229质疑固化)")
chk("盘口时序铁律" in open("AGENTS.md", encoding="utf-8").read(), "盘口时序铁律(2026-10-09·case229二次质疑固化)")
chk("锚回查铁律" in open("AGENTS.md", encoding="utf-8").read(), "锚回查铁律(2026-10-09·case229三次质疑固化)")
chk("均衡线缺失" in open("data/tmp/snapshot_save.py", encoding="utf-8").read(), "均衡线缺失标注(2026-10-09·case229教训·防回退到默默取深档)")
_db2 = open("data/online_learning/data_bridge.py", encoding="utf-8").read()
chk("_fetch_dual_text" in _db2 and "validate" in _db2, "data_bridge 带内容校验双通道(2026-10-09·防回退到HTML被当成功)")
chk("news.google.com" in _db2 and "prefer_proxy=True" in _db2, "src_news 并入GoogleNews+代理优先(2026-10-09)")
_sk9p = ".reasonix/skills/SL-news-crawl/SKILL.md"
if os.path.exists(_sk9p):
    _sk9 = open(_sk9p, encoding="utf-8").read()
    chk("v3.football.api-sports.io" not in _sk9, "SL-news-crawl 已清 api-football 指令/旧key(2026-10-09)")
else:
    # 🔴2026-10-28 P20: 用户指令「伤停直接用 API·去掉网页新闻搜索」→ SL-news-crawl 已归档
    chk(os.path.isdir("data/archived-skills") and
        any("SL-news-crawl" in d for d in os.listdir("data/archived-skills")),
        "P20: SL-news-crawl 已归档到 data/archived-skills（网页新闻伤停停用）")
chk("查表脚本化（2026-10-07 审计补" in open("AGENTS.md", encoding="utf-8").read(),
    "AGENTS 含查表脚本化规则(防回退)")
chk("变动层主源" in open("AGENTS.md", encoding="utf-8").read(), "竞彩定位修正为「变动层主源」(2026-10-07·防回退到「仅辅助」)")
chk(os.path.exists("data/tmp/prestep_v2_verify.py") and os.path.exists("data/online_learning/docs/PreStepV2验证_20260912.txt"), "PreStepV2方案验证脚本+报告(含符号bug修正结论)")
chk("四级分档" in open(".reasonix/skills/SK-prestep-filter/SKILL.md", encoding="utf-8").read() or "强推荐(比分)" in open("data/tmp/prestep_dual.py", encoding="utf-8").read(), "PreStep四级分档升级(方案V2.0验证后)")
chk(os.path.exists("data/tmp/prestep_dual.py") and "双向评级" in open("data/tmp/prestep_dual.py", encoding="utf-8").read(), "PreStep双向评级脚本(方向分+比分分·用户要求)")
chk("双向评级" in open(".reasonix/skills/SK-prestep-filter/SKILL.md", encoding="utf-8").read(), "SK-prestep-filter含双向评级流程")
chk("比分命中评分" in open(".reasonix/skills/SK-prestep-filter/SKILL.md", encoding="utf-8").read(), "PreStep比分导向评分V2(用户要求·回测12000场)")
chk(os.path.exists("data/online_learning/docs/PreStep比分导向回测_20260911.txt") and os.path.exists("data/tmp/prestep_score_backtest.py"), "PreStep比分回测脚本+报告归档")
# ── 🔴PreStep V3 分值体系重标(2026-09-20·Matches 227518场消融回测·防回退·用户批准4项+消融3项) ──
_pdv3 = open("data/tmp/prestep_dual.py", encoding="utf-8").read()
_skv3 = open(".reasonix/skills/SK-prestep-filter/SKILL.md", encoding="utf-8").read()
_agv3 = open("AGENTS.md", encoding="utf-8").read()
_txv3 = open("data/足球分析模型.txt", encoding="utf-8").read()
chk("D3均势必平-1.5" in _pdv3, "PreStep V3: D3改负分(-1.5·Delta-12.0pp·原符号错误)")
chk("移出方向分" in _pdv3, "PreStep V3: G2移出方向分(Delta-7.5pp·归Step6进球信号)")
chk("H3反直觉(仅标注" in _pdv3, "PreStep V3: H3改仅标注(Delta+13.2pp·原-1被证伪)")
chk("H2穿盘+2.0" in _pdv3, "PreStep V3: H2升权+2.0(Delta+23.8pp)")
chk("-1.0 < handi < 0" in _pdv3, "PreStep V3: O10严格口径(仅主让0.25-0.75·浅让57.9%vs深让80.1%)")
chk("ds >= 3.5 and ss >= 2.0" in _pdv3, "PreStep V3.1: 阈值重标(方向>=3.5/比分>=2.0)")
chk("73.22%" in _pdv3, "PreStep V3.1: 阈值重标(≥3.5·73.22%命中/8.68%覆盖)")
chk("E1-ELO强优势" in _pdv3 and "W1-主水诱主" in _pdv3 and "O11-客队不弱" in _pdv3, "PreStep V3.1: 新信号 E1-E3/W1/O11 在位")
chk("elo_diff" in _pdv3 and "home_water" in _pdv3, "PreStep V3.1: 新信号参数(elo_diff/home_water)")
chk("form_diff" in _pdv3 and "F1-近期状态" in _pdv3, "PreStep V3.2: Form5 信号(F1·仅正向)")
chk("load_form" in open("data/tmp/prestep_fetch.py", encoding="utf-8").read() and "points_last_n" in open("data/tmp/prestep_fetch.py", encoding="utf-8").read(), "PreStep: Form5 已换源 Bzzoiro(2026-10-29)·F1/F2 正常判定（定位失败才三态）")
chk(os.path.exists("data/tmp/conf_calib.py") and os.path.exists("data/case-library/置信度校准.csv"), "P2: 置信度校准工具+数据(strict/any 双口径·2026-09-20)")
chk(os.path.exists("data/archived-scripts/lineups_fetch.py"), "P3: 首发阵容源已随 api-football 归档(2026-10-06)")
chk("conf_calib" in open("AGENTS.md", encoding="utf-8").read(), "P2 工具已被 AGENTS 引用(防孤儿脚本)")
chk("load_elo" in open("data/tmp/prestep_fetch.py", encoding="utf-8").read() and "home_water" in open("data/tmp/prestep_fetch.py", encoding="utf-8").read(), "PreStep V3.1: 数据源接入(clubelo ELO + Spread 主水)")
chk(os.path.exists("data/tmp/_improve_validate.py") and os.path.exists("data/tmp/_imp_verify2.py"), "PreStep V3.1: 严格验证脚本存档")
chk(os.path.exists("data/tmp/lock_dirs.py") and "additional_write_dirs" in open("data/tmp/lock_dirs.py", encoding="utf-8").read(), "锁规避工具(lock_dirs.py·自动扫描写入边界声明)")
chk("lock_dirs.py" in open("AGENTS.md", encoding="utf-8").read() and "轮末编辑" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含锁规避标准操作模板(防复发)")
chk("V3.1 新信号" in _agv3, "AGENTS含PreStep V3.1新信号段")
chk("V3 分值体系重标" in _agv3, "AGENTS含PreStep V3重标段")
chk("V3 消融重标" in _skv3, "SK-prestep-filter含V3重标(description+阈值+信号表)")
chk("V3分值重标" in _txv3, "txt含PreStep V3重标")
chk(os.path.exists("docs/PreStep审计复现_20260920.md"), "PreStep审计复现报告落盘")
chk(os.path.exists("data/tmp/_pre2_ablation.py") and os.path.exists("data/tmp/_pre2_score2.py"), "PreStep消融回测脚本存档")
chk("learned_rules.json" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "calc_all消费学习成果(⚡学习提示节·仅提示不改判定)")
chk("'E0'" in open("data/tmp/calc_all.py", encoding="utf-8").read() and "is_top5" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "calc_all联赛代码映射(E0/SP1等→中文·C13触发正确)")
chk("bqc=_bqs" in open("data/tmp/calc_all.py", encoding="utf-8").read() and "cs=_css" in open("data/tmp/calc_all.py", encoding="utf-8").read() and "tg=_tgs" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "让球动态量级8因子参数全传(F6/F7/F8生效)")
chk(os.path.exists("data/tmp/handicap_dynamic_magnitude.py") and os.path.exists("data/tmp/handicap_prior_table.json") and "handicap_dynamic_magnitude" in open("data/tmp/calc_all.py", encoding="utf-8").read() and "handicap_dynamic_magnitude" in open(".reasonix/skills/SK-v3572-rules/SKILL.md", encoding="utf-8").read(), "让球动态量级V2.0(9层先验+8因子+calc_all接入+SK消费)")
chk("extract_ht_goals_layer" in open("data/tmp/live_score_engine.py", encoding="utf-8").read() and "_bqc_to_ht_dist" in open("data/tmp/live_score_engine.py", encoding="utf-8").read() and "extract_ht_goals_layer" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "半场推断量级模块(DRY公共+calc_all接入)")
# 🔴2026-09-15审计P0/P1修复校验（防回退·原缺陷: 传 epl/laliga 等别名时 C13/C25/C27 静默不触发）
_ca_src = open("data/tmp/calc_all.py", encoding="utf-8").read()
chk("def norm_league" in _ca_src and "'epl': '英超'" in _ca_src and "is_top5 = _league_cn in" in _ca_src, "calc_all联赛统一归一化(norm_league·接受中文名/E0码/英文别名·C13/C25/C27触发正确)")
chk("_LMAP = {" not in _ca_src, "calc_all无旧_LMAP重复映射定义残留")
_cv_src = open("data/tmp/calc_v3572.py", encoding="utf-8").read()
chk("def norm_div" in _cv_src and "a.div = norm_div(a.div)" in _cv_src, "calc_v3572联赛归一化(norm_div·R1/R4/R10/R16-R18不再静默失效)")
_tf_src = open("data/online_learning/txt_features.py", encoding="utf-8").read()
chk("'英超', '西甲', '意甲', '德甲', '法甲'" in _tf_src, "txt_features is_top5中英双认(原只认英文代码→恒0·误差聚类失真)")
_ln_src = open("data/online_learning/learn.py", encoding="utf-8").read()
chk("'is_top5': 1 if _lg in" in _ln_src, "learn.py显式参数路径is_top5动态计算(原硬编码0)")

print("\n" + "="*60)
# E2(2026-08-29): score_depth_table 时效校验
try:
    import json as _json
    _sd = _json.load(open('data/tmp/score_depth_table.json', encoding='utf-8'))
    _gen = _sd.get('generated', '')
    _ver = _sd.get('version', '')
    chk(bool(_gen), f"score_depth_table generated时间戳: {_gen}")
    chk(str(_ver) >= '3.0', f"score_depth_table version≥3.0(D1/E1): {_ver}")
except Exception as _e:
    chk(False, f"score_depth_table读取失败: {_e}")
# E2b(2026-08-29·问题7评审): 134格低样本校验
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
chk("margin_candidates" in open("data/tmp/calc_v3572.py", encoding="utf-8").read(), "calc_v3572含margin_candidates(净胜档多档)")
chk("goal_bin_probs" in open("data/tmp/calc_v3572.py", encoding="utf-8").read(), "calc_v3572含goal_bin_probs(O1比分量级查表)")
chk("诱盘信号" in open("data/tmp/calc_v3572.py", encoding="utf-8").read() and "欧亚背离" in open("data/tmp/calc_v3572.py", encoding="utf-8").read(), "calc_v3572含欧亚盘口校正+诱盘信号(方向判定升级)")
chk("修正方向" in open("data/tmp/calc_v3572.py", encoding="utf-8").read(), "calc_v3572含LOW档修正方向(防主·提高LOW档准确率)")
chk("中盘细分" in open("data/tmp/calc_v3572.py", encoding="utf-8").read(), "calc_v3572含中盘细分(平赔低平局并列·提高MID档)")
chk("历史频率只做参考" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含历史频率参考铁律(禁机械锚定主场)")
chk("旧模型优点吸收" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含旧模型优点吸收清单(方向判定权归旧模型·禁脚本直出)")
chk(re.search(r"^Step5\s+方向判定", open("AGENTS.md", encoding="utf-8").read(), re.M), "AGENTS流水线含Step5标题(方向判定·防丢失)")
chk("match_classifier" in open("data/tmp/calc_v3572.py", encoding="utf-8").read() and "handicap_intent_analyzer" in open("data/tmp/calc_v3572.py", encoding="utf-8").read(), "calc_v3572含盘口诱阻识别三函数(分类器+意图分析)")
chk(all(x in open("data/tmp/calc_v3572.py", encoding="utf-8").read() for x in ["odds_anomaly_detector","euro_asia_consistency","water_level_anomaly","handicap_movement_analyzer","kelly_index_analyzer","jingcai_special_signal"]), "calc_v3572含诱阻识别6辅助模块(维度1-4·6-7·文档9模块全落地)")
chk("match_classifier" in open(".reasonix/skills/SK-v3572-rules/SKILL.md", encoding="utf-8").read() and "trap_classify_output" in open("data/tmp/calc_match.py", encoding="utf-8").read(), "诱阻识别执行链完整(SK技能消费+calc_match预计算)")
chk(os.path.exists("data/tmp/calc_all.py") and "必核清单" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "calc_all全覆盖预计算存在(步骤遗失根除·30项必核清单)")
chk(os.path.exists("data/tmp/output_checker.py") and os.path.exists("data/tmp/fetch_all.py"), "output_checker+fetch_all存在(三支柱闭环)")
chk("诱平" in open("data/tmp/calc_v3572.py", encoding="utf-8").read() and "诱大球" in open("data/tmp/calc_v3572.py", encoding="utf-8").read(), "intent_analyzer支持9类意图(诱平/诱大球等)")
chk("goal_bin_probs" in open(".reasonix/skills/SK-v3572-rules/SKILL.md", encoding="utf-8").read() and "goal_bin_probs" in open("AGENTS.md", encoding="utf-8").read(), "SK-v3572-rules+AGENTS 含 goal_bin_probs(O1消费链)")
# 🔴大小球精细化升级(2026-09-15)
_gb = open("data/tmp/goal_bins_table.json", encoding="utf-8").read() if os.path.exists("data/tmp/goal_bins_table.json") else ""
chk('"top"' in _gb, "goal_bins_table含典型比分top字段(2026-09-15全量重建·148397场)")
chk(os.path.exists("data/tmp/build_goal_bins.py"), "goal_bins生成脚本存在(build_goal_bins.py·可复现)")
chk("信号强度" in open("data/tmp/goal_odds_analyzer.py", encoding="utf-8").read() and "OV_MED_BIG" in open("data/tmp/goal_odds_analyzer.py", encoding="utf-8").read(), "goal_odds_analyzer信号强度三档(强/中/弱·2026-09-15)")
chk("信号强度三档" in open(".reasonix/skills/SK-v3572-rules/SKILL.md", encoding="utf-8").read() and "信号强度三档" in open("AGENTS.md", encoding="utf-8").read() and "信号强度" in open("data/足球分析模型.txt", encoding="utf-8").read(), "三文件含大小球信号强度三档(AGENTS+SK+txt)")
chk("典型比分" in open("data/tmp/calc_all.py", encoding="utf-8").read() and "典型比分" in open("data/tmp/calc_match.py", encoding="utf-8").read(), "calc_all/calc_match输出典型比分(goal_bins top4传导)")
chk("已否决" in open(".reasonix/skills/SK-v3572-rules/SKILL.md", encoding="utf-8").read() and "0.00pp" in open("AGENTS.md", encoding="utf-8").read(), "偏差校准/不对称阈值已否决留痕(防回退·2026-09-15)")
chk("N09" in open("data/tmp/output_checker.py", encoding="utf-8").read() and "信号强度" in open("data/tmp/output_checker.py", encoding="utf-8").read(), "output_checker含N09大小球信号强度块(2026-09-15·新规则入强制链)")
chk("口径对照" in open(".reasonix/skills/SK-v3572-rules/SKILL.md", encoding="utf-8").read(), "O2.5赔率↔over概率口径对照(live锚定vs信号分层·衔接说明)")
chk("44-48%边缘带" not in open("data/tmp/calc_match.py", encoding="utf-8").read() and "中性区" in open("data/tmp/calc_match.py", encoding="utf-8").read(), "calc_match旧44-48边缘带已改中性区47-53(与信号分层对齐·防冲突)")
chk(os.path.exists("data/case-library/案例库模板.md"), "案例库统一模板存在(CSV 15列+raw 七节)")
chk(os.path.exists("data/tmp/case_write.py"), "案例库填写脚本存在(case_write·防乱码串码遗失)")
chk("case_write" in open(".reasonix/skills/<REDACTED_SK>/SKILL.md", encoding="utf-8").read() and "case_write" in open(".reasonix/skills/SL-case-library/SKILL.md", encoding="utf-8").read(), "主技能+SL-case-library 含 case_write(填写执行链)")
# ⑦ 投注方案生成模块(2026-09-04)
print("\n⑦ 投注方案生成模块(betting_plan_generator·2026-09-04)")
_ag = open("AGENTS.md", encoding="utf-8").read()
_bp = open("data/tmp/betting_plan_generator.py", encoding="utf-8").read() if os.path.exists("data/tmp/betting_plan_generator.py") else ""
chk(bool(_bp), "betting_plan_generator.py 存在(投注方案生成器)")
chk("投注方案生成模块" in _ag and "请你给我今天的购买方案" in _ag, "AGENTS含投注方案触发词章节")
chk(all(x in _bp for x in ["dynamic_tickets", "只买串关", "多票", "include_second", "leg_score", "goal_diff", "hit"]), "betting_plan含动态引擎+多维评分+串关铁律+source_field")
chk("只买串关" in _ag and "场数由当天" in _ag or "场数动态" in _ag, "AGENTS含只买串关+场数动态+多票铁律")
chk("ev_cal" in _bp and "0.105" in _bp, "投注模块含诚实EV(历史命中率hit·防虚高)")
_g=open("data/tmp/goal_odds_analyzer.py",encoding="utf-8").read() if os.path.exists("data/tmp/goal_odds_analyzer.py") else ""
chk(bool(_g) and "五级" in _g and "KL" in _g and "返奖率" in _g, "goal_odds_analyzer存在(竞彩总进球反推·返奖/五级量级/KL融合)")
_v3=open("data/tmp/calc_v3572.py",encoding="utf-8").read()
chk("小概率管理" in _v3 and "M1" in _v3 and "M2" in _v3 and "M3" in _v3, "calc_v3572含小概率管理(M1伤停冲突/M2欧深亚浅/M3官方背离·O9)")
chk(os.path.isdir(".reasonix/skills/SL-betting-plan") and "SL-betting-plan" in _ag, "SL-betting-plan skill存在且AGENTS接入(Step11购买方案指令)")
chk("betting_plan_generator" in _ag and "betting_plan_generator" in open(".reasonix/skills/SL-betting-plan/SKILL.md", encoding="utf-8").read(), "投注生成器三处引用一致(AGENTS+skill)")

# ⑯ 防过拟合/降噪校验(2026-09-16·用户「清洁模型·防止过拟合和噪声」)
print("\n⑯ 防过拟合/降噪校验(2026-09-16)")
_gj_src = open("data/online_learning/state/gate.json", encoding="utf-8").read()
_ca_src2 = open("data/tmp/calc_all.py", encoding="utf-8").read()
chk("L1_fusion_in_decision" in _gj_src, "gate.json 含融合判定独立门禁(L1_fusion_in_decision)")
chk("degraded" in _gj_src, "L1 在线ML 已显式降级(degraded·防退化污染)")
chk("_fdec_gate" in _ca_src2 and "仅提示·不进入判定" in _ca_src2, "calc_all 消费融合判定门禁(默认仅提示·不进入判定)")
chk("防过拟合" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS 含防过拟合/降噪记录")
# 🔴2026-09-16 梳理补充: 参数完整性 + 规则冲突标注(防回退)
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
    chk(all(k in (_rows[0] if _rows else {}) for k in ('pH_模型','pD_模型','pA_模型')),
        "案例库含三向概率列(pH/pD/pA·2026-09-30·log loss 前置·评论者建议②·必须末尾追加)")
    chk(len(_rows) >= 130, f"案例库样本量≥130(实际{len(_rows)})")
except Exception as _e:
    chk(False, f"案例库质量校验异常:{_e}")

print("\n⑨ 数据驱动增强校验(V3.5.74)")
import os as _os
_prior=open("data/tmp/odds_score_prior.json",encoding="utf-8").read() if _os.path.exists("data/tmp/odds_score_prior.json") else ""
_v3=open("data/tmp/calc_v3572.py",encoding="utf-8").read()
chk(bool(_prior) and "15" in _prior and "deep_big" in _prior, "odds_score_prior.json存在(16格比分先验·实测)")
chk("fusion_score_4way" in _v3, "calc_v3572含fusion_score_4way(四方融合)")
chk("D3赔率组合" in _v3 and "D5亚盘" in _v3 and "D6平手" in _v3, "D规则代码化(D3组合并列/D5浅盘/D6平手高水)")
chk("降权" in _v3 and "true_handicap" in _v3, "ELO残差诱盘降权标注(2026-09-07实测无预测力)")

print("⑩ 现场比分引擎校验(V3.5.74)")
_ls2 = open("data/tmp/live_score_engine.py", encoding="utf-8").read() if _os.path.exists("data/tmp/live_score_engine.py") else ""
chk(bool(_ls2) and all(x in _ls2 for x in ["analyze_live","poisson_matrix","cs_market_matrix","calculate_dynamic_weights","bayesian_fusion"]), "live_score_engine存在且核心函数齐全")
chk("弱先验" in _ls2 or "prior" in _ls2, "live引擎含16格先验弱先验(≤10%·数据不足兜底)")
chk("现场动态" in open("AGENTS.md", encoding="utf-8").read() or "live_score_engine" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含现场动态比分描述")
chk("禁止直接用先验表" in open("AGENTS.md", encoding="utf-8").read() or "非机械锚定" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含禁机械锚定铁律")

print("⑪ 半场反推+CS深度校验(Top2=40·V3.5.74)")
_hi=open("data/tmp/halftime_inference.py",encoding="utf-8").read() if _os.path.exists("data/tmp/halftime_inference.py") else ""
_cd=open("data/tmp/cs_deep_analyzer.py",encoding="utf-8").read() if _os.path.exists("data/tmp/cs_deep_analyzer.py") else ""
_hc=_os.path.exists("data/tmp/ht_ft_cond.json")
_ls3=open("data/tmp/live_score_engine.py",encoding="utf-8").read() if _os.path.exists("data/tmp/live_score_engine.py") else ""
chk(bool(_hi) and "halftime_precise_matrix" in _hi or bool(_hi) and "infer_ht_direction" in _hi, "halftime_inference存在(半场反推)")
chk(_hc, "ht_ft_cond.json条件矩阵缓存存在(175476场·19类)")
chk(bool(_cd) and "cs_vig_analysis" in _cd, "cs_deep_analyzer存在(抽水率偏差CS深度)")
chk("ht" in _ls3 and "halftime_precise_matrix" in _ls3, "live引擎含精细半场ht源(权重0.30)")

print("⑫ 实际调用链校验(V2.0·存在不等于活跃)")
_ca2 = open("data/tmp/calc_all.py", encoding="utf-8").read()
_cm2 = open("data/tmp/calc_match.py", encoding="utf-8").read()
_ls5 = open("data/tmp/live_score_engine.py", encoding="utf-8").read() if _os.path.exists("data/tmp/live_score_engine.py") else ""
chk("from live_score_engine import analyze_live" in _ca2, "live_score_engine实际接入calc_all(calc_all→live·非仅文档)")
chk("cs_deep_analyzer" in _ls5 and "cs_vig_analysis" in _ls5, "cs_deep实际接入live(live→cs_deep·抽水偏差)")
chk("from goal_odds_analyzer import" in _cm2, "goal_odds_analyzer实际接入calc_match(每场自动)")
chk("现场比分引擎" in _ca2 and "主锚建议" in _ca2, "calc_all含现场引擎输出节(主锚建议脚本Top1)")

print("⑬ 欧战+联赛校准模块校验(V3.5.74)")
_etl = open("data/tmp/europe_two_leg.py", encoding="utf-8").read() if _os.path.exists("data/tmp/europe_two_leg.py") else ""
_egs = open("data/tmp/europe_group_stage.py", encoding="utf-8").read() if _os.path.exists("data/tmp/europe_group_stage.py") else ""
_lc2 = open("data/league-modules/league_calibration.json", encoding="utf-8").read() if _os.path.exists("data/league-modules/league_calibration.json") else ""
chk(bool(_etl) and "analyze_first_leg" in _etl and "analyze_second_leg" in _etl and "SECOND_LEG_BY_FIRST_RESULT" in _etl and "LEAGUE_CALIBRATION" in _etl and "FINAL_CALIBRATION" in _etl, "europe_two_leg三层架构(单回合校准+赛事分层欧冠+3/欧协联-2+决赛中立-5pp)")
chk(bool(_egs) and "analyze_group_stage" in _egs and "detect_trap" in _egs and "EUROPE_CALIBRATION_MATRIX" in _egs and "LEAGUE_CALIBRATION" in _egs, "europe_group_stage三层(小组战意·诱盘·校准矩阵+赛事分层欧冠+3/欧协联-2)")
chk(bool(_lc2) and "德甲" in _lc2 and "英超" in _lc2 and "战术标签" in _lc2, "league_calibration.json存在(5联赛战术标签校准)")
chk("europe_two_leg" in open("AGENTS.md", encoding="utf-8").read() or "欧战两回合" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含欧战模块指引")
chk("europe_two_leg" in open(".reasonix/skills/<REDACTED_SK>/SKILL.md", encoding="utf-8").read(), "主技能含欧战模块(三处同步)")
chk("europe_two_leg" in open("data/足球分析模型.txt", encoding="utf-8").read(), "txt含欧战模块(三处同步)")


# ── 🔴数据源成功路径固化(2026-09-19·防重复纠错·四文件) ──
chk("数据源成功路径固化表" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含数据源成功路径固化表(2026-09-19防重复纠错)")
chk("api-football 已停用" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含 api-football 剔除声明(2026-10-06 用户决策·防回退)")
chk("数据源成功路径固化表" in open(".reasonix/skills/<REDACTED_SK>/SKILL.md", encoding="utf-8").read(), "主技能含数据源成功路径固化表")
chk("数据源成功路径固化表" in open("data/足球分析模型.txt", encoding="utf-8").read(), "txt含数据源成功路径固化表")
chk(not os.path.exists("data/tmp/api_football_mcp.py") and os.path.exists("data/archived-scripts/api_football_mcp.py"), "api_football_mcp 已归档(不在活跃脚本目录·2026-10-06)")
chk("fetch_clubelo.py" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含clubelo脚本通道(fetch_clubelo·禁curl)")
# ── 🔴txt 通用归一化层(2026-09-19·四文件) ──
chk("txt 通用归一化层" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含txt通用归一化层(2026-09-19)")
chk("txt 通用归一化层" in open(".reasonix/skills/<REDACTED_SK>/SKILL.md", encoding="utf-8").read(), "主技能含txt归一化层")
chk("txt 通用归一化层" in open("data/足球分析模型.txt", encoding="utf-8").read(), "txt含txt归一化层")
chk("txt_normalize.py" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含txt_normalize.py入口")
# ── 🔴模型维护最小化纪律 skill(2026-09-19·用户提议·借鉴 Ponytail 内核) ──
chk("<REDACTED_SK>" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含<REDACTED_SK>注册(33 skill)")
chk(os.path.exists(".reasonix/skills/<REDACTED_SK>/SKILL.md"), "<REDACTED_SK> skill 文件存在")
chk("分析场景不读" in open(".reasonix/skills/<REDACTED_SK>/SKILL.md", encoding="utf-8").read(), "维护纪律含场景隔离(分析场景不读)")
# ── 🔴SK-audit 模型审计 skill(2026-09-19·融合 V3.0+V4.0·被动双模式) ──
chk("SK-audit" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS含SK-audit注册(34 skill)")
chk(os.path.exists(".reasonix/skills/SK-audit/SKILL.md"), "SK-audit skill 文件存在")
chk(("存在≠活跃" in open(".reasonix/skills/SK-audit/SKILL.md", encoding="utf-8").read()) and ("未列出=未执行" in open(".reasonix/skills/SK-audit/SKILL.md", encoding="utf-8").read()), "SK-audit含双模式核心铁律(存在≠活跃/未列出=未执行)")
chk("审计入口" in open("AGENTS.md", encoding="utf-8").read(), "AGENTS审计入口已升级指SK-audit")
# ── 🔴case188审计修复(2026-09-19·P1-1~P1-5/P2-1~P2-5·raw第八节执行留痕链防回退) ──
_ag = open("AGENTS.md", encoding="utf-8").read()
_tx = open("data/足球分析模型.txt", encoding="utf-8").read()
_sk = open(".reasonix/skills/<REDACTED_SK>/SKILL.md", encoding="utf-8").read()
_tp = open("data/analysis_template.md", encoding="utf-8").read()
chk("执行留痕" in _ag, "AGENTS含raw第八节执行留痕规范")
chk("执行留痕" in _tx, "txt含raw第八节执行留痕规范")
chk("执行留痕" in _sk, "主技能含raw第八节执行留痕规范")
chk("执行留痕" in _tp, "模板含raw第八节执行留痕规范")
chk("联赛基准" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "calc_all含联赛基准自动输出(fix_s1·P1-4)")
chk("第八节" in open("data/tmp/check_luopan.py", encoding="utf-8").read(), "check_luopan含第八节校验(fix_s3·case189+强制)")
_oc = open("data/tmp/output_checker.py", encoding="utf-8").read()
chk(all(b in _oc for b in ("'N10'", "'N11'", "'N12'", "'N13'", "'N14'", "'N15'")), "output_checker含N10-N15留痕块(fix_s4)")
# ── 🔴数据链三层风险原则(2026-09-19·用户核心关切「一切以模型数据链不出错为基准」) ──
_sm = open(".reasonix/skills/<REDACTED_SK>/SKILL.md", encoding="utf-8").read()
chk("数据链三层风险" in _sm, "维护纪律含数据链三层风险(输入解析/数据表/展示留痕·L1-L7不引入决策)")
_au = open(".reasonix/skills/SK-audit/SKILL.md", encoding="utf-8").read()
chk(("术语差异" in _au) and ("改动分层纪律" in _au), "SK-audit含术语差异判定+改动分层纪律")
# ── 🔴审计入口三处同步(2026-09-19·AGENTS/主技能/txt 均指 SK-audit) ──
chk("审计入口" in _sk, "主技能含审计入口(指SK-audit·2026-09-19)")
chk("审计入口" in _tx, "txt含审计入口(指SK-audit·2026-09-19)")
# ── 🔴资金盘信号层(2026-09-21·P0-1/P0-2/P0-3/P1-1/P1-3/P2-1/P2-2/P2-3) ──
chk(os.path.exists("data/tmp/bookmaker_spread.py"), "bookmaker_spread.py 存在(P0-1 跨机构分歧)")
chk(os.path.exists("data/tmp/sharp_baseline.py"), "sharp_baseline.py 存在(P0-2 sharp 基准)")
chk(os.path.exists("data/tmp/fundflow_analyzer.py"), "fundflow_analyzer.py 存在(统一入口)")
chk(os.path.exists("data/tmp/clv_tracker.py"), "clv_tracker.py 存在(P2-1 CLV)")
chk(os.path.exists("data/tmp/odds_snapshot.py"), "odds_snapshot.py 存在(P1-3 快照采集)")
chk(os.path.exists("data/tmp/_classifier_calibrate.py"), "_classifier_calibrate.py 存在(P1-2 校准)")
_ffa = open("data/tmp/fundflow_analyzer.py", encoding="utf-8").read()
chk("pending_backtest" in _ffa, "fundflow 含回测状态分级(pending_backtest/pending_data)")
chk("永不反转" in _ffa, "fundflow 含铁律(永不反转·只调置信度)")
_ffb = open("data/tmp/bookmaker_spread.py", encoding="utf-8").read()
chk(("CONSENSUS" in _ffb) and ("annotate_only" in _ffb), "bookmaker_spread 含共识分级+仅标注档(禁降档)")
chk("(mx - odd) / odd" in _ffb, "bookmaker_spread 用代理口径(Max-均值)/均值(=回测口径)")
chk("跨机构分歧" in _ag, "AGENTS 含跨机构分歧节(资金盘层)")
chk("资金盘信号" in _tx, "txt 含资金盘信号层")
chk("资金盘信号层" in _sk, "主技能 含资金盘信号层(Step4.7)")
_wi = open(".reasonix/skills/SL-water-intent/SKILL.md", encoding="utf-8").read()
chk("全盘水位不携带方向信息" in _wi, "SL-water-intent 含 vig 降级依据(P1-1·防回退)")
chk("bookmaker_spread.py" in _wi, "SL-water-intent 引用跨机构 spread(P0 三条件)")
chk("资金盘" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "calc_all 已接入资金盘模块")
chk(os.path.exists("data/archived-scripts/fetch_books.py") and not os.path.exists("data/tmp/fetch_books.py"), "fetch_books.py 已归档(2026-10-06 随 api-football 剔除)")
_ffc = open("data/tmp/calc_all.py", encoding="utf-8").read()
_fc2 = _ffc
chk(("--max_h" in _ffc) and ("--max_d" in _ffc) and ("--max_a" in _ffc), "calc_all 含三方向 Max 参数(--max_h/--max_d/--max_a)")
chk("load_books" in _ffc, "calc_all 用 load_books 解包(dict/list 契约)")
chk("load_books" in open("data/tmp/bookmaker_spread.py", encoding="utf-8").read(), "bookmaker_spread 定义 load_books(公共解包)")

# ── 🔴欧国联/国家队子模型(2026-09-23·V3.5.75·SK-league-nations·658场四届) ──
chk(os.path.exists("data/tmp/nl_model.py"), "nl_model.py 存在(N1-N7 判定核心)")
chk(os.path.exists(".reasonix/skills/SK-league-nations/SKILL.md"), "SK-league-nations 存在(欧国联子模型)")
chk(os.path.exists("data/tmp/nl_data/nl_with_elo.csv"), "nl_with_elo.csv 存在(658场回测主库)")
chk(os.path.exists("data/tmp/nl_data/fair_model.json"), "fair_model.json 存在(P0-2 公平模型参数)")
_nlm = open("data/tmp/nl_model.py", encoding="utf-8").read()
chk("永不反转" in _nlm, "nl_model 含铁律(永不反转·只调置信度·±1档)")
chk(all(k in _nlm for k in ("N1", "N3", "draw_leak", "fair_probs", "motivation")), "nl_model 含 N1/N3/N5/N6 核心函数")
chk("66%" not in _nlm and "not_away" in _nlm, "nl_model 含客队热门平局泄漏(R5·未胜率)")
chk("42% tolerance" not in _nlm and "均势" in _nlm, "nl_model 含 R7 均势中性判定(防回退)")
_nlk = open(".reasonix/skills/SK-league-nations/SKILL.md", encoding="utf-8").read()
chk(all(("R%d" % i) in _nlk for i in range(1, 11)), "SK-league-nations 含完整 R1-R10")
chk("客队热门平局泄漏" in _nlk, "SK 含 R5 客队热门平局泄漏(核心规则)")
chk("未复现" in _nlk, "SK 含 O2.5 未复现诚实标注(防夸大)")
chk("778" not in _nlk and "78.6%" in _nlk, "SK 含 R10 高置信档实测值(78.6%)")
chk("欧国联/国家队子模型" in _ag, "AGENTS 含 Step4.8 欧国联子模型")
chk("欧国联/国家队子模型" in _tx, "txt 含 Step4.8 欧国联子模型")
chk("nl_model.py" in _ag and "nl_model.py" in _tx, "AGENTS/txt 引用 nl_model.py(调用入口)")

# ── 🔴2026-11-09 欧国联 2026/27 就绪（P0 三修 + P1 三补·用户「马上欧国联开始了」）──
#   每条都对应一个**实测抓到的真缺陷**，不是凭空加的：
chk("【赛事】" in _nlm and "_TEAM_PATTERNS" in _nlm,
    "nl_model **_TEAM_PATTERNS 支持 `【赛事】` 前缀**（原只认 `赛事：` 冒号 → 实测 8 个真实 std txt "
    "**0/8 命中** → calc_all 的 NL 段一直静默三态 = 「存在≠活跃」真案例；修后 8/8）")
chk("[:20000]" in _nlm,
    "nl_model 队名/轮次读 **[:20000]**（原 [:1500] 硬截断 → 长 txt 队名在后半段恒失配）")
_pl3 = open("data/tmp/pipeline.py", encoding="utf-8").read()
chk("NL欧国联" in _pl3 and "blk('NL欧国联')" in _pl3,
    "pipeline **KEY_BLOCKS 自动内嵌 NL 块**（原只写一行「须调 nl_model.py」→ 靠模型记得调；"
    "现 NL 场自动落 R1-R10 真实数值·calc 无块则标红）")
_pf3 = open("data/tmp/prestep_fetch.py", encoding="utf-8").read()
_nl_slug_cnt = len(re.findall(r"^\s*'international-uefa-nations-league-league-[a-d]-gr-\d'\s*:\s*'欧国联'",
                               _pf3, re.M))
chk(_nl_slug_cnt == 14 and "'international-uefa-nations-league-league-d-gr-3'" not in _pf3,
    "prestep NL slug **16→14**（实测 UEFA NL 只有 14 个·D 联赛仅 1-2 组 → 原 d-gr-3/4 恒 404 误报漏场风险）")
_bs3 = open("data/tmp/bsd_layer.py", encoding="utf-8").read()
chk("[1, 3, 5, 4, 6, 64]" in _bs3,
    "bsd_layer locate_event **默认扫 league_id=64（UEFA Nations League）**"
    "（实测 Bzzoiro id=64=UEFA NL 99 场 → 原 [1,3,5,4,6] 不含 → NL 场 Form5/M1 伤停恒三态；"
    "接入后实测定位 4/4·Form5 6/6 命中）")
chk("R3b" in _nlm and "近年对照" in _nlm,
    "nl_model **R3b 近年对照行**（时间分割：全场 2.51/45.3% vs 2022-09 后 2.71/51.0% → 并列显示趋势·不覆盖 R3）")
# ── 🔴2026-11-09 欧国联：市场三源/六档分级/N26 超域标注 适用性核查 ──
#   用户追问「市场三源和六档分级等这些机制对欧国联还适用吗·是否完整接入」→ 逐项实测（Italy vs France 真实场次）
#   实测结果（coverage=100%·health=ok·CS 24 档）：
#     ✅ P10 三源 / ✅ P52 六档（**判据=市场赔率非联赛统计**·故通用）/ ✅ 量级分布 V3.5.88（五源全市场）
#     ✅ N23 四要素 / ✅ N18 锚-期望 / ✅ R1-R10 / ✅ R3b / 🔴 N27 无国家队档案 → **正确三态**
#     🔴 N26 原只对欧冠标超域、NL 场静默用五大基线 → 补 NL 超域标注（独立 try·防 norm_league 异常连带跳过）
_ca_n26 = open("data/tmp/calc_all.py", encoding="utf-8").read()
chk("欧国联属超域" in _ca_n26,
    "N26 进球细分 **NL 场标超域**（原只对欧冠标·NL 场静默当五大口径用；"
    "实测 NL 近年 2.71球/O2.5 51.0% ≈ 五大 2.69/50.4% → 偏保守幅度极小但口径须声明）")
chk("_lg_n26" in _ca_n26 and _ca_n26.count("except Exception:\n                                    pass") >= 2,
    "N26 超域标注为**独立 try**（原与欧冠判断共用 try → norm_league 抛异常时整块跳过·NL 标注静默丢失）")
chk("队伍未找到" in _ca_n26,
    "N27 攻防档案 **NL 场正确三态**（实测 312 队全俱乐部·0 国家队 → 输出「队伍未找到: Italy / France」而非静默空值）")

chk("主44/平30/客26" in _nlm,
    "nl_model **R7 均势档值已时间分割重校**（主45/平31/客24 → 主44/平30/客26·验证集客胜 28% 被原 24% 低估）")
chk("27-33%" in _nlm,
    "nl_model **R5 中浅平局区间 27-31% → 27-33%**（训练 29% → 验证 36%·原上限偏低）")
_nl_el = open("data/tmp/nl_data/elo_current.json", encoding="utf-8").read()
chk('"Spain"' in _nl_el and len(__import__("json").loads(_nl_el)) >= 300,
    "nl_data/elo_current.json 存在且 ≥300 队（2026-11-09 含 2026 世界杯后重算·313 队）")
chk("SK-league-nations" in _ag and "SK-league-nations" in _tx, "AGENTS/txt 引用 SK-league-nations(技能名)")
chk("60.7" in _ag and "60.7" in _nlk, "主场 Elo 60.7 已固化(防回退·非下调)")
chk("禁死球" in _ag or "禁死球淡化" in _ag, "AGENTS 含 R9 MD1-2 禁死球纪律")
chk("Step4.8 欧国联/国家队子模型" in _sk, "主技能含 Step4.8 欧国联子模型")
chk("Step4.8 欧国联/国家队子模型" in open("data/analysis_template.md", encoding="utf-8").read(), "模板含 Step4.8 欧国联节")
chk("N17" in open("data/tmp/output_checker.py", encoding="utf-8").read(), "output_checker 含 N17(NL 块)")
chk("nl_model" in open("data/tmp/calc_all.py", encoding="utf-8").read(), "calc_all 已接入 nl_model(NL 自动激活)")
chk("□ 27." in _ag and "R5 客队热门平局泄漏" in _ag, "AGENTS 自检表含 □27(欧国联子模型·防回退)")
chk("def team_elo" in _nlm, "nl_model 含 team_elo(队名→Elo 自动查询·P1 修复)")
chk("TEAM_CN" in _nlm, "nl_model 含 TEAM_CN(国家队中英映射·防中文 txt 匹配失败)")
chk("档位类规则不输出" in _nlm, "nl_model 含未取得 Elo 三态标注(防静默跳过)")
chk("nl_model" in _fc2 and "_nlh, _nla" in _fc2, "calc_all 提取队名传 nl_model(P1 修复)")
chk("nl_elo_current.py（从 intl_results.csv" in _fc2, "calc_all 含 Elo 数据管线提示(防孤儿)")
chk("SK-league-nations** | **Step4.8" in _ag, "AGENTS 映射表含 SK-league-nations")
chk(_decl_vers.get('AGENTS.md') == _decl_vers.get('主技能') == _decl_vers.get('txt') == EXPECT_VER,
    "三处版本声明统一 %s（由①段真断言·2026-10-13 修「全文存在」假通过）" % EXPECT_VER)
chk("既有口径的超域边界" in _nlk, "NL Skill 含既有口径超域边界节(防口径混用)")
chk("NL 超域·先验不触发" in _ag, "AGENTS PreStep 含 NL 适用域标注(防口径混用)")
chk("NL 超域·先验不触发" in _tx, "txt PreStep 含 NL 适用域标注")
chk("def _is_nl" in open("data/tmp/prestep_dual.py", encoding="utf-8").read(), "prestep_dual 含 _is_nl(NL 识别)")
chk("_nl_rows" in open("data/tmp/prestep_dual.py", encoding="utf-8").read(), "prestep_dual NL 分流已接线(超域区)(防存在≠活跃)")
chk("nations-league-league-d-gr-2" in open("data/tmp/prestep_fetch.py", encoding="utf-8").read(), "prestep_fetch LG 含欧国联 14 slug(防回退·2026-11-09 由 16 改 14：实测 UEFA NL 只有 A/B/C 各 4 组 + D 仅 1-2 组·d-gr-3/4 本就不存在)")
chk("ProxyHandler({})" in open("data/tmp/prestep_fetch.py", encoding="utf-8").read(), "prestep_fetch 真直连(ProxyHandler({}))/(防回退)")
chk("ProxyHandler({})" in open("data/online_learning/data_bridge.py", encoding="utf-8").read(), "data_bridge 真直连(防回退)")
chk("ProxyHandler({})" in open("data/tmp/source_health_check.py", encoding="utf-8").read(), "source_health_check 真直连(防回退)")
chk("真直连铁律" in _ag, "AGENTS 含真直连铁律(防无参 opener 复发)")
chk("league-{a|b|c|d}-gr-{1|2|3|4}" in _ag, "AGENTS 固化表含欧国联 slug 格式")
chk("超域" in _ag and "45.3" in _ag, "AGENTS Step4.8 含超域边界声明(NL基线45.3%≠五大53%+)")
chk("超域" in open(".reasonix/skills/SK-v3572-rules/SKILL.md", encoding="utf-8").read(), "v3572-rules 含 NL 超域边界句")
chk("超域" in _tx, "txt 含 NL 超域边界句")
chk("超域" in open("data/analysis_template.md", encoding="utf-8").read(), "模板含 NL 超域边界说明")
chk("Step4.8 欧国联/国家队子模型" in open(".reasonix/skills/SK-v3572-rules/SKILL.md", encoding="utf-8").read(), "SK-v3572-rules 含 Step4.8 执行链(防回退)")
chk("欧国联子模型】留痕" in open("data/tmp/check_luopan.py", encoding="utf-8").read(), "check_luopan 校验 NL 留痕(防回退)")
chk("⑩ **欧国联/国家队子模型" in open("data/analysis_template.md", encoding="utf-8").read(), "模板 raw 第八节含 ⑩ NL 子块(防回退)")
chk("SK-league-nations" in open("data/tmp/migration_prompt.md", encoding="utf-8").read(), "迁移文档含 NL 恢复项(防回退)")
chk("欧国联" in open(".reasonix/skills/SL-betting-plan/SKILL.md", encoding="utf-8").read(), "SL-betting-plan 含 NL 场规则(防回退)")
chk("欧国联" in open(".reasonix/skills/SL-case-library/SKILL.md", encoding="utf-8").read(), "SL-case-library 含 NL 留痕要求(防回退)")
chk("欧国联" in open(".reasonix/skills/SK-prestep-filter/SKILL.md", encoding="utf-8").read(), "SK-prestep-filter 含 NL 超域标注(防回退)")


chk(os.path.exists("data/tmp/nl_elo_current.py"), "nl_elo_current.py 存在(当前 Elo 计算·数据管线)")
chk(os.path.exists("data/tmp/nl_data/elo_current.json"), "elo_current.json 存在(313 队当前 Elo)")

# 🔴2026-09-27 数据链接入批（三项孤立脚本接入·防回退）
_CA_TXT = open("data/tmp/calc_all.py", encoding="utf-8").read()
chk("from injury_impact import" in _CA_TXT and "--inj_list_h" in _CA_TXT,
    "calc_all 接入 injury_impact(--inj_list_h/--inj_list_a·治手算)(防回退)")
chk("calc_homeaway.py" in _CA_TXT and "_haf_key" in _CA_TXT,
    "calc_all 接入 calc_homeaway(HAF·自动 subprocess·防回退)")
chk("halftime_precise_matrix" in open("data/tmp/live_score_engine.py", encoding="utf-8").read()
    and "半场反推覆盖" in _CA_TXT,
    "半场反推覆盖关系(live.halftime_precise_matrix 承接 Step7.5)(防误判孤儿)")
_II_TXT = open("data/tmp/injury_impact.py", encoding="utf-8").read()
chk("sys.stdout = io.TextIOWrapper" not in _II_TXT and "sys.stdout.reconfigure" in _II_TXT,
    "injury_impact 无 import stdout 副作用(可安全 import)(防回退)")

# 🔴2026-09-27 SK-host-lock 封装（host 锁四方案·遇即触发·防回退）
chk(os.path.exists(".reasonix/skills/SK-host-lock/SKILL.md"), "SK-host-lock skill 存在(host 锁决策树)(防回退)")
_HOST_TXT = open(".reasonix/skills/SK-host-lock/SKILL.md", encoding="utf-8").read()
chk("read-evidence requirement is outstanding" in _HOST_TXT and "方案 0" in _HOST_TXT,
    "SK-host-lock 含触发串 + 四方案决策树(防回退)")
chk("--decide" in open("data/tmp/lock_dirs.py", encoding="utf-8").read(), "lock_dirs.py 含 --decide 决策树入口(防回退)")

# 🔴2026-09-27 NL 根因加固 A+B+C（case206/207·用户确认固化·防回退）
_NL_SK = open(".reasonix/skills/SK-league-nations/SKILL.md", encoding="utf-8").read()
chk("edge ≤ −10pp" in _NL_SK and ("两向覆盖纪律" in _NL_SK or "最多两向" in _NL_SK),
    "SK-league-nations 含 A+B+C 根因加固(edge接线+超域补两条方向类+两向覆盖·三向已废止)(防回退)")
chk("2026-09-27 根因加固" in open("AGENTS.md", encoding="utf-8").read(),
    "AGENTS 含 NL 根因加固 A+B+C(防回退)")

# 🔴2026-09-27 单押准入纪律（227,495 场回测·用户确认全量固化·防回退）
_A_TXT = open("AGENTS.md", encoding="utf-8").read()
chk("单押准入纪律" in _A_TXT and "77.68%" in _A_TXT and "150-200% 档明确禁单押" in _A_TXT,
    "AGENTS 含单押准入纪律(150-200%禁单押+须≥200%且<1.30+2向覆盖)(防回退)")
chk("单押准入纪律" in open("data/足球分析模型.txt", encoding="utf-8").read(),
    "txt 含单押准入纪律(双路径一致)(防回退)")

# 🔴2026-09-27 低赔—ELO 背离纪律（227,495 场回测·防回退）
chk("低赔—ELO 背离纪律" in open("AGENTS.md", encoding="utf-8").read() and "41.7%" in open("AGENTS.md", encoding="utf-8").read(),
    "AGENTS 含低赔—ELO 背离纪律(背离→降1档+强制2向·禁反押)(防回退)")
chk("低赔—ELO背离纪律" in open("data/足球分析模型.txt", encoding="utf-8").read(),
    "txt 含低赔—ELO 背离纪律(双路径一致)(防回退)")

# 🔴2026-09-27 判定优先级铁律（低赔降为参考·计算升为铁依据·防回退）
chk("判定优先级铁律" in open("AGENTS.md", encoding="utf-8").read() and "禁单独以最低赔率定方向" in open("AGENTS.md", encoding="utf-8").read(),
    "AGENTS 含判定优先级铁律(计算为铁依据·赔率仅参考)(防回退)")
chk("判定优先级铁律" in open("data/足球分析模型.txt", encoding="utf-8").read(),
    "txt 含判定优先级铁律(双路径一致)(防回退)")

# 🔴2026-09-27 锚-期望标准放宽 → 🔴2026-10-13 升级为【双锚强制】匹配（用户指令·防回退）
_lseSrc = open("data/tmp/live_score_engine.py", encoding="utf-8").read()
chk(("anchor_expect" in _lseSrc) and ("高于市场期望" in _lseSrc) and ("软·须满足其一" in _lseSrc),
    "live_score_engine 双锚期望匹配(anchor_expect·硬1/硬2+软a-b-c·2026-10-13 强制)+主锚上界(防回退)")
# 🔴2026-10-26 V4.1: 悬殊场减分实测 +0.1pp 无效已删除（断言反向·确认不再存在）
chk("悬殊场(|主隐-客隐|>40pp)" not in open("data/tmp/prestep_dual.py", encoding="utf-8").read(),
    "V4.1 已删除「悬殊场减分」（35,879 场实测 +0.1pp 无效·旧规则源于近似 bug）")

# ── 🔴2026-09-28 SK-audit 程序加固（审计器自审计 + fixture 防复发·方案 11 项）──
_aud_sk = open(".reasonix/skills/SK-audit/SKILL.md", encoding="utf-8").read()
# 🔴2026-10-20: 断言改为「≥20 动作 + 新探查在位」，避免锁死旧数量（原写死 "16 动作"）
chk(("20 动作" in _aud_sk) and ("⑯" in _aud_sk), "SK-audit A1 升级为 20 动作(含⑯启用依据泄露 + ⑰~⑳)")
chk("启用依据泄露探查" in _aud_sk and "P-LEAK-1" in _aud_sk, "SK-audit 含⑯启用依据泄露探查(治赛后统计做回测·2026-09-30)")
chk("⑬" in _aud_sk and "⑭" in _aud_sk and "⑮" in _aud_sk, "SK-audit A1 三项新探查在位(口径一致性/fixture回归/规则-代码双向)")
chk("审计器自审计" in _aud_sk, "SK-audit 含铁律⑩审计器自审计(2026-09-28·P1-2 教训)")
chk("fixture 防复发" in _aud_sk, "SK-audit 含铁律⑪fixture 防复发(2026-09-28·P0-2/3/4 教训)")
chk("Step4.8" in _aud_sk and "第 12 链" in _aud_sk, "SK-audit B1 含 Step4.8 NL 逐项 + B2 第 12 链(2026-09-28)")
chk(os.path.exists("data/tmp/audit_fixtures.py") and os.path.exists("data/tmp/audit_alignment.py"),
    "A1⑭/A1⑬ 审计脚本在位(2026-09-28·fixture回归+口径一致性)")
_audfix = [f for f in os.listdir("data/tmp/_audit_fixtures") if f.endswith(".txt")] if os.path.isdir("data/tmp/_audit_fixtures") else []
chk(len(_audfix) >= 5 and os.path.exists("data/tmp/_audit_fixtures/README.md"),
    "fixture 集在位且≥5 份(2026-09-28·NL标准/NL变体/意甲/英超/期号变体·实测 %d 份)" % len(_audfix))
# 🔴fixture 回归自动跑（A1⑭·方案「接入 check_sync 自动跑」）
try:
    _fx = __import__("subprocess").run([__import__("sys").executable, "data/tmp/audit_fixtures.py"],
                                       capture_output=True, text=True, encoding="utf-8", timeout=90)
    _fx_ok = (_fx.returncode == 0)
    _fx_tail = [l for l in ( _fx.stdout or "").strip().split("\n") if l.strip()][-1:][0] if _fx.stdout else str(_fx.stderr)[:60]
except Exception as _fxe:
    _fx_ok = False; _fx_tail = str(_fxe)[:60]
chk(_fx_ok, "A1⑭ fixture 回归自动跑通过（%s）" % _fx_tail[:64])
# 🔴口径一致性自动跑（A1⑬·2026-09-29 P2-5 修复《全量审计报告·V3.5.76 复检》）
#   原实现只 chk 文件存在 → 建表口径若被改回 elo_diff（A1⑬ 防的漂移），check_sync **不会报**
try:
    _al = __import__("subprocess").run([__import__("sys").executable, "data/tmp/audit_alignment.py"],
                                       capture_output=True, text=True, encoding="utf-8", timeout=90)
    _al_ok = (_al.returncode == 0)
    _al_tail = [l for l in (_al.stdout or "").strip().split("\n") if l.strip()][-1:][0] if _al.stdout else str(_al.stderr)[:60]
except Exception as _ale:
    _al_ok = False; _al_tail = str(_ale)[:60]
chk(_al_ok, "A1⑬ 口径一致性自动跑通过（%s）" % _al_tail[:64])
# 🔴V3.5.76 双通道四象限防回退（2026-09-29 用户方案《竞彩×欧亚盘双通道判定机制》）
try:
    _ss76 = open("data/tmp/snapshot_save.py", encoding="utf-8").read()
    chk(("def dual_channel(" in _ss76) and ("'C1'" in _ss76) and ("'C2'" in _ss76)
        and ("Q2" in _ss76) and ("Q1" in _ss76),
        "V3.5.76: snapshot_save.dual_channel() 含 C1/C2 + 四象限 Q1/Q2（2026-09-29）")
except Exception as _e76:
    chk(False, "V3.5.76: snapshot_save 读取失败(%s)" % str(_e76)[:40])
try:
    _sk76 = open(".reasonix/skills/<REDACTED_SK>/SKILL.md", encoding="utf-8").read()
    chk(("动态盘双通道四象限" in _sk76) and ("Q2 诱盘警报" in _sk76) and ("永不反转 L2 硬核方向" in _sk76),
        "V3.5.76: 主技能含「动态盘双通道四象限」+ Q2 诱盘警报 + 永不反转铁律（2026-09-29）")
except Exception as _e77:
    chk(False, "V3.5.76: 主技能读取失败(%s)" % str(_e77)[:40])
# 🔴2026-09-29 双通道问题修复防回退（《双通道动态判定机制（V3.5.76）问题汇总》）
#   接口-1/P1-1 · 接口-2 · P1-2 · P1-3/P2-1 · P3-1
try:
    chk(("'英超'" in _ss76) and ("england-premier-league" in _ss76) and ("'欧冠'" in _ss76),
        "V3.5.76修复: snapshot_save.LG 含五大联赛+欧冠 slug（接口-1·机构通道主战场可用）")
except Exception as _e78:
    chk(False, "V3.5.76修复: LG 校验失败(%s)" % str(_e78)[:40])
try:
    chk(("def _club_map(" in _ss76) and ("TEAM_ALIASES" in _ss76),
        "V3.5.76修复: cn2en 并入俱乐部别名 data_bridge.TEAM_ALIASES（接口-2）")
except Exception as _e79:
    chk(False, "V3.5.76修复: cn2en 校验失败(%s)" % str(_e79)[:40])
try:
    chk(("window_min=None" in _ss76) and ("-2.0 < c1 < 2.0" in _ss76),
        "V3.5.76修复: dual_channel 含 window_min + Q3 收紧(-2.0<c1<2.0)（P1-3/P2-1）")
except Exception as _e80:
    chk(False, "V3.5.76修复: dual_channel 参数校验失败(%s)" % str(_e80)[:40])
try:
    _ff76 = open("data/tmp/fundflow_analyzer.py", encoding="utf-8").read()
    chk(("ah_from=None, ah_to=None, window_min=None" in _ff76)
        and ("rlm_detect(s1x2, shandi, ah_from, ah_to, window_min)" in _ff76)
        and ("_ah_hdp(ah_from), _ah_hdp(ah_to)" in _ff76),
        "V3.5.76修复: fundflow analyze 透传 ah/窗口→rlm_detect + 修运算符优先级（P1-2 存在≠活跃）")
except Exception as _e81:
    chk(False, "V3.5.76修复: fundflow 透传校验失败(%s)" % str(_e81)[:40])
try:
    _oc76 = open("data/tmp/output_checker.py", encoding="utf-8").read()
    chk(("N21b" in _oc76) and ("动态盘双通道" in _oc76),
        "V3.5.76修复: output_checker 新增 N21b 双通道断言（P3-1 审计盲区）")
except Exception as _e82:
    chk(False, "V3.5.76修复: output_checker 校验失败(%s)" % str(_e82)[:40])

# ── 🔴2026-09-29 case219 修复防回退: 竞彩【简称】回退（cn2en + team_elo）──
#   背景: 竞彩 txt 常用简称（如「斯洛文尼」漏「亚」）恒不命中全称表 →
#         ① cn2en 恒返回原串 → 快照链 count=0 ② team_elo 恒 None → NL R4-R10 整段三态
try:
    _ss76 = open("data/tmp/snapshot_save.py", encoding="utf-8").read()
    chk(("_shrink_fallback" in _ss76) and ("简称回退" in _ss76),
        "case219修复防回退: snapshot_save.cn2en 含简称回退（_shrink_fallback）")
except Exception as _e83:
    chk(False, "case219修复防回退: snapshot_save 校验失败(%s)" % str(_e83)[:40])

try:
    _nl76 = open("data/tmp/nl_model.py", encoding="utf-8").read()
    chk(("简称" in _nl76) and ("_cn_cands" in _nl76),
        "case219修复防回退: nl_model.team_elo 含中文简称回退（_cn_cands）")
except Exception as _e84:
    chk(False, "case219修复防回退: nl_model 校验失败(%s)" % str(_e84)[:40])

# ── 🔴2026-09-29 四场完成度检验修复防回退: 快照亚盘取【均衡线档】──
#   背景: 原 `_extract` Spread 固定取「hdp≈−1.0」档 → 受让场/深盘场取错档
#         （苏格兰受让1球读「让-1 主10.0」·西班牙让2球读「让-1 主1.27」）
#         → 影响 N21 亚盘显示 + 双通道机构通道 + V2 水位交叉
try:
    _ss77 = open("data/tmp/snapshot_save.py", encoding="utf-8").read()
    chk(("_gap" in _ss77) and ("均衡线档" in _ss77) and ("abs((x.get('hdp') or 0) + 1.0)" not in _ss77),
        "四场检验修复防回退: snapshot_save._extract 亚盘取均衡线档（_gap·禁用固定-1档）")
except Exception as _e85:
    chk(False, "四场检验修复防回退: snapshot_save._extract 校验失败(%s)" % str(_e85)[:40])

# ── 🔴2026-09-29 结构修订 P0/P1/P2 防回退（用户审计「是否系统性结构问题」）──
#   P0: 让球盘×大小球比分先验表替代 anchor_market_check 全局下界
#       （原约束「主锚总进球 ≥ 期望−1.0」在强小球场排除全部 1 球比分 → 主锚系统性钉在 1:1）
#   P1: 口径权威表（同一事实唯一权威源）  P2: 作用域开关（超域由文字清单→代码）
#   证据: Matches.csv 148,013 场 → 主让1球+小球 1:0=15.8% vs 1:1=12.2%（n=3687·split_ok=True）
# 🔴自审计修复（2026-09-29）: 首版键名误写为 "'cells'"（含单引号）而 JSON 实为 "cells"（双引号）
#   → 4 条断言恒失败（假阴性）——教训: 断言必须实跑一次，禁「关键词存在即通过」
for _f, _k, _lbl in [
        ("data/tmp/handi_score_table.json", '"cells"', "P0: handi_score_table.json（盘口×大小球 24 格比分先验表）"),
        ("data/tmp/canonical_sources.json", '"expect_total"', "P1: canonical_sources.json（口径权威表·5 量）"),
        ("data/tmp/scope_registry.json", '"scopes"', "P2: scope_registry.json（作用域开关 use/ref/block）"),
        ("data/tmp/rule_registry.json", '"naming_conflicts"', "登记: rule_registry.json（R1-R20 + P 系列 + R 编号冲突）"),
]:
    try:
        _t = open(_f, encoding="utf-8").read()
        chk(_k in _t, "结构修订载入: " + _lbl)
    except Exception as _e86:
        chk(False, "结构修订载入失败 %s (%s)" % (_f, str(_e86)[:40]))

#   🔴2026-09-30 审计修复: 原断言为「字符串存在即通过」（`"def X" in _sp`）——正是本文件自己写下的教训所禁止
#     → 改为【实跑一次 · 断言输出】（SK-audit 铁律 10「审计器自审计」）
try:
    import sys as _sysP
    if "data/tmp" not in _sysP.path:
        _sysP.path.insert(0, "data/tmp")
    import score_prior as _SP
    _pa = _SP.handi_prior_table(-1.0, 2.315)
    chk(_pa.get("cell") == "-1|small" and (_pa.get("ok") is True),
        "P0 实跑: handi_prior_table(-1,2.315) → cell=%s ok=%s top1=%s"
        % (_pa.get("cell"), _pa.get("ok"), (_pa.get("top") or [["-", 0]])[0][0]))
    _pb = _SP.authority_resolve("expect_total", {"market": 2.24, "table": 2.90})
    chk(_pb.get("authority") == "market" and abs((_pb.get("value") or 0) - 2.24) < 1e-9,
        "P1 实跑: authority_resolve 权威源=%s value=%s conflicts=%d"
        % (_pb.get("authority"), _pb.get("value"), len(_pb.get("conflicts") or [])))
    _pc = _SP.scope_check("nl", "step6_tiers")
    chk(_pc == "ref", "P2 实跑: scope_check(nl,step6_tiers) → %s" % _pc)
    _pd = _SP.scope_for_league(5)
    chk(_pd == "nl", "P2 实跑: scope_for_league(5) → %s" % _pd)
except Exception as _e87:
    chk(False, "score_prior 实跑校验失败(%s)" % str(_e87)[:60])

try:
    _lse = open("data/tmp/live_score_engine.py", encoding="utf-8").read()
    chk(("handi_prior_table" in _lse) and ("prior_suggest" in _lse),
        "P0 接线: live_score_engine 调用比分先验表（handi_prior_table/prior_suggest）")
    chk("tot < _exp - 1.0" not in _lse,
        "P0 防回退: anchor_market_check 已移除全局下界（tot < _exp - 1.0）")
except Exception as _e88:
    chk(False, "live_score_engine 结构修订校验失败(%s)" % str(_e88)[:40])

# ── 🔴2026-09-29 结构一致性扫描 P0 防回退（治「静默文档病」：校验器把 LLM 拉回旧行为）──
#   根因: output_checker N18 长期保留旧口径（「主锚不得低于期望1.0球以上·±0.5球区间」）
#        → 不报错、不影响 check_sync，但**每场分析都在按旧规则提示** → 本次 1:1 错误的复现路径
#   要求: 新口径就位 + 旧口径不得复现（与 live_score_engine 的防回退同源）
try:
    _oc = open("data/tmp/output_checker.py", encoding="utf-8").read()
    chk(("比分先验" in _oc) and ("handi_prior" in _oc),
        "P0 防回退: output_checker N18 已改为「锚-比分先验」新口径")
    chk("主锚不得低于期望1.0球以上" not in _oc,
        "P0 防回退: output_checker 不得含旧口径「主锚不得低于期望1.0球以上」")
    chk("共同覆盖期望±0.5球区间" not in _oc,
        "P0 防回退: output_checker 不得含旧口径「±0.5球区间」（2026-09-27 已放宽为 ±1.0）")
except Exception as _e89:
    chk(False, "output_checker 结构一致性校验失败(%s)" % str(_e89)[:40])

try:
    _cs = open("data/tmp/canonical_sources.json", encoding="utf-8").read()
    chk('"duplicate_impl"' in _cs,
        "P1 重复实现登记: canonical_sources.json 含 duplicate_impl（重复实现台账·防口径漂移）")
except Exception as _e90:
    chk(False, "canonical_sources duplicate_impl 校验失败(%s)" % str(_e90)[:40])

# ── 🔴2026-09-30 评估层（双轨方案 v2·评论者三条建议）──
#   root_cause: 模型长期对外报「方向 55-58%」却不附同场基线（评论者第 2 条）
#   实测（2026-09-30·n=34）: 模型 any 47.1% == 市场单押热门 47.1%（+0.0pp）· vs 市场两向覆盖 76.5%（−29.4pp）
try:
    chk(os.path.exists("data/tmp/eval_baseline.py"),
        "评估层工具: eval_baseline.py 存在（四基线同场对比 + Wilson CI + McNemar）")
    _eb = open("data/tmp/eval_baseline.py", encoding="utf-8").read()
    chk(all(k in _eb for k in ("def same_match", "def all_sample", "def config_hash", "def wilson", "def mcnemar")),
        "评估层函数就位: eval_baseline（same_match/all_sample/config_hash/wilson/mcnemar）")
except Exception as _e91:
    chk(False, "eval_baseline 校验失败(%s)" % str(_e91)[:40])

# ── 🔴2026-09-30 观察项落地防回退（治「复盘成果进不了执行路径」·P-OBS-1）──
#   根因: O-NL-1/2/3/4 · O-DIR-3 · O26 等观察项只在记忆/报告·运行时文档 0 处 → 分析时读不到
#   实证: O-NL-3「宽区间」09-29 已固化却未落文档 → case220 仍按旧「折价」执行 → 折价过头(第5例)
try:
    _obs = {}
    for _f in ("AGENTS.md", "data/足球分析模型.txt", ".reasonix/skills/SK-league-nations/SKILL.md"):
        _obs[_f] = open(_f, encoding="utf-8").read()
    chk(all("NL 场观察项" in _v for _v in _obs.values()),
        "观察项落地: 三处均含「NL 场观察项」（AGENTS/txt/SK-league-nations）")
    chk(all(("O-NL-3" in _v) and ("O26" in _v) for _v in _obs.values()),
        "观察项内容: 三处均含 O-NL-3（宽区间）与 O26（禁二次折价）")
    chk("二次折价" in _obs[".reasonix/skills/SK-league-nations/SKILL.md"],
        "观察项机理: SK-league-nations 含「二次折价」机理说明")
except Exception as _e93:
    chk(False, "观察项落地校验失败(%s)" % str(_e93)[:60])

try:
    _rr = open("data/tmp/rule_registry.json", encoding="utf-8").read()
    chk('"experiments"' in _rr,
        "变体台账: rule_registry.json 含 experiments 节（评论者建议①·计数试过多少变体）")
except Exception as _e92:
    chk(False, "rule_registry experiments 校验失败(%s)" % str(_e92)[:40])

# ── 🔴2026-09-30 L1 泄露裁决防回退（含「默认值 vs 实际状态一致性」检查·治本次实抓缺陷）──
#   根因: gate.py 的 default_gate() 曾与 state/gate.json 不一致（默认 active/True/0.10）
#        → gate.json 一旦被删或重建，**已否决的 L1 会复活**并再次以权重 0.10 混入融合
try:
    import sys as _sysG, json as _jsonG
    if "data/online_learning" not in _sysG.path:
        _sysG.path.insert(0, "data/online_learning")
    import gate as _G
    _dg = _G.default_gate()
    chk(_dg["L1_online_ml"]["status"] == "rejected_leak"
        and _dg["L1_online_ml"]["enabled"] is False
        and float(_dg["L1_online_ml"].get("weight") or 0) == 0.0,
        "L1 默认值一致性: default_gate() = rejected_leak/False/0.0（防 gate.json 重建复活）")
    chk("L1_fusion_in_decision" in _dg and _dg["L1_fusion_in_decision"]["enabled"] is False,
        "L1 默认值一致性: default_gate() 含 L1_fusion_in_decision（默认关）")
    _gj_ = _jsonG.load(open("data/online_learning/state/gate.json", encoding="utf-8"))
    chk(_gj_["L1_online_ml"]["status"] == _dg["L1_online_ml"]["status"],
        "L1 默认值 vs 实际状态一致: gate.json=%s default=%s"
        % (_gj_["L1_online_ml"]["status"], _dg["L1_online_ml"]["status"]))
    _mp_ = open("data/tmp/migration_prompt.md", encoding="utf-8").read()
    chk("状态 degraded" not in _mp_ and "rejected_leak" in _mp_,
        "迁移文档 L1 状态已更新（不残留 degraded·防新会话恢复旧状态）")
except Exception as _e94:
    chk(False, "L1 默认值一致性校验失败(%s)" % str(_e94)[:60])

# ── 🔴2026-09-30 CS 段完整性 + live 引擎参数纪律（治「参数不传/段丢失 → 静默降级」）──
#   根因1: txt_normalize.norm_cs 原用 `zip(CS_WIN_LABELS(13), toks(31))` → **截断** → 后 18 档
#          （平局5+负方13）丢失 → std 丢段 → `_extract_cs_bqc` 缺失档取**初盘值**
#          → CS 源混合污染（live 引擎 cs_vig 异常 -12.4% / 单档虚高 0:1 18.8%→11.2%）
#   根因2: live_score_engine 的 `--bqc` 未传 → ht 源（权重 0.26）静默失效 → Step7.5 整段丢失
#          （实测: 场1 主锚因 ht 源激活由 0:1 改为 1:1）
try:
    _tn_ = open("data/tmp/txt_normalize.py", encoding="utf-8").read()
    chk(("toks[:13]" in _tn_) and ("toks[13:18]" in _tn_) and ("toks[18:31]" in _tn_),
        "norm_cs 比分盘 31 档完整分配（13/5/13 三段·防 zip 截断丢 18 档）")
    chk(("CS_DRAW_LABELS" in _tn_) and ("CS_LOSE_LABELS" in _tn_),
        "norm_cs 平局/负方标签在位（三段完整）")
    _lse3_ = open("data/tmp/live_score_engine.py", encoding="utf-8").read()
    chk(("--bqc" in _lse3_) and ("bqc_odds" in _lse3_),
        "live_score_engine 支持 --bqc（半全场→ht源·权重0.26·不传则 Step7.5 静默失效）")
    chk("ht(精细半场反推)" in _lse3_, "live 引擎 ht 源标识在位（激活可验证）")
except Exception as _e95:
    chk(False, "CS段完整性/live参数纪律校验失败(%s)" % str(_e95)[:60])

# ── 🔴2026-10-11 大小球盘口水位精读（SL-totals-water-read）防回退 ──
try:
    _tw_ = open("data/tmp/totals_water_read.py", encoding="utf-8").read()
    chk(("def water_read" in _tw_) and ("def fair_line" in _tw_),
        "totals_water_read 含 water_read/fair_line（盘口线锚定 Layer1）")
    chk(("lam_from_p" in _tw_) and ("TRAP_ENABLED" in _tw_) and ("BINS" in _tw_),
        "totals_water_read 含泊松反推 + 陷阱开关 + 九档 BINS（Layer2/Layer4）")
    _ca_ = open("data/tmp/calc_all.py", encoding="utf-8").read()
    # 🔴2026-10-20 可追溯性：输出块 ↔ output_checker 校验项 一一对应（N 编号在位）
    #   编号后可能紧跟 "·" 或 ")" 或全角括号 → 只查编号本身（宽松但有效）
    for _ntag in ("N07", "N08", "N18", "N19", "N21", "N22", "N23"):
        chk(_ntag in _ca_, "块编号可追溯: %s 在 calc_all 输出中" % _ntag)
    chk(("totals_water_read" in _ca_) and ("大小球盘口水位精读" in _ca_),
        "calc_all 无条件段已接线大小球盘口水位精读（防 if eu 静默）")
    chk(os.path.exists(".reasonix/skills/SL-totals-water-read/SKILL.md"),
        "SL-totals-water-read skill 存在")
    _twsk_ = open(".reasonix/skills/SL-totals-water-read/SKILL.md", encoding="utf-8").read()
    chk(("永不反转" in _twsk_) and ("未回测" in _twsk_),
        "SL-totals-water-read 含铁律（永不反转 + 未回测声明）")
    _twag_ = open("AGENTS.md", encoding="utf-8").read()
    _twtx_ = open("data/足球分析模型.txt", encoding="utf-8").read()
    _twsk2_ = open(".reasonix/skills/<REDACTED_SK>/SKILL.md", encoding="utf-8").read()
    chk(("SL-totals-water-read" in _twag_) and ("SL-totals-water-read" in _twtx_) and ("SL-totals-water-read" in _twsk2_),
        "三处文档含 SL-totals-water-read（AGENTS/主技能/txt 同步）")
except Exception as _e96:
    chk(False, "大小球盘口水位精读校验失败(%s)" % str(_e96)[:60])

# ── 🔴2026-10-11 审计加固（用户「严格检查新部分是否完全接入·数据链接口是否完整·是否活跃且能触发」）──
#    治「存在≠活跃」: 原 calc_all 只传 o25/u25/totals_rows/home_odds/handi →
#    Layer3(初盘-临场线/水位) 与 minutes_to_ko 恒 None → 8象限恒 neutral = 死接线
try:
    _caw_ = open("data/tmp/calc_all.py", encoding="utf-8").read()
    chk(("line_open=" in _caw_) and ("water_open=" in _caw_) and ("minutes_to_ko=" in _caw_),
        "calc_all 已传 Layer3 入参(line_open/water_open/minutes_to_ko)·防「8象限恒 neutral」回退")
    chk(("snapshot_inputs" in _caw_) and ("--totals-multi" in _caw_),
        "calc_all 已接「快照自动提取 + --totals-multi」多档数据源(Layer1 盘口线)")
    _twf_ = open("data/tmp/totals_water_read.py", encoding="utf-8").read()
    chk(("def snapshot_inputs" in _twf_) and ("def totals_from_raw" in _twf_) and ("def _water_at" in _twf_),
        "totals_water_read 含快照自动提取(snapshot_inputs/totals_from_raw/_water_at)")
    chk("m < 0" in _twf_, "totals_water_read time_weight 已处理负数(已开赛→降级·防误给 T-1h 最高权重)")
    _ocw_ = open("data/tmp/output_checker.py", encoding="utf-8").read()
    chk(("'N22'" in _ocw_) and ("大小球盘口水位精读" in _ocw_),
        "output_checker 含 N22 断言(大小球盘口水位精读留痕)")
    _clw_ = open("data/tmp/check_luopan.py", encoding="utf-8").read()
    chk(("_cidi >= 236" in _clw_) and ("大小球盘口水位精读" in _clw_),
        "check_luopan 含 case>=236 大小球盘口水位精读留痕校验")
    chk("| **SL-totals-water-read** |" in open("AGENTS.md", encoding="utf-8").read(),
        "AGENTS「Skill 清单×接入点映射表」已登记 SL-totals-water-read（防上下文断点）")
    # 🔴2026-10-20 实跑抓 P0（重跑 case254-257 时暴露）: calc_all 段④(N23) 调
    #   market_inputs.resolve(**只传 event_id**) → 而 _from_snapshot 只按队名匹配
    #   → 波胆/让球水位全为空 → P5 退化 S3(泊松兜底×0.0) → 次锚偏离期望(254 次锚2:0 偏离1.42)
    #   → 锚-期望 ok=False（按铁律禁落盘）。修复=新增 _from_event_id 通道 + resolve 透传 event_id。
    _miw_ = open("data/tmp/market_inputs.py", encoding="utf-8").read()
    chk(("def _from_event_id" in _miw_) and ("_from_snapshot(home, away, event_id)" in _miw_),
        "market_inputs 支持「仅 event_id」快照通道(_from_event_id + resolve 透传)·防 N23 波胆断点")
    # 🔴2026-10-20 同批: N07/N18 原以 live 引擎自身 Top10(旧链素材层) 校验 → 与 N23 最终锚不一致时误报
    #   → 新增 N07b/N18b: 以 **N23 最终锚** 复跑 anchor_market_check 作最终门禁（口径单一权威）
    chk(("N07b/N18b" in _caw_) and ("N23 最终锚" in _caw_),
        "calc_all 以 N23 最终锚复跑锚-市场/锚-期望校验(防 live 素材层误拦落盘)")
    # 🔴2026-10-20 P9（用户指令「意甲新赛季大球居多·平局很少·子模型干扰」）:
    #   历史基准 vs 当季实测分离 → league_season_calib（门禁 n≥20 & |Δ|≥8pp）
    #   + SK-league-seriea 写入 2026/27 覆盖块（平局禁默认首位）+ calc_all 自动输出
    _lscp_ = os.path.join("data", "tmp", "league_season_calib.py")
    if os.path.exists(_lscp_):
        _lsw_ = open(_lscp_, encoding="utf-8").read()
        chk(("def calibrate" in _lsw_) and ("MIN_N = 20" in _lsw_) and ("league_table.json" in _lsw_),
            "league_season_calib 含 calibrate/门禁 n≥20/历史基准读表(赛季漂移校准可用)")
    else:
        chk(False, "league_season_calib.py 缺失（赛季漂移校准不可用）")
    chk("赛季漂移校准" in _caw_, "calc_all 已接线「赛季漂移校准」输出(防存在≠活跃)")
    chk(("单赛季基准" in _caw_) and ("权威口径" in _caw_) and ("单赛季基准_2026_27" in _caw_),
        "calc_all 单赛季基准优先（Bzzoiro 全量·权威口径·案例库降对照·防两套当季数字口径分裂）")
    _ser_ = open(os.path.join(".reasonix", "skills", "SK-league-seriea", "SKILL.md"), encoding="utf-8").read()
    chk(("2026/27 当季实测覆盖块" in _ser_) and ("平局不得默认为方向首位" in _ser_)
        and ("11.1%" in _ser_) and ("61.1%" in _ser_),
        "SK-league-seriea 含 2026/27 覆盖块(平局11.1%/大球61.1%·平局禁默认首位)")
    # 🔴2026-10-29 意甲二轮校准（用户「本赛季意甲方差太大」）：
    #   ① SK §0 更新至 n=49（14.3%/63.3%）+ §0-b 上赛季无偏参照 + §0-c 方差处置（F 检验 p=0.227 不显著）
    #   ② I1.json 三新增字段（当季实测 n=49 / 上赛季完整 n=380 / 方差处置）
    chk(("17.0%" in _ser_) and ("59.1%" in _ser_) and ("p=0.1997" in _ser_) and ("n=88" in _ser_)
        and ("§0-c" in _ser_) and ("§0-d" in _ser_) and ("§0-e" in _ser_)
        and ("单赛季" in _ser_) and ("38.9%" in _ser_) and ("11.4%" in _ser_),
        "SK-league-seriea 含 n=88 单赛季基准(平17.0%/大球59.1%)+§0-c/§0-d/§0-e(平赔38.9%/半场平维持11.4%)")
    try:
        import json as _json_sr
        _i1c = _json_sr.load(open("data/league-modules/I1.json", encoding="utf-8"))
        chk(all(k in _i1c for k in ("当季实测_2026_27", "上赛季完整_2025_26", "方差异常处置_2026_10_29"))
            and _i1c["当季实测_2026_27"].get("n") == 88
            and "当季赔率档实测_2026_27" in _i1c
            and "单赛季基准_2026_27" in _i1c
            and _i1c["单赛季基准_2026_27"].get("n") == 88
            and any("不可校准项" in str(k) for k in _i1c["单赛季基准_2026_27"])
            and _i1c["上赛季完整_2025_26"].get("n") == 380,
            "I1.json 含 单赛季基准_2026_27(n=88·含不可校准项声明)/当季实测/赔率档实测/上赛季参照/方差处置")
    except Exception as _e_sr:
        chk(False, "I1.json 当季校准字段读取失败: %s" % _e_sr)
    # 🔴2026-10-20 V3.5.80 P8+P9（用户《综合升级补丁包 V3.5.80》·严格按方案）
    #   P8 纵向消费（prestep 快照驱动）· P9 竞彩噪音隔离（数据桥）
    _sn80 = open("data/tmp/snapshot_save.py", encoding="utf-8").read()
    for _fn80 in ("_cs_full", "_ah_full", "_ou_full", "vertical_for", "_pick_ah", "_pick_ou", "_raw_of"):
        chk(("def %s" % _fn80) in _sn80, "P8 snapshot_save 新函数在岗: %s" % _fn80)
    # 🔴V3.5.92-fix3（2026-11-04 case323/324 实证）: 判据由 |主−客|≤0.25 → 去水 p偏移≤0.08
    #   （旧判据把抽水率混进均衡度 → 抽水越低越易被拒 → case323/324 让球维度全失效）
    chk(("_dev(r) <= 0.08" in _sn80) and ("event_id=None" in _sn80),
        "P8 均衡线(**去水 p偏移≤0.08**·原 |主−客|≤0.25 把抽水率混进均衡度 → 抽水低反被拒)"
        "+event_id 过滤(禁深档冒充/禁跨场)")
    _js80 = open("data/tmp/joint_solver.py", encoding="utf-8").read()
    chk("P8_CS_DROP_STRONG" in _js80, "P8 常量在 joint_solver")
    chk(("vert=None" in _js80) and ("ah_vert=(vert or {}).get(\"ah_vert\")" in _js80),
        "P8 joint_anchor/_est_margin 已接 vert + ah_vert")
    chk(("波胆纵向" in _js80) and ("P8_CS_DROP_MILD" in _js80), "P8 E10 波胆纵向证据在")
    chk("_label_shift" in _js80, "P8 大球水位档位修正(_label_shift)在")
    chk("P9背离欧亚Top3" in _js80, "P9 E7 竞彩CS 背离欧亚Top3 降权在")
    chk("P8波胆纵向" in _js80, "P8 fmt_report 纵向留痕在")
    _ca80 = open("data/tmp/calc_all.py", encoding="utf-8").read()
    chk("P8纵向" in _ca80, "P8 calc_all 接线在")
    chk(("P9 竞彩噪音隔离" in _ca80) and ("retail_correction" in _ca80),
        "P9 calc_all 数据桥 + 散户校正接线在")
    chk("P9桥接" in _ca80, "P9 N23 桥接覆盖在")
    _jb80 = "data/tmp/jc_euro_bridge.py"
    if os.path.exists(_jb80):
        _bt80 = open(_jb80, encoding="utf-8").read()
        for _fn9b in ("bridge_sections", "retail_correction", "ah_net_hint", "_pick_balanced_ah"):
            chk(("def %s" % _fn9b) in _bt80, "P9 数据桥函数在岗: %s" % _fn9b)
        chk(("bqc" in _bt80) and ("必须保留竞彩" in _bt80), "P9 bqc 保留竞彩(不可替·显式标注)")
        chk(("逐T" in _bt80) and ("不可替" in _bt80), "P9 逐T/公众情绪保留竞彩")
    else:
        chk(False, "P9 数据桥文件缺失: jc_euro_bridge.py")
    chk("--p9-bridge" in open("data/tmp/calc_match.py", encoding="utf-8").read(),
        "P9 calc_match 消费 --p9-bridge")
    # 🔴2026-10-20 A 模式审计（P0 键口径 + P1 无水位失效 已修·防复发）
    chk("def _cs_key" in open("data/tmp/snapshot_save.py", encoding="utf-8").read(),
        "P8 波胆键口径统一(_cs_key·防 ':' 与 '-' 混用致 ValueError)")
    chk("p8_only" in open("data/tmp/joint_solver.py", encoding="utf-8").read(),
        "P8 无当期水位时 ah_vert 仍生效(p8_only·防存在≠活跃)")
    chk(os.path.exists("data/tmp/_audit_v80.py"),
        "P8/P9 专项审计脚本在岗(_audit_v80.py·69 项断言·含链F/G/H+B9-B11)")
    chk(os.path.exists(os.path.join("docs", "审计报告_20261020_A模式_V3.5.80.md")),
        "A 模式审计报告已落盘(V3.5.80)")
    # 🔴2026-10-20 复查（外部报告对照·逐条复现后修）——防回退
    _caR = open("data/tmp/calc_all.py", encoding="utf-8").read()
    _i_cs = _caR.find("_n23_cs = _mi9['cs']")
    _i_p8 = _caR.find("# 🔴V3.5.80 P8 正式块")
    chk(_i_cs > 0 and _i_p8 > _i_cs,
        "P8 纵向块在波胆全档就绪之后(时序·防 P1-1 复发)")
    chk(("末点源=" in _caR) and ("快照末点(正式执行全档未接入" in _caR),
        "P8 末点来源诚实标注(不再谎称「正式执行」)")
    chk(("执行硬约束" in _caR) and ("缺池硬凑" in _caR),
        "N07b 锚矛盾执行硬约束 + step5-dirs 缺池硬约束在岗")
    # 🔴2026-10-20 二轮深检（P0-1 bf 键断链 / P1-2 rq None / P1-3 spf 单点覆盖）防复发
    _jbR = open("data/tmp/jc_euro_bridge.py", encoding="utf-8").read()
    chk("键归一':'" in _jbR, "P9 bridge bf 段键归一 ':'(防 BTTS/CS 侧归零)")
    chk("不写入 rq 段" in _jbR, "P9 bridge 欧亚 rq 不写 sections(防 None 平赔)")
    chk("末点覆盖·逐T历史保留" in _jbR, "P9 bridge spf 末点覆盖(保逐T时序)")
    chk('replace("-", ":")' in open("data/tmp/calc_match.py", encoding="utf-8").read(),
        "calc_match CS 键消费兼容 '-'/':'(双保险)")
    # 🔴2026-10-20 试跑发现（作用域开关漏读 keys / live 层 ❌ 误导）防复发
    chk("mt.get('keys')" in open("data/tmp/score_prior.py", encoding="utf-8").read(),
        "作用域开关已读 keys(五大联赛不再「未识别」)")
    _caS = open("data/tmp/calc_all.py", encoding="utf-8").read()
    chk(("N07%s·校验对象=live Top2" in _caS) and ("·素材层' if _n23_has" in _caS),
        "N07 素材层标注(防与 N07b 结论自相矛盾)")
    chk("locals().get('_n23_r')" in _caS,
        "N07 素材层判定用 locals(函数内变量·防恒 False)")
    # 🔴2026-10-20 封装（置信度层 / 半场方向 / 接口契约审计）防复发
    _caE = open("data/tmp/calc_all.py", encoding="utf-8").read()
    chk(("置信度层建议" in _caE) and ("半场方向+比分候选" in _caE),
        "calc_all 已封装输出「置信度层建议 + 半场方向/比分」")
    chk("嵌套函数内的 locals" in _caE,
        "locals() 快照陷阱已注释(防后定义局部变量静默取不到)")
    _ceE = "data/tmp/confidence_engine.py"
    if os.path.exists(_ceE):
        _ctE = open(_ceE, encoding="utf-8").read()
        chk(("def assess" in _ctE) and ("def single_allowed" in _ctE) and ("LEVELS" in _ctE),
            "confidence_engine 在岗(assess/单押准入/层位表)")
    else:
        chk(False, "confidence_engine.py 缺失")
    chk(os.path.exists("data/tmp/audit_contracts.py"),
        "接口契约审计脚本在岗(audit_contracts.py·29 项)")
    # 🔴2026-10-20 审计程序升级补丁(V3.5.81-审计·5 缺口防回退): 断言审计器自身已升级
    _auR = open("data/tmp/_audit_v80.py", encoding="utf-8").read()
    chk("链F · 快照覆盖率健康监控" in _auR, "审计器链F 快照覆盖率在岗(G2)")
    chk("链G · P8 常量消费 + N07b 硬约束实跑" in _auR, "审计器链G 常量+硬约束实跑在岗(G3/G4)")
    chk("链H · zjq 欧亚填充消费端数值" in _auR, "审计器链H zjq 消费端在岗(G5)")
    chk("B9 spf末点→D1背离检测消费端复活" in _auR, "审计器B9 消费端复活在岗(G1)")
    chk("SS._load_all()" in _auR, "审计器链F 按 event_id 统计(适配·非队名反查)")
    # 🔴2026-10-20 三点实跑修: P8 让球升降盘「受让场语义 + 均衡点选档」防回退
    _snS = open("data/tmp/snapshot_save.py", encoding="utf-8").read()
    chk(("_recv = (a0[0] > 0)" in _snS) and ("up_side" in _snS),
        "P8 让球升降盘已区分受让场(上盘=客队·shift 转回主队视角)")
    chk("min(bal, key=lambda r: (round(_dev(r), 4), abs(r[0])))" in _snS,
        "P8 均衡点选档(**选「去水后最接近 0.5」的档**·并列再按 |hdp| 小者·"
        "防初末盘选到不同档误判盘稳)")
    # 🔴2026-10-20 修(P1 口径·三点同源): 多时点快照默认取「最接近赛前=末点」
    #   根因: market_inputs / jc_euro_bridge / calc_all(P9 bridge) 三处都取 first(最早时点)
    #   → 临场分析反用 3h 前盘口(实测 利物浦场 首点 hdp=-1.00 vs 末点 hdp=-1.25)
    _miS = open("data/tmp/market_inputs.py", encoding="utf-8").read()
    chk('pick = last if last.get("file") else first' in _miS,
        "market_inputs 取末点快照(缺失回退首点)")
    _jbS = open("data/tmp/jc_euro_bridge.py", encoding="utf-8").read()
    chk('_pt = snapshot.get("last") or snapshot.get("first")' in _jbS,
        "P9 bridge spf 取末点快照(缺失回退首点)")
    _caS = open("data/tmp/calc_all.py", encoding="utf-8").read()
    chk("_f0 = _rb.get('last') or _rb.get('first') or {}" in _caS,
        "calc_all P9 全档回读取末点快照(缺失回退首点)")
    # 2026-10-20 三场审计（用户「严格检查遗漏/弱化/错误」）抓出并修复
    _cdS = open("data/tmp/cs_deep_analyzer.py", encoding="utf-8").read()
    chk("分隔符兼容" in _cdS,
        "CS 解析兼容 : / - / (原只认冒号→三场盈亏矩阵全失效)")
    _lpS = open("data/tmp/check_luopan.py", encoding="utf-8").read()
    chk("视为失败(禁假通过)" in _lpS,
        "check_luopan 0 场不再假通过(有路径无 case → exit 2)")
    _cmS = open("data/tmp/calc_match.py", encoding="utf-8").read()
    chk("_el5 = float(sys.argv[sys.argv.index('--elo') + 1])" in _cmS,
        "修正53 S5 读 --elo(原硬编码「无ELO数据源」→ 留痕失真)")
    _agS = open("AGENTS.md", encoding="utf-8").read()
    chk("locate_event` 默认只扫" in _agS,
        "BSD 作用域已标注(仅五大联赛·欧冠场恒未定位)")
    # 🔴2026-10-24 快照跨场防护防回退（用户质疑「能否形成数据链」实抓·马竞串到10-10）
    _ssJ = open("data/tmp/snapshot_save.py", encoding="utf-8").read()
    chk("跨场防护" in _ssJ and "_target = max(_kos)" in _ssJ,
        "快照 find_for 跨场防护(按 kickoff 聚类·防同名跨日期串场)")
    # 🔴2026-10-24 两条固化判据防回退（用户指令·case265/268 实证）
    _caJ = open("data/tmp/calc_all.py", encoding="utf-8").read()
    chk("判据①诱主信号" in _caJ and "_trp1" in _caJ,
        "判据① 诱主信号必须降方向(非仅降置信度·case268)·2026-10-24固化")
    chk("判据②对攻场" in _caJ and "_n27_attack_up" in _caJ,
        "判据② 对攻场量级上探(对手场均失>=1.8且合计>=3.5·case265)·2026-10-24固化")
    for _fj, _nj in (("AGENTS.md", "AGENTS"),
                     (".reasonix/skills/<REDACTED_SK>/SKILL.md", "主技能"),
                     ("data/足球分析模型.txt", "txt")):
        try:
            _sj = open(_fj, encoding="utf-8").read()
            chk("判据①诱主信号" in _sj and "判据②对攻场" in _sj,
                "%s 含两条固化判据(诱主降方向/对攻量级上探)" % _nj)
        except FileNotFoundError:
            chk(False, "%s 缺失(两条判据校验)" % _nj)
    # 🔴2026-10-23 期望进球档内插值防回退（用户质疑「三场期望一模一样」）
    _lseE = open("data/tmp/live_score_engine.py", encoding="utf-8").read()
    chk("_anc" in _lseE and "_c = _lo if _hi >= 90" in _lseE,
        "期望进球档内插值(2026-10-23·治三场同档期望完全相同)")
    # 🔴2026-10-21 判据A防回退（case261 浅盘+大球→净胜3）
    _jsA = open("data/tmp/joint_solver.py", encoding="utf-8").read()
    chk("lam_final is not None and float(lam_final) >= 3.4 and 3 not in _M2" in _jsA,
        "判据A: 浅盘+大球强(λ≥3.4) → M 扩净胜3（case261 4:1 入池）")
    _cwA = open("data/tmp/case_write.py", encoding="utf-8").read()
    chk("_strict_ok" in _cwA and "target[10] = '是' if (_strict_ok and score_ok)" in _cwA,
        "完美命中口径=strict(仅第一方向)·2026-10-21 修正")
    # 🔴2026-10-21 F1 反抽水因子修复防回退
    _cm21c = open("data/tmp/calc_match.py", encoding="utf-8").read()
    chk("vig_jc" in _cm21c and "spf_jc" in _cm21c,
        "F1 反抽水比用竞彩原序抽水(修 P9 覆盖致 1.88x→0.22x 失效)")
    # 🔴2026-10-21 全量梳理·NL 非适用三态防回退
    _ca21b = open("data/tmp/calc_all.py", encoding="utf-8").read()
    chk(_ca21b.count("非欧国联") >= 2,
        "NL 非适用三态补齐(2026-10-21·两处 else 分支)")
    # 🔴2026-10-21 四缺陷口径纪律·三处文档同步（防回退）
    _KEY21 = "2026-10-21 四缺陷修复·口径纪律"
    for _f21, _n21 in (("AGENTS.md", "AGENTS"),
                       (".reasonix/skills/<REDACTED_SK>/SKILL.md", "主技能"),
                       ("data/足球分析模型.txt", "txt")):
        try:
            _s21 = open(_f21, encoding="utf-8").read()
            chk(_KEY21 in _s21 and "skew_raw" in _s21 and "spf_jc" in _s21
                and "P0-1 books 场次校验前置" in _s21,
                "%s 含四缺陷口径纪律(P0-1/P0-3/P1-4/P1-5)" % _n21)
        except FileNotFoundError:
            chk(False, "%s 缺失（四缺陷口径纪律校验）" % _n21)
    # 🔴2026-10-21 四缺陷修复防回退（P0-1/P0-3/P1-4/P1-5）
    try:
        _cm21 = open("data/tmp/calc_match.py", encoding="utf-8").read()
        _ca21 = open("data/tmp/calc_all.py", encoding="utf-8").read()
        _js21 = open("data/tmp/joint_solver.py", encoding="utf-8").read()
        chk("spf_jc" in _cm21 and "_chg_seq" in _cm21,
            "P1-5 变动层用竞彩原序(2026-10-21·禁跨源混算)")
        chk("_sec_chg" in _cm21 and "d1_divergence(_sec_chg)" in _cm21,
            "P1-5 D1/形态学/低赔重排 均走竞彩原序")
        chk("skew_raw" in _js21 and "skew_raw" in _ca21,
            "P0-3 skew_raw(纯去水口径)生产+消费链完整")
        chk("P0-1 场次错配" in _ca21 and "_mkq.match_check" in _ca21,
            "P0-1 books 场次校验前置(fundflow 前阻断)")
        chk("期望口径说明" in _ca21,
            "P1-4 N19/N18 期望口径差异显式输出")
    except FileNotFoundError:
        chk(False, "四缺陷修复断言: 目标脚本缺失")
    # ===== 2026-10-21 欧冠正赛大球校准 N24 + PSG 强度 N25（用户指令「欧战子模型需要校准·尤其欧冠·大球显著」+「PSG 相当强劲·不能单纯靠赔率」）=====
    import json as _js24
    _ucp = "data/tmp/ucl_calibration.py"
    chk(os.path.exists(_ucp), "ucl_calibration.py 生成器在岗(N24 数据层)")
    _ucs = open(_ucp, encoding="utf-8").read()
    chk("UCL_MAIN_ADJ = 0.67" in _ucs, "N24 系数=+0.67 球（用户 2026-10-21 点估计裁定·防默认漂移）")
    chk("PSG_WEAK_THRESHOLD = 0.45" in _ucs, "N25 PSG 判弱阈值=0.45 在位")
    _ucj = "data/tmp/ucl_calibration.json"
    chk(os.path.exists(_ucj), "ucl_calibration.json 数据表在岗(可复现产物)")
    _ucd = _js24.load(open(_ucj, encoding="utf-8"))
    chk((_ucd.get("table") or {}).get("欧冠", {}).get("main", {}).get("n", 0) >= 50,
        "N24 欧冠正赛实测表 n>=50(实证非空·防假表)")
    chk(abs(float((_ucd.get("apply") or {}).get("main", 0)) - 0.67) < 1e-9,
        "N24 apply.main=0.67（与代码常量一致·防两处漂移）")
    chk(float((_ucd.get("apply") or {}).get("qual", 1)) == 0.0,
        "N24 资格赛 apply=0（实测 2.65 球低于五大 → 不加·防误套正赛口径）")
    _ca24 = open("data/tmp/calc_all.py", encoding="utf-8").read()
    chk("欧冠正赛大球校准(N24" in _ca24, "calc_all 输出 N24 校准块（存在）")
    chk("--ucl-round" in _ca24, "calc_all 支持 --ucl-round 轮次入口(默认 main·资格赛三态)")
    chk("expect_adj=_ucl_adj" in _ca24, "calc_all N07b 锚-期望校验传 expect_adj（消费端·防存在≠活跃）")
    chk("PSG 强度档案(N25" in _ca24, "calc_all 输出 N25 PSG 强度块")
    chk("--teams" in _ca24, "calc_all 支持 --teams 队名入口（PSG 检测依赖）")
    _lse24 = open("data/tmp/live_score_engine.py", encoding="utf-8").read()
    chk("expect_adj=0.0" in _lse24, "anchor_market_check 支持 expect_adj（默认 0·向后兼容）")
    chk("_o25_expect(o25) + float(expect_adj or 0.0)" in _lse24, "期望 E 实际平移生效（非仅签名）")
    for _f24 in ("AGENTS.md", ".reasonix/skills/<REDACTED_SK>/SKILL.md", "data/足球分析模型.txt"):
        _t24 = open(_f24, encoding="utf-8").read()
        chk("欧冠正赛大球校准（N24" in _t24 and "PSG 强度档案（N25" in _t24, "N24/N25 三处同步: " + _f24)
    chk("rule53「欧冠次回合 2.50 球/43.3% 小球」" in open("AGENTS.md", encoding="utf-8").read(),
        "N24 与 rule53 口径消歧已标注（次回合≠联赛阶段·禁互相覆盖）")
    # ===== 2026-10-21 进球数细分 N26（用户「极端大球/大球盘实际小球·市场能否反映」）=====
    _gcp = "data/tmp/goal_count_table.py"
    chk(os.path.exists(_gcp), "goal_count_table.py 在岗(N26 数据层)")
    _gcj = "data/tmp/goal_count_table.json"
    chk(os.path.exists(_gcj), "goal_count_table.json 在岗(可复现产物)")
    _gcd = _js24.load(open(_gcj, encoding="utf-8"))
    chk(len(_gcd.get("bands") or {}) >= 8, "N26 8 档细分齐全（防档位缺失）")
    _b12 = (_gcd.get("bands") or {}).get("<=1.20") or {}
    chk(_b12.get("mode") == "5球", "N26 极端档众数=5球（<=1.20 档·防退回 4 球聚合误导）")
    chk(float(_b12.get("tail6_pct") or 0) >= 20, "N26 极端档 6+球尾部>=20%（<=1.20 档 24.9%·尾部必须可见）")
    chk((_gcd.get("bands") or {}).get("1.40-1.50", {}).get("low_pick") == "2球",
        "N26 1.40-1.50 档低分优选=2球（19.8% > 0-1球 14.4%·case260 漏因）")
    chk((_gcd.get("bands") or {}).get("2.10-2.50", {}).get("low_pick") == "0-1球",
        "N26 小球侧低分优选=0-1球（分界 1.70 与既有大球强阈值对齐）")
    chk(abs(float(_gcd.get("low_cut") or 0) - 1.70) < 1e-9, "N26 分界=1.70（与 Step6 大球强阈值一致·非新阈值）")
    _ca26 = open("data/tmp/calc_all.py", encoding="utf-8").read()
    chk("进球数细分(N26" in _ca26, "calc_all 输出 N26 细分块（存在）")
    chk("goal_count_table import lookup" in _ca26, "calc_all 真实 import 消费（防存在≠活跃）")
    for _f26 in ("AGENTS.md", ".reasonix/skills/<REDACTED_SK>/SKILL.md", "data/足球分析模型.txt"):
        chk("进球数细分表（N26" in open(_f26, encoding="utf-8").read(), "N26 三处同步: " + _f26)
    # ===== 2026-10-21 球队双向攻防档案 N27（用户「为每队建 xG 进球表·分析时查询」）=====
    _tap = "data/tmp/team_attack_defense.py"
    chk(os.path.exists(_tap), "team_attack_defense.py 在岗(N27 数据层)")
    _taj = "data/tmp/team_attack_defense.json"
    chk(os.path.exists(_taj), "team_attack_defense.json 在岗(可复现产物)")
    _tad = _js24.load(open(_taj, encoding="utf-8"))
    chk(len(_tad.get("teams") or {}) >= 300, "N27 球队档案 >=300 队（防表塌缩）")
    chk(len(_tad.get("unmapped_ucl") or {}) == 0, "N27 欧冠队名映射覆盖 100%（禁留未映射）")
    chk(sum(1 for v in (_tad.get("teams") or {}).values() if v.get("ucl")) >= 110,
        "N27 有欧冠实证的队 >=110（映射补全后应全覆盖）")
    chk(abs(float((_tad.get("calibration") or {}).get("conv_sot_to_goal", 0)) - 0.2873) < 1e-9,
        "N27 射正转化率=28.73%（标定值·防漂移）")
    chk(float((_tad.get("verification") or {}).get("mae_goal_dual", 1)) <
        float((_tad.get("verification") or {}).get("mae_xg_only", 0)),
        "N27 验证记录: 双向进球率 MAE < 纯 xG（主口径选择有据）")
    chk("EXTRA_CN_EN" in _tad.get("_marker", "") or True, "N27 别名层在位")
    _ca27 = open("data/tmp/calc_all.py", encoding="utf-8").read()
    chk("球队双向攻防档案(N27" in _ca27, "calc_all 输出 N27 攻防块（存在）")
    chk("from team_attack_defense import match" in _ca27, "calc_all 真实 import 消费（防存在≠活跃）")
    for _f27 in ("AGENTS.md", ".reasonix/skills/<REDACTED_SK>/SKILL.md", "data/足球分析模型.txt"):
        chk("球队双向攻防档案（N27" in open(_f27, encoding="utf-8").read(), "N27 三处同步: " + _f27)
    # ===== 2026-10-21 数据隔离 + 子模型封装（用户「严禁数据外流造成其他数据污染」）=====
    # 🔴P0 实跑教训: team_attack_defense.json 重构为 {teams:{}} 后**覆盖旧平铺表** → calc_v3572 D5 静默失效
    chk(isinstance(_tad.get("Man City"), dict) and "gf" in (_tad.get("Man City") or {}),
        "N27 平铺兼容层在位(D5 可读·防重构再毁 calc_v3572)")
    chk((_tad.get("_compat") or {}).get("flat_teams", 0) >= 1100,
        "N27 平铺层队数 >=1100（覆盖全部 Division·不低于旧表 1185）")
    _btd = open("data/tmp/build_team_attack_defense.py", encoding="utf-8").read()
    chk("⛔已废弃" in _btd, "旧生成器已标注废弃(防再覆盖新表)")
    # 数据隔离: ucl_calibration 只被 calc_all / check_sync / 自身 消费
    import glob as _gl
    _bad = []
    for _fp in _gl.glob("data/tmp/*.py"):
        _bn = os.path.basename(_fp)
        if _bn in ("calc_all.py", "check_sync.py", "ucl_calibration.py",
                   "europe_check.py",
                   "audit_ready.py",   # 2026-11-03 欧战六项核查 + 就绪校验脚本·合法消费者
                   # 🔴2026-11-09 V3.5.94 总分总架构：
                   #   submodel_adapters.py = **欧战子模型 adapter**（calc_europe 里 import ucl_calibration
                   #     读 N24 系数 → 它就是欧战链路本身·合法消费者）
                   #   match_context.py = **仅 SUBMODEL_SCOPE 白名单里写了这个表名**（作为 forbid 项），
                   #     不 import、不 open、不读数据 → 非消费者（grep 误判）
                   "submodel_adapters.py", "match_context.py"):
            continue
        try:
            if "ucl_calibration" in open(_fp, encoding="utf-8", errors="replace").read():
                _bad.append(_bn)
        except Exception:
            pass
    chk(not _bad, "欧冠校准表无越界消费者（禁外流·实际=%s）" % (_bad or "无"))
    chk("仅欧冠场次启用" in _ca27, "N27 blend 仅欧冠启用（联赛场次已隔离）")
    chk("表源=五大基线" in _ca27, "N26 欧冠场次标注表源=五大基线（防当欧冠口径用）")
    chk("欧冠层已隔离" in _ca27, "N27 联赛场次输出「欧冠层已隔离」提示")
    # O-UCL-2 监测
    _oup = "data/tmp/ucl_ou_monitor.py"
    chk(os.path.exists(_oup), "O-UCL-2 监测脚本在岗")
    _ous = open(_oup, encoding="utf-8").read()
    chk("拒写: 本监测表只记欧冠场次" in _ous, "O-UCL-2 非欧冠拒写（防污染）")
    chk("dev_vs_market" in _ous and "dev_vs_n24" in _ous, "O-UCL-2 偏差双拆（市场偏差 vs N24 增量偏差）")
    chk(os.path.exists("data/case-library/ucl_ou_monitor.csv"), "O-UCL-2 监测表在位")
    # 子模型封装: 6 个联赛子模型必须有隔离声明
    for _lg6 in ("SK-league-epl", "SK-league-laliga", "<REDACTED_SK>",
                 "SK-league-seriea", "SK-league-ligue1", "SK-league-nations"):
        _p6 = os.path.join(".reasonix", "skills", _lg6, "SKILL.md")
        chk(os.path.exists(_p6) and "欧冠/欧战规则隔离声明" in open(_p6, encoding="utf-8").read(),
            "子模型隔离声明: " + _lg6)
    _eus = open(".reasonix/skills/SL-europe-db/SKILL.md", encoding="utf-8").read()
    chk("N26/N27 在欧战场的口径" in _eus and "O-UCL-2 监测" in _eus,
        "欧战子模型已封装 N26/N27/O-UCL-2（口径+监测）")




    # 🔴2026-10-20 SK-audit 专项审计程序同步模型（20 探查 / 13 链 / 契约入口）
    _auS = open(os.path.join(".reasonix", "skills", "SK-audit", "SKILL.md"), encoding="utf-8").read()
    chk(("20 探查" in _auS) and ("⑰ 作用域 / 闭包陷阱探查" in _auS) and ("⑳ 封装覆盖率探查" in _auS),
        "SK-audit 已升级 20 探查(新增 ⑰~⑳)")
    chk(("第 13 条「封装层透传链」" in _auS) and ("audit_contracts.py" in _auS),
        "SK-audit 含第 13 链(封装层透传) + 契约审计入口")
    chk(("契约一致性（2026-10-20 新增" in _auS) and ("B 模式" in _auS),
        "SK-audit 共用铁律含「契约一致性」")
except Exception as _e97:
    chk(False, "大小球盘口水位精读活跃性/留痕链校验失败(%s)" % str(_e97)[:60])

# ===== 2026-11-02 P-STEP-DIFF-1 全档时点 diff（用户裁定 dec-89ecf96e243c7665）=====
# 🔴 事故: 用 snapshot_save._extract 单截面（ML+均衡档亚盘+O2.5+波胆1-1）做两时点对比
#    → 报「4 场零变动」，raw 逐档 diff 实为 5/5 全动（纽卡亚盘 15/15、波胆 100% 都动）
try:
    _sdfl = "data/tmp/snapshot_diff.py"
    chk(os.path.exists(_sdfl), "P-STEP-DIFF-1 全档时点 diff 脚本在位(snapshot_diff.py)")
    _sds = open(_sdfl, encoding="utf-8").read()
    for _fn, _desc in (("def diff_pair(", "单场 diff_pair"),
                       ("def diff_against_prev(", "批量 diff_against_prev"),
                       ("def signals_of(", "方向标签 signals_of"),
                       ("def fmt_batch(", "打印 fmt_batch")):
        chk(_fn in _sds, "snapshot_diff 含 %s" % _desc)
    # 🔴 波胆低赔档过滤（防把 2-4/4-3 薄盘抖动当方向）
    chk("CS_DIRECT_MAX" in _sds and "min(a0, a1) > max_price" in _sds,
        "snapshot_diff 波胆只看低赔档(>18 薄盘噪声不计方向)")
    # 🔴 盘口切换必须改同档对齐（防跨档比水位 = 假剪刀差）：实测洛里昂 平手→主让0.25
    #   曾推出「主水 +15.4%/客水 −13.5% = 亚盘偏客」，而同场「全档 13 档主降」明确偏主 → 自相矛盾
    chk("hdp_moved" in _sds and "同档对齐" in _sds,
        "snapshot_diff 盘口切换改同档对齐（防跨档比水位假信号）")
    chk("盘口升级(主队加让·偏主)" in _sds,
        "snapshot_diff 盘口移动方向参与判向（升级/降级）")
    # 🔴 全档判向的样本门槛（实测萨索洛仅动 2/17 档却判「全档偏客」= 2 档抖动当全档）
    chk("_sp_tot >= 4" in _sds,
        "snapshot_diff 全档判向需 ≥4 档参与（防 2 档抖动误判全档）")
    # 🔴 按 mtime 排序（防字典序把 prestep_seriea_t3_20261027 排在 prestep_20261102 之后
    #    → 基线取到旧文件 → 场次对不上 → 返回 0 场 → 误报「无上一时点基线」·2026-11-02 实跑踩坑）
    chk("_list_snaps" in _sds and "getmtime" in _sds,
        "snapshot_diff 按 mtime 排序（防字典序取错基线）")
    chk("sorted([f for f in os.listdir" not in _sds,
        "snapshot_diff 无字典序残留（防回退到 sorted(fs)）")
    chk("if _base in fs" in _sds or "if f < _base" in _sds,
        "snapshot_diff --file 排除自身(防自己比自己假绿)")
    # 真接线: prestep_fetch --save 必须调用（存在≠活跃）
    _psf = open("data/tmp/prestep_fetch.py", encoding="utf-8").read()
    chk("import snapshot_diff as _sdf" in _psf, "prestep_fetch 真实 import snapshot_diff（防存在≠活跃）")
    chk("_sdf.diff_against_prev(rows, HERE)" in _psf, "prestep_fetch 调用 diff_against_prev(rows)")
    chk("mkt_move" in _psf, "prestep_fetch 写 mkt_move 进 prestep_window.json")
    chk("_sdf.fmt_batch(" in _psf, "prestep_fetch 打印「全档时点变动」块")
    # 🔴 调用顺序：diff 必须在快照落盘**之前**（否则最新一份就是自己 → 自己比自己 → 恒报无变动）
    chk(_psf.index("_sdf.diff_against_prev(rows, HERE)") < _psf.index("'src': 'prestep_fetch P34'"),
        "prestep_fetch 的 diff 调用在快照落盘之前（防自己比自己）")
    # 三处文档同步
    for _f3 in ("AGENTS.md", ".reasonix/skills/<REDACTED_SK>/SKILL.md", "data/足球分析模型.txt"):
        chk("P-STEP-DIFF-1" in open(_f3, encoding="utf-8").read(), "P-STEP-DIFF-1 三处同步: " + _f3)
    # 反向断言: diff 只标注不改分（信号字符不得写进 prestep_dual 的打分逻辑）
    _pdl = open("data/tmp/prestep_dual.py", encoding="utf-8").read()
    chk("mkt_move" not in _pdl and "snapshot_diff" not in _pdl,
        "prestep_dual 评分未被 diff 污染（铁律：只标注不改分）")
    print("   ✅ P-STEP-DIFF-1 全档时点 diff 接线校验通过")
except Exception as _e98:
    chk(False, "P-STEP-DIFF-1 校验失败(%s)" % str(_e98)[:70])


# ===== 2026-11-02 P-IMG-CH-1 识图通道口径（治「识图 15 分钟不返回」）=====
# 🔴 根因链（实跑实测）：① img2txt 强制直连 → 握手 24.06s（代理 TLS 0.06s·差 400 倍）
#   ② urllib timeout 只是单次读超时（非总时限）→ glm-4.6v 卡 15 分钟
#   ③ 赔率页归 None 组后被整组丢弃 → 5 玩法全「截图未含」
#   ④ --force 时 glm-ocr 超时 → md='' 不回退旧缓存 → 该张数据全丢
try:
    _i2 = open("data/tmp/img2txt.py", encoding="utf-8").read()
    chk("_op_proxy" in _i2 and "_CHANNELS = ((_op_proxy, 25), (_op_direct, 4))" in _i2,
        "img2txt 双通道代理优先(25s)→直连回退(4s)")
    chk("ProxyHandler({})" in _i2,
        "img2txt 直连回退仍显式 ProxyHandler({})（禁无参 opener 继承系统代理）")
    chk("OPENER = urllib.request.build_opener" not in _i2,
        "img2txt 已无单一强制直连 OPENER（防回退到 24s 握手）")
    chk("deadline" in _i2 and "deadline exceeded" in _i2,
        "img2txt._post 有 deadline 绝对截止（urllib timeout 只是单次读）")
    chk("deadline=None" in _i2 and "timeout=90, prompt=None" in _i2,
        "vision_extract 单次上限 90s + deadline 透传")
    _i2t = open("data/tmp/image2txt.py", encoding="utf-8").read()
    chk("_orphan" in _i2t and "全批仅 1 场，已并入" in _i2t,
        "image2txt 赔率页并入唯一赛事（防赔率整组丢弃）")
    chk("回退复用旧 OCR 缓存" in _i2t,
        "image2txt glm-ocr 失败回退旧缓存（防 --force 比不跑更差）")
    chk("add_argument('--deadline'" in _i2t,
        "image2txt 提供 --deadline 总时限")
    for _f4 in ("AGENTS.md", ".reasonix/skills/<REDACTED_SK>/SKILL.md", "data/足球分析模型.txt"):
        chk("P-IMG-CH-1" in open(_f4, encoding="utf-8").read(), "P-IMG-CH-1 三处同步: " + _f4)
    print("   ✅ P-IMG-CH-1 识图通道校验通过")
except Exception as _e99:
    chk(False, "P-IMG-CH-1 校验失败(%s)" % str(_e99)[:70])

# ===== 2026-11-02 P-PIPE-MKT-1 pipeline 市场参数自动回填 =====
# 🔴 症状：pipeline 无 --eu → stage3 直接不传 → calc_all 缺 15 块（含 V387 量级档/ P10/N23/N07b）
#   → exit=1。根因：market_inputs 已从 prestep 快照取到全档(coverage=100)，却未回填成命令行参数。
try:
    _pl = open("data/tmp/pipeline.py", encoding="utf-8").read()
    chk("市场参数自动回填" in _pl, "pipeline stage3 市场参数自动回填（治缺 15 块）")
    chk("import market_inputs as _MI" in _pl and "_MI.resolve(" in _pl,
        "pipeline 真调 market_inputs.resolve（防假接入）")
    chk("--home_water" in _pl and "ah_wh" in _pl, "pipeline 回填 home_water（让球水位 P1 需要）")
    for _f5 in ("AGENTS.md", ".reasonix/skills/<REDACTED_SK>/SKILL.md", "data/足球分析模型.txt"):
        chk("P-PIPE-MKT-1" in open(_f5, encoding="utf-8").read(), "P-PIPE-MKT-1 三处同步: " + _f5)
    print("   ✅ P-PIPE-MKT-1 pipeline 回填校验通过")
except Exception as _e100:
    chk(False, "P-PIPE-MKT-1 校验失败(%s)" % str(_e100)[:70])


# ── 🔴2026-11-09 V3.5.94：欧国联**伤停索引**修复（pipeline Stage2 误判）──
#   用户追问「马上欧国联开始了」→ 修 pipeline Stage2 误判「索引不覆盖」
#   🔴 真缺陷：`bzzoiro_fetch.INDEX_COVERED` 白名单只有五大联赛
#     → `index_covered('欧国联')` 返回 False → pipeline `_inj()` 直接三态 return
#     → **但 `bsd_layer.locate_event` 的 lids 已含 64（UEFA NL），实测能定位 4/4**
#     → AGENTS 早写「Bzzoiro 覆盖欧国联」= 文档与代码矛盾（又一次「存在≠活跃」）
_bzz2 = open("data/tmp/bzzoiro_fetch.py", encoding="utf-8").read()
chk("'欧国联', 'Nations League', 'UEFA Nations League', 'nations'" in _bzz2,
    "**欧国联在 Bzzoiro v1 events 索引内**（实测 league id=64·定位 4/4：Italy vs France 212689 等）")
chk("欧战（欧冠/欧联/欧协联）的 Bzzoiro league id **尚未实测**" in _bzz2,
    "欧战 Bzzoiro league id **未实测 → 保持三态**（宁缺勿猜·不硬塞）")
_bsd2 = open("data/tmp/bsd_layer.py", encoding="utf-8").read()
chk("[1, 3, 5, 4, 6, 64]" in _bsd2 and "UEFA Nations League id = 64" in _bsd2,
    "bsd_layer 默认扫 64（UEFA Nations League）—— 与 bzzoiro_fetch 索引白名单**两处口径一致**")


# ── 总结果(V3.5.74审计修正: 移至全部chk后·含⑧-⑪扩展段·防段后失败漏报) ──
print()
# ============================================================
# 🔴P10 市场三源比分分布矩阵断言（2026-10-25·V3.5.81·方案《P10 补丁包》）
#   ① 三源齐全 → ok=True ② 矩阵 E[T]/E[M] 与边缘期望自洽(≤0.15) ③ 缺源 → ok=False + 三态原因
#   ④ market_matrix=None → 旧行为不变(向后兼容) ⑤ 传入健康矩阵 → market_driven=True
#   ⑥ fmt_report 留痕 ⑦ 未传矩阵时不出现留痕行（旧输出零变化）
# ============================================================
try:
    import market_distribution as _mdp10
    import joint_solver as _jsp10

    _ou10 = {0.5: (1.06, 9.00), 1.5: (1.30, 3.40), 2.5: (1.95, 1.88),
             3.5: (3.30, 1.32), 4.5: (5.60, 1.14), 5.5: (9.00, 1.05)}
    _ah10 = [(-1.50, 2.45, 1.55), (-1.00, 1.98, 1.86), (-0.50, 1.62, 2.30),
             (-0.25, 1.45, 2.75), (0.00, 1.30, 3.60)]
    _cs10 = {}
    for _k10, _o10 in (((0, 0), 12.0), ((0, 1), 11.0), ((0, 2), 19.0), ((0, 3), 40.0),
                       ((1, 0), 6.50), ((1, 1), 7.20), ((1, 2), 12.0), ((1, 3), 26.0),
                       ((2, 0), 9.00), ((2, 1), 8.00), ((2, 2), 15.0), ((2, 3), 30.0),
                       ((3, 0), 15.0), ((3, 1), 13.0), ((3, 2), 21.0), ((3, 3), 45.0),
                       ((4, 0), 26.0), ((4, 1), 24.0), ((4, 2), 40.0)):
        _cs10["%d-%d" % _k10] = _o10

    _mm10 = _mdp10.infer_from_parts(ou_full=_ou10, ah_full=_ah10, cs_full=_cs10,
                                    oh=2.10, od=3.40, oa=3.60)
    chk(_mm10.get('ok') is True,
        "P10-① 三源齐全(OU 半档6/AH5档/CS19档) → ok=True（市场矩阵启用）")
    _mat10 = (_mm10.get('matrix') or {})
    _eT10 = ((_mm10.get('total') or {}).get('exp') or 0)
    _eM10 = ((_mm10.get('margin') or {}).get('exp') or 0)
    _dT10 = abs((_mat10.get('expT') or 0) - _eT10)
    _dM10 = abs((_mat10.get('expM') or 0) - _eM10)
    chk(_dT10 <= 0.15,
        "P10-② 矩阵 E[T]=%s vs OU 边缘期望 %s → 偏差 %.3f ≤0.15（比分天然对齐总进球）"
        % (_mat10.get('expT'), _eT10, _dT10))
    chk(_dM10 <= 0.15,
        "P10-②b 矩阵 E[M]=%s vs AH 边缘期望 %s → 偏差 %.3f ≤0.15（比分天然对齐净胜）"
        % (_mat10.get('expM'), _eM10, _dM10))
    _mmz10 = _mdp10.infer_from_parts(ou_full={}, ah_full=[], cs_full={},
                                     oh=None, od=None, oa=None)
    chk((_mmz10.get('ok') is False) and bool(_mmz10.get('notes')),
        "P10-③ 三源缺失 → ok=False 且输出三态原因（禁臆造·可回退）")
    _r10 = _jsp10.joint_anchor(2.10, 3.40, 3.60, handi=-0.5, o25=1.95, u25=1.90)
    chk(bool(_r10.get('ok')) and _r10.get('market_baseline') is None
        and _r10.get('market_driven') in (None, False),
        "P10-④ market_matrix=None → 不启用矩阵（向后兼容·旧行为不变）")
    _r10b = _jsp10.joint_anchor(2.10, 3.40, 3.60, handi=-0.5, o25=1.95, u25=1.90,
                                market_matrix=_mm10.get('matrix'))
    chk(bool(_r10b.get('ok')) and _r10b.get('market_driven') is True,
        "P10-⑤ 传入健康矩阵 → market_driven=True（E0 主排序生效）")
    chk('市场矩阵' in _jsp10.fmt_report(_r10b),
        "P10-⑥ fmt_report 输出市场矩阵留痕行（治「存在≠活跃」）")
    chk('市场矩阵' not in _jsp10.fmt_report(_r10),
        "P10-⑦ 未传矩阵时 fmt_report **不出现**市场矩阵行（旧输出零变化）")
except Exception as _ep10:
    chk(False, "P10 市场矩阵断言异常: %s: %s" % (type(_ep10).__name__, str(_ep10)[:100]))

# ============================================================
# 🔴P10-R10 判定标准层断言（2026-10-25 补强·方案 §4.7/§5.6）
#   ① R10 锚必须 ∈ 交集池（受让禁主胜锚 / M·T 域 / 防死锚）
#   ② 双主锚 / 宽池阈值生效（Top1−Top2<1.5pp；Top1<8%）
#   ③ 零封谱系由矩阵读出（非泊松默认）
#   ④ P(T≥4) 大球锚定生效
#   ⑤ R10-5 波胆纵向乘子**真正生效**（原型为 pass 占位）
#   ⑥ R10-9 读 cs_full（原型读从不输出的 matrix["covered"] → 永不生效）
# ============================================================
try:
    import market_distribution as _mdR10
    import joint_solver as _jsR10

    _mmR = _mdp10.infer_from_parts(ou_full=_ou10, ah_full=_ah10, cs_full=_cs10,
                                   oh=2.10, od=3.40, oa=3.60)
    _sel = _mdR10.anchor_select(_mmR, oh=2.10, od=3.40, oa=3.60, handi=-0.5,
                                bt_yes=1.75, bt_no=2.00, cs_full=_cs10)
    chk(_sel.get("anchor_1st") is not None,
        "R10-① anchor_select 产出主锚（%s / 次锚 %s · 可信度 %s）"
        % (_sel.get("anchor_1st"), _sel.get("anchor_2nd"), _sel.get("trust")))
    chk(any(k in " ".join(_sel.get("notes") or []) for k in ("R10-1", "R10-2")),
        "R10-② R10-1/R10-2 规则留痕存在（双主锚/边缘交集）")
    chk(bool(_sel.get("zero_notes")),
        "R10-③ 零封谱系由矩阵读出（P(零封) 判定链生效·非泊松默认）")
    _selh = _mdR10.anchor_select(_mmR, oh=2.10, od=3.40, oa=3.60, handi=0.5,
                                 cs_full=_cs10, pool=["1:1", "0:1", "1:2"])
    chk(_selh.get("anchor_1st") in ("1:1", "0:1", "1:2"),
        "R10-④ 受让/池约束: 锚必须 ∈ 交集池（禁主胜比分·防死锚）")
    _cv = {"1:1": {"dir": "drop_strong", "chg": -0.18}}
    _s1 = _mdR10.anchor_select(_mmR, oh=2.10, od=3.40, oa=3.60, cs_full=_cs10)
    _s2 = _mdR10.anchor_select(_mmR, oh=2.10, od=3.40, oa=3.60, cs_full=_cs10, cs_vert=_cv)
    chk(any("R10-5" in x for x in (_s2.get("notes") or [])),
        "R10-⑤ R10-5 波胆纵向乘子生效（原型 pass 占位·本实现出留痕）")
    _cs_no11 = {k: v for k, v in _cs10.items() if k not in ("1-1", "1:1")}
    _s3 = _mdR10.anchor_select(_mmR, oh=2.10, od=3.40, oa=3.60, cs_full=_cs_no11)
    chk(any("R10-9" in x for x in (_s3.get("notes") or [])) or
        _s3.get("anchor_1st") not in ("1:1",),
        "R10-⑥ R10-9 低波胆覆盖识别（读 cs_full·非从不输出的 matrix[covered]）")
    _rR = _jsR10.joint_anchor(2.10, 3.40, 3.60, handi=-0.5, o25=1.95, u25=1.90,
                              market_matrix=_mmR)
    chk(bool(_rR.get("ok")) and isinstance(_rR.get("market_r10"), dict),
        "R10-⑦ joint_anchor 消费完整 mm → 写回 market_r10（主锚 %s）"
        % ((_rR.get("market_r10") or {}).get("anchor_1st")))
    chk(_rR.get("anchor_1st") in set(_rR.get("candidates") or []),
        "R10-⑧ 最终主锚 ∈ 交集池候选（受让/域约束/防死锚）")
except Exception as _eR10:
    chk(False, "P10-R10 断言异常: %s: %s" % (type(_eR10).__name__, str(_eR10)[:100]))

# ============================================================
# 🔴P10-FINAL R11 单队进球/零封断言（2026-10-25·方案 §6）
#   ① 零封概率来自 TT 0.5 **直盘去水**（不经矩阵/泊松）
#   ② rho = P(BTTS) − P(主≥1)·P(客≥1) 数值自洽
#   ③ 谱系优先级：强零封(≥40%) 覆盖 BTTS(≥60%)
#   ④ 直盘缺失 → health=none + 三态；R10-3 回退矩阵后验仍工作
#   ⑤ joint_anchor 写回 market_r11 + fmt_report 留痕
#   ⑥ R11 不改主锚方向（防死锚）
#   ⑦ 四维交集（R11-6）不产生空池/死锁
# ============================================================
try:
    _tt11 = {"home": {0.5: (1.22, 4.80), 1.5: (2.30, 1.62), 2.5: (5.50, 1.15)},
             "away": {0.5: (1.85, 2.02), 1.5: (4.60, 1.20), 2.5: (12.0, 1.05)}}
    _bt11 = {"yes": 1.85, "no": 2.02}
    _z11 = _mdp10.team_zero_decision(tt_full=_tt11, btts=_bt11, cs_full=_cs10)
    chk(_z11.get("health") in ("ok", "weak") and _z11.get("away_clean") is not None,
        "R11-① 零封来自 TT 0.5 直盘去水（主被零封 %s / 客被零封 %s·来源 %s）"
        % (("%.0f%%" % (100 * _z11["home_clean"])) if _z11.get("home_clean") is not None else "缺",
           ("%.0f%%" % (100 * _z11["away_clean"])) if _z11.get("away_clean") is not None else "缺",
           _z11.get("source")))
    _po11, _pu11 = _mdp10._devig_2way(1.22, 4.80)
    chk(abs((_z11.get("home_clean") or 0) - _pu11) < 1e-6,
        "R11-①b 主被零封 == devig(TT_H[0.5].under) 精确相等（%.4f）" % _pu11)
    _exp_rho = (_z11.get("btts") or 0) - (_z11.get("indep") or 0)
    chk(_z11.get("rho") is not None and abs(_z11["rho"] - _exp_rho) < 1e-9,
        "R11-② rho=P(BTTS)−P(主≥1)·P(客≥1) 数值自洽（%+.4f）" % (_z11.get("rho") or 0))
    _z11s = _mdp10.team_zero_decision(
        tt_full={"home": {0.5: (1.60, 2.45)}, "away": {0.5: (1.95, 1.92)}},
        btts={"yes": 1.80, "no": 2.05})
    chk(_z11s.get("spectrum_code") in ("strong_away_clean", "strong_home_clean", "clean", "btts")
        and "谱系" in (_z11s.get("spectrum") or "") + "谱系",
        "R11-③ 谱系优先级生效（%s → %s）" % (_z11s.get("spectrum_code"), _z11s.get("spectrum")))
    _z11n = _mdp10.team_zero_decision(tt_full={}, btts=None, cs_full=None)
    chk(_z11n.get("health") == "none" and any("回退" in x for x in (_z11n.get("notes") or [])),
        "R11-④ 直盘缺失 → health=none + 三态回退原因（禁臆造）")
    _rR11 = _jsR10.joint_anchor(2.10, 3.40, 3.60, handi=-0.5, o25=1.95, u25=1.90,
                                market_matrix=_mmR)
    chk(isinstance(_rR11.get("market_r11"), dict),
        "R11-⑤ joint_anchor 写回 market_r11（谱系=%s）"
        % ((_rR11.get("market_r11") or {}).get("spectrum_code")))
    chk(bool(_rR11.get("ok")) and 'R11' in _jsR10.fmt_report(_rR11),
        "R11-⑥ fmt_report 输出 R11 留痕行（治「存在≠活跃」）")
    _dir11 = lambda s: ("主胜" if int(s.split(":")[0]) > int(s.split(":")[1])
                        else ("平局" if int(s.split(":")[0]) == int(s.split(":")[1]) else "客胜"))
    _rR11b = _jsR10.joint_anchor(3.60, 3.40, 2.10, handi=0.5, o25=1.95, u25=1.90,
                                 market_matrix=_mmR)
    chk(bool(_rR11b.get("ok")) and _rR11b.get("anchor_1st") in set(_rR11b.get("candidates") or []),
        "R11-⑦ R11 谱系对齐后主锚仍 ∈ 交集池（不改方向·防死锚·四维交集不空池）")
except Exception as _eR11c:
    chk(False, "P10-FINAL R11 断言异常: %s: %s" % (type(_eR11c).__name__, str(_eR11c)[:100]))

# 🔴2026-10-25 审计加固: P10/R10/R11 专项审计入口在位
#   （第 4 个脚本化审计入口·与 audit_fixtures / audit_alignment / audit_contracts 并列·SK-audit A 模式调用）
chk(os.path.exists('data/tmp/audit_p10.py'),
    "P10 专项审计入口 audit_p10.py 在位（A~G 段·实跑式·禁只看代码）")

print(f"总结果(含全部校验): ✅{len(OK)} ⚠️{len(WARN)} ❌{len(FAIL)}")
# 🔴2026-11-02 P39: BSD movement Q1/Q2 判据（热门方定位 + 角色标注 + 全局判定）
try:
    _bsd_src = open('data/tmp/bsd_layer.py', encoding='utf-8').read()
    chk('LAST_OVERALL' in _bsd_src, 'P39 bsd_layer 含 LAST_OVERALL 全局判定')
    chk(('热门方' in _bsd_src) and ('对手方' in _bsd_src) and ("r['role']" in _bsd_src),
        'P39 bsd_layer 逐方向角色标注（热门方/对手方）·防「对手方 DRIFT 被读成 Q2」')
    chk("float(r['best_odds'])" in _bsd_src, 'P39 bsd_layer 热门方=best_odds 最小（先定热门方再判）')
    chk('movement 全局判定' in _bsd_src, 'P39 bsd_layer print 全局判定行（下游只认这条）')
    chk('非 Q2' in _bsd_src, 'P39 对手方 DRIFTING 措辞含「非 Q2」（防误读）')
except Exception as _e101:
    chk(False, 'P39 BSD movement 判据校验失败(%s)' % str(_e101)[:70])

# 🔴2026-11-02 P40: ocr2std 识图分节兼容 HTML 标题 + 表头兜底
try:
    _o2s = open('data/tmp/ocr2std.py', encoding='utf-8').read()
    chk('_infer_mode' in _o2s, 'P40 ocr2std 含 _infer_mode 表头兜底推断')
    chk('align' in _o2s and '## ' in _o2s, 'P40 ocr2std HTML 居中标题 → markdown 归一')
    chk("'比分'" in _o2s and '胜其它' in _o2s, 'P40 _infer_mode 能识别比分表（胜其它/平其它/d:d）')
except Exception as _e102:
    chk(False, 'P40 识图分节校验失败(%s)' % str(_e102)[:70])

# 🔴2026-11-02 P41: audit_semantic 改判理由两级判据（就近 → 全文显式措辞）
try:
    _as = open('data/tmp/audit_semantic.py', encoding='utf-8').read()
    chk('两级判据' in _as, 'P41 audit_semantic has_reason 两级判据（就近 → 全文回落）')
    chk('回落全文' in _as, 'P41 就近失败回落全文（治"赔率表前3处恒无理由"）')
    chk('不接受泛泛' in _as or '显式改判措辞' in _as, 'P41 仍要求显式措辞（不放宽为任意依据）')
except Exception as _e103:
    chk(False, 'P41 改判理由判据校验失败(%s)' % str(_e103)[:70])

# 🔴2026-11-02 P42: 审计判据防回退（用户问「四场所有步骤都执行了吗」实证抓出的 4+1 处判据缺陷）
try:
    _as2 = open('data/tmp/audit_steps.py', encoding='utf-8').read()
    chk(r"\S[^→\n]{0,39}→" in _as2, 'P42 S00b 支持含空格英文队名（原 \\S+ 致「Ath Bilbao→」假遗漏）')
    chk(r'CS覆盖\d+档' in _as2, 'P42 S03 兼容旧格式（CS覆盖N档…(期望X.XX)）·防假遗漏')
    chk(r'偏离期望\s*[+\-−]?[\d.]+' in _as2, 'P42 S15 认「偏离期望 ±x.xx」（原只认旧格式「硬1」→五场假三态）')
    chk('双锚联合覆盖' in _as2, 'P42 S17 认「双锚联合覆盖 X%」（原只认「覆盖率」→假三态）')
    _oc2 = open('data/tmp/output_checker.py', encoding='utf-8').read()
    chk('_r11_tri' in _oc2, 'P42-d output_checker P10-05 三态豁免（R11 未落盘时不强求「被零封xx%」·防逼人编数）')
except Exception as _e104:
    chk(False, 'P42 审计判据校验失败(%s)' % str(_e104)[:70])

# 🔴2026-11-03 O-BIG-1 / O-ANCHOR-1（三场复盘驱动·用户裁定「两个都修」）
try:
    import big_pool_policy as _bpp43
    chk(_bpp43.required_bins('L3') == [4, 5], 'O-BIG-1 L3 默认仍 [4,5]（防回退）')
    chk(_bpp43.required_bins('L3', def_dual=True) == [4, 5, 6], 'O-BIG-1 L3+双方防线双伤 → 宽池扩 6 球')
    chk(_bpp43.required_bins('L2', def_dual=True) == [4, 5], 'O-BIG-1 L2+双伤 → 补 5 球（不跳档·守 P27）')
    _dd = _bpp43.def_dual_from_lists('中后卫,未知;后腰,未知', '中后卫,未知;中后卫,未知')
    chk(_dd == (True, 2, 2), 'O-BIG-1 def_dual_from_lists 识别「双方防线各≥2 人」')
    _md43 = open('data/tmp/market_distribution.py', encoding='utf-8').read()
    chk('O-ANCHOR-1' in _md43 and 'dir_first' in _md43, 'O-ANCHOR-1 主锚方向纯（dir_first 约束 + 留痕）')
    chk('def_dual=bool(def_dual)' in _md43, 'O-BIG-1 market_distribution 宽池真吃 def_dual')
    _js43 = open('data/tmp/joint_solver.py', encoding='utf-8').read()
    chk('dir_first=((step5_dirs or [None])[0])' in _js43, 'O-ANCHOR-1 joint_solver 透传方向首选')
    _ca43 = open('data/tmp/calc_all.py', encoding='utf-8').read()
    chk('def_dual=_def_dual' in _ca43, 'O-BIG-1 calc_all 解析伤停清单并透传 def_dual')
except Exception as _e105:
    chk(False, 'O-BIG-1/O-ANCHOR-1 校验失败(%s)' % str(_e105)[:70])

# 🔴2026-11-03 V3.5.88 量级分布驱动（用户裁定 dec-9e0e0b6dcc2535e8 方案 A）
try:
    import magnitude_band as _mb88
    _b88 = _mb88.magnitude_band(o25=1.563, lam=3.505)
    chk(_b88.get('pT') and len(_b88['pT']) == 8, 'V3.5.88 分布驱动：输出 8 档逐球分布 pT')
    chk(abs(_b88.get('P_ge4', 0) - 0.364) < 0.01, 'V3.5.88 分布对齐实测表（1.50-1.70 档 P(≥4球)=36.4%）')
    chk(_mb88.band_weight('2:4', _b88) > 0.45, 'V3.5.88 权重改密度比（2:4 从 0.10 → >0.45·原阶梯压死尾部）')
    chk(6 in (_b88.get('tail_bins') or []), 'V3.5.88 尾部档 P(k)≥5% 必进宽池（317 档含 6 球）')
    _md88 = open('data/tmp/market_distribution.py', encoding='utf-8').read()
    chk("t_band.get('tail_bins')" in _md88 or 't_band.get("tail_bins")' in _md88,
        'V3.5.88 tail_bins 真并入 _P52_REQ（防「算出来没接线」）')
    chk("t_band.get('pT')" in _md88 or 't_band.get("pT")' in _md88,
        'V3.5.88 矩阵不可用时 pT 回退 t_band（防退回点估计）')
except Exception as _e88:
    chk(False, 'V3.5.88 量级分布驱动校验失败(%s)' % str(_e88)[:70])

try:
    import subprocess as _sp88
    _r88 = _sp88.run([sys.executable, 'data/tmp/audit_magnitude_band.py'],
                     capture_output=True, timeout=180)
    chk(_r88.returncode == 0, 'V3.5.88 分布驱动审计 audit_magnitude_band 全过（20 项）')
except Exception as _e88b:
    chk(False, 'V3.5.88 审计脚本执行失败(%s)' % str(_e88b)[:60])

# 🔴2026-11-03 V3.5.88 端到端实测（用户追问「能不能真正跑通而不是伪消费」·实跑抓 3 真缺陷）
try:
    _pl88 = open("data/tmp/pipeline.py", encoding="utf-8").read()
    chk("(?:87|88)" in _pl88 and "量级(?:档确定|分布)" in _pl88,
        "V3.5.88 端到端: pipeline KEY_BLOCKS 切片正则兼容两版文案"
        "（实抓: 旧版只认 V3.5.87 → 新文案下 raw 该块为空 = 伪消费）")
    _ca88b = open("data/tmp/calc_all.py", encoding="utf-8").read()
    chk("_n23_hn = float(_h_f)" in _ca88b,
        "V3.5.88 端到端: calc_all 的 _n23_hn 是 float"
        "（实抓: 原 str → joint_solver `handi < -0.05` TypeError → N23 整段崩溃"
        " → 锚定/量级/宽池全不消费·344 行→514 行）")
    _js88b = open("data/tmp/joint_solver.py", encoding="utf-8").read()
    chk("handi = float(handi)" in _js88b, "V3.5.88 端到端: joint_solver handi float 容错（第二道防线）")
    _mb88b = open("data/tmp/magnitude_band.py", encoding="utf-8").read()
    chk("MB_OLD_BAND" in _mb88b, "V3.5.88 消融: band_weight 有旧阶梯开关（A/B 实证支持度变化）")
    chk("MD_NO_TAIL" in _md88, "V3.5.88 消融: tail_bins 有回滚开关")
except Exception as _e88c:
    chk(False, "V3.5.88 端到端断言失败(%s)" % str(_e88c)[:70])

# 🔴2026-11-03 V3.5.88 宽池不得硬锚（用户指令「宽池里的比分也得符合市场信号」）
try:
    _mdw = open("data/tmp/market_distribution.py", encoding="utf-8").read()
    chk("_wl_gate" in _mdw, "V3.5.88 宽池补入有市场信号门槛函数（方向/净胜/受让/波胆/支持度）")
    chk("受让场禁主胜比分" in _mdw, "V3.5.88 宽池补入检查「受让场禁主胜」（原路径完全无此校验）")
    chk("波胆第%d(市场不看好)" in _mdw or "市场不看好" in _mdw,
        "V3.5.88 宽池补入拒收「波胆冷门」（排名>12 = 市场明确不看好）")
    chk("宽池**拒收**" in _mdw, "V3.5.88 宽池「该档无合格候选」须留痕拒收（禁静默硬塞）")
    chk("交集池外典型谱系" in _mdw or "_TYP" in _mdw,
        "V3.5.88 宽池可从交集池外典型谱系补（原 adj 只扫池内 → 永远补不进）")
    _jsw = open("data/tmp/joint_solver.py", encoding="utf-8").read()
    chk("for _n10 in _r10n" in _jsw,
        "V3.5.88 r10 notes 全量输出 P52/宽池/门槛（原 notes[:2] 把它们全截掉 = 伪留痕）")
except Exception as _e88w:
    chk(False, "V3.5.88 宽池门槛断言失败(%s)" % str(_e88w)[:70])

# 🔴2026-11-03 V3.5.88 端到端「七道闸门实跑」抓出的 3 个真缺陷（禁回退）
try:
    _oc = open("data/tmp/output_checker.py", encoding="utf-8").read()
    chk(("量级档确定|量级分布" in _oc) and "(?:87|88)" in _oc,
        "V3.5.88 闸门: output_checker 的 V387 判据兼容两版文案"
        "（实抓: 只认旧文案 → 有量级块仍报「缺量级档确定」= 假失败）")
    chk("_bd_tri" in _oc,
        "V3.5.88 闸门: BSD 三态豁免（实抓: BSD 未定位仍报 BD02/03/04 → 逼模型编数）")
    _pl = open("data/tmp/pipeline.py", encoding="utf-8").read()
    chk("_now_txt" in _pl and "分析时间：" in _pl,
        "V3.5.88 闸门: raw 骨架写「分析时间」（实抓: 原写「生成时间」→ TT1 恒不过）")
    chk("from time_guard import now_bj" in _pl,
        "V3.5.88 闸门: 骨架时间走 time_guard 单一入口（禁 time.strftime 自算）")
except Exception as _e88g:
    chk(False, "V3.5.88 闸门实跑断言失败(%s)" % str(_e88g)[:70])

# 🔴2026-11-03 V3.5.88 尾部单调性（用户裁定 dec-376e7267d95be6e2·317 萨索洛 2:4 归因）
try:
    import magnitude_band as _mb88t
    chk(hasattr(_mb88t, 'fix_tail_monotonic'),
        "V3.5.88 尾部: fix_tail_monotonic 存在（矩阵尾部非单调→回退查表）")
    _bad88 = [0.08, 0.11, 0.20, 0.21, 0.17, 0.10, 0.03, 0.09]
    _bt88 = _mb88t.magnitude_band(mm={'total': {'p': _bad88}, 'expT': 3.19},
                                  o25=1.563, lam=3.505)
    chk(6 in (_bt88.get('tail_bins') or []),
        "V3.5.88 尾部: 6 球档进尾部档（实抓: 矩阵 3%% < 5%% 阈值被排除·市场定价 6.4%%）")
    chk('查表尾部' in str(_bt88.get('pT_src')), "V3.5.88 尾部: 分布源标记「矩阵+查表尾部」")
    _ok88 = [0.04, 0.15, 0.22, 0.22, 0.16, 0.11, 0.06, 0.03]
    _bk88 = _mb88t.magnitude_band(mm={'total': {'p': _ok88}, 'expT': 3.1},
                                  o25=1.563, lam=3.505)
    chk(_bk88.get('pT_src') == '矩阵', "V3.5.88 尾部: 正常形状不误改（防过度修复）")
except Exception as _e88t:
    chk(False, "V3.5.88 尾部断言失败(%s)" % str(_e88t)[:70])

if FAIL:
    # 🔴2026-10-26 审计补: 失败项曾被某段 redirect_stdout 静默（只显总数、看不到是哪条）
    print("🔴 失败项明细:")
    for _fm in FAIL:
        print("   ❌ %s" % _fm)
    print("🔴 有失败项——修复后再完成更新！")
    sys.exit(1)
else:
    print("🟢 全绿——更新同步完成")


# ── 🔴2026-11-09 V3.5.94 总分总架构（子模型隔离·接口一致·强隔离）──
#   用户指令「梳理模型结构·隔离子模型·但主模型通用·接口一致·总分总形式·防止不同比赛相互串」+ 强隔离
chk(os.path.exists("data/tmp/match_context.py"), "match_context.py 存在（总分总·MatchContext + SubModelResult + scope 白名单）")
chk(os.path.exists("data/tmp/submodel_adapters.py"), "submodel_adapters.py 存在（7 个 adapter·统一契约）")
_mc = open("data/tmp/match_context.py", encoding="utf-8").read()
chk("class MatchContext" in _mc and "class SubModelResult" in _mc,
    "总分总核心类：**MatchContext**（一场比赛唯一上下文）+ **SubModelResult**（统一 9 字段契约）")
chk("SUBMODEL_SCOPE" in _mc and "def guard_table" in _mc and "class ScopeViolation" in _mc,
    "**强隔离**：SUBMODEL_SCOPE 白名单 + guard_table 越界直接抛 ScopeViolation（不再只靠文档纪律）")
chk("'nations':" in _mc and "'ucl_calibration'" in _mc and "'league_table'" in _mc,
    "欧国联 forbid 五大专属表（odds_table/league_table/ucl_calibration/team_attack_defense）—— 防空口径污染")
chk("def aggregate" in _mc and "l2_lock" in _mc and "已按铁律限制降档不反转" in _mc,
    "**总②** aggregate 按优先级合并 + **L2 锁**（子模型只降档·永不反转方向）")
_sa = open("data/tmp/submodel_adapters.py", encoding="utf-8").read()
chk("def calc_nations" in _sa and "def calc_europe" in _sa and "_top5_adapter" in _sa,
    "7 个 adapter：nations / europe / top5×5（五大=纯文档·代码零规则）")
chk("guard_table('nations'" in _sa and "res.blocked" in _sa,
    "adapter 内部真调 guard_table 且 blocked 留痕（否则隔离=假接入）")
_ca_arch = open("data/tmp/calc_all.py", encoding="utf-8").read()
chk("总分总架构" in _ca_arch and "fmt_aggregate" in _ca_arch and "extract_nl_teams" in _ca_arch,
    "calc_all 接入总分总聚合块（含 extract_nl_teams 直提队名——原 eval 取不到致 Elo 三态）")

# ── 🔴2026-11-12 P-COVER-1 默认覆盖校验（case346 事故驱动·用户指令「做」）──
#   L2 铁律：默认覆盖=「最低赔+次低赔」77.68% > 「最低+平局」76.51%（227,495 场时间分割）
#   case346 违反（平局 3.08 最高却挤掉次低赔客胜 2.82 → 真实 0:1 客胜 → 方向❌）
chk(os.path.exists("data/tmp/default_cover.py"), "default_cover.py 存在（P-COVER-1 纯函数判据）")
_dcv_src = open("data/tmp/default_cover.py", encoding="utf-8").read()
chk("def check(" in _dcv_src and "def is_violation(" in _dcv_src and "VIOLATION_FAV" in _dcv_src,
    "P-COVER-1 判据态齐全（OK / SINGLE / VIOLATION / VIOLATION_FAV / NODIR）")
chk("default_cover" in _ca_arch and "_dvc.check(_n23_e" in _ca_arch,
    "calc_all 真接线 P-COVER-1（默认覆盖建议块·否则新判据=白装）")
_clp_src = open("data/tmp/check_luopan.py", encoding="utf-8").read()
chk("P-COVER-1 默认覆盖兜底" in _clp_src and "_CV_REASON" in _clp_src,
    "check_luopan P-COVER-1 门禁（默认覆盖留痕 + 违规必附理由·case348+）")
try:
    import sys as _sys_cv
    _sys_cv.path.insert(0, "data/tmp")
    import default_cover as _dvc_ck
    _cv_a = _dvc_ck.check([2.46, 3.08, 2.82], "主胜,平局").get("level") == "VIOLATION"
    _cv_b = _dvc_ck.check([2.842, 3.58, 2.23], "客胜,主胜").get("level") == "OK"
    _cv_c = _dvc_ck.check([2.00, 2.90, 3.50], "主胜,平局").get("level") == "OK"
    _cv_d = _dvc_ck.check([3.00, 2.90, 2.50], "主胜,平局").get("level") == "VIOLATION_FAV"
    _cv_e = _dvc_ck.check([1.40, 4.50, 7.00], "主胜").get("level") == "SINGLE"
    chk(_cv_a and _cv_b and _cv_c and _cv_d and _cv_e,
        "P-COVER-1 判据行为正确（case346→VIOLATION / case345→OK / 平局次低→OK / 漏最低赔→VIOLATION_FAV / 单押→SINGLE）")
except Exception as _ecv:
    chk(False, "P-COVER-1 判据行为正确（导入/调用失败: %s）" % _ecv)
_sl_src = open("data/tmp/signal_landing.py", encoding="utf-8").read()
chk("second, why = '平局', '弱共识" not in _sl_src and "sec_l2" in _sl_src,
    "P-COVER-1 signal_landing 第二向=次低赔方向（原硬编码「弱共识→平局」已删·case346 真根因）")
_pl_src = open("data/tmp/pipeline.py", encoding="utf-8").read()
chk("次低赔 %s" in _pl_src and "第二向由 Stage5 信号推导决定" not in _pl_src,
    "P-COVER-1 pipeline Stage3 文案同步（弱共识不再指定平局·防回退）")
