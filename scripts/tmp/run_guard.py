# -*- coding: utf-8 -*-
"""
run_guard.py — V3.5.81【执行总控·开场 preflight】（<REDACTED_SK> 触发器）
================================================================================
定位：三段质量链的「开场前」一段——
  run_guard.py（开场 preflight：归一化/参数/快照/域/命令/门禁）
    → calc_all.py（计算中：全覆盖预计算 + C01-C34 必核清单）
      → output_checker.py + check_luopan.py（交付后：报告断言 / 落盘校验）
本脚本只做【编排与防漏】，不持有任何预测规则、不做方向/比分判定（规则归 <REDACTED_SK>）。

用法（cwd = 模型根目录）：
  python data/tmp/run_guard.py <竞彩txt路径>
      [--teams "主队,客队"] [--league <联赛>] [--event <eventId>] [--kickoff "YYYY-MM-DD HH:MM"]
      [--eu "h,d,a"] [--handi <让球·主让为负>] [--home_water <主水>]
      [--o25 <大2.5赔率>] [--u25 <小2.5赔率>]
      [--inj_h <主队伤停影响分>] [--inj_a <客队伤停影响分>]
      [--p12-fund "home_fatigue=..,away_intent=.."]
任何一项缺了都不报错，只在输出里标「需补/三态」，并给可直接复制的 calc_all 命令。
"""
import os, re, sys, argparse, glob

# ── 保证能 import 同目录（data/tmp）的 calc_match / snapshot_save ──
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(os.getcwd(), 'data', 'tmp')):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

# 联赛名 → calc_all 归一化参数
LEAGUE_MAP = {
    '英超': 'epl', 'E0': 'epl', 'epl': 'epl', 'premier': 'epl',
    '西甲': 'laliga', 'la liga': 'laliga', 'laliga': 'laliga',
    '意甲': 'seriea', 'serie a': 'seriea', 'seriea': 'seriea',
    '德甲': 'bundesliga', 'bundesliga': 'bundesliga',
    '法甲': 'ligue1', 'ligue 1': 'ligue1', 'ligue1': 'ligue1',
    '欧冠': 'ucl', '欧冠联赛': 'ucl', '欧洲冠军联赛': 'ucl', 'ucl': 'ucl',
    '欧联': 'uel', '欧联杯': 'uel', '欧洲联赛': 'uel', 'uel': 'uel',
    '欧协联': 'uecl', '欧协': 'uecl',
    # —— 其他联赛（CORE：calc_all 识别为非五大，自动不触发 C13/C27；值仅用于 --league）——
    '英冠': '英冠', 'championship': '英冠', '日职': '日职', 'jleague': '日职', 'j1': '日职',
    '葡超': '葡超', '荷甲': '荷甲', '苏超': '苏超', '中超': '中超', '挪超': '挪超',
    '奥甲': '奥甲', '俄超': '俄超', '土超': '土超', '比甲': '比甲', '瑞士超': '瑞士超',
    '丹麦超': '丹麦超', '瑞典超': '瑞典超', '波兰超': '波兰超', '沙特联': '沙特联',
    'mls': 'mls', '巴甲': '巴甲', '阿超': '阿超', '澳超': '澳超', 'k联赛': 'k联赛',
    '亚冠': '亚冠', '解放者杯': '解放者杯', '南美杯': '南美杯',
}
NL_KEYS = ('欧国联', '国家联赛', 'nations league', 'league_id=5', '世预赛', '欧预赛', '世界杯', '欧洲杯', '美洲杯')
FIVE = {'epl', 'laliga', 'seriea', 'bundesliga', 'ligue1'}
UCL = {'ucl', 'uel', 'uecl'}


