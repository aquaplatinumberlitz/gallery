import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import { nextTick, ref } from "vue";
import { useDelayedBoolean } from "../useDelayedBoolean";
import { withSetup } from "@/test/withSetup";

describe("useDelayedBoolean", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns false initially when the source is false", () => {
    const { result } = withSetup(() => useDelayedBoolean(ref(false), 250));
    expect(result.value).toBe(false);
  });

  it("returns false immediately when the source becomes true, then true after the delay", async () => {
    const source = ref(false);
    const { result } = withSetup(() => useDelayedBoolean(source, 250));
    source.value = true;
    await nextTick();
    expect(result.value).toBe(false);
    vi.advanceTimersByTime(249);
    expect(result.value).toBe(false);
    vi.advanceTimersByTime(1);
    expect(result.value).toBe(true);
  });

  it("respects the default delay of 250ms when no delay is provided", async () => {
    const source = ref(false);
    const { result } = withSetup(() => useDelayedBoolean(source));
    source.value = true;
    await nextTick();
    expect(result.value).toBe(false);
    vi.advanceTimersByTime(249);
    expect(result.value).toBe(false);
    vi.advanceTimersByTime(1);
    expect(result.value).toBe(true);
  });

  it("immediately sets true when the source starts true (immediate watch)", async () => {
    const source = ref(true);
    const { result } = withSetup(() => useDelayedBoolean(source, 100));
    // The watch is immediate; the timer starts at setup time.
    expect(result.value).toBe(false);
    vi.advanceTimersByTime(100);
    expect(result.value).toBe(true);
  });

  it("immediately sets false when the source becomes false, cancelling any pending timer", async () => {
    const source = ref(false);
    const { result } = withSetup(() => useDelayedBoolean(source, 250));
    source.value = true;
    await nextTick();
    vi.advanceTimersByTime(100);
    expect(result.value).toBe(false);
    source.value = false;
    await nextTick();
    expect(result.value).toBe(false);
    // Even after the original delay elapses, the result stays false because
    // the timer was cancelled when the source flipped to false.
    vi.advanceTimersByTime(250);
    expect(result.value).toBe(false);
  });

  it("reschedules the timer when the source flips true -> false -> true before firing", async () => {
    const source = ref(false);
    const { result } = withSetup(() => useDelayedBoolean(source, 250));
    source.value = true;
    await nextTick();
    vi.advanceTimersByTime(100);
    source.value = false;
    await nextTick();
    vi.advanceTimersByTime(50);
    source.value = true;
    await nextTick();
    vi.advanceTimersByTime(100);
    // Only 100ms since the last true; should still be false.
    expect(result.value).toBe(false);
    vi.advanceTimersByTime(150);
    expect(result.value).toBe(true);
  });

  it("cancels pending timers on unmount", async () => {
    const source = ref(false);
    const { result, wrapper } = withSetup(() => useDelayedBoolean(source, 250));
    source.value = true;
    await nextTick();
    vi.advanceTimersByTime(100);
    wrapper.unmount();
    // After unmount, advancing timers should not affect the delayed ref
    // (no longer subscribed) and should not throw.
    vi.advanceTimersByTime(500);
    expect(result.value).toBe(false);
  });
});
