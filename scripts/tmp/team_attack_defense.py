# -*- coding: utf-8 -*-
"""team_attack_defense.py — 球队双向攻防档案表（2026-10-21·用户指令「依托现有数据为每队建 xG 进球表·分析时查询」）

## 为什么不是纯 xG 表（实测依据·五大 37,195 场滚动验证）

用每队近 10 场滚动预测本场进球，MAE（越小越好）:

    ① 本队近 10 场场均进球                      MAE 0.9960  ← 基线
    ② 本队近 10 场 射正 × 28.73%（xG 代理）      MAE 0.9890  (−0.70%)
    ③ 双向: 本队进攻 xG + 对手防守 xG            MAE 0.9836  (−1.25%)
    ④ 双向: 本队进攻进球率 + 对手失球率          MAE 0.9732  (−2.29%) ← 最优

标定值（五大 37,989 场·有射门/射正）: 射正转化率 **28.73%** · 射正率 38.18% · 射门转化率 10.97%
                                   射正 vs 进球 **r=0.456 (r²=0.208)**

→ **xG 代理仅比纯进球率好 0.7%，而「双向进球率」好 2.3%（3 倍）** → 主口径取双向进球率，xG 代理作可选列。

## 数据源

- **联赛层**：`data/Matches.csv`（五大 E0/SP1/D1/I1/F1 · 43,708 场 · 218 队 · 139 队 ≥200 场）
- **欧战层**：`data/europe/欧冠_历史.csv`（264 场 · 116 队 · 每队 2-22 场 → **样本小·仅参考**）

## 口径

| 列 | 含义 | 用法 |
|:--|:--|:--|
| `lg.gf/ga` | 全期场均进/失（联赛） | 基础实力 |
| `lg.home_gf/home_ga` | 主场分离 | **HAF 铁律：只用对应场地子集·禁混合** |
| `lg.away_gf/away_ga` | 客场分离 | 同上 |
| `lg.r50` | 近 50 场（近期状态） | 优先于全期（球队会变） |
| `lg.xg` | 射正×28.73%（xG 代理） | 有射门数据才有（覆盖 49.8%） |
| `ucl.*` | 欧冠进/失/场次 | **n<5 标「仅参考」** |
| `dual` | 本场双向预期进球 | `(主队主场进攻 + 客队客场防守)/2` 及其镜像 |

## 用法

    python data/tmp/team_attack_defense.py build         # 重建 team_attack_defense.json
    python data/tmp/team_attack_defense.py show 巴黎圣曼   # 查单队
    python data/tmp/team_attack_defense.py match 巴黎圣曼 巴萨   # 双向预期进球

## 铁律

- 只提供**独立于赔率的攻防维度**（伤停/ELO/xG/H2H 同级）→ 可用于 Step5 计算结果定方向与 Step6 量级校验
- **永不反转 L2 硬核方向**；与市场冲突时**以市场为准**，本表仅标注
- 欧战样本 <5 场**禁作定量依据**（只标定性参考）
- 主客场必须分离（禁混用），缺失标三态
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
ROOT = os.path.abspath(os.path.join(_HERE, '..', '..'))
MATCHES = os.path.join(ROOT, 'data', 'Matches.csv')
EURO = os.path.join(ROOT, 'data', 'europe', '欧冠_历史.csv')
MAP25 = os.path.join(ROOT, 'data', 'team_name_mapping_2025-26.json')
OUT = os.path.join(_HERE, 'team_attack_defense.json')

BIG5 = {'E0', 'SP1', 'D1', 'I1', 'F1'}
CONV = 0.2873        # 射正 → 进球转化率（五大 37,989 场标定）
RECENT = 50          # 「近期」窗口场次
UCL_MIN = 5          # 欧冠样本门槛（<5 标「仅参考」）

# 欧冠库用的是竞彩式中文简称，映射表未必覆盖 → 手工补常见队
# （只补「能在五大联赛库里找到英文名」的队；纯小国球队无联赛数据·映射也无用）
EXTRA_CN_EN = {
    '皇马': 'Real Madrid', '巴萨': 'Barcelona', '拜仁': 'Bayern Munich',
    '国际米兰': 'Inter', '那不勒斯': 'Napoli', '尤文图斯': 'Juventus',
    '亚特兰大': 'Atalanta', '摩纳哥': 'Monaco', '马赛': 'Marseille',
    '里昂': 'Lyon', '尼斯': 'Nice', '里尔': 'Lille',
    '多特蒙德': 'Dortmund', '勒沃库森': 'Leverkusen', '莱比锡': 'RB Leipzig',
    '斯图加特': 'Stuttgart', '沃尔夫斯堡': 'Wolfsburg', '门兴': 'Mgladbach',
    '切尔西': 'Chelsea', '阿森纳': 'Arsenal', '利物浦': 'Liverpool',
    '曼城': 'Man City', '曼联': 'Man United', '热刺': 'Tottenham',
    '纽卡斯尔': 'Newcastle', '阿斯顿维拉': 'Aston Villa', '埃弗顿': 'Everton',
    '西汉姆': 'West Ham', '布莱顿': 'Brighton', '水晶宫': 'Crystal Palace',
    '马竞': 'Ath Madrid', '马德里竞技': 'Ath Madrid', '塞维利亚': 'Sevilla',
    '比利亚雷': 'Villarreal', '比利亚雷亚尔': 'Villarreal', '毕尔巴鄂': 'Ath Bilbao',
    '皇家社会': 'Sociedad', '贝蒂斯': 'Betis', '巴伦西亚': 'Valencia',
    '巴伦西亚': 'Valencia', '赫塔费': 'Getafe', '塞尔塔': 'Celta',
    '西班牙人': 'Espanol', '巴列卡诺': 'Vallecano', '赫罗纳': 'Girona',
    '奥萨苏纳': 'Osasuna', '阿拉维斯': 'Alaves',
    '巴黎圣曼': 'Paris SG', '巴黎圣日耳曼': 'Paris SG', '巴黎': 'Paris SG',
    '摩纳哥': 'Monaco', '本菲卡': 'Benfica', '阿贾克斯': 'Ajax',
    '布鲁日': 'Club Brugge', '奥林匹亚': 'Olympiacos', '费内巴切': 'Fenerbahce',
    '哥本哈根': 'Copenhagen', '布拉迪斯': 'Slovan', '马尔默': 'Malmo',
    '卢多戈雷': 'Ludogorets', '贝红星': 'Crvena Zvezda', '格风暴': 'Sturm Graz',
    '里斯本': 'Sp Lisbon', '波兹莱赫': 'Lech', '萨迪纳摩': 'Dinamo Zagreb',
    '流浪者': 'Rangers', '凯尔特人': 'Celtic', '萨尔茨堡': 'Salzburg',
    '顿涅茨克': 'Shakhtar', '加拉塔萨雷': 'Galatasaray', '费耶诺德': 'Feyenoord',
    '埃因霍温': 'PSV', '维京': 'Viking', '博德闪耀': 'Bodo/Glimt',
    '斯拉维亚': 'Slavia Prague', '布拉格斯拉维亚': 'Slavia Prague',
    # ── 2026-10-21 补：欧冠库其余中小球队（web 核实 UEFA 资格赛名单·2025-26 / 2026-27）
    #    注意：这些队**不在五大联赛库内** → 只有「欧冠实证」层，无联赛层
    '图凯拉特': 'Kairat Almaty', '帕佛斯': 'Pafos', '圣吉联合': 'Union St.Gilloise',
    '林肯红魔': 'Lincoln Red Imps', '库普斯': 'KuPS', '索列夫': 'Levski Sofia',
    '斯肯迪亚': 'Shkendija', '德利塔': 'Drita', '伊比利亚': 'Iberia 1999',
    '沙巴巴库': 'Sabah Baku', '亚拉腊': 'Ararat-Armenia', '萨基列斯': 'Kauno Zalgiris',
    '埃格纳蒂': 'Egnatia', '费伦茨瓦': 'Ferencvaros', '新圣徒': 'The New Saints',
    '伊斯卡尔': 'Iskra Danilovgrad', '布星': 'FCSB', '日林斯基': 'Zrinjski',
    '沙姆洛克': 'Shamrock Rovers', '贝雷达比': 'Breidablik', '克拉克斯': 'KI Klaksvik',
    '拉恩': 'Larne', '维京古尔': 'Vikingur Reykjavik', '克约大学': 'Universitatea Craiova',
    '米亚尔比': 'Mjallby', '采列': 'Celje', '奥胡斯': 'Aarhus',
    '贝夏普尔': 'Hapoel Beer Sheva', '加拉塔萨': 'Galatasaray', '谢尔伯恩': 'Shelbourne',
    '基迪纳摩': 'Dynamo Kyiv', '哈姆伦': 'Hamrun Spartans', '诺亚FC': 'Noah',
    '比尔森': 'Viktoria Plzen', '里加学院': 'RFS', '迪弗当日': 'Differdange',
    '戈塔维京人': 'Vikingur Gota', '米尔萨米': 'Milsami', '奥林': 'Olimpija Ljubljana',
    '瓦尔达尔': 'Vardar', '弗罗拉': 'Flora Tallinn', '里加FC': 'Riga FC',
    '佛罗里亚': 'Floriana', '阿特比森': 'Atert Bissen', '特费奥里': 'Tre Fiori',
    '吉奧利': 'ETO Gyor', '尼卡斯克': 'Sutjeska Niksic', '巴战士': 'Borac Banja Luka',
    '维捷布斯克': 'Vitebsk', '佩特罗古': 'Petrocub', '图恩': 'Thun',
    '哈茨': 'Hearts', '奥莫尼亚': 'Omonia', '扎布矿工': 'Shakhtar Donetsk',
    '奈梅亨': 'NEC Nijmegen', '布斯巴达': 'Sparta Prague', '特马卡比': 'Maccabi Tel-Aviv',
    '帕纳辛纳': 'Panathinaikos', '布兰': 'Brann', '塞尔维特': 'Servette',
    '维图斯': 'Virtus', '林菲尔德': 'Linfield', '明斯克': 'Dinamo Minsk',
    '雷瓦迪亚': 'Levadia Tallinn', '扎尔吉斯': 'Zalgiris Vilnius',
    '布度洛斯': 'Buducnost', '里耶卡': 'Rijeka',
}


def load_maps():
    """建立 中文↔英文 双向映射（三源合并 + 手工补充）"""
    cn2en, en2cn = {}, {}
    if os.path.exists(MAP25):
        with open(MAP25, encoding='utf-8') as f:
            d = json.load(f)
        for v in d.get('teams') or []:
            en, cn = v.get('en'), v.get('cn')
            if en and cn:
                cn2en.setdefault(cn, en)
                en2cn.setdefault(en, cn)
    for cn, en in EXTRA_CN_EN.items():
        cn2en.setdefault(cn, en)
        en2cn.setdefault(en, cn)
    return cn2en, en2cn


def _num(x):
    try:
        return float(x)
    except Exception:
        return None


def build():
    cn2en, en2cn = load_maps()
    teams = {}

    def slot(en):
        if en not in teams:
            teams[en] = {
                'cn': en2cn.get(en), 'leagues': set(),
                'lg': {'n': 0, 'gf': 0, 'ga': 0, 'hgf': 0, 'hga': 0, 'hn': 0,
                       'agf': 0, 'aga': 0, 'an': 0, 'sot': 0.0, 'sotn': 0,
                       'over25': 0, 'hist': []},
                'ucl': {'n': 0, 'gf': 0, 'ga': 0},
            }
        return teams[en]

    # ---------- 联赛层 ----------
    # 🔴2026-10-21 兼容层修复（P0·实跑抓）: 本表 2026-10-21 重构为 {teams:{...}} 结构后
    #   **覆盖了旧平铺表**（原 1185 队 {队名:{gf,ga,n}}），而 `calc_v3572.adjust_by_team_half`
    #   （D5 球队攻防分层）按平铺结构 `ad.get(队名)` 读取 → 恒返回 {} → **D5 静默失效**
    #   → 修: 同一文件内**同时**输出平铺兼容层（全 Division·n>=10·覆盖面不低于旧表）
    flat = {}
    with open(MATCHES, encoding='utf-8', errors='replace') as f:
        for r in csv.DictReader(f):
            fth, fta = _num(r['FTHome']), _num(r['FTAway'])
            if fth is None or fta is None:
                continue
            fth, fta = int(fth), int(fta)
            # 平铺兼容层（全 Division·不区分五大·对应旧表覆盖面）
            for _en, _gf, _ga in ((r['HomeTeam'], fth, fta), (r['AwayTeam'], fta, fth)):
                _fd = flat.setdefault(_en, {'gf': 0, 'ga': 0, 'n': 0})
                _fd['gf'] += _gf
                _fd['ga'] += _ga
                _fd['n'] += 1
            if r['Division'] not in BIG5:
                continue
            h, a = r['HomeTeam'], r['AwayTeam']
            sot_h, sot_a = _num(r['HomeTarget']), _num(r['AwayTarget'])
            for en, gf, ga, is_home, sot in ((h, fth, fta, True, sot_h), (a, fta, fth, False, sot_a)):
                s = slot(en)
                s['leagues'].add(r['Division'])
                lg = s['lg']
                lg['n'] += 1
                lg['gf'] += gf
                lg['ga'] += ga
                if is_home:
                    lg['hn'] += 1
                    lg['hgf'] += gf
                    lg['hga'] += ga
                else:
                    lg['an'] += 1
                    lg['agf'] += gf
                    lg['aga'] += ga
                if sot is not None:
                    lg['sot'] += sot
                    lg['sotn'] += 1
                if gf + ga >= 3:
                    lg['over25'] += 1
                lg['hist'].append((r['MatchDate'], gf, ga))

    # ---------- 欧战层（欧冠·中文队名 → 英文） ----------
    ucl_rows = []
    with open(EURO, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            m = re.match(r'^(\d+):(\d+)$', (r['score'] or '').strip())
            if not m:
                continue
            ucl_rows.append((r['home'], int(m.group(1)), r['away'], int(m.group(2)), r['round'], r['date']))
    ucl_unmapped = {}
    for home, gh, away, ga, rnd, dt in ucl_rows:
        for cn, gf, gaa in ((home, gh, ga), (away, ga, gh)):
            en = cn2en.get(cn)
            if not en:
                ucl_unmapped[cn] = ucl_unmapped.get(cn, 0) + 1
                continue
            s = slot(en)
            if not s['cn']:
                s['cn'] = cn
            s['leagues'].add('欧冠')
            s['ucl']['n'] += 1
            s['ucl']['gf'] += gf
            s['ucl']['ga'] += gaa

    # ---------- 汇总 ----------
    out = {}
    for en, s in teams.items():
        lg = s['lg']
        n = lg['n']
        if n == 0 and s['ucl']['n'] == 0:
            continue
        item = {
            'cn': s['cn'],
            'leagues': sorted(s['leagues']),
            'lg': None,
            'ucl': None,
            'dual_ref': None,
        }
        if n > 0:
            lg['hist'].sort(key=lambda x: x[0])
            r50 = lg['hist'][-RECENT:]
            item['lg'] = {
                'n': n,
                'gf': round(lg['gf'] / n, 2), 'ga': round(lg['ga'] / n, 2),
                'home_n': lg['hn'],
                'home_gf': round(lg['hgf'] / lg['hn'], 2) if lg['hn'] else None,
                'home_ga': round(lg['hga'] / lg['hn'], 2) if lg['hn'] else None,
                'away_n': lg['an'],
                'away_gf': round(lg['agf'] / lg['an'], 2) if lg['an'] else None,
                'away_ga': round(lg['aga'] / lg['an'], 2) if lg['an'] else None,
                'r50_n': len(r50),
                'r50_gf': round(sum(x[1] for x in r50) / len(r50), 2) if r50 else None,
                'r50_ga': round(sum(x[2] for x in r50) / len(r50), 2) if r50 else None,
                'sot': round(lg['sot'] / lg['sotn'], 2) if lg['sotn'] else None,
                'xg': round(lg['sot'] / lg['sotn'] * CONV, 2) if lg['sotn'] else None,
                'xg_cov': round(lg['sotn'] / n * 100, 1),
                'over25': round(lg['over25'] / n * 100, 1),
                'sample': 'ok' if n >= 100 else ('small' if n >= 30 else 'tiny'),
            }
        if s['ucl']['n'] > 0:
            u = s['ucl']
            item['ucl'] = {
                'n': u['n'],
                'gf': round(u['gf'] / u['n'], 2), 'ga': round(u['ga'] / u['n'], 2),
                'sample': 'ok' if u['n'] >= UCL_MIN else 'reference_only',
                'note': None if u['n'] >= UCL_MIN else '样本<5场·仅定性参考·禁作定量依据',
            }
        # 🔴融合口径（贝叶斯收缩）: 欧战样本小 → 向联赛收缩
        #   w_lg = min(n_lg,200)/200（联赛封顶 200 场即可信）
        #   w_ucl = n_ucl/(n_ucl+5)（n=5 时仅 50% 权重·n=2 时 29%）
        _lgw = min(n, 200) / 200.0 if n > 0 else 0.0
        _uclw = s['ucl']['n'] / (s['ucl']['n'] + 5.0) if s['ucl']['n'] > 0 else 0.0
        if n > 0 and s['ucl']['n'] > 0:
            _w = _lgw + _uclw
            item['blend'] = {
                'att': round((_lgw * item['lg']['gf'] + _uclw * item['ucl']['gf']) / _w, 2),
                'def': round((_lgw * item['lg']['ga'] + _uclw * item['ucl']['ga']) / _w, 2),
                'w_lg': round(_lgw / _w, 3), 'w_ucl': round(_uclw / _w, 3),
                'note': '联赛+欧冠贝叶斯收缩（w_ucl=n/(n+5)）',
            }
        elif n > 0:
            item['blend'] = {'att': item['lg']['gf'], 'def': item['lg']['ga'],
                             'w_lg': 1.0, 'w_ucl': 0.0, 'note': '仅联赛'}
        else:
            item['blend'] = None
        out[en] = item

    doc = {
        'generated': '2026-10-21',
        'version': 'V3.5.80-N27',
        'source': {'league': 'data/Matches.csv 五大 43,708 场', 'europe': 'data/europe/欧冠_历史.csv 264 场'},
        'calibration': {'conv_sot_to_goal': CONV, 'conv_note': '五大 37,989 场标定（总进球/总射正）',
                        'sot_goal_r': 0.456, 'sot_goal_r2': 0.208},
        'verification': {
            'mae_goal_only': 0.9960, 'mae_xg_only': 0.9890,
            'mae_xg_dual': 0.9836, 'mae_goal_dual': 0.9732,
            'note': '滚动验证 37,195 场·双向进球率最优（−2.29%）→ 主口径；xG 代理仅作可选列',
        },
        'dual_formula': {
            'home_expect': '(主队 home_gf + 客队 away_ga) / 2',
            'away_expect': '(客队 away_gf + 主队 home_ga) / 2',
            'total_expect': 'home_expect + away_expect',
        },
        'teams': out,
        'unmapped_ucl': dict(sorted(ucl_unmapped.items(), key=lambda x: -x[1])),
    }
    # 🔴平铺兼容层（供 calc_v3572 D5 · n>=10 与旧表口径一致）
    _flat = {k: {'gf': round(v['gf'] / v['n'], 2), 'ga': round(v['ga'] / v['n'], 2), 'n': v['n']}
             for k, v in flat.items() if v['n'] >= 10}
    _META = set(doc.keys())
    _clash = [k for k in _flat if k in _META]
    assert not _clash, ('平铺层与元数据键冲突: %s' % _clash)
    doc['_compat'] = {
        'flat_teams': len(_flat),
        'note': ('平铺层 {队名:{gf,ga,n}} 供 calc_v3572.adjust_by_team_half(D5) 消费·'
                 '含全部 Division（不限五大）·n>=10 · 与 2026-10-21 重构前旧表同口径'),
    }
    doc.update(_flat)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    return doc


def _load():
    if not os.path.exists(OUT):
        return build()
    with open(OUT, encoding='utf-8') as f:
        return json.load(f)


# 🔴平铺兼容键（非球队·禁被 find/show 当队处理）
_META_KEYS = {'generated', 'version', 'source', 'calibration', 'verification',
              'dual_formula', 'teams', 'unmapped_ucl', '_compat'}


def find(name):
    """队名查找（英/中全称/中简称/手工别名/全称映射/反向子串·逐级回退）"""
    d = _load()
    t = d['teams']
    name = str(name or '').strip()
    # 🔴2026-10-30 批次4（P0-5）: the-odds-api / prestep 的**全称** → 表内键
    #   实测今晚 5 场: `Paris Saint-Germain` / `Stade Rennais FC` / `SV 07 Elversberg`
    #   原实现只做「传入名 ⊂ 表内键」→ 全称全部匹配不到 → N27 恒三态
    _FULL = {
        'Paris Saint-Germain': 'Paris SG', 'Paris Saint Germain': 'Paris SG',
        'Stade Rennais FC': 'Rennes', 'Stade Rennais': 'Rennes',
        'Racing Club De Lens': 'Lens', 'Le Havre AC': 'Le Havre',
        'Lille OSC': 'Lille', 'OGC Nice': 'Nice', 'FSV Mainz': 'Mainz',
        'SV 07 Elversberg': 'Elversberg', 'Villarreal CF': 'Villarreal',
        'Espanyol Barcelona': 'Espanyol', 'Real Betis': 'Betis',
        'Athletic Club': 'Athletic Bilbao', 'Real Sociedad': 'Real Sociedad',
    }
    if name in _FULL and _FULL[name] in t:
        return _FULL[name], t[_FULL[name]]
    if name in t:
        return name, t[name]
    # ① 手工别名表（竞彩简称 → 英文）
    _en = EXTRA_CN_EN.get(name)
    if _en and _en in t:
        return _en, t[_en]
    # ② 表内中文名精确
    for en, v in t.items():
        if v.get('cn') == name:
            return en, v
    # ③ 英文大小写无关
    low = name.lower()
    for en, v in t.items():
        if en.lower() == low:
            return en, v
    # ④ 手工别名表的所有英文候选（含 cn2en 全表）
    cn2en, _ = load_maps()
    for cand in ([_en] if _en else []) + [cn2en.get(name)]:
        if cand and cand in t:
            return cand, t[cand]
    # ⑤ 中文子串回退（唯一命中才采用·防「西班牙人」误配「西班牙」）
    hits = [(en, v) for en, v in t.items()
            if v.get('cn') and (name in str(v['cn']) or str(v['cn']) in name)]
    if len(hits) == 1:
        return hits[0]
    # ⑥ 英文子串回退（唯一命中）
    hits2 = [(en, v) for en, v in t.items() if low and low in en.lower()]
    if len(hits2) == 1:
        return hits2[0]
    # ⑥b 🔴2026-10-30 批次4 修（今晚 5 场实测抓出·P0-5）: **反向子串** —— 表内键出现在
    #   传入名中（如表内 `Lille` ⊂ 传入 `Lille OSC` · `Lens` ⊂ `Racing Club De Lens`）
    #   原 ⑥ 只做了「传入名 ⊂ 表内键」，方向单一 → the-odds-api/prestep 的全称
    #   （`Lille OSC` / `Racing Club De Lens` / `SV 07 Elversberg`）**全部匹配不到** → N27 恒三态。
    #   取**最长命中**优先（防 `Nice` 误配 `Nicexxx`）。
    # 🔴P0-5b（2026-10-30）: **城市名黑名单** — Espanyol Barcelona 会误配 Barcelona（巴萨）
    #   → 纯城市名不能作反向子串目标（必须靠 _FULL 显式映射）
    _CITY_NOISE = {"barcelona", "madrid", "milan", "manchester", "london",
                   "munich", "rome", "lisbon", "porto", "seville", "valencia",
                   "turin", "naples", "florence", "berlin", "hamburg", "lyon", "marseille"}
    _cand3 = [(en, v) for en, v in t.items()
              if en and len(en) >= 4 and en.lower() in low
              and en.lower() not in _CITY_NOISE]
    if _cand3:
        _cand3.sort(key=lambda x: -len(x[0]))
        return _cand3[0]
    return None, None


def match(home, away):
    """双向预期进球（本场）"""
    en_h, h = find(home)
    en_a, a = find(away)
    if not h or not a:
        _miss = ('%s%s%s' % ('' if h else home, ' / ' if (not h and not a) else '',
                             '' if a else away)).strip()
        return {'ok': False, 'reason': '队伍未找到: %s' % _miss}
    res = {'ok': True, 'home': en_h, 'away': en_a,
           'home_cn': h.get('cn'), 'away_cn': a.get('cn')}
    hl, al = h.get('lg'), a.get('lg')
    if hl and al and hl.get('home_gf') is not None and al.get('away_ga') is not None:
        he = (hl['home_gf'] + al['away_ga']) / 2
        ae = (al['away_gf'] + hl['home_ga']) / 2
        res.update({'home_expect': round(he, 2), 'away_expect': round(ae, 2),
                    'total_expect': round(he + ae, 2),
                    'src': 'lg_home_away_dual'})
    elif hl and al:
        he = (hl['gf'] + al['ga']) / 2
        ae = (al['gf'] + hl['ga']) / 2
        res.update({'home_expect': round(he, 2), 'away_expect': round(ae, 2),
                    'total_expect': round(he + ae, 2),
                    'src': 'lg_all_dual(主客分离缺失·降级)'})
    else:
        res.update({'ok': False, 'reason': '至少一队无联赛数据（仅欧冠实证）·双向预期不可算'})
        res['ok'] = False
    # 🔴blend 口径（联赛+欧冠贝叶斯收缩）
    hb, ab = h.get('blend'), a.get('blend')
    if hb and ab:
        res['blend_home_expect'] = round((hb['att'] + ab['def']) / 2, 2)
        res['blend_away_expect'] = round((ab['att'] + hb['def']) / 2, 2)
        res['blend_total'] = round(res['blend_home_expect'] + res['blend_away_expect'], 2)
        res['blend_w'] = {'home': hb.get('w_ucl'), 'away': ab.get('w_ucl')}
    # 欧战实证叠加
    hu, au = h.get('ucl'), a.get('ucl')
    if hu and au:
        res['ucl_note'] = '欧冠实证: %s %d场(进%.2f失%.2f) vs %s %d场(进%.2f失%.2f)' % (
            h.get('cn') or en_h, hu['n'], hu['gf'], hu['ga'],
            a.get('cn') or en_a, au['n'], au['gf'], au['ga'])
    return res


def show(name):
    en, v = find(name)
    if not v:
        print('❌ 未找到球队: %s' % name)
        return
    print('球队档案 — %s / %s' % (en, v.get('cn') or '无中文'))
    print('  所属: %s' % ', '.join(v.get('leagues') or []))
    lg = v.get('lg')
    if lg:
        print('  【联赛层】n=%d (%s)' % (lg['n'], lg['sample']))
        print('    全期: 进 %.2f / 失 %.2f ｜ 主 %d场(进%s/失%s) ｜ 客 %d场(进%s/失%s)'
              % (lg['gf'], lg['ga'], lg['home_n'], lg['home_gf'], lg['home_ga'],
                 lg['away_n'], lg['away_gf'], lg['away_ga']))
        print('    近%d场: 进 %s / 失 %s ｜ 射正 %s/场 · xG代理 %s (覆盖%.1f%%) ｜ O2.5 %.1f%%'
              % (RECENT, lg['r50_gf'], lg['r50_ga'], lg['sot'], lg['xg'], lg['xg_cov'], lg['over25']))
    else:
        print('  【联赛层】无数据（非五大联赛球队）')
    u = v.get('ucl')
    if u:
        print('  【欧冠层】n=%d 进%.2f 失%.2f %s'
              % (u['n'], u['gf'], u['ga'], '⚠️ ' + (u['note'] or '') if u['note'] else ''))
    else:
        print('  【欧冠层】无欧冠场次（本库内）')


def show_table():
    d = _load()
    t = d['teams']
    both = [(en, v) for en, v in t.items() if v.get('lg') and v.get('ucl')]
    both.sort(key=lambda x: -x[1]['ucl']['n'])
    print('五大数据源: %s' % d['source'])
    print('总队数 %d ｜ 有联赛档案 %d ｜ 有欧冠实证 %d ｜ 两者兼有 %d'
          % (len(t), sum(1 for v in t.values() if v.get('lg')),
             sum(1 for v in t.values() if v.get('ucl')), len(both)))
    print()
    print('兼具联赛+欧冠的球队（按欧冠场次）:')
    print('  队名                联赛n  联赛进/失   主进/失    客进/失   xG代理 | 欧冠n 欧冠进/失')
    for en, v in both[:40]:
        lg, u = v['lg'], v['ucl']
        print('  %-18s %5d  %4.2f/%4.2f  %s/%s  %s/%s  %5s | %4d  %4.2f/%4.2f'
              % (en, lg['n'], lg['gf'], lg['ga'],
                 lg['home_gf'], lg['home_ga'], lg['away_gf'], lg['away_ga'],
                 lg['xg'], u['n'], u['gf'], u['ga']))
    un = d.get('unmapped_ucl') or {}
    print()
    print('欧冠库未映射队（无联赛数据·仅能欧战定性）: %d 支 → %s'
          % (len(un), ', '.join(list(un)[:15]) + (' ...' if len(un) > 15 else '')))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'show'
    if cmd == 'build':
        d = build()
        print('✅ 已生成 %s（%d 队）' % (OUT, len(d['teams'])))
        show_table()
    elif cmd == 'show':
        if len(sys.argv) > 2:
            show(sys.argv[2])
        else:
            show_table()
    elif cmd == 'match':
        if len(sys.argv) < 4:
            print('用法: match <主队> <客队>')
            return
        r = match(sys.argv[2], sys.argv[3])
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
