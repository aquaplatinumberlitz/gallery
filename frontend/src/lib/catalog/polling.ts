import type { UnifiedStatus } from "./status";

export const ACTIVE_POLL_INTERVAL = 2_500;
export const STABLE_POLL_INTERVAL = 60_000;

/**
 * Returns true when a catalog or metadata job is currently queued or running
 * for the given status, so the UI should poll on the active interval.
 */
export function isUnifiedStatusActive(status: UnifiedStatus | undefined | null): boolean {
  if (!status) return false;
  if (status.scan.state === "queued" || status.scan.state === "scanning") return true;
  if (status.metadata.state === "queued" || status.metadata.state === "indexing") return true;
  return false;
}

/**
 * Shared refetch interval calculator for catalog status queries.
 *
 * Returns `false` (disable polling) when the query is not enabled or no status
 * is available yet, `ACTIVE_POLL_INTERVAL` while catalog/metadata work is
 * queued or running, and `STABLE_POLL_INTERVAL` once the scope settles.
 */
export function statusRefetchInterval(status: UnifiedStatus | undefined | null, enabled: boolean): number | false {
  if (!enabled || !status) return false;
  return isUnifiedStatusActive(status) ? ACTIVE_POLL_INTERVAL : STABLE_POLL_INTERVAL;
}
