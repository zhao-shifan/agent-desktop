import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Tree,
  type NodeApi,
  type NodeRendererProps,
  type RenameHandler,
  type MoveHandler,
} from "react-arborist";
import { useDraggable } from "@dnd-kit/core";
import { buildTreeData, useWorkbench } from "../store/workbench";
import { openFileNode } from "../lib/dockController";
import { isChatReady, requestNewSession, requestReorderSessions, requestRenameSession } from "../lib/chatBridge";
import { seedOpenState } from "../data/seed";
import type { TreeNode } from "../types/workbench";
import { extOf } from "../lib/preview";
import {
  AgentIcon,
  ApiIcon,
  ChatIcon,
  ChevronIcon,
  FileTypeIcon,
  FolderIcon,
  GripIcon,
  PencilIcon,
  PlusIcon,
  SearchIcon,
  TrashIcon,
  WorkspaceIcon,
  CloseIcon,
} from "./Icons";
import { LegacyTools } from "./LegacyTools";

function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (!rect) return;
      setSize({ width: Math.floor(rect.width), height: Math.floor(rect.height) });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return [ref, size] as const;
}

function canDrop(parent: NodeApi<TreeNode> | null, dragNodes: NodeApi<TreeNode>[]): boolean {
  if (!dragNodes.length) return false;
  const dragged = dragNodes[0];
  if (dragNodes.length > 1) return false;
  const data = dragged.data;

  // 聊天「文档」里的产物由会话自己管，禁止拖到别处，避免和聊天记录脱节
  if (data.chatId) return false;

  if (data.kind === "workspace") return parent === null;

  if (!parent) return false;
  const parentData = parent.data;
  if (parentData.workspaceId !== data.workspaceId) return false;

  if (data.kind === "chat") {
    return parentData.kind === "folder" && parentData.group === "chats";
  }
  if (data.kind === "agent") {
    return parentData.kind === "folder" && parentData.group === "agents";
  }
  if (data.kind === "api") {
    return parentData.kind === "folder" && parentData.group === "apis";
  }
  if (data.kind === "file" || data.kind === "folder") {
    if (parentData.workspaceId !== data.workspaceId) return false;
    return (
      (parentData.kind === "folder" && parentData.group === "files") ||
      (parentData.kind === "folder" && !parentData.group)
    );
  }
  return false;
}

