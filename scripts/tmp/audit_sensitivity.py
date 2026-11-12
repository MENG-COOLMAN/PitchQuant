# -*- coding: utf-8 -*-
"""Step 输入敏感性消融 audit_sensitivity.py（2026-10-31 批次2·owner 版）

🔴 判据（替代 D 段静态 grep）：
   每个监视项声明它的 **owner**（哪些变体「应该」让它变）。
   · owner 变体 → 输出**必须变**（否则 = 该 Step 未真消费 → 🔴）
   · 非 owner 变体 → 输出**应变**（否则 = 该输入被无关环节偷偷消费 → ⚠️）
   这样才区分得开「没消费」与「本来就不该被这个输入影响」。

用法：
   python data/tmp/audit_sensitivity.py            # 走缓存（若已跑过）
   python data/tmp/audit_sensitivity.py --fresh    # 清缓存重跑 5×calc_all
"""
import argparse
import io
import os
import re
import shutil
import subprocess
import sys

WS = r'<HOME>\AppData\Roaming\reasonix\global-workspace'
os.chdir(WS)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

OUT = 'data/tmp/_sens'
TXT = 'data/tmp/std_raw_lehavre_psg_20261031.txt'
LG = '法甲'
BASE = ['--eu', '1.28,5.50,9.50', '--handi', '-1.5', '--o25', '1.378', '--u25', '3.04']

VARIANTS = [
    ('A_eu', ['--eu', '3.20,3.40,2.20'], '改欧盘（主队超热门 → 冷门）'),
    ('B_o25', ['--o25', '2.30', '--u25', '1.58'], '改大小球（大 → 小）'),
    ('C_draw', ['--draw-score', '3.0'], '改修正53分组分（0 → 3.0）'),
    ('D_handi', ['--handi', '0.0'], '改让球（-1.5 → 平手）'),
    # 🔴2026-11-01 加伤停（此前 4 个变体全无伤停 → 伤停「算了不动作」查不出来）
    # 🔴2026-11-01 用**位置明细**而非直传分：直传分(--inj_h)无位置信息 → calc_all 不打 λ 调整行 → 测不到
    ('E_inj', ['--inj_list_h', '前锋,主力;前锋,主力;后腰,主力',
               '--inj_list_a', '后腰,未知'],
     '加伤停（位置明细·主队攻击线 2 前锋+1 后腰）'),
]

# (标签, 正则, 该由哪个变体触发, 对应 Step)
WATCH = [
    ('S01去水概率', r'去抽水率: [\d.]+% → 隐含: 主[\d.]+%/平[\d.]+%/客[\d.]+%', ['A_eu'], 'S01'),
    ('S01方向差距', r'方向差距\(前两方向\): [\d.]+pt', ['A_eu'], 'S01'),
    ('S01诱阻分类', r'诱阻分类: [^\n]{0,26}', ['A_eu', 'D_handi'], 'S01'),
    ('S01净胜候选池', r'\[netmargin\] 亚盘[^\n]{0,50}', ['D_handi'], 'S01'),
    ('S02修正53覆盖', r'修正53 分组分: \*\*显式覆盖 [\d.]+\*\*', ['C_draw'], 'S02'),
    ('S02修正53明细', r'修正53预计算[^\n]*', ['A_eu'], 'S02'),
    ('S02 V5跨市场', r'V5跨市场分歧[^\n]{0,44}', ['A_eu'], 'S02'),
    ('S05置信度', r'调整后 \*\*[A-Z\-]+\*\*[^\n]{0,16}', ['A_eu', 'E_inj'], 'S05'),
    ('S05并列建议', r'方向\(欧亚综合\): [^\n|]{0,14}\| 并列:[a-z]+', ['C_draw'], 'S05'),
    ('S06进球档', r'量级\(O25校准分布[^\n]{0,44}', ['B_o25'], 'S06'),
    ('S06 P52分级', r'P52 超大球分级[^\n]*', ['B_o25'], 'S06'),
    ('S06.5 λ_final', r'λ_final=[\d.]+ →', ['B_o25', 'E_inj'], 'S06.5'),
    ('S07主锚', r'主锚 [\d:]+ / 次锚 [\d:]+', ['A_eu', 'B_o25'], 'S07'),
    # 🔴2026-11-01 伤停监视项（原 WATCH 表一条伤停都没有 → 伤停未消费查不出）
    ('S02伤停影响分', r'伤停影响分[^\n]{0,44}', ['E_inj'], 'S02'),
    ('S02伤停λ调整', r'λ调整: 主队[+\-][\d.]+[^\n]{0,30}', ['E_inj'], 'S02'),
]


