---
name: SL-history-analyzer
description: 历史数据查询：从6.3万场SQL缓存中提取H2H交锋+近10场战绩，补充1.10基本面
---

# SL-history-analyzer：历史数据查询模块

从 football-api.sql 的预建缓存中提取历史交锋、近期战绩。

## 使用方式
```bash
python data/SL-history-analyzer.py "主队名" "客队名"
```

## 输出
- 两队历史交锋（按日期倒序，最多10场）
- 主队近10场战绩（含W/D/L统计和胜率）
- 客队近10场战绩

## 数据源
`C:\Users\12242\Desktop\football-api.sql` → 缓存 `data/fixture_cache.json` (5.6MB)
63,023场完场比赛，51个联赛，覆盖2022-2026赛季

## 依赖
- 缓存文件已预建（data/fixture_cache.json）
- 无需每次读取2.2GB SQL文件

## 模板嵌入
在1.10基本面数据后，调用此模块补充：
- 历史交锋细节（覆盖竞彩自带的基本面数据）
- 近期战绩复核（与用户提供的近10场数据交叉验证）
- 如用户未提供基本面，此模块为主力来源
