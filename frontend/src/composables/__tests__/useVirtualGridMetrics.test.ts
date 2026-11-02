/**
 * Purpose: Protect the exact row height and list offset the mobile virtual grid derives from the DOM.
 * Guarantees: The row height is the observed border-box height without rounding (184.5px rows must not
 * drift by half a pixel per row), a close first-frame fallback is used until a row is measured, only
 * one live row is observed at a time and observation moves on when it unmounts, and the scroll margin
 * follows the list's distance from the top of the scroll content.
 * Run when: Changing the mobile gallery grid, TanStack Virtual options, or row measurement.
 */
import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";
import { useUniformRowSize, useVirtualScrollMargin } from "../useVirtualGridMetrics";

class FakeResizeObserver {
  static instances: FakeResizeObserver[] = [];
  readonly observed = new Set<Element>();
  disconnected = false;
  private readonly callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
    FakeResizeObserver.instances.push(this);
  }
  observe(target: Element) {
    this.observed.add(target);
  }
  unobserve(target: Element) {
    this.observed.delete(target);
  }
  disconnect() {
    this.disconnected = true;
    this.observed.clear();
  }
  emit(target: Element, blockSize: number) {
    this.callback(
      [
        {
          target,
          borderBoxSize: [{ blockSize, inlineSize: 100 }],
          contentRect: { height: blockSize - 1 },
        } as unknown as ResizeObserverEntry,
      ],
      this as unknown as ResizeObserver,
    );
  }
}

beforeEach(() => {
  FakeResizeObserver.instances = [];
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useUniformRowSize", () => {
  const setup = (fallback = () => 180) => {
    let api!: ReturnType<typeof useUniformRowSize>;
    const wrapper = mount(
      defineComponent({
        setup() {
          api = useUniformRowSize(fallback);
          return () => h("div");
        },
      }),
    );
    return { api, wrapper, observer: () => FakeResizeObserver.instances[0]! };
  };

  it("uses the fallback until a row has been measured", () => {
    const { api } = setup(() => 184.25);
    expect(api.rowSize.value).toBe(184.25);
  });

  it("never lets the fallback collapse to zero", () => {
    const { api } = setup(() => -4);
    expect(api.rowSize.value).toBe(1);
  });

  it("keeps the exact fractional border-box height instead of rounding", () => {
    const { api, observer } = setup();
    const row = document.createElement("div");
    document.body.appendChild(row);

    api.observeRow(row);
    observer().emit(row, 184.5);

    expect(api.rowSize.value).toBe(184.5);
  });

  it("follows size changes of the observed row, e.g. on rotation", () => {
    const { api, observer } = setup();
    const row = document.createElement("div");
    document.body.appendChild(row);
    api.observeRow(row);

    observer().emit(row, 184.5);
    observer().emit(row, 169.5);

    expect(api.rowSize.value).toBe(169.5);
  });

  it("observes a single row and moves to another one once the first is unmounted", () => {
    const { api, observer } = setup();
    const first = document.createElement("div");
    const second = document.createElement("div");
    document.body.append(first, second);

    api.observeRow(first);
    api.observeRow(second);
    expect([...observer().observed]).toEqual([first]);

    first.remove();
    api.observeRow(second);

    expect([...observer().observed]).toEqual([second]);
  });

  it("ignores empty ref callbacks and disconnects on unmount", () => {
    const { api, wrapper, observer } = setup();
    api.observeRow(null);
    expect(FakeResizeObserver.instances).toHaveLength(0);

    const row = document.createElement("div");
    document.body.appendChild(row);
    api.observeRow(row);
    wrapper.unmount();

    expect(observer().disconnected).toBe(true);
  });
});

describe("useVirtualScrollMargin", () => {
  const rect = (top: number) => ({ top }) as DOMRect;

  it("measures the list offset from the top of the scroll content", async () => {
    const scroller = document.createElement("div");
    const leading = document.createElement("div");
    const list = document.createElement("div");
    scroller.append(leading, list);
    document.body.appendChild(scroller);
    // Scroller at y=50 scrolled by 120px, list currently at y=210 => 280px below the content top.
    scroller.scrollTop = 120;
    vi.spyOn(scroller, "getBoundingClientRect").mockReturnValue(rect(50));
    vi.spyOn(list, "getBoundingClientRect").mockReturnValue(rect(210));

    const scrollRef = ref<HTMLElement | null>(scroller);
    const listRef = ref<HTMLElement | null>(list);
    const leadingRef = ref<HTMLElement | null>(leading);
    let api!: ReturnType<typeof useVirtualScrollMargin>;
    mount(
      defineComponent({
        setup() {
          api = useVirtualScrollMargin(scrollRef, listRef, leadingRef);
          return () => h("div");
        },
      }),
    );
    await nextTick();

    expect(api.scrollMargin.value).toBe(280);
    const observer = FakeResizeObserver.instances[FakeResizeObserver.instances.length - 1]!;
    expect([...observer.observed]).toEqual([scroller, leading]);
  });

  it("re-measures when the leading content changes size", async () => {
    const scroller = document.createElement("div");
    const leading = document.createElement("div");
    const list = document.createElement("div");
    scroller.append(leading, list);
    document.body.appendChild(scroller);
    vi.spyOn(scroller, "getBoundingClientRect").mockReturnValue(rect(0));
    let listTop = 271;
    vi.spyOn(list, "getBoundingClientRect").mockImplementation(() => rect(listTop));

    let api!: ReturnType<typeof useVirtualScrollMargin>;
    mount(
      defineComponent({
        setup() {
          api = useVirtualScrollMargin(ref(scroller), ref(list), ref(leading));
          return () => h("div");
        },
      }),
    );
    await nextTick();
    expect(api.scrollMargin.value).toBe(271);

    // Album strip collapsed.
    listTop = 41;
    FakeResizeObserver.instances[FakeResizeObserver.instances.length - 1]!.emit(leading, 0);

    expect(api.scrollMargin.value).toBe(41);
  });
});
