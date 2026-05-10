import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: true,
    allowedHosts: "all",
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
