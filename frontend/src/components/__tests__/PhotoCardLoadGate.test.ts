/**
 * Purpose: Protect PhotoCard's visibility-gated, cancellable thumbnail loading.
 * Guarantees: The thumbnail request starts only after the card rested in view, first-row (high priority)
 * cards and images already shown load at once, leaving or unmounting before the image completed clears
 * `src` so the browser cancels the request, a loaded image is kept, and the cancel is not reported as
 * an image error. The loading skeleton stays visible until the image has loaded.
 * Run when: Changing PhotoCard loading, fetch priority, or the grid virtualization that mounts cards.
 */
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PhotoCard from "../PhotoCard.vue";
import { VISIBLE_LOAD_DWELL_MS } from "@/composables/useVisibleLoadGate";
import { IMAGE_RETRY_DELAYS_MS } from "@/composables/useImageRetry";

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

const observer = () => FakeIntersectionObserver.instances[FakeIntersectionObserver.instances.length - 1]!;

let counter = 0;
const nextSrc = () => `/gate-test/${++counter}.png`;

const mountCard = (props: Record<string, unknown> = {}) =>
  mount(PhotoCard, {
    props: { src: nextSrc(), name: "photo.png", ...props },
    attachTo: document.body,
    global: { stubs: { AssetActionMenu: true } },
  });

const thumbnail = (wrapper: ReturnType<typeof mountCard>) => wrapper.find<HTMLImageElement>("img.thumbnail-img");

describe("PhotoCard thumbnail load gate", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeIntersectionObserver.instances = [];
    vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("at rest, requests the thumbnail of an in-range card at once, without a dwell", async () => {
    const wrapper = mountCard();
    expect(thumbnail(wrapper).attributes("src")).toBeUndefined();

    observer().emit(true);
    await nextTick();

    expect(thumbnail(wrapper).attributes("src")).toContain("/api/thumbnail");
  });

  it("while scrolling, does not request the thumbnail until the card has rested in view", async () => {
    const wrapper = mountCard();
    expect(thumbnail(wrapper).attributes("src")).toBeUndefined();

    window.dispatchEvent(new Event("scroll"));
    observer().emit(true);
    await vi.advanceTimersByTimeAsync(VISIBLE_LOAD_DWELL_MS - 1);
    expect(thumbnail(wrapper).attributes("src")).toBeUndefined();

    await vi.advanceTimersByTimeAsync(1);
    expect(thumbnail(wrapper).attributes("src")).toContain("/api/thumbnail");
  });

  it("shows the same skeleton while the request has not started", () => {
    const wrapper = mountCard();
    expect(wrapper.find(".shimmer-placeholder").exists()).toBe(true);
    expect(wrapper.find(".photo-card").classes()).not.toContain("loaded");
  });

  it("loads first-row cards (fetchPriority high) immediately", () => {
    const wrapper = mountCard({ fetchPriority: "high" });
    expect(thumbnail(wrapper).attributes("src")).toContain("/api/thumbnail");
  });

  it("cancels the request by clearing src when the card leaves before the image loaded", async () => {
    const wrapper = mountCard();
    observer().emit(true);
    await vi.advanceTimersByTimeAsync(VISIBLE_LOAD_DWELL_MS);
    expect(thumbnail(wrapper).attributes("src")).toBeDefined();

    observer().emit(false);
    await vi.advanceTimersByTimeAsync(0);

    expect(thumbnail(wrapper).attributes("src")).toBeUndefined();
    expect(wrapper.find(".placeholder").exists()).toBe(false);
  });

  it("ignores the error event a cleared src can raise", async () => {
    const wrapper = mountCard();
    observer().emit(true);
    await vi.advanceTimersByTimeAsync(VISIBLE_LOAD_DWELL_MS);
    observer().emit(false);
    await vi.advanceTimersByTimeAsync(0);

    await thumbnail(wrapper).trigger("error");

    expect(wrapper.text()).not.toContain("Preview unavailable");
  });

  it("keeps a loaded thumbnail when the card leaves", async () => {
    const wrapper = mountCard();
    observer().emit(true);
    await vi.advanceTimersByTimeAsync(VISIBLE_LOAD_DWELL_MS);
    await thumbnail(wrapper).trigger("load");
    expect(wrapper.find(".photo-card").classes()).toContain("loaded");

    observer().emit(false);
    await vi.advanceTimersByTimeAsync(0);

    expect(thumbnail(wrapper).attributes("src")).toBeDefined();
  });

  it("clears src of an unfinished image when unmounted so detached images stop downloading", async () => {
    const wrapper = mountCard({ fetchPriority: "high" });
    const img = thumbnail(wrapper).element;
    expect(img.getAttribute("src")).toBeTruthy();

    wrapper.unmount();

    expect(img.getAttribute("src")).toBeNull();
  });

  it("reports a real image error once its retries are used up", async () => {
    const wrapper = mountCard({ fetchPriority: "high" });

    await thumbnail(wrapper).trigger("error");
    // A real error is retried first (PhotoCardRetry.test.ts); the placeholder shows after the last retry fails.
    for (const delay of IMAGE_RETRY_DELAYS_MS) {
      await vi.advanceTimersByTimeAsync(delay);
      await thumbnail(wrapper).trigger("error");
    }

    expect(wrapper.text()).toContain("Preview unavailable");
  });

  it("loads an already seen image without waiting again", async () => {
    const src = nextSrc();
    const first = mountCard({ src, fetchPriority: "high" });
    await thumbnail(first).trigger("load");
    first.unmount();

    const again = mountCard({ src });

    expect(thumbnail(again).attributes("src")).toContain("/api/thumbnail");
  });
});
