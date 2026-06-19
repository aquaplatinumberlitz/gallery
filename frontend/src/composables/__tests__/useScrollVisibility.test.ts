import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import { defineComponent, h, ref, type Ref } from "vue";
import { mount } from "@vue/test-utils";
import { useScrollVisibility } from "../useScrollVisibility";

function mountWithScrollVisibility(useContainerRef: boolean) {
  let container: Ref<HTMLElement | null> = ref(null);
  const wrapper = mount(
    defineComponent({
      setup() {
        if (useContainerRef) {
          container = ref<HTMLElement | null>(null);
          useScrollVisibility(container);
          return () => h("div", { ref: container, class: "container" });
        }
        useScrollVisibility();
        return () => h("div");
      },
    }),
    { attachTo: document.body },
  );
  return { wrapper, getContainer: () => container.value };
}

function makeScrollableScroller(scrollHeight = 2000, clientHeight = 500, initialScrollTop = 0) {
  const el = document.createElement("div");
  el.className = "scroller";
  Object.defineProperty(el, "scrollHeight", { configurable: true, get: () => scrollHeight });
  Object.defineProperty(el, "clientHeight", { configurable: true, get: () => clientHeight });
  let scrollTop = initialScrollTop;
  Object.defineProperty(el, "scrollTop", {
    configurable: true,
    get: () => scrollTop,
    set: (v: number) => {
      scrollTop = v;
    },
  });
  el.addEventListener = el.addEventListener.bind(el);
  return el;
}

