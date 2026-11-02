/**
 * Purpose: Protect the bounded wait main.ts puts on the library list before the first mount.
 * Guarantees: Resolves as soon as the promise fulfils or rejects, resolves at the time limit when it stays pending
 * (so a slow or hung list never blocks the mount for longer than the limit), never rejects, and leaves no timer behind.
 * Run when: Changing the start-up sequence in main.ts or this helper.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { settleWithin } from "../settleWithin";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("settleWithin", () => {
  it("resolves when the promise fulfils before the limit, without waiting for the timer", async () => {
    let settled = false;
    const done = settleWithin(Promise.resolve("libraries"), 300).then(() => (settled = true));
    await vi.advanceTimersByTimeAsync(0);
    await done;
    expect(settled).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("resolves when the promise rejects (never rejects itself)", async () => {
    await expect(settleWithin(Promise.reject(new Error("offline")), 300)).resolves.toBeUndefined();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("resolves at the limit when the promise stays pending", async () => {
    let settled = false;
    void settleWithin(new Promise(() => {}), 300).then(() => (settled = true));
    await vi.advanceTimersByTimeAsync(299);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    expect(settled).toBe(true);
  });
});
