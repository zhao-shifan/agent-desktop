import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import {
  createInitialState,
  MAIN_WORKSPACE_ID,
  makeChatFileNode,
  makeWorkspaceGroups,
} from "../data/seed";
import { isChatReady, requestDeleteSession, requestOpenSession } from "../lib/chatBridge";
import type {
  CenterState,
  ChatFileInput,
  LegacyPageKey,
  LegacyStatus,
  SessionMeta,
  WorkbenchStore,
  WorkspaceMeta,
  TreeNode,
} from "../types/workbench";

function cloneTree(nodes: TreeNode[]): TreeNode[] {
  return nodes.map((node) => ({
    ...node,
    children: node.children ? cloneTree(node.children) : undefined,
  }));
}

function findNodeIn(nodes: TreeNode[], id: string): TreeNode | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    if (node.children) {
      const found = findNodeIn(node.children, id);
      if (found) return found;
    }
  }
  return null;
}

/** 聊天「文档」里的节点不在 tree 里，单独找一遍 */
function findChatFileIn(
  chatFiles: Record<string, TreeNode[]>,
  id: string,
): { chatId: string; node: TreeNode } | null {
  for (const [chatId, nodes] of Object.entries(chatFiles)) {
    const node = findNodeIn(nodes, id);
    if (node) return { chatId, node };
  }
  return null;
}

function findAnyNode(state: Pick<WorkbenchStore, "tree" | "chatFiles">, id: string): TreeNode | null {
  return findNodeIn(state.tree, id) ?? findChatFileIn(state.chatFiles, id)?.node ?? null;
}

/** 树和工作区、会话文档里的节点统一查找（聊天文件不在 tree 里） */
export function findWorkbenchNode(
  state: Pick<WorkbenchStore, "tree" | "chatFiles">,
  id: string,
): TreeNode | null {
  return findAnyNode(state, id);
}

function removeNode(nodes: TreeNode[], id: string): TreeNode | null {
  for (let i = 0; i < nodes.length; i++) {
    if (nodes[i].id === id) return nodes.splice(i, 1)[0];
    if (nodes[i].children) {
      const removed = removeNode(nodes[i].children!, id);
      if (removed) return removed;
    }
  }
  return null;
}

function updateNode(nodes: TreeNode[], id: string, patch: Partial<TreeNode>): TreeNode[] {
  return nodes.map((node) => {
    if (node.id === id) return { ...node, ...patch };
    if (node.children) return { ...node, children: updateNode(node.children, id, patch) };
    return node;
  });
}

function subtreeContains(node: TreeNode, id: string): boolean {
  if (node.id === id) return true;
  return Boolean(node.children?.some((child) => subtreeContains(child, id)));
}

function adoptWorkspace(nodes: TreeNode[], workspaceId: string): TreeNode[] {
  return nodes.map((node) => ({
    ...node,
    workspaceId,
    children: node.children ? adoptWorkspace(node.children, workspaceId) : undefined,
  }));
}

/** 把新节点放进去（按 arborist 的“删除前 index”语义修正） */
function insertAt(nodes: TreeNode[], parentId: string | null, index: number, items: TreeNode[]): void {
  if (parentId === null) {
    let adjusted = Math.max(0, Math.min(index, nodes.length));
    for (const item of items) {
      const pos = nodes.findIndex((node) => node.id === item.id);
      if (pos >= 0 && pos < adjusted) adjusted--;
    }
    nodes.splice(adjusted, 0, ...items);
    return;
  }

  const parent = findNodeIn(nodes, parentId);
  if (!parent) return;
  if (!parent.children) parent.children = [];
  let adjusted = Math.max(0, Math.min(index, parent.children.length));
  for (const item of items) {
    const pos = parent.children.findIndex((node) => node.id === item.id);
    if (pos >= 0 && pos < adjusted) adjusted--;
  }
  parent.children.splice(adjusted, 0, ...items);
}

/**
 * 一个会话节点 = chat 本身 + 两个固定子节点：
 *   1. agent：当前对话绑定的 Agent 配置入口（加载旧 HTML 配置页）
 *   2. folder「文档」：这个对话产生 / 上传的文件
 */
function sessionToNode(session: SessionMeta, chatFiles: Record<string, TreeNode[]>): TreeNode {
  const files = chatFiles[session.id] ?? [];
  return {
    id: `sess:${session.id}`,
    kind: "chat",
    name: session.title || "新对话",
    workspaceId: session.workspaceId,
    sessionId: session.id,
    badge: session.pinned ? "置顶" : files.length ? `${files.length}` : undefined,
    children: [
      {
        id: `agent:${session.id}`,
        kind: "agent",
        name: "Agent 配置",
        workspaceId: session.workspaceId,
        chatId: session.id,
        legacyPage: "agent",
      },
      {
        id: `folder:${session.id}:docs`,
        kind: "folder",
        name: "文档",
        workspaceId: session.workspaceId,
        chatId: session.id,
        children: files,
      },
    ],
  };
}

