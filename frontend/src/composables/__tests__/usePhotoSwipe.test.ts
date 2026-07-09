import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h, ref, computed } from "vue";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import type { FileNode, MetadataResponse } from "@/types";
import { usePhotoSwipe } from "../usePhotoSwipe";
import { useLightboxStore } from "@/stores/lightbox";
import { queryClient } from "@/query";
import { queryKeys } from "@/query/keys";
import { fetchMetadata } from "@/services/api";
import { shouldAlwaysLoadOriginal, type LightboxDimensions, type PhotoSwipeImageItem } from "@/utils/lightbox";

interface MockPswpInstance {
  currIndex: number;
  currSlide: null | Record<string, unknown>;
  options: Record<string, unknown> & { dataSource: unknown[] };
  init: ReturnType<typeof vi.fn>;
  destroy: ReturnType<typeof vi.fn>;
  goTo: ReturnType<typeof vi.fn>;
  on: ReturnType<typeof vi.fn>;
  refreshSlideContent: ReturnType<typeof vi.fn>;
}

const { pswpInstances, pswpEventHandlers, triggerPswpEvent } = vi.hoisted(() => {
  const instances: MockPswpInstance[] = [];
  const eventHandlers = new Map<MockPswpInstance, Map<string, Array<(...args: any[]) => void>>>();
  function triggerPswpEvent(instance: MockPswpInstance, event: string, ...args: any[]) {
    const handlers = eventHandlers.get(instance)?.get(event);
    if (handlers) {
      for (const handler of handlers) {
        handler(...args);
      }
    }
  }
  return { pswpInstances: instances, pswpEventHandlers: eventHandlers, triggerPswpEvent };
});

vi.mock("photoswipe", () => ({
  default: vi.fn(function (opts: Record<string, unknown>) {
    const dataSource = (opts?.dataSource ?? []) as unknown[];
    const index = (opts?.index ?? 0) as number;
    const instance: MockPswpInstance = {
      currIndex: index,
      currSlide: null,
      options: { ...opts, dataSource },
      init: vi.fn(() => {
        const handlers = pswpEventHandlers.get(instance)?.get("uiRegister");
        if (handlers) {
          for (const fn of handlers) fn();
        }
      }),
      destroy: vi.fn(),
      goTo: vi.fn(),
      on: vi.fn((event: string, handler: (...args: any[]) => void) => {
        const handlers = pswpEventHandlers.get(instance);
        if (handlers) {
          if (!handlers.has(event)) handlers.set(event, []);
          handlers.get(event)!.push(handler);
        }
      }),
      refreshSlideContent: vi.fn(),
    };
    pswpEventHandlers.set(instance, new Map());
    pswpInstances.push(instance);
    return instance;
  }),
}));

vi.mock("@/services/api", () => ({
  fetchMetadata: vi.fn(),
  getImageUrl: vi.fn((p: string) => `/api/image?path=${encodeURIComponent(p)}`),
  getPreviewUrl: vi.fn((p: string) => `/api/preview?path=${encodeURIComponent(p)}`),
  getThumbnailUrl: vi.fn(),
}));

vi.mock("@/utils/lightbox", () => ({
  buildPhotoSwipeItem: vi.fn((item: FileNode, resolvedDimensions?: LightboxDimensions | null) => {
    const previewSrc = `/api/preview?path=${encodeURIComponent(item.path)}`;
    const isAnimatedAsset = /\.(gif|apng)$/i.test(item.path || item.name || "");
    return {
      src: previewSrc,
      previewSrc,
      msrc: `/api/thumb?path=${encodeURIComponent(item.path)}`,
      width: resolvedDimensions?.width ?? 800,
      height: resolvedDimensions?.height ?? 600,
      alt: item.name,
      path: item.path,
      isAnimatedAsset,
    };
  }),
  hasValidDimensions: vi.fn((d: { width?: number | null; height?: number | null } | null | undefined) => {
    if (!d) return false;
    return typeof d.width === "number" && d.width > 0 && typeof d.height === "number" && d.height > 0;
  }),
  LIGHTBOX_PREVIEW_EDGE: 1440,
  LIGHTBOX_ORIGINAL_ZOOM_THRESHOLD: 1.2,
  shouldAlwaysLoadOriginal: vi.fn(() => false),
}));

