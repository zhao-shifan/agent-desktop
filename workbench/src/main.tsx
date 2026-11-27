import { createRoot } from "react-dom/client";
import "dockview-react/dist/styles/dockview.css";
import "@xterm/xterm/css/xterm.css";
import "react-photo-view/dist/react-photo-view.css";
import "./styles/workbench.css";
import "./styles/dockview-overrides.css";
import "./styles/previews.css";
import App from "./App";
import { restoreWorkbenchTheme } from "./lib/theme";

restoreWorkbenchTheme();

const container = document.getElementById("root");
if (!container) throw new Error("缺少 #root 节点");

// 有意不使用 StrictMode：旧聊天 iframe、xterm、docx-preview 在开发期重复挂载会重复初始化。
createRoot(container).render(<App />);
