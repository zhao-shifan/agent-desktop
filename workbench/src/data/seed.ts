import { extOf } from "../lib/preview";
import type {
  ChatFileInput,
  SessionMeta,
  TreeNode,
  WorkbenchStore,
  WorkspaceMeta,
} from "../types/workbench";

const now = Date.now();

export const MAIN_WORKSPACE_ID = "ws:main";

function file(
  workspaceId: string,
  name: string,
  path: string,
  options: { size?: number; mime?: string; badge?: string } = {},
): TreeNode {
  return {
    id: `file:${workspaceId}:${path}`,
    kind: "file",
    name,
    workspaceId,
    path,
    url: `/${path}`,
    size: options.size,
    mime: options.mime,
    badge: options.badge,
    children: undefined,
  };
}

function folder(
  workspaceId: string,
  key: string,
  name: string,
  children: TreeNode[] = [],
): TreeNode {
  return {
    id: `folder:${workspaceId}:${key}`,
    kind: "folder",
    name,
    workspaceId,
    children,
  };
}

function group(
  workspaceId: string,
  groupKey: "chats" | "agents" | "apis" | "files",
  name: string,
  children: TreeNode[] = [],
): TreeNode {
  return {
    id: `folder:${workspaceId}:${groupKey}`,
    kind: "folder",
    name,
    workspaceId,
    group: groupKey,
    children,
  };
}

export function makeWorkspaceGroups(workspaceId: string, withDemo = true): TreeNode[] {
  return [
    group(workspaceId, "chats", "会话"),
    group(workspaceId, "agents", "智能体", withDemo ? [
      {
        id: `agent:${workspaceId}:writer`,
        kind: "agent",
        name: "写作智能体",
        workspaceId,
        legacyPage: "agent",
      },
      {
        id: `agent:${workspaceId}:reviewer`,
        kind: "agent",
        name: "代码评审官",
        workspaceId,
        legacyPage: "agent",
      },
    ] : []),
    group(workspaceId, "apis", "API 配置", withDemo ? [
      {
        id: `api:${workspaceId}:deepseek`,
        kind: "api",
        name: "DeepSeek · 主模型",
        workspaceId,
        legacyPage: "api",
      },
      {
        id: `api:${workspaceId}:local`,
        kind: "api",
        name: "本地 OpenAI 兼容",
        workspaceId,
        legacyPage: "api",
      },
    ] : []),
    group(workspaceId, "files", "工作区文件", withDemo ? [
      folder(workspaceId, "docs", "文档", [
        file(workspaceId, "项目汇报.pptx", "samples/quarterly-review.pptx", {
          size: 38005,
          mime: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }),
        file(workspaceId, "技术方案.pdf", "samples/tech-plan.pdf", {
          size: 104297,
          mime: "application/pdf",
        }),
      ]),
      folder(workspaceId, "assets", "素材", [
        file(workspaceId, "工作台视觉稿.png", "samples/design.png", {
          size: 105905,
          mime: "image/png",
        }),
      ]),
      folder(workspaceId, "data", "数据", [
        file(workspaceId, "销售数据.xlsx", "samples/sales-data.xlsx", {
          size: 6589,
          mime: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }),
      ]),
      file(workspaceId, "代码评审.diff", "samples/code-review.diff", {
        size: 1333,
        mime: "text/x-diff",
      }),
      file(workspaceId, "README.md", "samples/README.md", {
        size: 991,
        mime: "text/markdown",
      }),
    ] : []),
  ];
}

export const seedWorkspaces: WorkspaceMeta[] = [
  { id: MAIN_WORKSPACE_ID, name: "小凡工作区", createdAt: now },
];

export const seedTree: TreeNode[] = [
  {
    id: MAIN_WORKSPACE_ID,
    kind: "workspace",
    name: "小凡工作区",
    workspaceId: MAIN_WORKSPACE_ID,
    children: makeWorkspaceGroups(MAIN_WORKSPACE_ID),
  },
];

