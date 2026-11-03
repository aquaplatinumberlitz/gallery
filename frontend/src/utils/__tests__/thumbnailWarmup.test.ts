/**
 * Purpose: Protect the album-open thumbnail warm-up: which thumbnails the first viewport will request, and
 * that the preload links use the same URL, `srcset` and `sizes` as the `PhotoCard` `<img>`.
 * Guarantees: a plan only covers rows that start above the viewport bottom, skips videos and images whose
 * 256/512 choice depends on the exact card width, marks the first row high priority, and a link is added once.
 * Run when: Changing `thumbnailWarmup.ts`, `thumbnailSizes.ts`, the grid geometry or the thumbnail `srcset`.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { getThumbnailSrcset, getThumbnailUrl } from "@/services/api";
import { thumbnailSizes } from "../thumbnailSizes";
import {
  planThumbnailWarmup,
  warmThumbnails,
  WARMUP_ALBUM_STRIP_ALLOWANCE,
  WARMUP_HEADER_ALLOWANCE,
  WARMUP_LINK_LIFETIME_MS,
  WARMUP_MAX_TARGETS,
  type WarmupGeometry,
  type WarmupItem,
} from "../thumbnailWarmup";

const item = (index: number, extra: Partial<WarmupItem> = {}): WarmupItem => ({
  path: `/lib/photo-${index}.png`,
  type: "image",
  content_version: `v${index}`,
  width: 1000,
  height: 1000,
  ...extra,
});
const items = (count: number, extra: Partial<WarmupItem> = {}) =>
  Array.from({ length: count }, (_, i) => item(i, extra));

// Mobile: 2 columns of 184 px cards at DPR 2 in a 390x844 viewport, the grid starting at y=100.
const mobile: WarmupGeometry = {
  columns: 2,
  cardWidth: 184,
  rowPitch: 189,
  top: 100,
  viewportHeight: 844,
  devicePixelRatio: 2,
};

describe("planThumbnailWarmup", () => {
  it("covers the rows that start above the viewport bottom, after the header allowance", () => {
    const rows = Math.ceil((844 - (100 + WARMUP_HEADER_ALLOWANCE)) / 189);

    const plan = planThumbnailWarmup(items(60), mobile);

    expect(plan).toHaveLength(rows * 2);
  });

  it("uses the PhotoCard URL, srcset and sizes for each thumbnail", () => {
    const [first] = planThumbnailWarmup([item(7, { width: 1200, height: 800 })], mobile);

    expect(first.href).toBe(getThumbnailUrl("/lib/photo-7.png", 512, "v7"));
    expect(first.imagesrcset).toBe(getThumbnailSrcset("/lib/photo-7.png", "v7"));
    expect(first.imagesizes).toBe(thumbnailSizes(184, 1.5));
  });

  it("marks only the first row high priority", () => {
    const plan = planThumbnailWarmup(items(60), mobile);

    expect(plan.slice(0, 2).map((target) => target.fetchpriority)).toEqual(["high", "high"]);
    expect(plan.slice(2).every((target) => target.fetchpriority === "auto")).toBe(true);
  });

  it("starts fewer rows when the album strip sits above the grid", () => {
    const plain = planThumbnailWarmup(items(60), mobile);
    const withStrip = planThumbnailWarmup(items(60), mobile, { hasFolders: true });

    expect(withStrip.length).toBeLessThan(plain.length);
    const rows = Math.ceil((844 - (100 + WARMUP_HEADER_ALLOWANCE + WARMUP_ALBUM_STRIP_ALLOWANCE)) / 189);
    expect(withStrip).toHaveLength(rows * 2);
  });

  it("never plans more than the item count or the hard cap", () => {
    expect(planThumbnailWarmup(items(3), mobile)).toHaveLength(3);
    const desktop: WarmupGeometry = { ...mobile, columns: 8, cardWidth: 400, rowPitch: 100, viewportHeight: 4000 };
    expect(planThumbnailWarmup(items(200), desktop).length).toBeLessThanOrEqual(WARMUP_MAX_TARGETS);
  });

  it("skips videos and items without a path", () => {
    const plan = planThumbnailWarmup([item(0, { type: "video" }), item(1, { path: "" }), item(2)], mobile);

    expect(plan.map((target) => target.href)).toEqual([getThumbnailUrl("/lib/photo-2.png", 512, "v2")]);
  });

  it("skips an image whose 256/512 choice depends on the exact card width", () => {
    // 3 columns at DPR 2: a 128 px square card needs 256 px, right on the 256w candidate.
    const borderline: WarmupGeometry = { ...mobile, columns: 3, cardWidth: 128, rowPitch: 133 };

    expect(planThumbnailWarmup(items(6), borderline)).toEqual([]);
    // 100 px is clearly 256, 160 px is clearly 512: both are planned.
    expect(planThumbnailWarmup(items(6), { ...borderline, cardWidth: 100 }).length).toBeGreaterThan(0);
    expect(planThumbnailWarmup(items(6), { ...borderline, cardWidth: 160 }).length).toBeGreaterThan(0);
  });

  it.each([
    ["no columns", { columns: 0 }],
    ["an unmeasured card", { cardWidth: 0 }],
    ["no row pitch", { rowPitch: 0 }],
    ["no viewport", { viewportHeight: 0 }],
    ["no device pixel ratio", { devicePixelRatio: 0 }],
    ["a grid below the viewport", { top: 5000 }],
  ])("plans nothing for %s", (_name, override) => {
    expect(planThumbnailWarmup(items(20), { ...mobile, ...override })).toEqual([]);
  });
});

describe("warmThumbnails", () => {
  afterEach(() => {
    vi.useRealTimers();
    document.head.querySelectorAll("link[rel='preload']").forEach((link) => link.remove());
  });

  it("adds one image preload link per target with srcset, sizes and priority", () => {
    const targets = planThumbnailWarmup(items(2, { path: "/lib/link.png" }), mobile).slice(0, 1);

    const links = warmThumbnails(targets);

    expect(links).toHaveLength(1);
    expect(links[0].parentElement).toBe(document.head);
    expect(links[0].getAttribute("rel")).toBe("preload");
    expect(links[0].getAttribute("as")).toBe("image");
    expect(links[0].getAttribute("href")).toBe(targets[0].href);
    expect(links[0].getAttribute("imagesrcset")).toBe(targets[0].imagesrcset);
    expect(links[0].getAttribute("imagesizes")).toBe(targets[0].imagesizes);
    expect(links[0].getAttribute("fetchpriority")).toBe("high");
  });

  it("does not add a second link for a URL that is already warm", () => {
    const targets = planThumbnailWarmup(items(2, { path: "/lib/dup.png" }), mobile).slice(0, 1);

    expect(warmThumbnails(targets)).toHaveLength(1);
    expect(warmThumbnails(targets)).toHaveLength(0);
    expect(document.head.querySelectorAll("link[rel='preload']")).toHaveLength(1);
  });

  it("removes the link after its lifetime and allows warming the URL again", () => {
    vi.useFakeTimers();
    const targets = planThumbnailWarmup(items(2, { path: "/lib/expire.png" }), mobile).slice(0, 1);

    warmThumbnails(targets);
    vi.advanceTimersByTime(WARMUP_LINK_LIFETIME_MS + 1);

    expect(document.head.querySelectorAll("link[rel='preload']")).toHaveLength(0);
    expect(warmThumbnails(targets)).toHaveLength(1);
  });
});
