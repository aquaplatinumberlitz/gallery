import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchGeneratedImagesStatus } from "@/services/api";
import { useGeneratedImagesStatusQuery } from "../useGeneratedImagesStatusQuery";

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

function setup(id: number | null) {
  const queryClient = new QueryClient();
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
  it("fetches status when library id is provided", async () => {
    const { result } = setup(1);
    await vi.waitFor(() => expect(result.data.value).toEqual(mockStatus));
    expect(fetchGeneratedImagesStatus).toHaveBeenCalledWith(1);
  });

  it("does not fetch when library id is null", () => {
    setup(null);
    expect(fetchGeneratedImagesStatus).not.toHaveBeenCalled();
  });
});
