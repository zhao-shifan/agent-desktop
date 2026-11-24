# -*- coding: utf-8 -*-
"""小凡智能体 · 工具层（function calling）

模型只决定「要不要用工具、用哪个、传什么参数」；真正干活的是这里：
联网搜索、抓网页、读文件、列目录、执行命令都在本机发生，结果再回灌给模型。
"""
import html
import json
import os
import re
import ast
import subprocess
import sys
import urllib.parse
import urllib.request
import fnmatch
import concurrent.futures
import threading
import socket
import ipaddress
import time

MAX_CHARS = 12000
MAX_ROUNDS = 4          # 一次提问里最多来回几轮工具调用
APP_ROOT = os.path.dirname(os.path.abspath(__file__))

# 部分精简版 Python 没带根证书，优先用 certifi；没有 certifi 时退回系统默认。
# 不再静默降级为"不校验证书"——那等于给中间人攻击开门，让证书错误直接暴露
try:
    import ssl
    try:
        import certifi
        _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        _SSL_CTX = ssl.create_default_context()
except Exception:
    ssl = None
    _SSL_CTX = None

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _http(url, data=None, headers=None, timeout=25):
    hdrs = {"User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs)
    kw = {"context": _SSL_CTX} if _SSL_CTX is not None else {}
    try:
        with urllib.request.urlopen(req, timeout=timeout, **kw) as r:
            # 限制单次最多读 5MB，防止恶意页面超大响应占内存
            raw, ctype = r.read(5 * 1024 * 1024), r.headers.get("Content-Type", "")
    except Exception as e:
        raise
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
        # 用 wait 而不是 as_completed：超时只放弃未完成的源，已完成的结果照常收集
        done, _ = concurrent.futures.wait(futures, timeout=20)
        for fut in done:
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


def get_time():
    """当前本地时间（LangChain datetime 工具同款用途，标准库实现）。"""
    import datetime as _dt
    now = _dt.datetime.now()
    week = "一二三四五六日"[now.weekday()]
    return ("现在时间：%s（周%s）\nISO：%s\nUnix 时间戳：%d"
            % (now.strftime("%Y-%m-%d %H:%M:%S"), week,
               now.isoformat(timespec="seconds"), int(now.timestamp())))


_CALC_ALLOWED_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
                        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
                        ast.Pow, ast.USub, ast.UAdd)


class _CalcTooBig(Exception):
    pass


def _calc_safe_pow(base, exp):
    """幂运算防卡死：9**9**9 这类表达式静态检查拦不住，求值时按位数拦截。"""
    if abs(exp) > 10000:
        raise _CalcTooBig()
    if base != 0 and abs(base) > 1 and abs(exp) > 0:
        import math
        digits = abs(exp) * math.log10(abs(base))
        if digits > 100000:   # 结果超过 10 万位数字就拒绝
            raise _CalcTooBig()
    return base ** exp


def _calc_eval(node):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp):
        l, r = _calc_eval(node.left), _calc_eval(node.right)
        op = type(node.op)
        if op is ast.Pow:
            return _calc_safe_pow(l, r)
        if op is ast.Add:
            return l + r
        if op is ast.Sub:
            return l - r
        if op is ast.Mult:
            return l * r
        if op is ast.Div:
            return l / r
        if op is ast.FloorDiv:
            return l // r
        if op is ast.Mod:
            return l % r
        raise _CalcTooBig()
    if isinstance(node, ast.UnaryOp):
        v = _calc_eval(node.operand)
        return -v if isinstance(node.op, ast.USub) else +v
    raise _CalcTooBig()


