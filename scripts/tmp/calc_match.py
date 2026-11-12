# -*- coding: utf-8 -*-
"""
calc_match.py — V3.5.58 计算脚本（方案1+4：负载超载缓解·计算脚本化）
用途：解析竞彩txt → 一次性算完全部确定性计算，模型只消费结果做判断。
用法：PYTHONIOENCODING=utf-8 python data/tmp/calc_match.py <txt路径>
输出：各盘去抽水/隐含概率/凯利/CS-P_i排序/半场三元+45A推导/总进球分布/O2.5映射/方向差距分级
"""
import re, sys, io, os, json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8') if hasattr(sys.stdout, 'buffer') else sys.stdout

def parse_txt(text):
    """解析竞彩txt各盘，返回 {盘名: [(时间戳, {选项:赔率})]}
    用户txt格式：表头"发布时间,胜,平,负" + 数据行"2026-08-20 09:20:59,1.40,4.15,5.75"（逗号分隔·按表头对齐）"""

    text = re.sub(r'=====([^=]+?)=====', r'【\1】', text)  # 2026-08-31兼容=====盘标题格式(raw防\1八进制)
    lines = text.splitlines()
    sections = {}
    current = None
    _PBF = [None]   # 🔴2026-09-24 审计修复: 比分盘时间戳独立行的暂存槽
    headers = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 盘标题（【】包裹）
        m = re.match(r'【([^】]+)】', line)
        if m:
            name = m.group(1)
            if '胜平负' in name and '让球' not in name and '半全场' not in name:
                current = 'spf'
            elif '让球' in name:
                current = 'rq'
                # 🔴2026-09-04审计修复: 保留竞彩让球数/方向(标题"让球:+1"主受让1=客让1·"-1"主让1)——margin候选方向依据
                _mh = re.search(r'让球[:：]?\s*([+-]\d+(?:\.\d+)?)', name)  # 🔴2026-09-11修复: 兼容'让球-1'(无冒号·要求符号)
                sections['_rq_handicap'] = float(_mh.group(1)) if _mh else None
            elif '总进球' in name:
                current = 'zjq'
            elif '半全场' in name:
                current = 'bqc'
            elif '比分' in name:
                current = 'bf'
            else:
                current = None
            sections.setdefault(current, [])
            headers = None
            continue
        # 表头行（发布时间开头 → 定义列名）
        if current and line.startswith('发布时间'):
            parts = [p.strip() for p in line.split(',')]
            headers = parts[1:]  # 去掉"发布时间"
            # 比分盘的表头是"比分固定奖金 时间"标题行（无发布时间表头·用标题时间）
            continue
        # 数据行（时间戳开头）
        ts_match = re.match(r'(\d{4}-\d{2}-\d{2}[ \d:]+)[,\t]?(.*)', line)
        # 2026-09-24 审计修复(P0·CS段静默缺失): 比分盘常为「时间戳独立行 + 数据行」分离格式
        if (not ts_match) and current == 'bf' and _PBF[0] and re.search(r'\d+:\d+', line):
            ts_match, ts, rest = True, _PBF[0], line.strip()
        elif ts_match and current:
            ts = ts_match.group(1).strip()
            rest = ts_match.group(2).strip()
        if ts_match and current:
            if current == 'bf' and not rest.strip():
                _PBF[0] = ts
                continue
            if current == 'bf':
                # 比分盘两种格式:
                # ①旧格式: 胜方比分:1:0=10.00,2:0=7.50 或 胜方比分 1:0=10.00(含"胜其它/胜其他"档)
                # ②表头对齐格式(实际主流): 表头"发布时间,1:0,2:0,...,胜其它" + 数据行"2026-08-21 09:55:11,18.00,..."
                if '=' in rest and ('比分' in rest or '其他' in rest or '其它' in rest):
                    odds = {}
                    for kv in re.finditer(r'(\d+:\d+)=([\d.]+)', rest):
                        odds[kv.group(1)] = float(kv.group(2))
                    for kv in re.finditer(r'(胜其他|平其他|负其他|胜其它|平其它|负其它)=([\d.]+)', rest):
                        odds[kv.group(1)] = float(kv.group(2))
                    if odds:
                        sections.setdefault(current, []).append((ts, odds))
                elif '=' in rest:
                    odds = {}
                    for kv in re.finditer(r'(\d+:\d+)=([\d.]+)', rest):
                        odds[kv.group(1)] = float(kv.group(2))
                    for kv in re.finditer(r'(胜其他|平其他|负其他|胜其它|平其它|负其它)=([\d.]+)', rest):
                        odds[kv.group(1)] = float(kv.group(2))
                    if odds:
                        sections.setdefault(current, []).append((ts, odds))
                elif headers and len([p for p in rest.split(',') if p.strip()]) >= len(headers):
                    # ②表头对齐格式: rest = "18.00,35.00,..." 按 headers(含1:0/胜其它)对齐
                    vals = [p.strip() for p in rest.split(',')]
                    odds = {}
                    for h, v in zip(headers, vals):
                        try:
                            odds[h] = float(v)
                        except ValueError:
                            pass
                    if odds:
                        sections.setdefault(current, []).append((ts, odds))
                continue
            # 非比分盘：逗号分隔数值·按表头对齐
            if not headers:  # 🔴容错(2026-08-29): 无表头txt→自动用标准列名(用户粘贴常无表头)
                std = {'spf': ['胜','平','负'], 'rq': ['胜','平','负'],
                       'zjq': ['0','1','2','3','4','5','6','7+'],
                       'bqc': ['胜胜','胜平','胜负','平胜','平平','平负','负胜','负平','负负']}
                headers = std.get(current)
            if headers:
                vals = [p.strip() for p in rest.split(',')]
                if len(vals) >= len(headers):
                    odds = {}
                    for h, v in zip(headers, vals):
                        try:
                            odds[h] = float(v)
                        except ValueError:
                            pass
                    if odds:
                        sections.setdefault(current, []).append((ts, odds))
    # 比分盘：合并多行（胜方/平局/负方）为一次快照
    if 'bf' in sections and sections['bf']:
        # 按时间戳分组
        by_ts = {}
        for ts, odds in sections['bf']:
            by_ts.setdefault(ts, {}).update(odds)
        sections['bf'] = sorted([(ts, o) for ts, o in by_ts.items()])
    return sections

def dejuice(odds):
    """去抽水：返回 (抽水率, 隐含概率dict)"""
    inv = {k: 1/v for k, v in odds.items()}
    total = sum(inv.values())
    return total - 1, {k: v/total for k, v in inv.items()}

