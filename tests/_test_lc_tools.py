"""验证 agent_lc_tools 与现有 TOOL_DEFS 完全等价（不联网、不调模型）。

跑法：python tests/_test_lc_tools.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools_layer
from agent_lc_tools import build_lc_tools, build_all_tools

from langchain_core.utils.function_calling import convert_to_openai_tool

ok = 0
fail = 0


def check(cond, label, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print("  PASS  " + label)
    else:
        fail += 1
        print("  FAIL  " + label + ("  -> " + detail if detail else ""))


def main():
    defs = {d["function"]["name"]: d for d in tools_layer.TOOL_DEFS}
    tools = build_lc_tools(perm={"workDir": "", "allowCommand": False})
    names = [t.name for t in tools]

    print("[1] 数量与名称")
    check(len(tools) == len(tools_layer.TOOL_DEFS),
          "工具数量一致: %d" % len(tools))
    check(names == list(defs.keys()), "顺序与 TOOL_DEFS 一致")

    print("[2] 每个工具导出的 OpenAI schema 与原始定义逐字段相等")
    for t in tools:
        got = convert_to_openai_tool(t)
        want = defs[t.name]
        check(got == want, t.name,
              "got=%s" % json.dumps(got, ensure_ascii=False)[:180])

    print("[3] bind_tools 可用（不联网，只构造 payload）")
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(base_url="http://127.0.0.1:1/v1", api_key="EMPTY",
                     model="glm-4-flash")
    bound = llm.bind_tools(tools)
    payload = bound.kwargs.get("tools") if hasattr(bound, "kwargs") else None
    check(bool(payload), "bind_tools(tools) 产出 tools payload")
    if payload:
        check(len(payload) == len(tools), "payload 条数与工具数一致")
        check(payload[0]["function"]["name"] == tools[0].name, "payload 首项名称一致")

    print("[4] 合并 MCP 工具")
    fake_mcp = list(tools[:1])
    merged = build_all_tools(perm={}, mcp_tools=fake_mcp)
    check(len(merged) == len(tools) + 1, "build_all_tools 追加 MCP 工具")

    print("[5] 转发器真的会调 run_tool")
    from agent_lc_tools import _make_runner
    runner = _make_runner("get_time", {})
    res = runner()
    check(isinstance(res, str) and len(res) > 0, "get_time 返回非空字符串",
          str(res)[:80])

    print()
    print("结果: %d passed, %d failed" % (ok, fail))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
