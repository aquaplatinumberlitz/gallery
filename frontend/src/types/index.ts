export interface FileNode {
  name: string;
  path: string;
  type: "folder" | "image";
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
}

export type LibraryErrorCode =
  | "library_not_registered"
  | "library_not_indexed"
  | "library_discovering"
  | "library_overlap"
  | "library_offline"
  | "library_error";

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

export interface ScanResponse {
  folders: FolderTreeNode[];
  images: FileNode[];
  next_cursor: number | null;
  total_images: number;
  request_path?: string;
  index_source?: "warm_db" | "direct_scan" | "mixed";
}

export type FolderChildrenResponse = FolderTreeNode[];

export type SearchScope = "current" | "all";

export interface UnifiedSearchResult {
  name: string;
  path: string;
  type: "folder" | "photo" | "file";
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
}

export interface UnifiedSearchResults {
  albums: UnifiedSearchResult[];
  photos: UnifiedSearchResult[];
  prompt: UnifiedSearchResult[];
}

export interface UnifiedSearchResponse extends UnifiedSearchResults {
  query: string;
  scope: SearchScope;
  root: string;
}

export interface IndexStatusResponse {
  // From get_metadata_index_status (job stats)
  path: string;
  total: number;
  indexed_photos: number;
  metadata_records: number;
  missing_metadata_records?: number;
  counts: Record<string, number>;
  queued: number;
  running: number;
  done: number;
  failed: number;
  stale: number;
  skipped: number;
  oldest_queued_age_seconds: number | null;
  last_error: { path: string; message: string; updated_at: number } | null;
  updated_at: number | null;

  // From get_indexer_runtime_status
  enabled: boolean;
  worker_count: number;
  active_jobs: number;
  runtime_queue_depth: number;
  coalesced_duplicates: number;
  staged_path_queue_depth: number;
  staged_path_coalesced: number;
  staged_path_failed: number;
  staged_path_flushes_forced: number;
  staged_path_worker_count: number;
  active_scan_requests: number;
  batch_size: number;
  staged_path_batch_size: number;
  stage_max_wait_seconds: number;
  scope?: IndexStatusScope;
  global_runtime?: IndexStatusRuntime;
}

export interface IndexStatusRuntime {
  enabled: boolean;
  worker_count: number;
  active_jobs: number;
  runtime_queue_depth: number;
  coalesced_duplicates: number;
  staged_path_queue_depth: number;
  staged_path_coalesced: number;
  staged_path_failed: number;
  staged_path_flushes_forced: number;
  staged_path_worker_count: number;
  active_scan_requests: number;
  batch_size: number;
  staged_path_batch_size: number;
  stage_max_wait_seconds: number;
}

export interface IndexStatusScope {
  path: string;
  total: number;
  indexed_photos: number;
  metadata_records: number;
  missing_metadata_records?: number;
  counts: Record<string, number>;
  queued: number;
  running: number;
  done: number;
  failed: number;
  stale: number;
  skipped: number;
  oldest_queued_age_seconds: number | null;
  last_error: { path: string; message: string; updated_at: number } | null;
  updated_at: number | null;
  active_jobs: number;
  runtime_queue_depth: number;
  staged_path_queue_depth: number;
  active_scan_requests: number;
  active_rebuilds?: number;
}

export type IndexStatusState = "failed" | "active" | "queued" | "idle" | "unavailable" | "disabled";

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

export interface LibraryProgress {
  indexed_assets: number;
  estimated_assets: number;
  discovery_complete: boolean;
  library_state: LibraryState;
  active_job_id?: number | null;
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
  state: string;
}

export interface LibraryRepairResponse {
  library_id: number;
  job_id?: number;
  added: number;
  removed: number;
  modified: number;
}

export interface LibraryInspectorResource {
  name?: string;
  hash?: string | null;
  resource_hash?: string | null;
  weight?: string | number | null;
  strength?: string | number | null;
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
