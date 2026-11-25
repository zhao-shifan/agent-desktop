# 小凡智能体 · Web 前端（React + assistant-ui）

基于 [assistant-ui](https://www.assistant-ui.com) 原语组件 + Tailwind v4 的三栏智能体前端，
对接**小凡自研 LangGraph 后端**（仓库根目录 `agent_graph.py` + `server.py`）。

> 组件自带的默认后端请求逻辑已全部弃用：所有请求经 `src/lib/backend.ts`
> 重写，直连后端自定义 SSE 协议（token 级流式 / 工具卡片 / 人工审核 interrupt）。

## 功能

- ✅ 三栏布局：左（会话/技能/MCP/模型/Key 配置）· 中（流式对话）· 右（docx-preview Word 预览）
- ✅ 响应式：移动端只显示对话区，左侧栏变抽屉、右侧预览变弹窗，审核弹窗全屏
- ✅ token 级流式（打字机）+ 思考过程折叠条 + 工具调用卡片
- ✅ 每次请求携带 `sessionId` → 后端 LangGraph thread_id（检查点/断点续跑）
- ✅ 接口地址/超时全部环境变量化（`.env.example`）
- ⏳ 人工审核确认/拒绝弹窗 UI 已就绪，等待后端 interrupt 事件（阶段3）联调

## 部署

### 0. 前置

- Node.js 20+，包管理器 pnpm（`npm i -g pnpm`）
- 小凡后端已启动：仓库根目录 `启动智能体.bat`（监听 8765）

### 1. 安装依赖

```bash
cd frontend
pnpm install
cp .env.example .env.local   # 按需改 VITE_API_BASE / VITE_API_TIMEOUT
```

### 2. 本地开发

```bash
pnpm dev        # http://localhost:5173
```

开发模式默认走 Vite 代理（`/api → http://127.0.0.1:8765`），免 CORS；
要连别的后端就在 `.env.local` 里配 `VITE_API_BASE`。

### 3. 生产构建

```bash
pnpm build      # 产物在 dist/
pnpm preview    # 本地预览构建产物
```

`dist/` 是纯静态文件，任意静态服务器可托管；
注意 `VITE_API_BASE` 需指向后端实际地址（构建时固化）。

## 技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 构建 | Vite + React 19 + TS | |
| 样式 | Tailwind CSS v4（@tailwindcss/vite） | 响应式前缀 sm:/lg: 控制三栏/抽屉切换 |
| 聊天 UI | assistant-ui 原语（ThreadPrimitive 等） | styled 包与 core 版本不兼容，故用稳定原语自组 |
| Word 预览 | docx-preview | 原选 vue-office 为 Vue 生态无法与 React 共存，功能平替 |
| 状态 | localStorage + 极简事件总线 | 无重量级状态库 |

## 目录结构

```
src/
├── lib/
│   ├── backend.ts      # ★ 唯一后端对接层（SSE 解析，环境变量配置）
│   ├── adapter.ts      # assistant-ui ChatModelAdapter（异步队列桥接 token 流）
│   ├── eventBus.ts     # 工具卡片/审核/思考事件广播
│   └── settings.ts     # 侧边栏配置持久化
├── components/
│   ├── ThreadView.tsx  # 聊天区（原语组装，打字机）
│   ├── Sidebar.tsx     # 左栏：会话/技能/MCP/模型/Key
│   ├── ToolCards.tsx   # 工具调用卡片 + 思考折叠条
│   ├── ReviewDialog.tsx# 人工审核弹窗（确认/拒绝 → /api/resume）
│   └── DocPreview.tsx  # docx-preview 预览（缩放）
└── App.tsx             # 三栏布局 + 响应式切换
```

## 后端接口约定

`POST /api/chat`（SSE），请求体含 `sessionId/baseUrl/apiKey/model/messages/tools...`；
事件：`choices.delta.content`（token）· `choices.delta.reasoning_content`（思考）·
`tool`（工具卡片）· `thinking`（心跳）· `interrupt`（人工审核）。
