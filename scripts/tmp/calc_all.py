# calc_all.py — 全覆盖预计算聚合器 + 必核清单生成器（2026-09-02·步骤遗失结构性根除·支柱A）
# 用法: python calc_all.py <竞彩txt路径> [联赛key] [--eu 主,平,客] [--handi 盘口] [--o25 大小球赔率] [--u25 U2.5赔率]
#        [--home_water 主水] [--elo 主队ELO差] [--inj_h 主伤停分] [--inj_a 客伤停分] [--net 启用网络源]
#        🔴2026-09-21 新增: [--max 方向最高价] [--max_o25 O2.5最高价] [--max_u25 U2.5最高价] → 资金盘 P0-1 跨机构 spread
# 原理: 一次性输出全部确定性计算(calc_match管道) + 脚本生成的必核清单(非LLM自我清单·防自我遗漏)
# 输出: 完整预计算报告 + [必核清单] 段——LLM 照清单逐项消费·缺项=输出不完整

import io, sys, os, subprocess, re, json
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)  # 🔴2026-09-15合并(源自workbuddy): 防Windows管道块缓冲/丢行

# ── 必核清单（脚本硬编码·随模型规则更新·替代LLM自我清单）──
CHECKLIST = [
    # (编号, 必核项, 触发条件(脚本判定·None=必做), 数据来源/脚本)
    ('C01', 'Step1 去抽水+校准+方向差距+skew', None, 'calc_match'),
    ('C02', 'Step1 赔率档查表(odds_table·H/D/A实际率)', None, 'odds_table.json'),
    ('C03', 'Step1 凯利+反抽水比(>1.30触发F1)', None, 'calc_match'),
    ('C04', 'V1 双源赔率变动+形态学', None, 'calc_match+欧盘'),
    ('C05', 'V2 诱阻盘四步(让球变动/水位交叉/半全场/P0-P1)', None, 'calc_match'),
    ('C06', 'V3 水位联动(盘口未变前提)', None, '欧盘spread'),
    ('C07', 'V4 半全场传导+半场三元', None, 'calc_match'),
    ('C08', 'V5+V5+ 跨市场分歧+反向校验', None, 'calc_match --eu'),
    ('C09', 'V6 盘口联动(赛前60-90min临场·无→标不触发)', None, '欧盘临场'),
    ('C10', 'Step3 场景44/45/46(+欧战六项核查表·欧战才完整)', '欧战', 'SL-europe-db'),
    ('C11', 'Step3.5 情境F1-F7', None, 'calc_match反抽水'),
    ('C12', 'Step4 修正26基本面ABCDE', None, '基本面'),
    ('C13', 'Step4.5 联赛子模型(五大联赛才触发)', '五大联赛', 'SK-league-*'),
    ('C14', 'Step5 方向判定D1-D4+修正53 S1-S7', None, 'calc_match+calc_v3572'),
    ('C15', '🔴欧亚综合: direction_full(handi校正·诱盘信号)', None, 'calc_v3572'),
    ('C16', '🔴诱阻识别: match_classifier+intent(庄家主导才)', '总分>=3', 'calc_v3572'),
    ('C17', 'Step6 大球深度(O2.5→档位·goal_bin_probs)', None, 'calc_v3572'),
    ('C18', 'Step7 泊松λ反推+比分谱系+查表+融合', None, 'calc_poisson'),
    ('C19', 'Step7 净胜档多档候选(margin_candidates_pool)', None, 'calc_match'),
    ('C20', 'Step7 市场一致性检查+条件化锚定两步', None, 'calc_match'),
    ('C21', 'Step7 盈亏矩阵+资金流+主锚次锚+停止分支', None, 'CS赔率'),
    ('C22', 'Step8 总进球概率化+凯利联动', None, 'calc_match'),
    ('C23', '伤停(Bzzoiro 结构化·源B8·唯一源·三态)', None, 'bzzoiro_fetch'),
    ('C24', '⛔api-football已停用(2026-10-06)→替代: the-odds-api赔率/Bing News伤停/Odds-API定位', '全部', 'the_odds_api_fetch+Bing News'),
    ('C25', 'footballcharts基本面(λ/校准/蒙特卡洛)·⛔源已废弃(2026-09-15·域名DNS全失效)→降级 understat_xg+SK-xg-depth+联赛校准(按“无数据”三态标注·不算遗漏)', '五大联赛', 'SL-footballcharts-fetch'),
    ('C26', 'clubelo ELO(修正41一致性)', '五大联赛+欧战', 'SL-elo-fetch'),
    ('C27', 'xG深度比分判定(understat·防泄露)', '五大联赛', 'SK-xg-depth'),
    ('C28', '比分命中口径标注(主锚/次锚·第3/4候选不算)', None, '口径铁律'),
    ('C29', '自检表22项逐项证据', None, 'checklist'),
    ('C30', '落盘: case_write add/review + raw七节 + check_luopan', None, 'case_write'),
    # 🔴2026-09-27 审计补（根因: 清单缺 Step0 的 4 个源 → LLM 照清单执行必漏·case209 实证漏 B1+H2H）
    ('C31', 'Step0① txt归一化(txt_normalize·第一动作·禁手工转换喂下游)', None, 'txt_normalize'),
    ('C32', 'Step0② Odds-API欧盘全市场(B1·🔴主数据源: ML/Spread亚盘水位/Totals/CS/BTTS/HT-FT/DC)', None, 'Odds-API'),
    ('C33', 'Step0⑤ H2H历史交锋(fixture_cache/SL-history-analyzer·无数据三态)', None, 'SL-history-analyzer'),
    ('C34', 'Step0 B7 the-odds-api机构21家(合并去水+跨机构分歧·market_consensus)', None, 'market_consensus'),
]

# 🔴统一联赛归一化（2026-09-15 审计 P0 修复·三套命名空间统一）——
# 原 _LMAP 只认 E0/SP1/I1/D1/F1/ec，传 epl/laliga/seriea/bundesliga/ligue1 等常见别名时
# 静默降级为「非五大」→ C13 联赛子模型 / C25 footballcharts / C27 xG 三大模块不触发
# （实测对比: 同一场英超 epl→[不触发·非五大] / E0→[必做]，已证实）。
_LG_ALIAS = {
    # 中文标准名（透传）
    '英超': '英超', '西甲': '西甲', '意甲': '意甲', '德甲': '德甲', '法甲': '法甲',
    '欧冠': '欧冠', '欧联': '欧联', '欧协联': '欧协联', '英冠': '英冠', '日职': '日职',
    # 英文代码（Matches.csv 口径）
    'E0': '英超', 'SP1': '西甲', 'I1': '意甲', 'D1': '德甲', 'F1': '法甲',
    # 英文别名（常见输入写法·大小写不敏感）
    'epl': '英超', 'premier': '英超', 'premierleague': '英超',
    'laliga': '西甲', 'liga': '西甲',
    'seriea': '意甲',
    'bundesliga': '德甲', 'bundes': '德甲',
    'ligue1': '法甲',
    'championship': '英冠', 'jleague': '日职', 'j1': '日职',
    # 欧战别名
    'ec': '欧冠', 'ucl': '欧冠', 'champions': '欧冠', 'championsleague': '欧冠',
    'el': '欧联', 'uel': '欧联', 'europa': '欧联', 'europaleague': '欧联',
    'uecl': '欧协联', 'conference': '欧协联', 'conferenceleague': '欧协联',
}


def norm_league(x):
    """联赛归一化 → 中文标准名（2026-09-15审计P0修复·接受 中文名/英文代码/英文别名·大小写与分隔符不敏感）"""
    if not x:
        return x
    s = str(x).strip()
    return _LG_ALIAS.get(s) or _LG_ALIAS.get(s.lower().replace(' ', '').replace('-', ''), s)


def gen_checklist(league, eu=None, handi=None, o25=None, is_europe=False, is_top5=False):
    """脚本生成必核清单(附数据状态·LLM照单逐项消费)"""
    lines = ['', '=' * 70, '【必核清单·脚本生成(2026-09-02·防自我遗漏·LLM逐项执行不可跳过)】', '=' * 70]
    for cid, item, cond, src in CHECKLIST:
        if cond == '欧战' and not is_europe:
            lines.append('  %s %-40s [不触发·非欧战]' % (cid, item))
        elif cond == '五大联赛' and not is_top5:
            lines.append('  %s %-40s [不触发·非五大]' % (cid, item))
        else:
            lines.append('  %s %-40s [必做·源:%s]' % (cid, item, src))
    lines.append('  🔴执行纪律: 逐项执行·每项输出数值证据·条件层三态(触发/不触发(原因)/无数据(原因))·无证据=未执行=禁止通过')
    return '\n'.join(lines)

def _extract_cs_bqc(txt_path):
    """提取竞彩txt比分盘/半全场末盘串(评审P0接入·live引擎输入)·多时点取末值
    支持三格式: A胜胜= 等号 / B'发布时间,胜胜'表头 / C纯逗号无表头(2026-09-10·错误13)
    🔴2026-09-07修复: 半全场兼容逗号表头格式——原仅支持 胜胜= 格式致ht源未激活"""
    import re as _re
    try:
        s = open(txt_path, encoding='utf-8').read()
    except Exception:
        return None, None
    cs = {}
    for m in _re.finditer(r'(\d+:\d+)=([\d.]+)', s):
        cs[m.group(1)] = float(m.group(2))
    # 🔴2026-09-15审计P1修复: CS 补齐逗号表头格式(格式B)——原仅支持 `1:0=` 等号格式，
    # 致逗号表头txt 的 cs={} → live引擎丢失CS源(0.20权重)·Elche vs 皇马实测复现
    if not cs:
        mhc = _re.search(r'发布时间,1:0,2:0', s)
        if mhc:
            _hseg = s[mhc.start():]
            _hnext = _hseg.find('【', 5)
            if _hnext > 0: _hseg = _hseg[:_hnext]
            _hkeys = _hseg.split('\n', 1)[0].split(',')[1:]  # 去掉"发布时间"表头列
            _crows = _re.findall(r'^(\d{4}-\d{2}-\d{2} [\d:]+),(.+)$', _hseg, _re.M)
            if _crows and _hkeys:
                _last = _crows[-1][1].split(',')
                for _i, _k in enumerate(_hkeys):
                    if _i < len(_last) and _re.match(r'^\d+:\d+$', _k.strip()):
                        try: cs[_k.strip()] = float(_last[_i])
                        except Exception: pass
    # 半全场: 优先 胜胜= 格式·否则逗号表头格式(取末数据行)
    bq = {}
    for m in _re.finditer(r'(胜胜|胜平|胜负|平胜|平平|平负|负胜|负平|负负)=([\d.]+)', s):
        bq[m.group(1)] = float(m.group(2))
    if not bq:
        mh = _re.search(r'发布时间,胜胜,胜平,胜负,平胜,平平,平负,负胜,负平,负负', s)
        if mh:
            keys = ['胜胜', '胜平', '胜负', '平胜', '平平', '平负', '负胜', '负平', '负负']
            seg = s[mh.start():]
            # 🔴2026-09-15审计P0修复: 原 seg 未截断到下一节 → seg_rows[-1] 取到【比分固定奖金】段末行
            # → bq 全错(实测 Elche vs 皇马 bq = CS值 50/90/35/300/100/70/500/300/300)·污染 live引擎 ht源(0.24权重)
            _nxt = seg.find('【', 5)
            if _nxt > 0: seg = seg[:_nxt]
            seg_rows = _re.findall(r'^(\d{4}-\d{2}-\d{2} [\d:]+),(.+)$', seg, _re.M)
            if seg_rows:
                last = seg_rows[-1][1].split(',')
                if len(last) >= 9:
                    for i, k in enumerate(keys):
                        try: bq[k] = float(last[i])
                        except Exception: pass
    # 🔴2026-09-10格式C: 纯逗号无表头数据行(原始粘贴竞彩txt·【半全场】段后时间行直接9值)·映射按固定顺序
    if not bq:
        keys = ['胜胜', '胜平', '胜负', '平胜', '平平', '平负', '负胜', '负平', '负负']
        segm = _re.search(r'【半全场胜平负固定奖金】\s*\n', s)
        if segm:
            _seg_rest = s[segm.end():]
            _nseg = _seg_rest.find('【')
            if _nseg > 0: _seg_rest = _seg_rest[:_nseg]
            seg_lines = [l for l in _seg_rest.split('\n') if l.strip() and _re.match(r'^\d{4}-\d{2}-\d{2}', l)]
            if seg_lines:
                last = seg_lines[-1].split(',')
                if len(last) >= 10:  # 时间+9值
                    for i, k in enumerate(keys):
                        try: bq[k] = float(last[i + 1])
                        except Exception: pass
    cs_s = ','.join('%s=%.2f' % (k, v) for k, v in cs.items()) if cs else None
    bq_s = ','.join('%s=%.2f' % (k, v) for k, v in bq.items()) if bq else None
    return cs_s, bq_s


