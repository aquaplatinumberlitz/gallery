import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h, ref, computed } from "vue";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import type { FileNode } from "@/types";
import { usePhotoSwipe } from "../usePhotoSwipe";

interface MockPswpInstance {
  currIndex: number;
  currSlide: null | Record<string, unknown>;
  options: { dataSource: unknown[] };
  init: ReturnType<typeof vi.fn>;
  destroy: ReturnType<typeof vi.fn>;
  goTo: ReturnType<typeof vi.fn>;
  on: ReturnType<typeof vi.fn>;
  refreshSlideContent: ReturnType<typeof vi.fn>;
}

const { pswpInstances } = vi.hoisted(() => {
  const instances: MockPswpInstance[] = [];
  return { pswpInstances: instances };
});

vi.mock("photoswipe", () => ({
  default: vi.fn(function () {
    const instance: MockPswpInstance = {
      currIndex: 0,
      currSlide: null,
      options: { dataSource: [] },
      init: vi.fn(),
      destroy: vi.fn(),
      goTo: vi.fn(),
      on: vi.fn(),
      refreshSlideContent: vi.fn(),
    };
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
  buildPhotoSwipeItem: vi.fn((item: FileNode) => ({
    src: `/api/image?path=${encodeURIComponent(item.path)}`,
    previewSrc: `/api/preview?path=${encodeURIComponent(item.path)}`,
    msrc: `/api/thumb?path=${encodeURIComponent(item.path)}`,
    width: 800,
    height: 600,
    alt: item.name,
    path: item.path,
    isAnimatedAsset: false,
  })),
  hasValidDimensions: vi.fn(
    (d: { width?: number | null; height?: number | null } | null | undefined) => {
      if (!d) return false;
      return typeof d.width === "number" && d.width > 0 && typeof d.height === "number" && d.height > 0;
    },
  ),
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
  const testQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return { queryClient: testQueryClient };
});

function mockImageConstructor() {
  const originalImage = globalThis.Image;
  globalThis.Image = function () {
    this.onload = null;
    this.onerror = null;
    this.decoding = "async";
    this.naturalWidth = 800;
    this.naturalHeight = 600;
    this._src = "";
    this.decode = function () { return Promise.resolve(); };
  } as unknown as typeof Image;
  Object.defineProperty(globalThis.Image.prototype, "src", {
    get() { return this._src; },
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

function setup(items: FileNode[], currentIndex = 0, isInitiallyOpen = false) {
  restoreImage = mockImageConstructor();
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const pinia = createPinia();
  setActivePinia(pinia);

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
});

afterEach(() => {
  delete (window as Record<string, unknown>).__pswp;
  delete (window as Record<string, unknown>).__loadOriginalForCurrent;
  if (restoreImage) {
    restoreImage();
    restoreImage = null;
  }
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
    const registeredEvents = instance.on.mock.calls.map((c: [string]) => c[0]);
    expect(registeredEvents).toContain("change");
    expect(registeredEvents).toContain("close");
    expect(registeredEvents).toContain("zoomPanUpdate");
    expect(registeredEvents).toContain("beforeZoomTo");
    expect(registeredEvents).toContain("loadError");
  });

  it("exposes test hooks on window in test mode", async () => {
    const { isOpenRef } = setup([makeItem("/img1.png", "img1.png")], 0, false);

    isOpenRef.value = true;
    await vi.waitFor(() => expect((window as Record<string, unknown>).__pswp).toBeDefined());
    expect(typeof (window as Record<string, unknown>).__loadOriginalForCurrent).toBe("function");
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
});