def calculator(expression):
    """安全计算器：AST 白名单求值，不 exec（LangChain Calculator 同用途，无依赖实现）。"""
    expr = str(expression or "").strip().replace("×", "*").replace("÷", "/").replace("^", "**")
    if not expr:
        return "表达式为空"
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return "表达式不合法：%s（只支持 + - * / % ** ( ) 和数字）" % e
    for node in ast.walk(tree):
        if not isinstance(node, _CALC_ALLOWED_NODES):
            return "不支持的内容：%s（计算器只做纯数值运算，代码请用 run_python）" % type(node).__name__
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            return "只允许数字常量，不允许字符串"
    try:
        value = _calc_eval(tree.body)   # 自定义求值：幂运算带防卡死上限
        out = ("%s = %s" % (expr, repr(value)))
        if isinstance(value, float) and value == int(value) and abs(value) < 1e15:
            out += "（整数结果：%d）" % int(value)
        return out
    except ZeroDivisionError:
        return "除零错误"
    except OverflowError:
        return "数值溢出"
    except _CalcTooBig:
        return "结果/中间值过大（超过 10 万位数字），请分步计算"
    except Exception as e:
        return "计算失败：%s" % e


def run_python(code, work_dir=""):
    """执行一段 Python 代码并返回输出（smolagents PythonInterpreterTool 同用途）。"""
    if not str(code or "").strip():
        return "代码为空"
    low = re.sub(r"\s+", " ", str(code).lower())
    for bad in ("shutil.rmtree(", "os.system('format", 'os.system("format',
                "os.remove(:", "format-volume", "subprocess.run('shutdown",
                "send2trash(", "zwdelete", "reg delete"):
        if bad in low:
            return "被拒绝：代码命中高危黑名单（%s），破坏性操作不做。" % bad
    import tempfile
    try:
        f = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8")
        f.write(code)
        f.close()
        p = subprocess.run([sys.executable, f.name], capture_output=True, timeout=60)
        out = (p.stdout or b"").decode("utf-8", errors="replace")
        err = (p.stderr or b"").decode("utf-8", errors="replace")
        text = (out + (("\n[stderr]\n" + err) if err.strip() else "")).strip() or "（没有输出，可用 print 输出结果）"
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS] + "\n…（已截断）"
        return "exit=%d\n%s" % (p.returncode, text)
    except subprocess.TimeoutExpired:
        return "代码超时（60 秒上限）"
    except Exception as e:
        return "执行失败：%s" % e
    finally:
        try:
            os.unlink(f.name)
        except Exception:
            pass


def wikipedia_search(query, lang="zh"):
    """维基百科搜索（smolagents WikipediaSearchTool 同用途；MediaWiki API 免 Key）。"""
    q = str(query or "").strip()
    if not q:
        return "搜索词为空"
    lang = lang if lang in ("zh", "en", "ja") else "zh"
    try:
        # 1) OpenSearch 找条目名
        data = json.loads(_http(
            "https://%s.wikipedia.org/w/api.php?action=opensearch&limit=5&format=json&search=%s"
            % (lang, urllib.parse.quote(q)),
            headers={"Accept": "application/json"}))
        titles = data[1] if isinstance(data, list) and len(data) > 1 else []
        if not titles:
            return "维基百科没找到「%s」相关条目" % q
        # 2) 逐条取摘要（REST summary 接口）
        out = []
        for i, title in enumerate(titles[:3], 1):
            try:
                s = json.loads(_http(
                    "https://%s.wikipedia.org/api/rest_v1/page/summary/%s"
                    % (lang, urllib.parse.quote(title.replace(" ", "_"))),
                    headers={"Accept": "application/json"}))
                extract = str(s.get("extract", ""))[:500]
                url = s.get("content_urls", {}).get("desktop", {}).get("page", "")
                out.append("%d. %s\n   %s\n   链接：%s" % (i, s.get("title", title), extract, url))
            except Exception:
                out.append("%d. %s（摘要获取失败）" % (i, title))
        return "\n\n".join(out)
    except Exception as e:
        return "维基百科查询失败：%s（可能是网络不通，被墙时用 web_search 代替）" % e


