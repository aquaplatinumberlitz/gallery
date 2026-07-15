/**
 * Purpose: Protect adaptable Related Assets query keys, retries, and reference isolation.
 * Guarantees: Plain/ref/getter inputs work; reference changes clear prior data; refetch errors retain successful data.
 * Run when: Changing Related Assets requests, TanStack Query policy, or panel refresh behavior.
 */
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h, ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchRelatedAssets, GalleryAPIError } from "@/services/api";
import type { RelatedSearchRequestV1, RelatedSearchResponseV1 } from "@/types";
import { useRelatedAssetsQuery } from "../useRelatedAssetsQuery";

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return { ...actual, fetchRelatedAssets: vi.fn() };
});

const request = (assetId: number): RelatedSearchRequestV1 => ({
  schema_version: 1,
  reference_asset_id: assetId,
  profile: "related",
  scope: { kind: "library", library_id: 1 },
  limit: 60,
});

const response = (assetId: number): RelatedSearchResponseV1 => ({
  schema_version: 1,
  reference_asset_id: assetId,
  profile: "related",
  scope: { kind: "library", library_id: 1 },
  items: [],
  returned: 0,
  limit: 60,
  status: {
    metadata: { index_name: "generation_signatures", state: "ready", usable: true, indexed_count: 1, target_count: 1 },
    visual: { index_name: "visual_fingerprints", state: "building", usable: false, indexed_count: 0, target_count: 1 },
  },
});

function setup(initial: RelatedSearchRequestV1 | null) {
  const source = ref(initial);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  let result!: ReturnType<typeof useRelatedAssetsQuery>;
  mount(
    defineComponent({
      setup() {
        result = useRelatedAssetsQuery(() => source.value);
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { result, source };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchRelatedAssets).mockImplementation(async (value) => response(value.reference_asset_id));
});

describe("useRelatedAssetsQuery", () => {
  it("accepts a getter and fetches the complete reference request", async () => {
    const { result } = setup(request(10));
    await vi.waitFor(() => expect(result.data.value?.reference_asset_id).toBe(10));
    expect(fetchRelatedAssets).toHaveBeenCalledWith(request(10), expect.any(AbortSignal));
  });

  it("does not leak prior results when the reference changes", async () => {
    const { result, source } = setup(request(10));
    await vi.waitFor(() => expect(result.data.value?.reference_asset_id).toBe(10));
    let resolveNext!: (value: RelatedSearchResponseV1) => void;
    vi.mocked(fetchRelatedAssets).mockReturnValueOnce(
      new Promise((resolve) => {
        resolveNext = resolve;
      }),
    );
    source.value = request(20);
    await vi.waitFor(() => expect(fetchRelatedAssets).toHaveBeenCalledWith(request(20), expect.any(AbortSignal)));
    expect(result.data.value).toBeUndefined();
    resolveNext(response(20));
    await vi.waitFor(() => expect(result.data.value?.reference_asset_id).toBe(20));
  });

  it("cancels the prior request when the reference changes", async () => {
    let firstSignal: AbortSignal | undefined;
    vi.mocked(fetchRelatedAssets)
      .mockImplementationOnce(
        (_value, signal) =>
          new Promise((_resolve, reject) => {
            firstSignal = signal;
            signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
          }),
      )
      .mockImplementationOnce(async (value) => response(value.reference_asset_id));
    const { result, source } = setup(request(10));
    await vi.waitFor(() => expect(firstSignal).toBeInstanceOf(AbortSignal));
    source.value = request(20);
    await vi.waitFor(() => expect(firstSignal?.aborted).toBe(true));
    await vi.waitFor(() => expect(result.data.value?.reference_asset_id).toBe(20));
  });

  it("retries one typed retryable failure and not an untyped failure", async () => {
    vi.mocked(fetchRelatedAssets)
      .mockRejectedValueOnce(new GalleryAPIError("server_error", "Failed", "Retry", true))
      .mockImplementationOnce(async (value) => response(value.reference_asset_id));
    const retryable = setup(request(10));
    await vi.waitFor(() => expect(retryable.result.data.value?.reference_asset_id).toBe(10), { timeout: 3_000 });
    expect(fetchRelatedAssets).toHaveBeenCalledTimes(2);

    vi.clearAllMocks();
    vi.mocked(fetchRelatedAssets).mockRejectedValue(new Error("untyped"));
    const nonRetryable = setup(request(20));
    await vi.waitFor(() => expect(nonRetryable.result.isError.value).toBe(true));
    expect(fetchRelatedAssets).toHaveBeenCalledTimes(1);
  });

  it("stops after the documented single retry", async () => {
    vi.mocked(fetchRelatedAssets).mockRejectedValue(new GalleryAPIError("server_error", "Failed", "Retry", true));
    const retryable = setup(request(10));

    await vi.waitFor(() => expect(retryable.result.isError.value).toBe(true), { timeout: 3_000 });
    expect(fetchRelatedAssets).toHaveBeenCalledTimes(2);
  });

  it("does not retry deterministic relation-readiness failures", async () => {
    vi.mocked(fetchRelatedAssets).mockRejectedValue(
      new GalleryAPIError("relation_index_not_ready", "Not ready", "Build the index", true),
    );
    const readiness = setup(request(10));

    await vi.waitFor(() => expect(readiness.result.isError.value).toBe(true));
    expect(fetchRelatedAssets).toHaveBeenCalledTimes(1);
  });

  it("retains successful data when a background refetch fails", async () => {
    const { result } = setup(request(10));
    await vi.waitFor(() => expect(result.data.value?.reference_asset_id).toBe(10));
    vi.mocked(fetchRelatedAssets).mockRejectedValue(new GalleryAPIError("server_error", "Failed", "Retry", true));
    await result.refetch();
    expect(result.data.value?.reference_asset_id).toBe(10);
    expect(result.isRefetchError.value).toBe(true);
  });
});
