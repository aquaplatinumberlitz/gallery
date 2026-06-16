import type { IndexStatusResponse, IndexStatusState } from "@/types";

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

export function getIndexStatusCounts(status: IndexStatusResponse | null | undefined): IndexStatusCounts {
  return {
    queued: status?.queued ?? 0,
    running: status?.running ?? 0,
    done: status?.done ?? 0,
    failed: status?.failed ?? 0,
    stale: status?.stale ?? 0,
    skipped: status?.skipped ?? 0,
    activeJobs: status?.active_jobs ?? 0,
    runtimeQueueDepth: status?.runtime_queue_depth ?? 0,
    stagedPathQueueDepth: status?.staged_path_queue_depth ?? 0,
    stagedPathFailed: status?.staged_path_failed ?? 0,
    activeScanRequests: status?.active_scan_requests ?? 0,
  };
}

export function hasFailedIndexWork(status: IndexStatusResponse | null | undefined) {
  const counts = getIndexStatusCounts(status);
  return counts.failed > 0 || counts.stagedPathFailed > 0 || Boolean(status?.last_error);
}

export function hasActiveIndexWork(status: IndexStatusResponse | null | undefined) {
  const counts = getIndexStatusCounts(status);
  return counts.running > 0 || counts.activeJobs > 0 || counts.activeScanRequests > 0;
}

export function hasQueuedIndexWork(status: IndexStatusResponse | null | undefined) {
  const counts = getIndexStatusCounts(status);
  return counts.queued > 0 || counts.runtimeQueueDepth > 0 || counts.stagedPathQueueDepth > 0;
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
  if ((status.stale ?? 0) > 0) return "stale";
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
  if (hasActiveIndexWork(status) || hasQueuedIndexWork(status)) return 2_500;
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
