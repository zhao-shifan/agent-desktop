import { lazy, Suspense, useMemo } from "react";
import type { PreviewFile } from "../../types/workbench";
import { formatBytes } from "../../lib/preview";
import { useBinaryResource } from "../../lib/useResource";
import { PreviewError, PreviewLoading, PreviewToolbar } from "./PreviewParts";

const PptxViewer = lazy(() => import("./PptxViewerImpl"));

export function PptxPreview({ file }: { file: PreviewFile }) {
  const url = file.url || file.path;
  const resource = useBinaryResource(url);
  const bytes = useMemo(
    () => (resource.status === "ready" ? new Uint8Array(resource.data) : null),
    [resource.status, resource.data],
  );

  return (
    <div className="wb-preview wb-pptx-preview">
      <PreviewToolbar>
        <span className="wb-preview-file">
          <span className="wb-preview-ext">PPTX</span>
          {file.name}
        </span>
        <span className="wb-preview-meta">{formatBytes(file.size)}</span>
        <span className="wb-preview-spacer" />
        <span className="wb-preview-chip">只读 · 无工具栏</span>
        <button type="button" className="wb-btn wb-btn--ghost" onClick={resource.reload}>
          重新加载
        </button>
      </PreviewToolbar>
      <div className="wb-preview-stage wb-pptx-stage">
        {resource.status === "loading" ? <PreviewLoading label="正在解析演示文稿…" /> : null}
        {resource.status === "error" ? (
          <PreviewError message={`PPTX 文件读取失败：${resource.error}`} onRetry={resource.reload} />
        ) : null}
        {bytes ? (
          <Suspense fallback={<PreviewLoading label="正在加载 PowerPoint 渲染器…" />}>
            <PptxViewer bytes={bytes} fileName={file.name} />
          </Suspense>
        ) : null}
      </div>
    </div>
  );
}
