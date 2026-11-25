/**
 * backend.ts —— 唯一的后端对接层
 *
 * assistant-ui 自带的请求逻辑已全部弃用，本项目通过 ChatModelAdapter
 * （见 adapter.ts）调用这里的 streamChat()，直接对接小凡自研 LangGraph 后端的
 * 自定义 SSE 协议。接口地址/超时全部走环境变量（见 .env.example）。
 */

// ---- 环境变量（不要硬编码）----
export const API_BASE = import.meta.env.VITE_API_BASE ?? "";      // 空串 = 走 Vite 代理
export const API_TIMEOUT = Number(import.meta.env.VITE_API_TIMEOUT ?? 300000); // 5 分钟

/** 单次对话请求的配置（来自侧边栏设置，持久化在 localStorage） */
export interface ChatConfig {
  baseUrl: string;       // OpenAI 兼容上游地址（如 bigmodel / deepseek）
  apiKey: string;
  model: string;
  temperature?: number;
  reasoning?: string;    // auto / off / low / medium / high
  sessionId: string;     // 会话标识 → 后端 LangGraph thread_id（断点/检查点）
  tools: boolean;        // 是否启用工具
  skills: boolean;       // 技能包开关（占位，随 sessionId 传给后端）
}

/** 后端 SSE 事件（与小凡 LangGraph 协议一一对应） */
export type BackendEvent =
  | { choices: [{ delta: { content?: string; reasoning_content?: string } }] }  // token 流/思考流
  | { tool: { id: string; name: string; args?: string; status: "running" | "done"; preview?: string } }
  | { thinking: { elapsed: number } }                                            // 心跳
  | { interrupt: { id: string; tool: string; args: unknown; question?: string } } // 人工审核（阶段3）
  | { error: string };

/**
 * 发起一轮对话，逐事件回调。
 * 采用 fetch + ReadableStream 手动解析 SSE（后端是 chunked data: 行协议）。
 */
export async function streamChat(
  cfg: ChatConfig,
  messages: { role: string; content: string }[],
  onEvent: (ev: BackendEvent) => void,
  abortSignal?: AbortSignal,
): Promise<void> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), API_TIMEOUT);
  // 用户点停止时同时中止网络请求
  abortSignal?.addEventListener("abort", () => ctrl.abort(), { once: true });

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: ctrl.signal,
      body: JSON.stringify({
        baseUrl: cfg.baseUrl,
        apiKey: cfg.apiKey,
        model: cfg.model,
        temperature: cfg.temperature,
        reasoning: cfg.reasoning,
        sessionId: cfg.sessionId,   // → 后端 thread_id
        tools: cfg.tools,
        skills: cfg.skills,
        perm: { allowCommand: false },
        messages,
      }),
    });
    if (!res.ok || !res.body) {
      throw new Error(`后端返回 ${res.status}: ${await res.text().catch(() => "")}`);
    }

    // ---- 手动解析 SSE：按行切 data: 载荷 ----
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n\n");          // 事件以空行分隔
      buf = lines.pop() ?? "";                  // 最后一段可能不完整，留到下轮
      for (const line of lines) {
        const t = line.trim();
        if (!t.startsWith("data:")) continue;
        const payload = t.slice(5).trim();
        if (!payload || payload === "[DONE]") continue;
        try {
          onEvent(JSON.parse(payload) as BackendEvent);
        } catch { /* 忽略无法解析的行（心跳注释等） */ }
      }
    }
  } finally {
    clearTimeout(timer);
  }
}

/** 会话 ID：每会话一个 uuid，对应后端检查点 thread_id */
export function newSessionId(): string {
  return crypto.randomUUID();
}
