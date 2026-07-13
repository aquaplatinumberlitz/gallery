/**
 * Purpose: Protect the canonical responsive Related Assets result surface.
 * Guarantees: Profiles, coverage, reasons, metadata-only messaging, retry-safe results, and existing-lightbox selection render correctly.
 * Run when: Changing RelatedAssetsPanel state handling, result cards, profile tabs, or lightbox handoff.
 */
import { createPinia, setActivePinia } from "pinia";
import { mount } from "@vue/test-utils";
import { ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { RelatedSearchResponseV1 } from "@/types";
import { useLightboxStore } from "@/stores/lightbox";
import { useRelatedAssetsStore } from "@/stores/relatedAssets";

const queryState = vi.hoisted(() => ({
  data: { value: null as RelatedSearchResponseV1 | null },
  error: { value: null as Error | null },
  isPending: { value: false },
  refetch: vi.fn(),
}));

vi.mock("@/composables/useRelatedAssetsQuery", () => ({ useRelatedAssetsQuery: () => queryState }));
vi.mock("@/composables/usePhotoMetadataQuery", () => ({
  usePhotoMetadataQuery: () => ({ data: ref(null), isLoading: ref(false) }),
}));

const response: RelatedSearchResponseV1 = {
  schema_version: 1,
  reference_asset_id: 1,
  profile: "related",
  scope: { kind: "library", library_id: 4 },
  returned: 1,
  limit: 60,
  status: {
    metadata: { index_name: "generation_signatures", state: "ready", usable: true, indexed_count: 5, target_count: 5 },
    visual: { index_name: "visual_fingerprints", state: "building", usable: false, indexed_count: 2, target_count: 5 },
  },
  items: [
    {
      asset_id: 2,
      library_id: 4,
      library_name: "Library",
      name: "candidate.png",
      path: "/library/candidate.png",
      type: "image",
      parent_path: "/library",
      relative_path: "",
      mtime: 2,
      width: 512,
      height: 512,
      match_type: "related",
      model: "forest-xl",
      sampler: "Euler",
      seed: "202",
      prompt_snippet: "cinematic fox",
      relation_tier: 90,
      relation_reasons: ["same_recipe", "same_generation_family"],
      visual_distance: null,
      metadata_score: 0.9,
    },
  ],
};

const stubs = {
  Sheet: { template: "<div><slot /></div>" },
  SheetContent: { template: "<section><slot /></section>" },
  SheetHeader: { template: "<header><slot /></header>" },
  SheetTitle: { template: "<h1><slot /></h1>" },
  SheetDescription: { template: "<p><slot /></p>" },
  Tabs: { template: "<div><slot /></div>" },
  TabsList: { template: "<div role='tablist'><slot /></div>" },
  TabsTrigger: { props: ["value"], template: "<button role='tab'><slot /></button>" },
  TabsContent: { template: "<div><slot /></div>" },
  GenerationFamilySummary: { template: "<div data-testid='family-summary'>same recorded settings</div>" },
  PhotoCard: {
    template:
      '<div><button class="open-result" @click="$emit(\'click\')">Open</button><button class="new-reference" @click="$emit(\'find-related\')">Related</button></div>',
  },
};

describe("RelatedAssetsPanel", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    queryState.data.value = response;
    queryState.error.value = null;
    queryState.isPending.value = false;
    queryState.refetch.mockReset();
  });

  it("renders explicit profiles, coverage, reasons, and honest metadata-only wording", async () => {
    const store = useRelatedAssetsStore();
    store.open({ assetId: 1, path: "/library/reference.png", name: "reference.png" }, response.scope);
    const Panel = (await import("../RelatedAssetsPanel.vue")).default;
    const wrapper = mount(Panel, { global: { stubs } });
    expect(wrapper.text()).toContain("Related");
    expect(wrapper.text()).toContain("Same recipe");
    expect(wrapper.text()).toContain("Visual variants");
    expect(wrapper.text()).toContain("Metadata: ready");
    expect(wrapper.text()).toContain("Visual: building");
    expect(wrapper.text()).toContain("Showing metadata relations");
    expect(wrapper.text()).toContain("Same recorded recipe");
    expect(wrapper.text()).toContain("same recorded settings");
    expect(wrapper.text()).not.toMatch(/\d+%/);
  });

  it("opens a related result in the existing lightbox and closes the panel", async () => {
    const store = useRelatedAssetsStore();
    store.open({ assetId: 1, path: "/library/reference.png", name: "reference.png" }, response.scope);
    const lightbox = useLightboxStore();
    const Panel = (await import("../RelatedAssetsPanel.vue")).default;
    const wrapper = mount(Panel, { global: { stubs } });
    await wrapper.get(".open-result").trigger("click");
    expect(store.isOpen).toBe(false);
    expect(lightbox.itemPath).toBe("/library/candidate.png");
    expect(lightbox.galleryItems[0]?.relation_scope).toEqual(response.scope);
  });

  it("changes the reference without reusing saved-search state", async () => {
    const store = useRelatedAssetsStore();
    store.open({ assetId: 1, path: "/library/reference.png", name: "reference.png" }, response.scope);
    const Panel = (await import("../RelatedAssetsPanel.vue")).default;
    const wrapper = mount(Panel, { global: { stubs } });
    await wrapper.get(".new-reference").trigger("click");
    expect(store.reference).toMatchObject({ assetId: 2, path: "/library/candidate.png" });
    expect(store.profile).toBe("related");
  });
});
