/**
 * Purpose: Protect the lazy boundary around the search results panel.
 * Guarantees: The wrapper does not statically depend on the panel implementation (it renders nothing until the chunk
 * arrives), then renders it with every prop, attribute and listener forwarded unchanged; and no module imports the
 * implementation statically.
 * Run when: Changing SearchResultsPanel.vue, utils/searchChunks.ts, or who imports the results panel.
 */
import { flushPromises, mount } from "@vue/test-utils";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { defineComponent, h } from "vue";
import { describe, expect, it, vi } from "vitest";
import SearchResultsPanel from "../SearchResultsPanel.vue";

// `__esModule` makes Vue async-component resolver read `.default` (a real module namespace answers that itself).
vi.mock("../SearchResultsPanelImpl.vue", () => ({
  __esModule: true,
  default: defineComponent({
    name: "SearchResultsPanelImpl",
    props: { columnCount: { type: Number, required: true }, successfulEmpty: Boolean },
    emits: ["clear"],
    setup:
      (props, { emit }) =>
      () =>
        h("button", { class: "impl", "data-columns": props.columnCount, onClick: () => emit("clear") }, "impl"),
  }),
}));

describe("SearchResultsPanel (lazy boundary)", () => {
  it("renders nothing until the implementation chunk has loaded, then forwards props, attrs and listeners", async () => {
    const onClear = vi.fn();
    const wrapper = mount(SearchResultsPanel, {
      attrs: { columnCount: 4, successfulEmpty: true, class: "from-parent", onClear },
    });

    expect(wrapper.find(".impl").exists()).toBe(false);

    await flushPromises();

    const impl = wrapper.get(".impl");
    expect(impl.attributes("data-columns")).toBe("4");
    expect(impl.classes()).toContain("from-parent");
    await impl.trigger("click");
    expect(onClear).toHaveBeenCalledTimes(1);
  });
});

describe("results panel import graph", () => {
  const srcRoot = join(process.cwd(), "src");
  const sourceFiles = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) return name === "__tests__" ? [] : sourceFiles(path);
      return /\.(vue|ts)$/.test(name) ? [path] : [];
    });

  it("reaches the implementation only through the dynamic import in utils/searchChunks.ts", () => {
    const importers = sourceFiles(srcRoot).filter((file) =>
      /(from\s+|import\()\s*["'][^"']*SearchResultsPanelImpl/.test(readFileSync(file, "utf8")),
    );
    expect(importers.map((file) => file.slice(srcRoot.length + 1))).toEqual(["utils/searchChunks.ts"]);

    const chunks = readFileSync(join(srcRoot, "utils/searchChunks.ts"), "utf8");
    expect(chunks).not.toMatch(/from\s+["'][^"']*SearchResultsPanelImpl/);
    expect(chunks).toContain('import("@/components/search/SearchResultsPanelImpl.vue")');
  });
});
