# -*- coding: utf-8 -*-
"""兼容转发（2026-09-11·轻封装后入口已迁入模块 scripts/online_learning/learn.py）
保留本文件以保证旧文档/旧命令仍可用。新调用请用:
  python scripts/online_learning/learn.py --case X --real 比分 --txt <竞彩txt> ...
"""
import os, sys, subprocess

# GBK console guard (2026-09-15)
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
target = os.path.join(ROOT, 'data', 'online_learning', 'learn.py')
sys.exit(subprocess.call([sys.executable, target] + sys.argv[1:],
                         env=dict(os.environ, PYTHONIOENCODING='utf-8')))
