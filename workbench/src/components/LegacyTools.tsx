import { openLegacyOverlay, type LegacyOverlay } from "../lib/legacyActions";
import {
  ApiIcon,
  PaletteIcon,
  PhoneIcon,
  PlugIcon,
  SettingsIcon,
  SkillsIcon,
} from "./Icons";

const ACTIONS: Array<{
  type: LegacyOverlay;
  label: string;
  hint: string;
  icon: typeof SettingsIcon;
  wide?: boolean;
}> = [
  { type: "openSettings", label: "API 设置", hint: "接入与模型设置", icon: SettingsIcon },
  { type: "openThemes", label: "主题外观", hint: "主题、壁纸与我的照片", icon: PaletteIcon },
  { type: "openSkills", label: "技能", hint: "技能列表", icon: SkillsIcon },
  { type: "openMcpManager", label: "MCP 工具", hint: "MCP 管理", icon: PlugIcon },
  { type: "openQR", label: "手机扫码", hint: "用手机打开同一份对话", icon: PhoneIcon, wide: true },
];

export function LegacyTools() {
  return (
    <div className="wb-legacy-tools">
      <div className="wb-legacy-tools-head">
        <span>快捷入口</span>
        <span className="wb-legacy-tools-kicker">TOOLS</span>
      </div>
      <div className="wb-legacy-tools-grid">
        {ACTIONS.map(({ type, label, hint, icon: Icon, wide }) => (
          <button
            key={type}
            type="button"
            className={`wb-legacy-tool ${wide ? "is-wide" : ""}`}
            title={`${hint}（在对话页中打开）`}
            onClick={() => openLegacyOverlay(type)}
          >
            <span className="wb-legacy-tool-icon">
              {type === "openSettings" ? <ApiIcon size={13} /> : <Icon size={13} />}
            </span>
            <span>{label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
