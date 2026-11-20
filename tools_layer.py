# -*- coding: utf-8 -*-
"""小凡智能体 · 工具层（function calling）

模型只决定「要不要用工具、用哪个、传什么参数」；真正干活的是这里：
联网搜索、抓网页、读文件、列目录、执行命令都在本机发生，结果再回灌给模型。
"""
import html
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
import concurrent.futures

MAX_CHARS = 12000
MAX_ROUNDS = 4          # 一次提问里最多来回几轮工具调用
APP_ROOT = os.path.dirname(os.path.abspath(__file__))

# 部分精简版 Python 没带根证书，优先用 certifi，实在没有就退化为不校验证书
try:
    import ssl
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
    _SSL_FALLBACK = ssl._create_unverified_context()
except Exception:
    ssl = None
    _SSL_CTX = None
    _SSL_FALLBACK = None

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _http(url, data=None, headers=None, timeout=25):
    hdrs = {"User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs)
    try:
        kw = {"context": _SSL_CTX} if _SSL_CTX is not None else {}
        with urllib.request.urlopen(req, timeout=timeout, **kw) as r:
            raw, ctype = r.read(), r.headers.get("Content-Type", "")
    except Exception:
        if _SSL_FALLBACK is None:
            raise
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_FALLBACK) as r:
            raw, ctype = r.read(), r.headers.get("Content-Type", "")
    m = re.search(r"charset=([\w-]+)", ctype, re.I)
    charset = m.group(1) if m else "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def strip_html(s):
    s = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>|</tr>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\u00a0]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()


