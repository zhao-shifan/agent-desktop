import type { DockviewApi } from "dockview-react";
import { useWorkbench } from "../store/workbench";
import type { DiffInput, PreviewSpec, TerminalInput, TreeNode } from "../types/workbench";
import { legacyConfig } from "./legacy";
import { getChatBlobUrl } from "./chatFiles";
import { previewFromNode } from "./preview";

type DockDisposable = { dispose: () => void };

let api: DockviewApi | null = null;
let restoring = false;
let saveTimer: number | null = null;
let counter = 0;
const pending: Array<{ id: string; spec: PreviewSpec }> = [];
const keyToPanel = new Map<string, string>();
const panelToKey = new Map<string, string>();
const disposables: DockDisposable[] = [];

function nextPanelId(): string {
  counter += 1;
  return `wb-panel-${Date.now().toString(36)}-${counter}`;
}

function specKey(spec: PreviewSpec): string {
  if (spec.key) return spec.key;
  if (spec.kind === "terminal") return `terminal:${Date.now().toString(36)}`;
  if (spec.file?.path) return `file:${spec.file.path}`;
  if (spec.kind === "diff") return `diff:${spec.title}:${Date.now().toString(36)}`;
  return `preview:${spec.title}:${Date.now().toString(36)}`;
}

function rebuildIndex(): void {
  keyToPanel.clear();
  panelToKey.clear();
  if (!api) return;
  for (const panel of api.panels) {
    const params = panel.params as { preview?: PreviewSpec } | undefined;
    const spec = params?.preview;
    if (!spec) continue;
    const key = specKey(spec);
    keyToPanel.set(key, panel.id);
    panelToKey.set(panel.id, key);
  }
}

function scheduleSave(): void {
  if (!api || restoring) return;
  if (saveTimer !== null) window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(() => {
    saveTimer = null;
    if (!api) return;
    try {
      useWorkbench.getState().setDockLayout(api.toJSON());
    } catch (error) {
      console.warn("[workbench] dockview serialize failed", error);
    }
  }, 220);
}

function addNow(id: string, spec: PreviewSpec): string {
  if (!api) return id;
  const withKey: PreviewSpec = { ...spec, key: specKey(spec) };

  // 布局恢复、HMR、pending 队列都可能让同一个文件重复进入，这里再按 params.key 兜底去重
  const existing = api.panels.find((panel) => {
    const params = panel.params as { preview?: PreviewSpec } | undefined;
    return params?.preview?.key === withKey.key;
  });
  if (existing) {
    keyToPanel.set(withKey.key!, existing.id);
    panelToKey.set(existing.id, withKey.key!);
    existing.api.setActive();
    useWorkbench.getState().setRightOpen(true);
    return existing.id;
  }

  try {
    api.addPanel({
      id,
      component: "preview",
      title: withKey.title,
      params: { preview: withKey },
    });
    keyToPanel.set(withKey.key!, id);
    panelToKey.set(id, withKey.key!);
    useWorkbench.getState().setRightOpen(true);
  } catch (error) {
    console.warn("[workbench] addPanel failed", error);
    useWorkbench.getState().notify("预览面板创建失败，请展开右侧面板后重试", "error");
  }
  return id;
}

function flushPending(): void {
  if (!api || restoring) return;
  const queued = pending.splice(0, pending.length);
  for (const item of queued) addNow(item.id, item.spec);
}

export function attachDockview(next: DockviewApi): void {
  api = next;
  // 存进 store，聊天消息里的「在右侧打开」、外部脚本都通过它操作 dockview
  useWorkbench.getState().setDockviewApi(next);

  const saved = useWorkbench.getState().dockLayout;
  if (saved) {
    restoring = true;
    try {
      next.fromJSON(saved as Parameters<DockviewApi["fromJSON"]>[0]);
    } catch (error) {
      console.warn("[workbench] dockview layout restore failed", error);
      try {
        next.clear();
      } catch {
        // ignore
      }
      useWorkbench.getState().setDockLayout(null);
    }
    rebuildIndex();
    window.setTimeout(() => {
      restoring = false;
      rebuildIndex();
      flushPending();
      scheduleSave();
    }, 80);
  } else {
    rebuildIndex();
  }

  disposables.push(next.onDidLayoutChange(() => scheduleSave()));
  disposables.push(
    next.onDidAddPanel(() => {
      // 面板恢复或新增后更新去重索引
      window.setTimeout(rebuildIndex, 0);
    }),
  );
  disposables.push(
    next.onDidRemovePanel((panel) => {
      const key = panelToKey.get(panel.id);
      if (key) keyToPanel.delete(key);
      panelToKey.delete(panel.id);
      scheduleSave();
    }),
  );

  if (!saved) flushPending();
}

export function detachDockview(): void {
  if (saveTimer !== null) {
    window.clearTimeout(saveTimer);
    saveTimer = null;
  }
  for (const disposable of disposables.splice(0, disposables.length)) {
    disposable.dispose();
  }
  api = null;
  useWorkbench.getState().setDockviewApi(null);
  keyToPanel.clear();
  panelToKey.clear();
  pending.length = 0;
}

