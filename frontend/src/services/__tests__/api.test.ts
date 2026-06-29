import type { AxiosError } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors: { response: { use: vi.fn() } },
  },
}));

vi.mock("axios", async () => {
  const actual = await vi.importActual<typeof import("axios")>("axios");
  return {
    ...actual,
    default: { ...actual.default, create: vi.fn(() => mockApi) },
  };
});

import {
  browseDirectory,
  clearImportedData,
  createLibrary,
  deleteLibrary,
  fetchCatalogStatus,
  fetchFacets,
  fetchFileHealth,
  fetchGalleryStats,
  fetchGeneratedImagesStatus,
  fetchJob,
  fetchJobs,
  fetchLandingPages,
  fetchLibraries,
  fetchLibrary,
  fetchLibraryInspector,
  fetchLibraryInspectorMetadata,
  fetchLibraryJobs,
  fetchLibraryStats,
  fetchLibraryStatusBatch,
  fetchMaintenanceRuntime,
  fetchMetadata,
  GalleryAPIError,
  generateMissingImages,
  getImageUrl,
  getLibraryEventsUrl,
  getPreviewUrl,
  getThumbnailUrl,
  getVideoPosterUrl,
  getVideoUrl,
  listFolderChildren,
  LIBRARY_ERRORS,
  openFolder,
  rebuildImportedData,
  resetCatalogDatabase,
  runFileHealthCheck,
  scanAllLibraries,
  scanLibrary,
  unifiedSearch,
  updateLibrary,
  validateLibraryCreate,
  validateLibraryUpdate,
} from "../api";

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// GalleryAPIError.fromAxiosError
// ---------------------------------------------------------------------------

