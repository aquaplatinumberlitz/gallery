import { describe, expect, it } from "vitest";
import { ref } from "vue";
import { useFieldedSearch } from "../useFieldedSearch";
import type { FieldFilter } from "@/types";

describe("useFieldedSearch", () => {
  it("derives managed filters from the raw query", () => {
    const rawQuery = ref("cat model:pony seed:>=12");
    const search = useFieldedSearch(rawQuery);
    expect(search.isActive.value).toBe(true);
    expect(search.residualText.value).toBe("cat");
    expect(search.fieldedFilters.value).toEqual([
      { field: "model", value: "pony", operator: undefined },
      { field: "seed", value: "12", operator: ">=" },
    ]);
  });

  it("replaces managed filters without dropping residual or pass-through text", () => {
    const rawQuery = ref("cat tool:ComfyUI model:pony");
    const search = useFieldedSearch(rawQuery);
    const next = search.applyFilters([{ field: "sampler", value: "Euler a" }]);
    expect(next).toBe('cat tool:ComfyUI sampler:"Euler a"');
  });

  it("removes and clears filters explicitly", () => {
    const rawQuery = ref("cat model:pony seed:12");
    const search = useFieldedSearch(rawQuery);
    rawQuery.value = search.removeFilter(0);
    expect(search.fieldedFilters.value).toEqual([{ field: "seed", value: "12", operator: undefined }]);
    rawQuery.value = search.clearAll();
    expect(rawQuery.value).toBe("cat");
    expect(search.isActive.value).toBe(false);
  });

  it("keeps instances isolated because each reads its own query", () => {
    const firstQuery = ref("model:pony");
    const secondQuery = ref("seed:42");
    const first = useFieldedSearch(firstQuery);
    const second = useFieldedSearch(secondQuery);
    firstQuery.value = first.applyFilters([{ field: "sampler", value: "Euler" }]);
    expect(first.fieldedFilters.value).toEqual([{ field: "sampler", value: "Euler", operator: undefined }]);
    expect(second.fieldedFilters.value).toEqual([{ field: "seed", value: "42", operator: undefined }]);
  });

  it("accepts a plain string or getter", () => {
    const filters: FieldFilter[] = [{ field: "model", value: "SDXL" }];
    expect(useFieldedSearch("model:SDXL").fieldedFilters.value).toEqual([
      { field: "model", value: "SDXL", operator: undefined },
    ]);
    expect(useFieldedSearch(() => "model:SDXL").applyFilters(filters)).toBe("model:SDXL");
  });
});
