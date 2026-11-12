# -*- coding: utf-8 -*-
"""data_bridge.py —— 统一数据接入层（2026-09-11）
把一场比赛所需的**全部 ML 数据源**自动汇聚为一个统一特征集（供在线学习/预测/复盘），
每源独立接入 + 三态标注（ok / missing / error），缺失不臆造。

数据源清单:
  A txt        竞彩txt（本地·必得）      → ML/让球/总进球/O25反推/半全场/比分/场均进失
  B haf        HAF 主客场因子（本地表）   → 主客场 λ/胜平负/分离度
  C clubelo    实时 ELO（网络·clubelo）   → elo_h/elo_a/elo_diff
  D xg         understat xG（网络·缓存）  → xg_for/xg_against 近N场均值
  E api_fb     ⛔已停用（2026-10-06 用户决策）→ 替代: the-odds-api(赔率)/Bing News(伤停)/Odds-API(定位)
  F euro_odds  Odds-API（网络·VPN）       → 欧盘 ML/Spread水位/Totals/CS
  G h2h        H2H 历史（本地 SQL/缓存）  → 近N次交锋分布
  H news       新闻伤停（网络·VPN）        → 伤停清单文本

用法:
  python data/online_learning/data_bridge.py <txt路径> [--league 欧冠] [--net] [--json]
    --net  启用网络源（clubelo/xg/the-odds-api·默认关闭以保速度与稳定）
"""
import os, re, sys, io, json, subprocess, time
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.dirname(HERE)                 # data/
TMP = os.path.join(DATA, 'tmp')
ROOT = os.path.dirname(DATA)
sys.path.insert(0, HERE)
# 🔴stdout 包装移至 __main__（被 import 时不得重复包装·防 I/O closed 错误）
ENV = dict(os.environ, PYTHONIOENCODING='utf-8')


# ═══════════════════════════════════════════════════════════
# 统一队名多别名映射（2026-09-14升级·161中文队名/239+英文别名）
# 结构: {中文名: [英文关键词1, 英文关键词2, ...]}
# 归一化: NFKD去组合符 + 小写 + 特殊字符替换
# ═══════════════════════════════════════════════════════════
def normalize_name(name):
    """队名归一化: NFKD去组合符→小写→ø→o/ß→ss/ç→c/æ→ae/&→and/去标点空格"""
    if not name:
        return ""
    import unicodedata as _ud
    s = _ud.normalize("NFKD", str(name))
    s = "".join(c for c in s if not _ud.combining(c))
    s = s.lower()
    for _a, _b in [("ø","o"),("ö","o"),("ó","o"),("ò","o"),("ô","o"),("õ","o"),
                    ("ß","ss"),("ç","c"),("ć","c"),("č","c"),("æ","ae"),("&","and"),
                    ("š","s"),("ş","s"),("ś","s"),("ź","z"),("ż","z"),("ž","z"),
                    ("á","a"),("à","a"),("â","a"),("ã","a"),("ä","a"),("å","a"),
                    ("é","e"),("è","e"),("ê","e"),("ë","e"),("í","i"),("ì","i"),
                    ("î","i"),("ï","i"),("ú","u"),("ù","u"),("û","u"),("ü","u"),
                    ("ý","y"),("ÿ","y"),("ñ","n"),("ń","n"),("đ","d"),("ł","l")]:
        s = s.replace(_a, _b)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s

