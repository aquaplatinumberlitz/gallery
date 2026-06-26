import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import { nextTick } from "vue";
import { useGalleryTheme } from "../useGalleryTheme";
import { withSetup } from "@/test/withSetup";

const originalMatchMedia = window.matchMedia;
const originalLocalStorage = window.localStorage;

describe("useGalleryTheme", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // jsdom doesn't implement matchMedia; the setup file provides a stub but
    // we want predictable prefers-reduced-motion behavior here.
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    window.localStorage.clear();
  });

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
    // localStorage is replaced via spies in some tests; restore the original.
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: originalLocalStorage,
    });
    vi.advanceTimersByTime(200);
    vi.useRealTimers();
  });

  it("defaults to 'system' mode and a resolved theme driven by vueuse", async () => {
    const { result } = withSetup(() => useGalleryTheme());
    // vueuse reads the storageKey; with an empty localStorage it falls back to
    // 'auto' which our wrapper maps to 'system'.
    expect(result.mode.value).toBe("system");
  });

  it("setTheme('dark') updates the mode and persists under the gallery-theme key", async () => {
    const { result } = withSetup(() => useGalleryTheme());
    result.setTheme("dark");
    await nextTick();
    expect(result.mode.value).toBe("dark");
    expect(window.localStorage.getItem("gallery-theme")).toBe("dark");
  });

  it("setTheme('light') updates the mode and persists", async () => {
    const { result } = withSetup(() => useGalleryTheme());
    result.setTheme("light");
    await nextTick();
    expect(result.mode.value).toBe("light");
    expect(window.localStorage.getItem("gallery-theme")).toBe("light");
  });

  it("setTheme('system') maps to 'auto' in the underlying color mode store", async () => {
    const { result } = withSetup(() => useGalleryTheme());
    result.setTheme("dark");
    await nextTick();
    result.setTheme("system");
    await nextTick();
    expect(result.mode.value).toBe("system");
    expect(window.localStorage.getItem("gallery-theme")).toBe("auto");
  });

  it("toggleTheme flips between light and dark and persists the new value", async () => {
    const { result } = withSetup(() => useGalleryTheme());
    result.setTheme("light");
    await nextTick();
    result.toggleTheme();
    await nextTick();
    expect(result.mode.value).toBe("dark");
    expect(window.localStorage.getItem("gallery-theme")).toBe("dark");
    result.toggleTheme();
    await nextTick();
    expect(result.mode.value).toBe("light");
  });

  it("cycleTheme advances light -> dark -> system -> light", async () => {
    const { result } = withSetup(() => useGalleryTheme());
    result.setTheme("light");
    await nextTick();
    result.cycleTheme();
    expect(result.mode.value).toBe("dark");
    result.cycleTheme();
    expect(result.mode.value).toBe("system");
    result.cycleTheme();
    expect(result.mode.value).toBe("light");
  });

  it("isDark reflects the resolved theme", async () => {
    const { result } = withSetup(() => useGalleryTheme());
    result.setTheme("dark");
    await nextTick();
    expect(result.isDark.value).toBe(true);
    result.setTheme("light");
    await nextTick();
    expect(result.isDark.value).toBe(false);
  });

  it("uses document.startViewTransition when available (no reduced motion)", async () => {
    const startViewTransition = vi.fn((cb: () => void) => {
      cb();
      return { finished: Promise.resolve() };
    });
    Object.defineProperty(document, "startViewTransition", {
      configurable: true,
      writable: true,
      value: startViewTransition,
    });
    const { result } = withSetup(() => useGalleryTheme());
    result.setTheme("dark");
    await nextTick();
    expect(startViewTransition).toHaveBeenCalledTimes(1);
    expect(window.localStorage.getItem("gallery-theme")).toBe("dark");
    delete (document as Partial<Document> & { startViewTransition?: unknown }).startViewTransition;
  });

  it("skips the view transition when prefers-reduced-motion: reduce matches", async () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("reduce"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    const startViewTransition = vi.fn();
    Object.defineProperty(document, "startViewTransition", {
      configurable: true,
      writable: true,
      value: startViewTransition,
    });
    const { result } = withSetup(() => useGalleryTheme());
    result.setTheme("dark");
    await nextTick();
    expect(startViewTransition).not.toHaveBeenCalled();
    expect(window.localStorage.getItem("gallery-theme")).toBe("dark");
    delete (document as Partial<Document> & { startViewTransition?: unknown }).startViewTransition;
  });

  it("falls back to the theme-transitioning class when startViewTransition is unavailable", async () => {
    // jsdom does not provide startViewTransition; the applyWithTransition helper
    // should synchronously add the .theme-transitioning class. afterEach drains
    // the setTimeout(200ms) so it never fires after jsdom cleanup.
    const { result } = withSetup(() => useGalleryTheme());
    result.setTheme("dark");
    await nextTick();
    expect(document.documentElement.classList.contains("theme-transitioning")).toBe(true);
    expect(window.localStorage.getItem("gallery-theme")).toBe("dark");
  });
});
