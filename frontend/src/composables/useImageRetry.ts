import { onScopeDispose, readonly, ref } from "vue";

/**
 * Backoff before retry 1, 2 and 3 of an image that failed to load. A cold album can answer
 * `/api/thumbnail` with a 503 after waiting 10 s for generation; the derivative is usually ready a few
 * seconds later, so the tile retries instead of staying on the error placeholder for the whole visit.
 */
export const IMAGE_RETRY_DELAYS_MS = [1500, 4000, 10000] as const;

/**
 * Bounded retry of one `<img>`.
 *
 * `<img>` does not expose the HTTP status, so every real error counts as retryable; the bound is the
 * three delays above. The consumer adds `retryAttempt` to the URL as `&r=<n>` while it is above zero, so the
 * browser makes a new request instead of reusing the failed one.
 *
 * - `scheduleRetry()` on a real error: true when a retry was scheduled (keep showing the loading
 *   skeleton), false when the attempts are used up (show the error state).
 * - `resetRetry()` when the card leaves the viewport or gets a new image: it cancels a pending retry and
 *   restarts the sequence, so a card that comes back starts again with a fresh budget.
 * - A pending retry is cancelled with the owning component/scope.
 */
export function useImageRetry() {
  const attempt = ref(0);
  const pending = ref(false);
  let timer: ReturnType<typeof setTimeout> | null = null;

  const cancelRetry = () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    pending.value = false;
  };

  const scheduleRetry = (): boolean => {
    if (timer) return true; // duplicate error events while a retry is already waiting
    const delay = IMAGE_RETRY_DELAYS_MS[attempt.value];
    if (delay === undefined) return false;
    pending.value = true;
    timer = setTimeout(() => {
      timer = null;
      pending.value = false;
      attempt.value += 1;
    }, delay);
    return true;
  };

  const resetRetry = () => {
    cancelRetry();
    attempt.value = 0;
  };

  onScopeDispose(cancelRetry, true);

  return {
    /** Retries already started: 0 for the first load, up to `IMAGE_RETRY_DELAYS_MS.length`. */
    retryAttempt: readonly(attempt),
    /** A retry is waiting for its backoff. */
    retryPending: readonly(pending),
    scheduleRetry,
    cancelRetry,
    resetRetry,
  };
}
