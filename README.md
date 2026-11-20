# 小凡智能体（XiaoFan Agent）

一个**零依赖、单文件夹、开箱即用**的 AI 智能体应用。桌面、手机、平板全平台通用：填入任意 OpenAI 兼容 API（或使用免费模型）即可开始对话，支持文件问答、图片识别、Word 导出、技能系统。

![Python](https://img.shields.io/badge/Python-3.8+-blue) ![License](https://img.shields.io/badge/License-MIT-green)

## ✨ 功能

- 💬 **流式对话** — 逐字输出、Markdown/表格渲染、多轮上下文、消息复制/分支对话
- 📁 **文件问答** — 拖入 TXT / Markdown / Word / Excel / PPT / PDF / 代码文件
- 🖼️ **图片识别** — 传入图片自动切换视觉模型（如智谱 `glm-4v-flash`，免费）
- 📄 **一键导出 Word** — AI 回复按 **Pandoc + GFM 标准** 转成排版完整的 .docx（表格/代码/列表全支持）
- 🧩 **技能系统** — 内置 8 大技能（论文/报告/PPT/文献精读/翻译/代码/数据/文案），支持导入 Claude Skills 规范的 .zip/.md 技能包、自定义技能
- 🎨 **10 套主题** — 每套配色带专属动态背景（流星/气泡/极光/萤火虫/樱花…），深浅色都有
- 📱 **全平台通用** — 电脑服务模式 + 手机独立模式（同一套代码自动识别）
- 🔌 **11 家服务商预设** — 每家带「三步获取 Key」图文引导和官网直达链接
- 🔐 **Key 独立管理** — 各供应商 Key 分开保存、切换自动带出、保存前真实校验

## 🚀 快速开始

### Windows

1. 安装 [Python 3.8+](https://www.python.org/downloads/)（勾选 **Add to PATH**）
2. 下载本仓库（Releases 里的 ZIP，解压）
3. 双击 **`启动智能体.bat`** —— 浏览器自动打开

> 打包成 exe 时注意：单文件 exe 要放在**纯英文路径**（如 `D:\XiaoFan`）。放在中文目录（如 `D:\桌面版agent`）下，PyInstaller 解压临时文件会失败，双击没反应。

### macOS / Linux

```bash
pip install pypdf pypandoc-binary   # 可选：PDF 支持 + Word 导出
python3 server.py
```

## 📱 手机使用

两种方式：

**方式 A · 局域网互联**（电脑开机时）
电脑页面 → 「📱 手机扫码使用」→ 手机扫码打开，可「添加到主屏幕」当 App。

**方式 B · 完全独立**（无需电脑）
把 `index.html` 发到手机（微信/QQ 传给自己）→ 浏览器打开 → 添加到主屏幕。
独立模式直连 API，DeepSeek / OpenRouter 等支持跨域的平台可用。

## 📲 装成 App

**PWA（推荐，一个网页就是 App）**
- 桌面：Chrome 打开 `http://127.0.0.1:8765` → 地址栏右侧「安装」
- 手机：需要 https 才能安装，用 GitHub Pages 部署后打开链接 → 「添加到主屏幕」
- 装好后是独立图标、全屏无地址栏，界面可离线打开（对话仍需网络 + Key）

**APK（安卓真 App）**
- 壳工程在 `mobile/`（Capacitor），图标在 `mobile/android-icons/`
- 打包走 `.github/workflows/build-apk.yml`，云端出 `app-debug.apk` 产物
- 也可以本地打：`cd mobile && npm install && npm run build:www && npx cap add android && cd android && ./gradlew assembleDebug`

## 🆓 完全免费方案

| 模型 | 说明 |
|---|---|
| `glm-4-flash` | 智谱，免费不限量，日常首选 |
| `glm-5.3-flash` | 智谱新一代，带深度思考 |
| `glm-4v-flash` | 智谱视觉模型，看图 |
| Ollama 本地 | 任意开源模型，完全离线 |

注册 [open.bigmodel.cn](https://open.bigmodel.cn) → API 密钥 → 复制 → 粘贴，完事。

## ❓ FAQ

**有上下文记忆吗？** 有。同一会话全部历史作为上下文，支持分支对话。
**Key 安全吗？** 只存你设备本地，请求由本机直连模型服务商。
**智谱为什么不显示模型列表？** 该平台不提供列表接口，手动填模型名即可（预设已填好）。

## 📂 目录结构

```
agent-desktop/
├── server.py        # 本地服务（零第三方依赖，可选装 pypdf/pypandoc 增强功能）
├── index.html       # 统一前端（电脑/手机同一套代码）
├── qrcode.js        # 二维码库（MIT）
├── official_skills.js  # 官方技能库
├── manifest.json    # PWA 清单
├── sw.js            # Service Worker（离线外壳）
├── icons/           # PWA / 手机图标（192 / 512 / maskable / apple-touch）
├── icon.ico         # Windows 应用图标（多尺寸）
├── make_icon.py     # 图标生成器（改一次出全套）
├── mobile/          # Capacitor 壳工程 + 安卓图标（打 APK 用）
└── 启动智能体.bat    # Windows 一键启动
```

## License

MIT
