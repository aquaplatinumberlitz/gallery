import axios, { AxiosError } from "axios";
import type {
  BrowseResponse,
  FacetsResponse,
  FolderChildrenResponse,
  IndexStatusResponse,
  GalleryStats,
  LibraryCreateRequest,
  LibraryJob,
  LibraryInspectorMetadataResponse,
  LibraryInspectorResponse,
  LibraryProgress,
  LibraryRepairResponse,
  LibraryRebuildResponse,
  LibraryScanResponse,
  LibraryStats,
  LibraryUpdateRequest,
  LibraryValidationResult,
  MetadataResponse,
  RegisteredLibrary,
  ScanAllLibrariesResponse,
  ScanResponse,
  SearchScope,
  SortValue,
  UnifiedSearchResponse,
} from "../types";
import type { LibraryStatusBatchResponse, StatusResponseEnvelope } from "../lib/catalog/status";

const API_BASE = import.meta.env.VITE_API_URL || "";

// Error types from backend
export const LIBRARY_ERRORS = {
  library_not_registered: "Register this folder before browsing it",
  library_not_indexed: "Library registered but not indexed yet. Start scan?",
  library_discovering: "Library is currently being scanned",
  library_overlap: "This folder overlaps with an existing library",
  library_offline: "Library root is offline or unavailable",
  library_error: "Library scan failed",
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
  | "network"
  | LibraryErrorType;

export interface APIErrorResponse {
  error: ErrorType;
  message: string;
}

const isLibraryError = (errorType: string): errorType is LibraryErrorType => errorType in LIBRARY_ERRORS;

export interface IndexRebuildResponse {
  path: string;
  cleared: Record<string, number>;
  rebuild_started: boolean;
  rebuild_started_at: number;
}

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

export const scanDirectory = async (
  path?: string,
  opts?: { limit?: number; mediaCursor?: number },
): Promise<ScanResponse> => {
  try {
    const params: Record<string, string | number> = {};
    if (path) params.path = path;
    if (opts?.limit) params.limit = opts.limit;
    if (typeof opts?.mediaCursor === "number") params.media_cursor = opts.mediaCursor;

    const { data } = await api.get<ScanResponse>("/api/scan", { params });
    return { ...data, next_media_cursor: data.next_media_cursor ?? null };
  } catch (error) {
    if (error instanceof AxiosError) {
      throw GalleryAPIError.fromAxiosError(error);
    }
    throw error;
  }
};

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
  try {
    const params: Record<string, string> = {};
    if (path) params.path = path;

    const { data } = await api.get<FolderChildrenResponse>("/api/folders", { params });
    return data;
  } catch (error) {
    if (error instanceof AxiosError) {
      throw GalleryAPIError.fromAxiosError(error);
    }
    throw error;
  }
};

export const openFolder = async (path: string): Promise<void> => {
  try {
    await api.post("/api/open-folder", null, { params: { path } });
  } catch (error) {
    if (error instanceof AxiosError) {
      throw GalleryAPIError.fromAxiosError(error);
    }
    throw error;
  }
};

export const fetchMetadata = async (path: string, signal?: AbortSignal): Promise<MetadataResponse> => {
  try {
    const { data } = await api.get<MetadataResponse>("/api/metadata", {
      params: { path },
      signal,
    });
    return data;
  } catch (error) {
    if (error instanceof AxiosError) {
      throw GalleryAPIError.fromAxiosError(error);
    }
    throw error;
  }
};

export const unifiedSearch = async (
  query: string,
  opts?: { scope?: SearchScope; path?: string; limit?: number },
): Promise<UnifiedSearchResponse> => {
  try {
    const { data } = await api.get<UnifiedSearchResponse>("/api/search", {
      params: {
        q: query,
        scope: opts?.scope ?? "current",
        path: opts?.path,
        limit: opts?.limit ?? 50,
      },
    });
    return data;
  } catch (error) {
    if (error instanceof AxiosError) {
      throw GalleryAPIError.fromAxiosError(error);
    }
    throw error;
  }
};

export const fetchLibraryInspector = async (opts?: {
  q?: string;
  scope?: SearchScope;
  path?: string;
  limit?: number;
  sort?: SortValue;
  cursor?: string;
}): Promise<LibraryInspectorResponse> => {
  try {
    const requestScope = opts?.scope ?? "current";
    const { data } = await api.get<LibraryInspectorResponse>("/api/library/inspector", {
      params: {
        q: opts?.q ?? "",
        scope: requestScope,
        path: requestScope === "current" ? opts?.path : undefined,
        limit: opts?.limit ?? 200,
        sort: opts?.sort ?? "date_desc",
        cursor: opts?.cursor ?? undefined,
      },
    });
    return data;
  } catch (error) {
    if (error instanceof AxiosError) {
      throw GalleryAPIError.fromAxiosError(error);
    }
    throw error;
  }
};

