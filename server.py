# -*- coding: utf-8 -*-
"""
Aria 智能体 · 本地服务
零第三方依赖（PDF/Office 解析用可选库），双击 start.bat 或运行:
    python server.py
浏览器打开 http://127.0.0.1:8765
"""
import base64
import html
import io
import json
import os
import re
import socket
import subprocess
import sys
import urllib.parse
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import tools_layer

# 兼容 PyInstaller 打包：资源文件在临时解包目录
if getattr(sys, "frozen", False):
    ROOT = sys._MEIPASS
else:
    ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8765

# 工具层允许读写/执行的基础目录：打包后取 exe 所在目录，源码运行取项目目录
tools_layer.APP_ROOT = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else ROOT

# Windows 控制台默认 GBK，统一按 UTF-8 输出避免打印崩溃
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 让 pip --user 与工作区 libs 里的包都可被找到
sys.path.insert(0, os.path.join(ROOT, "server", "libs"))


def extract_text(name: str, data: bytes) -> str:
    """按扩展名抽取文件文本内容。"""
    lower = name.lower()
    if lower.endswith((".txt", ".md", ".csv", ".json", ".log", ".py", ".js", ".ts",
                       ".html", ".css", ".xml", ".yaml", ".yml", ".ini", ".bat", ".sh")):
        return data.decode("utf-8", errors="replace")
    if lower.endswith(".docx"):
        import docx
        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(x for x in parts if x.strip())
    if lower.endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        out = []
        for ws in wb.worksheets:
            out.append(f"### 工作表: {ws.title}")
            for row in ws.iter_rows(values_only=True):
                if any(v is not None for v in row):
                    out.append(" | ".join("" if v is None else str(v) for v in row))
        return "\n".join(out)
    if lower.endswith(".pptx"):
        from pptx import Presentation
        prs = Presentation(io.BytesIO(data))
        out = []
        for i, slide in enumerate(prs.slides, 1):
            out.append(f"### 第 {i} 页")
            for shape in slide.shapes:
                if shape.has_text_frame:
                    txt = shape.text_frame.text.strip()
                    if txt:
                        out.append(txt)
        return "\n".join(out)
    if lower.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    # 兜底：尝试按文本解码
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(f"暂不支持该文件格式: {name}")


def wallpaper_dir():
    """壁纸目录。打包成 exe 后写在 exe 同目录（持久化，重启不丢），首次自动从内置资源复制。"""
    if getattr(sys, "frozen", False):
        d = os.path.join(os.path.dirname(sys.executable), "wallpapers")
        if not os.path.isdir(d) or not os.listdir(d):
            src = os.path.join(ROOT, "wallpapers")
            if os.path.isdir(src):
                import shutil
                shutil.copytree(src, d, dirs_exist_ok=True)
    else:
        d = os.path.join(ROOT, "wallpapers")
    os.makedirs(d, exist_ok=True)
    return d


def wallpaper_ids():
    """返回现有壁纸编号（升序）。按真实编号返回，删图后前端不会留空位破图。"""
    import glob
    import re
    ids = []
    for f in glob.glob(os.path.join(wallpaper_dir(), "wp*.jpg")):
        m = re.match(r"wp(\d+)\.jpg$", os.path.basename(f))
        if m:
            ids.append(int(m.group(1)))
    return sorted(ids)


def wallpaper_count():
    return len(wallpaper_ids())


