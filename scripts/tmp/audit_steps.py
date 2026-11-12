# -*- coding: utf-8 -*-
"""全模型步骤审计器 audit_steps.py（2026-10-30 用户最后通牒后建立）

🔴 设计原则（治「遗漏」）：
   每一大步必须给出**三态之一**，且「三态」必须**附执行证据**：
     ✅ PASS     — 拿到非空正确数值
     ⚪ TRISTATE — 已尝试执行且失败（**必须给出尝试记录**：命令/调用+返回）
     ❌ MISSING  — 没有数值也没有证据 = **遗漏**（硬失败·禁止交付）

用法:
   python data/tmp/audit_steps.py --case 298                       # 审 raw
   python data/tmp/audit_steps.py --case 298 --calc data/tmp/_pipe_calc_298.txt   # 同时审 calc 输出
   python data/tmp/audit_steps.py --case 298 --strict              # MISSING 即非零退出
"""
import argparse
import io
import os
import re
import sys

os.chdir(r'<HOME>\AppData\Roaming\reasonix\global-workspace')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# (步骤ID, 名称, raw 里的数值判据, 三态证据关键词, 影响等级)
STEPS = [
    # 🔴2026-11-01 S00 时间上下文（time_guard）—— 所有完整分析的第一步，缺失=无法判时效
    # 🔴2026-11-01 新增：队名为空 = 连锁打掉 P10/P8/N21/R11/P1 五项（case308/309 实证）
    #   根因当时是 txt_teams 正则排除空格 → 英文队名恒失配 → 下游全三态
    # 🔴 正向 = calc 里出现「主=<真队名>」（如 `主=Machida Zelvia→None`）；
    #   🔴 三态**留空**：队名为空是**硬缺陷**（正则/编码问题），不是「源不可用」→
    #      必须判 MISSING 逼修，禁止给三态出口（case308/309 实证）
    # 🔴2026-11-02 端到端审计实抓：原判据 `主=[^\s→\n]{2,}` 与 calc 实际输出不符
    #   （calc 输出「🔎 队名解析: Liverpool→Liverpool ｜ Arsenal→Arsenal」·无「主=」字样）
    #   → 恒判 MISSING（假遗漏）。改匹配真实格式 + 兼容「主=」写法
    # 🔴2026-11-02 P42 修：原 `\S+` 不支持**含空格的英文队名**
    #   （「队名解析: Ath Bilbao→Ath Bilbao」恒失配 → case315 假报 MISSING；
    #     case316「Liverpool→Liverpool」单字能过 → 正是判据过窄的证据）→ 改 [^→\n]{1,40}?
    ('S00b', '队名提取(txt_teams)', r'(队名解析[:：]\s*\S[^→\n]{0,39}→|主=[^\s→\n]{2,})',
     r'(?!x)x', 'H'),
    ('S00', '时间上下文(time_guard)', r'(时间上下文|当前时间.{0,30}UTC)',
     r'(time_guard 时间上下文不可用)', 'H'),
    ('S01', 'txt 归一化', r'(std_|归一化|标准模板)', r'(已是标准模板|归一化)', 'H'),
    # 🔴2026-11-07 新增 S01b：竞彩胜平负时点数（case335 实证·**审计盲区**）
    #   事故：335 的 4 张图里没有「胜平负固定奖金」表 → 胜平负 **0 时点**
    #   → V1 双源变动 / D1 背离 / 竞彩逐T形态学 / 低赔大幅变动重排 **四层全部失效**
    #   而 S01「txt 归一化」只看格式（文件是标准模板就 PASS）→ **静默放行**
    #   用户问「有步骤遗漏吗」时才被发现 → 审计器必须自己拦。
    #   判据：① raw/calc 出现「胜平负 **N**」（N≥1）→ PASS
    #        ② 「胜平负 0 时点 / 缺失 / 未截 / 截图未含」→ TRISTATE（有实证）
    #        ③ 两者都无 → MISSING（连写都没写）
    #   🔴 负向断言 (?<!让球)(?<!全场) 排除「让球胜平负」「半全场胜平负」（否则恒匹配让球/半全场段）
    # 🔴2026-11-11 P-TOOL-2 加宽（case344 实证·判据写窄 → 假报 MISSING）：
    #   原判据要求「胜平负」紧跟数字；而合规写法「竞彩 2 时点（1.79/3.6/3.3…）」/
    #   「胜平负时点 2 个」/「胜平负：2 时点」全部失配 → 判 MISSING（而数据其实在）
    #   → PASS 接住：冒号变体 + 「胜平负时点 N」前置变体
    #   → TRISTATE 接住：0 时点 / 缺失 / 未截 / 截图未含 / 时点不足 / <3 时点 / 「胜平负时点 0」
    ('S01b', '竞彩胜平负时点数',
     r'(?<!让球)(?<!全场)胜平负\s*[:：]?\s*\*{0,2}[1-9]\d*'
     r'|(?<!让球)(?<!全场)胜平负时点[^\n]{0,10}[1-9]\d*',
     r'(?<!让球)(?<!全场)胜平负\s*[:：]?\s*\*{0,2}0\*{0,2}'
     r'|胜平负[^\n]{0,14}(0 ?时点|缺失|未截|截图未含|时点不足|时点数不足|<3 ?时点)'
     r'|(?<!让球)(?<!全场)胜平负时点[^\n]{0,8}0', 'H'),
    # 🔴2026-11-01 升级：原判据三态含 `bzzoiro_fetch` → 而 calc 输出里**总有**
    #   「可用 bzzoiro_fetch.py」这句提示 → **恒判三态**（假通过）
    #   实证：307/308/309 三场 calc 都是「🔴伤停影响分(缺失)」但 audit 判 TRI
    #   新判据：① 必须出现**具体分值**「主队 X.X 分 →」 ② 或明确「源不覆盖」
    #   （合规三态：Bzzoiro 50 个联赛**无任何亚洲联赛** → 日职/韩职等确实无从查）；
    #   三态留空 → 无分值即 MISSING
    # 🔴2026-11-04 修（case323 实证）: V3.5.91 起三态文案是「**索引**不覆盖」（不是「源不覆盖」）
    #   原白名单只认「源不覆盖」→ 判据退化成「靠模型在 raw 手写该四字才过」= 假通过
    #   实证: case321/322 恰好写了「全部为「源不覆盖/…」」→ PASS；case323 没写 → MISSING（证据完全一样）
    #   → 加「索引不覆盖 / 不覆盖（含限定词）/ 未定位到任何队」三种真实输出变体
    ('S02', '伤停(Bzzoiro·源B8)',
     r'(主队\s*[\d.]+\s*分\s*→|源不覆盖|索引不覆盖|不在 v1 events 索引'
     r'|未定位到任何队|未定位到队名)',
     r'(?!x)x', 'H'),
    # 🔴2026-11-01 升级（case308/309 实证）：原判据只要「E[T 后面有数字」就算 PASS，
    #   但三源不齐时 N26/其它块也可能出现 E[T 字样 → **假通过**。
    #   实测 308/309：P10「三源不齐」却判 PASS 16/遗漏 0 → 队名 bug 无人发现。
    #   新判据：必须 `市场矩阵(P10·E0): health=ok`（真跑起来）或明确的 `矩阵E[T]=数字`。
    # 🔴2026-11-02 P42 修：原只认新格式「health=ok ⋯ 矩阵E[T]=x.xx」
    #   而 315/316 为旧格式「市场矩阵(P10)：CS覆盖22档/OU 8半档/AH 15档 ⋯ (期望2.99)」→ 假报 MISSING
    #   （矩阵真跑了：决策门 CS≥15/AH≥4/OU≥3 全满足）→ 加旧格式兼容，仍要求**实质证据**
    #   （CS 档数 + 总进球期望值），不是"出现关键词就算过"
    ('S03', '市场三源(P10)', r'(health=ok[^\n]{0,30}矩阵E\[T\]=[\d.]+|矩阵E\[T\]=[\d.]+[^\n]{0,20}health=ok'
                              r'|市场矩阵\(P10\)[：:]CS覆盖\d+档[^\n]{0,100}\(期望[\d.]+\)'
                              r'|CS覆盖\d+档[^\n]{0,40}AH \d+档[^\n]{0,120}\(期望[\d.]+\))',
     r'(三源不齐[^\n]{0,80}(按队名定位|定位失败|未定位|1xbet 未开盘|滚球|overs?eason|源不可用'
     r'|已尝试)|市场矩阵未启用[^\n]{0,80}已尝试)', 'H'),
    ('S04', '跨机构共识(the-odds-api)', r'(家机构|平均抽水)',
     r'(未取|三态.{0,40}家|未找到|自动刷新|免费档未覆盖|不含本场|场次错配|no_books|未提供逐家)',
     'H'),
    ('S05', 'ELO(clubelo·源B6)', r'(ELO\s*差[^\n]{0,20}[\d+\-]|ELO\s*\d{3,4})',
     r'(clubelo|403|无 ELO|ELO 三态)', 'M'),
    ('S06', 'H2H 双源', r'(Matches\.csv|H2H)', r'(无芬超|无亚冠|无数据)', 'H'),
    ('S07', '赔率档查表(odds_table)', r'(档\s*[\d.\-]+|实际H/D/A|主胜赔率档)', r'(非五大|超域|不查表)', 'M'),
    ('S08', 'goal_bins 总进球档', r'(4\+球|4\+:\s*[\d.]+%)', r'(三态)', 'H'),
    ('S09', 'R20 平局温度', r'(S9|S10|S11|S12)[^\n]{0,30}([\d.]+%)', r'(缺输入|未匹配)', 'M'),
    ('S10', 'V6 四象限', r'V6四象限[^\n]{0,60}[\d.]+%', r'(三态)', 'M'),
    ('S11', '让球水位 P1', r'上盘覆盖\s*[\d.]+%', r'(无均衡档|P1 不采用|均衡线缺失)', 'H'),
    ('S12', 'N26 进球数细分', r'(进球数细分|N26)[^\n]{0,80}[\d.]+%', r'(三态)', 'M'),
    ('S13', 'R-POOL-BIG 宽池分级', r'(R-POOL-BIG|宽池必含|L[123]\s*(极强|大球))', r'(无 --o25|无分布)', 'H'),
    ('S14', 'R-ANCHOR-BIG 次锚上探', r'(R-ANCHOR-BIG|次锚须\s*≥\s*\d+\s*球)', r'(次锚不受限|非大球)', 'H'),
    # 🔴2026-11-02 P42-c 修：原只认 `硬1…数字`（旧格式）
    #   实际输出为「硬: 主锚≤1.0=False」/「【锚-市场期望匹配】… 偏离期望 +0.18」→ 五场全假三态
    ('S15', '锚-期望硬/软校验',
     r'(硬[1:：][^\n]{0,60}[\d.]+|锚-市场期望匹配[^\n]{0,80}[\d.]+'
     r'|偏离期望\s*[+\-−]?[\d.]+|【锚-市场期望匹配】)', r'(三态)', 'H'),
    ('S16', '锚-量级一致性', r'(锚-量级|量级一致)', r'(三态)', 'H'),
    # 🔴2026-11-02 P42-c 修：原只认「覆盖率X%」→ 实际输出「双锚联合覆盖 13.6%」→ 假三态
    ('S17', '双锚覆盖率披露',
     r'(覆盖率[^\n]{0,20}[\d.]+%|双锚联合覆盖[^\n]{0,30}[\d.]+%|联合覆盖\s*[:：]?\s*\**\s*[\d.]+%)',
     r'(不适用)', 'M'),
    ('S18', 'P30 信号落地', r'(信号落地核查|本场处置)', r'(不触发)', 'H'),
    ('S19', '修正53 平局序列', r'(修正53|S1✓|S1✗|分组分)', r'(不计)', 'M'),
    ('S20', 'NL 子模型三态', r'(欧国联|Nations League|非欧国联)', r'(不触发)', 'M'),
]


