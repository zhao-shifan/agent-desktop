import type { PreviewSpec, TreeNode } from "../types/workbench";
import { useWorkbench } from "../store/workbench";
import { legacyConfig } from "./legacy";
import { previewFromFile } from "./preview";
import {
  closeAllTabs,
  closeTab,
  getDockLayout,
  openDiff,
  openFileNode,
  openPreview,
  openTerminal,
  resetLayout,
  restoreDockLayout,
} from "./dockController";
import { requestNewSession, requestOpenSession } from "./chatBridge";

export interface WorkbenchGlobalApi {
  version: string;
  openFile: (file: {
    path: string;
    name?: string;
    url?: string;
    size?: number;
    mime?: string;
  }) => string | null;
  openPreview: (spec: PreviewSpec) => string;
  openNode: (node: TreeNode) => string | null;
  openTerminal: (options?: { cwd?: string; wsUrl?: string }) => string;
  openDiff: (input: {
    fileName?: string;
    unified?: string;
    oldText?: string;
    newText?: string;
  }) => string;
  closeTab: (panelId: string) => boolean;
  closeAll: () => void;
  resetLayout: () => void;
  getLayout: () => unknown | null;
  restoreLayout: (layout: unknown) => void;
  selectNode: (nodeId: string) => void;
  config: typeof legacyConfig;
  chat: {
    newSession: () => boolean;
    openSession: (sessionId: string) => boolean;
  };
}

declare global {
  interface Window {
    xiaofanWorkbench?: WorkbenchGlobalApi;
  }
}

export function installWorkbenchApi(): void {
  const api: WorkbenchGlobalApi = {
    version: "0.1.0",
    openFile(file) {
      const spec = previewFromFile(file);
      if (!spec) {
        useWorkbench.getState().notify("没有匹配这个后缀的预览组件", "error");
        return null;
      }
      return openPreview(spec);
    },
    openPreview,
    openNode: openFileNode,
    openTerminal,
    openDiff,
    closeTab,
    closeAll: closeAllTabs,
    resetLayout,
    getLayout: getDockLayout,
    restoreLayout: restoreDockLayout,
    selectNode(nodeId) {
      useWorkbench.getState().selectNode(nodeId);
    },
    config: legacyConfig,
    chat: {
      newSession: requestNewSession,
      openSession: requestOpenSession,
    },
  };
  window.xiaofanWorkbench = api;
}

/** 旧 HTML 页面（聊天模板 / Agent 配置 / API 配置）都可以用 postMessage 调工作台 */
export function installLegacyMessageBridge(): () => void {
  const handler = (event: MessageEvent) => {
    if (event.origin !== window.location.origin) return;
    const data = event.data;
    if (!data || typeof data !== "object" || data.__wb !== 1) return;

    if (data.type === "open-file" && data.file && typeof data.file.path === "string") {
      const spec = previewFromFile({
        path: data.file.path,
        name: data.file.name,
        url: data.file.url,
        size: data.file.size,
        mime: data.file.mime,
      });
      if (spec) openPreview(spec);
      return;
    }
    if (data.type === "open-terminal") {
      openTerminal({ cwd: data.cwd, wsUrl: data.wsUrl });
      return;
    }
    if (data.type === "open-diff" && data.diff) {
      openDiff(data.diff);
      return;
    }
    if (data.type === "select-node" && typeof data.id === "string") {
      useWorkbench.getState().selectNode(data.id);
      return;
    }
    if (data.type === "notify" && typeof data.message === "string") {
      useWorkbench.getState().notify(data.message, data.tone || "info");
    }
  };
  window.addEventListener("message", handler);
  return () => window.removeEventListener("message", handler);
}
