import { createPinia, setActivePinia } from "pinia";
import { ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useGalleryStore } from "@/stores/gallery";
import { useLibraryInspectorFilters } from "../useLibraryInspectorFilters";

vi.mock("@/composables/useFacetsQuery", () => ({
  useFacetsQuery: vi.fn(() => ({
    data: { value: { model: [{ value: "SDXL", count: 12 }] } },
  })),
}));

describe("useLibraryInspectorFilters", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("keeps the selected model stable while facet data does not contain it", () => {
    const galleryStore = useGalleryStore();
    galleryStore.metadataInspector.modelFilter = "LegacyTool";

    const filters = useLibraryInspectorFilters({
      scope: ref("all"),
      currentPath: ref(""),
    });

    expect(filters.modelFilter.value).toBe("LegacyTool");
    expect(filters.modelOptions.value).toEqual(["LegacyTool", "SDXL"]);
  });

  it("derives the active filter count from the two server filters", () => {
    const galleryStore = useGalleryStore();
    const filters = useLibraryInspectorFilters({
      scope: ref("current"),
      currentPath: ref("/photos"),
    });

    expect(filters.activeFilterCount.value).toBe(0);
    galleryStore.metadataInspector.modelFilter = "SDXL";
    galleryStore.metadataInspector.promptFilter = "has_prompt";
    expect(filters.activeFilterCount.value).toBe(2);
  });
});
