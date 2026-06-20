import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { queryKeys } from "@/query/keys";
import {
  createLibrary,
  deleteLibrary,
  repairLibrary,
  scanAllLibraries,
  scanLibrary,
  updateLibrary,
} from "@/services/api";
import { useLibraryMutations } from "../useLibraryMutations";

const toast = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
};

vi.mock("@/composables/useToast", () => ({ useToast: () => toast }));
vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return {
    ...actual,
    createLibrary: vi.fn(),
    deleteLibrary: vi.fn(),
    repairLibrary: vi.fn(),
    scanAllLibraries: vi.fn(),
    scanLibrary: vi.fn(),
    updateLibrary: vi.fn(),
    validateLibraryCreate: vi.fn(),
    validateLibraryUpdate: vi.fn(),
  };
});

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const invalidate = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue();
  let mutations!: ReturnType<typeof useLibraryMutations>;
  const wrapper = mount(
    defineComponent({
      setup() {
        mutations = useLibraryMutations();
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { invalidate, mutations, wrapper };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(createLibrary).mockResolvedValue({ id: 3 } as Awaited<ReturnType<typeof createLibrary>>);
  vi.mocked(updateLibrary).mockResolvedValue({ id: 3 } as Awaited<ReturnType<typeof updateLibrary>>);
  vi.mocked(scanLibrary).mockResolvedValue({ library_id: 3, job_id: 8, state: "queued" });
  vi.mocked(scanAllLibraries).mockResolvedValue({ job_id: 9, state: "queued" });
  vi.mocked(repairLibrary).mockResolvedValue({ library_id: 3, added: 1, removed: 0, modified: 0 });
  vi.mocked(deleteLibrary).mockResolvedValue();
});

describe("useLibraryMutations invalidation", () => {
  it("invalidates the library root after create and unregister", async () => {
    const { invalidate, mutations, wrapper } = setup();

    await mutations.createMutation.mutateAsync({ root_path: "/photos" });
    await mutations.unregisterMutation.mutateAsync(3);

    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.librariesRoot() });
    expect(invalidate).toHaveBeenCalledTimes(2);
    wrapper.unmount();
  });

  it("invalidates detail and list after update", async () => {
    const { invalidate, mutations, wrapper } = setup();

    await mutations.updateMutation.mutateAsync({ id: 3, payload: { name: "Updated" } });

    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.library(3) });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.libraries() });
    wrapper.unmount();
  });

  it("invalidates progress and job queries after scan", async () => {
    const { invalidate, mutations, wrapper } = setup();

    await mutations.scanMutation.mutateAsync(3);

    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.libraryProgress(3) });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.libraryJobs(3) });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.jobsRoot() });
    wrapper.unmount();
  });

  it("invalidates stats and job queries after repair", async () => {
    const { invalidate, mutations, wrapper } = setup();

    await mutations.repairMutation.mutateAsync(3);

    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.libraryStats(3) });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.libraryJobs(3) });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.jobsRoot() });
    wrapper.unmount();
  });

  it("invalidates global jobs after scan-all", async () => {
    const { invalidate, mutations, wrapper } = setup();

    await mutations.scanAllMutation.mutateAsync();

    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.jobsRoot() });
    wrapper.unmount();
  });
});
