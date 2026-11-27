import type { LegacyConfig } from "../types/workbench";

const defaults: LegacyConfig = {
  chat: "/legacy/chat.html",
  agent: "/legacy/agent-config.html",
  api: "/legacy/api-config.html",
  samplesBase: "/samples",
  terminalWs: "",
};

function pick(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

export const legacyConfig: LegacyConfig = (() => {
  const raw = typeof window !== "undefined" ? window.__WORKBENCH_CONFIG__ ?? {} : {};
  return {
    chat: pick(raw.chat, defaults.chat),
    agent: pick(raw.agent, defaults.agent),
    api: pick(raw.api, defaults.api),
    samplesBase: pick(raw.samplesBase, defaults.samplesBase),
    terminalWs: typeof raw.terminalWs === "string" ? raw.terminalWs : defaults.terminalWs,
  };
})();

export function legacyUrl(page: "chat" | "agent" | "api"): string {
  return legacyConfig[page];
}

function looksLikeWorkbenchShell(html: string): boolean {
  return (
    html.includes('<div id="root">') &&
    (html.includes("/src/main.tsx") || /\/assets\/index-[^"]+\.js/.test(html))
  );
}

/**
 * 探测旧 HTML 是否存在。
 * - 工作台自己生成/复制的旧页会带 <meta name="workbench-legacy">；
 * - 如果返回的是工作台自己的 SPA index（Vite fallback），视为不存在，避免 iframe 套娃。
 */
export async function probeLegacyPage(url: string): Promise<"ready" | "missing"> {
  try {
    const response = await fetch(url, {
      cache: "no-store",
      headers: { Accept: "text/html" },
    });
    if (!response.ok) return "missing";
    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.includes("text/html")) return "missing";
    const html = await response.text();
    if (html.includes('name="workbench-legacy"')) return "ready";
    if (looksLikeWorkbenchShell(html)) return "missing";
    return "ready";
  } catch {
    return "missing";
  }
}

export function openInNewWindow(url: string): void {
  window.open(url, "_blank", "noopener,noreferrer");
}