def profile_of(lcode, lraw):
    """返回 (profile, 中文域)。FULL=五大/欧战全量；NL=国家队走 Step4.8；CORE=其他联赛通用主干。"""
    if lcode == 'NL' or (lraw and any(k in lraw for k in NL_KEYS)):
        return 'NL', '欧国联/国家队'
    if lcode in FIVE:
        return 'FULL-5', '五大联赛(%s)' % lcode
    if lcode in UCL:
        return 'FULL-UCL', '欧战(%s)' % lcode
    # 已识别为五大/欧战中文但未归码的兜底
    if lraw in ('英超', '西甲', '意甲', '德甲', '法甲'):
        return 'FULL-5', '五大联赛(%s)' % lraw
    if lraw in ('欧冠', '欧联', '欧协联'):
        return 'FULL-UCL', '欧战(%s)' % lraw
    return 'CORE', '其他联赛(%s)·通用主干' % (lraw or '未知')


def _read(path):
    for enc in ('utf-8', 'gbk', 'utf-8-sig'):
        try:
            return open(path, encoding=enc).read()
        except Exception:
            continue
    return ''


def parse_header(text):
    """鲁棒提取 (主队, 客队, 联赛原文, 联赛归一码, kickoff)。兼容多种竞彩 txt 变体：
       - 赛事行可能带/不带「周X编号」「联赛前缀」（旧：周三006 西甲 马竞(主)；新：圣克拉拉(主)）
       - 联赛可能在赛事行内（旧）或独立「联赛：葡超 ...」行（新）
       - 时间关键词「开赛时间」或「比赛时间」"""
    home = away = league_raw = league_code = kickoff = None
    m = re.search(r'赛事[：:]\s*(.+?)\(主\)\s*[Vv][Ss]\s*(.+?)\(客\)', text)
    if m:
        head, away = m.group(1).strip(), m.group(2).strip()
        head = re.sub(r'周[一二三四五六日天]\s*\d+', '', head).strip()
        for k in sorted(LEAGUE_MAP, key=len, reverse=True):
            if head.startswith(k):
                league_raw = k
                head = head[len(k):].strip()
                break
        home = head.strip()
    # ① 独立「联赛：」行（新格式，最可靠）
    ml = re.search(r'联赛[：:]\s*\s*([\u4e00-\u9fa5A-Za-z0-9]+?)(?=\s|20\d{2}|赛季|常规赛|第|$)', text)
    if ml and not league_raw:
        league_raw = ml.group(1).strip()
    # ② 赛事行前缀没有、独立行也没有 → 全文找已知联赛词
    if not league_raw:
        for k in LEAGUE_MAP:
            if re.search(k, text, re.I):
                league_raw = k
                break
    # 归一码
    if league_raw:
        league_code = LEAGUE_MAP.get(league_raw) or LEAGUE_MAP.get(
            league_raw.lower().replace(' ', '').replace('-', ''))
    # NL 优先
    if any(re.search(k, text, re.I) for k in NL_KEYS):
        league_raw, league_code = '欧国联', 'NL'
    # 开赛时间（开赛时间/比赛时间，YYYY-MM-DD HH:MM 或 YYYY/M/D）
    mt = re.search(r'(?:开赛时间|比赛时间)\s*[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]?\d{1,2}:\d{2})', text)
    if mt:
        kickoff = mt.group(1).replace('/', '-').replace('T', ' ')
    return home, away, league_raw, league_code, kickoff


def parse_ah(ah):
    """'让-0.5 主1.95/客2.0' / '让+0.00 主1.853' / '-1.50 主1.95' → (handi, home_water)。
    符号约定：主让为负、主受让为正（与 calc_all --handi 一致）。"""
    if not ah:
        return None, None
    s = str(ah)
    m = re.search(r'让\s*([+-]?\d+(?:\.\d+)?)\s*主\s*(\d+(?:\.\d+)?)', s)
    if not m:   # 无"让"前缀兜底：-1.50 主1.95/客2.0
        m = re.search(r'(?<![\d.])([+-]?\d+(?:\.\d+)?)\s*主\s*(\d+(?:\.\d+)?)', s)
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))


