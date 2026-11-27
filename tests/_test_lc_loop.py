"""验证「LangChain 官方智能体循环」能在本项目的工具上跑通（不联网、不调真模型）。

用脚本化的假模型模拟两步：
    第 1 次：模型发 tool_call -> get_time
    第 2 次：模型拿到工具结果后给出最终回答
然后交给 langchain.agents.create_agent 跑，断言官方 ToolNode 真的执行了我们的
StructuredTool 并把结果回灌（即循环是官方的，不是手写的）。

跑法：python tests/_test_lc_loop.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from agent_lc_tools import build_lc_tools

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


class ScriptedChatModel(BaseChatModel):
    """按脚本顺序吐消息的假模型；bind_tools 直接返回自己。"""

    script: list = Field(default_factory=list)
    step: int = 0
    seen: list = Field(default_factory=list)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        i = min(self.step, len(self.script) - 1)
        self.step += 1
        return ChatResult(generations=[ChatGeneration(message=self.script[i])])

    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self):
        return "scripted"


def main():
    from langchain.agents import create_agent

    model = ScriptedChatModel(script=[
        AIMessage(content="", tool_calls=[{"name": "get_time", "args": {},
                                           "id": "call_time_1"}]),
        AIMessage(content="现在是测试时间，循环跑通了。"),
    ])

    tools = build_lc_tools(perm={"workDir": "", "allowCommand": False})
    agent = create_agent(model=model, tools=tools, system_prompt="你是测试助手。")

    print("[1] 图结构是官方的 agent 循环")
    nodes = sorted(agent.get_graph().nodes.keys())
    print("      nodes =", nodes)
    check(any("tools" in n for n in nodes), "存在官方 ToolNode 节点", nodes)

    print("[2] 跑一轮完整循环（tool_call -> 执行 -> 回灌 -> 最终回答）")
    out = agent.invoke({"messages": [{"role": "user", "content": "现在几点？"}]})
    msgs = out["messages"]

    tool_msgs = [m for m in msgs if getattr(m, "type", "") == "tool"]
    check(len(tool_msgs) == 1, "产生了 1 条 ToolMessage", len(tool_msgs))
    if tool_msgs:
        tm = tool_msgs[0]
        check(tm.name == "get_time", "ToolMessage.name == get_time", tm.name)
        check(isinstance(tm.content, str) and len(tm.content) > 0,
              "工具结果非空（说明真的执行了 tools_layer.run_tool）",
              str(tm.content)[:80])
        print("      tool content =", str(tm.content)[:100].replace("\n", " "))

    ai_msgs = [m for m in msgs if getattr(m, "type", "") == "ai"]
    check(len(ai_msgs) >= 2, "至少两条 AI 消息（调用 + 回答）", len(ai_msgs))
    check("循环跑通了" in str(msgs[-1].content), "最终回答来自第二次模型调用",
          str(msgs[-1].content)[:80])

    print("[3] 模型被调用两次（说明不是一次性的假循环）")
    check(model.step == 2, "模型调用次数 == 2", model.step)

    print()
    print("结果: %d passed, %d failed" % (ok, fail))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
