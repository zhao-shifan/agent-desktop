import { useWorkbench } from "../store/workbench";
import { isChatReady, requestNewSession } from "../lib/chatBridge";
import { openTerminal, resetLayout } from "../lib/dockController";
import {
  LayoutIcon,
  PanelIcon,
  PlusIcon,
  TerminalIcon,
  TrashIcon,
} from "./Icons";

export function TopBar() {
  const workspaces = useWorkbench((state) => state.workspaces);
  const activeWorkspaceId = useWorkbench((state) => state.activeWorkspaceId);
  const rightOpen = useWorkbench((state) => state.rightOpen);
  const setActiveWorkspace = useWorkbench((state) => state.setActiveWorkspace);
  const setRightOpen = useWorkbench((state) => state.setRightOpen);
  const createWorkspace = useWorkbench((state) => state.createWorkspace);
  const promptDeleteWorkspace = useWorkbench((state) => state.promptDeleteWorkspace);

  const startChat = () => {
    useWorkbench.getState().setCenter({
      ...useWorkbench.getState().center,
      mode: "chat",
    });
    if (!isChatReady()) {
      useWorkbench.getState().notify("对话页还没加载完成，请稍后再试", "error");
      return;
    }
    requestNewSession();
  };

  return (
    <header className="wb-topbar">
      <div className="wb-brand">
        <span className="wb-brand-mark">✦</span>
        <div className="wb-brand-text">
          <strong>小凡 · 智能体工作台</strong>
          <span>AGENT WORKBENCH</span>
        </div>
      </div>

      <div className="wb-workspace-switch">
        <span className="wb-workspace-label">WORKSPACE</span>
        <select
          value={activeWorkspaceId}
          onChange={(event) => setActiveWorkspace(event.target.value)}
          aria-label="切换工作区"
        >
          {workspaces.map((workspace) => (
            <option key={workspace.id} value={workspace.id}>
              {workspace.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="wb-icon-btn"
          title="新建工作区"
          onClick={() => createWorkspace()}
        >
          <PlusIcon size={14} />
        </button>
        <button
          type="button"
          className="wb-icon-btn wb-icon-btn--danger"
          title={workspaces.length <= 1 ? "至少保留一个工作区" : "删除当前工作区"}
          disabled={workspaces.length <= 1}
          onClick={() => promptDeleteWorkspace(activeWorkspaceId)}
        >
          <TrashIcon size={14} />
        </button>
      </div>

      <span className="wb-topbar-spacer" />

      <div className="wb-topbar-actions">
        <button type="button" className="wb-btn wb-btn--accent" onClick={startChat}>
          <PlusIcon size={14} /> 新对话
        </button>
        <button
          type="button"
          className="wb-icon-btn"
          title="打开网页终端"
          onClick={() => openTerminal()}
        >
          <TerminalIcon size={16} />
        </button>
        <button
          type="button"
          className="wb-icon-btn"
          title="重置预览布局"
          onClick={() => resetLayout()}
        >
          <LayoutIcon size={16} />
        </button>
        <button
          type="button"
          className={`wb-btn wb-btn--ghost ${rightOpen ? "" : "is-muted"}`}
          onClick={() => setRightOpen(!rightOpen)}
        >
          <PanelIcon size={14} /> {rightOpen ? "收起预览" : "展开预览"}
        </button>
      </div>
    </header>
  );
}
