import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useClipboard } from "../useClipboard";
import { withSetup } from "@/test/withSetup";

const mocks = vi.hoisted(() => ({
  mockSonnerSuccess: vi.fn(),
  mockSonnerError: vi.fn(),
}));

vi.mock("vue-sonner", () => ({
  toast: Object.assign(vi.fn(), {
    success: mocks.mockSonnerSuccess,
    error: mocks.mockSonnerError,
    warning: vi.fn(),
    info: vi.fn(),
    dismiss: vi.fn(),
  }),
  Toaster: { render: () => null },
}));

describe("useClipboard", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.useFakeTimers();
    vi.clearAllMocks();

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

    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { write: vi.fn().mockResolvedValue(undefined) },
    });

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
    expect(mocks.mockSonnerSuccess).toHaveBeenCalledWith(expect.stringMatching(/^Prompt/), expect.any(Object));
  });

  it("uses the 'Negative prompt' label for the neg id", async () => {
    const { result } = withSetup(() => useClipboard());
    await Promise.resolve();
    await result.copyText("hello", "neg");
    expect(mocks.mockSonnerSuccess).toHaveBeenCalledWith(expect.stringMatching(/^Negative prompt/), expect.any(Object));
  });

  it("uses the 'Seed' label for the seed id", async () => {
    const { result } = withSetup(() => useClipboard());
    await Promise.resolve();
    await result.copyText("123", "seed");
    expect(mocks.mockSonnerSuccess).toHaveBeenCalledWith(expect.stringMatching(/^Seed/), expect.any(Object));
  });

  it("uses the 'Path' label for the path id", async () => {
    const { result } = withSetup(() => useClipboard());
    await Promise.resolve();
    await result.copyText("/some/path", "path");
    expect(mocks.mockSonnerSuccess).toHaveBeenCalledWith(expect.stringMatching(/^Path/), expect.any(Object));
  });

  it("uses the generic 'Text' label for unknown ids", async () => {
    const { result } = withSetup(() => useClipboard());
    await Promise.resolve();
    await result.copyText("data", "custom-id");
    expect(mocks.mockSonnerSuccess).toHaveBeenCalledWith(expect.stringMatching(/^Text/), expect.any(Object));
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
    expect(mocks.mockSonnerError).toHaveBeenCalledWith("Copy failed", expect.any(Object));
    errorSpy.mockRestore();
  });
});
