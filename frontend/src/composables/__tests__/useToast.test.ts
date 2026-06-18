import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useToast } from "../useToast";
import { useToastStore } from "../../stores/toast";

describe("useToast composable", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("success() delegates to the toast store and adds a success-typed toast", () => {
    const toast = useToast();
    const id = toast.success("Saved", "Done");
    expect(id).toMatch(/^toast-/);
    const store = useToastStore();
    const created = store.toasts.find((t) => t.id === id)!;
    expect(created.type).toBe("success");
    expect(created.title).toBe("Saved");
    expect(created.message).toBe("Done");
  });

  it("error() adds an error-typed toast with the LONG default duration", () => {
    const toast = useToast();
    const id = toast.error("Boom", "Something broke");
    const store = useToastStore();
    const created = store.toasts.find((t) => t.id === id)!;
    expect(created.type).toBe("error");
    expect(created.duration).toBe(store.DURATION.LONG);
  });

  it("warning() adds a warning-typed toast", () => {
    const toast = useToast();
    const id = toast.warning("Careful");
    const store = useToastStore();
    const created = store.toasts.find((t) => t.id === id)!;
    expect(created.type).toBe("warning");
  });

  it("info() adds an info-typed toast", () => {
    const toast = useToast();
    const id = toast.info("FYI");
    const store = useToastStore();
    const created = store.toasts.find((t) => t.id === id)!;
    expect(created.type).toBe("info");
  });

  it("show() adds a toast with the exact options provided", () => {
    const toast = useToast();
    const id = toast.show({ type: "info", title: "Custom" });
    const store = useToastStore();
    const created = store.toasts.find((t) => t.id === id)!;
    expect(created.title).toBe("Custom");
  });

  it("dismiss() removes the toast with the given id", () => {
    const toast = useToast();
    const id = toast.info("To remove");
    toast.dismiss(id);
    const store = useToastStore();
    expect(store.toasts.find((t) => t.id === id)).toBeUndefined();
  });

  it("clear() removes all toasts", () => {
    const toast = useToast();
    toast.info("one");
    toast.info("two");
    toast.clear();
    const store = useToastStore();
    expect(store.toasts).toHaveLength(0);
  });

  it("promise() shows a loading toast, then a success toast on resolve", async () => {
    const toast = useToast();
    const promise = toast.promise(Promise.resolve("data"), {
      loading: "Saving",
      success: (data) => `Done: ${data}`,
      error: "Failed",
    });
    await expect(promise).resolves.toBe("data");
    const store = useToastStore();
    const titles = store.toasts.map((t) => t.title);
    expect(titles).toContain("Done: data");
    expect(titles).not.toContain("Saving");
  });

  it("promise() shows a loading toast, then an error toast on reject, and rethrows", async () => {
    const toast = useToast();
    const promise = toast.promise(Promise.reject(new Error("boom")), {
      loading: "Saving",
      success: "Done",
      error: (err) => `Failed: ${(err as Error).message}`,
    });
    await expect(promise).rejects.toThrow("boom");
    const store = useToastStore();
    const titles = store.toasts.map((t) => t.title);
    expect(titles).toContain("Failed: boom");
    expect(titles).not.toContain("Saving");
  });
});
