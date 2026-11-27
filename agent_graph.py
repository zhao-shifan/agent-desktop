# -*- coding: utf-8 -*-
"""小凡智能体 · LangGraph 对话图（v2.0 架构升级）

把原 server.py 手写的 function-calling 循环迁移为 LangGraph StateGraph。
图结构：

    START → prepare → call_model ─┬─(有 tool_calls)→ exec_tools → call_model …
                                  ├─(正文漏发工具)→ 恢复层补执行 → call_model
                                  └─(最终回答 / 超轮)→ finalize → END

与旧实现逐项对齐的行为（一项不少）：
- 人设注入在 handle_chat 入口（不变）；本图负责：长期记忆注入、强制预搜索
- 上下文预算裁剪 _trim_history（每次调模型前）
- 思考心跳 SSE（6 秒无响应开始发 thinking.elapsed）
- 429/5xx 指数退避重试（最多 2 次）
- reasoning_content 思考文字实时转发
- 恢复层：模型漏发 tool_call 时从正文解析并补执行（Qwen-Agent 同思路）
- 多 tool_calls 并发执行（线程池，按原顺序回灌）
- 工具结果统一截断 MAX_CHARS，防上下文爆炸
- 超轮收尾：让模型基于已有信息总结（smolagents 同思路）
- trace_event 全链路日志、异步记忆抽取

SSE 事件格式与旧协议完全一致，前端零改动。
执行工具仍统一走 tools_layer.run_tool（保留 perm 权限、MCP、lark_cli 分发）。
"""
import json
import re
import threading
import time
import concurrent.futures

import urllib.error

import tools_layer
from server_helpers import trim_history

# ---- LangChain / LangGraph ----
try:
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.messages.utils import convert_to_openai_messages
    from langgraph.graph import StateGraph, START, END
    from typing import TypedDict
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "缺少 LangChain/LangGraph 依赖，请在运行时 Python 里执行：\n"
        "  python -m pip install langgraph langchain langchain-openai\n"
        f"原始错误：{e}")

MAX_ROUNDS = tools_layer.MAX_ROUNDS
MAX_CHARS = tools_layer.MAX_CHARS


# ----------------------------------------------------------------------
# MCP 工具（langchain-mcp-adapters 官方适配器）
# 配置沿用 agent_data/mcp_servers.json：
#   stdio 服务器：{"name","command","args"} → transport="stdio"
#   http 服务器： {"name","url"[,"transport"]} → transport="streamable_http"/"sse"
# 与 tools_layer 的零依赖 stdio 客户端并存：那边负责兜底与管理面板数据源，
# 这边把工具以 LangChain StructuredTool 形式并入 bind_tools。
# 加载结果模块级缓存；失败只打日志并降级为仅内置工具，绝不拖垮主对话。
# ----------------------------------------------------------------------
_MCP_LC_TOOLS: list = []            # 缓存的 BaseTool/StructuredTool 列表
_MCP_LC_BY_NAME: dict = {}          # name -> BaseTool（exec_tools 直连执行用）
_MCP_LC_LOADED = {"done": False}


def mcp_lc_reset():
    """失效缓存：/api/mcp 保存配置后调用，下次对话重新加载 MCP 工具。"""
    _MCP_LC_TOOLS.clear()
    _MCP_LC_BY_NAME.clear()
    _MCP_LC_LOADED["done"] = False


def _mcp_lc_connections():
    """把 mcp_servers.json 翻译成 MultiServerMCPClient 的 connections dict。
    transports 依据 langchain-mcp-adapters 0.3.2 sessions.py：
    StdioConnection{transport:"stdio",command,args} /
    StreamableHttpConnection{transport:"streamable_http",url} /
    SSEConnection{transport:"sse",url}。"""
    cfg = json.loads(open(tools_layer._mcp_config_path(), "rb").read().decode("utf-8"))
    conns = {}
    for s in (cfg.get("servers") or []):
        if not isinstance(s, dict):
            continue
        name = str(s.get("name") or "").strip()
        if not name:
            continue
        if s.get("url"):
            conns[name] = {"url": str(s["url"]),
                           "transport": s.get("transport") or "streamable_http"}
        elif s.get("command"):
            conns[name] = {"command": str(s["command"]),
                           "args": [str(a) for a in (s.get("args") or [])],
                           "transport": "stdio"}
    return conns


