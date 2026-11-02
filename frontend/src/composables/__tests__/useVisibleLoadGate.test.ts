/**
 * Purpose: Protect the visibility gate that decides when a grid card may start its image request.
 * Guarantees: A request starts only after the card stayed in view for the dwell time, is cancelled
 * (shouldLoad back to false) when the card leaves before the image settled, is never cancelled once
 * settled, and is skipped entirely for immediate (first-row / already seen) cards.
 * Run when: Changing PhotoCard or album card image loading, or the scroll-root detection.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";
import { mount } from "@vue/test-utils";
import {
  findScrollRoot,
  SCROLL_IDLE_MS,
  useVisibleLoadGate,
  VISIBLE_LOAD_DWELL_MS,
  type UseVisibleLoadGateOptions,
} from "../useVisibleLoadGate";

class FakeIntersectionObserver {
  static instances: FakeIntersectionObserver[] = [];
  readonly options: IntersectionObserverInit | undefined;
  readonly targets: Element[] = [];
  disconnected = false;
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
  disconnect() {
    this.disconnected = true;
  }
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

/** The window is the scroll root when no scrolling ancestor exists; a scroll event starts "active scrolling". */
const scroll = () => window.dispatchEvent(new Event("scroll"));

const observer = () => FakeIntersectionObserver.instances[FakeIntersectionObserver.instances.length - 1]!;

function mountGate(options: Partial<UseVisibleLoadGateOptions> = {}) {
  const settled = ref(false);
  const immediate = ref(false);
  let api!: ReturnType<typeof useVisibleLoadGate>;
  const wrapper = mount(
    defineComponent({
      setup() {
        const target = ref<HTMLElement | null>(null);
        api = useVisibleLoadGate({
          target,
          settled: () => settled.value,
          immediate: () => immediate.value,
          ...options,
        });
        return () => h("div", { ref: target, class: "card" });
      },
    }),
  );
  return { wrapper, api, settled, immediate };
}

