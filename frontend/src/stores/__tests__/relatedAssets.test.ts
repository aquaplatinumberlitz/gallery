/**
 * Purpose: Protect ephemeral Related Assets navigation state.
 * Guarantees: Opening resets to combined profile and copies scope; closing does not write saved/recent search state.
 * Run when: Changing Related Assets panel navigation or profile state.
 */
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useRelatedAssetsStore } from "../relatedAssets";

describe("useRelatedAssetsStore", () => {
  beforeEach(() => setActivePinia(createPinia()));

  it("opens a reference in the combined profile and resets profile on reference change", () => {
    const store = useRelatedAssetsStore();
    store.open({ assetId: 1, path: "/a.png", name: "a.png" }, { kind: "library", library_id: 4 });
    store.setProfile("visual");
    store.open({ assetId: 2, path: "/b.png", name: "b.png" }, { kind: "all" });
    expect(store.reference?.assetId).toBe(2);
    expect(store.scope).toEqual({ kind: "all" });
    expect(store.profile).toBe("related");
    expect(store.isOpen).toBe(true);
  });

  it("closes without discarding the current reference context", () => {
    const store = useRelatedAssetsStore();
    store.open({ assetId: 1, path: "/a.png", name: "a.png" }, { kind: "library", library_id: 4 });
    store.close();
    expect(store.isOpen).toBe(false);
    expect(store.reference?.path).toBe("/a.png");
  });
});
