import { chromium } from "@playwright/test";

const baseUrl = "http://127.0.0.1:4800";
const browser = await chromium.launch({ args: ["--lang=en-US"] });
const page = await browser.newPage();

page.on("pageerror", (e) => console.log("PAGEERROR:", e.message.slice(0, 300)));
page.on("console", (m) => {
  if (m.type() === "error") console.log("CONSOLE.ERR:", m.text().slice(0, 300));
});
page.on("response", (r) => {
  if (r.url().includes("/api/")) console.log("API:", r.status(), r.url().replace(baseUrl, ""));
});

await page.addInitScript(() => {
  localStorage.setItem("gallery-active-library-id", "1");
  localStorage.setItem("gallery-active-import-path-id", "10");
  localStorage.setItem("gallery-sort-preference", JSON.stringify({ field: "name", order: "asc" }));
});

await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(4000);
const enter = page.getByRole("button", { name: /enter gallery/i });
console.log("enter visible:", await enter.isVisible().catch(() => "ERR"));
if (await enter.isVisible().catch(() => false)) {
  await enter.click();
  await page.waitForTimeout(2500);
}
const album = page.getByText("a1111", { exact: false }).first();
let found = false;
try { await album.waitFor({ state: "visible", timeout: 15000 }); found = true; } catch {}
console.log("a1111 visible =", found);
if (!found) {
  const body = await page.locator("body").innerText().catch((e) => "ERR " + e);
  console.log("BODY:", body.slice(0, 500));
}
await browser.close();
