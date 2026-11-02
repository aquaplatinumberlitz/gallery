/**
 * Purpose: Protect PhotoCard's retry of failed thumbnails (a cold album answers 503 after its 10 s generation
 * wait; the derivative is ready a few seconds later).
 * Guarantees: A real image error retries the same thumbnail up to 3 times (backoff 1.5 s, 4 s, 10 s) with a
 * throwaway `r=<n>` query parameter on `src` and every `srcset` candidate; the loading shimmer stays while
 * retrying; the error placeholder shows only after the last retry failed; a retry that loads clears the
 * pending state; leaving the viewport cancels a pending retry and a returning card starts a fresh sequence;
 * unmounting cancels the timer; the error a cleared `src` raises is not counted; a new image resets it.
 * Run when: Changing PhotoCard error handling, retries, or the visibility gate.
 */
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PhotoCard from "../PhotoCard.vue";
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
const nextSrc = () => `/retry-test/${++counter}.png`;

const mountCard = (props: Record<string, unknown> = {}) =>
  mount(PhotoCard, {
    props: { src: nextSrc(), name: "photo.png", ...props },
    attachTo: document.body,
    global: { stubs: { AssetActionMenu: true } },
  });

type Wrapper = ReturnType<typeof mountCard>;
const thumbnail = (wrapper: Wrapper) => wrapper.find<HTMLImageElement>("img.thumbnail-img");
const srcOf = (wrapper: Wrapper) => thumbnail(wrapper).attributes("src");
const fail = async (wrapper: Wrapper) => {
  await thumbnail(wrapper).trigger("error");
};
const shimmerVisible = (wrapper: Wrapper) => wrapper.find(".shimmer-placeholder").exists();
const placeholderVisible = (wrapper: Wrapper) => wrapper.text().includes("Preview unavailable");

