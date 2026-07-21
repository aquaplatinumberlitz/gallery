import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

const configuredMaxWorkers = Number(process.env.VITEST_MAX_WORKERS ?? "3");
const maxWorkers = Number.isFinite(configuredMaxWorkers) && configuredMaxWorkers > 0 ? configuredMaxWorkers : 3;

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
    fileParallelism: true,
    maxWorkers,
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
        // Measured 2026-07-15 baseline, rounded down to whole-percent
        // ratchets so direct coverage runs cannot silently regress.
        statements: 68,
        branches: 57,
        functions: 62,
        lines: 70,
      },
    },
  },
});
