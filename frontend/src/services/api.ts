import axios, { AxiosError } from "axios";
import type { MetadataResponse, ScanResponse } from "../types";

const API_BASE = import.meta.env.VITE_API_URL || "";

// Error types from backend
export type ErrorType = 
  | 'not_found' 
  | 'not_directory' 
  | 'permission' 
  | 'invalid_file' 
  | 'timeout' 
  | 'server_error'
  | 'network';

export interface APIErrorResponse {
  error: ErrorType;
  message: string;
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

export const getImageUrl = (path: string) =>
  `${API_BASE}/api/image?path=${encodeURIComponent(path)}`;

export const getThumbnailUrl = (path: string, maxSize?: number) => {
  const params = new URLSearchParams({ path });
  if (maxSize) params.set("max_size", String(maxSize));
  return `${API_BASE}/api/thumbnail?${params.toString()}`;
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
