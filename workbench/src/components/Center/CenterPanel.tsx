import { useEffect, useState } from "react";
import { getCenterNode, useWorkbench } from "../../store/workbench";
import { legacyConfig, openInNewWindow } from "../../lib/legacy";
import {
  isChatReady,
  requestNewSession,
  sendChat,
} from "../../lib/chatBridge";
import { ChatHost } from "./ChatHost";
import { ConfigHost } from "./ConfigHost";
import {
  AgentIcon,
  ApiIcon,
  ChatIcon,
  ExternalIcon,
  PlusIcon,
  RefreshIcon,
} from "../Icons";

export function CenterPanel() {
  const center = useWorkbench((state) => state.center);
  const tree = useWorkbench((state) => state.tree);
  const chatFiles = useWorkbench((state) => state.chatFiles);
  const sessions = useWorkbench((state) => state.sessions);
  const activeSessionId = useWorkbench((state) => state.activeSessionId);
  const legacyStatus = useWorkbench((state) => state.legacyStatus);
  const [visited, setVisited] = useState({ agent: false, api: false });

  useEffect(() => {
    if (center.mode === "agent") setVisited((current) => ({ ...current, agent: true }));
    if (center.mode === "api") setVisited((current) => ({ ...current, api: true }));
  }, [center.mode]);

  const activeSession = sessions.find((session) => session.id === activeSessionId);
  const selectedNode = center.mode === "chat" ? null : getCenterNode(center, tree, chatFiles);
  const page = center.mode === "agent" ? "agent" : center.mode === "api" ? "api" : null;

  const title =
    center.mode === "chat"
      ? activeSession?.title || "新的对话"
      : selectedNode?.name || (center.mode === "agent" ? "智能体配置" : "API 配置");

  const kicker =
    center.mode === "chat" ? "CHAT SESSION" : center.mode === "agent" ? "AGENT CONFIG" : "API CONFIG";

  const subtitle =
    center.mode === "chat"
      ? activeSession
        ? `${activeSession.messages ?? 0} 条消息`
        : "新会话 · 发送第一条消息后自动出现在左侧"
      : "";

  const modeStatus =
    center.mode === "chat" ? legacyStatus.chat : center.mode === "agent" ? legacyStatus.agent : legacyStatus.api;

  const startNewChat = () => {
    if (!isChatReady()) {
      useWorkbench.getState().notify("对话页还没加载完成，请稍后再试", "error");
      return;
    }
    requestNewSession();
  };

  const refreshChat = () => {
    if (!isChatReady()) {
      useWorkbench.getState().notify("对话页还没加载完成", "error");
      return;
    }
    sendChat({ type: "refresh" });
  };

  return (
    <section className="wb-center" data-mode={center.mode}>
      <header className="wb-center-head">
        <div className="wb-center-title-wrap">
          <span className={`wb-center-badge wb-center-badge--${center.mode}`}>
            {center.mode === "chat" ? <ChatIcon size={14} /> : center.mode === "agent" ? <AgentIcon size={14} /> : <ApiIcon size={14} />}
            {kicker}
          </span>
          <div className="wb-center-title-block">
            <h2 title={title}>{title}</h2>
            <p>{subtitle}</p>
          </div>
        </div>

        <div className="wb-center-actions">
          <span className={`wb-center-status is-${modeStatus}`}>
            <span className="wb-dot" />
            {modeStatus === "ready" ? "已连接" : modeStatus === "checking" ? "检测中" : modeStatus === "missing" ? "未连接" : "待加载"}
          </span>
          {center.mode === "chat" ? (
            <>
              <button type="button" className="wb-btn wb-btn--ghost" onClick={refreshChat}>
                <RefreshIcon size={13} /> 同步
              </button>
              <button type="button" className="wb-btn wb-btn--accent" onClick={startNewChat}>
                <PlusIcon size={13} /> 新对话
              </button>
            </>
          ) : page ? (
            <button
              type="button"
              className="wb-btn wb-btn--ghost"
              onClick={() => openInNewWindow(legacyConfig[page])}
            >
              <ExternalIcon size={13} /> 新窗口
            </button>
          ) : null}
          {center.mode === "chat" ? (
            <button
              type="button"
              className="wb-icon-btn"
              title="在新窗口打开完整页面"
              onClick={() => openInNewWindow(legacyConfig.chat)}
            >
              <ExternalIcon size={15} />
            </button>
          ) : null}
        </div>
      </header>

      <div className="wb-center-body">
        <div className="wb-center-pane" hidden={center.mode !== "chat"}>
          <ChatHost />
        </div>

        {visited.agent ? (
          <div className="wb-center-pane" hidden={center.mode !== "agent"}>
            {getCenterNode({ mode: "agent", agentId: center.agentId }, tree, chatFiles) ? (
              <ConfigHost
                page="agent"
                node={getCenterNode({ mode: "agent", agentId: center.agentId }, tree, chatFiles)}
              />
            ) : (
              <div className="wb-legacy-empty">
                <div className="wb-legacy-empty-mark">◌</div>
                <h3>请在左侧选择一个智能体</h3>
                <p className="wb-legacy-empty-hint">点击「智能体」分组下的节点即可打开配置页。</p>
              </div>
            )}
          </div>
        ) : null}

        {visited.api ? (
          <div className="wb-center-pane" hidden={center.mode !== "api"}>
            {getCenterNode({ mode: "api", apiId: center.apiId }, tree, chatFiles) ? (
              <ConfigHost
                page="api"
                node={getCenterNode({ mode: "api", apiId: center.apiId }, tree, chatFiles)}
              />
            ) : (
              <div className="wb-legacy-empty">
                <div className="wb-legacy-empty-mark">◌</div>
                <h3>请在左侧选择一个 API 配置</h3>
                <p className="wb-legacy-empty-hint">点击「API 配置」分组下的节点即可打开配置页。</p>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </section>
  );
}