export const seedSessions: SessionMeta[] = [
  {
    id: "seed:req",
    title: "需求梳理：工作台三栏",
    workspaceId: MAIN_WORKSPACE_ID,
    messages: 6,
    updatedAt: now - 1000 * 60 * 18,
    source: "seed",
  },
  {
    id: "seed:review",
    title: "代码评审：预览注册表",
    workspaceId: MAIN_WORKSPACE_ID,
    messages: 4,
    updatedAt: now - 1000 * 60 * 60 * 3,
    source: "seed",
  },
  {
    id: "seed:agent",
    title: "智能体编排草稿",
    workspaceId: MAIN_WORKSPACE_ID,
    pinned: true,
    messages: 9,
    updatedAt: now - 1000 * 60 * 60 * 26,
    source: "seed",
  },
];

/** 聊天生成 / 上传的文件 → 树节点（会话「文档」文件夹里的一项） */
export function makeChatFileNode(
  workspaceId: string,
  chatId: string,
  input: ChatFileInput,
): TreeNode {
  return {
    id: `file:${input.id}`,
    kind: "file",
    name: input.name,
    workspaceId,
    path: input.url || input.name,
    url: input.url,
    ext: input.ext?.toLowerCase() || extOf(input.name),
    size: input.size,
    mime: input.mime,
    chatId,
    generated: input.generated !== false,
    badge: input.generated === false ? undefined : "生成",
  };
}

export const seedChatFiles: Record<string, TreeNode[]> = {
  "seed:req": [
    makeChatFileNode(MAIN_WORKSPACE_ID, "seed:req", {
      id: "seed:req:产品需求说明.docx",
      name: "产品需求说明.docx",
      url: "/samples/product-spec.docx",
      ext: "docx",
      size: 38043,
      mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }),
  ],
};

/** 初始 open state：默认展开工作区、会话分组、第一个会话和它的文档夹 */
export const seedOpenState: Record<string, boolean> = {
  [MAIN_WORKSPACE_ID]: true,
  [`folder:${MAIN_WORKSPACE_ID}:chats`]: true,
  [`folder:${MAIN_WORKSPACE_ID}:agents`]: true,
  [`folder:${MAIN_WORKSPACE_ID}:apis`]: true,
  [`folder:${MAIN_WORKSPACE_ID}:files`]: true,
  [`folder:${MAIN_WORKSPACE_ID}:docs`]: true,
  [`folder:${MAIN_WORKSPACE_ID}:assets`]: true,
  [`folder:${MAIN_WORKSPACE_ID}:data`]: true,
  "sess:seed:req": true,
  "folder:seed:req:docs": true,
};

export function createInitialState(): Omit<
  WorkbenchStore,
  | "selectNode"
  | "setActiveWorkspace"
  | "setCenter"
  | "setRightOpen"
  | "syncLegacySessions"
  | "renameSession"
  | "renameNode"
  | "moveNodes"
  | "createWorkspace"
  | "promptDeleteWorkspace"
  | "promptDeleteNode"
  | "promptDeleteSession"
  | "confirmPending"
  | "cancelConfirm"
  | "deleteWorkspace"
  | "deleteNode"
  | "deleteSession"
  | "addFileToChatFolder"
  | "removeFile"
  | "setDockviewApi"
  | "setDockLayout"
  | "setLegacyStatus"
  | "notify"
  | "clearToast"
  | "setHydrated"
> {
  return {
    workspaces: seedWorkspaces,
    activeWorkspaceId: MAIN_WORKSPACE_ID,
    sessions: seedSessions,
    activeSessionId: seedSessions[0]?.id ?? null,
    tree: seedTree,
    chatFiles: seedChatFiles,
    selectedId: `sess:${seedSessions[0]?.id ?? ""}`,
    center: { mode: "chat" },
    rightOpen: false,
    dockLayout: null,
    dockviewApi: null,
    legacyStatus: {
      chat: "unknown",
      agent: "unknown",
      api: "unknown",
    },
    toast: null,
    confirm: null,
    hydrated: false,
  };
}
