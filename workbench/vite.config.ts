import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 工作台与旧版服务（server.py，8765）同源部署时，/api 会自然代理；
// 开发期由 Vite 代理到本机 8765，方便旧聊天页在 iframe 里直接调用 SSE。
export default defineConfig({
  plugins: [react()],
  appType: "mpa",
  server: {
    // 必须显式绑 127.0.0.1：Vite 默认绑 localhost，在 Windows 上只监听 [::1]（IPv6），
    // 浏览器按 IPv4 打开 127.0.0.1:5276 / localhost:5276 会直接 ERR_CONNECTION_REFUSED。
    // 项目其它地方（server.py、vite 代理 target、启动脚本）统一用 127.0.0.1。
    host: "127.0.0.1",
    port: 5276,
    strictPort: true,
    watch: {
      // 某些编辑器/杀软会短暂锁住临时目录，chokidar 在 Windows 上会抛 EBUSY；
      // 忽略这些临时文件，避免开发服务器被无关文件拖崩。
      ignored: ["**/*.tmpdir/**", "**/*.tmp"],
    },
    proxy: {
      "/api": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/v1": { target: "http://127.0.0.1:8765", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    chunkSizeWarningLimit: 2000,
  },
  preview: {
    host: "127.0.0.1",
    port: 5276,
    proxy: {
      "/api": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/v1": { target: "http://127.0.0.1:8765", changeOrigin: true },
    },
  },
});
