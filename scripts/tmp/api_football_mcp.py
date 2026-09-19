#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""API-Football 轻量 MCP stdio server — 源B3 伤停回归候选（2026-08-23 自建·V3.5.71）
工具: fixtures / standings / team_search / league_search / predictions / h2h / injuries / sidelined
key: 环境变量 API_FOOTBALL_KEY 或 每调用参数 _apiKey（优先）
协议: MCP stdio 2024-11-05 (newline-delimited JSON-RPC) · 零依赖(Python 标准库)

🔴🔴 调用规范固化（2026-09-19·防重复纠错·唯一正确链路）:
  ① fixtures?date=YYYY-MM-DD（UTC日·纯 date 定位·**禁 league/season**）→ 取本场 fixture id
  ② predictions?fixture=ID（官方概率） / odds?fixture=ID（13家赔率） / injuries?fixture=ID（本场伤停） / h2h?team1=X&team2=Y
  ③ 免费计划限赛季 2022-2024：带 season>=2025 会被服务端拒绝 → 本 server 已加**自动剥离**防错（见 fixtures 分支）
  ④ 直连 REST 降级: GET https://v3.football.api-sports.io/fixtures?date=... · header x-apisports-key
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://v3.football.api-sports.io"
ENV_KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()

TOOLS = [
    {"name": "fixtures", "description": "🔴调用规范(2026-09-19固化·防重复纠错): 当前赛季(2025+)必须**纯 date 定位** fixtures?date=YYYY-MM-DD(UTC日) → 取 fixture id → 再查 predictions/odds/injuries?fixture=ID。🔴禁带 league/season（免费计划限 2022-2024·带当前赛季必报错全灭——2026-09-18 重大失误根因）。last/next 仅历史查询用。",
     "inputSchema": {"type": "object", "properties": {
         "date": {"type": "string", "description": "🔴当前赛季唯一可用: YYYY-MM-DD (UTC日)"},
         "team": {"type": "number", "description": "Team ID"},
         "last": {"type": "number"}, "next": {"type": "number"},
         "league": {"type": "number", "description": "⚠️仅 season<=2024 可用·当前赛季带此参数必失败(server 会自动剥离)"},
         "season": {"type": "number", "description": "⚠️仅<=2024 可用·当前赛季(2025+)禁带(server 会自动剥离)"},
         "_apiKey": {"type": "string"}}}},
    {"name": "standings", "description": "联赛积分榜: league+season 必填。返回 rank/team/points/gd/form",
     "inputSchema": {"type": "object", "properties": {
         "league": {"type": "number"}, "season": {"type": "number"}, "_apiKey": {"type": "string"}},
      "required": ["league", "season"]}},
    {"name": "team_search", "description": "按名称查球队ID: name 必填, country 可选消歧",
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string"}, "country": {"type": "string"}, "_apiKey": {"type": "string"}},
      "required": ["name"]}},
    {"name": "league_search", "description": "按名称查联赛ID: name 必填, country 可选",
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string"}, "country": {"type": "string"}, "_apiKey": {"type": "string"}},
      "required": ["name"]}},
    {"name": "predictions", "description": "API-Football 官方胜负预测: fixture 必填。返回 home/draw/away 概率+advice+h2h+form",
     "inputSchema": {"type": "object", "properties": {
         "fixture": {"type": "number"}, "_apiKey": {"type": "string"}},
      "required": ["fixture"]}},
    {"name": "h2h", "description": "两队历史交锋: team1+team2 必填, last 默认5",
     "inputSchema": {"type": "object", "properties": {
         "team1": {"type": "number"}, "team2": {"type": "number"}, "last": {"type": "number"}, "_apiKey": {"type": "string"}},
      "required": ["team1", "team2"]}},
    {"name": "injuries", "description": "🔴伤停/停赛: fixture(场次ID) 或 date(YYYY-MM-DD) 或 team+season。返回 player 受伤/停赛(type: Injury/Suspended, reason, date)",
     "inputSchema": {"type": "object", "properties": {
         "fixture": {"type": "number"}, "date": {"type": "string", "description": "YYYY-MM-DD"},
         "team": {"type": "number"}, "season": {"type": "number"}, "_apiKey": {"type": "string"}}}},
    {"name": "sidelined", "description": "长期缺阵: player 或 team+season。返回长期伤病/停赛名单",
     "inputSchema": {"type": "object", "properties": {
         "player": {"type": "number"}, "team": {"type": "number"}, "season": {"type": "number"}, "_apiKey": {"type": "string"}}}},
    {"name": "odds", "description": "🔴多机构赔率(补Odds-API未覆盖): fixture 必填(当前赛季fixture id 由 fixtures?date 定位)。返回 13 家博彩公司赔率(胜平负/让球/大小球/半场等市场·实时更新)",
     "inputSchema": {"type": "object", "properties": {
         "fixture": {"type": "number"}, "_apiKey": {"type": "string"}},
      "required": ["fixture"]}},
]


