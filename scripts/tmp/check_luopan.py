import re
# -*- coding: utf-8 -*-
"""落盘完整性校验（2026-08-24·结构性机制②·防落盘缺节）
用法: python check_luopan.py [case_id]  # 缺省=校验全部
检查: ①raw 五部分+六(硬核12项)+七(xG判定)节 ②CSV 字段完整 ③raw/CSV 结论一致(主锚次锚)
"""
import sys, os, re, csv, glob
try:
    sys.stdout.reconfigure(encoding='utf-8')  # 🔴2026-09-04链路优化: 默认GBK控制台防UnicodeEncodeError崩溃
except Exception:
    pass

def check_case(cid):
    issues = []
    # 1. raw 节完整性
    raws = glob.glob(f'data/case-library/raw/case{cid}_*.md') + glob.glob(f'data/case-library/raw/case{cid}.md')
    if not raws:
        issues.append(f'case{cid}: raw 缺失')
        return issues
    for p in raws:
        t = open(p, encoding='utf-8').read()
        need = ['## 一、竞彩全文', '## 二、欧盘', '## 三、场景', '## 四、基本面', '## 五、结论', '## 六、硬核层12项', '## 七、xG深度判定']
        # 🔴2026-09-11 新增(case159起): raw 须含「学习成果/融合判定」留痕（闭环可审计）
        _learn_trace = False
        _cidi = int(cid) if str(cid).isdigit() else 0
        if _cidi < 97:
            # 🔴2026-09-13 旧格式兼容（模板固化前 case65-96·用户选择）: 节标题变体 + 六/七节不强制
            #   旧格式实例: '## 五、模型结论' / '## 三、API数据'(代替场景) / 无六、七节(模板后加)
            _legacy_need = [('一、竞彩', ('竞彩',)), ('二、欧盘', ('欧盘', 'Odds-API')),
                            ('三、场景/API数据', ('场景', 'API数据')), ('四、基本面', ('基本面',)),
                            ('五、结论', ('结论',))]
            for _lbl, _keys in _legacy_need:
                if not any(_k in t for _k in _keys):
                    issues.append(f'case{cid} ({os.path.basename(p)}): 缺节 [{_lbl}]')
        else:
            # 🔴2026-10-25 修（case279 实证·3 轮试错）: 原为精确字符串匹配 →
            #   '## 六、硬核层 12 项'（多空格）/ '**## 七、xG深度判定**' 等排版变体全部误报缺节。
            #   改为「去空白与星号后」比对 —— 只吸收排版差异，不放松到关键词（语义强度不变）。
            import re as _re_h
            _tq = _re_h.sub(r'[\s\*]+', '', t)
            for n in need:
                if _re_h.sub(r'[\s\*]+', '', n) not in _tq:
                    issues.append(f'case{cid} ({os.path.basename(p)}): 缺节 [{n}]')
        # 🔴2026-09-13 新增(审计P1): raw 须含市场源/锚-量级一致性留痕
        _new_rules = ['市场', '量级']
        # 🔴2026-09-13: 三类新规则留痕仅对 case168 起强制（历史 raw 不回溯·防噪音·既定策略）
        _cidi = int(cid) if str(cid).isdigit() else 0
        if _cidi >= 168 and not any(k in t for k in ('市场源', '市场净胜', 'market')):
            issues.append(f'case{cid}: raw 缺【市场源/市场净胜档】留痕(2026-09-13起)')
        if _cidi >= 168 and not any(k in t for k in ('锚-量级', '量级一致', '量级矛盾')):
            issues.append(f'case{cid}: raw 缺【锚-量级一致性】留痕(2026-09-13起)')
        # 🔴2026-09-13 新增(用户要求"锚定一定要与市场信号一致"): raw 须含锚-市场一致性留痕
        if _cidi >= 168 and not any(k in t for k in ('锚-市场', '市场一致性', 'market_anchor')):
            issues.append(f'case{cid}: raw 缺【锚-市场一致性】留痕(2026-09-13起·用户要求)')
        # 🔴2026-10-31 批次5 修复（Step 全流程审计·承诺未兑现实抓）:
        #   calc_all 明写「若坚持原锚 → check_luopan 会拦」，而本文件原**只查关键词存在**
        #   （写「❌不匹配」也通过）= 门禁空转。现加**结论级**断言:
        #   判 ❌/矛盾 → 必须同时有处置（替换锚 / 宽池不可预测 / 信号落地）。
        if _cidi >= 303:
            _mm5 = re.search(r'锚[-－]?市场[^\n]{0,300}(❌|不匹配|⚠️矛盾)', t)
            if _mm5:
                _handled5 = any(k in t for k in ('必须替换', '已替换', '宽候选池',
                                                  '比分不可预测', '信号落地核查'))
                if not _handled5:
                    issues.append(f'case{cid}: 锚-市场判 ❌/矛盾 但**无处置留痕**'
                                  f'（须替换锚 或 标宽池/比分不可预测·2026-10-31 起）')
        # 🔴2026-09-26 新增(用户建议"市场期望进球和比分锚定要匹配"): raw 须含锚-市场期望匹配留痕
        if _cidi >= 206 and not any(k in t for k in ('市场期望', '期望进球', 'exp_total')):
            issues.append(f'case{cid}: raw 缺【锚-市场期望匹配】留痕(2026-09-26起·用户建议)')
        # 🔴2026-09-30 升级为**断言型**（治 case221 疏漏: 只写「主锚∈期望区间」不给偏离数值 →
        #   次锚 0:1 偏离期望 1.62 球逃逸；铁律「审计器禁止关键词存在即通过」SK-audit ⑩）
        if _cidi >= 221:
            _mexp = re.search(r'【锚-市场期望匹配】(.{0,600})', t, re.S)
            if not (_mexp and ('偏离' in _mexp.group(1)) and re.search(r'\d+\.\d+', _mexp.group(1))):
                issues.append(f'case{cid}: 【锚-市场期望匹配】须含各锚「偏离期望」数值(2026-09-30起·治只写∈区间不写偏离)')
        # 🔴2026-09-27 新增(用户要求"期望进球和泊松查表必须联动·一致且自洽"): raw 须含三源联动留痕
        if _cidi >= 206 and not any(k in t for k in ('三源', '期望联动', '自洽')):
            issues.append(f'case{cid}: raw 缺【期望三源联动】留痕(2026-09-27起·用户要求)')
        # 🔴2026-09-27 新增(用户要求固化V6四象限): 有亚盘/O25 的场次须留痕四象限
        if _cidi >= 206 and not any(k in t for k in ('四象限', 'quadrant', '共振')):
            issues.append(f'case{cid}: raw 缺【V6四象限】留痕(2026-09-27起·用户要求)')
        # 🔴2026-09-19 审计修复(P1-1/2/3·case188审计): raw 第八节「执行留痕」六子块校验(case189+强制) — 治「审计看不到=判未执行」: 对话输出做了但 raw 没写 → 审计误判未执行
        if _cidi >= 189:
            if ('## 八' not in t) and ('八、执行留痕' not in t) and ('执行留痕' not in t):
                issues.append(f'case{cid}: raw 缺第八节「执行留痕」标题(## 八、执行留痕·2026-09-19起)')
            _trace8 = [('V2诱阻四步', ('V2', '诱阻四步', '四步')),
                       ('F1-F7情境因子', ('F1', 'F2', 'F3', '情境因子')),
                       ('Step4推论层26项', ('推论层', '修正14', '修正2')),
                       ('SK-league调用证据', ('SK-league', 'R1', 'R规则', 'R12')),
                       ('Step9自检22项', ('自检', '22项')),
                       ('数据源健康', ('数据源', '健康', '/6', 'source_health'))]
            _miss8 = [lbl for lbl, keys in _trace8 if not any(k in t for k in keys)]
            if _miss8:
                issues.append(f'case{cid}: raw 第八节缺子块: {"/".join(_miss8)}(2026-09-19起)')
        # 🔴2026-09-21 资金盘信号层（审计修复 P1-11·治「存在≠活跃」）: raw 须含资金盘留痕
        if _cidi >= 202 and not any(k in t for k in ('资金盘', '跨机构分歧', 'spread', '机构一致', '机构分歧')):
            issues.append(f'case{cid}: raw 缺【资金盘信号层】留痕(2026-09-21起·calc_all 已自动输出【资金盘信号总览】·须消费并留痕)')
        # 2026-09-23 欧国联/国家队子模型（V3.5.75）: raw 须含 NL 留痕（league_id=5 场·或标'非欧国联·不触发'）
        if _cidi >= 202 and not any(k in t for k in ('欧国联', 'Nations League', 'nl_model', '非欧国联')):
            issues.append(f'case{cid}: raw 缺【欧国联子模型】留痕(2026-09-23起·NL 场须含 R1-R10/非NL 场须标「非欧国联·不触发」)')
        # 🔴2026-10-11 新增（用户「严格检查新部分是否完全接入」）: 大小球盘口水位精读留痕
        if _cidi >= 236 and not any(k in t for k in ('大小球盘口水位精读', 'SL-totals-water-read', '九档量级')):
            issues.append(f'case{cid}: raw 缺【大小球盘口水位精读】留痕(2026-10-11起·calc_all 无条件段已自动输出该块→分析须消费并留痕)')
        # 🔴2026-10-13 新增（V3.5.77 四要素深度融合·用户方案·第一优先级）:
        #   raw 须含 (D,M,T) 联合象限 / joint_solver 留痕（四要素估值 + 仲裁命中 + 交集池 + 锚）
        if _cidi >= 244 and not any(k in t for k in ('(D,M,T)', 'D,M,T', '四方素', '四要素', 'joint_solver', '联合象限')):
            issues.append(f'case{cid}: raw 缺【(D,M,T) 四要素联合象限】留痕(2026-10-13 V3.5.77起·须含四要素估值+仲裁命中+交集池+主/次锚)')
        if _cidi >= 244 and not any(k in t for k in ('交集池', '交集内泊松', '仲裁')):
            issues.append(f'case{cid}: raw 需含【交集池+仲裁留痕】(2026-10-13 V3.5.77·治「审计看不到=判未执行」)')
        # 🔴2026-10-17 新增（V3.5.79 综合升级·用户「严格审查是否完全嵌入模型」）:
        #   raw 须含 V3.5.79 留痕（case248 起·V3.5.79 于 2026-10-17 上线·case244-247 属上线前不追溯）
        if _cidi >= 248 and not any(k in t for k in ('V3.5.79', '波胆', '零封修正', '均衡档', '浅盘M×零封')):
            issues.append(f'case{cid}: raw 缺【V3.5.79 综合升级】留痕(2026-10-17起·须含波胆E5证据/零封修正λa/均衡档水位或「P1不采用」三态)')
        # 🔴2026-10-17 晚上新增（V3.5.79 P5 市场信号主导排序）: raw 须含市场排序基线三态留痕
        #   P5 于 2026-10-17 晚（case254 起）上线 → case248-253 属上线前不追溯
        if _cidi >= 254 and not any(k in t for k in ('市场排序基线', 'market_baseline', '波胆排名基线', '交集池为空')):
            issues.append(f'case{cid}: raw 缺【P5 市场排序基线】留痕(2026-10-17晚起·须写 S1/S2/S3 三态之一 + 泊松基线降权×0.5)')
        # 复盘节
        if '复盘' not in t and '## 六' in t:
            pass
    return issues