def parse_ou(s):
    """'O1.54/U2.35' → (大球赔率, 小球赔率)。"""
    if not s:
        return None, None
    m = re.search(r'O\s*(\d+(?:\.\d+)?)\s*/\s*U\s*(\d+(?:\.\d+)?)', str(s))
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


def find_snapshot(home, away):
    """查 data/tmp/snapshots 早盘快照；返回 (n,fml,lml,ah,o25,o35,btts,note)。"""
    empty = (None, None, None, None, None, None)  # fml,lml,ah,o25,o35,btts
    if not home or not away:
        return (None, *empty, '未给队名→跳过快照匹配（请用 --teams）')
    try:
        import snapshot_save as SS
    except Exception as e:
        return (None, *empty, 'snapshot_save 不可用(%s)·三态' % type(e).__name__)
    try:
        r = SS.find_for(home, away)
        pts = r.get('points') or []
        n = r.get('count') or 0
        if not n:
            return (0, *empty, '无本场快照(T-0 缺失)→P12 双通道/纵向三态（建议补快照）')
        def ext(i):
            return (pts[i].get('extract') or {}) if i < len(pts) else {}
        e0, e1 = ext(0), ext(-1)
        return (n, e0.get('ml'), e1.get('ml'), e1.get('ah'),
                e1.get('o25'), e1.get('o35'), e1.get('btts'),
                'span=%s→%s' % (pts[0].get('saved_at'), pts[-1].get('saved_at')))
    except Exception as e:
        return (None, *empty, '快照查询异常(%s)·三态' % type(e).__name__)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('txt', nargs='?', help='竞彩 txt（原始或 std_ 归一化均可）')
    ap.add_argument('--teams'); ap.add_argument('--league'); ap.add_argument('--event')
    ap.add_argument('--kickoff'); ap.add_argument('--eu')
    ap.add_argument('--handi'); ap.add_argument('--home_water')
    ap.add_argument('--o25'); ap.add_argument('--u25')
    ap.add_argument('--inj_h'); ap.add_argument('--inj_a'); ap.add_argument('--p12-fund', dest='p12fund')
    a = ap.parse_args()

    L = []
    def out(s=''): L.append(s)

    out('=' * 78)
    out('【执行总控 run_guard · 开场 preflight】V3.5.81（编排/防漏·不做预测判定）')
    out('=' * 78)

    if not a.txt or not os.path.exists(a.txt):
        out('❌ 未给可读的 txt 路径。用法：python data/tmp/run_guard.py <txt> [--teams ...]')
        print('\n'.join(L)); return 1
    txt = a.txt
    base = os.path.basename(txt)

    # A 归一化检测
    out('\n── A. txt 归一化（第一动作·禁手工）──')
    if not base.startswith('std_'):
        out('⚠️ 未归一化：先跑  →  python data/tmp/txt_normalize.py "%s"' % txt)
        out('   得到 data/tmp/std_<名>.txt 后用它喂 calc_all（❌缺必填节/赔率<1.01 须先修原始txt）')
    else:
        out('✅ 已是归一化文件：%s' % base)

    text = _read(txt)
    home, away, lraw, lcode, ko = parse_header(text)
    if a.teams:
        ts = [x.strip() for x in a.teams.replace('，', ',').split(',') if x.strip()]
        if len(ts) == 2: home, away = ts
    if a.league:
        lcode = LEAGUE_MAP.get(a.league.strip().lower(), a.league.strip())
        lraw = a.league.strip()
    kickoff = a.kickoff or ko

    # B 解析摘要（calc_match.parse_txt）
    out('\n── B. txt 解析摘要 ──')
    parsed = None
    try:
        import calc_match
        parsed = calc_match.parse_txt(text)
        spf = parsed.get('spf') or []
        out('队名：%s（主） vs %s（客）　联赛：%s（域码 %s）' % (home, away, lraw, lcode))
        out('开赛时间：%s%s' % (kickoff or '未识别', '' if kickoff else '（请补 --kickoff "YYYY-MM-DD HH:MM"）'))
        out('胜平负时点：%d 个　末盘：%s' % (len(spf), dict(spf[-1][1]) if spf else '无'))
        out('节齐全：让球=%s 总进球8档=%s 半全场=%s 比分=%s'
            % ('有' if parsed.get('rq') else '缺',
               '有' if parsed.get('zjq') else '缺',
               '有' if parsed.get('bqc') else '缺(三态)',
               '有' if parsed.get('bf') else '缺(三态)'))
        last_eu = spf[-1][1] if spf else None
    except Exception as e:
        last_eu = None
        out('⚠️ calc_match 解析异常：%s %s（请先归一化）' % (type(e).__name__, e))

    # 域判定 → 两套触发机制
    prof, pname = profile_of(lcode, lraw)
    out('\n── C. 赛事域 → 触发机制（两套 profile）──')
    out('识别联赛：%s（域码 %s）→ 【%s】%s' % (lraw, lcode, prof, pname))
    if prof in ('FULL-5', 'FULL-UCL'):
        out('★ PROFILE A · 全量分析（五大/欧战）：Step0-11 全量 + 专属子模型/校准表')
        if prof == 'FULL-5':
            out('  专属启用：Step4.5 SK-league-%s（R1-R15 逐条数值）+ Step4.6 HAF（λh/λa）+ C26 clubelo + C27 understat xG' % lcode)
        else:
            out('  专属启用：Step3 欧战六项核查表 + 欧战分层校准 + N24 欧冠大球校准 + N27 攻防档案(适用队)')
        out('  铁律：C13/C27 必须有脚本实跑数值，禁用 calc_v3572 查表替代；无数据三态')
    elif prof == 'NL':
        out('★ PROFILE B+ · 国家队：通用主干 + Step4.8 SK-league-nations（R1-R10）')
        out('  五大 Step6 三档/Step7 深度表/修正53 在 NL 场属「超域·仅参考」；R10 edge>0 且公平≥0.60 才进串关')
    else:
        out('☆ PROFILE B · 通用主干（其他联赛）：市场/赔率/盘口全量分析；五大&欧战专属步骤显式三态跳过')
        out('  ⤷ 跳过(须写"非五大/非欧战·不适用")：Step4.5 五大子模型、Step4.6 HAF、C27 xG、欧战六项、N24/N27')
        out('  ⤷ 保留全量：Step0 数据 / Step1 硬核12 / Step2 变动+双通道+P12 / Step3 场景45·46 / Step3.5 F1-F7 /')
        out('             Step4 推论26 / Step5 方向 / Step6+6.5 量级与五源λ / Step7 市场矩阵+零封+双锚 / Step8 / Step9 / Step10')
        out('  ⤷ 尝试·无则三态：clubelo ELO、the-odds-api 欧盘（其他联赛覆盖度可能低，取不到写原因，禁臆造）')

    # 快照 T-0
    out('\n── D. 早盘快照 T-0（P12 双通道/纵向依赖）──')
    n, fml, lml, lah, o25raw, o35raw, btts, snote = find_snapshot(home, away)
    out('快照：%s' % snote)
    if n:
        out('  count=%d　初盘ML=%s　末盘ML=%s' % (n, fml, lml))
        out('  让球AH=%s　大2.5/小2.5=%s　大3.5/小3.5=%s' % (lah, o25raw, o35raw))
        out('  双方进球BTTS=%s（Step7 R11 零封直盘直接用此·禁默认双方都进球）' % btts)
        if n == 1:
            out('  🔴 仅 1 时点：P12 必须双兜底——补 --eu（临场欧赔）+ --handi/--home_water（亚盘串），否则国米型强诱盘漏判')

    # E 命令行参数缺口
    out('\n── E. calc_all 参数缺口（必传/需补）──')
    eu = a.eu
    eu_src = '显式参数'
    if not eu and lml:
        eu = lml.replace('/', ',')
        eu_src = '快照末盘ML(真实欧盘)'
    # 🔴P13.1 修复(同源污染): 禁止用竞彩胜平负末盘填 --eu。
    #   --eu 语义=独立欧盘；若填竞彩值，P9 会把 spf 虚假标注"欧亚"、V5 同源相比分歧恒0(假一致)。
    if not eu:
        _jc = ('%.2f/%.2f/%.2f' % (last_eu.get('胜'), last_eu.get('平'), last_eu.get('负'))) if last_eu else None
        out('  🔴 无独立欧盘：--eu 留空（V5 跨市场将三态）。须补 1xbet/Pinnacle 临场欧赔(主,平,客)；')
        out('     ❌ 禁止把竞彩末盘%s当欧盘填入（同源会让 V5 分歧恒0、给假一致）' % ('（%s）' % _jc if _jc else ''))
    else:
        out('  --eu 来源：%s' % eu_src)
    handi, hw = a.handi, a.home_water
    if (not handi or not hw) and lah:
        h0, w0 = parse_ah(lah)
        handi = handi if handi else (h0 if h0 is not None else None)
        hw = hw if hw else (w0 if w0 is not None else None)
    o25, u25 = a.o25, a.u25
    _o, _u = parse_ou(o25raw)
    if not o25 and _o is not None: o25 = _o
    if not u25 and _u is not None: u25 = _u

    def mark(v, need, tip=''):
        return ('%-22s %s %s' % (need, ('✅' if v not in (None, '') else '🔴需补'), tip if v in (None, '') else ('= %s' % v)))
    out(mark(lcode, '--league'))
    out('%-22s ✅ 固定必传（否则网络源全 skipped/学习特征残缺）' % '--net')
    out(mark(kickoff, '--kickoff'))
    out(mark(('%s,%s' % (home, away)) if (home and away) else None, '--teams'))
    out(mark(a.event, '--event', '（Odds-API get_events 定位）'))
    out(mark(eu, '--eu'))
    out(mark(handi, '--handi'))
    out(mark(hw, '--home_water'))
    out(mark(o25, '--o25', '（快照2.5盘大球·已自动解析）' if o25 and not a.o25 else ''))
    out(mark(u25, '--u25', '（快照2.5盘小球·已自动解析）' if u25 and not a.u25 else ''))
    out(mark(a.inj_h, '--inj_h', '（Bing News 伤停·影响分 injury_impact）'))
    out(mark(a.inj_a, '--inj_a'))
    out('  --p12-fund：Step3 研判疲劳/战意/轮换后回填（未回传则闸门仅伤停维生效）')
    out('  --step5-dirs：Step5 定稿后回填；强诱盘/矛盾/弱共识必须 ≥2 个方向')

    # F 标准命令
    std_txt = txt if base.startswith('std_') else 'data/tmp/std_<归一化文件名>.txt'
    lc = lcode or '<联赛>'
    parts = ['python data/tmp/calc_all.py "%s" %s --net' % (std_txt, lc),
             ('--kickoff "%s"' % kickoff) if kickoff else '--kickoff <"YYYY-MM-DD HH:MM">',
             ('--teams "%s,%s"' % (home, away)) if (home and away) else '--teams "<主,客>"',
             '--event %s' % (a.event or '<eventId>'),
             ('--eu "%s"' % eu) if eu else '--eu "<真实欧盘主,平,客·禁填竞彩>"',
             '--handi %s' % (handi if handi is not None else '<让球·主让为负>'),
             '--home_water %s' % (hw if hw is not None else '<主水>'),
             '--o25 %s' % (o25 if o25 is not None else '<大2.5赔率>'),
             '--u25 %s' % (u25 if u25 is not None else '<小2.5赔率>'),
             '--inj_h %s' % (a.inj_h or '<主队伤停分>'),
             '--inj_a %s' % (a.inj_a or '<客队伤停分>'),
             '--snapshot --league %s' % lc]
    out('\n── F. 可直接复制的 calc_all 命令（Step5 后再补 --step5-dirs/--p12-fund 重跑）──')
    out('  ' + ' \\\n    '.join(parts))

    # G 本场必核门禁（按 profile 裁剪：两套触发机制）
    out('\n── G. 本场放行门禁（按 profile 裁剪·逐项过·三态标注·禁跳步）──')
    gates = ['Step0 数据源健康 X/6 + txt 归一化(第一动作)',
             'Step1 硬核12项逐项数值(skew/凯利禁手算)+概率校准',
             'Step2 V2诱阻四步 + 双通道四象限(N21b) + P12机构意图(gate/fav·取fav禁max(shift))']
    if prof == 'FULL-5':
        gates.append('Step4.5 SK-league-%s R1-R15 七维校正 + Step4.6 HAF λh/λa（脚本实跑数值）' % lcode)
        gates.append('Step3 场景44/45/46 + C26 clubelo + C27 understat xG（无则三态）')
    elif prof == 'FULL-UCL':
        gates.append('Step3 场景44【欧战六项核查表逐项】+ 45/46 + 欧战分层 + N24/N27(适用队)')
        gates.append('Step4.5 欧战分层（非五大俱乐部不得套用五大表）')
    elif prof == 'NL':
        gates.append('Step4.8 SK-league-nations R1-R10（替代4.5）；五大专属表标「超域·仅参考」')
        gates.append('Step3 场景45/46（44 欧战＝非欧战·不触发）')
    else:
        gates.append('Step3 场景45/46（44 欧战＝非欧战·显式写"不触发"）')
        gates.append('【CORE跳过确认】Step4.5 五大子模型/Step4.6 HAF/C27 xG/欧战六项/N24/N27 逐项写"非五大/非欧战·不适用"')
    gates += ['Step3 伤停/疲劳/战意/轮换警报（抓到必须在 Step5 消费·存在≠活跃）',
              'Step3.5 情境 F1-F7 + Step4 推论26项逐项三态（未列出=未执行）',
              'Step5 D1-D4+修正53 + 置信度(单押 skew≥200%且最低赔<1.30) + 并列进 step5-dirs≥2',
              'Step6.5 五源λ(唯一期望口径) + 极端大球(O2.5<1.4)给1-6球宽区间',
              'Step7 P10市场矩阵E0主排序(泊松仅0.05-0.15回填) + R11零封(禁默认双方进球) + R10主锚/R12次锚',
              'Step7 锚-市场三对齐(方向∈Step5/净胜∈让球档/总进球∈量级) + 极端场保留低分谱系',
              'Step8 总进球交叉验证(矛盾必须回查)',
              'Step9 自检22项逐项附数值(N21/N21b/N21c/N23)',
              'Step10 case_write + check_luopan 校验通过']
    for i, g in enumerate(gates, 1):
        out('  □ %d. %s' % (i, g))

    out('\n── H. 执行顺序（红线）──')
    out('  1) 先跑 A 的归一化（若非 std_）；2) 补全 E 中 🔴 参数，跑 F 的 calc_all；')
    out('  3) 🔴 --step5-dirs **首次 calc_all 就要给**（首选方向·pipeline stage3 自动推导）；--p12-fund 可缺（三态·**不必为它重跑**）；🔴 禁「先跑一次看输出再补参数重跑」（重跑=最大耗时且覆盖锚）')
    out('  4) 按 G 门禁串行 Step0→11，上一步不合格不进下一步；')
    out('  5) 交付前过 output_checker（N21/N21b/N21c/N23）+ check_luopan；任一不过补齐再交。')
    out('=' * 78)
    print('\n'.join(L))
    return 0


if __name__ == '__main__':
    sys.exit(main())
