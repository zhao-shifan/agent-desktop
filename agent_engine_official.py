"""官方智能体循环引擎：langchain.agents.create_agent + 官方 ToolNode + middleware。

设计原则
- 循环/工具调度/并发/错误回填全部交给官方 ToolNode，不再手写；
- 旧 agent_graph.py 的 prepare/call_model/exec_tools/finalize 里的业务能力，
  逐条改写成 AgentMiddleware（官方扩展点），不另起一套调度；
- 入口与旧实现同名 run_chat(cfg, messages)，SSE 事件键与旧协议一致。

已迁移的 middleware（按计划顺序）
1. PresearchMiddleware  —— 时效预搜索注入（对应旧 prepare 的强制搜索）
2. RecoveryMiddleware   —— 恢复层：模型把工具调用写成正文时补执行
3. HeartbeatMiddleware  —— 思考心跳 {"thinking":{"elapsed":N}}（每 6s）
4. RoundLimitMiddleware —— 超轮收尾：达到 MAX_ROUNDS 后摘工具 + 要求总结
5. FollowupsMiddleware  —— 追问建议 {"suggestions":[...]}
6. TrimMiddleware       —— 用官方 trim_messages 替换手写 trim_history
+  ToolEventsMiddleware  —— 人工审批 + 工具事件 + trace（工具调度仍归官方 ToolNode）

已知差异（2026-11-27 观测，方案 A：保留官方顺序）
- 多工具 + 审批时，官方是"逐个审批→逐个执行"；旧图是"先批量要审批→再执行"。
  前端的审批弹窗目前尚未实现（index.html 无 approve 引用），故不影响现状；
  将来做审批 UI 时按"逐个弹窗"实现即可。
- create_agent 的 messages 是 add_messages 归约器（追加），旧图是覆盖。
  因此每轮请求前清掉该 thread 的旧快照，保持"前端传全量历史"的旧语义。

灰度开关：环境变量 XIAOFAN_ENGINE=official 时 server.py 走这里，否则走旧图。
"""
from __future__ import annotations

import json
import os
import re
import threading
import time

from langchain_core.messages import (AIMessage, AIMessageChunk, HumanMessage,
                                     RemoveMessage, SystemMessage, ToolMessage)
from langchain_openai import ChatOpenAI

from agent_lc_tools import build_lc_tools
from agent_tool_registry import (TOOL_ORIGIN, build_all_tools, normalize_result)
import tools_layer


class ToolFailure(Exception):
    """工具执行失败：统一格式化后抛出，由官方 ToolErrorMiddleware 转成错误 ToolMessage。

    之所以"先标记再抛"：既满足"异常向上抛、由官方兜底"的约定，又能让模型拿到
    "工具执行失败：..." 的文本、继续本轮对话（与旧引擎的 error 回填行为一致）。
    """

MAX_ROUNDS = getattr(tools_layer, "MAX_ROUNDS", 4)
MAX_CHARS = getattr(tools_layer, "MAX_CHARS", 12000)
CTX_BUDGET = 120000          # 与 server_helpers.trim_history 的 budget 一致
KEEP_RECENT = 8

_PRESEARCH_RE = re.compile(r"(最新|近日|热点|新闻|多少钱|价格|哪一年|哪年|是谁|搜一?下|查一?下)")


# ---------------------------------------------------------------- 模型
def _make_model(cfg):
    base = cfg.get("base") or ""
    extra = {}
    reasoning = cfg.get("reasoning") or "auto"
    if "bigmodel" in base:
        if reasoning in ("off", "low", "medium", "high"):
            extra["thinking"] = {"type": "disabled" if reasoning == "off" else "enabled"}
    elif reasoning not in ("auto", "off"):
        extra["reasoning_effort"] = reasoning
    return ChatOpenAI(
        base_url=base,
        api_key=cfg.get("key") or "EMPTY",
        model=cfg.get("model") or "",
        temperature=cfg.get("temperature"),
        top_p=cfg.get("topP"),
        max_tokens=cfg.get("maxTokens"),
        timeout=300,
        extra_body=extra or None,
    )


