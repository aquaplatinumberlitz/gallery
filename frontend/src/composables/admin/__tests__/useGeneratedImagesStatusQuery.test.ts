import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchGeneratedImagesStatus } from "@/services/api";
import { generatedImagesNeedActivePolling, useGeneratedImagesStatusQuery } from "../useGeneratedImagesStatusQuery";

vi.mock("@/services/api", () => ({
  fetchGeneratedImagesStatus: vi.fn(),
}));

const mockStatus = {
  library_id: 1,
  total_assets: 100,
  ready_derivatives: 45,
  expected_derivatives: 200,
  quota_bytes: 1_073_741_824,
  quota_used_bytes: 256_000_000,
  quota_utilization: 0.238,
};

function setup(id: number | null, retry = 1) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry } } });
  let result!: ReturnType<typeof useGeneratedImagesStatusQuery>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useGeneratedImagesStatusQuery(() => id);
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { result, wrapper };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchGeneratedImagesStatus).mockResolvedValue(mockStatus);
});

describe("useGeneratedImagesStatusQuery", () => {
  it("polls only while derivative coverage is incomplete", () => {
    expect(generatedImagesNeedActivePolling(undefined)).toBe(false);
    expect(generatedImagesNeedActivePolling({ ...mockStatus, expected_derivatives: 0, ready_derivatives: 0 })).toBe(
      false,
    );
    expect(generatedImagesNeedActivePolling({ ...mockStatus, expected_derivatives: 200, ready_derivatives: 45 })).toBe(
      true,
    );
    expect(generatedImagesNeedActivePolling({ ...mockStatus, expected_derivatives: 200, ready_derivatives: 200 })).toBe(
      false,
    );
  });

  it("fetches status when library id is provided", async () => {
    const { result } = setup(1);
    await vi.waitFor(() => expect(result.data.value).toEqual(mockStatus));
    expect(fetchGeneratedImagesStatus).toHaveBeenCalledWith(1);
  });

  it("does not fetch when library id is null", () => {
    setup(null);
    expect(fetchGeneratedImagesStatus).not.toHaveBeenCalled();
  });

  it("has isPending true while loading", () => {
    vi.mocked(fetchGeneratedImagesStatus).mockReturnValue(new Promise(() => {}));
    const { result } = setup(1);
    expect(result.isPending.value).toBe(true);
  });

  it("sets isError on fetch failure", async () => {
    vi.mocked(fetchGeneratedImagesStatus).mockRejectedValue(new Error("network error"));
    const { result } = setup(1, 0);
    await vi.waitFor(() => expect(result.isError.value).toBe(true));
    expect(result.error.value).toBeTruthy();
  });

  it("handles expected_derivatives = 0 (empty library)", async () => {
    const emptyLib = { ...mockStatus, expected_derivatives: 0, ready_derivatives: 0 };
    vi.mocked(fetchGeneratedImagesStatus).mockResolvedValue(emptyLib);
    const { result } = setup(1);
    await vi.waitFor(() => expect(result.data.value).toEqual(emptyLib));
    const data = result.data.value!;
    expect(data.expected_derivatives).toBe(0);
    expect(data.ready_derivatives).toBe(0);
  });
});
