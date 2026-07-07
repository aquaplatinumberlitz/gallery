/**
 * Canonical asset-type vocabulary on the frontend.
 *
 * The backend `assets` table normalizes every write to one of these values
 * (`backend/metadata_store.py` `_normalize_file_type` / `_upsert_asset_conn`),
 * and the v6->v7 migration back-fills legacy `photo` rows to `image`. The
 * scan/folder/stats endpoints all surface `AssetType` values.
 *
 * `LegacySearchAssetType` below is a separate, wider union kept for the
 * unified-search response shape, where `_format_prompt_rows` in
 * `backend/metadata_store.py` still emits the legacy string `"photo"` and the
 * `file_index`-backed search can in principle still surface a stale `'file'`
 * row from older catalogs. Consumers should normalize via
 * `normalizeAssetType()` from `@/utils/assetType` before comparing against
 * `AssetType`. Do not introduce new emit sites for `"photo"` or `"file"`.
 */
export type AssetType = "folder" | "image" | "video";

export type LegacySearchAssetType = AssetType | "photo" | "file";
export type BrowseAvailabilityState = "unknown" | "available" | "degraded" | "unavailable";
export type BrowseEntryKind = "import_root";

export interface FileNode {
  name: string;
  path: string;
  type: AssetType;
  has_children?: boolean;
  children?: FileNode[];
  isOpen?: boolean;
  cover_images?: string[];
  mtime?: number; // Modified time from backend
  image_count?: number; // Number of images in folder (from backend)
  width?: number | null; // Image width in pixels when available
  height?: number | null; // Image height in pixels when available
  asset_id?: number | null;
  metadata_state?: string | null;
  derivative_ready?: Record<string, boolean> | null;
  duration_ms?: number | null;
  mime_type?: string | null;
  entry_kind?: BrowseEntryKind;
  display_label?: string;
  availability?: BrowseAvailabilityState;
}

export type LibraryErrorCode =
  | "library_not_registered"
  | "library_not_indexed"
  | "library_discovering"
  | "library_overlap"
  | "library_offline"
  | "library_error"
  | "library_busy";

export interface FolderTreeNode extends Omit<FileNode, "type" | "children"> {
  type: "folder";
  children?: FolderTreeNode[];
}

export type SortField = "name" | "date";
export type SortOrder = "asc" | "desc";
export type SortValue = "date_desc" | "date_asc" | "name_asc" | "name_desc";

export interface SortOption {
  field: SortField;
  order: SortOrder;
}

export type GenerationParams = {
  Seed?: string;
  Steps?: string;
  CFG?: string;
  Sampler?: string;
  Scheduler?: string;
  Model?: string;
  AspectRatio?: string;
  Width?: string;
  Height?: string;
  SwarmVersion?: string;
  Lora?: string[];
  // Allow backend to add additional fields in the future
  [key: string]: string | number | string[] | undefined;
};

export interface MetadataModelInfo {
  name?: string;
  param?: string;
  hash?: string;
}

export interface MetadataResponse {
  tool: string;
  prompt: string;
  negative_prompt: string;
  params: GenerationParams;
  models?: MetadataModelInfo[];
  date?: string;
  generation_time?: string;
  width: number | null;
  height: number | null;
  name: string;
  error?: string;
}

export interface BrowseResponse {
  folders: FolderTreeNode[];
  media: FileNode[];
  next_media_cursor: number | null;
  next_cursor?: number | null;
  total_images: number;
  total_videos: number;
  total_assets: number;
  request_path: string | null;
  index_source: "catalog";
  library_id: number;
  path: string | null;
}

export type FolderChildrenResponse = FolderTreeNode[];

export type SearchScope = "current" | "all";

export interface UnifiedSearchResult {
  name: string;
  path: string;
  // Width is `LegacySearchAssetType` (not `AssetType`) because the unified
  // search response is backed by the legacy `file_index` table and
  // `_format_prompt_rows`, which can still emit the un-normalized strings
  // "photo" / "file". See `AssetType` doc above and `normalizeAssetType()`.
  type: LegacySearchAssetType;
  parent_path: string;
  relative_path: string;
  mtime: number;
  width: number | null;
  height: number | null;
  cover_images?: string[];
  image_count?: number;
  match_type: string;
  model: string;
  sampler: string;
  seed: string;
  prompt_snippet: string;
  duration_ms?: number | null;
  mime_type?: string | null;
}

export interface UnifiedSearchResults {
  albums: UnifiedSearchResult[];
  photos: UnifiedSearchResult[];
  videos?: UnifiedSearchResult[];
  prompt: UnifiedSearchResult[];
  media?: UnifiedSearchResult[];
}

export interface UnifiedSearchResponse extends UnifiedSearchResults {
  query: string;
  scope: SearchScope;
  root: string;
  media: UnifiedSearchResult[];
  next_cursor: number | null;
  has_more: boolean;
  returned: number;
  limit: number;
}

export interface FieldFilter {
  field: string;
  operator?: string;
  value: string;
}

export interface FieldedSearchParams {
  filters: FieldFilter[];
}

export interface FacetEntry {
  value: string;
  count: number;
}

export interface FacetsResponse {
  tool?: FacetEntry[];
  model?: FacetEntry[];
  sampler?: FacetEntry[];
  scheduler?: FacetEntry[];
  orientation?: FacetEntry[];
  seed_availability?: FacetEntry[];
  metadata_availability?: FacetEntry[];
  lora?: FacetEntry[];
  folders?: FacetEntry[];
  [key: string]: FacetEntry[] | undefined;
}