TEAM_ALIASES = {
    "AC米兰": ["AC Milan", "Milan"],
    "中日德兰": ["FC Midtjylland", "Midtjylland"],
    "乌迪内斯": ["Udinese", "Udinese Calcio"],
    "云达不莱梅": ["SV Werder Bremen", "Werder", "Werder Bremen"],
    "亚特兰大": ["Atalanta", "Atalanta BC"],
    "亨克": ["Genk", "KRC Genk"],
    "伊普斯维奇": ["Ipswich", "Ipswich Town"],
    "伍尔弗汉普顿流浪者": ["Wolverhampton", "Wolverhampton Wanderers", "Wolves"],
    "伯尔尼年轻人": ["BSC Young Boys", "YB", "Young Boys"],
    "伯恩茅斯": ["AFC Bournemouth", "Bournemouth"],
    "佛罗伦萨": ["ACF Fiorentina", "Fiorentina"],
    "克莱蒙": ["CF63", "Clermont", "Clermont Foot"],
    "克雷莫纳": ["Cremonese", "US Cremonese"],
    "兰斯": ["Reims", "Stade de Reims"],
    "凯尔特人": ["Celtic", "Celtic FC"],
    "切尔西": ["Chelsea", "Chelsea FC"],
    "利兹联": ["Leeds", "Leeds United", "Leeds Utd"],
    "利物浦": ["Liverpool", "Liverpool FC"],
    "前进之鹰": ["GAE", "Go Ahead Eagles"],
    "加拉塔萨雷": ["Galatasaray", "Galatasaray SK"],
    "勒沃库森": ["B04", "Bayer Leverkusen", "Leverkusen"],
    "勒芒": ["Le Mans", "Le Mans FC"],
    "勒阿弗尔": ["HAC", "Le Havre", "Le Havre AC"],
    "南特": ["FC Nantes", "Nantes"],
    "博德闪耀": ["Bodo/Glimt", "Bodoe/Glimt", "Bodø/Glimt"],
    "博洛尼亚": ["Bologna", "Bologna FC"],
    "卡利亚里": ["Cagliari", "Cagliari Calcio"],
    "卡拉巴赫": ["Karabakh", "Qarabag", "Qarabağ"],
    "卢多戈雷茨": ["Ludogorets", "Ludogorets Razgrad"],
    "哥本哈根": ["Copenhagen", "FC Copenhagen", "FCK"],
    "国际米兰": ["FC Internazionale", "Inter", "Inter Milan", "Internazionale"],
    "图卢兹": ["TFC", "Toulouse", "Toulouse FC"],
    "圣吉罗斯联合": ["USG", "Union SG", "Union Saint-Gilloise"],
    "埃因霍温": ["PSV", "PSV Eindhoven"],
    "埃尔切": ["Elche", "Elche CF"],
    "埃尔弗斯贝格": ["Elversberg", "SV Elversberg"],
    "埃弗顿": ["Everton", "Everton FC"],
    "塞尔塔维戈": ["Celta", "Celta Vigo", "RC Celta"],
    "塞维利亚": ["Sevilla", "Sevilla FC"],
    "塞萨洛尼基": ["PAOK", "PAOK FC", "PAOK Thessaloniki"],
    "多特蒙德": ["BVB", "Borussia Dortmund", "Dortmund"],
    "奥林匹亚科斯": ["Olympiacos", "Olympiacos FC", "Olympiakos"],
    "奥格斯堡": ["Augsburg", "FC Augsburg"],
    "奥萨苏纳": ["CA Osasuna", "Osasuna"],
    "威尼斯": ["Venezia", "Venezia FC"],
    "安德莱赫特": ["Anderlecht", "RSC Anderlecht"],
    "富勒姆": ["Fulham", "Fulham FC"],
    "尤文图斯": ["Juve", "Juventus", "Juventus FC"],
    "尼斯": ["Nice", "OGC Nice"],
    "巴列卡诺": ["Rayo", "Rayo Vallecano"],
    "巴塞尔": ["Basel", "Basel 1893", "FC Basel"],
    "巴塞罗那": ["Barca", "Barcelona", "FC Barcelona"],
    "巴拉多利德": ["Real Valladolid", "Valladolid"],
    "巴黎FC": ["PFC", "Paris FC"],
    "巴黎圣日耳曼": ["PSG", "Paris SG", "Paris Saint Germain", "Paris Saint-Germain"],
    "布伦特福德": ["Brentford", "Brentford FC"],
    "布加勒斯特星": ["FCSB", "FCSB Bucuresti", "Steaua Bucuresti"],
    "布拉加": ["Braga", "SC Braga", "Sporting Braga"],
    "布拉格斯巴达": ["Sparta", "Sparta Prague", "Sparta Praha"],
    "布拉格斯拉维亚": ["Slavia", "Slavia Prague", "Slavia Praha"],
    "布拉迪斯拉发": ["Slovan", "Slovan Bratislava"],
    "布莱顿": ["BHA", "Brighton", "Brighton & Hove Albion"],
    "布雷斯特": ["Brest", "SB29", "Stade Brestois"],
    "布鲁日": ["Club Brugge", "Club Brugge KV"],
    "帕尔马": ["Parma", "Parma Calcio"],
    "帕德博恩": ["Paderborn", "SC Paderborn"],
    "帕福斯": ["Pafos", "Pafos FC"],
    "帕纳辛奈科斯": ["PAO", "Panathinaikos", "Panathinaikos FC"],
    "弗罗西诺内": ["Frosinone", "Frosinone Calcio"],
    "弗赖堡": ["Freiburg", "SC Freiburg"],
    "恩波利": ["Empoli", "Empoli FC"],
    "托特纳姆热刺": ["Spurs", "Tottenham", "Tottenham Hotspur"],
    "拉斯帕尔马斯": ["Las Palmas", "UD Las Palmas"],
    "拉科鲁尼亚": ["Depor", "Deportivo La Coruna"],
    "拉齐奥": ["Lazio", "SS Lazio"],
    "拜仁慕尼黑": ["Bayern", "Bayern Munich", "Bayern München", "FC Bayern"],
    "摩纳哥": ["AS Monaco", "Monaco"],
    "斯图加特": ["Stuttgart", "VfB Stuttgart"],
    "斯特拉斯堡": ["RC Strasbourg", "RCSA", "Strasbourg"],
    "昂热": ["Angers", "SCO Angers"],
    "曼彻斯特城": ["Man City", "ManCity", "Manchester City"],
    "曼彻斯特联": ["Man United", "ManUtd", "Manchester United"],
    "朗斯": ["Lens", "RC Lens"],
    "本菲卡": ["Benfica", "SL Benfica"],
    "林茨": ["LASK", "LASK Linz"],
    "柏林联合": ["Union Berlin"],
    "格拉斯哥流浪者": ["Glasgow Rangers", "Rangers", "Rangers FC"],
    "格拉茨风暴": ["SK Sturm Graz", "Sturm Graz"],
    "桑坦德竞技": ["Racing Santander", "Santander"],
    "桑德兰": ["Sunderland", "Sunderland AFC"],
    "桑普多利亚": ["Sampdoria", "UC Sampdoria"],
    "梅斯": ["FC Metz", "Metz"],
    "欧塞尔": ["AJ Auxerre", "Auxerre"],
    "比利亚雷亚尔": ["Villarreal", "Villarreal CF"],
    "比尔森胜利": ["Viktoria", "Viktoria Plzen", "Viktoria Plzeň"],
    "毕尔巴鄂竞技": ["Athletic Bilbao", "Athletic Club"],
    "水晶宫": ["Crystal Palace", "Crystal Palace FC"],
    "汉堡": ["HSV", "Hamburg", "Hamburger SV"],
    "沃尔夫斯堡": ["VfL Wolfsburg", "Wolfsburg"],
    "沙尔克04": ["FC Schalke 04", "Schalke", "Schalke 04"],
    "法兰克福": ["Eintracht Frankfurt", "Frankfurt"],
    "波尔图": ["FC Porto", "Porto"],
    "波鸿": ["Bochum", "VfL Bochum"],
    "洛里昂": ["FC Lorient", "FCL", "Lorient"],
    "海拉提阿拉木图": ["FC Kairat", "Kairat", "Kairat Almaty"],
    "海登海姆": ["1. FC Heidenheim", "Heidenheim"],
    "热那亚": ["Genoa", "Genoa CFC"],
    "特拉维夫马卡比": ["Maccabi", "Maccabi Tel Aviv"],
    "特鲁瓦": ["ESTAC Troyes", "Troyes"],
    "琴斯托霍瓦": ["Rakow Czestochowa", "Raków", "Raków Częstochowa"],
    "瓦伦西亚": ["Valencia", "Valencia CF"],
    "皇家社会": ["Real Sociedad", "Sociedad"],
    "皇家贝蒂斯": ["Betis", "Real Betis"],
    "皇家马德里": ["Real Madrid", "Real Madrid CF"],
    "科莫": ["Como", "Como 1907"],
    "科隆": ["1. FC Cologne", "Cologne", "FC Cologne", "FC Köln", "Koln", "Köln"],
    "纽卡斯尔联": ["Newcastle", "Newcastle United", "Newcastle Utd"],
    "维罗纳": ["Hellas Verona", "Verona"],
    "罗马": ["AS Roma", "Roma"],
    "美因茨": ["1. FSV Mainz 05", "Mainz", "Mainz 05"],
    "考文垂": ["Coventry", "Coventry City"],
    "腓特烈斯塔": ["Fredrikstad", "Fredrikstad FK"],
    "莱万特": ["Levante", "Levante UD"],
    "莱切": ["Lecce", "US Lecce"],
    "莱加内斯": ["CD Leganes", "Leganes"],
    "莱斯特城": ["Leicester", "Leicester City"],
    "莱比锡红牛": ["Leipzig", "RB Leipzig", "RasenBallsport Leipzig"],
    "萨勒尼塔纳": ["Salernitana", "US Salernitana"],
    "萨尔茨堡红牛": ["RB Salzburg", "Red Bull Salzburg", "Salzburg"],
    "萨格勒布迪纳摩": ["Dinamo Zagreb", "GNK Dinamo", "Zagreb"],
    "萨索洛": ["Sassuolo", "US Sassuolo"],
    "葡萄牙体育": ["Sporting", "Sporting CP", "Sporting Lisbon"],
    "蒙彼利埃": ["Montpellier", "Montpellier HSC"],
    "蒙扎": ["AC Monza", "Monza"],
    "西汉姆联": ["West Ham", "West Ham United", "West Ham Utd"],
    "西班牙人": ["Espanyol", "RCD Espanyol"],
    "诺丁汉森林": ["Forest", "Nottingham Forest", "Nottm Forest"],
    "贝尔格莱德红星": ["Crvena Zvezda", "Red Star", "Red Star Belgrade"],
    "费伦茨瓦罗斯": ["FTC", "Ferencvaros", "Ferencváros"],
    "费内巴切": ["Fenerbahce", "Fenerbahçe", "Fenerbahçe SK"],
    "费耶诺德": ["Feyenoord", "Feyenoord Rotterdam"],
    "赫塔费": ["Getafe", "Getafe CF"],
    "赫尔城": ["Hull", "Hull City"],
    "赫罗纳": ["Girona", "Girona FC"],
    "达姆施塔特": ["Darmstadt", "SV Darmstadt 98"],
    "那不勒斯": ["Napoli", "SSC Napoli"],
    "都灵": ["Torino", "Torino FC"],
    "里尔": ["LOSC Lille", "Lille"],
    "里昂": ["Lyon", "OL", "Olympique Lyon", "Olympique Lyonnais"],
    "门兴格拉德巴赫": ["Borussia Mönchengladbach", "Gladbach", "Monchengladbach"],
    "阿尔克马尔": ["AZ", "AZ Alkmaar"],
    "阿拉维斯": ["Alaves", "Deportivo Alaves"],
    "阿斯顿维拉": ["Aston Villa", "Villa"],
    "阿森纳": ["Arsenal", "Arsenal FC"],
    "阿贾克斯": ["AFC Ajax", "Ajax"],
    "雅典AEK": ["AEK", "AEK Athens"],
    "雷恩": ["Rennes", "SRFC", "Stade Rennais"],
    "霍芬海姆": ["Hoffenheim", "TSG Hoffenheim"],
    "顿涅茨克矿工": ["FC Shakhtar", "Shakhtar", "Shakhtar Donetsk"],
    "马尔默": ["Malmo", "Malmo FF", "Malmö", "Malmö FF"],
    "马德里竞技": ["Atletico", "Atletico Madrid", "Atlético", "Atlético Madrid"],
    "马拉加": ["Malaga", "Malaga CF"],
    "马略卡": ["Mallorca", "RCD Mallorca"],
    "马赛": ["Marseille", "OM", "Olympique Marseille"],
}

