import { useCallback, useEffect, useRef, useState } from "react";
import { legacyConfig } from "../../lib/legacy";
import {
  getBridgeActiveId,
  isChatReady,
  markChatFrameLoaded,
  parseChatFileMessage,
  parseChatMessage,
  parseOpenFileMessage,
  requestOpenSession,
  setBridgeActiveId,
  setChatFrame,
  subscribeChatBridge,
} from "../../lib/chatBridge";
import { findWorkbenchNode, useWorkbench } from "../../store/workbench";
import { applyWorkbenchTheme } from "../../lib/theme";
import { chatFileId, registerChatBlob } from "../../lib/chatFiles";
import { openFileNode } from "../../lib/dockController";
import { PreviewLoading } from "../Previews/PreviewParts";
import { LegacyMissing } from "./LegacyMissing";
import { useLegacyAvailability } from "./useLegacyAvailability";

export function ChatHost() {
  const url = legacyConfig.chat;
  const { status, recheck } = useLegacyAvailability(url, "chat");
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [bridgeReady, setBridgeReady] = useState(() => isChatReady());
  const activeSessionId = useWorkbench((state) => state.activeSessionId);

  useEffect(() => {
    setBridgeReady(isChatReady());
    return subscribeChatBridge(() => setBridgeReady(isChatReady()));
  }, []);

  useEffect(() => {
    const handler = (event: MessageEvent) => {
      const frame = iframeRef.current;
      if (!frame || event.source !== frame.contentWindow) return;
      if (event.origin !== window.location.origin) return;
      const data = event.data;
      if (data && typeof data === "object" && data.__wb === 1 && data.type === "theme") {
        applyWorkbenchTheme(typeof data.theme === "string" ? data.theme : "");
        return;
      }

      // 规则 1：旧页生成 / 导出文件 → 自动进当前会话的「文档」
      const incoming = parseChatFileMessage(event.data);
      if (incoming) {
        const store = useWorkbench.getState();
        const chatId = incoming.chatId || store.activeSessionId;
        if (!chatId) return;
        const id = chatFileId(chatId, incoming.name);
        let url: string | undefined;
        if (incoming.blob) url = registerChatBlob(id, incoming.blob);
        store.addFileToChatFolder(chatId, {
          id,
          name: incoming.name,
          url,
          ext: incoming.ext,
          size: incoming.size,
        });
        return;
      }

      // 聊天卡片上的「在右侧打开」
      const openRequest = parseOpenFileMessage(event.data);
      if (openRequest) {
        const store = useWorkbench.getState();
        const node = findWorkbenchNode(store, `file:${openRequest.fileId}`);
        if (node) openFileNode(node);
        else store.notify("这个文件还没同步到工作台，请重新生成一次", "error");
        return;
      }

      const parsed = parseChatMessage(event.data);
      if (!parsed) return;
      setBridgeActiveId(parsed.activeId);
      useWorkbench.getState().setLegacyStatus("chat", "ready");
      useWorkbench.getState().syncLegacySessions(parsed.sessions, parsed.activeId);
      setBridgeReady(true);
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  useEffect(() => {
    if (!bridgeReady || status !== "ready") return;
    if (!activeSessionId) return;
    if (getBridgeActiveId() === activeSessionId) return;
    requestOpenSession(activeSessionId);
  }, [activeSessionId, bridgeReady, status]);

  const handleLoad = useCallback(() => {
    setLoaded(true);
    const frame = iframeRef.current;
    if (frame) {
      setChatFrame(frame);
      markChatFrameLoaded();
      useWorkbench.getState().setLegacyStatus("chat", "ready");
    }
  }, []);

  const setRef = useCallback((element: HTMLIFrameElement | null) => {
    iframeRef.current = element;
    setChatFrame(element);
    if (!element) setLoaded(false);
  }, []);

  if (status === "missing") {
    return <LegacyMissing page="chat" url={url} onRecheck={recheck} />;
  }

  if (status === "checking") {
    return (
      <div className="wb-legacy-loading">
        <PreviewLoading label="正在检测对话页…" />
      </div>
    );
  }

  return (
    <div className="wb-legacy-host">
      <iframe
        ref={setRef}
        className="wb-legacy-frame"
        src={url}
        title="小凡智能体 · 对话"
        allow="clipboard-read; clipboard-write"
        onLoad={handleLoad}
      />
      {!loaded ? (
        <div className="wb-legacy-loading is-overlay">
          <PreviewLoading label="正在载入对话页…" />
        </div>
      ) : null}
    </div>
  );
}
