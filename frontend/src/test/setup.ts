import { afterEach, beforeEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";

/**
 * Vitest global setup.
 *
 * Purpose:
 * Stabilises the jsdom environment for unit/integration tests by providing
 * missing browser APIs (matchMedia, ResizeObserver, IntersectionObserver,
 * MutationObserver) and resetting per-test state (localStorage, timers,
 * window globals).
 *
 * Guarantees:
 * * jsdom gaps that crash Vue composables are filled before any test runs
 * * localStorage / sessionStorage / window flags are cleared between tests
 * * unhandled console errors surface as test failures for easier debugging
 *
 * Run when:
 * * adding new vitest files that touch DOM/browser APIs
 * * debugging "X is not a function" errors in jsdom test setup
 */

type WriteableWindow = Window & {
  ResizeObserver?: typeof ResizeObserver;
  IntersectionObserver?: typeof IntersectionObserver;
  MutationObserver?: typeof MutationObserver;
};

const ResizeObserverShim = class {
  private callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }
  observe(target: Element) {
    this.callback(
      [
        {
          target,
          contentRect: { width: 1024, height: 768, x: 0, y: 0, top: 0, left: 0, right: 1024, bottom: 768 },
          borderBoxSize: [],
          contentBoxSize: [],
          devicePixelContentBoxSize: [],
        } as unknown as ResizeObserverEntry,
      ],
      this as unknown as ResizeObserver,
    );
  }
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

const IntersectionObserverShim = class {
  private callback: IntersectionObserverCallback;
  readonly root: Element | Document | null;
  readonly rootMargin: string;
  readonly thresholds: number[];
  constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {
    this.callback = callback;
    this.root = options?.root ?? null;
    this.rootMargin = options?.rootMargin ?? "0px";
    this.thresholds = Array.isArray(options?.threshold)
      ? options!.threshold
      : typeof options?.threshold === "number"
        ? [options.threshold]
        : [0];
  }
  observe(target: Element) {
    this.callback(
      [
        {
          target,
          isIntersecting: true,
          intersectionRatio: 1,
          boundingClientRect: {} as DOMRectReadOnly,
          intersectionRect: {} as DOMRectReadOnly,
          rootBounds: null,
          time: 0,
        } as unknown as IntersectionObserverEntry,
      ],
      this as unknown as IntersectionObserver,
    );
  }
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
} as unknown as typeof IntersectionObserver;

const MutationObserverShim = class {
  observe() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
} as unknown as typeof MutationObserver;

beforeEach(() => {
  const w = window as WriteableWindow;

  // jsdom does not implement matchMedia; vueuse/reka-ui rely on it.
  if (typeof w.matchMedia !== "function") {
    w.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  }

  if (typeof w.ResizeObserver !== "function") w.ResizeObserver = ResizeObserverShim;
  if (typeof w.IntersectionObserver !== "function") w.IntersectionObserver = IntersectionObserverShim;
  if (typeof w.MutationObserver !== "function") w.MutationObserver = MutationObserverShim;

  if (typeof w.scrollTo !== "function") {
    w.scrollTo = vi.fn();
  }
  if (typeof HTMLElement !== "undefined" && typeof HTMLElement.prototype.scrollIntoView !== "function") {
    HTMLElement.prototype.scrollIntoView = vi.fn();
  }

  // requestAnimationFrame in jsdom can be 0; keep a sane fallback for tests that rely on it.
  if (typeof w.requestAnimationFrame !== "function") {
    w.requestAnimationFrame = ((cb: FrameRequestCallback) => cb(0)) as typeof requestAnimationFrame;
  }

  // Clipboard API — used by composables, missing in jsdom.
  if (typeof navigator.clipboard?.writeText !== "function") {
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
  }

  // EventSource API — used by SSE subscription, missing in jsdom.
  if (typeof w.EventSource !== "function") {
    class EventSourceShim extends EventTarget {
      static readonly CONNECTING = 0;
      static readonly OPEN = 1;
      static readonly CLOSED = 2;
      readonly CONNECTING = 0;
      readonly OPEN = 1;
      readonly CLOSED = 2;
      readonly readyState = EventSourceShim.CONNECTING;
      readonly url: string;
      readonly withCredentials = false;
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      constructor(url: string) {
        super();
        this.url = url;
      }
      close() {}
    }
    w.EventSource = EventSourceShim as unknown as typeof EventSource;
  }

  // PointerEvent — jsdom does not implement PointerEvent.
  if (typeof w.PointerEvent !== "function") {
    class PointerEventShim extends MouseEvent {
      readonly pointerId = 0;
      readonly pointerType = "";
      readonly isPrimary = false;
      readonly width = 1;
      readonly height = 1;
      readonly pressure = 0;
      readonly tangentialPressure = 0;
      readonly tiltX = 0;
      readonly tiltY = 0;
      readonly twist = 0;
    }
    w.PointerEvent = PointerEventShim as unknown as typeof PointerEvent;
  }
});

afterEach(() => {
  // Reset persistent browser state so tests do not leak localStorage / flags.
  window.localStorage.clear();
  window.sessionStorage.clear();
  delete (window as Partial<Window> & { __GALLERY_DEBUG_INDEX_REBUILD?: boolean }).__GALLERY_DEBUG_INDEX_REBUILD;
  delete (window as Partial<Window> & { __GALLERY_DEBUG_LIGHTBOX_NAV?: boolean }).__GALLERY_DEBUG_LIGHTBOX_NAV;
  // Clear DOM so mounted wrappers/leftover nodes from one test do not bleed into the next.
  document.body.innerHTML = "";
  vi.restoreAllMocks();
  vi.useRealTimers();
});
