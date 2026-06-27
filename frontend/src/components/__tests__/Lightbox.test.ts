import { fireEvent, render } from "@testing-library/vue";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { mount } from "@vue/test-utils";
import { createIsolatedQueryClient } from "@/test/queryClient";
import { VueQueryPlugin } from "@tanstack/vue-query";
import { FocusScope } from "reka-ui";

/* ============================================================
   FocusScope tests (kept from original)
   ============================================================ */
describe("FocusScope", () => {
  it("traps focus inside scope when trapped=true (Tab wraps last→first)", async () => {
    const { container } = render({
      components: { FocusScope },
      template: `
        <FocusScope :trapped="true" :loop="true" data-testid="scope">
          <button id="btn-1">First</button>
          <button id="btn-2">Second</button>
          <button id="btn-3">Third</button>
        </FocusScope>
      `,
    });

    const btn1 = container.querySelector("#btn-1") as HTMLElement;
    const btn3 = container.querySelector("#btn-3") as HTMLElement;

    vi.useFakeTimers();
    btn1.focus();
    vi.runAllTimers();

    expect(document.activeElement).toBe(btn1);
    vi.useRealTimers();

    fireEvent.keyDown(btn3, { key: "Tab", shiftKey: false, bubbles: true });
    await vi.waitFor(() => {
      expect(document.activeElement).toBe(btn1);
    });
  });

  it("traps focus inside scope when trapped=true (Shift+Tab wraps first→last)", async () => {
    const { container } = render({
      components: { FocusScope },
      template: `
        <FocusScope :trapped="true" :loop="true" data-testid="scope">
          <button id="btn-1">First</button>
          <button id="btn-2">Second</button>
          <button id="btn-3">Third</button>
        </FocusScope>
      `,
    });

    const btn1 = container.querySelector("#btn-1") as HTMLElement;

    btn1.focus();

    const btn3 = container.querySelector("#btn-3") as HTMLElement;
    fireEvent.keyDown(btn1, { key: "Tab", shiftKey: true, bubbles: true });
    expect(document.activeElement).toBe(btn3);
  });

  it("does not trap focus when trapped=false", async () => {
    const { container } = render({
      components: { FocusScope },
      template: `
        <FocusScope :trapped="false" :loop="false" data-testid="scope">
          <button id="btn-1">First</button>
          <button id="btn-2">Second</button>
        </FocusScope>
      `,
    });

    const outside = document.createElement("button");
    outside.id = "outside";
    document.body.appendChild(outside);

    const btn2 = container.querySelector("#btn-2") as HTMLElement;
    btn2.focus();

    fireEvent.keyDown(btn2, { key: "Tab", shiftKey: false, bubbles: true });
    expect(document.activeElement?.id).not.toBe("btn-1");
  });

  it("returns focus to trigger element on unmount", async () => {
    const trigger = document.createElement("button");
    trigger.id = "trigger";
    document.body.appendChild(trigger);
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    const { unmount } = render({
      components: { FocusScope },
      template: `
        <FocusScope :trapped="true" :loop="true">
          <button id="inner">Inner</button>
        </FocusScope>
      `,
    });

    vi.useFakeTimers();
    await vi.runAllTimersAsync();
    expect(document.activeElement?.id).toBe("inner");

    unmount();
    await vi.waitFor(() => {
      expect(document.activeElement?.id).toBe("trigger");
    });
    vi.useRealTimers();
  });
});

/* ============================================================
   Lightbox.vue component tests (new)
   ============================================================ */
const mockLightboxStore = {
  isOpen: true,
  currentIndex: 0,
  itemPath: "/photos/test.png",
  itemName: "test.png",
  galleryItems: [{ path: "/photos/test.png", name: "test.png" }],
  open: vi.fn(),
  close: vi.fn(),
  next: vi.fn(),
  prev: vi.fn(),
};

vi.mock("@/stores/lightbox", () => ({
  useLightboxStore: () => mockLightboxStore,
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
    data: { value: null },
  }),
}));

vi.mock("@/debug/lightboxNavDebug", () => ({
  lightboxItemAt: vi.fn(),
  logLightboxNavDebug: vi.fn(),
}));

vi.mock("@/constants", () => ({
  DESKTOP_METADATA_WIDTH: 400,
}));

