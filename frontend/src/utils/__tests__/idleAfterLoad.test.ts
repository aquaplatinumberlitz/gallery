import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { whenBrowserIdleAfterLoad } from "../idleAfterLoad";

function setReadyState(state: DocumentReadyState) {
  Object.defineProperty(document, "readyState", { configurable: true, get: () => state });
}

describe("whenBrowserIdleAfterLoad", () => {
  let idleCallbacks: IdleRequestCallback[];

  beforeEach(() => {
    vi.useFakeTimers();
    idleCallbacks = [];
    vi.stubGlobal(
      "requestIdleCallback",
      vi.fn((callback: IdleRequestCallback) => {
        idleCallbacks.push(callback);
        return idleCallbacks.length;
      }),
    );
    vi.stubGlobal("cancelIdleCallback", vi.fn());
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    setReadyState("complete");
  });

  const flushIdle = () => idleCallbacks.splice(0).forEach((callback) => callback({} as IdleDeadline));

  it("waits for the load event, the settle delay and an idle period", () => {
    setReadyState("loading");
    const callback = vi.fn();
    whenBrowserIdleAfterLoad(callback, 1500);

    vi.advanceTimersByTime(5000);
    flushIdle();
    expect(callback).not.toHaveBeenCalled();

    window.dispatchEvent(new Event("load"));
    vi.advanceTimersByTime(1499);
    flushIdle();
    expect(callback).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(callback).not.toHaveBeenCalled();
    flushIdle();
    expect(callback).toHaveBeenCalledTimes(1);
  });

  it("starts the settle delay immediately when the page has already loaded", () => {
    setReadyState("complete");
    const callback = vi.fn();
    whenBrowserIdleAfterLoad(callback, 100);

    vi.advanceTimersByTime(100);
    flushIdle();
    expect(callback).toHaveBeenCalledTimes(1);
  });

  it("falls back to a timeout where requestIdleCallback is unavailable", () => {
    vi.stubGlobal("requestIdleCallback", undefined);
    setReadyState("complete");
    const callback = vi.fn();
    whenBrowserIdleAfterLoad(callback, 100);

    vi.advanceTimersByTime(299);
    expect(callback).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(callback).toHaveBeenCalledTimes(1);
  });

  it("never runs the callback once cancelled", () => {
    setReadyState("loading");
    const callback = vi.fn();
    const cancel = whenBrowserIdleAfterLoad(callback, 100);

    cancel();
    window.dispatchEvent(new Event("load"));
    vi.advanceTimersByTime(1000);
    flushIdle();
    expect(callback).not.toHaveBeenCalled();
  });
});
