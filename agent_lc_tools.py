"""LangChain 官方工具层适配：把 tools_layer.TOOL_DEFS 转成 StructuredTool 列表。

设计原则（不改行为，只换包装）：
1. 不碰 tools_layer.py 里 20 个工具的实现体，也不重写它们的 JSON Schema；
2. StructuredTool 的 func 只是一个转发器，最终仍走 run_tool(call, perm) 这一个分发点，
   所以权限（perm）、路径白名单、checkpoint 快照、trace 全部保持原样；
3. args_schema 直接复用 TOOL_DEFS 里的 parameters（langchain-core 的 ArgsSchema 支持
   dict[str, Any]，实测 langchain-core 1.8.4 可用），因此模型看到的 schema 与现在
   bind_tools(TOOL_DEFS) 完全一致。

MCP 工具不在这里构建：它们由 langchain-mcp-adapters 以 StructuredTool 形式提供
（见 agent_graph._load_mcp_lc_tools），合并时不要重复。
"""
from __future__ import annotations

import json
from typing import Any, Callable, Optional

import tools_layer

# 空 schema：极少数工具没写 parameters 时的兜底
_EMPTY_SCHEMA = {"type": "object", "properties": {}}


def _make_runner(name: str, perm: Optional[dict]) -> Callable[..., str]:
    """生成一个把关键字参数原样回灌给 run_tool 的转发函数。"""

    def _run(**kwargs: Any) -> str:
        call = {
            "function": {
                "name": name,
                "arguments": json.dumps(kwargs, ensure_ascii=False),
            }
        }
        return tools_layer.run_tool(call, perm)

    _run.__name__ = name
    _run.__doc__ = "转发到 tools_layer.run_tool('%s')" % name
    return _run


def build_lc_tools(perm: Optional[dict] = None) -> list:
    """返回与 TOOL_DEFS 一一对应的 StructuredTool 列表（不含 MCP 工具）。"""
    from langchain_core.tools import StructuredTool

    out = []
    for d in tools_layer.TOOL_DEFS:
        fn = d.get("function") or {}
        name = fn.get("name")
        if not name:
            continue
        out.append(
            StructuredTool.from_function(
                func=_make_runner(name, perm),
                name=name,
                description=fn.get("description") or name,
                args_schema=fn.get("parameters") or dict(_EMPTY_SCHEMA),
            )
        )
    return out


def build_all_tools(perm: Optional[dict] = None, mcp_tools: Optional[list] = None) -> list:
    """内置工具 + MCP 适配器工具合并（MCP 由调用方先加载好传进来）。"""
    tools = build_lc_tools(perm)
    if mcp_tools:
        tools.extend(mcp_tools)
    return tools
