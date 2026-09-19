# -*- coding: utf-8 -*-
"""data_bridge.py —— 统一数据接入层（2026-09-11）
把一场比赛所需的**全部 ML 数据源**自动汇聚为一个统一特征集（供在线学习/预测/复盘），
每源独立接入 + 三态标注（ok / missing / error），缺失不臆造。

数据源清单:
  A txt        竞彩txt（本地·必得）      → ML/让球/总进球/O25反推/半全场/比分/场均进失
  B haf        HAF 主客场因子（本地表）   → 主客场 λ/胜平负/分离度
  C clubelo    实时 ELO（网络·clubelo）   → elo_h/elo_a/elo_diff
  D xg         understat xG（网络·缓存）  → xg_for/xg_against 近N场均值
  E api_fb     api-football（网络·key）   → 官方概率/13家赔率/伤停
  F euro_odds  Odds-API（网络·VPN）       → 欧盘 ML/Spread水位/Totals/CS
  G h2h        H2H 历史（本地 SQL/缓存）  → 近N次交锋分布
  H news       新闻伤停（网络·VPN）        → 伤停清单文本

用法:
  python scripts/online_learning/data_bridge.py <txt路径> [--league 欧冠] [--net] [--json]
    --net  启用网络源（clubelo/xg/api-football·默认关闭以保速度与稳定）
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
#   normalize_name 去非 ASCII 得空串 → haf/h2h/api_football/clubelo/news 五源恒失配）。
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
    """中文名→归一化英文关键词列表（用于模糊匹配）"""
    if not cn_name:
        return []
    ens = TEAM_ALIASES.get(cn_name, [cn_name])
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
          B1 euro_odds(源B1 Odds-API) / B3 api_football / h2h / clubelo / news
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
        # 3. 包含匹配
        for k, v in flat.items():
            if nk and (nk[:4] in k or k[:4] in nk):
                return v
        return None
    h, a = _clubelo_pick(home), _clubelo_pick(away)
    if not h and not a:
        return 'missing', {'file': os.path.basename(path), 'n_teams': len(flat)}, \
            '队名未匹配 clubelo（%d 队·需中英别名扩展）' % len(flat)
    def elo(x):
        return x.get('elo') if isinstance(x, dict) else None
    return 'ok', {'elo_home': elo(h), 'elo_away': elo(a), 'file': os.path.basename(path)}, \
        '' if (h and a) else '仅一队匹配'


def src_xg(home, away):
    script = os.path.join(TMP, 'understat_xg.py')
    if not os.path.exists(script):
        return 'missing', {}, 'understat_xg.py 不存在'
    rc, out = _run([sys.executable, script], timeout=90)
    if rc != 0:
        return 'error', {}, 'understat 执行失败（网络/代理）: %s' % out[-100:]
    return 'ok', {'output': out[-800:]}, ''


def src_api_fb(date_str, home=None, away=None):
    """api-football: fixtures?date → 定位 → predictions/odds/injuries"""
    key = os.environ.get('API_FOOTBALL_KEY', '')
    # 🔴2026-09-15 workbuddy 适配: 本地 key 配置（无 reasonix.toml 时的来源）
    if not key:
        try:
            _lk = json.load(open(os.path.join(DATA, 'tmp', 'api_keys.json'), encoding='utf-8'))
            key = _lk.get('api_football', '')
        except Exception:
            pass
    cfg = os.path.join(ROOT, 'reasonix.toml')
    if not key and os.path.exists(cfg):
        # 🔴2026-09-11 修复: 原宽泛正则可能取到其他插件的 key（曾取错致误判"账户暂停"）
        _cfg = open(cfg, encoding='utf-8', errors='replace').read()
        _m = re.search(r'api[_-]?football[\s\S]{0,800}?([0-9a-f]{32})', _cfg, re.I)
        if not _m:
            _m = re.search(r'([0-9a-f]{32})', _cfg)
        if _m:
            key = _m.group(1)
        # 候选 key 有效性校验（/status errors 为空）
        if key:
            try:
                import urllib.request as _u2
                _req = _u2.Request('https://v3.football.api-sports.io/status', headers={'x-apisports-key': key})
                with _u2.urlopen(_req, timeout=15) as _r:
                    if json.loads(_r.read().decode('utf-8')).get('errors'):
                        key = ''
            except Exception:
                pass
    if not key:
        return 'missing', {}, '未找到有效 api-football key'
    import urllib.request
    def get(url):
        req = urllib.request.Request(url, headers={'x-apisports-key': key})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    try:
        d = get('https://v3.football.api-sports.io/fixtures?date=%s' % date_str)
    except Exception as e:
        return 'error', {}, 'fixtures 请求失败: %s' % str(e)[:80]
    fid = None
    # 🔴2026-09-14 升级: 使用统一多别名映射+归一化
    def _api_en(n):
        if not n:
            return ""
        kws = cn_to_en_keywords(n)
        return kws[0] if kws else normalize_name(n)
    eh, ea = _api_en(home), _api_en(away)
    for f in d.get('response', []):
        hn = normalize_name(f['teams']['home']['name'] or '')
        an = normalize_name(f['teams']['away']['name'] or '')
        # 多别名匹配: 任一别名命中即算匹配
        h_match = any((kw and (kw in hn or hn in kw or (len(kw)>=4 and kw[:4]==hn[:4]))) for kw in cn_to_en_keywords(home)) or (eh and eh in hn)
        a_match = any((kw and (kw in an or an in kw or (len(kw)>=4 and kw[:4]==an[:4]))) for kw in cn_to_en_keywords(away)) or (ea and ea in an)
        if h_match and a_match:
            fid = f['fixture']['id']; break
    if not fid:
        return 'missing', {'n_fixtures': len(d.get('response', []))}, '未匹配到本场 fixture'
    out = {'fixture_id': fid}
    _empty = []
    for ep in ('predictions', 'odds', 'injuries'):
        try:
            out[ep] = get('https://v3.football.api-sports.io/%s?fixture=%s' % (ep, fid))
            if not (out[ep].get('results') or 0):
                _empty.append(ep)
        except Exception as e:
            out[ep] = {'error': str(e)[:60]}
            _empty.append(ep)
    return 'ok', out, ('空端点: %s' % ','.join(_empty)) if _empty else ''


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
        return 'missing', {}, '队名缺失'
    import csv
    hs, aw = normalize_name(h)[:5], normalize_name(a)[:5]
    # 多别名匹配集
    h_kws = set(cn_to_en_keywords(home)) | {hs}
    a_kws = set(cn_to_en_keywords(away)) | {aw}
    rows = []
    try:
        with open(m, encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                H = (r.get('HomeTeam') or '').lower()
                A = (r.get('AwayTeam') or '').lower()
                if hs and aw and ((hs in H and aw in A) or (hs in A and aw in H)):
                    rows.append((r.get('MatchDate', ''), r.get('HomeTeam'), r.get('AwayTeam'),
                                 r.get('FTHome'), r.get('FTAway')))
    except Exception as e:
        return 'error', {}, str(e)[:80]
    if not rows:
        return 'missing', {}, 'Matches.csv 未匹配两队（中文↔英文别名未覆盖）'
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
    for _ph in (None, proxy):
        try:
            op = (_ur.build_opener() if _ph is None
                  else _ur.build_opener(_ur.ProxyHandler({'https': _ph, 'http': _ph})))
            return op.open(_ur.Request(url, headers=hdr), timeout=timeout)
        except Exception as _e:
            last = _e
    raise last


def src_news(home, away):
    """Bing News 伤停搜索（🔴2026-09-16: 直连优先 + 代理回退）
    RSS 搜索 队名+injury → 标题命中列表（供伤停核查·非唯一源）
    """
    import urllib.parse as _up, re as _re
    if not (home and away):
        return 'missing', {}, '队名缺失'
    q = _up.quote('%s vs %s injury team news' % (home, away))
    url = 'https://www.bing.com/news/search?q=%s&format=rss' % q
    try:
        with _open_dual(url, timeout=30) as r:
            xml = r.read().decode('utf-8', errors='replace')
    except Exception as e:
        return 'error', {}, 'Bing News 请求失败（直连+代理均失败）: %s' % str(e)[:70]
    items = _re.findall(r'<item>(.*?)</item>', xml, _re.S)
    titles = []
    for it in items[:10]:
        t = _re.search(r'<title>(.*?)</title>', it, _re.S)
        if t:
            titles.append(_re.sub(r'<[^>]+>', '', t.group(1))[:120])
    if not titles:
        return 'missing', {}, 'Bing News 无结果'
    injury_hits = [x for x in titles if _re.search(r'(?i)injur|doubt|suspend|out of|miss|fitness|lineup', x)]
    return 'ok', {'n': len(titles), 'injury_related': len(injury_hits), 'titles': injury_hits or titles[:5]}, ''


LEAGUE_SLUG = {'西甲': 'spain-laliga', 'SP1': 'spain-laliga', '英超': 'england-premier-league', 'E0': 'england-premier-league',
               '意甲': 'italy-serie-a', 'I1': 'italy-serie-a', '德甲': 'germany-bundesliga', 'D1': 'germany-bundesliga',
               '法甲': 'france-ligue-1', 'F1': 'france-ligue-1'}
# 🔴2026-09-16 清洁: key 外部化(防硬编码/泄露)——解析优先级
#   ① 环境变量 ODDS_API_KEY  ② data/tmp/api_keys.json 的 odds_api  ③ 内联回退(向后兼容·不破坏现网)
_ODDS_API_KEY_FALLBACK = os.environ.get('ODDS_API_KEY', '')


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
    add('news', src_news, home, away)
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
        st, d = add('api_football', src_api_fb, ds, home, away)
        if st == 'ok' and isinstance(d, dict):
            res['rich']['api_football'] = d
            res['match_date'] = {'beijing': bj_d, 'utc': ds}
    else:
        for s in ('clubelo', 'xg', 'api_football'):
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
    # api-football 官方概率汇入（predictions.percent）
    apid = res['rich'].get('api_football') or {}
    try:
        pr = (apid.get('predictions') or {}).get('response') or []
        if pr:
            pdata = pr[0].get('predictions') or {}
            pct = pdata.get('percent') or {}
            winner = (pdata.get('winner') or {}).get('name')
            vals = [str(pct.get(k, '')).replace('%', '') for k in ('home', 'draw', 'away')]
            # 🔴2026-09-11 修复: api 无结论时返回 33/33/33 默认值 → 不得当真实概率汇入
            _is_default = vals[0] == '33' and vals[1] == '33' and vals[2] == '33'
            if not winner and _is_default:
                res['status']['api_football']['note'] = (res['status']['api_football'].get('note') or '') +                     ' | 官方预测无结论(33/33/33默认·未汇入)'
            else:
                for k, tag in (('home', 'api_home_p'), ('draw', 'api_draw_p'), ('away', 'api_away_p')):
                    v = str(pct.get(k, '')).replace('%', '')
                    if v:
                        res['features'][tag] = float(v) / 100
    except Exception:
        pass
    ok = sum(1 for v in res['status'].values() if v['status'] == 'ok')
    tot = len(res['status'])
    res['completeness'] = '%d/%d 源可用' % (ok, tot)
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
    print('=' * 70)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('txt'); ap.add_argument('--league')
    ap.add_argument('--net', action='store_true', help='(默认已启用直连源)'); ap.add_argument('--no-net', action='store_true', help='离线模式·禁用网络源')
    ap.add_argument('--date'); ap.add_argument('--json', action='store_true')
    ap.add_argument('--save', action='store_true', help='保存为预测日志')
    a = ap.parse_args()
    r = collect(a.txt, a.league, (not a.no_net), a.date)   # 默认启用直连源(api-football/clubelo/understat)·VPN 源仍标 missing
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
