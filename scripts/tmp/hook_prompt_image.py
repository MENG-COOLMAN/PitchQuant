# -*- coding: utf-8 -*-
"""UserPromptSubmit hook — 检测新图片并登记待识别任务

设计（2026-11-01·用户方案 C「hook + 规则两者都做」）:
  🔴 本 hook **不做 OCR**，只做「快速检测 + 登记」——
     Reasonix UserPromptSubmit 默认 timeout 仅 5s，而 glm-ocr 单图约 3.6s
     且大图更久 → 在 hook 里跑 OCR 大概率超时被强杀（超时=block，会卡住用户消息）。
     故：hook 只扫附件目录、写 data/tmp/_pending_image.json、立即 exit 0（<100ms）。
     真正识别由模型按 SK-image-to-txt 规则执行（可见、可重试、不阻塞）。

payload（stdin 单行 JSON）:
  {"event":"UserPromptSubmit","cwd":"/repo","prompt":"...","turn":1}

纪律:
  · 永不 block（恒 exit 0）—— 识别失败不该拦用户说话
  · 只认最近 N 分钟新增的图片（默认 180s），避免每轮重复识别旧图
  · 已识别过的图片（.std.txt 已存在）不重复登记
"""
import io
import json
import os
import sys
import time

STATE = None
WINDOW_SEC = 180
IMG_EXT = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')


def main():
    try:
        raw = sys.stdin.read()
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except Exception:
            payload = {}
        cwd = payload.get('cwd') or os.getcwd()

        # 找附件目录（项目级 .reasonix/attachments）
        att = os.path.join(cwd, '.reasonix', 'attachments')
        if not os.path.isdir(att):
            return 0

        now = time.time()
        fresh = []
        for f in os.listdir(att):
            if not f.lower().endswith(IMG_EXT):
                continue
            p = os.path.join(att, f)
            try:
                if now - os.path.getmtime(p) > WINDOW_SEC:
                    continue
            except OSError:
                continue
            # 已产出标准 txt 的跳过（防重复识别）
            stem = os.path.splitext(f)[0]
            done = os.path.join(cwd, 'data', 'tmp', 'ocr_out', stem + '.std.txt')
            if os.path.exists(done):
                continue
            fresh.append({'img': p, 'name': f,
                          'mtime': time.strftime('%Y-%m-%d %H:%M:%S',
                                                 time.localtime(os.path.getmtime(p)))})

        if not fresh:
            return 0

        out = os.path.join(cwd, 'data', 'tmp', '_pending_image.json')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        prev = []
        if os.path.exists(out):
            try:
                prev = (json.load(io.open(out, encoding='utf-8')) or {}).get('items') or []
            except Exception:
                prev = []
        seen = {x.get('img') for x in prev}
        items = prev + [x for x in fresh if x['img'] not in seen]
        json.dump({'detected_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                   'turn': payload.get('turn'), 'items': items},
                  io.open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

        # stdout 对 UserPromptSubmit 无注入效果，但会进 hook 日志，便于排查
        print('[image-hook] 检测到 %d 张新图片 → 已登记 %s' % (len(fresh), out))
        for x in fresh:
            print('  · %s (%s)' % (x['name'], x['mtime']))
    except Exception as e:
        # 🔴 任何异常都不 block（识别失败不该拦用户消息）
        print('[image-hook] 异常（已忽略·不阻断）: %s' % str(e)[:160], file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
