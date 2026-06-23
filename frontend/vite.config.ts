import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发时把 /api、/amiba 代理到 FastAPI 后端（9100，避免与 worktime 的 8000 冲突）。
const BACKEND = process.env.NESTING_BACKEND || "http://localhost:9100";
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: BACKEND,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
      // 阿米巴对接端点（/amiba/*）原样转发，不剥前缀
      "/amiba": { target: BACKEND, changeOrigin: true },
    },
  },
});
