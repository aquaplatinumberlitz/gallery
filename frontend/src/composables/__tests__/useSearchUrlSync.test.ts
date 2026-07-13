import { createPinia, setActivePinia } from "pinia";
import { mount, flushPromises } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useGalleryStore } from "@/stores/gallery";
import type { RegisteredLibrary } from "@/types";
import { encodeSearchUrlQuery } from "@/utils/searchUrlCodec";
import { useSearchUrlSync } from "../useSearchUrlSync";

const library: RegisteredLibrary = {
  id: 2,
  name: "Library",
  root_path: "/GalleryRoot",
  import_paths: [{ id: 7, library_id: 2, path: "/GalleryRoot", position: 0, created_at: 1, updated_at: 1 }],
  exclusion_patterns: [],
  state: "ready",
  watch_enabled: 1,
  warm_enabled: 1,
  asset_count: 10,
  created_at: 1,
  updated_at: 1,
  last_scan_at: null,
  last_error: null,
};

const request = (text: string) => ({
  schema_version: 1 as const,
  mode: "lexical" as const,
  text,
  scope: {
    kind: "folder" as const,
    library_id: 2,
    import_path_id: 7,
    relative_path: "CaseSensitive/Portraits",
  },
  filters: { prompt_groups: [], workflow_groups: [] },
  cursor: null,
  limit: 60,
});

const setup = async (query: Record<string, string> = {}) => {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/", name: "gallery", component: { render: () => h("div") } }],
  });
  await router.push({ name: "gallery", query });
  await router.isReady();
  const wrapper = mount(
    defineComponent({
      setup() {
        useSearchUrlSync(() => [library], true);
        return () => h("div");
      },
    }),
    { global: { plugins: [pinia, router] } },
  );
  await flushPromises();
  return { wrapper, router, store: useGalleryStore() };
};

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useSearchUrlSync", () => {
  it("hydrates a copied folder URL once and preserves path casing", async () => {
    const { store, router } = await setup(encodeSearchUrlQuery(request("cat")) as Record<string, string>);
    expect(store.searchQuery).toBe("cat");
    expect(store.submittedSearchQuery).toBe("cat");
    expect(store.searchScope).toBe("current");
    expect(store.currentBrowsePath).toBe("/GalleryRoot/CaseSensitive/Portraits");
    expect(router.currentRoute.value.query.path).toBe("CaseSensitive/Portraits");
  });

  it("uses replace for debounced typing and push for explicit submit", async () => {
    const { store, router } = await setup();
    store.applyActiveSelection(library, library.import_paths[0], "/GalleryRoot/CaseSensitive/Portraits");
    const replace = vi.spyOn(router, "replace");
    const push = vi.spyOn(router, "push");

    store.setSearchQuery("cat");
    await vi.advanceTimersByTimeAsync(250);
    await flushPromises();
    expect(replace).toHaveBeenCalledTimes(1);
    expect(router.currentRoute.value.query.q).toBe("cat");

    store.submitSearch();
    await flushPromises();
    expect(push).toHaveBeenCalledTimes(1);
  });

  it("applies browser navigation without writing the same state back", async () => {
    const { store, router } = await setup(encodeSearchUrlQuery(request("cat")) as Record<string, string>);
    const replace = vi.spyOn(router, "replace");
    const push = vi.spyOn(router, "push");

    await router.replace({ name: "gallery", query: encodeSearchUrlQuery(request("dog")) });
    await flushPromises();
    expect(store.searchQuery).toBe("dog");
    expect(replace).toHaveBeenCalledTimes(1);
    expect(push).not.toHaveBeenCalled();
  });

  it("sanitizes invalid URL data with one replace and a safe fallback", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/", name: "gallery", component: { render: () => h("div") } }],
    });
    await router.push({ name: "gallery", query: { search_v: "1", scope: "folder", library: "2", import: "999" } });
    await router.isReady();
    const replace = vi.spyOn(router, "replace");
    mount(
      defineComponent({
        setup() {
          useSearchUrlSync(() => [library], true);
          return () => h("div");
        },
      }),
      { global: { plugins: [pinia, router] } },
    );
    await flushPromises();
    expect(replace).toHaveBeenCalledTimes(1);
    expect(router.currentRoute.value.query.search_v).toBeUndefined();
    expect(useGalleryStore().searchQuery).toBe("");
  });
});
