import axios, { AxiosError } from "axios";
import type {
  BrowseResponse,
  FacetsResponse,
  FacetRequestContext,
  FolderChildrenResponse,
  GalleryStats,
  GeneratedImageKind,
  GeneratedImagesStatus,
  GeneratedImagesWarmResponse,
  CatalogResetResponse,
  ImportedDataClearResponse,
  ImportedDataRebuildResponse,
  LibraryCreateRequest,
  LibraryJob,
  LibraryInspectorMetadataResponse,
  LibraryInspectorResponse,
  LibraryScanResponse,
  LibraryStats,
  OfflineLibraryAssetsResponse,
  ForgetOfflineLibraryAssetsResponse,
  LibraryUpdateRequest,
  LibraryValidationResult,
  MetadataResponse,
  RegisteredLibrary,
  ScanAllLibrariesResponse,
  SearchScope,
  SearchQueryRequestV1,
  SortValue,
  PromptPresenceFilter,
  UnifiedSearchResponse,
} from "../types";

export interface FileHealthIssues {
  missing_source_files: number;
  generated_image_missing: number;
  generated_image_abandoned: number;
  metadata_mismatch: number;
  orphaned_work_item: number;
  generated_image_job_mismatch: number;
}

export interface FileHealthRepairs {
  repaired: number;
  requeued: number;
  failed: number;
  skipped: number;
  recovered: number;
  unchanged: number;
}

export interface FileHealthRun {
  id: number;
  trigger: string;
  started_at: number;
  finished_at: number | null;
  status: string;
  error: string | null;
  issues: FileHealthIssues;
  repairs: FileHealthRepairs;
}

export interface FileHealthResponse {
  run: FileHealthRun | null;
}
import type {
  GlobalRuntime,
  LibraryStatusBatchResponse,
  MetadataLifecycle,
  StatusResponseEnvelope,
} from "../lib/catalog/status";

const API_BASE = import.meta.env.VITE_API_URL || "";

// Error types from backend
export const LIBRARY_ERRORS = {
  library_not_registered: "Register this folder before browsing it",
  library_not_indexed: "Library registered but not indexed yet. Update library?",
  library_discovering: "Library is currently being updated",
  library_overlap: "This folder overlaps with an existing library",
  library_offline: "Library root is offline or unavailable",
  library_error: "Library update failed",
  library_busy: "Library is currently busy",
} as const;

export type LibraryErrorType = keyof typeof LIBRARY_ERRORS;

export type ErrorType =
  | "bad_request"
  | "not_found"
  | "not_directory"
  | "permission"
  | "invalid_file"
  | "timeout"
  | "server_error"
  | "confirmation_required"
  | "feature_disabled"
  | "network"
  | LibraryErrorType;

export interface APIErrorResponse {
  error: ErrorType;
  message: string;
}

const isLibraryError = (errorType: string): errorType is LibraryErrorType => errorType in LIBRARY_ERRORS;

export class GalleryAPIError extends Error {
  readonly type: ErrorType;
  readonly userMessage: string;
  readonly suggestion: string;
  readonly canRetry: boolean;

  constructor(type: ErrorType, userMessage: string, suggestion: string, canRetry: boolean = false) {
    super(userMessage);
    this.name = "GalleryAPIError";
    this.type = type;
    this.userMessage = userMessage;
    this.suggestion = suggestion;
    this.canRetry = canRetry;
  }

