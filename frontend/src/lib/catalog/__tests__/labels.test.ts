import { describe, expect, it } from "vitest";
import { CATALOG_STATUS_LABELS, getCatalogStatusLabel, getCatalogStatusPresentation } from "../labels";
import type { SummaryState } from "../status";

const EXPECTED_LABELS: Record<SummaryState, string> = {
  unknown: "Unknown",
  offline: "Offline",
  needs_scan: "Needs update",
  scanning: "Updating",
  indexing: "Updating",
  needs_update: "Needs update",
  ready_with_issues: "Ready with issues",
  ready: "Ready",
  error: "Error",
};

describe("getCatalogStatusPresentation", () => {
  it("returns the locked label for every summary state", () => {
    for (const [state, label] of Object.entries(EXPECTED_LABELS)) {
      expect(getCatalogStatusPresentation(state as SummaryState).label).toBe(label);
    }
  });

  it("falls back to unknown for null or invalid states", () => {
    expect(getCatalogStatusPresentation(null).label).toBe("Unknown");
    expect(getCatalogStatusPresentation(undefined).label).toBe("Unknown");
  });

  it("marks scanning and indexing with showPulse", () => {
    expect(getCatalogStatusPresentation("scanning").showPulse).toBe(true);
    expect(getCatalogStatusPresentation("indexing").showPulse).toBe(true);
    expect(getCatalogStatusPresentation("ready").showPulse).toBe(false);
  });

  it("uses destructive variant for offline and error states", () => {
    expect(getCatalogStatusPresentation("offline").variant).toBe("destructive");
    expect(getCatalogStatusPresentation("error").variant).toBe("destructive");
  });

  it("uses green tone for ready and red tone for error", () => {
    expect(getCatalogStatusPresentation("ready").tone).toBe("green");
    expect(getCatalogStatusPresentation("error").tone).toBe("red");
  });
});

describe("CATALOG_STATUS_LABELS", () => {
  it("matches the plan label table for every state", () => {
    expect(CATALOG_STATUS_LABELS).toEqual(EXPECTED_LABELS);
  });
});

describe("getCatalogStatusLabel", () => {
  it("returns the label for a known state", () => {
    expect(getCatalogStatusLabel("scanning")).toBe("Updating");
    expect(getCatalogStatusLabel("ready_with_issues")).toBe("Ready with issues");
  });

  it("returns Unknown for null", () => {
    expect(getCatalogStatusLabel(null)).toBe("Unknown");
  });
});