function TreeRow({ node, style, dragHandle }: NodeRendererProps<TreeNode>) {
  const data = node.data;
  const isGroup = data.kind === "folder" && Boolean(data.group);
  // 会话节点也有子节点（Agent 配置 + 文档），所以 chevron 要对 chat 生效
  const expandable =
    data.kind === "folder" || data.kind === "workspace" || data.kind === "chat";
  const selectedId = useWorkbench((state) => state.selectedId);
  const selected = selectedId === data.id || node.isSelected;
  const childCount = node.children?.length ?? 0;

  const draggable = useDraggable({
    id: `wb-drag:${data.id}`,
    disabled: data.kind !== "file" || Boolean(data.chatId),
    data: data.kind === "file" ? { file: data } : undefined,
  });

  const handleDragPointerDown = (event: React.PointerEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    draggable.listeners?.onPointerDown?.(event);
  };

  const triggerRename = (event: React.MouseEvent) => {
    event.stopPropagation();
    void node.edit();
  };

  const triggerNewSession = (event: React.MouseEvent) => {
    event.stopPropagation();
    useWorkbench.getState().setCenter({ ...useWorkbench.getState().center, mode: "chat" });
    if (!isChatReady()) {
      useWorkbench.getState().notify("对话页还没就绪，请稍后再试", "error");
      return;
    }
    requestNewSession();
  };

  const onRenameBlur = (event: React.FocusEvent<HTMLInputElement>) => {
    const cancelled = event.currentTarget.dataset.cancel === "1";
    if (cancelled) {
      node.reset();
      return;
    }
    node.submit(event.currentTarget.value);
  };

  return (
    <div
      ref={dragHandle}
      className={[
        "wb-tree-row",
        `wb-tree-row--${data.kind}`,
        isGroup ? "is-group" : "",
        selected ? "is-selected" : "",
        node.isDragging ? "is-dragging" : "",
        node.willReceiveDrop ? "will-drop" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      style={style}
      data-kind={data.kind}
      title={data.path || data.name}
    >
      {expandable ? (
        <button
          type="button"
          className="wb-tree-chevron"
          aria-label={node.isOpen ? "折叠" : "展开"}
          onMouseDown={(event) => event.stopPropagation()}
          onClick={(event) => {
            event.stopPropagation();
            node.toggle();
          }}
        >
          <ChevronIcon open={node.isOpen} size={13} />
        </button>
      ) : (
        <span className="wb-tree-chevron wb-tree-chevron--empty" />
      )}

      <span className={`wb-tree-icon wb-tree-icon--${data.kind}`}>
        {data.kind === "workspace" ? (
          <WorkspaceIcon size={15} />
        ) : data.kind === "chat" ? (
          <ChatIcon size={15} />
        ) : data.kind === "agent" ? (
          <AgentIcon size={15} />
        ) : data.kind === "api" ? (
          <ApiIcon size={15} />
        ) : data.kind === "folder" ? (
          <FolderIcon size={15} open={node.isOpen} />
        ) : (
          <FileTypeIcon ext={extOf(data.path || data.name)} size={15} />
        )}
      </span>

      {node.isEditing ? (
        <input
          className="wb-tree-rename"
          defaultValue={data.name}
          autoFocus
          onFocus={(event) => event.currentTarget.select()}
          onClick={(event) => event.stopPropagation()}
          onMouseDown={(event) => event.stopPropagation()}
          onBlur={onRenameBlur}
          onKeyDown={(event) => {
            event.stopPropagation();
            if (event.key === "Enter") event.currentTarget.blur();
            if (event.key === "Escape") {
              event.currentTarget.dataset.cancel = "1";
              event.currentTarget.blur();
            }
          }}
        />
      ) : (
        <span className={`wb-tree-name ${isGroup ? "is-group-label" : ""}`}>{data.name}</span>
      )}

      {data.kind === "file" && data.badge ? <span className="wb-tree-badge">{data.badge}</span> : null}
      {data.kind === "chat" && data.badge ? <span className="wb-tree-badge">{data.badge}</span> : null}
      {isGroup || (data.kind === "folder" && data.chatId) ? (
        childCount > 0 ? (
          <span className="wb-tree-count">{childCount}</span>
        ) : null
      ) : null}

      {data.kind === "folder" && data.group === "chats" ? (
        <button
          type="button"
          className="wb-tree-action wb-tree-action--plus"
          title="新建对话"
          onMouseDown={(event) => event.stopPropagation()}
          onClick={triggerNewSession}
        >
          <PlusIcon size={13} />
        </button>
      ) : null}

      {data.kind === "file" ? (
        <button
          ref={draggable.setNodeRef}
          type="button"
          className={`wb-tree-action wb-tree-grip ${draggable.isDragging ? "is-dragging" : ""}`}
          title="拖到右侧面板打开预览"
          aria-label="拖到右侧面板打开预览"
          draggable={false}
          {...draggable.attributes}
          onPointerDown={handleDragPointerDown}
          onDragStart={(event) => event.stopPropagation()}
          onClick={(event) => event.stopPropagation()}
        >
          <GripIcon size={13} />
        </button>
      ) : null}

      {!data.chatId && (data.kind !== "folder" || !data.group) ? (
        <button
          type="button"
          className="wb-tree-action wb-tree-action--edit"
          title="重命名（F2 / Enter）"
          onMouseDown={(event) => event.stopPropagation()}
          onClick={triggerRename}
        >
          <PencilIcon size={12} />
        </button>
      ) : null}

      {!isGroup && !(data.chatId && data.kind !== "file") ? (
        <button
          type="button"
          className="wb-tree-action wb-tree-action--delete"
          title={
            data.kind === "workspace"
              ? "删除工作区"
              : data.kind === "chat"
                ? "删除会话"
                : data.kind === "file" && data.chatId
                  ? "从会话文档中移除"
                  : "从树中移除"
          }
          onMouseDown={(event) => event.stopPropagation()}
          onClick={(event) => {
            event.stopPropagation();
            const store = useWorkbench.getState();
            if (data.kind === "workspace") store.promptDeleteWorkspace(data.id);
            else if (data.kind === "chat" && data.sessionId) store.promptDeleteSession(data.sessionId);
            else store.promptDeleteNode(data.id);
          }}
        >
          <TrashIcon size={12} />
        </button>
      ) : null}
    </div>
  );
}

export function TreePanel() {
  const tree = useWorkbench((state) => state.tree);
  const sessions = useWorkbench((state) => state.sessions);
  const chatFiles = useWorkbench((state) => state.chatFiles);
  const selectedId = useWorkbench((state) => state.selectedId);
  const legacyStatus = useWorkbench((state) => state.legacyStatus);
  const [search, setSearch] = useState("");
  const [containerRef, size] = useElementSize<HTMLDivElement>();

  const data = useMemo(() => buildTreeData(tree, sessions, chatFiles), [tree, sessions, chatFiles]);

  const handleSelect = useCallback((nodes: NodeApi<TreeNode>[]) => {
    const node = nodes[0];
    if (!node) return;
    const store = useWorkbench.getState();
    const item = node.data;
    // 规则：chat → 切中间聊天；agent → 旧配置页；file → dockview；folder → 只折叠
    store.selectNode(item.id);
    if (item.kind === "folder" || item.kind === "workspace") {
      node.toggle();
      return;
    }
    if (item.kind === "file") {
      openFileNode(item);
    }
  }, []);

  const handleRename = useCallback<RenameHandler<TreeNode>>(
    ({ id, name, node }) => {
      const store = useWorkbench.getState();
      if (node.data.kind === "chat" && node.data.sessionId) {
        store.renameSession(node.data.sessionId, name);
        requestRenameSession(node.data.sessionId, name);
        return;
      }
      store.renameNode(id, name);
      if (node.data.kind === "workspace") {
        store.setActiveWorkspace(id);
      }
    },
    [],
  );

  const handleMove = useCallback<MoveHandler<TreeNode>>(
    ({ dragIds, parentId, index }) => {
      const store = useWorkbench.getState();
      store.moveNodes(dragIds, parentId, index);
      if (dragIds.some((id) => id.startsWith("sess:"))) {
        const all = useWorkbench.getState().sessions.map((session) => session.id);
        requestReorderSessions(all);
      }
    },
    [],
  );

  const filter = search.trim().toLowerCase();

  return (
    <aside className="wb-left">
      <div className="wb-panel-head">
        <div className="wb-panel-title">
          <span className="wb-panel-kicker">NAVIGATOR</span>
          <strong>资源</strong>
        </div>
        <span className="wb-panel-sub">{tree.length} 个工作区</span>
      </div>

      <div className="wb-tree-search">
        <SearchIcon size={14} />
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="筛选会话 / Agent / 文件…"
          spellCheck={false}
        />
        {search ? (
          <button type="button" title="清空筛选" onClick={() => setSearch("")}>
            <CloseIcon size={12} />
          </button>
        ) : null}
      </div>

      <div className="wb-tree-body" ref={containerRef}>
        {size.height > 0 ? (
          <Tree<TreeNode>
            data={data}
            width="100%"
            height={size.height}
            rowHeight={32}
            indent={13}
            paddingTop={8}
            paddingBottom={16}
            openByDefault={false}
            initialOpenState={seedOpenState}
            selection={selectedId ?? undefined}
            searchTerm={filter}
            searchMatch={(node, term) => {
              const value = term.trim().toLowerCase();
              if (!value) return true;
              return (
                node.data.name.toLowerCase().includes(value) ||
                (node.data.path ?? "").toLowerCase().includes(value) ||
                (node.data.badge ?? "").toLowerCase().includes(value)
              );
            }}
            disableMultiSelection
            disableEdit={(item) => Boolean(item.chatId) || (item.kind === "folder" && Boolean(item.group))}
            disableDrag={(item) =>
              Boolean(item.chatId) || (item.kind === "folder" && Boolean(item.group))
            }
            disableDrop={({ parentNode, dragNodes }) => !canDrop(parentNode, dragNodes)}
            onSelect={handleSelect}
            onRename={handleRename}
            onMove={handleMove}
            className="wb-tree"
            rowClassName="wb-tree-row-wrap"
          >
            {TreeRow}
          </Tree>
        ) : null}
      </div>

      <LegacyTools />

      <div className="wb-left-foot">
        <div className="wb-foot-status">
          <span
            className={`wb-dot ${
              legacyStatus.chat === "ready"
                ? "is-ok"
                : legacyStatus.chat === "missing"
                  ? "is-warn"
                  : ""
            }`}
          />
          <span>
            对话服务 ·{" "}
            {legacyStatus.chat === "ready"
              ? "已连接"
              : legacyStatus.chat === "missing"
                ? "未连接"
                : "待连接"}
          </span>
        </div>
        <div className="wb-foot-hint">拖拽排序 · F2 重命名 · 空格折叠</div>
      </div>
    </aside>
  );
}