def wallpaper_card_ids():
    """照片漂浮用的卡片图编号（cardNN.jpg，带缺号时只返回真实存在的）。"""
    import glob
    import re
    ids = []
    for f in glob.glob(os.path.join(wallpaper_dir(), "card*.jpg")):
        m = re.match(r"card(\d+)\.jpg$", os.path.basename(f))
        if m:
            ids.append(int(m.group(1)))
    return sorted(ids)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # 静默日志

    # ---------- 工具 ----------
    def _json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_js_empty(self):
        """给可选脚本占位，避免前端控制台出现 404。"""
        body = b"// optional local config (not provided)\n"
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---------- 路由 ----------
    def do_GET(self):
        static = {
            "/": "index.html",
            "/index.html": "index.html",
            "/qrcode.js": "qrcode.js",
            "/config.local.js": "config.local.js",
            "/official_skills.js": "official_skills.js",
            "/manifest.json": "manifest.json",
            "/sw.js": "sw.js",
        }
        TYPES = {".js": "application/javascript; charset=utf-8",
                 ".json": "application/json; charset=utf-8",
                 ".webmanifest": "application/manifest+json; charset=utf-8",
                 ".png": "image/png", ".ico": "image/x-icon", ".jpg": "image/jpeg"}
        if self.path in static:
            path = os.path.join(ROOT, static[self.path])
            if not os.path.isfile(path):
                # config.local.js 是可选的本地私有配置，缺失时给空脚本，避免前端报 404
                if self.path == "/config.local.js":
                    self._send_js_empty()
                else:
                    self._send_json({"error": "not found"}, 404)
                return
            ctype = TYPES.get(os.path.splitext(path)[1].lower(), "text/html; charset=utf-8")
            with open(path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            if self.path == "/sw.js":  # Service Worker 必须不被强缓存，否则更新不生效
                self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/icons/"):
            fname = os.path.basename(self.path)  # 防目录穿越
            fpath = os.path.join(ROOT, "icons", fname)
            if os.path.isfile(fpath):
                body = open(fpath, "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", TYPES.get(os.path.splitext(fname)[1].lower(), "application/octet-stream"))
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(body)
            else:
                self._send_json({"error": "not found"}, 404)
        elif self.path.startswith("/wallpapers/"):
            fname = os.path.basename(self.path)  # 防目录穿越
            fpath = os.path.join(wallpaper_dir(), fname)
            if os.path.isfile(fpath):
                body = open(fpath, "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(body)
            else:
                self._send_json({"error": "not found"}, 404)
        elif self.path == "/api/health":
            try:
                import trafilatura
                has_traf = getattr(trafilatura, "__version__", "yes")
            except Exception:
                has_traf = False
            self._send_json({"ok": True, "trafilatura": has_traf,
                             "tools": ["web_search", "fetch_url", "read_file", "list_dir", "run_command"]})
        elif self.path == "/api/lan":
            self._send_json({"ok": True, "url": f"http://{lan_ip()}:{PORT}"})
        elif self.path == "/api/wallpapers":
            ids = wallpaper_ids()
            self._send_json({"ok": True, "count": len(ids), "ids": ids,
                             "cards": wallpaper_card_ids()})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        try:
            if self.path == "/api/chat":
                self.handle_chat()
            elif self.path == "/api/extract":
                self.handle_extract()
            elif self.path == "/api/models":
                self.handle_models()
            elif self.path == "/api/docx":
                self.handle_docx()
            elif self.path == "/api/skill":
                self.handle_skill()
            elif self.path == "/api/verify":
                self.handle_verify()
            elif self.path == "/api/wallpaper":
                self.handle_wallpaper_upload()
            elif self.path == "/api/image":
                self.handle_image()
            elif self.path == "/api/xlsx":
                self.handle_xlsx()
            else:
                self._send_json({"error": "not found"}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            try:
                self._send_json({"error": str(e)}, 500)
            except Exception:
                pass

    # ---------- Markdown 转 Word 下载 ----------
    def handle_docx(self):
        payload = self._json_body()
        md = payload.get("markdown", "")
        title = (payload.get("filename") or "小凡智能体文档").strip()[:50]

        body = None
        # 首选：Pandoc 引擎 + GFM 规范（业界标准，表格/代码块/嵌套列表/任务列表全支持）
        try:
            import pypandoc, tempfile
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tf:
                outpath = tf.name
            pypandoc.convert_text(md, "docx", format="gfm",
                                  outputfile=outpath, extra_args=["--standalone"])
            with open(outpath, "rb") as f:
                body = f.read()
            os.unlink(outpath)
        except Exception:
            import traceback
            traceback.print_exc()

        # 回退：python-docx 简易转换（无 Pandoc 环境时）
        if not body:
            body = self._docx_fallback(md)

        import urllib.parse
        fname_encoded = urllib.parse.quote(title + ".docx")
        self.send_response(200)
        self.send_header("Content-Type",
                         "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        self.send_header("Content-Disposition",
                         f"attachment; filename*=UTF-8''{fname_encoded}")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _docx_fallback(self, md):
        import re
        import docx
        from docx.shared import Pt
        d = docx.Document()
        style = d.styles["Normal"]
        style.font.name = "微软雅黑"
        style.font.size = Pt(11)
        in_code = False
        code_buf = []
        for raw in md.split("\n"):
            line = raw.rstrip()
            if line.startswith("```"):
                if in_code:
                    p = d.add_paragraph()
                    r = p.add_run("\n".join(code_buf))
                    r.font.name = "Consolas"; r.font.size = Pt(9)
                    code_buf = []
                in_code = not in_code
                continue
            if in_code:
                code_buf.append(raw)
                continue
            if not line.strip():
                continue
            m = re.match(r"^(#{1,4})\s+(.*)", line)
            if m:
                d.add_heading(m.group(2), level=min(len(m.group(1)), 3))
                continue
            m = re.match(r"^[-*]\s+(.*)", line)
            if m:
                d.add_paragraph(m.group(1), style="List Bullet")
                continue
            m = re.match(r"^\d+\.\s+(.*)", line)
            if m:
                d.add_paragraph(m.group(1), style="List Number")
                continue
            p = d.add_paragraph()
            for seg in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", line):
                if seg.startswith("**") and seg.endswith("**"):
                    r = p.add_run(seg[2:-2]); r.bold = True
                elif seg.startswith("`") and seg.endswith("`"):
                    r = p.add_run(seg[1:-1]); r.font.name = "Consolas"
                elif seg:
                    p.add_run(seg)
        import io
        buf = io.BytesIO()
        d.save(buf)
        return buf.getvalue()

    # ---------- Key 真实校验（发一次最小请求验证） ----------
    def handle_verify(self):
        payload = self._json_body()
        base = (payload.get("baseUrl") or "").rstrip("/")
        key = payload.get("apiKey") or ""
        model = payload.get("model") or ""
        if not base or not key:
            self._send_json({"ok": False, "error": "地址或 Key 为空"}); return
        req = urllib.request.Request(
            base + "/chat/completions",
            data=json.dumps({"model": model or "gpt-4o-mini",
                             "messages": [{"role": "user", "content": "hi"}],
                             "max_tokens": 1, "stream": False}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                resp.read()
            self._send_json({"ok": True})
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:200]
            self._send_json({"ok": False, "code": e.code, "error": detail})
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)[:200]})

    # ---------- 上传照片加入专属壁纸库 ----------
    def handle_wallpaper_upload(self):
        from PIL import Image, ImageFilter, ImageEnhance
        payload = self._json_body()
        try:
            data = base64.b64decode(payload.get("data", ""))
            im = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception as e:
            self._send_json({"error": "图片解析失败: " + str(e)}, 400); return
        # 自动裁剪手机截图状态栏（按尺寸特征判断）
        W, H = im.size
        if H >= 2200 and W <= 1200:
            im = im.crop((int(W*0.06), int(H*0.124), int(W*0.94), int(H*0.832)))
        scale = 1600 / im.height
        if scale < 1:
            im = im.resize((int(im.width*scale), 1600), Image.LANCZOS)
        ids = wallpaper_ids()
        n = (max(ids) if ids else 0) + 1
        base = f"wp{n:03d}"
        d = wallpaper_dir()
        im.save(os.path.join(d, base + ".jpg"), quality=82)
        ImageEnhance.Brightness(im).enhance(0.62).save(os.path.join(d, base + "-dark.jpg"), quality=82)
        blur = ImageEnhance.Brightness(im.filter(ImageFilter.GaussianBlur(18))).enhance(0.8)
        blur.save(os.path.join(d, base + "-blur.jpg"), quality=82)
        if n <= 8:  # 漂浮卡片前8张用最新照片
            scale2 = 360 / im.width
            im.resize((360, int(im.height*scale2)), Image.LANCZOS).save(os.path.join(d, f"card{n:02d}.jpg"), quality=80)
        self._send_json({"ok": True, "count": wallpaper_count(), "name": base})

    # ---------- 文生图（智谱 CogView，免费） ----------
    def handle_image(self):
        payload = self._json_body()
        base = (payload.get("baseUrl") or "").strip().rstrip("/")
        key = payload.get("apiKey") or ""
        prompt = (payload.get("prompt") or "").strip()
        model = payload.get("model") or "cogview-3-flash"
        if not base or not prompt:
            self._send_json({"error": "缺少 baseUrl 或画面描述"}, 400); return
        req = urllib.request.Request(
            base + "/images/generations",
            data=json.dumps({"model": model, "prompt": prompt}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            item = (d.get("data") or [{}])[0]
            url = item.get("url") or ""
            b64 = item.get("b64_json") or ""
            if not url and not b64:
                self._send_json({"error": "上游未返回图片"}, 502); return
            self._send_json({"ok": True, "url": url, "b64": b64, "model": model})
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
            except Exception:
                msg = ""
            self._send_json({"error": msg or ("上游返回 " + str(e.code)), "code": e.code}, 200)
        except Exception as e:
            self._send_json({"error": str(e)}, 200)

    # ---------- Markdown 表格 → Excel 下载 ----------
    def handle_xlsx(self):
        payload = self._json_body()
        md = payload.get("markdown", "")
        # 抽取 Markdown 表格：连续的 | 行，跳过分隔行
        tables, cur = [], []
        for line in md.splitlines():
            if line.strip().startswith("|"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if all(set(c) <= set("-: ") for c in cells):  # 分隔行
                    continue
                cur.append(cells)
            else:
                if len(cur) >= 1:
                    tables.append(cur)
                cur = []
        if cur:
            tables.append(cur)
        if not tables:
            self._send_json({"error": "内容里没有找到 Markdown 表格"}, 200); return
        title = (payload.get("filename") or "小凡智能体表格").strip()[:40]
        try:
            from openpyxl import Workbook
            wb = Workbook(); wb.remove(wb.active)
            for i, rows in enumerate(tables[:8], 1):
                ws = wb.create_sheet(f"表{i}")
                for r in rows:
                    ws.append(r)
            import io as _io
            buf = _io.BytesIO(); wb.save(buf)
            body = buf.getvalue()
            ctype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            fname = title + ".xlsx"
        except ImportError:
            # 无 openpyxl：回退 CSV（Excel 可直接打开）
            import csv as _csv
            out = io.StringIO()
            writer = _csv.writer(out)
            for rows in tables:
                writer.writerows(rows); writer.writerow([])
            body = "\ufeff" + out.getvalue()
            ctype = "text/csv; charset=utf-8"
            fname = title + ".csv"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{urllib.parse.quote(fname)}")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---------- 技能包导入（zip 内 SKILL.md，Claude Skills 规范） ----------
    def handle_skill(self):
        import re, zipfile
        payload = self._json_body()
        name = payload.get("name", "skill")
        data = base64.b64decode(payload.get("data", ""))
        text = None
        if name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                candidates = [n for n in z.namelist()
                              if n.lower().endswith("skill.md") or (n.lower().endswith(".md") and "/" not in n)]
                if not candidates:
                    candidates = [n for n in z.namelist() if n.lower().endswith(".md")]
                if not candidates:
                    self._send_json({"error": "压缩包里没找到 .md 技能文件（需要 SKILL.md）"}, 400); return
                text = z.read(candidates[0]).decode("utf-8", errors="replace")
        else:
            text = data.decode("utf-8", errors="replace")
        m = re.match(r"^---\s*\n([\s\S]*?)\n---\s*\n?([\s\S]*)$", text)
        if m:
            meta = {}
            for l in m[1].split("\n"):
                kv = re.match(r"^(\w+):\s*(.*)$", l)
                if kv: meta[kv.group(1).strip()] = kv.group(2).strip()
            self._send_json({"ok": True, "name": meta.get("name", "导入技能"),
                             "desc": meta.get("description", "导入的技能"), "prompt": m[2].strip()})
        else:
            first = next((l.strip() for l in text.split("\n") if l.strip()), "导入技能")
            self._send_json({"ok": True, "name": re.sub(r"^#+\s*", "", first)[:20],
                             "desc": "上传的技能文件", "prompt": text.strip()})

    # ---------- 文件解析 ----------
    def handle_extract(self):
        payload = self._json_body()
        name = payload.get("name", "file")
        data = base64.b64decode(payload.get("data", ""))
        text = extract_text(name, data)
        # 限制长度，避免超出上下文
        if len(text) > 200_000:
            text = text[:200_000] + "\n\n[...内容过长，已截断...]"
        self._send_json({"ok": True, "text": text, "chars": len(text)})

    # ---------- 拉取模型列表 ----------
    def handle_models(self):
        payload = self._json_body()
        base = (payload.get("baseUrl") or "").rstrip("/")
        key = payload.get("apiKey") or ""
        req = urllib.request.Request(
            base + "/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
        self._send_json({"ok": True, "models": ids})

    # ---------- 对话（流式转发） ----------
    def handle_chat(self):
        payload = self._json_body()
        base = (payload.get("baseUrl") or "").rstrip("/")
        key = payload.get("apiKey") or ""
        model = payload.get("model") or ""
        temperature = payload.get("temperature")
        messages = payload.get("messages") or []

        tools_on = bool(payload.get("tools"))
        perm = payload.get("perm") or {}

        def build_body(msgs, stream_flag, with_tools):
            body = {
                "model": model,
                "messages": msgs,
                "stream": stream_flag,
            }
            if temperature is not None:
                body["temperature"] = float(temperature)
            if payload.get("maxTokens"):
                body["max_tokens"] = int(payload["maxTokens"])
            # 推理深度：智谱用 thinking，其他 OpenAI 兼容用 reasoning_effort
            reasoning = payload.get("reasoning") or "auto"
            if "bigmodel" in base:
                if reasoning in ("off", "low", "medium", "high"):
                    body["thinking"] = {"type": "disabled" if reasoning == "off" else "enabled"}
            elif reasoning not in ("auto", "off"):
                body["reasoning_effort"] = reasoning
            if with_tools:
                body["tools"] = tools_layer.TOOL_DEFS
                body["tool_choice"] = "auto"
            return body

        # ---------- 带工具：服务端自己跑 function-calling 循环 ----------
        if tools_on:
            self._chat_with_tools(base, key, messages, build_body, perm)
            return

        upstream_body = build_body(messages, bool(payload.get("stream", True)), False)

        req = urllib.request.Request(
            base + "/chat/completions",
            data=json.dumps(upstream_body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
                "Accept": "text/event-stream",
            },
            method="POST",
        )

        try:
            upstream = urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:2000]
            self._send_json({"error": f"上游接口返回 {e.code}: {detail}"}, 502)
            return

        # 以 SSE 透传给浏览器
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        try:
            for line in upstream:
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="replace")
                line = line.strip()
                if not line:
                    continue
                chunk = (line + "\n\n").encode("utf-8")
                self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            import traceback
            traceback.print_exc()
        finally:
            try:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except Exception:
                pass
            upstream.close()

    # ---------- 工具调用循环 ----------
    def _sse(self, obj):
        """发一条 SSE 事件（手动 chunked）。"""
        chunk = ("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8")
        self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
        self.wfile.flush()

    def _chat_with_tools(self, base, key, messages, build_body, perm):
        """模型要工具 → 本地执行 → 结果回灌 → 最多 4 轮，最后把答案流式吐给前端。"""
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def call_upstream(msgs):
            req = urllib.request.Request(
                base + "/chat/completions",
                data=json.dumps(build_body(msgs, False, True)).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {key}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read().decode("utf-8"))

        try:
            msgs = list(messages)
            final_text = ""
            for _round in range(tools_layer.MAX_ROUNDS):
                try:
                    data = call_upstream(msgs)
                except urllib.error.HTTPError as e:
                    detail = e.read().decode("utf-8", errors="replace")[:600]
                    hint = ""
                    if e.code in (400, 404, 422):
                        hint = "\n\n（当前模型/平台可能不支持工具调用，换 glm-4-flash、deepseek-chat 等支持 function calling 的模型试试）"
                    final_text = f"上游接口返回 {e.code}: {detail}{hint}"
                    break
                msg = ((data.get("choices") or [{}])[0]).get("message") or {}
                tool_calls = msg.get("tool_calls") or []
                if not tool_calls:
                    final_text = msg.get("content") or ""
                    reasoning = msg.get("reasoning_content") or ""
                    if not final_text.strip() and reasoning:
                        final_text = reasoning
                    break
                msgs.append({"role": "assistant",
                             "content": msg.get("content") or "",
                             "tool_calls": tool_calls})
                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    self._sse({"tool": {"id": tc.get("id"), "name": fn.get("name"),
                                        "args": fn.get("arguments") or "", "status": "running"}})
                    result = tools_layer.run_tool(tc, perm)
                    msgs.append({"role": "tool", "tool_call_id": tc.get("id"), "content": result})
                    self._sse({"tool": {"id": tc.get("id"), "name": fn.get("name"),
                                        "status": "done", "preview": str(result)[:400]}})
            else:
                final_text = "（工具调用轮数达到上限，先给你目前掌握的信息）"

            # 把最终答案切成小段，前端按流式渲染
            for i in range(0, len(final_text), 24):
                self._sse({"choices": [{"delta": {"content": final_text[i:i + 24]}}]})
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            import traceback
            traceback.print_exc()
            try:
                self._sse({"choices": [{"delta": {"content": "服务端处理出错，请查看终端日志。"}}]})
            except Exception:
                pass
        finally:
            try:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except Exception:
                pass


def lan_ip():
    """获取局域网 IP，取不到则回退本机地址。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def open_app_window(url):
    """优先用 Chrome/Edge 的「应用窗口」打开：无地址栏无标签页，像一个桌面程序。"""
    import subprocess
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for exe in candidates:
        if os.path.isfile(exe):
            try:
                subprocess.Popen([exe, f"--app={url}", "--start-maximized",
                                  "--window-size=1440,960"],
                                 close_fds=True)
                return True
            except Exception:
                continue
    import webbrowser
    webbrowser.open(url)
    return False


def main():
    try:
        server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    except OSError:
        # 端口被占：通常已经有一个实例在跑（比如双击了两次），直接开窗口即可
        open_app_window(f"http://127.0.0.1:{PORT}")
        print(f"检测到已有实例在运行，已打开 http://127.0.0.1:{PORT}")
        return
    ip = lan_ip()
    print("小凡智能体服务已启动")
    print(f"  本机访问:  http://127.0.0.1:{PORT}")
    print(f"  手机访问:  http://{ip}:{PORT}   （手机需与电脑同一 WiFi，页面里有扫码入口）")
    print("  按 Ctrl+C 停止")
    # exe / --open 模式：自动打开应用窗口
    import threading
    if getattr(sys, "frozen", False) or "--open" in sys.argv:
        threading.Timer(1.2, lambda: open_app_window(f"http://127.0.0.1:{PORT}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
