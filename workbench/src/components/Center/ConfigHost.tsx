import { useCallback, useEffect, useRef, useState } from "react";
import type { LegacyPageKey, TreeNode } from "../../types/workbench";
import { legacyConfig } from "../../lib/legacy";
import { openLegacyOverlay } from "../../lib/legacyActions";
import { useWorkbench } from "../../store/workbench";
import { PreviewLoading } from "../Previews/PreviewParts";
import { LegacyMissing } from "./LegacyMissing";
import { useLegacyAvailability } from "./useLegacyAvailability";

export function ConfigHost({
  page,
  node,
}: {
  page: Extract<LegacyPageKey, "agent" | "api">;
  node: TreeNode | null;
}) {
  const url = node?.legacyUrl || (page === "agent" ? legacyConfig.agent : legacyConfig.api);
  const { status, recheck } = useLegacyAvailability(url, page);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [loaded, setLoaded] = useState(false);

  const sendContext = useCallback(() => {
    const frame = iframeRef.current;
    if (!frame?.contentWindow) return;
    const state = useWorkbench.getState();
    const workspace = state.workspaces.find((item) => item.id === state.activeWorkspaceId);
    frame.contentWindow.postMessage(
      {
        __wb: 1,
        type: "context",
        page,
        node: node
          ? {
              id: node.id,
              name: node.name,
              kind: node.kind,
              legacyPage: node.legacyPage,
              legacyUrl: node.legacyUrl,
              path: node.path,
            }
          : null,
        workspace: workspace ? { id: workspace.id, name: workspace.name } : null,
        theme: "dark",
      },
      window.location.origin,
    );
  }, [node, page]);

  useEffect(() => {
    if (loaded) sendContext();
  }, [loaded, sendContext]);

  const handleLoad = useCallback(() => {
    setLoaded(true);
    useWorkbench.getState().setLegacyStatus(page, "ready");
    sendContext();
  }, [page, sendContext]);

  const setRef = useCallback((element: HTMLIFrameElement | null) => {
    iframeRef.current = element;
    if (!element) setLoaded(false);
  }, []);

  if (status === "missing") {
    return (
      <LegacyMissing
        page={page}
        url={url}
        onRecheck={recheck}
        onOpenOldSettings={page === "api" ? () => openLegacyOverlay("openSettings") : undefined}
      />
    );
  }

  if (status === "checking") {
    return (
      <div className="wb-legacy-loading">
        <PreviewLoading label={`正在检测 ${page === "agent" ? "Agent" : "API"} 配置页…`} />
      </div>
    );
  }

  return (
    <div className="wb-legacy-host">
      <iframe
        ref={setRef}
        className="wb-legacy-frame"
        src={url}
        title={page === "agent" ? "Agent 配置" : "API 配置"}
        allow="clipboard-read; clipboard-write"
        onLoad={handleLoad}
      />
      {!loaded ? (
        <div className="wb-legacy-loading is-overlay">
          <PreviewLoading label="正在载入配置…" />
        </div>
      ) : null}
    </div>
  );
}
