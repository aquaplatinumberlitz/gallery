import { beforeEach, describe, it, expect, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useToast } from "../useToast";

const mocks = vi.hoisted(() => ({
  mockSonnerSuccess: vi.fn(),
  mockSonnerError: vi.fn(),
  mockSonnerWarning: vi.fn(),
  mockSonnerInfo: vi.fn(),
  mockSonnerDismiss: vi.fn(),
}));

vi.mock("vue-sonner", () => ({
  toast: Object.assign(vi.fn(), {
    success: mocks.mockSonnerSuccess,
    error: mocks.mockSonnerError,
    warning: mocks.mockSonnerWarning,
    info: mocks.mockSonnerInfo,
    dismiss: mocks.mockSonnerDismiss,
  }),
  Toaster: { render: () => null },
}));

describe("useToast composable", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("success() returns an id and creates a sonner success toast", () => {
    const toast = useToast();
    const id = toast.success("Saved", "Done");
    expect(id).toMatch(/^toast-/);
    expect(mocks.mockSonnerSuccess).toHaveBeenCalledWith("Saved", expect.objectContaining({ id, description: "Done" }));
  });

  it("error() returns an id and creates a sonner error toast", () => {
    const toast = useToast();
    const id = toast.error("Boom", "Something broke");
    expect(id).toMatch(/^toast-/);
    expect(mocks.mockSonnerError).toHaveBeenCalledWith(
      "Boom",
      expect.objectContaining({ id, description: "Something broke" }),
    );
  });

  it("warning() returns an id and creates a sonner warning toast", () => {
    const toast = useToast();
    const id = toast.warning("Careful");
    expect(id).toMatch(/^toast-/);
    expect(mocks.mockSonnerWarning).toHaveBeenCalledWith("Careful", expect.objectContaining({ id }));
  });

  it("info() returns an id and creates a sonner info toast", () => {
    const toast = useToast();
    const id = toast.info("FYI");
    expect(id).toMatch(/^toast-/);
    expect(mocks.mockSonnerInfo).toHaveBeenCalledWith("FYI", expect.objectContaining({ id }));
  });

  it("show() adds a toast with the exact options provided", () => {
    const toast = useToast();
    const id = toast.show({ type: "info", title: "Custom" });
    expect(id).toMatch(/^toast-/);
    expect(mocks.mockSonnerInfo).toHaveBeenCalledWith("Custom", expect.objectContaining({ id }));
  });

  it("dismiss() removes the toast with the given id", () => {
    const toast = useToast();
    toast.dismiss("test-id");
  });

  it("clear() calls remove on all active toasts", () => {
    const toast = useToast();
    toast.info("one");
    toast.info("two");
    toast.clear();
  });

  it("promise() shows a loading toast, then a success toast on resolve", async () => {
    const toast = useToast();
    const promise = toast.promise(Promise.resolve("data"), {
      loading: "Saving",
      success: (data) => `Done: ${data}`,
      error: "Failed",
    });
    await expect(promise).resolves.toBe("data");
    expect(mocks.mockSonnerInfo).toHaveBeenCalledWith("Saving", expect.any(Object));
    expect(mocks.mockSonnerSuccess).toHaveBeenCalledWith("Done: data", expect.any(Object));
  });

  it("promise() shows a loading toast, then an error toast on reject, and rethrows", async () => {
    const toast = useToast();
    const promise = toast.promise(Promise.reject(new Error("boom")), {
      loading: "Saving",
      success: "Done",
      error: (err) => `Failed: ${(err as Error).message}`,
    });
    await expect(promise).rejects.toThrow("boom");
    expect(mocks.mockSonnerInfo).toHaveBeenCalledWith("Saving", expect.any(Object));
    expect(mocks.mockSonnerError).toHaveBeenCalledWith("Failed: boom", expect.any(Object));
  });

  describe("duration contract", () => {
    it("success defaults to DEFAULT (4000ms)", () => {
      const toast = useToast();
      toast.success("Saved");
      expect(mocks.mockSonnerSuccess).toHaveBeenCalledWith("Saved", expect.objectContaining({ duration: 4000 }));
    });

    it("error defaults to LONG (4000ms)", () => {
      const toast = useToast();
      toast.error("Failed");
      expect(mocks.mockSonnerError).toHaveBeenCalledWith("Failed", expect.objectContaining({ duration: 4000 }));
    });

    it("warning defaults to MEDIUM (4000ms)", () => {
      const toast = useToast();
      toast.warning("Careful");
      expect(mocks.mockSonnerWarning).toHaveBeenCalledWith("Careful", expect.objectContaining({ duration: 4000 }));
    });

    it("info defaults to DEFAULT (4000ms)", () => {
      const toast = useToast();
      toast.info("Heads up");
      expect(mocks.mockSonnerInfo).toHaveBeenCalledWith("Heads up", expect.objectContaining({ duration: 4000 }));
    });
  });

  it("passes action option through to the toast", () => {
    const toast = useToast();
    const onClick = vi.fn();
    toast.error("Error", "msg", { action: { label: "Retry", onClick } });
    expect(mocks.mockSonnerError).toHaveBeenCalledWith(
      "Error",
      expect.objectContaining({ action: expect.objectContaining({ label: "Retry" }) }),
    );
  });

  it("passes dismissible option through to the toast", () => {
    const toast = useToast();
    toast.info("Sticky", undefined, { dismissible: false });
    expect(mocks.mockSonnerInfo).toHaveBeenCalledWith("Sticky", expect.objectContaining({ dismissible: false }));
  });

  it("allows caller to override the default duration per variant", () => {
    const toast = useToast();
    toast.success("Quick", undefined, { duration: 3000 });
    expect(mocks.mockSonnerSuccess).toHaveBeenCalledWith("Quick", expect.objectContaining({ duration: 3000 }));
  });

  it("show() accepts a full ToastOptions object", () => {
    const toast = useToast();
    const onClick = vi.fn();
    const id = toast.show({
      type: "warning",
      title: "Custom",
      message: "Custom message",
      duration: 5000,
      action: { label: "Undo", onClick },
      dismissible: false,
    });
    expect(id).toMatch(/^toast-/);
    expect(mocks.mockSonnerWarning).toHaveBeenCalledWith(
      "Custom",
      expect.objectContaining({
        description: "Custom message",
        duration: 5000,
        action: expect.objectContaining({ label: "Undo" }),
        dismissible: false,
      }),
    );
  });
});
