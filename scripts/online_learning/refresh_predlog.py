# -*- coding: utf-8 -*-
"""预测日志补全（2026-09-11·用 data_bridge 采集完整源状态写入 prediction_log）
用法: python scripts/online_learning/refresh_predlog.py [--net]
"""
import os, sys, io, json, glob
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import data_bridge as DB

net = '--net' in sys.argv
d = os.path.join(HERE, 'prediction_log')
for f in sorted(glob.glob(os.path.join(d, '*.json'))):
    try:
        j = json.load(open(f, encoding='utf-8'))
        txt = j.get('txt')
        if not txt or not os.path.exists(txt):
            print('%-14s 跳过（txt 不存在: %s）' % (os.path.basename(f), txt)); continue
        br = DB.collect(txt, j.get('league') or None, net=net)
        j['features'] = br.get('features') or j.get('features')
        j['sources'] = br.get('status', {})
        j['completeness'] = br.get('completeness')
        j['refreshed_at'] = __import__('time').strftime('%Y-%m-%d %H:%M')
        json.dump(j, open(f, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        st = {k: v.get('status') for k, v in (br.get('status') or {}).items()}
        print('%-14s features=%2d | %s | %s' % (os.path.basename(f), len(j['features']), br.get('completeness'), st))
    except Exception as e:
        print('%-14s 失败: %s' % (os.path.basename(f), str(e)[:80]))
