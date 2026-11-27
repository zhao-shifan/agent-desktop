import { useCallback, useEffect, useRef, useState } from "react";import { Document, Page, pdfjs } from "react-pdf";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import type { PreviewFile } from "../../types/workbench";
import { formatBytes } from "../../lib/preview";
import { useBinaryResource } from "../../lib/useResource";
import { PreviewError, PreviewLoading, PreviewToolbar } from "./PreviewParts";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect) setWidth(Math.floor(rect.width));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

const PDF_OPTIONS = {
  isEvalSupported: false,
};

export function PdfPreview({ file }: { file: PreviewFile }) {
  const url = file.url || file.path;
  const resource = useBinaryResource(url);
  const [numPages, setNumPages] = useState(0);
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [containerRef, width] = useWidth<HTMLDivElement>();

  const data = resource.status === "ready" ? resource.data : null;

  useEffect(() => {
    setPage(1);
    setNumPages(0);
  }, [data]);

  const onLoadSuccess = useCallback(({ numPages: total }: { numPages: number }) => {
    setNumPages(total);
    setPage((current) => Math.min(Math.max(current, 1), total));
  }, []);

  const baseWidth = Math.max(260, Math.min(width - 56, 1080));
  const pageWidth = Math.round(baseWidth * zoom);

  return (
    <div className="wb-preview wb-pdf-preview">
      <PreviewToolbar>
        <span className="wb-preview-file">
          <span className="wb-preview-ext">PDF</span>
          {file.name}
        </span>
        <span className="wb-preview-meta">{formatBytes(file.size)}</span>
        <span className="wb-preview-spacer" />
        <div className="wb-pager">
          <button
            type="button"
            className="wb-icon-btn"
            disabled={page <= 1 || !numPages}
            onClick={() => setPage((value) => Math.max(1, value - 1))}
            title="上一页"
          >
            ‹
          </button>
          <span>
            {numPages ? `${page} / ${numPages}` : "—"}
          </span>
          <button
            type="button"
            className="wb-icon-btn"
            disabled={!numPages || page >= numPages}
            onClick={() => setPage((value) => Math.min(numPages, value + 1))}
            title="下一页"
          >
            ›
          </button>
        </div>
        <div className="wb-zoom">
          <button
            type="button"
            className="wb-icon-btn"
            onClick={() => setZoom((value) => Math.max(0.55, Number((value - 0.1).toFixed(2))))}
            title="缩小"
          >
            −
          </button>
          <span>{Math.round(zoom * 100)}%</span>
          <button
            type="button"
            className="wb-icon-btn"
            onClick={() => setZoom((value) => Math.min(2.4, Number((value + 0.1).toFixed(2))))}
            title="放大"
          >
            +
          </button>
        </div>
      </PreviewToolbar>
      <div className="wb-preview-stage wb-pdf-stage" ref={containerRef}>
        {resource.status === "loading" ? <PreviewLoading label="正在读取 PDF…" /> : null}
        {resource.status === "error" ? (
          <PreviewError message={`PDF 读取失败：${resource.error}`} onRetry={resource.reload} />
        ) : null}
        {data ? (
          <Document
            file={data}
            options={PDF_OPTIONS}
            onLoadSuccess={onLoadSuccess}
            onLoadError={(error) => console.warn("[workbench] pdf load error", error)}
            loading={<PreviewLoading label="正在解析 PDF…" />}
            error={<PreviewError message="PDF 解析失败，文件可能已损坏" onRetry={resource.reload} />}
          >
            {width > 0 ? (
              <Page
                pageNumber={page}
                width={pageWidth}
                renderTextLayer={false}
                renderAnnotationLayer={false}
                loading={<PreviewLoading label="正在渲染页面…" />}
              />
            ) : null}
          </Document>
        ) : null}
      </div>
    </div>
  );
}
