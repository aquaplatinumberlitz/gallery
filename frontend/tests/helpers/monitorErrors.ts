import { test as base } from "@playwright/test";

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

      await use(monitored);

      if (monitored.pageErrors.length > 0) {
        throw new Error("Unhandled page errors detected:\n" + monitored.pageErrors.join("\n"));
      }
    },
    { auto: true },
  ],
});

export { expect } from "@playwright/test";
