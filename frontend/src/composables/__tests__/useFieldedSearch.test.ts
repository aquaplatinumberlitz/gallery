import { describe, expect, it, beforeEach } from "vitest";
import { useFieldedSearch } from "../useFieldedSearch";
import type { FieldFilter } from "@/types";

// useFieldedSearch uses module-level state, so each test affects the same state
describe("useFieldedSearch", () => {
  beforeEach(() => {
    const { clearAll } = useFieldedSearch();
    clearAll();
  });

  it("starts with no active filters", () => {
    const { isActive, fieldedFilters } = useFieldedSearch();
    expect(isActive.value).toBe(false);
    expect(fieldedFilters.value).toHaveLength(0);
  });

  it("applies filters and marks as active", () => {
    const { applyFilters, isActive, fieldedFilters } = useFieldedSearch();
    const filters: FieldFilter[] = [{ field: "prompt", operator: "contains", value: "cat" }];
    applyFilters(filters);
    expect(isActive.value).toBe(true);
    expect(fieldedFilters.value).toEqual(filters);
  });

  it("removes a filter by index", () => {
    const { applyFilters, removeFilter, fieldedFilters } = useFieldedSearch();
    applyFilters([
      { field: "prompt", operator: "contains", value: "cat" },
      { field: "model", operator: "equals", value: "sd-xl" },
    ]);
    expect(fieldedFilters.value).toHaveLength(2);
    removeFilter(0);
    expect(fieldedFilters.value).toHaveLength(1);
    expect(fieldedFilters.value[0].field).toBe("model");
  });

  it("clearAll resets filters and cache", () => {
    const { applyFilters, clearAll, isActive, fieldedFilters, queryString } = useFieldedSearch();
    applyFilters([{ field: "prompt", operator: "contains", value: "cat" }]);
    expect(isActive.value).toBe(true);
    clearAll();
    expect(isActive.value).toBe(false);
    expect(fieldedFilters.value).toHaveLength(0);
    expect(queryString.value).toBe("");
  });

  it("isActive is false after removing last filter", () => {
    const { applyFilters, removeFilter, isActive } = useFieldedSearch();
    applyFilters([{ field: "prompt", operator: "contains", value: "cat" }]);
    expect(isActive.value).toBe(true);
    removeFilter(0);
    expect(isActive.value).toBe(false);
  });

  it("generates query string from filters", () => {
    const { applyFilters, queryString } = useFieldedSearch();

    // The actual serialization is done by serializeAdvancedSearchToQuery
    // We just verify it's called and a string is produced
    applyFilters([{ field: "prompt", operator: "contains", value: "cat" }]);
    expect(queryString.value).toBeTruthy();
    expect(typeof queryString.value).toBe("string");
  });

  it("caches query string between calls", () => {
    const { applyFilters, queryString } = useFieldedSearch();
    applyFilters([{ field: "prompt", operator: "contains", value: "cat" }]);
    const firstQuery = queryString.value;
    const secondQuery = queryString.value;
    expect(firstQuery).toBe(secondQuery);
  });
});