vi.mock("@/debug/lightboxDomReport", () => ({
  registerLightboxDOMReport: vi.fn(),
}));

vi.mock("@/debug/lightboxNavDebug", () => ({
  logLightboxNavDebug: vi.fn(),
  summarizeLightboxItems: vi.fn(() => ({ total: 0, currentIndex: 0 })),
}));

vi.mock("@/query", () => {
  const testQueryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 30_000 } },
  });
  return { queryClient: testQueryClient };
});

function mockImageConstructor() {
  const originalImage = globalThis.Image;
  globalThis.Image = function (this: any) {
    this.onload = null;
    this.onerror = null;
    this.decoding = "async";
    this.naturalWidth = 800;
    this.naturalHeight = 600;
    this._src = "";
    this.decode = () => Promise.resolve();
  } as unknown as typeof Image;
  Object.defineProperty(globalThis.Image.prototype, "src", {
    get() {
      return this._src;
    },
    set(url: string) {
      this._src = url;
      if (this.onload) this.onload();
    },
    configurable: true,
  });
  return () => {
    globalThis.Image = originalImage;
  };
}

function makeItem(path: string, name: string): FileNode {
  return { path, name, type: "image", mtime: 1000 };
}

interface SetupOptions {
  preloadedStoreDimensions?: Record<string, LightboxDimensions>;
  onRegisterUi?: (pswp: any) => void;
  onAfterInit?: (pswp: any) => void;
}

function setup(items: FileNode[], currentIndex = 0, isInitiallyOpen = false, options?: SetupOptions) {
  restoreImage = mockImageConstructor();
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const pinia = createPinia();
  setActivePinia(pinia);

  if (options?.preloadedStoreDimensions) {
    const store = useLightboxStore();
    for (const [path, dims] of Object.entries(options.preloadedStoreDimensions)) {
      store.dimensionsByPath[path] = dims;
    }
  }

  const containerRef = ref<HTMLElement | null>(document.createElement("div"));
  const itemsRef = ref(items);
  const currentIndexRef = ref(currentIndex);
  const isOpenRef = ref(isInitiallyOpen);
  const onIndexChange = vi.fn();
  const onClose = vi.fn();

  let result!: ReturnType<typeof usePhotoSwipe>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = usePhotoSwipe({
          containerRef,
          items: computed(() => itemsRef.value),
          currentIndex: currentIndexRef,
          isOpen: isOpenRef,
          onIndexChange,
          onClose,
          onRegisterUi: options?.onRegisterUi,
          onAfterInit: options?.onAfterInit,
        });
        return () => h("div");
      },
    }),
    { global: { plugins: [pinia, [VueQueryPlugin, { queryClient }]] } },
  );
  return { result, wrapper, isOpenRef, currentIndexRef, onIndexChange, onClose };
}

let restoreImage: (() => void) | null = null;

beforeEach(() => {
  vi.clearAllMocks();
  pswpInstances.length = 0;
  pswpEventHandlers.clear();
  queryClient.clear();
});

afterEach(() => {
  delete (window as any).__pswp;
  delete (window as any).__loadOriginalForCurrent;
  if (restoreImage) {
    restoreImage();
    restoreImage = null;
  }
  (shouldAlwaysLoadOriginal as unknown as ReturnType<typeof vi.fn>).mockImplementation(() => false);
  (fetchMetadata as unknown as ReturnType<typeof vi.fn>).mockReset();
});

