import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  webServer: {
    command: process.env.VITE_COVERAGE === "true"
      ? "VITE_COVERAGE=true pnpm exec vite --host 127.0.0.1 --port 5173"
      : "pnpm exec vite --host 127.0.0.1 --port 5173",
    url: "http://127.0.0.1:5173",
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