def kelly(odds, prob):
    """凯利指数：赔率 × 隐含概率（>1 有价值）
    🔴注意: 若 prob 来自同一赔率源去水 → odds×p = 1/Σ(1/o) < 1 恒成立（单源凯利恒<1·仅相对排序参考）
    🔴有效凯利 = 竞彩赔率 × 独立源概率(欧盘去水/模型概率·跨市场价值)·需传 external_prob"""
    return {k: odds[k] * prob.get(k, 0) for k in odds}

def main():
    if len(sys.argv) < 2:
        print("用法: python calc_match.py <竞彩txt路径>")
        return
    text = open(sys.argv[1], encoding='utf-8').read()
    secs = parse_txt(text)
    # 🔴V3.5.80 P9 竞彩噪音隔离·数据桥消费（2026-10-20 用户方案 B3）
    #   竞彩 txt = 结构壳 · 欧亚盘 = 内容源 → 各段按源分层填充
    #   🔴只覆盖**结构同构**的段（spf/bf）：
    #     rq/zjq 在 calc_match 期望「竞彩让球/总进球」结构·与欧亚水位/去水概率格式不同 →
    #     不强行覆盖（欧亚口径已由 calc_all 的 --handi/--o25/--u25 直接进判定·口径更准）
    #   🔴bqc 半全场 / 逐T 时序 / 公众情绪 → **恒用竞彩**（欧亚快照无 HT-FT·仅 2-4 时点）
    _p9 = None
    if '--p9-bridge' in sys.argv:
        try:
            _p9 = json.load(open(sys.argv[sys.argv.index('--p9-bridge') + 1], encoding='utf-8'))
        except Exception as _e9b:
            print('  ⚪P9桥接: 读取失败(%s) → 竞彩源全部保留' % type(_e9b).__name__)
            _p9 = None
    if _p9:
        _bsec = _p9.get('sections') or {}
        _bsrc = _p9.get('src_map') or {}
        _jc_spf = list(secs.get('spf') or [])
        _applied, _kept = [], []
        # 🔴2026-10-21 P1-5 修复: 覆盖前保存**竞彩原序** → 变动层(V1/D1/形态学/低赔重排)读原序
        #   根因: 整段替换后 secs['spf'] 末项=欧盘值·初项=竞彩 → 变动计算**跨源混算**
        #   （case260 实测: 客胜 竞彩原序 -13.3% 流入 → 混算 +8.5% 流出·方向相反）
        #   口径: 绝对概率/末盘 = 欧亚（设计意图）· 变动/形态 = 竞彩原序（本修复）
        if _jc_spf:
            secs['spf_jc'] = list(_jc_spf)
        for _k in ('spf', 'bf'):
            if _bsec.get(_k) and str(_bsrc.get(_k, '')).startswith('欧亚'):
                secs[_k] = list(_bsec[_k])
                _applied.append('%s←%s' % (_k, _bsrc[_k]))
        for _k in ('rq', 'zjq', 'bqc'):
            if _bsec.get(_k) and str(_bsrc.get(_k, '')).startswith('欧亚'):
                _kept.append('%s(欧亚源=%s·结构异形·不覆盖)' % (_k, _bsrc[_k]))
        print('=' * 70)
        print('🔴P9 数据桥消费: 欧亚填充段 %d 个（%s）' % (len(_applied), ' · '.join(_applied) or '无'))
        if _kept:
            print('   结构异形未覆盖: %s' % ' · '.join(_kept))
        print('   🔴保留竞彩: bqc 半全场 / 逐T 时序 / 公众情绪（物理不可替）')
        if _jc_spf and _bsec.get('spf'):
            print('   对照(竞彩源·散户噪音·不参与主判定): %s' % (_jc_spf[-1][1],))
        print('=' * 70)
    # 🔴2026-10-07 审计补: 未归一化 txt 静默降级告警（原始 txt 解析 spf=0 → 下游全三态）
    if len(secs.get('spf') or []) == 0:
        print('=' * 70)
        print('🔴🔴 告警: 胜平负段未识别(spf 时点=0) → 本 txt **未经过归一化**或格式异常')
        print('    🔴 铁则: 用户 txt 到手第一个动作 = txt_normalize')
        print('    → 请先执行: python data/tmp/txt_normalize.py <原始txt> → 得 std_<name>.txt 后再跑')
        print('    ⚠️ 未归一化时: 变动层(V1/D1/V2)/竞彩逐T形态学/低赔变动重排 将**全部静默失效**(三态)')
        print('=' * 70)
    print("=" * 70)
    print("calc_match.py — V3.5.58 计算脚本（确定性计算·模型只判断）")
    print("=" * 70)

    # 1. 胜平负
    if 'spf' in secs and secs['spf']:
        ts, odds = secs['spf'][-1]
        vig, prob = dejuice(odds)
        # 🔴2026-10-21 修复(F1 反抽水信号失效·P1-5 只修了一半): P9 覆盖 spf 末点后
        #   上方 vig 算的是**欧亚赔率**抽水(约1.5%)·非竞彩(约12.9%) → 反抽水比从 1.88 变成 0.22
        #   → F1 情境因子(>1.30 触发)四场全部失效。故单独用**竞彩原序末点**算竞彩抽水率。
        _jc_last_odds = (secs.get('spf_jc') or [])[-1][1] if secs.get('spf_jc') else None
        try:
            vig_jc = dejuice(_jc_last_odds)[0] if _jc_last_odds else vig
        except Exception:
            vig_jc = vig
        print(f"\n【胜平负】末盘({ts}): {odds}")
        print(f"  去抽水率: {vig*100:.2f}% → 隐含: 主{prob.get('胜',0)*100:.1f}%/平{prob.get('平',0)*100:.1f}%/客{prob.get('负',0)*100:.1f}%")
        # 🔴2026-08-29评审固化·P0-1: 校准后概率（prob_calibration.json·热门低估偏差·禁仅等比例去水）
        try:
            calib = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prob_calibration.json'), encoding='utf-8'))
            ph = prob.get('胜', 0)
            adj = 0
            for k, v in calib.items():
                lo, hi = float(k.split('-')[0]), float(k.split('-')[1])
                if lo <= ph < hi: adj = v['bias_pp'] / 100; break
            print(f"  🔴校准后主胜概率(P0-1): {ph*100:.1f}% + {adj*100:+.1f}pp = {(ph+adj)*100:.1f}% (prob_calibration.json·热门低估·用于凯利/λ反推)")
        except Exception:
            print(f"  🔴提示: 等比例去抽水未校准「赔率理解修正」(深盘热门隐含55-85%实际命中率+2.4~3.3pp·市场低估热门)·方向判定以联赛档位实际概率为主·隐含仅作资金流/背离参考")
        # 方向差距分级（最大两方向差距）+ 🔴skew精确计算(2026-08-24·模型手算易错·case72教训: 43.2/31.6=137%温和共识非无共识)
        probs_sorted = sorted(prob.values(), reverse=True)
        if len(probs_sorted) >= 2:
            gap = (probs_sorted[0] - probs_sorted[1]) * 100
            level = '明确区(>15pt)' if gap > 15 else ('倾向区(10-15pt)' if gap >= 10 else ('微弱区(5-10pt)' if gap >= 5 else '均衡区(<5pt)'))
            top2 = sorted(prob.items(), key=lambda x: -x[1])[:2]
            print(f"  方向差距(前两方向): {gap:.1f}pt ({top2[0][0]}vs{top2[1][0]}) → {level}")
            # 🔴skew = 最高隐含/次高隐含(精确·禁手算): <100%无共识/100-150%温和/150-200%高/≥200%极端
            skew = probs_sorted[0] / probs_sorted[1] * 100
            sklvl = '无共识(<100%)' if skew < 100 else ('温和共识(100-150%)' if skew < 150 else ('高共识(150-200%)' if skew < 200 else '极端(≥200%)'))
            print(f"  🔴skew精确计算: {probs_sorted[0]*100:.1f}/{probs_sorted[1]*100:.1f} = {skew:.0f}% → {sklvl} (修正32判定依据·禁手算)")
            # 🔴弱共识场平局并列铁律（2026-09-13·22.7万场回测: skew<150%→市场首选仅36.4-43.0%≈随机）
            if skew < 150:
                print(f"  🔴🔴弱共识场(skew={skew:.1f}%<150%) → 市场首选方向命中率仅 36.4-43.0%(≈随机) → "
                      f"**平局必须与市场首选并列（禁单押市场首选）**·置信度按原档降1档")
            elif skew >= 200:
                print(f"  ✅强共识场(skew={skew:.1f}%≥200%) → 市场首选命中 64.6% → 可单押")
        # 凯利
        k = kelly(odds, prob)
        print(f"  凯利指数(单源·恒<1·仅相对排序): " + " ".join(f"{kk}={vv:.3f}" for kk, vv in k.items()) + " 🔴单源凯利=1/Σ(1/o) 恒<1 无价值判断·有效凯利需跨市场(竞彩赔率×欧盘概率)")
        # 反抽水（欧盘抽水基准·🔴2026-08-23修复: 原固定3.1%错误→16联赛查表(与SL-jc-reverse基准表一致·Matches.csv 10万+场)·缺省6.9%）
        LEAGUE_VIG = {'epl':0.0561,'championship':0.0652,'league1':0.0685,'league2':0.0667,
                      'bundesliga':0.0689,'bundesliga2':0.0784,'seriea':0.0675,'laliga':0.0684,
                      'ligue1':0.0710,'eredivisie':0.0799,'portugal':0.0814,'finland':0.0703,
                      'norway':0.0645,'japan':0.0704,'china':0.0792,'ec':0.0729}
        league = None
        if len(sys.argv) > 2:
            league = sys.argv[2]
        eu_vig = LEAGUE_VIG.get(league or '', 0.069)
        print(f"  竞彩抽水 {vig_jc*100:.2f}% · 欧盘基准(联赛{'查表' if league in LEAGUE_VIG else '缺省6.9%'}) {eu_vig*100:.2f}% → 反抽水比 {vig_jc/eu_vig:.2f}x" + (" 🔴触发反抽水(>1.30)→F1 情境因子" if vig_jc/eu_vig > 1.30 else ""))
        if abs(vig_jc - vig) > 0.01:
            print(f"     🔴口径: 竞彩抽水 {vig_jc*100:.2f}%（竞彩原序）｜欧亚抽水 {vig*100:.2f}%（末盘概率基准·P9 双源分工）")
        # 变动序列（逐T）—— 🔴P1-5: 用竞彩原序(spf_jc)·禁跨源混算（欧亚末点仅作末盘概率基准）
        _chg_seq = secs.get('spf_jc') or secs['spf']
        if len(_chg_seq) > 1:
            first_ts, first_odds = _chg_seq[0]
            # 🔴2026-10-21 P1-5 修复(b): 末点也必须用竞彩末点（原用 odds=欧亚末点 → 「竞彩初→欧盘末」= 跨源混算）
            _last_ts, _last_odds = _chg_seq[-1]
            print(f"  变动: 初({first_ts}) {first_odds} → 末({_last_ts}) {_last_odds}")
            if secs.get('spf_jc'):
                print(f"     🔴口径: 变动/形态 = 竞彩原序（{len(_chg_seq)} 时点）｜绝对概率/末盘 = 欧亚 {odds}（P9·双源分工）")
            for k in ('胜','平','负'):
                if k in first_odds and k in _last_odds:
                    chg = (_last_odds[k] - first_odds[k]) / first_odds[k] * 100
                    print(f"    {k}: {first_odds[k]}→{_last_odds[k]} ({chg:+.1f}% {'流入' if chg < 0 else '流出'})")

    # 2. 让球
    if 'rq' in secs and secs['rq']:
        ts, odds = secs['rq'][-1]
        vig, prob = dejuice(odds)
        # 让球盘键映射（胜→让胜 等）
        kmap = {'胜': '让胜', '平': '让平', '负': '让负'}
        disp = {kmap.get(k, k): v for k, v in prob.items()}
        print(f"\n【让球】末盘({ts}): {odds}")
        print(f"  去抽水率: {vig*100:.2f}% → " + " ".join(f"{k}{v*100:.1f}%" for k, v in disp.items()))

    # 3. 总进球
    if 'zjq' in secs and secs['zjq']:
        ts, odds = secs['zjq'][-1]
        vig, prob = dejuice(odds)
        # 2026-08-31 fix: key with '球' char (0球/7+球) -> normalize
        prob = {k.replace('球', ''): v for k, v in prob.items()}
        keys = sorted([k for k in prob if re.match(r'^\d+(\+?)$', k)], key=lambda x: int(x.rstrip('+')))
        print(f"\n【总进球】末盘({ts}): {odds}")
        print(f"  去抽水率: {vig*100:.2f}%")
        cum = 0
        for k in keys:
            cum += prob.get(k, 0) * 100
            print(f"    {k}球: {prob.get(k,0)*100:.1f}% (≤{k} 累计{cum:.1f}%)")
        p2 = sum(prob.get(k, 0) for k in keys if k in ('0','1','2'))
        p3 = sum(prob.get(k, 0) for k in keys if k in ('0','1','2','3'))
        p4 = sum(prob.get(k, 0) for k in keys if int(k.rstrip('+')) >= 4) if keys else 0
        print(f"  ≤2球 {p2*100:.1f}% · ≤3球 {p3*100:.1f}% · ≥4球 {p4*100:.1f}%")
        o25 = 1 - p2
        print(f"  O2.5 ≈ {1/o25:.2f} (over {o25*100:.0f}%)" if o25 > 0 else "  O2.5 极端")
        o35 = 1 - p3
        print(f"  O3.5 ≈ {1/o35:.2f} (over {o35*100:.0f}%)" if o35 > 0 else "  O3.5 极端")
        # 🔴2026-09-06: 竞彩总进球赔率反推增强(goal_odds_analyzer·方案阈值优化版)——大小球五级倾向+比分量级
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from goal_odds_analyzer import analyze_goal_odds
            _o8 = []
            for _k in ('0', '1', '2', '3', '4', '5', '6', '7+'):
                _v = odds.get(_k)
                if _v is None: _v = odds.get(_k + '球')   # 🔴兼容'球'后缀表头(0球/7+球)
                _o8.append(float(_v) if _v else 0.0)
            _ga = analyze_goal_odds(_o8)
            if 'error' in _ga:
                print('  ⚠️goal_odds未执行(赔率解析异常):', _ga['error'])
            else:
                print('🔴进球数赔率反推(goal_odds_analyzer): 返奖%.1f%%(倒数和%.4f) | mean=%.2f球 | 量级: %s' % (
                    _ga['返奖率'], _ga['倒数和'], _ga['mean'], _ga['量级']))
                print('    大小球: over1.5=%.1f%% over2.5=%.1f%% over3.5=%.1f%% | %s | 倾向: %s' % (
                    _ga['over1.5'], _ga['over2.5'], _ga['over3.5'], _ga['大小球单调'], _ga['大小球倾向']))
                if _ga.get('信号强度'):
                    print('    🔴信号强度: %s' % _ga['信号强度'])
                if _ga.get('极端档提示'):
                    print('    ⚠️%s' % _ga['极端档提示'])
                if 0.47 <= _ga['over2.5'] / 100 <= 0.53:
                    print('    ⚫中性区(over2.5=%.1f%%·47-53%%): 不判大小方向（V3.5.74 已将原「44-48%%边缘带」并入信号强度分层：42-45%%=中信号/45-47%%=弱信号）' % _ga['over2.5'])
                if _ga['异常'] != '无':
                    print('    校验提示: %s' % ('; '.join(_ga['异常'][:6]) + ('...' if len(_ga['异常']) > 6 else '')))
                if '一致度' in _ga:
                    print('    与泊松: KL=%.3f %s | α=%.2f | 偏差: %s' % (_ga['KL'], _ga['一致度'], _ga['α'],
                          _ga['偏差信号'] if _ga['偏差信号'] != '无' else '无'))
        except Exception as _e:
            print('  ⚠️goal_odds_analyzer未执行:', _e)

    # 4. 半全场 → 半场三元 + 45A推导
    if 'bqc' in secs and secs['bqc']:
        ts, odds = secs['bqc'][-1]
        vig, prob = dejuice(odds)
        ht_home = prob.get('胜胜', 0) + prob.get('胜平', 0) + prob.get('胜负', 0)
        ht_draw = prob.get('平胜', 0) + prob.get('平平', 0) + prob.get('平负', 0)
        ht_away = prob.get('负胜', 0) + prob.get('负平', 0) + prob.get('负负', 0)
        print(f"\n【半全场】末盘({ts}): 半场主{ht_home*100:.1f}%/半场平{ht_draw*100:.1f}%/半场客{ht_away*100:.1f}% (抽水{vig*100:.1f}%)")
        if 'spf' in secs and secs['spf']:
            _, spo = secs['spf'][-1]
            _, sprob = dejuice(spo)
            pm = sprob.get('胜', 0); pd = sprob.get('平', 0); pa = sprob.get('负', 0)
            print(f"  vs 胜平负市场: 主{pm*100:.1f}%/平{pd*100:.1f}%/客{pa*100:.1f}%")
            print(f"  🔴半场-全场对比: 半场平{ht_draw*100:.1f}% vs 全场平{pd*100:.1f}% → 半场平{'高于' if ht_draw > pd else '低于'}市场{' (首回合保守·修正53 S3参考)' if ht_draw >= 0.40 else ''}")
            print(f"  半场主{ht_home*100:.1f}% vs 全场主{pm*100:.1f}% → {'半场落后预期' if ht_home < pm else '半场领先预期'}")

    # 5. 比分 → CS去抽水 P_i 排序 + BTTS估算
    if 'bf' in secs and secs['bf']:
        ts, odds = secs['bf'][-1]
        # 🔴2026-09-29 修复（用户批准·三场 NL 实测）: 竞彩比分盘后续时点常只公布「胜方比分」档
        #   → 末盘档位残缺时 CS 去抽水完全失真（实测 217 主97.9%/平0.0%/客0.0%·抽水-25.8%；218 -70.5%；219 同类）
        #   → 回退到最近一个「档位最完整」的时点（份数 ≥ max(10, 末盘×1.5)）
        _full = max(secs['bf'], key=lambda x: len(x[1]))
        if len(_full[1]) >= max(10, int(len(odds) * 1.5)):
            print(f"  🔴末盘档位不全({len(odds)}档·缺平/客档) → 回退最近完整时点({_full[0]}·{len(_full[1])}档)")
            ts, odds = _full
        # 🔴2026-10-20 二轮深检修(P0-1 消费端双保险): 键分隔符统一为 ':'
        #   （欧亚波胆经数据桥可能带 '-'·原判据 k.count(':')==1 → 全被过滤 → BTTS/CS 侧 0.0%）
        if isinstance(odds, dict) and any("-" in str(k) for k in odds):
            odds = {str(k).replace("-", ":").replace("/", ":"): v for k, v in odds.items()}
        vig, prob = dejuice(odds)
        print(f"\n【比分】末盘({ts}) CS去抽水(抽水{vig*100:.1f}%) P_i排序:")
        for k, v in sorted(prob.items(), key=lambda x: -x[1]):
            print(f"    {k}: {v*100:.1f}%")
        # BTTS估算
        btts = sum(v for k, v in prob.items() if k.count(':') == 1 and int(k.split(':')[0]) >= 1 and int(k.split(':')[1]) >= 1)
        print(f"  BTTS估算: {btts*100:.1f}%")
        # 主/平/客侧合计
        home = sum(v for k, v in prob.items() if k.count(':') == 1 and int(k.split(':')[0]) > int(k.split(':')[1]))
        draw = sum(v for k, v in prob.items() if k.count(':') == 1 and int(k.split(':')[0]) == int(k.split(':')[1]))
        away = sum(v for k, v in prob.items() if k.count(':') == 1 and int(k.split(':')[0]) < int(k.split(':')[1]))
        print(f"  CS侧: 主{home*100:.1f}%/平{draw*100:.1f}%/客{away*100:.1f}%")
        # 比分变动（初末对比）
        if len(secs['bf']) > 1:
            first_ts, first_odds = secs['bf'][0]
            print(f"  比分变动: 初({first_ts}) → 末")
            for k in odds:
                if k in first_odds and first_odds[k] != odds[k]:
                    chg = (odds[k] - first_odds[k]) / first_odds[k] * 100
                    print(f"    {k}: {first_odds[k]}→{odds[k]} ({chg:+.1f}% {'流入' if chg < 0 else '流出'})")

    # 🔴扩展模块（2026-08-24·防手算: D1背离/修正53预计算/V5跨市场·--eu 参数）
    eu_odds = None
    if '--eu' in sys.argv:
        try:
            i = sys.argv.index('--eu')
            eu_odds = sys.argv[i+1]
        except IndexError:
            pass
    # 🔴2026-10-13 审计修复(P1·margin_candidates 口径不一致): 接受欧盘**真实让球** --handi
    #   → 覆盖竞彩让球 _rq_handicap（竞彩让球常与欧盘真实盘口不符: 如 case242 竞彩 -1 vs 欧盘 -0.25）
    #   → 净胜档多档候选池(margin_candidates_pool)改用**真实盘口**（_rq_handicap 仅此一处被读·覆盖安全）
    if '--handi' in sys.argv:
        try:
            _ih = sys.argv.index('--handi')
            secs['_rq_handicap'] = float(sys.argv[_ih + 1])
        except (IndexError, ValueError):
            pass
    feat = parse_features(text)
    print(run_extensions(secs, feat, eu_odds))

    print("\n" + "=" * 70)
    print("提示: 模型消费以上结果做【判断】——资金流方向/诱阻识别/信号聚合/主锚次锚·计算不占推理")


