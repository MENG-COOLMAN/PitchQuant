# -*- coding: utf-8 -*-
"""magnitude_ledger.py — 量级台账规范化 + 门槛计数（2026-10-13·用户指令「先规范化台账两列+加门槛自动计数」）

背景：`data/case-library/量级台账.csv` 的「偏差」「特征标记」两列为**自由文本**
  （实测 66 / 85 种写法：`低估2档(扁平场独锁2:0)` / `**高估2球**(...)` / `连续差` / `接近` / `+0.6球(实际3.0 vs 期望2.42)`…）
  → **无法按类聚合** → AGENTS ⑤量级对账的「每类累积≥20-30 场才固化调节系数」门槛**判不出来**。

本脚本：
  normalize —— 新增两列 `偏差档`（枚举）/`特征类`（多标签·`+`连接），**保留原列不动**（零信息损失·可审计）
  status    —— 按「偏差档」「偏差档×特征类」计数 → 门槛 20 → 输出达标清单
               🔴 **自动区分「调参期(<2026-10-01)」与「前瞻 holdout(≥2026-10-01)」**
               （holdout 按铁则**不得用于调参**·只作前向验证 → 门槛只数调参期）

偏差符号约定：**实际 − 期望**（正 = 高于期望 = 低估；负 = 低于期望 = 高估）
  |偏差| ≤0.5 → 命中 ｜ (0.5,1.5] → 低估/高估1档 ｜ (1.5,2.5] → 2档 ｜ >2.5 → 3档+

用法：
    python data/tmp/magnitude_ledger.py normalize [--csv 路径]
    python data/tmp/magnitude_ledger.py status [--json out.json]
"""
import csv
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(_HERE, "..", "case-library", "量级台账.csv")
HOLDOUT_FROM = "2026-10-01"          # 🔴前瞻 holdout 起算（只作前向验证·不得用于调参）
THRESHOLD = 20                        # 量级类固化门槛（AGENTS ⑤量级对账：≥20-30 场）

# 特征标签（顺序即优先级·最多取 3 个）
FEAT_RULES = [
    ("超深屠杀", ("超深屠杀",)),
    ("超深盘", ("超深盘",)),
    ("NL超域", ("NL", "欧国联")),
    ("对攻", ("对攻", "双方进球大战")),
    ("死守", ("死守", "摆大巴")),
    ("防线缺", ("防线", "漏")),
    ("伤停极端", ("伤停",)),
    ("大球强失效", ("大球强完全失效", "大球强失效", "大球强信号失效", "大球强未兑现", "大球未兑现")),
    ("大球强", ("大球强",)),
    ("小球", ("小球",)),
    ("客热门", ("客热", "客强", "客队热门")),
    ("弱共识", ("弱共识",)),
    ("强共识", ("强共识", "skew")),
    ("平局并列", ("平局并列",)),
    ("完美命中", ("完美命中", "主锚精确", "次锚精确", "主锚中")),
    ("方向误判", ("方向误判", "方向错", "方向✗")),
    ("正常", ("正常",)),
]


def _num(x):
    try:
        return float(str(x).replace("球", "").strip())
    except Exception:
        return None


def norm_dev(raw):
    """偏差原值 -> 枚举档位（返回 (档位, 依据)）"""
    s = str(raw or "").strip().replace("**", "")
    if not s:
        return "?" + "待人工", "空"
    # ① 形如 实际X vs 期望Y / 实际X球·期望Y球 -> 精确差值
    m = re.search(r"实际\s*(-?\d+(?:\.\d+)?)\s*(?:球|\.0)?\s*(?:vs|·|,)\s*期望\s*(-?\d+(?:\.\d+)?)", s)
    if m:
        d = float(m.group(1)) - float(m.group(2))
        return _band(d), "实测差 %.2f" % d
    # ② 形如 +0.6球 / -2.2 / +1 / -0.8 / 0 （纯数值·可为档数）
    m = re.fullmatch(r"([+\-]?\d+(?:\.\d+)?)\s*球?", s)
    if m:
        d = float(m.group(1))
        return _band(d), "数值 %.2f" % d
    # ③ 文本类
    if "严重低估" in s:
        return "低估3档+", "文本"
    if "严重高估" in s:
        return "高估3档+", "文本"
    if "低估→高估" in s or "→高估" in s:
        return "?待人工", "矛盾表述"
    for kw, band in (("低估3", "低估3档+"), ("低估2", "低估2档"), ("低估1", "低估1档"),
                     ("低估", "低估1档")):
        if re.search(re.escape(kw), s):
            return band, "文本 " + kw
    for kw, band in (("高估3", "高估3档+"), ("高估2", "高估2档"), ("高估1", "高估1档"),
                     ("高估", "高估1档")):
        if re.search(re.escape(kw), s):
            return band, "文本 " + kw
    if any(k in s for k in ("命中", "准确", "相邻差", "接近")):
        return "命中", "文本"
    return "?待人工", "未识别"


def _band(d):
    a = abs(d)
    if d >= 0:
        return "命中" if a <= 0.5 else ("低估1档" if a <= 1.5 else ("低估2档" if a <= 2.5 else "低估3档+"))
    return "命中" if a <= 0.5 else ("高估1档" if a <= 1.5 else ("高估2档" if a <= 2.5 else "高估3档+"))


def norm_feat(raw):
    s = str(raw or "").strip().replace("**", "")
    if not s:
        return "其他", "空"
    tags = []
    for tag, kws in FEAT_RULES:
        if any(k in s for k in kws):
            tags.append(tag)
        if len(tags) >= 3:
            break
    return ("+".join(tags) if tags else "其他"), ("多标签" if len(tags) > 1 else "单标签")


