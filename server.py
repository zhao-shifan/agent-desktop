# -*- coding: utf-8 -*-
"""
Aria 智能体 · 本地服务
零第三方依赖（PDF/Office 解析用可选库），双击 start.bat 或运行:
    python server.py
浏览器打开 http://127.0.0.1:8765
"""
import base64
import io
import json
import os
import socket
import sys
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 兼容 PyInstaller 打包：资源文件在临时解包目录
if getattr(sys, "frozen", False):
    ROOT = sys._MEIPASS
else:
    ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8765

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

    # ---------- 路由 ----------
    def do_GET(self):
        static = {
            "/": "index.html",
            "/index.html": "index.html",
            "/qrcode.js": "qrcode.js",
        }
        if self.path in static:
            path = os.path.join(ROOT, static[self.path])
            ctype = "application/javascript" if self.path.endswith(".js") else "text/html; charset=utf-8"
            with open(path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/health":
            self._send_json({"ok": True})
        elif self.path == "/api/lan":
            self._send_json({"ok": True, "url": f"http://{lan_ip()}:{PORT}"})
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

        upstream_body = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if temperature is not None:
            upstream_body["temperature"] = float(temperature)

        # 推理深度：智谱用 thinking，其他 OpenAI 兼容用 reasoning_effort
        reasoning = payload.get("reasoning") or "auto"
        if "bigmodel" in base:
            if reasoning in ("off", "low", "medium", "high"):
                upstream_body["thinking"] = {"type": "disabled" if reasoning == "off" else "enabled"}
        elif reasoning not in ("auto", "off"):
            upstream_body["reasoning_effort"] = reasoning

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


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    ip = lan_ip()
    print("小凡智能体服务已启动")
    print(f"  本机访问:  http://127.0.0.1:{PORT}")
    print(f"  手机访问:  http://{ip}:{PORT}   （手机需与电脑同一 WiFi，页面里有扫码入口）")
    print("  按 Ctrl+C 停止")
    # exe / --open 模式：自动打开浏览器
    import webbrowser, threading
    if getattr(sys, "frozen", False) or "--open" in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
