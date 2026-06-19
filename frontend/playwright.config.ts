import { defineConfig, devices } from "@playwright/test";

const devPort = Number(process.env.VITE_PORT ?? "5173");
const baseUrl = process.env.GALLERY_BASE_URL ?? `http://127.0.0.1:${devPort}`;

export default defineConfig({
  testDir: "./tests/e2e",
  retries: Number(process.env.PLAYWRIGHT_RETRIES ?? (process.env.CI ? "1" : "0")),
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  webServer: {
    command:
      process.env.VITE_COVERAGE === "true"
        ? `VITE_COVERAGE=true corepack pnpm exec vite --host 127.0.0.1 --port ${devPort}`
        : `corepack pnpm exec vite --host 127.0.0.1 --port ${devPort}`,
    url: baseUrl,
    reuseExistingServer: true,
    timeout: 30_000,
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: {
          args: ["--ignore-certificate-errors"],
        },
      },
    },
  ],
});
