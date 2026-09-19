"""案例库全量统计（标准15列+分锚3列格式·V3.5.74）: python scripts/tmp/case_stats.py"""
import csv, io, sys
sys.stdout.reconfigure(encoding='utf-8')
rows = list(csv.reader(open('data/case-library/实战案例.csv', encoding='utf-8-sig')))
hdr = rows[0]; idx = {h: i for i, h in enumerate(hdr)}
done = [r for r in rows[1:] if r[idx['真实比分']].strip() and r[idx['方向命中']] in ('是','否')]
wait = [r[0] for r in rows[1:] if not (r[idx['真实比分']].strip() and r[idx['方向命中']] in ('是','否'))]
n = len(done)
dh = sum(1 for r in done if r[idx['方向命中']]=='是')
sh = sum(1 for r in done if r[idx['比分命中']]=='是')
ph = sum(1 for r in done if r[idx['完美命中']]=='是')
print('=' * 60)
print('案例库统计（标准列·case数%d·已复盘%d）' % (len(rows)-1, n))
print('=' * 60)
print('方向命中(any·含并列): %d/%d = %.1f%%' % (dh, n, dh/n*100))
print('比分命中(历史口径):   %d/%d = %.1f%%' % (sh, n, sh/n*100))
print('完美命中:              %d/%d = %.1f%%' % (ph, n, ph/n*100))
print('待赛果/待补充: %s' % (wait or '无'))
# 分档（置信度层）
from collections import Counter
conf = Counter(r[idx['置信度层']] for r in done if r[idx['置信度层']])
print('置信度层分布:', dict(conf))

# ========= 分锚比分口径(P0-3·V3.5.74) =========
print()
print('======== 分锚比分口径(P0-3·V3.5.74) ========')
try:
    _main = sum(1 for r in done if idx.get('主锚命中') is not None and r[idx['主锚命中']]=='是')
    _sec = sum(1 for r in done if idx.get('次锚命中') is not None and r[idx['次锚命中']]=='是')
    _both = sum(1 for r in done if (idx.get('主锚命中') is not None and r[idx['主锚命中']]=='是') or (idx.get('次锚命中') is not None and r[idx['次锚命中']]=='是'))
    print(f"严格口径(已复盘{n}): 主锚only {_main}/{n}={_main/n*100:.1f}% | 次锚 {_sec}/{n}={_sec/n*100:.1f}% | 主或次 {_both}/{n}={_both/n*100:.1f}%")
    print("说明: 历史case01-49旧口径含候选池(比分命中>主或次)·case50+严格主锚/次锚口径·真实命中以复盘结论为准")
except Exception as _e:
    print("分锚统计跳过:", _e)
