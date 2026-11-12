"""案例库结构化写入（防乱码/串码/遗失·2026-08-30）
用法:
  python data/tmp/case_write.py add    --league 英超 --home 曼城 --away 伯恩茅斯 --pred 主胜 --anchor "2:1,3:1" --conf HIGH --signal "D1+G1" --assoc 无
  python data/tmp/case_write.py review --case 70 --real "2:1" [--dir 是|否] [--score 是|否] [--concl 复盘结论]
铁律: 案例库写入必须走本脚本·禁止手写CSV（防串码）·字段清洗+写后读回校验（防遗失）·编码utf-8-sig（防乱码）
"""
import csv, io, sys, os, re, datetime
sys.stdout.reconfigure(encoding='utf-8')
CSV = 'data/case-library/实战案例.csv'
RAW_DIR = 'data/case-library/raw'
HDR = ['case_id','日期','联赛','主队','客队','预测方向','预测比分','真实比分','方向命中','比分命中','完美命中','置信度层','触发信号','关联假设','复盘结论','比分口径','主锚命中','次锚命中',
       'pH_模型','pD_模型','pA_模型']   # 🔴2026-09-30 追加 3 列（评论者建议②·log loss 前置）
                                        #   必须置于【末尾】：本表 7 个消费方（case_stats/check_luopan/conf_calib/
                                        #   eval_baseline/learn_result/check_sync/case_write）中 check_luopan 按索引访问
                                        #   r[5]/r[6]/r[7] → 前置列会破坏解析；末尾追加则前 18 列索引不变
HITS = ('是','否')
LEVELS = ('HIGH','MID','LOW','MID-LOW','待补充')
CONF_RE = re.compile(r'^\d+\s*:\s*\d+$')

def dir_hit(pred_dir, rd):
    """🔴方向命中·单一实现（2026-10-17 固化·治「多脚本各写一份·改一处≠改全部」复发第2次）

    口径（2026-08-27 用户定）：预测含并列/次方向即 ✅ —— 全称优先匹配。
    简写兜底（主/平/客）必须排除「括号内孤字主方向标记」：
      「客胜(主)+平局(覆盖)」的 (主) = **主方向标记**，不是主胜声明
        → case250 实抓：真实 1:0 主胜被判方向✅（应为❌）
      「主胜(并列平局)」括号含并列语义 = **真方向声明**，全称匹配即可命中，不受影响
    调用方：case_write.cmd_review / self_iterate.learn（禁再各自实现）
    """
    if not pred_dir or not rd:
        return False
    if rd in pred_dir:
        return True
    _SHORT = {'主胜': '主', '平局': '平', '客胜': '客'}
    _s = re.sub(r'[（(]\s*[主客平]\s*[）)]', '', pred_dir)
    return _SHORT.get(rd, '') in _s


def clean(v, field, allow_comma=False):
    """字段清洗: 去首尾空格·禁换行·信号禁逗号（防串码）"""
    v = (v or '').strip().replace('\n', ' ').replace('\r', '')
    if not allow_comma and ',' in v and field != '预测比分':
        raise ValueError(f'字段[{field}]禁含逗号(防串码): {v!r}·信号请用+连接')
    return v

def load():
    rows = list(csv.reader(open(CSV, encoding='utf-8-sig')))
    assert rows[0] == HDR, '表头不匹配!'
    return rows

def verify(rows):
    """写后读回校验: 列数=len(HDR)·无空case_id·无乱码(可解码)"""
    errs = []
    for i, r in enumerate(rows[1:], 1):
        if len(r) != len(HDR): errs.append(f'行{i+1} 列数{len(r)}≠{len(HDR)}')
        if not r[0].strip(): errs.append(f'行{i+1} case_id空')
    if errs: raise RuntimeError('校验失败: ' + '; '.join(errs[:5]))
    return True