def _load_mcp_lc_tools():
    """同步加载（内部转 asyncio.run），带缓存。任何失败只打日志并返回空列表。"""
    if _MCP_LC_LOADED["done"]:
        return _MCP_LC_TOOLS
    _MCP_LC_LOADED["done"] = True
    try:
        conns = _mcp_lc_connections()
        if not conns:
            return _MCP_LC_TOOLS
        from langchain_mcp_adapters.client import MultiServerMCPClient
        client = MultiServerMCPClient(conns, tool_name_prefix=True)
        import asyncio
        try:
            asyncio.get_running_loop()
            # 已在事件循环内（理论上不会，LangGraph 同步 invoke）：换线程跑
            import concurrent.futures as _cf
            with _cf.ThreadPoolExecutor(1) as ex:
                tools = ex.submit(asyncio.run, client.get_tools()).result(timeout=120)
        except RuntimeError:
            tools = asyncio.run(client.get_tools())
        builtin_names = {t["function"]["name"] for t in tools_layer.TOOL_DEFS}
        for t in tools:
            n = getattr(t, "name", "")
            if not n or n in builtin_names or n in _MCP_LC_BY_NAME:
                continue
            _MCP_LC_BY_NAME[n] = t
            _MCP_LC_TOOLS.append(t)
        if _MCP_LC_TOOLS:
            print(f"[MCP-adapters] 已挂载 {len(_MCP_LC_TOOLS)} 个工具："
                  f"{list(_MCP_LC_BY_NAME)}", flush=True)
    except Exception as e:
        print(f"[MCP-adapters] 加载失败，降级为仅内置工具：{e}", flush=True)
        _MCP_LC_TOOLS.clear()
        _MCP_LC_BY_NAME.clear()
    return _MCP_LC_TOOLS


def _invoke_mcp_lc_tool(name, args_json):
    """直连执行 adapter 返回的 BaseTool（每次调用自动开新 MCP 会话）。"""
    tool = _MCP_LC_BY_NAME.get(name)
    if tool is None:
        return "未知 MCP 工具：%s" % name
    try:
        kwargs = json.loads(args_json) if isinstance(args_json, str) and args_json.strip() else {}
        return str(tool.invoke(kwargs))[:MAX_CHARS]
    except Exception as e:
        return "工具执行失败：%s" % e


def _all_bind_tools():
    """内置 OpenAI function 定义 + MCP adapter 工具，供 bind_tools 使用。"""
    return list(tools_layer.TOOL_DEFS) + _load_mcp_lc_tools()


# ----------------------------------------------------------------------
# State 定义
# ----------------------------------------------------------------------
class ChatState(TypedDict, total=False):
    messages: list          # OpenAI dict 格式消息列表（人设已注入）
    rounds: int             # 已进行的调模型轮数
    final_text: str         # 最终回答
    pending_tools: list     # 本轮待执行 tool_calls（AIMessage 上的）
    utext: str              # 最近一条用户输入（记忆抽取用）
    streamed: bool          # token 是否已实时流出（True 则 finalize 不再补切片）


