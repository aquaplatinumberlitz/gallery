import type { AxiosError } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { RegisteredLibrary } from "@/types";

const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("axios", async () => {
  const actual = await vi.importActual<typeof import("axios")>("axios");
  return {
    ...actual,
    default: {
      ...actual.default,
      create: vi.fn(() => mockApi),
    },
  };
});

import {
  browseDirectory,
  createLibrary,
  deleteLibrary,
  fetchLibraries,
  GalleryAPIError,
  LIBRARY_ERRORS,
  scanLibrary,
} from "../api";

const library = {
  id: 4,
  root_path: "/photos",
  import_paths: [],
  exclusion_patterns: [],
  name: "Photos",
  state: "ready",
  watch_enabled: 1,
  warm_enabled: 1,
  asset_count: 12,
  created_at: 1,
  updated_at: 2,
  last_scan_at: 2,
  last_error: null,
} satisfies RegisteredLibrary;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("GalleryAPIError", () => {
  it("maps library error codes to user-friendly messages", () => {
    const error = {
      response: {
        data: {
          detail: {
            error: "library_not_registered",
            message: "Register this root before browsing it",
          },
        },
      },
    } as unknown as AxiosError;

    const apiError = GalleryAPIError.fromAxiosError(error);

    expect(LIBRARY_ERRORS.library_not_registered).toBe("Register this folder before browsing it");
    expect(apiError.type).toBe("library_not_registered");
    expect(apiError.userMessage).toBe("Register this folder before browsing it");
    expect(apiError.suggestion).toBe("Register this root before browsing it");
  });
});

describe("library API", () => {
  it("fetches the registered library list", async () => {
    mockApi.get.mockResolvedValueOnce({ data: [library] });

    await expect(fetchLibraries()).resolves.toEqual([library]);
    expect(mockApi.get).toHaveBeenCalledWith("/api/libraries");
  });

  it("creates a library with the supplied payload", async () => {
    const payload = { import_paths: ["/photos"], name: "Photos" };
    mockApi.post.mockResolvedValueOnce({ data: library });

    await expect(createLibrary(payload)).resolves.toEqual(library);
    expect(mockApi.post).toHaveBeenCalledWith("/api/libraries", payload);
  });

  it("queues a scan for one library", async () => {
    const response = { library_id: 4, job_id: 9, state: "queued" };
    mockApi.post.mockResolvedValueOnce({ data: response });

    await expect(scanLibrary(4)).resolves.toEqual(response);
    expect(mockApi.post).toHaveBeenCalledWith("/api/libraries/4/scan");
  });

  it("browses catalog rows for a library path", async () => {
    const response = {
      folders: [],
      media: [],
      next_media_cursor: null,
      total_images: 0,
      total_videos: 0,
      total_assets: 0,
      index_source: "catalog",
      library_id: 4,
      path: "/photos",
      request_path: "/photos",
    };
    mockApi.get.mockResolvedValueOnce({ data: response });

    await expect(browseDirectory(4, "/photos", { limit: 100, cursor: 0 })).resolves.toEqual({
      ...response,
      next_cursor: null,
    });
    expect(mockApi.get).toHaveBeenCalledWith("/api/browse", {
      params: { library_id: 4, path: "/photos", limit: 100, cursor: 0 },
    });
  });

  it("browses the virtual library root without a path", async () => {
    const response = {
      folders: [],
      media: [],
      next_cursor: null,
      total_images: 0,
      total_videos: 0,
      total_assets: 0,
      index_source: "catalog",
      library_id: 4,
      path: null,
      request_path: null,
    };
    mockApi.get.mockResolvedValueOnce({ data: response });

    await expect(browseDirectory(4, null)).resolves.toEqual({
      ...response,
      next_media_cursor: null,
    });
    expect(mockApi.get).toHaveBeenCalledWith("/api/browse", {
      params: { library_id: 4 },
    });
  });

  it("confirms library deletion", async () => {
    mockApi.delete.mockResolvedValueOnce({ data: undefined });

    await expect(deleteLibrary(4)).resolves.toBeUndefined();
    expect(mockApi.delete).toHaveBeenCalledWith("/api/libraries/4", { params: { confirm: true } });
  });
});