def load_args(argv):
    """参数解析: 支持 --file params.json（推荐·UTF-8无编码/引号问题）或 --k v 命令行"""
    args = {}
    i = 0
    argv = [a.strip("'\"") for a in argv]  # 🔴清洗cmd包装残留的单/双引号
    while i < len(argv):
        if argv[i] == '--file' and i+1 < len(argv):
            import json
            args.update(json.load(open(argv[i+1], encoding='utf-8'))); i += 2
        elif argv[i].startswith('--') and i+1 < len(argv):
            args[argv[i][2:]] = argv[i+1]; i += 2
        else: i += 1
    return args

def cmd_add(args):
    # 🔴2026-09-04修复: 键别名归一(docstring用--home/--away英文·HDR表头为中文·原实现args.get('主队')=None→写空行)
    _ALIAS = {'league': '联赛', 'home': '主队', 'away': '客队', 'pred': '预测方向', 'anchor': '预测比分',
              'conf': '置信度层', 'signal': '触发信号', 'assoc': '关联假设', 'date': '日期',
              # 🔴2026-10-29 补：pH/pD/pA 模型概率（2026-09-30 追加的 log loss 前置三列）
              #   实测三场（294/295/296）add 时未传 → 三列全空 → 追溯补填须走本参数
              'ph': 'pH_模型', 'pd': 'pD_模型', 'pa': 'pA_模型'}
    # 🔴2026-09-29 完成度检验修复: `case_id` 别名（原仅认 `case`）—— 本次实测踩坑:
    #   params.json 用 `case_id` 时 args.get('case')=None → 未走显式 ID 分支 → 自动 +1 编号
    #   → 复跑 case220 时误插为 case221（重复行）→ 补别名 + 下条「已存在则拦截」双保险
    if 'case_id' in args and 'case' not in args:
        args['case'] = args['case_id']
    for _en, _cn in _ALIAS.items():
        if _en in args and _cn not in args:
            args[_cn] = args[_en]
    rows = load()
    ids = [int(r[0]) for r in rows[1:] if r[0].strip().isdigit()]
    cid = str(max(ids) + 1) if ids else '1'
    if args.get('case') and str(args['case']).strip().isdigit():  # 2026-09-27 修复: 支持显式 --case
        cid = str(int(args['case']))
    row = [cid]
    for f in HDR[1:]:
        v = args.get(f)
        row.append(clean(v, f, allow_comma=(f == '预测比分')) if v is not None else '')
    # 预测比分格式校验: 主:客,主:客
    for s in row[6].split(','):
        if s and not CONF_RE.match(s): raise ValueError(f'预测比分格式错(需 主:客,主:客): {s!r}')
    # 🔴2026-09-29 修复(P0·实测发生): 原实现无条件 rows.append(row) → 对同一 case 重跑 add 会产生
    #   重复行（案例库 217 行→手动去重），污染统计。改为 upsert: 已存在 → 替换该行；
    #   🔴替换时必须保留既有「复盘派生列」，否则改预测会清空赛果/命中统计。
    KEEP = (7, 8, 9, 10, 14, 15, 16, 17)   # 真实比分/方向命中/比分命中/完美命中/复盘结论/比分口径/主锚命中/次锚命中
    idx, kept = None, 0
    for i, r in enumerate(rows[1:], 1):
        if r and r[0].strip() == cid: idx = i; break
    if idx is not None:
        old = rows[idx]
        while len(row) < len(HDR): row.append('')
        for k in KEEP:
            if k < len(old) and old[k].strip() and not row[k].strip():
                row[k] = old[k]; kept += 1
        rows[idx] = row
        action = f'已更新(保留{kept}个复盘字段)'
    else:
        rows.append(row)
        action = '已新增'
    with open(CSV, 'w', encoding='utf-8-sig', newline='') as f:
        csv.writer(f).writerows(rows)
    verify(rows)
    print(f'✅ 预测{action} case{cid}: {row[3]}vs{row[4]} {row[5]} {row[6]} ({row[11]})')

