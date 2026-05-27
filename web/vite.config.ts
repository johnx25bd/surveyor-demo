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
    // maplibre-gl is inherently ~800KB; it's isolated in its own lazy chunk, so raise the warning
    // threshold above it rather than chasing a number we can't move without dropping the map library.
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      // Split the heavy, rarely-changing libraries into their own chunks so they cache across
      // deploys. MapPane is also lazy-loaded (see App.tsx), so maplibre stays off the initial load.
      output: {
        manualChunks: {
          maplibre: ["maplibre-gl"],
          markdown: ["react-markdown", "remark-gfm"],
        },
      },
    },
  },
});