# ============ 扩展模块（2026-08-24·防手算错误·结构性机制） ============

def parse_features(text):
    """解析【特征分析】段 → {交锋平数, 主队近10平率, 客队客场平率, 主队近10战绩, 客队客场战绩}"""
    feat = {}
    m = re.search('近10场交锋[：:]\\s*([\u4e00-\u9fa5]+)(\\d+)[胜勝](\\d+)[平](\\d+)[负敗]', text)
    if m:
        feat['交锋平数'] = int(m.group(3))
    m = re.search('近10场战况[：:]\\s*([\u4e00-\u9fa5]+)(\\d+)[胜勝](\\d+)[平](\\d+)[负敗]', text)
    if m:
        feat['主队近10平率'] = int(m.group(3)) / 10
    m = re.search('同主客战况[：:]\\s*([\u4e00-\u9fa5]+)(\\d+)[胜勝](\\d+)[平](\\d+)[负敗]', text)
    if m:
        feat['客队客场平率'] = int(m.group(3)) / 10
    return feat


def x53_predict(sections, feat):
    """修正53 S1-S7 预计算（防手算·输出信号计数+触发判定）"""
    res = []
    # S1: CS平局比分池内P_i前排 或 资金流入≥3%（需比分盘多时点·单点标观察）
    s1 = '✗'
    if 'bf' in sections and sections['bf']:
        ts, odds = sections['bf'][-1]
        vig, prob = dejuice(odds)
        draw_cs = {k: v for k, v in prob.items() if k in ('0:0', '1:1', '2:2')}
        if draw_cs:
            top = sorted(prob.items(), key=lambda x: -x[1])[:3]
            top_keys = [k for k, _ in top]
            if any(k in top_keys for k in ('0:0', '1:1', '2:2')):
                s1 = '✓(平局比分P_i前排)'
            if len(sections['bf']) >= 2:  # 多时点→看资金流入(或条件·增强标注)
                t0, o0 = sections['bf'][0]
                flows = []
                for k in ('0:0', '1:1', '2:2'):
                    if k in o0 and k in odds:
                        chg = (odds[k] - o0[k]) / o0[k]
                        if chg < -0.03:
                            flows.append(f'{k}流入{-chg*100:.0f}%')
                if flows:
                    s1 = '✓(' + ','.join(flows) + (f'+P_i前排' if '✓' in s1 else '') + ')'
            # 单时点:P_i前排本身即S1充分条件(修正53: P_i前排 或 资金流入)·保留✓·标注单时点
    # S2: 平局降赔≥2%
    s2 = '✗'
    if 'spf' in sections and sections['spf'] and len(sections['spf']) >= 2:
        t0, o0 = sections['spf'][0]
        t1, o1 = sections['spf'][-1]
        if '平' in o0 and '平' in o1:
            chg = (o1['平'] - o0['平']) / o0['平']
            if chg <= -0.02:
                s2 = f'✓(平降{chg*100:.1f}%)'
    # S3: 半场平≥45%（半场平 = 平胜+平平+平负 组合隐含·与主输出一致）
    s3 = '✗'
    if 'bqc' in sections and sections['bqc']:
        ts, odds = sections['bqc'][-1]
        vig, prob = dejuice(odds)
        ht_draw = prob.get('平胜', 0) + prob.get('平平', 0) + prob.get('平负', 0)
        if ht_draw >= 0.45:
            s3 = f'✓(半场平{ht_draw*100:.1f}%)'
        else:
            s3 = f'✗(半场平{ht_draw*100:.1f}%<45%)'
    # S4: 主队近10平率≥30% 或 客队客场平率≥40%
    s4 = '✗'
    if feat.get('主队近10平率') is not None and feat['主队近10平率'] >= 0.30:
        s4 = f"✓(主平率{feat['主队近10平率']*100:.0f}%)"
    elif feat.get('客队客场平率') is not None and feat['客队客场平率'] >= 0.40:
        s4 = f"✓(客客场平率{feat['客队客场平率']*100:.0f}%)"
    # S5: |ELO差|<100 → 不计（仅参考不计数·回测 B 独立 +4.5pp）
    # 2026-10-20 修(P2·三场审计): 原硬编码「无ELO数据源」→ 传了 --elo 也不读 → 留痕失真
    s5 = '不计(无ELO数据源)'
    try:
        if '--elo' in sys.argv:
            _el5 = float(sys.argv[sys.argv.index('--elo') + 1])
            s5 = ('OK(差%.0f<100·仅参考不计数)' % _el5) if abs(_el5) < 100 else ('X(差%.0f>=100)' % _el5)
    except Exception:
        pass
    # S6: 交锋近2场平≥1 或 近3场平≥2（txt仅汇总·标观察）
    s6 = '✗'
    if feat.get('交锋平数') is not None and feat['交锋平数'] >= 2:
        s6 = f"⚠️(交锋{feat['交锋平数']}平·位置不确定·观察)"
    # S7: 两回合首回合（非欧战=0）
    s7 = '✗(非两回合)'
    # 🔴2026-08-29评审固化·P0-2: 分组去相关（组A资金/S1+S2+S8·组B盘口/S9-S11·组C基本面/S4+S6+S12·组D赛事/S3+S7·组内最多计1/1.5分·禁重复计数）
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from draw_signal_aggregator import draw_signal_aggregator
        signals = {
            'S1': 1 if s1.startswith('✓') else 0, 'S2': 1 if s2.startswith('✓') else 0,
            'S3': 1 if s3.startswith('✓') else 0, 'S4': 1 if s4.startswith('✓') else 0,
            'S6': 1 if s6.startswith('✓') else 0, 'S8': 0,
            'S9': 0, 'S10': 0, 'S11': 0, 'S12': 0,
        }
        score, trigger, detail = draw_signal_aggregator(signals, pd if 'pd' in dir() else 0)
        res.append(f"🔴修正53预计算: S1{s1} | S2{s2} | S3{s3} | S4{s4} | S5{s5} | S6{s6} | S7{s7}")
        res.append(f"  🔴分组去相关(P0-2): {detail} → 总分{score} → " + ({'sole': '平局唯一(≥4+P_平≥25%)', 'parallel': '平局并列(≥2.5 或 D1背离+≥1.5)', 'none': '不并列'}[trigger]))
    except Exception:
        cnt = sum(1 for s in (s1, s2, s3, s4, s6) if s.startswith('✓'))
        res.append(f"🔴修正53预计算: S1{s1} | S2{s2} | S3{s3} | S4{s4} | S5{s5} | S6{s6} | S7{s7}")
        res.append(f"  信号计数(不计S5): {cnt} → " + ("≥3触发平局并列" if cnt >= 3 else ("≥5触发平局唯一" if cnt >= 5 else "<3不并列")))
    return '\n'.join(res)





