/**
 * DocPreview.tsx —— 右侧文档预览面板（docx-preview 渲染 Word）
 * 大屏常驻右栏；移动端以独立弹窗打开，支持双指/按钮缩放。
 */
import { useCallback, useRef, useState } from "react";
import { renderAsync } from "docx-preview";

export function DocPreview({ onClose, className }: { onClose?: () => void; className?: string }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [name, setName] = useState("");

  /** 选择 .docx 并渲染到面板 */
  const onFile = useCallback(async (f: File) => {
    setName(f.name);
    const buf = await f.arrayBuffer();
    const box = boxRef.current;
    if (!box) return;
    box.innerHTML = "";
    await renderAsync(buf, box, undefined, {
      className: "docx", inWrapper: true, ignoreWidth: false,
      useBase64URL: true,   // 图片内联 base64，本地预览无外链问题
    });
  }, []);

  return (
    <div className={`flex flex-col h-full bg-zinc-50 dark:bg-zinc-900 border-l border-zinc-200
                     dark:border-zinc-800 ${className ?? ""}`}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-200
                      dark:border-zinc-800">
        <span className="font-semibold text-sm text-zinc-900 dark:text-zinc-100 truncate">
          📄 {name || "文档预览"}
        </span>
        <div className="flex items-center gap-2">
          {/* 移动端缩放按钮 */}
          <button onClick={() => setScale((s) => Math.max(0.5, +(s - 0.1).toFixed(2)))}
                  className="sm:hidden w-7 h-7 rounded border border-zinc-300 dark:border-zinc-700 text-zinc-600">−</button>
          <button onClick={() => setScale((s) => Math.min(2, +(s + 0.1).toFixed(2)))}
                  className="sm:hidden w-7 h-7 rounded border border-zinc-300 dark:border-zinc-700 text-zinc-600">＋</button>
          {onClose && (
            <button onClick={onClose} className="lg:hidden text-zinc-500 text-xl leading-none">✕</button>
          )}
        </div>
      </div>

      <div className="p-3">
        <label className="block cursor-pointer rounded-lg border border-dashed border-zinc-300
                          dark:border-zinc-700 p-3 text-center text-xs text-zinc-500 hover:border-emerald-500">
          选择 .docx 文件预览
          <input type="file" accept=".docx" className="hidden"
                 onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
        </label>
      </div>

      {/* 渲染区：transform 缩放，overflow 防横向滚动 */}
      <div className="flex-1 overflow-auto px-3 pb-3">
        <div ref={boxRef}
             style={{ transform: `scale(${scale})`, transformOrigin: "top left" }}
             className="origin-top-left [&_.docx-wrapper]:bg-transparent
                        [&_.docx-wrapper]:p-0 text-sm" />
      </div>
    </div>
  );
}
