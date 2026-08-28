import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // 개발 중 /api 요청을 FastAPI(8000)로 넘긴다 → CORS 신경 안 써도 됨
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
