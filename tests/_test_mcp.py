# -*- coding: utf-8 -*-
"""MCP 集成测试：起假 MCP 服务器 → mcp_init → 验证工具挂载与调用。"""
import importlib.util, json, os, sys

ROOT = r"D:\桌面版agent"
spec = importlib.util.spec_from_file_location("tl", os.path.join(ROOT, "tools_layer.py"))
tl = importlib.util.module_from_spec(spec); spec.loader.exec_module(tl)

# 写临时配置指向假服务器
cfgp = tl._mcp_config_path()
bak = open(cfgp, "rb").read() if os.path.exists(cfgp) else None
json.dump({"servers": [{"name": "test", "command": sys.executable,
                        "args": [os.path.join(ROOT, "dev", "_fake_mcp_server.py")]}]},
          open(cfgp, "w", encoding="utf-8"))

try:
    tl.mcp_init()
    defs = tl.mcp_tool_defs()
    print("挂载数:", len(defs), "| 名字:", [d["function"]["name"] for d in defs])
    assert any(d["function"]["name"] == "mcp_test_echo" for d in defs), "echo 未挂载"
    r1 = tl.run_tool({"function": {"name": "mcp_test_echo", "arguments": '{"text": "你好小凡"}'}})
    print("echo:", r1)
    r2 = tl.run_tool({"function": {"name": "mcp_test_add", "arguments": '{"a": 3, "b": 4}'}})
    print("add:", r2)
    assert "你好小凡" in r1 and "7" in r2
    print("MCP 集成测试通过 ✅")
finally:
    if bak: open(cfgp, "wb").write(bak)
    else: json.dump({"servers": []}, open(cfgp, "w", encoding="utf-8"))
    for p in tl._MCP_PROCS.values():
        try: p.kill()
        except Exception: pass
