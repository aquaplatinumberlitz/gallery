import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useToastStore } from "../toast";

describe("useToastStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts with no toasts", () => {
    const store = useToastStore();
    expect(store.toasts).toEqual([]);
    expect(store.activeToasts).toEqual([]);
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
      expect(store.toasts).toHaveLength(1);
      const toast = store.toasts[0]!;
      expect(toast.id).toBe(id);
      expect(toast.title).toBe("Hello");
      expect(toast.type).toBe("info");
      expect(toast.duration).toBe(store.DURATION.DEFAULT);
      expect(toast.html).toBe(false);
      expect(toast.dismissible).toBe(true);
      expect(toast.createdAt).toBeTypeOf("number");
    });

    it("respects explicit type, message, duration, html, action, and dismissible options", () => {
      const store = useToastStore();
      const action = { label: "Retry", onClick: vi.fn() };
      const id = store.addToast({
        type: "error",
        title: "Boom",
        message: "Something broke",
        duration: store.DURATION.LONG,
        html: true,
        action,
        dismissible: false,
      });
      const toast = store.toasts.find((t) => t.id === id)!;
      expect(toast.type).toBe("error");
      expect(toast.message).toBe("Something broke");
      expect(toast.duration).toBe(store.DURATION.LONG);
      expect(toast.html).toBe(true);
      expect(toast.action?.label).toBe("Retry");
      expect(toast.dismissible).toBe(false);
    });

    it("auto-removes the toast after its duration elapses", () => {
      const store = useToastStore();
      const id = store.addToast({ title: "Bye", duration: 1000 });
      expect(store.toasts).toHaveLength(1);
      vi.advanceTimersByTime(1000);
      expect(store.toasts).toHaveLength(0);
      expect(id).toMatch(/^toast-/);
    });

    it("keeps persistent toasts (duration 0) until removed manually", () => {
      const store = useToastStore();
      store.addToast({ title: "Persistent", duration: 0 });
      vi.advanceTimersByTime(60_000);
      expect(store.toasts).toHaveLength(1);
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

  describe("activeToasts", () => {
    it("limits visible toasts to MAX_TOASTS (3)", () => {
      const store = useToastStore();
      for (let i = 0; i < 5; i++) {
        store.addToast({ title: `t${i}`, duration: 0 });
      }
      expect(store.toasts).toHaveLength(5);
      expect(store.activeToasts).toHaveLength(3);
      expect(store.activeToasts.map((t) => t.title)).toEqual(["t0", "t1", "t2"]);
    });
  });

  describe("removeToast", () => {
    it("removes the toast with the given id", () => {
      const store = useToastStore();
      const id1 = store.addToast({ title: "one", duration: 0 });
      const id2 = store.addToast({ title: "two", duration: 0 });
      store.removeToast(id1);
      expect(store.toasts.map((t) => t.id)).toEqual([id2]);
    });

    it("is a no-op for an unknown id", () => {
      const store = useToastStore();
      store.addToast({ title: "one", duration: 0 });
      store.removeToast("does-not-exist");
      expect(store.toasts).toHaveLength(1);
    });
  });

  describe("clearAll", () => {
    it("removes every toast", () => {
      const store = useToastStore();
      store.addToast({ title: "one", duration: 0 });
      store.addToast({ title: "two", duration: 0 });
      store.clearAll();
      expect(store.toasts).toEqual([]);
    });
  });

  describe("convenience helpers", () => {
    it("success() adds a toast with type=success and default duration", () => {
      const store = useToastStore();
      const id = store.success("Saved", "Done");
      const toast = store.toasts.find((t) => t.id === id)!;
      expect(toast.type).toBe("success");
      expect(toast.title).toBe("Saved");
      expect(toast.message).toBe("Done");
      expect(toast.duration).toBe(store.DURATION.DEFAULT);
    });

    it("error() adds a toast with type=error and LONG duration", () => {
      const store = useToastStore();
      const id = store.error("Failed", "Oops");
      const toast = store.toasts.find((t) => t.id === id)!;
      expect(toast.type).toBe("error");
      expect(toast.duration).toBe(store.DURATION.LONG);
    });

    it("warning() adds a toast with type=warning and MEDIUM duration", () => {
      const store = useToastStore();
      const id = store.warning("Careful", "Heads up");
      const toast = store.toasts.find((t) => t.id === id)!;
      expect(toast.type).toBe("warning");
      expect(toast.duration).toBe(store.DURATION.MEDIUM);
    });

    it("info() adds a toast with type=info and DEFAULT duration", () => {
      const store = useToastStore();
      const id = store.info("FYI");
      const toast = store.toasts.find((t) => t.id === id)!;
      expect(toast.type).toBe("info");
      expect(toast.duration).toBe(store.DURATION.DEFAULT);
    });

    it("helpers allow caller options to override the default duration", () => {
      const store = useToastStore();
      const id = store.success("Saved", "Done", { duration: store.DURATION.SHORT });
      const toast = store.toasts.find((t) => t.id === id)!;
      expect(toast.duration).toBe(store.DURATION.SHORT);
    });
  });
});