  static fromAxiosError(error: AxiosError): GalleryAPIError {
    // Network error - cannot connect to server
    if (!error.response) {
      if (error.code === "ECONNABORTED" || error.message.includes("timeout")) {
        return new GalleryAPIError(
          "timeout",
          "Request timed out",
          "Server is taking too long. Please try again.",
          true,
        );
      }
      return new GalleryAPIError(
        "network",
        "Can't connect to server",
        "Check if the backend is running and try again.",
        true,
      );
    }

    // Parse backend error response
    // FastAPI wraps our error in "detail" field: {"detail": {"error": "...", "message": "..."}}
    const responseData: unknown = error.response.data;
    let parsed: APIErrorResponse | undefined;

    if (responseData && typeof responseData === "object") {
      const maybeDetail = (responseData as { detail?: unknown }).detail;
      if (maybeDetail && typeof maybeDetail === "object") {
        parsed = maybeDetail as APIErrorResponse;
      } else {
        parsed = responseData as APIErrorResponse;
      }
    }

    const errorType = parsed?.error || "server_error";

    if (isLibraryError(errorType)) {
      return new GalleryAPIError(
        errorType,
        LIBRARY_ERRORS[errorType],
        parsed?.message || LIBRARY_ERRORS[errorType],
        false,
      );
    }

    switch (errorType) {
      case "bad_request":
        return new GalleryAPIError(
          "bad_request",
          "Invalid request",
          parsed?.message || "Check the supplied values and try again.",
          false,
        );

      case "not_found":
        return new GalleryAPIError(
          "not_found",
          "Folder not found",
          "The folder may have been moved or deleted.",
          false,
        );

      case "not_directory":
        return new GalleryAPIError("not_directory", "Not a folder", "The selected path is not a valid folder.", false);

      case "permission":
        return new GalleryAPIError(
          "permission",
          "Access denied",
          "You don't have permission to access this folder.",
          false,
        );

      case "invalid_file":
        return new GalleryAPIError("invalid_file", "Invalid file", "This file type is not supported.", false);

      case "timeout":
        return new GalleryAPIError(
          "timeout",
          "Taking too long",
          "The folder has too many files. Try a smaller folder.",
          true,
        );

      case "confirmation_required":
        return new GalleryAPIError(
          "confirmation_required",
          "Confirmation required",
          "This action requires explicit confirmation.",
          false,
        );

      default:
        return new GalleryAPIError(
          "server_error",
          "Something went wrong",
          "An unexpected error occurred. Please try again.",
          true,
        );
    }
  }
}

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000, // 30 second timeout
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error instanceof AxiosError) {
      return Promise.reject(GalleryAPIError.fromAxiosError(error));
    }
    return Promise.reject(error);
  },
);

export const browseDirectory = async (
  libraryId: number,
  path?: string | null,
  opts?: { limit?: number; cursor?: number; includeOffline?: boolean },
): Promise<BrowseResponse> => {
  try {
    const params: Record<string, string | number | boolean> = { library_id: libraryId };
    if (path) params.path = path;
    if (opts?.limit) params.limit = opts.limit;
    if (typeof opts?.cursor === "number") params.cursor = opts.cursor;
    if (typeof opts?.includeOffline === "boolean") params.include_offline = opts.includeOffline;

    const { data } = await api.get<BrowseResponse>("/api/browse", { params });
    return {
      ...data,
      next_media_cursor: data.next_media_cursor ?? data.next_cursor ?? null,
      next_cursor: data.next_cursor ?? data.next_media_cursor ?? null,
    };
  } catch (error) {
    if (error instanceof AxiosError) {
      throw GalleryAPIError.fromAxiosError(error);
    }
    throw error;
  }
};

export const listFolderChildren = async (path?: string): Promise<FolderChildrenResponse> => {
  const params: Record<string, string> = {};
  if (path) params.path = path;

  const { data } = await api.get<FolderChildrenResponse>("/api/folders", { params });
  return data;
};

export const openFolder = async (path: string): Promise<void> => {
  await api.post("/api/open-folder", null, { params: { path } });
};

export const fetchMetadata = async (path: string, signal?: AbortSignal): Promise<MetadataResponse> => {
  const { data } = await api.get<MetadataResponse>("/api/metadata", {
    params: { path },
    signal,
  });
  return data;
};

export const unifiedSearch = async (
  query: string,
  opts?: { scope?: SearchScope; path?: string; limit?: number; cursor?: string },
  signal?: AbortSignal,
): Promise<UnifiedSearchResponse> => {
  const { data } = await api.get<UnifiedSearchResponse>("/api/search", {
    params: {
      q: query,
      scope: opts?.scope ?? "current",
      path: opts?.path,
      limit: opts?.limit ?? 50,
      cursor: opts?.cursor,
    },
    signal,
  });
  return data;
};

export const unifiedSearchV2 = async (
  request: SearchQueryRequestV1,
  signal?: AbortSignal,
): Promise<UnifiedSearchResponse> => {
  const { data } = await api.post<UnifiedSearchResponse>("/api/search/query", request, { signal });
  return data;
};

