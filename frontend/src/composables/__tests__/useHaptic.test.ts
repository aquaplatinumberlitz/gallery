import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { useHaptic } from "../useHaptic";

describe("useHaptic", () => {
  let vibrateSpy: ReturnType<typeof vi.fn>;
  const originalVibrate = navigator.vibrate;

  beforeEach(() => {
    vibrateSpy = vi.fn();
    Object.defineProperty(navigator, "vibrate", {
      configurable: true,
      writable: true,
      value: vibrateSpy,
    });
  });

  afterEach(() => {
    Object.defineProperty(navigator, "vibrate", {
      configurable: true,
      writable: true,
      value: originalVibrate,
    });
  });

  it("reports canVibrate=true when navigator.vibrate is a function", () => {
    const haptic = useHaptic();
    expect(haptic.canVibrate).toBe(true);
  });

  it("light() calls navigator.vibrate(10)", () => {
    const haptic = useHaptic();
    haptic.light();
    expect(vibrateSpy).toHaveBeenCalledWith(10);
  });

  it("medium() calls navigator.vibrate(20)", () => {
    const haptic = useHaptic();
    haptic.medium();
    expect(vibrateSpy).toHaveBeenCalledWith(20);
  });

  it("does not throw when navigator.vibrate is unavailable", () => {
    Object.defineProperty(navigator, "vibrate", {
      configurable: true,
      writable: true,
      value: undefined,
    });
    const haptic = useHaptic();
    expect(haptic.canVibrate).toBe(false);
    expect(() => haptic.light()).not.toThrow();
    expect(() => haptic.medium()).not.toThrow();
  });
});
