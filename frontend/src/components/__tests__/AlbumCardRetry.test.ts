/**
 * Purpose: Protect the retry of failed album covers (mobile, tablet and desktop cards), the same behaviour as
 * PhotoCard: a cold album can answer 503 for a cover and the derivative is ready seconds later.
 * Guarantees: A real cover error retries the same cover up to 3 times (1.5 s, 4 s, 10 s) with `r=<n>` on its
 * URL while the loading skeleton keeps shimmering; the skeleton hides only after the last retry failed or a
 * retry loaded; scrolling away cancels a pending retry, a card that comes back restarts with a fresh budget,
 * and the error of a cleared `src` is not counted.
 * Run when: Changing album card cover loading, error handling, or the visibility gate.
 */
import { mount } from "@vue/test-utils";
import { nextTick, type Component } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AlbumCard from "../AlbumCard.vue";
import AlbumCardMobile from "../AlbumCardMobile.vue";
import AlbumCardTablet from "../AlbumCardTablet.vue";
import { IMAGE_RETRY_DELAYS_MS } from "@/composables/useImageRetry";
import type { FileNode } from "@/types";

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

const node: FileNode = {
  name: "Album",
  path: "/photos/album",
  type: "folder",
  has_children: false,
  image_count: 3,
  cover_images: ["/photos/album/a.png", "/photos/album/b.png"],
  cover_versions: ["11-1", "22-2"],
};

const cards = [
  { name: "AlbumCardMobile", component: AlbumCardMobile, skeleton: ".cover-skeleton" },
  { name: "AlbumCardTablet", component: AlbumCardTablet, skeleton: ".cover-skeleton" },
  { name: "AlbumCard", component: AlbumCard, skeleton: null },
] as const;

describe.each(cards)("$name cover retry", ({ component, skeleton }) => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeIntersectionObserver.instances = [];
    vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  const mountCard = (props: Record<string, unknown> = {}) =>
    mount(component as Component, { props: { node, ...props }, attachTo: document.body });
  type Wrapper = ReturnType<typeof mountCard>;
  const frontCover = (wrapper: Wrapper) => wrapper.findAll("img").at(-1)!;
  const srcOf = (wrapper: Wrapper) => frontCover(wrapper).attributes("src");
  const fail = async (wrapper: Wrapper) => {
    await frontCover(wrapper).trigger("error");
  };
  const skeletonVisible = (wrapper: Wrapper) => (skeleton ? wrapper.find(skeleton).exists() : null);

  it("retries the same cover with r=1 after an error and keeps the skeleton", async () => {
    const wrapper = mountCard({ priority: true });
    const base = srcOf(wrapper)!;
    expect(base).toContain("v=11-1");

    await fail(wrapper);

    expect(srcOf(wrapper)).toBe(base);
    if (skeleton) expect(skeletonVisible(wrapper)).toBe(true);
    await vi.advanceTimersByTimeAsync(IMAGE_RETRY_DELAYS_MS[0]);
    expect(srcOf(wrapper)).toBe(`${base}&r=1`);
    if (skeleton) expect(skeletonVisible(wrapper)).toBe(true);
  });

  it("hides the skeleton when a retry loads", async () => {
    const wrapper = mountCard({ priority: true });
    await fail(wrapper);
    await vi.advanceTimersByTimeAsync(IMAGE_RETRY_DELAYS_MS[0]);

    await frontCover(wrapper).trigger("load");

    if (skeleton) expect(skeletonVisible(wrapper)).toBe(false);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(srcOf(wrapper)).toContain("&r=1");
    expect(srcOf(wrapper)).not.toContain("&r=2");
  });

  it("retries 3 times, then settles", async () => {
    const wrapper = mountCard({ priority: true });
    const base = srcOf(wrapper)!;

    for (const [index, delay] of IMAGE_RETRY_DELAYS_MS.entries()) {
      await fail(wrapper);
      if (skeleton) expect(skeletonVisible(wrapper)).toBe(true);
      await vi.advanceTimersByTimeAsync(delay);
      expect(srcOf(wrapper)).toBe(`${base}&r=${index + 1}`);
    }
    if (skeleton) expect(skeletonVisible(wrapper)).toBe(true);

    await fail(wrapper); // retries used up
    if (skeleton) expect(skeletonVisible(wrapper)).toBe(false);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(srcOf(wrapper)).toBe(`${base}&r=3`);
  });

  it("scrolling away cancels the pending retry and a returning card restarts from the plain URL", async () => {
    const wrapper = mountCard();
    observer().emit(true);
    await nextTick();
    const base = srcOf(wrapper)!;

    await fail(wrapper);
    await vi.advanceTimersByTimeAsync(IMAGE_RETRY_DELAYS_MS[0]);
    expect(srcOf(wrapper)).toBe(`${base}&r=1`);
    await fail(wrapper); // second retry now pending

    observer().emit(false);
    await nextTick();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(srcOf(wrapper)).toBeUndefined();
    if (skeleton) expect(skeletonVisible(wrapper)).toBe(true);

    observer().emit(true);
    await nextTick();
    expect(srcOf(wrapper)).toBe(base);
    for (const [index, delay] of IMAGE_RETRY_DELAYS_MS.entries()) {
      await fail(wrapper);
      await vi.advanceTimersByTimeAsync(delay);
      expect(srcOf(wrapper)).toBe(`${base}&r=${index + 1}`);
    }
  });

  it("does not count the error of a cleared src", async () => {
    const wrapper = mountCard();
    observer().emit(true);
    await nextTick();
    observer().emit(false);
    await nextTick();

    await fail(wrapper);
    await vi.advanceTimersByTimeAsync(60_000);

    expect(srcOf(wrapper)).toBeUndefined();
    if (skeleton) expect(skeletonVisible(wrapper)).toBe(true);
  });

  it("unmounting cancels the pending retry", async () => {
    const wrapper = mountCard({ priority: true });
    await fail(wrapper);
    expect(vi.getTimerCount()).toBeGreaterThan(0);

    wrapper.unmount();

    expect(vi.getTimerCount()).toBe(0);
  });
});
