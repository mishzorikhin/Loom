import { defineConfig } from "vite";

// Страница собирается в web/dist, её отдаёт сервер (python3 -m tsim.server).
// В разработке npm run dev проксирует сокет на запущенный сервер.
export default defineConfig({
  server: {
    port: 5180,
    proxy: {
      "/ws": { target: "ws://127.0.0.1:8500", ws: true },
      "/api": "http://127.0.0.1:8500",
    },
  },
  build: { target: "es2022", chunkSizeWarningLimit: 1500 },
});