export interface LibraryInspectorRow {
  path: string;
  name: string;
  folder: string;
  relative_path: string;
  mtime: number | null;
  width: number | null;
  height: number | null;
  model: string;
  tool: string;
  sampler: string;
  seed: string;
  prompt_preview: string;
  has_prompt: boolean;
  has_negative: boolean;
  has_lora: boolean;
  lora_count: number;
  lora_preview: string;
  metadata_detail_available: boolean;
}

export interface LibraryInspectorResponse {
  root: string;
  scope: SearchScope;
  query: string;
  limit: number;
  generated_at: number;
  total_indexed: number;
  returned: number;
  truncated: boolean;
  next_cursor?: string | null;
  has_more?: boolean;
  sort: string;
  rows: LibraryInspectorRow[];
}

export type LibraryState = "queued" | "discovering" | "indexing" | "ready" | "error" | "offline";

export type LibraryJobState = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface LibraryImportPath {
  id: number;
  library_id: number;
  path: string;
  position: number;
  created_at: number;
  updated_at: number;
}

export interface RegisteredLibrary {
  id: number;
  root_path: string;
  import_paths: LibraryImportPath[];
  exclusion_patterns: string[];
  name: string;
  state: LibraryState;
  watch_enabled: 0 | 1;
  warm_enabled: 0 | 1;
  asset_count: number;
  created_at: number;
  updated_at: number;
  last_scan_at: number | null;
  last_error: string | null;
}

export interface LibraryCreateRequest {
  root_path?: string;
  import_paths?: string[];
  exclusion_patterns?: string[];
  name?: string;
}

export interface LibraryUpdateRequest {
  name?: string;
  import_paths?: string[];
  exclusion_patterns?: string[];
}

export interface LibraryStats {
  photos: number;
  videos: number;
  total_assets: number;
  active_assets: number;
  offline_assets: number;
  usage_bytes: number;
  import_path_count: number;
}

export interface GalleryStats {
  photos: number;
  videos: number;
  total_assets: number;
  active_assets: number;
  offline_assets: number;
  usage_bytes: number;
  library_count: number;
}

export interface LibraryJob {
  id: number;
  library_id: number | null;
  parent_job_id: number | null;
  type: string;
  state: LibraryJobState;
  progress_current: number;
  progress_total: number | null;
  message: string | null;
  error: string | null;
  counters?: Record<string, number>;
  created_at: number;
  updated_at: number;
  started_at: number | null;
  finished_at: number | null;
}

export interface LibraryValidationItem {
  value: string;
  normalized_value: string | null;
  is_valid: boolean;
  message: string | null;
  warnings: string[];
}

export interface LibraryValidationResult {
  is_valid: boolean;
  import_paths: LibraryValidationItem[];
  exclusion_patterns: LibraryValidationItem[];
}

export interface LibraryScanResponse {
  library_id: number;
  job_id: number;
  scope_path: string | null;
  operation: "scan";
  trigger: "initial" | "manual" | "watcher" | "scheduled" | "startup";
  state: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  coalesced: boolean;
}

export interface ScanAllLibrariesResponse {
  job_id: number;
  state: string;
  count: number;
  child_job_ids: number[];
}

export interface LibraryInspectorResource {
  name?: string;
  hash?: string | null;
  resource_hash?: string | null;
  weight?: string | number | null;
  strength?: string | number | null;
}

export interface GeneratedImagesStatus {
  library_id: number;
  total_assets: number;
  ready_derivatives: number;
  expected_derivatives: number;
  by_kind?: Partial<
    Record<
      "thumbnail" | "preview",
      {
        ready_derivatives: number;
        expected_derivatives: number;
      }
    >
  >;
  quota_bytes: number;
  quota_used_bytes: number;
  quota_utilization: number;
}

export type GeneratedImageKind = "thumbnail" | "preview";

export interface GeneratedImagesWarmResponse {
  library_id: number;
  state: string;
  assets: number;
  derivatives_considered: number;
  kind?: GeneratedImageKind | null;
}

export interface ImportedDataClearResponse {
  state: "cleared";
  libraries_preserved: number;
  assets_cleared: number;
  file_index_rows_cleared: number;
  image_metadata_rows_cleared: number;
  image_resource_rows_cleared: number;
  metadata_jobs_cleared: number;
  library_jobs_cleared: number;
  rebuild_staging_rows_cleared: number;
  folder_index_rows_cleared: number;
  integrity_runs_cleared: number;
  derivative_catalog_entries_cleared: number;
  derivative_jobs_cleared: number;
  thumbnail_disk_cache_entries_cleared: number;
  preview_files_deleted: number;
}

export interface ImportedDataRebuildResponse {
  job_id: number;
  state: "running" | "succeeded";
  child_job_ids: number[];
  count: number;
  clear: Omit<ImportedDataClearResponse, "state" | "libraries_preserved">;
}

export interface CatalogResetResponse {
  state: "reset";
  libraries_deleted: number;
  import_paths_deleted: number;
  exclusion_patterns_deleted: number;
  assets_deleted: number;
  image_metadata_rows_deleted: number;
  metadata_jobs_deleted: number;
  library_jobs_deleted: number;
  derivative_catalog_entries_cleared: number;
  derivative_jobs_cleared: number;
  thumbnail_disk_cache_entries_cleared: number;
  preview_files_deleted: number;
  sequences_reset: number;
  sequence_tables_reset: string[];
}

export interface LibraryInspectorMetadataResponse {
  path: string;
  prompt: string;
  negative_prompt: string;
  raw_metadata: Record<string, unknown> | null;
  model: string;
  tool: string;
  sampler: string;
  seed: string;
  width: number | null;
  height: number | null;
  mtime: number | null;
  loras: LibraryInspectorResource[];
  resources: LibraryInspectorResource[];
  metadata_detail_available: boolean;
}
