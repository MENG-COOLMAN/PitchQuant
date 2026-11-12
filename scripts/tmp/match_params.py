# -*- coding: utf-8 -*-
"""🔴本场参数标准化（2026-10-11 封装·治「每场手写临时参数文件 + 手打 60+ CLI 参数」的散乱与易错）

## 为什么封装（证据）
  · `calc_all.py` 支持 **60+ 个 `--参数`** → 分析时手打易错
    历史事故: case151 `--eu` 主客传反 / 多次漏传 `--handi` / 漏传 `--net` 致网络源静默 skipped
  · 此前**每场手工创建** `data/tmp/_caseXXX_params.json` / `_euXXX.json` / `_revXXX.json`
    （格式各一·无校验·事后零引用残留 **17 个**·与「数据隔离/禁跨场复用」纪律相冲）
  · → 统一为 `data/tmp/params/case<ID>.json`（**单一格式 + 自洽校验 + 一键生成命令/执行**）

## 用法
  python data/tmp/match_params.py save  --case 236 --txt data/tmp/std_jc_x.txt --league 英超 \\
        --eu 2.72,3.63,2.68 --o25 1.71 --u25 2.32 --handi 0 --net
  python data/tmp/match_params.py show  --case 236          # 打印完整 calc_all 命令（可复制）
  python data/tmp/match_params.py check --case 236          # 自洽校验（去水/格式/让球口径）
  python data/tmp/match_params.py run   --case 236 [--dry-run]
  python data/tmp/match_params.py list

🔴 边界: 本脚本**只做参数标准化与校验**·不改任何判定逻辑·不产生分析结论。
🔴 2026-10-11 自查修复: ①ROOT 由 dirname(HERE) 更正为 dirname(dirname(HERE))（原指向 data/ → run 必然失败）
   ②去掉「主<平<客」顺序硬判（平局隐含最低是正常现场·会误报）→ 改判「平局隐含为三者最高」（真异常）
"""
import sys, os, json, argparse, subprocess, datetime

sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))            # <ws>/data/tmp
ROOT = os.path.dirname(os.path.dirname(HERE))                # <ws>（calc_all 相对路径基准·run 的 cwd）
PDIR = os.path.join(HERE, 'params')
CALC_ALL = os.path.join(HERE, 'calc_all.py')
POS_KEYS = ('txt', 'league')                 # calc_all 的两个位置参数
SWITCH = ('net', 'off')                      # 无值开关
ORDER = ['eu', 'o25', 'u25', 'handi', 'home_water', 'elo', 'inj_h', 'inj_a', 'off',
         'totals_multi', 'line_open', 'line_close', 'water_open', 'water_close',
         'mins_to_ko', 'kickoff', 'snapshot', 'home', 'away', 'bsd_event', 'bsd_teams',
         'max_h', 'max_d', 'max_a', 'max_o25', 'max_u25', 'net']


def _pairs(extra):
    """['--eu','1,2,3','--net'] → {'eu':'1,2,3','net':'1'}"""
    d, i = {}, 0
    while i < len(extra):
        k = extra[i]
        if not str(k).startswith('--'):
            i += 1
            continue
        k = k[2:].replace('-', '_')
        nxt = extra[i + 1] if i + 1 < len(extra) else None
        if nxt is not None and not str(nxt).startswith('--'):
            d[k] = nxt
            i += 2
        else:
            d[k] = '1'
            i += 1
    return d


def _path(case):
    return os.path.join(PDIR, 'case%s.json' % case)


def _txt_ok(txt):
    if not txt:
        return False
    if os.path.isabs(txt):
        return os.path.exists(txt)
    return any(os.path.exists(p) for p in (os.path.join(ROOT, txt), os.path.join(os.getcwd(), txt)))


