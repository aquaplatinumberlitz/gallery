import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useClipboard } from "../useClipboard";
import { useToastStore } from "@/stores/toast";
import { withSetup } from "@/test/withSetup";

describe("useClipboard", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.useFakeTimers();

    // VueUse useClipboard checks navigator.permissions.query("clipboard-write").
    // jsdom lacks Permissions API — stub it so VueUse uses the modern path.
    Object.defineProperty(navigator, "permissions", {
      configurable: true,
      value: {
        query: vi.fn().mockResolvedValue({
          state: "granted",
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
        }),
      },
    });

    // VueUse useClipboard (non-legacy) calls navigator.clipboard.write([ClipboardItem]).
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { write: vi.fn().mockResolvedValue(undefined) },
    });

    // ClipboardItem constructor needed by VueUse's createClipboardItem.
    globalThis.ClipboardItem = class {
      types: string[];
      items = {} as Record<string, string>;
      constructor(items: Record<string, string>) {
        this.items = items;
        this.types = Object.keys(items);
      }
    } as unknown as typeof ClipboardItem;
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    delete (globalThis as Record<string, unknown>).ClipboardItem;
  });

  function setClipboardWrite(mockFn: unknown) {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { write: mockFn },
    });
  }

  it("does nothing when text is undefined", async () => {
    const { result } = withSetup(() => useClipboard());
    await result.copyText(undefined, "prompt");
    expect(result.copyStatus.value).toEqual({});
  });

  it("does nothing when text is empty", async () => {
    const { result } = withSetup(() => useClipboard());
    await result.copyText("", "prompt");
    expect(result.copyStatus.value).toEqual({});
  });

  it("copies via clipboard API and flips copyStatus to true", async () => {
    const write = vi.fn().mockResolvedValue(undefined);
    setClipboardWrite(write);
    const { result } = withSetup(() => useClipboard());
    await Promise.resolve();
    await result.copyText("hello", "prompt");
    expect(write).toHaveBeenCalledWith(expect.arrayContaining([expect.any(globalThis.ClipboardItem)]));
    expect(result.copyStatus.value.prompt).toBe(true);
  });

  it("shows a success toast with a per-id label after copying", async () => {
    const { result } = withSetup(() => useClipboard());
    await Promise.resolve();
    await result.copyText("hello", "prompt");
    const store = useToastStore();
    const toast = store.toasts.find((t) => t.title.startsWith("Prompt"));
    expect(toast).toBeDefined();
    expect(toast?.message).toBe("Copied to clipboard");
  });

  it("uses the 'Negative prompt' label for the neg id", async () => {
    const { result } = withSetup(() => useClipboard());
    await Promise.resolve();
    await result.copyText("hello", "neg");
    const store = useToastStore();
    expect(store.toasts.find((t) => t.title.startsWith("Negative prompt"))).toBeDefined();
  });

  it("uses the 'Seed' label for the seed id", async () => {
    const { result } = withSetup(() => useClipboard());
    await Promise.resolve();
    await result.copyText("123", "seed");
    const store = useToastStore();
    expect(store.toasts.find((t) => t.title.startsWith("Seed"))).toBeDefined();
  });

  it("uses the 'Path' label for the path id", async () => {
    const { result } = withSetup(() => useClipboard());
    await Promise.resolve();
    await result.copyText("/some/path", "path");
    const store = useToastStore();
    expect(store.toasts.find((t) => t.title.startsWith("Path"))).toBeDefined();
  });

  it("uses the generic 'Text' label for unknown ids", async () => {
    const { result } = withSetup(() => useClipboard());
    await Promise.resolve();
    await result.copyText("data", "custom-id");
    const store = useToastStore();
    expect(store.toasts.find((t) => t.title.startsWith("Text"))).toBeDefined();
  });

  it("resets copyStatus back to false after 1500ms", async () => {
    const { result } = withSetup(() => useClipboard());
    await Promise.resolve();
    await result.copyText("hello", "prompt");
    expect(result.copyStatus.value.prompt).toBe(true);
    vi.advanceTimersByTime(1500);
    expect(result.copyStatus.value.prompt).toBe(false);
  });

  it("shows an error toast when the clipboard API call fails", async () => {
    const write = vi.fn().mockRejectedValue(new Error("denied"));
    setClipboardWrite(write);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { result } = withSetup(() => useClipboard());
    await Promise.resolve();
    await result.copyText("hello", "prompt");
    expect(result.copyStatus.value.prompt).toBeUndefined();
    const store = useToastStore();
    const toast = store.toasts.find((t) => t.title === "Copy failed");
    expect(toast).toBeDefined();
    expect(toast?.message).toBe("Unable to copy to clipboard");
    errorSpy.mockRestore();
  });
});