def cmd_review(args):
    rows = load()
    cid = str(args.get('case'))
    target = None
    for r in rows[1:]:
        if r[0].strip() == cid: target = r; break
    if not target: raise ValueError(f'case{cid} 不存在')
    real = clean(args.get('real'), '真实比分')
    if not CONF_RE.match(real): raise ValueError(f'真实比分格式错(需 主:客): {real!r}')
    gh, ga = map(int, real.split(':'))
    pred_dir = target[5]
    rd = '主胜' if gh > ga else ('平局' if gh == ga else '客胜')
    # 方向命中: 预测含真实方向(并列/次方向)
    # 🔴2026-09-29 修复: 预测方向串可能用简写（如「主胜(降档)>平>客」的「客」），
    #   原实现 rd in pred_dir 只认全称 → case216 客胜被误判「否」。改为全称优先+简写兜底。
    _SHORT = {'主胜': '主', '平局': '平', '客胜': '客'}
    dir_ok = dir_hit(pred_dir, rd)                 # 🔴单一实现（见模块级 dir_hit）
    # 比分命中: 真实==主锚或次锚(候选前2·逗号分隔)
    anchors = [a for a in target[6].split(',') if a]
    score_ok = real in anchors[:2]
    target[7] = real
    target[8] = '是' if dir_ok else '否'
    target[9] = '是' if score_ok else '否'
    # 🔴2026-10-21 P0 修正: 完美 = **strict(仅第一推荐方向)** 且 锚命中
    #   原实现用 dir_ok(any·含并列/次方向) → 与 AGENTS 定义「direction_hit_strict」冲突
    #   实测: 14 场被误判完美（case56/112/119/123/175/190/192/200/210/228/232/242/247/262）
    _first_dir = None
    _m = re.search(r'(主胜|平局|客胜)', pred_dir or '')
    if _m: _first_dir = _m.group(1)
    _strict_ok = (_first_dir == rd)
    target[10] = '是' if (_strict_ok and score_ok) else '否'
    # 🔴2026-10-17 追加（复盘实抓）: 派生三列自动填充——原实现只写 7/8/9/10/14，
    #   而「比分口径(15)/主锚命中(16)/次锚命中(17)」恒空 → conf_calib/case_stats 失去分锚口径
    if len(anchors) >= 1:
        target[16] = '是' if real == anchors[0] else '否'
    if len(anchors) >= 2:
        target[17] = '是' if real == anchors[1] else '否'
    if anchors:
        target[15] = '主锚+次锚'
    concl = clean(args.get('concl'), '复盘结论', allow_comma=True)
    if concl: target[14] = concl
    with open(CSV, 'w', encoding='utf-8-sig', newline='') as f:
        csv.writer(f).writerows(rows)
    verify(rows)
    # raw 复盘节写入
    # 🔴2026-09-29 修复(与 cmd_add 的 append 同类缺陷): 原实现 c += 复盘节（无条件追加）
    #   → 重跑 review（如修正口径/改写结论）会产生**重复复盘节**。改为幂等:
    #   已有「## 复盘（」节则整段替换（含其前置 --- 分隔线），否则追加。
    # 🔴2026-10-16 修复（"存在≠活跃"型缺陷·case244-247 复盘实抓）:
    #   原实现只认 `case{cid}_*.md`（历史命名带队名后缀），而本批 raw 命名为 `case{cid}.md`
    #   → 恒不匹配 → **静默不写 raw 复盘节**（CSV 更新了但 raw 无留痕 = 复盘不完整且无报错）
    _rd_files = os.listdir(RAW_DIR)
    _exact = f'case{cid}.md'
    if _exact in _rd_files:
        raws = [_exact]
    else:
        raws = [f for f in _rd_files if f.startswith(f'case{cid}_')]
    if raws:
        rp = os.path.join(RAW_DIR, raws[0])
        with open(rp, encoding='utf-8') as f: c = f.read()
        sec = (f'\n---\n## 复盘（{datetime.date.today()}·用户提供真实赛果）\n'
               f'- 真实比分: **{real}**\n'
               f'- 方向命中: {target[8]}（预测{target[5]}·真实{rd}）\n'
               f'- 比分命中: {target[9]}（真实==主锚或次锚·新口径）\n'
               f'- 完美命中: {target[10]}\n'
               f'- 复盘结论: {concl or "无"}\n')
        MARK = '\n---\n## 复盘（'
        if MARK in c:
            c = c[:c.index(MARK)] + sec; verb = '已更新(幂等替换)'
        else:
            c = c.rstrip('\n') + '\n' + sec; verb = '已追加'
        with open(rp, 'w', encoding='utf-8') as f: f.write(c)
        print(f'  raw复盘节{verb}: {raws[0]}')
    print(f'✅ 复盘完成 case{cid}: 真实{real} 方向{target[8]} 比分{target[9]} 完美{target[10]}')

