import { useEffect } from "react";
import { useWorkbench } from "../store/workbench";
import { AlertIcon, CloseIcon } from "./Icons";

export function ConfirmDialog() {
  const confirm = useWorkbench((state) => state.confirm);
  const confirmPending = useWorkbench((state) => state.confirmPending);
  const cancelConfirm = useWorkbench((state) => state.cancelConfirm);

  useEffect(() => {
    if (!confirm) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") cancelConfirm();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [confirm, cancelConfirm]);

  if (!confirm) return null;

  return (
    <div
      className="wb-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) cancelConfirm();
      }}
    >
      <div className="wb-confirm" role="dialog" aria-modal="true" aria-labelledby="wb-confirm-title">
        <div className="wb-confirm-head">
          <span className="wb-confirm-icon">
            <AlertIcon size={17} />
          </span>
          <span className="wb-confirm-kicker">PLEASE CONFIRM</span>
          <button type="button" className="wb-icon-btn" title="关闭" onClick={cancelConfirm}>
            <CloseIcon size={14} />
          </button>
        </div>
        <h3 id="wb-confirm-title">{confirm.title}</h3>
        <p>{confirm.message}</p>
        <div className="wb-confirm-actions">
          <button type="button" className="wb-btn wb-btn--ghost" onClick={cancelConfirm} autoFocus>
            取消
          </button>
          <button type="button" className="wb-btn wb-btn--danger" onClick={confirmPending}>
            {confirm.label}
          </button>
        </div>
      </div>
    </div>
  );
}
