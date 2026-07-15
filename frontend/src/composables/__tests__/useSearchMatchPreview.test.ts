import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h, ref, type Ref } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { searchCountV2 } from "@/services/api";
import { useSearchMatchPreview } from "../useSearchMatchPreview";
import type { PersistableSearchRequestV1, SearchCountResponseV1 } from "@/types";

vi.mock("@/services/api", () => ({
  searchCountV2: vi.fn(),
}));

const sampleRequest = (text: string): PersistableSearchRequestV1 => ({
  schema_version: 1,
  mode: "lexical",
  text,
  scope: { kind: "all" },
  filters: { prompt_groups: [], workflow_groups: [] },
});

const makeCountResponse = (overrides: Partial<SearchCountResponseV1>): SearchCountResponseV1 => ({
  schema_version: 1,
  total: 0,
  has_more: false,
  ...overrides,
});

function setup(request: Ref<PersistableSearchRequestV1 | null>, debounceMs = 50) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  let result!: ReturnType<typeof useSearchMatchPreview>;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useSearchMatchPreview(request, { enabled: true, debounceMs });
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { result, wrapper };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useSearchMatchPreview", () => {
  it("stays idle when there is no request", async () => {
    const request = ref<PersistableSearchRequestV1 | null>(null);
    const { result } = setup(request);
    await vi.advanceTimersByTimeAsync(100);
    expect(result.state.value.status).toBe("idle");
    expect(searchCountV2).not.toHaveBeenCalled();
  });

  it("delays the preview request until the debounce window elapses after a change", async () => {
    vi.mocked(searchCountV2).mockResolvedValue(makeCountResponse({ total: 5, has_more: false }));
    const request = ref<PersistableSearchRequestV1 | null>(null);
    const { result } = setup(request, 50);
    await vi.advanceTimersByTimeAsync(0);
    request.value = sampleRequest("cat");
    await vi.advanceTimersByTimeAsync(20);
    expect(searchCountV2).not.toHaveBeenCalled();
    expect(result.state.value.status).toBe("idle");
    await vi.advanceTimersByTimeAsync(40);
    await vi.waitFor(() => expect(result.state.value.status).toBe("done"));
    expect(searchCountV2).toHaveBeenCalledTimes(1);
  });

  it("reports the exact total from the count endpoint", async () => {
    vi.mocked(searchCountV2).mockResolvedValue(makeCountResponse({ total: 42, has_more: false }));
    const request = ref<PersistableSearchRequestV1 | null>(sampleRequest("cat"));
    const { result } = setup(request, 50);
    await vi.advanceTimersByTimeAsync(60);
    await vi.waitFor(() => expect(result.state.value.status).toBe("done"));
    expect(result.state.value).toEqual({ status: "done", total: 42, hasMore: false });
    expect(searchCountV2).toHaveBeenCalledWith(
      expect.objectContaining({ cursor: null, limit: 1, text: "cat" }),
      expect.any(AbortSignal),
    );
  });

  it("reports hasMore when total exceeds the preview limit", async () => {
    vi.mocked(searchCountV2).mockResolvedValue(makeCountResponse({ total: 100, has_more: true }));
    const request = ref<PersistableSearchRequestV1 | null>(sampleRequest("cat"));
    const { result } = setup(request, 50);
    await vi.advanceTimersByTimeAsync(60);
    await vi.waitFor(() => expect(result.state.value.status).toBe("done"));
    expect(result.state.value).toEqual({ status: "done", total: 100, hasMore: true });
  });

  it("reports zero matches when the count endpoint returns total 0", async () => {
    vi.mocked(searchCountV2).mockResolvedValue(makeCountResponse({ total: 0, has_more: false }));
    const request = ref<PersistableSearchRequestV1 | null>(sampleRequest("zzz"));
    const { result } = setup(request, 50);
    await vi.advanceTimersByTimeAsync(60);
    await vi.waitFor(() => expect(result.state.value.status).toBe("done"));
    expect(result.state.value.total).toBe(0);
  });

  it("surfaces an error state when the count request fails", async () => {
    vi.mocked(searchCountV2).mockRejectedValue(new Error("network"));
    const request = ref<PersistableSearchRequestV1 | null>(sampleRequest("cat"));
    const { result } = setup(request, 50);
    await vi.advanceTimersByTimeAsync(60);
    await vi.waitFor(() => expect(result.state.value.status).toBe("error"));
    expect(result.state.value.total).toBe(0);
  });
});
