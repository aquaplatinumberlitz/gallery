import type { LocationQuery, LocationQueryRaw } from "vue-router";
import type { SearchFiltersV1, SearchMode, SearchQueryRequestV1 } from "@/types";
import { parseSearchRequestV1, SEARCH_V2_DEFAULT_LIMIT } from "./searchRequest";

export const SEARCH_URL_KEYS = ["search_v", "q", "scope", "library", "import", "path", "mode", "pg", "wf"] as const;
const MAX_FILTER_PARAM_LENGTH = 16_384;

const scalar = (value: LocationQuery[string]): string | null => (typeof value === "string" ? value : null);

const positiveId = (value: string | null): number | null => {
  if (!value || !/^[1-9]\d*$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : null;
};

const encodeBase64UrlJson = (value: unknown): string => {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
};

const decodeBase64UrlJson = (value: string | null): unknown => {
  if (!value) return [];
  if (value.length > MAX_FILTER_PARAM_LENGTH || !/^[A-Za-z0-9_-]+$/.test(value)) throw new Error("invalid filter");
  const padded = `${value.replace(/-/g, "+").replace(/_/g, "/")}${"=".repeat((4 - (value.length % 4)) % 4)}`;
  const binary = atob(padded);
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes));
};

export const encodeSearchUrlQuery = (request: SearchQueryRequestV1): LocationQueryRaw => {
  const query: LocationQueryRaw = {
    search_v: "1",
    q: request.text,
    scope: request.scope.kind,
    mode: request.mode,
  };
  if (request.scope.kind === "folder") {
    query.library = String(request.scope.library_id);
    query.import = String(request.scope.import_path_id);
    if (request.scope.relative_path) query.path = request.scope.relative_path;
  } else if (request.scope.kind === "library") {
    query.library = String(request.scope.library_id);
  }
  if (request.filters.prompt_groups.length) query.pg = encodeBase64UrlJson(request.filters.prompt_groups);
  if (request.filters.workflow_groups.length) query.wf = encodeBase64UrlJson(request.filters.workflow_groups);
  return query;
};

export interface DecodedSearchUrl {
  request: SearchQueryRequestV1 | null;
  invalid: boolean;
}

export const decodeSearchUrlQuery = (query: LocationQuery): DecodedSearchUrl => {
  if (query.search_v === undefined) return { request: null, invalid: false };
  try {
    if (scalar(query.search_v) !== "1") return { request: null, invalid: true };
    const mode = (scalar(query.mode) ?? "lexical") as SearchMode;
    if (!["lexical", "workflow", "raw"].includes(mode)) return { request: null, invalid: true };
    const kind = scalar(query.scope);
    const libraryId = positiveId(scalar(query.library));
    const importPathId = positiveId(scalar(query.import));
    const relativePath = scalar(query.path) ?? "";
    let scope: SearchQueryRequestV1["scope"];
    if (kind === "folder") {
      if (!libraryId || !importPathId) return { request: null, invalid: true };
      scope = { kind, library_id: libraryId, import_path_id: importPathId, relative_path: relativePath };
    } else if (kind === "library") {
      if (!libraryId) return { request: null, invalid: true };
      scope = { kind, library_id: libraryId };
    } else if (kind === "all") {
      scope = { kind };
    } else {
      return { request: null, invalid: true };
    }
    const filters: SearchFiltersV1 = {
      prompt_groups: decodeBase64UrlJson(scalar(query.pg)) as SearchFiltersV1["prompt_groups"],
      workflow_groups: decodeBase64UrlJson(scalar(query.wf)) as SearchFiltersV1["workflow_groups"],
    };
    const request = parseSearchRequestV1({
      schema_version: 1,
      mode,
      text: scalar(query.q) ?? "",
      scope,
      filters,
      cursor: null,
      limit: SEARCH_V2_DEFAULT_LIMIT,
    });
    return request ? { request, invalid: false } : { request: null, invalid: true };
  } catch {
    return { request: null, invalid: true };
  }
};