# ----------------------------------------------------------------------
# 图构建
# ----------------------------------------------------------------------
def build_graph(cfg):
    """按本次请求的配置（模型/权限/SSE 回调）编译一张 StateGraph。"""
    sse = cfg["sse"]
    perm = cfg.get("perm") or {}

    # ---------------- 模型实例 ----------------
    def _make_llm():
        extra = {}
        reasoning = cfg.get("reasoning") or "auto"
        if "bigmodel" in cfg["base"]:
            if reasoning in ("off", "low", "medium", "high"):
                extra["thinking"] = {"type": "disabled" if reasoning == "off" else "enabled"}
        elif reasoning not in ("auto", "off"):
            extra["reasoning_effort"] = reasoning
        return ChatOpenAI(
            base_url=cfg["base"],
            api_key=cfg["key"] or "EMPTY",
            model=cfg["model"],
            temperature=cfg.get("temperature"),
            top_p=cfg.get("topP"),
            max_tokens=cfg.get("maxTokens"),
            timeout=300,
            extra_body=extra,
        ).bind_tools(_all_bind_tools())

    # ---------------- 节点：prepare ----------------
    def prepare(state: ChatState) -> dict:
        """长期记忆注入 + 强制预搜索（DeepSeek/数据注入同思路）。"""
        msgs = list(state["messages"])
        utext = next((m.get("content") for m in reversed(msgs)
                      if m.get("role") == "user" and isinstance(m.get("content"), str)), "")
        try:
            tools_layer.trace_event("user", {"q": str(utext)[:120]})
        except Exception:
            pass
        # mem0 式记忆注入：检索相关历史事实（后台异步抽取写入，这里只读）
        try:
            mem_facts = tools_layer.retrieve_memory(utext)
            if mem_facts:
                msgs.append({"role": "system", "content":
                    "【长期记忆·关于用户的已知事实】来自过去对话的自动记忆，相关时自然使用，"
                    "与本次问题无关时忽略，不要主动逐条复述：\n- " + "\n- ".join(mem_facts)})
        except Exception:
            pass
        # 强制预搜索：事实/时效类问题先搜后答，结果注入上下文
        try:
            if utext and re.search(r"(最新|近日|热点|新闻|多少钱|价格|哪一年|哪年|是谁|搜一?下|查一?下)", utext):
                q = re.sub(r"^(你知道|请问|帮我|麻烦|给我|帮我查?一?下|查一下|搜一下|告诉我|你知道.*吗)+",
                           "", utext.strip())
                q = re.sub(r"(吗|呢|吧|呀|啊|么样|怎么样|咋样|？|\?)+$", "", q).strip() or utext.strip()
                q = q[:40]
                print(f"[预搜索] 改写后关键词：{q}", flush=True)
                pres = tools_layer.web_search(q, key=perm.get("searchKey") or "")
                msgs.append({"role": "system", "content":
                    "以下是系统自动预取的搜索结果（编号 1/2/3…）。回答规则：\n"
                    "1) 必须基于这些内容回答，不许使用搜索结果之外的\"记忆\"；\n"
                    "2) 引用到某条结果时，在句子后面标注编号，如 [1]、[2]；\n"
                    "3) 回答最后单独一行列出用到的来源：[1] 标题 - 链接；\n"
                    "4) 不要重复调用 web_search。\n搜索结果：\n" + str(pres)[:4000]})
        except Exception:
            pass
        return {"messages": msgs, "rounds": 0, "final_text": "", "utext": utext}

    # ---------------- 节点：call_model（token 级流式） ----------------
    def call_model(state: ChatState) -> dict:
        """流式调一次模型：token 到一个转发一个（打字机效果）；
        带心跳、限流重试、reasoning 转发、恢复层、工具调用判定。"""
        rounds = state.get("rounds", 0)
        msgs = list(state["messages"])
        # 客户端已断开（前端点了停止）：不再发起新一轮上游请求，直接收尾退出
        if (cfg.get("_stop") or {}).get("on"):
            print("[断开] 客户端已停止，跳过本轮模型调用", flush=True)
            return {"messages": msgs, "rounds": rounds,
                    "final_text": "", "pending_tools": [], "streamed": True}
        # 轮数上限：不再带工具调模型，直接进入 finalize 的超轮收尾
        if rounds >= MAX_ROUNDS:
            return {"messages": msgs, "rounds": rounds,
                    "final_text": "", "pending_tools": []}
        llm = _make_llm()

        def _beat_flag():
            beat = {"on": True}
            def _heartbeat():
                start = time.time()
                while beat["on"]:
                    if time.time() - start >= 6:
                        sse({"thinking": {"elapsed": round(time.time() - start)}})
                    time.sleep(2)
            t = threading.Thread(target=_heartbeat, daemon=True)
            t.start()
            return beat

        # 恢复层保护缓冲：正文“疑似工具调用 JSON”时先扣住不转发，确认不是再放行。
        # 判定收窄为工具调用签名（```json{ / {"name"… 等），正常代码块与正文立即放行，
        # 保住打字机效果（对齐 Qwen-Agent：结构化 tool_calls 为主，正文解析仅兜底）。
        held = {"buf": "", "locked": False}

        def _held_maybe_tooljson(buf: str) -> bool:
            """held 缓冲是否仍“可能是工具调用 JSON”。True=继续扣住，False=立即放行。"""
            s = buf.lstrip()
            if s.startswith("```"):
                s = s[3:].lstrip()
                if s.startswith("json"):
                    s = s[4:].lstrip()
                elif "json".startswith(s):      # "j"/"js"/"jso" 仍可能是 ```json
                    return True
                elif not s.startswith("{"):
                    return False                # ```python / ```js 等正常代码块
            if not s:
                return True
            if not s.startswith("{"):
                return False
            rest = s[1:].lstrip()
            if not rest:
                return True
            if not rest.startswith('"'):
                return False
            key = rest[1:]
            return any(k.startswith(key) or key.startswith(k)
                       for k in ("name", "tool", "function", "arguments"))

        def _flush(force=False):
            if force or held["locked"] or not _held_maybe_tooljson(held["buf"]):
                held["locked"] = True
                if held["buf"]:
                    sse({"choices": [{"delta": {"content": held["buf"]}}]})
                    held["buf"] = ""

        assembled = None
        for attempt in range(3):     # 0,1,2 → 最多 2 次重试
            beat = _beat_flag()
            t0 = time.time()
            try:
                print(f"[第{rounds + 1}轮] 流式请求模型中（LangGraph）…", flush=True)
                for chunk in llm.stream(trim_history(msgs)):
                    # 客户端已断开（前端点了停止）：立刻停止拉取上游，不再白跑完
                    if (cfg.get("_stop") or {}).get("on"):
                        print("[断开] 客户端已停止，中断本轮生成", flush=True)
                        _flush(force=True)
                        return {"messages": msgs, "rounds": rounds,
                                "final_text": "", "pending_tools": [], "streamed": True}
                    # thinking 文字实时转发（glm/deepseek 推理模型）
                    try:
                        rc = (chunk.additional_kwargs or {}).get("reasoning_content") or ""
                    except Exception:
                        rc = ""
                    if rc and rc.strip():
                        sse({"choices": [{"delta": {"reasoning_content": rc}}]})
                    # 正文 token 实时转发（打字机）
                    c = chunk.content
                    if isinstance(c, list):     # 多模态块只取文本
                        c = "".join(p.get("text", "") for p in c if isinstance(p, dict))
                    if c:
                        held["buf"] += c
                        _flush()
                    assembled = chunk if assembled is None else assembled + chunk
                print(f"[第{rounds + 1}轮] 模型响应耗时 {time.time() - t0:.1f}s", flush=True)
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                    wait = (2 ** attempt) * 3
                    sse({"choices": [{"delta": {"content":
                        f"（接口限流/波动，{wait}s 后自动重试 {attempt + 1}/2…）"}}]})
                    time.sleep(wait)
                    assembled = None
                    continue
                raise
            finally:
                beat["on"] = False

        if assembled is None:
            raise RuntimeError("模型无响应")

        # thinking 文字兜底（非流式场景）
        rc = ""
        try:
            rc = (assembled.additional_kwargs or {}).get("reasoning_content") or ""
        except Exception:
            pass

        try:
            tools_layer.trace_event("llm", {"round": rounds + 1,
                                            "elapsed": round(time.time() - t0, 1),
                                            "tool_calls": len(assembled.tool_calls or [])})
        except Exception:
            pass

        oai = convert_to_openai_messages([assembled])[0]

        # ---- 无 tool_calls：先过恢复层，再判定是否最终回答 ----
        if not (assembled.tool_calls or []):
            final_text = oai.get("content") or ""
            if not str(final_text).strip() and rc:
                final_text = rc
            # 恢复层：模型把工具参数写成正文 → 框架层补执行并回灌
            try:
                from server import _recover_tool_call   # 复用主服务里的恢复层实现
                rec = _recover_tool_call(final_text,
                                         {t["function"]["name"] for t in tools_layer.TOOL_DEFS})
            except Exception:
                rec = None
            if rec:
                held["buf"] = ""   # 确认是工具 JSON：丢弃原文，绝不让前端看到裸 JSON
                rname, rargs, rclean = rec
                tc = {"id": "rec-%d" % int(time.time() * 1000), "type": "function",
                      "function": {"name": rname, "arguments": json.dumps(rargs, ensure_ascii=False)}}
                print(f"[恢复层] 模型漏发 tool_call，框架补执行：{rname}({json.dumps(rargs)[:80]})", flush=True)
                # 交给 exec_tools 执行（事件由 _run_one 统一发 running/done），执行后
                # 自动回到 call_model，让模型基于工具结果继续作答（对齐 Qwen-Agent 循环）。
                return {"messages": msgs + [
                            {"role": "assistant", "content": str(rclean).strip(), "tool_calls": [tc]},
                        ],
                        "rounds": rounds + 1, "final_text": "", "pending_tools": [tc]}
            # 正常最终回答：先放行被扣住的缓冲（确认不是工具 JSON），token 已实时流出
            _flush(force=True)
            return {"messages": msgs + [oai], "rounds": rounds + 1,
                    "final_text": str(final_text), "pending_tools": [], "streamed": True}

        # ---- 有 tool_calls：正文已实时流出，暂存工具调用交给 exec_tools ----
        _flush(force=True)   # 工具调用前的序言文字照常放行
        return {"messages": msgs + [oai], "rounds": rounds + 1,
                "pending_tools": oai.get("tool_calls") or [], "streamed": True}

    # ---------------- 条件路由 ----------------
    def route(state: ChatState) -> str:
        if state.get("pending_tools"):
            return "exec_tools"
        if str(state.get("final_text") or "").strip():
            return "finalize"
        # 理论到不了这里（要么有工具要么有文本），兜底收尾
        return "finalize"

    # ---------------- 节点：exec_tools ----------------
    def exec_tools(state: ChatState) -> dict:
        """并发执行本轮全部 tool_calls（线程池），结果按原顺序回灌。"""
        tool_calls = state["pending_tools"]
        msgs = list(state["messages"])
        # 工具执行期间可能几十秒没有任何 data 事件 → 定期发 SSE 注释心跳保活
        # （防代理网关/手机 WebView 判定空闲断流；注释行前端解析器直接跳过）
        ping_on = {"v": True}

        def _pinger():
            while ping_on["v"]:
                time.sleep(15)
                if not ping_on["v"]:
                    break
                try:
                    ping = cfg.get("ping")
                    if callable(ping):
                        ping()
                except Exception:
                    pass

        ping_thread = threading.Thread(target=_pinger, daemon=True)
        ping_thread.start()

        def _run_one(tc):
            fn = tc.get("function") or {}
            t0 = time.time()
            # ---- 人工审批（HITL）：approveTools 开启时，执行前先请示 ----
            if cfg.get("approveTools") and callable(cfg.get("waitApproval")):
                aid = str(tc.get("id") or "") or ("apr-%d" % int(time.time() * 1000))
                sse({"approval_request": {"id": aid, "name": fn.get("name"),
                                          "args": str(fn.get("arguments") or "")}})
                approved = bool(cfg["waitApproval"](aid, 120))
                if not approved:
                    print(f"[审批] 用户拒绝/超时：{fn.get('name')}", flush=True)
                    try:
                        tools_layer.trace_event("approval", {"name": fn.get("name"),
                                                             "approved": False})
                    except Exception:
                        pass
                    sse({"tool": {"id": tc.get("id"), "name": fn.get("name"),
                                  "args": str(fn.get("arguments") or ""),
                                  "status": "denied"}})
                    return tc, fn.get("name"), "用户拒绝执行该工具。"
                try:
                    tools_layer.trace_event("approval", {"name": fn.get("name"),
                                                         "approved": True})
                except Exception:
                    pass
            # 开始事件必须在执行前发出（对齐 LangGraph ToolNode 的 on_tool_start 语义）
            sse({"tool": {"id": tc.get("id"), "name": fn.get("name"),
                          "args": str(fn.get("arguments") or ""), "status": "running"}})
            # ---- MCP adapter 工具直连执行；其余走 tools_layer（保留 perm/MCP 兜底） ----
            try:
                if fn.get("name") in _MCP_LC_BY_NAME:
                    result = _invoke_mcp_lc_tool(fn.get("name"), fn.get("arguments") or "")
                else:
                    result = tools_layer.run_tool(tc, perm)
            except Exception as e:      # 错误回填：不中断循环，让模型自行纠正
                result = f"工具执行失败：{e}"
            sse({"tool": {"id": tc.get("id"), "name": fn.get("name"),
                          "status": "done", "preview": str(result)[:400]}})
            try:
                brief = str(fn.get("arguments") or "")[:80]
                print(f"[工具] {fn.get('name')}({brief}) 耗时 {time.time() - t0:.1f}s", flush=True)
                tools_layer.trace_event("tool", {
                    "name": fn.get("name"), "args": brief,
                    "elapsed": round(time.time() - t0, 1),
                    "ok": not str(result).startswith(("工具执行失败", "被拒绝"))})
            except Exception:
                pass
            return tc, fn.get("name"), result

        if len(tool_calls) > 1:
            with concurrent.futures.ThreadPoolExecutor(
                    max_workers=min(4, len(tool_calls))) as ex:
                futures = [ex.submit(_run_one, tc) for tc in tool_calls]
                pairs = [f.result() for f in concurrent.futures.as_completed(futures)]
            order = {id(tc): i for i, tc in enumerate(tool_calls)}
            pairs.sort(key=lambda p: order[id(p[0])])
        else:
            pairs = [_run_one(tool_calls[0])]
        ping_on["v"] = False   # 工具全部执行完，停掉心跳线程

        # 工具事件已由 _run_one 在执行前后发出（对齐 LangGraph ToolNode 的
        # on_tool_start 语义），这里只回灌结果，避免重复/滞后事件
        for tc, name, result in pairs:
            msgs.append({"role": "tool", "tool_call_id": tc.get("id"),
                         "content": str(result)[:MAX_CHARS]})
        return {"messages": msgs, "pending_tools": []}

    # ---------------- 节点：finalize ----------------
    def finalize(state: ChatState) -> dict:
        """最终回答切片流式吐给前端 + 超轮收尾 + 异步记忆抽取。"""
        final_text = str(state.get("final_text") or "")
        msgs = list(state["messages"])
        rounds = state.get("rounds", 0)

        # 超轮收尾：让模型基于已有信息直接总结（smolagents provide_final_answer 同思路）
        if not final_text.strip() and rounds >= MAX_ROUNDS:
            msgs.append({"role": "user", "content":
                "工具调用轮数已达上限，不能再调用任何工具。请立即基于上面已经拿到的信息给出你能给出的最佳回答；"
                "如果关键信息确实缺失，明确指出缺什么、让用户补充。"})
            try:
                ai = _make_llm().invoke(trim_history(msgs))
                oai = convert_to_openai_messages([ai])[0]
                final_text = oai.get("content") or final_text or "（工具调用轮数达到上限，请补充信息后重试）"
            except Exception:
                final_text = final_text or "（工具调用轮数达到上限，请补充信息后重试）"

        # token 已由 call_model 实时流出时不再重复切片；只有恢复层清洗文字、
        # 超轮收尾总结这类"事后才知道的文本"才在这里补流
        if not state.get("streamed"):
            for i in range(0, len(final_text), 24):
                sse({"choices": [{"delta": {"content": final_text[i:i + 24]}}]})
        # Follow-up 追问建议：可选开启，用同一模型（不带工具、temperature 0.8）
        # 生成 3 条追问；解析失败静默跳过，绝不影响主回答。
        if cfg.get("followups") and final_text.strip():
            _gen_followups(cfg, final_text)
        try:
            tools_layer.trace_event("final", {"rounds": len(msgs), "answer_len": len(final_text)})
        except Exception:
            pass
        # mem0 式记忆抽取：答案完整后后台异步跑，不阻塞响应
        try:
            utext = state.get("utext") or ""
            if utext and len(utext) >= 6 and len(final_text) >= 10 \
                    and not re.match(r"^(你好|您好|hi|hello|嗨|哈喽|在吗|谢谢|再见|晚安|早安)[\s！!～~。.]*$",
                                     utext.strip()):
                _extract_memory_async(cfg, utext, final_text)
        except Exception:
            pass
        return {"final_text": final_text}

    # ---------------- 组图 ----------------
    g = StateGraph(ChatState)
    g.add_node("prepare", prepare)
    g.add_node("call_model", call_model)
    g.add_node("exec_tools", exec_tools)
    g.add_node("finalize", finalize)
    g.add_edge(START, "prepare")
    g.add_edge("prepare", "call_model")
    g.add_conditional_edges("call_model", route,
                            {"exec_tools": "exec_tools", "finalize": "finalize"})
    g.add_edge("exec_tools", "call_model")
    g.add_edge("finalize", END)
    # Checkpointer：按 thread_id 保存每步状态快照，支持断点恢复/时间旅行。
    # 开发用 MemorySaver（内存）；线上换 RedisSaver/PostgresSaver 只需改这里。
    return g.compile(checkpointer=_CHECKPOINTER)


