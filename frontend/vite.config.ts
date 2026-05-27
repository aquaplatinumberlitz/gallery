import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const DEV_PORT = Number(process.env.VITE_PORT) || 5173;
const API_TARGET = process.env.VITE_API_URL || "http://localhost:4180";

export default defineConfig({
  plugins: [vue()],
  server: {
    host: "127.0.0.1",
    port: DEV_PORT,
    strictPort: true,
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
});
