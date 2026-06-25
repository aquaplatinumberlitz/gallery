import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { createPinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clearGeneratedImages, refreshStaleGeneratedImages } from "@/services/api";
import { queryKeys } from "@/query/keys";
import { useGeneratedImagesGlobalMutations } from "../useGeneratedImagesGlobalMutations";

const toast = { success: vi.fn(), error: vi.fn(), warning: vi.fn() };

vi.mock("@/composables/useToast", () => ({ useToast: () => toast }));
vi.mock("@/services/api", () => ({
  refreshStaleGeneratedImages: vi.fn(),
  clearGeneratedImages: vi.fn(),
}));

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
  vi.mocked(refreshStaleGeneratedImages).mockResolvedValue({
    stale_derivatives: 3,
    state: "queued",
  });
  vi.mocked(clearGeneratedImages).mockResolvedValue({
    catalog_entries_cleared: 200,
    files_deleted: 180,
  });
});

describe("useGeneratedImagesGlobalMutations", () => {
  it("rebuildMutation invalidates global queries", async () => {
    const { invalidate, mutations, wrapper } = setup();

    await mutations.rebuildMutation.mutateAsync();

    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.generatedImagesRoot() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.jobsRoot() });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.statusRoot() });
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

  it("rebuildMutation calls refreshStaleGeneratedImages (no library arg)", async () => {
    const { mutations, wrapper } = setup();

    await mutations.rebuildMutation.mutateAsync();

    expect(refreshStaleGeneratedImages).toHaveBeenCalled();
    wrapper.unmount();
  });

  it("clearMutation calls clearGeneratedImages (no library arg)", async () => {
    const { mutations, wrapper } = setup();

    await mutations.clearMutation.mutateAsync();

    expect(clearGeneratedImages).toHaveBeenCalled();
    wrapper.unmount();
  });

  it("rebuildMutation toast includes stale count", async () => {
    const { mutations, wrapper } = setup();

    await mutations.rebuildMutation.mutateAsync();

    expect(toast.success).toHaveBeenCalledWith("Refresh queued for 3 stale items across all libraries");
    wrapper.unmount();
  });

  it("clearMutation toast says all libraries", async () => {
    const { mutations, wrapper } = setup();

    await mutations.clearMutation.mutateAsync();

    expect(toast.success).toHaveBeenCalledWith(
      "Generated files cleared across all libraries. Source images are not affected.",
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