# 进程内共享的检查点器（开发版）。线上部署时替换为：
#   from langgraph.checkpoint.redis import RedisSaver      # pip install langgraph-checkpoint-redis
#   from langgraph.checkpoint.postgres import PostgresSaver # pip install langgraph-checkpoint-postgres
from langgraph.checkpoint.memory import MemorySaver


class BoundedMemorySaver(MemorySaver):
    """带 thread 数量上限的 MemorySaver：LRU 淘汰最久未写入的会话。

    背景：MemorySaver 的 storage/writes/blobs 是三个只增不减的容器
    （见 langgraph/checkpoint/memory/__init__.py），长驻 8765 服务每聊一次
    就多一份完整快照，内存会一直涨。官方提供了 delete_thread(thread_id)
    一次性清理 storage/writes/blobs 三处（同文件 L514-530），这里在每次
    put 后按 LRU 调它释放，语义与 RedisSaver/PostgresSaver 的过期淘汰一致。
    """

    def __init__(self, max_threads: int = 50):
        super().__init__()
        self._max_threads = max(1, int(max_threads))
        self._touched: dict = {}      # thread_id -> 最近写入时间
        self._evict_lock = threading.Lock()

    def _touch_and_evict(self, thread_id: str) -> None:
        with self._evict_lock:
            self._touched[thread_id] = time.time()
            if len(self._touched) <= self._max_threads:
                return
            stale = sorted(self._touched.items(), key=lambda kv: kv[1])
            for tid, _ in stale[:len(self._touched) - self._max_threads]:
                self._touched.pop(tid, None)
                try:
                    self.delete_thread(tid)
                except Exception:
                    pass

    def put(self, config, checkpoint, metadata, new_versions):
        try:
            tid = config["configurable"]["thread_id"]
            self._touch_and_evict(str(tid))
        except Exception:
            pass
        return super().put(config, checkpoint, metadata, new_versions)


