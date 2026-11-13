# -*- coding: utf-8 -*-
"""
pipeline.py — 单场分析「一键全流程」（2026-10-28 P21·治「漏步骤 + 重复跑 + 消费不足」）
================================================================================
定位：把原本分散在多轮手工调用的阶段串成一条命令，**一次跑完**：

  Stage0 txt 归一化            (txt_normalize·0.1s)
  Stage1 开场 preflight        (run_guard·0.4s·A-H 段门禁)
  Stage2 数据采集(并行缓存)     (the-odds-api books + Bzzoiro 伤停·热缓存 ~6s)
  Stage3 方向默认推导          (去水→最低+次低赔率·铁律默认覆盖)
  Stage4 计算                  (calc_all 一次跑全参数·~35s·禁重跑)
  Stage5 raw 骨架生成          (八节框架 + calc_all 关键块全量内嵌 + 「待模型判断」占位)
  Stage6 消费审计              (audit_consumption·骨架已含数值→应 0 遗漏)
  Stage7 汇总报告              (自动过/待模型填/三态缺口·一屏输出)

设计铁律：
  · **不省步骤**：Stage0-6 缺一不可，任一失败即停并给原因
  · **不重复跑**：--step5-dirs / --inj_* / --event 全部在**第一次**就传对（禁「先跑看输出再补参数」）
  · **数值程序填·判断模型填**：raw 骨架把 calc_all 的所有数值原样内嵌 → 消除「算了不写」
  · **失败不掩盖**：任一阶段异常 → 三态标注 + 非零退出码（禁静默通过）

用法：
  python pipeline.py <竞彩txt> --teams "主,客" --league 意甲 --kickoff "YYYY-MM-DD HH:MM"
      [--event <id>] [--eu "h,d,a"] [--handi <-1.5>] [--home_water <>] [--o25 <>] [--u25 <>]
      [--inj_list_h "..."] [--inj_list_a "..."] [--draw-score <>] [--case <id>]
      [--skip-net] [--no-skeleton]
"""
import os, re, sys, io, json, time, argparse, subprocess, glob

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
os.chdir(ROOT)
PY = sys.executable
SC = HERE  # 脚本所在目录（工作区=data/tmp · 发布版=scripts/tmp）


def _sc(name):
    """子脚本路径（目录无关·禁写死 data/tmp）"""
    return os.path.join(SC, name)

TIMING = []
STAGE_FAIL = []


def stage(no, name):
    return (no, name, time.time())


SOFT_WARN = []          # 外部源三态（不进 STAGE_FAIL·但必须 raw 留痕）


def done(s, ok=True, note='', soft=False):
    """soft=True: 外部数据源三态 —— 打 🔴 提醒但**不算流程失败**。

    AGENTS 铁律: 三态标注 = 合规输出（没数据也要说）≠ 缺失。
    （原实现把 books 配额用尽也计入 STAGE_FAIL → pipeline 永远 EXIT=1 → 门禁被判坏掉）
    """
    no, name, t0 = s
    dt = time.time() - t0
    TIMING.append((no, name, dt, ok, note))
    flag = '✅' if ok else ('⚠️' if soft else '🔴')
    print('  %s [%s] %-22s %6.1fs  %s' % (flag, no, name, dt, note))
    if not ok:
        if soft:
            SOFT_WARN.append('%s %s: %s' % (no, name, note))
        else:
            STAGE_FAIL.append('%s %s: %s' % (no, name, note))
    return dt


def run(cmd, timeout=600, quiet=True):
    _env = dict(os.environ, PYTHONIOENCODING='utf-8')  # 🔴2026-11-14 子进程 IO 强制 UTF-8（防 GBK 管道 emoji 崩溃）
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding='utf-8', errors='ignore', timeout=timeout, env=_env)
    return r.returncode, (r.stdout or ''), (r.stderr or '')