def _merge_score_candidates(live_cands, handi_cands, handi_weight=0.40):
    """融合live引擎top10与让球分层候选池(2026-09-10·错误5·深盘场候选消费)"""
    if not handi_cands: return live_cands or []
    if not live_cands: return handi_cands
    merged = {}
    for c in live_cands:
        sc = c.get('score', c.get('s', ''))
        p = c.get('prob', c.get('p', c.get('weight', 0))) or 0
        merged[sc] = merged.get(sc, 0) + p * (1 - handi_weight)
    for c in handi_cands:
        sc = c.get('score', '')
        w = c.get('weight', 0) or 0
        merged[sc] = merged.get(sc, 0) + w * handi_weight
    res = [{'score': k, 'weight': v} for k, v in sorted(merged.items(), key=lambda x: -x[1])]
    tot = sum(c['weight'] for c in res)
    if tot > 0:
        for c in res: c['weight'] = round(c['weight'] / tot, 3)
    return res[:5]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    txt_path = sys.argv[1]
    league = sys.argv[2] if len(sys.argv) > 2 else None
    # 🔴2026-11-01 P2b 时间上下文前置（time_guard）——calc_all 是所有完整分析的必经路径，
    #    只在 pipeline Stage0 打印 = 只覆盖一条路径（手工跑 calc_all/PreStep/复盘全漏）
    if '--no-time' not in sys.argv:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import time_guard as _tg
            _ko = None
            for _i, _a in enumerate(sys.argv):
                if _a == '--kickoff' and _i + 1 < len(sys.argv):
                    _ko = sys.argv[_i + 1]
            _tg.print_context(kickoff=_ko, sweep_data=True)
        except Exception as _te:
            print('⚪ time_guard 时间上下文不可用（三态·不阻断）: %s' % str(_te)[:70])
    # ⚡ 学习成果提示(learned_rules.json·2026-09-10·提示级不改变任何计算/判定)
    try:
        _lf = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'learned_rules.json')
        if os.path.exists(_lf):
            import json as _lj
            _lr = _lj.load(open(_lf, encoding='utf-8'))
            _hints = [(t, e.get('rule', '')) for t, e in _lr.items() if e.get('status') in ('提示', '待回测验证', '已固化')]
            if _hints:
                print('=' * 70)
                print('⚡ 学习成果提示(历史复盘自动累积·仅提示·判定权在模型)')
                for _t, _r in _hints:
                    print('  [%s] %s' % (_t, _r))
                print('  → 状态: 提示级=复发累积; 待批量回测验证=达门槛; 已固化=回测验证通过')
    except Exception as _le:
        print('  ⚠️学习提示读取失败:', str(_le)[:60])
    # ⚡ L3 误差规则 + L4 CBR + L1 观察（2026-09-11接线·原本定义未调用=存在≠活跃修复）
    try:
        _old2 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'online_learning')
        if os.path.isdir(_old2):
            import sys as _s3
            _s3.path.insert(0, _old2)
            import json as _jh
            _tf2 = None
            try:
                import txt_features as _tf2m
                _tf2 = _tf2m
            except Exception:
                pass
            _feat2 = {}
            if _tf2:
                try:
                    _feat2, _ = _tf2.extract(txt_path)
                except Exception:
                    _feat2 = {}
            if _feat2:
                try:
                    import error_miner as _em
                    _rs = _em.rules_for(_feat2)
                    if _rs:
                        print('  ⚡ L3 误差规则命中(%d 条·仅提示): %s' % (
                            len(_rs), '; '.join('%s %s mag=%.2f conf=%.2f' % (
                                r['type'], r['action'], r['magnitude'], r['confidence']) for r in _rs[:3])))
                    _cbr = _em.cbr_predict(_feat2)
                    if _cbr.get('enabled'):
                        _p = _cbr.get('direction_probs') or {}
                        print('  ⚡ L4 CBR 案例辅助(%d 例·权重%.0f%%·仅提示): 主%.0f%% 平%.0f%% 客%.0f%%%s' % (
                            _cbr['n_cases'], _cbr['weight'] * 100,
                            (_p.get(1, 0)) * 100, (_p.get(0, 0)) * 100, (_p.get(2, 0)) * 100,
                            ' ⚠️相似案例常高估主胜' if _cbr.get('error_warning') else ''))
                    else:
                        print('  ⚡ L4 CBR 未启用(案例 %d < 10·冷启动)' % _cbr.get('n_cases', 0))
                except Exception as _em2:
                    print('  ⚠️L3/L4 提示失败:', str(_em2)[:60])
                try:
                    import river_models as _rm
                    _m2 = _rm.load_models()
                    _pv = _rm.predict(_m2, _feat2)
                    if _pv.get('direction_probs'):
                        _dp = _pv['direction_probs']
                        # 🔴2026-09-30 裁决（L1 泄露专项）: L1 已 rejected_leak
                        #   原打印「主97% 平0% 客3%」是**被污染的模型**输出（数值爆炸后的饱和值）·
                        #   且其启用依据(+0.68pp)证实为数据泄露 → 不再打印误导性数字
                        _g0 = {}
                        try:
                            _gp0 = os.path.join(_old2, 'state', 'gate.json')
                            if os.path.exists(_gp0):
                                _g0 = json.load(open(_gp0, encoding='utf-8')).get('L1_online_ml', {})
                        except Exception:
                            _g0 = {}
                        if (not _g0.get('enabled', False)) or _g0.get('status') in ('rejected_leak', 'degraded'):
                            print('  ⚫ L1 在线ML: 已否决(%s·数据泄露裁决 2026-09-30) → 权重 0·不参与融合' % _g0.get('status', 'unknown'))
                            print('     依据: 赛前可得特征下增益 +0.01pp(≈0) · 融合监测 n=48 融合21=基准21 · 详见 gate.json / validate_fusion.py 作废声明')
                        else:
                            print('  ⚡ L1 在线ML(第6源): 主%.0f%% 平%.0f%% 客%.0f%% | 进球λ≈%s' % (
                                _dp.get(1, 0) * 100, _dp.get(0, 0) * 100, _dp.get(2, 0) * 100, _pv.get('goals')))
                        # 🔴学习结果接入预测(2026-09-11·融合·含门禁+防噪音影响门槛)
                        _l1_degen = False
                        try:
                            _gate = {}
                            _gp = os.path.join(_old2, 'state', 'gate.json')
                            if os.path.exists(_gp):
                                _gate = json.load(open(_gp, encoding='utf-8')).get('L1_online_ml', {})
                            _w = float(_gate.get('weight', 0.10)) if _gate.get('enabled', True) else 0.0
                            if _gate.get('status') == 'degraded':
                                _w = 0.0
                            # 🔴2026-09-16 全面审计(L1 退化守卫·P1): 在线ML 实测饱和退化
                            #   (max>0.95 / min<1e-6 / 平局恒 0) → 强制权重 0·不参与融合
                            #   否则饱和输出会按权重 0.10 混入 → 把弱共识场硬推成强方向
                            if (max(_dp.values()) > 0.95) or (min(_dp.values()) < 1e-6):
                                print('  🔴L1 退化守卫: 输出饱和(max=%.3f/min=%.6f) → 权重强制 0·不参与融合'
                                      % (max(_dp.values()), min(_dp.values())))
                                _w = 0.0
                                _l1_degen = True
                            _mk = None
                            _mk_src = ''
                            _eu_arg = sys.argv[sys.argv.index('--eu') + 1] if '--eu' in sys.argv else None
                            if _eu_arg:
                                try:
                                    _e3 = [float(x) for x in _eu_arg.split(',')]
                                    _inv = {1: 1 / _e3[0], 0: 1 / _e3[1], 2: 1 / _e3[2]}
                                    _tt = sum(_inv.values())
                                    _mk = {k: v / _tt for k, v in _inv.items()}
                                    _mk_src = '欧盘--eu'
                                except Exception:
                                    _mk = None
                            # 🔴2026-09-11 修复(P1-2): 未传 --eu 时用竞彩 txt 末盘去水（自动·不依赖参数）
                            if _mk is None:
                                _oh5, _od5, _oa5 = (_feat2.get('home_odds'), _feat2.get('draw_odds'), _feat2.get('away_odds'))
                                if _oh5 and _od5 and _oa5:
                                    try:
                                        _inv = {1: 1 / float(_oh5), 0: 1 / float(_od5), 2: 1 / float(_oa5)}
                                        _tt = sum(_inv.values())
                                        _mk = {k: v / _tt for k, v in _inv.items()}
                                        _mk_src = '竞彩txt去水'
                                        # 🔴V3.5.80 P9 噪音隔离: 竞彩概率源过散户偏差校正
                                        #   （热捧 −2pp·其余 +1pp·仅竞彩源生效·欧亚不校正·待回测校准）
                                        try:
                                            from jc_euro_bridge import retail_correction as _rc9
                                            _nl9 = []
                                            _mk = _rc9(_mk, '竞彩', _nl9)
                                            _mk_src = '竞彩txt去水(散户校正)'
                                            for _x9 in _nl9:
                                                print('  ' + _x9)
                                        except Exception:
                                            pass
                                    except Exception:
                                        _mk = None
                            if _mk and (_w > 0 or _l1_degen):
                                # 🔴2026-09-16 防过拟合/降噪: 融合「进入判定」需**独立门禁**(默认关·可回滚)
                                #   依据: 融合监测 n=22 → 融合命中8 = 基准命中8(**无增益**);
                                #   且 L1 已 degraded → 融合=市场·无新增信息 → 只提示不进入判定
                                try:
                                    _fdec_gate = json.load(open(os.path.join(_old2, 'state', 'gate.json'), encoding='utf-8')).get('L1_fusion_in_decision', {})
                                except Exception:
                                    _fdec_gate = {}
                                _fdec = bool(_fdec_gate.get('enabled')) and (_w > 0)
                                _fu = {k: _mk[k] * (1 - _w) + _dp.get(k, 0) * _w for k in (0, 1, 2)}
                                _fm = max(_fu, key=_fu.get)
                                _mm = max(_mk, key=_mk.get)
                                _lab = {0: '平', 1: '主胜', 2: '客胜'}
                                _dpp = (_fu[_fm] - _mk[_mm]) * 100
                                print('    🔴融合方向概率(市场%.2f+在线ML%.2f·门禁=%s): 主%.1f%% 平%.1f%% 客%.1f%% → 融合倾向 %s' % (
                                    1 - _w, _w, ('L1退化·权重0(仅记录)' if _l1_degen else _gate.get('status', 'active')),
                                    _fu[1] * 100, _fu[0] * 100, _fu[2] * 100, _lab[_fm]))
                                _mk_gap = (_mk[_mm] - sorted(_mk.values())[-2]) * 100 if len(_mk) == 3 else 0
                                _mk_top = _mk[_mm] * 100
                                if not _fdec:
                                    _why = ('L1 未参与(权重0·退化/降级)' if _w <= 0
                                            else '门禁 L1_fusion_in_decision=关闭(未通过独立回测门禁)')
                                    print('    → 🔴融合**仅提示·不进入判定**: %s → 判定权归【市场+盘口+基本面】(防过拟合/噪声·2026-09-16)' % _why)
                                elif _fm == _mm:
                                    print('    → 融合与市场同向(差%+.1fpp·源=%s)·不改方向建议' % (_dpp, _mk_src))
                                elif abs(_dpp) > 5:
                                    if _mk_top < 45:
                                        print('    → 🔴🔴学习成果进入判定: 市场弱方向(最高%.1f%%<45%%)且融合异向差%.1fpp>5pp → **「%s」进入主方向判定（列为并列主方向）**（门禁已开·弱档+0.99~2.43pp）' % (
                                            _mk_top, abs(_dpp), _lab[_fm]))
                                    else:
                                        print('    → ⚠️融合与市场异向且差 %.1fpp>5pp·市场强方向(%.1f%%≥45%%): 仅置信度降1档(**不参与判定**·强档净优势=0)' % (
                                            abs(_dpp), _mk_top))
                                else:
                                    print('    → 融合与市场异向但差 %.1fpp≤5pp: 视作噪声·不调整' % abs(_dpp))
                                if _fdec and _fm == _mm and _mk_top < 45:
                                    print('    → 🔴学习成果进入判定: 市场弱方向(%.1f%%<45%%)·融合同向强化 → **采纳融合概率作为方向判定依据之一**（门禁已开·弱档优势+0.99~2.43pp）' % _mk_top)
                            elif _w == 0:
                                print('    → 门禁未启用/已降级(权重0)·仅记录不参与融合')
                            else:
                                print('    → 无欧盘去水概率·未做融合(需 --eu 参数)')
                        except Exception as _fe:
                            print('    ⚠️融合计算失败:', str(_fe)[:60])
                except Exception:
                    pass
    except Exception as _l3:
        print('  ⚠️L3/L4/L1 接线失败:', str(_l3)[:60])
    # 📄 预测日志(2026-09-11·分析时自动存特征 → 赛果时 learn_from_result --from-log 回溯)
    try:
        import sys as _sys2
        _oldir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'online_learning')
        if os.path.isdir(_oldir):
            _sys2.path.insert(0, _oldir)
            try:
                import data_bridge as _db
                # 🔴2026-09-11: 离线模式（快·保证源状态写入）·网络源仅记录 skipped
                # 🔴2026-09-14 修复: 新增 --net 开关 —— **完整分析必须传 --net**，否则网络源
                #   (clubelo ELO/xg/h2h/news/euro_odds) 全部 skipped → prediction_log（api-football 已停用 2026-10-06）
                #   仅 1/8 源(27键/18非空) → 学习模块特征残缺。传 --net 后 3-4/8 源(32-37键)。
                _netflag = ('--net' in sys.argv)
                # 🔴2026-09-14 修复: 原用 _league_cn（392行才定义）→ UnboundLocalError → 每次静默降级 txt(1/8源)
                _lcn = norm_league(league)
                # 🔴2026-09-30 审计修复（P2 接线）：score_prior.scope_check / scope_for_league
                #   原【无任何消费端】= 孤岛（存在≠活跃）→ 在此真实调用：按赛事识别作用域并输出
                #   use/ref/block 判定，替代原「12 行文字超域清单」（靠 LLM 记忆）
                try:
                    import os as _os2, sys as _sys2
                    _spd = _os2.path.dirname(_os2.path.abspath(__file__))
                    if _spd not in _sys2.path:
                        _sys2.path.insert(0, _spd)
                    from score_prior import scope_for_league as _sfl, scope_check as _sck
                    _scope = _sfl(None, league) or _sfl(None, _lcn)
                    if _scope:
                        print('  🔴【作用域开关】%s（scope_registry.json·超域代码化）:' % _scope)
                        for _k in ('step6_tiers', 'score_depth_table', 'fair_edge(R10)', 'prior(R2)', 'haf'):
                            print('     %-20s → %-5s' % (_k, _sck(_scope, _k)))
                    else:
                        print('  🔴【作用域开关】⚪ 未识别（league=%s）→ 默认 ref（保守）' % league)
                except Exception as _se:
                    print('  🔴【作用域开关】⚠️ 不可用: %s' % str(_se)[:60])
                _br = _db.collect(txt_path, _lcn, net=_netflag)
                _feat = _br.get('features') or {}
                _diag = {'detail': (_br.get('rich') or {}).get('txt_detail', {}),
                         'sources': _br.get('status', {}), 'completeness': _br.get('completeness')}
                if not _feat:
                    raise RuntimeError('bridge 无特征')
            except Exception:
                import txt_features as _tf
                _feat, _diag = _tf.extract(txt_path)
                _diag = {'detail': (_diag or {}).get('detail', {}),
                         'sources': {'txt': {'status': 'ok', 'note': 'bridge失败·txt直取', 'ms': 0}},
                         'completeness': '1/8 源可用(bridge降级)'}
            if _feat:
                _plog = os.path.join(_oldir, 'prediction_log')
                os.makedirs(_plog, exist_ok=True)
                import json as _pj
                _pname = os.path.splitext(os.path.basename(txt_path))[0] + '.json'
                _pj.dump({'txt': txt_path, 'features': _feat, 'detail': _diag.get('detail', {}),
                          'sources': _diag.get('sources', {}), 'completeness': _diag.get('completeness'),
                          'analyzed_at': __import__('time').strftime('%Y-%m-%d %H:%M')},
                         open(os.path.join(_plog, _pname), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
                print('  [预测日志] 特征已存: prediction_log/%s (赛果时 --from-log 自动回溯)' % _pname)
    except Exception as _pe:
        print('  ⚠️预测日志写入失败:', str(_pe)[:60])
    # 🧠 在线学习系统状态(2026-09-11·L1 实测无增益已默认关闭·仅状态提示)
    try:
        _ol = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'online_learning', 'state', 'river', 'n.json')
        import json as _oj
        if os.path.exists(_ol):
            _n = _oj.load(open(_ol, encoding='utf-8'))
            print('  [在线学习] L1样本=%s (⚫已否决: 原+0.68pp证实为数据泄露·赛前可得特征增益+0.01pp·2026-09-30裁决→权重0) L2/L3/L4累积中' % _n.get('direction', 0))
    except Exception:
        pass
    # 解析可选参数
    # 🔴2026-09-15合并(源自workbuddy): 原实现 `--eu --handi` 会把 '--handi' 当成 eu 的值 →
    #   eu.split(',') 长度≠3 → 现场引擎 ls 未赋值 → 掩盖真实原因。现改为仅当下一个 token 非 '--' 开头才取值。
    eu = handi = o25 = u25 = home_water = elo = inj_h = inj_a = off = None
    _tad_h27 = _tad_a27 = None      # 🔴P36: N27 攻防档案（main 内初始化·供 N23 传参）
    # 🔴V3.5.92-fix: --teams 值（供快照/市场入口优先使用·治「txt 简要名查不到」）
    _args_teams = None
    try:
        _av0 = sys.argv
        if '--teams' in _av0:
            _args_teams = _av0[_av0.index('--teams') + 1]
        elif any('--teams=' in _x for _x in _av0):
            _args_teams = [x.split('=', 1)[1] for x in _av0 if x.startswith('--teams=')][0]
    except Exception:
        _args_teams = None
    _bp_need_second = None          # 🔴2026-11-01 R-ANCHOR-BIG 次锚上探（供 N23 消费·原只打印=断链）
    _inj_lam_h = _inj_lam_a = 0.0   # 🔴2026-11-01 伤停 λ 调整（inj_list 分支赋值·Step6.5 消费）
    _bp_need_first = 0              # 🔴2026-11-01 P52 主锚下限（六级分级驱动）
    # 🔴2026-09-21 资金盘升级: 新增 --max/--max_o25/--max_u25（跨机构最高价·供 P0-1 spread 计算）
    #   代理口径 = (Max − 均值)/均值（与 Matches.csv 回测口径一致·Odds-API/竞彩无逐家时使用）
    _OVFLAGS = ('--eu', '--handi', '--o25', '--u25', '--home_water', '--elo', '--inj_h', '--inj_a', '--off',
                '--max', '--max_o25', '--max_u25', '--max_h', '--max_d', '--max_a',
                '--inj_list_h', '--inj_list_a', '--snapshot', '--draw-score',
                '--step5-dirs', '--jc-cs',   # 🔴P6 市场信号透传
                '--p12-fund', '--p12_fund',   # 🔴P12.1 R3 闸门维度回传
                   '--home', '--away', '--kickoff', '--ko', '--step5_dirs',
                   # 🔴2026-10-31 批次1（Step 全流程审计）: S03.5 疲劳战意输入（须登记·否则 _ov.get 恒 None）
                   '--fi-h7', '--fi-a7', '--fi-h14', '--fi-a14', '--fi-hkm', '--fi-akm',
                   '--fi-hrank', '--fi-arank', '--fi-hderby', '--fi-aderby')
    # 🔴2026-10-26 审计补: 上 5 项此前未登记 → _ov.get 恒 None（P12 队名兜底/临场窗口/R4 下划线变体均静默失效）
    _ov = {}
    for i, a in enumerate(sys.argv):
        if a in _OVFLAGS:
            _ov[a] = sys.argv[i + 1] if (i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith('--')) else ''
    _missing = [_k for _k in ('--eu', '--handi', '--o25') if _k in _ov and _ov[_k] == '']
    if _missing:
        print('  ⚠️参数无值(被跳过): %s —— 用法: --eu 主,平,客 --handi <让球值> --o25 <O2.5赔率> [--u25 <U2.5赔率>]'
              % ' '.join(_missing))
    eu = _ov.get('--eu') or None
    handi = _ov.get('--handi') or None
    o25 = _ov.get('--o25') or None
    u25 = _ov.get('--u25') or None
    home_water = _ov.get('--home_water') or None
    elo = _ov.get('--elo') or None
    inj_h = _ov.get('--inj_h') or None
    inj_a = _ov.get('--inj_a') or None
    inj_list_h = _ov.get('--inj_list_h') or None
    inj_list_a = _ov.get('--inj_list_a') or None
    off = _ov.get('--off') or None
    mx_dir = _ov.get('--max') or None
    mx_o25 = _ov.get('--max_o25') or None
    mx_u25 = _ov.get('--max_u25') or None
    mx_h = _ov.get('--max_h') or None
    mx_d = _ov.get('--max_d') or None
    mx_a = _ov.get('--max_a') or None
    print('=' * 70)
    print('calc_all.py — 全覆盖预计算(2026-09-02·步骤遗失结构性根除)')
    print('=' * 70)
    # ══════════════════════════════════════════════════════════════
    # 🔴2026-11-01 时间模块全模型安装（用户指令「时间模块全模型安装」）
    #   背景：模型今夜 **6 次**报错时间（说 01:28 实际 23:18·差 2h10m）
    #   → 不能靠「我记得」，必须**每份输出都带程序算的时间**
    #   本段：每份 calc_all 输出开头打印「分析时间 + 本场状态」，落进 raw 可审计
    try:
        import sys as _sysTG
        _sysTG.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from time_guard import now_bj as _now_bj, fmt_bj as _fmt_bj, match_state as _mst
        _tg_now = _now_bj()
        print('🔴 分析时间: %s  （🕐 程序计算·禁凭记忆·2026-11-01 全模型安装）'
              % _fmt_bj(_tg_now, True))
        _ko = None
        for _kn in ('kickoff', 'ko'):
            _ko = _ov.get('--' + _kn) if _ov else None
            if _ko:
                break
        if _ko:
            _stt = _mst(_ko)
            print('   本场状态: %s' % _stt['note'])
        print('=' * 70)
    except Exception as _te:
        print('   时间模块: ⚪ %s' % str(_te)[:70])

    # ══════════════════════════════════════════════════════════════
    # 🔴2026-09-27 数据链接入批（用户指令「三项孤立脚本全部封装接入数据链」）
    #   ① injury_impact   → 伤停清单直算影响分（治愈「--home 6.0 被当未知位置 → 1.0 分」手算错误）
    #   ② calc_homeaway   → HAF 主客场因子层（Step4.6 每场必调·原靠模型记得手跑并手记 λ）
    #   ③ halftime_inference → 覆盖标注（算法已并入 live·该文件为独立 CLI 工具·防「误判为孤儿」）
    # ══════════════════════════════════════════════════════════════
    _dir_here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _dir_here)
    _olp2 = os.path.join(os.path.dirname(_dir_here), 'online_learning')
    if os.path.isdir(_olp2) and _olp2 not in sys.path:
        sys.path.insert(0, _olp2)
    # ① 伤停影响分（injury_impact·P0-5·位置×重要性·与 --inj_h/--inj_a 叠加·后向兼容）
    if inj_list_h or inj_list_a:
        try:
            from injury_impact import (parse as _inj_parse, verdict as _inj_verdict,
                                       lambda_adj as _inj_lamadj)
            _lh_, _lhu, _lhp = _inj_parse([x for x in (inj_list_h or '').split(';') if x.strip()])
            _la_, _lau, _lap = _inj_parse([x for x in (inj_list_a or '').split(';') if x.strip()])
            _ih_ = (float(inj_h) if inj_h else 0.0) + _lh_
            _ia_ = (float(inj_a) if inj_a else 0.0) + _la_
            inj_h = ('%.2f' % _ih_) if _ih_ > 0 else inj_h
            inj_a = ('%.2f' % _ia_) if _ia_ > 0 else inj_a
            print('🔴伤停影响分(injury_impact·脚本计算·模型禁手算·P0-5):')
            print('  主队 %.1f 分 → %s%s' % (_ih_, _inj_verdict(_ih_),
                                          ('  [清单: %s]' % inj_list_h) if inj_list_h else ''))
            print('  客队 %.1f 分 → %s%s' % (_ia_, _inj_verdict(_ia_),
                                          ('  [清单: %s]' % inj_list_a) if inj_list_a else ''))
            print('  铁则32触发: %s | 已写入 --inj_h/--inj_a → 供 direction_full / true_handicap / 动态量级消费' % (
                '是(≥4.0·重度)' if (_ih_ >= 4.0 or _ia_ >= 4.0) else '否'))
            # 🔴2026-11-01 伤停 λ 调整（原 injury_impact.lambda_adj **从未进主链**·只在 CLI 打印）
            #   消融审计实证：calc_all 只叠加影响分，λ_final 完全不受伤停影响
            def _is_attack(_pn):
                # 🔴2026-11-01 修：原按**人数**比较 `F >= D+G` → 门将/中后卫各算 1，
                #   而 POS_WEIGHT 里门将=3.0 / 中后卫=2.5 / 前锋=2.2 → 权重差很大。
                #   实证（埃尔切场）：客队缺 2前锋+3后腰+1中后卫+**1门将** → 人数 2 vs 2
                #   平手被判「攻击线」→ λ -0.6（方向反了：门将缺应让**对手** λ 升）
                #   → 改按 POS_WEIGHT 加权：防 5.5 vs 攻 4.4 → 正确判「防线」→ +0.6
                _wdef = _pn.get('G', 0) * 3.0 + _pn.get('D', 0) * 2.5
                _watt = _pn.get('F', 0) * 2.2
                if _wdef == 0 and _watt == 0:
                    return False          # 只有中场缺 → 不算攻击线（走中性）
                return _watt > _wdef
            _inj_lam_h = _inj_lamadj(_lh_, _is_attack(_lhp)) if _lh_ else 0.0
            _inj_lam_a = _inj_lamadj(_la_, _is_attack(_lap)) if _la_ else 0.0
            print('  λ调整: 主队%+.2f·客队%+.2f → 合计 %+.2f 球（±0.6/队上限·Step6.5 λ_final 消费）'
                  % (_inj_lam_h, _inj_lam_a, _inj_lam_h + _inj_lam_a))
            if _lhu or _lau:
                print('  ⚠️未识别位置: %s%s（按1.0计·请用「位置,重要性」如「门将,主力」·或用 --inj_h/--inj_a 直传分）' % (
                    ('主:' + ','.join(_lhu)) if _lhu else '', ('客:' + ','.join(_lau)) if _lau else ''))
        except Exception as _e9:
            print('  ⚠️伤停影响分计算失败(保留 --inj_h/--inj_a 原值): %s' % _e9)
    elif inj_h or inj_a:
        # 🔴2026-10-27 修（case287 实抓）: 只传 --inj_h/--inj_a（已由 injury_impact 算好的分）时
        #   原else分支仍打印「未提供伤停清单·缺失」→ 与事实相反，模型会误记「伤停缺失」
        _ih2 = float(inj_h) if inj_h else 0.0
        _ia2 = float(inj_a) if inj_a else 0.0
        print('🔴伤停影响分(判定铁依据·直传分·injury_impact 已算):')
        print('  主队 %.2f 分 ｜ 客队 %.2f 分 → 铁则32触发: %s' % (
            _ih2, _ia2, '是(≥4.0·重度)' if (_ih2 >= 4.0 or _ia2 >= 4.0) else '否'))
        print('  🔴方向影响: direction_full 内 伤停≥4.0 → 该队概率 −4pp / 对手 +3pp（L531-532）')
        print('  ⓘ 如需脚本按位置现算: 改传 --inj_list_h "中后卫,主力;后腰,替补"（自动叠加）')
    else:
        print('🔴伤停影响分(判定铁依据·缺失): 未提供伤停清单（可用 --inj_list_h "门将,主力;后腰,主力" 由脚本算·或 --inj_h/--inj_a 直传分）')
        # 🔴2026-10-25 修（case279 实证）: 原仅报「未提供」→ 模型易写成三态直接交付（漏抓）
        print('   🔴🔴行动指令（铁则32·禁以三态直接交付）: 先跑 '
              '`python data/tmp/bzzoiro_fetch.py --teams "主队英文,客队英文"`（结构化位置级·五大联赛 5/5）'
              '→ 按输出的 --home/--away 条目跑 injury_impact.py；Bzzoiro 未定位的场次改 Bing/Google News（经代理 7897）。')
        print('   口径铁律: 「未执行」≠「无数据」· 不得以「源不可用/三态」了事。')
    # ② HAF 主客场因子层（calc_homeaway·Step4.6·顶层执行不可 import → subprocess·实测约 1.3s）
    try:
        try:
            import market_consensus as _mkc
            _th_, _ta_ = _mkc.txt_teams([txt_path])
        except Exception:
            _th_, _ta_ = (None, None)
        if _th_ and _ta_:
            _hk = _ak = None
            try:
                import data_bridge as _db2
                _hafjs = json.load(open(os.path.join(_dir_here, 'homeaway_table.json'), encoding='utf-8'))
                _keys = {_db2.normalize_name(k): k for k in _hafjs.get('_teams', {})}

                def _haf_key(_cn):
                    """中文/英文队名 → HAF 表键（football-data 简名·精确优先→末词/首词→子串兜底）

                    🔴2026-10-31 批次3 修复（Step 全流程审计实抓·真断链）:
                      「巴黎圣曼」→ None 导致 **HAF 整层未触发**（同场主队「勒阿弗尔」却映射成功）。
                      根因: 只查 `TEAM_ALIASES`（该表仅有全称「巴黎圣日耳曼」），
                      而**统一别名层** `snapshot_save.cn2en_list('巴黎圣曼')` 是有 ['Paris Saint-Germain','PSG','Paris SG'] 的。
                      → 现优先接统一别名层（与 2026-09-29 中→英根治同源），并加归一化子串兜底。
                    """
                    if not _cn:
                        return None
                    _cands = []
                    try:
                        import snapshot_save as _ssH
                        _cands += list(_ssH.cn2en_list(_cn) or [])
                    except Exception:
                        pass
                    _cands += list(_db2.TEAM_ALIASES.get(_cn, []) or []) + [_cn]
                    _ns = [_db2.normalize_name(c) for c in _cands]
                    for _n in _ns:
                        if _n and _n in _keys:
                            return _keys[_n]
                    for _n in _ns:
                        if not _n:
                            continue
                        _t = _n.split()
                        for _k, _orig in _keys.items():
                            _kt = _k.split()
                            if not _t or not _kt:
                                continue
                            if _t[-1] == _kt[-1] and len(_t[-1]) >= 4:
                                return _orig
                            if _t[0] == _kt[0] and (len(_t) == 1 or len(_kt) == 1) and len(_t[0]) >= 4:
                                return _orig
                    # 兜底: 归一化子串（候选 ⊂ 表键 或 表键 ⊂ 候选·取最长命中）
                    for _n in _ns:
                        if not _n or len(_n) < 4:
                            continue
                        _hit = [_k for _k in _keys if (_n in _k or _k in _n)]
                        if _hit:
                            return _keys[sorted(_hit, key=len)[-1]]
                    return None

                _hk, _ak = _haf_key(_th_), _haf_key(_ta_)
            except Exception:
                _hk, _ak = (None, None)
            if _hk and _ak:
                _r2 = subprocess.run([sys.executable, os.path.join(_dir_here, 'calc_homeaway.py'),
                                      '--ha', '%s,%s' % (_hk, _ak)],
                                     capture_output=True, text=True, encoding='utf-8', timeout=120,
                                     cwd=os.path.dirname(os.path.dirname(_dir_here)))
                _o2 = (_r2.stdout or '').strip()
                print('🔴HAF主客场因子层(calc_homeaway·Step4.6·脚本计算·LLM消费·禁手记λ):')
                if _o2:
                    print(_o2 if len(_o2) <= 1600 else _o2[:1600] + '\n  …(截断)')
                    # 🔴批次3 补（2026-10-31 Step 全流程审计）: AGENTS Step4.6 要求
                    #   「HAF 回归主模型 Step5(λ对照)/Step6/Step7」—— 原实现只 print 原始输出，
                    #   「对照」全靠模型手算。现脚本自动算偏移量（HAF 总λ vs 市场期望）。
                    try:
                        import re as _reH
                        _mh = _reH.search(r'λh\s*[=＝]\s*([\d.]+)', _o2)
                        _ma = _reH.search(r'λa\s*[=＝]\s*([\d.]+)', _o2)
                        if _mh and _ma:
                            _haf_tot = float(_mh.group(1)) + float(_ma.group(1))
                            _mkt_tot = None
                            try:
                                from live_score_engine import _o25_expect as _o25xH
                                if o25:
                                    _mkt_tot = float(_o25xH(float(o25)))
                            except Exception:
                                _mkt_tot = None
                            if _mkt_tot:
                                _dH = _haf_tot - _mkt_tot
                                print('  🔴HAF λ对照(Step4.6→Step5/6/7·**作偏移标注·不替代 calc_poisson**): '
                                      'HAF 总λ=%.2f ｜ 市场期望=%.2f → 偏离 %+.2f 球 %s'
                                      % (_haf_tot, _mkt_tot, _dH,
                                         '⚠️>0.5·两维分歧·以市场为准·仅留痕' if abs(_dH) > 0.5 else '（一致·可交叉验证）'))
                            else:
                                print('  🔴HAF λ对照: HAF 总λ=%.2f ｜ 市场期望缺失（无 --o25 → 三态）' % _haf_tot)
                        else:
                            print('  ⚪HAF λ对照: 输出未含 λh/λa（格式变更?）→ 三态·模型手读上方原文')
                    except Exception as _eH:
                        print('  ⚪HAF λ对照: %s（三态）' % type(_eH).__name__)
                else:
                    print('  ⚪无输出（%s）' % ((_r2.stderr or '').strip()[:120] or 'stderr 空'))
            else:
                print('🔴HAF主客场因子层: ⚪未触发（队名未映射到 HAF 表键: 主=%s→%s 客=%s→%s·可手跑 --ha）'
                      % (_th_, _hk, _ta_, _ak))
        else:
            print('🔴HAF主客场因子层: ⚪未触发（txt 未提取到队名·可手跑 --ha "主队,客队"）')
    except Exception as _e8:
        print('⚠️HAF接入失败(降级手工): %s' % _e8)
    # ③ 半场反推覆盖标注（防「误判为孤儿」·算法已并入 live）
    print('🔴半场反推覆盖: live_score_engine.halftime_precise_matrix(ht_ft_cond.json·175476场) 已承接 Step7.5·'
          'halftime_inference.py = 独立 CLI 工具(主流程不依赖·非缺失)')
    # 🔴V3.5.80 P9: 竞彩→欧亚盘数据桥（隔离竞彩噪音·结构不变·下游零改动）
    _bridge = None
    try:
        import jc_euro_bridge as _jeb
        _bs_cs, _bs_ah = None, None
        try:
            from snapshot_save import find_for as _ffb, _raw_of as _rawofb, _cs_full as _csf9, _ah_full as _ahf9
            import market_consensus as _mcb9      # 🔴实跑修: txt_teams 在 market_consensus（calc_match 无此函数）
            _bh, _ba = _mcb9.txt_teams([txt_path])
            if _bh and _ba:
                _rb = _ffb(_bh, _ba)
                if _rb.get('count'):
                    # 🔴2026-10-20 修(P1 口径·同源): 原取 first(最早时点) → P9 rq 用 3h 前盘口
                    #   (实测 利物浦场: 首点 hdp=-1.00 / 末点 hdp=-1.25) → 改取 last·缺则回退 first
                    _f0 = _rb.get('last') or _rb.get('first') or {}
                    _raw0 = _rawofb(_f0.get('file'), _f0.get('event_id'))
                    _bs_cs = _csf9(_raw0) or None
                    _bs_ah = _ahf9(_raw0) or None
        except Exception as _ebr:
            print('  ⚪P9 快照全档回读失败: %s: %s' % (type(_ebr).__name__, str(_ebr)[:70]))
            _bs_cs, _bs_ah = None, None
        _bridge = _jeb.bridge_sections(txt_path, eu=eu, handi=handi,
                                       o25=o25, u25=u25,
                                       cs_full=_bs_cs, ah_full=_bs_ah)
        print('=' * 70)
        print('🔴P9 竞彩噪音隔离·数据桥: 分段源=%s' % _bridge['src_map'])
        for _bn in (_bridge.get('notes') or []):
            print('  ' + _bn)
        print('=' * 70)
    except Exception as _eb:
        print('  ⚪P9数据桥: 异常→%s（不阻断主流程·竞彩源保留）' % str(_eb)[:80])
        _bridge = None
    # ══════ 🔴S03.5 疲劳战意（2026-10-31 Step 全流程审计修复）══════
    #   审计实证: fatigue_intent.py **零调用**（全库 grep 只有自身 docstring）
    #   AGENTS Step3.5 要求「有赛程/排名数据时执行·三态标注」→ 现接入（数据不足即显式三态）
    #   真实接口: fatigue(games_7d, games_14d, travel_km) / intent(rank, cup_rotation, derby)
    _fi_fat_fav, _fi_int_fav = None, None   # 🔴S03.5 → 置信度层（批次3 接线）
    try:
        import fatigue_intent as _fi
        _fi_k = ('--fi-h7', '--fi-a7', '--fi-h14', '--fi-a14', '--fi-hkm', '--fi-akm',
                '--fi-hrank', '--fi-arank', '--fi-hderby', '--fi-aderby')
        if any(_ov.get(k) not in (None, '') for k in _fi_k):
            def _fi_i(k, d=0):
                try:
                    return int(float(_ov.get(k)))
                except (TypeError, ValueError):
                    return d
            _fh = _fi.fatigue(_fi_i('--fi-h7', 1), _fi_i('--fi-h14', 2), _fi_i('--fi-hkm', 0))
            _fa = _fi.fatigue(_fi_i('--fi-a7', 1), _fi_i('--fi-a14', 2), _fi_i('--fi-akm', 0))
            _ih = _fi.intent(_fi_i('--fi-hrank', 10), False, bool(_ov.get('--fi-hderby')))
            _ia = _fi.intent(_fi_i('--fi-arank', 10), False, bool(_ov.get('--fi-aderby')))
            print('  🔴情境因子 S03.5 疲劳+战意量化(L3·仅调置信度/λ):')
            print('     疲劳分: 主%.1f 客%.1f（≥2 → 该队降1档·λ-0.2）' % (_fh, _fa))
            print('     战意分: 主%+.1f 客%+.1f（差≥2 → 该侧升1档·差 %+.1f）' % (_ih, _ia, _ih - _ia))
            print('     🔴铁律: 只调置信度/λ·永不反转 L2 方向')
            # 🔴批次3: 取**热门侧**的疲劳/战意 → 供置信度层消费（此前只 print）
            _eufi = (_ov.get('--eu') or '').split(',')
            try:
                _h_odd, _a_odd = float(_eufi[0]), float(_eufi[2])
            except (IndexError, TypeError, ValueError):
                _h_odd = _a_odd = None
            if _h_odd is not None and _a_odd is not None:
                if _h_odd <= _a_odd:      # 主队更热
                    _fi_fat_fav, _fi_int_fav = _fh, _ih
                else:
                    _fi_fat_fav, _fi_int_fav = _fa, _ia
                print('     → 传导: 热门侧=『%s』疲劳%.1f/战意%+.1f → 交置信度层（±1 档夹逼）'
                      % ('主' if _h_odd <= _a_odd else '客', _fi_fat_fav, _fi_int_fav))
        else:
            print('  ⚪情境因子 S03.5(疲劳战意): 未提供赛程/排名数据'
                  '（--fi-h7 --fi-a7 --fi-h14 --fi-a14 --fi-hkm --fi-akm --fi-hrank --fi-arank '
                  '--fi-hderby --fi-aderby）→ 三态·不触发（本条即三态留痕·禁静默）')
    except Exception as _efi:
        print('  ⚪情境因子 S03.5(疲劳战意): %s: %s（三态）' % (type(_efi).__name__, str(_efi)[:60]))

    # ══════ 🔴S00d H2H 双源（2026-10-31 Step 全流程审计修复）══════
    #   审计实证: 原 calc_all 零 H2H 计算代码 → 只有 C33 清单文本 + 「修正53 需外部补 S6」提示
    #   → H2H 全靠模型手工查 skill + 手传 --draw-score（P16③ 同款「靠人记得」缺陷）
    #   现: 源2（Matches.csv 逐场可核对）变确定性计算 → 直接消费到 修正53 S6
    _h2h_res, _h2h_s6 = None, False
    try:
        import market_consensus as _mch2h
        import h2h_lookup as _h2hl
        _h2h_h, _h2h_a = _mch2h.txt_teams([txt_path])
        if _h2h_h and _h2h_a:
            _h2h_txt, _h2h_res = _h2hl.report(_h2h_h, _h2h_a, n=6, league=league)
            for _ln2 in _h2h_txt.splitlines():
                print('  ' + _ln2)
            _h2h_s6, _h2h_why = _h2hl.draw_score(_h2h_res)
            # 🔴2026-10-31 批次6（传导可见性）: 原只打「✗ 不计」→ 审计看不到依据来自 H2H
            #   现带上「交锋 N 场·平X负Y·平局率·场均球」→ 值级传导可验（F04）
            _h2n = (_h2h_res or {}).get('n') or 0
            _h2tot = (_h2h_res or {}).get('total_all') or 0
            _h2dr = (_h2h_res or {}).get('draw') or 0
            _h2rate = (_h2h_res or {}).get('draw_rate')
            _h2ag = (_h2h_res or {}).get('avg_goals')
            print('  → S6 传导: %s ｜ 交锋 %d 场（库内共 %d 场·平 %d 场·平局率 %s·场均 %s 球）→ %s'
                  % ('✅ 计入修正53（+1 分）' if _h2h_s6 else '✗ 不计',
                     _h2n, _h2tot, _h2dr,
                     ('%.1f%%' % _h2rate) if isinstance(_h2rate, (int, float)) else '-',
                     ('%.2f' % _h2ag) if isinstance(_h2ag, (int, float)) else '-',
                     _h2h_why or '-'))
            print('     ｜ 源1(竞彩txt 特征分析·近N场交锋) 须模型另行提取并核对（两源口径并列·以本行 Matches.csv 为准）')
        else:
            print('  ⚪H2H 双源: txt 队名解析为空（三态·C33 须手工补）')
    except Exception as _eh2h:
        print('  ⚪H2H 双源: %s: %s（三态）' % (type(_eh2h).__name__, str(_eh2h)[:60]))

    # ① 跑 calc_match 全管道(含修正的run_extensions·净胜档/总进球档已接入)
    cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'calc_match.py'), txt_path]
    if league: cmd.append(league)
    # 🔴2026-10-13 审计修复(P1): 把欧盘**真实让球**透传给 calc_match →
    #   净胜档多档候选(margin_candidates_pool)用真实盘口而非竞彩让球
    #   （修 case240「竞彩+1 vs 真实0」/ case242「竞彩-1 vs 真实-0.25」的口径偏差）
    if handi: cmd += ['--handi', str(handi)]

    # 🔴P13.1 修复(P0 断链): 把 --eu 透传给 calc_match 子进程——
    #   原只传 --handi/--p9-bridge，calc_match 的 V5(C08) 只认命令行 --eu，
    #   导致 V5 在自动链路里永远跳过。eu 必须是真实欧盘（run_guard 已确保不用竞彩末盘）。
    if eu: cmd += ['--eu', str(eu)]
    # 🔴V3.5.80 P9: 把数据桥结果传给 calc_match（欧亚填充段生效·竞彩 bqc/逐T 保留）
    if _bridge:
        try:
            _bj = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_p9_bridge_tmp.json')
            json.dump(_bridge, open(_bj, 'w', encoding='utf-8'), ensure_ascii=False)
            cmd += ['--p9-bridge', _bj]
        except Exception as _ebj:
            print('  ⚪P9桥接透传失败(%s) → calc_match 用竞彩源' % type(_ebj).__name__)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=60)
        # 🔴V3.5.80 P9: 桥接临时文件用完即删（沙盒临时纪律·防残留污染）
        try:
            if _bridge:
                _bjx = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_p9_bridge_tmp.json')
                if os.path.exists(_bjx):
                    os.remove(_bjx)
        except Exception:
            pass
        out = r.stdout
        # 🔴2026-09-04链路优化: calc_match内部从竞彩盘反推O2.5常失败(竞彩txt无大小球盘段)→输出"O2.5未识别"会误导LLM跳过C17档位查表
        # 当调用方显式提供 --o25 时, 用真实档位分布替换该误导行(与calc_match同款格式·消除calc_match段与②量级段的矛盾观感)
        if o25 and out and 'O2.5未识别' in out:
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from calc_v3572 import goal_bin_probs as _gbp
                _g = _gbp(float(o25))
                if _g:
                    _tp2 = ''
                    if _g.get('top'):
                        _tp2 = ' | 典型比分:' + ' '.join('%s(%.1f%%)' % (s, pc) for s, pc in _g['top'])
                    _rep = ('  [goalbins] O2.5=%s 总进球档 0-1:%d%% 2球:%d%% 3球:%d%% 4+:%d%% 净3+:%d%%%s (Step6/7量级依据·calc_all注入)' % (
                        o25, round(_g['prob_01']*100), round(_g['prob_2']*100),
                        round(_g['prob_3']*100), round(_g['prob_4']*100), round(_g['net3']*100), _tp2))
                    out = out.replace('  [goalbins] O2.5未识别->不触发', _rep)
            except Exception:
                pass
        print(out)
        if r.stderr: print('⚠️calc_match stderr:', r.stderr[:200])
    except Exception as e:
        print('⚠️calc_match运行失败:', e)
    # ② 附加参数驱动的计算(欧亚综合·诱阻分类·量级)
    print('=' * 70)
    print('【欧亚综合+诱阻识别+量级(2026-09-02·direction_full新机制)】')
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from calc_v3572 import direction_full, match_classifier, handicap_intent_analyzer, goal_bin_probs
        if eu:
            parts = eu.split(',')
            if len(parts) == 3:
                oh, od, oa = map(float, parts)
                hs = float(handi) if handi else None
                hw = float(home_water) if home_water else None
                # 🔴2026-09-16 修复(P1·参数缺失致功能静默降级·与 F3/F5 同类):
                #   ① draw_group_score: 修正53 分组分(组A-D 去相关后总分) → direction_full 内部
                #      「平局并列/唯一」判定（>=4 唯一 / >=2.5 并列 / >=1.5 / >=1.0 加权）。
                #      原恒用默认 0.0 → **内部并列判定恒不触发**，与 calc_match 段输出的并列建议口径不一致。
                #   ② true_handi: 真实实力盘 → match_classifier 的「盘口背离」异常指标（|handi-true|>0.25）。
                #      原恒 None → 该指标恒不参与 → 诱阻分类 total_score 少一维(可能漏判庄家主导盘)。
                _draw_score = 0.0
                # 🔴2026-10-27 新增（case287 实抓）: calc_match 只能算 txt 可见的 S1/S2/S3，
                #   算不了 S4(近10场平局率)/S6(H2H交锋平局)/S12 —— 缺 H2H 就恒判 S6✗
                #   → 总分低 1 分 → 「≥2.5 并列平局」门槛误不触发。
                #   现支持 --draw-score 显式覆盖（模型用 H2H/交锋率等外部证据补齐后传入）。
                _ds_ov = _ov.get('--draw-score')
                if _ds_ov:
                    try:
                        _draw_score = float(_ds_ov)
                        print('  🔴修正53 分组分: **显式覆盖 %.1f**（外部证据补 S4/S6/S12·如 H2H 交锋平局）'
                              % _draw_score)
                    except Exception as _eds:
                        print('  ⚠️--draw-score 解析失败(%s)→回退正则提取' % _eds)
                else:
                    try:
                        _mds = re.search(r'总分(\d+(?:\.\d+)?)\s*→', out)
                        if _mds:
                            _draw_score = float(_mds.group(1))
                    except Exception:
                        _draw_score = 0.0
                    # 🔴2026-10-31 S00d 修复: H2H 源2 实测满足 S6 → 自动 +1 分
                    #   （原恒用正则总分 → 缺 H2H 就恒判 S6✗ → 「≥2.5 平局并列」门槛误不触发）
                    if _h2h_s6:
                        _draw_score += 1.0
                        print('  🔴修正53 分组分: 正则 %.1f + H2H源2 S6(+1.0) = **%.1f**'
                              % (_draw_score - 1.0, _draw_score))
                _true_handi = None
                try:
                    from calc_v3572 import true_handicap_calculator as _thc
                    _th, _ = _thc(elo_diff=float(elo) if elo else None, home_adv=0.25,
                                  inj_h=float(inj_h) if inj_h else 0, inj_a=float(inj_a) if inj_a else 0)
                    if _th is not None:
                        _true_handi = -_th   # 符号与 handi 一致(负=主让)·函数返回"正=主让"
                except Exception:
                    _true_handi = None
                # 🔴资金盘 P0-1: 跨机构分歧（热门侧 spread）→ 注入 direction_full 调置信度（审计 P1-12 接入）
                # 🔴 2026-09-21 修复(断链②+P1-1 方向错配): 支持三方向 Max 并**自动按热门方向选取**
                #   旧实现: mx 为单值 + _fav_o=min(...) → 客队热门时方向错配 → 虚假 SHARP_CONSENSUS 升权
                _fav_spread = None
                try:
                    _odds3 = [oh, od, oa]
                    _fi = _odds3.index(min(_odds3))
                    _fav_o = _odds3[_fi]
                    _mx3 = [mx_h, mx_d, mx_a]
                    _fav_max = None
                    if all(_mx3):
                        _fav_max = float(_mx3[_fi])
                    elif mx_dir:
                        # 单值 --max 兼容：仅当传入值与热门同向（比值在 0.9~1.3）才采纳
                        _v = float(mx_dir)
                        if 0.9 <= _v / _fav_o <= 1.3:
                            _fav_max = _v
                    if _fav_max is not None:
                        _fav_spread = (_fav_max - _fav_o) / _fav_o
                except (TypeError, ValueError, ZeroDivisionError):
                    _fav_spread = None
                # 🔴V3.5.81 P12 机构意图预计算（方向层·必须在 direction_full 之前·快照驱动·三态不阻断）
                _market_intent = None
                try:
                    from market_intent import build_market_intent as _bmi12, load_config as _lc12
                    _p12_mode = _lc12()
                    if _p12_mode != 'off':
                        import market_consensus as _mc12
                        _th12, _ta12 = _mc12.txt_teams([txt_path])
                        if not _th12:
                            _th12 = _ov.get('--home')
                            _ta12 = _ov.get('--away')
                        _ko12 = _ov.get('--kickoff') or _ov.get('--ko')
                        _ev12 = None
                        for _vk12 in ('--odd-event', '--event'):
                            if _vk12 in sys.argv and sys.argv.index(_vk12) + 1 < len(sys.argv):
                                _ev12 = sys.argv[sys.argv.index(_vk12) + 1]
                                break
                        _fund12 = {
                            'home_inj': float(inj_h) if inj_h else 0,
                            'away_inj': float(inj_a) if inj_a else 0,
                            'home_fatigue': locals().get('_fat_h'),
                            'away_fatigue': locals().get('_fat_a'),
                            'home_intent': locals().get('_int_h'),
                            'away_intent': locals().get('_int_a'),
                            'home_rotation': locals().get('_rot_h'),
                            'away_rotation': locals().get('_rot_a'),
                        }
                        # 🔴P12.1 R3：疲劳/战意/轮换由 Step3 研判后经 --p12-fund 回传（自动链路仅伤停）
                        #   格式：--p12-fund "home_fatigue=1,away_intent=2,home_rotation=1"
                        _pf12 = _ov.get('--p12-fund') or _ov.get('--p12_fund')
                        if _pf12:
                            for _kv in str(_pf12).replace('，', ',').split(','):
                                if '=' in _kv:
                                    _k12, _v12 = _kv.split('=', 1)
                                    _k12 = _k12.strip()
                                    if _k12 in _fund12:
                                        try:
                                            _fund12[_k12] = float(_v12)
                                        except ValueError:
                                            pass
                        if _th12 and _ta12:
                            _market_intent = _bmi12(_th12, _ta12, txt_path=txt_path, fund=_fund12,
                                                    kickoff=_ko12, event_id=_ev12,
                                                    spread=_fav_spread,          # 🔴P12.1 R2 资金盘 spread 加权
                                                    handi=hs, home_water=hw,     # 🔴P12.1 R2 亚盘字符串兜底
                                                    end_ml=(oh, od, oa))         # 🔴P12.1 R2 临场欧赔点
                            print('【机构意图(P12)·赔率升降三向结构】开关=%s · 快照 %s 时点'
                                  % (_p12_mode, _market_intent.get('count')))
                            if _market_intent.get('ok'):
                                for _e12 in _market_intent.get('evidence', []):
                                    print('     ' + _e12)
                                print('     → ' + str(_market_intent.get('action')))
                                # 🔴P12.1 R3：闸门维度诚实标注（自动链路仅伤停就绪）
                                _missing_fund = [k for k in
                                                 ('home_fatigue', 'away_fatigue', 'home_intent', 'away_intent',
                                                  'home_rotation', 'away_rotation')
                                                 if _fund12.get(k) is None]
                                if _missing_fund:
                                    print('     ⚠️闸门维度: 本场仅伤停维自动就绪；%s 未回传 → 相关诱盘/真信号判据三态。'
                                          'Step3 研判后可 --p12-fund 补传（不补不阻断，结果偏保守）'
                                          % ('、'.join(_missing_fund),))
                                # 🔴P12.1 R4：强诱盘/矛盾要求并列 → 校验 step5-dirs 是否含 ≥2 方向
                                _g12 = str(_market_intent.get('gate', ''))
                                if _g12.startswith('🔴强诱盘') or _g12.startswith('强诱盘') or _g12.startswith('矛盾'):
                                    _s5d12 = _ov.get('--step5-dirs') or _ov.get('--step5_dirs') or ''
                                    _ndir12 = len([x for x in str(_s5d12).replace('，', ',').split(',') if x.strip()])
                                    if _ndir12 < 2:
                                        print('     🔴P12 闸门=%s 要求并列，但本次 --step5-dirs 仅 %d 个方向'
                                              ' → 平局/次方向谱系不进比分池。Step5 必须传 ≥2 个方向（如 "主胜,平局"）'
                                              % (_g12, _ndir12))
                                    else:
                                        print('     ✅P12 并列已闭环: --step5-dirs 含 %d 个方向' % _ndir12)
                            else:
                                print('     ⚪ ' + str(_market_intent.get('reason')))
                except Exception as _e12:
                    print('  ⚪机构意图(P12): 异常→%s（三态·不阻断主流程）' % str(_e12)[:70])
                    _market_intent = None
                dr = direction_full(oh, od, oa, float(o25) if o25 else None, league_div=league, handi=hs, home_water=hw,
                    draw_group_score=_draw_score,
                    inj_score_h=float(inj_h) if inj_h else 0, inj_score_a=float(inj_a) if inj_a else 0,
                    official_dc=float(off) if off else None,
                    fav_spread=_fav_spread,
                    market_intent=_market_intent)
                print('  方向(欧亚综合): %s(%s) | 并列:%s | 诱盘:%s | 提示:%s | 修正53分组分%.1f' % (
                    dr['主方向'], dr['置信度'], dr['并列建议'], dr.get('诱盘信号') or '无', dr.get('执行提示') or '无', _draw_score))
                print('  ' + str(dr.get('小概率管理') or ''))
                # 🔴2026-09-21 资金盘信号模块（P0-1/P0-2/P0-3/P1-1/P1-3/P2-2/P2-3）
                #   消费纪律: 仅 backtested 项（P0-1 方向 spread）可调置信度·其余 pending 仅提示·永不反转方向
                try:
                    from fundflow_analyzer import analyze as _ff_analyze, render as _ff_render
                    _ff_books = None
                    try:
                        _ff_bp = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fundflow_books.json')
                        if os.path.exists(_ff_bp):
                            from bookmaker_spread import load_books as _lb
                            _ff_books = _lb(_ff_bp)
                            if _ff_books is None:
                                print('  ⚠️资金盘 books: 文件存在但 status!=ok/为空 → 降级代理通道(三态)')
                            # 🔴2026-10-21 P0-1 修复: books 场次校验（全局单文件·防上一场污染）
                            #   根因: load_books 返回**裸 list**（丢了 home/away）→ 下游 P0-1/P0-2 无法自校验
                            #   → 读原始 json 拿队名，match_check 比对本场 txt；mismatch 则整层阻断
                            try:
                                import market_consensus as _mkq
                                _rawq = json.load(open(_ff_bp, encoding='utf-8'))
                                _chkq = _mkq.match_check(_rawq, [txt_path])
                                if _chkq['verdict'] == 'mismatch':
                                    print('  🔴P0-1 场次错配 → 拒绝消费 books（源=%s / 本场=%s）'
                                          % (_chkq['books_teams'], _chkq['txt_teams']))
                                    print('     重跑: python data/tmp/the_odds_api_fetch.py books --home X --away Y')
                                    _ff_books = None
                                elif _chkq['verdict'] == 'unverifiable':
                                    print('  ⚠️P0-1 books 来源未校验（%s）→ 参考级' % _chkq.get('reason'))
                                else:
                                    print('  ✅P0-1 books 场次校验通过: %s' % (_chkq['books_teams'],))
                            except Exception as _eq:
                                print('  ⚠️P0-1 场次校验异常(%s) → 参考级' % type(_eq).__name__)
                    except Exception:
                        _ff_books = None
                    _ff_fav = min(oh, od, oa)
                    _ff_dir = 'H' if oh == _ff_fav else ('D' if od == _ff_fav else 'A')
                    # 🔴 2026-09-21 修复A: 三方向 Max 传给 fundflow（修「热门标签 NA」）
                    #   上方已算 _fav_max(热门侧 Max); 若 mx_h/mx_d/mx_a 均非空取热门侧 Max, 否则回退 mx_dir
                    _ff_mx = float(mx_dir) if mx_dir else None
                    if all([mx_h, mx_d, mx_a]):
                        _odds3f = [oh, od, oa]
                        _ff_mx = float([mx_h, mx_d, mx_a][_odds3f.index(min(_odds3f))])
                    # 🔴P1-2 修复(2026-09-29《双通道问题汇总》·存在≠活跃):
                    #   此前调用未传 ah/window → rlm_detect 新增的「真实亚盘盘口逆浅≥0.25」「临场窗口过滤」
                    #   两分支走不到 → 恒落 jc_handi 兜底(pending_backtest)。现透传真实快照盘口+距开赛分钟。
                    _ff_ah0 = _ff_ah1 = _ff_wmin = None
                    try:
                        import market_consensus as _mkf
                        _fh, _fa = _mkf.txt_teams([txt_path])
                        if _fh and _fa:
                            from snapshot_save import find_for as _ffind
                            _fs = _ffind(_fh, _fa)
                            if _fs['count']:
                                _ff_ah0 = _fs['first']['extract']['ah']
                                if _fs['count'] >= 2:
                                    _ff_ah1 = _fs['last']['extract']['ah']
                    except Exception:
                        pass
                    if _ff_ah1 is None and handi and home_water:
                        try:
                            _ff_ah1 = '让%+.2f 主%s/客0' % (float(handi), home_water)
                        except Exception:
                            _ff_ah1 = None
                    try:
                        import datetime as _dtf
                        _kof = _ov.get('--kickoff') or _ov.get('--ko')
                        if _kof:
                            _ff_wmin = (_dtf.datetime.strptime(str(_kof)[:16], '%Y-%m-%d %H:%M')
                                        - _dtf.datetime.now()).total_seconds() / 60.0
                    except Exception:
                        _ff_wmin = None
                    _ff = _ff_analyze(jc_path=txt_path, books=_ff_books, odd=oh,
                                      mx=_ff_mx,
                                      o25=float(o25) if o25 else None,
                                      max_o25=float(mx_o25) if mx_o25 else None,
                                      u25=float(u25) if u25 else None,
                                      max_u25=float(mx_u25) if mx_u25 else None,
                                      odd_h=float(oh), odd_a=float(oa),
                                      max_h=float(mx_h) if mx_h else None,
                                      max_a=float(mx_a) if mx_a else None,
                                      fav_odd=_ff_fav, fav_dir=_ff_dir,
                                      ah_from=_ff_ah0, ah_to=_ff_ah1, window_min=_ff_wmin,
                                      kickoff=_kof)   # 🔴2026-10-26 修: 原未传 → P2-3 时间权重恒「未提供开赛时间」
                    print()
                    print(_ff_render(_ff))
                    print('  🔴消费纪律: 仅 backtested 项（P0-1 方向 spread）可调置信度·其余 pending 仅提示·永不反转方向')
                except Exception as _ffe:
                    print('  ⚠️资金盘模块未执行:', str(_ffe)[:120])
                # 🔴2026-09-23 欧国联/国家队子模型（V3.5.75·league 含欧国联/Nations League 时激活·SK-league-nations）
                #   消费纪律: 只调置信度·永不反转 L2 硬核方向·最多±1档·未回测项仅提示
                try:
                    from nl_model import (is_nations_league as _nli, analyze as _nlan,
                                          extract_nl_teams as _nleteams, parse_matchday as _nlmd_)
                    _nlhit, _nlwhy = _nli(None, str(league or ''))
                    if _nlhit:
                        print()
                        # 🔴2026-09-28 P0-2/P0-4 修复: 队名与轮次统一由 nl_model 提取
                        #   （原正则要求字面"主场"结尾且不跨行 → 真实 txt 全不命中 → R4-R7 全部三态；
                        #     轮次原硬编码 1 → MD3+ 战意规则失效）
                        # 🔴2026-11-09 P0-2: 原 [:1500] 硬截断 → 长 txt 队名在后半段恒失配 → Elo 三态 → R4-R7 全失效
                        _nltx = open(txt_path, encoding='utf-8').read()[:20000]
                        _nlh, _nla = _nleteams(_nltx, str(league or ''))
                        _nlmd_v = _nlmd_(_nltx)
                        # 🔴2026-09-28 P0-3 修复: 市场赔率传入 → edge 自动计算
                        #   （原 mkt=None → case211「edge>0 且 公平≥0.60 才进串关 / ≤−10pp 降档」拦截形同不存在）
                        print(_nlan(None, str(league or ''), None, None, _nlmd_v, (oh, od, oa), 0, _fav_spread, _nlh, _nla))
                        print('  🔴NL 参数提取: 主=%s / 客=%s（未命中→Elo 三态·可手传 --home-team/--away-team）'
                              % (_nlh or '❌未命中', _nla or '❌未命中'))
                        print('  🔴NL 轮次: %s（未解析→R9 仅提示·禁按 MD1-2 硬套）'
                              % (('MD%s' % _nlmd_v) if _nlmd_v else '⚪未解析'))
                        print('  🔴NL 铁律: R5客队热门平局泄漏(禁稳胆)·R6主客进球分流·R7均势中性·R8主场60.7不下调·'
                              'R9 按真实轮次·R10 edge>0 且 公平≥0.60 才进串关·逐方向 ±10pp 调档')
                        print('  🔴Elo 数据陈旧时更新: python data/tmp/nl_elo_current.py（从 intl_results.csv 重算 313 队·数据管线·非自动）')
                    elif _nlhit is None:
                        print('  欧国联子模型: ⚪ 不确定（%s）' % _nlwhy)
                    else:
                        # 🔴2026-10-21 全量梳理修复(第5缺陷): 非 NL 场缺三态标注
                        #   AGENTS 铁则「非欧国联→不激活(三态标注·全局规则)」·原无 else → 输出零行
                        print('  ⚪ 欧国联/国家队子模型: 非欧国联（league=%s）→ 不触发(三态·R1-R10 均不适用)'
                              % (league or '⚪未传'))
                except Exception as _nle:
                    print('  ⚠️欧国联子模型未执行:', str(_nle)[:100])
                # ══════════════════════════════════════════════════════════════
                # 🔴2026-11-09 总分总架构（用户指令「隔离子模型·主模型通用·接口一致·防止不同比赛相互串」）
                #   总① MatchContext 一次性灌数据 → 分 子模型 analyze(ctx) → 总② aggregate 统一聚合
                #   · 子模型由 SUBMODELS 注册表驱动（一处定义·主模型只认这张表）
                #   · scope 白名单**强隔离**：子模型越界读表 → 直接拒绝 + 报警（不再只靠 AGENTS 文档纪律）
                #   · 与上方 NL 段**不重复**：上方给 R1-R10 原始数值（人读），本块给统一契约摘要（机读/审计）
                try:
                    from match_context import (MatchContext as _MC,
                                               aggregate as _aggf, fmt_aggregate as _aggfmt,
                                               violations as _aggviol)
                    from submodel_adapters import run_all as _subrun
                    def _safe(name, default=None):
                        # 🔴 作用域安全取值（eval 在函数内可见 globals+locals·失败则兜底）
                        try:
                            v = eval(name)
                            return v if v is not None else default
                        except Exception:
                            return default
                    # 🔴 队名不走 eval（实测 eval('_nlh') 在深层块取不到 → 导致 Elo 三态、R4/R5 解析失败）
                    #   改为直接重新提取：extract_nl_teams 已修好 `【赛事】` 支持（8/8 命中）
                    _agg_h = _agg_a = ''
                    try:
                        from nl_model import extract_nl_teams as _enta
                        _agg_h, _agg_a = _enta(
                            open(txt_path, encoding='utf-8').read()[:20000], str(league or ''))
                        _agg_h, _agg_a = (_agg_h or ''), (_agg_a or '')
                    except Exception:
                        pass
                    _aggctx = _MC(case_id=str(_safe('_case_id', '') or ''),
                                  league=str(league or ''),
                                  home=_agg_h, away=_agg_a,
                                  eu=(oh, od, oa), handi=_safe('hs'),
                                  o25=_safe('_o25_v') or _safe('o25'),
                                  u25=_safe('_u25_v') or _safe('u25'),
                                  spread=_safe('_fav_spread'),
                                  kickoff=str(_safe('_kickoff_v') or _safe('_kickoff', '') or ''),
                                  market=None, elo=None)
                    _subr = _subrun(_aggctx)
                    _aggr = _aggf([_subr], l2_lock=None)
                    print()
                    print(_aggfmt(_aggr))
                    _vv = _aggviol()
                    if _vv:
                        print('  🔒 强隔离拦截记录: %d 条（子模型越界读表已拒绝·证明隔离生效）' % len(_vv))
                except Exception as _agge:
                    print('  ⚪ 子模型聚合(总分总): 三态（%s: %s）'
                          % (type(_agge).__name__, str(_agge)[:80]))
                if hs is not None:
                    cf = match_classifier(oh, od, oa, handi=hs, water=hw, true_handi=_true_handi)
                    if _true_handi is not None:
                        print('  真实实力盘(ELO/伤停推导·参考): 真实%+.2f vs 实盘%+.2f' % (_true_handi, hs))
                    print('  诱阻分类: %s(总分%d·置信%.0f%%)' % (cf['match_type'], cf['total_score'], cf['confidence']*100))
                    # 🔴2026-10-24 固化判据①（用户指令·case268 实证）：诱主信号必须降**方向**·非仅降置信度
                    #   触发: direction_full 的「诱盘」字段含「诱主嫌疑」或「欧亚背离」
                    #   动作: 该方向从**首选降为并列**（降为并列 ≠ 反转·永不反转 L2 硬核方向）
                    #   反例: case268 阿拉维斯 主胜1.69 但仅让0.75 → 已报警诱主·仅降置信度未降方向 → 真实 1:1 平局
                    try:
                        _trp1 = str((dr or {}).get('诱盘信号') or '') if isinstance(dr, dict) else ''
                        if '诱主' in _trp1 or '欧亚背离' in _trp1:
                            print('  🔴判据①诱主信号(2026-10-24固化): %s' % _trp1)
                            print('     → 🔴执行要求: **该方向必须从首选降为并列**（仅降置信度=执行不足·case268实证）')
                            print('     → 铁律: 降为并列 ≠ 反转·永不反转 L2 硬核方向')
                    except Exception:
                        pass
                    if cf['anomaly_details']: print('    异常:', '; '.join(cf['anomaly_details']))
                    try:
                        ia = handicap_intent_analyzer(cf, dr['主方向'], dr.get('诱盘信号'))
                        if ia: print('    意图: %s → %s' % (ia['intent_type'], ia['true_direction']))
                    except Exception:
                        pass  # ia异常不阻断量级/后续(2026-09-09批检修复)
                if o25:
                    gb = goal_bin_probs(float(o25))
                    if gb:
                        _t3 = gb['prob_3'] + gb['prob_4']
                        print('  量级(O25校准分布·148397场实际·🔴禁市场隐含直读): O2.5=%s档%s → 0-1球%.0f%%/2球%.0f%%/3球%.0f%%/4+球%.0f%% | 总3+球%.0f%% 净3+%.0f%%' % (
                            o25, gb['band'], gb['prob_01']*100, gb['prob_2']*100, gb['prob_3']*100, gb['prob_4']*100, _t3*100, gb['net3']*100))
                        if gb.get('top'):
                            print('    典型比分(该档实测top4·候选池优先): %s' % ' '.join('%s(%.1f%%)' % (s, pc) for s, pc in gb['top']))
                        _ps = [gb['prob_01']*100, gb['prob_2']*100, gb['prob_3']*100, gb['prob_4']*100]
                        _span = max(_ps) - min(_ps); _mx = max(_ps)
                        print('    分布跨度%.0fpp(众数%.0f%%): %s' % (_span, _mx,
                            '🔴量级不确定·宽候选池按分布比例覆盖0-1到4+全档·禁锁单中心(147型2:0独锁误判根因)' if _span < 20 else ('中等·锁中心±1档' if _span < 35 else '量级明确·锁中心档')))
                        if float(o25) >= 2.3:
                            print('    🔴档≥2.3(总3+球%.0f%%≥1/3): 勿判强小球·对攻/防线伤停(影响分>=4)上场总进球中心上调1档·候选池强制含3:2/2:3对攻比分' % (_t3*100))
                        elif float(o25) <= 1.7:
                            print('    🔴档≤1.7(4+球%.0f%%): 大球强·但对手摆大巴/降级死守+主队控场→中心下调(保留0:0/1:0小球出口·case134教训)' % (gb['prob_4']*100))
                        # 🔴2026-10-21 进球数细分 N26（goal_count_table·用户指令「今晚这种极端大球/大球盘实际小球·市场信号能反映吗」）
                        #   实测 148,396 场: ①市场只反映「方向」（各档隐含 vs 实际校准差 −1.3~+1.8pp）
                        #     ②不反映「幅度」（同档 3/4/5/6+ 球概率同量级·单场 σ≈2 球）
                        #     ③1.40-1.50 档打 ≤2 球 34.2%（「大球盘实际小球」= 该档固有概率·非市场失灵）
                        #   ④🔴低分出口按档选: O2.5≤1.70 → 2 球（19.8% > 0-1 球 14.4%）｜>1.70 → 0-1 球（分界=既有大球强阈值）
                        #   ⑤🔴极端档（≤1.30）须打开 5-6 球候选（≤1.20 档 5球21.7%+6球9.6%+7+球15.3% = 46.6%）
                        try:
                            import sys as _s26
                            _d26 = os.path.dirname(os.path.abspath(__file__))
                            if _d26 not in _s26.path:
                                _s26.path.insert(0, _d26)
                            from goal_count_table import lookup as _gcl26
                            _gc = _gcl26(float(o25))
                            if _gc.get('ok'):
                                _pp = _gc['p']
                                print('  🔴进球数细分(N26·goal_count_table·148,396场实测): 档 %s(n=%s) | 0球%.1f%% 1球%.1f%% 2球%.1f%% 3球%.1f%% 4球%.1f%% 5球%.1f%% 6球%.1f%% 7+球%.1f%%'
                                      % (_gc['band'], _gc['n'], _pp['0'], _pp['1'], _pp['2'], _pp['3'],
                                         _pp['4'], _pp['5'], _pp['6'], _pp['7+']))
                                _cmp = ('>0-1球%.1f%%' % _gc['low01_pct']) if _gc['low_pick'] == '2球' else ('>2球%.1f%%' % _gc['low2_pct'])
                                print('     → 众数 %s(%.1f%%) · **低分出口优选 %s(%.1f%% %s·按档选)** · 6+球尾部 %.1f%%%s'
                                      % (_gc['mode'], _gc['mode_pct'], _gc['low_pick'], _gc['low_pick_pct'], _cmp,
                                         _gc['tail6_pct'],
                                         ' 🔴须开 5-6 球候选(尾部≥10%)' if _gc.get('tail_required') else ''))
                                print('     🔴纪律: 市场只反映「方向」(各档隐含vs实际≤2pp)·不反映「幅度」(同档3-6球同量级) → 出口按档选·尾部按档开·不改 L2 方向')
                                # 🔴2026-10-21 数据隔离: 本表为**五大基线**（148,396 场）·欧冠实测更高
                                #   （欧冠正赛 3.37球/O2.5 64.5% vs 五大 2.69/50.4%）→ 欧冠场次本表概率**偏保守**
                                #   禁把本表当欧冠口径、禁反向外流到联赛（联赛才是本表原生域）
                                # 🔴2026-11-09 欧国联完善：拆成**两个独立 try**
                                #   原 NL 判断嵌在「欧冠判断」同一个 try 里 → norm_league 抛异常时
                                #   整块跳过 → NL 标注静默不输出（实测抓到）。
                                try:
                                    if norm_league(league) == '欧冠':
                                        print('     ⚠️表源=五大基线(148,396场)·**欧冠实测更高**(3.37球/64.5% vs 五大2.69/50.4%) → 本表在欧冠场次偏保守·仅参考·禁当欧冠口径')
                                except Exception:
                                    pass
                                try:
                                    # NL 场同属**超域**（本表原生域=五大联赛 148,396 场）
                                    #   实测 NL 近年（n=198·2022-09 后）场均 2.71 球 / O2.5 51.0% vs 五大 2.69/50.4%
                                    #   → 数值几乎相同 → 偏保守幅度极小，但口径仍须声明（禁默认为原生域）。
                                    _lg_n26 = str(league or '')
                                    if any(k in _lg_n26.lower() for k in ('欧国联', 'nations', 'nl')):
                                        print('     ⚠️表源=五大基线(148,396场)·**欧国联属超域**（NL 近年实测 2.71球/O2.5 51.0% ≈ 五大 2.69/50.4% → 偏保守幅度极小·可参考）·禁当作 NL 专属口径')
                                except Exception:
                                    pass
                            else:
                                print('  ⚪进球数细分(N26): %s（三态）' % _gc.get('reason'))
                        except Exception as _e26:
                            print('  ⚪进球数细分(N26): %s' % type(_e26).__name__)
        # 🔴2026-10-30 R-POOL-BIG 宽池大球分级（用户指令「明确大球场次·数据越明确越应把 4/5/6 球放进宽池」）
        #   与回测的关系：回测否决的是**改锚**（全放宽 −0.60/−0.77pp·强制高分档 −0.24~−1.79pp）
        #   本段只作用于**宽池（不占锚位·不参与 Top2 排序）** → 零代价扩覆盖
        try:
            from big_pool_policy import report as _bpr
            _bp_o25 = o25 if 'o25' in dir() else None
            _bp_lam = None
            try:
                _bp_lam = _tw.get('lam_final') if isinstance(_tw, dict) else None
            except Exception:
                _bp_lam = None
            # 🔴P47/P48(2026-10-31): 均衡线由多档 Totals 均衡线（_tw['line']）优先，
            #   回退 λ（P(T≥k) 首≤50% 等价），再回退 None → 三态
            _bp_line = None
            try:
                # 🔴P51(2026-10-31): 分级用**均衡线**（fair_line·机构直接定价）
                #   优先级: _tw['line_fair']（多档插值·本场 3.42）→ line_close → λ_final
                if isinstance(_tw, dict):
                    # 🔴V3.5.91 修（2026-11-03 case320 实证）: key 名写错
                    #   原查 'lambda_final'，而 totals_water_read 实际输出 'lam_final'
                    #   （同段 L1213 用的就是 lam_final）→ 三档全 None → _bp_line=None
                    #   → level_from_line(None, o25) → 按 O2.5 判 L3
                    #   而 market_distribution 拿到均衡线 4.02 → 判 L5 → **同场两个分级**
                    _bp_line = (_tw.get('line_fair') or _tw.get('line_close')
                                or _tw.get('line_open') or _tw.get('lam_final')
                                or _tw.get('lambda_final'))
                if _bp_line is None and _bp_lam:
                    _bp_line = float(_bp_lam)
            except Exception:
                _bp_line = None
            if _bp_o25:
                _bp_txt, _bp_pol = _bpr(float(_bp_o25), None, _bp_lam, _bp_line)
                # 🔴P52-fix(2026-10-31 端到端审计): 分级**已接入锚定链**（不止打印）
                #   market_distribution 用同一入口 level_from_line/required_bins/span_requirement
                #   → 消费点 ①量级分项 ②宽池必含档补入 ③次锚跨度
                try:
                    from big_pool_policy import level_from_line as _lvfl, required_bins as _rbins
                    # 🔴2026-11-03 O-BIG-1: 双方防线各 ≥2 人伤 → 宽池扩档（L3→6 球 / L2→5 球）
                    try:
                        from big_pool_policy import def_dual_from_lists as _ddfl
                        _av_ = sys.argv
                        _hl_ = _av_[_av_.index('--inj_list_h') + 1] if '--inj_list_h' in _av_ else ''
                        _al_ = _av_[_av_.index('--inj_list_a') + 1] if '--inj_list_a' in _av_ else ''
                        _def_dual, _dnh_, _dna_ = _ddfl(_hl_, _al_)
                        if _def_dual:
                            print('  🔴O-BIG-1 防线双伤: 主 %d 人 / 客 %d 人 → 宽池扩档（L3 含 6 球 / L2 补 5 球）'
                                  % (_dnh_, _dna_))
                    except Exception:
                        _def_dual = False
                    _lv52 = _lvfl(_bp_line, _bp_o25)
                    print('  🔴P52 超大球分级: %s（均衡线%s·宽池必含%s球）→ 已接入锚定(量级/宽池/次锚跨度)'
                          % (_lv52, ('%.2f' % _bp_line) if _bp_line else '-',
                             ('/'.join(str(b) for b in _rbins(_lv52, def_dual=bool(_def_dual)))) or '无'))
                except Exception as _e52:
                    print('  ⚪P52 分级: %s（三态）' % type(_e52).__name__)
                for _ln in _bp_txt.splitlines():
                    print('  ' + _ln)
                # 🔴2026-10-30 R-ANCHOR-BIG: 明确大球场「次锚上探」（用户指令「也必须改锚定」）
                try:
                    from big_pool_policy import anchor_requirement as _barq
                    _tl = _bp_pol.get('tail') or {}
                    # 🔴P49(2026-10-31): E 口径统一 = **N18 市场期望**（O2.5 反推·权威）
                    #   原实现由 tail 反推（case300 给 3.29，而 N18=3.53）→ 同场两个 E
                    try:
                        from live_score_engine import _o25_expect as _o25x
                        _bp_E = float(_o25x(float(_bp_o25)))
                    except Exception:
                        _bp_E = sum(k * (_tl.get(k, 0) - _tl.get(k + 1, 0)) for k in range(7)) if _tl else 0.0
                    if _bp_E <= 0:
                        _bp_E = 3.0
                    _need, _note, _cost = _barq(_bp_E, _bp_pol)
                    _bp_need_second = _need if _need > 0 else None  # 🔴2026-11-01 供 N23 真正改锚
                    try:  # 🔴2026-11-01 P52 主锚下限（六级分级驱动·原只约束次锚）
                        from big_pool_policy import first_requirement as _bfrq
                        _bp_need_first = _bfrq(_bp_pol.get("level"))[0]
                    except Exception:
                        _bp_need_first = 0
                    if _need > 0:
                        try:
                            from big_pool_policy import span_requirement as _bsrq
                            _need2 = _bsrq(_bp_line, _bp_pol.get('level'), 2)
                        except Exception:
                            _need2 = 0
                        print('  🔹 R-ANCHOR-BIG(次锚上探): 本场 E=%.2f(市场期望) → 次锚须 ≥ %d 球 ｜ %s'
                              % (_bp_E, _need, _note))
                        if _need2:
                            print('      🔴P47 跨度式口径: 次锚 ≥ max(主锚+1, round(均衡线%.2f)) = **≥%d 球**'
                                  '（主锚不设任何限制·数据驱动）' % (_bp_line or 0, _need2))
                        print('      数据依据: %s ｜ 🔴 主锚不动（保主命中率）' % _cost)
                    else:
                        print('  🔹 R-ANCHOR-BIG: %s（%s）' % (_note or '次锚不受限', _bp_pol.get('level')))
                except Exception as _ebar:
                    print('  ⚪R-ANCHOR-BIG: %s（三态）' % type(_ebar).__name__)
            else:
                print('  ⚪宽池大球策略(R-POOL-BIG): 无 --o25 → 三态（无分布不可分级）')
        except Exception as _ebp:
            print('  ⚪宽池大球策略(R-POOL-BIG): %s（三态）' % type(_ebp).__name__)
        # 🔴2026-09-28 P0-5 兜底（防"存在≠活跃"复发·2026-09-27 三段无条件修复时遗漏了 NL 段）:
        #   NL 段原位于上方 `if eu:` 内 → 实测确认：不传 --eu 时整段静默（NL 场只输出必核清单，无 R1-R10）
        #   此处兜底：R1-R9 不依赖市场赔率照常输出；R10 edge 需市场 → mkt=None 走三态标注
        if not eu:
            try:
                from nl_model import (is_nations_league as _nli2, analyze as _nlan2,
                                      extract_nl_teams as _nlet2, parse_matchday as _nmd2)
                _nlhit2, _nlwhy2 = _nli2(None, str(league or ''))
                if _nlhit2:
                    print()
                    _nltx2 = open(txt_path, encoding='utf-8').read()[:1500]
                    _nlh2, _nla2 = _nlet2(_nltx2, str(league or ''))
                    _nlmd2v = _nmd2(_nltx2)
                    print(_nlan2(None, str(league or ''), None, None, _nlmd2v, None, 0, None, _nlh2, _nla2))
                    print('  🔴NL 参数提取: 主=%s / 客=%s' % (_nlh2 or '❌未命中', _nla2 or '❌未命中'))
                    print('  🔴NL 轮次: %s' % (('MD%s' % _nlmd2v) if _nlmd2v else '⚪未解析'))
                    print('  ⚪ 未传 --eu → R10 edge/逐方向 ±10pp 不计算（三态标注）·R1-R9 已输出')
                elif _nlhit2 is None:
                    print('  欧国联子模型(兜底段): ⚪ 不确定（%s）' % _nlwhy2)
                else:
                    # 🔴2026-10-21 全量梳理: 非 NL 场三态补齐（同第一处）
                    print('  ⚪ 欧国联/国家队子模型(兜底段): 非欧国联→ 不触发(三态)')
            except Exception as _nle2:
                print('  ⚠️欧国联子模型(无 --eu 兜底段)未执行:', str(_nle2)[:100])
    except Exception as e:
        print('  ⚠️欧亚综合计算失败:', e)
    # 🔴2026-09-27 审计修复（存在≠活跃）: 三条新规则改为**无条件输出**
    #   （原实现挂在 live 分析分支内 · 常规调用无 --eu 时不触发 = 存在但未活跃）
    try:
        import calc_v3572 as _qv2

        def _opt2(nm):
            _a2 = sys.argv
            if nm in _a2 and _a2.index(nm) + 1 < len(_a2):
                try:
                    return float(_a2[_a2.index(nm) + 1])
                except Exception:
                    return None
            return None

        _hn = _opt2('--handi')
        _o25n = _opt2('--o25')
        _u25n = _opt2('--u25')
        print('')
        print('  ' + '-' * 66)
        print('  🔴新规则无条件输出（2026-09-27 审计修复: 存在=活跃验证）')
        print('  ' + '-' * 66)
        # ① V6 四象限（N20）
        _qh2 = _qv2.quadrant_hint(_hn, _o25n, _u25n)
        print('  ' + (_qh2 if _qh2 else '⚪ V6四象限: 缺 --handi/--o25 → 不触发(三态)'))
        # ② 🔴🔴(D,M,T) 四要素联合象限 + joint_solver 锚（V3.5.77·2026-10-13 用户方案§5·第一优先级）
        #    🔴2026-10-13 接入审计修（用户「严格检查新更新是否真正介入模型·接口是否正确·有断点」）:
        #      原实现在此只传 handi/o25/u25 → ① 四源融合退化为 2 源（λ_line/λ_pois 恒缺）
        #      ② 与 Step6.5 大小球水位精读各算一套 λ = **口径分裂**（同场两个期望总进球）
        #      → 本块**整块下移**至 Step6.5 水位精读之后（见下方「N23 正式块」），
        #        消费 _tw（五源 λ）+ _lmkt/_ltab + league + ou_line → 口径单一权威。
        # ④ 🔴R20 平局温度计 + 深盘锚表（2026-10-07 审计补运行时入口·原仅技能手查→现脚本化·禁手查）
        try:
            from calc_v3572 import draw_temp_lookup as _dtl, deep_anchor_lookup as _dal
            _a2v = sys.argv
            _eu2 = _a2v[_a2v.index('--eu') + 1] if '--eu' in _a2v else None
            _ohv = float(str(_eu2).split(',')[0]) if _eu2 else None
            _elov = _opt2('--elo')
            _hv2 = float(_hn) if _hn not in (None, '') else None
            _dt = _dtl(o25=float(_o25n) if _o25n else None, handi=_hv2,
                       win_odd=_ohv, elo_diff=float(_elov) if _elov else None)
            print('  ' + _dt.replace('\n', '\n  '))
            _da = _dal(win_odd=_ohv, handi=_hv2)
            print('  ' + _da.replace('\n', '\n  '))
        except Exception as _e2:
            print('  ⚠️ R20平局温度/深盘锚查表异常:', _e2)
        # ② 锚-市场期望匹配（N18）+ ③ 期望三源联动（N19）
        if _o25n is not None:
            from live_score_engine import expect_triple_check
            _et = expect_triple_check(_o25n)
            print('  🔴期望三源联动(2026-09-27·N19): %s' % _et['msg'])
            if _et['exp_market'] is not None:
                print('  🔴锚-市场期望匹配(2026-09-27·N18·已放宽): 市场期望 %.2f 球 → 主锚 ∈ [%.2f, %.2f]（期望−1.0~+1.5）·主+次锚须覆盖期望±1.0（[%.2f, %.2f]）'
                      % (_et['exp_market'], _et['exp_market'] - 1.0, _et['exp_market'] + 1.5,
                         _et['exp_market'] - 1.0, _et['exp_market'] + 1.0))
        else:
            print('  ⚪ 锚-市场期望匹配(N18)/期望三源联动(N19): 缺 --o25 → 不触发(三态)')
        # ⑤ 🔴欧亚盘完整时间序列（N21·2026-09-28 建点 / 🔴2026-09-29 串联「正式执行时点」）
        #    序列 = [prestep 快照 T-0 … T-n] + [正式执行时点(--eu/--handi/--o25)]
        #    → 供 V1 变动层 / V2 诱阻 / V6 盘口联动 / P1-3 消费
        try:
            _snap_arg = _ov.get('--snapshot') or 'auto'
            if _snap_arg == 'none':
                print('  ⚪ 欧亚盘时间序列(N21): --snapshot none → 手动关闭(三态)')
            else:
                import market_consensus as _mk9
                _th9, _ta9 = _mk9.txt_teams([txt_path])
                # 🔴V3.5.92-fix（2026-11-04 case321 实证·P36b 同型漏修）: **--teams 优先**
                #   原只用 txt 中文名 → 「莱红牛」不在 cn2en 表 → find_for count=0
                #   → P10 三源全缺 → R11 零封块缺失（calc_all 报「缺块」）
                #   而 --teams 传「莱比锡」时 cn2en_list → ['RB Leipzig','Leipzig'] 能命中
                #   🔴 同一教训两次: P36b 只修了 N27，本处(find_for) 与 market_inputs 未修
                try:
                    if _args_teams:
                        _t9 = [x.strip() for x in _args_teams.split(',')]
                        if len(_t9) >= 2 and _t9[0] and _t9[1]:
                            _th9, _ta9 = _t9[0], _t9[1]
                except Exception:
                    pass
                if _th9 and _ta9:
                    from snapshot_save import find_for, delta_for
                    _sn9 = find_for(_th9, _ta9)
                    # 🔴正式执行时点（本场分析所用赔率/盘口）→ 作为序列末点
                    _cur_ml = (eu.replace(',', '/') if eu else None)
                    _cur_ah = None
                    # 🔴仅当 handi **且** home_water 都给出时才构造亚盘末点
                    #   （2026-09-29 修复: 原实现缺 home_water 时补 '0' → 误报「主水 3.220→0.000」水位剪刀差）
                    if handi and home_water:
                        try:
                            _cur_ah = '让%+.2f 主%s/客0' % (float(handi), home_water)
                        except Exception:
                            _cur_ah = None
                    _cur_o25 = ('O%s' % o25) if o25 else None
                    _dl = delta_for(_th9, _ta9, end_ml=_cur_ml, end_ah=_cur_ah, end_o25=_cur_o25,
                                    end_label='正式执行')
                    if _sn9['count'] or _cur_ml:
                        print('  🔴欧亚盘时间序列(N21): prestep 快照 %d 时点%s → 共 %d 时点'
                              % (_sn9['count'], ' + 正式执行时点' if _cur_ml else '（⚠️未传 --eu·末点缺失）', _dl['count'] or 0))
                        for _p in _dl['series']:
                            print('     · %-24s ML %s | 亚盘 %s | O2.5 %s'
                                  % (_p['at'], _p.get('ml'), _p.get('ah'), _p.get('o25')))
                        # 🔴2026-09-29 P2-4 修复（《全量审计报告·V3.5.76 复检》）:
                        #   消费端容缺键（`.get`）—— 生产端 delta_for 已补 'ml_chg_pct'，
                        #   此处双保险：任一字段缺失均不再抛 KeyError 被吞成「异常」
                        if _dl.get('ml_chg_pct') and _dl.get('ml_pp'):
                            print('     🔴全跨度变动(T-0→正式执行·共 %d 时点): 赔率%% 主 %+.1f/平 %+.1f/客 %+.1f ｜ 隐含pp 主 %+.1f/平 %+.1f/客 %+.1f ｜ 亚盘 %s ｜ O2.5隐含 %+.1fpp'
                                  % (_dl.get('count') or len(_dl.get('series') or []) or 2,
                                     _dl['ml_chg_pct'][0], _dl['ml_chg_pct'][1], _dl['ml_chg_pct'][2],
                                     _dl['ml_pp'][0], _dl['ml_pp'][1], _dl['ml_pp'][2],
                                     (_dl.get('ah') or {}).get('hdp', '-'), _dl.get('o25_imp') or 0))
                        elif _dl.get('count') and _cur_ml and not _sn9.get('count'):
                            # 🔴单时点（无 prestep 快照·仅正式执行时点）→ 三态标注·非「异常」
                            print('     ⚪ 无 prestep 快照可对比 → 仅正式执行时点 1 点（无变动可算·三态标注）')
                        if _dl.get('signal'):
                            for _s in _dl['signal']:
                                print('     ⚡ 判定信号(模块输出→V1/V2/V6 消费): %s' % _s)
                        else:
                            print('     ⚪ 全跨度变动未触发阈值(≥3%%/盘口移动/水位≥0.15) → 无判定信号')
                        print('     ⏱ 跨度 %s ｜ 🔴禁跨场复用(已按队名校验)' % (_dl['span'] or '-'))
                    else:
                        print('  ⚪ 欧亚盘时间序列(N21): 无本场快照匹配 且 未传 --eu → **序列不可构建**·三态标注')
                else:
                    print('  ⚪ 欧亚盘时间序列(N21): 未能从 txt 提取队名 → 不触发(三态)')
        except Exception as _e9:
            print('  ⚪ 欧亚盘时间序列(N21): 异常→%s（不阻断主流程）' % _e9)
    # ⑤.5 🔴动态盘双通道判定（V3.5.76·2026-09-29 用户方案《竞彩×欧亚盘双通道判定机制》）
        #     公众通道 = 竞彩逐T（txt → calc_match.parse_txt['spf']）· 抽水12.8%·散户情绪代理
        #     机构通道 = 欧亚盘时序（snapshot series 早盘→临场）· 抽水6.9%·机构意图
        #     🔴只调置信度 ≤±1档·永不反转 L2 硬核方向·未回测项标「⏳待回测·仅参考」
        try:
            from snapshot_save import dual_channel, find_for as _ff9
            from snapshot_save import cn2en as _cn9
            import market_consensus as _mk91
            _th91, _ta91 = _mk91.txt_teams([txt_path])
            # ── 公众通道：竞彩逐T（真实适配 txt 输入）──
            _jc9 = []
            try:
                import calc_match as _cm9
                _pd9 = _cm9.parse_txt(open(txt_path, encoding='utf-8').read())
                _jc9 = [(t, (v.get('胜'), v.get('平'), v.get('负')))
                        for t, v in (_pd9.get('spf') or [])
                        if v.get('胜') and v.get('平') and v.get('负')]
            except Exception as _e10:
                print('  ⚪动态盘双通道: 竞彩逐T 解析失败→%s（三态）' % str(_e10)[:50])
            # ── 机构通道：欧亚盘 早盘/临场（真实适配快照输入·中文队名已 cn2en）──
            _ah0 = _ah1 = None
            try:
                if _th91 and _ta91:
                    _sf9 = _ff9(_th91, _ta91)
                    if _sf9['count']:
                        _ah0 = _sf9['first']['extract']['ah']
                        if _sf9['count'] >= 2:
                            _ah1 = _sf9['last']['extract']['ah']
            except Exception:
                pass
            # 🔴P2-3 修复(2026-09-29《双通道问题汇总》): 快照不足 2 时点 → 用「正式执行时点」
            #   (--handi/--home_water) 兜底临点 · 口径与 N21 段 _cur_ah 完全一致
            #   （客水补 0·只消费主水）→ 不再因缺临场快照而必然三态·即使本场已给 --handi 也不用
            if _ah1 is None and handi and home_water:
                try:
                    _ah1 = '让%+.2f 主%s/客0' % (float(handi), home_water)
                except Exception:
                    _ah1 = None
            # 🔴P1-3 修复: 距开赛分钟数 → 窗口分级（>48h 烟雾弹降级 / ≤90min 临场最强）
            _wmin9 = None
            try:
                import datetime as _dt9
                _ko9 = _ov.get('--kickoff') or _ov.get('--ko')
                if _ko9:
                    _wmin9 = (_dt9.datetime.strptime(str(_ko9)[:16], '%Y-%m-%d %H:%M')
                              - _dt9.datetime.now()).total_seconds() / 60.0
            except Exception:
                _wmin9 = None
            _dc = dual_channel(_jc9, None, _ah0, _ah1, _wmin9)
            _q = _dc.get('quadrant')
            _c1 = _dc.get('C1')
            print('  【动态盘双通道判定】(V3.5.76·只调置信度·永不反转 L2 方向)')
            print('     公众通道(竞彩逐T %d 时点): %s'
                  % (len(_jc9), ('热门 %s 变动 %+.2f%%（负=降赔·公众涌入）' % (_c1['fav'], _c1['pct'])) if _c1 else '⚪不可判(三态·未传/解析失败)'))
            print('     机构通道(欧亚盘): 早盘 %s → 临场 %s%s'
                  % (_ah0 or '-', _ah1 or '-', '' if _ah1 else '（⚠️缺临场时点·三态）'))
            if _dc.get('window'):
                print('     窗口分级: %s' % _dc['window']['grade'])
            print('     四象限: %s' % ('🟣 %s %s — %s' % (_q[0], _q[1], _q[2]) if _q else '⚪未触发'))
            if _q:
                print('     └ 依据: %s' % _q[3])
            for _n9 in (_dc.get('notes') or []):
                if _n9.startswith(('⚪双通道: 公众主动看衰', '⚪双通道: 欧亚盘口')):
                    print('     %s' % _n9)
            print('     🔴纪律: 只调置信度 ≤±1档·永不反转 L2 硬核方向·未回测项仅参考')
        except Exception as _e11:
            print('  ⚪动态盘双通道: 异常→%s（不阻断主流程）' % str(_e11)[:70])
        # ④ 机构共识层（2026-09-27·用户指令「跨市场分歧 + 多元合并去水 双用途分配」）
        try:
            _bp = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fundflow_books.json')
            if os.path.exists(_bp):
                import market_consensus as _mc
                _bk = json.load(open(_bp, encoding='utf-8'))
                # 🔴2026-09-27 审计P0修复: 场次错配阻断（fundflow_books.json 为全局单文件·实测 case103 读到 fixture 1528863 他场）
                _chk = _mc.match_check(_bk, sys.argv[1:])
                if _chk['verdict'] == 'mismatch':
                    print('  🔴机构共识层: **场次错配 → 拒绝消费**! books来源=%s vs 本场txt=%s'
                          % (_chk['books_teams'], _chk['txt_teams']))
                    print('     重跑: python data/tmp/fetch_books.py --fixture <本场ID> --home X --away Y')
                    print('     或:   python data/tmp/the_odds_api_fetch.py books --home X --away Y')
                else:
                    if _chk['verdict'] == 'unverifiable':
                        print('  ⚪机构共识层 场次校验: 无法校验（%s）→ 请人工确认来源' % _chk.get('reason'))
                    _md = _mc.merge_devig(_bk)
                    _sp = _mc.spread(_bk)
                    print('  🔴机构共识层(2026-09-27): %d 家 · 平均抽水 %.2f%%'
                          % (_md['n_books'], _md['margin_mean'] * 100))
                    print('     ① 多元合并去水(→方向/凯利/λ): 主 %.1f%% / 平 %.1f%% / 客 %.1f%% (热门 %s)'
                          % (_md['pH'] * 100, _md['pD'] * 100, _md['pA'] * 100,
                             {'H': '主胜', 'D': '平局', 'A': '客胜'}[_md['favorite']]))
                    _sH = (_sp.get('H') or {}).get('spread_pct')
                    _sD = (_sp.get('D') or {}).get('spread_pct')
                    _sA = (_sp.get('A') or {}).get('spread_pct')
                    print('     ② 跨市场分歧(→仅调置信度): 主 %s / 平 %s / 客 %s'
                          % (('%.2f%%' % (_sH * 100)) if _sH is not None else 'n/a',
                             ('%.2f%%' % (_sD * 100)) if _sD is not None else 'n/a',
                             ('%.2f%%' % (_sA * 100)) if _sA is not None else 'n/a'))
                    if _sH is not None and _md['favorite'] == 'H' and _sH < 0.02:
                        print('     🟡 P0-1: 热门侧 spread<2%% → 置信度 +0.5/+1 档（回测 52.7-81.5%%）')
                    else:
                        print('     ⚪ P0-1: spread≥2%% → 仅标注·不降档（回测不达 >3pp 门禁）')
            else:
                print('  ⚪ 机构共识层: 缺 fundflow_books.json → 不触发(先跑 the_odds_api_fetch books / fetch_books)')
        except Exception as _e3:
            print('  ⚠️ 机构共识层降级: %s' % str(_e3)[:60])
    except Exception as _e2:
        print('  ⚠️ 新规则输出降级: %s' % str(_e2)[:70])

    # 🔵BSD 增强层（Bzzoiro·2026-10-09 用户指令「不用观察·直接进行」→ P0/P1/P2 全接入判定链）
    # 🔴2026-10-29 断链修复（审计）: calc_all 无 --bsd-teams 参数 → 原实现恒三态；
    #   而 txt 里就有主客队名 → 此处提前解析一次（_TT_H/_TT_A），供 BSD/N27 共用
    _TT_H = _TT_A = None
    try:
        import market_consensus as _mkT0
        _TT_H, _TT_A = _mkT0.txt_teams([txt_path])
    except Exception:
        _TT_H = _TT_A = None
    try:
        _bsdt = sys.argv[sys.argv.index('--bsd-teams') + 1] if '--bsd-teams' in sys.argv else (('%s,%s' % (_TT_H, _TT_A)) if (_TT_H and _TT_A) else None)
        _bsde = sys.argv[sys.argv.index('--bsd-event') + 1] if '--bsd-event' in sys.argv else None
        if _bsdt or _bsde:
            _bcmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bsd_layer.py'), '--apply']
            if _bsde:
                _bcmd += ['--event', _bsde]
            else:
                _bcmd += ['--teams', _bsdt]
            _br = subprocess.run(_bcmd, capture_output=True, text=True, encoding='utf-8', timeout=150)
            print(_br.stdout or '')
            if _br.stderr and 'Traceback' in _br.stderr:
                print('  ⚠️ BSD stderr: %s' % _br.stderr.strip().split(chr(10))[-1][:90])
        else:
            print('  🔵 BSD 增强层: 无 --bsd-event 且 txt 队名解析失败 → 不触发(三态·方案§六降级)')
            print('     P0-a 伤停加权分: ⚪ 无数据（BSD 未触发·三态）→ 伤停走 Bzzoiro 结构化（源B8）')
            print('     P0-b movement: ⚪ 无数据（0 家·BSD 未触发）→ 双通道走 prestep 快照')
    except Exception as _e12:
        print('  ⚪ BSD 增强层: 异常→%s（不阻断主流程·铁律: BSD 挂了模型独立跑通）' % str(_e12)[:70])
        print('     P0-a 伤停加权分: ⚪ 无数据（BSD 异常·三态）')
        print('     P0-b movement: ⚪ 无数据（0 家）')

    # 🔴 大小球盘口水位精读（SL-totals-water-read·2026-10-11 用户方案接入·**无条件段**防 if eu 静默·2026-09-27 教训）
    #   🔴2026-10-11 审计补（用户「严格检查新部分是否完全接入模型·数据链接口是否完整·是否活跃且能触发」）:
    #     原实现只传 o25/u25/totals_rows/home_odds/handi → **Layer3(初盘-临场线/水位) 与 minutes_to_ko
    #     在 calc_all 路径恒为 None** → 8 象限恒 neutral、时间权重恒 1.0 = 典型「存在≠活跃」(死接线)。
    #     现补齐三条数据源（全部复用既有采集链路·不新建源）:
    #       ① 多档 Totals: `--totals-multi` > data/tmp/_totals_multi.json > **本场快照 raw_1xbet 自动提取**
    #       ② Layer3 初盘/临场: `--line-open/--line-close/--water-open/--water-close` > **快照多时点自动**
    #       ③ 时间权重: `--mins-to-ko` > `--kickoff` 计算 > **快照 kickoff_bj 自动计算**
    try:
        _tw_dir = os.path.dirname(os.path.abspath(__file__))
        if _tw_dir not in sys.path:
            sys.path.insert(0, _tw_dir)
        from totals_water_read import water_read as _wr, snapshot_inputs as _sni, totals_from_raw as _tfr
        # 🔴变量名不得再用 _g（上方 562 行 `_g = _gbp(o25)` 是 goal-bin 对象 → 覆盖会造成隐性坏味道）
        _av = lambda n: (sys.argv[max(i for i, x in enumerate(sys.argv) if x == n) + 1]
                         if (n in sys.argv and max(i for i, x in enumerate(sys.argv) if x == n) + 1 < len(sys.argv))
                         else None)
        _f1 = lambda x: (float(x) if x not in (None, '') else None)
        _o25v, _u25v = _av('--o25'), _av('--u25')
        _handiv, _euv = _av('--handi'), _av('--eu')
        # ── ① 多档 Totals（Layer1 均衡线）──
        _tr, _trsrc = None, None
        _tmv = _av('--totals-multi')
        if _tmv:
            try:
                _tr = (json.load(open(_tmv, encoding='utf-8')) if os.path.exists(_tmv) else json.loads(_tmv))
                _trsrc = '--totals-multi'
            except Exception:
                _tr = None
        if not _tr:
            _trj = os.path.join(_tw_dir, '_totals_multi.json')
            if os.path.exists(_trj):
                try:
                    _trc = json.load(open(_trj, encoding='utf-8'))
                    if _trc:
                        _tr, _trsrc = _trc, '_totals_multi.json'
                except Exception:
                    pass
        # ── ② 快照自动提取（Layer1 多档 + Layer3 初盘/临场 + 距开赛分钟）──
        _sn = {}
        try:
            import market_consensus as _mkT
            _hT, _aT = _mkT.txt_teams([txt_path])
            # 🔴V3.5.92-fix: 同上 —— market_inputs 也要 --teams 优先
            #   实证: 「莱红牛」查不到 → cs/btts/totals/spread 全空 → P10 回退泊松链路
            try:
                if _args_teams:
                    _tm = [x.strip() for x in _args_teams.split(',')]
                    if len(_tm) >= 2 and _tm[0] and _tm[1]:
                        _hT, _aT = _tm[0], _tm[1]
            except Exception:
                pass
            if _hT and _aT:
                _sn = _sni(_hT, _aT)
        except Exception:
            _sn = {}
        if not _tr and _sn.get('totals_rows'):
            _tr, _trsrc = _sn['totals_rows'], '本场快照 1xbet Totals 多档(自动)'
        # 🔴V3.5.79 修复(2026-10-17 审计·用户「欧亚盘开盘都是大3」): 多档 Totals 同样只认 fast 快照
        #   → 未跑 prestep 的常规分析中 Layer1 退化为「O2.5 反推等效线」= 真盘口线(3球)未参与
        #   修复: 无快照时回退**当场实时 1xbet Totals 全档**(--odd-event/--event)
        # 🔴2026-10-17 封装: 改由统一入口 market_inputs 取（一次 API 拿全 5 市场·带来源标记）
        _trsrc = _trsrc or None
        _MI = None
        if not _tr:
            try:
                import market_inputs as _MImod
                _MI = _MImod.resolve(home=_hT, away=_aT,
                                     event_id=(_av('--odd-event') or _av('--event')),
                                     league=league)   # 🔴2026-11-01 联赛过滤·防跨联赛误配
                if _MI.get('totals'):
                    _tr, _trsrc = _MI['totals'], _MI['src'].get('totals')
            except Exception:
                _MI = None
        # 🔴2026-10-17 数据链体检表（每场必打·缺项显式告警·禁静默降级）
        if _MI is None:
            try:
                import market_inputs as _MImod2
                _MI = _MImod2.resolve(home=_hT, away=_aT,
                                      event_id=(_av('--odd-event') or _av('--event')),
                                      league=league)
            except Exception:
                _MI = None
        if _MI:
            try:
                # 🔴2026-10-17 修复（审计实抓 UnboundLocalError）: 原 L1099 直接用 `_MImod`，
                #   但 `_MImod` 只在 L1079「`not _tr`」分支内 import → 本场快照已有 totals 时该分支跳过
                #   → `_MImod` 未定义 → 体检表整块崩（只打印「体检表输出异常: UnboundLocalError」）
                #   → 改为在本 try 内独立 import，两条路径都安全
                import market_inputs as _MIrep
                print('  🔴市场数据链体检[统一入口 market_inputs]:')
                for _ln in _MIrep.report(_MI).split('\n'):
                    print('  ' + _ln)
                _mcs = _MI.get('cs') or {}
                if len(_mcs) < 8:
                    print('    ⚠️ 波胆仅 %d 档(<8) → P2 证据链弱·仅查表排序' % len(_mcs))
                if not _MI.get('eq'):
                    print('    ⚠️ 无均衡档 → P1 让球水位不采用（三态·禁深档冒充）')
            except Exception as _exMI:
                print('    ⚠️ 体检表输出异常: %s' % type(_exMI).__name__)
        # ── ③ Layer3 入参（显式参数优先 → 快照多时点）──
        _lo = _f1(_av('--line-open')) if _av('--line-open') else _sn.get('line_open')
        _lc = _f1(_av('--line-close')) if _av('--line-close') else _sn.get('line_close')
        _wo = _f1(_av('--water-open')) if _av('--water-open') else _sn.get('water_open')
        _wc = _f1(_av('--water-close')) if _av('--water-close') else _sn.get('water_close')
        _mk = _f1(_av('--mins-to-ko')) if _av('--mins-to-ko') else _sn.get('mins_to_ko')
        if _mk is None:
            try:
                import datetime as _dtT
                _koT = _av('--kickoff') or _av('--ko')
                if _koT:
                    _mk = round((_dtT.datetime.strptime(str(_koT)[:16], '%Y-%m-%d %H:%M')
                                 - _dtT.datetime.now()).total_seconds() / 60.0, 1)
            except Exception:
                _mk = None
        # ── ④ 五源补全（λ_market / λ_table·方案 §6 是**五源**加权 → 原实现只给 line/water/pois 三源、
        #      market/table 恒缺失 = 文档与实现不符）──
        _lmkt = _ltab = None
        if _o25v:
            try:
                from live_score_engine import expect_triple_check as _etcT
                _e3T = _etcT(float(_o25v))
                _lmkt, _ltab = _e3T.get('exp_market'), _e3T.get('exp_table')
            except Exception:
                _lmkt = _ltab = None
        _tw = _wr(o25=_o25v, u25=_u25v, totals_rows=_tr,
                  line_open=_lo, line_close=_lc, water_open=_wo, water_close=_wc,
                  home_win_odds=float(_euv.split(',')[0]) if _euv else None,
                  handicap=_f1(_handiv), minutes_to_ko=_mk,
                  lambda_market=_lmkt, lambda_table=_ltab)
        # 🔴2026-11-01 伤停 λ 调整真正接入 λ_final（原 lambda_adj 从未进主链·消融审计实证）
        try:
            if _inj_lam_h or _inj_lam_a:
                _lam_pre = _tw.get('lambda_final')
                if _lam_pre is not None:
                    _tw['lambda_inj_raw'] = _lam_pre
                    # 🔴2026-11-01 打折 0.3（防与市场双重计算）：
                    #   庄家定价时**已知伤停** → 市场 λ（P10/O2.5）已含该信息 →
                    #   直接叠加 = 二次计入（实证埃尔切场：伤停 +1.20 → λ 3.787，
                    #   但 P10 市场期望仅 2.728，O2.5 2.001 ≈ 2.4-2.5）
                    #   打折后 2.587 + 1.20×0.3 = 2.947 ≈ 市场 ✅
                    _INJ_LAM_W = 0.3
                    _tw['lambda_inj_raw'] = _inj_lam_h + _inj_lam_a
                    _tw['lambda_final'] = round(
                        max(0.3, float(_lam_pre) + (_inj_lam_h + _inj_lam_a) * _INJ_LAM_W), 3)
                    print('     🔴λ_final 伤停调整 %+.2f×%.1f=%+.2f（主%+.2f/客%+.2f·'
                          '🔴打折防与市场双重计算）→ %s'
                          % (_inj_lam_h + _inj_lam_a, _INJ_LAM_W,
                             (_inj_lam_h + _inj_lam_a) * _INJ_LAM_W,
                             _inj_lam_h, _inj_lam_a, _tw['lambda_final']))
        except Exception as _eij:
            print('     ⚪伤停 λ 调整未生效: %s（三态）' % type(_eij).__name__)
        print('  🔴 大小球盘口水位精读(N22·SL-totals-water-read·2026-10-11·未回测项仅参考):')
        print('     λ_line=%s · λ_water=%s · λ_pois=%s · λ_base=%s · λ_move=%s · trap=%s'
              % (_tw.get('lambda_line'), _tw.get('lambda_water'), _tw.get('lambda_pois'),
                 _tw.get('lambda_base'), _tw.get('lambda_move'), _tw.get('trap_adj')))
        print('     λ_final=%s → 九档量级「%s」（源=%s·离散=%s·置信=%s·8象限=%s·时间权重=%s）'
              % (_tw.get('lambda_final'), _tw.get('totals_bin'), ','.join(_tw.get('sources') or []),
                 _tw.get('src_spread'), _tw.get('confidence'), _tw.get('quadrant'), _tw.get('time_window')))
        print('     数据来源: 多档=%s ｜ 快照=%s ｜ 初盘/临场线=%s→%s 水=%s→%s ｜ 六源(含handi) market=%s/table=%s'
              % (_trsrc or '无(用 O2.5 反推等效线)',
                 (_sn.get('note') or '未匹配本场快照'),
                 _lo if _lo is not None else '-', _lc if _lc is not None else '-',
                 _wo if _wo is not None else '-', _wc if _wc is not None else '-',
                 _lmkt if _lmkt is not None else '缺', _ltab if _ltab is not None else '缺'))
        if _mk is not None:
            print('     距开赛 %s 分钟%s' % (_mk, '（⚠️负数=比赛已开始·历史场次复跑/快照时点已过 → 时间权重降级 0.5）' if _mk < 0 else ''))
        for _n in (_tw.get('notes') or []):
            print('     · %s' % _n)
        print('     🔴 纪律: 只调量级标签/置信度·永不反转 L2 方向·未回测项(盘口线/盘口移动/水位动态)仅参考')
    except Exception as _e13:
        print('  ⚪ 大小球盘口水位精读: 异常→%s（不阻断主流程）' % str(_e13)[:70])

    # 🔴🔴 2026-10-21 欧冠正赛大球校准（N24·用户指令「欧战子模型需要校准·尤其欧冠·大球显著」）
    #   实测（欧战全量 1174 场·同主胜档加权消除强弱结构差异）:
    #     欧冠正赛(联赛阶段) 3.37球/O2.5 64.5%/O3.5 52.6%  vs  欧联正赛 2.81/51.9%  vs  欧协联正赛 2.38/43.5%
    #     欧冠淘汰赛(含附加赛) 3.82球/76.5%  |  欧冠资格赛 2.65/47.5%（低于五大）  |  五大基线 2.69/50.4%
    #     控制主胜去水概率分档后，欧冠仍高于五大同档 +0.5~0.8 球；bootstrap 场均差 +0.67·95%CI[+0.15,+1.20]
    #   用户 2026-10-21 裁定: λ_final 与期望 E **各全额 +0.67 球（点估计）**·仅正赛/淘汰赛·资格赛不加
    #   诚实边界: 76 场全落单赛季(2025-10-01~2026-01-29)·**无法时间分割**·置换p=0.0252 / 二项p=0.1213 两法不一
    _ucl_adj = 0.0
    try:
        _lcn24 = norm_league(league)
        if _lcn24 != '欧冠':
            print('  ⚪ 欧冠大球校准(N24)/PSG 强度(N25): 非欧冠场（%s）→ 不触发（三态·数据隔离）' % _lcn24)
        if _lcn24 == '欧冠':
            _p24 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ucl_calibration.json')
            _d24 = json.load(open(_p24, encoding='utf-8'))
            _rd24 = sys.argv[sys.argv.index('--ucl-round') + 1] if '--ucl-round' in sys.argv else 'main'
            _adj24 = float((_d24.get('apply') or {}).get(_rd24, 0.0))
            _c24 = ((_d24.get('table') or {}).get('欧冠') or {}).get(_rd24) or {}
            _b24 = _d24.get('five_league_baseline') or {}
            if _adj24:
                _ucl_adj = _adj24
                print('  🔴欧冠正赛大球校准(N24·ucl_calibration.json·2026-10-21 用户裁定):')
                print('     轮次=%s · n=%s · 场均 %s 球 · O2.5 %s%% · O3.5 %s%%（五大基线 %s 球/%s%%）'
                      % (_rd24, _c24.get('n'), _c24.get('mean_goals'), _c24.get('o25'), _c24.get('o35'),
                         _b24.get('mean_goals'), _b24.get('o25')))
                print('     → λ_final 与期望 E 各 %+.2f 球（点估计·仅正赛/淘汰赛）· 资格赛/附加赛不加' % _ucl_adj)
                try:
                    _lam24 = _tw.get('lambda_final')
                    if _lam24 is not None:
                        _tw['lambda_final_raw'] = _lam24
                        _tw['lambda_final'] = round(float(_lam24) + _ucl_adj, 3)
                        _tw['ucl_adj'] = _ucl_adj
                        print('     λ_final %s → %s（校准后·下游 N23/量级/期望共用此口径）' % (_lam24, _tw['lambda_final']))
                except Exception as _e24b:
                    print('     ⚠️ λ 校准未生效: %s（三态）' % type(_e24b).__name__)
                print('     ⚠️ 诚实边界: 76 场全落单赛季(2025-10→2026-01)·无法时间分割·置换p=0.0252/二项p=0.1213')
                # 🔴2026-10-21 P1-4 修复: 显式输出「校准后期望」→ 消 N19(纯三源) 与 N18(含N24) 的口径歧义
                try:
                    from live_score_engine import expect_triple_check as _etc24
                    if _o25v:
                        _eN19 = _etc24(float(_o25v)).get('exp_market')
                        if _eN19 is not None:
                            print('     🔴期望口径说明: N19 三源联动=%s 球（**纯市场·不含N24**·用于三源自洽校验）欄 '
                                  'N18 锚-期望=%s 球（**含N24 %+.2f**·用于锚定校验）'
                                  % ('%.2f' % _eN19, '%.2f' % (_eN19 + _ucl_adj), _ucl_adj))
                except Exception:
                    pass
            else:
                print('  ⚪ 欧冠大球校准(N24): 轮次=%s（资格赛/附加赛实测 2.65 球·低于五大 → 不加·三态）' % _rd24)
            # 🔴 2026-11-03 欧战六项核查表（rule51-70）脚本化
            #   实跑实抓: 欧冠场跑 pipeline 时「C10 Step3 场景44/45/46(+欧战六项核查表)」
            #   只是**必核清单里一行文字**·脚本层**零输出** → 模型漏调 SL-europe-db 就缺六项
            try:
                from europe_check import report as _eurep
                _eu24 = []
                if _euv:
                    try:
                        _eu24 = [float(x) for x in str(_euv).split(',')]
                    except Exception:
                        _eu24 = []
                _hn24 = None
                if '--handi' in sys.argv:
                    try:
                        _hn24 = float(sys.argv[sys.argv.index('--handi') + 1])
                    except Exception:
                        _hn24 = None
                _fl24 = sys.argv[sys.argv.index('--first-leg') + 1] if '--first-leg' in sys.argv else None
                for _ln24 in _eurep(league='欧冠', rnd=_rd24,
                                   oh=(_eu24[0] if len(_eu24) > 2 else None),
                                   od=(_eu24[1] if len(_eu24) > 2 else None),
                                   oa=(_eu24[2] if len(_eu24) > 2 else None),
                                   handi=_hn24, first_leg=_fl24):
                    print('  ' + _ln24)
            except Exception as _eec:
                print('  ⚪欧战六项核查(rule51-70): 三态(%s)' % type(_eec).__name__)
            # PSG 强度档案（用户 2026-10-21·权限=并列+量级上修·不反转 L2 硬核方向）
            try:
                _tms24 = sys.argv[sys.argv.index('--teams') + 1] if '--teams' in sys.argv else ''
                _pk = ('巴黎', 'PSG', '圣日耳曼', 'Paris')
                if _tms24 and any(k in _tms24 for k in _pk):
                    _h24, _a24 = (_tms24.split(',') + ['', ''])[:2]
                    _side24 = '主队' if any(k in _h24 for k in _pk) else '客队'
                    _p24v = None
                    try:
                        _eup24 = [float(x) for x in _euv.split(',')]
                        _iv24 = [1 / x for x in _eup24]; _sv24 = sum(_iv24)
                        _p24v = round((_iv24[0] if _side24 == '主队' else _iv24[2]) / _sv24, 3)
                    except Exception:
                        _p24v = None
                    _psgd = (_d24.get('psg') or {})
                    _thr24 = float(_psgd.get('weak_threshold') or 0.45)
                    print('  🔵PSG 强度档案(N25·ucl_calibration.json·用户 2026-10-21 裁定「并列+量级上修」):')
                    print('     PSG 在%s · 去水胜率=%s · 判弱阈值=%.2f · 欧冠可核 5 场场均 %s 球'
                          % (_side24, _p24v if _p24v is not None else '缺(--eu)', _thr24, _psgd.get('mean_goals_all5')))
                    if _p24v is not None and _p24v < _thr24:
                        print('     🔴触发: 赔率把 PSG 判为弱方(去水 %.3f < %.2f) → **必须把 PSG 方向列为并列候选**（禁单押对手）' % (_p24v, _thr24))
                        print('     → 本场量级按欧冠大球处理（含 N24 %+.2f）· **永不反转 L2 硬核方向**（不得把 PSG 单独立为主方向）' % _ucl_adj)
                    else:
                        print('     ○ 未触发强制并列（赔率未把 PSG 判弱）→ 仅作方向强度加权参考·不覆盖赔率')
                    print('     ⚠️ 样本 5 场 < 单队固化门槛 20 → 有限权限观察项·非定量系数')
            except Exception as _e25:
                print('  ⚪ PSG 强度档案: %s（三态·须传 --teams "主队,客队"）' % type(_e25).__name__)
    except Exception as _e24:
        print('  ⚪ 欧冠大球校准(N24): %s（不阻断主流程）' % str(_e24)[:70])
    # 判据②输入: 对攻特征（对手场均失球 + 双方合计场均进球）
    _n27_attack_up = None
    try:
        import json as _j27b, os as _o27b
        _f27b = _o27b.path.join(_o27b.path.dirname(_o27b.path.abspath(__file__)), 'team_attack_defense.json')
        _D27b = _j27b.load(open(_f27b, encoding='utf-8')).get('teams') or {}
        _tm27 = (sys.argv[sys.argv.index('--teams') + 1] if '--teams' in sys.argv else '')
        _hh27, _aa27 = ([x.strip() for x in _tm27.split(',')] + ['', ''])[:2]
        def _mk27(name):
            for k, v in _D27b.items():
                if v.get('cn') == name or k.lower() == name.lower(): return v
            return None
        _h27, _a27 = _mk27(_hh27), _mk27(_aa27)
        if _h27 and _a27:
            _ga_h27 = ((_h27.get('lg') or {}).get('home_ga') or (_h27.get('lg') or {}).get('ga') or 0)
            _ga_a27 = ((_a27.get('lg') or {}).get('away_ga') or (_a27.get('lg') or {}).get('ga') or 0)
            _gf_h27 = ((_h27.get('lg') or {}).get('home_gf') or (_h27.get('lg') or {}).get('gf') or 0)
            _gf_a27 = ((_a27.get('lg') or {}).get('away_gf') or (_a27.get('lg') or {}).get('gf') or 0)
            _tot27 = float(_gf_h27) + float(_gf_a27)
            if float(_ga_a27) >= 1.8 and _tot27 >= 3.5:
                _n27_attack_up = ('对手客场场均失 %.2f ≥1.8 · 双方合计场均进 %.2f ≥3.5 → 对攻场' % (float(_ga_a27), _tot27))
            elif float(_ga_h27) >= 1.8 and _tot27 >= 3.5:
                _n27_attack_up = ('主队主场场均失 %.2f ≥1.8 · 双方合计场均进 %.2f ≥3.5 → 对攻场' % (float(_ga_h27), _tot27))
    except Exception:
        _n27_attack_up = None
    # 🔴2026-10-24 判据②双源修正（case265 实测：N27 历史档案判不出来）
    #   根因: N27 用联赛历史(蒙扎客场失1.63) 而竞彩 txt 显示近期 2.0 → 历史档案低估近期对攻属性
    #   修法: 竞彩近10场场均数据作为第二数据源·任一源命中即触发
    try:
        import re as _re27
        _tx27 = open(txt_path, encoding='utf-8', errors='replace').read()[:2000]
        _m_ga = _re27.search(r'场均失球[：:]\s*[^\d]*(\d+\.?\d*)[^\d]+(\d+\.?\d*)', _tx27)
        _m_gf = _re27.search(r'场均进球[：:]\s*[^\d]*(\d+\.?\d*)[^\d]+(\d+\.?\d*)', _tx27)
        if _m_ga and _m_gf:
            _ga_away_jc = float(_m_ga.group(2))
            _tot_jc = float(_m_gf.group(1)) + float(_m_gf.group(2))
            if _n27_attack_up is None and _ga_away_jc >= 1.8 and _tot_jc >= 3.0:
                _n27_attack_up = ('竞彩近10场: 对手场均失 %.2f ≥1.8 · 双方合计场均进 %.2f ≥3.0 → 对攻场'
                                  % (_ga_away_jc, _tot_jc))
    except Exception:
        pass
    # 🔴🔴 2026-10-25 N28 xG 滚动均值（understat·**自动调用·防漏执行**）
    #   动因: case279 实测我漏跑 xG（人工步骤 → 遗忘 → 只标"未执行"）→ 用户指令「自动调用·防再漏执行」
    #   防泄露: 只用**已赛**场次滚动均值（understat_xg.team_avg_xg 内部按已赛过滤）·本场 xG 严禁赛前使用
    #   定位: 攻防验证信号（与 N27 同族）·**不主导方向/锚**·缺失→三态
    print('🔴xG 滚动均值(N28·understat·自动·防泄露):')
    try:
        import understat_xg as _uxg28
        _lgm28 = {'英超': 'EPL', '西甲': 'La_liga', '德甲': 'Bundesliga', '意甲': 'Serie_A', '法甲': 'Ligue_1'}
        # 🔴2026-10-25 修（作用域陷阱·同模块连踩三次）:
        #   ①原先用 dir() 检查 _league_cn —— 只查模块命名空间 → main() 局部变量恒 False
        #   ②`_league_cn` 直到 L2073 才赋值，N28 在 L1422 → NameError
        #   ③`args` 不存在（calc_all 用 sys.argv 手工解析·无 argparse）
        #   → 统一改用 main 内**已存在**的 `league` / `o25` / `txt_path`
        try:
            _ln28 = _lgm28.get(norm_league(league))
        except Exception:
            _ln28 = _lgm28.get(league)
        if not _ln28:
            print('   ⚪ 非五大联赛/未识别 → xG 不适用(三态·不算遗漏)')
        else:
            # 🔴2026-10-25 修（首次实战 4/4 场「队名未命中」·真因=**赛季选择**非队名映射）:
            #   understat 赛季初期当前季数据极稀（实测 season=2026: Ligue_1 仅 2 队 / Serie_A 0 队 / EPL 2 队），
            #   而 cn2en_list 映射本身正常（摩纳哥→AS Monaco ✅）。
            #   → 改为「按队数阈值自动选赛季」：当前季队数 <8 视为稀疏 → 回退上一季（season=2025 各联赛 18-20 队完整）
            #   防泄露不变：team_avg_xg 内部只取已赛场次滚动均值
            _xg28, _sn_used, _sparse = None, None, None
            for _sn28 in (2027, 2026, 2025):
                try:
                    _d28 = _uxg28.team_avg_xg(_ln28, _sn28, n=3) or None
                except Exception:
                    _d28 = None
                if not _d28:
                    continue
                if len(_d28) >= 8:
                    _xg28, _sn_used = _d28, _sn28
                    break
                if _sparse is None:
                    _sparse, _sn_used = _d28, _sn28
            if _xg28 is None:
                _xg28 = _sparse or {}
            if _xg28:
                print('   （understat season=%d · 各队近3场滚动均值 · 覆盖 %d 队%s）'
                      % (_sn_used, len(_xg28), '' if len(_xg28) >= 8 else ' ⚠️赛季稀疏·仅参考'))
            _xg28 = _xg28 or {}

            def _uxg_find28(tbl, cn):
                """队名三级匹配: ①精确/互含 ②英文别名候选 ③首词回退"""
                if not cn:
                    return None
                _cands = [cn]
                try:
                    import snapshot_save as _ss28
                    _cands = (_ss28.cn2en_list(cn) or []) + _cands
                except Exception:
                    pass
                for _c in _cands:
                    _cl = str(_c).lower().strip()
                    if not _cl:
                        continue
                    for _k in tbl:
                        if _cl in _k.lower() or _k.lower() in _cl:
                            return _k
                for _c in _cands:
                    _w1 = (str(_c).lower().split() or [''])[0]
                    if len(_w1) < 5:
                        continue
                    for _k in tbl:
                        _w2 = (_k.lower().split() or [''])[0]
                        if _w1 == _w2:
                            return _k
                return None

            # 🔴2026-10-25 修: calc_all **无 --teams 参数** → 队名统一由 txt 解析（同 N27 / P0-1 口径）
            _tp28 = []
            try:
                import market_consensus as _mc28
                _bh28, _ba28 = _mc28.txt_teams([txt_path])
                _tp28 = [x for x in (_bh28, _ba28) if x]
            except Exception:
                _tp28 = []
            if not _tp28:
                print('   ⚪ txt 队名解析失败 → 无法定位队名(三态)')
            else:
                _h28 = _uxg_find28(_xg28, _tp28[0])
                _a28 = _uxg_find28(_xg28, _tp28[1] if len(_tp28) > 1 else None)
                if not (_h28 or _a28):
                    print('   ⚪ understat 队名未命中（%s·候选=%s）→ 三态·不算遗漏'
                          % (_ln28, '/'.join(str(x) for x in _tp28[:2])))
                else:
                    _hv = _xg28.get(_h28) or {}
                    _av = _xg28.get(_a28) or {}
                    print('   主 %s: 近3场 xG %.2f / xGA %.2f (n=%s)'
                          % (_h28 or '-', _hv.get('avg_xg') or 0, _hv.get('avg_xga') or 0, _hv.get('n') or 0))
                    print('   客 %s: 近3场 xG %.2f / xGA %.2f (n=%s)'
                          % (_a28 or '-', _av.get('avg_xg') or 0, _av.get('avg_xga') or 0, _av.get('n') or 0))
                    if _hv.get('avg_xg') is not None and _av.get('avg_xg') is not None:
                        _xh28 = (_hv['avg_xg'] + (_av.get('avg_xga') or _hv['avg_xg'])) / 2.0
                        _xa28 = (_av['avg_xg'] + (_hv.get('avg_xga') or _av['avg_xg'])) / 2.0
                        _xt28 = _xh28 + _xa28
                        print('   → xG 口径预期: 主 %.2f / 客 %.2f / 总 %.2f 球' % (_xh28, _xa28, _xt28))
                        _o25v28 = None
                        try:
                            _o25v28 = float(o25) if o25 else None
                        except Exception:
                            _o25v28 = None
                        if _o25v28:
                            try:
                                from live_score_engine import _o25_expect as _ox28
                                _e28 = _ox28(_o25v28)
                            except Exception:
                                _e28 = None
                            if _e28:
                                _d28 = _xt28 - _e28
                                print('   🔴对照市场期望 %.2f 球 → 偏差 %+.2f 球 %s'
                                      % (_e28, _d28,
                                         '(✅一致·≤0.35)' if abs(_d28) <= 0.35 else '(⚠️背离·以市场为准·xG 仅验证)'))
                    print('   🔴纪律: xG = 验证信号（不主导方向/锚）·背离只降权不反转·本场 xG 仅赛后验证')
    except Exception as _e28x:
        print('   ⚪ understat 取数失败（%s: %s）→ 三态·不算遗漏' % (type(_e28x).__name__, str(_e28x)[:60]))

