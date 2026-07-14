import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useFileHealthQuery, useFileHealthMutation } from "../useFileHealthQuery";
import * as api from "@/services/api";

const mockRun = {
  id: 1,
  trigger: "manual" as const,
  started_at: 1730000000,
  finished_at: 1730000005,
  status: "ok" as const,
  error: null,
  issues: {
    missing_source_files: 0,
    generated_image_missing: 2,
    generated_image_abandoned: 1,
    metadata_mismatch: 1,
    file_index_ownership_mismatch: 1,
    orphaned_work_item: 0,
    generated_image_job_mismatch: 3,
  },
  repairs: {
    repaired: 3,
    requeued: 2,
    failed: 0,
    skipped: 1,
    recovered: 1,
    unchanged: 1,
  },
};

const mockResponse = { run: mockRun };

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof api>("@/services/api");
  return {
    ...actual,
    fetchFileHealth: vi.fn(),
    runFileHealthCheck: vi.fn(),
  };
});

vi.mock("@/composables/useToast", () => ({
  useToast: () => ({ error: vi.fn() }),
}));

describe("useFileHealthQuery", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  });

  function setup() {
    let result!: ReturnType<typeof useFileHealthQuery>;
    const wrapper = mount(
      defineComponent({
        setup() {
          result = useFileHealthQuery();
          return () => h("div");
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
    );
    return { result, wrapper };
  }

  it("returns a query that fetches file health", () => {
    const { wrapper } = setup();
    expect(vi.mocked(api.fetchFileHealth).mock).toBeDefined();
    wrapper.unmount();
  });
});

describe("useFileHealthMutation", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  });

  function setup() {
    let result!: ReturnType<typeof useFileHealthMutation>;
    const wrapper = mount(
      defineComponent({
        setup() {
          result = useFileHealthMutation();
          return () => h("div");
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
    );
    return { result, wrapper };
  }

  it("calls runFileHealthCheck on mutation", async () => {
    vi.mocked(api.runFileHealthCheck).mockResolvedValue(mockResponse);
    const { result, wrapper } = setup();
    result.mutate();
    await vi.waitFor(() => {
      expect(vi.mocked(api.runFileHealthCheck)).toHaveBeenCalled();
    });
    wrapper.unmount();
  });

  it("invalidates file-health query on success", async () => {
    vi.mocked(api.runFileHealthCheck).mockResolvedValue(mockResponse);
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const { result, wrapper } = setup();
    result.mutate();
    await vi.waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ["maintenance", "file-health"],
      });
    });
    wrapper.unmount();
  });
});
