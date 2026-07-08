import { mount } from "@vue/test-utils";
import { describe, expect, it, vi, beforeEach } from "vitest";
import ResponsiveLibrarySelector from "../ResponsiveLibrarySelector.vue";

const deviceState = vi.hoisted(() => ({
  isMobile: { value: false },
  isTablet: { value: false },
}));

const selectionState = vi.hoisted(() => ({
  librariesQuery: {
    isPending: { value: false },
    isError: { value: false },
    refetch: vi.fn(),
  },
  libraries: {
    value: [
      {
        id: 1,
        name: "Primary Library",
        state: "ready",
        import_paths: [{ id: 11, library_id: 1, path: "/photos", position: 0 }],
      },
    ],
  },
}));

const storeState = vi.hoisted(() => ({
  activeLibraryId: null as number | null,
  activeImportPathId: null as number | null,
  setActiveLibrary: vi.fn(() => true),
}));

vi.mock("@/composables/useDevice", () => ({
  useDevice: () => deviceState,
}));

vi.mock("@/composables/useActiveLibrarySelection", () => ({
  useActiveLibrarySelection: () => selectionState,
}));

vi.mock("@/stores/gallery", () => ({
  useGalleryStore: () => storeState,
}));

function mountSubject() {
  return mount(ResponsiveLibrarySelector, {
    props: {
      modelValue: true,
    },
    global: {
      stubs: {
        Dialog: { props: ["open"], template: "<div data-testid='dialog'><slot /></div>" },
        DialogContent: { template: "<div data-testid='dialog-content' :class='$attrs.class'><slot /></div>" },
        DialogHeader: { template: "<div><slot /></div>" },
        DialogTitle: { template: "<h2><slot /></h2>" },
        DialogDescription: { template: "<p><slot /></p>" },
        Sheet: { props: ["open"], template: "<div data-testid='sheet'><slot /></div>" },
        SheetContent: { template: "<div data-testid='sheet-content' :class='$attrs.class'><slot /></div>" },
        SheetHeader: { template: "<div><slot /></div>" },
        SheetTitle: { template: "<h2><slot /></h2>" },
        SheetDescription: { template: "<p><slot /></p>" },
        Button: { template: "<button><slot /></button>" },
        ButtonLink: { template: "<a><slot /></a>" },
        Badge: { template: "<span><slot /></span>" },
        OverflowTooltip: { template: "<span><slot /></span>" },
      },
    },
  });
}

describe("ResponsiveLibrarySelector", () => {
  beforeEach(() => {
    deviceState.isMobile.value = false;
    deviceState.isTablet.value = false;
    storeState.activeLibraryId = null;
    storeState.activeImportPathId = null;
    storeState.setActiveLibrary.mockClear();
  });

  it("uses a compact dialog on desktop", () => {
    const wrapper = mountSubject();

    expect(wrapper.find("[data-testid='dialog']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='sheet']").exists()).toBe(false);
    expect(wrapper.get("[data-testid='dialog-content']").classes()).toContain("max-w-[34rem]");
    expect(wrapper.text()).toContain("Choose library");
    expect(wrapper.text()).toContain("/photos");
  });

  it("uses a bottom sheet on mobile and tablet", () => {
    deviceState.isMobile.value = true;

    const wrapper = mountSubject();

    expect(wrapper.find("[data-testid='sheet']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='dialog']").exists()).toBe(false);
    expect(wrapper.get("[data-testid='sheet-content']").classes()).toContain("max-h-[75vh]");
  });

  it("selects an import path and closes", async () => {
    const wrapper = mountSubject();
    const pathButton = wrapper.findAll("button").find((button) => button.text().includes("/photos"));

    expect(pathButton).toBeDefined();
    await pathButton!.trigger("click");

    expect(storeState.setActiveLibrary).toHaveBeenCalledWith(selectionState.libraries.value[0], {
      id: 11,
      library_id: 1,
      path: "/photos",
      position: 0,
    });
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });
});
