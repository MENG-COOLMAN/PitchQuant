---
name: SL-news-crawl
description: 新闻基本面抓取：通过VPN代理抓Bing News→Sportsmole赛前预览，提取伤停/阵容/预测
---

# SL-news-crawl — 新闻基本面抓取

通过 VPN 代理抓取 Bing News → Sportsmole 赛前预览，提取伤停/阵容/预测。

## 前置条件
VPN 代理已开启（Clash Verge默认: 127.0.0.1:7897）。
无代理时：跳过此步骤，标注【数据缺失】。

## 执行流程

### Step 1: 搜索赛前预览
```bash
curl -s --proxy http://127.0.0.1:7897 --max-time 15 \
  "https://www.bing.com/news/search?q={主队}+{客队}+preview+team+news+lineups" \
  | python -c "import sys,re; t=sys.stdin.read(); 
     urls=re.findall(r'<a[^>]*href=\"([^\"]*)\"',t); 
     [print(u.replace('&amp;','&')) for u in urls 
      if u.startswith('http') and 'sportsmole' in u.lower()][:1]"
```
备用源：MSN Sport（同样从搜索结果中提取）。

### Step 2: 抓取预览文章
```bash
curl -s --proxy http://127.0.0.1:7897 --max-time 15 "{article_url}" \
  | python -c "
import sys, re
t = sys.stdin.read()
# 清洗HTML
clean = re.sub(r'<script[^>]*>.*?</script>', '', t, flags=re.DOTALL)
clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL)
clean = re.sub(r'<[^>]+>', ' ', clean)
clean = re.sub(r'\s+', ' ', clean)

# 提取Team News段落
idx = clean.find('Team News')
if idx < 0: idx = clean.find('team news')
if idx > 0:
    print(clean[idx:idx+2000])
else:
    # 搜索伤停关键词
    for kw in ['injury','Injury','injured','unavailable','ruled out','absent']:
        i = clean.find(kw)
        if i > 0:
            print(f'[{kw}]:', clean[max(0,i-100):i+300])
            break
"
```

### Step 3: 解析输出
从提取的文本中识别：
- 伤停名单："X remains unavailable / out / injured"
- 预计阵容："possible starting lineup:"
- 专家预测："We say: X 1-2 Y"

### Step 4: 传导至模型
- 伤停数据 → 填入 1.10 基本面 → 触发铁则32检查
- 预计阵容 → 填入 1.10 基本面
- 专家预测方向 → 作为参考项（不纳入权调，仅供对比）

## 约束
- 优先 Sportsmole，备选 MSN/TalkSport
- 无代理时标注【数据缺失】并跳过
- 提取的信息必须标注来源URL

---

## 🔴备用通道：API-Football injuries（源B3·接入·case49验证）

> 触发：新闻抓取失败（coverage少/站点反爬）或需要精确伤停位置时。
> case49 实证：Bing代理无预览/Sportsmole无场/CBSSports 406/MSN空 → API-Football injuries 直接返回 20 条伤停（含位置·主力门将Steffen缺阵→触发修正58）。

### 调用方法（经VPN代理127.0.0.1:7897）
```bash
# 1. 找 fixture id（按日期+队伍）
curl -s --max-time 20 -x http://127.0.0.1:7897 "https://v3.football.api-sports.io/fixtures?date=YYYY-MM-DD&timezone=Asia/Shanghai" \
  -H "x-apisports-key: <YOUR_API_FOOTBALL_KEY>"
# 2. 伤停（触发铁则32/修正58·含位置reason字段）
curl -s --max-time 20 -x http://127.0.0.1:7897 "https://v3.football.api-sports.io/injuries?fixture={id}" -H "x-apisports-key: ..."
# 3. 可选：阵容 lineups / 统计 statistics / H2H fixtures/headtohead
```

### 传导规则
- injuries → 铁则32（≥3人平局上调）+ 修正58（门将缺阵总进球+1/射手缺阵净胜-1/后腰中卫缺阵+BTTS）
- 限流 100次/天（每场 2-3 次调用足够：fixtures+injuries±lineups）
- 新闻与 API-Football 伤停冲突时：以 API-Football 为准（结构化数据·位置明确）
