import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { createPinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { resetCatalogDatabase } from "@/services/api";
import { queryKeys } from "@/query/keys";
import { useCatalogResetMutation } from "../useCatalogResetMutation";

const toast = { success: vi.fn(), error: vi.fn() };

vi.mock("@/composables/useToast", () => ({ useToast: () => toast }));
vi.mock("@/services/api", () => ({
  resetCatalogDatabase: vi.fn(),
}));

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const invalidate = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue();
  let mutation!: ReturnType<typeof useCatalogResetMutation>;
  const wrapper = mount(
    defineComponent({
      setup() {
        mutation = useCatalogResetMutation();
        return () => h("div");
      },
    }),
    { global: { plugins: [createPinia(), [VueQueryPlugin, { queryClient }]] } },
  );
  return { invalidate, mutation, wrapper };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(resetCatalogDatabase).mockResolvedValue({
    state: "reset",
    libraries_deleted: 2,
    import_paths_deleted: 2,
    exclusion_patterns_deleted: 1,
    assets_deleted: 20,
    image_metadata_rows_deleted: 18,
    metadata_jobs_deleted: 3,
    library_jobs_deleted: 1,
    derivative_catalog_entries_cleared: 20,
    preview_files_deleted: 18,
  });
});

describe("useCatalogResetMutation", () => {
  it("calls resetCatalogDatabase", async () => {
    const { mutation, wrapper } = setup();

    await mutation.mutateAsync("RESET CATALOG DATABASE");

    expect(resetCatalogDatabase).toHaveBeenCalledWith("RESET CATALOG DATABASE");
    wrapper.unmount();
  });

  it("invalidates catalog-wide queries", async () => {
    const { invalidate, mutation, wrapper } = setup();

    await mutation.mutateAsync("RESET CATALOG DATABASE");

    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.generatedImagesRoot() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.librariesRoot() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.galleryStats() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.jobsRoot() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.statusRoot() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.maintenanceRoot() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.browseAllRoot() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.browseInfiniteAllRoot() });
    wrapper.unmount();
  });

  it("shows a success toast", async () => {
    const { mutation, wrapper } = setup();

    await mutation.mutateAsync("RESET CATALOG DATABASE");

    expect(toast.success).toHaveBeenCalledWith(
      "Catalog database reset. Library registrations and imported data were removed.",
    );
    wrapper.unmount();
  });
});