# 本地笔记（RAG-lite，mem0/LangChain Memory 同用途）：JSON 存储 + 关键词打分检索
# 路径延迟求值：frozen(exe) 模式下 server.py 会在运行时改写 APP_ROOT，
# import 时求值会把笔记写进解包临时目录，重启即丢
_NOTES_LOCK = threading.Lock()


def _notes_path():
    return os.path.join(APP_ROOT, "agent_data", "notes.json")


def _load_notes():
    try:
        with open(_notes_path(), "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    except Exception:
        return []


def save_note(title, content):
    """保存一条长期记忆笔记，供后续对话用 search_notes 检索。"""
    title, content = str(title or "").strip() or "未命名", str(content or "").strip()
    if not content:
        return "内容为空，没保存"
    import datetime as _dt
    with _NOTES_LOCK:
        notes = _load_notes()
        notes.insert(0, {"title": title, "content": content,
                         "time": _dt.datetime.now().strftime("%Y-%m-%d %H:%M")})
        os.makedirs(os.path.dirname(_notes_path()), exist_ok=True)
        with open(_notes_path(), "w", encoding="utf-8") as f:
            json.dump(notes[:500], f, ensure_ascii=False, indent=1)   # 上限 500 条
    return "已保存笔记「%s」（现共 %d 条）。之后用 search_notes 可以检索" % (title, min(len(notes), 500))


def search_notes(query):
    """按关键词检索自己的笔记（简单词重叠打分，无需向量库）。"""
    q = str(query or "").strip()
    if not q:
        return "检索词为空"
    notes = _load_notes()
    if not notes:
        return "还没有任何笔记，可先用 save_note 保存"
    terms = [t for t in re.split(r"[\s,，。;；|]+", q) if t]
    scored = []
    for n in notes:
        blob = (n.get("title", "") + " " + n.get("content", ""))
        score = sum(2 for t in terms if t in blob) + sum(1 for t in terms if t in n.get("title", ""))
        if score > 0:
            scored.append((score, n))
    if not scored:
        return "笔记里没搜到「%s」相关内容（共 %d 条笔记）" % (q, len(notes))
    scored.sort(key=lambda x: -x[0])
    out = ["搜到 %d 条相关笔记：" % len(scored)]
    for score, n in scored[:5]:
        out.append("「%s」（%s）：%s" % (n.get("title"), n.get("time"), str(n.get("content"))[:300]))
    return "\n".join(out)


def _is_private_host(host):
    """判断主机名是否指向内网/环回地址，防 SSRF（fetch_url 不允许打内网）。"""
    host = (host or "").strip().lower().strip("[]")
    if not host:
        return True
    if host in ("localhost",) or host.endswith(".localhost") or host.endswith(".local"):
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return True   # 解析失败的一律视为不可信
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast):
            return True
    return False


def fetch_url(url):
    if not re.match(r"^https?://", url or ""):
        return "只支持 http/https 链接"
    try:
        host = urllib.parse.urlsplit(url).hostname
    except Exception:
        return "链接不合法"
    if _is_private_host(host):
        return "被拒绝：不允许访问内网/本机地址（安全限制）"
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


def write_file(path, content, work_dir=""):
    """新建或整体覆盖一个文本文件（参考 smolagents save_file：先校验边界再写）。"""
    full = _check_path(path, work_dir)
    content = str(content or "")
    existed = os.path.isfile(full)
    if existed and os.path.getsize(full) > 0:
        with open(full, "rb") as f:
            old = f.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
    else:
        old = ""
    os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    if existed:
        return "已覆盖 %s（原 %d 字符 → 新 %d 字符）" % (full, len(old), len(content))
    return "已创建 %s（%d 字符）" % (full, len(content))


