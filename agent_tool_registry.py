"""工具注册表：自研工具 + LangChain 生态工具，统一成 StructuredTool 后合并。

三层职责
1. 构建：自研 18 个（转发到 tools_layer.run_tool）+ LangChain 原生 @tool / StructuredTool
   （可选的社区包存在时才加载），名称去重时自研优先。
2. 来源标记：TOOL_ORIGIN 记录每个工具来自 builtin / langchain / mcp，便于排障与统计；
   模型侧看到的 schema 完全一致（都是 StructuredTool），无感知来源。
3. 结果归一化：LangChain 原生工具返回值五花八门（str / dict / list / Document /
   ToolMessage / (content, artifact) 元组），这里统一转成项目约定的
   {"text", "preview", "files"}，供 wrap_tool_call 下发 tool_done 事件，
   保证前端预览 / 导出链路不会因为拿不到 preview 或文件标识而崩。

注意：这里只做"标准化"，不做审批/事件下发——那是 agent_engine_official 的
wrap_tool_call 统一胶水层的职责，对所有工具（不论来源）一视同仁。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

import tools_layer
from agent_lc_tools import build_lc_tools

# 工具来源：builtin=自研（转发 run_tool）；langchain=LangChain 原生/社区；mcp=MCP 适配器
TOOL_ORIGIN: dict[str, str] = {}

# 前端可预览/导出的后缀（与 workbench/src/lib/preview.ts 的映射保持一致）
PREVIEWABLE_EXT = ("docx", "doc", "pptx", "ppt", "pdf", "png", "jpg", "jpeg", "webp",
                   "gif", "bmp", "svg", "avif", "xlsx", "xls", "csv", "tsv",
                   "diff", "patch", "txt", "md")

_FILE_RE = re.compile(
    r"((?:[A-Za-z]:)?[\\/]?[\w\-. \\u4e00-\u9fa5]+(?:[\\/][\w\-. \\u4e00-\u9fa5]+)*"
    r"\.(?:%s))\b" % "|".join(PREVIEWABLE_EXT),
    re.IGNORECASE,
)

MAX_PREVIEW = 400


# ---------------------------------------------------------------- 结果归一化
def _stringify(value: Any) -> str:
    """把任意返回值转成给模型看的字符串。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    # LangChain Document / Blob 之类
    content = getattr(value, "page_content", None)
    if isinstance(content, str):
        return content
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            return str(value)
    return str(value)


def extract_files(text: str, extra: Any = None) -> list[dict]:
    """从工具输出里提取可预览的文件标识（去重、统一成正斜杠）。"""
    seen = set()
    out = []

    def _add(raw: str) -> None:
        raw = str(raw or "").strip().strip('"\'')
        if not raw:
            return
        # 正则会把"已写入 D:/a/b.docx"这种前缀一起吃掉：从右往左找到真正带分隔符的片段
        parts = raw.split()
        if len(parts) > 1:
            for i in range(len(parts) - 1, -1, -1):
                if "/" in parts[i] or "\\" in parts[i] or ":" in parts[i]:
                    raw = " ".join(parts[i:])
                    break
            else:
                raw = parts[-1]
        norm = raw.replace("\\", "/").lstrip("（(【[").strip()
        # JSON 文本里的路径是转义过的（D:\\a\\b → D://a//b），合并重复斜杠
        norm = re.sub(r"/{2,}", "/", norm)
        ext = norm.rsplit(".", 1)[-1].lower() if "." in norm else ""
        if ext not in PREVIEWABLE_EXT:
            return
        key = norm.lower()
        if key in seen:
            return
        seen.add(key)
        out.append({"path": norm, "name": os.path.basename(norm), "ext": ext})

    if text:
        for m in _FILE_RE.finditer(text):
            _add(m.group(1))

    # artifact / dict 里显式给出的文件字段（LangChain 工具有 response_format 时常见）
    def _walk(node, depth=0):
        if depth > 4 or node is None:
            return
        if isinstance(node, dict):
            for k in ("path", "file", "file_path", "filename", "filepath", "url", "source"):
                if isinstance(node.get(k), str):
                    _add(node[k])
            for v in node.values():
                if isinstance(v, (dict, list)):
                    _walk(v, depth + 1)
        elif isinstance(node, (list, tuple)):
            for v in node:
                _walk(v, depth + 1)

    if extra is not None:
        _walk(extra)
    return out


def normalize_result(name: str, result: Any) -> dict:
    """LangChain 原生返回值 → 项目约定结构 {"text", "preview", "files"}。

    任何异常都退回"安全默认"，绝不让预览/导出链路因为缺字段而崩。
    """
    text = ""
    extra = None
    try:
        if isinstance(result, tuple) and len(result) == 2:
            # (content, artifact)：LangChain 的 response_format="content_and_artifact"
            text, extra = _stringify(result[0]), result[1]
        elif hasattr(result, "content") and not isinstance(result, str):
            # ToolMessage / BaseMessage
            text = _stringify(getattr(result, "content", ""))
            extra = getattr(result, "artifact", None)
        else:
            text = _stringify(result)
    except Exception as e:                       # 归一化失败也要给个能看的东西
        text = "[结果解析失败] %s: %s" % (type(e).__name__, e)

    text = str(text or "")
    files = extract_files(text, extra)
    # preview 保留原始换行（前端工具卡片按多行展示，与旧引擎 str(result)[:400] 一致）
    preview = text[:MAX_PREVIEW].rstrip()
    if not preview:
        # 缺省 preview：按文件/类型给一句人能看懂的，前端工具卡片不至于空白
        if files:
            preview = "生成文件：%s" % ", ".join(f["name"] for f in files[:3])
        elif result is None:
            preview = "%s 执行完成（无输出）" % name
        else:
            preview = "%s 执行完成（%s）" % (name, type(result).__name__)
    return {"text": text, "preview": preview, "files": files}


