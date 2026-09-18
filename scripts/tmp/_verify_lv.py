# -*- coding: utf-8 -*-
"""临时验证脚本（2026-09-19·fix_s1 验收）: 跑 calc_all 确认「联赛基准」自动输出
用法: python data/tmp/_verify_lv.py
"""
import subprocess, sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

def run(tag, args):
    r = subprocess.run([sys.executable, 'data/tmp/calc_all.py'] + args,
                       capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=240)
    hits = [l.strip() for l in (r.stdout or '').splitlines()
            if ('联赛基准' in l) or ('本场主胜档' in l) or ('联赛比分Top5' in l)]
    print('--- %s | exit=%s ---' % (tag, r.returncode))
    print('\n'.join(hits) if hits else '(无联赛基准行)')

# ① 意甲(五大联赛·应触发)
run('意甲 mon188', ['data/tmp/mon188.txt', '意甲', '--eu', '2.836,3.415,2.704', '--handi', '0.25', '--o25', '1.827'])
# ② 欧冠(非五大·应不触发·脚本仍正常)
run('欧冠 bar153', ['data/tmp/bar153.txt', '欧冠', '--eu', '1.10,10.0,26.0', '--handi', '-3', '--o25', '1.22'])
# ③ 英超(应触发·不同档位分支)
run('英超 bet184', ['data/tmp/bet184.txt', '英超', '--eu', '1.55,4.20,6.00', '--handi', '-1', '--o25', '1.90'])
print('DONE')