# 🔴2026-09-15 workbuddy修复: 补充常用**中文简称**（原表只收全称 → 中文txt用"皇马/巴萨/马竞"等简称时
#   normalize_name 去非 ASCII 得空串 → haf/h2h/the_odds_api/clubelo/news 恒失配）。
TEAM_ALIASES.update({
    # 西甲
    "皇马": ["Real Madrid", "Real Madrid CF"], "巴萨": ["Barcelona", "FC Barcelona", "Barca"],
    "马竞": ["Atletico Madrid", "Atletico de Madrid"], "塞维利亚": ["Sevilla", "Sevilla FC"],
    "贝蒂斯": ["Real Betis", "Betis"], "皇家社会": ["Real Sociedad"], "毕尔巴鄂": ["Athletic Bilbao", "Athletic Club"],
    "比利亚雷亚尔": ["Villarreal", "Villarreal CF"], "塞尔塔": ["Celta Vigo", "Celta de Vigo"],
    "赫塔菲": ["Getafe", "Getafe CF"], "奥萨苏纳": ["Osasuna", "CA Osasuna"],
    "阿拉维斯": ["Alaves", "Deportivo Alaves"], "赫罗纳": ["Girona", "Girona FC"],
    "巴列卡诺": ["Rayo Vallecano"], "西班牙人": ["Espanyol", "Espanyol Barcelona"],
    "莱万特": ["Levante", "Levante UD"], "格拉纳达": ["Granada", "Granada CF"],
    "拉斯帕尔马斯": ["Las Palmas"], "埃瓦尔": ["Eibar"], "加的斯": ["Cadiz"],
    # 英超
    "曼联": ["Man United", "Manchester United"], "曼城": ["Man City", "Manchester City"],
    "利物浦": ["Liverpool"], "阿森纳": ["Arsenal"], "切尔西": ["Chelsea"],
    "热刺": ["Tottenham", "Spurs"], "纽卡": ["Newcastle", "Newcastle United"],
    "阿斯顿维拉": ["Aston Villa", "Villa"], "埃弗顿": ["Everton"], "西汉姆": ["West Ham"],
    "布莱顿": ["Brighton"], "水晶宫": ["Crystal Palace"], "狼队": ["Wolves", "Wolverhampton"],
    "富勒姆": ["Fulham"], "布伦特福德": ["Brentford"], "诺丁汉森林": ["Nottingham", "Nottingham Forest"],
    "伯恩茅斯": ["Bournemouth"], "莱斯特城": ["Leicester", "Leicester City"],
    "南安普顿": ["Southampton"], "利兹联": ["Leeds", "Leeds United"],
    # 意甲
    "尤文": ["Juventus", "Juventus FC"], "国米": ["Inter", "Inter Milan"], "国际米兰": ["Inter", "Inter Milan"],
    "米兰": ["AC Milan", "Milan"], "那不勒斯": ["Napoli"], "拉齐奥": ["Lazio"],
    "亚特兰大": ["Atalanta"], "佛罗伦萨": ["Fiorentina"], "博洛尼亚": ["Bologna"],
    "都灵": ["Torino"], "乌迪内斯": ["Udinese"], "热那亚": ["Genoa"], "维罗纳": ["Verona"],
    # 德甲
    "拜仁": ["Bayern", "Bayern Munich"], "多特": ["Dortmund", "Borussia Dortmund"],
    "莱比锡": ["RB Leipzig", "Leipzig"], "勒沃库森": ["Leverkusen", "Bayer Leverkusen"],
    "法兰克福": ["Eintracht Frankfurt", "Frankfurt"], "门兴": ["Monchengladbach", "Borussia Monchengladbach"],
    "沃尔夫斯堡": ["Wolfsburg"], "斯图加特": ["Stuttgart"], "弗赖堡": ["Freiburg"],
    "不莱梅": ["Werder Bremen", "Bremen"], "霍芬海姆": ["Hoffenheim"], "美因茨": ["Mainz"],
    "科隆": ["Cologne", "FC Koln"], "柏林联合": ["Union Berlin"],
    # 法甲
    "巴黎": ["Paris", "Paris Saint-Germain", "PSG"], "大巴黎": ["PSG", "Paris Saint-Germain"],
    "摩纳哥": ["Monaco", "AS Monaco"], "里昂": ["Lyon", "Olympique Lyon"],
    "里尔": ["Lille", "LOSC Lille"], "雷恩": ["Rennes"], "尼斯": ["Nice", "OGC Nice"],
    "朗斯": ["Lens", "RC Lens"], "南特": ["Nantes"], "蒙彼利埃": ["Montpellier"],
    "斯特拉斯堡": ["Strasbourg"], "布雷斯特": ["Brest"], "图卢兹": ["Toulouse"],
})

# 归一化后的反向索引: {归一化英文名: 中文名}
_ALIAS_INDEX = {}
for _cn, _ens in TEAM_ALIASES.items():
    for _e in _ens:
        _k = normalize_name(_e)
        if _k and _k not in _ALIAS_INDEX:
            _ALIAS_INDEX[_k] = _cn

def cn_to_en_keywords(cn_name):
    """中文名→归一化英文关键词列表（用于模糊匹配）

    🔴🔴2026-10-31 根治「为什么出现 3/8 / 4/8 缺源」（case301 比利亚雷亚尔实抓）:
      原实现 `TEAM_ALIASES.get(cn_name, [cn_name])` 是**精确查找** ——
      txt 写**简称**（如「比利亚雷」）而表键是全称（「比利亚雷亚尔」）→ get 返回 None
      → 回退成 `[cn_name]`（**中文**）→ 拿去匹配英文事件名 → **必然失败**
      → 连锁: euro_odds / h2h / xg / bzz_injury 四源 missing → 3/8
      （而 `snapshot_save.cn2en_list` 有「精确→子串→简称」三级回退，能正常转出 Villarreal
        → 两套转换器覆盖度不一致 = 各源表现不一致的根源）

      修法: 精确查不到时**回退 cn2en_list**（含子串/简称回退）→ 一处改·六源受益。
    """
    if not cn_name:
        return []
    ens = TEAM_ALIASES.get(cn_name)
    if not ens:
        # 🔴 精确未命中 → 回退统一入口（子串/简称回退）·延迟 import 防循环依赖
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), 'tmp'))
            import snapshot_save as _ss
            ens = list(_ss.cn2en_list(cn_name) or [])
        except Exception:
            ens = []
    if not ens:
        ens = [cn_name]          # 最终兜底（保留原名·中文名至少可用于本地表精确匹配）
    return [normalize_name(e) for e in ens if normalize_name(e)]

def match_team(name, candidates, threshold=0.6):
    """在候选队名中匹配: 精确→包含→前缀4字符→返回(候选, 置信度)"""
    if not name or not candidates:
        return None, 0.0
    nk = normalize_name(name)
    if not nk:
        return None, 0.0
    # 1. 精确匹配
    for c in candidates:
        if normalize_name(c) == nk:
            return c, 1.0
    # 2. 别名索引精确匹配
    cn = _ALIAS_INDEX.get(nk)
    if cn:
        for c in candidates:
            if normalize_name(c) in [normalize_name(e) for e in TEAM_ALIASES.get(cn, [])]:
                return c, 0.95
    # 3. 包含匹配
    for c in candidates:
        ck = normalize_name(c)
        if ck and (nk in ck or ck in nk):
            return c, 0.8
    # 4. 前缀4字符匹配
    if len(nk) >= 4:
        for c in candidates:
            ck = normalize_name(c)
            if ck and len(ck) >= 4 and (nk[:4] == ck[:4]):
                return c, 0.65
    return None, 0.0



def _run(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                           errors='replace', env=ENV, timeout=timeout, cwd=ROOT)
        return r.returncode, (r.stdout or '') + (r.stderr or '')
    except subprocess.TimeoutExpired:
        return -9, 'timeout'
    except Exception as e:
        return -1, str(e)[:120]


# ---------- 队名提取 ----------
def extract_teams(txt_path):
    """从 txt 解析主客队名 → (home, away, head_首行)

    🔴2026-09-16 修复(P0·五源连锁失效根因): 原实现只读**第 1 行**
      → 遇「两行式 txt」队名恒 None:
          行1「赛事：西甲 周二008」
          行2「对阵：阿拉维斯(主) VS 巴伦西亚(客)」   ← 对阵在第2行·行1无队名
      → 依赖队名的 5 个源全部 missing(非数据源故障):
          B1 euro_odds(源B1 Odds-API) / B7 the_odds_api / h2h / clubelo / news（api-football 已停用 2026-10-06）
      → 连锁后果: V3 水位联动、V5 跨市场分歧、V6 盘口联动(修正54-58 四象限/剪刀差/卡位/退盘)
        全部「无数据·不触发」(实测 alaves008 case183)。
      现改为在**前 5 行**内检索对阵行；单行式 txt(行1 含完整对阵)行为不变。
      兼容全角/半角括号: A(主) / A（主）。
    """
    try:
        lines = open(txt_path, encoding='utf-8').read().split('\n')
    except Exception:
        return None, None, None
    head = lines[0] if lines else ''
    block = '\n'.join(lines[:5])
    m = re.search(r'([^：:\s]+)\s*[（(]主[）)]\s*(?:VS|vs|对)\s*([^(\s（]+)', block)
    if m:
        return m.group(1).strip(), m.group(2).strip(), head
    # 兼容 "主队 VS 客队" 或 "A(主) VS B(客)"
    m2 = re.search(r'([^\s：:]+)\s*VS\s*([^\s(（]+)', block)
    if m2:
        return m2.group(1).strip(), m2.group(2).strip(), head
    return None, None, head


def extract_match_date(txt_path):
    """从 txt 第二行提取比赛时间 → (北京日期, 估算UTC日期)  2026-09-11 00:45 北京 → UTC 2026-09-10"""
    try:
        lines = open(txt_path, encoding='utf-8').read().split('\n')[:4]
    except Exception:
        return None, None
    for ln in lines:
        m = re.search(r'(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})', ln)
        if m:
            d, hh = m.group(1), int(m.group(2))
            try:
                import datetime as _dt
                bj = _dt.datetime.strptime('%s %02d:%s' % (d, hh, m.group(3)), '%Y-%m-%d %H:%M')
                utc = bj - _dt.timedelta(hours=8)
                return bj.strftime('%Y-%m-%d'), utc.strftime('%Y-%m-%d')
            except Exception:
                return d, d
    return None, None


# ---------- 各源 ----------
def src_txt(txt_path):
    import txt_features as TF
    f, d = TF.extract(txt_path)
    if not f:
        return 'error', {}, (d or {}).get('error', '提取失败')
    return ('ok' if d.get('complete') else 'missing'), {'features': f, 'detail': d.get('detail', {})}, \
        ('' if d.get('complete') else '缺字段: %s' % d.get('missing'))


