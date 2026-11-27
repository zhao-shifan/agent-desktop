/**
 * 工作台外部配置（不需要重新构建，改完刷新页面即可）。
 *
 * chat  —— 旧聊天 HTML 模板（iframe 嵌入，sendMsg / SSE / 会话分支全部沿用旧页）
 * agent —— 旧 Agent 配置 HTML（点击左侧 Agent 节点时加载，不会自动生成表单）
 * api   —— 旧 API 配置 HTML（点击左侧 API 节点时加载，不会自动生成表单）
 *
 * 默认约定：
 *   public/legacy/chat.html
 *   public/legacy/agent-config.html
 *   public/legacy/api-config.html
 *
 * 也可以直接指向已有的线上/本地地址，例如：
 *   chat: 'http://127.0.0.1:8765/'
 * 注意：跨域 iframe 无法共享会话桥，只建议同源地址。
 */
window.__WORKBENCH_CONFIG__ = {
  chat: "/legacy/chat.html",
  agent: "/legacy/agent-config.html",
  api: "/legacy/api-config.html",
  samplesBase: "/samples",
  // 可选：接入真实 PTY 的 WebSocket 地址；留空则终端为本地演示模式
  terminalWs: "",
};
