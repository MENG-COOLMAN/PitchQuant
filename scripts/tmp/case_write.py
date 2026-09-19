"""案例库结构化写入（防乱码/串码/遗失·2026-08-30）
用法:
  python scripts/tmp/case_write.py add    --league 英超 --home 曼城 --away 伯恩茅斯 --pred 主胜 --anchor "2:1,3:1" --conf HIGH --signal "D1+G1" --assoc 无
  python scripts/tmp/case_write.py review --case 70 --real "2:1" [--dir 是|否] [--score 是|否] [--concl 复盘结论]
铁律: 案例库写入必须走本脚本·禁止手写CSV（防串码）·字段清洗+写后读回校验（防遗失）·编码utf-8-sig（防乱码）
"""
import csv, io, sys, os, re, datetime
sys.stdout.reconfigure(encoding='utf-8')
CSV = 'data/case-library/实战案例.csv'
RAW_DIR = 'data/case-library/raw'
HDR = ['case_id','日期','联赛','主队','客队','预测方向','预测比分','真实比分','方向命中','比分命中','完美命中','置信度层','触发信号','关联假设','复盘结论','比分口径','主锚命中','次锚命中']
HITS = ('是','否')
LEVELS = ('HIGH','MID','LOW','MID-LOW','待补充')
CONF_RE = re.compile(r'^\d+\s*:\s*\d+$')

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
    """写后读回校验: 列数=HDR(18)·无空case_id·无乱码(可解码)"""
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
              'conf': '置信度层', 'signal': '触发信号', 'assoc': '关联假设', 'date': '日期'}
    for _en, _cn in _ALIAS.items():
        if _en in args and _cn not in args:
            args[_cn] = args[_en]
    rows = load()
    ids = [int(r[0]) for r in rows[1:] if r[0].strip().isdigit()]
    cid = str(max(ids) + 1) if ids else '1'
    row = [cid]
    for f in HDR[1:]:
        v = args.get(f)
        row.append(clean(v, f, allow_comma=(f == '预测比分')) if v is not None else '')
    # 预测比分格式校验: 主:客,主:客
    for s in row[6].split(','):
        if s and not CONF_RE.match(s): raise ValueError(f'预测比分格式错(需 主:客,主:客): {s!r}')
    rows.append(row)
    with open(CSV, 'w', encoding='utf-8-sig', newline='') as f:
        csv.writer(f).writerows(rows)
    verify(rows)
    print(f'✅ 预测已写入 case{cid}: {row[3]}vs{row[4]} {row[5]} {row[6]} ({row[11]})')

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
    dir_ok = rd in pred_dir
    # 比分命中: 真实==主锚或次锚(候选前2·逗号分隔)
    anchors = [a for a in target[6].split(',') if a]
    score_ok = real in anchors[:2]
    target[7] = real
    target[8] = '是' if dir_ok else '否'
    target[9] = '是' if score_ok else '否'
    target[10] = '是' if (dir_ok and score_ok) else '否'
    concl = clean(args.get('concl'), '复盘结论', allow_comma=True)
    if concl: target[14] = concl
    with open(CSV, 'w', encoding='utf-8-sig', newline='') as f:
        csv.writer(f).writerows(rows)
    verify(rows)
    # raw 复盘节追加
    raws = [f for f in os.listdir(RAW_DIR) if f.startswith(f'case{cid}_')]
    if raws:
        rp = os.path.join(RAW_DIR, raws[0])
        with open(rp, encoding='utf-8') as f: c = f.read()
        c += f'\n---\n## 复盘（{datetime.date.today()}·用户提供真实赛果）\n- 真实比分: **{real}**\n- 方向命中: {target[8]}（预测{target[5]}·真实{rd}）\n- 比分命中: {target[9]}（真实==主锚或次锚·新口径）\n- 完美命中: {target[10]}\n- 复盘结论: {concl or "无"}\n'
        with open(rp, 'w', encoding='utf-8') as f: f.write(c)
        print(f'  raw复盘节已追加: {raws[0]}')
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
        '（新闻伤停 + api-football + footballcharts + ELO + H2H·三态标注）\n\n'
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
    cmd, argv = argv[0], argv[1:]
    args = load_args(argv)
    try:
        if cmd == 'add': cmd_add(args)
        elif cmd == 'review': cmd_review(args)
        elif cmd == 'raw': cmd_raw(args)
        else: raise ValueError(f'未知命令 {cmd}')
    except (ValueError, RuntimeError) as e:
        print('❌', e); sys.exit(1)