def edit_file(path, old_string, new_string, work_dir="", replace_all=False):
    """局部替换（参考 dsh/claude code 的 edit：old 必须唯一命中，防写坏文件）。"""
    full = _check_path(path, work_dir)
    if not os.path.isfile(full):
        return "文件不存在：%s（先用 write_file 创建，或用 read_file 确认路径）" % full
    if os.path.getsize(full) > 8 * 1024 * 1024:
        return "文件太大（>8MB），请用 run_command 处理"
    with open(full, "rb") as f:
        data = f.read()
    text = None
    for enc in ("utf-8", "gbk"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return "看起来是二进制文件，编辑不了"
    old_string, new_string = str(old_string or ""), str(new_string or "")
    if not old_string:
        return "old_string 不能为空（覆盖整个文件请用 write_file）"
    n = text.count(old_string)
    if n == 0:
        return "old_string 在文件中没找到，先 read_file 核对原文（注意空格/换行）"
    if n > 1 and not replace_all:
        return "old_string 出现了 %d 次，为避免误改请扩大上下文使其唯一，或确认后用 replace_all=true" % n
    new_text = text.replace(old_string, new_string, n if (replace_all and n > 1) else 1)
    with open(full, "w", encoding=enc, newline="") as f:
        f.write(new_text)
    return "已编辑 %s：%d 处替换（%d → %d 字符）" % (full, n if (replace_all and n > 1) else 1, len(text), len(new_text))


def grep(pattern, path=".", work_dir="", max_results=30):
    """按正则搜文件内容（参考 ripgrep 语义，纯标准库实现）。"""
    import fnmatch as _fnm
    full = _check_path(path, work_dir)
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return "正则不合法：%s" % e
    max_results = max(1, min(int(max_results or 30), 100))
    hits, scanned = [], 0
    for dirpath, dirnames, filenames in os.walk(full):
        dirnames[:] = [d for d in dirnames if d not in (
            ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".idea", ".vscode")]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(p) > 2 * 1024 * 1024:
                    continue
            except OSError:
                continue
            scanned += 1
            try:
                with open(p, "rb") as f:
                    text = f.read().decode("utf-8", errors="ignore")
            except OSError:
                continue
            if "\x00" in text[:2000]:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append("%s:%d: %s" % (os.path.relpath(p, full), i, line.strip()[:200]))
                    if len(hits) >= max_results:
                        return "找到 %d+ 处（已截断，扫了 %d 个文件）：\n%s" % (max_results, scanned, "\n".join(hits))
    if not hits:
        return "没搜到匹配（扫了 %d 个文件）。试试放宽正则，或先用 list_dir 确认目录" % scanned
    return "找到 %d 处（扫了 %d 个文件）：\n%s" % (len(hits), scanned, "\n".join(hits))


def glob_files(pattern, path=".", work_dir=""):
    """按通配符找文件，如 **/*.py。限制在允许目录内。"""
    full = _check_path(path, work_dir)
    matches = []
    for dirpath, dirnames, filenames in os.walk(full):
        dirnames[:] = [d for d in dirnames if d not in (
            ".git", "node_modules", "__pycache__", ".venv", "venv")]
        for fn in filenames:
            rel = os.path.relpath(os.path.join(dirpath, fn), full).replace("\\", "/")
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(fn, pattern):
                matches.append(rel)
                if len(matches) >= 200:
                    break
        if len(matches) >= 200:
            break
    if not matches:
        return "没找到匹配 %s 的文件（在 %s 下）。注意 pattern 用相对路径，如 **/*.py" % (pattern, full)
    return "%s 下匹配 %s 的文件（%d 个，已截断则取前 200）：\n%s" % (
        full, pattern, len(matches), "\n".join(matches[:200]))


# 高危命令黑名单：即使 allowCommand 开着也拒绝（提示注入的最后防线）。
# 命中即拒，宁可误杀不可放行破坏性操作
_DANGEROUS_CMDS = (
    "format ", "format-volume", "diskpart", "cipher /w", "rd /s /q c:",
    "remove-item -recurse", "remove-itemitem -r", "rm -rf /", "rm -rf ~",
    "del /f /s /q c:\\", "rmdir /s /q c:\\", "shutdown", "restart-computer",
    "reg delete hk", "reg add hk", "bcdedit", "vssadmin delete",
    "wmic shadowshadow", "mklink", "attrib -s -h", "schtasks /create",
    "net user ", "net localgroup", "set-mppreference", "add-mppreference",
    "invoke-expression (invoke-webrequest", "iex (iwr", "iex(iwr",
    "curl | iex", "curl|bash", "wget | sh", "start-process -verb runas",
    "-encodedcommand", "downloadsstring", "netstat -ano", "taskkill /f /im",
)


def run_command(command, work_dir=""):
    low = " " + re.sub(r"\s+", " ", str(command or "").lower()) + " "
    for bad in _DANGEROUS_CMDS:
        if bad in low:
            return ("被拒绝：命令命中高危黑名单（%s…）。\n"
                    "这类破坏性/系统级操作一律不做；如是用户明确要求，请让用户自己在终端手动执行。" % bad.strip())
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
        "name": "write_file",
        "description": "新建或整体覆盖一个文本文件。修改已有文件请优先用 edit_file（更省更安全）。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "绝对路径"},
            "content": {"type": "string", "description": "完整文件内容"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "edit_file",
        "description": "对已有文件做精确局部替换：old_string 必须与原文唯一匹配。改代码/文档首选这个。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "old_string": {"type": "string", "description": "要替换的原文（带足够上下文保证唯一）"},
            "new_string": {"type": "string", "description": "替换后的新文本"},
            "replace_all": {"type": "boolean", "description": "替换全部匹配，默认只替换唯一一处"}},
            "required": ["path", "old_string", "new_string"]}}},
    {"type": "function", "function": {
        "name": "grep",
        "description": "在工作目录内按正则搜索文件内容，返回 文件:行号:内容。找代码/找配置先用它。",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "正则表达式"},
            "path": {"type": "string", "description": "起始目录，默认工作目录"},
            "max_results": {"type": "integer", "description": "最多返回条数，默认 30"}},
            "required": ["pattern"]}}},
    {"type": "function", "function": {
        "name": "glob_files",
        "description": "按通配符找文件路径，如 **/*.py、report*.docx。不知道确切文件名时先 glob 再 read。",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "通配符，如 **/*.py"},
            "path": {"type": "string", "description": "起始目录，默认工作目录"}},
            "required": ["pattern"]}}},
    {"type": "function", "function": {
        "name": "run_command",
        "description": "在本机执行一条命令并返回输出（仅当用户开启了命令权限时可用）。",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "get_time",
        "description": "获取当前本地时间、星期、时间戳。用户问'现在几点/今天星期几'或需要时间基准时使用（无需联网）。",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "calculator",
        "description": "精确计算数学表达式（+ - * / % ** 和括号）。任何数值计算都必须用它，不要心算，避免算错。",
        "parameters": {"type": "object", "properties": {
            "expression": {"type": "string", "description": "数学表达式，如 (1250*0.85+360)/3"}},
            "required": ["expression"]}}},
    {"type": "function", "function": {
        "name": "run_python",
        "description": "执行一段 Python 代码并返回 print 输出（60 秒上限）。适合复杂数据处理、批量计算、文件解析等计算器搞不定的事。仅当用户开启命令权限时可用。",
        "parameters": {"type": "object", "properties": {
            "code": {"type": "string", "description": "完整 Python 代码，结果用 print() 输出"}},
            "required": ["code"]}}},
    {"type": "function", "function": {
        "name": "wikipedia_search",
        "description": "查询维基百科百科知识（人物/概念/历史/术语等），返回摘要和链接。通用知识类问题优先用它，实时信息用 web_search。",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "条目关键词"},
            "lang": {"type": "string", "description": "语言版本 zh/en/ja，默认 zh"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "save_note",
        "description": "把重要信息（用户偏好、结论、待办、事实）存成长期记忆笔记，跨对话可用。用户说'记住这个/记一下'时必须用它。",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description": "简短标题"},
            "content": {"type": "string", "description": "要记住的内容"}},
            "required": ["title", "content"]}}},
    {"type": "function", "function": {
        "name": "search_notes",
        "description": "检索之前保存的长期记忆笔记。用户问'我之前让你记的…/我的偏好是什么'或需要历史信息时先用它。",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "检索关键词"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "get_location",
        "description": "按出口 IP 粗略判断用户所在城市（免 Key、无需授权，精度到城市）。用户问天气/本地信息但没说城市时可先调它。",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "lark_cli",
        "description": "调用飞书/Lark 命令行（lark-cli，全量 OpenAPI）。可查日程/任务/消息记录/文档/多维表格/审批/OKR 等一切飞书功能。读操作直接执行；发消息、建文档等写操作需用户开启命令权限。args 为 lark-cli 子命令字符串，如 \"calendar +agenda\"、\"task +get-my-tasks\"、\"im +search 王小凡\"。",
        "parameters": {"type": "object", "properties": {
            "args": {"type": "string", "description": "lark-cli 子命令及参数（不含 lark-cli 本身）"}},
            "required": ["args"]}}},
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
        # 不再静默置空：告诉模型参数格式错了，让它修正重试，避免浪费轮次
        return "参数不是合法 JSON（收到：%s）。请修正 arguments 格式后重试。" % str(raw)[:200]
    work_dir = perm.get("workDir") or ""
    # MCP 工具：名字以 mcp_ 开头的走 MCP 服务器执行（tools/call）
    if name.startswith("mcp_"):
        return mcp_call_tool(name, args)
    if name == "lark_cli":
        return lark_cli(args.get("args", ""), perm)
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
        if name == "write_file":
            return write_file(args.get("path", ""), args.get("content", ""), work_dir)
        if name == "edit_file":
            return edit_file(args.get("path", ""), args.get("old_string", ""),
                             args.get("new_string", ""), work_dir,
                             bool(args.get("replace_all")))
        if name == "grep":
            return grep(args.get("pattern", ""), args.get("path", "."), work_dir,
                        args.get("max_results", 30))
        if name == "glob_files":
            return glob_files(args.get("pattern", ""), args.get("path", "."), work_dir)
        if name == "run_command":
            if not perm.get("allowCommand"):
                return "被拒绝：用户没有开启命令执行权限，请让用户到设置里打开「允许执行命令」。"
            return run_command(args.get("command", ""), work_dir)
        if name == "get_time":
            return get_time()
        if name == "calculator":
            return calculator(args.get("expression", ""))
        if name == "run_python":
            if not perm.get("allowCommand"):
                return "被拒绝：用户没有开启命令执行权限，请让用户到设置里打开「允许执行命令」。"
            return run_python(args.get("code", ""), work_dir)
        if name == "wikipedia_search":
            return wikipedia_search(args.get("query", ""), args.get("lang", "zh"))
        if name == "save_note":
            return save_note(args.get("title", ""), args.get("content", ""))
        if name == "search_notes":
            return search_notes(args.get("query", ""))
        if name == "get_location":
            return get_location()
        if name == "get_weather":
            return get_weather(args.get("city", ""), args.get("days", 3))
        return "未知工具：%s" % name
    except PermissionError as e:
        return "被拒绝：%s" % e
    except Exception as e:
        return "工具执行失败：%s" % e


