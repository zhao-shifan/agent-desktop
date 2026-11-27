import { Component, type ErrorInfo, type ReactNode } from "react";
import type { IDockviewPanelProps } from "dockview-react";
import type { PreviewSpec } from "../../types/workbench";
import { extOf } from "../../lib/preview";
import { DocxPreview } from "./DocxPreview";
import { PptxPreview } from "./PptxPreview";
import { PdfPreview } from "./PdfPreview";
import { ImagePreview } from "./ImagePreview";
import { SheetPreview } from "./SheetPreview";
import { DiffPreview } from "./DiffPreview";
import { TerminalPreview } from "./TerminalPreview";
import { TextPreview } from "./TextPreview";
import { AlertIcon } from "../Icons";

type PanelParams = { preview?: PreviewSpec };

class PreviewErrorBoundary extends Component<
  { children: ReactNode; title: string },
  { error: string | null }
> {
  state = { error: null as string | null };

  static getDerivedStateFromError(error: unknown) {
    return { error: error instanceof Error ? error.message : String(error) };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[workbench] preview crashed", this.props.title, error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="wb-preview-state is-error">
          <span className="wb-preview-state-icon">
            <AlertIcon size={22} />
          </span>
          <p>预览组件异常：{this.state.error}</p>
          <button
            type="button"
            className="wb-btn wb-btn--ghost"
            onClick={() => this.setState({ error: null })}
          >
            重试渲染
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export function PreviewPanel({ params }: IDockviewPanelProps<PanelParams>) {
  const spec = params?.preview;
  if (!spec) {
    return (
      <div className="wb-preview-panel wb-preview-state">
        <p>没有可用的预览参数</p>
      </div>
    );
  }

  let body: ReactNode;
  switch (spec.kind) {
    case "docx":
      body = spec.file ? <DocxPreview file={spec.file} /> : null;
      break;
    case "pptx":
      body = spec.file ? <PptxPreview file={spec.file} /> : null;
      break;
    case "pdf":
      body = spec.file ? <PdfPreview file={spec.file} /> : null;
      break;
    case "image":
      body = spec.file ? <ImagePreview file={spec.file} /> : null;
      break;
    case "sheet":
      body = spec.file ? <SheetPreview file={spec.file} /> : null;
      break;
    case "diff":
      body = <DiffPreview spec={spec} file={spec.file} />;
      break;
    case "terminal":
      body = <TerminalPreview terminal={spec.terminal} />;
      break;
    case "text":
      body = spec.file ? <TextPreview file={spec.file} /> : null;
      break;
    default:
      body = (
        <div className="wb-preview-state">
          <span className="wb-preview-state-icon">
            <AlertIcon size={22} />
          </span>
          <p>暂不支持预览这个文件类型</p>
          <code>{spec.file?.path ?? spec.title}</code>
          <span className="wb-preview-chip">后缀：{extOf(spec.file?.path ?? spec.title) || "无"}</span>
        </div>
      );
  }

  return (
    <div className="wb-preview-panel">
      <PreviewErrorBoundary title={spec.title}>{body}</PreviewErrorBoundary>
    </div>
  );
}
