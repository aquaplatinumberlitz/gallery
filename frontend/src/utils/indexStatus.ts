import type { IndexStatusResponse, IndexStatusState } from "@/types";

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