# ───────────────────────── Stage 0 归一化 ─────────────────────────
def stage00_context(kickoff=None):
    """🔴2026-11-01 P2: 时间上下文前置（time_guard·用户指令「模型的时间会漂移」）
    —— 确认当前北京时间/UTC + 比赛状态 + 数据新鲜度体检，防跨日指代错误/用过期数据判定
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import time_guard as TG
        TG.print_context(kickoff=kickoff, sweep_data=True)
    except Exception as e:
        print('⚪ time_guard 时间上下文不可用（三态·不阻断）: %s' % str(e)[:70])


def stage_img(paths, league=None, teams=None, kickoff=None):
    """Stage -1：竞彩截图 → 标准 txt（2026-11-01 用户要求「pipeline 直接吃图片」）

    内部调 image2txt.py（自动分流：赔率表走 glm-ocr 不花钱 / 赛事页回退 glm-4.6v），
    返回 (std_txt 路径, meta 字典)。meta 用于回填 teams/league/kickoff。
    🔴 识别失败 → 返回 (None, {}) → 主流程终止，绝不带病往下跑。
    """
    s = stage(-1, '图片识别 → 标准 txt')
    cmd = [PY, _sc('image2txt.py')] + list(paths)
    for k, v in (('--league', league), ('--teams', teams), ('--kickoff', kickoff)):
        if v:
            cmd += [k, v]
    rc, out, err = run(cmd, timeout=900)
    tail = (out or '')[-3000:]
    if tail:
        print(tail)
    m = re.search(r'标准 txt:\s*(\S+)', out or '')
    if not m:
        done(s, False, '未产出标准 txt（见上方 image2txt 输出）')
        return None, {}
    p = m.group(1).strip()
    # 🔴 image2txt 打印的是相对 workspace 的路径；pipeline 的 cwd 也是 workspace，
    #    但若从别处调用则需兜底按脚本位置（data/tmp 的上两级 = workspace 根）还原
    if not os.path.exists(p):
        cand = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), p)
        if os.path.exists(cand):
            p = cand
    meta = {}
    # meta.json 与 std.txt 同目录、同 stem（image2txt 写的 `<stem>.meta.json`）
    mp = os.path.splitext(p)[0]
    mp = mp[:-4] if mp.endswith('.std') else mp
    mp = mp + '.meta.json'
    if os.path.exists(mp):
        try:
            meta = json.load(open(mp, encoding='utf-8'))
        except Exception as e:
            print('   ⚠️ meta.json 解析失败: %s' % str(e)[:80])
    fill = meta.get('fill') or []
    ok_n = sum(1 for x in fill if x.get('state') == 'ok')
    miss = [x['slot'] for x in fill if x.get('state') == 'miss']
    note = '槽位 %d/%d 已填' % (ok_n, len(fill))
    if miss:
        note += ' · 🔴缺失: ' + ','.join(miss)
    done(s, bool(meta) and not miss, note)
    return p, meta


def stage0(txt):
    s = stage(0, 'txt 归一化')
    if os.path.basename(txt).startswith('std_'):
        done(s, True, '已是标准模板·跳过')
        return txt
    rc, out, err = run([PY, _sc('txt_normalize.py'), txt], timeout=120)
    m = re.search(r'标准模板已落盘:\s*(\S+)', out)
    if rc == 0 and m:
        p = m.group(1).strip()
        done(s, True, os.path.basename(p))
        return p
    done(s, False, (err or out)[-160:])
    return txt


# ───────────────────────── Stage 1 preflight ─────────────────────────
def stage1(std, a):
    s = stage(1, 'preflight(run_guard)')
    cmd = [PY, _sc('run_guard.py'), std, '--teams', a.teams, '--league', a.league,
           '--kickoff', a.kickoff]
    if a.event:
        cmd += ['--event', a.event]
    if a.eu:
        cmd += ['--eu', a.eu]
    if a.handi is not None:
        cmd += ['--handi', str(a.handi)]
    if a.home_water:
        cmd += ['--home_water', str(a.home_water)]
    if a.o25:
        cmd += ['--o25', str(a.o25)]
    if a.u25:
        cmd += ['--u25', str(a.u25)]
    rc, out, err = run(cmd, timeout=180)
    lacks = len(re.findall(r'需补|三态', out))
    done(s, rc == 0, '门禁段已出·标记需补/三态 %d 处' % lacks)
    return out


# ───────────────────────── Stage 2 数据采集（并行）─────────────────────────
def stage2(a):
    s = stage(2, '数据采集(books+伤停)')
    import threading
    res = {}

    def _books():
        if not (a.league and a.teams):
            res['books'] = (1, '缺 --league/--teams')
            return
        h, w = [x.strip() for x in a.teams.split(',')][:2]
        rc1, o1, _ = run([PY, _sc('the_odds_api_fetch.py'), 'current',
                          '--league', a.league, '--case', str(a.case or 'tmp')], timeout=180)
        rc2, o2, _ = run([PY, _sc('the_odds_api_fetch.py'), 'books',
                          '--case', str(a.case or 'tmp'), '--home', h, '--away', w,
                          '--league', a.league], timeout=180)
        mm = re.search(r'→\s*(\d+)\s*家机构', o2)
        if mm:
            res['books'] = (rc2, '%s 家' % mm.group(1))
            return
        # 🔴2026-10-31 批次6 修（「脚本跑完但没数据」= 假成功·与 _inj 同型）:
        #   本场实测 EXIT=0 但输出「❌ HTTP401 Usage quota reached → 三态」→ 仍显示 ✅
        #   → 输出含 ❌/三态 → 提升为软失败 rc=2（Stage2 标红·不假绿）
        # 🔴同时修显示: 原 (o2 or o1)[-100:] 从**任意位置**截断 → 「Le Havre vs …」
        #   显示成「re vs Paris SG」= 看起来像队名解析错（误导排查）
        _all = (o2 or '') + (o1 or '')
        _lines = [x.strip() for x in _all.splitlines() if x.strip()]
        _last = _lines[-1][:70] if _lines else '无输出'
        _bad = ('❌' in _all) or ('三态' in _all) or ('401' in _all) or \
               ('quota' in _all.lower()) or ('OUT_OF' in _all)
        _why = '配额用尽' if (('401' in _all) or ('quota' in _all.lower())) else ''
        res['books'] = (2 if _bad else rc2,
                        ('%s｜' % _why if _why else '') + _last)

    def _inj():
        if a.inj_list_h or a.inj_list_a or (a.inj_h and a.inj_a):
            res['inj'] = (0, '已显式提供')
            return

        # 🔴2026-11-01 新增：**先判源是否覆盖本联赛**（防「源不覆盖」被写成「(缺失)」）
        #   实证：Bzzoiro `/api/v2/leagues/` 共 50 个联赛，**无任何亚洲联赛**
        #         （仅中超/澳超/亚洲杯/世预赛AFC，无日职J1/J2、无韩职K League）
        #   → case307(韩职)/308(日职)/309(日职) 三场伤停缺失 = **源不覆盖**（合规三态）
        #   → 原标注只说「伤停影响分(缺失)」→ 审计无法区分「源不覆盖」与「漏查」
        #   🔴缩进注意：本函数体为 8 空格（首版误写 4 空格 → IndentationError → 已回滚重做）
        try:
            import bzzoiro_fetch as _BZC
            _lg = getattr(a, 'league', None) or getattr(a, 'lg', None)
            if _lg:
                _cov, _cmsg = _BZC.league_covered(_lg)
                if _cov is False:
                    print("     ⚪ %s" % _cmsg)
                    res['inj'] = (0, _cmsg)
                    return
                # 🔴V3.5.91 修（2026-11-03 case320 实证）: **联赛覆盖 ≠ 索引可定位**
                #   欧冠在 COVERED_LEAGUES（API 有数据）但不在 v1 events 索引（仅五大）
                #   → --teams 路径必然定位失败，却要扫完五大才报（实测等满 240s 超时）
                #   → 入口直接三态，省掉整段空等
                if _cov is True:
                    _icov, _imsg = _BZC.index_covered(_lg)
                    if _icov is False:
                        print("     ⚪ %s" % _imsg)
                        res['inj'] = (0, _imsg)
                        return
        except Exception:
            pass
        # 🔴2026-10-30 修 P0（**第二次同类事故**：case297/298 伤停全部误报「三态不可用」）
        #   原实现: 直接 `a.teams.split(',')` 传**中文**给 bzzoiro_fetch → Bzzoiro 索引为英文 → 恒「未定位」
        #   🔴同文件 L224 早有 `_bsd_teams()`（2026-10-28 修 BSD 时加的中→英转换），但 Stage2 未使用
        #   → 典型「修一处漏一处」：改了报错点，没横向排查同源的其它调用点
        #   修法: ① 先英后中双向尝试（各一次·保留尝试记录）② 全失败才算三态，且 **rc=2 软失败**
        #         （原 rc 只看脚本退出码 → 脚本正常跑完但没定位到队 = rc==0 = 假成功，Stage2 显示 ✅）
        raw_teams = a.teams
        en_teams = _bsd_teams(raw_teams)
        tried = []
        for label, tstr in (('英文', en_teams), ('中文原样', raw_teams)):
            rc, o, _ = run([PY, _sc('bzzoiro_fetch.py'), '--teams', tstr], timeout=240)
            n = len(re.findall(r'🏳', o))
            tried.append('%s[%s]→%d队' % (label, tstr, n))
            # 🔴2026-11-01 判据去 emoji 依赖（subprocess 捕获可能变 ?? → 假报未定位）
            n = len(re.findall(r"team_id=\d+", o)) or len(re.findall(r"缺阵/存疑", o)) \
                or len(re.findall(r"名单 \d+ 人", o))
            tried.append("%s[%s]→%d队" % (label, tstr, n))
            if n:
                # 🔴2026-11-01 修「查了不用」：解析缺阵名单 → 供 Stage4 传 --inj_list_*
                _POS = ("门将", "中后卫", "边后卫", "后腰", "中场", "前腰", "边锋", "前锋")
                _blk = re.split(r"team_id=\d+\)", o)
                _sides = []
                for _b in _blk[1:]:
                    _pl = []
                    for _ln in _b.splitlines():
                        if not ("injured" in _ln or "doubtful" in _ln or "suspended" in _ln):
                            continue
                        for _p in _POS:
                            if "→" + _p in _ln:
                                _pl.append(_p)
                                break
                    _sides.append(_pl)
                while len(_sides) < 2:
                    _sides.append([])
                res["inj_list_h"] = ";".join("%s,未知" % p for p in _sides[0])
                res["inj_list_a"] = ";".join("%s,未知" % p for p in _sides[1])
                res['inj'] = (0, '定位 %d 队（%s）｜ 缺阵 主%d/客%d 人'
                              % (n, ' ｜ '.join(tried), len(_sides[0]), len(_sides[1])))
                return
        res['inj_list_h'] = ''
        res['inj_list_a'] = ''
        res['inj'] = (2, '🔴两次尝试均未定位（%s）→ 须人工复核队名/源覆盖，**禁直接标三态**' % ' ｜ '.join(tried))

    th = [threading.Thread(target=_books), threading.Thread(target=_inj)]
    for t in th:
        t.start()
    for t in th:
        t.join()
    ok = True
    notes = []
    for k in ('books', 'inj'):
        rc, note = res.get(k, (1, '未执行'))
        notes.append('%s=%s' % (k, note))
        if rc != 0:
            ok = False
    # 🔴2026-10-31 批次6: 外部源三态（配额/未覆盖/未定位）→ soft（须 raw 留痕·不阻断）
    if not ok:
        notes.append('🔴 raw 必须写明本次已尝试 + 失败原因（三态·禁标「未执行」）')
    done(s, ok, ' | '.join(notes), soft=True)
    return res


# ───────────────────────── Stage 3 方向默认推导 ─────────────────────────
def stage3(a):
    """按铁律：默认覆盖＝最低赔率+次低赔率；skew≥200% 且最低赔<1.30 → 单押"""
    s = stage(3, '方向默认(step5-dirs)')
    # 🔴🔴2026-11-02 修真断链（用户「检验早上更新有无遗漏」实测抓出）：
    #   原实现「无 --eu → 不传(由 calc_all 三态)」→ calc_all **15 个块全部三态**：
    #   P10矩阵 / N23四要素 / **量级档V387** / N07b锚校验 / R11零封 / N26进球细分 /
    #   让球水位P1 / P12机构意图 / 置信度层 / 资金盘 / 半全场 …
    #   而 market_inputs **明明已能从 prestep 快照取到全档**（实测 coverage=100：
    #   ML 2.944/3.785/2.429 · 均衡档 0.25 · 大小球 22 档 · 波胆 24 档 · BTTS）
    #   → 白放着不用 = 「入口取到了、下游没接上」（与 P18 消费保障同类）。
    #   修：缺失时**自动回填** --eu/--handi/--home_water/--o25/--u25（显式传参仍优先·不覆盖）。
    if not (a.eu and a.handi is not None and a.o25):
        try:
            sys.path.insert(0, HERE)
            import market_inputs as _MI
            _tm = [x.strip() for x in (a.teams or '').split(',') if x.strip()]
            _r = _MI.resolve(home=(_tm[0] if _tm else None),
                             away=(_tm[-1] if len(_tm) > 1 else None),
                             event_id=a.event, league=a.league)
            _ml = _r.get('ml') or {}
            _auto = []
            if not a.eu and _ml.get('home') and _ml.get('draw') and _ml.get('away'):
                a.eu = '%s,%s,%s' % (_ml['home'], _ml['draw'], _ml['away'])
                _auto.append('--eu %s' % a.eu)
            if a.handi is None and _r.get('handi') is not None:
                a.handi = _r['handi']
                _auto.append('--handi %s' % a.handi)
            if not a.home_water and _r.get('ah_wh') is not None:
                a.home_water = _r['ah_wh']
                _auto.append('--home_water %s' % a.home_water)
            if not a.o25 and _r.get('o25') is not None:
                a.o25 = _r['o25']
                _auto.append('--o25 %s' % a.o25)
            if not a.u25 and _r.get('u25') is not None:
                a.u25 = _r['u25']
                _auto.append('--u25 %s' % a.u25)
            if _auto:
                print('   🔗 市场参数自动回填(来源 %s·coverage %s): %s'
                      % ((_r.get('src') or {}).get('ml'), _r.get('coverage'), ' · '.join(_auto)))
        except Exception as _e3:
            print('   ⚠️ 市场参数自动回填失败(三态·非流程失败): %s' % str(_e3)[:80])
    if a.step5_dirs:
        done(s, True, '显式指定: %s' % a.step5_dirs)
        return a.step5_dirs
    eu = (a.eu or '').split(',')
    if len(eu) != 3:
        done(s, True, '⚪无 --eu → 不传(由 calc_all 三态)')
        return None
    try:
        h, d, w = [float(x) for x in eu]
    except Exception:
        done(s, True, '⚪--eu 解析失败 → 不传')
        return None
    inv = [(1.0 / h, '主胜'), (1.0 / d, '平局'), (1.0 / w, '客胜')]
    tot = sum(v for v, _ in inv)
    p = sorted([(v / tot, n) for v, n in inv], reverse=True)
    p = [(v, n) for v, n in inv]
    p.sort(reverse=True)
    pmax, nmax = p[0]
    psec, nsec = p[1]
    skew = pmax / psec if psec else 0
    min_odd = min(h, d, w)
    # 🔴2026-10-28 实跑修：step5-dirs 是【锚池约束】（影响 N23 D_lock），**不是**输出覆盖字段。
    #   若把 2 向塞进去 → 池混入平局/次优谱系 → 主锚可能被拉离首选方向（case288 实测）。
    #   故：**只传首选方向**（池聚焦·锚定更准）；「是否需 2 向覆盖」只在报告提示，由模型在方向字段处理。
    dirs = nmax
    if skew >= 2.0 and min_odd < 1.30:
        cover = '可单押（skew %.0f%%≥200%% 且最低赔 %.2f<1.30）' % (skew * 100, min_odd)
    else:
        # 🔴2026-11-12 P-COVER-1 修正：第二向**默认=次低赔方向**（L2 铁律·227,495 场）
        #   原注释写「弱共识 → 平局」与 L2 冲突，case346 实证致方向❌（详见 signal_landing.simulate）
        #   诱主 / M1伤停仍热门 / Q2诱盘 / P12强诱盘 → 次方向 = **对手方**（P30 硬动作·优先）
        #   其余 → **最低+次低赔**；弱共识只强制「禁单押首选」= 必须两向，**不指定**平局
        #   本 Stage 只有赔率（calc 未跑）→ 只给铁律下限，具体由 Stage5 `signal_landing.simulate` 定。
        cover = ('🔴输出须 2 向覆盖（首选 %s ｜ 第二向：诱主/Q2/M1 → 对手方 · '
                 '其余 → **次低赔 %s**（L2 铁律 77.68%% > 最低+平局 76.51%%·'
                 '弱共识只要求两向·不指定平局）｜ skew %.0f%%·最低赔 %.2f）'
                 % (nmax, nsec, skew * 100, min_odd))
    done(s, True, '池锚定方向=%s ｜ %s' % (dirs, cover))
    return dirs


# ───────────────────────── Stage 4 calc_all（一次跑对）─────────────────────────
KEY_BLOCKS = [
    ('伤停影响分', r'伤停影响分'),
    ('HAF', r'HAF主客场'),
    ('P9数据桥', r'P9 竞彩噪音隔离'),
    ('胜平负/去水', r'【胜平负】'),
    # 2026-10-31 批次6: 实际输出「竞彩逐T形态: 时点不足(<3)·三态不触发」
    #   ⚠️不带 emoji（带  会被 _emoji_tolerant 反向要求必须有 emoji → 永不匹配）
    ('变动/形态', r'竞彩逐T形态'),
    ('D1背离', r'D1背离检测'),
    ('修正53', r'修正53预计算'),
    ('净胜候选', r'净胜档多档候选'),
    ('goal_bins', r'总进球档查表'),
    ('P12机构意图', r'【机构意图\(P12\)'),
    ('欧亚综合', r'方向\(欧亚综合\)'),
    # 2026-10-31 修假失败: 实际输出可能是「⚠️猫腻观察(...默认正常不降档...)」→ 须接受
    ('小概率管理', r'小概率管理|正常\(无盘面猫腻|猫腻观察|默认正常不降档'),
    ('资金盘', r'【资金盘信号总览'),
    ('P0-1分歧', r'【跨机构分歧'),
    ('R20平局', r'R20 平局温度计'),
    ('V6四象限', r'V6四象限'),
    ('N19三源', r'期望三源联动'),
    ('N21时序', r'欧亚盘时间序列\(N21\)'),
    ('双通道', r'【动态盘双通道判定】'),
    ('机构共识', r'机构共识层'),
    # 2026-10-31 批次6: BSD 三态降级（「 BSD 未定位到…」）也是合规输出，不是缺块
    ('BSD', r'BSD\s*(增强层|未定位|定位失败)'),
    ('market_inputs', r'市场数据链体检'),
    ('N22水位精读', r'大小球盘口水位精读'),
    ('N28 xG', r'xG 滚动均值'),
    ('N27攻防', r'球队双向攻防档案'),
    ('P10矩阵', r'市场矩阵\(P10\)'),
    ('P8纵向', r'P8纵向'),
    ('半场', r'半场方向\+比分候选'),
    ('N26进球细分', r'进球数细分\(N26'),
    ('联赛基准', r'联赛基准'),
    ('赛季漂移', r'赛季漂移校准'),
    ('必核清单', r'【必核清单·脚本生成'),
    ('live引擎', r'现场比分引擎'),
    ('N23四要素', r'\(D,M,T\) 四要素联合象限'),
    # 2026-10-31 修假失败: 平手盘无均衡档时输出「P1 让球水位不采用（三态）」→ 须接受
    ('让球水位P1', r'让球水位\(P1\)|让球水位不采用|无均衡档'),
    # 🔴2026-11-02 端到端审计实抓断点：calc_all 输出 3 行 R11 零封，但 KEY_BLOCKS 缺
    #   → raw 骨架不含 → audit_consumption 报「未消费 3」（必须 36 / 已消费 33）
    ('R11零封', r'R11 零封'),
    # 🔴2026-11-09 欧国联完善 P0-1（用户「马上欧国联开始了·完善模型」）：
    #   原 pipeline 只在 raw 骨架写一行「须调 nl_model.py」→ **靠模型记得调** = 「存在≠活跃」。
    #   实际 calc_all 早已跑过 NL（L1107 `if eu:` 内 + L1312 兜底段），pipeline 却不知道结果。
    #   → 加进 KEY_BLOCKS：NL 场自动内嵌 R1-R10 真实数值；非 NL 场自动内嵌「⚪不触发」三态。
    ('NL欧国联', r'欧国联[^\n]{0,10}子模型|══════ 欧国联'),
    # 🔴2026-11-09 V3.5.94 总分总架构（用户指令「隔离子模型·主模型通用·接口一致·防止不同比赛相互串」）：
    #   calc_all 新增「子模型聚合（总分总·总②）」块（由 match_context.fmt_aggregate 输出）
    #   → pipeline 必须切片进 raw 骨架，否则「聚合结果算了但没进 raw」= 又一处「存在≠活跃」。
    #   块内含：生效子模型 / 方向校正(pp) / 置信度档 / 量级球 / 锚提示 / 规则命中 / L2 锁 / 冲突 / 🔒越界拦截
    # 🔴2026-11-11 P-TOOL-2 判据加宽（case344 实证·假失败）：
    #   原判据只认「子模型聚合（总分总」→ 而 calc_all 实际有 **3 种**真实文案：
    #     a) match_context.L443（有适用子模型）→ `🔴 子模型聚合（总分总·总②）: 生效 …`
    #     b) match_context.L441（无适用子模型）→ `⚪ 子模型聚合: 无适用子模型（三态: none）`
    #     c) calc_all.L1186（异常降级）        → `⚪ 子模型聚合(总分总): 三态（…）`
    #   → b/c 两种恒不匹配 → **无适用子模型的场次（日联赛杯/英锦赛等超域）每次都报「❌缺块」**
    #   → 与 P42「有块却报缺」同一型（判据写窄 → 假失败 → 人会开始忽略闸门）
    ('子模型聚合', r'子模型聚合（总分总|子模型聚合\(总分总\)|子模型聚合[:：]\s*(无适用|三态)'),
    ('锚校验N07b', r'锚-市场/期望复校验'),
    # 🔴V3.5.87 量级确定层（方法二·先定量级再选比分）—— 用户 2026-11-02 指令
    #   配套链路：calc_all 生成 → joint_solver 透传 → anchor_select ×档权重 → pipeline 切片
    # 🔴V3.5.88(2026-11-03 分布驱动重写)：文案由「量级档确定(V3.5.87」改为「量级分布(V3.5.88」
    #   → **切片正则必须兼容两版**，否则 raw 骨架该块为空 = 算出来但没进 raw（伪消费）
    ('量级档V387', r'量级(?:档确定|分布)\(V3\.5\.(?:87|88)'),
    ('置信度层', r'置信度层建议'),
    # 🔴 2026-11-03 欧战六项核查表（rule51-70）脚本化——
    #   实跑实抓: 欧冠场原只有「C10 Step3 场景44/45/46(+欧战六项核查表)」一行**必核清单文字**，
    #   脚本层零输出 → 模型漏调 SL-europe-db 就缺 44A/44B/44C+定价偏差+亚盘铁则 六项而不自知
    ('欧战六项核查', r'欧战六项核查表'),
    ('N24欧冠校准', r'欧冠(正赛)?大球校准\(N24'),
    # 🔴 2026-11-03 V3.5.90 厚尾三线索——实跑实抓:
    #   calc_all 每场打印「厚尾三线索(V3.5.90)」，但 pipeline 四处零命中
    #   → raw 不含该块 + 闸门不查 = 伪消费（同 V3.5.88 第1个缺陷型）
    ('厚尾三线索', r'厚尾三线索\(V3\.5\.9[09]'),
]


def _bsd_teams(cn_teams):
    """🔴2026-10-28 实跑修：BSD（Bzzoiro）只认英文队名 → 中文必须转英文，否则定位失败→BSD 整块缺失"""
    try:
        sys.path.insert(0, SC)
        from snapshot_save import cn2en_list
        out = []
        for x in [t.strip() for t in cn_teams.split(',') if t.strip()]:
            cands = cn2en_list(x) or []
            out.append(cands[0] if cands else x)
        print('  [bsd] 队名中→英: %s → %s' % (cn_teams, ','.join(out)))
        return ','.join(out)
    except Exception as e:
        print('  [bsd] ⚠️队名转换失败(%s) → 原样传' % str(e)[:60])
        return cn_teams


# 🔴2026-10-28 实跑修：KEY_BLOCKS 正则空格容错
#   实际输出存在「🔵 BSD 增强层」（emoji 后有空格）与「🔴市场矩阵」（无空格）两种写法，
#   而原 pattern 是手写的 → 空格差异即误报「缺块」。这里给**每个 emoji 后统一插入 \s***。
KEY_BLOCKS = [(n, re.sub(r'([\U0001F300-\U0001FAFF\u26A0\u26AA\u26AB\u2B50\u274C\u2705])[\s\uFE0F]*',
                         lambda m: m.group(1) + r'\s*', p))
              for n, p in KEY_BLOCKS]

# 🔴2026-10-30 修「缺块」误报（case294 实跑抓）: 三态行用 ⚪/🔴 开头（「⚪球队双向攻防档案(N27)」
#   「⚪ 联赛基准 / 赛季漂移校准」「🔴 BSD 未定位到…」），而 pattern 写死单一 emoji → 三态也判缺块。
#   AGENTS 铁律: 三态标注 = 合规输出（没数据也要说），≠ 缺失 → 状态 emoji 前缀统一为 [🔴🔵⚪]。
_STATE_EMOJI = ('🔴', '🔵', '⚪')


def _emoji_tolerant(p):
    if p[:1] in _STATE_EMOJI:
        return r'[🔴🔵⚪]\s*' + re.sub(r'^[🔴🔵⚪]\s*', '', p)
    return p


KEY_BLOCKS = [(n, _emoji_tolerant(p)) for n, p in KEY_BLOCKS]


def stage4(std, a, dirs, pre=None):
    s = stage(4, 'calc_all(一次跑全参数)')
    cmd = [PY, _sc('calc_all.py'), std, 'seriea' if a.league in ('意甲', 'seriea') else (a.league or 'seriea'),
           # 🔴2026-11-01 去掉 --no-time：audit_steps S00 只读 calc 输出 → 不传给 calc 就判「遗漏」
        '--net', '--kickoff', a.kickoff, '--teams', a.teams, '--snapshot',
        # 🔴2026-11-01 透传 Bzzoiro 缺阵名单（否则 calc_all 判「伤停缺失」= 查了不用）
        *(['--inj_list_h', pre['inj_list_h']] if (pre or {}).get('inj_list_h') else []),
        *(['--inj_list_a', pre['inj_list_a']] if (pre or {}).get('inj_list_a') else []),
           '--league', 'seriea' if a.league in ('意甲', 'seriea') else (a.league or 'seriea')]
    if a.skip_net:
        cmd.remove('--net')
    for k, v in (('--event', a.event), ('--eu', a.eu), ('--handi', a.handi),
                 ('--home_water', a.home_water), ('--o25', a.o25), ('--u25', a.u25),
                 ('--inj_list_h', a.inj_list_h), ('--inj_list_a', a.inj_list_a),
                 ('--inj_h', a.inj_h), ('--inj_a', a.inj_a),
                 ('--draw-score', a.draw_score), ('--bsd-teams', _bsd_teams(a.teams)),
                 ('--step5-dirs', dirs),
                 ('--ucl-round', getattr(a, 'ucl_round', None))):
        if v not in (None, ''):
            cmd += [k, str(v)]
    rc, out, err = run(cmd, timeout=900)
    p = os.path.join(ROOT, 'data', 'tmp', '_pipe_calc_%s.txt' % (a.case or 'tmp'))
    open(p, 'w', encoding='utf-8').write(out)
    lacks = [n for n, pat in KEY_BLOCKS if not re.search(pat, out)]
    ok = rc == 0 and not lacks
    done(s, ok, '%d 行 → %s%s' % (out.count('\n') + 1, os.path.basename(p),
                                  ('  ❌缺块: ' + ','.join(lacks)) if lacks else ''))
    return out, p


# ───────────────────────── Stage 5 raw 骨架 ─────────────────────────
def stage5(a, std, calc_out, calc_path, inj_msg=None):
    s = stage(5, 'raw 骨架生成')
    if a.no_skeleton:
        done(s, True, '按参数跳过')
        return None
    cid = a.case or 'tmp'
    raw_p = 'data/case-library/raw/case%s_%s.md' % (cid, a.teams.replace(',', 'vs'))
    lines = calc_out.split('\n')
    # 按 KEY_BLOCKS 切片：命中标记起，到下一个块标记前
    sections = {}
    idx = []
    for i, ln in enumerate(lines):
        for name, pat in KEY_BLOCKS:
            if re.search(pat, ln):
                idx.append((i, name))
                break
    idx.sort()
    for j, (i, name) in enumerate(idx):
        end = idx[j + 1][0] if j + 1 < len(idx) else min(i + 40, len(lines))
        sections.setdefault(name, []).extend(lines[i:end])

    def blk(name):
        v = sections.get(name)
        if not v:
            return '（⚪ 未在 calc_all 输出中找到该块 → 三态·需手查）'
        return '\n'.join('  ' + x for x in v[:26])

    def _now_txt():
        """🔴2026-11-03 端到端实跑抓：raw 骨架原写「生成时间」→ TT1 闸门要「分析时间」→ 恒不过
        且取时间须走 time_guard 单一入口（禁 time.strftime 自算·时间漂移铁律）"""
        try:
            from time_guard import now_bj
            return now_bj().strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return time.strftime('%Y-%m-%d %H:%M:%S')

    buf = []
    buf.append('# case%s %s · %s\n' % (cid, a.teams.replace(',', ' vs '), a.kickoff))
    buf.append('> 🔴 **本文件由 `pipeline.py` 生成骨架**：所有【程序已填】块为 calc_all 实跑数值原样内嵌；'
               '模型只需在每个【空位】处写结论（附数值依据）。禁删块、禁空置。\n')
    buf.append('> 🔴 **分析时间：%s**（time_guard 单一入口·程序计算·禁凭记忆）｜ 骨架生成：%s ｜ '
               'calc_all 原始输出：`%s`\n' % (
                   _now_txt(), time.strftime('%Y-%m-%d %H:%M:%S'), calc_path))
    buf.append('\n## 一、竞彩全文（源A）\n\n```\n%s\n```\n' % open(std, encoding='utf-8').read().strip())
    buf.append('\n## 二、欧盘 + 亚盘（源B）\n\n### 【程序已填】N21 欧亚盘时间序列\n\n```\n%s\n```\n' % blk('N21时序'))
    buf.append('\n### 【程序已填】机构共识层（the-odds-api）\n\n```\n%s\n```\n' % blk('机构共识'))
    buf.append('\n### 【程序已填】资金盘 P0-1/P0-2/P0-3\n\n```\n%s\n%s\n```\n' % (blk('资金盘'), blk('P0-1分歧')))
    buf.append('\n### 【程序已填】双通道四象限 + P8 纵向\n\n```\n%s\n%s\n```\n' % (blk('双通道'), blk('P8纵向')))
    buf.append('\n### 【程序已填】BSD 增强层\n\n```\n%s\n```\n' % blk('BSD'))
    buf.append('\n### 【程序已填】大小球水位精读（N22·六源 λ）\n\n```\n%s\n```\n' % blk('N22水位精读'))
    buf.append('\n### 【待模型判断】本层小结：盘面意图 = ______（依据：上列哪些数值？）\n')
    buf.append('\n## 三、场景（Step3/3.5/4）\n\n### 【程序已填】HAF 主客场 + P9 数据桥\n\n```\n%s\n%s\n```\n' % (blk('HAF'), blk('P9数据桥')))
    buf.append('\n### 【程序已填】联赛基准 + 赛季漂移 + 子模型输入\n\n```\n%s\n%s\n```\n' % (blk('联赛基准'), blk('赛季漂移')))
    buf.append('\n### 【待模型判断】Step4.5 子模型 R1-R20 逐条：______（触发/不触发+数值）\n')
    # 🔴2026-11-04 修（case324 实证·P31 同型第 3 次）: Stage2 的伤停三态实证**必须进 raw**
    #   原 stage5 只从 calc_all 切片 → calc_all 不知道「索引覆盖预判」→ raw 只有「未提供清单」
    #   → audit_steps S02 判 MISSING → 每场靠模型手写「索引不覆盖」才过（假通过）
    _inj_add = ''
    if inj_msg:
        _inj_add = ('\n\n🔴 **Stage2 伤停实证（pipeline 实测·非未执行）**\n\n'
                    '```\n  %s\n```\n\n'
                    '→ 该三态为「已尝试」结果（Bzzoiro 索引不覆盖本联赛/未定位到队），'
                    '**非流程遗漏**；铁则32 位置级影响分本场不参与判定。\n'
                    % str(inj_msg)[:400])
    buf.append('\n## 四、基本面\n\n### 【程序已填】伤停（Bzzoiro·位置级）\n\n```\n%s\n```\n%s'
               % (blk('伤停影响分'), _inj_add))
    buf.append('\n### 【程序已填】N27 双向攻防 + N28 xG\n\n```\n%s\n%s\n```\n' % (blk('N27攻防'), blk('N28 xG')))
# 🔴 2026-11-03 欧战六项核查表（rule51-70）+ N24 欧冠校准——
#   实跑实抓: 欧冠场原只有「C10 必核清单」一行文字，脚本层零输出。
#   现 calc_all 已脚本化六项判定 → raw 必须含该块（否则模型仍可静默漏项）
    if blk('欧战六项核查') or blk('N24欧冠校准'):
        buf.append('\n### 【程序已填】欧战六项核查表 + N24 欧冠校准\n\n```\n%s\n%s\n```\n'
                   '\n> 【待模型判断】六项逐条：哪项真触发？>>该项对本场方向/比分的具体影响？'

                   ' ⚪ 项必须写「不适用的理由」（禁只留ω）；N24 校准后 λ/E 须与锚-期望校验同口径\n' %
                   (blk('欧战六项核查'), blk('N24欧冠校准')))
    # 🔴 2026-11-03 V3.5.90 厚尾三线索块（观察期标注级）
    if blk('厚尾三线索'):
        buf.append('\n### 【程序已填】厚尾三线索(V3.5.90·premium 单条判据)\n\n```\n%s\n```\n'
                   '\n> 【待模型判断】厚尾标注如何处理？观察期 `_TAIL_ACT=False` 不动锚'
                   '——若判「厚尾/强厚尾」须写「为何本场仍不调锚」；若判「正常」须写盘面依据\n' % blk('厚尾三线索'))
    buf.append('\n### 【待模型判断】H2H 双源（Matches.csv + 竞彩特征）：______\n')
    buf.append('\n### 【待模型判断】修正26 ABCDE 五要素：______\n')
    buf.append('\n## 五、结论\n\n')
    buf.append('| 项 | 判定 |\n|:--|:--|\n')
    buf.append('| **方向** | 【待模型判断】 |\n')
    # 🔴2026-11-01 R02 要求「置信度层 + HIGH/MID/LOW」**连写**（原只写「详见下方」→ 判缺）
    _cl_lv = None
    try:
        _cl_blk = blk('置信度层') or ''
        _mm_cl = re.search(r'调整后\s*\*{0,2}([A-Z][A-Z\-]*)', _cl_blk)
        if _mm_cl:
            _cl_lv = _mm_cl.group(1)
    except Exception:
        _cl_lv = None
    buf.append('| 置信度层 | %s |\n'
               % (('**%s**（程序预填·模型可改须给理由）' % _cl_lv) if _cl_lv
                  else '【待模型判断】HIGH/MID/MID-HIGH/MID-LOW/LOW'))
    buf.append('| **量级** | 【待模型判断】见下方 N22/N26 |\n')
    buf.append('| **主锚 / 次锚** | 【待模型判断】见下方 P10/N23 交集池 |\n')
    buf.append('| **锚可信度** | 【待模型判断】见下方 N23 |\n')
    buf.append('| **半场** | 【待模型判断】见下方「半场」 |\n')
    buf.append('| **停止分支** | 【待模型判断】 |\n\n')
    # 🔴V3.5.87 量级确定层（方法二·先定量级再选比分）—— 必须放在 P10/锚定**之前**
    #   因果顺序：市场三源+六档 → 定量级档 → 档内用信号筛比分 → 定锚
    buf.append('\n### 【程序已填】🔴量级档确定（V3.5.87·方法二·先定量级再选比分）\n\n'
               '```\n%s\n```\n'
               '【待模型判断】量级档合理性：______（档中心 X 球 vs 本场盘口线/伤停/联赛特性是否一致？'
               '档外比分是否有强信号需保留？）\n' % blk('量级档V387'))
    buf.append('### 【程序已填】P10 市场矩阵（三源·E0 主排序）\n\n```\n%s\n```\n' % blk('P10矩阵'))
    buf.append('\n### 【程序已填】N23 四要素 + 交集池 + 锚校验\n\n```\n%s\n```\n' % blk('N23四要素'))
    # 🔴2026-11-02 修：字符串里的 '≥30%' / '≥60%' 中的 `%` 会被 `%` 格式化当占位符
    #   → `TypeError: not enough arguments for format string` → 全用 %% 转义（或改用 .format 外的拼接）
    buf.append('\n### 【程序已填】R11 零封/BTTS 直盘（单队被零封 + 双方进球 + rho）\n\n'
               '```\n%s\n```\n'
               '【待模型判断】零封谱系采信：______（客被零封≥30%% → 零封比分进前列；'
               'BTTS≥60%% → 禁纯零封比分；rho>+3pp 对攻）\n' % blk('R11零封'))
    buf.append('\n### 【程序已填】锚-市场/期望复校验（N07b/N18b）\n\n```\n%s\n```\n' % blk('锚校验N07b'))
    buf.append('\n### 【程序已填】置信度层建议 + 单押准入\n\n```\n%s\n```\n' % blk('置信度层'))
    buf.append('\n### 【程序已填】半场方向 + 比分候选\n\n```\n%s\n```\n' % blk('半场'))
    buf.append('\n## 六、硬核层 12 项\n\n### 【程序已填】去水/校准/skew/凯利/形态/D1/修正53/净胜/goal_bins\n\n```\n%s\n%s\n%s\n%s\n%s\n%s\n```\n' % (
        blk('胜平负/去水'), blk('变动/形态'), blk('D1背离'), blk('修正53'), blk('净胜候选'), blk('goal_bins')))
    buf.append('\n### 【程序已填】欧亚综合 + P12 + 小概率管理\n\n```\n%s\n%s\n%s\n```\n' % (
        blk('欧亚综合'), blk('P12机构意图'), blk('小概率管理')))
    buf.append('\n### 【程序已填】R20 平局温度 + V6 四象限 + N19 三源\n\n```\n%s\n%s\n%s\n```\n' % (
        blk('R20平局'), blk('V6四象限'), blk('N19三源')))
    buf.append('\n### 【待模型判断】12 项逐项结论（每项数值 + 判定）：______\n')
    buf.append('\n## 七、xG 深度判定\n\n### 【程序已填】N28 xG + 三源期望\n\n```\n%s\n%s\n```\n' % (blk('N28 xG'), blk('N19三源')))
    buf.append('\n### 【待模型判断】xG 与市场一致性：______\n')
    buf.append('\n## 八、执行留痕\n\n')
    buf.append('### ① V2 诱阻盘四步\n\n```\n%s\n```\n【待模型判断】四步逐条结论：______\n' % blk('变动/形态'))
    buf.append('\n### ② Step7 市场矩阵 + 交集池 + 让球水位 P1\n\n```\n%s\n%s\n%s\n```\n' % (
        blk('P10矩阵'), blk('N23四要素'), blk('让球水位P1')))
    buf.append('\n### ③ N26 进球数细分（低分出口按档选）\n\n```\n%s\n```\n【待模型判断】低分出口取哪档：______\n' % blk('N26进球细分'))
    buf.append('\n### ④ 必核清单（脚本生成·逐项打勾）\n\n```\n%s\n```\n' % blk('必核清单'))
    buf.append('\n### ⑤ live 引擎现场比分\n\n```\n%s\n```\n' % blk('live引擎'))
    buf.append('\n### ⑥ 数据源健康（X/6）\n\n【待模型判断】______（news 已按 P20 停用）\n')
    buf.append('\n### ⑦ Step9 自检 22 项\n\n【待模型判断】逐项 1-22 + 证据：______\n')
    buf.append('\n### ⑧ 学习成果 / 融合判定\n\n【待模型判断】______\n')
    buf.append('\n### ⑨ 锚-量级一致性 + 锚-六项校验\n\n【待模型判断】逐项：______\n')
    buf.append('\n### ⑩ 置信度合成留痕\n\n【待模型判断】基础层/升降档逐条：______\n')

    # 🔴2026-10-29 P30 信号落地核查（程序预填表·模型只填处置与影响）
    try:
        sys.path.insert(0, SC)
        import signal_landing as _SL
        _sigs = _SL.signals(calc_out)
        _sim = _SL.simulate(calc_out, _sigs)
        buf.append('\n## 信号落地核查（P30·2026-10-29 强制）\n')
        buf.append('> 🔴 每场「预测方向」**最多 2 向**（列 3 向 = 违规）。'
                   '下表「信号/等级/强制动作」由程序预填，模型须填「本场处置」与「对方向/锚影响」。\n')
        buf.append('| # | 信号 | 等级 | 强制动作 | 本场处置 | 对方向/锚影响 |')
        buf.append('|:-:|:--|:-:|:--|:--|:--|')
        for _i, _sg in enumerate(_sigs, 1):
            buf.append('| %d | %s | %s | %s | ______ | ______ |'
                       % (_i, _sg['name'], _sg['level'], _sg['action']))
        if not _sigs:
            buf.append('| 1 | （本场无 H/M 级信号） | — | 无需处置 | 无需处置 | 方向=______ ｜ 锚=______ |')
        buf.append('')
        buf.append('**应覆盖方向（程序推导·≤2向）**: %s ｜ 第二向依据: %s'
                   % ('＋'.join(_sim['dirs']) or '—', _sim['second_why'] or '不需要第二向'))
        # 🔴2026-11-01 预测方向**程序预填**（原留 ______ → 模型漏填 = 覆盖不足·case304/306 实证）
        _cover_pre = ('＋'.join(_sim.get('dirs') or []) or '______')
        # 🔴2026-11-01 output_checker N03/N17 兜底：非弱共识 / 非欧国联须**显式三态**
        try:
            _eu_o = [float(x) for x in (a.eu or '').split(',')] if getattr(a, 'eu', None) else []
        except Exception:
            _eu_o = []
        if len(_eu_o) == 3:
            _iv = sorted([1.0 / _eu_o[0], 1.0 / _eu_o[1], 1.0 / _eu_o[2]], reverse=True)
            _sk_o = (_iv[0] / _iv[1]) if _iv[1] else 0
            if _sk_o >= 1.5:
                buf.append('**弱共识场平局并列声明**: 不触发（skew **%.0f%%** ≥150%% → '
                           '非弱共识·不强制两向覆盖）\n' % (_sk_o * 100))
            else:
                buf.append('**弱共识场平局并列声明**: 🔴触发「两向覆盖」（skew **%.0f%%** <150%% → '
                           '**禁单押首选**·第二向取**次低赔方向**（L2 铁律 77.68%%>最低+平局 76.51%%）；'
                           '若坚持用平局作第二向，须在 raw 说明理由·check_luopan P-COVER-1 会核）\n'
                           % (_sk_o * 100))
        else:
            buf.append('**弱共识场平局并列声明**: ⚪三态（无 --eu → 不可判）\n')
        _lg_o = str(getattr(a, 'league', '') or '')
        _is_nl = any(k in _lg_o.lower() for k in ('nations', '欧国联', 'nl'))
        if _is_nl:
            # 🔴2026-11-09 欧国联完善 P0-1：原只写「须调 nl_model.py」→ 靠模型记得调 = 存在≠活跃。
            #   现从 calc_out 真实切片（KEY_BLOCKS 'NL欧国联'）→ 数值自动落进 raw；
            #   若 calc 未输出有效块 → 显式标红要求手跑（禁静默降级）。
            _nl_sec = blk('NL欧国联')
            if ('未在 calc_all 输出中找到' in _nl_sec) or ('非欧国联' in _nl_sec):
                buf.append('**欧国联/国家队子模型**: 🔴 **calc 未输出有效 NL 块**（league=%s）→ '
                           '须手工跑 `python nl_model.py --league-id 5 --home-team <主> '
                           '--away-team <客> --md <轮次> --o-h X --o-d Y --o-a Z` 并把 R1-R10 抄进来【待模型判断】\n'
                           % _lg_o)
            else:
                buf.append('**欧国联/国家队子模型（【程序已填】·R1-R10 真实数值·来自 calc_all）**:\n'
                           '%s\n'
                           '【待模型判断】R1-R10 逐条消费结论（哪条真触发·对方向/锚/置信度的具体影响·'
                           '未触发项写「不适用的理由」）：______\n' % _nl_sec)
        else:
            buf.append('**欧国联/国家队子模型**: ⚪不触发（league=%s 非欧国联·'
                       'R1-R10 均不适用·三态合规）\n' % (_lg_o or '?'))
        buf.append('**预测方向（程序预填）**: **%s**  '
                   '（🔴依据: %s ｜ 最多 2 向·第三方向只进概率表 ｜ '
                   '模型可改但须给理由，改了 check_luopan 会按「应覆盖方向」复核）\n'
                   % (_cover_pre, _sim.get('second_why') or '首选方向即可'))
        # 🔴P-COVER-1 终局校验（2026-11-12·case346 事故）
        #   calc_all 的 --step5-dirs 是【锚池约束】只传首选方向（L364 `dirs = nmax`）
        #   → 那里 P-COVER-1 恒判 SINGLE（单押·非违规）→ **真正校验必须在此**
        #   用 signal_landing 推导的**两向** + 欧盘赔率复核「默认覆盖」是否被违规替换
        try:
            import default_cover as _dvc_p
            _cvp = _dvc_p.check(_eu_o, _sim.get('dirs') or [])
            buf.append('%s\n' % _dvc_p.fmt(_cvp))
            if _dvc_p.is_violation(_cvp):
                buf.append('🔴 **默认覆盖违规** → 须在 raw 说明理由（Q2诱盘 / 诱主 / M1伤停仍热门 '
                           '等硬动作），或改为建议覆盖 **%s**\n'
                           % ' + '.join(_cvp.get('suggestion') or []))
        except Exception as _ecvp:
            buf.append('⚪ 默认覆盖校验三态: %s\n' % _ecvp)
    except Exception as _e30:
        buf.append('\n## 信号落地核查（P30）\n\n⚪程序预填失败（%s）→ 须手工跑 `python signal_landing.py --calc <calc输出> --raw auto` 后填表\n' % _e30)

    os.makedirs('data/case-library/raw', exist_ok=True)
    open(raw_p, 'w', encoding='utf-8').write('\n'.join(buf))
    filled = sum(1 for x in buf if '【程序已填】' in x)
    todo = sum(1 for x in buf if '【待模型判断】' in x)
    done(s, True, '%s ｜ 程序已填 %d 块 · 待判断 %d 处' % (os.path.basename(raw_p), filled, todo))
    return raw_p


# ───────────────────────── Stage 6 消费审计 ─────────────────────────
def stage6(calc_path, raw_p):
    s = stage(6, '消费审计')
    if not raw_p:
        done(s, True, '⚪无 raw → 跳过')
        return
    rc, out, err = run([PY, _sc('audit_consumption.py'), calc_path, raw_p], timeout=180)
    mm = re.search(r'必须 (\d+) ｜ ✅(\d+) ｜ 🔴(\d+)', out)
    if mm:
        must, ok, miss = int(mm.group(1)), int(mm.group(2)), int(mm.group(3))
        done(s, miss == 0, '必须 %d / 已消费 %d / 未消费 %d' % (must, ok, miss))
    else:
        done(s, rc == 0, (out or err)[-120:])
    # 🔴2026-10-30 P33 步骤审计（用户最后通牒·20 步逐项·case299+ 硬门禁）
    try:
        _cid6 = re.sub(r'\D', '', os.path.basename(raw_p).split('_')[0])
        rc6, o6, _ = run([PY, _sc('audit_steps.py'), '--case', _cid6,
                          '--calc', calc_path], timeout=120)
        mm6 = re.search(r'PASS (\d+) ｜ ⚪ TRISTATE (\d+) ｜ ❌ MISSING (\d+)', o6)
        if mm6:
            p6, t6, m6 = mm6.groups()
            hm6 = re.findall(r'高影响遗漏 \d+ 项：([^\n]+)', o6)
            note6 = 'PASS %s / 三态 %s / 遗漏 %s' % (p6, t6, m6)
            if hm6:
                note6 += ' ｜ 🔴高影响: ' + hm6[0][:80]
            print('  📋 步骤审计(case%s): %s' % (_cid6, note6))
        else:
            print('  ⚪ 步骤审计: 未解析到汇总行')
    except Exception as _e6:
        print('  ⚪ 步骤审计: %s（三态）' % type(_e6).__name__)
    # 🔴2026-10-29 P30: 信号落地 + 最多两向（骨架阶段模型未填 → 显示待填数，非失败）
    try:
        sys.path.insert(0, SC)
        import signal_landing as _SL
        _cc = open(calc_path, encoding='utf-8', errors='ignore').read()
        _rw = open(raw_p, encoding='utf-8', errors='ignore').read()
        _sigs = _SL.signals(_cc)
        _ok, _bad = _SL.check(_rw, _sigs)
        _two, _three = _SL.max_two_check(_rw)
        print('  · P30 信号落地: 触发 %d 条 ｜ 已处置 %d ｜ 待填 %d ｜ 两向校验 %s'
              % (len(_sigs), len(_ok), len(_bad), '✅≤2向' if _two else '❌检出3向'))
        if _bad:
            print('    待填: %s' % '、'.join(x[0]['name'] for x in _bad[:6]))
    except Exception as _e6:
        print('  ⚪P30 校验跳过: %s' % _e6)


# ───────────────────────── main ─────────────────────────
def do_verify(case):
    """🔴P42（2026-10-30）: raw 填完后**一键全量校验**（七道闸门）
       用法: python pipeline.py --verify 997
       检查: ① raw 无残留待填 ② output_checker ③ check_luopan 七节 ④ audit_steps 20步\n      ⑤ audit_judgment 判定层（S3/3.5/4/4.5/4.6/7.5/9） ⑥ audit_chain 8 条传导链
    """
    import glob as _gl
    print('=' * 78)
    print('pipeline --verify case%s（七道闸门）' % case)
    print('=' * 78)
    raws = _gl.glob('data/case-library/raw/case%s*.md' % case)
    if not raws:
        print('  ❌ 未找到 raw: data/case-library/raw/case%s*.md' % case)
        return 1
    raw_p = raws[0]
    txt = io.open(raw_p, encoding='utf-8', errors='replace').read()
    ok_all = True

    # ① 残留待填
    n_pend = txt.count('待模型判断')
    if n_pend:
        print('  🔴 [1/7] 残留「待模型判断」%d 处 → 须填完' % n_pend)
        ok_all = False
    else:
        print('  ✅ [1/7] 无残留待填')

    # ② output_checker
    rc, o, _ = run([PY, _sc('output_checker.py'), raw_p], timeout=180)
    good = '全部必填块通过' in (o or '')
    print('  %s [2/7] output_checker: %s'
          % ('✅' if good else '🔴', '全部通过' if good else (o or '')[-160:].replace(chr(10), ' ')))
    ok_all &= good

    # ③ check_luopan（🔴P42-fix: 它只遍历 CSV 里的 case → 未入库则跳过而非失败）
    _csv_p = 'data/case-library/实战案例.csv'
    _in_csv = False
    try:
        _ct = io.open(_csv_p, encoding='utf-8-sig', errors='replace').read()
        _in_csv = bool(re.search(r'^%s,' % re.escape(str(case)), _ct, re.M))
    except Exception:
        pass
    if not _in_csv:
        print('  ⚪ [3/7] check_luopan: case 未写入 CSV（先 case_write add）→ 跳过（三态）')
    else:
        rc, o, _ = run([PY, _sc('check_luopan.py'), str(case)], timeout=180)
        good = (rc == 0)
        print('  %s [3/7] check_luopan: %s'
              % ('✅' if good else '🔴', '通过' if good else (o or '')[-200:].replace(chr(10), ' ')))
        ok_all &= good

    # ④ audit_steps（20 步）
    calc = os.path.join(ROOT, 'data', 'tmp', '_pipe_calc_%s.txt' % case)
    if os.path.exists(calc):
        rc, o, _ = run([PY, _sc('audit_steps.py'), '--case', str(case), '--calc', calc],
                       timeout=180)
        mm = re.search(r'PASS (\d+) ｜ ⚪ TRISTATE (\d+) ｜ ❌ MISSING (\d+)', o or '')
        if mm:
            p, tr, ms = mm.groups()
            print('  %s [4/7] audit_steps: PASS %s / 三态 %s / 遗漏 %s'
                  % ('✅' if ms == '0' else '🔴', p, tr, ms))
            ok_all &= (ms == '0')
        else:
            print('  ⚪ [4/7] audit_steps: 未解析（三态）')
    else:
        print('  ⚪ [4/7] audit_steps: 无 calc 输出 → 跳过（三态）')

    # ⑤ audit_judgment（🔴2026-11-01 补 7 个原无审计的步骤：S3/3.5/4/4.5/4.6/7.5/9）
    #    判据区分 calc 层 vs raw 层：「calc 有但 raw 没写」= 算了没写 = 模型未消费
    _rc5, _o5, _ = run([PY, _sc('audit_judgment.py'),
                        '--calc', calc if os.path.exists(calc) else '',
                        '--raw', raw_p], timeout=180)
    _m5 = re.search(r'✅ 落地 (\d+) ｜ 🔴 算了没写 (\d+) ｜ ⚪ 三态 (\d+) ｜ ❌ 遗漏 (\d+)',
                    _o5 or '')
    if _m5:
        _p5, _u5, _t5, _s5 = _m5.groups()
        _ok5 = (_u5 == '0' and _s5 == '0')
        print('  %s [5/7] audit_judgment(判定层): 落地 %s / 算了没写 %s / 三态 %s / 遗漏 %s'
              % ('✅' if _ok5 else '🔴', _p5, _u5, _t5, _s5))
        if not _ok5:
            for _ln in (_o5 or '').splitlines():
                if '算了没写' in _ln or 'S4.5' in _ln or 'S9 ' in _ln or 'S4.6' in _ln:
                    if _ln.strip().startswith(('S', '🔴', '❌', ' ')):
                        print('     ' + _ln.strip()[:96])
                        break
        ok_all &= _ok5
    else:
        print('  ⚪ [5/7] audit_judgment: 未解析（三态）')

    # ⑥ audit_chain（8 条传导链·数据源三态不计入分母）
    if os.path.exists(calc):
        _rc6, _o6, _ = run([PY, _sc('audit_chain.py'), '--l4'], timeout=180)
        _m6 = re.search(r'贯通 (\d+)/(\d+)', _o6 or '')
        if _m6:
            _g6, _d6 = _m6.groups()
            _ok6 = (_g6 == _d6)
            print('  %s [6/7] audit_chain(传导链): 贯通 %s/%s'
                  % ('✅' if _ok6 else '🔴', _g6, _d6))
            ok_all &= _ok6
        else:
            print('  ⚪ [6/7] audit_chain: 未解析（三态）')
    else:
        print('  ⚪ [6/7] audit_chain: 无 calc 输出 → 跳过（三态）')

    # ⑦ audit_semantic（🔴2026-11-01 **语义级**·calc 权威值 vs raw 声明值）
    #    补 audit_judgment 的诚实边界：关键词级只拦「完全没提」，拦不住「提了但判断错」
    if os.path.exists(calc):
        _rc7, _o7, _ = run([PY, _sc('audit_semantic.py'),
                            '--calc', calc, '--raw', raw_p], timeout=180)
        _m7 = re.search(r'✅ 一致 (\d+) ｜ ⚠️ 已说明 (\d+) ｜ 🔴 \*\*冲突 (\d+)\*\* ｜ ⚪ 未写 (\d+)',
                        _o7 or '')
        if _m7:
            _c7, _e7, _x7, _n7 = _m7.groups()
            _ok7 = (_x7 == '0')
            print('  %s [7/7] audit_semantic(语义级): 一致 %s / 已说明 %s / **冲突 %s** / 未写 %s'
                  % ('✅' if _ok7 else '🔴', _c7, _e7, _x7, _n7))
            if not _ok7:
                _shown = 0
                for _ln in (_o7 or '').splitlines():
                    if 'CONFLICT' in _ln and _shown < 3:
                        print('     ' + _ln.strip()[:94])
                        _shown += 1
                print('     → 改判可以，但须写「改锚理由: / 改判理由:」（否则判判断与计算脱节）')
            ok_all &= _ok7
        else:
            print('  ⚪ [7/7] audit_semantic: 未解析（三态）')
    else:
        print('  ⚪ [7/7] audit_semantic: 无 calc 输出 → 跳过（三态）')

    print('=' * 78)
    print('结论: %s' % ('✅ 七道闸门全过·可交付' if ok_all else '🔴 有闸门未过·禁止交付'))
    return 0 if ok_all else 1


def main():
    # 🔴P42: --verify 子模式（raw 填完后一键四道闸门）
    if "--verify" in sys.argv:
        _vi = sys.argv.index("--verify")
        _cv = sys.argv[_vi + 1] if len(sys.argv) > _vi + 1 else None
        if not _cv:
            print("用法: python pipeline.py --verify <case_id>")
            sys.exit(2)
        sys.exit(do_verify(_cv))
    ap = argparse.ArgumentParser()
    # 🔴 2026-11-01 用户要求：pipeline 直接吃图片
    #    python pipeline.py 图1.png 图2.png ...   → 自动 image2txt → 标准 txt → 原流程
    #    python pipeline.py case.txt              → 原样（txt 直接跑）
    ap.add_argument('input', nargs='+',
                    help='竞彩 txt，或 1 张以上竞彩截图（自动识别成标准 txt）')
    # 图片模式下 队名/联赛/开赛时间 可由赛事页自动提取 → 不再必填
    ap.add_argument('--teams', default=None, help='「主,客」·图片模式可自动提取')
    ap.add_argument('--league', default=None, help='图片模式可自动提取')
    ap.add_argument('--kickoff', default=None, help='图片模式可自动提取')
    ap.add_argument('--event'); ap.add_argument('--eu'); ap.add_argument('--handi')
    ap.add_argument('--home_water'); ap.add_argument('--o25'); ap.add_argument('--u25')
    ap.add_argument('--inj_list_h'); ap.add_argument('--inj_list_a')
    ap.add_argument('--inj_h'); ap.add_argument('--inj_a')
    ap.add_argument('--draw-score'); ap.add_argument('--step5-dirs'); ap.add_argument('--ucl-round', default='main',
                    choices=['main', 'ko', 'qual', 'qual_playoff'])
    # 🔴2026-11-03 实跑实抓: 欧冠轮次原**传不进** calc_all → 资格赛被按 main 误加 +0.67 球
    ap.add_argument('--case'); ap.add_argument('--skip-net', action='store_true')
    ap.add_argument('--no-skeleton', action='store_true')
    a = ap.parse_args()

    # ── Stage -1：输入归一化（图片 → 标准 txt）──
    IMG_EXT = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')
    if all(x.lower().endswith(IMG_EXT) for x in a.input):
        std, meta = stage_img(a.input, a.league, a.teams, a.kickoff)
        if not std:
            print('🔴 图片识别失败 → 终止（不进入后续阶段）')
            return 2
        if not a.teams and meta.get('match'):
            a.teams = '%s,%s' % tuple(meta['match'])
        if not a.league and meta.get('league'):
            a.league = meta['league']
        if not a.kickoff and meta.get('kickoff'):
            a.kickoff = meta['kickoff']
    else:
        std = a.input[0] if len(a.input) == 1 else None
        if std is None:
            print('🔴 混传图片与 txt 不支持：请只给 txt，或只给图片')
            return 2

    miss = [k for k, v in (('--teams', a.teams), ('--kickoff', a.kickoff)) if not v]
    if miss:
        print('🔴 缺少 %s —— 图片里没识别出来，请手动补' % ' / '.join(miss))
        return 2
    a.league = a.league or '意甲'

    print('=' * 78)
    print('🔴 pipeline 一键全流程 · %s · %s' % (a.teams, a.kickoff))
    print('=' * 78)
    t0 = time.time()
    stage00_context(getattr(a, 'kickoff', None))   # 🔴P2 时间上下文前置
    std = stage0(std)
    stage1(std, a)
    _stage2_res = stage2(a)
    dirs = stage3(a)
    calc_out, calc_path = stage4(std, a, dirs, pre=_stage2_res)
    # 🔴2026-11-04: 把 Stage2 的伤停消息传进 raw（三态实证必须落盘）
    _inj_msg = None
    try:
        _inj_t = (_stage2_res or {}).get('inj')
        _inj_msg = _inj_t[1] if isinstance(_inj_t, (tuple, list)) and len(_inj_t) > 1 else None
    except Exception:
        _inj_msg = None
    raw_p = stage5(a, std, calc_out, calc_path, inj_msg=_inj_msg)
    stage6(calc_path, raw_p)

    total = time.time() - t0
    calc_t = next((d for n, nm, d, ok, note in TIMING if n == 4), 0)
    print('\n' + '=' * 78)
    print('总耗时 %.1fs ｜ 其中 calc_all %.1fs ｜ 其余 %.1fs' % (total, calc_t, total - calc_t))
    # 🔴2026-11-01 时间模块：**输出末尾必带程序算的当前时间**
    #   模型今夜 6 次报错时间 → 不许再靠「我记得」，每次收尾都给准数
    try:
        from time_guard import now_bj as _nbj, match_state as _ms, fmt_bj as _fb
        _n = _nbj()
        print('🔴 当前时间: %s（程序计算·禁凭记忆）' % _fb(_n, True))
        if getattr(a, 'kickoff', None):
            print('   本场: %s' % _ms(a.kickoff)['note'])
    except Exception as _e:
        print('   时间模块: ⚪ %s' % str(_e)[:60])

    print('=' * 78)
    print('\n【下一步·模型必做】')
    print('  1) 打开 raw，逐处填【待模型判断】（%s）' % (raw_p or '未生成'))
    print('  2) 填完跑: python pipeline.py --verify %s' % (a.case or '<case>'))
    print('  3) case_write add 写入案例库 + 补填 CSV')
    print('  4) 🔴 禁重跑 calc_all（参数已在 Stage3/4 一次给全·重跑会覆盖锚）')
    if SOFT_WARN:
        print('\n⚠️ 外部数据源三态（**不算流程失败**·但 raw 必须逐条留痕）：')
        for x in SOFT_WARN:
            print('  · ' + x)
    if STAGE_FAIL:
        print('\n🔴 失败阶段（必须先修）：')
        for x in STAGE_FAIL:
            print('  · ' + x)
    else:
        print('\n✅ 全部阶段通过' + ('（%d 处外部源三态·须 raw 留痕）' % len(SOFT_WARN)
                                    if SOFT_WARN else ''))
    return 1 if STAGE_FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
