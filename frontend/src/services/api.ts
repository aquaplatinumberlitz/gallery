import axios, { AxiosError } from "axios";
import type {
  FacetsResponse,
  FolderChildrenResponse,
  IndexStatusResponse,
  LibraryInspectorMetadataResponse,
  LibraryInspectorResponse,
  MetadataResponse,
  ScanResponse,
  SearchScope,
  UnifiedSearchResponse,
} from "../types";

const API_BASE = import.meta.env.VITE_API_URL || "";

// Error types from backend
export type ErrorType = 
  | 'not_found' 
  | 'not_directory' 
  | 'permission' 
  | 'invalid_file' 
  | 'timeout' 
  | 'server_error'
  | 'confirmation_required'
  | 'network';

export interface APIErrorResponse {
  error: ErrorType;
  message: string;
}

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

  constructor(
    type: ErrorType,
    userMessage: string,
    suggestion: string,
    canRetry: boolean = false
  ) {
    super(userMessage);
    this.name = 'GalleryAPIError';
    this.type = type;
    this.userMessage = userMessage;
    this.suggestion = suggestion;
    this.canRetry = canRetry;
  }

  static fromAxiosError(error: AxiosError): GalleryAPIError {
    // Network error - cannot connect to server
    if (!error.response) {
      if (error.code === 'ECONNABORTED' || error.message.includes('timeout')) {
        return new GalleryAPIError(
          'timeout',
          'Request timed out',
          'Server is taking too long. Please try again.',
          true
        );
      }
      return new GalleryAPIError(
        'network',
        "Can't connect to server",
        'Check if the backend is running and try again.',
        true
      );
    }

    // Parse backend error response
    // FastAPI wraps our error in "detail" field: {"detail": {"error": "...", "message": "..."}}
    const responseData: unknown = error.response.data;
    let parsed: APIErrorResponse | undefined;

    if (responseData && typeof responseData === 'object') {
      const maybeDetail = (responseData as { detail?: unknown }).detail;
      if (maybeDetail && typeof maybeDetail === 'object') {
        parsed = maybeDetail as APIErrorResponse;
      } else {
        parsed = responseData as APIErrorResponse;
      }
    }

    const errorType = parsed?.error || 'server_error';
    
    switch (errorType) {
      case 'not_found':
        return new GalleryAPIError(
          'not_found',
          'Folder not found',
          'The folder may have been moved or deleted.',
          false
        );
      
      case 'not_directory':
        return new GalleryAPIError(
          'not_directory',
          'Not a folder',
          'The selected path is not a valid folder.',
          false
        );
      
      case 'permission':
        return new GalleryAPIError(
          'permission',
          'Access denied',
          "You don't have permission to access this folder.",
          false
        );
      
      case 'invalid_file':
        return new GalleryAPIError(
          'invalid_file',
          'Invalid file',
          'This file type is not supported.',
          false
        );
      
      case 'timeout':
        return new GalleryAPIError(
          'timeout',
          'Taking too long',
          'The folder has too many files. Try a smaller folder.',
          true
        );
      
      case 'confirmation_required':
        return new GalleryAPIError(
          'confirmation_required',
          'Confirmation required',
          'This action requires explicit confirmation.',
          false
        );
      
      default:
        return new GalleryAPIError(
          'server_error',
          'Something went wrong',
          'An unexpected error occurred. Please try again.',
          true
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
  opts?: { imageLimit?: number; imageCursor?: number }
): Promise<ScanResponse> => {
  try {
    const params: Record<string, string | number> = {};
    if (path) params.path = path;
    if (opts?.imageLimit) params.image_limit = opts.imageLimit;
    if (typeof opts?.imageCursor === "number") params.image_cursor = opts.imageCursor;

    const { data } = await api.get<ScanResponse>("/api/scan", { params });
    return data;
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

export const fetchMetadata = async (path: string): Promise<MetadataResponse> => {
  try {
    const { data } = await api.get<MetadataResponse>("/api/metadata", {
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

export const unifiedSearch = async (
  query: string,
  opts?: { scope?: SearchScope; path?: string; limit?: number }
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

export const fetchLibraryInspector = async (
  opts?: { q?: string; scope?: SearchScope; path?: string; limit?: number }
): Promise<LibraryInspectorResponse> => {
  try {
    const requestScope = opts?.scope ?? "current";
    const { data } = await api.get<LibraryInspectorResponse>("/api/library/inspector", {
      params: {
        q: opts?.q ?? "",
        scope: requestScope,
        path: requestScope === "current" ? opts?.path : undefined,
        limit: opts?.limit ?? 200,
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

export const fetchLibraryInspectorMetadata = async (
  path: string
): Promise<LibraryInspectorMetadataResponse> => {
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

export const getImageUrl = (path: string) =>
  `${API_BASE}/api/image?path=${encodeURIComponent(path)}`;

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
