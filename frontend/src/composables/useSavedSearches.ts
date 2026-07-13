import { computed, shallowRef } from "vue";
import type { PersistableSearchRequestV1, SearchQueryRequestV1 } from "@/types";
import {
  canonicalSearchRequestKey,
  isAssetReferenceSearch,
  parseSearchRequestV1,
  persistableSearchRequest,
} from "@/utils/searchRequest";

export const SEARCH_LIBRARY_STORAGE_KEY = "gallery-search-library-v1";
export const MAX_SAVED_SEARCHES = 50;
export const MAX_RECENT_SEARCHES = 20;

export interface SavedSearchRecord {
  id: string;
  name: string;
  request: PersistableSearchRequestV1;
  created_at: number;
  updated_at: number;
}

export interface RecentSearchRecord {
  request: PersistableSearchRequestV1;
  used_at: number;
}

interface SearchLibraryDocument {
  schema_version: 1;
  saved: SavedSearchRecord[];
  recent: RecentSearchRecord[];
}

const emptyDocument = (): SearchLibraryDocument => ({ schema_version: 1, saved: [], recent: [] });

const normalizePersistableRequest = (value: unknown): PersistableSearchRequestV1 | null => {
  const parsed = parseSearchRequestV1({
    ...(value as Record<string, unknown>),
    cursor: null,
    limit: 60,
  });
  return parsed ? persistableSearchRequest(parsed) : null;
};

const normalizeSaved = (value: unknown): SavedSearchRecord | null => {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const request = normalizePersistableRequest(record.request);
  if (
    !request ||
    typeof record.id !== "string" ||
    !record.id ||
    typeof record.name !== "string" ||
    !record.name.trim() ||
    typeof record.created_at !== "number" ||
    typeof record.updated_at !== "number"
  ) {
    return null;
  }
  return {
    id: record.id,
    name: record.name.trim().slice(0, 120),
    request,
    created_at: record.created_at,
    updated_at: record.updated_at,
  };
};

const normalizeRecent = (value: unknown): RecentSearchRecord | null => {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const request = normalizePersistableRequest(record.request);
  if (!request || typeof record.used_at !== "number") return null;
  return { request, used_at: record.used_at };
};

const migrateDocument = (value: unknown): SearchLibraryDocument => {
  if (!value || typeof value !== "object") return emptyDocument();
  const record = value as Record<string, unknown>;
  const savedSource = record.schema_version === 1 ? record.saved : record.savedSearches;
  const recentSource = record.schema_version === 1 ? record.recent : record.recentSearches;
  const saved = Array.isArray(savedSource)
    ? savedSource.map(normalizeSaved).filter((item): item is SavedSearchRecord => item !== null)
    : [];
  const recent = Array.isArray(recentSource)
    ? recentSource.map(normalizeRecent).filter((item): item is RecentSearchRecord => item !== null)
    : [];
  return {
    schema_version: 1,
    saved: saved.slice(0, MAX_SAVED_SEARCHES),
    recent: recent.slice(0, MAX_RECENT_SEARCHES),
  };
};

const readDocument = (): SearchLibraryDocument => {
  if (typeof window === "undefined") return emptyDocument();
  try {
    const raw = localStorage.getItem(SEARCH_LIBRARY_STORAGE_KEY);
    if (!raw) return emptyDocument();
    const parsed = JSON.parse(raw);
    const migrated = migrateDocument(parsed);
    if (!parsed || parsed.schema_version !== 1) {
      localStorage.setItem(SEARCH_LIBRARY_STORAGE_KEY, JSON.stringify(migrated));
    }
    return migrated;
  } catch {
    try {
      localStorage.removeItem(SEARCH_LIBRARY_STORAGE_KEY);
    } catch {
      // Storage can remain unavailable in private/restricted browser modes.
    }
    return emptyDocument();
  }
};

const writeDocument = (document: SearchLibraryDocument): boolean => {
  if (typeof window === "undefined") return false;
  try {
    localStorage.setItem(SEARCH_LIBRARY_STORAGE_KEY, JSON.stringify(document));
    return true;
  } catch {
    return false;
  }
};

const newId = (): string =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `search-${Date.now()}-${Math.random().toString(36).slice(2)}`;

export const recordRecentSearch = (request: SearchQueryRequestV1, now = Date.now()): boolean => {
  const persistable = persistableSearchRequest(request);
  if (isAssetReferenceSearch(persistable)) return false;
  const document = readDocument();
  const key = canonicalSearchRequestKey(persistable);
  document.recent = [
    { request: persistable, used_at: now },
    ...document.recent.filter((item) => canonicalSearchRequestKey(item.request) !== key),
  ].slice(0, MAX_RECENT_SEARCHES);
  return writeDocument(document);
};

export function useSavedSearches() {
  const document = shallowRef(readDocument());

  const persist = (next: SearchLibraryDocument): boolean => {
    if (!writeDocument(next)) return false;
    document.value = next;
    return true;
  };

  const save = (name: string, request: SearchQueryRequestV1, now = Date.now()): SavedSearchRecord | null => {
    const trimmedName = name.trim().slice(0, 120);
    const persistable = persistableSearchRequest(request);
    if (!trimmedName || isAssetReferenceSearch(persistable)) return null;
    const key = canonicalSearchRequestKey(persistable);
    const existing = document.value.saved.find((item) => canonicalSearchRequestKey(item.request) === key);
    const record: SavedSearchRecord = existing
      ? { ...existing, name: trimmedName, request: persistable, updated_at: now }
      : { id: newId(), name: trimmedName, request: persistable, created_at: now, updated_at: now };
    const next = {
      ...document.value,
      saved: [record, ...document.value.saved.filter((item) => item.id !== record.id)].slice(0, MAX_SAVED_SEARCHES),
    };
    return persist(next) ? record : null;
  };

  const rename = (id: string, name: string, now = Date.now()): boolean => {
    const trimmedName = name.trim().slice(0, 120);
    if (!trimmedName || !document.value.saved.some((item) => item.id === id)) return false;
    return persist({
      ...document.value,
      saved: document.value.saved.map((item) =>
        item.id === id ? { ...item, name: trimmedName, updated_at: now } : item,
      ),
    });
  };

  const remove = (id: string): boolean =>
    persist({ ...document.value, saved: document.value.saved.filter((item) => item.id !== id) });

  const clearRecent = (): boolean => persist({ ...document.value, recent: [] });

  const refresh = () => {
    document.value = readDocument();
  };

  return {
    saved: computed(() => document.value.saved),
    recent: computed(() => document.value.recent),
    document,
    save,
    rename,
    remove,
    clearRecent,
    refresh,
  };
}