describe("GalleryAPIError", () => {
  it.each([
    ["library_overlap", "library_overlap"],
    ["library_busy", "library_busy"],
    ["permission", "permission"],
    ["invalid_file", "invalid_file"],
    ["confirmation_required", "confirmation_required"],
    ["maintenance_busy", "maintenance_busy"],
  ])("maps %s error", (errorCode, expectedType) => {
    const err = { response: { data: { detail: { error: errorCode, message: "msg" } } } } as unknown as AxiosError;
    expect(GalleryAPIError.fromAxiosError(err).type).toBe(expectedType);
  });

  it("maps library_not_registered to user-friendly message", () => {
    const error = {
      response: { data: { detail: { error: "library_not_registered", message: "msg" } } },
    } as unknown as AxiosError;
    const apiError = GalleryAPIError.fromAxiosError(error);
    expect(apiError.type).toBe("library_not_registered");
    expect(apiError.userMessage).toBe(LIBRARY_ERRORS.library_not_registered);
  });

  it("parses FastAPI detail wrapped error", () => {
    const err = { response: { data: { detail: { error: "bad_request", message: "bad" } } } } as unknown as AxiosError;
    expect(GalleryAPIError.fromAxiosError(err).type).toBe("bad_request");
  });

  it("handles data without detail wrapper", () => {
    const err = { response: { data: { error: "not_found", message: "gone" } } } as unknown as AxiosError;
    expect(GalleryAPIError.fromAxiosError(err).type).toBe("not_found");
  });

  it("maps maintenance_busy to an actionable message", () => {
    const err = {
      response: {
        data: { detail: { error: "maintenance_busy", message: "Maintenance cannot run while jobs are active" } },
      },
    } as unknown as AxiosError;
    const apiError = GalleryAPIError.fromAxiosError(err);
    expect(apiError.type).toBe("maintenance_busy");
    expect(apiError.userMessage).toBe("Maintenance is busy");
    expect(apiError.suggestion).toBe("Maintenance cannot run while jobs are active");
    expect(apiError.canRetry).toBe(false);
  });

  it("returns timeout for ECONNABORTED", () => {
    const err = { code: "ECONNABORTED", message: "timeout" } as AxiosError;
    const r = GalleryAPIError.fromAxiosError(err);
    expect(r.type).toBe("timeout");
    expect(r.canRetry).toBe(true);
  });

  it("returns network for Network Error", () => {
    const err = { message: "Network Error" } as AxiosError;
    const r = GalleryAPIError.fromAxiosError(err);
    expect(r.type).toBe("network");
    expect(r.canRetry).toBe(true);
  });

  it("falls back to server_error for unknown types", () => {
    const err = { response: { data: { detail: { error: "bogus", message: "?" } } } } as unknown as AxiosError;
    const r = GalleryAPIError.fromAxiosError(err);
    expect(r.type).toBe("server_error");
    expect(r.canRetry).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// URL helpers
// ---------------------------------------------------------------------------

describe("URL helpers", () => {
  it.each([
    ["getImageUrl", "/a.jpg", "/api/image?path=%2Fa.jpg"],
    ["getVideoUrl", "/v.mp4", "/api/video?path=%2Fv.mp4"],
    ["getVideoPosterUrl", "/v.mp4", "/api/video/poster?path=%2Fv.mp4"],
    ["getLibraryEventsUrl", undefined, "/api/events"],
  ] as const)("%s(%j) => %s", (fn, path, expected) => {
    expect(({ getImageUrl, getVideoUrl, getVideoPosterUrl, getLibraryEventsUrl } as any)[fn](path)).toBe(expected);
  });

  it("getThumbnailUrl default edge", () => {
    const url = getThumbnailUrl("/a.png");
    expect(url).toContain("/api/thumbnail");
    expect(url).toContain("max_long_edge=512");
  });
  it("getThumbnailUrl custom edge", () => {
    expect(getThumbnailUrl("/a.png", 256)).toContain("max_long_edge=256");
  });
  it("getPreviewUrl", () => {
    const url = getPreviewUrl("/a.png");
    expect(url).toContain("/api/preview");
    expect(url).toContain("max_long_edge=1440");
  });
});

// ---------------------------------------------------------------------------
// Browse and folder endpoints
// ---------------------------------------------------------------------------

describe("browseDirectory", () => {
  it("sends library_id and path", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { folders: [], media: [], next_media_cursor: null, next_cursor: null } });
    const r = await browseDirectory(4, "/photos", { limit: 100, cursor: 0 });
    expect(mockApi.get).toHaveBeenCalledWith("/api/browse", {
      params: { library_id: 4, path: "/photos", limit: 100, cursor: 0 },
    });
    expect(r.next_cursor).toBeNull();
  });
  it("handles null path", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { folders: [], media: [], next_cursor: null } });
    await browseDirectory(4, null);
    expect(mockApi.get).toHaveBeenCalledWith("/api/browse", { params: { library_id: 4 } });
  });
  it("passes include_offline", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { folders: [], media: [], next_cursor: null, next_media_cursor: null } });
    await browseDirectory(4, "/p", { includeOffline: true });
    expect(mockApi.get).toHaveBeenCalledWith("/api/browse", {
      params: { library_id: 4, path: "/p", include_offline: true },
    });
  });
});

describe("listFolderChildren", () => {
  it("sends path param", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { folders: [] } });
    const r = await listFolderChildren("/p");
    expect(r).toEqual({ folders: [] });
    expect(mockApi.get).toHaveBeenCalledWith("/api/folders", { params: { path: "/p" } });
  });
});

describe("openFolder", () => {
  it("posts to open-folder", async () => {
    mockApi.post.mockResolvedValueOnce({});
    await openFolder("/p");
    expect(mockApi.post).toHaveBeenCalledWith("/api/open-folder", null, { params: { path: "/p" } });
  });
});

// ---------------------------------------------------------------------------
// Metadata and search
// ---------------------------------------------------------------------------

describe("fetchMetadata", () => {
  it("GET /api/metadata with path", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { prompt: "test" } });
    const r = await fetchMetadata("/a.png");
    expect(r).toEqual({ prompt: "test" });
    expect(mockApi.get).toHaveBeenCalledWith("/api/metadata", { params: { path: "/a.png" }, signal: undefined });
  });
});