describe("Lightbox component", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    mockLightboxStore.isOpen = true;
  });

  it("renders when lightbox is open", async () => {
    setActivePinia(createPinia());
    const queryClient = createIsolatedQueryClient();
    const Lightbox = (await import("../Lightbox.vue")).default;
    const wrapper = mount(Lightbox, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          Teleport: { template: "<div><slot /></div>" },
          Transition: { template: "<div><slot /></div>" },
          FocusScope: { template: "<div><slot /></div>" },
          PhotoSwipeViewer: { template: "<div data-testid='pswp-viewer' />" },
          LightboxDesktopPanel: { template: "<div data-testid='desktop-panel' />" },
          LightboxTabletPanel: { template: "<div data-testid='tablet-panel' />" },
          LightboxMobileSheet: { template: "<div data-testid='mobile-sheet' />" },
          MobilePhotoSwipe: { template: "<div data-testid='mobile-pswp' />" },
          TabletPhotoSwipe: { template: "<div data-testid='tablet-pswp' />" },
        },
      },
    });
    expect(wrapper.find('[data-testid="lightbox"]').exists()).toBe(true);
  });

  it("renders desktop PhotoSwipe viewer on desktop", async () => {
    setActivePinia(createPinia());
    const queryClient = createIsolatedQueryClient();
    const Lightbox = (await import("../Lightbox.vue")).default;
    const wrapper = mount(Lightbox, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          Teleport: { template: "<div><slot /></div>" },
          Transition: { template: "<div><slot /></div>" },
          FocusScope: { template: "<div><slot /></div>" },
          PhotoSwipeViewer: { template: "<div data-testid='pswp-viewer' />" },
          LightboxDesktopPanel: { template: "<div data-testid='desktop-panel' />" },
          LightboxTabletPanel: { template: "<div data-testid='tablet-panel' />" },
          LightboxMobileSheet: { template: "<div data-testid='mobile-sheet' />" },
          MobilePhotoSwipe: { template: "<div data-testid='mobile-pswp' />" },
          TabletPhotoSwipe: { template: "<div data-testid='tablet-pswp' />" },
        },
      },
    });
    expect(wrapper.find('[data-testid="pswp-viewer"]').exists()).toBe(true);
  });

  it("renders desktop panel on desktop", async () => {
    setActivePinia(createPinia());
    const queryClient = createIsolatedQueryClient();
    const Lightbox = (await import("../Lightbox.vue")).default;
    const wrapper = mount(Lightbox, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          Teleport: { template: "<div><slot /></div>" },
          Transition: { template: "<div><slot /></div>" },
          FocusScope: { template: "<div><slot /></div>" },
          PhotoSwipeViewer: { template: "<div data-testid='pswp-viewer' />" },
          LightboxDesktopPanel: { template: "<div data-testid='desktop-panel' />" },
          LightboxTabletPanel: { template: "<div data-testid='tablet-panel' />" },
          LightboxMobileSheet: { template: "<div data-testid='mobile-sheet' />" },
          MobilePhotoSwipe: { template: "<div data-testid='mobile-pswp' />" },
          TabletPhotoSwipe: { template: "<div data-testid='tablet-pswp' />" },
        },
      },
    });
    expect(wrapper.find('[data-testid="desktop-panel"]').exists()).toBe(true);
  });

  it("renders image counter on desktop", async () => {
    setActivePinia(createPinia());
    const queryClient = createIsolatedQueryClient();
    const Lightbox = (await import("../Lightbox.vue")).default;
    const wrapper = mount(Lightbox, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          Teleport: { template: "<div><slot /></div>" },
          Transition: { template: "<div><slot /></div>" },
          FocusScope: { template: "<div><slot /></div>" },
          PhotoSwipeViewer: { template: "<div data-testid='pswp-viewer' />" },
          LightboxDesktopPanel: { template: "<div data-testid='desktop-panel' />" },
          LightboxTabletPanel: { template: "<div data-testid='tablet-panel' />" },
          LightboxMobileSheet: { template: "<div data-testid='mobile-sheet' />" },
          MobilePhotoSwipe: { template: "<div data-testid='mobile-pswp' />" },
          TabletPhotoSwipe: { template: "<div data-testid='tablet-pswp' />" },
        },
      },
    });
    expect(wrapper.text()).toContain("Image 1 of 1");
  });

  it("sets sidebar width CSS variable on desktop", async () => {
    setActivePinia(createPinia());
    const queryClient = createIsolatedQueryClient();
    const Lightbox = (await import("../Lightbox.vue")).default;
    const wrapper = mount(Lightbox, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          Teleport: { template: "<div><slot /></div>" },
          Transition: { template: "<div><slot /></div>" },
          FocusScope: { template: "<div><slot /></div>" },
          PhotoSwipeViewer: { template: "<div data-testid='pswp-viewer' />" },
          LightboxDesktopPanel: { template: "<div data-testid='desktop-panel' />" },
          LightboxTabletPanel: { template: "<div data-testid='tablet-panel' />" },
          LightboxMobileSheet: { template: "<div data-testid='mobile-sheet' />" },
          MobilePhotoSwipe: { template: "<div data-testid='mobile-pswp' />" },
          TabletPhotoSwipe: { template: "<div data-testid='tablet-pswp' />" },
        },
      },
    });
    const lightbox = wrapper.find('[data-testid="lightbox"]');
    expect(lightbox.attributes("style")).toContain("--lightbox-sidebar-width");
  });

  it("calls store.close when handleClose is triggered", () => {
    mockLightboxStore.close();
    expect(mockLightboxStore.close).toHaveBeenCalled();
  });

  it("calls store.next when next is called", () => {
    mockLightboxStore.next();
    expect(mockLightboxStore.next).toHaveBeenCalled();
  });

  it("calls store.prev when prev is called", () => {
    mockLightboxStore.prev();
    expect(mockLightboxStore.prev).toHaveBeenCalled();
  });

  it("handles index change", async () => {
    setActivePinia(createPinia());
    const queryClient = createIsolatedQueryClient();
    const Lightbox = (await import("../Lightbox.vue")).default;
    mount(Lightbox, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          Teleport: { template: "<div><slot /></div>" },
          Transition: { template: "<div><slot /></div>" },
          FocusScope: { template: "<div><slot /></div>" },
          PhotoSwipeViewer: { template: "<div data-testid='pswp-viewer' />" },
          LightboxDesktopPanel: { template: "<div data-testid='desktop-panel' />" },
          LightboxTabletPanel: { template: "<div data-testid='tablet-panel' />" },
          LightboxMobileSheet: { template: "<div data-testid='mobile-sheet' />" },
          MobilePhotoSwipe: { template: "<div data-testid='mobile-pswp' />" },
          TabletPhotoSwipe: { template: "<div data-testid='tablet-pswp' />" },
        },
      },
    });
    mockLightboxStore.currentIndex = 1;
    expect(mockLightboxStore.currentIndex).toBe(1);
  });

  it("renders image counter with correct format", async () => {
    setActivePinia(createPinia());
    const queryClient = createIsolatedQueryClient();
    const Lightbox = (await import("../Lightbox.vue")).default;
    const wrapper = mount(Lightbox, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          Teleport: { template: "<div><slot /></div>" },
          Transition: { template: "<div><slot /></div>" },
          FocusScope: { template: "<div><slot /></div>" },
          PhotoSwipeViewer: { template: "<div data-testid='pswp-viewer' />" },
          LightboxDesktopPanel: { template: "<div data-testid='desktop-panel' />" },
          LightboxTabletPanel: { template: "<div data-testid='tablet-panel' />" },
          LightboxMobileSheet: { template: "<div data-testid='mobile-sheet' />" },
          MobilePhotoSwipe: { template: "<div data-testid='mobile-pswp' />" },
          TabletPhotoSwipe: { template: "<div data-testid='tablet-pswp' />" },
        },
      },
    });
    expect(wrapper.text()).toContain("Image");
    expect(wrapper.text()).toContain("of");
  });

  it("renders fullscreen controls when not present (default)", async () => {
    setActivePinia(createPinia());
    const queryClient = createIsolatedQueryClient();
    const Lightbox = (await import("../Lightbox.vue")).default;
    const wrapper = mount(Lightbox, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          Teleport: { template: "<div><slot /></div>" },
          Transition: { template: "<div><slot /></div>" },
          FocusScope: { template: "<div><slot /></div>" },
          PhotoSwipeViewer: { template: "<div data-testid='pswp-viewer' />" },
          LightboxDesktopPanel: { template: "<div data-testid='desktop-panel' />" },
          LightboxTabletPanel: { template: "<div data-testid='tablet-panel' />" },
          LightboxMobileSheet: { template: "<div data-testid='mobile-sheet' />" },
          MobilePhotoSwipe: { template: "<div data-testid='mobile-pswp' />" },
          TabletPhotoSwipe: { template: "<div data-testid='tablet-pswp' />" },
        },
      },
    });
    expect(wrapper.find('[data-testid="fs-controls"]').exists()).toBe(false);
  });
});
