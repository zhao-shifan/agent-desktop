/**
 * Sidebar.tsx —— 左侧栏：会话列表 / 技能开关 / MCP 管理 / 模型选择 / API Key 配置
 * 移动端以抽屉（Drawer）形式弹出，大屏常驻。
 */
import { useEffect, useState } from "react";
import type { Settings, Session } from "../lib/settings";
import { newSessionId } from "../lib/backend";

const MODELS = ["glm-4-flash", "glm-4.5-flash", "glm-4-plus", "deepseek-chat", "deepseek-reasoner"];

interface Props {
  settings: Settings;
  update: (patch: Partial<Settings>) => void;
  onClose?: () => void;          // 移动端抽屉关闭
  className?: string;
}

export function Sidebar({ settings, update, onClose, className }: Props) {
  const [tab, setTab] = useState<"sessions" | "mcp" | "config">("sessions");
  const [mcp, setMcp] = useState<Record<string, string[]> | null>(null);

  // MCP 服务列表：GET /api/mcp（后端已有接口）
  useEffect(() => {
    if (tab !== "mcp" || mcp) return;
    fetch("/api/mcp").then((r) => r.json())
      .then((d) => setMcp(d?.servers ?? d ?? {}))
      .catch(() => setMcp({}));
  }, [tab, mcp]);

  function newSession() {
    const s: Session = { id: newSessionId(), title: `会话 ${settings.sessions.length + 1}`, createdAt: Date.now() };
    update({ sessions: [s, ...settings.sessions], activeSessionId: s.id, sessionId: s.id });
    onClose?.();
  }

  function switchSession(id: string) {
    update({ activeSessionId: id, sessionId: id });
    onClose?.();
  }

  return (
    <aside className={`flex flex-col h-full w-72 shrink-0 border-r border-zinc-200 dark:border-zinc-800
                      bg-zinc-50 dark:bg-zinc-900 ${className ?? ""}`}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-200 dark:border-zinc-800">
        <span className="font-semibold text-zinc-900 dark:text-zinc-100">小凡智能体</span>
        {onClose && (
          <button onClick={onClose} className="lg:hidden text-zinc-500 text-xl leading-none">✕</button>
        )}
      </div>

      {/* Tab 切换 */}
      <div className="flex text-sm border-b border-zinc-200 dark:border-zinc-800">
        {([["sessions", "会话"], ["mcp", "MCP"], ["config", "配置"]] as const).map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)}
                  className={`flex-1 py-2 ${tab === k
                    ? "border-b-2 border-emerald-600 text-emerald-600 font-medium"
                    : "text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"}`}>
            {label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2 text-sm">
        {/* ---- 会话列表 ---- */}
        {tab === "sessions" && (
          <>
            <button onClick={newSession}
                    className="w-full rounded-lg bg-emerald-600 text-white py-2 hover:bg-emerald-700">
              ＋ 新会话
            </button>
            {settings.sessions.map((s) => (
              <button key={s.id} onClick={() => switchSession(s.id)}
                      className={`w-full text-left truncate rounded-lg px-3 py-2 ${
                        settings.activeSessionId === s.id
                          ? "bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300"
                          : "hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-700 dark:text-zinc-300"}`}>
                {s.title}
              </button>
            ))}
            <label className="flex items-center gap-2 pt-3 text-zinc-600 dark:text-zinc-300">
              <input type="checkbox" checked={settings.skills}
                     onChange={(e) => update({ skills: e.target.checked })} />
              技能包
            </label>
            <label className="flex items-center gap-2 text-zinc-600 dark:text-zinc-300">
              <input type="checkbox" checked={settings.tools}
                     onChange={(e) => update({ tools: e.target.checked })} />
              工具调用
            </label>
          </>
        )}

        {/* ---- MCP 服务管理 ---- */}
        {tab === "mcp" && (
          mcp === null ? <p className="text-zinc-400">加载中…</p> :
            Object.keys(mcp).length === 0
              ? <p className="text-zinc-400">未配置 MCP 服务（后端 mcp_config.json）</p>
              : Object.entries(mcp).map(([srv, tools]) => (
                <div key={srv} className="rounded-lg bg-zinc-100 dark:bg-zinc-800 p-2">
                  <p className="font-medium text-zinc-700 dark:text-zinc-200">🔌 {srv}</p>
                  <p className="text-xs text-zinc-500 mt-1">{tools.join("、") || "（无工具）"}</p>
                </div>
              ))
        )}

        {/* ---- 模型 / Key 配置 ---- */}
        {tab === "config" && (
          <div className="space-y-3">
            <label className="block">
              <span className="text-zinc-500 text-xs">API 地址（OpenAI 兼容）</span>
              <input value={settings.baseUrl} onChange={(e) => update({ baseUrl: e.target.value })}
                     className="mt-1 w-full rounded-lg border border-zinc-300 dark:border-zinc-700
                                bg-transparent px-2 py-1.5 text-zinc-800 dark:text-zinc-200" />
            </label>
            <label className="block">
              <span className="text-zinc-500 text-xs">API Key（仅存本机浏览器）</span>
              <input type="password" value={settings.apiKey}
                     onChange={(e) => update({ apiKey: e.target.value })}
                     className="mt-1 w-full rounded-lg border border-zinc-300 dark:border-zinc-700
                                bg-transparent px-2 py-1.5 text-zinc-800 dark:text-zinc-200" />
            </label>
            <label className="block">
              <span className="text-zinc-500 text-xs">模型</span>
              <select value={settings.model} onChange={(e) => update({ model: e.target.value })}
                      className="mt-1 w-full rounded-lg border border-zinc-300 dark:border-zinc-700
                                 bg-transparent px-2 py-1.5 text-zinc-800 dark:text-zinc-200">
                {MODELS.map((m) => <option key={m}>{m}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-zinc-500 text-xs">推理深度</span>
              <select value={settings.reasoning} onChange={(e) => update({ reasoning: e.target.value })}
                      className="mt-1 w-full rounded-lg border border-zinc-300 dark:border-zinc-700
                                 bg-transparent px-2 py-1.5 text-zinc-800 dark:text-zinc-200">
                {["auto", "off", "low", "medium", "high"].map((r) => <option key={r}>{r}</option>)}
              </select>
            </label>
          </div>
        )}
      </div>
    </aside>
  );
}