def _which_lark():
    import shutil
    return shutil.which("lark-cli") or shutil.which("lark-cli.cmd")


# lark-cli 写操作动词：这些需要用户开"允许执行命令"权限（防止模型擅自发消息/改文档）
_LARK_WRITE_WORDS = ("send", "create", "delete", "update", "write", "reply", "add",
                     "remove", "patch", "set", "move", "mark", "upload", "import",
                     "approve", "reject", "subscribe", "unsubscribe")


def lark_cli(args, perm=None):
    """调用飞书命令行工具 lark-cli（全量 OpenAPI：消息/日历/任务/文档/表格/审批/OKR…）。
    读操作直接放行；写操作（发消息/建文档/改数据等）需要用户开「允许执行命令」。"""
    exe = _which_lark()
    if not exe:
        return "本机没有安装 lark-cli（npm install -g 后重启小凡）"
    a = str(args or "").strip()
    if not a:
        return "用法：lark_cli(args=\"<子命令> <参数>…\")，如 args=\"calendar +agenda\""
    low = " " + re.sub(r"\s+", " ", a.lower()) + " "
    # 安全白名单：凭据/登录态相关一律不给模型碰
    if re.search(r"\b(logout|token|credential|dpop|config\s+set)\b", low):
        return "被拒绝：登录态/凭据相关命令不开放给模型。"
    if not perm or not perm.get("allowCommand"):
        if any(w in low for w in _LARK_WRITE_WORDS):
            return ("被拒绝：这是飞书写操作（发消息/建文档/改数据），需要用户在设置里"
                    "打开「允许执行命令」权限；查询类操作不受限，可先做只读查询。")
    import shlex
    try:
        argv = [exe] + shlex.split(a)
    except ValueError as e:
        return "参数解析失败：%s" % e
    try:
        p = subprocess.run(argv, capture_output=True, timeout=90)
        out = (p.stdout or b"").decode("utf-8", errors="replace")
        err = (p.stderr or b"").decode("utf-8", errors="replace")
        text = (out + (("\n[stderr]\n" + err) if err.strip() else "")).strip()
        text = text or "（命令执行成功，无输出）"
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS] + "\n…（已截断）"
        return "exit=%d\n%s" % (p.returncode, text)
    except subprocess.TimeoutExpired:
        return "lark-cli 超时（90 秒上限）"
    except Exception as e:
        return "执行失败：%s" % e


