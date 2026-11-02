/**
 * Purpose: Protect that every image call site hands the backend `content_version` / `cover_versions[i]`
 * to the URL builders (docs/archived/IMAGE_PIPELINE_PLAN.md, IP-2).
 * Guarantees: Album covers (desktop, tablet, mobile) use the version of their own cover index, the
 * lightbox item (`src`, `previewSrc`, `msrc`) carries the item's version, search results and related
 * results reach PhotoCard (and the lightbox items) with their version, and items without a version keep
 * today's unversioned URLs.
 * Run when: Changing grid cards, album covers, search/related result mapping, or lightbox item building.
 */
import { createPinia, setActivePinia } from "pinia";
import { mount } from "@vue/test-utils";
import type { Component } from "vue";
import { nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AlbumCard from "../AlbumCard.vue";
import AlbumCardMobile from "../AlbumCardMobile.vue";
import AlbumCardTablet from "../AlbumCardTablet.vue";
import SearchResultsPanel from "../search/SearchResultsPanel.vue";
import { buildPhotoSwipeItem } from "@/utils/lightbox";
import { useLightboxStore } from "@/stores/lightbox";
import { useRelatedAssetsStore } from "@/stores/relatedAssets";
import type { FileNode, RelatedSearchResponseV1, RelatedSearchResultV1, UnifiedSearchResult } from "@/types";

const queryState = vi.hoisted(() => ({
  data: { value: null as RelatedSearchResponseV1 | null },
  error: { value: null as Error | null },
  isPending: { value: false },
  refetch: vi.fn(),
}));

vi.mock("@/composables/useRelatedAssetsQuery", () => ({ useRelatedAssetsQuery: () => queryState }));
vi.mock("@/composables/useRelatedAssetsIndexRecovery", () => ({
  useRelatedAssetsIndexRecovery: () => ({
    metadataStatus: { value: null },
    visualStatus: { value: null },
    statusError: { value: false },
    startingKind: { value: null },
    buildErrorKind: { value: null },
    progressPercent: () => 0,
    startBuild: vi.fn(),
    refreshStatus: vi.fn(),
  }),
}));

const encoded = (path: string) => encodeURIComponent(path);

describe("album covers", () => {
  const node: FileNode = {
    name: "Album",
    path: "/photos/album",
    type: "folder",
    has_children: false,
    image_count: 3,
    cover_images: ["/photos/album/a.png", "/photos/album/b.png"],
    cover_versions: ["11-1", "22-2"],
  };

  const covers = (component: Component, props: Record<string, unknown> = {}) => {
    // priority covers skip the visibility gate, so `src` is set at once
    const wrapper = mount(component, { props: { node, priority: true, ...props } });
    return wrapper.findAll("img").map((img) => img.attributes("src"));
  };

  it("AlbumCard uses cover_versions[i] for the back and front cover", () => {
    expect(covers(AlbumCard)).toEqual([
      `/api/thumbnail?path=${encoded("/photos/album/b.png")}&max_long_edge=512&v=22-2`,
      `/api/thumbnail?path=${encoded("/photos/album/a.png")}&max_long_edge=512&v=11-1`,
    ]);
  });

  it.each([
    ["AlbumCardMobile", AlbumCardMobile],
    ["AlbumCardTablet", AlbumCardTablet],
  ])("%s uses cover_versions[0] for the cover", (_name, component) => {
    expect(covers(component as Component)).toEqual([
      `/api/thumbnail?path=${encoded("/photos/album/a.png")}&max_long_edge=512&v=11-1`,
    ]);
  });

  it.each([
    ["AlbumCard", AlbumCard],
    ["AlbumCardMobile", AlbumCardMobile],
    ["AlbumCardTablet", AlbumCardTablet],
  ])("%s keeps unversioned URLs for covers without a version", (_name, component) => {
    const unversioned: FileNode = { ...node, cover_versions: undefined };
    const urls = covers(component as Component, { node: unversioned });
    expect(urls.length).toBeGreaterThan(0);
    for (const url of urls) expect(url).not.toContain("v=");
  });

  it("treats an empty version (cover without a recorded identity) as unversioned", () => {
    const urls = covers(AlbumCardMobile, { node: { ...node, cover_versions: [""] } });
    expect(urls).toEqual([`/api/thumbnail?path=${encoded("/photos/album/a.png")}&max_long_edge=512`]);
  });
});

describe("lightbox item", () => {
  const item: FileNode = {
    name: "photo.png",
    path: "/album/photo.png",
    type: "image",
    has_children: false,
    content_version: "1700-48213",
  };

  it("carries the content version on src, previewSrc and the msrc placeholder", () => {
    const built = buildPhotoSwipeItem(item);
    expect(built.src).toBe(`/api/preview?path=${encoded(item.path)}&max_long_edge=1440&v=1700-48213`);
    expect(built.previewSrc).toBe(built.src);
    expect(built.msrc).toBe(`/api/thumbnail?path=${encoded(item.path)}&max_long_edge=512&v=1700-48213`);
  });

  it("keeps today's URLs for an item without a version", () => {
    const built = buildPhotoSwipeItem({ ...item, content_version: undefined });
    expect(built.src).toBe(`/api/preview?path=${encoded(item.path)}&max_long_edge=1440`);
    expect(built.msrc).toBe(`/api/thumbnail?path=${encoded(item.path)}&max_long_edge=512`);
  });
});

const media = (n: number, overrides: Partial<UnifiedSearchResult> = {}): UnifiedSearchResult => ({
  asset_id: n,
  library_id: 1,
  library_name: "Lib",
  name: `${n}.png`,
  path: `/photos/${n}.png`,
  type: "image",
  parent_path: "/photos",
  relative_path: `${n}.png`,
  mtime: n,
  width: 800,
  height: 600,
  match_type: "filename",
  model: "",
  sampler: "",
  seed: "",
  prompt_snippet: "",
  ...overrides,
});

const photoCardProbe = {
  PhotoCard: {
    props: ["src", "version", "imageWidth", "imageHeight"],
    template:
      "<div class='photo-card' :data-src='src' :data-version='version' :data-w='imageWidth' :data-h='imageHeight' />",
  },
  VideoCard: { template: "<div class='video-card' />" },
  SearchFeedback: { template: "<div />" },
  SearchResultMetadata: { template: "<div />" },
  OverflowTooltip: { template: "<div><slot /></div>" },
};

describe("SearchResultsPanel", () => {
  beforeEach(() => {
    // jsdom has no layout: give every element a viewport-sized box so the virtualizer renders rows.
    vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(800);
    vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(1000);
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(1000);
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(800);
  });

  const mountPanel = async (props: Partial<InstanceType<typeof SearchResultsPanel>["$props"]>) => {
    const wrapper = mount(SearchResultsPanel, {
      props: {
        albums: [],
        media: [],
        fallbackFolders: [],
        isMobile: false,
        isTablet: false,
        columnCount: 4,
        rowHeight: 200,
        initialPending: false,
        blockingError: false,
        staleError: false,
        paginationError: false,
        successfulEmpty: false,
        hasNextPage: false,
        fetchingNextPage: false,
        showAllIndexedHint: false,
        ...props,
      },
      global: {
        stubs: {
          ...photoCardProbe,
          AlbumCard: { props: ["node"], template: "<div class='album' :data-covers='node.cover_versions' />" },
        },
      },
    });
    await nextTick();
    return wrapper;
  };

  it("passes content_version and the dimensions to each PhotoCard", async () => {
    const wrapper = await mountPanel({
      media: [media(1, { content_version: "5-6" }), media(2)],
    });
    const cards = wrapper.findAll(".photo-card");
    expect(cards).toHaveLength(2);
    expect(cards[0]!.attributes("data-version")).toBe("5-6");
    expect(cards[0]!.attributes("data-w")).toBe("800");
    expect(cards[0]!.attributes("data-h")).toBe("600");
    expect(cards[1]!.attributes("data-version")).toBeUndefined();
  });

  it("maps cover_versions onto the album nodes, also when the covers come from the fallback folder", async () => {
    const album = media(9, {
      type: "folder",
      path: "/photos/a",
      cover_images: ["/photos/a/1.png"],
      cover_versions: ["3-4"],
    });
    const fallbackAlbum = media(10, { type: "folder", path: "/photos/b", cover_images: [] });
    const wrapper = await mountPanel({
      albums: [album, fallbackAlbum],
      fallbackFolders: [
        {
          name: "b",
          path: "/photos/b",
          type: "folder",
          has_children: false,
          cover_images: ["/photos/b/1.png"],
          cover_versions: ["8-9"],
        },
      ],
    });
    expect(wrapper.findAll(".album").map((el) => el.attributes("data-covers"))).toEqual(["3-4", "8-9"]);
  });
});

describe("RelatedAssetsPanel", () => {
  const related = (id: number, version: string | null | undefined): RelatedSearchResultV1 => ({
    ...media(id, { content_version: version }),
    asset_id: id,
    library_id: 1,
    library_name: "Lib",
    type: "image" as const,
    relation_tier: 90 as const,
    relation_reasons: ["same_recipe" as const],
    visual_distance: null,
    metadata_score: 0.9,
  });

  beforeEach(() => {
    setActivePinia(createPinia());
    queryState.data.value = {
      schema_version: 1,
      reference_asset_id: 99,
      profile: "related",
      scope: { kind: "library", library_id: 1 },
      returned: 2,
      limit: 60,
      status: {
        metadata: {
          index_name: "generation_signatures",
          state: "ready",
          usable: true,
          indexed_count: 2,
          target_count: 2,
        },
        visual: { index_name: "visual_fingerprints", state: "ready", usable: true, indexed_count: 2, target_count: 2 },
      },
      items: [related(1, "21-22"), related(2, undefined)],
    };
  });

  const mountPanel = async () => {
    useRelatedAssetsStore().open(
      { assetId: 99, path: "/photos/ref.png", name: "ref.png", libraryId: 1 },
      {
        kind: "library",
        library_id: 1,
      },
    );
    const Panel = (await import("../RelatedAssetsPanel.vue")).default;
    return mount(Panel, {
      global: {
        stubs: {
          Sheet: { template: "<div><slot /></div>" },
          SheetContent: { template: "<section><slot /></section>" },
          SheetHeader: { template: "<header><slot /></header>" },
          SheetTitle: { template: "<h1><slot /></h1>" },
          SheetDescription: { template: "<p><slot /></p>" },
          Tooltip: { template: "<div><slot /></div>" },
          TooltipTrigger: { template: "<div><slot /></div>" },
          TooltipContent: { template: "<div><slot /></div>" },
          PhotoCard: {
            props: ["version", "imageWidth"],
            template:
              "<button class='related-card-stub' :data-version='version' :data-w='imageWidth' @click=\"$emit('click')\" />",
          },
        },
      },
    });
  };

  it("passes content_version and the dimensions to each PhotoCard", async () => {
    const wrapper = await mountPanel();
    const cards = wrapper.findAll(".related-card-stub");
    expect(cards.map((c) => c.attributes("data-version"))).toEqual(["21-22", undefined]);
    expect(cards[0]!.attributes("data-w")).toBe("800");
  });

  it("hands the content version to the lightbox items", async () => {
    const wrapper = await mountPanel();
    await wrapper.findAll(".related-card-stub")[0]!.trigger("click");
    const lightbox = useLightboxStore();
    await vi.waitFor(() => expect(lightbox.galleryItems).toHaveLength(2));
    expect(lightbox.galleryItems.map((node) => node.content_version)).toEqual(["21-22", undefined]);
  });
});
