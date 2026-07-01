import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { createPinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { resetCatalogDatabase } from "@/services/api";
import { GRID_SIZE_KEY } from "@/composables/useColumnResize";
import {
  ACTIVE_IMPORT_PATH_STORAGE_KEY,
  ACTIVE_LIBRARY_STORAGE_KEY,
  LEGACY_ROOT_PATH_STORAGE_KEY,
  SORT_STORAGE_KEY,
} from "@/stores/gallery";
import { LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY } from "@/utils/lightbox";
import { useCatalogResetMutation } from "../useCatalogResetMutation";

const { routerReplace, toast } = vi.hoisted(() => ({
  routerReplace: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@/composables/useToast", () => ({ useToast: () => toast }));
vi.mock("@/services/api", () => ({
  resetCatalogDatabase: vi.fn(),
}));
vi.mock("@/router", () => ({
  router: {
    replace: routerReplace,
  },
}));

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const clear = vi.spyOn(queryClient, "clear");
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
  return { clear, mutation, wrapper };
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  routerReplace.mockResolvedValue(undefined);
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
    derivative_jobs_cleared: 2,
    thumbnail_disk_cache_entries_cleared: 4,
    preview_files_deleted: 18,
    sequences_reset: 6,
    sequence_tables_reset: ["libraries"],
  });
});

describe("useCatalogResetMutation", () => {
  it("calls resetCatalogDatabase", async () => {
    const { mutation, wrapper } = setup();

    await mutation.mutateAsync("RESET CATALOG DATABASE");

    expect(resetCatalogDatabase).toHaveBeenCalledWith("RESET CATALOG DATABASE");
    wrapper.unmount();
  });

  it("clears cached queries and redirects to libraries", async () => {
    const { clear, mutation, wrapper } = setup();

    await mutation.mutateAsync("RESET CATALOG DATABASE");

    expect(clear).toHaveBeenCalledOnce();
    expect(routerReplace).toHaveBeenCalledWith({ name: "admin-libraries" });
    wrapper.unmount();
  });

  it("clears gallery handoff state from localStorage", async () => {
    const keys = [
      ACTIVE_LIBRARY_STORAGE_KEY,
      ACTIVE_IMPORT_PATH_STORAGE_KEY,
      LEGACY_ROOT_PATH_STORAGE_KEY,
      SORT_STORAGE_KEY,
      GRID_SIZE_KEY,
      LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY,
    ];
    for (const key of keys) {
      window.localStorage.setItem(key, "stale");
    }
    const { mutation, wrapper } = setup();

    await mutation.mutateAsync("RESET CATALOG DATABASE");

    for (const key of keys) {
      expect(window.localStorage.getItem(key)).toBeNull();
    }
    wrapper.unmount();
  });

  it("shows a success toast", async () => {
    const { mutation, wrapper } = setup();

    await mutation.mutateAsync("RESET CATALOG DATABASE");

    expect(toast.success).toHaveBeenCalledWith("App data reset. Source files were not touched.");
    wrapper.unmount();
  });
});
