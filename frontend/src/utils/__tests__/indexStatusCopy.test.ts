import { describe, it, expect, beforeEach } from "vitest";
import {
  INDEX_FIELD_COPY,
  INDEX_STATUS_LABELS,
  getFieldCopy,
  getFieldLabel,
  getFieldTooltip,
} from "../indexStatusCopy";

describe("INDEX_FIELD_COPY", () => {
  it("exposes copy for the core fields used by the status panel", () => {
    expect(INDEX_FIELD_COPY.metadata_records.label).toBe("Photo details ready");
    expect(INDEX_FIELD_COPY.indexed_photos.label).toBe("Photos found");
    expect(INDEX_FIELD_COPY.done.label).toBe("Details processed");
    expect(INDEX_FIELD_COPY.path.label).toBe("Folder");
    expect(INDEX_FIELD_COPY.recursive.label).toBe("Including subfolders");
  });

  it("includes apiTrace strings for debug mode", () => {
    expect(INDEX_FIELD_COPY.metadata_records.apiTrace).toBe("API: metadata_records");
    expect(INDEX_FIELD_COPY.done.apiTrace).toContain("done");
  });

  it("uses empty tooltip for the recursive flag", () => {
    expect(INDEX_FIELD_COPY.recursive.tooltip).toBe("");
  });
});

describe("getFieldCopy", () => {
  it("returns the cataloged copy for known fields", () => {
    const copy = getFieldCopy("metadata_records");
    expect(copy).toEqual(INDEX_FIELD_COPY.metadata_records);
  });

  it("returns a fallback object using the field name as label when the field is unknown", () => {
    const copy = getFieldCopy("custom_field");
    expect(copy.label).toBe("custom_field");
    expect(copy.tooltip).toBe("");
    expect(copy.apiTrace).toBe("custom_field");
  });
});

describe("getFieldLabel", () => {
  it("returns the cataloged label for known fields", () => {
    expect(getFieldLabel("done")).toBe("Details processed");
  });

  it("falls back to the raw field name for unknown fields", () => {
    expect(getFieldLabel("unknown_field")).toBe("unknown_field");
  });
});

describe("getFieldTooltip", () => {
  beforeEach(() => {
    delete (window as Partial<Window> & { __GALLERY_DEBUG_INDEX_REBUILD?: boolean }).__GALLERY_DEBUG_INDEX_REBUILD;
    window.localStorage.removeItem("debug-index-rebuild");
  });

  it("returns the cataloged tooltip for known fields when debug is disabled", () => {
    expect(getFieldTooltip("metadata_records")).toBe(INDEX_FIELD_COPY.metadata_records.tooltip);
  });

  it("returns an empty string for fields with empty tooltip (recursive)", () => {
    expect(getFieldTooltip("recursive")).toBe("");
  });

  it("returns an empty string for unknown fields", () => {
    expect(getFieldTooltip("custom_field")).toBe("");
  });

  it("appends the apiTrace line when debug-index-rebuild is enabled via localStorage", () => {
    window.localStorage.setItem("debug-index-rebuild", "true");
    const tooltip = getFieldTooltip("metadata_records");
    expect(tooltip).toBe(`${INDEX_FIELD_COPY.metadata_records.tooltip}\n${INDEX_FIELD_COPY.metadata_records.apiTrace}`);
  });

  it("appends the apiTrace line when the window debug flag is enabled", () => {
    (window as unknown as { __GALLERY_DEBUG_INDEX_REBUILD: boolean }).__GALLERY_DEBUG_INDEX_REBUILD = true;
    const tooltip = getFieldTooltip("done");
    expect(tooltip).toContain("\nAPI:");
  });

  it("returns an empty string for unknown fields even when debug mode is enabled (fallback has empty tooltip)", () => {
    window.localStorage.setItem("debug-index-rebuild", "true");
    // The fallback for unknown fields uses tooltip === "" which short-circuits
    // before the debug apiTrace branch can run.
    const tooltip = getFieldTooltip("custom_field");
    expect(tooltip).toBe("");
  });
});

describe("INDEX_STATUS_LABELS", () => {
  it("provides a label for every UI status", () => {
    expect(INDEX_STATUS_LABELS.unknown).toBe("Unknown");
    expect(INDEX_STATUS_LABELS.ready).toBe("Ready");
    expect(INDEX_STATUS_LABELS.indexing).toBe("Updating");
    expect(INDEX_STATUS_LABELS.stale).toBe("Needs update");
    expect(INDEX_STATUS_LABELS.warning).toBe("Unavailable");
    expect(INDEX_STATUS_LABELS.error).toBe("Error");
  });
});
