import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies BFF + WebSocket to app3 so the SPA uses same-origin relative URLs
// (nginx does the same in production — see nginx.conf).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/bff": "http://localhost:8082",
      "/realtime": { target: "ws://localhost:8082", ws: true },
    },
  },
});
