/**
 * Purpose: Protect the visibility-gated, cancellable cover loading of the album cards.
 * Guarantees: For the mobile, tablet and desktop album cards the cover request starts only after the
 * card rested in view, above-the-fold (priority) covers load at once, a cover that is scrolled away
 * before it loaded is cancelled by clearing `src`, the cancel keeps the loading skeleton, and a real
 * load or error still hides the skeleton.
 * Run when: Changing album card cover loading, the album strip, or the scroll-root detection.
 */
import { mount } from "@vue/test-utils";
import type { Component } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AlbumCard from "../AlbumCard.vue";
import AlbumCardMobile from "../AlbumCardMobile.vue";
import AlbumCardTablet from "../AlbumCardTablet.vue";
import { VISIBLE_LOAD_DWELL_MS } from "@/composables/useVisibleLoadGate";
import type { FileNode } from "@/types";

class FakeIntersectionObserver {
  static instances: FakeIntersectionObserver[] = [];
  readonly options: IntersectionObserverInit | undefined;
  readonly targets: Element[] = [];
  private readonly callback: IntersectionObserverCallback;
  constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {
    this.callback = callback;
    this.options = options;
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
};

const cards = [
  { name: "AlbumCardMobile", component: AlbumCardMobile, skeleton: ".cover-skeleton" },
  { name: "AlbumCardTablet", component: AlbumCardTablet, skeleton: ".cover-skeleton" },
  { name: "AlbumCard", component: AlbumCard, skeleton: null },
] as const;

describe.each(cards)("$name cover load gate", ({ component, skeleton }) => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeIntersectionObserver.instances = [];
    vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const mountCard = (props: Record<string, unknown> = {}) =>
    mount(component as Component, { props: { node, ...props }, attachTo: document.body });
  const frontCover = (wrapper: ReturnType<typeof mountCard>) => wrapper.findAll("img").at(-1)!;

  it("requests the cover only after the card has rested in view", async () => {
    const wrapper = mountCard();
    expect(frontCover(wrapper).attributes("src")).toBeUndefined();

    observer().emit(true);
    await vi.advanceTimersByTimeAsync(VISIBLE_LOAD_DWELL_MS);

    expect(frontCover(wrapper).attributes("src")).toContain("/api/thumbnail");
  });

  it("loads above-the-fold covers immediately", () => {
    const wrapper = mountCard({ priority: true });
    expect(frontCover(wrapper).attributes("src")).toContain("/api/thumbnail");
  });

  it("prefetches sideways: the observation margin is horizontal", () => {
    mountCard();
    expect(observer().options?.rootMargin).toBe("0px 400px");
  });

  it("cancels the cover when scrolled away before it loaded, without hiding the skeleton", async () => {
    const wrapper = mountCard();
    observer().emit(true);
    await vi.advanceTimersByTimeAsync(VISIBLE_LOAD_DWELL_MS);
    expect(frontCover(wrapper).attributes("src")).toBeDefined();

    observer().emit(false);
    await vi.advanceTimersByTimeAsync(0);
    await frontCover(wrapper).trigger("error");

    expect(frontCover(wrapper).attributes("src")).toBeUndefined();
    if (skeleton) expect(wrapper.find(skeleton).exists()).toBe(true);
  });

  it("keeps a loaded cover and hides the skeleton", async () => {
    const wrapper = mountCard({ priority: true });
    await frontCover(wrapper).trigger("load");

    observer().emit(false);
    await vi.advanceTimersByTimeAsync(0);

    expect(frontCover(wrapper).attributes("src")).toContain("/api/thumbnail");
    if (skeleton) expect(wrapper.find(skeleton).exists()).toBe(false);
  });

  it("treats a real error as settled so the skeleton does not shimmer forever", async () => {
    const wrapper = mountCard({ priority: true });

    await frontCover(wrapper).trigger("error");

    if (skeleton) expect(wrapper.find(skeleton).exists()).toBe(false);
  });
});
