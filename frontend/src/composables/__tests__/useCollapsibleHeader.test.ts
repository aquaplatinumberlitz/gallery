import { afterEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, ref, type Ref } from "vue";
import { mount } from "@vue/test-utils";
import { COLLAPSE_SCROLL_Y, EXPAND_SCROLL_Y, useCollapsibleHeader } from "@/composables/useCollapsibleHeader";

function makeScroller(initialScrollTop = 0) {
  const el = document.createElement("div");
  let scrollTop = initialScrollTop;

  Object.defineProperty(el, "scrollTop", {
    configurable: true,
    get: () => scrollTop,
    set: (value: number) => {
      scrollTop = value;
    },
  });
  Object.defineProperty(el, "scrollHeight", { configurable: true, get: () => 2000 });
  Object.defineProperty(el, "clientHeight", { configurable: true, get: () => 500 });

  document.body.appendChild(el);
  return el;
}

function mountComposable(scrollerRef: Ref<HTMLElement | null>, enabled: Ref<boolean> = ref(true)) {
  let isHeaderCollapsed: { value: boolean } = { value: false };
  const wrapper = mount(
    defineComponent({
      setup() {
        const result = useCollapsibleHeader(scrollerRef, { enabled });
        isHeaderCollapsed = result.isHeaderCollapsed;
        return () => h("div");
      },
    }),
  );

  return { wrapper, isHeaderCollapsed };
}

async function scrollTo(scroller: HTMLElement, scrollTop: number) {
  scroller.scrollTop = scrollTop;
  scroller.dispatchEvent(new Event("scroll"));
  if (typeof window.requestAnimationFrame === "function") {
    await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
  }
  await nextTick();
}

describe("useCollapsibleHeader", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  it("starts expanded at the top", async () => {
    const scroller = makeScroller(0);
    const { wrapper, isHeaderCollapsed } = mountComposable(ref(scroller));

    await nextTick();

    expect(isHeaderCollapsed.value).toBe(false);
    wrapper.unmount();
  });

  it("starts collapsed when the scroll container is already beyond the collapse threshold", async () => {
    const scroller = makeScroller(COLLAPSE_SCROLL_Y + 1);
    const { wrapper, isHeaderCollapsed } = mountComposable(ref(scroller));

    await nextTick();

    expect(isHeaderCollapsed.value).toBe(true);
    wrapper.unmount();
  });

  it("collapses after scrolling beyond 120px", async () => {
    const scroller = makeScroller(0);
    const { wrapper, isHeaderCollapsed } = mountComposable(ref(scroller));

    await scrollTo(scroller, COLLAPSE_SCROLL_Y + 1);

    expect(isHeaderCollapsed.value).toBe(true);
    wrapper.unmount();
  });

  it("stays collapsed while scrolling upward above the expand threshold", async () => {
    const scroller = makeScroller(0);
    const { wrapper, isHeaderCollapsed } = mountComposable(ref(scroller));

    await scrollTo(scroller, COLLAPSE_SCROLL_Y + 1);
    await scrollTo(scroller, EXPAND_SCROLL_Y + 1);

    expect(isHeaderCollapsed.value).toBe(true);
    wrapper.unmount();
  });

  it("expands again at 48px", async () => {
    const scroller = makeScroller(0);
    const { wrapper, isHeaderCollapsed } = mountComposable(ref(scroller));

    await scrollTo(scroller, COLLAPSE_SCROLL_Y + 1);
    await scrollTo(scroller, EXPAND_SCROLL_Y);

    expect(isHeaderCollapsed.value).toBe(false);
    wrapper.unmount();
  });

  it("does not leave duplicate scroll listeners across unmount and remount", async () => {
    const scroller = makeScroller(0);
    const addSpy = vi.spyOn(scroller, "addEventListener");
    const removeSpy = vi.spyOn(scroller, "removeEventListener");

    const first = mountComposable(ref(scroller));
    await nextTick();
    first.wrapper.unmount();

    const second = mountComposable(ref(scroller));
    await nextTick();
    second.wrapper.unmount();

    expect(addSpy.mock.calls.filter(([event]) => event === "scroll")).toHaveLength(2);
    expect(removeSpy.mock.calls.filter(([event]) => event === "scroll")).toHaveLength(2);
  });

  it("resets to expanded when disabled for a non-gallery route", async () => {
    const scroller = makeScroller(0);
    const enabled = ref(true);
    const { wrapper, isHeaderCollapsed } = mountComposable(ref(scroller), enabled);

    await scrollTo(scroller, COLLAPSE_SCROLL_Y + 1);
    enabled.value = false;
    await nextTick();

    expect(isHeaderCollapsed.value).toBe(false);
    wrapper.unmount();
  });
});
