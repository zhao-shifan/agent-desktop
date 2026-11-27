import { useMemo, useState } from "react";
import { html as renderDiffHtml } from "diff2html";
import type { DiffInput, PreviewFile, PreviewSpec } from "../../types/workbench";
import { createUnifiedDiff, formatBytes } from "../../lib/preview";
import { useTextResource } from "../../lib/useResource";
import { PreviewError, PreviewLoading, PreviewToolbar } from "./PreviewParts";

type DiffMode = "side-by-side" | "line-by-line";

function buildDiff(spec: PreviewSpec, fileText: string): string {
  const diff = spec.diff;
  if (!diff) return fileText;
  if (diff.unified) return diff.unified;
  if (diff.oldText !== undefined && diff.newText !== undefined) {
    return createUnifiedDiff(diff.oldText, diff.newText, diff.fileName || "file.txt");
  }
  return fileText;
}

export function DiffPreview({
  spec,
  file,
}: {
  spec: PreviewSpec;
  file?: PreviewFile;
}) {
  const url = file ? file.url || file.path : undefined;
  const resource = useTextResource(url);
  const [mode, setMode] = useState<DiffMode>("line-by-line");

  const diffText = useMemo(() => {
    const fromFile = resource.status === "ready" ? resource.data : "";
    return buildDiff(spec, fromFile);
  }, [resource.status, resource.data, spec]);

  const renderedResult = useMemo<{ html?: string; error?: string }>(() => {
    if (!diffText.trim()) return {};
    try {
      return {
        html: renderDiffHtml(diffText, {
          drawFileList: false,
          outputFormat: mode,
          matching: "lines",
          diffStyle: "word",
          renderNothingWhenEmpty: false,
        }),
      };
    } catch (error) {
      return { error: error instanceof Error ? error.message : String(error) };
    }
  }, [diffText, mode]);

  const rendered = renderedResult.html;
  const renderError = renderedResult.error ?? "";

  return (
    <div className="wb-preview wb-diff-preview">
      <PreviewToolbar>
        <span className="wb-preview-file">
          <span className="wb-preview-ext">DIFF</span>
          {spec.title}
        </span>
        {file ? <span className="wb-preview-meta">{formatBytes(file.size)}</span> : null}
        <span className="wb-preview-spacer" />
        <div className="wb-segmented">
          <button
            type="button"
            className={mode === "side-by-side" ? "is-active" : ""}
            onClick={() => setMode("side-by-side")}
          >
            并排
          </button>
          <button
            type="button"
            className={mode === "line-by-line" ? "is-active" : ""}
            onClick={() => setMode("line-by-line")}
          >
            统一
          </button>
        </div>
        {file ? (
          <button type="button" className="wb-btn wb-btn--ghost" onClick={resource.reload}>
            重新加载
          </button>
        ) : null}
      </PreviewToolbar>

      <div className="wb-preview-stage wb-diff-stage">
        {resource.status === "loading" ? <PreviewLoading label="正在读取 diff…" /> : null}
        {resource.status === "error" && file ? (
          <PreviewError message={`Diff 读取失败：${resource.error}`} onRetry={resource.reload} />
        ) : null}
        {renderError ? <PreviewError message={`Diff 解析失败：${renderError}`} /> : null}
        {!renderError && rendered && diffText.trim() ? (
          <div
            className={`wb-diff-host is-${mode}`}
            dangerouslySetInnerHTML={{ __html: rendered as string }}
          />
        ) : null}
        {!renderError && !diffText.trim() && resource.status !== "loading" ? (
          <div className="wb-preview-state">
            <p>{file ? "这个 diff 文件是空的" : "两侧内容一致，没有差异"}</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
