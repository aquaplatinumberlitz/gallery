import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { fetchLibraryStatusBatch } from "@/services/api";
import { useLibraryStatusBatchQuery } from "../useLibraryStatusBatchQuery";
import { assertLibraryStatusBatch, isStatusContractError } from "@/lib/catalog/contractGuard";

vi.mock("@/services/api", () => ({
  fetchLibraryStatusBatch: vi.fn(),
}));

vi.mock("@/lib/catalog/contractGuard", () => ({
  assertLibraryStatusBatch: vi.fn(),
  isStatusContractError: vi.fn(),
}));

vi.mock("@/lib/catalog/polling", () => ({
  ACTIVE_POLL_INTERVAL: 2000,
  STABLE_POLL_INTERVAL: 10000,
  isUnifiedStatusActive: vi.fn(() => false),
}));

const mockBatchResponse = {
  items: [
    {
      library_id: 1,
      status: {
        summary_state: "ready",
        generated_at: Date.now(),
      },
    },
  ],
};

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { gcTime: 0 } } });
  let result!: ReturnType<typeof useLibraryStatusBatchQuery>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useLibraryStatusBatchQuery();
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { result, wrapper };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchLibraryStatusBatch).mockResolvedValue(mockBatchResponse);
  vi.mocked(assertLibraryStatusBatch).mockReturnValue(undefined);
  vi.mocked(isStatusContractError).mockReturnValue(false);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useLibraryStatusBatchQuery", () => {
  it("fetches batch status on mount", async () => {
    const { result } = setup();
    await vi.waitFor(() => expect(result.data.value).toEqual(mockBatchResponse));
    expect(fetchLibraryStatusBatch).toHaveBeenCalled();
  });

  it("builds statusByLibrary map from response", async () => {
    const { result } = setup();
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(result.statusByLibrary.value.has(1)).toBe(true);
    expect(result.statusByLibrary.value.get(1)?.summary_state).toBe("ready");
  });

  it("has isPending true while loading", () => {
    vi.mocked(fetchLibraryStatusBatch).mockReturnValue(new Promise(() => {}));
    const { result } = setup();
    expect(result.isPending.value).toBe(true);
  });

  it("sets isError on fetch failure", async () => {
    vi.mocked(fetchLibraryStatusBatch).mockRejectedValue(new Error("network error"));
    vi.mocked(isStatusContractError).mockReturnValue(true);
    const { result } = setup();
    await vi.waitFor(() => expect(result.isError.value).toBe(true));
    expect(result.error.value).toBeTruthy();
  });

  it("sets contractError on contract failure", async () => {
    const contractErr = new Error("contract error");
    vi.mocked(fetchLibraryStatusBatch).mockRejectedValue(contractErr);
    vi.mocked(isStatusContractError).mockReturnValue(true);
    const { result } = setup();
    await vi.waitFor(() => expect(result.isError.value).toBe(true));
    expect(result.contractError.value).toBeTruthy();
  });

  it("returns null contractError for non-contract errors", async () => {
    vi.mocked(fetchLibraryStatusBatch).mockRejectedValue(new Error("network error"));
    const { result } = setup();
    await vi.waitFor(() => expect(result.isError.value).toBe(true), { timeout: 5000 });
    expect(result.contractError.value).toBeNull();
  });
});