export const fetchLibraryInspector = async (opts?: {
  q?: string;
  scope?: SearchScope;
  path?: string;
  limit?: number;
  sort?: SortValue;
  cursor?: string;
  model?: string;
  prompt?: PromptPresenceFilter;
}): Promise<LibraryInspectorResponse> => {
  const requestScope = opts?.scope ?? "current";
  const { data } = await api.get<LibraryInspectorResponse>("/api/library/inspector", {
    params: {
      q: opts?.q ?? "",
      scope: requestScope,
      path: requestScope === "current" ? opts?.path : undefined,
      limit: opts?.limit ?? 200,
      sort: opts?.sort ?? "date_desc",
      cursor: opts?.cursor ?? undefined,
      model: opts?.model || undefined,
      prompt: opts?.prompt && opts.prompt !== "all" ? opts.prompt : undefined,
    },
  });
  return data;
};

export const fetchLibraryInspectorMetadata = async (path: string): Promise<LibraryInspectorMetadataResponse> => {
  const { data } = await api.get<LibraryInspectorMetadataResponse>("/api/library/inspector/metadata", {
    params: { path },
  });
  return data;
};

export const getImageUrl = (path: string) => `${API_BASE}/api/image?path=${encodeURIComponent(path)}`;

export const getThumbnailUrl = (path: string, maxLongEdge: number = 512) => {
  const params = new URLSearchParams({ path });
  params.set("max_long_edge", String(maxLongEdge));
  return `${API_BASE}/api/thumbnail?${params.toString()}`;
};

export const getPreviewUrl = (path: string, maxLongEdge: number = 1440) => {
  const params = new URLSearchParams({ path });
  params.set("max_long_edge", String(maxLongEdge));
  return `${API_BASE}/api/preview?${params.toString()}`;
};

export const fetchFacets = async (context: FacetRequestContext, signal?: AbortSignal): Promise<FacetsResponse> => {
  const { data } = await api.get<FacetsResponse>("/api/facets", {
    params: {
      scope: context.scope,
      library_id: context.scope === "all" ? undefined : (context.libraryId ?? undefined),
      path: context.scope === "folder" ? (context.path ?? undefined) : undefined,
    },
    signal,
  });
  return data;
};

export const fetchLandingPages = async (): Promise<string[]> => {
  const { data } = await api.get<string[]>("/api/landing-pages");
  return data;
};

export const fetchLibraries = async (): Promise<RegisteredLibrary[]> => {
  const { data } = await api.get<RegisteredLibrary[]>("/api/libraries");
  return data;
};

export const fetchLibrary = async (id: number): Promise<RegisteredLibrary> => {
  const { data } = await api.get<RegisteredLibrary>(`/api/libraries/${id}`);
  return data;
};

export const fetchLibraryStats = async (id: number): Promise<LibraryStats> => {
  const { data } = await api.get<LibraryStats>(`/api/libraries/${id}/stats`);
  return data;
};

export const fetchOfflineLibraryAssets = async (id: number): Promise<OfflineLibraryAssetsResponse> => {
  const { data } = await api.get<OfflineLibraryAssetsResponse>(`/api/libraries/${id}/offline-assets`);
  return data;
};

export const forgetOfflineLibraryAssets = async (id: number): Promise<ForgetOfflineLibraryAssetsResponse> => {
  const { data } = await api.delete<ForgetOfflineLibraryAssetsResponse>(`/api/libraries/${id}/offline-assets`, {
    params: { confirm: true },
  });
  return data;
};

export const fetchLibraryJobs = async (id: number, limit?: number): Promise<LibraryJob[]> => {
  const { data } =
    typeof limit === "number"
      ? await api.get<LibraryJob[]>(`/api/libraries/${id}/jobs`, { params: { limit } })
      : await api.get<LibraryJob[]>(`/api/libraries/${id}/jobs`);
  return data;
};

export const fetchGalleryStats = async (): Promise<GalleryStats> => {
  const { data } = await api.get<GalleryStats>("/api/stats");
  return data;
};

export const fetchJobs = async (limit?: number): Promise<LibraryJob[]> => {
  const { data } =
    typeof limit === "number"
      ? await api.get<LibraryJob[]>("/api/jobs", { params: { limit } })
      : await api.get<LibraryJob[]>("/api/jobs");
  return data;
};

export const fetchJob = async (id: number): Promise<LibraryJob> => {
  const { data } = await api.get<LibraryJob>(`/api/jobs/${id}`);
  return data;
};

export const validateLibraryCreate = async (
  payload: LibraryCreateRequest | LibraryUpdateRequest,
): Promise<LibraryValidationResult> => {
  const { data } = await api.post<LibraryValidationResult>("/api/libraries/validate", payload);
  return data;
};

