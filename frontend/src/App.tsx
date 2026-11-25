/**
 * App.tsx —— 三栏布局入口
 *
 * 大屏（lg+）：左 会话/配置侧边栏 | 中 对话区 | 右 文档预览
 * 移动端：只显示中间对话区；左侧栏 → 抽屉弹窗；右预览 → 独立弹窗
 */
import { useMemo, useState } from "react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { ThreadView } from "./components/ThreadView";
import { makeAdapter } from "./lib/adapter";
import { loadSettings, saveSettings, type Settings } from "./lib/settings";
import { Sidebar } from "./components/Sidebar";
import { DocPreview } from "./components/DocPreview";
import { ToolCards, ReasoningBar } from "./components/ToolCards";
import { ReviewDialog } from "./components/ReviewDialog";

export default function App() {
  const [settings, setSettings] = useState<Settings>(loadSettings);
  const [drawerOpen, setDrawerOpen] = useState(false);   // 移动端左侧抽屉
  const [docModal, setDocModal] = useState(false);       // 移动端右侧弹窗

  const update = (patch: Partial<Settings>) => {
    setSettings((s) => { const n = { ...s, ...patch }; saveSettings(n); return n; });
  };

  // runtime 每次对话读最新配置（用 ref 式闭包而非重新 mount）
  const runtime = useLocalRuntime(makeAdapter(() => settings));

  const threadTitle = useMemo(
    () => settings.sessions.find((s) => s.id === settings.activeSessionId)?.title ?? "新对话",
    [settings.sessions, settings.activeSessionId]);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className="flex h-dvh w-full overflow-hidden bg-white dark:bg-zinc-950
                      text-zinc-900 dark:text-zinc-100">

        {/* ---- 左：大屏常驻侧边栏 ---- */}
        <Sidebar settings={settings} update={update} className="hidden lg:flex" />

        {/* ---- 左：移动端抽屉 ---- */}
        {drawerOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="absolute inset-0 bg-black/50" onClick={() => setDrawerOpen(false)} />
            <Sidebar settings={settings} update={update}
                     onClose={() => setDrawerOpen(false)}
                     className="absolute left-0 top-0 w-72 max-w-[80vw] shadow-2xl" />
          </div>
        )}

        {/* ---- 中：对话主区域 ---- */}
        <main className="flex flex-1 flex-col min-w-0">
          {/* 顶栏 */}
          <header className="flex items-center gap-2 border-b border-zinc-200 dark:border-zinc-800
                             px-3 py-2.5">
            <button onClick={() => setDrawerOpen(true)}
                    className="lg:hidden text-xl text-zinc-600 dark:text-zinc-300">☰</button>
            <span className="font-medium truncate">{threadTitle}</span>
            <span className="ml-auto text-xs text-zinc-400 hidden sm:inline">{settings.model}</span>
            <button onClick={() => setDocModal(true)}
                    className="lg:hidden text-sm text-emerald-600">📄 预览</button>
          </header>

          {/* 流式消息 + 工具卡片 + 思考条 */}
          <div className="flex-1 min-h-0">
            <ThreadView />
          </div>
          <ReasoningBar />
          <ToolCards />
        </main>

        {/* ---- 右：大屏常驻文档预览 ---- */}
        <DocPreview className="hidden lg:flex w-96 shrink-0" />

        {/* ---- 右：移动端独立弹窗 ---- */}
        {docModal && (
          <div className="fixed inset-0 z-40 lg:hidden bg-black/50"
               onClick={() => setDocModal(false)}>
            <div className="absolute inset-x-2 inset-y-10 bg-white dark:bg-zinc-900 rounded-2xl
                            overflow-hidden shadow-2xl"
                 onClick={(e) => e.stopPropagation()}>
              <DocPreview onClose={() => setDocModal(false)} className="h-full" />
            </div>
          </div>
        )}

        {/* 人工审核 interrupt 弹窗（阶段3后端就绪后启用） */}
        <ReviewDialog />
      </div>
    </AssistantRuntimeProvider>
  );
}