describe("useVisibleLoadGate", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeIntersectionObserver.instances = [];
    vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not load before the card is visible", () => {
    const { api } = mountGate();
    vi.advanceTimersByTime(5000);
    expect(api.shouldLoad.value).toBe(false);
  });

  it("while scrolling, loads only after the card stayed visible for the dwell time", () => {
    const { api } = mountGate();
    scroll();
    observer().emit(true);

    vi.advanceTimersByTime(VISIBLE_LOAD_DWELL_MS - 1);
    expect(api.shouldLoad.value).toBe(false);
    vi.advanceTimersByTime(1);
    expect(api.shouldLoad.value).toBe(true);
  });

  it("loads a card that is in range at mount at once when nothing is scrolling", () => {
    const { api } = mountGate();
    observer().emit(true);

    expect(api.shouldLoad.value).toBe(true);
  });

  it("loads a card that comes into range after the root stopped scrolling at once", () => {
    const { api } = mountGate();
    scroll();
    vi.advanceTimersByTime(SCROLL_IDLE_MS);

    observer().emit(true);

    expect(api.shouldLoad.value).toBe(true);
  });

  it("makes a card entering during active scrolling wait for the dwell", () => {
    const { api } = mountGate();
    scroll();
    observer().emit(true);

    expect(api.shouldLoad.value).toBe(false);
    vi.advanceTimersByTime(VISIBLE_LOAD_DWELL_MS - 1);
    expect(api.shouldLoad.value).toBe(false);
  });

  it("starts a dwell-pending card at once when scrolling stops", () => {
    const { api } = mountGate({ dwellMs: 1000 });
    scroll();
    observer().emit(true);
    vi.advanceTimersByTime(SCROLL_IDLE_MS - 1);
    expect(api.shouldLoad.value).toBe(false);

    vi.advanceTimersByTime(1);

    expect(api.shouldLoad.value).toBe(true);
  });

  it("does not start a pending card that left the range before scrolling stopped", () => {
    const { api } = mountGate();
    scroll();
    observer().emit(true);
    observer().emit(false);

    vi.advanceTimersByTime(SCROLL_IDLE_MS);

    expect(api.shouldLoad.value).toBe(false);
  });

  it("keeps treating continuous scrolling as active", () => {
    const { api } = mountGate({ dwellMs: 1000 });
    for (let i = 0; i < 5; i++) {
      scroll();
      vi.advanceTimersByTime(SCROLL_IDLE_MS - 10);
    }
    observer().emit(true);

    expect(api.shouldLoad.value).toBe(false);
  });

  it("shares one scroll listener per scroll root and removes it on unmount", () => {
    const add = vi.spyOn(window, "addEventListener");
    const remove = vi.spyOn(window, "removeEventListener");
    const first = mountGate();
    const second = mountGate();
    expect(add.mock.calls.filter(([type]) => type === "scroll")).toHaveLength(1);

    first.wrapper.unmount();
    expect(remove.mock.calls.filter(([type]) => type === "scroll")).toHaveLength(0);
    second.wrapper.unmount();
    expect(remove.mock.calls.filter(([type]) => type === "scroll")).toHaveLength(1);
  });

  it("never starts a card that scrolls past before the dwell time", () => {
    const { api } = mountGate();
    scroll();
    observer().emit(true);
    vi.advanceTimersByTime(60);
    observer().emit(false);
    vi.advanceTimersByTime(1000);

    expect(api.shouldLoad.value).toBe(false);
  });

  it("cancels an unfinished load when the card leaves, and restarts the dwell on re-entry", () => {
    const { api } = mountGate();
    scroll();
    observer().emit(true);
    vi.advanceTimersByTime(VISIBLE_LOAD_DWELL_MS);
    expect(api.shouldLoad.value).toBe(true);

    observer().emit(false);
    expect(api.shouldLoad.value).toBe(false);

    scroll();
    observer().emit(true);
    vi.advanceTimersByTime(VISIBLE_LOAD_DWELL_MS - 1);
    expect(api.shouldLoad.value).toBe(false);
    vi.advanceTimersByTime(1);
    expect(api.shouldLoad.value).toBe(true);
  });

  it("keeps a settled load when the card leaves", () => {
    const { api, settled } = mountGate();
    observer().emit(true);
    vi.advanceTimersByTime(VISIBLE_LOAD_DWELL_MS);
    settled.value = true;

    observer().emit(false);

    expect(api.shouldLoad.value).toBe(true);
  });

  it("loads immediate cards at once and never cancels them", async () => {
    const { api, immediate } = mountGate();
    immediate.value = true;
    await nextTick();
    expect(api.shouldLoad.value).toBe(true);

    observer().emit(true);
    observer().emit(false);
    expect(api.shouldLoad.value).toBe(true);
  });

  it("starts true when the card is immediate from the beginning", () => {
    let api!: ReturnType<typeof useVisibleLoadGate>;
    mount(
      defineComponent({
        setup() {
          api = useVisibleLoadGate({ target: ref(null), settled: () => false, immediate: () => true });
          return () => h("div");
        },
      }),
    );
    expect(api.shouldLoad.value).toBe(true);
  });

  it("re-arms for a new image on a card that is still in view", () => {
    const { api, settled } = mountGate();
    scroll();
    observer().emit(true);
    vi.advanceTimersByTime(VISIBLE_LOAD_DWELL_MS);
    settled.value = true;
    expect(api.shouldLoad.value).toBe(true);

    settled.value = false;
    api.reset();
    expect(api.shouldLoad.value).toBe(false);

    vi.advanceTimersByTime(VISIBLE_LOAD_DWELL_MS);
    expect(api.shouldLoad.value).toBe(true);
  });

  it("loads right away when IntersectionObserver is unavailable", () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    const { api } = mountGate();
    expect(api.shouldLoad.value).toBe(true);
  });

  it("observes the card against its scroll root with the given margin and disconnects on unmount", () => {
    const scroller = document.createElement("div");
    scroller.style.overflowY = "auto";
    document.body.appendChild(scroller);
    const wrapper = mount(
      defineComponent({
        setup() {
          const target = ref<HTMLElement | null>(null);
          useVisibleLoadGate({ target, settled: () => false, rootMargin: "300px 0px" });
          return () => h("div", { ref: target });
        },
      }),
      { attachTo: scroller },
    );

    expect(observer().options?.root).toBe(scroller);
    expect(observer().options?.rootMargin).toBe("300px 0px");

    wrapper.unmount();
    expect(observer().disconnected).toBe(true);
  });
});

describe("findScrollRoot", () => {
  const build = (outerStyle: string, innerStyle = "") => {
    const outer = document.createElement("div");
    outer.style.cssText = outerStyle;
    const inner = document.createElement("div");
    inner.style.cssText = innerStyle;
    const leaf = document.createElement("div");
    inner.appendChild(leaf);
    outer.appendChild(inner);
    document.body.appendChild(outer);
    return { outer, inner, leaf };
  };

  it("returns the nearest vertically scrolling ancestor and skips overflow-hidden boxes", () => {
    const { outer, leaf } = build("overflow-y: auto", "overflow: hidden");
    expect(findScrollRoot(leaf, "y")).toBe(outer);
  });

  it("returns the nearest horizontally clipping ancestor for the x axis, including overflow-hidden carousels", () => {
    const { inner, leaf } = build("overflow-x: auto", "overflow-x: hidden");
    expect(findScrollRoot(leaf, "x")).toBe(inner);
  });

  it("returns null when nothing clips, so the viewport is used", () => {
    const { leaf } = build("");
    expect(findScrollRoot(leaf, "y")).toBeNull();
  });
});
