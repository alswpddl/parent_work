import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 개발 중에는 /api 요청을 로컬 FastAPI(8000)로 넘긴다.
// 배포(Vercel)에서는 VITE_API_BASE_URL 로 Render 주소를 직접 부른다.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Codespaces 는 https://…-5173.app.github.dev 주소로 들어오므로 그 주소를 허용
    allowedHosts: [".app.github.dev", "localhost"],
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