export const validateLibraryUpdate = async (
  id: number,
  payload: LibraryUpdateRequest,
): Promise<LibraryValidationResult> => {
  const { data } = await api.post<LibraryValidationResult>(`/api/libraries/${id}/validate`, payload);
  return data;
};

export const createLibrary = async (payload: LibraryCreateRequest): Promise<RegisteredLibrary> => {
  const { data } = await api.post<RegisteredLibrary>("/api/libraries", payload);
  return data;
};

export const updateLibrary = async (id: number, payload: LibraryUpdateRequest): Promise<RegisteredLibrary> => {
  const { data } = await api.patch<RegisteredLibrary>(`/api/libraries/${id}`, payload);
  return data;
};

export const scanLibrary = async (id: number, scopePath?: string | null): Promise<LibraryScanResponse> => {
  const body = scopePath ? { scope_path: scopePath } : undefined;
  const { data } = await api.post<LibraryScanResponse>(`/api/libraries/${id}/scan`, body);
  return data;
};

export const scanAllLibraries = async (): Promise<ScanAllLibrariesResponse> => {
  const { data } = await api.post<ScanAllLibrariesResponse>("/api/libraries/scan-all");
  return data;
};

export const fetchCatalogStatus = async (
  libraryId: number,
  scopePath?: string | null,
): Promise<StatusResponseEnvelope> => {
  const params: Record<string, string | number> = {};
  if (scopePath) params.scope_path = scopePath;
  const { data } = await api.get<StatusResponseEnvelope>(`/api/libraries/${libraryId}/status`, {
    params,
  });
  return data;
};

export const fetchLibraryStatusBatch = async (): Promise<LibraryStatusBatchResponse> => {
  const { data } = await api.get<LibraryStatusBatchResponse>("/api/libraries/status");
  return data;
};

export const deleteLibrary = async (id: number): Promise<void> => {
  await api.delete(`/api/libraries/${id}`, { params: { confirm: true } });
};

export const getVideoUrl = (path: string): string => `${API_BASE}/api/video?path=${encodeURIComponent(path)}`;

export const getVideoPosterUrl = (path: string): string =>
  `${API_BASE}/api/video/poster?path=${encodeURIComponent(path)}`;

export const getLibraryEventsUrl = (): string => `${API_BASE}/api/events`;

export const fetchGeneratedImagesStatus = async (libraryId: number): Promise<GeneratedImagesStatus> => {
  const { data } = await api.get<GeneratedImagesStatus>("/api/derivatives/status", {
    params: { library_id: libraryId },
  });
  return data;
};

export const generateMissingImages = async (
  libraryId: number,
  kind?: GeneratedImageKind,
): Promise<GeneratedImagesWarmResponse> => {
  const { data } = await api.post<GeneratedImagesWarmResponse>("/api/derivatives/warm", null, {
    params: { library_id: libraryId, ...(kind ? { kind } : {}) },
  });
  return data;
};

export const clearImportedData = async (): Promise<ImportedDataClearResponse> => {
  const { data } = await api.post<ImportedDataClearResponse>("/api/maintenance/imported-data/clear", {
    confirm: true,
  });
  return data;
};

export const rebuildImportedData = async (): Promise<ImportedDataRebuildResponse> => {
  const { data } = await api.post<ImportedDataRebuildResponse>("/api/maintenance/imported-data/rebuild", {
    confirm: true,
  });
  return data;
};

export const resetCatalogDatabase = async (confirmPhrase: string): Promise<CatalogResetResponse> => {
  const { data } = await api.post<CatalogResetResponse>("/api/maintenance/catalog/reset", {
    confirm_phrase: confirmPhrase,
  });
  return data;
};

export const fetchFileHealth = async (): Promise<FileHealthResponse> => {
  const { data } = await api.get<FileHealthResponse>("/api/maintenance/file-health");
  return data;
};

export const runFileHealthCheck = async (): Promise<FileHealthResponse> => {
  const { data } = await api.post<FileHealthResponse>("/api/maintenance/file-health/check");
  return data;
};

export interface MaintenanceRuntimeResponse {
  global_runtime: GlobalRuntime;
  metadata_lifecycle: MetadataLifecycle | null;
}

export const fetchMaintenanceRuntime = async (): Promise<MaintenanceRuntimeResponse> => {
  const { data } = await api.get<MaintenanceRuntimeResponse>("/api/maintenance/runtime");
  return data;
};
