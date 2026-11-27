/**
 * 把仓库根目录的“旧版聊天页”同步成工作台中间栏可嵌入的副本。
 *
 * 原则：
 *  - 原文件（../index.html）只读，绝不修改；只复制到 public/legacy/chat.html。
 *  - 复制时仅加两样东西：embed 用的隐藏侧栏 CSS + 与工作台通信的 bridge。
 *  - sendMsg / SSE / 会话分支 / localStorage 全部沿用旧页原逻辑。
 *  - config.local.js（私有 Key）不复制；不复制 service worker。
 *
 * 如果根目录没有 index.html（例如工作台被单独拷走），脚本静默跳过，
 * 工作台会显示“未找到旧聊天页”的插槽提示。
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(appRoot, "..");
const srcHtml = path.join(repoRoot, "index.html");
const outDir = path.join(appRoot, "public", "legacy");
const outHtml = path.join(outDir, "chat.html");

const ASSETS = [  "marked.min.js",
  "mermaid.min.js",
  "echarts.min.js",
  "mammoth.min.js",
  "purify.min.js",
  "qrcode.js",
  "mcp_catalog.js",
  "official_skills.js",
];

function log(msg) {
  console.log(`[sync-legacy] ${msg}`);
}

if (!fs.existsSync(srcHtml)) {
  log(`跳过：未找到 ${srcHtml}`);
  process.exit(0);
}

fs.mkdirSync(outDir, { recursive: true });

let html = fs.readFileSync(srcHtml, "utf8");

// 1) 不直接给 <html> 加 wb-embed：直接打开 chat.html 时应该保留完整旧侧栏。
//    只有被工作台 iframe 嵌入时才加，脚本在 head 里尽早执行，避免闪一下旧侧栏。
html = html.replace(
  "<meta charset=\"UTF-8\">",
  "<meta charset=\"UTF-8\">\n<meta name=\"workbench-legacy\" content=\"chat\">\n<script id=\"wb-embed-mode\">(function(){try{if(window.self!==window.top)document.documentElement.classList.add(\"wb-embed\");}catch(e){document.documentElement.classList.add(\"wb-embed\");}})();</script>",
);

// 3) 旧页的私有配置与缺失脚本不复制，直接去掉引用，避免控制台 404
html = html.replace(/[ \t]*<script src="\.\/config\.local\.js"><\/script>\r?\n/, "");
if (!fs.existsSync(path.join(repoRoot, "mammoth.min.js"))) {
  html = html.replace(/[ \t]*<script src="\.\/mammoth\.min\.js"><\/script>\r?\n/, "");
}

// 3.1) 复制到 /legacy/ 后，旧页的相对健康检查路径会变成 /legacy/api/health。
//      这里只改副本，指向工作台同源的 /api/health，保持旧页“服务端托管”模式。
html = html.replace('fetch("./api/health"', 'fetch("/api/health"');

// 3.1.1) 旧页的壁纸 / 照片卡路径变成 /legacy/wallpapers/...，会 404。
//        壁纸资源由工作台 public/wallpapers 提供，统一改成站点根路径。
html = html.split("./wallpapers/").join("/wallpapers/");

// 3.2) 旧页的 manifest / 图标在 iframe 里没有意义，也会造成 404，副本里直接去掉
html = html
  .replace(/[ \t]*<link rel="manifest"[^>]*>\r?\n?/i, "")
  .replace(/[ \t]*<link rel="icon"[^>]*>\r?\n?/i, "")
  .replace(/[ \t]*<link rel="apple-touch-icon"[^>]*>\r?\n?/i, "");

// 4) 只隐藏“工作台自己负责”的外壳：侧栏、旧右侧预览、背景装饰。
//    聊天区（.main/.chat/.composer）原样保留。
const embedStyle = `
<style id="wb-embed-style">
  /* 中间对话区保留旧页自己的主题底色 / 壁纸 / 动效，只隐藏工作台负责的外壳 */
  html.wb-embed body::before { display: none !important; }
  html.wb-embed .aurora { display: none !important; }
  /* 浅色主题 + 壁纸：壁纸上的暗化层改成浅色薄雾，保证深色文字可读 */
  html.wb-embed body[data-theme^="light"] #customBg .cb-dim,
  html.wb-embed body[data-theme^="light"] #customBg::after {
    background: rgba(250, 248, 242, 0.58) !important;
  }
  html.wb-embed .sidebar, html.wb-embed #sbScrim, html.wb-embed .menu-toggle,
  html.wb-embed .expand-btn, html.wb-embed #canvasPanel { display: none !important; }
  html.wb-embed .app { display: block !important; height: 100% !important; }
  html.wb-embed .main { width: 100% !important; max-width: none !important; height: 100% !important; }
  html.wb-embed .chat { padding-top: 18px !important; }
  html.wb-embed .chat-inner { max-width: 980px !important; }
  html.wb-embed .welcome { padding-top: 7vh !important; }
  html.wb-embed .composer-wrap { padding-bottom: 18px !important; }
  html.wb-embed .scroll-nav, html.wb-embed .msg-nav { right: 10px !important; }
  html.wb-embed #onboardOverlay { display: none !important; }
  html.wb-embed .file-card .fc-btn.fc-wb-open { color: var(--accent2); border-color: var(--accent-dim); }