# ---------------------------------------------------------------- 恢复层缓冲
def _maybe_tooljson(buf: str) -> bool:
    """缓冲内容是否仍"可能是工具调用 JSON"（与旧 call_model 判定一致）。"""
    s = buf.lstrip()
    if s.startswith("```"):
        s = s[3:].lstrip()
        if s.startswith("json"):
            s = s[4:].lstrip()
        elif "json".startswith(s):
            return True
        elif not s.startswith("{"):
            return False
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


class _Hold:
    """正文保护缓冲：疑似工具 JSON 时先扣住不发给前端。"""

    def __init__(self):
        self.buf = ""
        self.locked = False

    def feed(self, text: str) -> str:
        if not text:
            return ""
        self.buf += text
        if self.locked or not _maybe_tooljson(self.buf):
            self.locked = True
            out, self.buf = self.buf, ""
            return out
        return ""

    def drop(self) -> None:
        """确认是工具 JSON：丢掉，绝不能让前端看到裸 JSON。"""
        self.buf = ""
        self.locked = True

    def finish(self) -> str:
        if self.locked:
            out, self.buf = self.buf, ""
            return out
        if _maybe_tooljson(self.buf):
            self.buf = ""
            return ""
        out, self.buf = self.buf, ""
        return out


# ---------------------------------------------------------------- middleware
def _make_middlewares(cfg, sse):
    from langchain.agents.middleware import (AgentMiddleware, ModelCallLimitMiddleware,
                                            ToolErrorMiddleware)

    perm = cfg.get("perm") or {}
    agent_state = {"model_calls": 0, "presearch_done": False, "memory_done": False,
                   "limit_hint": False}

    class Presearch(AgentMiddleware):
        """旧 prepare 的等价物：长期记忆 + 时效预搜索（每轮只做一次）。"""

        def before_model(self, state, runtime=None):
            msgs = list(state.get("messages") or [])
            utext = ""
            for m in reversed(msgs):
                if getattr(m, "type", "") == "human":
                    utext = getattr(m, "content", "") or ""
                    break
            add = []
            if not agent_state["memory_done"]:
                agent_state["memory_done"] = True
                try:
                    facts = tools_layer.retrieve_memory(str(utext))
                except Exception:
                    facts = []
                if facts:
                    add.append(SystemMessage(content=
                        "【长期记忆·关于用户的已知事实】来自过去对话的自动记忆，相关时自然使用，"
                        "与本次问题无关时忽略，不要主动逐条复述：\n- " + "\n- ".join(facts)))
            if not agent_state["presearch_done"]:
                agent_state["presearch_done"] = True
                if utext and _PRESEARCH_RE.search(utext):
                    try:
                        q = re.sub(r"^(你知道|请问|帮我|麻烦|给我|帮我查?一?下|查一下|搜一下|告诉我|你知道.*吗)+",
                                   "", utext.strip())
                        q = re.sub(r"(吗|呢|吧|呀|啊|么样|怎么样|咋样|？|\?)+$", "", q).strip() or utext.strip()
                        q = q[:40]
                        print(f"[预搜索] 改写后关键词：{q}", flush=True)
                        pres = tools_layer.web_search(q, key=perm.get("searchKey") or "")
                        add.append(SystemMessage(content=
                            "以下是系统自动预取的搜索结果（编号 1/2/3…）。回答规则：\n"
                            "1) 必须基于这些内容回答，不许使用搜索结果之外的\"记忆\"；\n"
                            "2) 引用到某条结果时，在句子后面标注编号，如 [1]、[2]；\n"
                            "3) 回答最后单独一行列出用到的来源：[1] 标题 - 链接；\n"
                            "4) 不要重复调用 web_search。\n搜索结果：\n" + str(pres)[:4000]))
                    except Exception as e:
                        print(f"[预搜索] 失败，跳过：{e}", flush=True)
            return {"messages": add} if add else None

    class Heartbeat(AgentMiddleware):
        """思考心跳：模型响应慢时每 6s 发一次 {"thinking":{"elapsed":N}}。"""

        def wrap_model_call(self, request, handler):
            on = {"v": True}
            start = time.time()

            def _beat():
                last = 0
                while on["v"]:
                    if time.time() - start >= 6 and int(time.time() - start) > last:
                        last = int(time.time() - start)
                        try:
                            sse({"thinking": {"elapsed": round(time.time() - start)}})
                        except Exception:
                            pass
                    time.sleep(2)

            t = threading.Thread(target=_beat, daemon=True)
            t.start()
            try:
                return handler(request)
            finally:
                on["v"] = False

    class RoundLimit(AgentMiddleware):
        """超轮收尾的"最后一轮"：官方 ModelCallLimitMiddleware 负责硬停（见下），
        这里只负责在硬停之后补一次"不带工具"的总结调用（对应旧 finalize 的超轮收尾）。

        说明：不要在 wrap_model_call 里直接返回最终消息来结束循环——create_agent 的
        路由会继续回到 tools 节点，形成死循环（实测 GraphRecursionError）。
        由官方 limit 中间件 exit_behavior="end" 结束，再在 run_chat 里补总结调用。
        """

        def wrap_model_call(self, request, handler):
            agent_state["model_calls"] += 1
            return handler(request)

    class Recovery(AgentMiddleware):
        """恢复层：模型没发 tool_calls、却把工具调用写进了正文 → 补成真正的 tool_call。"""

        def after_model(self, state, runtime=None):
            msgs = list(state.get("messages") or [])
            if not msgs:
                return None
            last = msgs[-1]
            if getattr(last, "type", "") != "ai" or getattr(last, "tool_calls", None):
                return None
            text = last.content if isinstance(last.content, str) else ""
            if not text or "{" not in text:
                return None
            try:
                from server import _recover_tool_call
                rec = _recover_tool_call(text, {t["function"]["name"] for t in tools_layer.TOOL_DEFS})
            except Exception:
                rec = None
            if not rec:
                return None
            name, args, clean = rec
            tc = {"id": "rec-%d" % int(time.time() * 1000), "type": "function",
                  "name": name, "args": args}
            print(f"[恢复层] 模型漏发 tool_call，框架补执行：{name}({json.dumps(args)[:80]})",
                  flush=True)
            return {"messages": [RemoveMessage(id=last.id),
                                 AIMessage(content=str(clean).strip(), tool_calls=[tc])]}

    class Trim(AgentMiddleware):
        """上下文裁剪：用官方 trim_messages 替换手写 trim_history。"""

        def before_model(self, state, runtime=None):
            msgs = list(state.get("messages") or [])
            total = sum(len(str(getattr(m, "content", "") or "")) for m in msgs)
            if total <= CTX_BUDGET:
                return None
            try:
                from langchain_core.messages.utils import trim_messages
                kept = trim_messages(
                    msgs,
                    max_tokens=CTX_BUDGET,
                    token_counter=lambda ms: sum(len(str(getattr(m, "content", "") or "")) for m in ms),
                    strategy="last",
                    include_system=True,
                    start_on="human",
                )
            except Exception as e:
                print(f"[裁剪] trim_messages 失败，回退逐条压缩：{e}", flush=True)
                n = len(msgs)
                return {"messages": [
                    RemoveMessage(id=m.id) for i, m in enumerate(msgs)
                    if i < n - KEEP_RECENT and getattr(m, "id", None)
                    and getattr(m, "type", "") in ("tool", "ai", "human")]}
            kept_ids = {getattr(m, "id", None) for m in kept}
            drop = [RemoveMessage(id=m.id) for m in msgs
                    if getattr(m, "id", None) and m.id not in kept_ids]
            if drop:
                print(f"[裁剪] trim_messages 移除 {len(drop)} 条（原 {len(msgs)} 条）", flush=True)
            return {"messages": drop} if drop else None

    class ToolGlue(AgentMiddleware):
        """统一胶水层：对所有工具（自研 / LangChain / MCP）一视同仁。

        执行前：approval_request 审批 → trace 埋点 → tool_running 事件
        执行后：normalize_result 强制归一化 → preview / files → tool_done 事件
        异常：格式化 + 错误 trace + tool_done（带错误 preview）→ 抛出 ToolFailure，
              由官方 ToolErrorMiddleware 转成错误 ToolMessage（模型可继续），
              未捕获的其它异常继续上抛给 server.py 统一兜底。
        """

        def wrap_tool_call(self, request, handler):
            tc = getattr(request, "tool_call", None) or {}
            name = tc.get("name") or ""
            args = tc.get("args") or {}
            tcid = tc.get("id") or ""
            origin = TOOL_ORIGIN.get(name, "builtin")
            t0 = time.time()

            if cfg.get("approveTools") and callable(cfg.get("waitApproval")):
                aid = str(tcid) or ("apr-%d" % int(time.time() * 1000))
                sse({"approval_request": {"id": aid, "name": name, "origin": origin,
                                          "args": json.dumps(args, ensure_ascii=False)}})
                if not bool(cfg["waitApproval"](aid, 120)):
                    try:
                        tools_layer.trace_event("approval", {"name": name, "approved": False})
                    except Exception:
                        pass
                    sse({"tool": {"id": tcid, "name": name, "origin": origin,
                                  "args": "", "status": "denied"}})
                    return ToolMessage(content="用户拒绝执行该工具。", tool_call_id=tcid,
                                       name=name)

            sse({"tool": {"id": tcid, "name": name, "origin": origin,
                          "args": json.dumps(args, ensure_ascii=False)[:400],
                          "status": "running"}})
            try:
                tools_layer.trace_event("tool_start", {"name": name, "origin": origin})
            except Exception:
                pass

            try:
                result = handler(request)
            except Exception as e:
                err = "工具执行失败：%s" % e
                try:
                    tools_layer.trace_event("tool_error", {
                        "name": name, "origin": origin,
                        "type": type(e).__name__, "msg": str(e)[:200]})
                except Exception:
                    pass
                # 先给前端一个带错误信息的 done，避免卡片一直转圈（与旧引擎一致）
                sse({"tool": {"id": tcid, "name": name, "origin": origin,
                              "status": "done", "preview": err[:400], "files": []}})
                raise ToolFailure(err) from e

            # ---- 结果归一化：不管 LangChain 工具返回什么形状，都对齐项目约定 ----
            if isinstance(result, ToolMessage):
                norm = normalize_result(name, result.content)
                artifact = getattr(result, "artifact", None)
                if artifact is not None:
                    extra = normalize_result(name, artifact)
                    seen = {f["path"] for f in norm["files"]}
                    norm["files"].extend(f for f in extra["files"] if f["path"] not in seen)
                out = ToolMessage(content=norm["text"][:MAX_CHARS] or norm["preview"],
                                  tool_call_id=tcid, name=name)
            else:
                norm = normalize_result(name, result)
                out = result          # Command 等官方控制流原样返回

            sse({"tool": {"id": tcid, "name": name, "origin": origin,
                          "status": "done", "preview": norm["preview"],
                          "files": norm["files"]}})
            try:
                tools_layer.trace_event("tool", {
                    "name": name, "origin": origin,
                    "args": json.dumps(args, ensure_ascii=False)[:80],
                    "elapsed": round(time.time() - t0, 1),
                    "files": [f["path"] for f in norm["files"]][:5],
                    "ok": True})
            except Exception:
                pass
            return out

    class Followups(AgentMiddleware):
        """回答结束后生成 3 条追问建议（旧 finalize 的同款能力）。"""

        def after_agent(self, state, runtime=None):
            if not cfg.get("followups"):
                return None
            msgs = list(state.get("messages") or [])
            final = ""
            for m in reversed(msgs):
                if getattr(m, "type", "") == "ai" and not getattr(m, "tool_calls", None):
                    c = getattr(m, "content", "")
                    final = c if isinstance(c, str) else ""
                    break
            if not final.strip():
                return None
            try:
                import agent_graph
                agent_graph._gen_followups(cfg, final)
            except Exception as e:
                print(f"[followups] 生成失败，已跳过：{e}", flush=True)
            return None

    return [Presearch(), Heartbeat(), RoundLimit(), Recovery(),
            # 中间件顺序：列表前面的在外层。ToolErrorMiddleware 必须包在 ToolGlue 外层，
            # 才能把 ToolGlue 抛出的 ToolFailure 转成错误 ToolMessage（实测顺序反了会直接冒到 server）。
            ToolErrorMiddleware(on_error=lambda exc, req: (
                str(exc) if isinstance(exc, ToolFailure) else None)),
            ToolGlue(),
            Trim(), Followups(),
            # 官方硬上限：超过 MAX_ROUNDS+1 次模型调用就优雅结束（不会再无限循环）
            ModelCallLimitMiddleware(run_limit=MAX_ROUNDS + 1, exit_behavior="end")]