export const fetchLibraryInspectorMetadata = async (path: string): Promise<LibraryInspectorMetadataResponse> => {
  try {
    const { data } = await api.get<LibraryInspectorMetadataResponse>("/api/library/inspector/metadata", {
      params: { path },
    });
    return data;
  } catch (error) {
    if (error instanceof AxiosError) {
      throw GalleryAPIError.fromAxiosError(error);
    }
    throw error;
  }
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

export const fetchIndexStatus = async (path: string): Promise<IndexStatusResponse> => {
  try {
    const { data } = await api.get<IndexStatusResponse>("/api/index/status", {
      params: { path },
    });
    return data;
  } catch (error) {
    if (error instanceof AxiosError) {
      throw GalleryAPIError.fromAxiosError(error);
    }
    throw error;
  }
};

export const rebuildIndex = async (path: string): Promise<IndexRebuildResponse> => {
  try {
    const { data } = await api.post<IndexRebuildResponse>("/api/index/rebuild", null, {
      params: { path, confirm: true },
    });
    return data;
  } catch (error) {
    if (error instanceof AxiosError) {
      throw GalleryAPIError.fromAxiosError(error);
    }
    throw error;
  }
};

export const fetchFacets = async (path: string): Promise<FacetsResponse> => {
  try {
    const { data } = await api.get<FacetsResponse>("/api/facets", {
      params: { path },
    });
    return data;
  } catch (error) {
    if (error instanceof AxiosError) {
      throw GalleryAPIError.fromAxiosError(error);
    }
    throw error;
  }
};

export const fetchLandingPages = async (): Promise<string[]> => {
  try {
    const { data } = await api.get<string[]>("/api/landing-pages");
    return data;
  } catch (error) {
    if (error instanceof AxiosError) {
      throw GalleryAPIError.fromAxiosError(error);
    }
    throw error;
  }
};

export const fetchLibraries = async (): Promise<RegisteredLibrary[]> => {
  try {
    const { data } = await api.get<RegisteredLibrary[]>("/api/libraries");
    return data;
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const fetchLibrary = async (id: number): Promise<RegisteredLibrary> => {
  try {
    const { data } = await api.get<RegisteredLibrary>(`/api/libraries/${id}`);
    return data;
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const fetchLibraryProgress = async (id: number): Promise<LibraryProgress> => {
  try {
    const { data } = await api.get<LibraryProgress>(`/api/libraries/${id}/progress`);
    return data;
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const fetchLibraryStats = async (id: number): Promise<LibraryStats> => {
  try {
    const { data } = await api.get<LibraryStats>(`/api/libraries/${id}/stats`);
    return data;
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const fetchLibraryJobs = async (id: number): Promise<LibraryJob[]> => {
  try {
    const { data } = await api.get<LibraryJob[]>(`/api/libraries/${id}/jobs`);
    return data;
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const fetchGalleryStats = async (): Promise<GalleryStats> => {
  try {
    const { data } = await api.get<GalleryStats>("/api/stats");
    return data;
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const fetchJobs = async (): Promise<LibraryJob[]> => {
  try {
    const { data } = await api.get<LibraryJob[]>("/api/jobs");
    return data;
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const fetchJob = async (id: number): Promise<LibraryJob> => {
  try {
    const { data } = await api.get<LibraryJob>(`/api/jobs/${id}`);
    return data;
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const validateLibraryCreate = async (
  payload: LibraryCreateRequest | LibraryUpdateRequest,
): Promise<LibraryValidationResult> => {
  try {
    const { data } = await api.post<LibraryValidationResult>("/api/libraries/validate", payload);
    return data;
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const validateLibraryUpdate = async (
  id: number,
  payload: LibraryUpdateRequest,
): Promise<LibraryValidationResult> => {
  try {
    const { data } = await api.post<LibraryValidationResult>(`/api/libraries/${id}/validate`, payload);
    return data;
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const createLibrary = async (payload: LibraryCreateRequest): Promise<RegisteredLibrary> => {
  try {
    const { data } = await api.post<RegisteredLibrary>("/api/libraries", payload);
    return data;
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const updateLibrary = async (id: number, payload: LibraryUpdateRequest): Promise<RegisteredLibrary> => {
  try {
    const { data } = await api.patch<RegisteredLibrary>(`/api/libraries/${id}`, payload);
    return data;
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const scanLibrary = async (id: number, scopePath?: string | null): Promise<LibraryScanResponse> => {
  try {
    const body = scopePath ? { scope_path: scopePath } : undefined;
    const { data } = await api.post<LibraryScanResponse>(`/api/libraries/${id}/scan`, body);
    return data;
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const scanAllLibraries = async (): Promise<ScanAllLibrariesResponse> => {
  try {
    const { data } = await api.post<ScanAllLibrariesResponse>("/api/libraries/scan-all");
    return data;
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const rebuildLibrary = async (id: number, scopePath?: string | null): Promise<LibraryRebuildResponse> => {
  try {
    const body: Record<string, unknown> = { confirm: true };
    if (scopePath) body.scope_path = scopePath;
    const { data } = await api.post<LibraryRebuildResponse>(`/api/libraries/${id}/rebuild`, body);
    return data;
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const repairLibrary = async (id: number): Promise<LibraryRepairResponse> => {
  try {
    const { data } = await api.post<LibraryRepairResponse>(`/api/libraries/${id}/repair`);
    return data;
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const fetchCatalogStatus = async (
  libraryId: number,
  scopePath?: string | null,
): Promise<StatusResponseEnvelope> => {
  try {
    const params: Record<string, string | number> = {};
    if (scopePath) params.scope_path = scopePath;
    const { data } = await api.get<StatusResponseEnvelope>(`/api/libraries/${libraryId}/status`, {
      params,
    });
    return data;
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const fetchLibraryStatusBatch = async (): Promise<LibraryStatusBatchResponse> => {
  try {
    const { data } = await api.get<LibraryStatusBatchResponse>("/api/libraries/status");
    return data;
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const deleteLibrary = async (id: number): Promise<void> => {
  try {
    await api.delete(`/api/libraries/${id}`, { params: { confirm: true } });
  } catch (error) {
    if (error instanceof AxiosError) throw GalleryAPIError.fromAxiosError(error);
    throw error;
  }
};

export const getVideoUrl = (path: string): string => `${API_BASE}/api/video?path=${encodeURIComponent(path)}`;

export const getVideoPosterUrl = (path: string): string =>
  `${API_BASE}/api/video/poster?path=${encodeURIComponent(path)}`;

export const getLibraryEventsUrl = (): string => `${API_BASE}/api/events`;