def src_haf(home, away):
    tbl = os.path.join(TMP, 'homeaway_table.json')
    if not os.path.exists(tbl):
        return 'missing', {}, 'homeaway_table.json 不存在'
    try:
        t = json.load(open(tbl, encoding='utf-8'))
    except Exception as e:
        return 'error', {}, str(e)[:80]
    teams = t.get('_teams') if isinstance(t, dict) else None
    teams = teams or t
    def find(name):
        if not name:
            return None
        if name in teams:
            return teams[name]
        # 🔴2026-09-15 workbuddy修复: 中文队名先转英文关键词(别名)再与英文档案键匹配
        cands = [c for c in (cn_to_en_keywords(name) or []) if c] or [normalize_name(name)]
        for k, v in teams.items():
            if k == '_meta' or not isinstance(k, str):
                continue
            kn = normalize_name(k)
            for c in cands:
                cn_ = normalize_name(c)
                if cn_ and (cn_ == kn or (len(cn_) >= 4 and cn_[:5] == kn[:5]) or cn_ in kn or kn in cn_):
                    return v
        return None
    h, a = find(home), find(away)
    meta = t.get('_meta', {}) if isinstance(t, dict) else {}
    if not h and not a:
        return 'missing', {'n_teams': len([k for k in teams if k != '_meta']), 'league_base': meta.get('联赛基准', {})}, \
            '两队不在 HAF 档案（%d 队·联赛基准可用）' % len([k for k in teams if k != '_meta'])
    return 'ok', {'home': h, 'away': a, 'league_base': meta.get('联赛基准', {})}, '' if (h and a) else '仅一队命中'


def src_clubelo(home, away):
    cache = [f for f in os.listdir(TMP) if f.startswith('clubelo_') and f.endswith('.json')]
    if not cache:
        rc, out = _run([sys.executable, os.path.join(TMP, 'fetch_clubelo.py')], timeout=90)
        cache = [f for f in os.listdir(TMP) if f.startswith('clubelo_') and f.endswith('.json')]
        if not cache:
            return 'error', {}, 'clubelo 抓取失败（网络/代理）: %s' % out[-80:]
    path = os.path.join(TMP, sorted(cache)[-1])
    try:
        data = json.load(open(path, encoding='utf-8'))
    except Exception as e:
        return 'error', {}, str(e)[:80]
    # 结构: {'date':..., 'leagues': {中文联赛: {'teams': [{'name','elo','rank'},...]}}}
    flat = {}
    for lg, lv in (data.get('leagues') or {}).items():
        for it in (lv.get('teams') or []) if isinstance(lv, dict) else []:
            nm = (it.get('name') or '').strip()
            if nm:
                flat[nm.lower()] = it
    # 🔴2026-09-14 升级: 使用统一多别名映射+归一化（原38条单值→164中文/395英文别名）
    def _clubelo_pick(name):
        if not name:
            return None
        # 1. 归一化精确匹配
        nk = normalize_name(name)
        if nk in flat:
            return flat[nk]
        # 2. 多别名匹配
        for kw in cn_to_en_keywords(name):
            if kw in flat:
                return flat[kw]
        # 3. 包含匹配（🔴2026-10-31 修同型 [:4] 截断: 原 'real'[:4] 会把
        #    Real Sociedad 当 Real Madrid → 改双向子串 + 长度差≤4 + 前缀/后缀约束）
        for k, v in flat.items():
            for cand in [nk] + [normalize_name(x) for x in (cn_to_en_keywords(name) or [])]:
                if not cand or len(cand) < 4:
                    continue
                if cand == k:
                    return v
                if (len(cand) - len(k)) <= 4 and (k in cand or cand in k):
                    return v
        return None
    h, a = _clubelo_pick(home), _clubelo_pick(away)
    if not h and not a:
        return 'missing', {'file': os.path.basename(path), 'n_teams': len(flat)}, \
            ('clubelo 无该队档案（仅五大 Level1·%d 队·**非队名问题**；队名候选: %s）'
             % (len(flat), ','.join(list(cn_to_en_keywords(home))[:2]
                                   + list(cn_to_en_keywords(away))[:2])))
    def elo(x):
        return x.get('elo') if isinstance(x, dict) else None
    return 'ok', {'elo_home': elo(h), 'elo_away': elo(a), 'file': os.path.basename(path)}, \
        '' if (h and a) else '仅一队匹配'


def src_xg(home, away):
    """🔴2026-10-13 审计修复(P2·假数据): 原实现**完全忽略 home/away** → 任何比赛都返回
    同一份 understat 输出（实测 4 场不同比赛均返回「EPL Arsenal 3-0 Coventry」）→
    表现为"有数据"实为无效 → **比三态标注更危险**（会造成"xG 已接入"假象）。
    修复: 输出须**命中本场任一队名（中文→英文候选）**，否则返回 missing（三态）。
    """
    script = os.path.join(TMP, 'understat_xg.py')
    if not os.path.exists(script):
        return 'missing', {}, 'understat_xg.py 不存在'
    rc, out = _run([sys.executable, script], timeout=90)
    if rc != 0:
        return 'error', {}, 'understat 执行失败（网络/代理）: %s' % out[-100:]
    # 🔴防「返回无关场次」: 输出须命中本场队名（TEAM_ALIASES 中文→英文候选 + 原名）
    _cands = []
    for _n in (home, away):
        # 🔴2026-10-31 统一队名入口（原自写 TEAM_ALIASES.get 精确匹配 →
        #   「比利亚雷」等**简称**查不到 → 候选缺该队 → 误判「未命中」·与主因同源）
        for _e in (cn_to_en_keywords(str(_n)) or []):
            _e = str(_e).strip()
            if _e and not re.search(r'[\u4e00-\u9fff]', _e):
                _cands.append(_e)
        if _n and not re.search(r'[\u4e00-\u9fff]', str(_n)):
            _cands.append(str(_n))
    _lo = out.lower()
    _hit = [c for c in _cands if len(c) >= 4 and c.lower() in _lo]
    if not _hit:
        # 🔴2026-10-31 归因修正（数据源专项审计）: 候选已转出 → **队名映射没问题**·
        #   真实原因是 understat **未覆盖该队/该联赛（仅五大·需本季已开赛）**。
        #   旧文案「未命中本场队名」会让审计误判为队名 bug（排查方向全错）。
        if not _cands:
            return 'missing', {}, '队名解析失败（中文名无英文候选·本地表+联网兜底均未命中）'
        return 'missing', {}, ('understat 无该队数据（仅覆盖五大·需本季已开赛；'
                               '队名已正确转出: %s）' % ','.join(_cands[:3]))
    return 'ok', {'output': out[-800:], 'matched': _hit[:3]}, ''


def src_api_fb(date_str, home=None, away=None):
    """🔴已停用（2026-10-06 用户决策：「api football 已停用，用现有数据源替代」·从数据链完全剔除）

    原职责 → 现有源替代映射（保证数据链完整）:
      fixtures?date 定位 fixture id  → Odds-API get_events(eventId) / the-odds-api current
      odds 13 家赔率                 → the-odds-api（源B7·21-32 家·market_consensus）
      injuries 本场伤停               → Bing News（SL-news-crawl·唯一主伤停源）
      h2h 端点                       → fixture_cache / Matches.csv / SL-history-analyzer
      predictions 官方模型概率        → ⚪ 无替代（三态标注·不再有官方概率源）
      Form5 近期战绩 / lineups 首发    → ⚪ 无替代（三态标注）
    """
    return 'missing', {}, ('api-football 已停用（2026-10-06 用户决策）·'
                           '替代: the-odds-api 赔率 / Bing News 伤停 / Odds-API 赛事定位 / fixture_cache H2H')



