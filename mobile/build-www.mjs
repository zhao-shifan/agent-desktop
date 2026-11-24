// 把仓库根目录的网页产物收进 mobile/www，供 Capacitor 打包进 APK。
// 不复制 config.local.js（里面是本机私有 Key）。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const out = path.join(here, "www");

const FILES = ["index.html", "qrcode.js", "official_skills.js", "manifest.json", "sw.js",
               "mcp_catalog.js", "marked.min.js", "purify.min.js", "html-docx.js"];
const DIRS = ["icons", "wallpapers"];

fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out, { recursive: true });

for (const f of FILES) {
  const src = path.join(root, f);
  if (!fs.existsSync(src)) throw new Error(`缺少文件: ${f}`);
  fs.copyFileSync(src, path.join(out, f));
}
for (const d of DIRS) {
  fs.cpSync(path.join(root, d), path.join(out, d), { recursive: true });
}

// APK 内资源已经随包更新，Service Worker 只会带来「装上新包还是旧界面」的坑，这里去掉注册。
const indexPath = path.join(out, "index.html");
let html = fs.readFileSync(indexPath, "utf8");
const before = html;
html = html.replace(
  'addEventListener("load", ()=>{ navigator.serviceWorker.register("./sw.js").catch(()=>{}); });',
  '/* APK 内不注册 Service Worker（资源随包更新） */'
);
if (html === before) console.warn("⚠ 未找到 SW 注册语句，可能已被改动");
fs.writeFileSync(indexPath, html);

console.log(`www 已生成: ${FILES.length} 个文件 + ${DIRS.join(", ")}`);