# ==================================================================
# MCP（Model Context Protocol）客户端 —— 零依赖实现
# 协议：Anthropic 开源的 stdio JSON-RPC（MIT）。配置 agent_data/mcp_servers.json
# 后，启动时拉起各 MCP 服务器，把它们的工具自动挂进 TOOL_DEFS（前缀 mcp_），
# 小凡即插即用整个 MCP 生态的现成工具，无需逐个手写。
# ==================================================================

_MCP_PROCS = {}        # server名 -> Popen
_MCP_TOOLS = {}        # server名 -> [ {name, description, inputSchema} ]
_MCP_STATUS = {}       # server名 -> starting / ready / failed:原因
_MCP_LOCK = threading.Lock()
_MCP_NEXT_ID = [1]


def _mcp_config_path():
    return os.path.join(APP_ROOT, "agent_data", "mcp_servers.json")


def _mcp_rpc(proc, method, params, timeout=30):
    """给 MCP 服务器发一条 JSON-RPC 请求，按 id 等回对应响应（行分隔 JSON）。
    每个 MCP 服务器一把锁：不同服务器可并发调用，互不阻塞。"""
    locks = _MCP_PROCS.setdefault("#locks", {})
    lock = locks.setdefault(id(proc), threading.Lock())
    with lock:
        rid = _MCP_NEXT_ID[0]
        _MCP_NEXT_ID[0] += 1
        req = (json.dumps({"jsonrpc": "2.0", "id": rid, "method": method,
                           "params": params}) + "\n").encode("utf-8")
        proc.stdin.write(req)
        proc.stdin.flush()
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                raise ConnectionError("MCP 服务器关闭了连接")
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line.decode("utf-8", errors="replace"))
            except Exception:
                continue
            if msg.get("id") == rid:
                if "error" in msg:
                    raise RuntimeError("MCP 错误: %s" % msg["error"])
                return msg.get("result") or {}
        raise TimeoutError("MCP 响应超时（%ss）" % timeout)


