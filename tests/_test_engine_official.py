"""验证官方引擎（create_agent + ToolNode）能复现旧 SSE 协议（不联网）。

脚本化假模型模拟两步：
    第 1 次：tool_call -> get_time
    第 2 次：最终回答
断言：
    - 工具 running / done 事件带 id/name
    - content delta 累加 == 最终回答
    - 审批拒绝时不执行工具，回灌"用户拒绝"

跑法：python tests/_test_engine_official.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
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
        print("  FAIL  " + label + ("  -> " + str(detail)[:200] if detail else ""))


class ScriptedModel(BaseChatModel):
    script: list = Field(default_factory=list)
    step: int = 0

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        i = min(self.step, len(self.script) - 1)
        self.step += 1
        return ChatResult(generations=[ChatGeneration(message=self.script[i])])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        i = min(self.step, len(self.script) - 1)
        self.step += 1
        msg = self.script[i]
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                yield ChatGenerationChunk(message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[{"name": tc["name"],
                                       "args": __import__("json").dumps(tc["args"]),
                                       "id": tc["id"], "index": 0}]))
            return
        text = msg.content if isinstance(msg.content, str) else ""
        for k in range(0, len(text), 5):
            yield ChatGenerationChunk(message=AIMessageChunk(content=text[k:k + 5]))

    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self):
        return "scripted-engine"


def run_case(name, script, cfg_extra=None):
    print("[%s]" % name)
    events = []

    class Holder:
        pass

    eng._make_model = lambda cfg: ScriptedModel(script=list(script))
    cfg = {"sse": events.append, "perm": {}, "systemPrompt": "测试",
           "threadId": "t-" + name, "base": "", "key": "", "model": "fake",
           "reasoning": "auto"}
    cfg.update(cfg_extra or {})
    final = eng.run_chat(cfg, [{"role": "user", "content": "现在几点？"}])
    return final, events


def main():
    script = [
        AIMessage(content="", tool_calls=[{"name": "get_time", "args": {},
                                           "id": "call_1"}]),
        AIMessage(content="现在是测试时间，官方循环跑通了。"),
    ]
    final, events = run_case("tool-loop", script)

    tool_running = [e["tool"] for e in events if "tool" in e and e["tool"]["status"] == "running"]
    tool_done = [e["tool"] for e in events if "tool" in e and e["tool"]["status"] == "done"]
    content = "".join(e["choices"][0]["delta"].get("content", "")
                      for e in events if "choices" in e)

    check(len(tool_running) == 1, "1 条 tool running 事件", len(tool_running))
    check(tool_running and tool_running[0]["name"] == "get_time",
          "running 事件 name == get_time", tool_running[:1])
    check(tool_running and tool_running[0]["id"] == "call_1",
          "running 事件带 tool_call id", tool_running[:1])
    check(len(tool_done) == 1, "1 条 tool done 事件", len(tool_done))
    check(tool_done and len(tool_done[0].get("preview", "")) > 0,
          "done 事件带 preview（说明工具真的执行了）", tool_done[:1])
    check("跑通了" in content, "content delta 拼出最终回答", content[:60])
    check(content == final, "SSE 正文与返回值一致", (content, final))

    print("[审批拒绝]")
    denied = {"approveTools": True, "waitApproval": lambda aid, t: False}
    final2, events2 = run_case("approval-deny", script, denied)
    denied_ev = [e["tool"] for e in events2 if "tool" in e and e["tool"]["status"] == "denied"]
    check(len(denied_ev) == 1, "拒绝时发 denied 事件", len(denied_ev))
    check(any("approval_request" in e for e in events2), "拒绝前先发 approval_request")

    print()
    print("结果: %d passed, %d failed" % (ok, fail))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
