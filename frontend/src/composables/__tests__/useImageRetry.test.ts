/**
 * Purpose: Protect the bounded retry state machine used by PhotoCard and the album covers.
 * Guarantees: Three retries with 1.5 s / 4 s / 10 s backoff; `scheduleRetry` returns false once they are
 * used up; a duplicate error while waiting does not consume a retry; `resetRetry` cancels the wait and
 * restores the full budget; the pending timer is cancelled with the owning effect scope.
 * Run when: Changing image retry behaviour or its backoff.
 */
import { effectScope } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { IMAGE_RETRY_DELAYS_MS, useImageRetry } from "../useImageRetry";

describe("useImageRetry", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts at attempt 0 with nothing pending", () => {
    const retry = useImageRetry();
    expect(retry.retryAttempt.value).toBe(0);
    expect(retry.retryPending.value).toBe(false);
  });

  it("schedules three retries with the documented backoff, then reports exhaustion", async () => {
    const retry = useImageRetry();
    for (const [index, delay] of IMAGE_RETRY_DELAYS_MS.entries()) {
      expect(retry.scheduleRetry()).toBe(true);
      expect(retry.retryPending.value).toBe(true);
      await vi.advanceTimersByTimeAsync(delay - 1);
      expect(retry.retryAttempt.value).toBe(index);
      await vi.advanceTimersByTimeAsync(1);
      expect(retry.retryAttempt.value).toBe(index + 1);
      expect(retry.retryPending.value).toBe(false);
    }
    expect(retry.scheduleRetry()).toBe(false);
    expect(retry.retryPending.value).toBe(false);
  });

  it("a duplicate error while waiting keeps the single scheduled retry", async () => {
    const retry = useImageRetry();
    expect(retry.scheduleRetry()).toBe(true);
    expect(retry.scheduleRetry()).toBe(true);
    await vi.advanceTimersByTimeAsync(IMAGE_RETRY_DELAYS_MS[0]);
    expect(retry.retryAttempt.value).toBe(1);
  });

  it("resetRetry cancels the wait and restores the budget", async () => {
    const retry = useImageRetry();
    retry.scheduleRetry();
    await vi.advanceTimersByTimeAsync(IMAGE_RETRY_DELAYS_MS[0]);
    retry.scheduleRetry();

    retry.resetRetry();
    await vi.advanceTimersByTimeAsync(60_000);

    expect(retry.retryAttempt.value).toBe(0);
    expect(retry.retryPending.value).toBe(false);
    expect(retry.scheduleRetry()).toBe(true);
  });

  it("cancels the pending retry when its scope stops", async () => {
    const scope = effectScope();
    const retry = scope.run(() => useImageRetry())!;
    retry.scheduleRetry();
    expect(vi.getTimerCount()).toBe(1);

    scope.stop();

    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(retry.retryAttempt.value).toBe(0);
  });
});
