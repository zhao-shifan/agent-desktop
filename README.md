# Aria · 智能体桌面版

一个**零依赖、单文件夹、开箱即用**的 AI 智能体网页应用。电脑、手机、平板都能用，填入任意 OpenAI 兼容 API 即可开始对话，支持文件问答（Word / Excel / PPT / PDF / TXT / 代码）。

![Python](https://img.shields.io/badge/Python-3.8+-blue) ![License](https://img.shields.io/badge/License-MIT-green)

## ✨ 功能

- 💬 **窗口式流式对话** — 逐字输出，Markdown / 代码块渲染，多轮上下文记忆
- 📁 **文件问答** — 拖入或上传文档，直接针对内容提问
- 🔌 **任意 OpenAI 兼容接口** — DeepSeek / OpenAI / 通义 / Kimi / GLM / Ollama 本地模型，填 Key 即用
- 📱 **手机扫码使用** — 局域网内手机扫码打开，可「添加到主屏幕」当 App 用
- 🕘 **多会话管理** — 历史对话本地保存，随时切换
- 🎨 **颗粒质感 UI** — 深色玻璃拟态界面，应用名称可自定义

## 🚀 一键安装

### Windows

1. 安装 [Python 3.8+](https://www.python.org/downloads/)（安装时勾选 **Add to PATH**）
2. 下载本仓库（绿色按钮 Code → Download ZIP，解压）
3. 双击 **`启动智能体.bat`** —— 完成！浏览器会自动打开

> 可选：`pip install pypdf` 以支持 PDF 文件解析（Word/Excel/PPT 无需额外安装）

### macOS / Linux

```bash
pip install pypdf          # 可选，PDF 支持
python3 server.py          # 启动
# 打开 http://127.0.0.1:8765
```

## 📱 手机端使用

1. 手机与电脑连接**同一个 WiFi**
2. 打开电脑端页面，点左下角 **「📱 手机扫码使用」**
3. 用手机相机扫码即可打开（也可手动输入显示的地址）
4. 建议：手机浏览器菜单 → **添加到主屏幕**，之后就像独立 App 一样全屏使用

## 🆓 完全免费方案（Ollama 本地模型）

不想花钱买 API？用 [Ollama](https://ollama.com) 在电脑上跑免费开源模型：

```bash
# 1. 安装 Ollama 后拉取模型（一次即可）
ollama pull qwen3:8b

# 2. 启动智能体，设置里选「Ollama 免费·本机」预设，不用填 Key
```

手机也能通过局域网用电脑的 Ollama（选「Ollama 免费·手机访问电脑」预设，把地址里的 IP 换成你电脑的局域网 IP）。

## ❓ FAQ

**有上下文记忆吗？**
有。同一会话内的全部历史都会作为上下文发给模型；切换/新建会话即开启新上下文。历史对话保存在浏览器本机。

**我的 API Key 安全吗？**
Key 只保存在你自己浏览器的 localStorage 里，请求由你本机的 server.py 直接转发给模型服务商，不经过任何第三方服务器。

**支持哪些模型？**
任何提供 OpenAI 兼容 `/v1/chat/completions` 接口的服务都可以。

## 📂 目录结构

```
agent-desktop/
├── server.py          # 本地服务（零第三方依赖）
├── index.html         # 前端界面（单文件）
├── qrcode.js          # 二维码库（MIT）
└── 启动智能体.bat       # Windows 一键启动
```

## License

MIT
