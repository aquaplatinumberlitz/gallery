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
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: vi.fn().mockReturnValue(true),
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  function setClipboardWriteText(mockFn: unknown) {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: mockFn },
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
    const writeText = vi.fn().mockResolvedValue(undefined);
    setClipboardWriteText(writeText);
    const { result } = withSetup(() => useClipboard());
    await Promise.resolve();
    await result.copyText("hello", "prompt");
    expect(writeText).toHaveBeenCalledWith("hello");
    expect(result.copyStatus.value.prompt).toBe(true);
  });

  it("falls back to execCommand when clipboard API rejects", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    const execCommand = vi.fn().mockReturnValue(true);
    setClipboardWriteText(writeText);
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: execCommand,
    });
    const { result } = withSetup(() => useClipboard());
    await Promise.resolve();
    await result.copyText("hello", "prompt");
    expect(execCommand).toHaveBeenCalledWith("copy");
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
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    setClipboardWriteText(writeText);
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: vi.fn().mockReturnValue(false),
    });
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { result } = withSetup(() => useClipboard());
    await Promise.resolve();
    await result.copyText("hello", "prompt");
    expect(result.copyStatus.value.prompt).toBeUndefined();
    expect(mocks.mockSonnerError).toHaveBeenCalledWith("Copy failed", expect.any(Object));
    errorSpy.mockRestore();
  });
});