describe("unifiedSearch", () => {
  it("GET /api/search with defaults", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { query: "cat", total: 0, results: [] } });
    const r = await unifiedSearch("cat");
    expect(mockApi.get).toHaveBeenCalledWith("/api/search", {
      params: { q: "cat", scope: "current", limit: 50 },
    });
    expect(r.query).toBe("cat");
  });
  it("passes scope and path", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { query: "", total: 0, results: [] } });
    await unifiedSearch("*", { scope: "all", path: "/p", limit: 10 });
    expect(mockApi.get).toHaveBeenCalledWith("/api/search", {
      params: { q: "*", scope: "all", path: "/p", limit: 10 },
    });
  });
});

// ---------------------------------------------------------------------------
// Library inspector
// ---------------------------------------------------------------------------

describe("fetchLibraryInspector", () => {
  it("GET /api/library/inspector with defaults", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { rows: [], truncated: false } });
    const r = await fetchLibraryInspector();
    expect(mockApi.get).toHaveBeenCalledWith("/api/library/inspector", {
      params: { q: "", scope: "current", limit: 200, sort: "date_desc" },
    });
    expect(r.truncated).toBe(false);
  });
  it("passes cursor and omits path for scope=all", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { rows: [] } });
    await fetchLibraryInspector({ scope: "all", path: "/p", cursor: "abc" });
    expect(mockApi.get).toHaveBeenCalledWith("/api/library/inspector", {
      params: { q: "", scope: "all", limit: 200, sort: "date_desc", cursor: "abc" },
    });
  });
});

describe("fetchLibraryInspectorMetadata", () => {
  it("GET /api/library/inspector/metadata", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { prompt: "x" } });
    const r = await fetchLibraryInspectorMetadata("/a.png");
    expect(r).toEqual({ prompt: "x" });
    expect(mockApi.get).toHaveBeenCalledWith("/api/library/inspector/metadata", { params: { path: "/a.png" } });
  });
});

// ---------------------------------------------------------------------------
// Facets and landing pages
// ---------------------------------------------------------------------------

describe("fetchFacets", () => {
  it("GET /api/facets", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { facets: {} } });
    const r = await fetchFacets("/p");
    expect(r).toEqual({ facets: {} });
    expect(mockApi.get).toHaveBeenCalledWith("/api/facets", { params: { path: "/p" } });
  });
});

describe("fetchLandingPages", () => {
  it("GET /api/landing-pages", async () => {
    mockApi.get.mockResolvedValueOnce({ data: ["/albums"] });
    const r = await fetchLandingPages();
    expect(r).toEqual(["/albums"]);
  });
});

// ---------------------------------------------------------------------------
// Libraries CRUD
// ---------------------------------------------------------------------------

describe("fetchLibraries", () => {
  it("GET /api/libraries", async () => {
    mockApi.get.mockResolvedValueOnce({ data: [] });
    const r = await fetchLibraries();
    expect(r).toEqual([]);
    expect(mockApi.get).toHaveBeenCalledWith("/api/libraries");
  });
});

describe("fetchLibrary", () => {
  it("GET /api/libraries/:id", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { id: 4 } });
    const r = await fetchLibrary(4);
    expect(r).toEqual({ id: 4 });
    expect(mockApi.get).toHaveBeenCalledWith("/api/libraries/4");
  });
});

describe("createLibrary", () => {
  it("POST /api/libraries", async () => {
    mockApi.post.mockResolvedValueOnce({ data: { id: 5 } });
    const r = await createLibrary({ import_paths: ["/p"] });
    expect(r).toEqual({ id: 5 });
    expect(mockApi.post).toHaveBeenCalledWith("/api/libraries", { import_paths: ["/p"] });
  });
});

describe("updateLibrary", () => {
  it("PATCH /api/libraries/:id", async () => {
    mockApi.patch.mockResolvedValueOnce({ data: { id: 4, name: "New" } });
    const r = await updateLibrary(4, { name: "New" });
    expect(r).toEqual({ id: 4, name: "New" });
    expect(mockApi.patch).toHaveBeenCalledWith("/api/libraries/4", { name: "New" });
  });
});

describe("deleteLibrary", () => {
  it("DELETE /api/libraries/:id with confirm", async () => {
    mockApi.delete.mockResolvedValueOnce({});
    await deleteLibrary(4);
    expect(mockApi.delete).toHaveBeenCalledWith("/api/libraries/4", { params: { confirm: true } });
  });
});

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

