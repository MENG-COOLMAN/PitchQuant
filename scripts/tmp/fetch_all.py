# fetch_all.py — 外部数据源聚合拉取器（步骤遗失根除·支柱B）
# 用法: python fetch_all.py --league 英超 --home 主队 --away 客队 [--event 欧盘eventId]
# 原理: 一次尝试拉齐全部外部数据源(ELO/xG/api-football/footballcharts)·拉不到自动标"无数据(原因)"
# ——数据缺不缺由脚本定·不由LLM记不记得(防"没拉标缺失"·防"忘了拉")
# 现实降级: 新闻伤停(SL-news-crawl)需VPN手动·api/footballcharts需MCP·本脚本聚合可用源+三态标注

import io, sys, os, subprocess, json
sys.stdout.reconfigure(encoding='utf-8')
TMP = os.path.dirname(os.path.abspath(__file__))

def run_script(script, *args, timeout=40):
    try:
        r = subprocess.run([sys.executable, os.path.join(TMP, script), *args],
                           capture_output=True, text=True, encoding='utf-8', timeout=timeout)
        return (r.stdout or '')[:800], r.returncode == 0
    except Exception as e:
        return '执行异常: %s' % e, False

def main():
    args = sys.argv[1:]
    league = home = away = event = None
    for i, a in enumerate(args):
        if a == '--league' and i+1 < len(args): league = args[i+1]
        if a == '--home' and i+1 < len(args): home = args[i+1]
        if a == '--away' and i+1 < len(args): away = args[i+1]
        if a == '--event' and i+1 < len(args): event = args[i+1]
    print('=' * 60)
    print('fetch_all.py 外部数据源聚合(2026-09-02·防数据源步骤遗失)')
    print('=' * 60)
    TOP5 = ('英超','西甲','意甲','德甲','法甲','epl','laliga','seriea','bundesliga','ligue1')
    if league in TOP5:
        out, ok = run_script('fetch_clubelo.py')
        print('[B6 clubelo ELO] %s' % ('OK已抓(调SL-elo-fetch查两队ELO差)' if ok else 'WARN抓取失败标无数据(网络)'))
    else:
        print('[B6 clubelo ELO] 不触发(非五大或未指定联赛)')
    xg_map = {'英超':'EPL','西甲':'La_liga','德甲':'Bundesliga','意甲':'Serie_A','法甲':'Ligue_1'}
    if league in xg_map:
        out, ok = run_script('understat_xg.py', xg_map[league], '2025')
        print('[B4 understat xG] %s (历史2025防泄露·本场xG禁赛前用)' % ('OK已抓' if ok else 'WARN无数据(网络/缓存)'))
    else:
        print('[B4 understat xG] 不触发(非五大·xG仅txt场Step7用)')
    if event:
        print('[B3 api-football] 需调SL-api-football-chain(fixtures?date定位→predictions/odds/injuries) event=%s' % event)
    else:
        print('[B3 api-football] 需--event eventId或按日期fixtures定位')
    if league in xg_map:
        print('[B5 footballcharts] ⛔源已废弃(2026-09-15·域名失效)·改用 understat_xg.py + SK-xg-depth + 联赛校准(标"无数据(源已废弃)")')
    else:
        print('[B5 footballcharts] 不触发(非五大)')
    print('[SL-news-crawl 新闻伤停] 唯一伤停源需VPN手动执行·未执行必须标未执行(原因)')
    print('=' * 60)
    print('三态标注铁律: 每源输出 已抓取(来源)/未执行(原因)/无数据(原因)·禁没做也不说·禁跳过')

if __name__ == '__main__':
    main()