def mcp_reset():
    """停掉所有 MCP 服务器进程并清空状态（设置里保存配置后重新挂载用）。"""
    for p in _MCP_PROCS.values():
        try:
            p.kill()
        except Exception:
            pass
    _MCP_PROCS.clear()
    _MCP_TOOLS.clear()
    _MCP_STATUS.clear()


def mcp_status():
    """返回当前挂载概览（服务器名 → 工具名列表）。"""
    return {s: [t["name"] for t in tools] for s, tools in _MCP_TOOLS.items()}


def mcp_lifecycle():
    """返回每个服务器的生命周期状态（starting/ready/failed），前端展示首次下载进度用。"""
    return dict(_MCP_STATUS)


def mcp_init():
    """读配置、拉起所有 MCP 服务器、握手并拉取工具清单。失败的服务器跳过不拖垮主程序。"""
    cfg_path = _mcp_config_path()
    try:
        cfg = json.loads(open(cfg_path, "rb").read().decode("utf-8"))
    except Exception:
        return
    for srv in cfg.get("servers") or []:
        sname = str(srv.get("name") or "").strip()
        cmd = srv.get("command") or ""
        if not sname or not cmd or sname in _MCP_PROCS:
            continue
        _MCP_STATUS[sname] = "starting"   # 首次运行 npx/uvx 会下载包，可能要等几十秒
        try:
            proc = subprocess.Popen(
                [cmd] + list(srv.get("args") or []),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=srv.get("cwd") or None,
                env={**os.environ, **(srv.get("env") or {})})
            _MCP_PROCS[sname] = proc
            _mcp_rpc(proc, "initialize", {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "xiaofan", "version": "1.9"}}, timeout=120)
            proc.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
            proc.stdin.flush()
            res = _mcp_rpc(proc, "tools/list", {}, timeout=60)
            tools = []
            for t in (res.get("tools") or []):
                tname = "%s" % t.get("name", "")
                tools.append({
                    "name": "mcp_%s_%s" % (sname, tname),
                    "description": "[MCP:%s] %s" % (sname, t.get("description", "")),
                    "inputSchema": t.get("inputSchema") or {"type": "object", "properties": {}}})
            _MCP_TOOLS[sname] = tools
            _MCP_STATUS[sname] = "ready"
            print("[MCP] %s 已连接，挂载 %d 个工具" % (sname, len(tools)), flush=True)
        except Exception as e:
            _MCP_STATUS[sname] = "failed:%s" % str(e)[:120]
            print("[MCP] %s 启动失败，已跳过：%s" % (sname, e), flush=True)
            try:
                _MCP_PROCS.pop(sname, None).kill()
            except Exception:
                pass


