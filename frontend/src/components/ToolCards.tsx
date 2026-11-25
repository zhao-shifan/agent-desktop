/**
 * ToolCards.tsx —— 工具调用卡片（本次对话实时流）
 * 订阅 eventBus 的 tool 频道；running/done 状态 + 参数/结果预览。
 */
import { useState } from "react";
import { useEvent, type ToolEvent } from "../lib/eventBus";

export function ToolCards() {
  const latest = useEvent<ToolEvent>("tool");
  const [list, setList] = useState<ToolEvent[]>([]);

  // 最新事件并入列表（同 id 覆盖状态）
  const key = latest ? `${latest.id}:${latest.status}` : "";
  const [lastKey, setLastKey] = useState("");
  if (latest && key !== lastKey) {
    setLastKey(key);
    setList((prev) => {
      const i = prev.findIndex((t) => t.id === latest.id);
      if (i >= 0) { const n = [...prev]; n[i] = latest; return n; }
      return [...prev, latest];
    });
  }

  if (!list.length) return null;
  return (
    <div className="mx-2 mb-2 space-y-1.5">
      {list.slice(-4).map((t) => (
        <div key={t.id + t.status}
             className="flex items-center gap-2 rounded-lg border border-zinc-200 dark:border-zinc-700
                        bg-zinc-50 dark:bg-zinc-800/60 px-3 py-1.5 text-xs text-zinc-600 dark:text-zinc-300">
          <span>{t.status === "running" ? "⚙️" : "✅"}</span>
          <span className="font-medium">{t.name}</span>
          {t.args && <span className="truncate opacity-60">{String(t.args).slice(0, 60)}</span>}
          {t.status === "done" && t.preview && (
            <span className="truncate opacity-50" title={t.preview}>→ {String(t.preview).slice(0, 60)}</span>
          )}
        </div>
      ))}
    </div>
  );
}

/** 思考指示条：reasoning 流入时展示"思考中/完毕（点击展开）" */
export function ReasoningBar() {
  const text = useEvent<string>("reasoning");
  const [open, setOpen] = useState(false);
  if (!text) return null;
  return (
    <div className="mx-2 mb-2 rounded-lg bg-zinc-100 dark:bg-zinc-800/60 px-3 py-1.5 text-xs text-zinc-500 dark:text-zinc-400">
      <button className="flex items-center gap-1 w-full text-left"
              onClick={() => setOpen(!open)}>
        <span>{open ? "🔽" : "💭"}</span>
        <span>小凡思考完毕（点击{open ? "收起" : "展开"}）</span>
      </button>
      {open && <pre className="mt-2 whitespace-pre-wrap max-h-48 overflow-auto">{text}</pre>}
    </div>
  );
}
