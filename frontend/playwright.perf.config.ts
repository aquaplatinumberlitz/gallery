import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.VITE_PORT ?? "5173");
const baseURL = process.env.GALLERY_BASE_URL ?? `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./tests/e2e/perf",
  outputDir: process.env.GALLERY_PLAYWRIGHT_OUTPUT_DIR ?? "test-results/perf-playwright",
  retries: 0,
  workers: 1,
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  reporter: [
    [
      "html",
      {
        open: "never",
        outputFolder: process.env.GALLERY_PLAYWRIGHT_REPORT_DIR ?? "playwright-report/perf",
      },
    ],
  ],
  webServer: {
    command: `corepack pnpm exec vite preview --host 127.0.0.1 --port ${port}`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 30_000,
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        baseURL,
        launchOptions: {
          args: ["--ignore-certificate-errors"],
        },
      },
    },
  ],
});