def run(tag, ov):
    out = os.path.join(OUT, '%s.txt' % tag)
    if os.path.exists(out) and os.path.getsize(out) > 5000:
        return out
    args = [sys.executable, '-u', 'data/tmp/calc_all.py', TXT, LG] + BASE + ov
    print('  [run] %-10s %s' % (tag, ' '.join(ov)), flush=True)
    with io.open(out, 'w', encoding='utf-8', errors='replace') as f:
        subprocess.run(args, stdout=f, stderr=subprocess.STDOUT, timeout=900)
    t = io.open(out, encoding='utf-8', errors='replace').read()
    if '未传 --eu' in t:
        print('  🔴 [无效] %s 丢 --eu' % tag)
        return None
    return out


def grab(path, pat):
    if not path:
        return ''
    try:
        t = io.open(path, encoding='utf-8', errors='replace').read()
    except Exception:
        return ''
    m = re.findall(pat, t)
    return (m[-1] if m else '')[:92].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fresh', action='store_true')
    a = ap.parse_args()
    if a.fresh and os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT, exist_ok=True)

    files = {'BASE': run('base', BASE)}
    for n, ov, _ in VARIANTS:
        files[n] = run(n, ov)
    if not files['BASE']:
        print('❌ 基准失败')
        return 2

    names = [n for n, _, _ in VARIANTS]
    print('\n' + '=' * 116)
    print('Step 输入敏感性消融（owner 版）｜ 基准 %d 行' % len(
        io.open(files['BASE'], encoding='utf-8', errors='replace').readlines()))
    print('=' * 116)
    print('%-14s %-24s %s' % ('监视项', '基准值', ' / '.join('%-13s' % n for n in names)))
    print('-' * 116)

    miss = []      # owner 变体未触发 → 疑似未消费
    leak = []      # 非 owner 变体触发 → 意外的耦合
    for label, pat, owners, step in WATCH:
        b = grab(files['BASE'], pat)
        cells = []
        for n in names:
            v = grab(files[n], pat)
            changed = (v != b)
            if n in owners:
                okk = changed
                miss += [] if okk else [(step, label, n, b)]
            else:
                okk = not changed
                leak += [] if okk else [(step, label, n, v)]
            # 🔴2026-11-01 修文案 bug：owner 变体「未变」原显示成 ⚠️意外变（应是 ❌未变）
            if changed:
                _cell = '✅变'
            elif n in owners:
                _cell = '❌未变'
            else:
                _cell = '—同'
            cells.append('%-13s' % _cell)
        print('%-14s %-24s %s' % (label, (b or '(空)')[:24], ' / '.join(cells)))

    print('-' * 116)
    print('应触发（owners）实际触发率：')
    for n in names:
        own = [w for w in WATCH if n in w[2]]
        hit = sum(1 for w in own if grab(files['BASE'], w[1]) != grab(files[n], w[1]))
        print('  %-10s %d/%d' % (n, hit, len(own)))

    print()
    if miss:
        print('🔴 owner 变体未触发（可疑未真消费）：')
        for step, lab, n, b in miss:
            if n not in ('C_draw',) or '修正53' in lab or '并列' in lab:
                print('   [%s] %s ｜ 变体 %s ／ 基准=%s' % (step, lab, n, b[:46]))
    if leak:
        print('⚠️ 非 owner 变体意外触发（耦合）：')
        for step, lab, n, v in leak[:8]:
            print('   [%s] %s ｜ %s → %s' % (step, lab, n, v[:44]))
    hard = [m for m in miss if not (m[2] == 'C_draw' and m[1] not in ('S02修正53', 'S05并列建议'))]
    print()
    if hard:
        print('🔴 硬性未消费 %d 处' % len(hard))
        return 1
    print('✅ owner 判据全过：每个 Step 的关键输入都能改变它的输出 → 真实消费确认')


if __name__ == '__main__':
    sys.exit(main())
