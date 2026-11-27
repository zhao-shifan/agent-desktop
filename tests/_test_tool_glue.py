"""验证统一胶水层（wrap_tool_call）对自研工具 / LangChain 工具 / 异常 的行为一致。

覆盖：
1. 自研工具：tool_running → tool_done，带 preview 和 files 字段
2. LangChain 工具（dict 返回）：返回值被归一化成文本 + preview
3. LangChain 工具（落盘文件）：files 里带可预览路径
4. 异常：done 带错误 preview、trace 记录、模型拿到错误文本继续作答（官方 ToolErrorMiddleware）

跑法：python tests/_test_tool_glue.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import StructuredTool
from pydantic import Field

import agent_engine_official as eng

ok = 0
fail = 0


def check(cond, label, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print("  PASS  " + label)
    else:
        fail += 1
        print("  FAIL  " + label + ("  -> " + str(detail)[:220] if detail else ""))


class ScriptedModel(BaseChatModel):
    script: list = Field(default_factory=list)
    step: int = 0
    seen_messages: list = Field(default_factory=list)

    def _pick(self, messages):
        self.seen_messages.append(list(messages))
        i = min(self.step, len(self.script) - 1)
        self.step += 1
        return self.script[i]

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=self._pick(messages))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        msg = self._pick(messages)
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=[{
                    "name": tc["name"], "args": __import__("json").dumps(tc["args"]),
                    "id": tc["id"], "index": 0}]))
            return
        text = msg.content if isinstance(msg.content, str) else ""
        for k in range(0, len(text), 6):
            yield ChatGenerationChunk(message=AIMessageChunk(content=text[k:k + 6]))

    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self):
        return "scripted-glue"


def call_tool(name, args, final="完成"):
    script = [AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "call_1"}]),
              AIMessage(content=final)]
    events = []
    eng._make_model = lambda cfg: ScriptedModel(script=script)
    cfg = {"sse": events.append, "perm": {}, "systemPrompt": "测试",
           "threadId": "glue-%d" % time.time_ns(), "base": "", "key": "", "model": "fake",
           "reasoning": "auto"}
    final_text = eng.run_chat(cfg, [{"role": "user", "content": "测试"}])
    return final_text, events


def done_event(events):
    for e in events:
        if "tool" in e and e["tool"].get("status") == "done":
            return e["tool"]
    return None


def main():
    print("[1] 自研工具 get_time")
    final, events = call_tool("get_time", {})
    running = [e["tool"] for e in events if "tool" in e and e["tool"]["status"] == "running"]
    done = done_event(events)
    check(len(running) == 1 and running[0]["origin"] == "builtin",
          "running 事件带 origin=builtin", running[:1])
    check(done is not None and done.get("preview"), "done 带 preview", done)
    check(done is not None and "files" in done, "done 带 files 字段（前端契约）", done)

    print("[2] LangChain 工具 lc_word_count（返回 dict）")
    final, events = call_tool("lc_word_count", {"text": "你好 世界 hello"})
    done = done_event(events)
    check(done is not None and done.get("origin") == "langchain",
          "origin=langchain", done)
    check(done is not None and "chars" in str(done.get("preview")),
          "dict 返回值进入 preview", done)
    check("完成" in final, "工具后继续给出最终回答", final)

    print("[3] LangChain 工具 lc_summary_doc（落盘文件）")
    final, events = call_tool("lc_summary_doc", {"title": "glue测试", "points": "要点一"})
    done = done_event(events)
    files = (done or {}).get("files") or []
    check(len(files) == 1, "files 提取到 1 个文件", files)
    if files:
        check(files[0]["ext"] == "md", "ext=md", files[0])
        check(files[0]["path"].endswith(".md"), "path 以 .md 结尾", files[0]["path"])
        exists = os.path.exists(files[0]["path"])
        check(exists, "文件真的落盘（前端预览可直接读）", files[0]["path"])

    print("[4] 工具异常：统一格式化 + 继续对话")
    def boom(x: str = ""):
        raise ValueError("故意失败")
    bad_tool = StructuredTool.from_function(func=boom, name="boom_tool",
                                            description="测试异常")
    events = []
    model = ScriptedModel(script=[
        AIMessage(content="", tool_calls=[{"name": "boom_tool", "args": {}, "id": "c9"}]),
        AIMessage(content="工具失败了，我换个办法回答。")])
    eng._make_model = lambda cfg: model
    sse = events.append
    ms = eng._make_middlewares({"perm": {}, "sse": sse}, sse)
    from langchain.agents import create_agent
    agent = create_agent(model=model, tools=[bad_tool], system_prompt="t", middleware=ms)
    for chunk, meta in agent.stream({"messages": [{"role": "user", "content": "测试异常"}]},
                                    {"configurable": {"thread_id": "glue-err-%d" % time.time_ns()}},
                                    stream_mode="messages"):
        pass
    done = done_event(events)
    check(done is not None and "工具执行失败" in str(done.get("preview")),
          "done 带错误 preview", done)
    err_seen = any("工具执行失败" in str(getattr(m, "content", ""))
                   for batch in model.seen_messages for m in batch)
    check(err_seen, "模型收到错误文本（错误回填，不会中断整轮）")

    print()
    print("结果: %d passed, %d failed" % (ok, fail))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
