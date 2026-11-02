import type { QueryClient } from "@tanstack/vue-query";
import {
  BROWSE_STALE_TIME_MS,
  browseInfiniteQueryKey,
  fetchBrowsePage,
  getNextBrowsePageParam,
} from "../composables/useInfiniteBrowseQuery";
import { getThumbnailUrl } from "../services/api";
import {
  ACTIVE_IMPORT_PATH_STORAGE_KEY,
  ACTIVE_LIBRARY_STORAGE_KEY,
  getStoredSort,
  orderedImportPaths,
} from "../stores/gallery";
import { sortByPreference } from "./sortNodes";
import type { FileNode, RegisteredLibrary } from "../types";

/**
 * Pre-mount start of the home page's data and first album cover (Track L2/L3 of the perf stretch plan).
 *
 * `main.ts` calls `startHomeBrowsePrefetch` as soon as the entry module runs. Once the library list is
 * known it resolves the library the gallery will open (the same choice `galleryStore.hydrateActiveLibrary`
 * makes) and fetches that library's root browse page with the exact query key and function the mounted
 * `useInfiniteBrowseQuery` uses, so the mounted query finds the page in the cache (or joins the request still
 * in flight) instead of starting its own after the route chunks have loaded and the app has mounted. The
 * first album cover is then requested too, so the image is already on its way when the card renders.
 *
 * Everything here is best effort: no stored library, an unknown library, a collapsed album strip, a failed
 * request or missing storage all end silently, and the mounted app then loads exactly as it did before.
 */

/** Album covers requested ahead of the card: only the first one (the likely LCP element). */
export const WARM_COVER_COUNT = 1;
/** `useStorage` key of the collapsed album strip in `AlbumScroller.vue`; a collapsed strip shows no covers. */
export const ALBUMS_COLLAPSED_STORAGE_KEY = "gallery-albums-collapsed-v2";
/** Edge of the thumbnail the album cards request (`AlbumCard*.vue` default). */
const COVER_THUMBNAIL_EDGE = 512;

// Warm-up images stay referenced until they settle so the browser does not drop the request.
const pendingWarmImages = new Set<HTMLImageElement>();

const readStoredId = (storage: Storage | undefined, key: string): number | null => {
  try {
    const raw = storage?.getItem(key) ?? null;
    if (!raw || !/^[1-9]\d*$/.test(raw)) return null;
    const id = Number(raw);
    return Number.isSafeInteger(id) ? id : null;
  } catch {
    return null;
  }
};

/**
 * The library and root folder the gallery opens on: the persisted selection, or the only library that has an
 * import path (mirrors `hydrateActiveLibrary`, without its side effects). Null when it cannot be told.
 */
export function resolveHomeBrowseTarget(
  libraries: readonly RegisteredLibrary[] | undefined,
  storage: Storage | undefined,
): { libraryId: number; path: string } | null {
  if (!libraries?.length) return null;
  const persistedLibraryId = readStoredId(storage, ACTIVE_LIBRARY_STORAGE_KEY);
  const persistedLibrary = libraries.find((library) => library.id === persistedLibraryId);
  const persistedPaths = persistedLibrary ? orderedImportPaths(persistedLibrary) : [];
  if (persistedLibrary && persistedPaths.length) {
    const persistedImportPathId = readStoredId(storage, ACTIVE_IMPORT_PATH_STORAGE_KEY);
    const importPath = persistedPaths.find((item) => item.id === persistedImportPathId) ?? persistedPaths[0];
    return { libraryId: persistedLibrary.id, path: importPath.path };
  }
  const eligible = libraries.filter((library) => library.import_paths.length > 0);
  if (eligible.length === 1) {
    return { libraryId: eligible[0].id, path: orderedImportPaths(eligible[0])[0].path };
  }
  return null;
}

/** Requests the cover thumbnail with the URL the album card will use, at high priority. */
export function warmAlbumCover(folder: FileNode | undefined): void {
  const cover = folder?.cover_images?.[0];
  if (!cover || typeof Image === "undefined") return;
  try {
    const image = new Image();
    image.decoding = "async";
    image.fetchPriority = "high";
    const release = () => pendingWarmImages.delete(image);
    image.addEventListener("load", release, { once: true });
    image.addEventListener("error", release, { once: true });
    pendingWarmImages.add(image);
    image.src = getThumbnailUrl(cover, COVER_THUMBNAIL_EDGE, folder.cover_versions?.[0]);
  } catch {
    // A warm-up that cannot start changes nothing: the card requests the cover itself.
  }
}

export interface HomeBrowsePrefetchEnv {
  location?: Pick<Location, "pathname" | "search">;
  storage?: Storage;
}

/**
 * Starts the root browse page (and first cover) once `librariesReady` settles. Resolves when the work is done;
 * never rejects. `librariesReady` is the library list prefetch (`queryKeys.libraries()`) `main.ts` already runs.
 */
export async function startHomeBrowsePrefetch(
  client: QueryClient,
  librariesReady: Promise<unknown>,
  libraries: () => readonly RegisteredLibrary[] | undefined,
  env: HomeBrowsePrefetchEnv = {},
): Promise<void> {
  try {
    const location = env.location ?? window.location;
    // Same condition as the route chunk preload in vite.config.ts: only the gallery home at "/". A search URL
    // may select another scope, so it is left to the mounted app.
    if (location.pathname !== "/" || location.search) return;
    const storage = env.storage ?? window.localStorage;
    await librariesReady;
    const target = resolveHomeBrowseTarget(libraries(), storage);
    if (!target) return;

    const queryKey = browseInfiniteQueryKey(target.libraryId, target.path);
    await client.prefetchInfiniteQuery({
      queryKey,
      initialPageParam: 0,
      queryFn: fetchBrowsePage,
      getNextPageParam: getNextBrowsePageParam,
      staleTime: BROWSE_STALE_TIME_MS,
    });

    // The cover is only worth requesting early when the album strip is open. The first card is the first folder
    // in the user's sort order (GalleryGrid sorts the folders client-side).
    if (storage.getItem(ALBUMS_COLLAPSED_STORAGE_KEY) === "true") return;
    const page = client.getQueryData<{ pages: Array<{ folders: FileNode[] }> }>(queryKey)?.pages[0];
    if (!page) return;
    const { field, order } = getStoredSort();
    sortByPreference(page.folders, field, order).slice(0, WARM_COVER_COUNT).forEach(warmAlbumCover);
  } catch {
    // Silent fallback: the mounted app loads its data as before.
  }
}