describe("validateLibraryCreate", () => {
  it("POST /api/libraries/validate", async () => {
    mockApi.post.mockResolvedValueOnce({ data: { is_valid: true } });
    const r = await validateLibraryCreate({ import_paths: ["/p"] });
    expect(r).toEqual({ is_valid: true });
  });
});

describe("validateLibraryUpdate", () => {
  it("POST /api/libraries/:id/validate", async () => {
    mockApi.post.mockResolvedValueOnce({ data: { is_valid: false } });
    const r = await validateLibraryUpdate(4, { name: "X" });
    expect(r).toEqual({ is_valid: false });
    expect(mockApi.post).toHaveBeenCalledWith("/api/libraries/4/validate", { name: "X" });
  });
});

// ---------------------------------------------------------------------------
// Scan and rebuild
// ---------------------------------------------------------------------------

describe("scanLibrary", () => {
  it("without scope", async () => {
    mockApi.post.mockResolvedValueOnce({ data: { state: "queued" } });
    await scanLibrary(4);
    expect(mockApi.post).toHaveBeenCalledWith("/api/libraries/4/scan", undefined);
  });
  it("with scope", async () => {
    mockApi.post.mockResolvedValueOnce({ data: { state: "queued" } });
    await scanLibrary(4, "/p");
    expect(mockApi.post).toHaveBeenCalledWith("/api/libraries/4/scan", { scope_path: "/p" });
  });
});

describe("scanAllLibraries", () => {
  it("POST /api/libraries/scan-all", async () => {
    mockApi.post.mockResolvedValueOnce({ data: { libraries: [4] } });
    const r = await scanAllLibraries();
    expect(r).toEqual({ libraries: [4] });
  });
});

// ---------------------------------------------------------------------------
// Status endpoints
// ---------------------------------------------------------------------------

describe("fetchCatalogStatus", () => {
  it("with scope", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { contract_version: 1, status: {} } });
    const r = await fetchCatalogStatus(4, "/p");
    expect(r).toEqual({ contract_version: 1, status: {} });
    expect(mockApi.get).toHaveBeenCalledWith("/api/libraries/4/status", { params: { scope_path: "/p" } });
  });
  it("without scope", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { contract_version: 1, status: {} } });
    await fetchCatalogStatus(4);
    expect(mockApi.get).toHaveBeenCalledWith("/api/libraries/4/status", { params: {} });
  });
});

describe("fetchLibraryStatusBatch", () => {
  it("GET /api/libraries/status", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { items: [] } });
    const r = await fetchLibraryStatusBatch();
    expect(r).toEqual({ items: [] });
  });
});

// ---------------------------------------------------------------------------
// Stats and jobs
// ---------------------------------------------------------------------------

describe("fetchGalleryStats", () => {
  it("GET /api/stats", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { photos: 10 } });
    const r = await fetchGalleryStats();
    expect(r).toEqual({ photos: 10 });
  });
});

describe("fetchLibraryStats", () => {
  it("GET /api/libraries/:id/stats", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { photos: 5 } });
    const r = await fetchLibraryStats(4);
    expect(r).toEqual({ photos: 5 });
    expect(mockApi.get).toHaveBeenCalledWith("/api/libraries/4/stats");
  });
});

describe("fetchLibraryJobs", () => {
  it("GET /api/libraries/:id/jobs", async () => {
    mockApi.get.mockResolvedValueOnce({ data: [] });
    const r = await fetchLibraryJobs(4);
    expect(r).toEqual([]);
    expect(mockApi.get).toHaveBeenCalledWith("/api/libraries/4/jobs");
  });
});

describe("fetchJobs", () => {
  it("GET /api/jobs", async () => {
    mockApi.get.mockResolvedValueOnce({ data: [] });
    const r = await fetchJobs();
    expect(r).toEqual([]);
  });
});

describe("fetchJob", () => {
  it("GET /api/jobs/:id", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { id: 9 } });
    const r = await fetchJob(9);
    expect(r).toEqual({ id: 9 });
    expect(mockApi.get).toHaveBeenCalledWith("/api/jobs/9");
  });
});

