/**
 * 工作台 ⇄ 旧聊天页 iframe 的薄桥。
 * 只传命令和会话摘要，不复制、不重写旧页的 sendMsg / SSE / 分支逻辑。
 */
import type { SessionMeta } from "../types/workbench";

type ChatMessage = {
  __wb: 1;
  source: "chat";
  type: "state";
  sessions: Array<{
    id: string;
    title?: string;
    pinned?: boolean;
    messages?: number;
    updatedAt?: number;
  }>;
  activeId?: string | null;
};

type ChatCommand =
  | { type: "ping" | "refresh" | "newSession" }
  | { type: "openSession"; id: string }
  | { type: "renameSession"; id: string; title: string }
  | { type: "deleteSession"; id: string }
  | { type: "reorderSessions"; ids: string[] }
  | { type: "openSettings" }
  | { type: "openThemes" }
  | { type: "openSkills" }
  | { type: "openMcpManager" }
  | { type: "openQR" };

let frame: HTMLIFrameElement | null = null;
let ready = false;
let bridgeActiveId: string | null = null;
let subscriber: (() => void) | null = null;

function notify(): void {
  subscriber?.();
}

export function setChatFrame(element: HTMLIFrameElement | null): void {
  frame = element;
  if (!element) {
    ready = false;
    bridgeActiveId = null;
  }
  notify();
}

export function markChatFrameLoaded(): void {
  ready = true;
  sendChat({ type: "ping" });
  notify();
}

export function setBridgeActiveId(id: string | null): void {
  if (bridgeActiveId === id) return;
  bridgeActiveId = id;
  notify();
}

export function getBridgeActiveId(): string | null {
  return bridgeActiveId;
}

export function isChatReady(): boolean {
  return ready;
}

export function sendChat(command: ChatCommand): boolean {
  const target = frame?.contentWindow;
  if (!target) return false;
  target.postMessage({ __wb: 1, ...command }, window.location.origin);
  return true;
}

export function requestNewSession(): boolean {
  return sendChat({ type: "newSession" });
}

export function requestOpenSession(id: string): boolean {
  return sendChat({ type: "openSession", id });
}

export function requestRenameSession(id: string, title: string): boolean {
  return sendChat({ type: "renameSession", id, title });
}

export function requestDeleteSession(id: string): boolean {
  return sendChat({ type: "deleteSession", id });
}

export function requestReorderSessions(ids: string[]): boolean {
  return sendChat({ type: "reorderSessions", ids });
}

export function parseChatMessage(data: unknown): {
  sessions: SessionMeta[];
  activeId: string | null;
} | null {
  if (!data || typeof data !== "object") return null;
  const message = data as Partial<ChatMessage>;
  if (message.__wb !== 1 || message.source !== "chat" || message.type !== "state") return null;
  if (!Array.isArray(message.sessions)) return null;
  const sessions = message.sessions
    .filter((item) => item && typeof item.id === "string")
    .map<SessionMeta>((item) => ({
      id: item.id,
      title: item.title || "新对话",
      workspaceId: "",
      pinned: Boolean(item.pinned),
      messages: Number(item.messages) || 0,
      updatedAt: Number(item.updatedAt) || 0,
      source: "legacy",
    }));
  return {
    sessions,
    activeId: typeof message.activeId === "string" ? message.activeId : null,
  };
}

/** 旧页生成文件时推来的消息 */
export interface ChatFileMessage {
  chatId: string | null;
  id: string;
  name: string;
  ext: string;
  size?: number;
  blob: Blob | null;
  dbg?: string;
}

export function parseChatFileMessage(data: unknown): ChatFileMessage | null {
  if (!data || typeof data !== "object") return null;
  const message = data as {
    __wb?: number;
    source?: string;
    type?: string;
    chatId?: unknown;
    dbg?: unknown;
    file?: {
      id?: unknown;
      name?: unknown;
      ext?: unknown;
      size?: unknown;
      blob?: unknown;
    };
  };
  if (message.__wb !== 1 || message.source !== "chat" || message.type !== "file") return null;
  const file = message.file;
  if (!file || typeof file.name !== "string" || !file.name) return null;
  return {
    chatId: typeof message.chatId === "string" ? message.chatId : null,
    id: typeof file.id === "string" && file.id ? file.id : file.name,
    name: file.name,
    ext: typeof file.ext === "string" ? file.ext : "",
    size: typeof file.size === "number" ? file.size : undefined,
    blob: file.blob instanceof Blob ? file.blob : null,
    dbg: typeof message.dbg === "string" ? message.dbg : undefined,
  };
}

/** 聊天卡片上的「在右侧打开」 */
export function parseOpenFileMessage(data: unknown): { fileId: string } | null {
  if (!data || typeof data !== "object") return null;
  const message = data as { __wb?: number; source?: string; type?: string; fileId?: unknown };
  if (message.__wb !== 1 || message.source !== "chat" || message.type !== "open-file") return null;
  if (typeof message.fileId !== "string" || !message.fileId) return null;
  return { fileId: message.fileId };
}

export function subscribeChatBridge(listener: () => void): () => void {
  subscriber = listener;
  return () => {
    if (subscriber === listener) subscriber = null;
  };
}
