import { test as base } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const NYC_OUTPUT = path.resolve(".nyc_output");

export interface MonitoredErrors {
  pageErrors: string[];
  consoleErrors: string[];
  apiErrors: string[];
}

export const test = base.extend<{
  monitoredErrors: MonitoredErrors;
}>({
  monitoredErrors: [
    async ({ page }, use) => {
      const monitored: MonitoredErrors = {
        pageErrors: [],
        consoleErrors: [],
        apiErrors: [],
      };

      page.on("pageerror", (err) => {
        monitored.pageErrors.push(`[PAGE_ERROR] ${err.message}`);
      });

      page.on("console", (msg) => {
        if (msg.type() === "error") {
          monitored.consoleErrors.push(`[CONSOLE_ERROR] ${msg.text()}`);
        }
      });

      page.on("response", (res) => {
        if (res.status() >= 500 && res.url().includes("/api/")) {
          monitored.apiErrors.push(`[API_ERROR] ${res.status()} ${res.url()}`);
        }
      });

      // Start JS coverage collection when coverage mode is enabled
      if (process.env.VITE_COVERAGE === "true") {
        await page.coverage.startJSCoverage({ resetOnNavigation: false });
      }

      await use(monitored);

      // Stop JS coverage and save data after each test
      if (process.env.VITE_COVERAGE === "true") {
        const coverage = await page.coverage.stopJSCoverage();
        const istanbulCoverage = await page.evaluate(() => (window as any).__coverage__);
        if (istanbulCoverage) {
          fs.mkdirSync(NYC_OUTPUT, { recursive: true });
          const filename = `coverage-${Date.now()}-${Math.random().toString(36).slice(2, 8)}.json`;
          fs.writeFileSync(path.join(NYC_OUTPUT, filename), JSON.stringify(istanbulCoverage));
        }
      }

      if (monitored.pageErrors.length > 0) {
        throw new Error("Unhandled page errors detected:\n" + monitored.pageErrors.join("\n"));
      }
    },
    { auto: true },
  ],
});

export { expect } from "@playwright/test";