// ---------------------------------------------------------------------------
// Derivative helpers
// ---------------------------------------------------------------------------

describe("fetchGeneratedImagesStatus", () => {
  it("GET /api/derivatives/status", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { ready_derivatives: 0 } });
    const r = await fetchGeneratedImagesStatus(4);
    expect(r).toEqual({ ready_derivatives: 0 });
    expect(mockApi.get).toHaveBeenCalledWith("/api/derivatives/status", { params: { library_id: 4 } });
  });
});

describe("generateMissingImages", () => {
  it("POST /api/derivatives/warm", async () => {
    mockApi.post.mockResolvedValueOnce({ data: { state: "queued" } });
    const r = await generateMissingImages(4);
    expect(r).toEqual({ state: "queued" });
    expect(mockApi.post).toHaveBeenCalledWith("/api/derivatives/warm", null, { params: { library_id: 4 } });
  });
});

describe("rebuildImportedData", () => {
  it("POST /api/maintenance/imported-data/rebuild", async () => {
    mockApi.post.mockResolvedValueOnce({ data: { state: "queued" } });
    const r = await rebuildImportedData();
    expect(r).toEqual({ state: "queued" });
    expect(mockApi.post).toHaveBeenCalledWith("/api/maintenance/imported-data/rebuild", { confirm: true });
  });
});

describe("clearImportedData", () => {
  it("POST /api/maintenance/imported-data/clear", async () => {
    mockApi.post.mockResolvedValueOnce({ data: { catalog_entries_cleared: 0 } });
    const r = await clearImportedData();
    expect(r).toEqual({ catalog_entries_cleared: 0 });
    expect(mockApi.post).toHaveBeenCalledWith("/api/maintenance/imported-data/clear", { confirm: true });
  });
});

describe("resetCatalogDatabase", () => {
  it("POST /api/maintenance/catalog/reset", async () => {
    mockApi.post.mockResolvedValueOnce({ data: { state: "reset" } });
    const r = await resetCatalogDatabase("RESET CATALOG DATABASE");
    expect(r).toEqual({ state: "reset" });
    expect(mockApi.post).toHaveBeenCalledWith("/api/maintenance/catalog/reset", {
      confirm_phrase: "RESET CATALOG DATABASE",
    });
  });
});

// ---------------------------------------------------------------------------
// Maintenance / file health
// ---------------------------------------------------------------------------

describe("fetchFileHealth", () => {
  it("GET /api/maintenance/file-health", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { run: null } });
    const r = await fetchFileHealth();
    expect(r).toEqual({ run: null });
  });
});

describe("runFileHealthCheck", () => {
  it("POST /api/maintenance/file-health/check", async () => {
    mockApi.post.mockResolvedValueOnce({ data: { run: { status: "ok" } } });
    const r = await runFileHealthCheck();
    expect(r).toEqual({ run: { status: "ok" } });
  });
});

// ---------------------------------------------------------------------------
// Maintenance / runtime
// ---------------------------------------------------------------------------

describe("fetchMaintenanceRuntime", () => {
  it("GET /api/maintenance/runtime", async () => {
    mockApi.get.mockResolvedValueOnce({
      data: {
        global_runtime: {
          catalog_worker_count: 1,
          catalog_active_jobs: 0,
          catalog_queue_depth: 0,
          metadata_worker_count: 2,
          metadata_active_jobs: 0,
          metadata_queue_depth: 0,
          metadata_staged_queue_depth: 0,
          derivative_active_jobs: 0,
          derivative_queue_depth: 0,
          watcher_enabled: true,
          watcher_healthy: true,
          watcher_issue: null,
          scheduled_reconciliation_enabled: true,
        },
        metadata_lifecycle: null,
      },
    });
    const r = await fetchMaintenanceRuntime();
    expect(r.global_runtime.catalog_worker_count).toBe(1);
    expect(r.metadata_lifecycle).toBeNull();
    expect(mockApi.get).toHaveBeenCalledWith("/api/maintenance/runtime");
  });
});
