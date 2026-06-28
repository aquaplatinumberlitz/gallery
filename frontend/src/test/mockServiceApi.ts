import { vi } from "vitest";

/**
 * Reusable mock module factory for @/services/api composable tests.
 *
 * Purpose:
 * Eliminate the "vi.mock + vi.fn()" boilerplate that every composable test
 * currently duplicates.
 *
 * Guarantees:
 * * Every exported API function is replaced with a vi.fn() stub
 *   (async, sync, and URL helpers all covered)
 * * The returned object is safe to spread into a vi.mock call
 * * Each call creates fresh vi.fn() instances — no cross-test state leak
 *
 * Usage — replace this boilerplate:
 * ```ts
 * vi.mock("@/services/api", async () => {
 *   const actual = await vi.importActual(...);
 *   return { ...actual, createLibrary: vi.fn(), ... };
 * });
 * ```
 *
 * With:
 * ```ts
 * const { mockApiModule } = useMockApiModule();
 * vi.mock("@/services/api", () => mockApiModule);
 * ```
 *
 * Then in beforeEach / individual tests set return values:
 * ```ts
 * vi.mocked(mockApiModule.fetchLibraries).mockResolvedValue([makeLibrary()]);
 * ```
 *
 * Note: Non-function exports (LIBRARY_ERRORS, GalleryAPIError, types) are
 * omitted because composables only import API functions. If a test needs
 * the real constants, spread them from the actual module:
 * ```ts
 * vi.mock("@/services/api", async () => {
 *   const actual = await vi.importActual(...);
 *   return { ...actual, ...mockApiModule };
 * });
 * ```
 *
 * Run when:
 * * writing new composable tests that call @/services/api functions
 * * refactoring existing tests to remove manual vi.mock boilerplate
 */

export interface MockApiModule {
  browseDirectory: ReturnType<typeof vi.fn>;
  listFolderChildren: ReturnType<typeof vi.fn>;
  openFolder: ReturnType<typeof vi.fn>;
  fetchMetadata: ReturnType<typeof vi.fn>;
  unifiedSearch: ReturnType<typeof vi.fn>;
  fetchLibraryInspector: ReturnType<typeof vi.fn>;
  fetchLibraryInspectorMetadata: ReturnType<typeof vi.fn>;
  getImageUrl: ReturnType<typeof vi.fn>;
  getThumbnailUrl: ReturnType<typeof vi.fn>;
  getPreviewUrl: ReturnType<typeof vi.fn>;
  fetchFacets: ReturnType<typeof vi.fn>;
  fetchLandingPages: ReturnType<typeof vi.fn>;
  fetchLibraries: ReturnType<typeof vi.fn>;
  fetchLibrary: ReturnType<typeof vi.fn>;
  fetchLibraryStats: ReturnType<typeof vi.fn>;
  fetchLibraryJobs: ReturnType<typeof vi.fn>;
  fetchGalleryStats: ReturnType<typeof vi.fn>;
  fetchJobs: ReturnType<typeof vi.fn>;
  fetchJob: ReturnType<typeof vi.fn>;
  validateLibraryCreate: ReturnType<typeof vi.fn>;
  validateLibraryUpdate: ReturnType<typeof vi.fn>;
  createLibrary: ReturnType<typeof vi.fn>;
  updateLibrary: ReturnType<typeof vi.fn>;
  scanLibrary: ReturnType<typeof vi.fn>;
  scanAllLibraries: ReturnType<typeof vi.fn>;
  rebuildLibrary: ReturnType<typeof vi.fn>;
  fetchCatalogStatus: ReturnType<typeof vi.fn>;
  fetchLibraryStatusBatch: ReturnType<typeof vi.fn>;
  deleteLibrary: ReturnType<typeof vi.fn>;
  getVideoUrl: ReturnType<typeof vi.fn>;
  getVideoPosterUrl: ReturnType<typeof vi.fn>;
  getLibraryEventsUrl: ReturnType<typeof vi.fn>;
  fetchGeneratedImagesStatus: ReturnType<typeof vi.fn>;
  generateMissingImages: ReturnType<typeof vi.fn>;
  rebuildImportedData: ReturnType<typeof vi.fn>;
  clearImportedData: ReturnType<typeof vi.fn>;
  resetCatalogDatabase: ReturnType<typeof vi.fn>;
  fetchFileHealth: ReturnType<typeof vi.fn>;
  runFileHealthCheck: ReturnType<typeof vi.fn>;
}

export function useMockApiModule(): { mockApiModule: MockApiModule } {
  return vi.hoisted(() => ({
    mockApiModule: {
      browseDirectory: vi.fn(),
      listFolderChildren: vi.fn(),
      openFolder: vi.fn(),
      fetchMetadata: vi.fn(),
      unifiedSearch: vi.fn(),
      fetchLibraryInspector: vi.fn(),
      fetchLibraryInspectorMetadata: vi.fn(),
      getImageUrl: vi.fn(),
      getThumbnailUrl: vi.fn(),
      getPreviewUrl: vi.fn(),
      fetchFacets: vi.fn(),
      fetchLandingPages: vi.fn(),
      fetchLibraries: vi.fn(),
      fetchLibrary: vi.fn(),
      fetchLibraryStats: vi.fn(),
      fetchLibraryJobs: vi.fn(),
      fetchGalleryStats: vi.fn(),
      fetchJobs: vi.fn(),
      fetchJob: vi.fn(),
      validateLibraryCreate: vi.fn(),
      validateLibraryUpdate: vi.fn(),
      createLibrary: vi.fn(),
      updateLibrary: vi.fn(),
      scanLibrary: vi.fn(),
      scanAllLibraries: vi.fn(),
      rebuildLibrary: vi.fn(),
      fetchCatalogStatus: vi.fn(),
      fetchLibraryStatusBatch: vi.fn(),
      deleteLibrary: vi.fn(),
      getVideoUrl: vi.fn(),
      getVideoPosterUrl: vi.fn(),
      getLibraryEventsUrl: vi.fn(),
      fetchGeneratedImagesStatus: vi.fn(),
      generateMissingImages: vi.fn(),
      rebuildImportedData: vi.fn(),
      clearImportedData: vi.fn(),
      resetCatalogDatabase: vi.fn(),
      fetchFileHealth: vi.fn(),
      runFileHealthCheck: vi.fn(),
    } as MockApiModule,
  }));
}
