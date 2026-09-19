# calc_all.py — 全覆盖预计算聚合器 + 必核清单生成器（步骤遗失结构性根除·支柱A）
# 用法: python calc_all.py <竞彩txt路径> [联赛key] [--eu 主,平,客] [--handi 盘口] [--o25 大小球赔率] [--home_water 主水] [--elo 主队ELO差]
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
    ('C23', '新闻伤停(SL-news-crawl·唯一源·三态)', None, 'SL-news-crawl'),
    ('C24', 'api-football三端点(官方概率/13家赔率/伤停)', '五大联赛+欧战', 'SL-api-football-chain'),
    ('C25', 'footballcharts基本面(λ/校准/蒙特卡洛)·⛔源已废弃(2026-09-15·域名DNS全失效)→降级 understat_xg+SK-xg-depth+联赛校准(按“无数据”三态标注·不算遗漏)', '五大联赛', 'SL-footballcharts-fetch'),
    ('C26', 'clubelo ELO(修正41一致性)', '五大联赛+欧战', 'SL-elo-fetch'),
    ('C27', 'xG深度比分判定(understat·防泄露)', '五大联赛', 'SK-xg-depth'),
    ('C28', '比分命中口径标注(主锚/次锚·第3/4候选不算)', None, '口径铁律'),
    ('C29', '自检表22项逐项证据', None, 'checklist'),
    ('C30', '落盘: case_write add/review + raw七节 + check_luopan', None, 'case_write'),
]