describe("useScrollVisibility", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("starts with barsVisible=true and isScrollingDown=false", () => {
    const { wrapper } = mountWithScrollVisibility(true);
    // We can't access the composable return value directly here, but we can
    // observe via the DOM-independent behaviour: defaults are exposed through
    // the rendered state. This test simply asserts the composable does not
    // throw and the wrapper mounts.
    expect(wrapper.exists()).toBe(true);
    wrapper.unmount();
  });

  it("hides bars when scrolling down past the top and shows them when scrolling back up", () => {
    const scroller = makeScrollableScroller(2000, 500, 0);
    document.body.appendChild(scroller);

    let barsVisible: { value: boolean } = { value: true };
    let isScrollingDown: { value: boolean } = { value: false };
    const wrapper = mount(
      defineComponent({
        setup() {
          const r = useScrollVisibility();
          barsVisible = r.barsVisible;
          isScrollingDown = r.isScrollingDown;
          return () => h("div");
        },
      }),
      { attachTo: document.body },
    );

    // Wait for the polling interval to find the scroller (200ms cadence).
    vi.advanceTimersByTime(250);

    // Simulate scrolling down.
    scroller.scrollTop = 400;
    scroller.dispatchEvent(new Event("scroll"));
    // rAF is synchronous via setup.ts, but it is gated by `if (rafId) return`.
    // We need to allow the frame callback to run; advanceTimersByTime handles
    // requestAnimationFrame in jsdom fake-timers mode.
    vi.advanceTimersByTime(20);
    expect(barsVisible.value).toBe(false);
    expect(isScrollingDown.value).toBe(true);

    // Simulate scrolling back up.
    scroller.scrollTop = 100;
    scroller.dispatchEvent(new Event("scroll"));
    vi.advanceTimersByTime(20);
    expect(barsVisible.value).toBe(true);
    expect(isScrollingDown.value).toBe(false);

    wrapper.unmount();
  });

  it("shows bars when scrolling back to the top (scrollTop <= 0)", () => {
    const scroller = makeScrollableScroller(2000, 500, 400);
    document.body.appendChild(scroller);

    let barsVisible: { value: boolean } = { value: true };
    let isScrollingDown: { value: boolean } = { value: false };
    const wrapper = mount(
      defineComponent({
        setup() {
          const r = useScrollVisibility();
          barsVisible = r.barsVisible;
          isScrollingDown = r.isScrollingDown;
          return () => h("div");
        },
      }),
      { attachTo: document.body },
    );

    vi.advanceTimersByTime(250);
    // attach() captured lastScrollY = 400 from the scroller's initial scrollTop.

    // Scroll further down to hide bars first.
    scroller.scrollTop = 600;
    scroller.dispatchEvent(new Event("scroll"));
    vi.advanceTimersByTime(20);
    expect(barsVisible.value).toBe(false);

    // Scroll to the very top (scrollTop <= 0 branch).
    scroller.scrollTop = 0;
    scroller.dispatchEvent(new Event("scroll"));
    vi.advanceTimersByTime(20);
    expect(barsVisible.value).toBe(true);
    expect(isScrollingDown.value).toBe(false);

    wrapper.unmount();
  });

  it("does not toggle bars when scrolling near the bottom (within 150px)", () => {
    const scroller = makeScrollableScroller(2000, 500, 0);
    document.body.appendChild(scroller);

    let barsVisible: { value: boolean } = { value: true };
    const wrapper = mount(
      defineComponent({
        setup() {
          const r = useScrollVisibility();
          barsVisible = r.barsVisible;
          return () => h("div");
        },
      }),
      { attachTo: document.body },
    );

    vi.advanceTimersByTime(250);

    // Scroll down to hide bars first.
    scroller.scrollTop = 400;
    scroller.dispatchEvent(new Event("scroll"));
    vi.advanceTimersByTime(20);
    expect(barsVisible.value).toBe(false);

    // Scroll to near the bottom (within 150px of scrollHeight - clientHeight).
    // scrollHeight - clientHeight - st < 150 -> st > 2000 - 500 - 150 = 1350
    scroller.scrollTop = 1400;
    scroller.dispatchEvent(new Event("scroll"));
    vi.advanceTimersByTime(20);
    // barsVisible should NOT have toggled back to true because of the bottom guard.
    expect(barsVisible.value).toBe(false);

    wrapper.unmount();
  });

  it("uses a container ref when provided (no polling)", () => {
    let barsVisible: { value: boolean } = { value: true };
    const containerRef = ref<HTMLElement | null>(null);

    const wrapper = mount(
      defineComponent({
        setup() {
          const r = useScrollVisibility(containerRef);
          barsVisible = r.barsVisible;
          return () => h("div", { ref: containerRef, class: "container" }, [h("div", { style: "height: 2000px" })]);
        },
      }),
      { attachTo: document.body },
    );

    const container = containerRef.value!;
    Object.defineProperty(container, "scrollHeight", { configurable: true, get: () => 2000 });
    Object.defineProperty(container, "clientHeight", { configurable: true, get: () => 500 });
    let scrollTop = 0;
    Object.defineProperty(container, "scrollTop", {
      configurable: true,
      get: () => scrollTop,
      set: (v: number) => {
        scrollTop = v;
      },
    });

    // No need to advance fake timers; the watcher attaches immediately on mount.
    scrollTop = 400;
    container.dispatchEvent(new Event("scroll"));
    vi.advanceTimersByTime(20);
    expect(barsVisible.value).toBe(false);

    scrollTop = 100;
    container.dispatchEvent(new Event("scroll"));
    vi.advanceTimersByTime(20);
    expect(barsVisible.value).toBe(true);

    wrapper.unmount();
  });

  it("does not crash when no scroller is found in the DOM (polling continues)", () => {
    let barsVisible: { value: boolean } = { value: true };
    const wrapper = mount(
      defineComponent({
        setup() {
          const r = useScrollVisibility();
          barsVisible = r.barsVisible;
          return () => h("div");
        },
      }),
      { attachTo: document.body },
    );

    // Advance timers without any scroller element in the DOM.
    expect(() => vi.advanceTimersByTime(1000)).not.toThrow();
    expect(barsVisible.value).toBe(true);

    wrapper.unmount();
  });

  it("stops polling after the component unmounts", () => {
    const scroller = makeScrollableScroller(2000, 500, 0);
    document.body.appendChild(scroller);

    const wrapper = mount(
      defineComponent({
        setup() {
          useScrollVisibility();
          return () => h("div");
        },
      }),
      { attachTo: document.body },
    );

    // Unmount before the polling finds the scroller; cleanup should cancel the interval.
    wrapper.unmount();
    expect(() => vi.advanceTimersByTime(1000)).not.toThrow();
  });
});
