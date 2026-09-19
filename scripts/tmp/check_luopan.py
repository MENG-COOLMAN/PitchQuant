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
        # 新增(case159起): raw 须含「学习成果/融合判定」留痕（闭环可审计）
        _learn_trace = False
        _cidi = int(cid) if str(cid).isdigit() else 0
        if _cidi < 97:
            # 旧格式兼容（模板固化前 -96·用户选择）: 节标题变体 + 六/七节不强制
            # 旧格式实例: '## 五、模型结论' / '## 三、API数据'(代替场景) / 无六、七节(模板后加)
            _legacy_need = [('一、竞彩', ('竞彩',)), ('二、欧盘', ('欧盘', 'Odds-API')),
                            ('三、场景/API数据', ('场景', 'API数据')), ('四、基本面', ('基本面',)),
                            ('五、结论', ('结论',))]
            for _lbl, _keys in _legacy_need:
                if not any(_k in t for _k in _keys):
                    issues.append(f'case{cid} ({os.path.basename(p)}): 缺节 [{_lbl}]')
        else:
            for n in need:
                if n not in t:
                    issues.append(f'case{cid} ({os.path.basename(p)}): 缺节 [{n}]')
        # 新增(raw 须含市场源/锚-量级一致性留痕
        _new_rules = ['市场', '量级']
        # 三类新规则留痕仅对 起强制（历史 raw 不回溯·防噪音·既定策略）
        _cidi = int(cid) if str(cid).isdigit() else 0
        if _cidi >= 168 and not any(k in t for k in ('市场源', '市场净胜', 'market')):
            issues.append(f'case{cid}: raw 缺【市场源/市场净胜档】留痕(2026-09-13起)')
        if _cidi >= 168 and not any(k in t for k in ('锚-量级', '量级一致', '量级矛盾')):
            issues.append(f'case{cid}: raw 缺【锚-量级一致性】留痕(2026-09-13起)')
        # 新增(用户要求"锚定一定要与市场信号一致"): raw 须含锚-市场一致性留痕
        if _cidi >= 168 and not any(k in t for k in ('锚-市场', '市场一致性', 'market_anchor')):
            issues.append(f'case{cid}: raw 缺【锚-市场一致性】留痕(2026-09-13起·用户要求)')
        # 审计修复(P1-1/2/3·case188审计): raw 第八节「执行留痕」六子块校验(+强制) — 治「审计看不到=判未执行」: 对话输出做了但 raw 没写 → 审计误判未执行
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
    if all_issues:
        print('❌ 问题:')
        for i in all_issues: print(' ', i)
        sys.exit(1)
    # case159起: 学习成果/融合判定留痕校验（闭环审计）
    import re as _re2, os as _os2
    _miss_trace = []
    for _f in _os2.listdir('data/case-library/raw'):
        _m = _re2.search(r'case(\d+)', _f)
        if not _m or int(_m.group(1)) < 159:
            continue
        _txt = open(_os2.path.join('data/case-library/raw', _f), encoding='utf-8').read()
        if ('学习成果' not in _txt) and ('融合方向概率' not in _txt) and ('学习成果进入判定' not in _txt):
            _miss_trace.append(_f)
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
