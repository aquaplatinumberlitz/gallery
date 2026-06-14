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
}

export type SortField = "name" | "date";
export type SortOrder = "asc" | "desc";

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
  folders: FileNode[];
  images: FileNode[];
  next_cursor: number | null;
  total_images: number;
  request_path?: string;
}

export type FolderChildrenResponse = FileNode[];

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
}
