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
        out.append("%d. %s\n   %s" % (len(out) + 1, title, href))
        if len(out) >= count:
            break
    snippets = [strip_html(s) for s in
                re.findall(r'(?is)class="result__snippet"[^>]*>(.*?)</a>', page)]
    for i, sn in enumerate(snippets[:len(out)]):
        if sn:
            out[i] += "\n   " + sn[:220]
    return out


def _parse_360(page, count):
    out = []
    for m in re.finditer(r'(?is)<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page):
        href, title = html.unescape(m.group(1)), strip_html(m.group(2))
        if not href.startswith("http") or not title:
            continue
        out.append("%d. %s\n   %s" % (len(out) + 1, title, href))
        if len(out) >= count:
            break
    return out


def web_search(query, count=5, key=""):
    """联网搜索。有 Tavily Key 走 Tavily；否则 DuckDuckGo，再不行用 360 兜底。"""
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

    errors = []
    try:
        res = _parse_ddg(_http("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q)), count)
        if res:
            return "\n".join(res)
        errors.append("duckduckgo 无结果")
    except Exception as e:
        errors.append("duckduckgo: %s" % e)

    try:
        res = _parse_360(_http("https://www.so.com/s?q=" + urllib.parse.quote(q)), count)
        if res:
            return "\n".join(res)
        errors.append("360 无结果")
    except Exception as e:
        errors.append("360: %s" % e)

    return "（没搜到结果：%s）" % "；".join(errors)


def fetch_url(url):
    if not re.match(r"^https?://", url or ""):
        return "只支持 http/https 链接"
    text = strip_html(_http(url))
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
        return "未知工具：%s" % name
    except PermissionError as e:
        return "被拒绝：%s" % e
    except Exception as e:
        return "工具执行失败：%s" % e
