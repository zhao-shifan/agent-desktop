# -*- coding: utf-8 -*-
"""端到端联调：假上游模型（返回 tool_call）+ 真 /api/chat（工具循环）。

流程：请求 /api/chat(tools=true) → 服务端问上游 → 上游要求调 web_search
→ 服务端执行 → 结果回灌 → 上游给最终答案 → 前端拿到 tool 事件 + 文本流。
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import urllib.request

CALLS = []          # 记录上游收到的请求，便于断言回灌内容


class Mock(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n).decode())
        CALLS.append(body)
        has_tool_result = any(m.get("role") == "tool" for m in body.get("messages", []))
        if not has_tool_result:
            msg = {"role": "assistant", "content": "",
                   "tool_calls": [{"id": "call_1", "type": "function",
                                   "function": {"name": "read_file",
                                                "arguments": json.dumps({"path": "D:\\桌面版agent\\README.md", "lines": 3})}}]}
        else:
            tool_msg = [m for m in body["messages"] if m.get("role") == "tool"][-1]["content"]
            msg = {"role": "assistant", "content": "看完了，README 开头是：" + tool_msg.split("\n")[1][:40]}
        out = json.dumps({"choices": [{"message": msg}], "usage": {}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 9911), Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    payload = {
        "baseUrl": "http://127.0.0.1:9911/v1", "apiKey": "test", "model": "mock",
        "messages": [{"role": "user", "content": "帮我读一下 README 开头"}],
        "tools": True,
        "perm": {"workDir": "D:\\桌面版agent"},
    }
    req = urllib.request.Request("http://127.0.0.1:8765/api/chat",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8", "replace")

    events = [json.loads(line[6:]) for line in raw.splitlines()
              if line.startswith("data: ") and line[6:].strip() != "[DONE]"]
    tools = [e["tool"] for e in events if "tool" in e]
    text = "".join(e["choices"][0]["delta"].get("content", "") for e in events if "choices" in e)

    fails = []
    if not any(t["status"] == "running" for t in tools):
        fails.append("没有 tool running 事件")
    if not any(t["status"] == "done" for t in tools):
        fails.append("没有 tool done 事件")
    if "read_file" not in [t.get("name") for t in tools]:
        fails.append("工具名不对")
    if len(CALLS) < 2:
        fails.append("没有发生第二轮回灌（只有 %d 次上游调用）" % len(CALLS))
    second = CALLS[-1]["messages"] if CALLS else []
    if not any(m.get("role") == "tool" and "README" in str(m.get("content")) for m in second):
        fails.append("第二轮没有带上工具结果")
    if "Aria" not in text and "小凡" not in text:
        fails.append("最终答案不对：" + text[:80])

    print("上游调用次数:", len(CALLS))
    for t in tools:
        print("  tool:", t.get("name"), t.get("status"), str(t.get("args"))[:60])
    print("最终文本:", text[:120])
    print("\n" + ("端到端通过 ✅" if not fails else "失败：" + "；".join(fails)))
    srv.shutdown()
    raise SystemExit(0 if not fails else 1)


if __name__ == "__main__":
    main()