# ---------------------------------------------------------------- 主入口
def run_chat(cfg, messages):
    """官方循环入口：与 agent_graph.run_chat 同签名、同 SSE 协议。"""
    from langchain.agents import create_agent

    sse = cfg["sse"]
    perm = cfg.get("perm") or {}
    mcp_tools = []
    try:
        import agent_graph
        mcp_tools = agent_graph._load_mcp_lc_tools()
    except Exception as e:
        print("[engine-official] MCP 加载跳过：%s" % e, flush=True)

    model = _make_model(cfg)
    tools, origins = build_all_tools(perm, mcp_tools)
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=cfg.get("systemPrompt") or "",
        middleware=_make_middlewares(cfg, sse),
        checkpointer=_get_checkpointer(),
    )

    lc_messages = [_to_lc(m) for m in messages] if isinstance(messages, list) else []

    thread_id = str(cfg.get("threadId") or "default")
    # create_agent 的 state.messages 是 add_messages 归约器（追加），而前端每轮都带全量历史。
    # 沿用旧图"用传入 messages 重建状态"的语义：先清掉该线程旧快照。
    try:
        _get_checkpointer().delete_thread(thread_id)
    except Exception:
        pass
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 40}

    hold = _Hold()
    final = ""

    def emit(text):
        if text:
            sse({"choices": [{"delta": {"content": text}}]})

    # 异常不在这里吞：交给 server.py 的统一兜底（补提示 + 记 llm_error trace）。
    for chunk, meta in agent.stream({"messages": lc_messages}, config,
                                    stream_mode="messages"):
        node = (meta or {}).get("langgraph_node") or ""
        if isinstance(chunk, ToolMessage):
            hold.drop()
            continue
        if node not in ("model", "agent", "call_model"):
            continue
        if not isinstance(chunk, (AIMessage, AIMessageChunk)):
            continue
        ak = getattr(chunk, "additional_kwargs", {}) or {}
        rc = ak.get("reasoning_content") or ak.get("reasoning")
        if rc:
            sse({"choices": [{"delta": {"reasoning_content": rc}}]})
        text = chunk.content
        if isinstance(text, list):
            text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
        if text:
            out = hold.feed(text)
            if out:
                final += out
                emit(out)
    emit(hold.finish())

    # 超轮收尾：官方 ModelCallLimitMiddleware 硬停后可能一条正文都没有（模型一直在要工具）。
    # 这里补一次"不带工具"的总结调用，对应旧 finalize 的超轮收尾逻辑。
    if not final.strip():
        try:
            msgs = list(lc_messages) + [HumanMessage(content=
                "不能再调工具了。请基于以上已有信息，立即给出最终总结回答，不要再请求工具。")]
            try:
                model_no_tools = model.bind_tools([])
            except Exception:
                model_no_tools = model
            resp = model_no_tools.invoke(msgs)
            text = resp.content if isinstance(resp.content, str) else ""
            if text:
                print("[超轮] 补总结调用已产出正文", flush=True)
                sse({"choices": [{"delta": {"content": text}}]})
                final = text
        except Exception as e:
            print(f"[超轮] 总结调用失败：{e}", flush=True)
    return final


def _to_lc(m):
    """dict 消息 → LangChain 消息对象。"""
    if not isinstance(m, dict):
        return m
    role = m.get("role")
    content = m.get("content")
    if isinstance(content, list):
        content = "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
    if role == "user":
        return HumanMessage(content=content or "")
    if role == "assistant":
        return AIMessage(content=content or "")
    if role == "system":
        return SystemMessage(content=content or "")
    if role == "tool":
        return ToolMessage(content=content or "", tool_call_id=m.get("tool_call_id") or "")
    return HumanMessage(content=str(content or ""))


_CP = {"saver": None}
_CP_LOCK = threading.Lock()


def _get_checkpointer():
    """复用旧图的 BoundedMemorySaver（有 thread 上限，防内存涨）。"""
    with _CP_LOCK:
        if _CP["saver"] is None:
            try:
                import agent_graph
                _CP["saver"] = agent_graph._CHECKPOINTER
            except Exception:
                from langgraph.checkpoint.memory import MemorySaver
                _CP["saver"] = MemorySaver()
        return _CP["saver"]


def enabled():
    return (os.environ.get("XIAOFAN_ENGINE") or "").strip().lower() == "official"
