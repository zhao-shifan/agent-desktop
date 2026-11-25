/**
 * adapter.ts —— assistant-ui ChatModelAdapter（对接小凡 LangGraph 后端）
 *
 * 官方 LocalRuntime 路径：默认请求逻辑全部删除，run() 里自己调后端。
 *
 * 实现要点：SSE 事件在回调里到达，而 yield 只能在 generator 里发生，
 * 所以用一条**异步队列**桥接：streamChat 把事件推进队列，
 * run() 的 for-await 循环逐个取出，每收到一个 token 就 yield 全量已累计文本
 * （assistant-ui 的 yield 是"更新 content part"语义 → 自动打字机效果）。
 * 工具卡片 / 人工审核 / 思考进度不属于消息正文，经 eventBus 广播给独立组件。
 */
import type { ChatModelAdapter } from "@assistant-ui/react";
import { streamChat, type ChatConfig } from "./backend";
import { eventBus } from "./eventBus";

/** 最小异步队列：回调生产 → generator 消费 */
function makeQueue<T>() {
  const items: T[] = [];
  const waiters: ((v: IteratorResult<T>) => void)[] = [];
  let done = false;
  return {
    push(v: T) {
      const w = waiters.shift();
      if (w) w({ value: v, done: false });
      else items.push(v);
    },
    end() {
      done = true;
      while (waiters.length) waiters.shift()!({ value: undefined, done: true });
    },
    [Symbol.asyncIterator](): AsyncIterator<T> {
      return {
        next(): Promise<IteratorResult<T>> {
          if (items.length) return Promise.resolve({ value: items.shift()!, done: false });
          if (done) return Promise.resolve({ value: undefined, done: true });
          return new Promise((res) => waiters.push(res));
        },
      };
    },
  };
}

export function makeAdapter(cfg: () => ChatConfig): ChatModelAdapter {
  return {
    async *run({ messages, abortSignal }) {
      // ---- 1) assistant-ui 消息 → 后端 OpenAI dict 格式 ----
      // 后端入口会自动注入小凡人设，前端只传对话历史
      const oai = messages
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => ({
          role: m.role as string,
          content: m.content
            .filter((p): p is { type: "text"; text: string } => p.type === "text")
            .map((p) => p.text)
            .join("\n"),
        }));

      // ---- 2) 回调事件 → 队列；token 类型用 {delta} 标记 ----
      const q = makeQueue<{ delta?: string; reasoningDelta?: string }>();
      let errText: string | undefined;

      const pending = streamChat(
        cfg(),
        oai,
        (ev) => {
          const e = ev as Record<string, unknown>;
          if ("choices" in e) {
            const d = (e.choices as { delta: { content?: string; reasoning_content?: string } }[])[0].delta;
            if (d.content) q.push({ delta: d.content });
            if (d.reasoning_content) {
              q.push({ reasoningDelta: d.reasoning_content });
            }
          } else if ("tool" in e) {
            eventBus.emit("tool", e.tool);
          } else if ("interrupt" in e) {
            eventBus.emit("interrupt", e.interrupt);
          } else if ("thinking" in e) {
            eventBus.emit("thinking", (e.thinking as { elapsed: number }).elapsed);
          }
        },
        abortSignal,
      )
        .catch((e) => { errText = String(e); })
        .finally(() => q.end());

      // ---- 3) 消费队列：token → yield 更新（打字机）；思考流 → bus 折叠条 ----
      let text = "";
      let reasoning = "";
      for await (const item of q) {
        if (item.delta) {
          text += item.delta;
          yield { content: [{ type: "text", text }] };
        }
        if (item.reasoningDelta) {
          reasoning += item.reasoningDelta;
          eventBus.emit("reasoning", reasoning);
        }
      }
      await pending;

      // ---- 4) 结束状态：出错时让 assistant-ui 显示错误 ----
      if (errText) {
        yield {
          content: [{ type: "text", text: text || `请求失败：${errText}` }],
          status: { type: "incomplete", reason: "error" },
        } as never;
      }
    },
  };
}