def mcp_tool_defs():
    """把所有 MCP 服务器工具转成 OpenAI function calling 格式，追加到工具清单。"""
    out = []
    for tools in _MCP_TOOLS.values():
        for t in tools:
            out.append({"type": "function", "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["inputSchema"]}})
    return out


def mcp_call_tool(fullname, args):
    """执行 mcp_<server>_<tool> 形式的调用。"""
    rest = fullname[len("mcp_"):]
    for sname in _MCP_TOOLS:
        if rest.startswith(sname + "_"):
            tool = rest[len(sname) + 1:]
            proc = _MCP_PROCS.get(sname)
            if not proc or proc.poll() is not None:
                return "MCP 服务器 %s 已断开" % sname
            try:
                res = _mcp_rpc(proc, "tools/call",
                               {"name": tool, "arguments": args}, timeout=120)
                parts = []
                for c in (res.get("content") or []):
                    if c.get("type") == "text":
                        parts.append(c.get("text", ""))
                    else:
                        parts.append(json.dumps(c, ensure_ascii=False))
                if res.get("isError"):
                    return "工具返回错误：" + ("\n".join(parts) or "未知错误")
                return ("\n".join(parts) or "（无输出）")[:MAX_CHARS]
            except Exception as e:
                return "MCP 调用失败：%s" % e
    return "未知 MCP 工具：%s" % fullname
