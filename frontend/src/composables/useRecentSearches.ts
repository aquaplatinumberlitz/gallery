import { computed, getCurrentInstance, onMounted, onUnmounted, shallowRef } from "vue";
import type { PersistableSearchRequestV1, SearchQueryRequestV1 } from "@/types";
import {
  canonicalSearchRequestKey,
  isAssetReferenceSearch,
  parseSearchRequestV1,
  persistableSearchRequest,
} from "@/utils/searchRequest";

export const RECENT_SEARCHES_STORAGE_KEY = "gallery-recent-searches-v1";
export const LEGACY_SEARCH_LIBRARY_STORAGE_KEY = "gallery-search-library-v1";
export const RECENT_SEARCHES_CHANGE_EVENT = "gallery-recent-searches-change";
export const MAX_RECENT_SEARCHES = 20;

export interface RecentSearchRecord {
  request: PersistableSearchRequestV1;
  used_at: number;
}

interface RecentSearchesDocument {
  schema_version: 1;
  recent: RecentSearchRecord[];
}

const emptyDocument = (): RecentSearchesDocument => ({ schema_version: 1, recent: [] });

const normalizePersistableRequest = (value: unknown): PersistableSearchRequestV1 | null => {
  const parsed = parseSearchRequestV1({
    ...(value as Record<string, unknown>),
    cursor: null,
    limit: 60,
  });
  return parsed ? persistableSearchRequest(parsed) : null;
};

const normalizeRecent = (value: unknown): RecentSearchRecord | null => {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const request = normalizePersistableRequest(record.request);
  if (!request || typeof record.used_at !== "number") return null;
  return { request, used_at: record.used_at };
};

const migrateDocument = (value: unknown): RecentSearchesDocument => {
  if (!value || typeof value !== "object") return emptyDocument();
  const record = value as Record<string, unknown>;
  const recentSource = Array.isArray(record.recent) ? record.recent : record.recentSearches;
  const recent = Array.isArray(recentSource)
    ? recentSource.map(normalizeRecent).filter((item): item is RecentSearchRecord => item !== null)
    : [];
  return { schema_version: 1, recent: recent.slice(0, MAX_RECENT_SEARCHES) };
};

const writeDocument = (document: RecentSearchesDocument): boolean => {
  if (typeof window === "undefined") return false;
  try {
    localStorage.setItem(RECENT_SEARCHES_STORAGE_KEY, JSON.stringify(document));
    return true;
  } catch {
    return false;
  }
};

const readDocument = (): RecentSearchesDocument => {
  if (typeof window === "undefined") return emptyDocument();

  try {
    const current = localStorage.getItem(RECENT_SEARCHES_STORAGE_KEY);
    if (current) {
      const migrated = migrateDocument(JSON.parse(current));
      localStorage.setItem(RECENT_SEARCHES_STORAGE_KEY, JSON.stringify(migrated));
      return migrated;
    }

    const legacy = localStorage.getItem(LEGACY_SEARCH_LIBRARY_STORAGE_KEY);
    if (!legacy) return emptyDocument();
    const migrated = migrateDocument(JSON.parse(legacy));
    writeDocument(migrated);
    return migrated;
  } catch {
    try {
      localStorage.removeItem(RECENT_SEARCHES_STORAGE_KEY);
    } catch {
      // Storage can remain unavailable in private or restricted browser modes.
    }
    return emptyDocument();
  }
};

const notifyRecentSearchesChange = () => {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(RECENT_SEARCHES_CHANGE_EVENT));
};

export const recordRecentSearch = (request: SearchQueryRequestV1, now = Date.now()): boolean => {
  const persistable = persistableSearchRequest(request);
  if (isAssetReferenceSearch(persistable)) return false;
  const document = readDocument();
  const key = canonicalSearchRequestKey(persistable);
  document.recent = [
    { request: persistable, used_at: now },
    ...document.recent.filter((item) => canonicalSearchRequestKey(item.request) !== key),
  ].slice(0, MAX_RECENT_SEARCHES);
  const written = writeDocument(document);
  if (written) notifyRecentSearchesChange();
  return written;
};

export function useRecentSearches() {
  const document = shallowRef(readDocument());

  const persist = (next: RecentSearchesDocument): boolean => {
    if (!writeDocument(next)) return false;
    document.value = next;
    notifyRecentSearchesChange();
    return true;
  };

  const clear = (): boolean => persist(emptyDocument());
  const refresh = () => {
    document.value = readDocument();
  };

  if (getCurrentInstance()) {
    onMounted(() => window.addEventListener(RECENT_SEARCHES_CHANGE_EVENT, refresh));
    onUnmounted(() => window.removeEventListener(RECENT_SEARCHES_CHANGE_EVENT, refresh));
  }

  return {
    recent: computed(() => document.value.recent),
    clear,
    refresh,
  };
}
