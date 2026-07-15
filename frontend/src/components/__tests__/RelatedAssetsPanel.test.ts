/**
 * Purpose: Protect the unified responsive Related Assets result surface.
 * Guarantees: One result list, defensive dedupe/reasons, partial readiness, correct recovery CTAs, and lightbox handoff.
 * Run when: Changing RelatedAssetsPanel results, readiness, recovery actions, accessibility, or lightbox integration.
 */
import { createPinia, setActivePinia } from "pinia";
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GalleryAPIError } from "@/services/api";
import type { RelatedSearchRequestV1, RelatedSearchResponseV1, RelatedSearchResultV1 } from "@/types";
import { useLightboxStore } from "@/stores/lightbox";
import { useRelatedAssetsStore } from "@/stores/relatedAssets";

const queryState = vi.hoisted(() => ({
  data: { value: null as RelatedSearchResponseV1 | null },
  error: { value: null as Error | null },
  isPending: { value: false },
  refetch: vi.fn(),
}));
const queryFactory = vi.hoisted(() => vi.fn((_request: unknown) => queryState));
const recoveryState = vi.hoisted(() => ({
  metadataStatus: { value: null as RelatedSearchResponseV1["status"]["metadata"] | null },
  visualStatus: { value: null as RelatedSearchResponseV1["status"]["visual"] | null },
  statusError: { value: false },
  startingKind: { value: null as "metadata" | "visual" | null },
  buildErrorKind: { value: null as "metadata" | "visual" | null },
  progressPercent: vi.fn(() => 40),
  startBuild: vi.fn(),
  refreshStatus: vi.fn(),
}));

vi.mock("@/composables/useRelatedAssetsQuery", () => ({ useRelatedAssetsQuery: queryFactory }));
vi.mock("@/composables/useRelatedAssetsIndexRecovery", () => ({
  useRelatedAssetsIndexRecovery: () => recoveryState,
}));

const result = (assetId: number, overrides: Partial<RelatedSearchResultV1> = {}): RelatedSearchResultV1 => ({
  asset_id: assetId,
  library_id: 4,
  library_name: "Library",
  name: `${assetId}.png`,
  path: `/library/${assetId}.png`,
  type: "image",
  parent_path: "/library",
  relative_path: "",
  mtime: assetId,
  width: 512,
  height: 512,
  match_type: "related",
  model: "forest-xl",
  sampler: "Euler",
  seed: `${assetId}`,
  prompt_snippet: "cinematic fox",
  relation_tier: 90,
  relation_reasons: ["same_recipe"],
  visual_distance: null,
  metadata_score: 0.9,
  ...overrides,
});

const response: RelatedSearchResponseV1 = {
  schema_version: 1,
  reference_asset_id: 1,
  profile: "related",
  scope: { kind: "library", library_id: 4 },
  returned: 3,
  limit: 60,
  status: {
    metadata: {
      index_name: "generation_signatures",
      state: "ready",
      usable: true,
      indexed_count: 5,
      target_count: 5,
    },
    visual: {
      index_name: "visual_fingerprints",
      state: "building",
      usable: false,
      indexed_count: 2,
      target_count: 5,
    },
  },
  items: [
    result(8),
    result(3, {
      name: "visual-only.png",
      path: "/library/visual-only.png",
      match_type: "visual_variant",
      relation_tier: 80,
      relation_reasons: ["visual_variant"],
      visual_distance: 2,
      metadata_score: null,
    }),
    result(8, {
      relation_tier: 80,
      relation_reasons: ["visual_variant", "same_model_hash"],
      visual_distance: 3,
      metadata_score: null,
    }),
  ],
};

const stubs = {
  Sheet: { template: "<div><slot /></div>" },
  SheetContent: { template: "<section><slot /></section>" },
  SheetHeader: { template: "<header><slot /></header>" },
  SheetTitle: { template: "<h1><slot /></h1>" },
  SheetDescription: { template: "<p><slot /></p>" },
  Tooltip: { template: "<div><slot /></div>" },
  TooltipTrigger: { template: "<div><slot /></div>" },
  TooltipContent: { template: "<div><slot /></div>" },
  PhotoCard: {
    template: '<div><button class="open-result" @click="$emit(\'click\')">Open</button></div>',
  },
};

async function mountPanel() {
  const store = useRelatedAssetsStore();
  store.open({ assetId: 1, path: "/library/reference.png", name: "reference.png", libraryId: 4 }, response.scope);
  const Panel = (await import("../RelatedAssetsPanel.vue")).default;
  return mount(Panel, { global: { stubs } });
}

beforeEach(() => {
  setActivePinia(createPinia());
  queryFactory.mockClear();
  queryState.data.value = response;
  queryState.error.value = null;
  queryState.isPending.value = false;
  queryState.refetch.mockReset();
  recoveryState.metadataStatus.value = response.status.metadata;
  recoveryState.visualStatus.value = response.status.visual;
  recoveryState.statusError.value = false;
  recoveryState.startingKind.value = null;
  recoveryState.buildErrorKind.value = null;
  recoveryState.progressPercent.mockClear();
  recoveryState.startBuild.mockReset();
  recoveryState.refreshStatus.mockReset();
});