def margin_candidates_pool(sections):
    """净胜档多档候选(2026-08-29优化·margin_candidates执行入口): 亚盘盘口->净胜档主+相邻档->各档查表合并候选池
    替代泊松Top1单档(2万场: 21.1% vs 47.4% +26.3pp)"""
    import sys as _s, os as _o, re as _re
    _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
    from calc_v3572 import margin_candidates, score_depth_lookup
    out = []
    if 'rq' not in sections or not sections['rq']:
        return "  [netmargin] 无亚盘数据->[0]平局档保守"
    seq = sections['rq']
    last = seq[-1][1] if isinstance(seq[-1], tuple) else seq[-1]
    # 🔴2026-09-04审计修复(客让场方向缺陷·case129/130/131三现): 优先用标题让球数(符号=主队视角: -1主让1/+1客让1)
    #  原逻辑从让球盘赔率取数恒取负(abs·当主让)→客让场必输出主胜候选(如皇马客让场出4:0/5:0)·已废弃
    hs = sections.get('_rq_handicap')
    if hs is None:  # 无标题让球数(非标txt)·降级旧逻辑但修正: 取让球盘行数字仅当无'+/-'标题时
        hs = None
        vals = last.values() if isinstance(last, dict) else [str(last)]
        for v in vals:
            m = _re.search(r'[-+]?[0-9]+\.?[0-9]*', str(v))
            if m:
                try:
                    n = float(m.group(0))
                    hs = -n if n >= 1 else n  # 让球盘赔率≥1→弱启发(方向未知·保守主让负)
                except Exception:
                    pass
                break
    if hs is None:
        return "  [netmargin] 亚盘盘口未识别->[0]"
    cands = margin_candidates(hs)
    ov = 1.9
    pool = []
    for m in cands:
        lk = score_depth_lookup(m, ov, odd_draw=3.3 if m == 0 else None)
        if lk:
            pool.append(lk['anchor'])
            if lk.get('second'): pool.append(lk['second'])
    uniq = list(dict.fromkeys(pool))
    out.append("  [netmargin] 亚盘" + str(hs) + " 档位" + str(cands) + " 候选池 " + '/'.join(uniq))
    return chr(10).join(out)