def _parse_ddg(page, count):
    out, seen = [], set()
    for m in re.finditer(r'(?is)<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page):
        href, title = html.unescape(m.group(1)), strip_html(m.group(2))
        if "uddg=" in href:
            try:
                href = urllib.parse.unquote(re.search(r"uddg=([^&]+)", href).group(1))
            except Exception:
                pass
        if not href.startswith("http") or href in seen or not title:
            continue
        seen.add(href)
        out.append({"title": title, "url": href, "snippet": ""})
        if len(out) >= count:
            break
    snippets = [strip_html(s) for s in
                re.findall(r'(?is)class="result__snippet"[^>]*>(.*?)</a>', page)]
    for i, sn in enumerate(snippets[:len(out)]):
        if sn:
            out[i]["snippet"] = sn[:220]
    return out


def _parse_360(page, count):
    out = []
    for m in re.finditer(r'(?is)<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page):
        href, title = html.unescape(m.group(1)), strip_html(m.group(2))
        if not href.startswith("http") or not title:
            continue
        out.append({"title": title, "url": href, "snippet": ""})
        if len(out) >= count:
            break
    return out


def _parse_bing(page, count):
    out = []
    blocks = re.findall(r'(?is)<li class="b_algo".*?</li>', page)
    for b in blocks:
        mt = re.search(r'(?is)<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', b)
        if not mt:
            continue
        href, title = html.unescape(mt.group(1)), strip_html(mt.group(2))
        if not href.startswith("http") or not title:
            continue
        ms = re.search(r'(?is)<p[^>]*>(.*?)</p>', b)
        out.append({"title": title, "url": href,
                    "snippet": strip_html(ms.group(1)) if ms else ""})
        if len(out) >= count:
            break
    return out


def _parse_baidu(page, count):
    out = []
    for m in re.finditer(r'(?is)<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page):
        href, title = html.unescape(m.group(1)), strip_html(m.group(2))
        if not href.startswith("http") or not title:
            continue
        out.append({"title": title, "url": href, "snippet": ""})
        if len(out) >= count:
            break
    return out


# 免 Key 的多引擎：并发抓取后合并去重，任何一个源挂了都不影响整体
_SEARCH_SOURCES = [
    ("bing", "https://cn.bing.com/search?q=%s&setlang=zh-CN", _parse_bing),
    ("360", "https://www.so.com/s?q=%s", _parse_360),
    ("ddg", "https://html.duckduckgo.com/html/?q=%s", _parse_ddg),
    ("baidu", "https://www.baidu.com/s?wd=%s", _parse_baidu),
]


def _norm_url(u):
    u = re.sub(r"^https?://", "", u.lower())
    u = re.sub(r"^www\.", "", u)
    return u.rstrip("/").split("#")[0]


def _multi_engine_search(query, count):
    q = urllib.parse.quote(query)
    results, seen = [], set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(_SEARCH_SOURCES)) as ex:
        futures = {ex.submit(_http, url % q, None, None, 15): (name, parser)
                   for name, url, parser in _SEARCH_SOURCES}
        for fut in concurrent.futures.as_completed(futures, timeout=20):
            name, parser = futures[fut]
            try:
                items = parser(fut.result(), count)
            except Exception:
                continue
            for it in items:
                key = _norm_url(it["url"])
                if not key or key in seen:
                    continue
                seen.add(key)
                it["source"] = name
                results.append(it)
                if len(results) >= count * 2:
                    break
    return results


def web_search(query, count=5, key=""):
    """联网搜索：有 Key 走 Tavily，否则多引擎聚合（bing/360/ddg/baidu）后去重。"""
    count = max(1, min(int(count or 5), 10))
    if not (query or "").strip():
        return "搜索关键词为空"
    q = query.strip()

    if key:
        try:
            body = json.dumps({"api_key": key, "query": q, "max_results": count,
                               "include_answer": True}).encode()
            data = json.loads(_http("https://api.tavily.com/search", data=body,
                                    headers={"Content-Type": "application/json"}))
            out = []
            if data.get("answer"):
                out.append("概要：" + str(data["answer"])[:600])
            for i, r in enumerate(data.get("results", [])[:count], 1):
                out.append("%d. %s\n   %s\n   %s" % (
                    i, r.get("title", ""), r.get("url", ""), str(r.get("content", ""))[:300]))
            if out:
                return "\n".join(out)
        except Exception:
            pass

    try:
        items = _multi_engine_search(q, count)
    except Exception as e:
        return "（搜索失败：%s）" % e
    if not items:
        return "（没搜到结果，换个关键词再试）"

    lines = []
    for i, it in enumerate(items[:count], 1):
        block = "%d. %s\n   %s" % (i, it["title"], it["url"])
        if it.get("snippet"):
            block += "\n   " + it["snippet"][:220]
        block += "\n   — 来源：%s" % it.get("source", "")
        lines.append(block)
    return "\n".join(lines)


def get_location():
    """按出口 IP 粗略定位（免 Key）。返回城市/省份/国家与经纬度。"""
    for url, parser in [
        ("http://ip-api.com/json/?lang=zh-CN",
         lambda d: (d.get("city"), d.get("regionName"), d.get("country"),
                    d.get("lat"), d.get("lon"), d.get("isp"))),
        ("https://ipapi.co/json/",
         lambda d: (d.get("city"), d.get("region"), d.get("country_name"),
                    d.get("latitude"), d.get("longitude"), d.get("org"))),
    ]:
        try:
            data = json.loads(_http(url))
            city, region, country, lat, lon, isp = parser(data)
            if not city:
                continue
            return ("IP 定位结果（精度到城市，VPN 会偏）：\n"
                    "城市：%s\n省份：%s\n国家：%s\n经纬度：%s, %s\n网络：%s\n"
                    "（如需精确位置，请在手机/浏览器里授权定位）"
                    % (city, region or "-", country or "-", lat, lon, isp or "-"))
        except Exception:
            continue
    return "IP 定位失败（网络不通或接口限流），可以让用户直接告诉你城市"


def _geocode(city):
    """城市名 → 经纬度，Open-Meteo 地理编码（免 Key）。"""
    url = "https://geocoding-api.open-meteo.com/v1/search?count=1&language=zh&format=json&name=" + \
          urllib.parse.quote(city)
    data = json.loads(_http(url))
    results = data.get("results") or []
    if not results:
        return None
    r = results[0]
    return r.get("name"), r.get("latitude"), r.get("longitude"), r.get("country")


_WEATHER_CODES = {
    0: "晴", 1: "晴间多云", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇",
    51: "毛毛雨", 53: "小雨", 55: "中雨", 61: "小雨", 63: "中雨", 65: "大雨",
    71: "小雪", 73: "中雪", 75: "大雪", 80: "阵雨", 81: "强阵雨", 82: "暴雨",
    95: "雷阵雨", 96: "雷阵雨伴冰雹", 99: "强雷暴",
}


def get_weather(city="", days=3):
    """天气：Open-Meteo（免 Key）。city 为空则先 IP 定位。"""
    days = max(1, min(int(days or 3), 7))
    place, lat, lon = None, None, None
    if city:
        g = _geocode(city)
        if not g:
            return "找不到城市：%s" % city
        place, lat, lon, country = g
        place = "%s（%s）" % (place, country or "")
    else:
        try:
            ip = json.loads(_http("http://ip-api.com/json/?lang=zh-CN"))
            lat, lon = ip.get("lat"), ip.get("lon")
            place = "%s（IP 定位）" % (ip.get("city") or "当前位置")
        except Exception:
            return "没给城市，IP 定位也失败了，让用户直接说个城市名"

    url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
           "&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
           "&timezone=auto&forecast_days=%d" % (lat, lon, days))
    data = json.loads(_http(url))
    cur = data.get("current") or {}
    daily = data.get("daily") or {}
    lines = ["%s 当前天气：%s，%s℃，体感 %s℃，湿度 %s%%，风速 %s km/h" % (
        place,
        _WEATHER_CODES.get(cur.get("weather_code"), "未知"),
        cur.get("temperature_2m"), cur.get("apparent_temperature"),
        cur.get("relative_humidity_2m"), cur.get("wind_speed_10m"))]
    dates = daily.get("time") or []
    for i, d in enumerate(dates[:days]):
        lines.append("%s：%s，%s~%s℃，降水概率 %s%%" % (
            d,
            _WEATHER_CODES.get((daily.get("weather_code") or [None])[i], "未知"),
            (daily.get("temperature_2m_min") or [None])[i],
            (daily.get("temperature_2m_max") or [None])[i],
            (daily.get("precipitation_probability_max") or [None])[i]))
    return "\n".join(lines)


def fetch_url(url):
    if not re.match(r"^https?://", url or ""):
        return "只支持 http/https 链接"
    raw = _http(url)
    text = ""
    # 首选 trafilatura：社区标准的正文抽取库，去导航/广告/页脚效果远好于正则
    try:
        import trafilatura
        text = trafilatura.extract(raw, url=url, include_comments=False,
                                   include_tables=True, favor_recall=True) or ""
    except Exception:
        text = ""
    if len(text.strip()) < 200:
        text = strip_html(raw)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n…（已截断）"
    return text or "（页面没有可读正文）"


def _roots(work_dir):
    roots = [os.path.abspath(APP_ROOT)]
    for p in str(work_dir or "").split(";"):
        p = p.strip()
        if p:
            roots.append(os.path.abspath(os.path.expanduser(p)))
    if len(roots) == 1:
        roots.append(os.path.abspath(os.path.expanduser("~")))
    return roots


def _check_path(path, work_dir):
    full = os.path.abspath(os.path.expanduser(path or "."))
    for root in _roots(work_dir):
        try:
            if os.path.commonpath([full, root]) == root:
                return full
        except ValueError:
            continue
    raise PermissionError("超出允许范围：%s（到设置里加「工作目录」）" % full)


def read_file(path, work_dir="", start=0, lines=400):
    full = _check_path(path, work_dir)
    if not os.path.isfile(full):
        return "文件不存在：%s" % full
    if os.path.getsize(full) > 8 * 1024 * 1024:
        return "文件太大（>8MB）"
    with open(full, "rb") as f:
        data = f.read()
    for enc in ("utf-8", "gbk"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return "看起来是二进制文件，读不了"
    rows = text.splitlines()
    start = max(0, int(start or 0))
    chunk = rows[start:start + max(1, int(lines or 400))]
    body = "\n".join(chunk)
    if len(body) > MAX_CHARS:
        body = body[:MAX_CHARS] + "\n…（已截断）"
    return "%s（共 %d 行，本次 %d-%d）\n%s" % (
        full, len(rows), start + 1, start + len(chunk), body)


def list_dir(path=".", work_dir=""):
    full = _check_path(path, work_dir)
    if not os.path.isdir(full):
        return "目录不存在：%s" % full
    items = []
    for name in sorted(os.listdir(full))[:200]:
        p = os.path.join(full, name)
        try:
            items.append("[目录] " + name if os.path.isdir(p)
                         else "%s  %dKB" % (name, os.path.getsize(p) // 1024))
        except OSError:
            continue
    return full + "\n" + "\n".join(items)


def run_command(command, work_dir=""):
    cwd = None
    if work_dir:
        try:
            cwd = _check_path(work_dir, work_dir)
        except PermissionError:
            cwd = None
    shell = (["powershell", "-NoProfile", "-Command", command]
             if os.name == "nt" else ["bash", "-lc", command])
    try:
        p = subprocess.run(shell, capture_output=True, timeout=60, cwd=cwd)
        out = (p.stdout or b"").decode("utf-8", errors="replace")
        err = (p.stderr or b"").decode("utf-8", errors="replace")
        text = (out + (("\n[stderr]\n" + err) if err.strip() else "")).strip()
        text = text or "（命令没有输出）"
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS] + "\n…（已截断）"
        return "exit=%d\n%s" % (p.returncode, text)
    except subprocess.TimeoutExpired:
        return "命令超时（60 秒）"


TOOL_DEFS = [
    {"type": "function", "function": {
        "name": "web_search",
        "description": "联网搜索最新信息，返回标题、链接和摘要。涉及实时新闻、版本号、价格等需要查证的内容时使用。",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "count": {"type": "integer", "description": "结果条数 1-10，默认 5"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "fetch_url",
        "description": "抓取指定网页的正文纯文本，用于精读搜索结果。",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "读取本机文本文件（代码、配置、文档）。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "绝对路径"},
            "start": {"type": "integer", "description": "起始行，默认 0"},
            "lines": {"type": "integer", "description": "读取行数，默认 400"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "列出目录内容，找文件时先用它。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "run_command",
        "description": "在本机执行一条命令并返回输出（仅当用户开启了命令权限时可用）。",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "get_location",
        "description": "按出口 IP 粗略判断用户所在城市（免 Key、无需授权，精度到城市）。用户问天气/本地信息但没说城市时可先调它。",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "get_weather",
        "description": "查询当前天气和未来几天预报（Open-Meteo，免 Key）。",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string", "description": "城市名，如 上海；留空则按 IP 定位"},
            "days": {"type": "integer", "description": "预报天数 1-7，默认 3"}}}}},
]


def run_tool(call, perm=None):
    """执行一个 tool_call，返回字符串结果。"""
    perm = perm or {}
    fn = (call.get("function") or {})
    name = fn.get("name") or ""
    raw = fn.get("arguments") or "{}"
    try:
        args = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception:
        args = {}
    work_dir = perm.get("workDir") or ""
    try:
        if name == "web_search":
            return web_search(args.get("query", ""), args.get("count", 5),
                              perm.get("searchKey") or "")
        if name == "fetch_url":
            return fetch_url(args.get("url", ""))
        if name == "read_file":
            return read_file(args.get("path", ""), work_dir,
                             args.get("start", 0), args.get("lines", 400))
        if name == "list_dir":
            return list_dir(args.get("path", "."), work_dir)
        if name == "run_command":
            if not perm.get("allowCommand"):
                return "被拒绝：用户没有开启命令执行权限，请让用户到设置里打开「允许执行命令」。"
            return run_command(args.get("command", ""), work_dir)
        if name == "get_location":
            return get_location()
        if name == "get_weather":
            return get_weather(args.get("city", ""), args.get("days", 3))
        return "未知工具：%s" % name
    except PermissionError as e:
        return "被拒绝：%s" % e
    except Exception as e:
        return "工具执行失败：%s" % e