def http_get(path: str, params: dict) -> dict:
    url = BASE + path
    qs = urllib.parse.urlencode({k: str(v) for k, v in params.items() if v is not None})
    if qs:
        url += "?" + qs
    key = ENV_KEY
    req = urllib.request.Request(url, headers={"x-apisports-key": key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (429, 401, 403):
            return {"errors": {str(e.code): f"HTTP {e.code}"}}
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"errors": {"http": f"HTTP {e.code}"}}
    except Exception as e:
        return {"errors": {"network": str(e)}}


def soft_fail(data: dict, tool: str) -> dict | None:
    """API-Football 软失败结构: rate_limit/auth_failed/paid_plan_required/upstream_error"""
    errs = data.get("errors") or {}
    if not errs:
        return None
    msgs = list(errs.values()) if isinstance(errs, dict) else list(errs)
    joined = "; ".join(str(m) for m in msgs)
    if any(k in str(errs) for k in ("429", "rate")):
        return {"found": False, "reason": "rate_limit", "tool": tool, "hint": f"API-Football 日限(免费100次/天): {joined}", "retry_after_sec": 60}
    if any(k in str(errs) for k in ("401", "403")):
        return {"found": False, "reason": "auth_failed", "tool": tool, "hint": f"key 无效: {joined}"}
    if "Free plans" in joined or "free plans" in joined:
        return {"found": False, "reason": "paid_plan_required", "tool": tool, "hint": f"免费计划限制: {joined}", "allowed_seasons": "2022-2024"}
    return {"found": False, "reason": "upstream_error", "tool": tool, "hint": f"API-Football: {joined[:300]}"}


def call_tool(name: str, args: dict) -> dict:
    global ENV_KEY
    key_arg = (args.get("_apiKey") or "").strip()
    if key_arg:
        ENV_KEY = key_arg
    if not ENV_KEY:
        return {"found": False, "reason": "missing_api_key", "tool": name,
                "hint": "无 API_FOOTBALL_KEY 环境变量且未传 _apiKey。注册: https://dashboard.api-football.com/register（免费100次/天）",
                "register_url": "https://dashboard.api-football.com/register"}
    clean = {k: v for k, v in args.items() if k != "_apiKey"}
    if name == "fixtures":
        # 固化(防重复纠错): 免费计划禁 league+season(当前赛季>2024) → 误带则**自动剥离**·强制走 date/team 定位
        warn = None
        try:
            if clean.get("season") and int(clean.get("season")) > 2024:
                clean = {k: v for k, v in clean.items() if k not in ("league", "season")}
                warn = "已自动剥离 league/season（免费计划限<=2024·当前赛季须纯 date 定位）——2026-09-19 固化防错"
        except (TypeError, ValueError):
            pass
        if not any(k in clean for k in ("date", "team", "last", "next")):
            return {"found": False, "reason": "bad_args",
                    "hint": "🔴当前赛季请用 date=YYYY-MM-DD(UTC日) 定位（先 fixtures?date 拿 fixture id 再查 predictions/odds/injuries?fixture=ID）; league/season 仅限 <=2024"}
        d = http_get("/fixtures", {**clean})
        f = soft_fail(d, name)
        if f: return f
        arr = d.get("response") or []
        out = {"count": len(arr), "fixtures": [proj_fixture(x) for x in arr[:50]]}
        if warn: out["warning"] = warn
        return out
    if name == "standings":
        d = http_get("/standings", clean)
        f = soft_fail(d, name)
        if f: return f
        arr = d.get("response") or []
        groups = (arr[0].get("league", {}).get("standings") if arr else None) or []
        return {"league_id": clean.get("league"), "season": clean.get("season"),
                "groups": [[proj_standing(t) for t in g] for g in groups]}
    if name == "team_search":
        d = http_get("/teams", {"search": clean.get("name"), "country": clean.get("country")})
        f = soft_fail(d, name)
        if f: return f
        arr = d.get("response") or []
        return {"count": len(arr), "teams": [proj_team(x) for x in arr[:20]]}
    if name == "league_search":
        d = http_get("/leagues", {"search": clean.get("name")})
        f = soft_fail(d, name)
        if f: return f
        arr = d.get("response") or []
        out = []
        for x in arr[:20]:
            lg = x.get("league", {})
            c = x.get("country", {})
            if clean.get("country") and c.get("name") and clean["country"].lower() not in str(c.get("name")).lower():
                continue
            out.append({"id": lg.get("id"), "name": lg.get("name"), "type": lg.get("type"),
                        "country": c.get("name"), "seasons": len(x.get("seasons") or [])})
        return {"count": len(out), "leagues": out}
    if name == "predictions":
        d = http_get("/predictions", {"fixture": clean.get("fixture")})
        f = soft_fail(d, name)
        if f: return f
        arr = d.get("response") or []
        return {"predictions": arr[:10]}
    if name == "h2h":
        if not clean.get("team1") or not clean.get("team2"):
            return {"found": False, "reason": "bad_args", "hint": "需要 team1 和 team2"}
        d = http_get("/fixtures/headtohead", {"h2h": f"{clean['team1']}-{clean['team2']}", "last": clean.get("last") or 5})
        f = soft_fail(d, name)
        if f: return f
        arr = d.get("response") or []
        return {"count": len(arr), "h2h": [proj_fixture(x) for x in arr[:10]]}
    if name == "injuries":
        d = http_get("/injuries", clean)
        f = soft_fail(d, name)
        if f: return f
        arr = d.get("response") or []
        return {"count": len(arr), "injuries": [proj_injury(x) for x in arr[:50]]}
    if name == "sidelined":
        d = http_get("/sidelined", clean)
        f = soft_fail(d, name)
        if f: return f
        arr = d.get("response") or []
        return {"count": len(arr), "sidelined": arr[:50]}
    if name == "odds":
        d = http_get("/odds", {"fixture": clean.get("fixture")})
        f = soft_fail(d, name)
        if f: return f
        arr = d.get("response") or []
        return {"count": len(arr), "odds": [proj_odds(x) for x in arr[:5]]}
    return {"found": False, "reason": "unknown_tool", "hint": name}


def proj_fixture(x: dict) -> dict:
    fx = x.get("fixture", {})
    teams = x.get("teams", {})
    goals = x.get("goals", {})
    h = teams.get("home", {}); a = teams.get("away", {})
    return {"id": fx.get("id"), "date": fx.get("date"), "status": fx.get("status", {}).get("short"),
            "home": h.get("name"), "away": a.get("name"),
            "score": f"{goals.get('home')}-{goals.get('away')}",
            "league": x.get("league", {}).get("name")}


def proj_standing(t: dict) -> dict:
    return {"rank": t.get("rank"), "team": t.get("team", {}).get("name"), "points": t.get("points"),
            "played": t.get("all", {}).get("played"), "gd": t.get("goalsDiff"),
            "form": t.get("form"), "win": t.get("all", {}).get("win"),
            "draw": t.get("all", {}).get("draw"), "lose": t.get("all", {}).get("lose")}


def proj_team(x: dict) -> dict:
    t = x.get("team", {})
    return {"id": t.get("id"), "name": t.get("name"), "country": t.get("country"), "founded": t.get("founded")}


def proj_injury(x: dict) -> dict:
    p = x.get("player", {}); t = x.get("team", {})
    return {"player": p.get("name"), "team": t.get("name"), "type": p.get("type"),
            "reason": p.get("reason"), "date": p.get("date"), "fixture": (x.get("fixture") or {}).get("id")}


def proj_odds(x: dict) -> dict:
    fx = x.get("fixture", {}) or {}
    out = {"fixture": fx.get("id"), "date": fx.get("date"), "update": x.get("update"),
           "league": (x.get("league", {}) or {}).get("name")}
    bms = []
    for b in (x.get("bookmakers") or [])[:13]:
        bets = {}
        for bet in (b.get("bets") or []):
            bets[bet.get("name")] = {v.get("value"): v.get("odd") for v in (bet.get("values") or [])}
        bms.append({"bookmaker": b.get("name"), "markets": bets})
    out["bookmakers"] = bms
    return out


def main():
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid = msg.get("id")
        method = msg.get("method")
        params = msg.get("params") or {}
        if method == "initialize":
            out = {"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "api-football-lite", "version": "0.1.0"}}}
            print(json.dumps(out, ensure_ascii=False), flush=True)
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            out = {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
            print(json.dumps(out, ensure_ascii=False), flush=True)
        elif method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            try:
                res = call_tool(name, args)
            except Exception as e:
                res = {"found": False, "reason": "internal_error", "hint": str(e)[:300]}
            out = {"jsonrpc": "2.0", "id": mid,
                   "result": {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, indent=1)}],
                              "isError": bool(res.get("found") is False)}}
            print(json.dumps(out, ensure_ascii=False), flush=True)
        else:
            out = {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}}
            print(json.dumps(out, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