# 🔴P40 DEPRECATED（2026-10-30 批次5）: 全库无真调用（仅在字符串里提到自己）
#   calc_all 直接调 calc_v3572.match_classifier/handicap_intent_analyzer → 本包装未用。
#   → 保留备查·不接入
def trap_classify_output(sections, oh=None, od=None, oa=None, handi=None, water=None):
    """盘口诱阻识别预计算(2026-09-02·match_classifier执行入口): 输出比赛分类+异常指标·Step5消费
    需欧盘ML+亚盘盘口+水位·无→降级标注"""
    import sys as _s, os as _o
    _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
    from calc_v3572 import match_classifier
    if not (oh and od and oa):
        return "  [trap] 无欧盘ML->不触发(需欧盘+亚盘)"
    cf = match_classifier(oh, od, oa, handi=handi, water=water)
    if cf['total_score'] == 0:
        return "  [trap] 正常盘(总分0·70%正常·不硬套)"
    return "  [trap] %s(总分%d·置信%.0f%%): %s" % (cf['match_type'], cf['total_score'], cf['confidence']*100, '; '.join(cf['anomaly_details']) or '无明细')

def goal_bin_output(sections):
    """总进球档查表预计算(2026-09-02·goal_bin_probs执行入口): O2.5→总进球档概率+净3+·Step6/7消费"""
    import sys as _s, os as _o
    _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
    from calc_v3572 import goal_bin_probs
    ov = None
    for key in ('dq', 'size'):
        if key in sections and sections[key]:
            try:
                for tup in sections[key]:
                    row = tup[1] if isinstance(tup, tuple) else tup
                    for v in (row.values() if isinstance(row, dict) else []):
                        s = str(v)
                        import re
                        # 提取「2.5」后的赔率数字(如 '2.5 1.24' 或 '大于2.5球:1.24' → 1.24)
                        m = re.search(r'2\.5[^0-9]*([0-9]+\.[0-9]+)', s)
                        if m:
                            try: ov = float(m.group(1))
                            except: pass
            except: pass
    if ov is None: return "  [goalbins] O2.5未识别->不触发"
    g = goal_bin_probs(ov)
    if not g: return "  [goalbins] O2.5=" + str(ov) + " 档外->不触发"
    _tp = ''
    if g.get('top'):
        _tp = " | 典型比分:" + " ".join("%s(%.1f%%)" % (s, pc) for s, pc in g['top'])
    return "  [goalbins] O2.5=" + str(ov) + " 总进球档 0-1:" + str(round(g['prob_01']*100)) + "% 2球:" + str(round(g['prob_2']*100)) + "% 3球:" + str(round(g['prob_3']*100)) + "% 4+:" + str(round(g['prob_4']*100)) + "% 净3+:" + str(round(g['net3']*100)) + "%" + _tp + " (Step6/7量级依据)"

