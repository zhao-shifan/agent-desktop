"""验证工具注册表：合并、来源标记、返回值归一化、文件标识提取（全离线）。

跑法：python tests/_test_tool_registry.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.documents import Document
from langchain_core.messages import ToolMessage

import agent_tool_registry as reg
import tools_layer

ok = 0
fail = 0


def check(cond, label, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print("  PASS  " + label)
    else:
        fail += 1
        print("  FAIL  " + label + ("  -> " + str(detail)[:200] if detail else ""))


def main():
    print("[1] 合并工具")
    tools, origins = reg.build_all_tools(perm={}, mcp_tools=[])
    names = [t.name for t in tools]
    builtin = [n for n, v in origins.items() if v == "builtin"]
    lc = [n for n, v in origins.items() if v == "langchain"]
    check(len(builtin) == len(tools_layer.TOOL_DEFS),
          "自研工具数量 == TOOL_DEFS（%d）" % len(tools_layer.TOOL_DEFS), len(builtin))
    check(len(lc) >= 3, "至少 3 个 LangChain 原生工具入表", lc)
    check(len(names) == len(set(names)), "工具名无重复")
    check(all(hasattr(t, "args_schema") for t in tools), "全部是 StructuredTool/BaseTool")

    print("[2] 名称冲突时自研优先")
    from langchain_core.tools import StructuredTool
    fake_dup = StructuredTool.from_function(
        func=lambda: "x", name="get_time", description="dup")
    tools2, origins2 = reg.build_all_tools(perm={}, mcp_tools=[fake_dup])
    check(origins2["get_time"] == "builtin", "同名工具保持 builtin 来源", origins2.get("get_time"))
    check(len([t for t in tools2 if t.name == "get_time"]) == 1, "同名工具只保留一个")

    print("[3] 归一化：字符串 / dict / list / Document / None")
    r = reg.normalize_result("t", "hello world")
    check(r["text"] == "hello world" and r["preview"].startswith("hello"), "str 直通")
    r = reg.normalize_result("t", {"chars": 12, "words": 3})
    check('"chars": 12' in r["text"], "dict 转 JSON 文本", r["text"])
    check(r["preview"], "dict 有 preview")
    r = reg.normalize_result("t", ["a", "b"])
    check('["a", "b"]' == r["text"], "list 转 JSON 文本", r["text"])
    r = reg.normalize_result("t", Document(page_content="文档正文"))
    check(r["text"] == "文档正文", "Document 取 page_content", r["text"])
    r = reg.normalize_result("get_time", None)
    check(r["preview"].startswith("get_time 执行完成"), "None 生成默认 preview", r["preview"])
    r = reg.normalize_result("t", ToolMessage(content="消息体", tool_call_id="1"))
    check(r["text"] == "消息体", "ToolMessage 取 content", r["text"])

    print("[4] 元组 (content, artifact)")
    r = reg.normalize_result("t", ("正文", {"path": "agent_data/exports/a.docx"}))
    check(r["text"] == "正文", "元组取 content")
    check(any(f["ext"] == "docx" for f in r["files"]), "artifact 里的文件被提取", r["files"])

    print("[5] 文件标识提取")
    r = reg.normalize_result("write_file", "已写入 D:\\桌面版agent\\agent_data\\exports\\报告.docx（12 KB）")
    check(len(r["files"]) == 1, "Windows 反斜杠路径识别", r["files"])
    check(r["files"][0]["path"] == "D:/桌面版agent/agent_data/exports/报告.docx",
          "路径统一成正斜杠", r["files"][0]["path"])
    check(r["files"][0]["ext"] == "docx", "ext 正确")
    r = reg.normalize_result("t", "见 agent_data/images/a.png 和 agent_data/images/a.png 两份")
    check(len(r["files"]) == 1, "重复路径去重", r["files"])
    r = reg.normalize_result("t", "C:/tmp/setup.exe 不是可预览类型")
    check(len(r["files"]) == 0, "不可预览后缀被过滤", r["files"])

    print("[6] 归一化遇到异常值也要安全")
    class Weird:
        def __str__(self):
            raise RuntimeError("boom")
    try:
        r = reg.normalize_result("t", Weird())
        check(bool(r["preview"]), "异常对象仍产出 preview", r["preview"])
    except Exception as e:
        check(False, "normalize_result 不应抛异常", e)

    print()
    print("结果: %d passed, %d failed" % (ok, fail))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
