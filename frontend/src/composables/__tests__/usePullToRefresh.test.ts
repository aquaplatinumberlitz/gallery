import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import { usePullToRefresh, type PullToRefreshOptions } from "../usePullToRefresh";
import { withSetup } from "@/test/withSetup";

function makeTouchEvent(
  target: EventTarget | null,
  clientX: number,
  clientY: number,
  extra: Partial<{ touches: Array<{ clientX: number; clientY: number }>; target: EventTarget | null }> = {},
): TouchEvent {
  return {
    target,
    touches: extra.touches ?? [{ clientX, clientY }],
  } as unknown as TouchEvent;
}

function installScroller(scrollTop: number) {
  const scroller = document.createElement("div");
  scroller.className = "scroller";
  Object.defineProperty(scroller, "scrollTop", {
    configurable: true,
    get: () => scrollTop,
    set: () => {},
  });
  document.body.appendChild(scroller);
  return scroller;
}

describe("usePullToRefresh", () => {
  let vibrateSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vibrateSpy = vi.fn();
    Object.defineProperty(navigator, "vibrate", {
      configurable: true,
      writable: true,
      value: vibrateSpy,
    });
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  function setupPullToRefresh(options: PullToRefreshOptions) {
    return withSetup(() => usePullToRefresh(options));
  }

  it("starts at rest with zero pull distance and no pulling", () => {
    const { result } = setupPullToRefresh({ onRefresh: vi.fn().mockResolvedValue(undefined) });
    expect(result.pullDistance.value).toBe(0);
    expect(result.isPulling.value).toBe(false);
    expect(result.isRefreshing.value).toBe(false);
    expect(result.pullProgress.value).toBe(0);
    expect(result.pullTransform.value).toBe("translateY(0px)");
    expect(result.pullOpacity.value).toBe(0);
    expect(result.showPullIndicator.value).toBe(false);
  });

  it("does not start pulling when canStart returns false (e.g. scrollTop > 5)", () => {
    installScroller(50);
    const { result } = setupPullToRefresh({ onRefresh: vi.fn().mockResolvedValue(undefined) });
    result.onTouchStart(makeTouchEvent(null, 100, 200));
    expect(result.isPulling.value).toBe(false);
  });

  it("does not start pulling while a refresh is in progress", () => {
    installScroller(0);
    let resolveRefresh: () => void = () => {};
    const onRefresh = vi.fn(
      () => new Promise<void>((resolve) => {
        resolveRefresh = resolve;
      }),
    );
    const { result } = setupPullToRefresh({ onRefresh });
    result.onTouchStart(makeTouchEvent(null, 100, 200));
    expect(result.isPulling.value).toBe(true);

    // Drive the gesture to completion to start the refresh.
    // deltaY=200 -> pullDistance = min(100, 120) = 100 >= threshold (80).
    result.onTouchMove(makeTouchEvent(null, 100, 400));
    result.onTouchEnd();
    expect(result.isRefreshing.value).toBe(true);

    // A new touch during refresh should be ignored.
    result.onTouchStart(makeTouchEvent(null, 100, 200));
    expect(result.isPulling.value).toBe(false);

    resolveRefresh();
  });

  it("locks to horizontal when deltaX exceeds deltaY and resets pull state", () => {
    installScroller(0);
    const { result } = setupPullToRefresh({
      onRefresh: vi.fn().mockResolvedValue(undefined),
      axisLockThreshold: 8,
    });
    result.onTouchStart(makeTouchEvent(null, 100, 200));
    result.onTouchMove(makeTouchEvent(null, 150, 205)); // big X delta, small Y delta
    expect(result.isPulling.value).toBe(false);
    expect(result.pullDistance.value).toBe(0);
  });

  it("accumulates pull distance (capped at maxDistance) on downward vertical moves", () => {
    installScroller(0);
    const { result } = setupPullToRefresh({
      onRefresh: vi.fn().mockResolvedValue(undefined),
      maxDistance: 120,
    });
    result.onTouchStart(makeTouchEvent(null, 100, 200));
    result.onTouchMove(makeTouchEvent(null, 100, 400)); // 200px delta
    // pullDistance = min(deltaY * 0.5, maxDistance) = min(100, 120) = 100
    expect(result.pullDistance.value).toBe(100);
    result.onTouchMove(makeTouchEvent(null, 100, 600)); // 400px delta
    expect(result.pullDistance.value).toBe(120);
  });

  it("resets pullDistance to 0 when the user drags back upward (deltaY <= 0)", () => {
    installScroller(0);
    const { result } = setupPullToRefresh({ onRefresh: vi.fn().mockResolvedValue(undefined) });
    result.onTouchStart(makeTouchEvent(null, 100, 200));
    result.onTouchMove(makeTouchEvent(null, 100, 400));
    expect(result.pullDistance.value).toBe(100);
    result.onTouchMove(makeTouchEvent(null, 100, 100)); // deltaY = -100
    expect(result.pullDistance.value).toBe(0);
  });

  it("does not move if onTouchMove is called without onTouchStart (not pulling)", () => {
    installScroller(0);
    const { result } = setupPullToRefresh({ onRefresh: vi.fn().mockResolvedValue(undefined) });
    result.onTouchMove(makeTouchEvent(null, 100, 400));
    expect(result.pullDistance.value).toBe(0);
  });

  it("onTouchEnd resets pull state when below the threshold (no refresh)", () => {
    installScroller(0);
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    const { result } = setupPullToRefresh({ onRefresh, threshold: 80 });
    result.onTouchStart(makeTouchEvent(null, 100, 200));
    result.onTouchMove(makeTouchEvent(null, 100, 250)); // 25px delta -> 12.5 pull
    result.onTouchEnd();
    expect(onRefresh).not.toHaveBeenCalled();
    expect(result.isRefreshing.value).toBe(false);
    expect(result.pullDistance.value).toBe(0);
    expect(result.isPulling.value).toBe(false);
  });

  it("onTouchEnd triggers onRefresh when the pull exceeds the threshold", async () => {
    installScroller(0);
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    const { result } = setupPullToRefresh({ onRefresh, threshold: 80 });
    result.onTouchStart(makeTouchEvent(null, 100, 200));
    result.onTouchMove(makeTouchEvent(null, 100, 400)); // 200px -> 100 pull (>= threshold)
    result.onTouchEnd();
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(result.isRefreshing.value).toBe(true);
    expect(vibrateSpy).toHaveBeenCalledWith(20);
    // Wait for the onRefresh promise to settle so isRefreshing flips back.
    await vi.waitFor(() => {
      expect(result.isRefreshing.value).toBe(false);
    });
    expect(result.pullDistance.value).toBe(0);
  });

  it("onTouchEnd triggers haptic feedback (medium) when threshold is exceeded", () => {
    installScroller(0);
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    const { result } = setupPullToRefresh({ onRefresh, threshold: 80 });
    result.onTouchStart(makeTouchEvent(null, 100, 200));
    result.onTouchMove(makeTouchEvent(null, 100, 400));
    vibrateSpy.mockClear();
    result.onTouchEnd();
    expect(vibrateSpy).toHaveBeenCalledWith(20);
  });

  it("onTouchEnd is a no-op when not pulling", () => {
    installScroller(0);
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    const { result } = setupPullToRefresh({ onRefresh });
    result.onTouchEnd();
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it("still clears isRefreshing when onRefresh rejects (local cleanup)", async () => {
    installScroller(0);
    const onRefresh = vi.fn().mockRejectedValue(new Error("refresh failed"));
    const { result } = setupPullToRefresh({ onRefresh, threshold: 80 });
    result.onTouchStart(makeTouchEvent(null, 100, 200));
    result.onTouchMove(makeTouchEvent(null, 100, 400));
    result.onTouchEnd();
    await vi.waitFor(() => {
      expect(result.isRefreshing.value).toBe(false);
    });
    expect(result.pullDistance.value).toBe(0);
  });

  it("showPullIndicator becomes true when pullDistance > 10", () => {
    installScroller(0);
    const { result } = setupPullToRefresh({ onRefresh: vi.fn().mockResolvedValue(undefined) });
    result.onTouchStart(makeTouchEvent(null, 100, 200));
    // deltaY=15 -> pullDistance = 7.5 (< 10) -> indicator hidden
    result.onTouchMove(makeTouchEvent(null, 100, 215));
    expect(result.showPullIndicator.value).toBe(false);
    // deltaY=30 -> pullDistance = 15 (> 10) -> indicator shown
    result.onTouchMove(makeTouchEvent(null, 100, 230));
    expect(result.showPullIndicator.value).toBe(true);
  });

  it("showPullIndicator is true while a refresh is in progress even at zero distance", async () => {
    installScroller(0);
    let resolveRefresh: () => void = () => {};
    const onRefresh = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveRefresh = resolve;
        }),
    );
    const { result } = setupPullToRefresh({ onRefresh, threshold: 80 });
    result.onTouchStart(makeTouchEvent(null, 100, 200));
    result.onTouchMove(makeTouchEvent(null, 100, 400));
    result.onTouchEnd();
    expect(result.showPullIndicator.value).toBe(true);
    resolveRefresh();
    await vi.waitFor(() => {
      expect(result.showPullIndicator.value).toBe(false);
    });
  });

  it("pullProgress caps at 1 when pullDistance exceeds threshold", () => {
    installScroller(0);
    const { result } = setupPullToRefresh({
      onRefresh: vi.fn().mockResolvedValue(undefined),
      threshold: 80,
    });
    result.onTouchStart(makeTouchEvent(null, 100, 200));
    result.onTouchMove(makeTouchEvent(null, 100, 500)); // 300px -> 150 pull
    expect(result.pullProgress.value).toBe(1);
  });

  it("pullOpacity caps at 1 when pullDistance exceeds half the threshold", () => {
    installScroller(0);
    const { result } = setupPullToRefresh({
      onRefresh: vi.fn().mockResolvedValue(undefined),
      threshold: 80,
    });
    result.onTouchStart(makeTouchEvent(null, 100, 200));
    result.onTouchMove(makeTouchEvent(null, 100, 500)); // 150 pull -> 150/40 = 3.75 capped to 1
    expect(result.pullOpacity.value).toBe(1);
  });

  it("pullTransform translates by min(pullDistance, maxDistance) px", () => {
    installScroller(0);
    const { result } = setupPullToRefresh({
      onRefresh: vi.fn().mockResolvedValue(undefined),
      maxDistance: 120,
    });
    result.onTouchStart(makeTouchEvent(null, 100, 200));
    result.onTouchMove(makeTouchEvent(null, 100, 400)); // pullDistance = 100
    expect(result.pullTransform.value).toBe("translateY(100px)");
  });

  it("respects a custom canStart callback that returns false", () => {
    installScroller(0);
    const canStart = vi.fn(() => false);
    const { result } = setupPullToRefresh({ onRefresh: vi.fn().mockResolvedValue(undefined), canStart });
    result.onTouchStart(makeTouchEvent(null, 100, 200));
    expect(canStart).toHaveBeenCalled();
    expect(result.isPulling.value).toBe(false);
  });

  it("does not start when the touch target is a horizontal scroll container (.album-grid)", () => {
    installScroller(0);
    const grid = document.createElement("div");
    grid.className = "album-grid";
    document.body.appendChild(grid);
    const { result } = setupPullToRefresh({ onRefresh: vi.fn().mockResolvedValue(undefined) });
    result.onTouchStart(makeTouchEvent(grid, 100, 200));
    expect(result.isPulling.value).toBe(false);
  });
});
