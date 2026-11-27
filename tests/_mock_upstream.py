"""本地 mock 上游：OpenAI 兼容 /v1/models + /v1/chat/completions（SSE 流式）。

用途：不花钱、不联网地跑双引擎协议对照（SSE 分帧 / 工具调度 / 审批 / 错误回填）。

行为（确定性，方便逐字节对比两边）：
  - 用户说"不要调用任何工具" → 直接给一段固定正文
  - 消息里还没有 role=tool → 按关键词发 tool_calls
        含"计算"  → calculator + get_time（多工具，验证并发/顺序回灌）
        含"几点"  → get_time（单工具）
  - 已有 role=tool → 给固定最终回答
  - 消息里出现 9001 时返回 HTTP 500（验证错误回填/异常链路）

跑法：python tests/_mock_upstream.py --port 8803
"""
import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FINAL_TEXT = "已拿到工具结果：当前时间 12:00:00，计算结果 6996652。"
CHAT_TEXT = "我是小凡测试助手，这是一段不调用工具的固定回复。"
MODEL = "mock-glm"


def sse(obj):
    return ("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8")


def chunk_pack(delta, finish=None):
    return {"id": "chatcmpl-mock", "object": "chat.completion.chunk",
            "created": int(time.time()), "model": MODEL,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [
                {"id": MODEL, "object": "model", "owned_by": "mock"}]})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._json(404, {"error": {"message": "not found"}})
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            self._json(400, {"error": {"message": "bad json"}})
            return

        messages = payload.get("messages") or []
        tools = payload.get("tools") or []
        tool_names = []
        for t in tools:
            fn = (t or {}).get("function") or {}
            if fn.get("name"):
                tool_names.append(fn["name"])
        user_text = ""
        for m in messages:
            if m.get("role") == "user":
                c = m.get("content")
                user_text = c if isinstance(c, str) else str(c)
        has_tool_msg = any(m.get("role") == "tool" for m in messages)

        if "9001" in user_text:
            self._json(500, {"error": {"message": "mock upstream 500（错误回填测试）"}})
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        def emit(obj):
            self.wfile.write(sse(obj))
            self.wfile.flush()

        # 1) 不带工具 / 明确要求别调工具 / 已有工具结果 → 正文
        text = None
        if not tools or "不要调用任何工具" in user_text:
            text = CHAT_TEXT
        elif has_tool_msg:
            text = FINAL_TEXT

        if text is not None:
            emit(chunk_pack({"role": "assistant", "content": ""}, None))
            # 用户要求"思考"时先发 reasoning_content，验证思考通道
            if "思考" in user_text:
                think = "我先想想这个问题的关键点，然后再给出结论。"
                for i in range(0, len(think), 6):
                    emit(chunk_pack({"reasoning_content": think[i:i + 6]}, None))
            for i in range(0, len(text), 8):
                emit(chunk_pack({"content": text[i:i + 8]}, None))
            emit(chunk_pack({}, "stop"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            self.close_connection = True
            return

        # 2) 发 tool_calls
        calls = []
        if "计算" in user_text and "calculator" in tool_names:
            calls.append({"name": "calculator",
                          "args": json.dumps({"expression": "1234*5678"})})
        if ("几点" in user_text or "时间" in user_text) and "get_time" in tool_names:
            calls.append({"name": "get_time", "args": "{}"})
        # 新增 LangChain 生态工具（仅在 official 引擎的工具表里存在）
        if "统计" in user_text and "lc_word_count" in tool_names:
            calls.append({"name": "lc_word_count",
                          "args": json.dumps({"text": user_text}, ensure_ascii=False)})
        if "解析" in user_text and "lc_json_extract" in tool_names:
            calls.append({"name": "lc_json_extract",
                          "args": json.dumps({"text": '{"a": 1, "b": [2, 3]}'},
                                             ensure_ascii=False)})
        if "文档" in user_text and "lc_summary_doc" in tool_names:
            calls.append({"name": "lc_summary_doc",
                          "args": json.dumps({"title": "mock文档", "points": user_text},
                                             ensure_ascii=False)})
        if not calls and tool_names:
            calls.append({"name": tool_names[0], "args": "{}"})

        emit(chunk_pack({"role": "assistant", "content": ""}, None))
        for idx, c in enumerate(calls):
            emit(chunk_pack({"tool_calls": [{
                "index": idx, "id": "call_%d" % (idx + 1), "type": "function",
                "function": {"name": c["name"], "arguments": ""}}]}, None))
            emit(chunk_pack({"tool_calls": [{
                "index": idx,
                "function": {"arguments": c["args"]}}]}, None))
        emit(chunk_pack({}, "tool_calls"))
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8803)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("[mock] listening on http://127.0.0.1:%d/v1" % args.port, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
