import type { DockviewApi } from "dockview-react";

export type NodeKind = "workspace" | "chat" | "agent" | "api" | "file" | "folder";

export type TreeGroup = "chats" | "agents" | "apis" | "files";

export interface TreeNode {
  id: string;
  kind: NodeKind;
  name: string;
  workspaceId: string;
  /** 固定分组（会话 / 智能体 / API / 文件）标识；只有 folder 会带 */
  group?: TreeGroup;
  children?: TreeNode[];
  /** chat 节点指向的会话 id */
  sessionId?: string;
  /** agent / api 节点对应的旧 HTML 类型 */
  legacyPage?: "agent" | "api";
  /** 可选：该节点单独指向的旧 HTML 地址（不填则用 workbench.config.js） */
  legacyUrl?: string;
  /** file 节点 */
  path?: string;
  url?: string;
  mime?: string;
  size?: number;
  /** 显式后缀（blob: URL 没有后缀时靠它选择预览器） */
  ext?: string;
  /** 该节点属于哪个会话；聊天「文档」及其文件会带 */
  chatId?: string;
  /** 由聊天流程生成 / 上传的文件 */
  generated?: boolean;
  /** 树节点上的轻量徽标（例如消息数） */
  badge?: string;
}

/** 聊天流程里新增的文件（addFileToChatFolder 的入参） */
export interface ChatFileInput {
  id: string;
  name: string;
  url?: string;
  ext?: string;
  size?: number;
  mime?: string;
  generated?: boolean;
}

export interface SessionMeta {
  id: string;
  title: string;
  workspaceId: string;
  pinned?: boolean;
  updatedAt?: number;
  messages?: number;
  source?: "legacy" | "seed";
}

export interface WorkspaceMeta {
  id: string;
  name: string;
  createdAt: number;
}

export type CenterMode = "chat" | "agent" | "api";

export interface CenterState {
  mode: CenterMode;
  agentId?: string;
  apiId?: string;
}

export type LegacyPageKey = "chat" | "agent" | "api";
export type LegacyStatus = "unknown" | "checking" | "ready" | "missing";

export type PreviewKind =
  | "docx"
  | "pptx"
  | "pdf"
  | "image"
  | "sheet"
  | "diff"
  | "terminal"
  | "text"
  | "unknown";

export interface PreviewFile {
  path: string;
  name: string;
  url?: string;
  size?: number;
  mime?: string;
  ext?: string;
}

export interface DiffInput {
  fileName?: string;
  /** 已经是 unified diff 文本 */
  unified?: string;
  oldText?: string;
  newText?: string;
}

export interface TerminalInput {
  cwd?: string;
  /** 可选：接入真实 PTY 的 WebSocket 地址；不填则使用内置演示命令 */
  wsUrl?: string;
}

export interface PreviewSpec {
  kind: PreviewKind;
  title: string;
  file?: PreviewFile;
  diff?: DiffInput;
  terminal?: TerminalInput;
  /** 去重键：同一文件重复打开只聚焦 */
  key?: string;
}

export interface LegacyConfig {
  chat: string;
  agent: string;
  api: string;
  samplesBase: string;
  terminalWs: string;
}

export interface ToastState {
  id: number;
  message: string;
  tone: "info" | "error" | "ok";
}

export interface ConfirmState {
  kind: "workspace" | "node" | "session";
  id: string;
  title: string;
  message: string;
  label: string;
}

export interface WorkbenchStore {
  workspaces: WorkspaceMeta[];
  activeWorkspaceId: string;
  sessions: SessionMeta[];
  activeSessionId: string | null;
  tree: TreeNode[];
  /** 会话「文档」文件夹里的文件：chatId → file 节点 */
  chatFiles: Record<string, TreeNode[]>;
  selectedId: string | null;
  center: CenterState;
  rightOpen: boolean;
  dockLayout: unknown | null;
  /** dockview 实例（不持久化），全局打开/关闭预览走它 */
  dockviewApi: DockviewApi | null;
  legacyStatus: Record<LegacyPageKey, LegacyStatus>;
  toast: ToastState | null;
  confirm: ConfirmState | null;
  hydrated: boolean;

  selectNode: (id: string) => void;
  setActiveWorkspace: (id: string) => void;
  setCenter: (center: CenterState) => void;
  setRightOpen: (open: boolean) => void;
  syncLegacySessions: (sessions: SessionMeta[], activeId: string | null) => void;
  renameSession: (id: string, title: string) => void;
  renameNode: (id: string, name: string) => void;
  moveNodes: (dragIds: string[], parentId: string | null, index: number) => void;
  createWorkspace: () => void;
  promptDeleteWorkspace: (id: string) => void;
  promptDeleteNode: (id: string) => void;
  promptDeleteSession: (id: string) => void;
  confirmPending: () => void;
  cancelConfirm: () => void;
  deleteWorkspace: (id: string) => void;
  deleteNode: (id: string) => void;
  deleteSession: (id: string) => void;
  /** 把文件追加进某个会话的「文档」文件夹 */
  addFileToChatFolder: (chatId: string, file: ChatFileInput) => void;
  /** 删除一个聊天文件节点；已打开的预览 tab 会被关闭 */
  removeFile: (fileId: string) => void;
  /** 登记 dockview 实例，供全局与聊天消息按钮调用 */
  setDockviewApi: (api: DockviewApi | null) => void;
  setDockLayout: (layout: unknown | null) => void;
  setLegacyStatus: (page: LegacyPageKey, status: LegacyStatus) => void;
  notify: (message: string, tone?: ToastState["tone"]) => void;
  clearToast: () => void;
  setHydrated: (value: boolean) => void;
}
