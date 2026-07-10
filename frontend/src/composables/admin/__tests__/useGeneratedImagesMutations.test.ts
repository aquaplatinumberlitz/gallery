import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { createPinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { queryKeys } from "@/query/keys";
import { generateMissingImages } from "@/services/api";
import { useGeneratedImagesMutations } from "../useGeneratedImagesMutations";

const toast = { success: vi.fn(), error: vi.fn(), warning: vi.fn() };

vi.mock("@/composables/useToast", () => ({ useToast: () => toast }));
vi.mock("@/services/api", () => ({
  generateMissingImages: vi.fn(),
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
    kind: null,
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

  it("calls toast.success on warm success", async () => {
    const { mutations, wrapper } = setup(1);

    await mutations.warmMutation.mutateAsync();

    expect(toast.success).toHaveBeenCalledWith("Generated images queued");
    wrapper.unmount();
  });

  it("warmMutation calls generateMissingImages without a kind by default", async () => {
    const { mutations, wrapper } = setup(42);

    await mutations.warmMutation.mutateAsync();

    expect(generateMissingImages).toHaveBeenCalledWith(42, undefined);
    wrapper.unmount();
  });

  it("passes through an explicit derivative kind", async () => {
    const { mutations, wrapper } = setup(42);

    await mutations.warmMutation.mutateAsync("preview");

    expect(generateMissingImages).toHaveBeenCalledWith(42, "preview");
    wrapper.unmount();
  });

  it("does not export global mutations (rebuild/clear)", async () => {
    const { mutations, wrapper } = setup(1);

    expect(mutations).not.toHaveProperty("rebuildMutation");
    expect(mutations).not.toHaveProperty("clearMutation");
    expect(mutations).toHaveProperty("warmMutation");
    wrapper.unmount();
  });
});
