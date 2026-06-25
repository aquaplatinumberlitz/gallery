import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { createPinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { queryKeys } from "@/query/keys";
import {
  clearGeneratedImages,
  generateMissingImages,
  refreshStaleGeneratedImages,
} from "@/services/api";
import { useGeneratedImagesMutations } from "../useGeneratedImagesMutations";

const toast = { success: vi.fn(), error: vi.fn(), warning: vi.fn() };

vi.mock("@/composables/useToast", () => ({ useToast: () => toast }));
vi.mock("@/services/api", () => ({
  generateMissingImages: vi.fn(),
  refreshStaleGeneratedImages: vi.fn(),
  clearGeneratedImages: vi.fn(),
}));

function setup(libraryId = 1) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const invalidate = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue();
  let mutations!: ReturnType<typeof useGeneratedImagesMutations>;
  const wrapper = mount(
    defineComponent({
      setup() {
        mutations = useGeneratedImagesMutations(libraryId);
        return () => h("div");
      },
    }),
    { global: { plugins: [createPinia(), [VueQueryPlugin, { queryClient }]] } },
  );
  return { invalidate, mutations, wrapper };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(generateMissingImages).mockResolvedValue({
    library_id: 1,
    state: "queued",
    assets: 50,
    derivatives_considered: 100,
  });
  vi.mocked(refreshStaleGeneratedImages).mockResolvedValue({
    stale_derivatives: 3,
    state: "queued",
  });
  vi.mocked(clearGeneratedImages).mockResolvedValue({
    catalog_entries_cleared: 200,
    files_deleted: 180,
  });
});

describe("useGeneratedImagesMutations", () => {
  it("invalidates generated-images and related queries after warm", async () => {
    const { invalidate, mutations, wrapper } = setup(1);

    await mutations.warmMutation.mutateAsync();

    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.generatedImages(1) });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.statusLibrary(1) });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.libraryJobs(1) });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.jobsRoot() });
    wrapper.unmount();
  });

  it("invalidates after rebuild", async () => {
    const { invalidate, mutations, wrapper } = setup(1);

    await mutations.rebuildMutation.mutateAsync();

    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.generatedImages(1) });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.statusLibrary(1) });
    wrapper.unmount();
  });

  it("invalidates browse roots after clear", async () => {
    const { invalidate, mutations, wrapper } = setup(1);

    await mutations.clearMutation.mutateAsync();

    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.browseRoot(1) });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.browseInfiniteRoot(1) });
    wrapper.unmount();
  });

  it("calls toast.success on warm success", async () => {
    const { mutations, wrapper } = setup(1);

    await mutations.warmMutation.mutateAsync();

    expect(toast.success).toHaveBeenCalledWith("Generated images queued");
    wrapper.unmount();
  });
});
