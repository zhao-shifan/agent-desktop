# -*- coding: utf-8 -*-
"""通过 GitHub Contents API 推送变更文件（绕过 git https 通道）"""
import base64, json, os, subprocess, sys, tempfile

GH = r"C:\Program Files\GitHub CLI\gh.exe"
REPO = "zhao-shifan/agent-desktop"
FILES = ["index.html", "server.py", "official_skills.js", "README.md"]
MSG = "重大修复：流式输出bytes解码bug（修复无法回复）；推理深度控制；统一桌面/手机版；主题选择器；消息复制/分支；模型快捷切换；默认鎏金配色"

def gh(args):
    return subprocess.run([GH] + args, capture_output=True)

def push_file(path):
    local = open(os.path.join(r"D:\桌面版agent", path), "rb").read()
    b64 = base64.b64encode(local).decode()
    payload = {"message": MSG, "content": b64}
    r = gh(["api", f"repos/{REPO}/contents/{path}?ref=main"])
    if r.returncode == 0:
        payload["sha"] = json.loads(r.stdout.decode("utf-8", "replace"))["sha"]
    tf = os.path.join(tempfile.gettempdir(), "gh_payload.json")
    with open(tf, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    r = gh(["api", "--method", "PUT", f"repos/{REPO}/contents/{path}", "--input", tf])
    return r.returncode, r.stderr.decode("utf-8", "replace")

fail = False
for p in FILES:
    code, err = push_file(p)
    print(p, "=>", "OK" if code == 0 else "FAIL " + err.strip()[:200])
    fail = fail or code != 0
sys.exit(1 if fail else 0)