def d1_divergence(sections):
    """D1背离检测：主方向升赔≥2T累计>3%（防手算·case42/44教训）"""
    out = []
    if 'spf' in sections and sections['spf'] and len(sections['spf']) >= 2:
        seq = sections['spf']
        t0, o0 = seq[0]
        t1, o1 = seq[-1]
        n_times = len(seq)
        for k in ('胜', '平', '负'):
            if k in o0 and k in o1:
                chg = (o1[k] - o0[k]) / o0[k]
                rising_times = sum(1 for i in range(1, len(seq)) if seq[i][1].get(k, 0) > seq[i-1][1].get(k, 0))
                if chg > 0.03 and rising_times >= 2:
                    out.append(f"  🔴D1背离候选: {k}升赔{chg*100:.1f}%(累计·{rising_times}个时点上升) → 触发硬降级检查")
                else:
                    out.append(f"  D1检测: {k}变动{chg*100:+.1f}%({rising_times}时点上升) → {'不触发' if chg < 0.03 else '上升时点<2·观察'}")
    return '\n'.join(out) if out else '  D1检测: 胜平负数据不足'


def jc_series_shape(sections):
    """\U0001f534竞彩逐T 形态学（2026-10-07 用户指令·变动层主源）

    对主/平/客三向分别计算: 净变动% / 单调性(最长连续同向段·反转次数) / 加速度(末段步幅 vs 全段步幅)
    形态标签: 持续单向(≥3段·强) / 末段加速(≥1.5x·强) / 反复震荡(≥3次反转·弱) / 平淡
    用途: Step2 变动层（V1 形态学增强）+ Step5 资金流判定（与 V3.5.76 双通道 C1/C2/C3 联动）
    依据: 竞彩逐T 时点密度(5-6)远高于欧盘快照(1-3) → 逐T 为资金流判定主源
          （case225: 主胜 1.90→1.85→1.90→1.95→2.01→2.06 连升4段+末段加速 → 实际 0:2 客胜）
    铁则: 仅调置信度/资金流判定·不反转 L2 硬核方向·时点<3 三态不触发
    """
    seq = sections.get('spf') or []
    if len(seq) < 3:
        return '  竞彩逐T形态: 时点不足(<3)·三态不触发'
    lines, strong = [], []
    for k in ('胜', '平', '负'):
        vals = [x[1].get(k) for x in seq]
        if any(v is None for v in vals):
            continue
        net = (vals[-1] - vals[0]) / vals[0] * 100
        steps = [vals[i] - vals[i - 1] for i in range(1, len(vals))]
        best = run = 1
        for i in range(1, len(steps)):
            if steps[i] * steps[i - 1] > 0:
                run += 1
                best = max(best, run)
            else:
                run = 1
        rev = sum(1 for i in range(1, len(steps)) if steps[i] * steps[i - 1] < 0)
        avg = abs(sum(steps)) / len(steps)
        tail = abs(sum(steps[-2:])) / 2 if len(steps) >= 2 else avg
        accel = (tail / avg) if avg > 1e-9 else 1.0
        tags = []
        if best >= 3 and abs(net) >= 3:
            tags.append('持续单向' + ('流出' if net > 0 else '流入'))
            strong.append((k, net))
        if accel >= 1.5 and abs(net) >= 3:
            tags.append('末段加速(%.2fx)' % accel)
        if rev >= 3:
            tags.append('反复震荡·信号弱')
        if not tags:
            tags.append('平淡')
        lines.append('  %s: 首→末 %+.1f%% · 最长连续%s%d段·反转%d次 · 末段/全段步幅 %.2fx → %s'
                     % (k, net, '升' if net > 0 else '降', best, rev, accel, ' / '.join(tags)))
    if not lines:
        return '  竞彩逐T形态: 数据不足'
    head = ('\U0001f534竞彩逐T形态学（2026-10-07 用户指令·变动层主源·时点%d个）:' % len(seq))
    so = [k for k, v in strong if v > 0]
    si = [k for k, v in strong if v < 0]
    parts = []
    if so:
        parts.append('／'.join(so) + '【持续流出】')
    if si:
        parts.append('／'.join(si) + '【持续流入】')
    body = ' · '.join(parts) if parts else '无持续单向方向(震荡/平淡·弱信号)'
    cross = '  \U0001f534双向对倒(资金转移)→ 支持「低赔大幅变动·主方向重排」' if (so and si) else ''
    foot = ('  → 资金流: %s%s | 铁则: 仅调置信度/资金流·不反转 L2 方向·与双通道 C1/C2/C3 联动' % (body, cross))
    return '\n'.join([head] + lines + [foot])



