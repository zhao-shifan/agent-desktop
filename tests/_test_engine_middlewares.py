"""验证官方引擎的 6 个 middleware 是否真的生效（全部离线，用脚本化假模型）。

覆盖：
1. Presearch      时效预搜索注入
2. Recovery       恢复层（正文里的工具 JSON → 补成 tool_call）
3. Heartbeat      思考心跳
4. RoundLimit     超轮收尾（摘工具 + 要求总结）
5. Followups      追问建议
6. Trim           trim_messages 替换手写裁剪

跑法：python tests/_test_engine_middlewares.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field

import tools_layer
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
    seen_tools: list = Field(default_factory=list)
    delay: float = 0.0

    def _pick(self, messages):
        self.seen_messages.append(list(messages))
        if getattr(self, "no_tools", False):
            return AIMessage(content="已到工具上限，基于现有信息总结完毕。")
        i = min(self.step, len(self.script) - 1)
        self.step += 1
        if self.delay:
            time.sleep(self.delay)
        return self.script[i]

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=self._pick(messages))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        msg = self._pick(messages)
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                yield ChatGenerationChunk(message=AIMessageChunk(
                    content="", tool_call_chunks=[{
                        "name": tc["name"], "args": __import__("json").dumps(tc["args"]),
                        "id": tc["id"], "index": 0}]))
            return
        text = msg.content if isinstance(msg.content, str) else ""
        for k in range(0, len(text), 6):
            yield ChatGenerationChunk(message=AIMessageChunk(content=text[k:k + 6]))

    def bind_tools(self, tools, **kwargs):
        self.seen_tools.append(list(tools or []))
        if not tools:
            self.no_tools = True
        return self

    @property
    def _llm_type(self):
        return "scripted-mw"


def run(script, prompt, extra=None, delay=0.0, model_box=None):
    events = []
    model = ScriptedModel(script=list(script), delay=delay)
    if model_box is not None:
        model_box.append(model)
    eng._make_model = lambda cfg: model
    cfg = {"sse": events.append, "perm": {}, "systemPrompt": "测试",
           "threadId": "mw-%d" % time.time_ns(), "base": "", "key": "", "model": "fake",
           "reasoning": "auto"}
    cfg.update(extra or {})
    final = eng.run_chat(cfg, [{"role": "user", "content": prompt}])
    return final, events, model


def content_of(events):
    return "".join(((e.get("choices") or [{}])[0].get("delta", {}) or {}).get("content", "")
                   for e in events if "choices" in e)


def main():
    # ---------------- 1. 预搜索
    print("[1] Presearch 时效预搜索")
    calls = []
    orig_search = tools_layer.web_search
    tools_layer.web_search = lambda q, count=5, key="": (calls.append(q) or "搜索结果：小凡 2026 新闻")
    try:
        script = [AIMessage(content="根据搜索结果，2026 年有这些新闻 [1]。")]
        final, events, model = run(script, "最新的新闻有哪些？")
    finally:
        tools_layer.web_search = orig_search
    check(len(calls) == 1, "触发了一次 web_search", calls)
    injected = any("搜索结果" in str(getattr(m, "content", "")) for m in model.seen_messages[-1])
    check(injected, "搜索结果已注入模型上下文")

    # ---------------- 2. 恢复层
    print("[2] Recovery 恢复层")
    script = [AIMessage(content='{"name":"get_time","arguments":{}}'),
              AIMessage(content="时间已拿到，回答完成。")]
    final, events, model = run(script, "现在几点")
    tool_running = [e["tool"] for e in events if "tool" in e and e["tool"]["status"] == "running"]
    check(len(tool_running) == 1 and tool_running[0]["name"] == "get_time",
          "正文工具 JSON 被补执行", tool_running[:1])
    check("{" not in content_of(events), "裸 JSON 没有泄漏给前端", content_of(events)[:80])
    check("回答完成" in content_of(events), "工具执行后继续给出最终回答", content_of(events)[:80])

    # ---------------- 3. 思考心跳
    print("[3] Heartbeat 思考心跳")
    script = [AIMessage(content="慢回答")]
    final, events, model = run(script, "慢慢来", delay=7.0)
    thinking = [e["thinking"] for e in events if "thinking" in e]
    check(len(thinking) >= 1, "超过 6s 发出 thinking 事件", thinking[:3])
    check(any(t.get("elapsed", 0) >= 6 for t in thinking), "elapsed >= 6", thinking[:3])

    # ---------------- 4. 超轮收尾
    print("[4] RoundLimit 超轮收尾")
    loop_script = [AIMessage(content="", tool_calls=[{"name": "get_time", "args": {}, "id": "c%d" % i}])
                   for i in range(8)]
    final, events, model = run(loop_script, "无限调工具")
    empty_bind = [t for t in model.seen_tools if not t]
    check(len(empty_bind) >= 1, "达到上限后最后几次模型调用不带工具",
          [len(t) for t in model.seen_tools])
    instr = any("不能再调工具" in str(getattr(m, "content", "")) for m in model.seen_messages[-1])
    check(instr, "注入了'不能再调工具，请总结'指令")

    # ---------------- 5. 追问建议
    print("[5] Followups 追问建议")
    import agent_graph
    orig_fu = agent_graph._gen_followups

    def fake_fu(cfg, text):
        cfg["sse"]({"suggestions": [{"title": "继续", "label": "继续问", "prompt": "继续"}]})
    agent_graph._gen_followups = fake_fu
    try:
        script = [AIMessage(content="回答完毕。")]
        final, events, model = run(script, "你好", extra={"followups": True})
    finally:
        agent_graph._gen_followups = orig_fu
    check(any("suggestions" in e for e in events), "输出 suggestions 事件")

    # ---------------- 6. 裁剪
    print("[6] Trim trim_messages")
    big = "x" * 1000
    history = []
    for i in range(200):
        history.append({"role": "user" if i % 2 == 0 else "assistant", "content": big})
    history.append({"role": "user", "content": "最后的问题"})
    events = []
    model = ScriptedModel(script=[AIMessage(content="收到")])
    eng._make_model = lambda cfg: model
    cfg = {"sse": events.append, "perm": {}, "systemPrompt": "测试",
           "threadId": "mw-trim-%d" % time.time_ns(), "base": "", "key": "", "model": "fake",
           "reasoning": "auto"}
    eng.run_chat(cfg, history)
    seen = len(model.seen_messages[-1]) if model.seen_messages else 0
    check(seen < 200, "超预算历史被裁剪（模型只看到 %d 条）" % seen, seen)

    print()
    print("结果: %d passed, %d failed" % (ok, fail))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
