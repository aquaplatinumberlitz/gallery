import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [tailwindcss(), vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/__tests__/**/*.test.ts"],
    exclude: ["node_modules/**", "dist/**", "tests/**", "src/debug/**"],
    testTimeout: 10000,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    coverage: {
      provider: "v8",
      reporter: ["text", "text-summary", "html", "lcov", "json-summary"],
      reportsDirectory: "coverage/vitest",
      include: ["src/**/*.{ts,vue}"],
      exclude: [
        "src/debug/**",
        "src/**/*.test.ts",
        "src/test/**",
        "src/**/*.d.ts",
        "src/main.ts",
        "src/App.vue",
        "src/**/*.spec.ts",
      ],
      thresholds: {
        statements: 0,
        branches: 0,
        functions: 0,
        lines: 0,
      },
    },
  },
});
