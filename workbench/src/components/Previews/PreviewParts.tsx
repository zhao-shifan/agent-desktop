import type { ReactNode } from "react";
import { AlertIcon, RefreshIcon } from "../Icons";

export function PreviewLoading({ label = "正在加载…" }: { label?: string }) {
  return (
    <div className="wb-preview-state">
      <div className="wb-preview-spinner" />
      <p>{label}</p>
    </div>
  );
}

export function PreviewError({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="wb-preview-state is-error">
      <span className="wb-preview-state-icon">
        <AlertIcon size={22} />
      </span>
      <p>{message}</p>
      {onRetry ? (
        <button type="button" className="wb-btn wb-btn--ghost" onClick={onRetry}>
          <RefreshIcon size={13} /> 重试
        </button>
      ) : null}
    </div>
  );
}

export function PreviewToolbar({ children }: { children: ReactNode }) {
  return <div className="wb-preview-toolbar">{children}</div>;
}
