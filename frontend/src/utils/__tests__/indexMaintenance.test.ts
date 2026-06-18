import { describe, it, expect, beforeEach, vi } from "vitest";
import type * as IndexMaintenance from "../indexMaintenance";

describe("indexMaintenance scope-rebuild markers", () => {
  let mod: typeof IndexMaintenance;

  beforeEach(async () => {
    // The marker map is module-scoped reactive state. Reset the module registry
    // so each test starts with an empty map.
    vi.resetModules();
    mod = await import("../indexMaintenance");
  });

  describe("markScopeRebuildStarted / getScopeRebuildStartedAt", () => {
    it("returns 0 when no rebuild has been marked for the path", () => {
      expect(mod.getScopeRebuildStartedAt("/some/path")).toBe(0);
    });

    it("records the rebuild start timestamp for the exact path", () => {
      mod.markScopeRebuildStarted("/root/album", 1000);
      expect(mod.getScopeRebuildStartedAt("/root/album")).toBe(1000);
    });

    it("propagates the marker to descendant paths", () => {
      mod.markScopeRebuildStarted("/root", 2000);
      expect(mod.getScopeRebuildStartedAt("/root/album")).toBe(2000);
      expect(mod.getScopeRebuildStartedAt("/root/album/sub")).toBe(2000);
    });

    it("returns the latest timestamp across multiple overlapping roots", () => {
      mod.markScopeRebuildStarted("/root", 1000);
      mod.markScopeRebuildStarted("/root/album", 3000);
      expect(mod.getScopeRebuildStartedAt("/root/album/sub")).toBe(3000);
    });

    it("returns 0 for sibling paths that are not inside any marked root", () => {
      mod.markScopeRebuildStarted("/root", 5000);
      expect(mod.getScopeRebuildStartedAt("/other/path")).toBe(0);
    });

    it("ignores empty paths", () => {
      mod.markScopeRebuildStarted("", 1000);
      expect(mod.getScopeRebuildStartedAt("")).toBe(0);
    });

    it("ignores non-finite timestamps", () => {
      mod.markScopeRebuildStarted("/root", Number.NaN);
      mod.markScopeRebuildStarted("/root", Number.POSITIVE_INFINITY);
      expect(mod.getScopeRebuildStartedAt("/root")).toBe(0);
    });

    it("keeps the maximum timestamp when markScopeRebuildStarted is called repeatedly on the same root", () => {
      mod.markScopeRebuildStarted("/root", 1000);
      mod.markScopeRebuildStarted("/root", 500);
      expect(mod.getScopeRebuildStartedAt("/root")).toBe(1000);
    });

    it("treats the filesystem root '/' as covering all absolute paths", () => {
      mod.markScopeRebuildStarted("/", 9000);
      expect(mod.getScopeRebuildStartedAt("/any/deep/path")).toBe(9000);
    });

    it("does not treat a parent path as covering a sibling that merely shares a string prefix", () => {
      mod.markScopeRebuildStarted("/root/foo", 4000);
      // /root/foobar is NOT inside /root/foo — boundary check uses `${root}/`
      expect(mod.getScopeRebuildStartedAt("/root/foobar")).toBe(0);
    });
  });

  describe("clearScopeRebuildMarker", () => {
    it("removes markers for roots that cover the cleared path", () => {
      mod.markScopeRebuildStarted("/root/album", 1000);
      mod.clearScopeRebuildMarker("/root/album", 2000);
      expect(mod.getScopeRebuildStartedAt("/root/album")).toBe(0);
    });

    it("does not remove markers when generatedAt is older than the marker", () => {
      mod.markScopeRebuildStarted("/root/album", 5000);
      mod.clearScopeRebuildMarker("/root/album", 1000);
      expect(mod.getScopeRebuildStartedAt("/root/album")).toBe(5000);
    });

    it("removes markers when generatedAt equals the marker timestamp", () => {
      mod.markScopeRebuildStarted("/root/album", 5000);
      mod.clearScopeRebuildMarker("/root/album", 5000);
      expect(mod.getScopeRebuildStartedAt("/root/album")).toBe(0);
    });

    it("ignores empty paths", () => {
      mod.markScopeRebuildStarted("/root", 1000);
      mod.clearScopeRebuildMarker("", 5000);
      expect(mod.getScopeRebuildStartedAt("/root")).toBe(1000);
    });

    it("ignores non-finite generatedAt", () => {
      mod.markScopeRebuildStarted("/root", 1000);
      mod.clearScopeRebuildMarker("/root", Number.NaN);
      expect(mod.getScopeRebuildStartedAt("/root")).toBe(1000);
    });

    it("clears all ancestor markers that cover the cleared deeper path", () => {
      mod.markScopeRebuildStarted("/root", 1000);
      mod.markScopeRebuildStarted("/root/album", 2000);
      mod.clearScopeRebuildMarker("/root/album/sub", 3000);
      // Both /root and /root/album cover /root/album/sub, so both are cleared.
      expect(mod.getScopeRebuildStartedAt("/root")).toBe(0);
      expect(mod.getScopeRebuildStartedAt("/root/album")).toBe(0);
    });

    it("only clears markers whose root covers the cleared scope", () => {
      mod.markScopeRebuildStarted("/root", 1000);
      mod.markScopeRebuildStarted("/other", 2000);
      mod.clearScopeRebuildMarker("/root/album", 3000);
      // /root covers /root/album so it's cleared; /other does not, so it stays.
      expect(mod.getScopeRebuildStartedAt("/root")).toBe(0);
      expect(mod.getScopeRebuildStartedAt("/other")).toBe(2000);
    });

    it("clearing the filesystem root '/' removes only the root marker itself", () => {
      mod.markScopeRebuildStarted("/", 1000);
      mod.markScopeRebuildStarted("/root", 2000);
      mod.clearScopeRebuildMarker("/", 5000);
      // Only the marker on '/' itself is cleared because /root does not cover '/'.
      expect(mod.getScopeRebuildStartedAt("/")).toBe(0);
      expect(mod.getScopeRebuildStartedAt("/root")).toBe(2000);
    });
  });
});
