import type { PreviewFile } from "../../types/workbench";
import { formatBytes } from "../../lib/preview";
import { useTextResource } from "../../lib/useResource";
import { PreviewError, PreviewLoading, PreviewToolbar } from "./PreviewParts";

export function TextPreview({ file }: { file: PreviewFile }) {
  const url = file.url || file.path;
  const resource = useTextResource(url);
  const text = resource.status === "ready" ? resource.data : "";
  const lines = text.split("\n").length;

  return (
    <div className="wb-preview wb-text-preview">
      <PreviewToolbar>
        <span className="wb-preview-file">
          <span className="wb-preview-ext">TEXT</span>
          {file.name}
        </span>
        <span className="wb-preview-meta">
          {[formatBytes(file.size), `${lines} 行`].filter(Boolean).join(" · ")}
        </span>
        <span className="wb-preview-spacer" />
        <button
          type="button"
          className="wb-btn wb-btn--ghost"
          onClick={() => {
            void navigator.clipboard?.writeText(text);
          }}
        >
          复制全文
        </button>
        <button type="button" className="wb-btn wb-btn--ghost" onClick={resource.reload}>
          重新加载
        </button>
      </PreviewToolbar>
      <div className="wb-preview-stage wb-text-stage">
        {resource.status === "loading" ? <PreviewLoading label="正在读取文本…" /> : null}
        {resource.status === "error" ? (
          <PreviewError message={`文本读取失败：${resource.error}`} onRetry={resource.reload} />
        ) : null}
        {resource.status === "ready" ? (
          <div className="wb-text-scroll">
            <div className="wb-text-gutter" aria-hidden>
              {Array.from({ length: lines }, (_, index) => (
                <span key={index}>{index + 1}</span>
              ))}
            </div>
            <pre className="wb-text-code">{text}</pre>
          </div>
        ) : null}
      </div>
    </div>
  );
}