def src_h2h(home, away):
    """H2H 从 Matches.csv（22 万场）尽力匹配（英文队名·中文需别名）"""
    m = os.path.join(DATA, 'Matches.csv')
    if not os.path.exists(m):
        return 'missing', {}, 'Matches.csv 不在位'
    # 🔴2026-09-14 升级: 使用统一多别名映射+归一化
    def _h2h_en(n):
        if not n:
            return None
        kws = cn_to_en_keywords(n)
        # 返回第一个别名作为主匹配词
        return kws[0] if kws else normalize_name(n)
    h, a = _h2h_en(home), _h2h_en(away)
    if not (h and a):
        return 'missing', {}, '队名解析失败（中文名无英文候选·本地表+联网兜底均未命中）'
    import csv

    # 🔴🔴2026-10-31 P0 修复（数据源专项审计实抓·静默失效）:
    #   原实现 `hs = normalize_name(_h2h_en(home))[:5]` —— 只取**第一个**别名再 **[截断 5 字符]**
    #   → 'AFC Ajax' → 'afcajax' → 'afcaj' → `'afcaj' in 'ajax'` = **False**
    #   → **凡第一个别名带 AFC/FC/CF 前缀的队，h2h 永久「未匹配」且归因写成「别名未覆盖」**
    #   实测: Ajax/Feyenoord 在 Matches.csv 有 1568 场（N1）却报未匹配。
    #   修: 用**全部候选**（含原名）逐个比对·不做 [:5] 截断（截断本身还会让 'Bournemouth'→'bourn' 误配）
    def _kws(n):
        out = [normalize_name(x) for x in (cn_to_en_keywords(n) or [])]
        out.append(normalize_name(n))
        # 去空 / 去重 / 短词(<3)丢弃（防 'fc'、'as' 这类误配）
        return [x for x in dict.fromkeys(out) if x and len(x) >= 3]

    h_kws, a_kws = _kws(home), _kws(away)
    if not h_kws or not a_kws:
        return 'missing', {}, '队名解析失败（候选为空）'

    # 🔴🔴2026-10-31 二次修复（数据源专项·跨源**拼写口径差异**）:
    #   实测 ① `Espanol`(库·1个n) vs `Espanyol`(官方·2个n) → 差 1 字符
    #        ② `Molde`(库) vs `molde fk`(候选·带后缀) → 单向 `k in H` 失配·需**反向**
    #   → `_hit()`: ①正向子串 ②反向子串(len≥4) ③**编辑距离≤1**(len≥5)
    def _ed1(a, b):
        """Levenshtein 距离是否 ≤1（等长替换 / 差1插入删除）"""
        if a == b:
            return True
        la, lb = len(a), len(b)
        if abs(la - lb) > 1:
            return False
        if la == lb:
            return sum(1 for x, y in zip(a, b) if x != y) <= 1
        if la > lb:
            a, b = b, a
        i = 0
        while i < len(a) and a[i] == b[i]:
            i += 1
        return a[i:] == b[i + 1:]

    def _hit(kws, T):
        if not T:
            return False
        for k in kws:
            if not k:
                continue
            if k in T:                                   # ①正向
                return True
            # ②反向：**必须**是前缀/后缀 **且** 长度差 ≤4
            #   （无约束的反向会把 'milan' 套进 'inter milan'、'barcelona' 套进
            #     'espanyol barcelona' → 实测把 AC米兰/巴萨 当国米/西班牙人）
            if (len(k) >= 4 and T in k and (len(k) - len(T)) <= 4
                    and (k.startswith(T) or k.endswith(T))):
                return True
            if len(k) >= 5 and len(T) >= 5 and _ed1(k, T):   # ③拼写差 1 字符
                return True
        return False

    rows = []
    try:
        with open(m, encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                H = normalize_name(r.get('HomeTeam') or '')
                A = normalize_name(r.get('AwayTeam') or '')
                if not (H and A):
                    continue
                if (_hit(h_kws, H) and _hit(a_kws, A)) or (_hit(h_kws, A) and _hit(a_kws, H)):
                    rows.append((r.get('MatchDate', ''), r.get('HomeTeam'), r.get('AwayTeam'),
                                 r.get('FTHome'), r.get('FTAway')))
    except Exception as e:
        return 'error', {}, str(e)[:80]
    if not rows:
        # 🔴归因改准: Matches.csv 覆盖 38 个联赛（含 N1 荷甲 / NOR 挪超 / JAP / CHN 等）
        #   → 真实原因是「两队无交锋记录」或「该联赛不在库内」·不再甩锅给「别名未覆盖」
        return 'missing', {}, ('Matches.csv 无该对阵记录（库含 38 联赛/23 万场·'
                               '非队名问题·候选: %s | %s）'
                               % (','.join(h_kws[:3]), ','.join(a_kws[:3])))
    rows.sort(key=lambda x: x[0])
    last = rows[-8:]
    return 'ok', {'n_matches': len(rows), 'recent': last}, ''


def _open_dual(url, timeout=30, headers=None):
    """🔴2026-09-16 修复: **直连优先 + 代理回退**（与 source_health_check 同口径）。

    原 src_news / src_euro_odds **硬编码走代理** 127.0.0.1:7897 → 未开 VPN 时两源恒
    error（实测 WinError 10061 连接被拒）→ 学习层特征缺 2 源（完整度 5/8 → 本可 7/8）。
    现先直连、失败再走代理，与「VPN 默认开 + 直连优先」铁律一致。
    """
    import urllib.request as _ur
    hdr = headers or {'User-Agent': 'Mozilla/5.0'}
    proxy = os.environ.get('HTTPS_PROXY') or 'http://127.0.0.1:7897'
    last = None
    for _ph, _to in ((proxy, timeout), (None, 4)):   # 🔴2026-10-31 代理优先 → 直连回退4s（直连 SSL 超时26s/代理1.2s）
        try:
            # 🔴2026-09-23 修复: 无参 build_opener() 继承系统代理(7897) → 非真直连
            op = (_ur.build_opener(_ur.ProxyHandler({})) if _ph is None
                  else _ur.build_opener(_ur.ProxyHandler({'https': _ph, 'http': _ph})))
            return op.open(_ur.Request(url, headers=hdr), timeout=_to)
        except Exception as _e:
            last = _e
    raise last


def _fetch_dual_text(url, timeout=30, headers=None, validate=None, prefer_proxy=False):
    """🔴2026-10-09 新增: **带内容校验**的双通道取文本（直连优先 → 代理回退）。

    背景（实测 4/4 场失效）: Bing News 直连返回 **HTTP 200 + HTML 搜索页**（非 RSS）→
    `_open_dual` 只判「无异常」→ 视为成功 → **不回退代理** → `src_news` 恒 `missing`
    → 「伤停唯一源」实际断链。`validate(raw_bytes)->bool` 校验内容，不通过则继续下一通道。
    返回 (text, 通道名)；双通道均失败/校验不通过 → 抛异常。
    """
    import urllib.request as _ur
    hdr = headers or {'User-Agent': 'Mozilla/5.0'}
    proxy = os.environ.get('HTTPS_PROXY') or 'http://127.0.0.1:7897'
    last = None
    # 🔴2026-10-09: prefer_proxy —— Bing 直连返 HTML(非RSS)·Google 直连必超时(25s)
    #   → 对这两源应代理优先，避免每场白等超时（实测 4 场 × 25s 拖垮执行）
    _order = ((('代理', proxy, timeout), ('直连', None, 4)) if prefer_proxy
              else (('代理', proxy, timeout), ('直连', None, 4)))   # 🔴2026-10-31 两分支均代理优先·直连 4s 快速失败
    for _nm, _ph, _to in _order:
        try:
            op = (_ur.build_opener(_ur.ProxyHandler({})) if _ph is None
                  else _ur.build_opener(_ur.ProxyHandler({'https': _ph, 'http': _ph})))
            with op.open(_ur.Request(url, headers=hdr), timeout=_to) as r:
                raw = r.read()
            if validate is not None and not validate(raw):
                last = ValueError('%s 通道返回非预期内容(校验未通过)' % _nm)
                continue
            return raw.decode('utf-8', errors='replace'), _nm
        except Exception as _e:
            last = _e
    raise last if last is not None else RuntimeError('双通道均失败')


def src_news(home, away):
    """Bing News 伤停搜索（伤停唯一主源·🔴2026-10-06 替代 api-football injuries）

    🔴2026-10-09 修复 + 增强:
      ①修复: 原实现用 `_open_dual`（仅判"无异常"）→ Bing 直连返回 HTTP 200 + **HTML 搜索页**
        被当成功 → 不回退代理 → 恒 `missing`（**实测 4/4 场失效**·伤停链实际断裂）
        → 改用 `_fetch_dual_text(validate=XML/item 校验)`
      ②增强: 并入 **Google News RSS**（代理通道实测 81 条 vs Bing 2 条）→ 覆盖显著提升
    🔴诚实边界: 产出仍为**文本级**（标题清单），**非结构化位置** →
      铁则32 位置级影响分须由 LLM 从标题/正文解析，或手工构造「位置,重要性」传给 injury_impact.py
    """
    import urllib.parse as _up, re as _re
    if not (home and away):
        return 'missing', {}, '队名缺失'
    q = _up.quote('%s vs %s injury team news' % (home, away))
    _srcs = [('Bing', 'https://www.bing.com/news/search?q=%s&format=rss' % q),
             ('Google', 'https://news.google.com/rss/search?q=%s' % q)]
    titles, chans, errs = [], [], []
    for _nm, _u in _srcs:
        try:
            xml, _ch = _fetch_dual_text(
                _u, timeout=25, prefer_proxy=True,
                validate=lambda b: (b'<item>' in b) or (b'<?xml' in b))
            items = _re.findall(r'<item>(.*?)</item>', xml, _re.S)
            for it in items[:10]:
                t = _re.search(r'<title>(.*?)</title>', it, _re.S)
                if t:
                    titles.append(_re.sub(r'<[^>]+>', '', t.group(1))[:120])
            chans.append('%s/%s/%d条' % (_nm, _ch, len(items)))
        except Exception as e:
            errs.append('%s:%s' % (_nm, str(e)[:40]))
    if not titles:
        return 'missing', {}, '无结果（%s）' % ('; '.join(errs) or '两源均 0 条')
    injury_hits = [x for x in titles
                   if _re.search(r'(?i)injur|doubt|suspend|out of|miss|fitness|lineup', x)]
    return 'ok', {'n': len(titles), 'injury_related': len(injury_hits),
                  'sources': chans, 'titles': injury_hits or titles[:5]}, ''


def src_bzz_injury(home, away, date_str=None):
    """\U0001f5342026-10-09 新增（源B8·用户决策①）: **Bzzoiro 结构化伤停**（替代 api-football injuries）

    为什么: api-football 停用后伤停降级为 Bing/Google News **文本标题** → 铁则32 的位置级影响分
    只能靠 LLM 猜。Bzzoiro 的 `teams/{id}/squad/` 给出 `position/availability/injury_type/
    injury_expected_return` → **位置级确定性输入**（G/D/M/F → 门将/中后卫/后腰/前锋）。
    \U0001f534 News 源**保留**作交叉验证（两者并列·不互斥）。
    \U0001f534 三态: ok（有结构化结果）/ missing（未定位或两队无缺阵）/ error（接口异常）。
    """
    import datetime as _dt
    try:
        _bzd = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tmp')
        if _bzd not in sys.path:
            sys.path.insert(0, _bzd)
        import bzzoiro_fetch as BZ
    except Exception as e:
        return 'error', {}, 'bzzoiro_fetch 不可用: %s' % str(e)[:60]
    try:
        _d0 = str(date_str or '')[:10] or _dt.datetime.utcnow().strftime('%Y-%m-%d')
        try:
            _dt0 = _dt.datetime.strptime(_d0, '%Y-%m-%d')
        except Exception:
            _dt0 = _dt.datetime.utcnow()
        f0 = (_dt0 - _dt.timedelta(days=5)).strftime('%Y-%m-%d')
        f1 = (_dt0 + _dt.timedelta(days=12)).strftime('%Y-%m-%d')
        fi = BZ.five_ids()
        idx = {}
        for _lid in fi.values():
            _st, _j = BZ.getj('events/?league=%s&date_from=%s&date_to=%s' % (_lid, f0, f1))
            for x in ((_j.get('results') if isinstance(_j, dict) else _j) or []):
                for tk, nk in (('home_team_id', 'home_team'), ('away_team_id', 'away_team')):
                    if x.get(tk) and x.get(nk):
                        idx[str(x[nk]).lower()] = (x.get(tk), x.get(nk))
        def _find(nm):
            # 🔴2026-10-31 统一队名入口（原只拿**中文原名**匹配 Bzzoiro 的**英文索引**
            #   → 「比利亚雷」vs 'villarreal cf' 恒失败 → 整个伤停源 missing·与主因同源）
            _cands = [str(c).lower().strip() for c in (cn_to_en_keywords(str(nm or '')) or [])
                      if str(c).strip()]
            if not _cands:
                return None
            for n in _cands:                      # ① 精确
                if n in idx:
                    return idx[n]
            for n in _cands:                      # ② 子串（≥4 字符防 'man' 类误配）
                if len(n) < 4:
                    continue
                for k, v in idx.items():
                    if n in k or k in n:
                        return v
            return None
        out = {}
        for side, nm in (('home', home), ('away', away)):
            hit = _find(nm)
            if not hit:
                out[side] = {'team': nm, 'found': False, 'out_n': 0, 'players': []}
                continue
            pl = BZ.squad(hit[0]) or []
            bad = [p for p in pl
                   if str(p.get('availability')).lower() not in ('available', 'none', '')]
            out[side] = {'team': hit[1], 'team_id': hit[0], 'found': True,
                         'squad_n': len(pl), 'out_n': len(bad),
                         'players': [{'name': p.get('name'), 'pos': p.get('position'),
                                      'pos_cn': BZ.POSMAP.get(str(p.get('position') or '').upper(), '未知'),
                                      'availability': p.get('availability'),
                                      'injury_type': p.get('injury_type'),
                                      'expected_return': p.get('injury_expected_return')}
                                     for p in bad]}
        _found = any(v.get('found') for v in out.values())
        _nout = sum(int(v.get('out_n') or 0) for v in out.values())
        if not _found:
            return 'missing', out, '两队均未在 Bzzoiro 赛事索引中定位'
        if _nout == 0:
            return 'ok', out, '两队均无缺阵记录（或未刷新）'
        return 'ok', out, ''
    except Exception as e:
        return 'error', {}, 'Bzzoiro 查询失败: %s' % str(e)[:70]


LEAGUE_SLUG = {'西甲': 'spain-laliga', 'SP1': 'spain-laliga', '英超': 'england-premier-league', 'E0': 'england-premier-league',
               '意甲': 'italy-serie-a', 'I1': 'italy-serie-a', '德甲': 'germany-bundesliga', 'D1': 'germany-bundesliga',
               '法甲': 'france-ligue-1', 'F1': 'france-ligue-1',
               # 🔴2026-10-31 并入用户 691 队/107 联赛映射表（slug 全部经 /leagues 实测·禁猜）
               #   二级联赛 + 欧战高频小联赛（原仅五大 10 条 → 扩到 34 条）
               '英冠': 'england-championship', '西乙': 'spain-laliga-2', '意乙': 'italy-serie-b', '德乙': 'germany-2-bundesliga', '法乙': 'france-ligue-2', '荷甲': 'netherlands-eredivisie', '葡超': 'portugal-liga-portugal', '比甲': 'belgium-first-division-a', '苏超': 'scotland-premiership', '捷克': 'czechia-1-liga', '克罗地亚': 'croatia-hnl', '挪威': 'norway-eliteserien', '瑞典': 'sweden-allsvenskan', '丹麦': 'denmark-superligaen', '瑞士': 'switzerland-super-league', '希腊': 'greece-super-league', '奥地利': 'austria-bundesliga', '乌克兰': 'ukraine-premier-league', '俄罗斯': 'russia-premier-league', '波兰': 'poland-ekstraklasa', '塞尔维亚': 'serbia-super-liga', '巴甲': 'brazil-brasileiro-serie-a', '中超': 'china-chinese-super-league', '沙特': 'saudi-arabia-saudi-professional-league',
               }
# 🔴2026-09-16 清洁: key 外部化(防硬编码/泄露)——解析优先级
#   ① 环境变量 ODDS_API_KEY  ② data/tmp/api_keys.json 的 odds_api  ③ 内联回退(向后兼容·不破坏现网)
_ODDS_API_KEY_FALLBACK = '<REDACTED_HEX>'


def _resolve_odds_key():
    _k = (os.environ.get('ODDS_API_KEY') or '').strip()
    if _k:
        return _k
    _d = os.path.dirname(os.path.abspath(__file__))
    for _p in (os.path.join(_d, '..', 'tmp', 'api_keys.json'), os.path.join(_d, 'api_keys.json')):
        try:
            import json as _j
            _v = _j.load(open(os.path.abspath(_p), encoding='utf-8')).get('odds_api')
            if _v:
                return str(_v).strip()
        except Exception:
            continue
    return _ODDS_API_KEY_FALLBACK


ODDS_API_KEY = _resolve_odds_key()


def _pick_fixture(cands, date_str=None):
    """从同名候选赛事中选出本场 → 优先与 date_str(UTC 日) 同日者，再按开赛时间最接近。

    🔴2026-09-16 新增: Odds-API events 返回**整赛季**待赛(西甲 107 场)，
      同赛季主客两回合队名必然重复 → 必须用日期消歧，否则会锚到错误轮次。
    """
    import datetime as _dt

    def _p(s):
        try:
            return _dt.datetime.fromisoformat(str(s).replace('Z', '+00:00'))
        except Exception:
            return None

    target = None
    if date_str:
        m = re.search(r'(\d{4})-(\d{2})-(\d{2})', str(date_str))
        if m:
            try:
                target = _dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except Exception:
                target = None
    if target:
        same_day = [e for e in cands if str(e.get('date') or '')[:10] == target.strftime('%Y-%m-%d')]
        pool = same_day or cands
        def _dist(e):
            d = _p(e.get('date'))
            return abs((d.replace(tzinfo=None) - target).total_seconds()) if d else 1e18
        return min(pool, key=_dist).get('id')
    dated = sorted([e for e in cands if _p(e.get('date'))], key=lambda e: _p(e.get('date')))
    return (dated or cands)[0].get('id')


def src_euro_odds(home, away, league=None, date_str=None):
    """Odds-API 欧盘真实接入（2026-09-11·此前硬编码 missing·VPN 下自动拉取）
    流程: get_events(league slug) → 队名匹配 eventId → get_odds 全市场 → 解析关键盘口"""
    slug = LEAGUE_SLUG.get(league or '', None)
    if not slug:
        return 'missing', {}, '联赛未映射 slug（%s）' % league
    import urllib.request, json as _j
    def _get(url):
        # 🔴2026-09-15 workbuddy修复: Odds-API 返回 Content-Encoding: gzip·原直接 utf-8 解码报
        #   "'utf-8' codec can't decode byte 0x8b" → 欧盘源恒 error。现按 gzip 魔数解压。
        # 🔴2026-09-16 修复: 改走 _open_dual(直连优先+代理回退)·原硬编码代理致无 VPN 时恒 error
        import gzip as _gz
        with _open_dual(url, timeout=40) as r:
            raw = r.read()
        if raw[:2] == b'\x1f\x8b':
            raw = _gz.decompress(raw)
        return _j.loads(raw.decode('utf-8'))
    try:
        ev = _get('https://api.odds-api.io/v3/events?apiKey=%s&sport=football&league=%s&status=pending' % (ODDS_API_KEY, slug))
    except Exception as e:
        return 'error', {}, 'Odds-API 请求失败（VPN/代理）: %s' % str(e)[:80]
    events = ev if isinstance(ev, list) else (ev.get('events') or ev.get('data') or [])
    EN = {'奥萨苏纳': 'osasuna', '西班牙人': 'espanyol', '埃斯帕尼奥尔': 'espanyol',
          '伯恩茅斯': 'bournemouth', '布伦特福德': 'brentford', '阿斯顿维拉': 'aston villa',
          '诺丁汉森林': 'nottingham', '水晶宫': 'crystal palace', '伊普斯维奇': 'ipswich',
          '利物浦': 'liverpool', '富勒姆': 'fulham',
          '塞维利亚': 'sevilla', '巴伦西亚': 'valencia', '瓦伦西亚': 'valencia', '雷恩': 'rennes', '马赛': 'marseille',
          '威尼斯': 'venezia', '佛罗伦萨': 'fiorentina', '柏林联合': 'unionberlin', '沙尔克04': 'schalke',
          '拜仁': 'bayern', '曼联': 'man', '罗马': 'roma', '费内巴切': 'fenerbahce', '朗斯': 'lens',
          '莱比锡': 'leipzig', '科莫': 'como', '斯拉维亚': 'slavia', '巴黎': 'paris', '皇马': 'realmadrid', '巴萨': 'barcelona'}
    def _en(n):
        # 🔴2026-09-15 workbuddy修复: 原仅查 37 条内联 EN 表 → 埃尔切等队失配。
        #   改为优先用 TEAM_ALIASES 归一化(cn_to_en_keywords)·再回退内联表。
        #   🔴返回前去空格: 事件名侧同样 replace(' ','') → 否则 'real madrid'[:5] 含空格前缀失配。
        kws = cn_to_en_keywords(n or '')
        base = kws[0] if kws else EN.get(n or '', normalize_name(n or ''))
        return (base or '').replace(' ', '')
    eh, ea = _en(home), _en(away)
    fid = None
    # 🔴2026-09-16 修复(P0): 队名未解析 → 明确归因(别赖数据源)
    if not (eh and ea):
        return 'missing', {'n_events': len(events), 'home_raw': home, 'away_raw': away}, \
               '队名未解析（txt 未取到主客队名·home=%r away=%r → 检查 txt 对阵行格式）' % (home, away)
    cands = []
    for e in events:
        h = (e.get('home') or '').lower().replace(' ', '')
        a = (e.get('away') or '').lower().replace(' ', '')
        if (eh[:5] in h or h[:5] in eh) and (ea[:5] in a or a[:5] in ea):
            cands.append(e)
    if not cands:
        return 'missing', {'n_events': len(events), 'home_en': eh, 'away_en': ea}, \
               '未匹配本场（%d 场待赛·队名/联赛）' % len(events)
    # 🔴2026-09-16 修复(P0): 事件表是**整赛季**待赛(西甲 107 场) → 原「取首个同名命中」会锚到
    #   错误轮次(同赛季主客两回合必然重名)。现按 date_str(赛程 UTC 日) 优先同日·再按时间最近取。
    fid = _pick_fixture(cands, date_str)
    try:
        od = _get('https://api.odds-api.io/v3/odds?apiKey=%s&eventId=%s&bookmakers=1xbet' % (ODDS_API_KEY, fid))
    except Exception as e:
        return 'error', {}, 'get_odds 失败: %s' % str(e)[:80]
    res = {'event_id': fid, 'markets': {}, 'n_events': len(events), 'date_utc': date_str}
    try:
        bm = {m['name']: m['odds'] for m in od['bookmakers']['1xbet']}
        if 'ML' in bm:
            m0 = bm['ML'][0]
            res['markets']['ML'] = {k: float(m0[k]) for k in ('home', 'draw', 'away') if k in m0}
        if 'Totals' in bm:
            res['markets']['Totals'] = {str(v['hdp']): [float(v['over']), float(v['under'])] for v in bm['Totals'] if 'hdp' in v and 'over' in v}
        if 'Spread' in bm:
            res['markets']['Spread'] = {str(v['hdp']): [float(v['home']), float(v['away'])] for v in bm['Spread'] if 'hdp' in v and 'home' in v}
        if 'Both Teams To Score' in bm:
            b0 = bm['Both Teams To Score'][0]
            res['markets']['BTTS'] = {k: float(b0[k]) for k in ('yes', 'no') if k in b0}
        if 'Correct Score' in bm:
            cs = {v['label']: float(v['odds']) for v in bm['Correct Score'] if 'label' in v}
            res['markets']['CS_low'] = dict(sorted(cs.items(), key=lambda x: x[1])[:8])
    except Exception as e:
        return 'error', res, '市场解析失败: %s' % str(e)[:60]
    return 'ok', res, ''


# ---------- 主接入 ----------
def collect(txt_path, league=None, net=False, date_str=None):
    home, away, head = extract_teams(txt_path)
    # 🔴2026-09-16 修复(P0): 赛程日期提前解析 → 供 euro_odds 选场消歧(原仅在 api_football 段
    #   才解析 → 欧盘拿到 date_str=None → 整赛季事件表只能取首个同名 → 可能锚错轮次)
    _kick_bj, _kick_utc = extract_match_date(txt_path)
    res = {'txt_path': txt_path, 'head': head, 'home': home, 'away': away,
           'kickoff': {'beijing': _kick_bj, 'utc': _kick_utc},
           'league_arg': league, 'sources': {}, 'features': {}, 'rich': {}, 'status': {}}

    def add(name, fn, *a):
        t0 = time.time()
        try:
            st, data, note = fn(*a)
        except Exception as e:
            st, data, note = 'error', {}, str(e)[:120]
        res['sources'][name] = data
        res['status'][name] = {'status': st, 'note': note, 'ms': int((time.time() - t0) * 1000)}
        return st, data

    # A txt（核心）
    st, data = add('txt', src_txt, txt_path)
    if data.get('features'):
        res['features'] = dict(data['features'])
        res['rich']['txt_detail'] = data.get('detail', {})
    if league and not res['features'].get('league'):
        res['features']['league'] = league
    res['league'] = res['features'].get('league') or league or '?'

    # B HAF（本地）
    add('haf', src_haf, home, away)
    # G H2H / H news / F euro_odds（缺环境标 missing）
    add('h2h', src_h2h, home, away)
    # 🔴2026-10-28 P20 用户决策：伤停只用 Bzzoiro 结构化 API（源B8）→ **网页新闻搜索伤停已停用**
    #   理由: ① news 是「文本标题级」无法给结构化位置 → 铁则32 位置级影响分只能靠 LLM 猜（case287 曾因此方向判反）
    #         ② Bzzoiro 直接给 position/availability/injury_type/回归日（确定性输入）
    #         ③ news 走代理 RSS，是主要卡顿源（实测 exit=2 / 超时）
    if os.environ.get('BRIDGE_NEWS') == '1':
        add('news', src_news, home, away)          # 应急恢复通道
    else:
        res['sources']['news'] = {'status': 'disabled',
                                  'reason': 'P20：伤停改 Bzzoiro 结构化 API 唯一源·网页新闻已停用（BRIDGE_NEWS=1 可恢复）'}
        res['features']['news_disabled'] = 1
    add('euro_odds', src_euro_odds, home, away, res.get('league') or league, date_str or _kick_utc)
    # 网络源
    if net:
        st, d = add('clubelo', src_clubelo, home, away)
        if st == 'ok':
            eh, ea = d.get('elo_home'), d.get('elo_away')
            if eh and ea:
                res['features']['elo_home'] = eh
                res['features']['elo_away'] = ea
                res['features']['elo_diff'] = float(eh) - float(ea)
        add('xg', src_xg, home, away)
        bj_d, utc_d = _kick_bj, _kick_utc
        ds = date_str or utc_d or time.strftime('%Y-%m-%d')
        # 🔴2026-10-06 用户决策: api-football 已停用·从数据链完全剔除（替代源见 src_api_fb 文档）
        add('api_football', src_api_fb, ds, home, away)
        add('bzz_injury', src_bzz_injury, home, away, ds)  # 🔴2026-10-09 源B8 结构化伤停(位置级·Bzzoiro)
        res['match_date'] = {'beijing': bj_d, 'utc': ds}
    else:
        for s in ('clubelo', 'xg', 'api_football', 'bzz_injury'):
            res['status'][s] = {'status': 'skipped', 'note': '未启用网络源（--net 开启）', 'ms': 0}

    # E. H2H 特征汇入（3 个·无数据填 0·不臆造）
    h2h = res['sources'].get('h2h') or {}
    rec = h2h.get('recent')
    if isinstance(rec, list) and rec:
        try:
            n = len(rec)
            hw = sum(1 for r in rec if int(float(r[3] or 0)) > int(float(r[4] or 0)))
            tg = sum(int(float(r[3] or 0)) + int(float(r[4] or 0)) for r in rec)
            res['features']['h2h_n_matches'] = n
            res['features']['h2h_home_win_rate'] = round(hw / n, 3)
            res['features']['h2h_avg_goals'] = round(tg / n, 3)
        except Exception:
            res['features']['h2h_n_matches'] = 0
            res['features']['h2h_home_win_rate'] = 0
            res['features']['h2h_avg_goals'] = 0
    else:
        res['features']['h2h_n_matches'] = 0
        res['features']['h2h_home_win_rate'] = 0
        res['features']['h2h_avg_goals'] = 0

    # HAF 汇入 features（🔴2026-09-11 修正: 真实结构=队名→联赛→主场/客场→{场均进球,胜率%,...}）
    haf = res['sources'].get('haf') or {}
    def _haf_flat(node):
        """取该队任一联赛的主/客场档案（结构: {联赛: {'主场':{...}, '客场':{...}}}）"""
        if not isinstance(node, dict):
            return None, None
        for _lg, _d in node.items():
            if isinstance(_d, dict) and ('主场' in _d or '客场' in _d):
                return _d.get('主场'), _d.get('客场')
        return None, None
    _h, _a = _haf_flat(haf.get('home'))
    if _h:
        res['features']['haf_home'] = 1
        for _src, _dst in (('场均进球', 'haf_home_goals'), ('胜率%', 'haf_home_winrate'),
                           ('场均失球', 'haf_home_conceded'), ('场均净胜', 'haf_home_net')):
            if _src in _h:
                try:
                    res['features'][_dst] = float(_h[_src])
                except Exception:
                    pass
    if _a:
        res['features']['haf_away'] = 1
        for _src, _dst in (('场均进球', 'haf_away_goals'), ('胜率%', 'haf_away_winrate'),
                           ('场均失球', 'haf_away_conceded'), ('场均净胜', 'haf_away_net')):
            if _src in _a:
                try:
                    res['features'][_dst] = float(_a[_src])
                except Exception:
                    pass
    # xG 汇入（解析 understat 输出中的数值对·2026-09-11）
    xgd = res['sources'].get('xg') or {}
    if isinstance(xgd.get('output'), str):
        import re as _rex
        # 支持 'xG 1.85424-0.558336'（实际格式）与 'a vs b' / 'a:b'
        _nums = _rex.findall(r'xG\s*([\d.]+)\s*-\s*([\d.]+)', xgd['output'])
        if not _nums:
            _nums = _rex.findall(r'([\d.]+)\s*(?:vs|VS|:)\s*([\d.]+)', xgd['output'])
        if _nums:
            try:
                _a = [float(x[0]) for x in _nums]; _b = [float(x[1]) for x in _nums]
                res['features']['xg_for_avg'] = round(sum(_a) / len(_a), 3)
                res['features']['xg_against_avg'] = round(sum(_b) / len(_b), 3)
            except Exception:
                pass
    # 🔴2026-10-09 A模式审计修复(P0-1·防「有产出无消费」): Bzzoiro 结构化伤停**汇入特征**
    #   原实现仅 add('bzz_injury') → res['sources'] 有数据但**无人读取**（特征空/无消费端）= 断点
    _bz = res['sources'].get('bzz_injury') or {}
    if isinstance(_bz, dict) and _bz:
        try:
            _bh, _ba = (_bz.get('home') or {}), (_bz.get('away') or {})
            if _bh.get('found') or _ba.get('found'):
                res['features']['inj_bzz_home_n'] = int(_bh.get('out_n') or 0)
                res['features']['inj_bzz_away_n'] = int(_ba.get('out_n') or 0)
                _ph = [str(p.get('pos_cn') or '未知') for p in (_bh.get('players') or [])]
                _pa = [str(p.get('pos_cn') or '未知') for p in (_ba.get('players') or [])]
                if _ph:
                    res['features']['inj_bzz_home_pos'] = ','.join(_ph)
                if _pa:
                    res['features']['inj_bzz_away_pos'] = ','.join(_pa)
                # 🔴铁则32 可消费条目（位置,重要性·保守=未知）
                if _ph:
                    res['features']['inj_bzz_home_items'] = ' '.join('%s,未知' % x for x in _ph)
                if _pa:
                    res['features']['inj_bzz_away_items'] = ' '.join('%s,未知' % x for x in _pa)
        except Exception:
            pass
    # 🔴2026-10-31（用户追问「为什么八源不能全齐」·实测）:
    #   原 `tot = len(res['status'])` **包含已停用的 api_football**（恒 missing）
    #   → **8/8 数学上不可达**（天花板 7/8）·且完整度被系统性压低 1/8 = 12.5pp
    #   两个停用源处理还不一致: api_football 占分母（写 status）· news 不占（只写 sources）
    #   → 分母只算**活跃源**：`api_football`（2026-10-06 用户决策停用）不计入。
    _DEAD_SRC = ('api_football',)
    ok = sum(1 for v in res['status'].values() if v['status'] == 'ok')
    tot = len([_k for _k in res['status'] if _k not in _DEAD_SRC])
    res['completeness'] = '%d/%d 源可用' % (ok, tot)
    _dead_hit = [_k for _k in res['status'] if _k in _DEAD_SRC]
    if _dead_hit:
        res['completeness'] += '（%s 已停用·不计入分母）' % ','.join(_dead_hit)
        res['sources_dead'] = _dead_hit
    return res


def print_bridge(res):
    print('=' * 70)
    print('🔗 统一数据接入 — %s' % (res.get('head') or '')[:56])
    print('-' * 70)
    print('  队伍: %s(主) vs %s | 联赛: %s | 完整度: %s' % (
        res.get('home'), res.get('away'), res.get('league'), res.get('completeness')))
    print('  数据源状态:')
    for k, v in res['status'].items():
        icon = {'ok': '✅', 'missing': '⚠️', 'error': '❌', 'skipped': '⏭️'}.get(v['status'], '?')
        print('    %s %-14s %-8s %s' % (icon, k, v['status'], v['note'] or ''))
    f = res.get('features') or {}
    print('  核心特征: 主%.2f/平%.2f/客%.2f 让球%+g O25(等效)%.3f 联赛%s%s' % (
        f.get('home_odds') or 0, f.get('draw_odds') or 0, f.get('away_odds') or 0,
        f.get('handicap') or 0, f.get('o25_odds') or 0, f.get('league') or '?',
        (' ELO差%.0f' % f['elo_diff']) if f.get('elo_diff') else ''))
    if f.get('inj_bzz_home_n') is not None or f.get('inj_bzz_away_n') is not None:
        print('  🔴Bzzoiro 伤停(源B8·结构化): 主 %s 人 [%s] | 客 %s 人 [%s]' % (
            f.get('inj_bzz_home_n', '-'), f.get('inj_bzz_home_pos') or '-',
            f.get('inj_bzz_away_n', '-'), f.get('inj_bzz_away_pos') or '-'))
        print('     → 铁则32 条目(保守·未知): 主「%s」客「%s」' % (
            f.get('inj_bzz_home_items') or '-', f.get('inj_bzz_away_items') or '-'))
    print('=' * 70)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('txt'); ap.add_argument('--league')
    ap.add_argument('--net', action='store_true', help='(默认已启用直连源)'); ap.add_argument('--no-net', action='store_true', help='离线模式·禁用网络源')
    ap.add_argument('--date'); ap.add_argument('--json', action='store_true')
    ap.add_argument('--save', action='store_true', help='保存为预测日志')
    a = ap.parse_args()
    r = collect(a.txt, a.league, (not a.no_net), a.date)   # 默认启用直连源(clubelo/understat/the-odds-api)·VPN 源仍标 missing
    if a.json:
        print(json.dumps(r, ensure_ascii=False)[:2000])
    else:
        print_bridge(r)
    if a.save:
        d = os.path.join(HERE, 'prediction_log')
        os.makedirs(d, exist_ok=True)
        name = os.path.splitext(os.path.basename(a.txt))[0] + '.json'
        json.dump(r, open(os.path.join(d, name), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('已保存预测日志: prediction_log/%s' % name)


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    main()