# 上限 50 个会话（约覆盖最近 50 个聊天）；超出的最旧会话快照自动释放。
_CHECKPOINTER = BoundedMemorySaver(max_threads=50)


def _extract_memory_async(cfg, user_text, answer):
    """异步记忆抽取（mem0 同思路）：后台跑，失败静默。实际实现复用 server.py 的。"""
    try:
        from server import _extract_memory_async as _impl
        _impl(cfg["base"], cfg["key"], cfg["model"], user_text, answer)
    except Exception:
        pass


def _gen_followups(cfg, final_text):
    """基于最终回答生成 3 条追问建议。失败静默。"""
    try:
        llm = ChatOpenAI(
            base_url=cfg["base"], api_key=cfg["key"] or "EMPTY",
            model=cfg["model"], temperature=0.8, timeout=60)
        resp = llm.invoke([
            {"role": "system", "content":
                "基于刚才的回答，给用户推荐 3 条简短的追问，输出 JSON 数组，"
                "每项 {\"title\",\"label\",\"prompt\"}，title≤10字，"
                "prompt 为完整追问句子，只输出 JSON，不要输出任何其他文字。"},
            {"role": "user", "content": str(final_text)[:4000]},
        ])
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        m = re.search(r"\[[\s\S]*\]", text)
        if not m:
            return
        data = json.loads(m.group(0))
        if not isinstance(data, list):
            return
        out = [{"title": str(it.get("title") or "")[:12],
                "label": str(it.get("label") or it.get("title") or "")[:20],
                "prompt": str(it.get("prompt") or "")}
               for it in data[:3] if isinstance(it, dict) and it.get("prompt")]
        if out:
            cfg["sse"]({"suggestions": out})
    except Exception as e:
        print(f"[followups] 生成失败，已跳过：{e}", flush=True)


