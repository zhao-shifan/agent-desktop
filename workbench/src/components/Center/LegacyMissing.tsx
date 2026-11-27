import { ExternalIcon, RefreshIcon, SettingsIcon } from "../Icons";
import { openInNewWindow } from "../../lib/legacy";
import type { LegacyPageKey } from "../../types/workbench";

const COPY: Record<
  LegacyPageKey,
  { title: string; hint: string; steps: string[] }
> = {
  chat: {
    title: "聊天页还没加载",
    hint: "对话、会话和附件都由工作台里的聊天页接管。",
    steps: [
      "在 workbench 目录运行 pnpm sync:legacy，自动把根目录 index.html 生成到 public/legacy/chat.html；",
      "或者把你的聊天 HTML 放到该位置；",
      "也可以修改 public/workbench.config.js 里的 chat 路径。",
    ],
  },
  agent: {
    title: "还没有 Agent 配置页",
    hint: "点击左侧 Agent 节点会加载你自己的配置页。",
    steps: [
      "把你的 Agent 配置页放到 public/legacy/agent-config.html；",
      "页面里的表单、保存逻辑、样式完全由你的页面决定；",
      "或者修改 public/workbench.config.js 里的 agent 路径。",
    ],
  },
  api: {
    title: "还没有 API 配置页",
    hint: "点击左侧 API 节点会加载你自己的配置页。",
    steps: [
      "把你的 API 配置页放到 public/legacy/api-config.html；",
      "页面里的服务商选择、Key 输入、保存逻辑完全沿用该页面；",
      "或者修改 public/workbench.config.js 里的 api 路径。",
    ],
  },
};

export function LegacyMissing({
  page,
  url,
  onRecheck,
  onOpenOldSettings,
}: {
  page: LegacyPageKey;
  url: string;
  onRecheck: () => void;
  onOpenOldSettings?: () => void;
}) {
  const copy = COPY[page];
  return (
    <div className="wb-legacy-empty">
      <div className="wb-legacy-empty-mark">◌</div>
      <span className="wb-legacy-empty-kicker">WORKBENCH PAGE</span>
      <h3>{copy.title}</h3>
      <p className="wb-legacy-empty-hint">{copy.hint}</p>
      <ul>
        {copy.steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ul>
      <div className="wb-legacy-path">
        <span>期望路径</span>
        <code>{url}</code>
      </div>
      <div className="wb-legacy-empty-actions">
        <button type="button" className="wb-btn" onClick={onRecheck}>
          <RefreshIcon size={14} /> 重新检测
        </button>
        {onOpenOldSettings ? (
          <button type="button" className="wb-btn wb-btn--ghost" onClick={onOpenOldSettings}>
            <SettingsIcon size={14} /> API 设置
          </button>
        ) : null}
        <button
          type="button"
          className="wb-btn wb-btn--ghost"
          onClick={() => openInNewWindow(url)}
        >
          <ExternalIcon size={14} /> 在新窗口打开
        </button>
      </div>
    </div>
  );
}