export function openPreview(spec: PreviewSpec): string {
  const key = specKey(spec);
  const existingId = keyToPanel.get(key);
  if (api && existingId) {
    const panel = api.getPanel(existingId);
    if (panel) {
      panel.api.setActive();
      useWorkbench.getState().setRightOpen(true);
      return panel.id;
    }
    keyToPanel.delete(key);
    panelToKey.delete(existingId);
  }

  const id = nextPanelId();
  useWorkbench.getState().setRightOpen(true);
  if (!api) {
    pending.push({ id, spec: { ...spec, key } });
    return id;
  }
  return addNow(id, { ...spec, key });
}

export function openFileNode(node: TreeNode): string | null {
  if (node.kind === "file" && node.chatId) {
    const fileId = node.id.startsWith("file:") ? node.id.slice(5) : node.id;
    const liveUrl = getChatBlobUrl(fileId);
    if (!node.url && !liveUrl) {
      useWorkbench.getState().notify(
        `「${node.name}」的内容还没同步到工作台，请在聊天里重新生成一次`,
        "error",
      );
      return null;
    }
    if (liveUrl && node.url !== liveUrl) {
      // 刷新后持久化的 blob: URL 已失效，换成当前会话里的新地址
      const liveSpec = previewFromNode({ ...node, url: liveUrl });
      if (liveSpec) return openPreview(liveSpec);
    }
  }
  const spec = previewFromNode(node);
  if (!spec) {
    useWorkbench.getState().notify("暂时没有匹配这个后缀的预览组件", "error");
    return null;
  }
  return openPreview(spec);
}

export function openTerminal(input?: TerminalInput): string {
  const wsUrl = input?.wsUrl || legacyConfig.terminalWs || undefined;
  const spec: PreviewSpec = {
    kind: "terminal",
    title: wsUrl ? "网页终端 · PTY" : "网页终端 · 演示",
    terminal: {
      cwd: input?.cwd || "~/xiaofan",
      wsUrl,
    },
    key: `terminal:${Date.now().toString(36)}`,
  };
  return openPreview(spec);
}

export function openDiff(input: DiffInput): string {
  return openPreview({
    kind: "diff",
    title: input.fileName || "代码对比",
    diff: input,
    key: `diff:${input.fileName || "diff"}:${Date.now().toString(36)}`,
  });
}

export function openSampleDiff(): string {
  return openPreview({
    kind: "diff",
    title: "代码评审.diff",
    file: {
      path: "samples/code-review.diff",
      name: "代码评审.diff",
      url: "/samples/code-review.diff",
      ext: "diff",
    },
    key: "file:samples/code-review.diff",
  });
}

export function closeTab(panelId: string): boolean {
  if (!api) return false;
  const panel = api.getPanel(panelId);
  if (!panel) return false;
  panel.api.close();
  return true;
}

/** 按预览去重键关闭 tab（删文件时用） */
export function closePanelByKey(key: string): number {
  const current = api ?? useWorkbench.getState().dockviewApi;
  if (!current) return 0;
  let closed = 0;
  for (const panel of current.panels) {
    const params = panel.params as { preview?: PreviewSpec } | undefined;
    if (params?.preview?.key !== key) continue;
    panel.api.close();
    closed += 1;
  }
  if (closed) {
    keyToPanel.delete(key);
  }
  return closed;
}

/** 按预览去重键激活 tab（已打开就切过去，不重复新建） */
export function focusPanelByKey(key: string): boolean {
  const current = api ?? useWorkbench.getState().dockviewApi;
  if (!current) return false;
  for (const panel of current.panels) {
    const params = panel.params as { preview?: PreviewSpec } | undefined;
    if (params?.preview?.key !== key) continue;
    panel.api.setActive();
    useWorkbench.getState().setRightOpen(true);
    return true;
  }
  return false;
}

export function closeAllTabs(): void {
  if (!api) return;
  pending.length = 0;
  api.clear();
  keyToPanel.clear();
  panelToKey.clear();
  useWorkbench.getState().setDockLayout(null);
}

export function resetLayout(): void {
  if (!api) {
    pending.length = 0;
    useWorkbench.getState().setDockLayout(null);
    return;
  }
  restoring = true;
  pending.length = 0;
  api.clear();
  keyToPanel.clear();
  panelToKey.clear();
  useWorkbench.getState().setDockLayout(null);
  window.setTimeout(() => {
    restoring = false;
  }, 30);
}

export function getDockLayout(): unknown | null {
  if (!api) return useWorkbench.getState().dockLayout;
  try {
    return api.toJSON();
  } catch {
    return null;
  }
}

export function restoreDockLayout(layout: unknown): void {
  if (!api || !layout) return;
  restoring = true;
  try {
    api.fromJSON(layout as Parameters<DockviewApi["fromJSON"]>[0]);
  } catch (error) {
    console.warn("[workbench] restoreDockLayout failed", error);
  } finally {
    window.setTimeout(() => {
      restoring = false;
      rebuildIndex();
      scheduleSave();
    }, 60);
  }
}

export function getPanelCount(): number {
  return api?.panels.length ?? 0;
}

export function isDockReady(): boolean {
  return api !== null;
}
