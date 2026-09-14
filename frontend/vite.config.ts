import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: true,
    allowedHosts: "all",
    // Windows + Docker 바인드 마운트에서는 inotify 가 안 먹어 파일 변경이
    // 감지되지 않는다 → 폴링으로 HMR 보장 (코드 수정이 브라우저에 안 뜨던 문제)
    watch: { usePolling: true, interval: 300 },
    proxy: {
      "/api": { target: "http://backend:8000", changeOrigin: true },
      "/ws":  { target: "ws://backend:8000", ws: true },
    },
  },
  build: {
    outDir: "dist",
    chunkSizeWarningLimit: 2000,
    rollupOptions: {
      output: {
        manualChunks: {
          three:  ["three"],
          r3f:    ["@react-three/fiber","@react-three/drei"],
          motion: ["framer-motion"],
          vendor: ["react","react-dom","react-router-dom","zustand","axios"],
        },
      },
    },
  },
});
