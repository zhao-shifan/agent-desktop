# 工作台接入说明

## 1. 旧聊天页

把旧 `index.html` 复制到 `public/legacy/chat.html`（`pnpm sync:legacy` 会自动完成），
工作台用 iframe 嵌入中间栏，只通过 bridge 传递会话列表与选中会话。

- `sendMsg` / SSE / 会话分支：保持原样
- 侧栏、旧右侧预览：在嵌入副本里隐藏
- 文件预览：由工作台 dockview 接管

## 2. 旧 Agent / API 配置页

把你的旧 HTML 放到：

- `public/legacy/agent-config.html`
- `public/legacy/api-config.html`

点击左侧对应节点时，中间栏直接加载该文件，不生成任何新表单。

## 3. 外部 API

```ts
window.xiaofanWorkbench.openPreview({ path, url, name });
window.xiaofanWorkbench.openTerminal();
window.xiaofanWorkbench.closeTab(id);
```

## 4. 样式

所有颜色来自 `src/styles/workbench.css` 顶部的 `--wb-*` 变量；
dockview、xterm、diff2html、photo-view 的外观均被覆盖，不加载第三方主题。