def cmd_raw(args):
    """生成 raw 七节骨架（防 raw 遗失·LLM 填充内容后 check_luopan 校验）"""
    cid = str(args.get('case'))
    home = clean(args.get('home'), '主队', allow_comma=True)
    away = clean(args.get('away'), '客队', allow_comma=True)
    fname = 'case' + cid + '_' + home + 'vs' + away + '.md'
    fpath = os.path.join(RAW_DIR, fname)
    if os.path.exists(fpath):
        print('⚠️ raw 已存在: ' + fname); return
    tpl = (
        '## 一、竞彩全文\n'
        '（用户txt完整粘贴·胜平负/让球/半全场/总进球/比分全部变动序列）\n\n'
        '## 二、欧盘\n'
        '（Odds-API get_odds 全文·ML/Spread/Totals·eventId）\n\n'
        '## 三、场景\n'
        '（Step3 44/45/46 + 欧战核查表 + 修正53 S1-S7）\n\n'
        '## 四、基本面\n'
        '（新闻伤停 + the-odds-api 机构赔率 + understat xG + ELO + H2H·三态标注）\n\n'
        '## 五、结论\n'
        '（方向/置信度/主锚次锚/总进球/半场/BTTS/停止分支）\n\n'
        '## 六、硬核层12项\n'
        '（Step1 硬核12项逐项数值·calc_match 输出）\n\n'
        '## 七、xG深度判定\n'
        '（xG 深度比分判定·防泄露）\n'
    )
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(tpl)
    print('✅ raw 骨架已生成: ' + fname + '(七节·待填充内容+check_luopan校验)')

if __name__ == '__main__':
    argv = sys.argv[1:]
    if not argv: print(__doc__); sys.exit(1)
    # 🔴V3.5.91 修（2026-11-03 实证）: `add --help` 曾把 --help 当参数 →
    #   **直接写入一条 21 列全空的记录**（污染案例库·须手工删）
    if any(a in ('-h', '--help', '/?', '-?') for a in argv):
        print(__doc__)
        print('\n用法: case_write.py add   --file params.json   (推荐·防引号/编码问题)')
        print('      case_write.py add   --case 320 --home 曼联 --away 罗马 ...')
        print('      case_write.py review --file review.json')
        print('      case_write.py raw   --case 320 --home 曼联 --away 罗马')
        print('\n⚠️ params.json 键: case/date/league/home/away/pred/anchor/conf/'
              'signal/assoc/ph/pd/pa')
        sys.exit(0)
    cmd, argv = argv[0], argv[1:]
    args = load_args(argv)
    try:
        if cmd == 'add': cmd_add(args)
        elif cmd == 'review': cmd_review(args)
        elif cmd == 'raw': cmd_raw(args)
        else: raise ValueError(f'未知命令 {cmd}')
    except (ValueError, RuntimeError) as e:
        print('❌', e); sys.exit(1)
