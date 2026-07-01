import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:54014",
      "/auth": "http://localhost:54014",
      "/health": "http://localhost:54014",
    },
  },
});