# 统一联赛归一化（审计 P0 修复·三套命名空间统一）——
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
    # CS 补齐逗号表头格式(格式B)——原仅支持 `1:0=` 等号格式，
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
            # 原 seg 未截断到下一节 → seg_rows[-1] 取到【比分固定奖金】段末行
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
    # 格式C: 纯逗号无表头数据行(原始粘贴竞彩txt·【半全场】段后时间行直接9值)·映射按固定顺序
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
    # ⚡ 学习成果提示(learned_rules.json·提示级不改变任何计算/判定)
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
    # ⚡ L3 误差规则 + L4 CBR + L1 观察（接线·原本定义未调用=存在≠活跃修复）
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
                        print('  ⚡ L1 在线ML(第6源): 主%.0f%% 平%.0f%% 客%.0f%% | 进球λ≈%s' % (
                            _dp.get(1, 0) * 100, _dp.get(0, 0) * 100, _dp.get(2, 0) * 100, _pv.get('goals')))
                        # 学习结果接入预测
                        _l1_degen = False
                        try:
                            _gate = {}
                            _gp = os.path.join(_old2, 'state', 'gate.json')
                            if os.path.exists(_gp):
                                _gate = json.load(open(_gp, encoding='utf-8')).get('L1_online_ml', {})
                            _w = float(_gate.get('weight', 0.10)) if _gate.get('enabled', True) else 0.0
                            if _gate.get('status') == 'degraded':
                                _w = 0.0
                            # 全面审计(L1 退化守卫·P1): 在线ML 实测饱和退化
                            # (max>0.95 / min<1e-6 / 平局恒 0) → 强制权重 0·不参与融合
                            # 否则饱和输出会按权重 0.10 混入 → 把弱共识场硬推成强方向
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
                            # 修复(P1-2): 未传 --eu 时用竞彩 txt 末盘去水（自动·不依赖参数）
                            if _mk is None:
                                _oh5, _od5, _oa5 = (_feat2.get('home_odds'), _feat2.get('draw_odds'), _feat2.get('away_odds'))
                                if _oh5 and _od5 and _oa5:
                                    try:
                                        _inv = {1: 1 / float(_oh5), 0: 1 / float(_od5), 2: 1 / float(_oa5)}
                                        _tt = sum(_inv.values())
                                        _mk = {k: v / _tt for k, v in _inv.items()}
                                        _mk_src = '竞彩txt去水'
                                    except Exception:
                                        _mk = None
                            if _mk and (_w > 0 or _l1_degen):
                                # 防过拟合/降噪: 融合「进入判定」需**独立门禁**(默认关·可回滚)
                                # 依据: 融合监测 n=22 → 融合命中8 = 基准命中8(**无增益**);
                                # 且 L1 已 degraded → 融合=市场·无新增信息 → 只提示不进入判定
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
    # 📄 预测日志
    try:
        import sys as _sys2
        _oldir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'online_learning')
        if os.path.isdir(_oldir):
            _sys2.path.insert(0, _oldir)
            try:
                import data_bridge as _db
                # 离线模式（快·保证源状态写入）·网络源仅记录 skipped
                # 修复: 新增 --net 开关 —— **完整分析必须传 --net**，否则网络源
                # (clubelo ELO/xg/api_football/h2h/news/euro_odds) 全部 skipped → prediction_log
                # 仅 1/8 源(27键/18非空) → 学习模块特征残缺。传 --net 后 3-4/8 源(32-37键)。
                _netflag = ('--net' in sys.argv)
                # 修复: 原用 _league_cn（392行才定义）→ UnboundLocalError → 每次静默降级 txt(1/8源)
                _lcn = norm_league(league)
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
    # 🧠 在线学习系统状态
    try:
        _ol = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'online_learning', 'state', 'river', 'n.json')
        import json as _oj
        if os.path.exists(_ol):
            _n = _oj.load(open(_ol, encoding='utf-8'))
            print('  [在线学习] L1样本=%s (🔴特征增强后融合验证+0.68pp·z=2.12→权重0.10启用·仅第6源不覆盖判定) L2/L3/L4累积中' % _n.get('direction', 0))
    except Exception:
        pass
    # 解析可选参数
    # 合并(): 原实现 `--eu --handi` 会把 '--handi' 当成 eu 的值 →
    # eu.split(',') 长度≠3 → 现场引擎 ls 未赋值 → 掩盖真实原因。现改为仅当下一个 token 非 '--' 开头才取值。
    eu = handi = o25 = u25 = home_water = elo = inj_h = inj_a = off = None
    _OVFLAGS = ('--eu', '--handi', '--o25', '--u25', '--home_water', '--elo', '--inj_h', '--inj_a', '--off')
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
    off = _ov.get('--off') or None
    print('=' * 70)
    print('calc_all.py — 全覆盖预计算(2026-09-02·步骤遗失结构性根除)')
    print('=' * 70)
    # ① 跑 calc_match 全管道(含修正的run_extensions·净胜档/总进球档已接入)
    cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'calc_match.py'), txt_path]
    if league: cmd.append(league)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=60)
        out = r.stdout
        # 链路优化: calc_match内部从竞彩盘反推O2.5常失败(竞彩txt无大小球盘段)→输出"O2.5未识别"会误导LLM跳过C17档位查表
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
                # 修复(P1·参数缺失致功能静默降级·与 F3/F5 同类):
                # ① draw_group_score: 修正53 分组分(组A-D 去相关后总分) → direction_full 内部
                # 「平局并列/唯一」判定（>=4 唯一 / >=2.5 并列 / >=1.5 / >=1.0 加权）。
                # 原恒用默认 0.0 → **内部并列判定恒不触发**，与 calc_match 段输出的并列建议口径不一致。
                # ② true_handi: 真实实力盘 → match_classifier 的「盘口背离」异常指标（|handi-true|>0.25）。
                # 原恒 None → 该指标恒不参与 → 诱阻分类 total_score 少一维(可能漏判庄家主导盘)。
                _draw_score = 0.0
                try:
                    _mds = re.search(r'总分(\d+(?:\.\d+)?)\s*→', out)
                    if _mds:
                        _draw_score = float(_mds.group(1))
                except Exception:
                    _draw_score = 0.0
                _true_handi = None
                try:
                    from calc_v3572 import true_handicap_calculator as _thc
                    _th, _ = _thc(elo_diff=float(elo) if elo else None, home_adv=0.25,
                                  inj_h=float(inj_h) if inj_h else 0, inj_a=float(inj_a) if inj_a else 0)
                    if _th is not None:
                        _true_handi = -_th   # 符号与 handi 一致(负=主让)·函数返回"正=主让"
                except Exception:
                    _true_handi = None
                dr = direction_full(oh, od, oa, float(o25) if o25 else None, league_div=league, handi=hs, home_water=hw,
                    draw_group_score=_draw_score,
                    inj_score_h=int(inj_h) if inj_h else 0, inj_score_a=int(inj_a) if inj_a else 0,
                    official_dc=float(off) if off else None)
                print('  方向(欧亚综合): %s(%s) | 并列:%s | 诱盘:%s | 提示:%s | 修正53分组分%.1f' % (
                    dr['主方向'], dr['置信度'], dr['并列建议'], dr.get('诱盘信号') or '无', dr.get('执行提示') or '无', _draw_score))
                print('  ' + str(dr.get('小概率管理') or ''))
                if hs is not None:
                    cf = match_classifier(oh, od, oa, handi=hs, water=hw, true_handi=_true_handi)
                    if _true_handi is not None:
                        print('  真实实力盘(ELO/伤停推导·参考): 真实%+.2f vs 实盘%+.2f' % (_true_handi, hs))
                    print('  诱阻分类: %s(总分%d·置信%.0f%%)' % (cf['match_type'], cf['total_score'], cf['confidence']*100))
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
    except Exception as e:
        print('  ⚠️欧亚综合计算失败:', e)
    # ③ 必核清单(脚本生成)
    _league_cn = norm_league(league)
    is_eu = _league_cn in ('欧冠', '欧联', '欧协联')
    is_top5 = _league_cn in ('英超', '西甲', '意甲', '德甲', '法甲')
    # 审计修复(P1-4·case188审计): 联赛基准自动输出(league_table.json·大球率/平局率/本场档位H-D-A) — 原靠人工记→易漏「Step0-6 联赛校准缺基准」→ 脚本化零遗漏(审计项0-6·硬核④平局基准自动满足)
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
        except Exception as _e:
            print('  (联赛基准读取失败: %s·降级人工查表)' % _e)
    print(gen_checklist(league, is_europe=is_eu, is_top5=is_top5))
    print('=' * 70)
    # ④ 现场比分引擎(评审P0修复半场反推/CS深度/5源融合实际接入·脚本计算LLM消费)
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
                # 市场净胜期望档（用户建议"按市场信号查表"·回测: 市场定净胜档±1球68.3%）
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
        # 锚-量级一致性告警消费（用户指出"判大球却锚1:1"）
            if ls and ls.get('status') == 'ok':
                for _w in (ls.get('warnings') or []):
                    if '锚-量级矛盾' in _w:
                        print('  ' + _w)
                        print('  → 🔴执行要求: 主锚必须按上方建议取（禁机械照搬 Top1）·并回查方向/净胜档/BTTS 一致性')
                if ls.get('magnitude_rerank'):
                    print('  [量级重排] %s' % ls['magnitude_rerank'])
                if ls.get('market_anchor_check'):
                    _amc = ls['market_anchor_check']
                    print('  🔴锚-市场一致性(2026-09-13·用户要求): %s | 市场净胜期望档 %s(净胜%+.2f球)'
                          % ('✅主锚/次锚均与市场一致' if _amc['ok'] else '⚠️矛盾→建议锚 ' + ' / '.join(_amc['suggestion'] or ['无候选']),
                             _amc['band'], _amc['exp_net'] or 0))
                    for _c in _amc['conflicts']:
                        print('     ❌ ' + _c)
                # 锚可信度分级（案例库157场回测固化·用户要求"运用到模型主体"·output_checker N08）
                try:
                    from prestep_dual import anchor_trust as _at
                    _atv, _atr = _at(_o25v, _hsv)
                    print('  🔴锚可信度(2026-09-13·157场回测): %s — %s' % (_atv, _atr))
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
        # 半场推断量级(V3.0方案F1瘦身版·上限验证43.8% vs O25 26.9%·+16.9pp):
        # 9格半全场→半场进球分布→ht_ft_cond 175476场→全场5层(0-1/2/3/4/5+球)·与goal_bin校准分布并列第三源
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
        # 让球动态量级(V2.0·9层先验->因子->贝叶斯->动态候选池·禁机械锚·评审标注独立增益待P2回测)
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
                    # 审计修复(V3.0·数据格式不匹配): 原只认 '发布时间,0,1,2,...'(无后缀) → 真实竞彩 txt 全部为 '发布时间,0球,1球,2球,...' → F8_总进球盘因子**恒静默失效**（存在≠活跃）→ 已兼容 球 后缀
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
        except Exception as _de:
            print('  让球动态量级未执行:', str(_de)[:80])
    else:
        print('=' * 70)
        print('  ⚠️未传 --eu 主,平,客 → 现场比分引擎不触发: 比分锚定降级纯LLM/查表(非5源融合)·🔴调用必带 --eu 主,平,客(--o25/--handi 同步传)防引擎静默缺')
    # ⑤ 欧战三层校准(P0修复europe_two_leg/group_stage实际接入·subprocess调用非仅文档)
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
                    # 积分txt提取
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