describe("usePhotoSwipe", () => {
  it("mounts and exposes expected return values", () => {
    const { result } = setup([makeItem("/img1.png", "img1.png")]);
    expect(result.pswp.value).toBeNull();
    expect(typeof result.destroyPhotoSwipe).toBe("function");
    expect(typeof result.loadOriginalForCurrent).toBe("function");
    expect(result.originalLoadingPath.value).toBeNull();
  });

  it("creates PhotoSwipe instance when isOpen becomes true", async () => {
    const { result, isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, false);
    expect(result.pswp.value).toBeNull();

    isOpenRef.value = true;
    await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());
  });

  it("zooms on image click and only closes from the backdrop", async () => {
    const { isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, false);

    isOpenRef.value = true;
    await vi.waitFor(() => expect(pswpInstances.length).toBe(1));

    expect(pswpInstances[0].options).toMatchObject({
      imageClickAction: "zoom",
      clickToCloseNonZoomable: false,
      bgClickAction: "close",
    });
  });

  it("destroys PhotoSwipe when isOpen becomes false", async () => {
    const { result, isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, true);
    await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());

    isOpenRef.value = false;
    await vi.waitFor(() => {
      expect(result.pswp.value).toBeNull();
    });
  });

  it("registers event handlers on the PhotoSwipe instance", async () => {
    const { result, isOpenRef } = setup(
      [makeItem("/img1.png", "img1.png"), makeItem("/img2.png", "img2.png")],
      0,
      false,
    );

    isOpenRef.value = true;
    await vi.waitFor(() => {
      expect(result.pswp.value).not.toBeNull();
      expect(pswpInstances.length).toBeGreaterThan(0);
    });

    const instance = pswpInstances[0];
    const registeredEvents = instance.on.mock.calls.map((c: any) => c[0]);
    expect(registeredEvents).toContain("change");
    expect(registeredEvents).toContain("close");
    expect(registeredEvents).toContain("zoomPanUpdate");
    expect(registeredEvents).toContain("beforeZoomTo");
    expect(registeredEvents).toContain("loadError");
  });

  it("exposes test hooks on window in test mode", async () => {
    const { isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, false);

    isOpenRef.value = true;
    await vi.waitFor(() => expect((window as any).__pswp).toBeDefined());
    expect(typeof (window as any).__loadOriginalForCurrent).toBe("function");
  });

  it("cleanly destroys on unmount", async () => {
    const { result, isOpenRef, wrapper } = setup([makeItem("/img1.png", "img1.png")], 0, false);

    isOpenRef.value = true;
    await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());

    wrapper.unmount();
    expect(result.pswp.value).toBeNull();
  });

  it("can be destroyed multiple times without error", () => {
    const { result } = setup([makeItem("/img1.png", "img1.png")]);
    expect(() => {
      result.destroyPhotoSwipe();
      result.destroyPhotoSwipe();
    }).not.toThrow();
  });

  it("loadOriginalForCurrent returns resolved promise when no instance", async () => {
    const { result } = setup([makeItem("/img1.png", "img1.png")]);
    const ret = result.loadOriginalForCurrent("fullscreen");
    await expect(ret).resolves.toBeUndefined();
  });

  describe("dimension resolution chain", () => {
    it("uses scan dimensions when item has width/height on the FileNode", async () => {
      const item = { ...makeItem("/img1.png", "img1.png"), width: 1920, height: 1080 };
      const { result, isOpenRef } = setup([item], 0, false);

      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());
      const dataItem = pswpInstances[0].options.dataSource[0] as PhotoSwipeImageItem;
      expect(dataItem.width).toBe(1920);
      expect(dataItem.height).toBe(1080);
    });

    it("falls back to remembered dimensions from store", async () => {
      const item = makeItem("/img1.png", "img1.png");
      const { result, isOpenRef } = setup([item], 0, false, {
        preloadedStoreDimensions: { "/img1.png": { width: 1920, height: 1080, source: "metadata" } },
      });

      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());
      const dataItem = pswpInstances[0].options.dataSource[0] as PhotoSwipeImageItem;
      expect(dataItem.width).toBe(1920);
      expect(dataItem.height).toBe(1080);
    });

    it("ignores remembered dimensions with thumbnail source", async () => {
      const item = makeItem("/img1.png", "img1.png");
      const { result, isOpenRef } = setup([item], 0, false, {
        preloadedStoreDimensions: { "/img1.png": { width: 200, height: 200, source: "thumbnail" } },
      });

      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());
      const store = useLightboxStore();
      expect(store.dimensionsByPath["/img1.png"]?.source).toBe("preview");
    });

    it("falls back to cached metadata dimensions", async () => {
      queryClient.setQueryData(queryKeys.metadata("/img1.png"), {
        width: 1920,
        height: 1080,
        name: "test",
        tool: "test",
        prompt: "",
        negative_prompt: "",
        params: {},
      } as MetadataResponse);
      const item = makeItem("/img1.png", "img1.png");
      const { result, isOpenRef } = setup([item], 0, false);

      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());
      const dataItem = pswpInstances[0].options.dataSource[0] as PhotoSwipeImageItem;
      expect(dataItem.width).toBe(1920);
      expect(dataItem.height).toBe(1080);
    });

    it("loads preview dimensions via Image when no scan/remembered/cached dimensions exist", async () => {
      const item = makeItem("/img1.png", "img1.png");
      const { result, isOpenRef } = setup([item], 0, false);

      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());
      const store = useLightboxStore();
      expect(store.dimensionsByPath["/img1.png"]).toEqual({ width: 800, height: 600, source: "preview" });
    });

    it("returns null from resolveOpeningSlideDimensions when all methods fail", async () => {
      (fetchMetadata as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("fetch failed"));

      const { result, isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, false);

      globalThis.Image = function (this: any) {
        this.onload = null;
        this.onerror = null;
        this._src = "";
        this.decode = () => Promise.resolve();
      } as unknown as typeof Image;
      Object.defineProperty(globalThis.Image.prototype, "src", {
        get() {
          return this._src;
        },
        set(url: string) {
          this._src = url;
          if (this.onerror) this.onerror();
        },
        configurable: true,
      });

      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());

      const dataItem = pswpInstances[0].options.dataSource[0] as PhotoSwipeImageItem;
      expect(dataItem.width).toBe(800);
      expect(dataItem.height).toBe(600);
    });

    it("fetches metadata dimensions when preview fails", async () => {
      const { result, isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, false);

      globalThis.Image = function (this: any) {
        this.onload = null;
        this.onerror = null;
        this._src = "";
        this.decode = () => Promise.resolve();
      } as unknown as typeof Image;
      Object.defineProperty(globalThis.Image.prototype, "src", {
        get() {
          return this._src;
        },
        set(url: string) {
          this._src = url;
          if (this.onerror) this.onerror();
        },
        configurable: true,
      });

      (fetchMetadata as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
        width: 1920,
        height: 1080,
        name: "test",
        tool: "test",
        prompt: "",
        negative_prompt: "",
        params: {},
      });

      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());
      const store = useLightboxStore();
      expect(store.dimensionsByPath["/img1.png"]?.source).toBe("metadata");
      expect(store.dimensionsByPath["/img1.png"]?.width).toBe(1920);
    });
  });

  describe("applyResolvedDimensions", () => {
    function makeItems() {
      return [makeItem("/img1.png", "img1.png"), makeItem("/img2.png", "img2.png")];
    }

    it("applies dimensions from fetchMetadata and remembers in store", async () => {
      (fetchMetadata as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
        width: 1920,
        height: 1080,
        name: "img2",
        tool: "test",
        prompt: "",
        negative_prompt: "",
        params: {},
      });

      const items = makeItems();
      const { result, isOpenRef } = setup(items, 0, false);

      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());
      const instance = pswpInstances[0];
      instance.currIndex = 1;
      triggerPswpEvent(instance, "change");

      await vi.waitFor(() => {
        const dataItem = instance.options.dataSource[1] as PhotoSwipeImageItem;
        expect(dataItem.width).toBe(1920);
        expect(dataItem.height).toBe(1080);
      });
      const store = useLightboxStore();
      expect(store.dimensionsByPath["/img2.png"]?.width).toBe(1920);
    });

    it("handles fetchMetadata rejection during resolveDimensions", async () => {
      (fetchMetadata as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("fetch failed"));

      const items = [makeItem("/img1.png", "img1.png"), makeItem("/img2.png", "img2.png")];
      const { result, isOpenRef } = setup(items, 0, false);

      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());
      const instance = pswpInstances[0];
      instance.currIndex = 1;
      triggerPswpEvent(instance, "change");

      await vi.waitFor(() => {
        expect(fetchMetadata as ReturnType<typeof vi.fn>).toHaveBeenCalled();
      });
    });

    it("calls refreshSlideContent when applying dimensions to non-current slide", async () => {
      (fetchMetadata as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
        width: 1920,
        height: 1080,
        name: "img2",
        tool: "test",
        prompt: "",
        negative_prompt: "",
        params: {},
      });

      const items = makeItems();
      const { result, isOpenRef } = setup(items, 0, false);

      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());
      const instance = pswpInstances[0];
      instance.currIndex = 1;

      triggerPswpEvent(instance, "change");
      await vi.waitFor(() => expect(instance.refreshSlideContent).toHaveBeenCalledWith(1));
    });
  });

  describe("loadOriginalForIndex", () => {
    async function openWithCurrSlide() {
      const { result, isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, false);
      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());
      const instance = pswpInstances[0];
      instance.currSlide = {
        index: 0,
        data: {} as Record<string, unknown>,
        content: {
          data: {} as Record<string, unknown>,
          element: document.createElement("img"),
        } as Record<string, unknown>,
        resize: vi.fn(),
      } as any;
      return { result, instance };
    }

    it("loads original image and swaps slide content", async () => {
      const { result, instance } = await openWithCurrSlide();
      const p = result.loadOriginalForCurrent("fullscreen");
      await p;

      const dataItem = instance.options.dataSource[0] as PhotoSwipeImageItem;
      expect(dataItem.isOriginalLoaded).toBe(true);
      expect(dataItem.originalLoadReason).toBe("fullscreen");
      expect(dataItem.src).toBe("/api/image?path=%2Fimg1.png");
    });

    it("deduplicates concurrent original loads for same src", async () => {
      const { result } = await openWithCurrSlide();

      const origImage = globalThis.Image;
      globalThis.Image = function (this: any) {
        this.onload = null;
        this.onerror = null;
        this._src = "";
        this.decode = () => Promise.resolve();
      } as unknown as typeof Image;
      Object.defineProperty(globalThis.Image.prototype, "src", {
        get() {
          return this._src;
        },
        set(url: string) {
          this._src = url;
          setTimeout(() => {
            if (this.onload) this.onload();
          }, 50);
        },
        configurable: true,
      });

      const p1 = result.loadOriginalForCurrent("fullscreen");
      const p2 = result.loadOriginalForCurrent("fullscreen");

      expect(p1).toBe(p2);
      globalThis.Image = origImage;
      await Promise.all([p1, p2]);
    });

    it("returns immediately if original is already loaded", async () => {
      const { result, instance } = await openWithCurrSlide();
      const dataItem = instance.options.dataSource[0] as PhotoSwipeImageItem;
      dataItem.isOriginalLoaded = true;

      const p = result.loadOriginalForCurrent("fullscreen");
      await expect(p).resolves.toBeUndefined();
      expect(dataItem.originalLoadReason).toBe("fullscreen");
    });

    it("handles Image API unavailability in loadOriginalForIndex", async () => {
      const { result } = await openWithCurrSlide();

      (globalThis as any).Image = undefined;

      const p = result.loadOriginalForCurrent("fullscreen");
      await expect(p).rejects.toThrow("Image API unavailable");
    });

    it("handles image load error", async () => {
      const { result } = await openWithCurrSlide();

      const origImage = globalThis.Image;
      globalThis.Image = function (this: any) {
        this.onload = null;
        this.onerror = null;
        this._src = "";
        this.decode = () => Promise.resolve();
      } as unknown as typeof Image;
      Object.defineProperty(globalThis.Image.prototype, "src", {
        get() {
          return this._src;
        },
        set(url: string) {
          this._src = url;
          if (this.onerror) this.onerror();
        },
        configurable: true,
      });

      const p = result.loadOriginalForCurrent("fullscreen");
      await expect(p).rejects.toThrow("Original image failed to load");
      globalThis.Image = origImage;
    });

    it("returns immediately if src already matches original", async () => {
      const { result, instance } = await openWithCurrSlide();
      const dataItem = instance.options.dataSource[0] as PhotoSwipeImageItem;
      dataItem.src = "/api/image?path=%2Fimg1.png";

      const p = result.loadOriginalForCurrent("fullscreen");
      await expect(p).resolves.toBeUndefined();
      expect(dataItem.isOriginalLoaded).toBe(true);
    });
  });

  describe("swapCurrentSlideToOriginal", () => {
    it("no-ops when pswp instance is null", async () => {
      const { result } = setup([makeItem("/img1.png", "img1.png")]);
      const p = result.loadOriginalForCurrent("fullscreen");
      await expect(p).resolves.toBeUndefined();
    });

    it("no-ops when currIndex does not match", async () => {
      const { result, isOpenRef } = setup(
        [makeItem("/img1.png", "img1.png"), makeItem("/img2.png", "img2.png")],
        0,
        false,
      );
      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());
      const instance = pswpInstances[0];
      instance.currIndex = 1;
      instance.currSlide = {
        index: 1,
        data: {} as Record<string, unknown>,
        content: { data: {} as Record<string, unknown> } as Record<string, unknown>,
        resize: vi.fn(),
      } as any;

      const p = result.loadOriginalForCurrent("fullscreen");
      await expect(p).resolves.toBeUndefined();
    });
  });

  describe("maybeLoadOriginalForZoom", () => {
    it("loads original when zoom exceeds threshold", async () => {
      const { result, isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, false);
      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());
      const instance = pswpInstances[0];
      instance.currSlide = {
        index: 0,
        zoomLevels: { initial: 1 },
        currZoomLevel: 2.0,
      } as any;

      triggerPswpEvent(instance, "zoomPanUpdate");
      await vi.waitFor(() => {
        const dataItem = instance.options.dataSource[0] as PhotoSwipeImageItem;
        expect(dataItem.isOriginalLoaded).toBe(true);
      });
    });

    it("does nothing when zoom is below threshold", async () => {
      const { result, isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, false);
      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());
      const instance = pswpInstances[0];
      instance.currSlide = {
        index: 0,
        zoomLevels: { initial: 1 },
        currZoomLevel: 1.0,
      } as any;

      triggerPswpEvent(instance, "zoomPanUpdate");
      const dataItem = instance.options.dataSource[0] as PhotoSwipeImageItem;
      expect(dataItem.isOriginalLoaded).toBeUndefined();
    });
  });

  describe("resolveAndRefresh", () => {
    it("resolves dimensions and applies them on change event", async () => {
      const { result, isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, false);
      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());

      const instance = pswpInstances[0];
      instance.currIndex = 0;
      triggerPswpEvent(instance, "change");

      await vi.waitFor(() => {
        const store = useLightboxStore();
        expect(store.dimensionsByPath["/img1.png"]).toBeDefined();
      });
    });
  });

  describe("currentIndex watch", () => {
    it("calls pswp.goTo when external index changes", async () => {
      const items = [makeItem("/img1.png", "img1.png"), makeItem("/img2.png", "img2.png")];
      const { result, currentIndexRef } = setup(items, 0, true);
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());

      currentIndexRef.value = 1;

      await vi.waitFor(() => {
        expect(pswpInstances[0].goTo).toHaveBeenCalledWith(1);
      });
    });
  });

  describe("initPhotoSwipe branching", () => {
    it("loads original immediately for animated assets (gif)", async () => {
      const { result, isOpenRef } = setup([makeItem("/img.gif", "img.gif")], 0, false);
      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());

      const dataItem = pswpInstances[0].options.dataSource[0] as PhotoSwipeImageItem;
      expect(dataItem.isAnimatedAsset).toBe(true);
      expect(dataItem.src).toBe("/api/image?path=%2Fimg.gif");
      expect(dataItem.isOriginalLoaded).toBe(true);
      expect(dataItem.originalLoadReason).toBe("animated");
    });

    it("calls onRegisterUi and onAfterInit callbacks", async () => {
      const onRegisterUi = vi.fn();
      const onAfterInit = vi.fn();
      const { isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, false, { onRegisterUi, onAfterInit });

      isOpenRef.value = true;
      await vi.waitFor(() => {
        expect(onRegisterUi).toHaveBeenCalled();
        expect(onAfterInit).toHaveBeenCalled();
      });
    });

    it("calls maybeLoadOriginalForCurrent when shouldAlwaysLoadOriginal is true", async () => {
      (shouldAlwaysLoadOriginal as unknown as ReturnType<typeof vi.fn>).mockReturnValue(true);
      const { isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, false);

      isOpenRef.value = true;
      await vi.waitFor(() => {
        const dataItem = pswpInstances[0].options.dataSource[0] as PhotoSwipeImageItem;
        expect(dataItem.isOriginalLoaded).toBe(true);
      });
    });

    it("does not create instance when cancelled by race condition", async () => {
      const { result, isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, false);

      isOpenRef.value = true;
      isOpenRef.value = false;

      expect(result.pswp.value).toBeNull();
    });
  });

  describe("event handler behavior", () => {
    it("change event calls onIndexChange and triggers resolveAndRefresh", async () => {
      const { result, isOpenRef, onIndexChange } = setup(
        [makeItem("/img1.png", "img1.png"), makeItem("/img2.png", "img2.png")],
        0,
        false,
      );
      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());

      const instance = pswpInstances[0];
      instance.currIndex = 1;
      triggerPswpEvent(instance, "change");

      expect(onIndexChange).toHaveBeenCalledWith(1);
      await vi.waitFor(() => expect(fetchMetadata as ReturnType<typeof vi.fn>).toHaveBeenCalled());
    });

    it("change event loads original when shouldAlwaysLoadOriginal is true", async () => {
      (shouldAlwaysLoadOriginal as unknown as ReturnType<typeof vi.fn>).mockReturnValue(true);
      const { result, isOpenRef } = setup(
        [makeItem("/img1.png", "img1.png"), makeItem("/img2.png", "img2.png")],
        0,
        false,
      );
      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());

      const instance = pswpInstances[0];
      instance.currIndex = 1;
      const dataItem = instance.options.dataSource[1] as PhotoSwipeImageItem;
      instance.currSlide = {
        index: 1,
        data: {} as Record<string, unknown>,
        content: { data: {} as Record<string, unknown>, element: document.createElement("img") } as Record<
          string,
          unknown
        >,
        resize: vi.fn(),
      } as any;

      triggerPswpEvent(instance, "change");
      await vi.waitFor(() => expect(dataItem.isOriginalLoaded).toBe(true));
      expect(dataItem.originalLoadReason).toBe("preference");
    });

    it("close event calls destroyPhotoSwipe and onClose", async () => {
      const { result, isOpenRef, onClose } = setup([makeItem("/img1.png", "img1.png")], 0, false);
      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());

      const instance = pswpInstances[0];
      triggerPswpEvent(instance, "close");

      expect(instance.destroy).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
      expect(result.pswp.value).toBeNull();
    });

    it("loadError event falls back to original for preview failures", async () => {
      const { result, isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, false);
      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());

      const instance = pswpInstances[0];
      instance.currSlide = {
        index: 0,
        data: {} as Record<string, unknown>,
        content: { data: {} as Record<string, unknown>, element: document.createElement("img") } as Record<
          string,
          unknown
        >,
        resize: vi.fn(),
      } as any;

      triggerPswpEvent(instance, "loadError", {
        slide: { index: 0 },
        content: { data: { src: "/api/preview?path=%2Fimg1.png" } },
      });

      await vi.waitFor(() => {
        const dataItem = instance.options.dataSource[0] as PhotoSwipeImageItem;
        expect(dataItem.isOriginalLoaded).toBe(true);
      });
      expect((instance.options.dataSource[0] as PhotoSwipeImageItem).originalLoadReason).toBe("fallback");
    });

    it("loadError ignores non-current slides", async () => {
      const { result, isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, false);
      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());

      const instance = pswpInstances[0];
      triggerPswpEvent(instance, "loadError", {
        slide: { index: 999 },
        content: { data: { src: "/api/preview?path=%2Fimg1.png" } },
      });

      const dataItem = instance.options.dataSource[0] as PhotoSwipeImageItem;
      expect(dataItem.isOriginalLoaded).toBeUndefined();
    });
  });

  describe("destroyPhotoSwipe cleanup", () => {
    it("clears test hooks on window", async () => {
      const { result, isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, false);
      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());
      expect((window as any).__pswp).toBeDefined();
      expect(typeof (window as any).__loadOriginalForCurrent).toBe("function");

      const instance = pswpInstances[0];
      result.destroyPhotoSwipe();

      expect(result.pswp.value).toBeNull();
      expect(instance.destroy).toHaveBeenCalled();
    });

    it("clears pending init timer when closing before init completes", async () => {
      vi.useFakeTimers();
      const { result, isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, false);

      isOpenRef.value = true;
      await Promise.resolve();
      await Promise.resolve();

      isOpenRef.value = false;
      await Promise.resolve();
      await Promise.resolve();

      expect(result.pswp.value).toBeNull();
      vi.useRealTimers();
    });
  });

  describe("additional coverage for remaining branches", () => {
    it("triggers maybeLoadCurrentAnimatedOriginal from change event on animated asset", async () => {
      const { result, isOpenRef } = setup(
        [makeItem("/img1.png", "img1.png"), makeItem("/img.gif", "img.gif")],
        0,
        false,
      );
      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());

      const instance = pswpInstances[0];
      const dataItem = instance.options.dataSource[1] as PhotoSwipeImageItem;
      instance.currSlide = {
        index: 1,
        data: {} as Record<string, unknown>,
        content: { data: {} as Record<string, unknown>, element: document.createElement("img") } as Record<
          string,
          unknown
        >,
        resize: vi.fn(),
      } as any;
      instance.currIndex = 1;
      triggerPswpEvent(instance, "change");

      await vi.waitFor(() => expect(dataItem.isOriginalLoaded).toBe(true));
      expect(dataItem.originalLoadReason).toBe("animated");
    });

    it("fires beforeZoomTo event and triggers maybeLoadOriginalForZoomLevel", async () => {
      const { result, isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, false);
      isOpenRef.value = true;
      await vi.waitFor(() => expect(result.pswp.value).not.toBeNull());

      const instance = pswpInstances[0];
      instance.currSlide = {
        index: 0,
        zoomLevels: { initial: 1 },
        currZoomLevel: 1,
      } as any;

      triggerPswpEvent(instance, "beforeZoomTo", { destZoomLevel: 2.0 });

      await vi.waitFor(() => {
        const dataItem = instance.options.dataSource[0] as PhotoSwipeImageItem;
        expect(dataItem.isOriginalLoaded).toBe(true);
      });
    });
  });
});
