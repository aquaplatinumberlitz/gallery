import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useToastStore } from "../toast";

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

describe("useToastStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("exposes the standard duration constants on the store instance", () => {
    const store = useToastStore();
    expect(store.DURATION.SHORT).toBe(3000);
    expect(store.DURATION.DEFAULT).toBe(4000);
    expect(store.DURATION.MEDIUM).toBe(6000);
    expect(store.DURATION.LONG).toBe(10000);
  });

  describe("addToast", () => {
    it("adds a toast with sensible defaults and returns its id", () => {
      const store = useToastStore();
      const id = store.addToast({ title: "Hello" });
      expect(id).toMatch(/^toast-\d+-[a-z0-9]+$/);
      expect(mocks.mockSonnerInfo).toHaveBeenCalledWith("Hello", expect.objectContaining({ id }));
    });

    it("defaults type to info", () => {
      const store = useToastStore();
      store.addToast({ title: "Hello" });
      expect(mocks.mockSonnerInfo).toHaveBeenCalled();
    });

    it("respects explicit type and calls the correct sonner method", () => {
      const store = useToastStore();
      store.addToast({ type: "success", title: "Saved" });
      expect(mocks.mockSonnerSuccess).toHaveBeenCalledWith("Saved", expect.any(Object));
    });

    it("respects explicit type error and calls sonner error", () => {
      const store = useToastStore();
      store.addToast({ type: "error", title: "Boom" });
      expect(mocks.mockSonnerError).toHaveBeenCalledWith("Boom", expect.any(Object));
    });

    it("respects explicit type warning and calls sonner warning", () => {
      const store = useToastStore();
      store.addToast({ type: "warning", title: "Careful" });
      expect(mocks.mockSonnerWarning).toHaveBeenCalledWith("Careful", expect.any(Object));
    });

    it("passes message as description to sonner", () => {
      const store = useToastStore();
      store.addToast({ title: "Hello", message: "World" });
      expect(mocks.mockSonnerInfo).toHaveBeenCalledWith("Hello", expect.objectContaining({ description: "World" }));
    });

    it("passes duration to sonner", () => {
      const store = useToastStore();
      store.addToast({ title: "Hello", duration: 5000 });
      expect(mocks.mockSonnerInfo).toHaveBeenCalledWith("Hello", expect.objectContaining({ duration: 5000 }));
    });

    it("maps duration 0 (persistent) to Infinity for sonner", () => {
      const store = useToastStore();
      store.addToast({ title: "Persistent", duration: 0 });
      expect(mocks.mockSonnerInfo).toHaveBeenCalledWith("Persistent", expect.objectContaining({ duration: Infinity }));
    });

    it("passes dismissible option to sonner", () => {
      const store = useToastStore();
      store.addToast({ title: "Sticky", dismissible: false });
      expect(mocks.mockSonnerInfo).toHaveBeenCalledWith("Sticky", expect.objectContaining({ dismissible: false }));
    });

    it("passes action option to sonner", () => {
      const store = useToastStore();
      const onClick = vi.fn();
      store.addToast({ title: "Error", action: { label: "Retry", onClick } });
      expect(mocks.mockSonnerInfo).toHaveBeenCalledWith(
        "Error",
        expect.objectContaining({
          action: expect.objectContaining({ label: "Retry" }),
        }),
      );
    });

    it("generates unique ids for repeated calls", () => {
      const store = useToastStore();
      const ids = new Set<string>();
      for (let i = 0; i < 5; i++) {
        ids.add(store.addToast({ title: `t${i}` }));
      }
      expect(ids.size).toBe(5);
    });
  });

  describe("removeToast", () => {
    it("removes the toast with the given id via sonner dismiss", () => {
      const store = useToastStore();
      store.removeToast("test-id");
      expect(mocks.mockSonnerDismiss).toHaveBeenCalledWith("test-id");
    });
  });

  describe("clearAll", () => {
    it("dismisses all active toasts", () => {
      const store = useToastStore();
      const id1 = store.addToast({ title: "one" });
      const id2 = store.addToast({ title: "two" });
      store.clearAll();
      expect(mocks.mockSonnerDismiss).toHaveBeenCalledWith(id1);
      expect(mocks.mockSonnerDismiss).toHaveBeenCalledWith(id2);
    });
  });

  describe("convenience helpers", () => {
    it("success() adds a toast with type=success and default duration", () => {
      const store = useToastStore();
      const id = store.success("Saved", "Done");
      expect(mocks.mockSonnerSuccess).toHaveBeenCalledWith(
        "Saved",
        expect.objectContaining({ id, description: "Done", duration: store.DURATION.DEFAULT }),
      );
    });

    it("error() adds a toast with type=error and LONG duration", () => {
      const store = useToastStore();
      store.error("Failed", "Oops");
      expect(mocks.mockSonnerError).toHaveBeenCalledWith(
        "Failed",
        expect.objectContaining({ description: "Oops", duration: store.DURATION.LONG }),
      );
    });

    it("warning() adds a toast with type=warning and MEDIUM duration", () => {
      const store = useToastStore();
      store.warning("Careful", "Heads up");
      expect(mocks.mockSonnerWarning).toHaveBeenCalledWith(
        "Careful",
        expect.objectContaining({ description: "Heads up", duration: store.DURATION.MEDIUM }),
      );
    });

    it("info() adds a toast with type=info and DEFAULT duration", () => {
      const store = useToastStore();
      store.info("FYI");
      expect(mocks.mockSonnerInfo).toHaveBeenCalledWith(
        "FYI",
        expect.objectContaining({ duration: store.DURATION.DEFAULT }),
      );
    });

    it("helpers allow caller options to override the default duration", () => {
      const store = useToastStore();
      store.success("Saved", "Done", { duration: store.DURATION.SHORT });
      expect(mocks.mockSonnerSuccess).toHaveBeenCalledWith(
        "Saved",
        expect.objectContaining({ description: "Done", duration: store.DURATION.SHORT }),
      );
    });
  });
});
