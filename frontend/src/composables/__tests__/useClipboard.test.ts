import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useClipboard } from "../useClipboard";
import { useToastStore } from "@/stores/toast";
import { withSetup } from "@/test/withSetup";

describe("useClipboard", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  function mockExecCommand(fn: () => boolean = () => true) {
    const spy = vi.fn(fn);
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      writable: true,
      value: spy,
    });
    return spy;
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

  it("copies via the legacy execCommand fallback and flips copyStatus to true", async () => {
    const execCommandSpy = mockExecCommand();

    const { result } = withSetup(() => useClipboard());
    await result.copyText("hello", "prompt");

    expect(execCommandSpy).toHaveBeenCalledWith("copy");
    expect(result.copyStatus.value.prompt).toBe(true);
  });

  it("shows a success toast with a per-id label after copying", async () => {
    mockExecCommand();

    const { result } = withSetup(() => useClipboard());
    await result.copyText("hello", "prompt");

    const store = useToastStore();
    const toast = store.toasts.find((t) => t.title.startsWith("Prompt"));
    expect(toast).toBeDefined();
    expect(toast?.message).toBe("Copied to clipboard");
  });

  it("uses the 'Negative prompt' label for the neg id", async () => {
    mockExecCommand();

    const { result } = withSetup(() => useClipboard());
    await result.copyText("hello", "neg");

    const store = useToastStore();
    expect(store.toasts.find((t) => t.title.startsWith("Negative prompt"))).toBeDefined();
  });

  it("uses the 'Seed' label for the seed id", async () => {
    mockExecCommand();

    const { result } = withSetup(() => useClipboard());
    await result.copyText("123", "seed");

    const store = useToastStore();
    expect(store.toasts.find((t) => t.title.startsWith("Seed"))).toBeDefined();
  });

  it("uses the 'Path' label for the path id", async () => {
    mockExecCommand();

    const { result } = withSetup(() => useClipboard());
    await result.copyText("/some/path", "path");

    const store = useToastStore();
    expect(store.toasts.find((t) => t.title.startsWith("Path"))).toBeDefined();
  });

  it("uses the generic 'Text' label for unknown ids", async () => {
    mockExecCommand();

    const { result } = withSetup(() => useClipboard());
    await result.copyText("data", "custom-id");

    const store = useToastStore();
    expect(store.toasts.find((t) => t.title.startsWith("Text"))).toBeDefined();
  });

  it("resets copyStatus back to false after 1500ms", async () => {
    mockExecCommand();

    const { result } = withSetup(() => useClipboard());
    await result.copyText("hello", "prompt");
    expect(result.copyStatus.value.prompt).toBe(true);

    vi.advanceTimersByTime(1500);
    expect(result.copyStatus.value.prompt).toBe(false);
  });

  it("falls back to document.execCommand('copy') when clipboard API is unavailable", async () => {
    const originalClipboard = (navigator as { clipboard?: unknown }).clipboard;
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: undefined,
    });
    const execCommandSpy = mockExecCommand();

    const { result } = withSetup(() => useClipboard());
    await result.copyText("fallback", "prompt");

    expect(execCommandSpy).toHaveBeenCalledWith("copy");
    expect(result.copyStatus.value.prompt).toBe(true);

    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: originalClipboard,
    });
  });

  it("shows an error toast when the clipboard fallback also fails", async () => {
    mockExecCommand(() => {
      throw new Error("denied");
    });
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const { result } = withSetup(() => useClipboard());
    await result.copyText("hello", "prompt");

    expect(result.copyStatus.value.prompt).toBeUndefined();
    const store = useToastStore();
    const toast = store.toasts.find((t) => t.title === "Copy failed");
    expect(toast).toBeDefined();
    expect(toast?.message).toBe("Unable to copy to clipboard");
    errorSpy.mockRestore();
  });
});