def low_odds_shift(sections, edge=None, th=5.0):
    """🔴低赔方大幅升赔 → 不再严格依照最低赔率（2026-10-07 用户指令）

    判定: 首时点最低赔方向(低赔方) 首→末升赔 ≥ th%  且  次低赔对手侧降赔(≤0%)
    动作: 低赔方【不再独主】(降为并列候选) · 对手侧【升为并列首位】
          若给 edge 且对手侧 edge ≥ +10pp → 对手侧【升为主方向】(被市场低估)
    约束: 不推翻 D1(仍降档) · 覆盖最多两向(2026-10-29 修订·禁三向) · 不反转(仅重排主次)
          机理驱动·未回测 → 前瞻验证中(触发场次须留存·累计 ≥20 场后回测)
    依据: case225 卢森堡vs保加利亚(2026-10-06·主胜 6 时点连续升赔 1.90→2.06/+8.4%
          + 平客双降赔·R10 edge H−4.21/A+11.23 → 实际 0:2 客胜·低赔方向未中)
    """
    seq = sections.get('spf') or []
    if len(seq) < 3:
        return '  低赔变动重排: 时点不足(<3)·三态不触发'
    K = {'胜': 'H', '平': 'D', '负': 'A'}
    o0, o1 = seq[0][1], seq[-1][1]
    side_k = min(('胜', '平', '负'), key=lambda k: o0[k])
    rise = (o1[side_k] - o0[side_k]) / o0[side_k] * 100
    low = min(x[1][side_k] for x in seq)
    rise_low = (o1[side_k] - low) / low * 100
    others = [k for k in ('胜', '平', '负') if k != side_k]
    opp_k = min(others, key=lambda k: o0[k])
    opp_chg = (o1[opp_k] - o0[opp_k]) / o0[opp_k] * 100
    if rise >= th and opp_chg <= 0:
        act = '低赔方【不再独主】(降为并列候选) · 对手侧=%s(降赔)【升为并列首位】' % opp_k
        # 🔴任一「非低赔方向」edge ≥ +10pp → 该方向升为主方向（不限于次低赔·case225 客胜 edge +11.23 教训）
        if edge:
            cand = [(k, edge.get(K[k])) for k in others if edge.get(K[k]) is not None]
            if cand:
                bk, bv = max(cand, key=lambda x: x[1])
                if bv >= 10:
                    act = ('对手侧=%s【升为主方向】(edge %+.1fpp≥+10·被市场低估) · 低赔方降为并列' % (bk, bv))
        return ('🔴低赔大幅变动·主方向重排: 低赔方=%s(%s) 升赔 %+.1f%%(自最低点 %+.1f%%) · '
                '对手侧=%s 降赔 %+.1f%%\n   → %s\n'
                '   🔴铁则: 保留 D1 降档 + 覆盖最多两向（禁三向·2026-10-29） · 不反转(仅重排主次) · '
                '机理驱动·前瞻验证中(触发场次留存·≥20 场后回测)'
                % (side_k, K[side_k], rise, rise_low, opp_k, opp_chg, act))
    return ('  低赔变动重排: 低赔方=%s(%s) 首→末 %+.1f%%(自最低点 %+.1f%%) · 对手侧=%s %+.1f%% → '
            '未达触发(需 升赔≥%.0f%% 且 对手侧降赔)' % (side_k, K[side_k], rise, rise_low, opp_k, opp_chg, th))


