import { defineConfig, type Plugin } from "vite";
import vue from "@vitejs/plugin-vue";

const DEV_PORT = Number(process.env.VITE_PORT) || 5173;
const API_TARGET = process.env.VITE_API_URL || "http://localhost:4180";

// Plugin to remove @vite/client injection since ws:false alone doesn't prevent it
function noViteClient(): Plugin {
  return {
    name: "no-vite-client",
    enforce: "post",
    transformIndexHtml(html) {
      return html.replace(
        /<script type="module" src=["'].*\/@vite\/client["']><\/script>\n*/,
        "",
      );
    },
  };
}

export default defineConfig({
  plugins: [vue(), noViteClient()],
  server: {
    host: "127.0.0.1",
    port: DEV_PORT,
    strictPort: true,
    hmr: false,
    ws: false,
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
});
