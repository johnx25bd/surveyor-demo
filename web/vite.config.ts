import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: Vite serves the app on :5173 and proxies /api to the FastAPI/uvicorn backend on :8000, so the
// browser sees one origin (no CORS) and the SSE stream passes through untouched.
// Build: emits to web/dist, which the FastAPI process mounts at / in production.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
