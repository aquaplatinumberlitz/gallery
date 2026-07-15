import { test as base } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const NYC_OUTPUT = path.resolve(".nyc_output");

export interface MonitoredErrors {
  pageErrors: string[];
  consoleErrors: string[];
  vueWarnings: string[];
  allowConsoleError: (pattern: string) => void;
}

export const test = base.extend<{
  monitoredErrors: MonitoredErrors;
  allowedConsoleErrorPatterns: string[];
}>({
  allowedConsoleErrorPatterns: [[], { option: true }],
  monitoredErrors: [
    async ({ page, allowedConsoleErrorPatterns }, use) => {
      const failedResponses: string[] = [];
      const allowedPatterns = [...allowedConsoleErrorPatterns];
      const monitored: MonitoredErrors = {
        pageErrors: [],
        consoleErrors: [],
        vueWarnings: [],
        allowConsoleError: (pattern: string) => allowedPatterns.push(pattern),
      };

      page.on("pageerror", (err) => {
        monitored.pageErrors.push(`[PAGE_ERROR] ${err.stack || err.message}`);
      });

      page.on("console", (msg) => {
        if (msg.type() === "error") {
          monitored.consoleErrors.push(`[CONSOLE_ERROR] ${msg.text()}`);
        } else if (msg.type() === "warning" && msg.text().includes("[Vue warn]")) {
          monitored.vueWarnings.push(`[VUE_WARN] ${msg.text()}`);
        }
      });

      // HTTP failures are diagnostic context, not a universal failure signal:
      // fault-injection specs intentionally exercise 4xx/5xx responses.
      page.on("response", (response) => {
        if (response.status() >= 400) {
          failedResponses.push(`${response.status()} ${response.request().method()} ${response.url()}`);
        }
      });

      // Start JS coverage collection when coverage mode is enabled
      if (process.env.VITE_COVERAGE === "true") {
        await page.coverage.startJSCoverage({ resetOnNavigation: false });
      }

      await use(monitored);

      // Stop JS coverage and save data after each test
      if (process.env.VITE_COVERAGE === "true") {
        await page.coverage.stopJSCoverage();
        const istanbulCoverage = await page.evaluate<Record<string, unknown> | undefined>(
          () => (window as unknown as { __coverage__?: Record<string, unknown> }).__coverage__,
        );
        if (istanbulCoverage) {
          fs.mkdirSync(NYC_OUTPUT, { recursive: true });
          const filename = `coverage-${Date.now()}-${Math.random().toString(36).slice(2, 8)}.json`;
          fs.writeFileSync(path.join(NYC_OUTPUT, filename), JSON.stringify(istanbulCoverage));
        }
      }

      if (monitored.pageErrors.length > 0) {
        throw new Error("Unhandled page errors detected:\n" + monitored.pageErrors.join("\n"));
      }
      const unexpectedConsoleErrors = monitored.consoleErrors.filter(
        (message) => !allowedPatterns.some((pattern) => message.includes(pattern)),
      );
      if (unexpectedConsoleErrors.length > 0) {
        const responseContext =
          failedResponses.length > 0 ? `\nHTTP failure context:\n${failedResponses.join("\n")}` : "";
        throw new Error("Unhandled console errors detected:\n" + unexpectedConsoleErrors.join("\n") + responseContext);
      }
      if (monitored.vueWarnings.length > 0) {
        throw new Error("Vue warnings detected:\n" + monitored.vueWarnings.join("\n"));
      }
    },
    { auto: true },
  ],
});

export { expect } from "@playwright/test";
