import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    port: 5174,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        configure: (proxy) => {
          const token = process.env.EXECUTION_AUTH_TOKEN;
          // This development-server-only bridge keeps the operator token out of
          // React code, browser storage, and network requests issued by the browser.
          if (token) proxy.on("proxyReq", (request) => request.setHeader("Authorization", `Bearer ${token}`));
        },
      },
    },
  },
});
