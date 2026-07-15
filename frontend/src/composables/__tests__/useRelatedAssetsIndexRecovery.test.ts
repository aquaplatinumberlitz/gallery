/**
 * Purpose: Protect unified Related Assets recovery across independently ready metadata and visual indexes.
 * Guarantees: Each index builds by kind, building status polls through the shared query, and completion refetches results.
 * Run when: Changing Related Assets readiness, index rebuild, polling, or automatic recovery behavior.
 */
import { effectScope, nextTick, ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { RelatedSearchStatusV1, SearchIndexStateV1 } from "@/types";
import { useRelatedAssetsIndexRecovery } from "../useRelatedAssetsIndexRecovery";

const useSearchIndexStatusQuery = vi.hoisted(() => vi.fn());

vi.mock("@/composables/useSearchIndexStatusQuery", () => ({ useSearchIndexStatusQuery }));

function indexState(indexName: string, overrides: Partial<SearchIndexStateV1> = {}): SearchIndexStateV1 {
  return {
    index_name: indexName,
    library_id: 4,
    library_name: "Library",
    state: "pending",
    usable: false,
    enabled: true,
    schema_version: 1,
    extractor_version: 1,
    indexed_count: 0,
    target_count: 5,
    failed_count: 0,
    skipped_count: 0,
    skip_reasons: {},
    active_job_id: null,
    ...overrides,
  };
}

function relatedStatus(): RelatedSearchStatusV1 {
  return {
    metadata: {
      index_name: "generation_signatures",
      state: "building",
      usable: false,
      indexed_count: 2,
      target_count: 5,
    },
    visual: {
      index_name: "visual_fingerprints",
      state: "ready",
      usable: true,
      indexed_count: 5,
      target_count: 5,
    },
  };
}

function setup(initialRows: SearchIndexStateV1[] = []) {
  const rows = ref<SearchIndexStateV1[]>(initialRows);
  const refetchStatus = vi.fn().mockResolvedValue(undefined);
  const mutateAsync = vi.fn().mockResolvedValue({ id: 1, state: "queued" });
  useSearchIndexStatusQuery.mockReturnValue({
    statuses: {
      data: rows,
      isPending: ref(false),
      isError: ref(false),
      refetch: refetchStatus,
    },
    rebuild: {
      isPending: ref(false),
      error: ref(null),
      mutateAsync,
    },
    cancel: { isPending: ref(false), mutate: vi.fn() },
  });
  const libraryId = ref<number | null>(4);
  const panelOpen = ref(true);
  const status = ref<RelatedSearchStatusV1 | null>(relatedStatus());
  const onReady = vi.fn().mockResolvedValue(undefined);
  const scope = effectScope();
  let recovery!: ReturnType<typeof useRelatedAssetsIndexRecovery>;
  scope.run(() => {
    recovery = useRelatedAssetsIndexRecovery({ libraryId, panelOpen, relatedStatus: status, onReady });
  });
  return { recovery, rows, mutateAsync, refetchStatus, onReady, stop: () => scope.stop() };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useRelatedAssetsIndexRecovery", () => {
  it("starts the requested index build without any profile state", async () => {
    const context = setup();

    await context.recovery.startBuild("metadata");
    expect(context.mutateAsync).toHaveBeenCalledWith({
      indexName: "generation_signatures",
      libraryId: 4,
      mode: "missing",
    });

    await context.recovery.startBuild("visual");
    expect(context.mutateAsync).toHaveBeenLastCalledWith({
      indexName: "visual_fingerprints",
      libraryId: 4,
      mode: "missing",
    });
    context.stop();
  });

  it("uses polled index progress over the response readiness snapshot", () => {
    const context = setup([
      indexState("generation_signatures", { state: "building", indexed_count: 3, active_job_id: 10 }),
    ]);

    expect(context.recovery.metadataStatus.value?.indexed_count).toBe(3);
    expect(context.recovery.progressPercent("metadata")).toBe(60);
    context.stop();
  });

  it("automatically refetches unified results when either building index becomes ready", async () => {
    const context = setup([
      indexState("generation_signatures", { state: "building", indexed_count: 2, active_job_id: 10 }),
    ]);
    context.rows.value = [indexState("generation_signatures", { state: "ready", usable: true, indexed_count: 5 })];
    await nextTick();
    await vi.waitFor(() => expect(context.onReady).toHaveBeenCalledOnce());
    context.stop();
  });
});
