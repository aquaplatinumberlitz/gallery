import type {
  PersistableSearchRequestV1,
  SearchFiltersV1,
  SearchMode,
  SearchQueryRequestV1,
  SearchScope,
} from "@/types";

export const SEARCH_V2_SCHEMA_VERSION = 1 as const;
export const SEARCH_V2_DEFAULT_LIMIT = 60;

const normalizeCatalogPath = (path: string): string => {
  const normalized = path.trim().replace(/\\/g, "/").replace(/\/+/g, "/");
  return normalized === "/" ? normalized : normalized.replace(/\/$/, "");
};

export const emptySearchFilters = (): SearchFiltersV1 => ({
  prompt_groups: [],
  workflow_groups: [],
});

export const persistableSearchRequest = (request: SearchQueryRequestV1): PersistableSearchRequestV1 => ({
  schema_version: request.schema_version,
  mode: request.mode,
  text: request.text,
  scope: request.scope,
  filters: request.filters,
});

export const canonicalSearchRequestKey = (request: SearchQueryRequestV1 | PersistableSearchRequestV1): string =>
  JSON.stringify("cursor" in request ? persistableSearchRequest(request) : request);

const relativePathWithinRoot = (rootPath: string, candidatePath: string): string | null => {
  const root = normalizeCatalogPath(rootPath);
  const candidate = normalizeCatalogPath(candidatePath || rootPath);
  if (!root || !candidate) return null;
  if (candidate === root) return "";
  const prefix = root === "/" ? "/" : `${root}/`;
  if (!candidate.startsWith(prefix)) return null;
  return candidate.slice(prefix.length);
};

export interface BuildSearchRequestOptions {
  text: string;
  scope: SearchScope;
  libraryId: number | null;
  importPathId: number | null;
  importRootPath: string;
  folderPath: string;
  mode?: SearchMode;
  filters?: SearchFiltersV1;
  limit?: number;
}

export const buildSearchScopeV1 = (options: Omit<BuildSearchRequestOptions, "text" | "mode" | "filters" | "limit">) => {
  let scope: SearchQueryRequestV1["scope"];
  if (options.scope === "all") {
    scope = { kind: "all" };
  } else if (options.scope === "library") {
    if (!options.libraryId) return null;
    scope = { kind: "library", library_id: options.libraryId };
  } else {
    if (!options.libraryId || !options.importPathId) return null;
    const relativePath = relativePathWithinRoot(options.importRootPath, options.folderPath);
    if (relativePath === null) return null;
    scope = {
      kind: "folder",
      library_id: options.libraryId,
      import_path_id: options.importPathId,
      relative_path: relativePath,
    };
  }

  return scope;
};

export const buildSearchRequestV1 = (options: BuildSearchRequestOptions): SearchQueryRequestV1 | null => {
  const text = options.text.trim();
  const filters = options.filters ?? emptySearchFilters();
  const hasFilters = filters.prompt_groups.length > 0 || filters.workflow_groups.length > 0;
  if (!text && !hasFilters) return null;
  const scope = buildSearchScopeV1(options);
  if (!scope) return null;

  return {
    schema_version: SEARCH_V2_SCHEMA_VERSION,
    mode: options.mode ?? "lexical",
    text,
    scope,
    filters,
    cursor: null,
    limit: options.limit ?? SEARCH_V2_DEFAULT_LIMIT,
  };
};

export const parseSearchRequestV1 = (value: unknown): SearchQueryRequestV1 | null => {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  if (record.schema_version !== 1 || !["lexical", "workflow"].includes(String(record.mode))) return null;
  if (typeof record.text !== "string" || record.text.length > 512) return null;
  if (!record.scope || typeof record.scope !== "object") return null;
  const scope = record.scope as Record<string, unknown>;
  if (scope.kind === "folder") {
    if (
      !Number.isSafeInteger(scope.library_id) ||
      Number(scope.library_id) < 1 ||
      !Number.isSafeInteger(scope.import_path_id) ||
      Number(scope.import_path_id) < 1 ||
      typeof scope.relative_path !== "string" ||
      scope.relative_path.length > 4096 ||
      scope.relative_path.includes("\0") ||
      scope.relative_path.startsWith("/") ||
      scope.relative_path.startsWith("\\") ||
      scope.relative_path.split(/[\\/]/).some((part) => part === "." || part === "..")
    ) {
      return null;
    }
  } else if (scope.kind === "library") {
    if (!Number.isSafeInteger(scope.library_id) || Number(scope.library_id) < 1) return null;
  } else if (scope.kind !== "all") {
    return null;
  }
  const filters = record.filters as SearchFiltersV1 | undefined;
  if (!filters || !Array.isArray(filters.prompt_groups) || !Array.isArray(filters.workflow_groups)) return null;
  if (
    filters.prompt_groups.length > 8 ||
    filters.prompt_groups.some(
      (group) =>
        !group ||
        !["positive", "negative"].includes(group.kind) ||
        typeof group.value_id !== "string" ||
        !/^[A-Za-z0-9_-]{43}$/.test(group.value_id),
    )
  ) {
    return null;
  }
  const propertyPattern = /^[A-Za-z_][A-Za-z0-9_]*$/;
  const operators = ["eq", "prefix", "contains", "gt", "gte", "lt", "lte"];
  if (
    filters.workflow_groups.length > 4 ||
    filters.workflow_groups.some(
      (group) =>
        !group ||
        typeof group.node_type !== "string" ||
        group.node_type.length > 128 ||
        !propertyPattern.test(group.node_type) ||
        !Array.isArray(group.predicates) ||
        group.predicates.length < 1 ||
        group.predicates.length > 8 ||
        group.predicates.some(
          (predicate) =>
            !predicate ||
            typeof predicate.property !== "string" ||
            predicate.property.length > 128 ||
            !propertyPattern.test(predicate.property) ||
            !operators.includes(predicate.op) ||
            !["string", "number", "boolean"].includes(typeof predicate.value) ||
            (typeof predicate.value === "string" && predicate.value.length > 512) ||
            (typeof predicate.value === "number" && !Number.isFinite(predicate.value)),
        ),
    )
  ) {
    return null;
  }
  const limit = record.limit ?? SEARCH_V2_DEFAULT_LIMIT;
  if (!Number.isInteger(limit) || Number(limit) < 1 || Number(limit) > 100) return null;
  if (
    record.cursor !== undefined &&
    record.cursor !== null &&
    (typeof record.cursor !== "string" || record.cursor.length > 2048)
  ) {
    return null;
  }
  const request = record as unknown as SearchQueryRequestV1;
  if (new TextEncoder().encode(JSON.stringify(request)).length > 32 * 1024) return null;
  return request;
};

export const isAssetReferenceSearch = (request: PersistableSearchRequestV1): boolean =>
  "asset_reference" in (request as unknown as Record<string, unknown>);