describe("PhotoCard thumbnail retry", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeIntersectionObserver.instances = [];
    vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("uses the same backoff as the documented 1.5 s / 4 s / 10 s", () => {
    expect([...IMAGE_RETRY_DELAYS_MS]).toEqual([1500, 4000, 10000]);
  });

  it("retries the same thumbnail after an error, with r=1 on src and srcset, and keeps the shimmer meanwhile", async () => {
    const src = nextSrc();
    const wrapper = mountCard({ src, version: "9-9", fetchPriority: "high" });
    const first = srcOf(wrapper);
    expect(first).not.toContain("r=");

    await fail(wrapper);

    // waiting for the backoff: nothing changed yet, still the loading look
    expect(srcOf(wrapper)).toBe(first);
    expect(shimmerVisible(wrapper)).toBe(true);
    expect(placeholderVisible(wrapper)).toBe(false);

    await vi.advanceTimersByTimeAsync(IMAGE_RETRY_DELAYS_MS[0] - 1);
    expect(srcOf(wrapper)).toBe(first);
    await vi.advanceTimersByTimeAsync(1);

    expect(srcOf(wrapper)).toBe(`${first}&r=1`);
    expect(srcOf(wrapper)).toContain("v=9-9");
    expect(srcOf(wrapper)).toContain(encodeURIComponent(src));
    expect(shimmerVisible(wrapper)).toBe(true);
  });

  it("adds r=<n> to every srcset candidate when the card has a measured width", async () => {
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(200);
    const wrapper = mountCard({ fetchPriority: "high", version: "1-2", imageWidth: 10, imageHeight: 10 });
    await nextTick();
    expect(thumbnail(wrapper).attributes("srcset")).not.toContain("r=");

    await fail(wrapper);
    await vi.advanceTimersByTimeAsync(IMAGE_RETRY_DELAYS_MS[0]);

    const candidates = thumbnail(wrapper).attributes("srcset")!.split(", ");
    expect(candidates).toHaveLength(2);
    for (const candidate of candidates) expect(candidate).toContain("&r=1");
    vi.restoreAllMocks();
  });

  it("shows the image after a retry succeeded and does not retry again", async () => {
    const wrapper = mountCard({ fetchPriority: "high" });
    await fail(wrapper);
    await vi.advanceTimersByTimeAsync(IMAGE_RETRY_DELAYS_MS[0]);

    await thumbnail(wrapper).trigger("load");

    expect(wrapper.find(".photo-card").classes()).toContain("loaded");
    expect(shimmerVisible(wrapper)).toBe(false);
    expect(placeholderVisible(wrapper)).toBe(false);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(srcOf(wrapper)).toContain("&r=1");
    expect(srcOf(wrapper)).not.toContain("&r=2");
  });

  it("retries 3 times and shows the error placeholder only after the last retry failed", async () => {
    const wrapper = mountCard({ fetchPriority: "high" });
    const base = srcOf(wrapper)!;

    for (const [index, delay] of IMAGE_RETRY_DELAYS_MS.entries()) {
      await fail(wrapper);
      expect(placeholderVisible(wrapper)).toBe(false);
      expect(shimmerVisible(wrapper)).toBe(true);
      await vi.advanceTimersByTimeAsync(delay);
      expect(srcOf(wrapper)).toBe(`${base}&r=${index + 1}`);
    }

    expect(placeholderVisible(wrapper)).toBe(false);
    await fail(wrapper); // the 4th failure: no retries left
    expect(placeholderVisible(wrapper)).toBe(true);
    expect(shimmerVisible(wrapper)).toBe(false);
    expect(wrapper.find("img.thumbnail-img").exists()).toBe(false);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(placeholderVisible(wrapper)).toBe(true);
  });

  it("waits the full backoff each time (1.5 s, then 4 s, then 10 s)", async () => {
    const wrapper = mountCard({ fetchPriority: "high" });
    const base = srcOf(wrapper)!;

    await fail(wrapper);
    await vi.advanceTimersByTimeAsync(1500);
    expect(srcOf(wrapper)).toBe(`${base}&r=1`);

    await fail(wrapper);
    await vi.advanceTimersByTimeAsync(3999);
    expect(srcOf(wrapper)).toBe(`${base}&r=1`);
    await vi.advanceTimersByTimeAsync(1);
    expect(srcOf(wrapper)).toBe(`${base}&r=2`);

    await fail(wrapper);
    await vi.advanceTimersByTimeAsync(9999);
    expect(srcOf(wrapper)).toBe(`${base}&r=2`);
    await vi.advanceTimersByTimeAsync(1);
    expect(srcOf(wrapper)).toBe(`${base}&r=3`);
  });

  it("a duplicate error event while the backoff runs does not burn a retry", async () => {
    const wrapper = mountCard({ fetchPriority: "high" });
    const base = srcOf(wrapper)!;

    await fail(wrapper);
    await fail(wrapper);
    await vi.advanceTimersByTimeAsync(IMAGE_RETRY_DELAYS_MS[0]);

    expect(srcOf(wrapper)).toBe(`${base}&r=1`);
  });

  it("leaving the viewport cancels the pending retry", async () => {
    const wrapper = mountCard();
    observer().emit(true);
    await nextTick();
    const base = srcOf(wrapper)!;
    expect(base).toContain("/api/thumbnail");

    await fail(wrapper);
    observer().emit(false);
    await nextTick();
    expect(srcOf(wrapper)).toBeUndefined();

    await vi.advanceTimersByTimeAsync(60_000);

    expect(srcOf(wrapper)).toBeUndefined();
    expect(placeholderVisible(wrapper)).toBe(false);
    expect(shimmerVisible(wrapper)).toBe(true);
  });

  it("a card that comes back restarts the sequence from the plain URL with a fresh retry budget", async () => {
    const wrapper = mountCard();
    observer().emit(true);
    await nextTick();
    const base = srcOf(wrapper)!;

    await fail(wrapper);
    await vi.advanceTimersByTimeAsync(IMAGE_RETRY_DELAYS_MS[0]);
    expect(srcOf(wrapper)).toBe(`${base}&r=1`);
    await fail(wrapper);
    await vi.advanceTimersByTimeAsync(IMAGE_RETRY_DELAYS_MS[1]);
    expect(srcOf(wrapper)).toBe(`${base}&r=2`);

    observer().emit(false);
    await nextTick();
    expect(srcOf(wrapper)).toBeUndefined();
    observer().emit(true);
    await nextTick();
    expect(srcOf(wrapper)).toBe(base);

    // three more retries are available again
    for (const [index, delay] of IMAGE_RETRY_DELAYS_MS.entries()) {
      await fail(wrapper);
      expect(placeholderVisible(wrapper)).toBe(false);
      await vi.advanceTimersByTimeAsync(delay);
      expect(srcOf(wrapper)).toBe(`${base}&r=${index + 1}`);
    }
    await fail(wrapper);
    expect(placeholderVisible(wrapper)).toBe(true);
  });

  it("the error a cleared src raises is not a failure and starts no retry", async () => {
    const wrapper = mountCard();
    observer().emit(true);
    await nextTick();
    observer().emit(false);
    await nextTick();
    expect(srcOf(wrapper)).toBeUndefined();

    await fail(wrapper);
    await vi.advanceTimersByTimeAsync(60_000);

    expect(placeholderVisible(wrapper)).toBe(false);
    expect(srcOf(wrapper)).toBeUndefined();
    observer().emit(true);
    await nextTick();
    expect(srcOf(wrapper)).not.toContain("r=");
  });

  it("the cancel-induced error does not use up a retry of a card that really failed before", async () => {
    const wrapper = mountCard();
    observer().emit(true);
    await nextTick();
    const base = srcOf(wrapper)!;

    await fail(wrapper); // real error: one retry scheduled
    observer().emit(false);
    await nextTick();
    await fail(wrapper); // error event of the cleared src
    observer().emit(true);
    await nextTick();

    // full budget again: three retries before the placeholder
    for (const [index, delay] of IMAGE_RETRY_DELAYS_MS.entries()) {
      await fail(wrapper);
      await vi.advanceTimersByTimeAsync(delay);
      expect(srcOf(wrapper)).toBe(`${base}&r=${index + 1}`);
    }
    expect(placeholderVisible(wrapper)).toBe(false);
  });

  it("unmounting cancels the pending retry", async () => {
    const wrapper = mountCard({ fetchPriority: "high" });
    await fail(wrapper);
    expect(vi.getTimerCount()).toBeGreaterThan(0);

    wrapper.unmount();

    expect(vi.getTimerCount()).toBe(0);
  });

  it("a different image starts with a fresh retry budget", async () => {
    const wrapper = mountCard({ fetchPriority: "high" });
    await fail(wrapper);
    await vi.advanceTimersByTimeAsync(IMAGE_RETRY_DELAYS_MS[0]);
    await fail(wrapper);

    const next = nextSrc();
    await wrapper.setProps({ src: next });
    await nextTick();

    expect(srcOf(wrapper)).toBe(`/api/thumbnail?path=${encodeURIComponent(next)}&max_long_edge=512`);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(srcOf(wrapper)).not.toContain("r=");
  });
});
