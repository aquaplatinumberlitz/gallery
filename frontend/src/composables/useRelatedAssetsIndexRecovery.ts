import { computed, shallowRef, toValue, watch, type MaybeRefOrGetter } from "vue";
import { useSearchIndexStatusQuery } from "@/composables/useSearchIndexStatusQuery";
import type { RelatedIndexComponentStatusV1, RelatedSearchStatusV1, SearchIndexStateV1 } from "@/types";

export type RelatedIndexKind = "metadata" | "visual";
export type RelatedIndexRecoveryStatus = RelatedIndexComponentStatusV1 | SearchIndexStateV1;

interface UseRelatedAssetsIndexRecoveryOptions {
  libraryId: MaybeRefOrGetter<number | null>;
  panelOpen: MaybeRefOrGetter<boolean>;
  relatedStatus: MaybeRefOrGetter<RelatedSearchStatusV1 | null>;
  onReady: () => unknown | Promise<unknown>;
}

const INDEX_NAMES: Record<RelatedIndexKind, RelatedIndexComponentStatusV1["index_name"]> = {
  metadata: "generation_signatures",
  visual: "visual_fingerprints",
};

function needsMonitoring(status: RelatedIndexComponentStatusV1 | null) {
  return Boolean(status && ["not_ready", "building", "failed"].includes(status.state));
}

export function useRelatedAssetsIndexRecovery(options: UseRelatedAssetsIndexRecoveryOptions) {
  const relatedStatus = computed(() => toValue(options.relatedStatus));
  const shouldMonitor = computed(
    () =>
      toValue(options.panelOpen) &&
      (needsMonitoring(relatedStatus.value?.metadata ?? null) || needsMonitoring(relatedStatus.value?.visual ?? null)),
  );
  const statusQuery = useSearchIndexStatusQuery(options.libraryId, shouldMonitor);
  const startingKind = shallowRef<RelatedIndexKind | null>(null);
  const buildErrorKind = shallowRef<RelatedIndexKind | null>(null);
  const readyRefetchInFlight = shallowRef(false);
  const lastStates = new Map<RelatedIndexKind, string>();

  function persistedStatus(kind: RelatedIndexKind): SearchIndexStateV1 | null {
    return statusQuery.statuses.data.value?.find((row) => row.index_name === INDEX_NAMES[kind]) ?? null;
  }

  const metadataStatus = computed<RelatedIndexRecoveryStatus | null>(
    () => persistedStatus("metadata") ?? relatedStatus.value?.metadata ?? null,
  );
  const visualStatus = computed<RelatedIndexRecoveryStatus | null>(
    () => persistedStatus("visual") ?? relatedStatus.value?.visual ?? null,
  );

  function statusFor(kind: RelatedIndexKind) {
    return kind === "metadata" ? metadataStatus.value : visualStatus.value;
  }

  function progressPercent(kind: RelatedIndexKind) {
    const status = statusFor(kind);
    if (!status?.target_count) return 0;
    return Math.min(100, Math.round((status.indexed_count / status.target_count) * 100));
  }

  async function refetchRelated() {
    if (readyRefetchInFlight.value) return;
    readyRefetchInFlight.value = true;
    try {
      await options.onReady();
    } finally {
      readyRefetchInFlight.value = false;
    }
  }

  async function startBuild(kind: RelatedIndexKind) {
    const libraryId = toValue(options.libraryId);
    if (!libraryId || statusQuery.rebuild.isPending.value) return;
    startingKind.value = kind;
    buildErrorKind.value = null;
    try {
      await statusQuery.rebuild.mutateAsync({
        indexName: INDEX_NAMES[kind],
        libraryId,
        mode: "missing",
      });
      const refreshed = await statusQuery.statuses.refetch();
      const refreshedStatus = refreshed.data?.find((row) => row.index_name === INDEX_NAMES[kind]);
      if (refreshedStatus?.state === "ready") await refetchRelated();
    } catch {
      buildErrorKind.value = kind;
    } finally {
      startingKind.value = null;
    }
  }

  async function refreshStatus() {
    await statusQuery.statuses.refetch();
  }

  watch(
    [metadataStatus, visualStatus],
    async ([metadata, visual]) => {
      if (!toValue(options.panelOpen)) {
        lastStates.clear();
        return;
      }
      let completed = false;
      for (const [kind, status] of [
        ["metadata", metadata],
        ["visual", visual],
      ] as const) {
        if (!status) continue;
        const previous = lastStates.get(kind);
        lastStates.set(kind, status.state);
        if (previous && previous !== "ready" && status.state === "ready") completed = true;
      }
      if (completed) await refetchRelated();
    },
    { immediate: true },
  );

  watch(
    () => toValue(options.panelOpen),
    (open) => {
      if (open) return;
      lastStates.clear();
      startingKind.value = null;
      buildErrorKind.value = null;
    },
  );

  return {
    metadataStatus,
    visualStatus,
    statusError: computed(() => statusQuery.statuses.isError.value),
    startingKind,
    buildErrorKind,
    progressPercent,
    startBuild,
    refreshStatus,
  };
}
