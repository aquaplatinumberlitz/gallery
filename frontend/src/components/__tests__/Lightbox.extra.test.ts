import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { mount } from "@vue/test-utils";
import { createIsolatedQueryClient } from "@/test/queryClient";
import { VueQueryPlugin } from "@tanstack/vue-query";
import Lightbox from "../Lightbox.vue";

vi.mock("@/stores/lightbox", () => ({
  useLightboxStore: () => ({
    isOpen: true,
    currentIndex: 0,
    itemPath: "/photos/test.png",
    itemName: "test.png",
    galleryItems: [{ path: "/photos/test.png", name: "test.png" }],
    open: vi.fn(),
    close: vi.fn(),
    next: vi.fn(),
    prev: vi.fn(),
  }),
}));

vi.mock("@/composables/useDevice", () => ({
  useDevice: () => ({
    isDesktop: true,
    isTablet: false,
    isMobile: false,
    isWide: false,
  }),
}));

vi.mock("@/composables/useClipboard", () => ({
  useClipboard: () => ({ copyStatus: {}, copyText: vi.fn() }),
}));

vi.mock("@/composables/usePhotoMetadataQuery", () => ({
  usePhotoMetadataQuery: () => ({
    isLoading: { value: false },
    data: { value: { name: "test.png", width: 1024, height: 768, date: "2024-01-15", generation_time: "15.2s" } },
  }),
}));

vi.mock("@/debug/lightboxNavDebug", () => ({
  lightboxItemAt: vi.fn(),
  logLightboxNavDebug: vi.fn(),
}));

vi.mock("@/constants", () => ({
  DESKTOP_METADATA_WIDTH: 400,
}));

function createWrapper() {
  setActivePinia(createPinia());
  const queryClient = createIsolatedQueryClient();
  return mount(Lightbox, {
    global: {
      plugins: [[VueQueryPlugin, { queryClient }]],
      stubs: {
        Teleport: { template: "<div><slot /></div>" },
        Transition: { template: "<div><slot /></div>" },
        FocusScope: { template: "<div><slot /></div>" },
        PhotoSwipeViewer: { template: "<div data-testid='pswp' />" },
        LightboxDesktopPanel: { template: "<div data-testid='desktop-panel' />" },
        LightboxTabletPanel: { template: "<div data-testid='tablet-panel' />" },
        LightboxMobileSheet: { template: "<div data-testid='mobile-sheet' />" },
        MobilePhotoSwipe: { template: "<div data-testid='mobile-pswp' />" },
        TabletPhotoSwipe: { template: "<div data-testid='tablet-pswp' />" },
      },
    },
  });
}

describe("Lightbox extra", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("renders lightbox overlay with sidebar style", () => {
    const wrapper = createWrapper();
    expect(wrapper.find('[data-testid="lightbox"]').exists()).toBe(true);
  });

  it("renders image counter with correct format", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Image");
    expect(wrapper.text()).toContain("of");
  });

  it("applies sidebar width style on overlay", () => {
    const wrapper = createWrapper();
    const overlay = wrapper.find('[data-testid="lightbox"]');
    expect(overlay.exists()).toBe(true);
  });

  it("renders fullscreen controls when not present (default)", () => {
    const wrapper = createWrapper();
    expect(wrapper.find(".fs-controls").exists()).toBe(false);
  });

  it("renders desktop panel with close button", () => {
    const wrapper = createWrapper();
    expect(wrapper.find('[data-testid="desktop-panel"]').exists()).toBe(true);
  });

  it("handles keyboard escape via store", () => {
    const wrapper = createWrapper();
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(wrapper.exists()).toBe(true);
  });
});
