import { expect, test, type Page } from "./helpers/monitorErrors";

const baseUrl = process.env.GALLERY_BASE_URL ?? "http://localhost:5173";
const imagePath = "/gallery-library-inspector-test/comfyui/ancient-door.png";
const png1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/luz4nQAAAABJRU5ErkJggg==",
  "base64"
);

async function installStubbedInspector(page: Page) {
  const requests: string[] = [];

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    requests.push(`${url.pathname}?${url.searchParams.toString()}`);

    if (url.pathname === "/api/library/inspector") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          root: "/gallery-library-inspector-test",
          scope: url.searchParams.get("scope") ?? "all",
          query: url.searchParams.get("q") ?? "",
          limit: Number(url.searchParams.get("limit") ?? 200),
          total_indexed: 1,
          returned: 1,
          truncated: false,
          sort: "mtime_desc",
          rows: [
            {
              path: imagePath,
              name: "ancient-door.png",
              folder: "/gallery-library-inspector-test/comfyui",
              relative_path: "comfyui",
              mtime: 1770000000,
              width: 1024,
              height: 1536,
              model: "SDXL",
              tool: "ComfyUI",
              sampler: "DPM++ 2M",
              seed: "123456",
              prompt_preview: "cinematic warm light, old wooden door, dust particles...",
              has_prompt: true,
              has_negative: true,
              has_lora: true,
              lora_count: 2,
              lora_preview: "door-detail, warm-light",
              metadata_detail_available: true,
            },
          ],
        }),
      });
      return;
    }

    if (url.pathname === "/api/library/inspector/metadata") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          path: imagePath,
          prompt: "cinematic warm light, old wooden door, dust particles, detailed wood grain",
          negative_prompt: "bad hands, watermark",
          raw_metadata: null,
          model: "SDXL",
          tool: "ComfyUI",
          sampler: "DPM++ 2M",
          seed: "123456",
          width: 1024,
          height: 1536,
          mtime: 1770000000,
          loras: [
            { name: "door-detail", resource_hash: "abc123", weight: 0.8 },
            { name: "warm-light", resource_hash: "def456", weight: 0.6 },
          ],
          resources: [],
          metadata_detail_available: true,
        }),
      });
      return;
    }

    if (["/api/thumbnail", "/api/preview", "/api/image"].includes(url.pathname)) {
      await route.fulfill({ contentType: "image/png", body: png1x1 });
      return;
    }

    if (url.pathname === "/api/landing-pages") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify([]) });
      return;
    }

    await route.fulfill({ contentType: "application/json", body: "{}" });
  });

  return requests;
}

test.describe("LibraryInspector", () => {
  test.use({ viewport: { width: 1366, height: 900 } });

  test("renders metadata route and fetches prompt detail on demand", async ({ page }) => {
    const requests = await installStubbedInspector(page);

    await page.goto(`${baseUrl}/metadata`, { waitUntil: "domcontentloaded" });

    await expect(page.getByRole("heading", { name: "Library Inspector" })).toBeVisible();
    const metadataButton = page.getByRole("link", { name: /Metadata/ });
    await expect(metadataButton).toHaveAttribute("aria-current", "page");

    await expect(page.getByText("ancient-door.png")).toBeVisible();
    await expect(page.getByText("SDXL")).toBeVisible();
    await expect(page.getByText("LoRA 2")).toBeVisible();
    await expect(page.getByText("123456")).toBeVisible();

    const promptTrigger = page.getByText("cinematic warm light, old wooden door, dust particles...");
    await expect(promptTrigger).toBeVisible();
    await promptTrigger.click();

    await expect(page.getByText("detailed wood grain")).toBeVisible();
    await expect(page.getByText("bad hands, watermark")).toBeVisible();
    expect(requests.some((request) => request.startsWith("/api/library/inspector/metadata?"))).toBeTruthy();

    await expect(page.locator(".col-prompt .long-text-trigger").first()).toBeVisible();
    await expect(page.locator(".col-path .long-text-preview").first()).toBeVisible();
  });
});
