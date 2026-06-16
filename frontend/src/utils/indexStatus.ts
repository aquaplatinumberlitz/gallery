import type { IndexStatusResponse, IndexStatusRuntime, IndexStatusScope, IndexStatusState } from "@/types";

export type IndexUiStatus =
  | "unknown"
  | "ready"
  | "indexing"
  | "stale"
  | "warning"
  | "error";

export interface IndexStatusPresentation {
  status: IndexUiStatus;
  label: string;
  tone: "green" | "yellow" | "red" | "gray";
  showPulse: boolean;
}

export interface IndexStatusCounts {
  queued: number;
  running: number;
  done: number;
  failed: number;
  stale: number;
  skipped: number;
  activeJobs: number;
  runtimeQueueDepth: number;
  stagedPathQueueDepth: number;
  stagedPathFailed: number;
  activeScanRequests: number;
  activeRebuilds: number;
  missingMetadataRecords: number;
}

export interface IndexStatusProgressInfo {
  indexed: number;
  pending: number;
  total: number | null;
  percent: number | null;
}

const INDEX_STATUS_PRESENTATION: Record<IndexUiStatus, IndexStatusPresentation> = {
  unknown: {
    status: "unknown",
    label: "Unknown",
    tone: "gray",
    showPulse: false,
  },
  ready: {
    status: "ready",
    label: "Ready",
    tone: "green",
    showPulse: false,
  },
  indexing: {
    status: "indexing",
    label: "Updating",
    tone: "yellow",
    showPulse: true,
  },
  stale: {
    status: "stale",
    label: "Needs update",
    tone: "yellow",
    showPulse: false,
  },
  warning: {
    status: "warning",
    label: "Unavailable",
    tone: "gray",
    showPulse: false,
  },
  error: {
    status: "error",
    label: "Error",
    tone: "red",
    showPulse: false,
  },
};

function getScopedStatus(status: IndexStatusResponse | null | undefined): IndexStatusResponse | IndexStatusScope | null {
  return status?.scope ?? status ?? null;
}

function getGlobalRuntime(status: IndexStatusResponse | null | undefined): IndexStatusRuntime | null {
  if (!status) return null;
  return status.global_runtime ?? {
    enabled: status.enabled,
    worker_count: status.worker_count,
    active_jobs: status.active_jobs,
    runtime_queue_depth: status.runtime_queue_depth,
    coalesced_duplicates: status.coalesced_duplicates,
    staged_path_queue_depth: status.staged_path_queue_depth,
    staged_path_coalesced: status.staged_path_coalesced,
    staged_path_failed: status.staged_path_failed,
    staged_path_flushes_forced: status.staged_path_flushes_forced,
    staged_path_worker_count: status.staged_path_worker_count,
    active_scan_requests: status.active_scan_requests,
    batch_size: status.batch_size,
    staged_path_batch_size: status.staged_path_batch_size,
    stage_max_wait_seconds: status.stage_max_wait_seconds,
  };
}

export function getIndexStatusCounts(status: IndexStatusResponse | null | undefined): IndexStatusCounts {
  const scoped = getScopedStatus(status);
  const scopedRuntime = scoped as IndexStatusScope | null;
  const hasExplicitScope = Boolean(status?.scope);
  return {
    queued: scoped?.queued ?? 0,
    running: scoped?.running ?? 0,
    done: scoped?.done ?? 0,
    failed: scoped?.failed ?? 0,
    stale: scoped?.stale ?? 0,
    skipped: scoped?.skipped ?? 0,
    activeJobs: hasExplicitScope ? (scoped?.active_jobs ?? 0) : 0,
    runtimeQueueDepth: hasExplicitScope ? (scoped?.runtime_queue_depth ?? 0) : 0,
    stagedPathQueueDepth: hasExplicitScope ? (scoped?.staged_path_queue_depth ?? 0) : 0,
    stagedPathFailed: 0,
    activeScanRequests: hasExplicitScope ? (scoped?.active_scan_requests ?? 0) : 0,
    activeRebuilds: hasExplicitScope ? (scopedRuntime?.active_rebuilds ?? 0) : 0,
    missingMetadataRecords: scoped?.missing_metadata_records ?? Math.max(
      0,
      (scoped?.indexed_photos ?? 0) - (scoped?.metadata_records ?? 0)
    ),
  };
}

export function getGlobalIndexStatusCounts(status: IndexStatusResponse | null | undefined): IndexStatusCounts {
  const runtime = getGlobalRuntime(status);
  return {
    queued: status?.queued ?? 0,
    running: status?.running ?? 0,
    done: status?.done ?? 0,
    failed: status?.failed ?? 0,
    stale: status?.stale ?? 0,
    skipped: status?.skipped ?? 0,
    activeJobs: runtime?.active_jobs ?? 0,
    runtimeQueueDepth: runtime?.runtime_queue_depth ?? 0,
    stagedPathQueueDepth: runtime?.staged_path_queue_depth ?? 0,
    stagedPathFailed: runtime?.staged_path_failed ?? 0,
    activeScanRequests: runtime?.active_scan_requests ?? 0,
    activeRebuilds: 0,
    missingMetadataRecords: status?.missing_metadata_records ?? Math.max(
      0,
      (status?.indexed_photos ?? 0) - (status?.metadata_records ?? 0)
    ),
  };
}

