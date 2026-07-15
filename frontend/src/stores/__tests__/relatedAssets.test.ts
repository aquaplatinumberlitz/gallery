/**
 * Purpose: Protect ephemeral Related Assets navigation state.
 * Guarantees: Opening copies unified reference/scope state; closing does not write saved/recent search state.
 * Run when: Changing Related Assets panel navigation or session state.
 */
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useRelatedAssetsStore } from "../relatedAssets";

describe("useRelatedAssetsStore", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it("opens a reference without carrying match-type selection state", () => {
    const store = useRelatedAssetsStore();
    store.open({ assetId: 1, path: "/a.png", name: "a.png" }, { kind: "library", library_id: 4 });
    store.open({ assetId: 2, path: "/b.png", name: "b.png" }, { kind: "all" });
    expect(store.reference?.assetId).toBe(2);
    expect(store.scope).toEqual({ kind: "all" });
    expect(store).not.toHaveProperty("profile");
    expect(store.isOpen).toBe(true);
  });

  it("closes without discarding the current reference context", () => {
    const store = useRelatedAssetsStore();
    store.open({ assetId: 1, path: "/a.png", name: "a.png" }, { kind: "library", library_id: 4 });
    store.close();
    expect(store.isOpen).toBe(false);
    expect(store.reference?.path).toBe("/a.png");
    store.reopen();
    expect(store.isOpen).toBe(true);
  });
});
