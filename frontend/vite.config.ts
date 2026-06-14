import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

const DEV_PORT = Number(process.env.VITE_PORT) || 5173;
const API_TARGET = process.env.VITE_API_URL || "http://localhost:4180";

export default defineConfig({
  plugins: [tailwindcss(), vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: "127.0.0.1",
    port: DEV_PORT,
    strictPort: true,
    allowedHosts: ["150.230.56.153"],
    hmr: process.env.VITE_MOBILE_NO_HMR === "1" ? false : undefined,
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
  },
});
