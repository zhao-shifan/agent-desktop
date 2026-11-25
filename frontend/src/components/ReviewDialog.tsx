/**
 * ReviewDialog.tsx —— 人工审核 interrupt 弹窗（阶段3预留）
 * 后端发出 interrupt 事件时弹出：确认 / 拒绝 → POST /api/resume 续跑 LangGraph。
 * 移动端全屏展示（max-sm:inset-0），桌面居中卡片。
 */
import { useState } from "react";
import { useEvent, type InterruptEvent } from "../lib/eventBus";
import { API_BASE } from "../lib/backend";

export function ReviewDialog() {
  const cur = useEvent<InterruptEvent>("interrupt");
  const [busy, setBusy] = useState(false);

  if (!cur) return null;

  async function decide(approved: boolean) {
    setBusy(true);
    try {
      await fetch(`${API_BASE}/api/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ interruptId: cur!.id, approved }),
      });
    } finally {
      setBusy(false);
      // 清空以关闭弹窗
      window.dispatchEvent(new CustomEvent("xiaofan-interrupt-done"));
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center
                    bg-black/50 p-0 sm:p-4">
      <div className="w-full sm:max-w-md bg-white dark:bg-zinc-900 rounded-t-2xl sm:rounded-2xl
                      shadow-2xl p-5 space-y-4">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
          🔐 需要你的确认
        </h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-300">
          小凡想执行工具 <span className="font-mono font-medium">{cur.tool}</span>，
          {cur.question ?? "请确认是否允许。"}
        </p>
        <pre className="max-h-40 overflow-auto rounded-lg bg-zinc-100 dark:bg-zinc-800
                        p-3 text-xs whitespace-pre-wrap text-zinc-700 dark:text-zinc-300">
          {JSON.stringify(cur.args, null, 2)}
        </pre>
        <div className="flex gap-3">
          <button disabled={busy} onClick={() => decide(true)}
                  className="flex-1 rounded-lg bg-emerald-600 text-white py-2.5 text-sm
                             hover:bg-emerald-700 disabled:opacity-50">
            ✅ 确认执行
          </button>
          <button disabled={busy} onClick={() => decide(false)}
                  className="flex-1 rounded-lg bg-zinc-200 dark:bg-zinc-700 text-zinc-800
                             dark:text-zinc-200 py-2.5 text-sm hover:opacity-80 disabled:opacity-50">
            ❌ 拒绝
          </button>
        </div>
      </div>
    </div>
  );
}
