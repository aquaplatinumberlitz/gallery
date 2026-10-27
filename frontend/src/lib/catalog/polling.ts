import type { UnifiedStatus } from "./status";

export const ACTIVE_POLL_INTERVAL = 2_500;
export const STABLE_POLL_INTERVAL = 60_000;
/** The active interval never drops below this multiple of the last observed fetch duration. */
export const POLL_BACKOFF_FACTOR = 2;

/** The slice of a TanStack `Query` the interval logic observes; any real query satisfies it. */
export interface PolledQuery {
  state?: { fetchStatus?: "fetching" | "paused" | "idle" };
}

interface FetchClock {
  startedAt: number | null;
  lastDurationMs: number | null;
}

const fetchClocks = new WeakMap<object, FetchClock>();

/**
 * Observes one `refetchInterval` callback invocation for a query and returns the duration of its
 * last completed fetch in milliseconds (null until one has been seen).
 *
 * TanStack Query re-evaluates `refetchInterval` on every query update, including the dispatch that
 * starts a fetch (`fetchStatus === "fetching"`) and the one that settles it (`"idle"`), so the
 * elapsed time between those two invocations is the fetch duration. Calls without a
 * `fetchStatus` (for example from tests) observe nothing.
 */
export function observeFetchDuration(
  query: PolledQuery | undefined | null,
  now: number = typeof performance !== "undefined" ? performance.now() : Date.now(),
): number | null {
  if (!query) return null;
  let clock = fetchClocks.get(query);
  if (!clock) {
    clock = { startedAt: null, lastDurationMs: null };
    fetchClocks.set(query, clock);
  }
  const fetchStatus = query.state?.fetchStatus;
  if (fetchStatus === "fetching") {
    if (clock.startedAt === null) clock.startedAt = now;
  } else if (fetchStatus === "idle" && clock.startedAt !== null) {
    clock.lastDurationMs = Math.max(0, now - clock.startedAt);
    clock.startedAt = null;
  }
  return clock.lastDurationMs;
}

/**
 * Active polling interval for a given last fetch duration: `ACTIVE_POLL_INTERVAL`, raised to
 * `POLL_BACKOFF_FACTOR` times the fetch duration when the endpoint is slow, and capped at
 * `STABLE_POLL_INTERVAL`. A slow status endpoint therefore cannot be re-requested faster than it
 * can answer, which keeps polling from queueing up behind itself.
 */
export function backoffInterval(lastFetchMs: number | null | undefined): number {
  if (lastFetchMs === null || lastFetchMs === undefined || !Number.isFinite(lastFetchMs) || lastFetchMs <= 0) {
    return ACTIVE_POLL_INTERVAL;
  }
  return Math.min(STABLE_POLL_INTERVAL, Math.max(ACTIVE_POLL_INTERVAL, POLL_BACKOFF_FACTOR * lastFetchMs));
}

/**
 * Active interval for one query. Call it from every `refetchInterval` invocation (also when the
 * result is not used) so the fetch clock sees both the start and the end of each fetch.
 */
export function activePollInterval(query?: PolledQuery | null, now?: number): number {
  return backoffInterval(observeFetchDuration(query, now));
}

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
 * is available yet, the active interval (`ACTIVE_POLL_INTERVAL`, backed off to twice the
 * last observed fetch duration of `query`) while catalog/metadata work is queued or
 * running, and `STABLE_POLL_INTERVAL` once the scope settles.
 */
export function statusRefetchInterval(
  status: UnifiedStatus | undefined | null,
  enabled: boolean,
  query?: PolledQuery | null,
): number | false {
  const activeInterval = activePollInterval(query);
  if (!enabled || !status) return false;
  return isUnifiedStatusActive(status) ? activeInterval : STABLE_POLL_INTERVAL;
}