export function buildTreeData(
  tree: TreeNode[],
  sessions: SessionMeta[],
  chatFiles: Record<string, TreeNode[]> = {},
): TreeNode[] {
  return tree.map((workspace) => ({
    ...workspace,
    children: (workspace.children ?? []).map((child) => {
      if (child.group === "chats") {
        return {
          ...child,
          children: sessions
            .filter((session) => session.workspaceId === workspace.id)
            .map((session) => sessionToNode(session, chatFiles)),
        };
      }
      return child;
    }),
  }));
}

export function findTreeNode(nodes: TreeNode[], id: string): TreeNode | null {
  return findNodeIn(nodes, id);
}

function sameSessions(a: SessionMeta[], b: SessionMeta[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (
      a[i].id !== b[i].id ||
      a[i].title !== b[i].title ||
      a[i].workspaceId !== b[i].workspaceId ||
      Boolean(a[i].pinned) !== Boolean(b[i].pinned) ||
      (a[i].messages ?? 0) !== (b[i].messages ?? 0)
    ) {
      return false;
    }
  }
  return true;
}

export const useWorkbench = create<WorkbenchStore>()(
  persist(
    (set, get) => ({
      ...createInitialState(),

      selectNode: (id) => {
        const state = get();
        if (id.startsWith("sess:")) {
          const sessionId = id.slice(5);
          const session = state.sessions.find((item) => item.id === sessionId);
          if (!session) {
            set({ selectedId: id });
            return;
          }
          // 规则：点会话 = 切换中间聊天，并把旧页切到同一个会话
          if (isChatReady()) requestOpenSession(sessionId);
          set({
            selectedId: id,
            activeSessionId: sessionId,
            activeWorkspaceId: session.workspaceId,
            center: { mode: "chat" },
          });
          return;
        }

        const node = findAnyNode(state, id);
        if (!node) {
          set({ selectedId: id });
          return;
        }

        if (node.kind === "agent") {
          set({
            selectedId: id,
            activeWorkspaceId: node.workspaceId,
            center: { ...state.center, mode: "agent", agentId: node.id },
          });
          return;
        }
        if (node.kind === "api") {
          set({
            selectedId: id,
            activeWorkspaceId: node.workspaceId,
            center: { ...state.center, mode: "api", apiId: node.id },
          });
          return;
        }
        if (node.kind === "workspace") {
          set({ selectedId: id, activeWorkspaceId: node.id });
          return;
        }
        set({ selectedId: id });
      },

      setActiveWorkspace: (id) => {
        if (get().workspaces.some((workspace) => workspace.id === id)) {
          set({ activeWorkspaceId: id });
        }
      },

      setCenter: (center) => set({ center }),

      setRightOpen: (open) => set({ rightOpen: open }),

      syncLegacySessions: (incoming, activeId) => {
        const state = get();
        const byId = new Map(state.sessions.map((session) => [session.id, session]));
        const next = incoming.map<SessionMeta>((session) => {
          const existing = byId.get(session.id);
          return {
            ...session,
            workspaceId: existing?.workspaceId ?? state.activeWorkspaceId ?? MAIN_WORKSPACE_ID,
            source: "legacy",
          };
        });

        let activeSessionId = state.activeSessionId;
        let selectedId = state.selectedId;
        let activeWorkspaceId = state.activeWorkspaceId;

        if (activeId) {
          const active = next.find((session) => session.id === activeId);
          if (active) {
            activeSessionId = active.id;
            activeWorkspaceId = active.workspaceId;
            if (!selectedId || selectedId.startsWith("sess:")) {
              selectedId = `sess:${active.id}`;
            }
          }
        } else {
          activeSessionId = null;
          if (selectedId?.startsWith("sess:")) selectedId = null;
        }

        if (selectedId?.startsWith("sess:")) {
          const selectedSessionId = selectedId.slice(5);
          if (!next.some((session) => session.id === selectedSessionId)) {
            selectedId = null;
          }
        }

        if (sameSessions(state.sessions, next)) {
          set({ activeSessionId, selectedId, activeWorkspaceId });
          return;
        }

        set({
          sessions: next,
          activeSessionId,
          selectedId,
          activeWorkspaceId,
          center: state.center.mode === "chat" ? { ...state.center, mode: "chat" } : state.center,
        });
      },

      renameSession: (id, title) => {
        const name = title.trim();
        if (!name) return;
        set({
          sessions: get().sessions.map((session) =>
            session.id === id ? { ...session, title: name } : session,
          ),
        });
      },

      renameNode: (id, name) => {
        const value = name.trim();
        if (!value) return;
        const state = get();
        const node = findNodeIn(state.tree, id);
        if (!node) return;
        const patch: Partial<TreeNode> = { name: value };
        if (node.kind === "workspace") {
          set({
            tree: state.tree.map((root) =>
              root.id === id ? { ...root, name: value } : root,
            ),
            workspaces: state.workspaces.map((workspace) =>
              workspace.id === id ? { ...workspace, name: value } : workspace,
            ),
          });
          return;
        }
        set({ tree: updateNode(state.tree, id, patch) });
      },

      moveNodes: (dragIds, parentId, index) => {
        const state = get();
        if (!dragIds.length) return;

        // 1) 会话节点：只允许在同一个“会话”分组里排序
        if (dragIds.every((id) => id.startsWith("sess:"))) {
          if (!parentId?.startsWith("folder:") || !parentId.endsWith(":chats")) return;
          const workspaceId = parentId.slice("folder:".length, -":chats".length);
          const order = state.sessions
            .filter((session) => session.workspaceId === workspaceId)
            .map((session) => session.id);
          const moving = dragIds.map((id) => id.slice(5)).filter((id) => order.includes(id));
          if (!moving.length) return;

          let adjusted = index;
          for (const id of moving) {
            const pos = order.indexOf(id);
            if (pos >= 0 && pos < adjusted) adjusted--;
          }
          const rest = order.filter((id) => !moving.includes(id));
          rest.splice(Math.max(0, Math.min(adjusted, rest.length)), 0, ...moving);

          const ordered = rest
            .map((id) => state.sessions.find((session) => session.id === id))
            .filter((session): session is SessionMeta => Boolean(session));
          const others = state.sessions.filter((session) => session.workspaceId !== workspaceId);
          set({ sessions: [...ordered, ...others] });
          return;
        }

        // 2) 普通树节点
        const tree = cloneTree(state.tree);
        const dragging: TreeNode[] = [];
        for (const id of dragIds) {
          const node = findNodeIn(tree, id);
          if (!node) continue;
          if (node.kind === "workspace" && parentId !== null) return;
          if (parentId) {
            const parent = findNodeIn(tree, parentId);
            if (!parent || (parent.kind !== "folder" && parent.kind !== "workspace")) return;
            if (node.id === parent.id) return;
            // 禁止把文件夹拖进自己的后代
            if (node.children && findNodeIn(node.children, parent.id)) return;
          }
          const removed = removeNode(tree, id);
          if (removed) dragging.push(removed);
        }
        if (!dragging.length) return;

        let targetWorkspaceId = state.activeWorkspaceId;
        if (parentId) {
          const parent = findNodeIn(tree, parentId);
          if (!parent) return;
          targetWorkspaceId = parent.workspaceId;
        }
        const adopted = dragging.map((node) => {
          const next = { ...node, workspaceId: targetWorkspaceId };
          return node.children ? { ...next, children: adoptWorkspace(node.children, targetWorkspaceId) } : next;
        });
        insertAt(tree, parentId, index, adopted);
        set({ tree });
      },

      createWorkspace: () => {
        const state = get();
        const id = `ws:${crypto.randomUUID()}`;
        const count = state.workspaces.length + 1;
        const workspace: WorkspaceMeta = {
          id,
          name: `工作区 ${count}`,
          createdAt: Date.now(),
        };
        const root: TreeNode = {
          id,
          kind: "workspace",
          name: workspace.name,
          workspaceId: id,
          children: makeWorkspaceGroups(id, false),
        };
        set({
          workspaces: [...state.workspaces, workspace],
          tree: [...state.tree, root],
          activeWorkspaceId: id,
          selectedId: id,
        });
      },

      promptDeleteWorkspace: (id) => {
        const state = get();
        const workspace = state.workspaces.find((item) => item.id === id);
        if (!workspace) return;
        if (state.workspaces.length <= 1) {
          state.notify("至少保留一个工作区；可以新建一个再删除当前工作区", "error");
          return;
        }
        const fallback = state.workspaces.find((item) => item.id !== id);
        set({
          confirm: {
            kind: "workspace",
            id,
            title: "删除这个工作区？",
            message: `将删除「${workspace.name}」及其中的自定义节点。里面的会话会转移到「${fallback?.name ?? "其他工作区"}」，聊天记录不会被删除。`,
            label: "删除工作区",
          },
        });
      },

      promptDeleteNode: (id) => {
        const state = get();
        const node = findAnyNode(state, id);
        if (!node) return;
        if (node.kind === "workspace") {
          state.promptDeleteWorkspace(id);
          return;
        }
        if (node.kind === "chat") {
          if (node.sessionId) state.promptDeleteSession(node.sessionId);
          return;
        }
        const message =
          node.kind === "agent" || node.kind === "api"
            ? `只从工作台树中移除「${node.name}」，不会删除配置文件。`
            : node.kind === "file" && node.chatId
              ? `从对话「文档」中移除「${node.name}」，已打开的预览 Tab 会一起关闭。`
              : `只从工作台树中移除「${node.name}」${node.children?.length ? "及其中所有子节点" : ""}，不会改动磁盘上的文件。`;
        set({
          confirm: {
            kind: "node",
            id,
            title: node.kind === "file" && node.chatId ? "移除这个文件？" : "从树中移除？",
            message,
            label: node.kind === "file" && node.chatId ? "移除文件" : "移除节点",
          },
        });
      },

      promptDeleteSession: (id) => {
        const state = get();
        const session = state.sessions.find((item) => item.id === id);
        if (!session) return;
        set({
          confirm: {
            kind: "session",
            id,
            title: "删除这个会话？",
            message: `「${session.title}」会从聊天记录中删除，聊天内容不可恢复。`,
            label: "删除会话",
          },
        });
      },

      confirmPending: () => {
        const pending = get().confirm;
        if (!pending) return;
        set({ confirm: null });
        if (pending.kind === "workspace") get().deleteWorkspace(pending.id);
        else if (pending.kind === "session") get().deleteSession(pending.id);
        else get().deleteNode(pending.id);
      },

      cancelConfirm: () => set({ confirm: null }),

      deleteWorkspace: (id) => {
        const state = get();
        if (state.workspaces.length <= 1) {
          state.notify("至少保留一个工作区", "error");
          return;
        }
        const workspace = state.workspaces.find((item) => item.id === id);
        const fallback = state.workspaces.find((item) => item.id !== id);
        if (!workspace || !fallback) return;

        const removedRoot = state.tree.find((node) => node.id === id) ?? null;
        const tree = state.tree.filter((node) => node.id !== id);
        const sessions = state.sessions.map((session) =>
          session.workspaceId === id ? { ...session, workspaceId: fallback.id } : session,
        );
        const activeWorkspaceId =
          state.activeWorkspaceId === id ? fallback.id : state.activeWorkspaceId;

        let selectedId = state.selectedId;
        if (selectedId && !selectedId.startsWith("sess:")) {
          if (selectedId === id || (removedRoot && subtreeContains(removedRoot, selectedId))) {
            selectedId = fallback.id;
          }
        }

        let center = state.center;
        if (removedRoot && center.mode === "agent" && center.agentId && subtreeContains(removedRoot, center.agentId)) {
          center = { ...center, mode: "chat", agentId: undefined };
        }
        if (removedRoot && center.mode === "api" && center.apiId && subtreeContains(removedRoot, center.apiId)) {
          center = { ...center, mode: "chat", apiId: undefined };
        }

        set({
          workspaces: state.workspaces.filter((item) => item.id !== id),
          tree,
          sessions,
          activeWorkspaceId,
          selectedId,
          center,
        });
        state.notify(`已删除工作区「${workspace.name}」，会话已转入「${fallback.name}」`);
      },

      deleteNode: (id) => {
        const state = get();
        const node = findAnyNode(state, id);
        if (!node) return;
        if (node.kind === "workspace") {
          state.deleteWorkspace(id);
          return;
        }
        if (node.kind === "chat") {
          if (node.sessionId) state.deleteSession(node.sessionId);
          return;
        }
        if (node.kind === "file" && node.chatId) {
          state.removeFile(id);
          return;
        }

        const tree = cloneTree(state.tree);
        const removed = removeNode(tree, id);
        if (!removed) return;

        let selectedId = state.selectedId;
        if (selectedId && (selectedId === id || subtreeContains(removed, selectedId))) {
          selectedId = state.activeWorkspaceId;
        }

        let center = state.center;
        if (center.mode === "agent" && center.agentId && subtreeContains(removed, center.agentId)) {
          center = { ...center, mode: "chat", agentId: undefined };
        }
        if (center.mode === "api" && center.apiId && subtreeContains(removed, center.apiId)) {
          center = { ...center, mode: "chat", apiId: undefined };
        }

        set({ tree, selectedId, center });
        state.notify(`已从树中移除「${node.name}」`);
      },

      deleteSession: (id) => {
        const state = get();
        const session = state.sessions.find((item) => item.id === id);
        if (!session) return;
        if (isChatReady()) requestDeleteSession(id);
        const chatFiles = { ...state.chatFiles };
        delete chatFiles[id];
        set({
          sessions: state.sessions.filter((item) => item.id !== id),
          chatFiles,
          activeSessionId: state.activeSessionId === id ? null : state.activeSessionId,
          selectedId: state.selectedId === `sess:${id}` ? null : state.selectedId,
        });
        state.notify(`已删除会话「${session.title}」`);
      },

      addFileToChatFolder: (chatId, file: ChatFileInput) => {
        const state = get();
        const session =
          state.sessions.find((item) => item.id === chatId) ??
          (state.activeSessionId
            ? state.sessions.find((item) => item.id === state.activeSessionId)
            : undefined);
        if (!session) {
          state.notify("找不到当前会话，文件没有加入文档", "error");
          return;
        }
        const node = makeChatFileNode(session.workspaceId, session.id, file);
        const current = state.chatFiles[session.id] ?? [];
        const exists = current.some((item) => item.id === node.id);
        const nextFiles = exists
          ? current.map((item) => (item.id === node.id ? node : item))
          : [...current, node];
        set({ chatFiles: { ...state.chatFiles, [session.id]: nextFiles } });
        if (!exists) state.notify(`已加入「${session.title || "当前会话"}」的文档：${file.name}`);
      },

      removeFile: (fileId) => {
        const state = get();
        const id = fileId.startsWith("file:") ? fileId : `file:${fileId}`;
        const hit = findChatFileIn(state.chatFiles, id);
        if (!hit) {
          // 工作区「文件」分组里的节点仍然走普通的从树中移除
          if (findNodeIn(state.tree, id)) state.deleteNode(id);
          return;
        }

        const nextFiles = (state.chatFiles[hit.chatId] ?? []).filter((item) => item.id !== id);
        const chatFiles = { ...state.chatFiles, [hit.chatId]: nextFiles };

        // 树删了，dockview 里对应的 tab 也要关掉（预览 tab 的去重键就是节点 id）
        const api = state.dockviewApi;
        for (const panel of api?.panels ?? []) {
          const params = panel.params as { preview?: { key?: string } } | undefined;
          if (params?.preview?.key === id) panel.api.close();
        }

        set({
          chatFiles,
          selectedId: state.selectedId === id ? `sess:${hit.chatId}` : state.selectedId,
        });
        state.notify(`已移除文件「${hit.node.name}」`);
      },

      setDockviewApi: (api) => set({ dockviewApi: api }),

      setDockLayout: (layout) => {
        const previous = get().dockLayout;
        if (JSON.stringify(previous) === JSON.stringify(layout)) return;
        set({ dockLayout: layout });
      },

      setLegacyStatus: (page, status) => {
        if (get().legacyStatus[page] === status) return;
        set({ legacyStatus: { ...get().legacyStatus, [page]: status } });
      },

      notify: (message, tone = "info") => {
        const id = Date.now();
        set({ toast: { id, message, tone } });
        window.setTimeout(() => {
          if (get().toast?.id === id) set({ toast: null });
        }, 3200);
      },

      clearToast: () => set({ toast: null }),

      setHydrated: (value) => set({ hydrated: value }),
    }),
    {
      name: "xiaofan-workbench-v1",
      version: 2,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) =>
        ({
          workspaces: state.workspaces,
          activeWorkspaceId: state.activeWorkspaceId,
          sessions: state.sessions,
          activeSessionId: state.activeSessionId,
          tree: state.tree,
          chatFiles: state.chatFiles,
          selectedId: state.selectedId,
          center: state.center,
          dockLayout: state.dockLayout,
        }) as Partial<WorkbenchStore>,
      onRehydrateStorage: () => (state) => {
        // 启动时默认收起右侧预览，不沿用上一次的展开状态
        state?.setRightOpen(false);
        state?.setHydrated(true);
      },
    },
  ),
);

export function getCenterNode(
  center: CenterState,
  tree: TreeNode[],
  chatFiles: Record<string, TreeNode[]> = {},
): TreeNode | null {
  const id = center.mode === "agent" ? center.agentId : center.mode === "api" ? center.apiId : null;
  return id ? findAnyNode({ tree, chatFiles }, id) : null;
}

export function statusLabel(status: LegacyStatus): string {
  switch (status) {
    case "ready":
      return "已连接";
    case "missing":
      return "未连接";
    case "checking":
      return "检测中";
    default:
      return "待检测";
  }
}