def run_chat(cfg, messages):
    """入口：编译图并执行。SSE 已由节点内回调发出；本函数阻塞到对话结束。

    LangSmith 全链路追踪：设置环境变量即自动生效（langchain 原生支持，零代码）：
        LANGSMITH_TRACING=true
        LANGSMITH_API_KEY=lsv2_...      # smith.langchain.com 免费注册
        LANGSMITH_PROJECT=xiaofan-agent # 可选，默认 project
    """
    graph = build_graph(cfg)
    thread_id = str(cfg.get("threadId") or "default")
    # 显式重置全部回合级字段：checkpointer 会把同 thread_id 上一轮的 state 带进来，
    # 若只传 messages，rounds/streamed/final_text 会从旧快照继承（rounds 越滚越大，
    # 几轮之后新请求一起步就撞 MAX_ROUNDS 上限）。历史仍由本次 messages 全量覆盖。
    final = graph.invoke(
        {"messages": list(messages), "rounds": 0, "final_text": "",
         "pending_tools": [], "utext": "", "streamed": False},
        config={
            "configurable": {"thread_id": thread_id},   # 断点续跑/恢复的会话标识
            "recursion_limit": (MAX_ROUNDS + 4) * 4,    # 防死循环兜底
        })
    return final.get("final_text", "")