def read(p):
    try:
        return io.open(p, encoding='utf-8', errors='replace').read()
    except Exception:
        return ''


def audit(case, calc_path=None, strict=False):
    raws = [f for f in os.listdir('data/case-library/raw')
            if f.startswith('case%s' % case)]
    if not raws:
        print('❌ 未找到 case%s 的 raw' % case)
        return 2
    raw = read(os.path.join('data/case-library/raw', raws[0]))
    calc = read(calc_path) if calc_path and os.path.exists(calc_path) else ''
    text = raw + '\n' + calc

    print('=' * 100)
    print('步骤审计 case%s ｜ raw %d 字 ｜ calc %d 字' % (case, len(raw), len(calc)))
    print('=' * 100)
    print('%-5s %-24s %-6s %s' % ('ID', '步骤', '等级', '状态'))
    miss, tri, ok = [], [], []
    for sid, name, pat_ok, pat_tri, lv in STEPS:
        has_ok = bool(re.search(pat_ok, text))
        has_tri = bool(re.search(pat_tri, text))
        if has_ok:
            st = '✅ PASS'
            ok.append(sid)
        elif has_tri:
            st = '⚪ TRISTATE（有证据）'
            tri.append(sid)
        else:
            st = '❌ **MISSING（无数值无证据=遗漏）**'
            miss.append((sid, name, lv))
        print('%-5s %-24s %-6s %s' % (sid, name, lv, st))

    print('-' * 100)
    print('✅ PASS %d ｜ ⚪ TRISTATE %d ｜ ❌ MISSING %d' % (len(ok), len(tri), len(miss)))
    if miss:
        print('\n🔴 遗漏项（必须补或以实证标三态）：')
        for sid, name, lv in miss:
            print('   [%s] %-24s 影响=%s' % (sid, name, lv))
        hm = [m for m in miss if m[2] == 'H']
        if hm:
            print('\n🔴🔴 高影响遗漏 %d 项：%s' % (len(hm), ' / '.join(m[1] for m in hm)))
    else:
        print('\n✅ 无遗漏（每步均有数值或实证三态）')
    if strict and miss:
        return 1
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--case', required=True)
    ap.add_argument('--calc', default=None)
    ap.add_argument('--strict', action='store_true')
    a = ap.parse_args()
    sys.exit(audit(a.case, a.calc, a.strict))