describe("RelatedAssetsPanel", () => {
  it("renders one unified result list with no tablist or match-type selector", async () => {
    const wrapper = await mountPanel();
    const request = queryFactory.mock.calls[0]?.[0] as { value: RelatedSearchRequestV1 };

    expect(request.value.profile).toBe("related");
    expect(wrapper.get("h1").text()).toBe("Related assets");
    expect(wrapper.find('[aria-label="How Related assets matches are found"]').exists()).toBe(true);
    expect(wrapper.find('[role="tablist"]').exists()).toBe(false);
    expect(wrapper.find('[role="tab"]').exists()).toBe(false);
    expect(wrapper.find("select").exists()).toBe(false);
    expect(wrapper.findAll('[data-testid="related-results"]')).toHaveLength(1);
  });

  it("shows metadata and visual matches together, deduplicates IDs, unions reasons, and keeps server order", async () => {
    const wrapper = await mountPanel();
    const cards = wrapper.findAll(".related-card");

    expect(cards).toHaveLength(2);
    expect(cards[0]?.text()).toContain("8.png");
    expect(cards[0]?.text()).toContain("Same recipe");
    expect(cards[0]?.text()).toContain("Same model");
    expect(cards[0]?.text()).toContain("Visually similar");
    expect(cards[1]?.text()).toContain("visual-only.png");
  });

  it("keeps metadata results visible while visual coverage builds", async () => {
    const wrapper = await mountPanel();

    expect(wrapper.text()).toContain("Visual matches are still indexing. Results will update automatically.");
    expect(wrapper.text()).toContain("2 / 5 indexed");
    expect(wrapper.findAll(".related-card")).toHaveLength(2);
    expect(wrapper.text()).not.toContain("Retry query");
  });

  it("keeps visual results visible while metadata coverage builds", async () => {
    queryState.data.value = {
      ...response,
      status: {
        metadata: { ...response.status.metadata, state: "building", usable: false, indexed_count: 1 },
        visual: { ...response.status.visual, state: "ready", usable: true, indexed_count: 5 },
      },
      items: [response.items[1]!],
      returned: 1,
    };
    recoveryState.metadataStatus.value = queryState.data.value.status.metadata;
    recoveryState.visualStatus.value = queryState.data.value.status.visual;
    const wrapper = await mountPanel();

    expect(wrapper.text()).toContain("Metadata matches are still indexing. Results will update automatically.");
    expect(wrapper.text()).toContain("visual-only.png");
  });

  it("shows Build index for pending coverage and Retry build after failure", async () => {
    queryState.data.value = {
      ...response,
      status: { ...response.status, visual: { ...response.status.visual, state: "not_ready" } },
    };
    recoveryState.visualStatus.value = queryState.data.value.status.visual;
    let wrapper = await mountPanel();

    await wrapper.get('[data-testid="build-visual-index"]').trigger("click");
    expect(wrapper.text()).toContain("Build index");
    expect(recoveryState.startBuild).toHaveBeenCalledWith("visual");

    wrapper.unmount();
    recoveryState.visualStatus.value = { ...response.status.visual, state: "failed", usable: false };
    wrapper = await mountPanel();
    expect(wrapper.text()).toContain("Retry build");
  });

  it("reserves Retry query for transient request failures", async () => {
    queryState.data.value = null;
    queryState.error.value = new GalleryAPIError("network", "Can't connect to server", "Try again", true);
    recoveryState.metadataStatus.value = null;
    recoveryState.visualStatus.value = null;
    const wrapper = await mountPanel();

    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("Retry query"))!
      .trigger("click");
    expect(wrapper.text()).toContain("Retry query");
    expect(queryState.refetch).toHaveBeenCalledOnce();
  });

  it("renders the shared loading and empty states", async () => {
    queryState.data.value = null;
    queryState.isPending.value = true;
    let wrapper = await mountPanel();
    expect(wrapper.text()).toContain("Finding related assets…");

    wrapper.unmount();
    queryState.isPending.value = false;
    queryState.data.value = { ...response, items: [], returned: 0 };
    recoveryState.visualStatus.value = queryState.data.value.status.visual;
    wrapper = await mountPanel();
    expect(wrapper.text()).toContain("No related assets found");
  });

  it("opens a related result in the existing lightbox and restores the results context after close", async () => {
    const wrapper = await mountPanel();
    const store = useRelatedAssetsStore();
    const lightbox = useLightboxStore();

    await wrapper.get(".open-result").trigger("click");
    await vi.waitFor(() => expect(store.isOpen).toBe(false));
    expect(lightbox.itemPath).toBe("/library/8.png");
    expect(lightbox.galleryItems).toHaveLength(2);
    expect(lightbox.currentIndex).toBe(0);
    lightbox.close();
    await vi.waitFor(() => expect(store.isOpen).toBe(true));
  });
});
