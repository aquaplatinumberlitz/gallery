/**
 * Purpose: Protect PhotoCard's versioned `src` and its `srcset` / `sizes` (256w + 512w).
 * Guarantees: `src` stays the 512 px fallback and carries the content version; `srcset` offers the 256 and
 * 512 px derivatives with the same version; `sizes` is the measured card width scaled by the cover-crop
 * aspect ratio and follows resizes; none of it is set before the F1 visibility gate allows loading, and
 * `srcset` is cleared together with `src` when the card leaves; without a measured width the card behaves
 * as before srcset existed (`src` only).
 * Run when: Changing PhotoCard thumbnails, grid card geometry, or the thumbnail derivatives.
 */
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PhotoCard from "../PhotoCard.vue";

class FakeIntersectionObserver {
  static instances: FakeIntersectionObserver[] = [];
  readonly targets: Element[] = [];
  private readonly callback: IntersectionObserverCallback;
  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback;
    FakeIntersectionObserver.instances.push(this);
  }
  observe(target: Element) {
    this.targets.push(target);
  }
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
  emit(isIntersecting: boolean) {
    this.callback(
      [{ isIntersecting, target: this.targets[0] } as unknown as IntersectionObserverEntry],
      this as unknown as IntersectionObserver,
    );
  }
}

class FakeResizeObserver {
  static instance: FakeResizeObserver | null = null;
  readonly targets = new Set<Element>();
  private readonly callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
    FakeResizeObserver.instance = this;
  }
  observe(target: Element) {
    this.targets.add(target);
  }
  unobserve(target: Element) {
    this.targets.delete(target);
  }
  disconnect() {}
  fire() {
    this.callback(
      [...this.targets].map((target) => ({ target }) as unknown as ResizeObserverEntry),
      this as unknown as ResizeObserver,
    );
  }
}

const observer = () => FakeIntersectionObserver.instances[FakeIntersectionObserver.instances.length - 1]!;

let cardWidth = 230;
let counter = 0;
const nextSrc = () => `/srcset-test/${++counter}.png`;

const mountCard = async (props: Record<string, unknown> = {}) => {
  const wrapper = mount(PhotoCard, {
    props: { src: nextSrc(), name: "photo.png", ...props },
    attachTo: document.body,
    global: { stubs: { AssetActionMenu: true } },
  });
  await nextTick();
  return wrapper;
};

const thumbnail = (wrapper: Awaited<ReturnType<typeof mountCard>>) =>
  wrapper.find<HTMLImageElement>("img.thumbnail-img");

describe("PhotoCard thumbnail srcset", () => {
  beforeEach(() => {
    cardWidth = 230;
    FakeIntersectionObserver.instances = [];
    vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockImplementation(() => cardWidth);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("keeps the 512 px fallback in src and offers 256w + 512w, all carrying the content version", async () => {
    const src = nextSrc();
    const wrapper = await mountCard({
      src,
      version: "11-22",
      imageWidth: 1024,
      imageHeight: 1024,
      fetchPriority: "high",
    });
    const img = thumbnail(wrapper);

    const encoded = encodeURIComponent(src);
    expect(img.attributes("src")).toBe(`/api/thumbnail?path=${encoded}&max_long_edge=512&v=11-22`);
    expect(img.attributes("srcset")).toBe(
      `/api/thumbnail?path=${encoded}&max_long_edge=256&v=11-22 256w, /api/thumbnail?path=${encoded}&max_long_edge=512&v=11-22 512w`,
    );
  });

  it("keeps today's URLs for an item without a version", async () => {
    const src = nextSrc();
    const wrapper = await mountCard({ src, imageWidth: 100, imageHeight: 100, fetchPriority: "high" });
    const img = thumbnail(wrapper);

    expect(img.attributes("src")).toBe(`/api/thumbnail?path=${encodeURIComponent(src)}&max_long_edge=512`);
    expect(img.attributes("srcset")).not.toContain("v=");
  });

  it("sets sizes to the measured card width for a square image", async () => {
    const wrapper = await mountCard({ imageWidth: 1024, imageHeight: 1024, fetchPriority: "high" });
    expect(thumbnail(wrapper).attributes("sizes")).toBe("230px");
  });

  it("widens sizes by the aspect ratio so the object-fit: cover crop is not upscaled", async () => {
    const landscape = await mountCard({ imageWidth: 1536, imageHeight: 1024, fetchPriority: "high" });
    expect(thumbnail(landscape).attributes("sizes")).toBe("345px");

    const portrait = await mountCard({ imageWidth: 1024, imageHeight: 1536, fetchPriority: "high" });
    expect(thumbnail(portrait).attributes("sizes")).toBe("345px");
  });

  it("assumes a wide image when the dimensions are unknown", async () => {
    const wrapper = await mountCard({ fetchPriority: "high" });
    expect(thumbnail(wrapper).attributes("sizes")).toBe("460px");
  });

  it("follows the card width when the grid is resized", async () => {
    const wrapper = await mountCard({ imageWidth: 10, imageHeight: 10, fetchPriority: "high" });
    expect(thumbnail(wrapper).attributes("sizes")).toBe("230px");

    cardWidth = 480;
    FakeResizeObserver.instance!.fire();
    await nextTick();

    expect(thumbnail(wrapper).attributes("sizes")).toBe("480px");
  });

  it("uses src only while the card has no measured width", async () => {
    cardWidth = 0;
    const wrapper = await mountCard({ fetchPriority: "high" });
    const img = thumbnail(wrapper);

    expect(img.attributes("src")).toContain("/api/thumbnail");
    expect(img.attributes("srcset")).toBeUndefined();
    expect(img.attributes("sizes")).toBeUndefined();
  });

  it("does not offer a srcset for a custom thumbnail size", async () => {
    const wrapper = await mountCard({ thumbnailSize: 128, fetchPriority: "high" });
    const img = thumbnail(wrapper);

    expect(img.attributes("src")).toContain("max_long_edge=128");
    expect(img.attributes("srcset")).toBeUndefined();
  });

  it("sets neither src nor srcset before the visibility gate allows loading, and clears both on cancel", async () => {
    vi.useFakeTimers();
    try {
      const wrapper = await mountCard({ version: "5-6", imageWidth: 10, imageHeight: 10 });
      expect(thumbnail(wrapper).attributes("src")).toBeUndefined();
      expect(thumbnail(wrapper).attributes("srcset")).toBeUndefined();

      observer().emit(true);
      await nextTick();
      expect(thumbnail(wrapper).attributes("src")).toContain("v=5-6");
      expect(thumbnail(wrapper).attributes("srcset")).toContain("256w");

      observer().emit(false);
      await nextTick();
      expect(thumbnail(wrapper).attributes("src")).toBeUndefined();
      expect(thumbnail(wrapper).attributes("srcset")).toBeUndefined();
    } finally {
      vi.useRealTimers();
    }
  });
});
