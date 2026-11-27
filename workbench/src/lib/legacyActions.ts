import { isChatReady, sendChat } from "./chatBridge";
import { useWorkbench } from "../store/workbench";

export type LegacyOverlay =
  | "openSettings"
  | "openThemes"
  | "openSkills"
  | "openMcpManager"
  | "openQR";

const LABELS: Record<LegacyOverlay, string> = {
  openSettings: "API 接入设置",
  openThemes: "主题外观",
  openSkills: "技能",
  openMcpManager: "MCP 工具",
  openQR: "手机扫码",
};

/** 打开旧聊天页里自带的设置 / 主题 / 技能 / MCP / 扫码面板 */
export function openLegacyOverlay(type: LegacyOverlay): boolean {
  const state = useWorkbench.getState();
  if (!isChatReady()) {
    state.notify(`对话页还没加载完成，暂时打不开「${LABELS[type]}」`, "error");
    return false;
  }
  state.setCenter({ ...state.center, mode: "chat" });
  const ok = sendChat({ type });
  if (!ok) {
    state.notify(`对话页没有响应「${LABELS[type]}」`, "error");
  }
  return ok;
}
