/**
 * Purpose: Protect the pre-mount start of the home page's root browse request and first album cover.
 * Guarantees: The target library and root folder are resolved the way the store hydrates them (persisted
 * selection, else the only library with an import path, else nothing). The root page is fetched with the exact
 * infinite-browse query key and function, so a mounted `useInfiniteBrowseQuery` reuses the cached page, or joins
 * the request still in flight, instead of requesting it again. Every failure or missing input ends silently and
 * leaves the mounted query to load as before. The first cover (first folder in the user's sort order) is requested
 * ahead of the card with the card's URL at high priority, unless the album strip is collapsed.
 * Run when: Changing main.ts start-up prefetching, useInfiniteBrowseQuery, browse query keys, or album cover URLs.
 */
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h, ref } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AlbumCard from "@/components/AlbumCard.vue";
import AlbumCardMobile from "@/components/AlbumCardMobile.vue";
import AlbumCardTablet from "@/components/AlbumCardTablet.vue";
import { IMAGE_PAGE_SIZE } from "@/constants";
import { useInfiniteBrowseQuery } from "@/composables/useInfiniteBrowseQuery";
import { queryKeys } from "@/query/keys";
import { browseDirectory, getThumbnailUrl } from "@/services/api";
import { ACTIVE_IMPORT_PATH_STORAGE_KEY, ACTIVE_LIBRARY_STORAGE_KEY, SORT_STORAGE_KEY } from "@/stores/gallery";
import type { BrowseResponse, FolderTreeNode, RegisteredLibrary } from "@/types";
import {
  ALBUMS_COLLAPSED_STORAGE_KEY,
  resolveHomeBrowseTarget,
  startHomeBrowsePrefetch,
  warmAlbumCover,
} from "../homeBrowsePrefetch";

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return { ...actual, browseDirectory: vi.fn() };
});

const importPath = (id: number, libraryId: number, path: string, position = 0) => ({
  id,
  library_id: libraryId,
  path,
  position,
  created_at: 0,
  updated_at: 0,
});

const library = (id: number, paths: Array<ReturnType<typeof importPath>>): RegisteredLibrary =>
  ({ id, name: `lib${id}`, import_paths: paths }) as unknown as RegisteredLibrary;

const libA = library(1, [importPath(11, 1, "/photos/a", 0), importPath(12, 1, "/photos/a2", 1)]);
const libB = library(2, [importPath(21, 2, "/photos/b")]);
const libEmpty = library(3, []);

const album = (name: string, mtime = 0): FolderTreeNode => ({
  name,
  path: `/photos/a/${name}`,
  type: "folder",
  has_children: false,
  cover_images: [`/photos/a/${name}/cover.png`],
  cover_versions: [`v-${name}`],
  mtime,
});

const browsePage = (folders: FolderTreeNode[]): BrowseResponse => ({
  folders,
  media: [],
  next_cursor: null,
  next_media_cursor: null,
  total_images: 0,
  total_videos: 0,
  total_assets: 0,
  request_path: null,
  library_id: 1,
  path: "/photos/a",
  index_source: "catalog",
});

const makeClient = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });
const home = { pathname: "/", search: "" };

const run = (client: QueryClient, libraries: RegisteredLibrary[] | undefined, env = {}) =>
  startHomeBrowsePrefetch(client, Promise.resolve(), () => libraries, {
    location: home,
    storage: localStorage,
    ...env,
  });

class FakeImage {
  static created: FakeImage[] = [];
  src = "";
  fetchPriority = "auto";
  decoding = "auto";
  private listeners = new Map<string, () => void>();
  constructor() {
    FakeImage.created.push(this);
  }
  addEventListener(type: string, listener: () => void) {
    this.listeners.set(type, listener);
  }
  fire(type: string) {
    this.listeners.get(type)?.();
  }
}

