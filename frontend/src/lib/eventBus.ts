/**
 * eventBus.ts —— 极简事件总线
 *
 * ChatModelAdapter 在 assistant-ui runtime 内部跑，拿不到 React 状态；
 * 工具卡片 / 人工审核 / 思考状态等"消息正文之外"的事件通过这里广播，
 * 由独立的 React 组件订阅渲染（ToolCard / ReviewDialog / 思考指示器）。
 */
import { useSyncExternalStore } from "react";

export interface ToolEvent {
  id: string;
  name: string;
  args?: string;
  status: "running" | "done";
  preview?: string;
}

export interface InterruptEvent {
  id: string;
  tool: string;
  args: unknown;
  question?: string;
}

type Handler = (data: never) => void;

class EventBus {
  private handlers = new Map<string, Set<Handler>>();
  private state: Record<string, unknown> = {};   // 各频道最新值（供 useSyncExternalStore）

  on(ch: string, h: Handler): () => void {
    if (!this.handlers.has(ch)) this.handlers.set(ch, new Set());
    this.handlers.get(ch)!.add(h);
    return () => this.handlers.get(ch)?.delete(h);
  }

  emit(ch: string, data: unknown): void {
    this.state[ch] = data;
    this.handlers.get(ch)?.forEach((h) => h(data as never));
  }

  get(ch: string): unknown {
    return this.state[ch];
  }
}

export const eventBus = new EventBus();

/** React hook：订阅某频道最新值 */
export function useEvent<T>(ch: string): T | undefined {
  return useSyncExternalStore(
    (cb) => eventBus.on(ch, () => cb()),
    () => eventBus.get(ch) as T | undefined,
  );
}
