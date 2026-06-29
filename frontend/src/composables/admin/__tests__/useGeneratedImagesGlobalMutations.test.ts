import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { createPinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clearImportedData, GalleryAPIError, rebuildImportedData } from "@/services/api";
import { queryKeys } from "@/query/keys";
import { useGeneratedImagesGlobalMutations } from "../useGeneratedImagesGlobalMutations";

const toast = { success: vi.fn(), error: vi.fn(), warning: vi.fn() };

vi.mock("@/composables/useToast", () => ({ useToast: () => toast }));
vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return {
    ...actual,
    rebuildImportedData: vi.fn(),
    clearImportedData: vi.fn(),
  };
});

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const invalidate = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue();
  let mutations!: ReturnType<typeof useGeneratedImagesGlobalMutations>;
  const wrapper = mount(
    defineComponent({
      setup() {
        mutations = useGeneratedImagesGlobalMutations();
        return () => h("div");
      },
    }),
    { global: { plugins: [createPinia(), [VueQueryPlugin, { queryClient }]] } },
  );
  return { invalidate, mutations, wrapper };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(rebuildImportedData).mockResolvedValue({
    job_id: 3,
    state: "running",
    count: 2,
    child_job_ids: [4, 5],
    clear: {
      assets_cleared: 0,
      file_index_rows_cleared: 0,
      image_metadata_rows_cleared: 0,
      image_resource_rows_cleared: 0,
      metadata_jobs_cleared: 0,
      library_jobs_cleared: 0,
      rebuild_staging_rows_cleared: 0,
      folder_index_rows_cleared: 0,
      integrity_runs_cleared: 0,
      derivative_catalog_entries_cleared: 0,
      preview_files_deleted: 0,
    },
  });
  vi.mocked(clearImportedData).mockResolvedValue({
    state: "cleared",
    libraries_preserved: 2,
    assets_cleared: 200,
    file_index_rows_cleared: 200,
    image_metadata_rows_cleared: 180,
    image_resource_rows_cleared: 0,
    metadata_jobs_cleared: 180,
    library_jobs_cleared: 3,
    rebuild_staging_rows_cleared: 0,
    folder_index_rows_cleared: 10,
    integrity_runs_cleared: 0,
    derivative_catalog_entries_cleared: 200,
    preview_files_deleted: 180,
  });
});

describe("useGeneratedImagesGlobalMutations", () => {
  it("rebuildMutation invalidates global queries", async () => {
    const { invalidate, mutations, wrapper } = setup();

    await mutations.rebuildMutation.mutateAsync();

    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.generatedImagesRoot() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.librariesRoot() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.galleryStats() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.jobsRoot() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.statusRoot() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.maintenanceRoot() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.browseAllRoot() });
    wrapper.unmount();
  });

  it("clearMutation invalidates global queries + browse caches", async () => {
    const { invalidate, mutations, wrapper } = setup();

    await mutations.clearMutation.mutateAsync();

    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.generatedImagesRoot() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.jobsRoot() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.statusRoot() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.browseAllRoot() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.browseInfiniteAllRoot() });
    wrapper.unmount();
  });

  it("rebuildMutation calls rebuildImportedData (no library arg)", async () => {
    const { mutations, wrapper } = setup();

    await mutations.rebuildMutation.mutateAsync();

    expect(rebuildImportedData).toHaveBeenCalled();
    wrapper.unmount();
  });

  it("clearMutation calls clearImportedData (no library arg)", async () => {
    const { mutations, wrapper } = setup();

    await mutations.clearMutation.mutateAsync();

    expect(clearImportedData).toHaveBeenCalled();
    wrapper.unmount();
  });

  it("rebuildMutation toast includes library count", async () => {
    const { mutations, wrapper } = setup();

    await mutations.rebuildMutation.mutateAsync();

    expect(toast.success).toHaveBeenCalledWith("Imported data rebuild queued for 2 libraries");
    wrapper.unmount();
  });

  it("clearMutation toast says all libraries", async () => {
    const { mutations, wrapper } = setup();

    await mutations.clearMutation.mutateAsync();

    expect(toast.success).toHaveBeenCalledWith("Imported data cleared. Libraries and source files are not affected.");
    wrapper.unmount();
  });

  it("clearMutation toast uses GalleryAPIError suggestion", async () => {
    vi.mocked(clearImportedData).mockRejectedValue(
      new GalleryAPIError(
        "maintenance_busy",
        "Maintenance is busy",
        "Wait for catalog, metadata, or preview jobs to finish, then try again.",
      ),
    );
    const { mutations, wrapper } = setup();

    await expect(mutations.clearMutation.mutateAsync()).rejects.toBeInstanceOf(GalleryAPIError);

    expect(toast.error).toHaveBeenCalledWith(
      "Could not clear imported data",
      "Wait for catalog, metadata, or preview jobs to finish, then try again.",
    );
    wrapper.unmount();
  });

  it("does not export warmMutation (library-scoped)", async () => {
    const { mutations, wrapper } = setup();

    expect(mutations).not.toHaveProperty("warmMutation");
    expect(mutations).toHaveProperty("rebuildMutation");
    expect(mutations).toHaveProperty("clearMutation");
    wrapper.unmount();
  });
});
