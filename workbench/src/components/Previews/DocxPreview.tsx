import { useEffect, useRef, useState } from "react";
import { renderAsync } from "docx-preview";
import type { PreviewFile } from "../../types/workbench";
import { formatBytes } from "../../lib/preview";
import { useBinaryResource } from "../../lib/useResource";
import { PreviewError, PreviewLoading, PreviewToolbar } from "./PreviewParts";

type FileShape = "docx" | "html" | "ole" | "rtf" | "unknown";

/** docx = ZIP(PK)；旧页兜底生成的 .doc 其实是 HTML；老 .doc 是 OLE2(D0CF11E0) */
function sniffShape(buffer: ArrayBuffer): FileShape {
  const bytes = new Uint8Array(buffer.slice(0, 8));
  if (bytes[0] === 0x50 && bytes[1] === 0x4b) return "docx";
  if (bytes[0] === 0xd0 && bytes[1] === 0xcf && bytes[2] === 0x11 && bytes[3] === 0xe0) return "ole";
  const head = new TextDecoder("utf-8", { fatal: false })
    .decode(buffer.slice(0, 1024))
    .replace(/^\uFEFF/, "")
    .trimStart()
    .toLowerCase();
  if (head.startsWith("{\\rtf")) return "rtf";
  if (head.startsWith("<!doctype html") || head.startsWith("<html") || head.startsWith("<")) {
    return "html";
  }
  return "unknown";
}

/** 旧页 .doc 兜底是整页 HTML：去掉脚本和外链，只保留排版，避免污染工作台样式 */
function sanitizeWordHtml(html: string): string {
  const doc = new DOMParser().parseFromString(html, "text/html");
  doc
    .querySelectorAll("script,link,meta,title,iframe,object,embed,base,form,input,button")
    .forEach((element) => element.remove());
  doc.querySelectorAll("*").forEach((element) => {
    for (const attribute of Array.from(element.attributes)) {
      if (/^on/i.test(attribute.name)) element.removeAttribute(attribute.name);
      if (
        (attribute.name === "href" || attribute.name === "src") &&
        /^\s*javascript:/i.test(attribute.value)
      ) {
        element.removeAttribute(attribute.name);
      }
    }
  });
  return doc.body.innerHTML;
}

function htmlToText(html: string): string {
  const doc = new DOMParser().parseFromString(html, "text/html");
  return (doc.body.textContent || "").replace(/\n{3,}/g, "\n\n").trim();
}

export function DocxPreview({ file }: { file: PreviewFile }) {
  const url = file.url || file.path;
  const resource = useBinaryResource(url);
  const containerRef = useRef<HTMLDivElement>(null);
  const [shape, setShape] = useState<FileShape>("unknown");
  const [renderState, setRenderState] = useState<"idle" | "rendering" | "ready" | "error">("idle");
  const [renderError, setRenderError] = useState("");
  const [notice, setNotice] = useState("");
  const [fallbackText, setFallbackText] = useState("");

  useEffect(() => {
    if (resource.status !== "ready" || !containerRef.current) return;
    let cancelled = false;
    const container = containerRef.current;
    container.innerHTML = "";
    container.classList.remove("is-html");
    setRenderState("rendering");
    setRenderError("");
    setNotice("");
    setFallbackText("");

    const buffer = resource.data;
    const detected = sniffShape(buffer);
    setShape(detected);

    const finish = () => {
      if (!cancelled) setRenderState("ready");
    };
    const fail = (error: unknown) => {
      if (cancelled) return;
      setRenderState("error");
      setRenderError(error instanceof Error ? error.message : String(error));
    };

    if (detected === "html") {
      const text = new TextDecoder("utf-8", { fatal: false }).decode(buffer).replace(/^\uFEFF/, "");
      container.classList.add("is-html");
      container.innerHTML = sanitizeWordHtml(text);
      setNotice("这是网页版 Word（.doc），已按网页排版渲染");
      finish();
      return () => {
        cancelled = true;
        container.innerHTML = "";
      };
    }

    if (detected === "ole" || detected === "rtf" || detected === "unknown") {
      setRenderState("error");
      setRenderError(
        detected === "ole"
          ? "这是二进制 .doc（OLE2），浏览器里无法直接排版渲染；下载后用 Word/WPS 打开即可。"
          : "无法识别这个 Word 文件的真实格式，可能是扩展名和内容不一致。",
      );
      return () => {
        cancelled = true;
      };
    }

    // 真 docx：先上 docx-preview（保排版），失败再退回 mammoth 的 HTML
    renderAsync(buffer, container, undefined, {
      inWrapper: true,
      breakPages: true,
      ignoreWidth: false,
      ignoreHeight: false,
      ignoreFonts: false,
      renderHeaders: true,
      renderFooters: true,
      renderFootnotes: true,
      renderEndnotes: true,
      useBase64URL: true,
      renderChanges: false,
      renderComments: false,
    })
      .then(() => {
        if (!cancelled) setRenderState("ready");
      })
      .catch(async (error: unknown) => {
        if (cancelled) return;
        console.warn("[workbench] docx-preview failed, fallback to mammoth", error);
        try {
          const mammoth = await import("mammoth/mammoth.browser");
          const result = await mammoth.convertToHtml({ arrayBuffer: buffer });
          if (cancelled) return;
          container.classList.add("is-html");
          container.innerHTML = sanitizeWordHtml(result.value || "");
          setNotice("docx-preview 排版失败，已用 mammoth 渲染为简化 HTML");
          setFallbackText(htmlToText(result.value || "").slice(0, 200000));
          setRenderState("ready");
        } catch (fallbackError) {
          fail(fallbackError instanceof Error ? fallbackError : error);
        }
      });

    return () => {
      cancelled = true;
      container.innerHTML = "";
    };
  }, [resource.status, resource.data]);

  return (
    <div className="wb-preview wb-docx-preview">
      <PreviewToolbar>
        <span className="wb-preview-file">
          <span className="wb-preview-ext">{shape === "html" ? "DOC" : "DOCX"}</span>
          {file.name}
        </span>
        <span className="wb-preview-meta">{formatBytes(file.size)}</span>
        <span className="wb-preview-spacer" />
        {notice ? <span className="wb-preview-chip">{notice}</span> : null}
        {renderState === "rendering" ? <span className="wb-preview-chip">渲染中…</span> : null}
        {url ? (
          <a className="wb-btn wb-btn--ghost" href={url} download={file.name} target="_blank" rel="noreferrer">
            下载原文件
          </a>
        ) : null}
        <button type="button" className="wb-btn wb-btn--ghost" onClick={resource.reload}>
          重新加载
        </button>
      </PreviewToolbar>
      <div className="wb-preview-stage wb-docx-stage">
        {resource.status === "loading" ? <PreviewLoading label="正在读取 Word 文件…" /> : null}
        {resource.status === "error" ? (
          <PreviewError message={`Word 文件读取失败：${resource.error}`} onRetry={resource.reload} />
        ) : null}
        {renderState === "error" ? (
          <PreviewError message={renderError} onRetry={resource.reload} />
        ) : null}
        {fallbackText && renderState === "ready" ? (
          <details className="wb-docx-raw">
            <summary>查看纯文本</summary>
            <pre>{fallbackText}</pre>
          </details>
        ) : null}
        <div ref={containerRef} className="wb-docx-holder" />
      </div>
    </div>
  );
}
