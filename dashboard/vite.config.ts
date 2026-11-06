import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3100,
    strictPort: true,
    proxy: {
      "/api": {
        // 127.0.0.1: Node 17+ đổi localhost sang ::1 trước, mà IPv6 của Docker Desktop hay treo.
        target: "http://127.0.0.1:8100",
        changeOrigin: true,
      },
    },
  },
});