def cmd_normalize(a):
    rows = list(csv.reader(open(CSV, encoding="utf-8-sig")))
    hdr = rows[0]
    for col in ("偏差档", "特征类"):
        if col not in hdr:
            hdr.append(col)
    ih, ift = hdr.index("偏差档"), hdr.index("特征类")
    idev, ifeat = hdr.index("偏差"), hdr.index("特征标记")
    n, unk = 0, []
    for r in rows[1:]:
        while len(r) < len(hdr):
            r.append("")
        band, why = norm_dev(r[idev])
        feat, _ = norm_feat(r[ifeat])
        if r[ih] != band:
            n += 1
        r[ih], r[ift] = band, feat
        if band.startswith("?"):
            unk.append((r[0], r[idev], why))
    with open(CSV, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)
    print("   规范化完成: %d 行·变更 %d 行" % (len(rows) - 1, n))
    if unk:
        print("   ⚠️ 待人工确认 %d 行（原列未动·仅枚举列标 ?）:" % len(unk))
        for cid, v, why in unk[:10]:
            print("      case%s  '%s'  (%s)" % (cid, v, why))
    else:
        print("   ✅ 全部行已成功映射（无待人工项）")


def cmd_status(a):
    rows = list(csv.reader(open(CSV, encoding="utf-8-sig")))
    hdr = rows[0]
    if "偏差档" not in hdr:
        raise SystemExit("    ❌ 请先跑 normalize（缺「偏差档」列）")
    icid, idate = hdr.index("case_id"), hdr.index("日期")
    iband, ift = hdr.index("偏差档"), hdr.index("特征类")
    pre, ho = {}, {}
    for r in rows[1:]:
        if len(r) <= max(iband, ift):
            continue
        key = r[iband] + " × " + r[ift]
        tgt = ho if (r[idate] or "") >= HOLDOUT_FROM else pre
        tgt[key] = tgt.get(key, 0) + 1
    print("   门槛 = %d 场/类（AGENTS ⑤量级对账·固化调节系数）" % THRESHOLD)
    print("   🔴 只数【调参期 < %s】（holdout 不得用于调参·仅前向验证）" % HOLDOUT_FROM)
    print("")
    print("   【调参期】达标清单（≥%d）:" % THRESHOLD)
    ok = [(k, v) for k, v in sorted(pre.items(), key=lambda x: -x[1]) if v >= THRESHOLD]
    for k, v in ok:
        print("      ✅ %-34s %d" % (k, v))
    if not ok:
        print("      （无）")
    print("   【调参期】最接近门槛 Top5:")
    for k, v in sorted(pre.items(), key=lambda x: -x[1])[:5]:
        print("      %-34s %d/%d" % (k, v, THRESHOLD))
    print("")
    print("   【前瞻 holdout ≥ %s】（仅前向验证·不参与门槛）: %d 条"
          % (HOLDOUT_FROM, sum(ho.values())))
    for k, v in sorted(ho.items(), key=lambda x: -x[1])[:6]:
        print("      %-34s %d" % (k, v))
    print("")
    print("   【偏差档口径·调参期】:")
    cnt = {}
    for r in rows[1:]:
        if (r[idate] or "") >= HOLDOUT_FROM:
            continue
        cnt[r[iband]] = cnt.get(r[iband], 0) + 1
    for k, v in sorted(cnt.items(), key=lambda x: -x[1]):
        print("      %-12s %d%s" % (k, v, "  ← 达门槛" if v >= THRESHOLD else ""))
    # 🔴 方向聚合（低估 vs 高估 vs 命中·不分档）——判断「是否存在系统性单向偏差」
    _dir = {"低估": 0, "高估": 0, "命中": 0, "?待人工": 0}
    for k, v in cnt.items():
        if k.startswith("低估"):
            _dir["低估"] += v
        elif k.startswith("高估"):
            _dir["高估"] += v
        elif k == "命中":
            _dir["命中"] += v
        else:
            _dir["?待人工"] += v
    print("")
    print("   【方向聚合·调参期】低估 %d ｜ 高估 %d ｜ 命中 %d ｜ 待人工 %d"
          % (_dir["低估"], _dir["高估"], _dir["命中"], _dir["?待人工"]))
    if _dir["低估"] and _dir["高估"]:
        _gap = _dir["低估"] - _dir["高估"]
        _tol = max(3, int(0.15 * (_dir["低估"] + _dir["高估"])))
        print("      → 低估/高估 差值 %+d 场%s" % (
            _gap,
            "（≈对称·独立印证「无系统性单向偏差」）" if abs(_gap) <= _tol
            else "（⚠️ 单向倾向·继续累积至门槛再回测）"))
    out = {"threshold": THRESHOLD, "holdout_from": HOLDOUT_FROM,
           "pre_pairs": pre, "holdout_pairs": ho, "pre_bands": cnt, "pre_dir": _dir}
    if a.get("json"):
        json.dump(out, open(a["json"], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("   JSON -> " + a["json"])


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1
    cmd, a = argv[0], {}
    i = 1
    while i < len(argv):
        if argv[i] == "--json" and i + 1 < len(argv):
            a["json"] = argv[i + 1]
            i += 2
        else:
            i += 1
    if cmd == "normalize":
        cmd_normalize(a)
    elif cmd == "status":
        cmd_status(a)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