# 🔴🔴 2026-10-21 球队双向攻防档案（N27·用户指令「依托现有数据为每队建 xG 进球表·分析时查询」）
    #   为什么不是纯 xG 表（滚动验证 37,195 场 MAE）: 纯进球率 0.9960 ｜ 射正xG 0.9890(-0.70%)
    #     ｜ 双向xG 0.9836(-1.25%) ｜ **双向进球率 0.9732(-2.29%) 最优** → 主口径取双向进球率
    #   标定: 射正→进球 28.73%（五大 37,989 场）· r=0.456(r²=0.208)
    #   数据: 联赛 Matches 43,708 场(218 队·主客分离) + 欧冠 europe 264 场(116 队·n<5 标仅参考)
    #   用途: **独立于赔率的攻防维度**（与伤停/ELO/xG/H2H 同级）→ Step5 方向与 Step6 量级交叉验证
    # 🔴2026-10-29 断链修复（审计）: calc_all **无 --teams 参数**（队名已在 L1317 由 txt 解析 _hT/_aT）
    #   原实现只读 sys.argv → 永远拿不到 → N27 恒三态（数据在手却没传下去）
    # 🔴P36（2026-10-30 批次2 断链2·实测抓出）: 原实现 **中文 txt 队名优先** →
    #   `_tfind27('弗洛西诺')` 匹配不到 N27 表（表内是 'Frosinone'）→ 恒「队伍未找到」三态
    #   → 即使消费链已接好，**数据仍拿不到**。修法: **--teams（英文）优先**，中文仅回退。
    _teams27 = ''
    if '--teams' in sys.argv:
        try:
            _teams27 = sys.argv[sys.argv.index('--teams') + 1]
        except (ValueError, IndexError):
            _teams27 = ''
    if not _teams27:
        try:
            if _hT and _aT:
                _teams27 = '%s,%s' % (_hT, _aT)
        except NameError:
            _teams27 = ''
    if _teams27 and ',' in _teams27:
        try:
            from team_attack_defense import match as _tad27, find as _tfind27
            _p27 = [x.strip() for x in _teams27.split(',')]
            _h27, _a27 = _p27[0], (_p27[1] if len(_p27) > 1 else '')
            if _h27 and _a27:
                _r27 = _tad27(_h27, _a27)
                if _r27.get('ok'):
                    print('  🔴球队双向攻防档案(N27·team_attack_defense·联赛43,708场+欧冠264场):')
                    for _side27, _en27, _cn27 in (('主', _r27.get('home'), _r27.get('home_cn')),
                                                  ('客', _r27.get('away'), _r27.get('away_cn'))):
                        _kv = (_tfind27(_en27 or '') or (None, {}))[1] or {}
                        _lg27 = _kv.get('lg') or {}
                        # 🔴P36: 存双向档案（联赛口径 gf/ga）→ 传 anchor_select 第7分项「攻防」
                        if _lg27 and _lg27.get('gf') is not None:
                            if _side27 == '主':
                                _tad_h27 = {'gf': _lg27.get('gf'), 'ga': _lg27.get('ga')}
                            else:
                                _tad_a27 = {'gf': _lg27.get('gf'), 'ga': _lg27.get('ga')}
                        _u27 = _kv.get('ucl') or {}
                        if _lg27:
                            print('     %s %s(%s): 联赛%s场 进%.2f/失%.2f ｜ 主%.2f/%.2f 客%.2f/%.2f ｜ xG代理%s(覆盖%.0f%%) ｜ 近50场 进%s/失%s'
                                  % (_side27, _cn27 or _en27, _en27, _lg27.get('n'), _lg27.get('gf'), _lg27.get('ga'),
                                     _lg27.get('home_gf') or 0, _lg27.get('home_ga') or 0,
                                     _lg27.get('away_gf') or 0, _lg27.get('away_ga') or 0,
                                     _lg27.get('xg'), _lg27.get('xg_cov') or 0,
                                     _lg27.get('r50_gf'), _lg27.get('r50_ga')))
                        else:
                            print('     %s %s(%s): ⚪无联赛数据（非五大）·仅欧冠实证' % (_side27, _cn27 or _en27, _en27))
                        if _u27:
                            print('        欧冠 %s场 进%.2f/失%.2f%s'
                                  % (_u27.get('n'), _u27.get('gf'), _u27.get('ga'),
                                     '  ⚠️' + _u27['note'] if _u27.get('note') else ''))
                    if _r27.get('home_expect') is not None:
                        print('     → 双向预期(联赛主客分离): 主 %.2f / 客 %.2f / 总 %.2f'
                              % (_r27['home_expect'], _r27['away_expect'], _r27['total_expect']))
                    # 🔴2026-10-21 数据隔离（用户「严禁数据外流造成其他数据污染」）:
                    #   blend 混入欧冠样本 → **仅欧冠场次可启用**；联赛场次只用联赛口径（否则 PSG/巴萨的
                    #   欧冠 2-3 场会污染其联赛预期 · 实测法甲/英超场次曾显示 w_ucl=0.273 = 外流）
                    _lcn27 = norm_league(league)
                    if _r27.get('blend_total') is not None and _lcn27 == '欧冠':
                        print('     → 双向预期(联赛+欧冠贝叶斯收缩 w_ucl=%s/%s·仅欧冠场次启用): 主 %.2f / 客 %.2f / 总 %.2f'
                              % ((_r27.get('blend_w') or {}).get('home'), (_r27.get('blend_w') or {}).get('away'),
                                 _r27['blend_home_expect'], _r27['blend_away_expect'], _r27['blend_total']))
                    elif _r27.get('blend_total') is not None:
                        print('     ⚪欧冠层已隔离（联赛=%s·非欧冠场次不混入欧冠样本·仅用联赛口径）' % _lcn27)
                    try:
                        _mkt27 = None
                        if isinstance(_lmkt, (int, float)):
                            _mkt27 = float(_lmkt) + float(_ucl_adj or 0)
                        _lam27 = (_tw.get('lambda_final') if isinstance(_tw, dict) else None)
                        _bl27 = _r27.get('blend_total') or _r27.get('total_expect')
                        _msg27 = []
                        if _mkt27 is not None:
                            _msg27.append('市场期望 E=%.2f' % _mkt27)
                        if _lam27 is not None:
                            _msg27.append('λ_final=%.2f' % float(_lam27))
                        if _bl27 is not None:
                            _msg27.append('攻防=%s' % _bl27)
                            if _mkt27 is not None:
                                _dv27 = float(_bl27) - _mkt27
                                _msg27.append('攻防−市场 %+.2f 球 %s' % (
                                    _dv27, '(⚠️差>0.5·两维分歧·以市场为准)' if abs(_dv27) > 0.5 else '(✅一致)'))
                        if _msg27:
                            print('     🔴对照: ' + ' ｜ '.join(_msg27))
                    except Exception:
                        pass
                    if _r27.get('ucl_note'):
                        print('     ' + _r27['ucl_note'])
                    print('     🔴纪律: 独立攻防维度（与伤停/ELO 同级）·可作 Step5 方向/Step6 量级交叉验证'
                          '·冲突以市场为准·永不反转 L2 硬核方向·欧冠样本<5 场禁作定量依据')
                else:
                    print('  ⚪球队双向攻防档案(N27): %s（三态）' % _r27.get('reason'))
        except Exception as _e27:
            print('  ⚪球队双向攻防档案(N27): %s（不阻断主流程）' % str(_e27)[:70])
    else:
        print('  ⚪球队双向攻防档案(N27): 未提供 --teams "主队,客队" → 不触发(三态)')
    # 🔴2026-10-24 固化判据②（用户指令·case265 实证）：对攻场量级上探·禁锁 2-3 球
    #   触发: 对手场均失球 >=1.8 且 双方合计场均进球 >=3.5
    #   动作: 量级区间上界上探至 5-6 球·候选池必含 4+ 球尾部（不因 goal_bins 4+球占比低而锁死）
    #   反例: case265 都灵vs蒙扎 蒙扎场均失2.0+合计3.8 → 实际 3:2(5球)·期望2.74低估2.26球
    #   🔴边界: 本条是球队级对攻特征·非全局大球上调（「大球低估」已于 2026-10-21 回测数据否决）
    try:
        if _n27_attack_up is not None:
            print('  🔴判据②对攻场(2026-10-24固化): %s' % _n27_attack_up)
            print('     → 执行要求: 量级上探·候选池必含 4+ 球尾部（禁锁 2-3 球）')
    except Exception:
        pass

    # ② 🔴🔴(D,M,T) 四要素联合象限 + joint_solver 锚（N23 **正式块**·V3.5.77·2026-10-13 用户方案§5·第一优先级）
    #    🔴2026-10-13 接入审计修（用户「严格检查新更新是否真正介入模型·接口是否正确·有断点」）:
    #      ① λ **五源由 Step6.5 注入口径**（market/table/line/pois/water）→ 消除「同场两套期望总进球」口径分裂
    #      ② 补传 ou_line(亚盘大小球线) + league(查表/D 三层校准) ③ 源数三态告警 ④ 异常显式 FAIL（不静默吞）
    #    ⚠️ 本块必须位于 Step6.5 之后（消费 _tw/_lmkt/_ltab）→ 故由原 L811 位置整块下移至此
    try:
        from joint_solver import joint_anchor as _n23_ja, fmt_report as _n23_fmt

        def _n23_fv(x):
            try:
                return float(x) if x not in (None, '') else None
            except Exception:
                return None
        _n23_argv = sys.argv
        _n23_eu = _n23_argv[_n23_argv.index('--eu') + 1] if '--eu' in _n23_argv else None
        if not _n23_eu:
            print('  ⚪ (D,M,T) 联合象限(N23): 缺 --eu → 不触发(三态)')
        else:
            # 🔴2026-10-20 修复(P1·静默降级): `locals().get` 绑定的是**此刻的 dict 快照**，
            #   之后定义的局部变量（如 `_n23_ht`）**永远取不到** → 半场推断静默三态（实跑抓）。
            #   → 保留 `_n23_g` 兼容既有调用（其所取变量均在定义前存在），
            #     新增 `_n23_loc(k)` **每次现取** locals()（供后定义变量使用）。
            #   ⚠️嵌套函数内的 locals() 只含自身参数 → 不可用于取外层局部变量；
            #     本块所需的 `_n23_ht` / `_dc` / `elo` / `_fav_spread` 与本块**同作用域**，直接按名引用。
            _n23_g = locals().get
            _n23_tw = _n23_g('_tw') or {}
            _n23_src = {}
            for _n23_k in ('market', 'table', 'line', 'pois', 'water'):
                _n23_vv = (_n23_g('_lmkt') if _n23_k == 'market' else
                           _n23_g('_ltab') if _n23_k == 'table' else
                           _n23_tw.get('lambda_' + _n23_k))
                _n23_f = _n23_fv(_n23_vv)
                if _n23_f is not None:
                    _n23_src[_n23_k] = _n23_f
            _n23_e = [float(x) for x in str(_n23_eu).split(',')]
            # 🔴V3.5.80 P9: 数据桥填充（spf 段若为欧亚源 → N23 方向输入以欧亚为准·竞彩仅对照）
            try:
                if _bridge and (_bridge.get('src_map') or {}).get('spf', '').startswith('欧亚'):
                    _bs_spf = (_bridge['sections'].get('spf') or [])
                    if _bs_spf:
                        _o9b = _bs_spf[-1][1]
                        if _o9b.get('胜') and _o9b.get('平') and _o9b.get('负'):
                            _n23_e = [float(_o9b['胜']), float(_o9b['平']), float(_o9b['负'])]
                            print('  🔴P9桥接: N23 方向源 ← %s' % _bridge['src_map']['spf'])
            except Exception as _e9n:
                print('  ⚪P9桥接(N23): %s' % type(_e9n).__name__)
            # 🔴V3.5.80 P8 纵向信号——**延后**到 _n23_cs（波胆全档）就绪之后再算
            #   2026-10-20 复查修(P1-1): 原实现在此即调 vertical_for(end_label='正式执行') 但不传 end_*，
            #   实际末点 = 快照末点 → **标签不实**；且 _n23_cs 在下方才拉取（时序在前）。
            #   🔴未照抄报告建议「直接传 _n23_cs」: market_inputs 降级链优先「快照首时点」，
            #   拿它当末点 = 首 vs 首 → chg≈0 → E10 完全失效。改为「仅当来源=实时1xbet 才作末点」。
            _n23_vert = None
            _n23_lg = (_n23_argv[2] if len(_n23_argv) > 2 and not _n23_argv[2].startswith('--') else None)
            # 🔴V3.5.79 P4-4: N23 参数回退——漏传 --handi/--o25/--u25 时从快照(_sn9)自动补
            #   （否则漏传 → handi=None 触发 P4-1 空锚 / o25=None 触发 B 档降级）
            _n23_hn = _n23_fv(_n23_g('_hn'))
            _n23_o25 = _n23_fv(_n23_g('_o25n'))
            _n23_u25 = _n23_fv(_n23_g('_u25n'))
            _n23_s9 = _n23_g('_sn9') or {}
            _n23_f9 = _n23_s9.get('first') or {}            # 🔴快照首点时点(extract/file/event_id 都在 first)
            _n23_ex9 = _n23_f9.get('extract') or {}
            try:
                if (_n23_hn is None and _n23_ex9.get('ah')
                        and re.search(r'让([+\-][0-9.]+)', str(_n23_ex9['ah']))):
                    _n23_hn = float(re.search(r'让([+\-][0-9.]+)', str(_n23_ex9['ah'])).group(1))
                if (_n23_o25 is None and _n23_ex9.get('o25')
                        and re.search(r'O([\d.]+)', str(_n23_ex9['o25']))):
                    _n23_o25 = float(re.search(r'O([\d.]+)', str(_n23_ex9['o25'])).group(1))
            except Exception:
                pass
            # 🔴V3.5.79 P1/P2/P3 数据源适配（方案假设的 _ah/_raw_cs/_raw_btts 在实际 calc_all 中不存在）:
            #   ① 波胆全表 + BTTS + **均衡档水位**: 由 _sn9 的 file+event_id 回读原始快照 raw_1xbet
            #      （快照 _extract 只留 CS 最低一条 → 不回读则 P2 永远空转 = 存在≠活跃）
            #   ② 🔴2026-10-17 审查修正: P1 让球水位**必须取均衡线档**（铁律 case229/234「禁把深档当让球盘解读」）
            #      原用 _sn9.extract.ah（= _extract 的「主客赔率最接近档」·实测常为深档：拉科场 hdp=-1.00 Δ=1.64
            #      且已自带「⚠️均衡线缺失」标注）→ 会把它当均衡盘解读 → 在 74% 非均衡场次给出系统性「弱」判定
            #      → 改为扫 Spread **全档**·取 |主−客| 最小且 ≤0.25 者为**真均衡档** → 无则 None（标缺·P1 不采用）
            _n23_ah_wh, _n23_ah_wa, _n23_eq_hdp, _n23_eq_scan = None, None, None, 0
            _n23_cs, _n23_btts = {}, {}
            # 🔴P10(2026-10-25): 市场三源矩阵所需的全档容器（与 _n23_cs 同一 raw/时点·口径一致）
            _n23_ou_full = {}                                  # {line: (over, under)} 大小球全档
            _n23_tt_full = {'home': {}, 'away': {}}            # Team Total 主/客全档
            _n23_ah_full = []                                  # [(hdp, home, away)] 让球全档
            try:
                _f9 = _n23_f9.get('file')
                _eid9 = _n23_f9.get('event_id')
                _p9 = None
                if _f9:
                    _p9 = str(_f9) if os.path.isabs(str(_f9)) else os.path.join(
                        'data', 'tmp', 'snapshots', os.path.basename(str(_f9)))
                    if os.path.exists(_p9):
                        _sd9 = json.load(open(_p9, encoding='utf-8'))
                        for _g9 in (_sd9.get('games') or []):
                            if _eid9 is None or _g9.get('event_id') == _eid9:
                                _rb9 = (_g9.get('raw_1xbet') or {})
                                for _b9 in ((_rb9.get('bookmakers') or {}).get('1xbet') or []):
                                    _nm9 = str(_b9.get('name') or '')
                                    if _nm9 == 'Correct Score':
                                        for _o9 in (_b9.get('odds') or []):
                                            _lb9 = str((_o9 or {}).get('label') or '').strip()
                                            _vv9 = _n23_fv((_o9 or {}).get('odds'))
                                            # 🔴占位档(赔率=100)必须剔除·否则去水期望虚高(与 cs 加固同源)
                                            if _lb9 and _vv9 is not None and 1 < _vv9 < 100:
                                                _n23_cs[_lb9] = _vv9
                                    elif _nm9 == 'Totals':
                                        # 🔴P10: 大小球全档（半档用于生存函数差分·整数/quarter 仅校验）
                                        for _o9 in (_b9.get('odds') or []):
                                            _hl9 = _n23_fv((_o9 or {}).get('hdp'))
                                            _ov9 = _n23_fv((_o9 or {}).get('over'))
                                            _un9 = _n23_fv((_o9 or {}).get('under'))
                                            if _hl9 is not None and _ov9 and _un9:
                                                _n23_ou_full[_hl9] = (_ov9, _un9)
                                    elif _nm9 in ('Team Total Home', 'Team Total Away'):
                                        # 🔴P10: 主/客各自进球边缘（仅作矩阵形状先验）
                                        _tk9 = 'home' if _nm9.endswith('Home') else 'away'
                                        for _o9 in (_b9.get('odds') or []):
                                            _hl9 = _n23_fv((_o9 or {}).get('hdp'))
                                            _ov9 = _n23_fv((_o9 or {}).get('over'))
                                            _un9 = _n23_fv((_o9 or {}).get('under'))
                                            if _hl9 is not None and _ov9 and _un9:
                                                _n23_tt_full[_tk9][_hl9] = (_ov9, _un9)
                                    elif _nm9 == 'Both Teams To Score':
                                        _o9 = (_b9.get('odds') or [{}])[0]
                                        _n23_btts = {'yes': _n23_fv((_o9 or {}).get('yes')),
                                                     'no': _n23_fv((_o9 or {}).get('no'))}
                                    elif _nm9 == 'Spread':
                                        _best9, _nsp9 = None, 0
                                        for _o9 in (_b9.get('odds') or []):
                                            _hh9 = _n23_fv((_o9 or {}).get('home'))
                                            _aa9 = _n23_fv((_o9 or {}).get('away'))
                                            if _hh9 is None or _aa9 is None:
                                                continue
                                            _nsp9 += 1
                                            # 🔴P10: 收集让球**全档**（矩阵 NNLS 需全部线·非仅均衡档）
                                            try:
                                                _n23_ah_full.append(
                                                    (float((_o9 or {}).get('hdp')), _hh9, _aa9))
                                            except (TypeError, ValueError):
                                                pass
                                            if _best9 is None or abs(_hh9 - _aa9) < abs(_best9[1] - _best9[2]):
                                                _best9 = ((_o9 or {}).get('hdp'), _hh9, _aa9)
                                        _n23_eq_scan = _nsp9
                                        # 🔴仅 |主−客|≤0.25 才算均衡盘口（≈1.9/1.9）·否则标缺不采用
                                        if _best9 is not None and abs(_best9[1] - _best9[2]) <= 0.25:
                                            _n23_eq_hdp = _best9[0]
                                            _n23_ah_wh, _n23_ah_wa = _best9[1], _best9[2]
                                break
            except Exception:
                pass
            # 🔴V3.5.79 修复(2026-10-17 审计): 原 P1/P2/P3 数据源**只认 prestep 快照**(_sn9)
            #   → 未跑 prestep 的常规分析中 波胆/BTTS/均衡水 恒为空 = 三项新功能永久空转(存在≠活跃)
            #   修复: 无快照时回退到**当场实时 1xbet 全市场**(--odd-event/--event 或快照 event_id)
            _n23_p1src = '快照' if (_n23_cs or _n23_ah_wh is not None) else None
            if not _n23_cs and _n23_ah_wh is None:
                _oe9 = None
                for _kk9 in ('--odd-event', '--event'):
                    if _kk9 in sys.argv and sys.argv.index(_kk9) + 1 < len(sys.argv):
                        _oe9 = sys.argv[sys.argv.index(_kk9) + 1]
                        break
                if not _oe9:
                    _oe9 = _n23_f9.get('event_id')
                # 🔴2026-11-01 最后一环：按**队名**定位 eventId
                #   原 _oe9 只来自 --event / 快照 → 两者皆无时 `if _oe9:` 直接拦住
                #   整段 → 全档/CS/BTTS 全空 → P10 恒「三源不齐」→ 误判「源不可用」
                if not _oe9:
                    try:
                        import market_inputs as _MIm9
                        _oe9, _slg9 = _MIm9._locate_event(_hT, _aT)
                        if _oe9:
                            print('     🔴按队名定位 eventId=%s（%s）→ 实时 1xbet 补齐全档'
                                  % (_oe9, _slg9 or '?'))
                    except Exception as _elc9:
                        _oe9 = None
                        print('     ⚪按队名定位失败: %s（三态）' % type(_elc9).__name__)
                if _oe9:
                    # 🔴2026-10-17 封装: 改由统一入口 market_inputs（占位档剔除/均衡档 Δ≤0.25 内建）
                    try:
                        import market_inputs as _MImod9
                        _mi9 = _MImod9.resolve(home=_hT, away=_aT, event_id=_oe9)   # 🔴2026-11-01 补 home/away（原只传 event_id → 队名定位不触发 → P10 恒三态）
                        if _mi9.get('cs'):
                            _n23_cs = _mi9['cs']
                        if _mi9.get('btts'):
                            _n23_btts = _mi9['btts']
                        # 🔴2026-11-01 无快照时用 _mi9 补**全档**（原 ou_full/ah_full 只从
                        #   快照 raw_1xbet 解析 → 没快照就全空 → P10「三源不齐」恒触发）
                        if not _n23_ou_full and _mi9.get('totals'):
                            for _t9 in (_mi9['totals'] or []):
                                try:
                                    _hl9b = _t9.get('hdp')
                                    _ov9b, _un9b = _t9.get('over'), _t9.get('under')
                                    if _hl9b is not None and _ov9b and _un9b:
                                        _n23_ou_full[float(_hl9b)] = (float(_ov9b), float(_un9b))
                                except Exception:
                                    continue
                        if not _n23_ah_full and _mi9.get('spread'):
                            for _s9 in (_mi9['spread'] or []):
                                try:
                                    _h9b = _s9.get('hdp')
                                    _hh9, _aa9 = _s9.get('home'), _s9.get('away')
                                    if _h9b is not None and _hh9 and _aa9:
                                        _n23_ah_full.append((float(_h9b), float(_hh9), float(_aa9)))
                                except Exception:
                                    continue
                        # 🔴2026-11-01 Team Total 全档（R11 零封判定·原 _mi9 没补 → R11「被零封 缺」）
                        if not (_n23_tt_full.get('home') or _n23_tt_full.get('away')):
                            for _sd9, _kk9 in (('home', 'tt_h'), ('away', 'tt_a')):
                                for _ln9, _v9 in (_mi9.get(_kk9) or {}).items():
                                    try:
                                        _n23_tt_full[_sd9][float(_ln9)] = (float(_v9[0]), float(_v9[1]))
                                    except Exception:
                                        continue
                        if _n23_ou_full or _n23_ah_full:
                            print('     🔴全档补齐(_mi9): 大小球 %d 档 ｜ 让球 %d 档 ｜ '
                                  'TeamTotal 主%d/客%d 档'
                                  % (len(_n23_ou_full), len(_n23_ah_full),
                                     len(_n23_tt_full.get('home') or {}),
                                     len(_n23_tt_full.get('away') or {})))
                        _n23_eq_scan = _mi9.get('eq_scan') or 0
                        _eq9 = _mi9.get('eq')
                        if _eq9:
                            _n23_eq_hdp = _eq9.get('hdp')
                            _n23_ah_wh, _n23_ah_wa = _eq9.get('home'), _eq9.get('away')
                        if _n23_cs or _n23_ah_wh is not None:
                            _n23_p1src = _mi9['src'].get('cs') or ('实时1xbet(%s)' % _oe9)
                    except Exception as _ex9:
                        _n23_p1src = '统一入口拉取失败(%s)' % type(_ex9).__name__
            _n23_p1tag = ('均衡档 hdp=%s' % _n23_eq_hdp if _n23_ah_wh
                          else ('⚪无均衡档(扫%d档)→P1不采用' % _n23_eq_scan if _n23_eq_scan
                                else '⚪无快照/无Spread→P1不采用'))
            print('  🔴V3.5.79 数据源[%s]: 波胆 %d 档 · BTTS %s · 让球均衡水 %s/%s [%s]'
                  % (_n23_p1src or '无', len(_n23_cs), ('有' if _n23_btts else '无'),
                     _n23_ah_wh, _n23_ah_wa, _n23_p1tag))
            # 🔴🔴2026-10-31 复盘固化（case301/302 实抓）: **--handi 口径防线**
            #   两场都把「竞彩让球（固定 ±1）」当欧盘均衡线传入:
            #     case301 比利亚雷亚尔 欧盘 -1.25 → 传 -1.0
            #     case302 里尔        欧盘 **平手盘 +0.00** → 传 -1.0（**差 1.0 档·平手盘被当深盘**）
            #   后果: 净胜档 M 域 / P1 让球水位上盘覆盖 / 受让场禁主胜锚 / R10-8 方向-亚盘一致性 全部失真
            #   铁律已有（P13.1/P16「--handi 必须欧盘均衡线」）但**无运行时校验** → 本次补上
            _handi_verified = False   # 🔴handi 是否已被欧盘均衡线确认（决定矛盾时该改谁）
            if handi not in (None, '') and _n23_eq_hdp is not None:
                try:
                    _h_u, _h_f = float(handi), float(_n23_eq_hdp)
                    _hd = abs(_h_u - _h_f)
                    if _hd >= 0.5:
                        _ico = '🔴🔴' if _hd >= 1.0 else '🔴'
                        print('  %s --handi 口径校验: 传入 %.2f vs **欧盘均衡线 %.2f** → 相差 %.2f 档'
                              % (_ico, _h_u, _h_f, _hd))
                        print('       → 疑似把**竞彩让球（固定 ±1）**当欧盘均衡线（P13.1/P16 铁律禁）')
                        # 🔴2026-10-31 用户追问「还会不会再犯」→ 从**告警**升级为**自动纠正**
                        #   机理: 均衡线=市场定价（权威）·错误 handi 会污染 净胜档M域/让球水位P1/
                        #         受让禁主胜锚/R10-8方向-亚盘一致性 四层 → 危害远大于「尊重错误输入」
                        #   顺序保险: 本校验在 `joint_anchor`(L2369) **之前** → 纠正对 N23 生效
                        print('       → 🔴 **已自动改用欧盘均衡线 %+.2f**（原传入 %+.2f 留痕·禁污染四层判定）'
                              % (_h_f, _h_u))
                        handi = ('%g' % _h_f)
                        # 🔴2026-11-03 端到端实测修（真断链）：原写 `_n23_hn = handi`（**str**）
                        #   → joint_solver._propagate L578 `handi < -0.05` 抛
                        #     TypeError: '<' not supported between 'str' and 'float'
                        #   → **N23 整段崩溃** → 锚定层/量级分布/宽池/tail_bins 全部不消费（伪消费）
                        _n23_hn = float(_h_f)
                        _handi_verified = True   # 已改用均衡线 → 同样权威
                        #   原只改 handi → 纠正对 N23 零影响（实测发现·防「改了没效果」）
                    else:
                        print('  ✅ --handi 口径校验: 传入 %.2f ≈ 欧盘均衡线 %.2f（差 %.2f 档·合规）'
                              % (_h_u, _h_f, _hd))
                        _handi_verified = True   # handi 权威（市场定价确认）
                except (TypeError, ValueError):
                    pass
            elif handi not in (None, ''):
                # 🔴洞2 堵法: 原「⚪ 无法比对」等于不校验（case301 类残缺场次照犯）→ 升级为风险提示
                print('  ⚪🔴 --handi 口径校验: **快照无均衡线 → 无法校验**（三态·不等于无风险）')
                print('       → 若传入的是竞彩让球（±1）→ 净胜档M域/让球水位P1/受让禁主胜锚 全部失真')
                print('       → 解法: 先跑 `pipeline`/`snapshot_save` 存快照 → 本校验即可自动比对并纠正')
            # 🔴🔴2026-10-31 防线扩展（case301 复现·参数传反 → 交集池空 → N07b 缺块 → pipeline EXIT=1）:
            #   `--eu 3.545,3.914,1.946`（客队热门）配 `--handi -1.25`（主队让球）→
            #   D 方向=客胜 但 M 净胜档=[+1,+2]（主队净胜）→ 两域互斥 → 交集必然为空 → 主锚 None。
            #   全程无断言发现这个自相矛盾（静默失败·只在末尾报「池为空」）。
            #   机理: 让球方理应=被看好方 → 矛盾则告警 + 自动翻转符号（原值留痕）。
            try:
                _oh, _od, _oa = [float(x) for x in str(eu).split(',')[:3]]
                _fav = 'H' if (_oh <= _od and _oh <= _oa) else ('A' if _oa <= _od else 'D')
                _hf2 = float(handi)
                if (_fav == 'A' and _hf2 < -0.01) or (_fav == 'H' and _hf2 > 0.01):
                    _hname = '主' if _hf2 < 0 else '客'
                    if _handi_verified:
                        # 🔴handi 已被欧盘均衡线确认 → **handi 权威**·矛盾出在 --eu
                        print('  🔴🔴 --eu 疑似**顺序传反**: 1x2 热门=%s（%.3f/%.3f/%.3f）vs 亚盘 %s让 %.2f 球'
                              % (_fav, _oh, _od, _oa, _hname, abs(_hf2)))
                        print('       → 亚盘已由快照均衡线确认（✅ 权威）→ **不改 handi**，请核对 --eu 顺序')
                        print('       → 若 ev 正确则 N23 交集池将为空（方向与净胜档互斥）·请复核盘口源')
                    else:
                        print('  🔴🔴 --handi 方向矛盾: eu 热门=%s（%.3f/%.3f/%.3f）但 handi=%+.2f（%s让球）'
                              % (_fav, _oh, _od, _oa, _hf2, _hname))
                        print('       → 无均衡线佐证 → 以 1x2 为准·自动翻转符号 %+.2f → %+.2f' % (_hf2, -_hf2))
                        handi = ('%g' % (-_hf2))
                        _n23_hn = float(-_hf2)   # 🔴2026-11-03 修：原为 str → N23 比较崩溃
                elif _fav != 'D':
                    print('  ✅ handi 方向与 eu 热门一致（热门=%s · handi=%+.2f）' % (_fav, _hf2))
            except Exception as _e2:
                print('  ⚪ handi 方向一致性校验跳过（%s）' % str(_e2)[:50])
            # 🔴2026-10-25 P10 市场三源比分分布矩阵（用户方案《P10 补丁包》·纯市场·全档反推）
            #   逻辑链: 大小球全档→进几个球 ｜ 让球全档→赢几个球 ｜ 波胆→怎么进
            #   三源齐全(决策门: OU半档≥3 / AH≥4 且边缘自洽 / CS≥15) → 矩阵为主排序基线(E0)
            #   缺源 → 三态标注 + 回退 P5/泊松（禁臆造·禁缺档硬差分）
            _n23_mm = None
            # 🔴P10 灰度开关（方案 §七.9）: fair_model.json 的 p10_market_matrix = on / off / auto
            #   auto（默认）= 按决策门自动启用（三源齐全且矩阵 health=ok）
            #   off = 完全停用（等价 V3.5.80 旧行为·可用于一键回滚）
            #   on  = 即使决策门未过也按矩阵弱排序（会打印警告·矩阵 health 仍决定 E0 是否生效）
            _p10_mode = 'auto'
            try:
                _fp10 = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'p10_config.json')
                if os.path.exists(_fp10):
                    _p10_mode = str(json.load(open(_fp10, encoding='utf-8'))
                                    .get('p10_market_matrix') or 'auto').strip().lower()
            except Exception:
                _p10_mode = 'auto'
            try:
                import market_distribution as _md10
                _jc810 = None
                try:
                    from calc_match import parse_txt as _pt10
                    _secs10 = _pt10(open(txt_path, encoding='utf-8').read()) or {}
                    _zjq10 = _secs10.get('zjq') or []
                    if _zjq10:
                        _odd10 = _zjq10[-1][1] or {}
                        _vals10 = [_n23_fv(_odd10.get(_k10))
                                   for _k10 in ('0', '1', '2', '3', '4', '5', '6', '7+')]
                        if all((v is not None and v > 1) for v in _vals10):
                            _jc810 = [float(v) for v in _vals10]
                except Exception:
                    _jc810 = None
                _n23_mm = _md10.infer_from_parts(
                    ou_full=_n23_ou_full, ah_full=_n23_ah_full, cs_full=_n23_cs,
                    oh=_n23_e[0], od=_n23_e[1], oa=_n23_e[2],
                    tt_full=_n23_tt_full, jc_goal8=_jc810,
                    btts=(_n23_btts or None))          # 🔴P10-FINAL: R11 直盘需要 BTTS 赔率
                if _p10_mode == 'off':
                    _n23_mm = None
                    print('  ⚪市场矩阵(P10): 开关=off（fair_model.json·一键回滚）→ 不启用·走 P5/泊松链路')
                elif _p10_mode == 'on' and not (_n23_mm or {}).get('ok'):
                    print('  ⚠️市场矩阵(P10): 开关=on（决策门未过·health=%s）→ 仍传矩阵但仅弱排序'
                          % ((_n23_mm or {}).get('matrix') or {}).get('health'))
                else:
                    print('  🔴市场矩阵(P10): 开关=%s' % _p10_mode)
                for _l10 in _md10.fmt_block(_n23_mm).split('\n'):
                    print('  ' + _l10)
            except Exception as _e10:
                print('  ⚪市场矩阵(P10): %s → 回退 P5/泊松链路（不阻断主流程）'
                      % type(_e10).__name__)
                _n23_mm = None
            # 🔴V3.5.80 P8 正式块（2026-10-20 复查修 P1-1：位置后移 + 末点诚实标注）
            try:
                from snapshot_save import vertical_for as _vfor9
                _vh, _va = _n23_g('_th9'), _n23_g('_ta9')
                _ve9 = None
                for _vk9 in ('--odd-event', '--event'):
                    if _vk9 in sys.argv and sys.argv.index(_vk9) + 1 < len(sys.argv):
                        _ve9 = sys.argv[sys.argv.index(_vk9) + 1]
                        break
                # 🔴末点: 仅当波胆源为**实时 1xbet**（非快照）时，才把它当「正式执行时点」
                _end_cs9 = None
                if _n23_cs and '实时' in str(_n23_p1src or ''):
                    _end_cs9 = _n23_cs
                _endl9 = ('正式执行(实时1xbet)' if _end_cs9
                          else '快照末点(正式执行全档未接入·仅快照)')
                if _vh and _va:
                    _n23_vert = _vfor9(_vh, _va, end_cs=_end_cs9, end_label=_endl9,
                                       event_id=_ve9)
                    if not (_n23_vert or {}).get('count'):
                        print('  ⚪P8纵向: %s ｜ 末点源=%s'
                              % (' '.join(_n23_vert.get('note') or ['三态']), _endl9))
                    else:
                        print('  🔴P8纵向信号: %s ｜ %s ｜ 末点源=%s'
                              % (_n23_vert.get('span'), ' '.join(_n23_vert.get('note') or []), _endl9))
                        _cv9 = _n23_vert.get('cs_vert') or {}
                        if _cv9:
                            _t9 = sorted(_cv9.items(), key=lambda x: -x[1].get('chg', 0))[:3]
                            print('     波胆纵向 TOP3: %s'
                                  % ", ".join('%s(%+.0f%%)' % (k, v['chg'] * 100) for k, v in _t9))
                        _av9 = _n23_vert.get('ah_vert') or {}
                        if _av9:
                            print('     让球升降: %s (line %+.2f→%+.2f·主水 %.2f→%.2f·净胜档%+d)'
                                  % (_av9.get('combo'), _av9.get('line0') or 0, _av9.get('line1') or 0,
                                     _av9.get('w0') or 0, _av9.get('w1') or 0, int(_av9.get('shift') or 0)))
                        _ov9 = _n23_vert.get('ou_vert') or {}
                        if _ov9:
                            print('     大小球水位: %s (线 %.2f→%.2f·大球水 %.2f→%.2f·置信%+d档)'
                                  % (_ov9.get('dir'), _ov9.get('line0') or 0, _ov9.get('line1') or 0,
                                     _ov9.get('over0') or 0, _ov9.get('over1') or 0,
                                     int(_ov9.get('conf_step') or 0)))
                else:
                    print('  ⚪P8纵向: txt 未提取到队名 → 不启用(三态)')
            except Exception as _e8v:
                print('  ⚪P8纵向: 异常→%s（不阻断主流程）' % type(_e8v).__name__)
                _n23_vert = None
            # 🔴2026-10-20 P6（用户指令「严格依赖市场信息决定·不依赖泊松」）:
            #   --step5-dirs  LLM 判定的最终方向（含平局并列）→ 平局谱系入池（禁手工塞 1:1）
            #   --jc-cs       竞彩比分盘去水 P_i（"1:1=0.130,2:1=0.089"）→ E7 证据
            _n23_st5 = [x.strip() for x in (_ov.get('--step5-dirs') or '').replace('，', ',').split(',')
                        if x.strip()]
            _n23_jc = {}
            for _kv in (_ov.get('--jc-cs') or '').replace('，', ',').split(','):
                if '=' in _kv:
                    _k, _v = _kv.split('=', 1)
                    try:
                        _n23_jc[_k.strip().replace('-', ':')] = float(_v)
                    except ValueError:
                        pass
            # 🔴2026-10-20 P6-g ①: jc-cs 未传 → 自动从竞彩 txt 比分盘去水构造
            #   根因: 竞彩CS 数据本就在 txt 里(calc_match 已解析)·却要人工另传 → 漏传即静默缺席 E7
            _n23_jc_src = '显式传参'
            _jc_was_empty = not _n23_jc
            if not _n23_jc:
                # 🔴契约: _extract_cs_bqc 返回 (cs_csv, bq_csv) **字符串**（非 dict）
                _jinv, _jerr = {}, None
                try:
                    _jc_csv = (_extract_cs_bqc(txt_path)[0] or '')
                    for _tok in _jc_csv.replace('，', ',').split(','):
                        if '=' not in _tok:
                            continue
                        _jk, _jv = _tok.split('=', 1)
                        try:
                            _jf = float(_jv)
                        except (TypeError, ValueError):
                            continue
                        if 1.0 < _jf < 100.0:
                            _jinv[_jk.strip().replace('-', ':')] = 1.0 / _jf
                except Exception as _je:
                    _jerr = str(_je)
                _jsum = sum(_jinv.values())
                if _jsum > 0 and len(_jinv) >= 6:
                    _n23_jc = {k: v / _jsum for k, v in _jinv.items()}
                    _n23_jc_src = '竞彩txt自动去水(%d档)' % len(_n23_jc)
                elif _jerr:
                    print('  ⚠️竞彩CS自动接入失败(异常): %s → E7 不参与' % _jerr)
                else:
                    print('  ⚠️竞彩CS自动接入失败: txt 比分盘仅 %d 档(<6) → E7 不参与'
                          % len(_jinv))
            if _n23_jc and _n23_jc_src != '显式传参':
                print('  🔴竞彩CS自动接入(P6): %s → E7 证据可用（无需再手传 --jc-cs）' % _n23_jc_src)
            # 🔴2026-10-20 P6-g ②: 方向未透传必须显式告警（原静默退化·用户不可见）
            if not _n23_st5:
                print('  ⚠️方向未透传(--step5-dirs): 平局谱系不进池 → 锚可能缺 1:1/0:0')
                print('     🔴复核要求(2026-10-20 复查): 若本场方向含平局并列，**必须**补传后重跑：')
                print('        calc_all.py <txt> <联赛> ... --step5-dirs "平局,主胜"   ← 方向按本场实际填')
                print('     ▪ 未补传而主锚出现 1:1/0:0 → 属「缺池硬凑」·不得直接落盘')
            # 🔴2026-10-20 P7: 半全场自动接入（同源 txt·无需手传）
            _n23_ht = None
            try:
                _bq_csv = (_extract_cs_bqc(txt_path)[1] or '')
                if _bq_csv:
                    _n23_ht = {}
                    for _tok in _bq_csv.replace('，', ',').split(','):
                        if '=' in _tok:
                            _hk, _hv = _tok.split('=', 1)
                            try:
                                _n23_ht[_hk.strip()] = float(_hv)
                            except (TypeError, ValueError):
                                pass
                    if len(_n23_ht) < 6:
                        _n23_ht = None
                if _n23_ht:
                    print('  🔴半全场自动接入(P7): %d 格 → E9 证据可用（无需手传）' % len(_n23_ht))
                else:
                    print('  ⚪半全场不可用(txt 无半全场或 <6 格) → E9 不参与')
            except Exception as _he:
                print('  ⚠️半全场解析失败: %s → E9 不参与' % _he)
            if _n23_st5 or _n23_jc:
                print('  🔴市场信号透传(P6): 方向=%s · 竞彩CS=%d 档（%s）'
                      % ('+'.join(_n23_st5) or '未传', len(_n23_jc),
                         _n23_jc_src if _n23_jc else '未接入·E7 不参与'))
            # ══════════════════════════════════════════════════════════════
            # 🔴V3.5.87 量级确定层（用户 2026-11-02 指令「方法二·先定量级再选比分」）
            #   「量级的确定也要依赖市场三源和六档分级」
            #   「方法一不用·禁止限制量级上下限」→ 本层只定**档中心+优先范围**，
            #     档外比分仅**降权**（1球×0.55 / 2球×0.25 / ≥3球×0.10），**不排除**
            #   315 场实证必要性：主锚总球 σ=0.77 vs 真实 σ=1.71
            #     （真实 4+ 球 44.4% 而主锚只 2.0%·真实 3+ 球场次里 49.2% 主锚 ≤2 球）
            # ══════════════════════════════════════════════════════════════
            _n23_tb = None
            try:
                from magnitude_band import magnitude_band as _mbg, fmt as _mbfmt
                _tb_p52 = None
                _tb_line = None
                try:
                    from big_pool_policy import level_from_line as _lvfl2
                    for _lck in ('line_eq', 'ou_line', 'line'):
                        try:
                            _v = _n23_tw.get(_lck)
                            if _v is not None:
                                _tb_line = float(_v)
                                break
                        except Exception:
                            pass
                    _tb_p52 = _lvfl2(_tb_line, _n23_o25)
                except Exception:
                    _tb_p52 = None
                # 🔴V3.5.89: cs_full 欧盘 1xbet 波胆优先·**缺时回退竞彩波胆反推赔率**
                #   （否则欧盘波胆缺失 → 厚尾波胆线索恒三态·竞彩 22 档明明可用 = 覆盖缺口）
                try:
                    _n23_cs_full9 = _n23_cs or {
                        str(_k9): (1.0 / _v9) for _k9, _v9 in (_n23_jc or {}).items()
                        if _v9 and 0 < float(_v9) < 1}
                except Exception:
                    _n23_cs_full9 = _n23_cs or None
                _n23_tb = _mbg(mm=_n23_mm, p52=_tb_p52,
                               o25=_n23_o25, u25=_n23_u25,
                               lam=_n23_fv(_n23_tw.get('lambda_final')),
                               line=_tb_line, handi=_n23_hn,
                               cs_full=_n23_cs_full9)   # 🔴V3.5.90 厚尾判据收敛·premium 单条（欧盘优先·竞彩回退）
                print('  🔴量级分布(V3.5.88·分布驱动·方法二·禁硬上下限): %s'
                      % _mbfmt(_n23_tb))
                try:
                    from magnitude_band import dist_line as _mbdist
                    _dl = _mbdist(_n23_tb)
                    if _dl:
                        print('    ' + _dl)
                except Exception:
                    pass
                # 🔴V3.5.90 厚尾判据收敛输出（2026-11-03 评审修复·唯一判据 premium·观察期标注级）
                # 🔴V3.5.90 评审修复: 判据仅 premium≥2.0·其余线索留痕·O-TAIL 标注级观察期（只打印不动作）
                try:
                    _tl_sig = (_n23_tb.get('tail') or {})
                    _tl_flag = _tl_sig.get('flag')
                    if _tl_flag and _tl_flag != '三态':
                        print('  🔴🔴厚尾三线索(V3.5.90): %s ｜ P(≥5)=%s P(≥6)=%s ｜ '
                              '波胆尾部=%s ｜ 溢价=%s ｜ 让球净胜=%s'
                              % (_tl_flag,
                                 ('%.0f%%' % (_tl_sig.get('p5_ge') * 100)) if _tl_sig.get('p5_ge') is not None else 'n/a',
                                 ('%.0f%%' % (_tl_sig.get('p6_ge') * 100)) if _tl_sig.get('p6_ge') is not None else 'n/a',
                                 ('%.0f%%' % (_tl_sig.get('cs_tail_ratio') * 100)) if _tl_sig.get('cs_tail_ratio') is not None else 'n/a',
                                 ('%.1f×' % _tl_sig.get('tail_premium')) if _tl_sig.get('tail_premium') is not None else 'n/a',
                                 ('%+.1f' % _tl_sig.get('margin_m')) if _tl_sig.get('margin_m') is not None else 'n/a'))
                        for _ntln in (_tl_sig.get('notes') or []):
                            print('     %s' % _ntln)
                        if _tl_flag in ('厚尾', '强厚尾'):
                            print('     🔴O-TAIL 标注(V3.5.90观察期): 建议主/次锚覆盖 ≥5球谱系·当前不动作（观察 ≥20 场后复核）')
                except Exception:
                    pass
                for _ntb in (_n23_tb.get('notes') or []):
                    print('     %s' % _ntb)
                _tb_tail = (_n23_tb.get('tail_bins') or [])
                print('     🔴尾部档(P(k)≥5%%·宽池必含·不占锚位): %s'
                      % (('/'.join('%d球' % k for k in _tb_tail)) or '无'))
                print('     比分权重=分布密度比 0.35+0.65×(p[k]/峰值)（不排除·最低 0.35）')
            except Exception as _etb:
                import traceback as _trb
                print('  ⚪量级档: %s（三态·回退原排序）' % type(_etb).__name__)
                print('    %s' % _trb.format_exc().splitlines()[-1][:200])
            _n23_r = _n23_ja(_n23_e[0], _n23_e[1], _n23_e[2],
                             handi=_n23_hn, o25=_n23_o25,
                             u25=_n23_u25,
                             ou_line=_n23_fv(_n23_tw.get('lambda_line')),
                             # 🔴V3.5.91: P52 分级必须用**盘口均衡线**（机构直接定价），
                             #   禁拿 E[T]/λ 顶替（N24 校准 +0.67 会把分级虚抬一档）
                             line_eq=_n23_fv((_n23_tw.get('line_fair')
                                              or _n23_tw.get('line_close')
                                              or _n23_tw.get('line_open')
                                              or _n23_tw.get('lam_final'))),
                             league=_n23_lg, src_lam=(_n23_src or None),
                             lambda_final=_n23_fv(_n23_tw.get('lambda_final')),
                             totals_bin=_n23_tw.get('totals_bin'),
                             ah_wh=_n23_ah_wh, ah_wa=_n23_ah_wa,
                             cs_odds=(_n23_cs or _n23_cs_full9 or None),
                             btts_yes=(_n23_btts or {}).get('yes'),
                             btts_no=(_n23_btts or {}).get('no'),
                             step5_dirs=(_n23_st5 or None),      # 🔴P6 方向透传
                             jc_cs=(_n23_jc or None),           # 🔴P6 竞彩CS证据
                             htft=(_n23_ht or None),            # 🔴P7 半全场证据
                             vert=_n23_vert,                    # 🔴P8 纵向信号
                             t_band=_n23_tb,                    # 🔴V3.5.87 量级档（方法二）
                             tad_h=_tad_h27, tad_a=_tad_a27,    # 🔴P36: N27 攻防（防死代码复发）
                             second_min_goals=_bp_need_second,   # 🔴2026-11-01 R-ANCHOR-BIG 次锚上探（原只打印不动作）
                             def_dual=_def_dual,                 # 🔴2026-11-03 O-BIG-1 宽池扩 6 球
      first_min_goals=_bp_need_first,     # 🔴2026-11-01 P52 主锚下限（分级驱动·原只约束次锚）
      market_matrix=(_n23_mm if ((_p10_mode == 'on')
                                                or (_n23_mm or {}).get('ok')) else None))  # 🔴P10+R10: 传**完整 mm**（R10 需 pT/pM）
            print('  ' + '-' * 66)
            print('  🔴🔴(D,M,T) 四要素联合象限 + 锚（N23·方案 V3.5.77·第一优先级）')
            print('  ' + '-' * 66)
            print('  ' + _n23_fmt(_n23_r).replace('\n', '\n  '))
            # 🔴口径对照（2026-10-13 接入加固）: N23 按方案 §4.1 权重合成 vs Step6.5 λ_final —
            #   同一份源值·不同权重 → 显式比对（差 ≤0.20 球 = 自洽·>0.20 = 口径分歧须查源）
            _n23_lf = _n23_fv(_n23_tw.get('lambda_final'))
            _n23_l2 = ((_n23_r.get('est') or {}).get('T') or {}).get('lambda')
            if _n23_lf is not None and _n23_l2 is not None:
                _n23_dv = abs(float(_n23_l2) - float(_n23_lf))
                print('  λ 口径对照: N23(joint·方案§4.1权重)=%s vs Step6.5 λ_final=%s → 差 %.3f 球 %s'
                      % (_n23_l2, _n23_lf, _n23_dv,
                         '✅自洽(≤0.20·源值单一权威)' if _n23_dv <= 0.20 else '⚠️口径分歧>0.20球→须查源'))
            # ══════════════════════════════════════════════════════════════
            # 🔴2026-11-02 N07b **自动改锚**（用户指令「把 311 那种改掉」）
            #   背景：case311 拉齐奥 N07b 报「次锚 3:1 净胜+2 超 D0 档」，脚本只 print
            #        「必须替换」→ **靠模型手工改** → 我漏了 → 真实 2:1 本可完美命中
            #   修法：锚**打印前**先跑一次校验，ok=False 且 suggestion_verified → **直接替换**
            #        （替换后**复核**；复核仍不过 → 回退原锚，防「改坏」）
            #   ⚠️ 只改锚，**不动方向**（铁律：永不反转 L2 硬核方向）
            # ══════════════════════════════════════════════════════════════
            _n23_anchor_fixed = None
            if _n23_r.get('anchor_1st'):
                try:
                    from live_score_engine import anchor_market_check as _amcP
                    _a1P = _n23_r['anchor_1st']
                    _a2P = _n23_r.get('anchor_2nd') or _a1P
                    _kwP = dict(o25=_n23_o25, u25=_n23_u25, handi=_n23_hn,
                                expect_adj=_ucl_adj)
                    _chkP = _amcP([_a1P, _a2P], _n23_e[0], _n23_e[1], _n23_e[2], **_kwP)
                    if not _chkP.get('ok'):
                        # 🔴2026-11-02 修（case314 实测）：`suggestion` 依赖波胆候选池 →
                        #   池里没有合规比分就报 `suggestion_verified=False` → 自动改锚失效
                        #   （埃尔切场 suggestion=['2:1'] 只有 1 个·而 1:1 实际合规）
                        #   → **自枚举候选**：净胜限制在 D0 档内 × 总进球 0-6，
                        #     按「总球接近市场期望」排序，逐个测到 ok=True
                        _etP = None
                        try:
                            _etP = float((_chkP.get('anchor_expect') or {}).get('exp'))
                        except Exception:
                            _etP = None
                        if _etP is None:
                            try:
                                from live_score_engine import _o25_expect as _oe
                                _etP = float(_oe(_n23_o25))
                            except Exception:
                                _etP = 2.6
                        _hdn = abs(float(_n23_hn or 0))
                        _mlim = 1 if _hdn < 0.5 else (2 if _hdn < 1.5 else 3)
                        _cand = []
                        for _h in range(0, 6):
                            for _a in range(0, 6):
                                if abs(_h - _a) <= _mlim and (_h + _a) <= 6:
                                    _cand.append('%d:%d' % (_h, _a))
                        _cand.sort(key=lambda s: abs(
                            int(s.split(':')[0]) + int(s.split(':')[1]) - _etP))
                        _hitP = None
                        for _c in _cand:
                            for _pair in ([_a1P, _c], [_c, _a1P]):
                                if _pair[0] == _pair[1]:
                                    continue
                                try:
                                    _tP = _amcP(_pair, _n23_e[0], _n23_e[1], _n23_e[2], **_kwP)
                                except Exception:
                                    continue
                                if _tP.get('ok'):
                                    _hitP = (_pair[0], _pair[1],
                                             str((_chkP.get('conflicts') or [''])[0])[:70])
                                    break
                            if _hitP:
                                break
                        if _hitP:
                            print('  🔴锚**自动校正**(N07b 前置·防手工改漏): %s/%s → %s/%s'
                                  % (_a1P, _a2P, _hitP[0], _hitP[1]))
                            print('     原因: %s ｜ 候选来自「净胜≤%d + 近期望 %.2f」自枚举'
                                  % (_hitP[2], _mlim, _etP))
                            _n23_r['anchor_1st_orig'] = _a1P
                            _n23_r['anchor_2nd_orig'] = _a2P
                            _n23_r['anchor_1st'] = _hitP[0]
                            _n23_r['anchor_2nd'] = _hitP[1]
                            _n23_anchor_fixed = (_a1P, _a2P, _hitP[0], _hitP[1])
                        else:
                            print('  ⚠️ 锚自动校正：净胜≤%d 且总球≤6 的候选**全部不通过**'
                                  ' → 标「锚不可信·宽候选池·比分不可预测」（方向仍可用）'
                                  % _mlim)
                            print('     冲突: %s' % str((_chkP.get('conflicts') or [''])[0])[:100])
                except Exception as _eP:
                    print('     ⚠️ 锚自动校正异常: %s: %s'
                          % (type(_eP).__name__, str(_eP)[:60]))
            if _n23_r.get('anchor_1st'):
                print('  → 🔴主锚 %s / 次锚 %s（交集内泊松 Top1/Top2·四要素自洽·禁各做各的）'
                      '· 一致度 %s · 锚可信度 %s%s'
                      % (_n23_r['anchor_1st'], _n23_r['anchor_2nd'],
                         _n23_r['consistency'], _n23_r['trust'],
                         '  ｜🔴已自动校正(原 %s/%s)' % (_n23_anchor_fixed[0], _n23_anchor_fixed[1])
                         if _n23_anchor_fixed else ''))
                # 🔴2026-10-20 口径修复（实跑抓）: 锚-市场/锚-期望校验**必须以 N23 最终锚为对象**
                #   根因: live 引擎(旧链·素材层)内部拿自身 Top10 做 anchor_market_check
                #        → N23 用 P5/P6 市场主导排序定锚后，两套锚不同 → 旧链误报
                #        「锚-期望不匹配 / 锚-市场矛盾」→ 按铁律 ok=False 禁落盘 = 误拦
                #        （实测 case254 主锚1:1/次锚2:1 却被 [1:1,1:0] 判 ❌）
                #   → 本处用 **N23 最终锚** 复跑一次，作为最终门禁（口径单一权威）
                try:
                    from live_score_engine import anchor_market_check as _amcN
                    _a1N = _n23_r['anchor_1st']
                    _a2N = _n23_r.get('anchor_2nd') or _a1N
                    _chkN = _amcN([_a1N, _a2N], _n23_e[0], _n23_e[1], _n23_e[2],
                                  o25=_n23_o25, u25=_n23_u25, handi=_n23_hn,
                                  expect_adj=_ucl_adj)  # 2026-10-21 欧冠正赛 +0.67 球（其余联赛 0）
                    print('  🔴锚-市场/期望复校验(N07b/N18b·校验对象=**N23 最终锚**·口径单一权威): %s'
                          % ('✅通过（可落盘）' if _chkN.get('ok')
                             else '❌不匹配 → ' + ' | '.join((_chkN.get('conflicts') or [])[:2])))
                    _amcN_ok = bool(_chkN.get('ok'))
                    if not _chkN.get('ok'):
                        # 🔴2026-10-20 复查修(P2-1): 原实现只提示「须改锚」→ 无消费闭环。
                        #   改为**执行硬约束**（明确动作 + 落盘校验会拦），并回传 _amcN_ok 供后续引用。
                        print('     🔴执行硬约束: 主锚/次锚**必须替换**为建议锚 %s%s'
                              % (' / '.join(_chkN.get('suggestion') or ['无候选']),
                                 '（✅已校验可执行·照此替换）' if _chkN.get('suggestion_verified')
                                 else '（⚠️候选池内无可行组合 → 锚不可信·须宽候选池·比分不可预测）'))
                        print('        或显式改标「锚不可信·宽候选池·比分不可预测」（方向仍可用）')
                        print('        ▪ 若坚持原锚 → 违反锚-市场一致性铁律 → 落盘阶段 check_luopan 会拦')
                    print('     （下方 live 素材层 N07/N18 若与之不一致 → 以本条为准·live 仅素材）')
                except Exception as _eN:
                    print('     ⚠️ N23 锚复校验异常: %s' % type(_eN).__name__)
            else:
                print('  ⚠️ N23 交集池为空 → 无锚（须排查盘口/源是否齐）')
            # 🔴V3.5.80 封装（2026-10-20 用户「需要封装的请封装·避免每次手算带来误差」）
            #   ① 置信度层：基础层(p_max 映射) + 5 类升降档信号 → 脚本合成，逐项留痕
            #   ② 半场方向/半场比分：`_bqc_to_ht_dist`（原仅 live 内部有矩阵·calc_all 无输出 → 手算）
            try:
                import confidence_engine as _cfe
                _ph9 = ((_n23_r or {}).get('est') or {}).get('D') or {}
                _p3 = [x for x in (_ph9.get('pH'), _ph9.get('pD'), _ph9.get('pA'))
                       if isinstance(x, (int, float))]
                _pmax9 = max(_p3) if _p3 else None
                _fav9 = min(_n23_e) if _n23_e else None
                _q2_9 = False
                try:
                    _dc9 = _dc or {}
                    _q2_9 = ('Q2' in str(_dc9.get('quadrant') or ''))
                except Exception:
                    _q2_9 = False
                _ediv9 = False
                try:
                    _el9 = float(elo or 0)
                    if abs(_el9) >= 30 and _fav9 is not None:
                        _idx9 = _n23_e.index(_fav9)
                        _lowdir9 = ('主胜', '平局', '客胜')[_idx9]
                        _elostr9 = '主胜' if _el9 > 0 else '客胜'
                        _ediv9 = (_lowdir9 != _elostr9)
                except Exception:
                    _ediv9 = False
                # 🔴2026-10-21 P0-3 修复: 弱共识/单押阈值(skew 150%/200%)来自**纯去水**回测
                #   → 优先用 skew_raw；缺失才退回校准后 skew（并标注三态）
                _sk9 = _ph9.get('skew_raw')
                if _sk9 is None:
                    _sk9 = _ph9.get('skew')
                    print('  ⚠️skew_raw 缺失 → 退回校准后 skew(口径可能偏·三态)')
                # 🔴2026-10-31（用户追问「还会不会再犯」·实跑抓）: **完整度兜底 + 审计可见**
                #   实跑发现 `_diag.get('completeness')` 在 bridge 降级时是 **None** →
                #   assess(completeness=None) → 封顶逻辑**静默不执行** = 又一处「改了没效果」
                #   → ① 缺失时自数 sources（status=='ok' 个数 / 总数）② 无论有无都显式打印
                _comp9 = (_diag or {}).get('completeness')
                if not _comp9:
                    _src9 = (_diag or {}).get('sources') or {}
                    if _src9:
                        _ok9 = sum(1 for _v in _src9.values()
                                   if isinstance(_v, dict) and _v.get('status') == 'ok')
                        # 🔴分母排除已停用源（api_football·否则 8/8 结构上不可达）
                        _DEAD9 = ('api_football',)
                        _tot9 = len([_k for _k in _src9 if _k not in _DEAD9])
                        _comp9 = '%d/%d 源可用(自数)' % (_ok9, _tot9)
                print('  🔴数据完整度: %s（≤3 源→MID-LOW 封顶 · 4 源→MID · ≥5 源不封顶·阈值待回测）'
                      % (_comp9 or '⚪未知(三态·不封顶)'))
                # 🔴2026-11-01 热门方伤停分（置信度降档用·原来是「算了不进置信度」）
                _inj_fav9 = None
                try:
                    _fdir9 = ''
                    # 🔴2026-11-01 热门方判定**不依赖 dr**（dr 在 try 内·可能未赋值 → NameError）
                    #   直接用欧盘赔率：主赔 < 客赔 → 主队热门
                    try:
                        _odds9 = ([float(_x) for _x in str(_euv).split(',')]
                                  if _euv else [])
                        if len(_odds9) >= 3:
                            _fdir9 = '主' if _odds9[0] < _odds9[2] else '客'
                    except Exception:
                        _fdir9 = ''
                    _ih9 = float(inj_h or 0)
                    _ia9 = float(inj_a or 0)
                    if '主' in _fdir9:
                        _inj_fav9 = _ih9
                    elif '客' in _fdir9:
                        _inj_fav9 = _ia9
                    else:
                        _inj_fav9 = max(_ih9, _ia9)   # 方向不明 → 取更重的一侧（保守）
                    print('  🔴热门方伤停: %s %.1f 分（方向=%s）→ 供置信度降档'
                          % ('主队' if '主' in _fdir9 else ('客队' if '客' in _fdir9 else '不明确·取更重侧'),
                             _inj_fav9 or 0, _fdir9 or '?'))
                except Exception as _eij9:
                    _inj_fav9 = None
                    print('  ⚪热门方伤停三态: %s' % type(_eij9).__name__)
                _cfr = _cfe.assess(p_max=_pmax9, skew=_sk9, fav_odd=_fav9,
                                   q2=_q2_9, elo_div=_ediv9,
                                   spread=_fav_spread,
                                   fatigue_fav=_fi_fat_fav, intent_fav=_fi_int_fav,  # 🔴批次3 S03.5
                                   completeness=_comp9,
                                   # 🔴2026-11-01 伤停进置信度：取**热门方**的伤停分
                                   #   （原 assess 无此参数 → 科莫场伤停 12.9 却仍判 HIGH）
                                   inj_fav=_inj_fav9)
                print('  ' + _cfe.fmt(_cfr).replace('\n', '\n  '))
            except Exception as _ecf:
                print('  ⚪置信度层建议: %s（三态·按 AGENTS 映射手判并留痕）' % type(_ecf).__name__)
            # 🔴P-COVER-1 默认覆盖校验（2026-11-12·case346 复盘驱动·用户指令「做」）
            #   AGENTS L2 铁律（227,495 场时间分割）:
            #     默认覆盖=「最低赔率 + 次低赔率」77.68% > 「最低 + 平局」76.51%
            #   case346 违反: 平局 3.08（**最高**）挤掉次低赔方向 客胜 2.82
            #     → 真实 0:1 客胜 → 方向❌（若按铁律则 ✅）·连带矩阵 Top2 的 0:1 被方向域屏蔽
            #   对照 case345 合规（次向取次低赔 主胜 2.842）→ **主锚 1:2 精确命中**
            #   🔴 只警告·不改方向·不改锚（永不反转 L2）｜违规须在 raw 说明理由
            try:
                import default_cover as _dvc
                try:
                    _dirs_pc = _n23_st5
                except NameError:
                    _dirs_pc = (_ov.get('--step5-dirs') or '')
                _dcov = _dvc.check(_n23_e, _dirs_pc)
                print('  ' + _dvc.fmt(_dcov))
                if _dvc.is_violation(_dcov):
                    print('     🔴落盘须在 raw 说明「为何不按默认覆盖」'
                          '（Q2诱盘 / 诱主 / M1伤停仍热门 等硬动作才算理由）'
                          '·否则 check_luopan P-COVER-1 会拦（case348+ 起）')
            except Exception as _edcv:
                print('  ⚪默认覆盖校验三态: %s（%s）' % (type(_edcv).__name__, _edcv))
            try:
                from live_score_engine import _bqc_to_ht_dist as _b2h9
                _bq9 = _n23_ht or {}
                _bqs9 = ','.join('%s=%s' % (k, v) for k, v in _bq9.items())
                _h29 = _b2h9(_bqs9) if _bqs9 else None
                if _h29:
                    _htd9, _hd9 = _h29[0], _h29[1]
                    _t29 = sorted(_htd9.items(), key=lambda x: -x[1])[:2]
                    print('  🔴半场方向+比分候选(脚本·_bqc_to_ht_dist·Step7.5): '
                          '半场主%.0f%%/平%.0f%%/客%.0f%% → 半场比分 Top2: %s'
                          % (_hd9.get('H', 0) * 100, _hd9.get('D', 0) * 100, _hd9.get('A', 0) * 100,
                             ' / '.join('%d:%d(%.1f%%)' % (h, a, p * 100) for (h, a), p in _t29)))
                else:
                    print('  ⚪半场方向+比分候选: 半全场 9 格不足/缓存缺失 → 三态（禁手算）')
            except Exception as _ebq:
                print('  ⚪半场方向+比分候选: %s' % type(_ebq).__name__)
    except Exception as _n23_err:
        print('  ❌ (D,M,T) 联合象限(N23) 调用失败: %s' % str(_n23_err)[:90])
        print('     🔴 V3.5.77 四要素融合未生效 = 本场分析不完整（**非**三态降级·须排查）')
        # 🔴2026-11-03 端到端实测加固：原来只打印异常消息 90 字符 → 拿不到栈
        #   → 2026-11-03 实跑抓到 `'<' not supported between str and float` 却无法定位
        import traceback as _tb23
        print('     ---- N23 traceback（末尾 8 帧·排障用）----')
        for _ln23 in _tb23.format_exc().strip().splitlines()[-8:]:
            print('     ' + _ln23)

    # ③ 必核清单(脚本生成)
    _league_cn = norm_league(league)
    is_eu = _league_cn in ('欧冠', '欧联', '欧协联')
    is_top5 = _league_cn in ('英超', '西甲', '意甲', '德甲', '法甲')
    # 🔴2026-09-19 审计修复(P1-4·case188审计): 联赛基准自动输出(league_table.json·大球率/平局率/本场档位H-D-A) — 原靠人工记→易漏「Step0-6 联赛校准缺基准」→ 脚本化零遗漏(审计项0-6·硬核④平局基准自动满足)
    if is_top5:
        try:
            _lt = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'league_table.json'), encoding='utf-8'))
            _lk = next((k for k in _lt if k.startswith(_league_cn)), None)
            if _lk:
                _lv = _lt[_lk]
                print('  🔴联赛基准(%s·league_table.json): 大球率 %.1f%% · 平局率 %.1f%%' % (_league_cn, _lv.get('大球率', 0), _lv.get('平局率', 0)))
                if eu:
                    _euh = float(eu.split(',')[0])
                    _bd = '<1.3' if _euh < 1.3 else ('1.3-1.5' if _euh < 1.5 else ('1.5-1.8' if _euh < 1.8 else ('1.8-2.1' if _euh < 2.1 else ('2.1-2.5' if _euh < 2.5 else ('2.5-3.0' if _euh < 3.0 else '3.0-3.5')))))
                    _pp = (_lv.get('主胜档→H/D/A') or {}).get(_bd)
                    if _pp:
                        print('    本场主胜档 %s → H %.1f%% / D %.1f%% / A %.1f%%(查表禁凭记忆)' % (_bd, _pp[0], _pp[1], _pp[2]))
                _ct = _lv.get('比分Top5')
                if _ct:
                    print('    联赛比分Top5: %s' % (_ct if isinstance(_ct, str) else ' '.join(map(str, _ct))))
                # 🔴2026-10-20 新增（用户指令「意甲新赛季大球居多·平局很少·子模型被干扰」）:
                #   联赛历史基准（league_table 全历史）vs 当季实测（案例库本季已复盘场次）
                #   → 漂移校准（机制通用·门禁 n≥20 且 |Δ|≥8pp·否则三态不改判定）
                #   消费: SK-league-* 当季覆盖块 + 本行留痕（防「存在≠活跃」）
                try:
                    import league_season_calib as _lsc
                    _cal = _lsc.calibrate(_league_cn)
                    # 🔴2026-10-29 口径统一（用户指令「只要本赛季数据·校准单赛季即可」）:
                    #   I1.json 的「单赛季基准_2026_27」（Bzzoiro 全量 n=88·无选择偏差·含赔率档/半场/净胜/球队）
                    #   = **权威口径**；league_season_calib（案例库本季已复盘·子样本·有选择偏差）降为「对照」。
                    #   禁两套当季数字并列进判定（此前同一场分析会同时出现 14.3%/17.0% 两个平局率 = 口径分裂）。
                    _sb = None
                    try:
                        if _league_cn in ('意甲', 'I1', 'Serie A'):
                            _i1p = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'league-modules', 'I1.json')
                            _i1d = json.load(open(_i1p, encoding='utf-8'))
                            _sb = _i1d.get('单赛季基准_2026_27')
                    except Exception:
                        _sb = None
                    if _sb and _sb.get('总体'):
                        _ob = _sb['总体']
                        _gd = (_sb.get('进球档') or {})
                        _sb_period = _sb.get('期次') or _sb.get('截至日期') or ''
                        print('  🔴单赛季基准（Bzzoiro 全量 n=%s·%s·**权威口径·与 SK §0-e 同源**）:'
                              % (_sb.get('n'), _sb_period))
                        print('     主 %.1f%% / 平 %.1f%% / 客 %.1f%% ｜ 场均 %.2f ｜ σ %.2f ｜ O2.5 %.1f%% ｜ BTTS %.1f%% ｜ 4+球 %.1f%%'
                              % (_ob.get('H', 0), _ob.get('D', 0), _ob.get('A', 0), _ob.get('场均', 0), _ob.get('σ', 0),
                                 _ob.get('O25', 0), _ob.get('BTTS', 0), _gd.get('4+球', 0)))
                        print('     ⚪ 让球盘/ELO 两维无当季数据 → 沿用历史表并标「非当季」（见 §0-e 不可校准项）')
                        print('  ⚪ 案例库子样本对照（有选择偏差·仅参考·禁与本基准混用）:')
                    print('  ' + _lsc.fmt(_cal).replace('\n', '\n  '))
                except Exception as _ec:
                    print('  ⚪ 赛季漂移校准不可用: %s（三态·沿用历史基准）' % type(_ec).__name__)
        except Exception as _e:
            print('  (联赛基准读取失败: %s·降级人工查表)' % _e)
    else:
        # 🔴2026-10-30 三态补（审计：非五大联赛时该段整段静默 = 「没做也不说」）
        print('  ⚪ 联赛基准 / 赛季漂移校准: %s 非五大联赛 → 不查表（三态·超域·league_table 阈值源自五大联赛）' % _league_cn)
    print(gen_checklist(league, is_europe=is_eu, is_top5=is_top5))
    print('=' * 70)
    # ④ 现场比分引擎(V3.5.74·评审P0修复2026-09-07·半场反推/CS深度/5源融合实际接入·脚本计算LLM消费)
    if eu:
        print('=' * 70)
        print('🔴现场比分引擎(live_score_engine·多源动态融合·主锚建议=脚本Top1·LLM确认):')
        ls = None  # 🔴2026-09-15合并(源自workbuddy): 欧盘参数异常时下游 ls 引用防 UnboundLocalError
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from live_score_engine import analyze_live
            _p3 = eu.split(',')
            if len(_p3) == 3:
                _oh, _od, _oa = map(float, _p3)
                _o25v = float(o25) if o25 else None
                if not u25: print('  ⚠️未传 --u25 → 大小球约束为单侧(O25)·建议补传 Under2.5 赔率')
                _hsv = float(handi) if handi else None
                _cs, _bq = _extract_cs_bqc(txt_path)
                ls = analyze_live(_oh, _od, _oa, _o25v, u25=(float(u25) if u25 else None), handi=_hsv, cs_odds=_cs, bqc_odds=_bq)
                if ls.get('status') == 'ok':
                    print('  λ: 主%s 客%s 总%s | 数据源: %s' % (
                        ls['lambda']['home'], ls['lambda']['away'], ls['lambda']['total'], ls['sources_used']))
                    print('  动态权重: %s' % ls['dynamic_weights'])
                    print('  Top5比分: %s' % ' | '.join('%s(%.1f%%)' % (x['score'], x['prob']) for x in ls['top10'][:5]))
                    print('  🔴主锚建议: %s | 次锚建议: %s(比分锚定起点·LLM综合本场基本面确认·禁机械照搬)' % (
                        ls['top10'][0]['score'], ls['top10'][1]['score']))
                # 🔴市场净胜期望档（2026-09-13·用户建议"按市场信号查表"·回测: 市场定净胜档±1球68.3%）
            try:
                _eu_f = [float(x) for x in (eu if isinstance(eu, (list, tuple)) else str(eu).split(','))]
                _inv = {'H': 1/_eu_f[0], 'D': 1/_eu_f[1], 'A': 1/_eu_f[2]}
                _t = sum(_inv.values())
                _p = {k: v/_t for k, v in _inv.items()}
                _en = _p['H']*1.35 + _p['A']*(-1.35) + _p['D']*(-0.05)
                _band = ('H3+' if _en >= 1.8 else 'H2' if _en >= 0.9 else 'H1' if _en >= 0.35
                         else 'D0' if _en >= -0.35 else 'A1' if _en >= -0.9 else 'A2' if _en >= -1.8 else 'A3+')
                print('  🔴市场净胜期望档: %s (期望净胜 %+.2f球) → 查表/净胜档应以本档为基准(与方向判定交叉核对)'
                      % (_band, _en))
            except Exception:
                pass
        # 🔴锚-量级一致性告警消费（2026-09-13·用户指出"判大球却锚1:1"）
            if ls and ls.get('status') == 'ok':
                for _w in (ls.get('warnings') or []):
                    if '锚-量级矛盾' in _w:
                        print('  ' + _w)
                        print('  → 🔴执行要求: 主锚必须按上方建议取（禁机械照搬 Top1）·并回查方向/净胜档/BTTS 一致性')
                if ls.get('magnitude_rerank'):
                    print('  [量级重排] %s' % ls['magnitude_rerank'])
                if ls.get('market_anchor_check'):
                    _amc = ls['market_anchor_check']
                    # 🔴2026-10-20 试跑修(P1·输出误导): live 层用**自身 Top2** 校验，
                    #   与 N23 市场主导排序后的最终锚不同时会打硬 ❌，而 N07b 已通过 → 自相矛盾。
                    #   → 有 N23 最终锚时，本层降为「素材层·非最终锚」，❌ 降 ⚪ 并指回 N07b/N18b。
                    # 🔴试跑修: `_n23_r` 在主流程函数内为**局部变量** → globals() 恒空
                    _n23f = (locals().get('_n23_r') or globals().get('_n23_r') or {})
                    _n23_has = bool(_n23f.get('anchor_1st'))
                    print('  🔴锚-市场一致性(N07%s·校验对象=live Top2): %s | 市场净胜期望档 %s(净胜%+.2f球)'
                          % (('·素材层' if _n23_has else '·2026-09-13·用户要求'),
                             ('✅主锚/次锚均与市场一致' if _amc['ok'] else
                              '⚠️矛盾→建议锚 ' + ' / '.join(_amc['suggestion'] or ['无候选']) +
                              ('（✅可执行）' if _amc.get('suggestion_verified') else '（⚠️无可行组合·锚不可信）')),
                             _amc['band'], _amc['exp_net'] or 0))
                    if _n23_has:
                        print('     ⚪ 本层仅素材（最终锚 %s/%s 的校验见 N07b/N18b·以那条为准）'
                              % (_n23f.get('anchor_1st'), _n23f.get('anchor_2nd')))
                    for _c in _amc['conflicts']:
                        print('     ' + ('⚪ ' if _n23_has else '❌ ') + _c
                              + ('（素材层·非最终锚）' if _n23_has else ''))
                # 🔴V6四象限量化（2026-09-27·用户要求固化·22.7万场验证·仅提示不改判定·output_checker N13）
                try:
                    import calc_v3572 as _qv
                    def _opt(nm):
                        _a = sys.argv
                        if nm in _a and _a.index(nm) + 1 < len(_a):
                            try:
                                return float(_a[_a.index(nm) + 1])
                            except Exception:
                                return None
                        return None
                    _qh = _qv.quadrant_hint(_opt('--handi'), _opt('--o25'), _opt('--u25'))
                    if _qh:
                        print('  ' + _qh)
                except Exception:
                    pass
                # 🔴锚可信度分级（2026-09-13·案例库157场回测固化·用户要求"运用到模型主体"·output_checker N08）
                try:
                    from prestep_dual import anchor_trust as _at
                    _atv, _atr = _at(_o25v, _hsv)
                    print('  🔴锚可信度(N08·2026-09-13·157场回测): %s — %s' % (_atv, _atr))
                    if _atv.startswith('🔴'):
                        print('     → 🔴执行要求: 大球场/深盘大胜场"锚不可信"·禁把主锚/次锚当高置信输出·改「宽候选池+比分不可预测」标注(方向仍可用)')
                except Exception as _e_at:
                    print('  ⚠️锚可信度未计算:', str(_e_at)[:50])
                print('  聚合: 主%s 平%s 客%s | O2.5%s | 置信%s | 不确定: %s' % (
                    ls['aggregated']['home_win'], ls['aggregated']['draw'], ls['aggregated']['away_win'],
                    ls['aggregated']['over25'], ls['confidence'], ls['uncertainty']))
                if ls.get('prior_bin'): print('  先验格: %s(弱平滑≤10%%)' % ls['prior_bin'])
            else:
                print('  ⚠️现场引擎:', (ls.get('message') if ls else '欧盘参数缺失/未启用(见上方提示)'))
        except Exception as e:
            print('  ⚠️现场引擎未执行(降级泊松+查表):', str(e)[:120])
        # 🔴半场推断量级(V3.0方案F1瘦身版·2026-09-09·上限验证43.8% vs O25 26.9%·+16.9pp):
        #   9格半全场→半场进球分布→ht_ft_cond 175476场→全场5层(0-1/2/3/4/5+球)·与goal_bin校准分布并列第三源
        try:
            _bq5 = _extract_cs_bqc(txt_path)[1] if eu else None
            if _bq5:
                if isinstance(_bq5, dict):
                    _bq5 = ','.join('%s=%.2f' % (k, v) for k, v in _bq5.items())
                from live_score_engine import extract_ht_goals_layer as _htgl
                _hg = _htgl(_bq5)
                if _hg:
                    _L = _hg['layers']; _hgstr = {k: '%.0f%%' % (v * 100) for k, v in _hg['ht_goals'].items()}
                    _row = '  半场推断量级(9格半全场->5层·上限43.8%%vsO25 26.9%%·置信%s): 半场进球%s -> 全场 0-1球%.0f%%%%/2球%.0f%%%%/3球%.0f%%%%/4球%.0f%%%%/5+球%.0f%%%% | 期望%.2f球' % (
                        _hg['confidence'], _hgstr, _L[0] * 100, _L[1] * 100, _L[2] * 100, _L[3] * 100, _L[4] * 100, _hg['mean_ft'])
                    print(_row.replace('%%%%', '%%').replace('%%', '%'))
                    if _hg['ht_goals']['0'] > 0.5:
                        print('    🔴推断半场0球>50%%: 全场小量级约束(0-1球>=约58%%·禁4+球主锚)')
                    elif _hg['ht_goals']['3'] > 0.25:
                        print('    🔴推断半场3+球>25%%: 大球约束(候选必含4:1/5:0类)')
                    if _hg['confidence'] < 0.5:
                        print('    (半全场分散·推断置信低·仅参考·主判以O25校准分布为准)')
        except Exception:
            pass
        # 让球动态量级(V2.0·2026-09-10·9层先验->因子->贝叶斯->动态候选池·禁机械锚·评审标注独立增益待P2回测)
        try:
            _hd = float(handi) if handi else None
            if _hd is not None and abs(_hd) >= 1.5 and eu:
                from handicap_dynamic_magnitude import analyze as _dyn_an
                _eu3 = eu.split(',')
                if len(_eu3) == 3:
                    _dr = '主胜' if float(_eu3[0]) < float(_eu3[2]) else ('客胜' if float(_eu3[0]) > float(_eu3[2]) else '平局')
                    _csd, _bqd = _extract_cs_bqc(txt_path)
                    _bqs = ','.join('%s=%.2f' % (k, v) for k, v in _bqd.items()) if isinstance(_bqd, dict) and _bqd else (_bqd if _bqd else None)
                    _css = ','.join('%s=%.2f' % (k, v) for k, v in _csd.items()) if isinstance(_csd, dict) and _csd else (_csd if _csd else None)
                    _tgs = None
                    _tgtxt = open(txt_path, encoding='utf-8').read()
                    # 🔴2026-09-19 审计修复(V3.0·数据格式不匹配): 原只认 '发布时间,0,1,2,...'(无后缀) → 真实竞彩 txt 全部为 '发布时间,0球,1球,2球,...' → F8_总进球盘因子**恒静默失效**（存在≠活跃）→ 已兼容 球 后缀
                    _mh8 = re.search(r'发布时间,0(?:球)?,1(?:球)?,2(?:球)?', _tgtxt)
                    if _mh8:
                        _rows8 = re.findall(r'^(\d{4}-\d{2}-\d{2} [\d:]+),(.+)$', _tgtxt[_mh8.start():], re.M)
                        if _rows8:
                            _vals8 = _rows8[-1][1].split(',')
                            _prs = ['%d=%.2f' % (i, float(_vals8[i])) for i in range(min(8, len(_vals8)))]
                            if len(_prs) >= 5: _tgs = ','.join(_prs)
                    _dyn = _dyn_an(_hd, league=_league_cn, o25=float(o25) if o25 else None,
                                   oh=float(_eu3[0]), od=float(_eu3[1]), oa=float(_eu3[2]),
                                   elo=float(elo) if elo else None,
                                   inj_h=float(inj_h) if inj_h else None,
                                   inj_a=float(inj_a) if inj_a else None,
                                   bqc=_bqs, cs=_css, tg=_tgs, direction=_dr)
                    if _dyn.get('status') == 'no_prior':
                        print('  让球动态量级: 层%s 样本不足无先验(受让3等·降级·由O25校准+live覆盖)' % _dyn.get('layer'))
                    elif _dyn.get('status') == 'ok':
                        _p = _dyn['posterior']
                        print('  让球动态量级(9层先验->因子->贝叶斯): 层%s 先验%.2f->后验%.2f(置信%.2f) 因子: %s' % (
                            _dyn['layer'], _dyn['prior'], _p['magnitude_center'], _p['confidence'],
                            ' '.join('%s:%+.2f' % (k, v) for k, v in _p['factor_contrib'].items())))
                        print('    动态候选池: %s' % ' | '.join('%s(%.0f%%)' % (c['score'], c['weight'] * 100) for c in _dyn['candidates'][:5]))
                    if _dyn.get('status') == 'ok' and abs(_hd) >= 1.5 and ls and ls.get('top10'):
                        _hw = 0.50 if abs(_hd) >= 2.5 else 0.40
                        _mc = _merge_score_candidates(ls.get('top10', []), _dyn['candidates'], _hw)
                        print('    🔴深盘融合候选池(让球分层%.0f%%+live%.0f%%): %s' % (
                            _hw * 100, (1 - _hw) * 100,
                            ' | '.join('%s(%.0f%%)' % (c['score'], c['weight'] * 100) for c in _mc)))
            elif _hd is not None and abs(_hd) < 1.5 and eu:
                print('  ⚪让球动态量级: 不触发（|让球|=%.2f < 1.5·浅让/平手场由 O25 校准分布 + live 引擎覆盖·非缺失）' % abs(_hd))
        except Exception as _de:
            print('  让球动态量级未执行:', str(_de)[:80])
    else:
        print('=' * 70)
        print('  ⚠️未传 --eu 主,平,客 → 现场比分引擎不触发: 比分锚定降级纯LLM/查表(非5源融合)·🔴调用必带 --eu 主,平,客(--o25/--handi 同步传)防引擎静默缺')
    # ⑤ 欧战三层校准(V3.5.74·P0修复2026-09-07·europe_two_leg/group_stage实际接入·subprocess调用非仅文档)
    if _league_cn in ('欧冠', '欧联', '欧协联') and eu:
        print('=' * 70)
        print('🔴欧战三层校准(europe_two_leg/group_stage·赛事分层+赛程阶段+赔率档):')
        try:
            import re as _re5
            _p5 = eu.split(',')
            if len(_p5) == 3:
                _oh5, _od5, _oa5 = float(_p5[0]), float(_p5[1]), float(_p5[2])
                _rnd5 = league
                try:
                    _rm5 = _re5.search(r'(1/8决赛|1/4决赛|半决赛|决赛|资格赛\d|附加赛|联赛阶段|小组赛)', open(txt_path, encoding='utf-8').read())
                    if _rm5: _rnd5 = _rm5.group(1)
                except Exception: pass
                _eu_dir = os.path.dirname(os.path.abspath(__file__))
                if '联赛' in _rnd5 or '小组' in _rnd5:
                    import re as _re5md
                    _md = 4
                    _mmd = _re5md.search(r'第\s*(\d+)\s*轮', open(txt_path, encoding='utf-8').read())
                    if _mmd: _md = int(_mmd.group(1))
                    # 🔴积分txt提取(2026-09-10·错误3: 无积分数据保留默认9/3·由LLM/外部更正)
                    _hp5, _ap5 = 9, 3
                    _ct5 = open(txt_path, encoding='utf-8').read()
                    _hpm5 = re.search(r'主队[^：:\n]{0,6}(?:积分|排名)?[：:]\s*(\d+)', _ct5)
                    _apm5 = re.search(r'客队[^：:\n]{0,6}(?:积分|排名)?[：:]\s*(\d+)', _ct5)
                    if _hpm5: _hp5 = int(_hpm5.group(1))
                    if _apm5: _ap5 = int(_apm5.group(1))
                    _cmd5 = [sys.executable, os.path.join(_eu_dir, 'europe_group_stage.py'), '--home_points', str(_hp5),
                             '--away_points', str(_ap5), '--matchday', str(_md), '--league', _league_cn,
                             '--home_odds', str(_oh5), '--away_odds', str(_oa5)]
                    if handi: _cmd5 += ['--handi', handi]
                    _g5 = json.loads(subprocess.run(_cmd5, capture_output=True, text=True, encoding='utf-8', timeout=30).stdout)
                    print('  类型: 小组赛/瑞士轮 | 战意: 主%s 客%s | 差:%s | 欧战校准主%s 赛事(%s)%s' % (
                        _g5['home_motivation']['level'], _g5['away_motivation']['level'],
                        _g5['motivation_gap']['level'],
                        _g5.get('europe_calibration', {}).get('home_win_adjust', '-'),
                        _g5.get('league_calibration', {}).get('league', '-'),
                        _g5.get('league_calibration', {}).get('home_win_adjust', '')))
                    for _t5 in _g5.get('trap_detection', []):
                        if _t5['severity'] in ('HIGH', 'MEDIUM'):
                            print('  ⚠️诱盘: %s(%s) → %s' % (_t5['type'], _t5['severity'], _t5['action']))
                else:
                    _is_leg2 = '次回合' in open(txt_path, encoding='utf-8').read()
                    _legv = '2' if _is_leg2 else '1'
                    _cmd5 = [sys.executable, os.path.join(_eu_dir, 'europe_two_leg.py'), '--leg', _legv,
                             '--league', _league_cn, '--round', _rnd5]
                    _t5 = json.loads(subprocess.run(_cmd5, capture_output=True, text=True, encoding='utf-8', timeout=30).stdout)
                    _d5 = _t5['direction_adjustment']
                    print('  类型: %s | 校准主%s 平%s 球%s%s | 关键: %s' % (
                        '决赛(中立)' if _t5.get('is_final') else '两回合首回合(%s)' % _rnd5,
                        _d5.get('home_win', _d5.get('home_win(次回合主队)', '-')), _d5['draw'], _d5['goals'],
                        ' | 赛事(%s)%s' % (_t5.get('league_calibration', {}).get('league', '-'), _t5.get('league_calibration', {}).get('note', ''))[:60] if _t5.get('league_calibration') else '',
                        '/'.join(_t5['score_tendency']['key_scores'][:3])))
        except Exception as e:
            print('  ⚠️欧战校准未执行(默认主回合·次回合需手动--first_leg):', str(e)[:100])
    print('🔴LLM执行流程(篇幅过载解药·2026-09-02·分5批聚焦·每批独立完成防过载):')
    print('  批次1 数据批: C01-C03(去水/档位/凯利)+外部源(fetch_all三态) → 输出数据证据')
    print('  批次2 方向批: C04-C16(变动/诱阻/方向/欧亚/诱阻分类/修正53) → 输出方向+置信度+诱盘')
    print('  批次3 比分批: C17-C22(量级/泊松/净胜档/查表/锚定/总进球) → 输出主锚次锚+停止分支')
    print('  批次4 输出批: C28-C29(口径标注+自检22项) → 组装完整输出')
    print('  批次5 落盘批: C30(case_write+raw+check_luopan) + output_checker校验 → 落盘完成')
    print('  🔴每批独立输出·完成一批再下一批·禁跳批·禁一批内赶完(防篇幅过载导致尾部弱化)')
    print('  🔴output_checker.py校验输出完整性·缺失=补齐重跑至全过')

if __name__ == '__main__':
    main()
