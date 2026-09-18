#!/usr/bin/env python
# 更新实战案例.md的6场赛果
path = 'data/case-library/实战案例.md'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

cases = [
    ('案例15 · 瓦萨 vs TPS图尔', '1:3（客胜）| 方向错 比分错 完美错'),
    ('案例16 · 不伦瑞克 vs 波鸿', '0:1（客胜）| 方向错 比分错 完美错'),
    ('案例17 · 罗森博格 vs 维京', '2:1（主胜）| 方向中 比分中 完美中'),
    ('案例18 · 特尔斯达 vs 鹿斯巴达', '1:3（客胜）| 方向错 比分错 完美错'),
    ('案例19 · 伍尔弗 vs 布莱克本', '2:2（平局）| 方向错 比分错 完美错'),
    ('案例20 · 里斯本 vs 吉马良斯', '3:2（主胜）| 方向中 比分错 完美错'),
]
for title, score in cases:
    idx = content.find(title)
    if idx < 0:
        print(f'未找到: {title}')
        continue
    status_idx = content.find('状态: 待赛果', idx)
    if status_idx < 0:
        print(f'未找到状态行: {title}')
        continue
    content = content[:status_idx] + '状态: 已复盘\n真实比分: ' + score + content[status_idx+len('状态: 待赛果'):]

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('md赛果已更新')