def check_cfg(cfg):
    """自洽校验 → (ok, issues)；issues 逐条可执行（含历史事故提示）"""
    issues = []
    txt = cfg.get('txt')
    if not txt:
        issues.append('缺 --txt（calc_all 第 1 位置参数）')
    elif not _txt_ok(txt):
        issues.append('txt 不存在: %s（先跑 txt_normalize.py 归一化）' % txt)
    if not cfg.get('league'):
        issues.append('缺 --league（calc_all 第 2 位置参数·联赛参数已归一化: 英超=E0=epl）')
    eu = cfg.get('eu')
    if not eu:
        issues.append('缺 --eu（硬核层统一用欧盘口径·必需）')
    else:
        try:
            a, b, c = [1.0 / float(x) for x in str(eu).split(',')]
            s = a + b + c
            ph, pdr, pa = 100 * a / s, 100 * b / s, 100 * c / s
            cfg['_imp'] = '%.1f/%.1f/%.1f' % (ph, pdr, pa)
            if not (0.98 <= s <= 1.10):
                issues.append('--eu 去水和 %.3f 异常（正常 0.99-1.08）→ 是否误传竞彩赔率/带抽水口径' % s)
            if pdr >= max(ph, pa):
                issues.append('--eu 平局隐含 %.1f%% 为三者最高 → 格式/顺序可疑（须【主,平,客】·历史 case151 主客传反）' % pdr)
        except Exception:
            issues.append('--eu 格式错（应 主,平,客 三段数字）: %s' % eu)
    for k in ('o25', 'u25', 'handi'):
        if k in cfg:
            try:
                float(cfg[k])
            except Exception:
                issues.append('--%s 非数字: %s' % (k, cfg[k]))
    if 'o25' in cfg and 'u25' in cfg:
        try:
            s2 = 1.0 / float(cfg['o25']) + 1.0 / float(cfg['u25'])
            if not (0.98 <= s2 <= 1.12):
                issues.append('O2.5/U2.5 去水和 %.3f 异常（正常 0.99-1.10）→ 检查两值是否同侧/传错' % s2)
        except Exception:
            pass
    if 'handi' in cfg:
        try:
            if abs(float(cfg['handi'])) > 5:
                issues.append('--handi %s 异常（应 -4~4；负数=主让·正数=主受让·取【均衡线】档）' % cfg['handi'])
        except Exception:
            pass
    if str(cfg.get('net', '')) != '1':
        issues.append('未带 --net → 网络源全 skipped（学习特征残缺·2026-09-14 铁律）· 离线复跑请显式 save --net 0')
    return (not issues), issues


def cmd_line(cfg):
    parts = ['python', 'data/tmp/calc_all.py', str(cfg.get('txt', '<txt>')), str(cfg.get('league', '<联赛>'))]
    seen = set()
    for k in ORDER:
        if k in cfg and k not in POS_KEYS:
            v = str(cfg[k])
            if k in SWITCH and v == '0':
                seen.add(k)
                continue
            parts.append('--' + k.replace('_', '-'))
            if k not in SWITCH:
                parts.append(v)
            seen.add(k)
    for k, v in cfg.items():
        if str(k).startswith('_') or k in seen or k in POS_KEYS:
            continue
        parts.append('--' + k.replace('_', '-'))
        if k not in SWITCH:
            parts.append(str(v))
    return ' '.join(parts)


def do_save(case, cfg):
    if not case:
        print('❌ 缺 --case'); return 1
    os.makedirs(PDIR, exist_ok=True)
    ok, issues = check_cfg(cfg)
    cfg['_case'] = case
    cfg['_saved_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(_path(case), 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    print('✅ 已写 data/tmp/params/case%s.json' % case)
    if cfg.get('_imp'):
        print('   隐含概率(主/平/客): %s%%' % cfg['_imp'])
    if ok:
        print('   校验: 全部通过')
    else:
        print('   ⚠️ 校验 %d 项待确认:' % len(issues))
        for i in issues:
            print('     · ' + i)
    return 0


def do_show(case):
    p = _path(case)
    if not os.path.exists(p):
        print('❌ 无参数文件: %s（先 save）' % p); return 1
    cfg = json.load(open(p, encoding='utf-8'))
    ok, issues = check_cfg(cfg)
    print('📋 case%s · 保存于 %s' % (case, cfg.get('_saved_at', '?')))
    print('   隐含概率: %s%%' % (cfg.get('_imp', '-')))
    print('▶ ' + cmd_line(cfg))
    for i in issues:
        print('   ⚠️ ' + i)
    return 0 if ok else 2


def do_run(case, dry=False):
    p = _path(case)
    if not os.path.exists(p):
        print('❌ 无参数文件: %s（先 save）' % p); return 1
    cfg = json.load(open(p, encoding='utf-8'))
    ok, issues = check_cfg(cfg)
    for i in issues:
        print('⚠️ ' + i)
    cl = cmd_line(cfg)
    print('▶ ' + cl)
    if dry:
        print('（--dry-run → 未执行）'); return 0
    return subprocess.run(cl, shell=True, cwd=ROOT).returncode


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument('cmd', choices=['save', 'show', 'check', 'run', 'list'])
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('-h', '--help', action='store_true')
    args, extra = ap.parse_known_args()
    if args.help:
        print(__doc__); return 0
    if args.cmd == 'list':
        if not os.path.isdir(PDIR):
            print('（params 目录尚未创建）'); return 0
        for f in sorted(os.listdir(PDIR)):
            print('  ' + f)
        return 0
    cfg = _pairs(extra)
    case = cfg.pop('case', None)
    if args.cmd == 'save':
        return do_save(case, cfg)
    if not case:
        print('❌ 缺 --case'); return 1
    if args.cmd == 'show':
        return do_show(case)
    if args.cmd == 'check':
        ok, issues = check_cfg(json.load(open(_path(case), encoding='utf-8')))
        print(('✅ case%s 参数自洽' % case) if ok else ('⚠️ case%s 有 %d 项待确认:' % (case, len(issues))))
        for i in issues:
            print('   · ' + i)
        return 0 if ok else 2
    if args.cmd == 'run':
        return do_run(case, args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