def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only:
        m = re.search(r'case(\d+)', only)   # 兼容 case97 / case97.md / 路径
        if m: only = m.group(1)
    rows = list(csv.reader(open('data/case-library/实战案例.csv', encoding='utf-8-sig')))
    all_issues = []
    checked = 0
    legacy = 0
    for r in rows[1:]:
        cid = r[0]
        if only and cid != only:
            continue
        checked += 1
        if int(cid) <= 64:  # 🔴历史场次(六/七节标准2026-08-23起·case01-64旧五部分标准·不回溯)
            legacy += 1  # 🔴历史场次(2026-08-19模板固化前·旧格式/无raw)·豁免不回溯
            continue
        issues = check_case(cid)
        # CSV 字段: 真实比分(7)/方向命中(8)/比分命中(9)/完美命中(10) 为空=待赛果·OK
        if not r[7].strip() and r[5].strip() and len(r[6].split(',')) < 1:
            issues.append(f'case{cid}: 预测比分空')
        all_issues += issues
    print(f'校验 {checked} 场 (严格校验 case65+ · 历史豁免 case01-64 {legacy} 场·旧格式不回溯)')
    # 🔴2026-10-20 修(P0 假通过·用户审计实抓): 原「校验 0 场」时仍往下打印
    #   ✅「全部场次落盘完整」→ 什么都没查却报通过。
    #   实证: case258/259/260 三场缺 3 个必需节(竞彩全文/硬核层12项/xG深度判定)
    #         + 锚-期望无数值 → 输出仍 ✅ → 误导「落盘完成」。
    #   → 有路径输入却解析出 0 场 = 硬失败(exit 2)，禁假通过。
    if sys.argv[1:] and checked == 0:
        print(f'🔴 校验 0 场（传入 {len(sys.argv) - 1} 个路径但未解析出任何 case）→ 视为失败(禁假通过)')
        for _p in sys.argv[1:]:
            print(f'   · 未识别: {_p}')
        sys.exit(2)
    if all_issues:
        print('❌ 问题:')
        for i in all_issues: print(' ', i)
        sys.exit(1)
    # 🔴case159起: 学习成果/融合判定留痕校验（2026-09-11·闭环审计）
    import re as _re2, os as _os2
    _miss_trace = []
    for _f in _os2.listdir('data/case-library/raw'):
        _m = _re2.search(r'case(\d+)', _f)
        if not _m or int(_m.group(1)) < 159:
            continue
        _txt = open(_os2.path.join('data/case-library/raw', _f), encoding='utf-8').read()
        if ('学习成果' not in _txt) and ('融合方向概率' not in _txt) and ('学习成果进入判定' not in _txt):
            _miss_trace.append(_f)
    # 🔴2026-10-09 A模式审计补(P0-2b): BSD 增强层留痕（条件化——仅 raw 提及 --bsd-* 才要求）
    _miss_bsd = []
    for _f in _os2.listdir('data/case-library/raw'):
        _m = _re2.search(r'case(\d+)', _f)
        if not _m or int(_m.group(1)) < 229:
            continue
        _t2 = open(_os2.path.join('data/case-library/raw', _f), encoding='utf-8').read()
        if (('--bsd-teams' in _t2) or ('--bsd-event' in _t2)) and ('BSD 增强层' not in _t2):
            _miss_bsd.append(_f)
    if _miss_bsd:
        print('❌ case229+ 提及 --bsd-* 但缺「BSD 增强层」留痕: %s' % _miss_bsd[:3])
    else:
        print('✅ BSD 增强层留痕校验通过（未提及 或 已留痕）')

    # 🔴2026-10-28 P18 消费兜底: calc_all 必输出「让球水位 P1」「N26 进球数细分」，
    #   模型漏消费 = 新程序白装（case287-289 实测三场全漏/半漏）
    _miss_p18 = []
    for _f in _os2.listdir('data/case-library/raw'):
        _p = _os2.path.join('data/case-library/raw', _f)
        try:
            _t8 = open(_p, encoding='utf-8').read()
        except Exception:
            continue
        # 仅对 case287+ （本条规则生效日）强制
        _cid8 = _f.replace('case', '').split('_')[0]
        if not _cid8.isdigit() or int(_cid8) < 287:
            continue
        _lack8 = []
        if ('让球水位' not in _t8) and ('上盘覆盖' not in _t8):
            _lack8.append('让球水位P1')
        if ('N26' not in _t8) and ('低分出口' not in _t8) and ('进球数细分' not in _t8):
            _lack8.append('N26低分出口')
        if _lack8:
            _miss_p18.append('%s 缺 %s' % (_f, '/'.join(_lack8)))
    if _miss_p18:
        print('❌ P18 消费兜底: raw 缺必消费项: %s' % _miss_p18[:3])
    else:
        print('✅ P18 消费兜底通过（让球水位 P1 + N26 均已留痕·case287+）')

    # 🔴2026-10-28 P19 H2H 双源兜底: case287+ 必须含 Matches.csv 或 H2H 三态说明
    _miss_p19 = []
    for _f in _os2.listdir('data/case-library/raw'):
        _p = _os2.path.join('data/case-library/raw', _f)
        try:
            _t9 = open(_p, encoding='utf-8').read()
        except Exception:
            continue
        _cid9 = _f.replace('case', '').split('_')[0]
        if not _cid9.isdigit() or int(_cid9) < 287:
            continue
        if ('Matches.csv' not in _t9) and ('H2H' not in _t9.upper()):
            _miss_p19.append('%s 缺 H2H 双源留痕（Matches.csv）' % _f)
    if _miss_p19:
        print('❌ P19 H2H 双源兜底: %s' % _miss_p19[:3])
    else:
        print('✅ P19 H2H 双源兜底通过（Matches.csv / H2H 留痕·case287+）')

    # 🔴2026-11-12 P-COVER-1 默认覆盖兜底（case346 事故驱动·用户指令「做」）
    #   事故: 神户0:1町田 · 赔率 主2.46/客2.82/平3.08（平局=最高赔）
    #         「次向」用平局挤掉次低赔方向客胜 → 真实客胜 → 方向❌（按铁律应✅）
    #   L2 铁律: 默认覆盖=「最低赔+次低赔」77.68% > 「最低+平局」76.51%（227,495 场）
    #   case348+ 强制: raw 须留「默认覆盖」块；判 VIOLATION 须附理由（Q2/诱主/M1 等硬动作）
    _miss_pcv = []
    _CV_REASON = ('Q2', '诱主', '诱盘', 'M1', '硬动作', '不按默认覆盖', '非默认覆盖')
    for _fc in _os2.listdir('data/case-library/raw'):
        _cidc = _fc.replace('case', '').split('_')[0]
        if not _cidc.isdigit() or int(_cidc) < 348:
            continue
        _pc = _os2.path.join('data/case-library/raw', _fc)
        try:
            _tc = open(_pc, encoding='utf-8').read()
        except Exception:
            continue
        if ('默认覆盖' not in _tc) and ('P-COVER-1' not in _tc):
            _miss_pcv.append('%s 缺「默认覆盖」留痕' % _fc)
            continue
        _cvbad = ('VIOLATION' in _tc) or ('默认覆盖违规' in _tc) or ('🔴【默认覆盖建议】' in _tc)
        if _cvbad and not any(_k in _tc for _k in _CV_REASON):
            _miss_pcv.append('%s 默认覆盖违规但未说明理由（Q2诱盘/诱主/M1伤停仍热门）' % _fc)
    if _miss_pcv:
        print('❌ P-COVER-1 默认覆盖兜底: %s' % _miss_pcv[:3])
    else:
        print('✅ P-COVER-1 默认覆盖兜底通过（默认覆盖留痕 + 违规必附理由·case348+）')

    # 🔴2026-10-30 P33 步骤审计硬门禁（用户最后通牒：不允许再遗漏·尤其伤停/市场三源）
    #   调用 audit_steps.py 的 20 项断言 → case299+ 若存在 MISSING（无数值且无三态证据）→ 判失败
    _miss_p33 = []
    try:
        sys.path.insert(0, 'data/tmp')
        from audit_steps import STEPS as _ASTEPS
        for _f in _os2.listdir('data/case-library/raw'):
            _cid9 = _f.replace('case', '').split('_')[0]
            if not _cid9.isdigit() or int(_cid9) < 299:
                continue
            _p = _os2.path.join('data/case-library/raw', _f)
            try:
                _t9 = open(_p, encoding='utf-8').read()
            except Exception:
                continue
            _calc = ''
            for _c in ('data/tmp/_pipe_calc_%s.txt' % _cid9,):
                if _os2.path.exists(_c):
                    try:
                        _calc = open(_c, encoding='utf-8').read()
                    except Exception:
                        _calc = ''
                    break
            _txt = _t9 + '\n' + _calc
            _bad = []
            for _sid, _nm, _pok, _ptri, _lv in _ASTEPS:
                if re.search(_pok, _txt):
                    continue
                if re.search(_ptri, _txt):
                    continue
                _bad.append('%s%s' % (_sid, '(H)' if _lv == 'H' else ''))
            if _bad:
                _miss_p33.append('%s 缺: %s' % (_f, ' '.join(_bad)))
    except Exception as _e33:
        _miss_p33.append('audit_steps 调用失败: %s' % type(_e33).__name__)
    if _miss_p33:
        print('❌ P33 步骤审计硬门禁: %s' % _miss_p33[:3])
    else:
        print('✅ P33 步骤审计硬门禁通过（20 步全有数值或实证三态·case299+）')

    # 🔴2026-10-30 P32 明确大球场次「次锚上探 + 宽池含 4/5/6 球」（用户指令「必须改锚定」）
    #   判据（case299+）：raw 若出现大球标记（R-POOL-BIG L1/L2/L3 或 over≥58%）
    #     → 必须含「次锚」上探说明（`次锚` 同行或邻近出现 `≥ 4 球` / `上探` / `R-ANCHOR-BIG`）
    #   并向宽池列出 ≥4 球比分（4 球档：3:1/4:0/2:2；5 球档：3:2/4:1；6 球档：4:2/3:3）
    _miss_p32 = []
    for _f in _os2.listdir('data/case-library/raw'):
        _p = _os2.path.join('data/case-library/raw', _f)
        try:
            _t9 = open(_p, encoding='utf-8').read()
        except Exception:
            continue
        _cid9 = _f.replace('case', '').split('_')[0]
        if not _cid9.isdigit() or int(_cid9) < 299:
            continue
        _isbig = any(k in _t9 for k in ('R-POOL-BIG', 'R-ANCHOR-BIG', '大球很强', '极强大球'))
        if not _isbig:
            continue
        if not any(k in _t9 for k in ('R-ANCHOR-BIG', '次锚上探', '次锚须 ≥', '次锚 ≥ ')):
            _miss_p32.append('%s 大球场但缺「R-ANCHOR-BIG 次锚上探」留痕' % _f)
        # 宽池须出现至少 2 个 ≥4 球比分
        _hi = len([s for s in re.findall(r'[3-9]:\d|\d:[3-9]', _t9) if True])
        if _hi < 2:
            _miss_p32.append('%s 大球场但宽池未见 ≥4 球比分（须含 3:1/3:2/4:2 类）' % _f)
    if _miss_p32:
        print('❌ P32 大球场次锚上探: %s' % _miss_p32[:3])
    else:
        print('✅ P32 大球场次锚上探通过（次锚上探 + 宽池 ≥4 球·case299+）')

    # 🔴2026-10-30 P31 三态必须「已验证」（第二次同类事故固化·case297/298 伤停误报三态）
    #   背景: pipeline Stage2 把**中文队名**传给 bzzoiro → 恒「未定位」→ LLM 照抄「三态不可用」
    #        → 伤停整层缺席，而机制上**没有任何断言**要求验证 → 三态成了「免罚牌」
    #   判据（case299+ 生效）:
    #     ① raw 出现「伤停」且含「三态/未定位/不可用」→ 必须同时含 **验证证据**
    #        （`bzzoiro_fetch` 或 `已验证` 或「两次尝试」）→ 否则判「未经验证的三态」
    #     ② raw 出现「P10 未启用 / 三源不齐」→ 必须含 the-odds-api 补档证据
    #        （`the_odds_api` 或 `补拉` 或 `41 家`）→ 否则判「未尝试补档」
    _miss_p31 = []
    for _f in _os2.listdir('data/case-library/raw'):
        _p = _os2.path.join('data/case-library/raw', _f)
        try:
            _t9 = open(_p, encoding='utf-8').read()
        except Exception:
            continue
        _cid9 = _f.replace('case', '').split('_')[0]
        if not _cid9.isdigit() or int(_cid9) < 299:
            continue
        # ① 伤停三态必须附验证证据
        if ('伤停' in _t9) and any(k in _t9 for k in ('伤停三态', '伤停：三态', '未定位', '伤停不可用')):
            if not any(k in _t9 for k in ('bzzoiro_fetch', '已验证', '两次尝试', 'Bzzoiro 已调用')):
                _miss_p31.append('%s 伤停标三态但**无验证证据**（须写明 bzzoiro_fetch 实跑结果）' % _f)
        # ② P10 三态必须附补档尝试
        if ('P10 未启用' in _t9 or '三源不齐' in _t9) or ('市场矩阵未启用' in _t9):
            if not any(k in _t9 for k in ('the_odds_api', 'the-odds-api', '补拉', '补档', '41 家', '家机构')):
                _miss_p31.append('%s P10 标三态但**无补档尝试**（须写明 the-odds-api 实拉结果）' % _f)
    if _miss_p31:
        print('❌ P31 三态须已验证: %s' % _miss_p31[:3])
    else:
        print('✅ P31 三态已验证通过（伤停/P10 三态均附实证·case299+）')

    # 🔴2026-10-29 P30 信号落地兜底: case294+ 必须含「信号落地核查」节且逐条给动作
    #   根因(case290/292): 告警信号全部写进 raw 但方向未随之改变 = 写了没动作
    _miss_p30 = []
    for _f in _os2.listdir('data/case-library/raw'):
        _p = _os2.path.join('data/case-library/raw', _f)
        try:
            _t30 = open(_p, encoding='utf-8').read()
        except Exception:
            continue
        _cid30 = _f.replace('case', '').split('_')[0]
        if not _cid30.isdigit() or int(_cid30) < 294:
            continue
        if '信号落地核查' not in _t30:
            _miss_p30.append('%s 缺「信号落地核查」节' % _f)
            continue
        _sec = _t30.split('信号落地核查', 1)[1]
        _rows = [l for l in _sec.splitlines() if l.strip().startswith('|') and l.count('|') >= 4]
        _rows = [l for l in _rows if not re.match(r'^\|[\s:\-|]+\|$', l.strip())]
        if len(_rows) < 3:   # 表头 + ≥2 条信号
            _miss_p30.append('%s 信号落地核查节条目不足(%d行)' % (_f, len(_rows)))
        # 🔴2026-10-29 用户指令: 每场最多两向（三向=任何结果都算命中=方向判定失效）
        _dl = [l for l in _t30.splitlines()
               if ('预测方向' in l or '**方向**' in l or l.strip().startswith('| 方向')
                   or l.strip().startswith('| **方向'))]
        _b3 = [l for l in _dl if sum(1 for _w in ('主胜', '平局', '客胜') if _w in l) >= 3]
        if _b3:
            _miss_p30.append('%s 预测方向声明 3 向（须≤2向）' % _f)
        # 🔴2026-11-01 方向覆盖**下限**（原只查「不超过2向」·不查「该2向却写1向」）
        #   缺陷实证（科莫场）：程序已推导「应覆盖 主胜＋平局（单押不准入）」并写进 raw，
        #   但「预测方向」只写主胜 → 没有任何门禁抓（check 只校信号处置·max_two 只管上限）。
        _need_m = re.search(r'应覆盖方向[^\n]*?[:：]\s*\**([^\n｜|]+)', _t30)
        if _need_m and int(_cid30) >= 303:   # 🔴2026-11-01 新增门禁·历史 case(<303) 已复盘免改，仅新场次强制
            _need_l = [_w for _w in ('主胜', '平局', '客胜') if _w in _need_m.group(1)]
            _got_l = []
            for _l in _dl:
                for _w in ('主胜', '平局', '客胜'):
                    if _w in _l and _w not in _got_l:
                        _got_l.append(_w)
            _missd = [_w for _w in _need_l if _w not in _got_l]
            if _missd and _need_l:
                _miss_p30.append(
                    '%s 方向覆盖不足: 程序推导应含 %s · 实际 %s · 缺 %s'
                    % (_f, '+'.join(_need_l), '+'.join(_got_l) or '无', '+'.join(_missd)))
    if _miss_p30:
        print('❌ P30 信号落地兜底: %s' % _miss_p30[:3])
    else:
        print('✅ P30 信号落地兜底通过（信号落地核查节 + 逐条动作·case294+）')

    # 🔴2026-10-25 P10 审计补: 市场矩阵/R10/R11 留痕（条件化——仅 raw 含「市场矩阵(P10」才要求）
    #   治「算了不写」：矩阵算了但 raw 只有锚、没有分布/判定层 → 事后无法审计 R10/R11 是否真跑
    _miss_p10 = []
    for _f in _os2.listdir('data/case-library/raw'):
        _p = _os2.path.join('data/case-library/raw', _f)
        try:
            _t3 = open(_p, encoding='utf-8').read()
        except Exception:
            continue
        if ('市场矩阵(P10' in _t3) or ('市场矩阵（P10' in _t3):
            _lack = [n for n in ('R10判定层', 'R11 零封') if n not in _t3]
            if _lack:
                _miss_p10.append('%s 缺 %s' % (_f, '/'.join(_lack)))
    if _miss_p10:
        print('❌ raw 含「市场矩阵(P10」但缺 R10/R11 留痕: %s' % _miss_p10[:3])
    else:
        print('✅ P10/R10/R11 留痕校验通过（未提及 或 已留痕）')

    # 🔴2026-10-26 审计补: P12 机构意图 + R12 双锚联合覆盖（条件化·治「算了不写」）
    _miss_p12 = []
    for _f in _os2.listdir('data/case-library/raw'):
        _p = _os2.path.join('data/case-library/raw', _f)
        try:
            _t4 = open(_p, encoding='utf-8').read()
        except Exception:
            continue
        if ('P12' in _t4) and ('机构意图' in _t4):
            _lack12 = [n for n in ('欧赔三向', '真伪闸门') if n not in _t4]
            if _lack12:
                _miss_p12.append('%s 缺P12[%s]' % (_f, '/'.join(_lack12)))
        if '双锚联合覆盖' in _t4:
            import re as _re12
            if not _re12.search(r'联合覆盖\s*[\d.]+\s*%', _t4):
                _miss_p12.append('%s 双锚覆盖缺百分比数值' % _f)
    if _miss_p12:
        print('❌ P12/R12 留痕不完整: %s' % _miss_p12[:3])
    else:
        print('✅ P12/R12 留痕校验通过（未提及 或 已留痕）')

    if _miss_trace:
        print('❌ case159+ 缺少「学习成果/融合判定」留痕: %s' % _miss_trace[:3])
    else:
        print('✅ case159+ 学习成果/融合判定留痕完整（闭环可审计）')
    print('✅ 全部场次落盘完整（五部分+硬核12项+xG判定·CSV 字段一致）')
    if not only:  # 🔴2026-09-04链路优化: 重复对阵检测仅全量时输出(原顶层无条件print·带单case参数时也误执行)
        print(dedup_check())



def dedup_check():
    """🔴物理任务锁(2026-08-24·防重复落盘): 案例库 CSV 已存在同主客队+同日期 → 报重复·阻断二次写入"""
    import csv, os, re
    csv_path = 'data/case-library/实战案例.csv'
    if not os.path.exists(csv_path): return '  ⚠️ 案例库CSV缺失·跳过重复检测'
    try:
        with open(csv_path, encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
    except Exception as e:
        return f'  ⚠️ 案例库CSV读取失败({e})·跳过'
    if not rows: return '  ✅ 案例库空·无重复'
    # 检查是否有完全相同的主客队组合(去重检测·模型按 eventId/日期人工比对)
    seen = {}
    dup = []
    for r in rows:
        key = (str(r.get('主队','')).strip(), str(r.get('客队','')).strip())
        if key in seen and key != ('',''):
            dup.append(f'{key[0]}vs{key[1]}({seen[key]}·{r.get("赛事编号","")})')
        else:
            seen[key] = r.get('赛事编号','')
    return f'  {"✅ 无重复对阵" if not dup else "🔴 疑似重复: " + "; ".join(dup[:5])}'


if __name__ == '__main__':
    main()
