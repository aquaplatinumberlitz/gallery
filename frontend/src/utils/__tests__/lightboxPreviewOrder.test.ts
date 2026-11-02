/**
 * Purpose: Protect the lightbox request order: the current slide's preview first, neighbours after.
 * Guarantees: With PhotoSwipe `preload: [1, 1]`, neighbour previews are only requested once the current
 * preview loaded or failed; navigating to a still-held slide requests it at once; neighbours that are
 * already loaded make navigation instant. Runs against the real PhotoSwipe core so an upstream change
 * to its preload order is caught.
 * Run when: Changing usePhotoSwipe preloading, the PhotoSwipe version, or lightbox source selection.
 */
import PhotoSwipe from "photoswipe";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { deferNeighbourPreviewsUntilCurrentSettles } from "../lightboxPreviewOrder";

const urls = ["/p/a", "/p/b", "/p/c", "/p/d", "/p/e"];
let requested: string[] = [];
let images: Map<string, HTMLImageElement>;
let container: HTMLElement;
let instance: PhotoSwipe | null = null;

const srcDescriptor = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, "src");

beforeEach(() => {
  requested = [];
  images = new Map();
  container = document.createElement("div");
  document.body.appendChild(container);
  // jsdom never loads images; record every `src` assignment (= network request) instead.
  Object.defineProperty(HTMLImageElement.prototype, "src", {
    configurable: true,
    get(this: HTMLImageElement) {
      return this.getAttribute("src") ?? "";
    },
    set(this: HTMLImageElement, value: string) {
      requested.push(value);
      images.set(value, this);
      this.setAttribute("src", value);
    },
  });
});

afterEach(() => {
  instance?.destroy();
  instance = null;
  if (srcDescriptor) Object.defineProperty(HTMLImageElement.prototype, "src", srcDescriptor);
});

function open(index: number, { defer }: { defer: boolean }) {
  instance = new PhotoSwipe({
    dataSource: urls.map((src) => ({ src, width: 1200, height: 800 })),
    index,
    appendToEl: container,
    showHideAnimationType: "none",
    preload: [1, 1],
    // jsdom has no layout; without a viewport size PhotoSwipe computes a zero display size and never loads.
    getViewportSizeFn: () => ({ x: 1000, y: 800 }),
    // Looping would also preload across the ends and make the expected sets harder to read.
    loop: false,
  });
  if (defer) deferNeighbourPreviewsUntilCurrentSettles(instance);
  instance.init();
  return instance;
}

/** Neighbours are created after the opening animation, which is immediate with animation type "none". */
async function settleOpening() {
  await vi.waitFor(() => expect(requested.length).toBeGreaterThan(0));
  await new Promise((resolve) => setTimeout(resolve, 30));
}

const finish = (url: string, outcome: "load" | "error" = "load") => {
  const img = images.get(url);
  if (!img) throw new Error(`${url} was never requested`);
  img.dispatchEvent(new Event(outcome));
};

describe("deferNeighbourPreviewsUntilCurrentSettles", () => {
  it("control: PhotoSwipe alone requests the neighbours together with the current slide", async () => {
    open(2, { defer: false });
    await settleOpening();

    expect(requested[0]).toBe("/p/c");
    expect(new Set(requested)).toEqual(new Set(["/p/b", "/p/c", "/p/d"]));
  });

  it("requests only the current preview until it has loaded, then both neighbours", async () => {
    open(2, { defer: true });
    await settleOpening();

    expect(requested).toEqual(["/p/c"]);

    finish("/p/c");

    expect(requested.slice(0, 1)).toEqual(["/p/c"]);
    expect(new Set(requested)).toEqual(new Set(["/p/b", "/p/c", "/p/d"]));
    expect(requested).toHaveLength(3);
  });

  it("starts the neighbours when the current preview fails", async () => {
    open(2, { defer: true });
    await settleOpening();
    expect(requested).toEqual(["/p/c"]);

    finish("/p/c", "error");

    expect(new Set(requested)).toEqual(new Set(["/p/b", "/p/c", "/p/d"]));
  });

  it("requests a held neighbour immediately when the user navigates to it", async () => {
    const pswp = open(2, { defer: true });
    await settleOpening();
    expect(requested).toEqual(["/p/c"]);

    pswp.next();
    await vi.waitFor(() => expect(requested).toContain("/p/d"));

    // d is the current slide now and is requested at once; the new neighbour e still waits for d.
    expect(requested).toContain("/p/d");
    expect(requested).not.toContain("/p/e");

    finish("/p/d");

    expect(requested).toContain("/p/e");
  });

  it("does not hold back anything once the new current slide is already loaded", async () => {
    const pswp = open(2, { defer: true });
    await settleOpening();
    finish("/p/c");
    finish("/p/d");
    finish("/p/b");
    requested.length = 0;

    pswp.next();

    // d was preloaded, so moving to it only has to start e: no waiting on the current slide.
    await vi.waitFor(() => expect(requested).toEqual(["/p/e"]));
  });
});