# ---------------------------------------------------------------- LangChain 工具
def _lc_json_extract():
    """用 LangChain 的 JsonOutputParser 解析文本，返回 dict（另一种返回形态）。

    注：这里不用 langchain_text_splitters —— 该包在本环境会连带导入
    sentence_transformers/transformers，实测让工具构建从 0.1s 涨到 40s+，
    不适合放进每轮对话的工具注册表。
    """
    from langchain_core.tools import tool
    from langchain_core.output_parsers import JsonOutputParser

    parser = JsonOutputParser()

    @tool("lc_json_extract", description="用 LangChain JsonOutputParser 从一段文本里解析出 JSON 对象/数组，返回结构化结果。")
    def lc_json_extract(text: str) -> dict:
        try:
            return parser.parse(text or "")
        except Exception as e:
            return {"error": "%s: %s" % (type(e).__name__, e)}

    return lc_json_extract


def _lc_word_count():
    """返回 dict（另一种非字符串返回形态）。"""
    from langchain_core.tools import tool

    @tool("lc_word_count", description="统计一段文本的字符数、词数、行数，返回结构化结果。")
    def lc_word_count(text: str) -> dict:
        t = text or ""
        return {"chars": len(t), "words": len(t.split()), "lines": t.count("\n") + 1}

    return lc_word_count


def _lc_write_doc():
    """使用 langchain_core.documents.Document 作为返回值（带 artifact 的场景）。"""
    from langchain_core.tools import tool
    from langchain_core.documents import Document

    @tool("lc_summary_doc", description="把用户给的要点整理成一份 Markdown 文档对象并落盘到 agent_data/exports/，返回文档。")
    def lc_summary_doc(title: str, points: str) -> dict:
        root = os.path.join(tools_layer.APP_ROOT, "agent_data", "exports")
        os.makedirs(root, exist_ok=True)
        safe = re.sub(r"[\\/:*?\"<>|]+", "_", title or "note")[:40] or "note"
        path = os.path.join(root, safe + ".md")
        body = "# %s\n\n%s\n" % (title or "未命名", points or "")
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        doc = Document(page_content=body[:200], metadata={"path": path, "title": title})
        return {"ok": True, "path": path, "doc": doc.page_content}

    return lc_summary_doc


def _optional_community_tools() -> list:
    """社区包存在时才加载（当前环境未安装 langchain-community，走空分支）。"""
    out = []
    try:
        from langchain_community.tools.file_management import ReadFileTool  # type: ignore
        try:
            out.append(ReadFileTool())
        except Exception:
            pass
    except Exception:
        pass
    try:
        from langchain_community.tools import TavilySearchResults  # type: ignore
        if os.environ.get("TAVILY_API_KEY"):
            out.append(TavilySearchResults(max_results=5))
    except Exception:
        pass
    return out


def build_langchain_tools() -> list:
    """LangChain 原生工具（全部是 StructuredTool / BaseTool，不是裸函数）。"""
    tools = []
    for factory in (_lc_json_extract, _lc_word_count, _lc_write_doc):
        try:
            tools.append(factory())
        except Exception as e:
            print("[registry] 构建 LangChain 工具失败，跳过 %s：%s" % (factory.__name__, e),
                  flush=True)
    try:
        tools.extend(_optional_community_tools())
    except Exception:
        pass
    return tools


# ---------------------------------------------------------------- 合并
def build_all_tools(perm: Optional[dict] = None, mcp_tools: Optional[list] = None):
    """自研 + LangChain 生态 + MCP，合并成一份 all_tools（名称去重，自研优先）。

    返回 (tools, origins)：origins 只用于日志/排障，不参与调度。
    """
    builtin = build_lc_tools(perm)
    lc_tools = build_langchain_tools()
    mcp_tools = list(mcp_tools or [])

    merged = []
    seen = set()
    for t in builtin:
        name = getattr(t, "name", "")
        if not name or name in seen:
            continue
        seen.add(name)
        TOOL_ORIGIN[name] = "builtin"
        merged.append(t)
    for t in lc_tools:
        name = getattr(t, "name", "")
        if not name or name in seen:
            print("[registry] 名称冲突，跳过 LangChain 工具：%s" % name, flush=True)
            continue
        seen.add(name)
        TOOL_ORIGIN[name] = "langchain"
        merged.append(t)
    for t in mcp_tools:
        name = getattr(t, "name", "")
        if not name or name in seen:
            continue
        seen.add(name)
        TOOL_ORIGIN[name] = "mcp"
        merged.append(t)
    print("[registry] 工具总数 %d（builtin=%d, langchain=%d, mcp=%d）" % (
        len(merged),
        sum(1 for v in TOOL_ORIGIN.values() if v == "builtin"),
        sum(1 for v in TOOL_ORIGIN.values() if v == "langchain"),
        sum(1 for v in TOOL_ORIGIN.values() if v == "mcp")), flush=True)
    return merged, dict(TOOL_ORIGIN)