</style>
`;

// 5) 工作台 ⇄ 旧聊天页 bridge。
//    旧页的 chats / curId / save / openChat / newChat / renderSessions 都是
//    顶层的 let/function，后续 script 可直接按名字访问。
const bridge = `
<script id="wb-chat-bridge">
(function () {
  // 直接打开 /legacy/chat.html 时保持旧页完整 UI，不启用桥、也不强制主题
  var embedded = false;
  try { embedded = window.self !== window.top; } catch (e) { embedded = true; }
  if (!embedded) return;
  var WB = 1;
  var last = "";
  function sessions() {
    try {
      return (chats || []).map(function (c) {
        var msgs = Array.isArray(c.messages) ? c.messages : [];
        return {
          id: c.id,
          title: c.title || "新对话",
          pinned: !!c.pinned,
          messages: msgs.length,
          updatedAt: c.updatedAt || c.time || 0
        };
      });
    } catch (e) { return []; }
  }
  function active() {
    try { return curId || null; } catch (e) { return null; }
  }
  function theme() {
    try { return document.body.dataset.theme || ""; } catch (e) { return ""; }
  }
  function postTheme() {
    try {
      parent.postMessage({ __wb: WB, source: "chat", type: "theme", theme: theme() }, location.origin);
    } catch (e) { /* ignore */ }
  }
  function push() {
    try {
      var payload = JSON.stringify({ sessions: sessions(), activeId: active() });
      last = payload;
      parent.postMessage({ __wb: WB, source: "chat", type: "state", sessions: sessions(), activeId: active() }, location.origin);
    } catch (e) { /* ignore */ }
  }
  function find(id) {
    try { return (chats || []).find(function (c) { return c.id === id; }); } catch (e) { return null; }
  }
  function persist() {
    try { if (typeof save === "function") save(); } catch (e) {}
    try { if (typeof renderSessions === "function") renderSessions(); } catch (e) {}
  }
  addEventListener("message", function (ev) {
    if (ev.source !== parent) return;
    var d = ev.data;
    if (!d || d.__wb !== WB) return;
    try {
      switch (d.type) {
        case "ping":
        case "refresh":
          last = "";
          push();
          rescanFileCards();
          break;
        case "openSession":
          if (typeof openChat === "function") openChat(d.id);
          push();
          break;
        case "newSession":
          if (typeof newChat === "function") newChat();
          push();
          break;
        case "renameSession": {
          var c = find(d.id);
          if (c) {
            c.title = String(d.title || c.title || "新对话");
            persist();
            push();
          }
          break;
        }
        case "deleteSession": {
          var i = (chats || []).findIndex(function (c) { return c.id === d.id; });
          if (i >= 0) {
            chats.splice(i, 1);
            if (curId === d.id && typeof newChat === "function") newChat();
            persist();
            push();
          }
          break;
        }
        case "reorderSessions": {
          var order = Array.isArray(d.ids) ? d.ids : [];
          if (!order.length) break;
          chats.sort(function (a, b) {
            var ia = order.indexOf(a.id), ib = order.indexOf(b.id);
            if (ia < 0) ia = order.length + 1;
            if (ib < 0) ib = order.length + 1;
            return ia - ib;
          });
          persist();
          push();
          break;
        }
        // 以下入口直接打开旧页自己的弹窗/面板
        case "openSettings":
          if (typeof openSettings === "function") openSettings();
          break;
        case "openThemes":
          if (typeof openThemes === "function") openThemes();
          break;
        case "openSkills":
          if (typeof openSkills === "function") openSkills();
          break;
        case "openMcpManager":
          if (typeof openMcpManager === "function") openMcpManager();
          break;
        case "openQR":
          if (typeof openQR === "function") openQR();
          break;
      }
    } catch (err) {
      console.error("[wb-bridge]", err);
    }
  });
  window.__WB_CHAT_BRIDGE__ = { list: sessions, active: active, theme: theme, push: push, dispose: function () {} };
  postTheme();
  try {
    new MutationObserver(postTheme).observe(document.body, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
  } catch (e) {}
  // —— 会话生成文件：上报给工作台，并在卡片上加「在右侧打开」 ——
  function chatIdNow() {
    try { return curId || null; } catch (e) { return null; }
  }
  function fileIdOf(chatId, name) {
    return (chatId || "chat") + ":" + name;
  }
  function postFile(card, idx) {
    var name = card.getAttribute("data-name") || "";
    if (!name) return;
    var chatId = chatIdNow();
    var it = null;
    try { it = idx !== null && typeof fileBlobs !== "undefined" ? fileBlobs[idx] : null; } catch (e) {}
    var ext = extOfName(name);
    var payload = {
      __wb: WB,
      source: "chat",
      type: "file",
      chatId: chatId,
      file: { id: fileIdOf(chatId, name), name: name, ext: ext },
    };
    if (it && it.blob) {
      payload.file.blob = it.blob;
      payload.file.size = it.blob.size;
    }
    try { parent.postMessage(payload, location.origin); } catch (e) {}
  }
  function digitsAt(text, pos) {
    var digits = "";
    while (pos < text.length && text.charAt(pos) >= "0" && text.charAt(pos) <= "9") {
      digits += text.charAt(pos);
      pos += 1;
    }
    return digits;
  }
  function idxOf(card) {
    var html = (card && card.innerHTML) || "";
    var names = ["canvasOpenFile(", "downloadStored(", "previewDoc("];
    for (var i = 0; i < names.length; i += 1) {
      var at = html.indexOf(names[i]);
      if (at >= 0) {
        var digits = digitsAt(html, at + names[i].length);
        if (digits) return parseInt(digits, 10);
      }
    }
    return null;
  }
  function extOfName(name) {
    var dot = String(name || "").lastIndexOf(".");
    return dot >= 0 ? String(name).slice(dot + 1).toLowerCase() : "";
  }
  function announceCard(card) {
    var idx = idxOf(card);
    if (idx === null) { postFile(card, null); return; }
    var ready = null;
    try { ready = fileBlobs[idx]; } catch (e) {}
    if (ready && ready.blob) { postFile(card, idx); return; }
    if (typeof downloadStored === "function") {
      // 刷新 / 分支回放后 blob 丢了：让旧页按消息原文重建一次，再上报
      Promise.resolve()
        .then(function () { return downloadStored(idx, true); })
        .then(function () { postFile(card, idx); })
        .catch(function () { postFile(card, idx); });
      return;
    }
    postFile(card, idx);
  }
  // 父窗口 ping 时重发一遍：iframe 首次加载可能早于父页监听器注册
  function rescanFileCards() {
    try {
      document.querySelectorAll(".file-card").forEach(announceCard);
    } catch (e) {}
  }
  function decorateFileCard(card) {
    if (!card || card.dataset.wbFile === "1") return;
    card.dataset.wbFile = "1";
    var name = card.getAttribute("data-name") || "";
    var chatIdAtCard = chatIdNow();

    var btn = document.createElement("span");
    btn.className = "fc-btn fc-wb-open";
    btn.textContent = "在右侧打开";
    btn.onclick = function (ev) {
      ev.stopPropagation();
      try {
        parent.postMessage(
          { __wb: WB, source: "chat", type: "open-file", fileId: fileIdOf(chatIdAtCard, name) },
          location.origin,
        );
      } catch (e) {}
    };
    card.appendChild(btn);
    announceCard(card);
  }
  function scanFileCards(root) {
    if (!root || root.nodeType !== 1) return;
    if (root.classList && root.classList.contains("file-card")) decorateFileCard(root);
    if (root.querySelectorAll) {
      root.querySelectorAll(".file-card").forEach(decorateFileCard);
    }
  }
  try {
    document.querySelectorAll(".file-card").forEach(decorateFileCard);
    new MutationObserver(function (muts) {
      muts.forEach(function (mutation) {
        mutation.addedNodes.forEach(scanFileCards);
      });
    }).observe(document.body, { childList: true, subtree: true });
  } catch (e) {}

  setInterval(push, 1200);
  addEventListener("load", function () { setTimeout(push, 250); });
  if (document.readyState === "complete") setTimeout(push, 250);
})();
</script>
`;

html = html.replace("</head>", `${embedStyle}\n</head>`);
const bodyClose = html.lastIndexOf("</body>");
html =
  bodyClose >= 0
    ? `${html.slice(0, bodyClose)}${bridge}\n${html.slice(bodyClose)}`
    : `${html}\n${bridge}`;

fs.writeFileSync(outHtml, html, "utf8");
log(`已写入 ${outHtml}`);

let copied = 0;
for (const name of ASSETS) {
  const from = path.join(repoRoot, name);
  if (!fs.existsSync(from)) continue;
  fs.copyFileSync(from, path.join(outDir, name));
  copied++;
}
log(`已复制 ${copied} 个旧页资源到 ${outDir}`);

// 壁纸库：旧页通过 ./wallpapers/... 读取，复制到工作台 public 后用 /wallpapers/... 访问。
// 同时生成 manifest，工作台外壳的「照片漂浮 / 壁纸」不用再依赖后端 /api/wallpapers。
const wallpaperSrc = path.join(repoRoot, "wallpapers");
const wallpaperOut = path.join(appRoot, "public", "wallpapers");
if (fs.existsSync(wallpaperSrc)) {
  fs.cpSync(wallpaperSrc, wallpaperOut, { recursive: true });
  const names = fs.readdirSync(wallpaperOut);
  const ids = names
    .map((name) => /^wp(\d{3})\.jpg$/i.exec(name))
    .filter(Boolean)
    .map((match) => Number(match[1]))
    .sort((a, b) => a - b);
  const cards = names
    .map((name) => /^card(\d{2})\.jpg$/i.exec(name))
    .filter(Boolean)
    .map((match) => Number(match[1]))
    .sort((a, b) => a - b);
  fs.writeFileSync(
    path.join(wallpaperOut, "manifest.json"),
    JSON.stringify({ ids, cards }),
    "utf8",
  );
  log(`已同步壁纸库到 ${wallpaperOut}（${ids.length} 张壁纸 / ${cards.length} 张卡片）`);
}
