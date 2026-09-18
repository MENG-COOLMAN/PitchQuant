# -*- coding: utf-8 -*-
"""持久化层：状态保存/加载/备份/回滚（JSON + pickle）"""
import os, json, pickle, shutil, time, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C


def _p(*parts):
    return os.path.join(C.STATE, *parts)


def ensure_dirs():
    for d in ('river', 'tables', 'rules', 'cases', 'logs', 'backups'):
        os.makedirs(_p(d), exist_ok=True)


def save_json(rel, obj):
    ensure_dirs()
    path = _p(rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    return path


def load_json(rel, default=None):
    path = _p(rel)
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def save_pickle(rel, obj):
    ensure_dirs()
    path = _p(rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        pickle.dump(obj, f)
    return path


def load_pickle(rel, default=None):
    path = _p(rel)
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'rb') as f:
            return pickle.load(f)
    except Exception:
        return default


def backup_state(tag=None):
    """备份当前状态 → state/backups/<tag>"""
    ensure_dirs()
    tag = tag or time.strftime('%Y%m%d_%H%M%S')
    dst = _p('backups', tag)
    os.makedirs(dst, exist_ok=True)
    for d in ('river', 'tables', 'rules', 'cases'):
        src = _p(d)
        if os.path.exists(src):
            shutil.copytree(src, os.path.join(dst, d), dirs_exist_ok=True)
    return dst


def restore_state(tag):
    """从备份回滚"""
    src = _p('backups', tag)
    if not os.path.exists(src):
        return False
    for d in ('river', 'tables', 'rules', 'cases'):
        s = os.path.join(src, d)
        if os.path.exists(s):
            shutil.copytree(s, _p(d), dirs_exist_ok=True)
    return True


def append_log(entry):
    ensure_dirs()
    with open(_p('logs', 'learning_log.jsonl'), 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def read_log(n=None):
    path = _p('logs', 'learning_log.jsonl')
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows[-n:] if n else rows
