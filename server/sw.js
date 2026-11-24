/* 小凡智能体 Service Worker
   目标：离线也能打开界面（对话本身仍需要网络 + API Key），并让「添加到主屏幕」成为真正的 App。
   策略：
   - 界面外壳（html/js/css/图标）precache，之后 stale-while-revalidate
   - /api/* 一律走网络，不缓存（对话、文件解析不能拿旧结果）
   - 壁纸大图 cache-first + 后台更新
*/
const VERSION = "xfan-v8-min";   // v8: 移除产物/终端弹窗，仅保留右侧画布自动预览
const SHELL_CACHE = VERSION + "-shell";
const IMG_CACHE = VERSION + "-img";
const SHELL = [
  "./",
  "./index.html",
  "./manifest.json",
  "./qrcode.js",
  "./mcp_catalog.js",
  "./official_skills.js",
  "./marked.min.js",
  "./purify.min.js",
  "./html-docx.js",
  "./mammoth.min.js",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-maskable-512.png",
  "./icons/apple-touch-icon-180.png",
  "./icons/favicon.ico",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches
      .open(SHELL_CACHE)
      // 单个文件缺失不应让整个安装失败
      .then((c) => Promise.allSettled(SHELL.map((u) => c.add(new Request(u, { cache: "reload" })))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // 模型 API 等跨域请求不拦
  if (url.pathname.includes("/api/")) return;      // 本地服务接口始终走网络

  // 壁纸：先给缓存，同时后台更新
  if (url.pathname.includes("/wallpapers/")) {
    e.respondWith(
      caches.open(IMG_CACHE).then(async (cache) => {
        const hit = await cache.match(req);
        const net = fetch(req)
          .then((res) => {
            if (res && res.ok) cache.put(req, res.clone());
            return res;
          })
          .catch(() => hit);
        return hit || net;
      })
    );
    return;
  }

  // 导航请求：网络优先，断网回退到缓存的界面，保证离线能打开
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(SHELL_CACHE).then((c) => c.put(req, copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match(req).then((hit) => hit || caches.match("./index.html")))
    );
    return;
  }

  // 其它静态资源：缓存优先 + 后台更新
  e.respondWith(
    caches.open(SHELL_CACHE).then(async (cache) => {
      const hit = await cache.match(req);
      const net = fetch(req)
        .then((res) => {
          if (res && res.ok) cache.put(req, res.clone());
          return res;
        })
        .catch(() => hit);
      return hit || net;
    })
  );
});