beforeEach(() => {
  vi.mocked(browseDirectory).mockReset();
  vi.mocked(browseDirectory).mockResolvedValue(browsePage([album("alpha"), album("beta")]));
  FakeImage.created = [];
  vi.stubGlobal("Image", FakeImage);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("resolveHomeBrowseTarget", () => {
  it("uses the persisted library and import path", () => {
    localStorage.setItem(ACTIVE_LIBRARY_STORAGE_KEY, "1");
    localStorage.setItem(ACTIVE_IMPORT_PATH_STORAGE_KEY, "12");
    expect(resolveHomeBrowseTarget([libA, libB], localStorage)).toEqual({ libraryId: 1, path: "/photos/a2" });
  });

  it("falls back to the first import path when the persisted one is gone", () => {
    localStorage.setItem(ACTIVE_LIBRARY_STORAGE_KEY, "1");
    localStorage.setItem(ACTIVE_IMPORT_PATH_STORAGE_KEY, "999");
    expect(resolveHomeBrowseTarget([libA, libB], localStorage)).toEqual({ libraryId: 1, path: "/photos/a" });
  });

  it("uses the only library that has an import path when nothing is persisted", () => {
    expect(resolveHomeBrowseTarget([libEmpty, libB], localStorage)).toEqual({ libraryId: 2, path: "/photos/b" });
  });

  it("ignores a persisted library that no longer exists and still finds the only eligible one", () => {
    localStorage.setItem(ACTIVE_LIBRARY_STORAGE_KEY, "42");
    expect(resolveHomeBrowseTarget([libB], localStorage)).toEqual({ libraryId: 2, path: "/photos/b" });
  });

  it("returns null when it cannot be told: several libraries, none persisted, or no libraries", () => {
    expect(resolveHomeBrowseTarget([libA, libB], localStorage)).toBeNull();
    expect(resolveHomeBrowseTarget([libEmpty], localStorage)).toBeNull();
    expect(resolveHomeBrowseTarget([], localStorage)).toBeNull();
    expect(resolveHomeBrowseTarget(undefined, localStorage)).toBeNull();
    expect(resolveHomeBrowseTarget([libA, libB], undefined)).toBeNull();
  });

  it("ignores malformed persisted ids", () => {
    localStorage.setItem(ACTIVE_LIBRARY_STORAGE_KEY, "1abc");
    expect(resolveHomeBrowseTarget([libA, libB], localStorage)).toBeNull();
  });
});

describe("startHomeBrowsePrefetch", () => {
  beforeEach(() => {
    localStorage.setItem(ACTIVE_LIBRARY_STORAGE_KEY, "1");
    localStorage.setItem(ACTIVE_IMPORT_PATH_STORAGE_KEY, "11");
  });

  it("fetches the root page of the persisted library under the infinite browse query key", async () => {
    const client = makeClient();
    await run(client, [libA, libB]);

    expect(browseDirectory).toHaveBeenCalledTimes(1);
    expect(browseDirectory).toHaveBeenCalledWith(1, "/photos/a", {
      limit: IMAGE_PAGE_SIZE,
      cursor: 0,
      includeOffline: false,
    });
    const cached = client.getQueryData<{ pages: BrowseResponse[]; pageParams: number[] }>(
      queryKeys.browseInfinite(1, "/photos/a", IMAGE_PAGE_SIZE, false),
    );
    expect(cached?.pageParams).toEqual([0]);
    expect(cached?.pages).toHaveLength(1);
    expect(cached?.pages[0].request_path).toBe("/photos/a");
    expect(cached?.pages[0].folders.map((folder) => folder.name)).toEqual(["alpha", "beta"]);
  });

  it("is reused by the mounted useInfiniteBrowseQuery without a second request", async () => {
    const client = makeClient();
    await run(client, [libA]);
    expect(browseDirectory).toHaveBeenCalledTimes(1);

    let result!: ReturnType<typeof useInfiniteBrowseQuery>;
    mount(
      defineComponent({
        setup() {
          result = useInfiniteBrowseQuery(ref(1), ref("/photos/a"));
          return () => h("div");
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
    );

    // The cached page is on screen at once, before any request could have returned.
    expect(result.isSuccess.value).toBe(true);
    expect(result.folders.value.map((folder) => folder.name)).toEqual(["alpha", "beta"]);
    await Promise.resolve();
    expect(browseDirectory).toHaveBeenCalledTimes(1);
  });

  it("is joined, not duplicated, by a query mounted while the prefetch is still in flight", async () => {
    let release!: (page: BrowseResponse) => void;
    vi.mocked(browseDirectory).mockReturnValue(new Promise<BrowseResponse>((resolve) => (release = resolve)));
    const client = makeClient();
    const started = run(client, [libA]);
    await vi.waitFor(() => expect(browseDirectory).toHaveBeenCalledTimes(1));

    let result!: ReturnType<typeof useInfiniteBrowseQuery>;
    mount(
      defineComponent({
        setup() {
          result = useInfiniteBrowseQuery(ref(1), ref("/photos/a"));
          return () => h("div");
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
    );
    expect(result.isLoading.value).toBe(true);

    release(browsePage([album("alpha")]));
    await started;
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(browseDirectory).toHaveBeenCalledTimes(1);
  });

  it("fetches the only library's root when nothing is persisted yet (first visit)", async () => {
    localStorage.clear();
    await run(makeClient(), [libB]);
    expect(browseDirectory).toHaveBeenCalledWith(2, "/photos/b", expect.anything());
  });

  it("falls back silently when no library can be chosen", async () => {
    localStorage.clear();
    const client = makeClient();
    await expect(run(client, [libA, libB])).resolves.toBeUndefined();
    await expect(run(client, undefined)).resolves.toBeUndefined();
    expect(browseDirectory).not.toHaveBeenCalled();
    expect(FakeImage.created).toHaveLength(0);
  });

  it("falls back silently, and lets the mounted query load, when the request fails", async () => {
    vi.mocked(browseDirectory).mockRejectedValueOnce(new Error("boom"));
    const client = makeClient();
    await expect(run(client, [libA])).resolves.toBeUndefined();
    expect(FakeImage.created).toHaveLength(0);

    let result!: ReturnType<typeof useInfiniteBrowseQuery>;
    mount(
      defineComponent({
        setup() {
          result = useInfiniteBrowseQuery(ref(1), ref("/photos/a"));
          return () => h("div");
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
    );
    await vi.waitFor(() => expect(result.isSuccess.value).toBe(true));
    expect(browseDirectory).toHaveBeenCalledTimes(2);
  });

  it("falls back silently when the library list or storage throws", async () => {
    const throwing = {
      getItem: () => {
        throw new Error("denied");
      },
    } as unknown as Storage;
    await expect(run(makeClient(), [libA], { storage: throwing })).resolves.toBeUndefined();
    await expect(
      startHomeBrowsePrefetch(
        makeClient(),
        Promise.resolve(),
        () => {
          throw new Error("no cache");
        },
        { location: home, storage: localStorage },
      ),
    ).resolves.toBeUndefined();
  });

  it("only runs on the gallery home: not on other routes, not on a search URL", async () => {
    await run(makeClient(), [libA], { location: { pathname: "/admin", search: "" } });
    await run(makeClient(), [libA], { location: { pathname: "/", search: "?q=cat" } });
    expect(browseDirectory).not.toHaveBeenCalled();
  });

  it("waits for the library list before looking at it", async () => {
    let ready!: () => void;
    const librariesReady = new Promise<void>((resolve) => (ready = resolve));
    const cache: { libraries?: RegisteredLibrary[] } = {};
    const done = startHomeBrowsePrefetch(makeClient(), librariesReady, () => cache.libraries, {
      location: home,
      storage: localStorage,
    });
    await Promise.resolve();
    expect(browseDirectory).not.toHaveBeenCalled();
    cache.libraries = [libA];
    ready();
    await done;
    expect(browseDirectory).toHaveBeenCalledTimes(1);
  });

  describe("first cover", () => {
    it("requests the first album's cover at high priority with the URL the card uses", async () => {
      await run(makeClient(), [libA]);
      expect(FakeImage.created).toHaveLength(1);
      const image = FakeImage.created[0];
      expect(image.src).toBe(getThumbnailUrl("/photos/a/alpha/cover.png", 512, "v-alpha"));
      expect(image.fetchPriority).toBe("high");
      expect(image.decoding).toBe("async");
    });

    it("starts the request before anything is mounted (the page is not needed for it)", async () => {
      await run(makeClient(), [libA]);
      expect(document.querySelectorAll("img")).toHaveLength(0);
      expect(FakeImage.created[0].src).toContain("/api/thumbnail?");
    });

    it("picks the first folder in the user's sort order, as the grid shows it", async () => {
      localStorage.setItem(SORT_STORAGE_KEY, JSON.stringify({ field: "name", order: "desc" }));
      await run(makeClient(), [libA]);
      expect(FakeImage.created[0].src).toContain(encodeURIComponent("/photos/a/beta/cover.png"));

      FakeImage.created = [];
      vi.mocked(browseDirectory).mockResolvedValue(browsePage([album("alpha", 5), album("beta", 9)]));
      localStorage.setItem(SORT_STORAGE_KEY, JSON.stringify({ field: "date", order: "asc" }));
      await run(makeClient(), [libA]);
      expect(FakeImage.created[0].src).toContain(encodeURIComponent("/photos/a/alpha/cover.png"));
    });

    it("skips the cover when the album strip is collapsed, but still prefetches the page", async () => {
      localStorage.setItem(ALBUMS_COLLAPSED_STORAGE_KEY, "true");
      await run(makeClient(), [libA]);
      expect(browseDirectory).toHaveBeenCalledTimes(1);
      expect(FakeImage.created).toHaveLength(0);
    });

    it("skips folders without a cover and pages without folders", async () => {
      vi.mocked(browseDirectory).mockResolvedValue(
        browsePage([{ ...album("alpha"), cover_images: [], cover_versions: [] }]),
      );
      await run(makeClient(), [libA]);
      expect(FakeImage.created).toHaveLength(0);
    });
  });
});

describe("warmed cover URL matches the album cards", () => {
  // The browser reuses the warm-up request only when the card asks for exactly the same URL.
  it.each([
    ["AlbumCardMobile", AlbumCardMobile],
    ["AlbumCardTablet", AlbumCardTablet],
    ["AlbumCard", AlbumCard],
  ])("%s requests the front cover with the warmed URL", (_name, component) => {
    const folder = album("alpha");
    warmAlbumCover(folder);
    const wrapper = mount(component, { props: { node: folder, priority: true }, attachTo: document.body });
    expect(wrapper.findAll("img").at(-1)!.attributes("src")).toBe(FakeImage.created[0].src);
    wrapper.unmount();
  });
});

describe("warmAlbumCover", () => {
  it("does nothing without a folder or a cover, and never throws", () => {
    warmAlbumCover(undefined);
    warmAlbumCover({ ...album("x"), cover_images: undefined });
    expect(FakeImage.created).toHaveLength(0);

    vi.stubGlobal(
      "Image",
      class {
        constructor() {
          throw new Error("no images here");
        }
      },
    );
    expect(() => warmAlbumCover(album("x"))).not.toThrow();
  });

  it("omits the version parameter when the folder has none", () => {
    warmAlbumCover({ ...album("x"), cover_versions: undefined });
    expect(FakeImage.created[0].src).toBe(getThumbnailUrl("/photos/a/x/cover.png", 512));
  });
});
