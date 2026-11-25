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
            max_tokens=cfg.get("maxTokens"),
            timeout=300,
            extra_body=extra,
        ).bind_tools(tools_layer.TOOL_DEFS)

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

        # 恢复层保护缓冲：正文若以 ``` 或 { 开头（疑似漏发工具 JSON），先扣住不转发，
        # 确认不是工具 JSON 再流出去 —— 打字机效果与恢复层洁净度兼得
        held = {"buf": ""}

        def _flush(force=False):
            if force or not re.match(r"\s*(```|\{)", held["buf"]):
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
                _flush(force=True)
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
                rname, rargs, rclean = rec
                tc = {"id": "rec-%d" % int(time.time() * 1000), "type": "function",
                      "function": {"name": rname, "arguments": json.dumps(rargs, ensure_ascii=False)}}
                print(f"[恢复层] 模型漏发 tool_call，框架已补执行：{rname}({json.dumps(rargs)[:80]})", flush=True)
                sse({"tool": {"id": tc["id"], "name": rname,
                              "args": tc["function"]["arguments"], "status": "running"}})
                try:
                    rres = tools_layer.run_tool(tc, perm)
                except Exception as e:
                    rres = f"工具执行失败：{e}"
                sse({"tool": {"id": tc["id"], "name": rname,
                              "status": "done", "preview": str(rres)[:400]}})
                # JSON 正文被 held 缓冲扣住了没流出去 → 清洗后的文字由 finalize 补流
                return {"messages": msgs + [
                            {"role": "assistant", "content": str(rclean).strip(), "tool_calls": [tc]},
                            {"role": "tool", "tool_call_id": tc["id"],
                             "content": str(rres)[:MAX_CHARS]},
                        ],
                        "rounds": rounds + 1, "final_text": "", "streamed": False}
            # 正常最终回答：token 已经实时流出，不再重复切片
            return {"messages": msgs + [oai], "rounds": rounds + 1,
                    "final_text": str(final_text), "pending_tools": [], "streamed": True}

        # ---- 有 tool_calls：正文已实时流出，暂存工具调用交给 exec_tools ----
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

        def _run_one(tc):
            fn = tc.get("function") or {}
            t0 = time.time()
            result = tools_layer.run_tool(tc, perm)
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

        for tc, name, result in pairs:
            sse({"tool": {"id": tc.get("id"), "name": name,
                          "args": (tc.get("function") or {}).get("arguments") or "",
                          "status": "running"}})
            sse({"tool": {"id": tc.get("id"), "name": name,
                          "status": "done", "preview": str(result)[:400]}})
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
_CHECKPOINTER = MemorySaver()


def _extract_memory_async(cfg, user_text, answer):
    """异步记忆抽取（mem0 同思路）：后台跑，失败静默。实际实现复用 server.py 的。"""
    try:
        from server import _extract_memory_async as _impl
        _impl(cfg["base"], cfg["key"], cfg["model"], user_text, answer)
    except Exception:
        pass


def run_chat(cfg, messages):
    """入口：编译图并执行。SSE 已由节点内回调发出；本函数阻塞到对话结束。

    LangSmith 全链路追踪：设置环境变量即自动生效（langchain 原生支持，零代码）：
        LANGSMITH_TRACING=true
        LANGSMITH_API_KEY=lsv2_...      # smith.langchain.com 免费注册
        LANGSMITH_PROJECT=xiaofan-agent # 可选，默认 project
    """
    graph = build_graph(cfg)
    thread_id = str(cfg.get("threadId") or "default")
    final = graph.invoke(
        {"messages": list(messages)},
        config={
            "configurable": {"thread_id": thread_id},   # 断点续跑/恢复的会话标识
            "recursion_limit": (MAX_ROUNDS + 4) * 4,    # 防死循环兜底
        })
    return final.get("final_text", "")