export function hasFailedIndexWork(status: IndexStatusResponse | null | undefined) {
  const counts = getIndexStatusCounts(status);
  const scoped = getScopedStatus(status);
  return counts.failed > 0 || Boolean(scoped?.last_error);
}

export function hasActiveIndexWork(status: IndexStatusResponse | null | undefined) {
  const counts = getIndexStatusCounts(status);
  return counts.running > 0 || counts.activeJobs > 0 || counts.activeScanRequests > 0 || counts.activeRebuilds > 0;
}

export function hasQueuedIndexWork(status: IndexStatusResponse | null | undefined) {
  const counts = getIndexStatusCounts(status);
  return counts.queued > 0 || counts.runtimeQueueDepth > 0 || counts.stagedPathQueueDepth > 0;
}

export function hasKnownIndexUpdates(status: IndexStatusResponse | null | undefined) {
  const counts = getIndexStatusCounts(status);
  return counts.stale > 0 || counts.missingMetadataRecords > 0;
}

export function hasGlobalIndexWork(status: IndexStatusResponse | null | undefined) {
  const counts = getGlobalIndexStatusCounts(status);
  return (
    counts.activeJobs > 0 ||
    counts.runtimeQueueDepth > 0 ||
    counts.stagedPathQueueDepth > 0 ||
    counts.activeScanRequests > 0
  );
}

export function hasGlobalIndexWorkOutsideScope(status: IndexStatusResponse | null | undefined) {
  return hasGlobalIndexWork(status) && !hasActiveIndexWork(status) && !hasQueuedIndexWork(status);
}

export function getIndexUiStatus(
  status: IndexStatusResponse | null | undefined,
  opts: { hasPath: boolean; isLoading?: boolean; isError?: boolean } = { hasPath: true }
): IndexUiStatus {
  if (opts.isError) return "error";
  if (!opts.hasPath || opts.isLoading || !status) return "unknown";
  if (!status.enabled) return "warning";
  if (hasFailedIndexWork(status)) return "error";
  if (hasActiveIndexWork(status) || hasQueuedIndexWork(status)) return "indexing";
  if (hasKnownIndexUpdates(status)) return "stale";
  return "ready";
}

export function getIndexStatusPresentation(
  status: IndexStatusResponse | null | undefined,
  opts: { hasPath: boolean; isLoading?: boolean; isError?: boolean } = { hasPath: true }
): IndexStatusPresentation {
  return INDEX_STATUS_PRESENTATION[getIndexUiStatus(status, opts)];
}

export function getIndexStatusState(
  status: IndexStatusResponse | null | undefined,
  opts: { hasPath: boolean; isUnavailable?: boolean }
): IndexStatusState {
  if (!opts.hasPath) return "disabled";
  if (opts.isUnavailable) return "unavailable";
  if (!status) return "idle";
  if (!status.enabled) return "disabled";
  if (hasFailedIndexWork(status)) return "failed";
  if (hasActiveIndexWork(status)) return "active";
  if (hasQueuedIndexWork(status)) return "queued";
  return "idle";
}

export function getIndexStatusRefetchInterval(
  status: IndexStatusResponse | null | undefined,
  isUnavailable = false
) {
  if (isUnavailable || !status) return 60_000;
  if (hasActiveIndexWork(status) || hasQueuedIndexWork(status) || hasGlobalIndexWork(status)) return 2_500;
  return 60_000;
}

export function getIndexStatusProgress(status: IndexStatusResponse | null | undefined) {
  const counts = getIndexStatusCounts(status);
  const total =
    counts.queued +
    counts.running +
    counts.done +
    counts.failed +
    counts.stale +
    counts.skipped;

  if (total <= 0) return null;
  return Math.max(0, Math.min(100, Math.round((counts.done / total) * 100)));
}

export function getIndexStatusProgressInfo(status: IndexStatusResponse | null | undefined): IndexStatusProgressInfo {
  const counts = getIndexStatusCounts(status);
  const pending =
    counts.queued +
    counts.running +
    counts.stale +
    counts.runtimeQueueDepth +
    counts.stagedPathQueueDepth +
    counts.activeJobs +
    counts.activeScanRequests;
  const fallbackTotal =
    counts.queued +
    counts.running +
    counts.done +
    counts.failed +
    counts.stale +
    counts.skipped;
  const total = (status?.total ?? 0) > 0 ? status!.total : fallbackTotal > 0 ? fallbackTotal : null;

  return {
    indexed: counts.done,
    pending,
    total,
    percent: total ? Math.max(0, Math.min(100, Math.round((counts.done / total) * 100))) : null,
  };
}