def v5_divergence(jc_prob, eu_odds):
    """V5跨市场分歧：竞彩隐含 vs 欧盘隐含（需 --eu 主,平,客 参数）"""
    if not eu_odds:
        return '  V5跨市场: 未提供欧盘(--eu 主,平,客·跳过·模型判断时用Odds-API/the-odds-api实测值)'
    try:
        eo = [float(x) for x in eu_odds.split(',')]
        if len(eo) != 3 or any(x <= 1 for x in eo):
            return '  V5跨市场: --eu 格式错误(需 主,平,客 三个>1的赔率)'
        inv = [1/x for x in eo]
        s = sum(inv)
        eu_p = [x/s for x in inv]
        diff = [(jc_prob.get('胜',0)-eu_p[0])*100, (jc_prob.get('平',0)-eu_p[1])*100, (jc_prob.get('负',0)-eu_p[2])*100]
        names = ['主', '平', '客']
        parts = [f"{names[i]}{diff[i]:+.1f}pp" for i in range(3) if abs(diff[i]) > 1]
        # 有效凯利 = 竞彩赔率×欧盘概率
        ek = []
        jc_odds_est = {k: 1/(p+1e-9) for k, p in jc_prob.items()}
        for i, k in enumerate(['胜', '平', '负']):
            ek.append(f"{k}{1/(jc_prob.get(k,0.01)+1e-9)*eu_p[i]:.2f}")
        return f"  V5跨市场分歧: {'·'.join(parts) if parts else '三向<1pp一致'} | 有效凯利(竞彩赔率×欧盘概率): {' '.join(ek)}"
    except Exception as e:
        return f'  V5跨市场: 解析失败({e})'


def run_extensions(sections, feat, eu_odds=None):
    """运行全部扩展模块（D1背离+修正53+V5）·防手算"""
    out = []
    out.append('')
    out.append('【扩展·防手算（2026-08-24结构性机制）】')
    out.append('🔴D1背离检测:')
    # 🔴2026-10-21 P1-5 修复(c): D1/低赔重排/形态学 → 全部用**竞彩原序**(spf_jc)
    #   根因: sections['spf'] 已被 P9 覆盖为「竞彩初→欧盘末」混源序列 → 变动率跨源
    #   （case260: 客胜 竞彩原序 -13.3% 流入 → 混算 +8.5% 流出·方向相反·D1/形态学全错）
    _sec_chg = dict(sections)
    if sections.get('spf_jc'):
        _sec_chg['spf'] = sections['spf_jc']
    out.append(d1_divergence(_sec_chg))
    out.append('🔴低赔大幅变动·主方向重排(2026-10-07 用户指令):')
    out.append(low_odds_shift(_sec_chg))
    out.append(jc_series_shape(_sec_chg))
    if 'spf' in sections and sections['spf']:
        # 🔴P13.1b 修复（P0-1 修好后才暴露的第二层断链）: V5 语义 = **竞彩 vs 欧盘** 跨市场分歧。
        #   P9 数据桥（bridge_sections·src_map='欧亚--eu'）已把 sections['spf'] **末点覆盖为欧盘值**
        #   → 此时 sections['spf'] 末点 与 eu_odds 是**同一份欧盘** → V5 变成「欧盘 vs 欧盘」：
        #     实测 三向<1pp一致 + 有效凯利恒 1.00（=竞彩赔率×同源概率）→ **假一致**。
        #   假一致比"跳过"更危险：跳过至少三态可审计，假一致会被当成"市场确认"误导 Step5 方向判定。
        #   修法：V5 的「竞彩侧」取**竞彩原序末点 spf_jc**（P9 覆盖前的真实竞彩末盘·同 D1/形态学口径）；
        #         无 spf_jc（未走 P9 桥的手动调用场景）→ 退回 sections['spf']（行为与修复前一致）。
        _v5_src = sections.get('spf_jc') or sections['spf']
        ts, odds = _v5_src[-1]
        vig, prob = dejuice(odds)
        out.append(x53_predict(sections, feat))
        out.append(v5_divergence(prob, eu_odds))
    # 🔴2026-09-02结构性根除: 接入孤儿函数(防步骤遗失·曾main未调用)
    out.append('')
    out.append('🔴净胜档多档候选(margin_candidates_pool):')
    out.append(margin_candidates_pool(sections))
    out.append('🔴总进球档查表(goal_bin_output):')
    out.append(goal_bin_output(sections))
    out.append('🔴诱阻分类预计算(trap_classify_output·需欧盘参数时在calc_all调用):')
    return '\n'.join(out)

if __name__ == '__main__':
    main()