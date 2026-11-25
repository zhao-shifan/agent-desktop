/**
 * settings.ts —— 侧边栏配置的持久化（localStorage）
 * API Key 只存本机浏览器，不随代码入库。
 */
import { newSessionId, type ChatConfig } from "./backend";

const KEY = "xiaofan-frontend-settings";

export interface Session {
  id: string;
  title: string;
  createdAt: number;
}

export interface Settings extends ChatConfig {
  sessions: Session[];
  activeSessionId: string;
}

export const DEFAULT_SETTINGS: Settings = {
  baseUrl: "https://open.bigmodel.cn/api/paas/v4",
  apiKey: "",
  model: "glm-4-flash",
  temperature: 0.7,
  reasoning: "auto",
  sessionId: newSessionId(),
  tools: true,
  skills: false,
  sessions: [],
  activeSessionId: "",
};

export function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) } as Settings;
  } catch { /* 损坏则重置 */ }
  return DEFAULT_SETTINGS;
}

export function saveSettings(s: Settings): void {
  localStorage.setItem(KEY, JSON.stringify(s));
}
